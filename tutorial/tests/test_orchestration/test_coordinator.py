"""Tests for ``TutorialCoordinator``."""

from __future__ import annotations

import pytest

from config.constants import IncidentSeverity
from config.settings import Settings, get_settings
from core.message_bus import MessageBus
from events.context import clear_coordinator
from orchestration.coordinator import TutorialCoordinator
from shared.models import Incident, Message, StudentProfile


@pytest.fixture
def settings(tmp_path) -> Settings:
    """Fresh settings pointing databases into ``tmp_path``."""

    get_settings.cache_clear()
    return Settings(
        orchestration__persistence_db_path=tmp_path / "orch.db",
        orchestration__defense_checkpoint_db=tmp_path / "def.sqlite",
        orchestration__teaching_checkpoint_db=tmp_path / "teach.sqlite",
        orchestration__max_agents_per_type=2,
    )


@pytest.mark.asyncio
async def test_coordinator_submit_incident_and_lesson(settings: Settings) -> None:
    """Defense and teaching workflows persist through the coordinator."""

    bus = MessageBus()
    await bus.start()
    coord = TutorialCoordinator(settings=settings, message_bus=bus)
    await coord.initialize()
    coord._flywheel.set_defense_complete_handler(None)
    incident = Incident(
        title="Sample incident",
        description="Suspicious outbound traffic",
        severity=IncidentSeverity.LOW,
    )
    ticket = await coord.submit_incident(incident)
    assert ticket.status == "completed"
    status = await coord.get_incident_status(str(incident.id))
    assert status.defense_trace
    profile = StudentProfile(name="learner", experience_level="beginner")
    lesson_ticket = await coord.submit_lesson_request(str(incident.id), profile)
    assert lesson_ticket.status == "completed"
    lesson_status = await coord.get_lesson_status(str(lesson_ticket.lesson_id))
    assert lesson_status.teaching_trace
    health = await coord.get_system_health()
    assert health.knowledge_graph_nodes >= 0
    await coord.shutdown()
    clear_coordinator()
    await bus.stop()
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_coordinator_routes_system_events(settings: Settings) -> None:
    """Router executes registered handlers."""

    bus = MessageBus()
    await bus.start()
    coord = TutorialCoordinator(settings=settings, message_bus=bus)
    await coord.initialize()
    coord._flywheel.set_defense_complete_handler(None)
    msg = Message(
        topic="tutorial.system",
        payload={"event": "system_heartbeat", "agent": "test", "metrics": {}},
        source_agent="test",
    )
    await coord._dispatch_event(msg)
    stats = coord._router.get_handler_stats()
    assert any(stats[k]["calls"] > 0 for k in stats)
    await coord.shutdown()
    clear_coordinator()
    await bus.stop()
    get_settings.cache_clear()
