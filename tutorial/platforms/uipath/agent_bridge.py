"""Bidirectional bridge between TUTORIAL message bus and UiPath Orchestrator queues."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog

from config.constants import EventType, MessageBusTopics
from core.message_bus import MessageBus
from platforms.uipath.maestro_orchestrator import (
    MaestroOrchestrator,
    QueueItem,
    TUTORIAL_QUEUE_EVIDENCE,
    TUTORIAL_QUEUE_HEALTH,
    TUTORIAL_QUEUE_LESSON,
    TUTORIAL_QUEUE_ROBOT_INBOUND,
    TUTORIAL_QUEUE_SECURITY_INCIDENTS,
    TUTORIAL_QUEUE_STUDENT,
)
from shared.models import Message

logger = structlog.get_logger(__name__)


def _priority_from_payload(payload: dict[str, Any]) -> str:
    sev = str(payload.get("severity", "")).lower()
    if sev == "critical":
        return "Critical"
    if sev == "high":
        return "High"
    return "Normal"


class AgentBridge:
    """Maps TUTORIAL ``Message`` envelopes to Orchestrator queue items and back."""

    def __init__(
        self,
        orchestrator: MaestroOrchestrator,
        message_bus: MessageBus,
        *,
        poll_interval_seconds: float = 5.0,
    ) -> None:
        self._orch = orchestrator
        self._bus = message_bus
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._sub_id: str | None = None
        self._poll_interval = max(0.05, poll_interval_seconds)

    def map_event_to_queue(self, event: str) -> str:
        """Route high-level event types to Maestro queue names."""

        if event in (EventType.INCIDENT_DETECTED.value, EventType.INVESTIGATION_STARTED.value):
            return TUTORIAL_QUEUE_SECURITY_INCIDENTS
        if event == EventType.EVIDENCE_COLLECTED.value:
            return TUTORIAL_QUEUE_EVIDENCE
        if event == EventType.LESSON_GENERATED.value:
            return TUTORIAL_QUEUE_LESSON
        if event == EventType.SYSTEM_HEARTBEAT.value:
            return TUTORIAL_QUEUE_HEALTH
        return TUTORIAL_QUEUE_STUDENT

    async def tutorial_to_uipath(self, event: Message) -> QueueItem:
        """Convert a TUTORIAL bus message into an Orchestrator queue item (and enqueue)."""

        payload = dict(event.payload)
        event_name = str(payload.get("event", ""))
        queue = self.map_event_to_queue(event_name)
        priority = _priority_from_payload(payload)
        due = datetime.now(timezone.utc) + timedelta(hours=6)
        data = {
            **payload,
            "correlation_id": str(event.correlation_id),
            "source_agent": event.source_agent,
            "due_date": due.isoformat(),
            "sla_hours": 6,
        }
        item_id = await self._orch.create_queue_item(queue, data, priority=priority)
        item = QueueItem(
            id=int(item_id) if item_id.isdigit() else None,
            queue_name=queue,
            status="New",
            priority=priority,
            due_date=due,
            data=data,
            correlation_id=str(event.correlation_id),
        )
        logger.info("bridge_tutorial_to_uipath", queue=queue, item_id=item_id)
        return item

    async def uipath_to_tutorial(self, queue_item: QueueItem) -> Message:
        """Translate robot-submitted queue payloads back into TUTORIAL bus messages."""

        data = dict(queue_item.data)
        kind = str(data.get("robot_event", "evidence_ingest"))
        topic = MessageBusTopics.EVIDENCE
        event_type = EventType.EVIDENCE_COLLECTED.value
        if kind == "endpoint_anomaly":
            topic = MessageBusTopics.INCIDENTS
            event_type = EventType.INCIDENT_DETECTED.value
        elif kind == "lesson_feedback":
            topic = MessageBusTopics.LESSONS
            event_type = EventType.LESSON_COMPLETED.value
        payload = {"event": event_type, "uipath": data, "queue": queue_item.queue_name}
        return Message(
            topic=topic,
            payload=payload,
            source_agent="uipath_robot",
            correlation_id=uuid.UUID(queue_item.correlation_id) if _is_uuid(queue_item.correlation_id) else uuid.uuid4(),
        )

    async def _on_bus_message(self, msg: Message) -> None:
        if self._stop.is_set():
            return
        try:
            ev = str(msg.payload.get("event", ""))
            if not ev or ev not in {e.value for e in EventType}:
                return
            await self.tutorial_to_uipath(msg)
        except Exception as exc:
            logger.error("bridge_outbound_failed", error=str(exc))

    async def _poll_robot_queue(self) -> None:
        while not self._stop.is_set():
            items = await self._orch.get_queue_items(TUTORIAL_QUEUE_ROBOT_INBOUND, status="New")
            for it in items:
                try:
                    msg = await self.uipath_to_tutorial(it)
                    await self._bus.publish(msg.topic, msg)
                    if it.id is not None:
                        await self._orch.dequeue_item(TUTORIAL_QUEUE_ROBOT_INBOUND, it.id)
                except Exception as exc:
                    logger.error("bridge_inbound_failed", error=str(exc))
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._poll_interval)
            except TimeoutError:
                continue

    async def start_sync(self) -> None:
        """Start outbound subscription and inbound queue polling."""

        await self._bus.start()
        self._stop.clear()
        self._sub_id = self._bus.subscribe(MessageBusTopics.SYSTEM, self._on_bus_message)
        self._task = asyncio.create_task(self._poll_robot_queue())
        logger.info("agent_bridge_sync_started")

    async def stop_sync(self) -> None:
        """Stop background synchronization."""

        self._stop.set()
        if self._sub_id:
            self._bus.unsubscribe(self._sub_id)
            self._sub_id = None
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self._bus.stop()
        await self._orch.close()
        logger.info("agent_bridge_sync_stopped")


def _is_uuid(val: str) -> bool:
    try:
        uuid.UUID(val)
        return True
    except ValueError:
        return False
