"""Async handlers for every ``EventType`` published on the bus."""

from __future__ import annotations

import structlog

from config.constants import EventType
from events.context import get_coordinator
from events.router import EventRouter
from shared.models import Incident, Message

logger = structlog.get_logger(__name__)


async def handle_incident_detected(event: Message) -> None:
    """Submit new incidents to the coordinator."""

    payload = event.payload
    incident_payload = payload.get("incident")
    if incident_payload is None:
        logger.warning("incident_detected_missing_payload")
        return
    incident = Incident.model_validate(incident_payload)
    await get_coordinator().submit_incident(incident)


async def handle_investigation_started(event: Message) -> None:
    """Track investigation lifecycle."""

    incident_id = str(event.payload.get("incident_id", ""))
    logger.info("investigation_started", incident_id=incident_id, source=event.source_agent)
    if incident_id:
        await get_coordinator().record_investigation_started(incident_id)


async def handle_evidence_collected(event: Message) -> None:
    """Validate evidence metadata and persist custody extensions."""

    await get_coordinator().record_evidence(dict(event.payload))


async def handle_containment_executed(event: Message) -> None:
    """Log containment and notify stakeholders."""

    logger.info("containment_executed", payload=event.payload)
    await get_coordinator().record_containment(dict(event.payload))


async def handle_lesson_generated(event: Message) -> None:
    """Kick off knowledge flywheel processing."""

    await get_coordinator().handle_lesson_generated_event(dict(event.payload))


async def handle_lesson_completed(event: Message) -> None:
    """Update learner models and knowledge graph."""

    await get_coordinator().handle_lesson_completed_event(dict(event.payload))


async def handle_agent_error(event: Message) -> None:
    """Attempt recovery orchestration."""

    await get_coordinator().handle_agent_error_event(dict(event.payload))


async def handle_system_heartbeat(event: Message) -> None:
    """Refresh health aggregates."""

    await get_coordinator().record_system_heartbeat(dict(event.payload))


def setup_router(router: EventRouter) -> None:
    """Register all known ``EventType`` handlers."""

    router.register(EventType.INCIDENT_DETECTED, handle_incident_detected)
    router.register(EventType.INVESTIGATION_STARTED, handle_investigation_started)
    router.register(EventType.EVIDENCE_COLLECTED, handle_evidence_collected)
    router.register(EventType.CONTAINMENT_EXECUTED, handle_containment_executed)
    router.register(EventType.LESSON_GENERATED, handle_lesson_generated)
    router.register(EventType.LESSON_COMPLETED, handle_lesson_completed)
    router.register(EventType.AGENT_ERROR, handle_agent_error)
    router.register(EventType.SYSTEM_HEARTBEAT, handle_system_heartbeat)

    async def default_handler(message: Message) -> None:
        logger.debug("event_default_handler", topic=message.topic, payload=message.payload)

    router.register_default(default_handler)
