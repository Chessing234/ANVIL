"""Top-level orchestration entry point coordinating agents, workflows, and events."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog

from config.constants import AgentType, MessageBusTopics
from config.settings import Settings, get_settings
from core.message_bus import MessageBus, get_message_bus
from events import handlers as event_handlers
from events.context import bind_coordinator, clear_coordinator
from events.router import EventRouter
from orchestration.agent_pool import AgentPool
from orchestration.defense_workflow import DefenseWorkflow, initial_defense_state
from orchestration.knowledge_flywheel import KnowledgeFlywheel
from orchestration.store import OrchestrationStore
from orchestration.teaching_workflow import TeachingWorkflow, initial_teaching_state
from shared.models import (
    Incident,
    IncidentStatus,
    IncidentTicket,
    LessonStatus,
    LessonTicket,
    Message,
    StudentProfile,
    SystemHealth,
)
from core.base_agent import BaseAgent

logger = structlog.get_logger(__name__)


class _StubAgent(BaseAgent):
    """Lightweight pool placeholder used until real agents are registered."""

    def __init__(self, agent_type: AgentType, bus: MessageBus) -> None:
        super().__init__(f"stub-{agent_type.value}-{uuid.uuid4().hex[:10]}", agent_type, bus, {})
        self._ticks = 0

    async def _run_iteration(self) -> None:
        self._ticks += 1
        await asyncio.sleep(0)


class TutorialCoordinator:
    """Coordinates defense/teaching workflows, pooling, and bus routing."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        message_bus: MessageBus | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._bus = message_bus
        self._store = OrchestrationStore(self._settings.orchestration.persistence_db_path)
        self._pool = AgentPool(self._settings)
        self._flywheel = KnowledgeFlywheel(self._store)
        self._router = EventRouter()
        self._initialized = False
        self._shutdown = False
        self._bus_subscription_id: str | None = None
        self._incidents: dict[str, IncidentStatus] = {}
        self._lessons: dict[str, LessonStatus] = {}
        self._heartbeat_samples: list[dict[str, Any]] = []

    async def initialize(self) -> None:
        """Start the bus, persistence, pool, and event routing."""

        if self._initialized:
            return
        self._bus = self._bus or await get_message_bus(
            max_queue_size=self._settings.message_bus.max_queue_size,
            message_ttl_seconds=self._settings.message_bus.message_ttl_seconds,
        )
        await self._bus.start()
        await asyncio.to_thread(self._store.initialize)
        await self._flywheel.load_graph()
        event_handlers.setup_router(self._router)
        bind_coordinator(self)
        self._bus_subscription_id = self._bus.subscribe(MessageBusTopics.SYSTEM, self._dispatch_event)
        await self._register_default_stub_factories()
        await self._pool.start_health_monitor()
        self._flywheel.set_defense_complete_handler(self._auto_queue_teaching)
        for agent_type in AgentType:
            try:
                await self._pool.scale(agent_type, 1)
            except Exception as exc:
                logger.warning("pool_prewarm_skipped", agent_type=str(agent_type), error=str(exc))
        self._initialized = True
        logger.info("tutorial_coordinator_initialized")

    async def _register_default_stub_factories(self) -> None:
        """Ensure every ``AgentType`` has a creatable factory."""

        for agent_type in AgentType:

            def _factory(at: AgentType = agent_type) -> BaseAgent:
                return _StubAgent(at, self._bus)

            self._pool.register_factory(agent_type, _factory)

    async def _dispatch_event(self, message: Message) -> None:
        """Forward bus messages to the ``EventRouter``."""

        await self._router.route(message)

    async def _auto_queue_teaching(self, incident_id: str) -> None:
        """Default hook that queues teaching after defense completes."""

        profile = StudentProfile(name="auto-learner", experience_level="intermediate")
        await self.submit_lesson_request(incident_id, profile)

    async def submit_incident(self, incident: Incident) -> IncidentTicket:
        """Execute the defense workflow for ``incident``."""

        if not self._initialized:
            raise RuntimeError("coordinator not initialized")
        incident_id = str(incident.id)
        ticket = IncidentTicket(
            incident_id=incident.id,
            status="running",
            defense_thread_id=incident_id,
        )
        self._incidents[incident_id] = IncidentStatus(
            incident_id=incident_id,
            ticket=ticket,
            defense_trace=[],
            latest_state={},
        )

        async def persist(state: dict[str, Any]) -> None:
            current = self._incidents[incident_id]
            trace = list(current.defense_trace) + [{"checkpoint": state.get("current_step")}]
            latest = dict(state)
            status = "running"
            if state.get("completed"):
                status = "completed"
            elif state.get("accuracy_report", {}).get("__fatal"):
                status = "failed"
            self._incidents[incident_id] = current.model_copy(
                update={"defense_trace": trace, "latest_state": latest, "ticket": current.ticket.model_copy(update={"status": status})},
            )
            await asyncio.to_thread(
                self._store.upsert_incident,
                incident_id,
                self._incidents[incident_id].ticket.model_dump(mode="json"),
                latest,
                trace,
                status,
            )

        async def on_event(kind: str, payload: dict[str, Any]) -> None:
            if kind == "defense_complete":
                await self._flywheel.on_defense_complete(payload["incident_id"])

        workflow = DefenseWorkflow(
            self._settings.orchestration.defense_checkpoint_db,
            on_persist=persist,
            on_event=on_event,
        )
        initial = initial_defense_state(incident)
        result = await workflow.run(initial, thread_id=incident_id)
        trace = result.get("trace", [])
        final_state = result.get("final_state", {})
        final_status = "completed" if final_state.get("completed") else "failed"
        final_ticket = ticket.model_copy(update={"status": final_status})
        self._incidents[incident_id] = IncidentStatus(
            incident_id=incident_id,
            ticket=final_ticket,
            defense_trace=trace,
            latest_state=final_state,
        )
        await asyncio.to_thread(
            self._store.upsert_incident,
            incident_id,
            final_ticket.model_dump(mode="json"),
            final_state,
            trace,
            final_status,
        )
        return final_ticket

    async def submit_lesson_request(self, incident_id: str, student_profile: StudentProfile) -> LessonTicket:
        """Execute the teaching workflow anchored to ``incident_id``."""

        if not self._initialized:
            raise RuntimeError("coordinator not initialized")
        row = await asyncio.to_thread(self._store.fetch_incident, incident_id)
        if row is None:
            raise ValueError(f"unknown incident: {incident_id}")
        latest = row["latest_state"]
        investigation_steps = list(latest.get("investigation_steps", []))
        narrative = str(latest.get("narrative", ""))
        incident_uuid = uuid.UUID(incident_id)
        lesson_uuid = uuid.uuid4()
        teaching_thread = f"{incident_id}:{lesson_uuid}"
        ticket = LessonTicket(
            incident_id=incident_uuid,
            teaching_thread_id=teaching_thread,
            lesson_id=lesson_uuid,
            status="running",
        )
        lesson_id = str(ticket.lesson_id)
        self._lessons[lesson_id] = LessonStatus(
            lesson_id=lesson_id,
            ticket=ticket,
            teaching_trace=[],
            latest_state={},
        )

        async def persist(state: dict[str, Any]) -> None:
            current = self._lessons[lesson_id]
            trace = list(current.teaching_trace) + [{"checkpoint": state.get("current_step")}]
            latest = dict(state)
            status = "running"
            if state.get("completed"):
                status = "completed"
            elif state.get("errors"):
                status = "failed"
            updated_ticket = current.ticket.model_copy(update={"status": status})
            self._lessons[lesson_id] = current.model_copy(
                update={"teaching_trace": trace, "latest_state": latest, "ticket": updated_ticket},
            )
            await asyncio.to_thread(
                self._store.upsert_lesson,
                lesson_id,
                incident_id,
                updated_ticket.model_dump(mode="json"),
                latest,
                trace,
                status,
            )

        async def on_event(kind: str, payload: dict[str, Any]) -> None:
            if kind == "lesson_complete":
                await self._flywheel.on_lesson_complete(payload["lesson_id"])

        workflow = TeachingWorkflow(
            self._settings.orchestration.teaching_checkpoint_db,
            on_persist=persist,
            on_event=on_event,
        )
        initial = initial_teaching_state(incident_id, investigation_steps, narrative, student_profile)
        result = await workflow.run(initial, thread_id=teaching_thread)
        trace = result.get("trace", [])
        from_graph = dict(result.get("final_state", {}))
        from_memory = dict(self._lessons[lesson_id].latest_state)
        final_state = from_memory if from_memory else from_graph
        if not isinstance(final_state.get("lesson"), dict) and isinstance(from_graph.get("lesson"), dict):
            final_state["lesson"] = from_graph["lesson"]
        status = "completed" if final_state.get("completed") else "failed"
        final_lesson_ticket = self._lessons[lesson_id].ticket.model_copy(update={"status": status})
        self._lessons[lesson_id] = LessonStatus(
            lesson_id=lesson_id,
            ticket=final_lesson_ticket,
            teaching_trace=trace,
            latest_state=final_state,
        )
        await asyncio.to_thread(
            self._store.upsert_lesson,
            lesson_id,
            incident_id,
            final_lesson_ticket.model_dump(mode="json"),
            final_state,
            trace,
            status,
        )
        return final_lesson_ticket

    async def get_system_health(self) -> SystemHealth:
        """Aggregate coordinator, pool, and bus health."""

        bus_stats: dict[str, Any] = {}
        if self._bus:
            bus_stats = self._bus.get_stats()
        agents = await self._pool.iter_agents()
        metrics = [agent.metrics for agent in agents]
        stats = self._flywheel.graph_stats()
        pending = sum(1 for s in self._incidents.values() if s.ticket.status != "completed")
        active_lessons = sum(1 for s in self._lessons.values() if s.ticket.status not in {"completed", "failed"})
        return SystemHealth(
            all_agents=metrics,
            message_bus_stats=bus_stats,
            pending_incidents=pending,
            active_lessons=active_lessons,
            knowledge_graph_nodes=stats["nodes"],
            knowledge_graph_edges=stats["edges"],
        )

    async def get_flywheel_snapshot(self) -> dict[str, Any]:
        """Expose orchestration-layer graph stats, insights, and learning signals for health/E2E."""

        return {
            "graph_stats": self._flywheel.graph_stats(),
            "defense_insights": await self._flywheel.get_defense_insights(),
            "learning_signals": await self._flywheel.collect_learning_signals(),
        }

    async def reload_knowledge_graph(self) -> None:
        """Reload the flywheel graph snapshot from orchestration storage."""

        await self._flywheel.load_graph()

    async def get_incident_status(self, incident_id: str) -> IncidentStatus:
        """Return the latest incident orchestration snapshot."""

        if incident_id in self._incidents:
            return self._incidents[incident_id]
        row = await asyncio.to_thread(self._store.fetch_incident, incident_id)
        if row is None:
            raise KeyError(incident_id)
        ticket = IncidentTicket.model_validate(row["ticket"])
        return IncidentStatus(
            incident_id=incident_id,
            ticket=ticket,
            defense_trace=row["trace"],
            latest_state=row["latest_state"],
        )

    async def get_lesson_status(self, lesson_id: str) -> LessonStatus:
        """Return the latest lesson orchestration snapshot."""

        if lesson_id in self._lessons:
            return self._lessons[lesson_id]
        row = await asyncio.to_thread(self._store.fetch_lesson, lesson_id)
        if row is None:
            raise KeyError(lesson_id)
        ticket = LessonTicket.model_validate(row["ticket"])
        return LessonStatus(
            lesson_id=lesson_id,
            ticket=ticket,
            teaching_trace=row["trace"],
            latest_state=row["latest_state"],
        )

    async def record_investigation_started(self, incident_id: str) -> None:
        """Update incident registry when investigations begin."""

        if incident_id in self._incidents:
            current = self._incidents[incident_id]
            ticket = current.ticket.model_copy(update={"status": "investigating"})
            self._incidents[incident_id] = current.model_copy(update={"ticket": ticket})

    async def record_evidence(self, payload: dict[str, Any]) -> None:
        """Validate evidence hashes from bus events."""

        evidence_hash = str(payload.get("hash_sha256", ""))
        if evidence_hash and len(evidence_hash) != 64:
            logger.error("evidence_hash_invalid", hash=evidence_hash)
            return
        logger.info("evidence_recorded", payload=payload)

    async def record_containment(self, payload: dict[str, Any]) -> None:
        """Persist containment notifications."""

        logger.info("containment_recorded", payload=payload)

    async def handle_lesson_generated_event(self, payload: dict[str, Any]) -> None:
        """Process ``LESSON_GENERATED`` bus events."""

        lesson_id = str(payload.get("lesson_id", uuid.uuid4()))
        await self._flywheel.on_lesson_generated(lesson_id, payload)

    async def handle_lesson_completed_event(self, payload: dict[str, Any]) -> None:
        """Process ``LESSON_COMPLETED`` bus events."""

        lesson_id = str(payload.get("lesson_id", ""))
        if lesson_id:
            await self._flywheel.on_lesson_complete(lesson_id)

    async def handle_agent_error_event(self, payload: dict[str, Any]) -> None:
        """Escalate agent failures."""

        logger.error("agent_error_event", payload=payload)

    async def record_system_heartbeat(self, payload: dict[str, Any]) -> None:
        """Track heartbeat payloads for dashboards."""

        self._heartbeat_samples.append({"ts": datetime.now(timezone.utc).isoformat(), "payload": payload})
        self._heartbeat_samples = self._heartbeat_samples[-200:]

    async def shutdown(self) -> None:
        """Gracefully stop orchestration components."""

        if self._shutdown:
            return
        self._shutdown = True
        if self._bus_subscription_id is not None and self._bus is not None:
            self._bus.unsubscribe(self._bus_subscription_id)
            self._bus_subscription_id = None
        await self._pool.stop_health_monitor()
        await self._pool.drain()
        clear_coordinator()
        self._initialized = False
        logger.info("tutorial_coordinator_shutdown")
