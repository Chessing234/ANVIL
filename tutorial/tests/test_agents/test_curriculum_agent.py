"""Tests for curriculum integration and CSTA traceability."""

from __future__ import annotations

from uuid import uuid4

import pytest

from agents.teaching.curriculum_integration import CurriculumIntegrationAgent
from agents.teaching.narrative_generation import NarrativeGenerationAgent
from agents.teaching.sandbox_generation import SandboxGenerationAgent
from agents.teaching.education_models import Sandbox, SandboxStatus, Challenge, LessonDifficulty
from config.constants import IncidentSeverity
from core.message_bus import MessageBus
from shared.models import Incident, InvestigationStep, StudentProfile


@pytest.mark.asyncio
async def test_map_curriculum_traceability(tmp_path) -> None:
    bus = MessageBus()
    iid = uuid4()
    inc = Incident(
        id=iid,
        title="Network anomaly",
        description="protocol analysis training",
        severity=IncidentSeverity.HIGH,
    )
    steps = [
        InvestigationStep(
            incident_id=iid,
            agent_name="defense",
            action_taken="pcap_review",
            tool_used="tshark",
            interpretation="suspicious TLS fingerprint",
            raw_output="ja3=…",
            confidence=0.7,
        ),
    ]
    narrative = await NarrativeGenerationAgent(bus, {}).generate_narrative(
        steps,
        inc,
        StudentProfile(name="Sam", experience_level="intermediate"),
    )
    cfg = {"sandbox_workspace_root": str(tmp_path / "sbx"), "csta_grade_band": "9-12"}
    sandbox = await SandboxGenerationAgent(bus, cfg).generate_sandbox(steps, narrative)
    mapping = await CurriculumIntegrationAgent(bus, cfg).map_curriculum(narrative, sandbox)
    assert mapping.standards_covered
    assert mapping.learning_objectives
    assert mapping.assessment_rubric.criteria
    assert mapping.recommended_sequence
    for cov in mapping.standards_covered:
        assert cov.standard.id
        assert cov.lesson_segments
        assert cov.standard.description

    from agents.teaching.tools.sandbox_builder import SandboxBuilder

    await SandboxBuilder(cfg).destroy(sandbox.container_id)


@pytest.mark.asyncio
async def test_minimal_sandbox_curriculum_stub(tmp_path) -> None:
    """Curriculum agent tolerates minimal sandbox metadata."""

    bus = MessageBus()
    iid = uuid4()
    inc = Incident(
        id=iid,
        title="T",
        description="d",
        severity=IncidentSeverity.LOW,
    )
    steps = [
        InvestigationStep(
            incident_id=iid,
            agent_name="a",
            action_taken="act",
            raw_output="encryption discussion",
            confidence=0.5,
        ),
    ]
    narrative = await NarrativeGenerationAgent(bus, {}).generate_narrative(
        steps,
        inc,
        StudentProfile(name="Q", experience_level="beginner"),
    )
    sandbox = Sandbox(
        id="stub",
        incident_id=str(iid),
        status=SandboxStatus.READY,
        challenges=[
            Challenge(
                id="c1",
                title="t",
                description="d",
                verification_type="find_file",
                verification_script="true",
                concept_tested="encryption",
                difficulty=LessonDifficulty.BEGINNER,
                points=5,
            ),
        ],
        sanitized=True,
    )
    m = await CurriculumIntegrationAgent(bus, {"csta_grade_band": "9-12"}).map_curriculum(narrative, sandbox)
    assert isinstance(m.recommended_sequence, list)
