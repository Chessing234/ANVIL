"""UiPath Maestro / Orchestrator integration tests."""

from __future__ import annotations

import asyncio
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from config.constants import EventType, IncidentSeverity, LessonDifficulty, MessageBusTopics
from core.message_bus import MessageBus
from platforms.uipath.agent_bridge import AgentBridge
from platforms.uipath.attended_automation import AttendedAutomation, ContainmentAction
from platforms.uipath.maestro_orchestrator import (
    MaestroOrchestrator,
    TUTORIAL_QUEUE_ROBOT_INBOUND,
    TUTORIAL_QUEUE_SECURITY_INCIDENTS,
)
from platforms.uipath.unattended_runner import UnattendedRunner
from platforms.uipath.workflow_generator import WorkflowGenerator
from shared.models import Incident, Lesson, Message


@pytest.fixture
def mock_maestro() -> MaestroOrchestrator:
    return MaestroOrchestrator(
        "https://mock.uipath.com",
        tenant_name="tenant",
        organization_name="org",
        mock=True,
    )


@pytest.mark.asyncio
async def test_maestro_queue_and_job(mock_maestro: MaestroOrchestrator) -> None:
    qid = await mock_maestro.create_queue_item(
        TUTORIAL_QUEUE_SECURITY_INCIDENTS,
        {"title": "Test", "description": "Malware on host", "severity": "high"},
        priority="High",
    )
    assert qid
    items = await mock_maestro.get_queue_items(TUTORIAL_QUEUE_SECURITY_INCIDENTS)
    assert len(items) == 1
    job = await mock_maestro.start_job("Tutorial.IncidentResponse")
    st = await mock_maestro.get_job_status(job)
    assert st.state == "Running"
    robots = await mock_maestro.get_robots()
    assert len(robots) >= 1


@pytest.mark.asyncio
async def test_agent_bridge_tutorial_to_uipath(mock_maestro: MaestroOrchestrator) -> None:
    bus = MessageBus()
    bridge = AgentBridge(mock_maestro, bus, poll_interval_seconds=0.05)
    await bridge.start_sync()
    msg = Message(
        topic=MessageBusTopics.SYSTEM,
        payload={
            "event": EventType.INVESTIGATION_STARTED.value,
            "title": "Bridge test",
            "description": "Investigation kickoff",
            "severity": "high",
        },
        source_agent="test",
    )
    await bus.publish(MessageBusTopics.SYSTEM, msg)
    await asyncio.sleep(0.15)
    pending = await mock_maestro.get_queue_items(TUTORIAL_QUEUE_SECURITY_INCIDENTS)
    assert len(pending) >= 1
    await bridge.stop_sync()


@pytest.mark.asyncio
async def test_agent_bridge_uipath_to_tutorial(mock_maestro: MaestroOrchestrator) -> None:
    bus = MessageBus()
    await bus.start()
    received: list[Message] = []

    async def cb(m: Message) -> None:
        received.append(m)

    bus.subscribe(MessageBusTopics.EVIDENCE, cb)
    bridge = AgentBridge(mock_maestro, bus, poll_interval_seconds=0.05)
    await bridge.start_sync()
    await mock_maestro.create_queue_item(
        TUTORIAL_QUEUE_ROBOT_INBOUND,
        {"robot_event": "evidence_ingest", "path": "/evidence/dump.mem"},
        priority="Normal",
    )
    await asyncio.sleep(0.15)
    assert any("uipath" in m.payload for m in received)
    await bridge.stop_sync()


@pytest.fixture
def incident_malware() -> Incident:
    return Incident(
        title="Malware outbreak",
        description="Trojan observed on finance workstations.",
        severity=IncidentSeverity.HIGH,
    )


@pytest.mark.asyncio
async def test_workflow_generator_bpmn(incident_malware: Incident) -> None:
    gen = WorkflowGenerator(escalation_minutes=30)
    wf = await gen.generate_workflow(incident_malware)
    assert wf.workflow_type == "malware"
    ET.fromstring(wf.bpmn_xml)
    assert "MemoryAnalysis" in wf.parallel_stages


@pytest.mark.asyncio
async def test_attended_automation_non_blocking() -> None:
    att = AttendedAutomation()
    await att.show_investigation_summary("inc-123")
    await asyncio.sleep(0.05)
    assert att.assistant_snapshot().investigation_cards
    approved = await att.prompt_for_approval(
        ContainmentAction(name="Isolate host", detail="Isolate host-01", requires_human_approval=True),
    )
    assert approved is False


@pytest.mark.asyncio
async def test_unattended_runner_processes_queue(mock_maestro: MaestroOrchestrator) -> None:
    await mock_maestro.create_queue_item(
        TUTORIAL_QUEUE_SECURITY_INCIDENTS,
        {
            "title": "Queued incident",
            "description": "Ransomware-like behavior",
            "severity": "critical",
        },
        priority="Critical",
    )
    runner = UnattendedRunner(mock_maestro, WorkflowGenerator(), monitor_interval_seconds=0.05)
    await runner.start_monitoring()
    await asyncio.sleep(0.15)
    await runner.stop_monitoring()
    remaining = await mock_maestro.get_queue_items(TUTORIAL_QUEUE_SECURITY_INCIDENTS)
    assert len(remaining) == 0


def test_security_xaml_files_parse() -> None:
    root = Path(__file__).resolve().parents[2] / "platforms" / "uipath" / "security_workflows"
    for name in (
        "incident_response.xaml",
        "threat_hunting.xaml",
        "evidence_collection.xaml",
        "lesson_generation.xaml",
    ):
        text = (root / name).read_text(encoding="utf-8")
        ET.fromstring(text)


@pytest.mark.asyncio
async def test_attended_lesson_preview() -> None:
    att = AttendedAutomation()
    inc = Incident(
        title="t",
        description="d" * 20,
        severity=IncidentSeverity.LOW,
    )
    lesson = Lesson(
        incident_id=inc.id,
        title="Lesson",
        narrative="n" * 30,
        difficulty=LessonDifficulty.BEGINNER,
    )
    await att.display_lesson_preview(lesson)
    await asyncio.sleep(0.05)
    assert att.assistant_snapshot().lesson_previews
