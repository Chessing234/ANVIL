"""Tests for ``NarrativeGenerationAgent``."""

from __future__ import annotations

from uuid import uuid4

import pytest

from agents.teaching.narrative_generation import NarrativeGenerationAgent
from config.constants import IncidentSeverity
from core.message_bus import MessageBus
from shared.models import Incident, InvestigationStep, StudentProfile


@pytest.mark.asyncio
async def test_generate_narrative_completeness_and_standards() -> None:
    bus = MessageBus()
    iid = uuid4()
    inc = Incident(
        id=iid,
        title="Suspicious DNS",
        description="Possible dns tunnel data exfiltration case study",
        severity=IncidentSeverity.HIGH,
    )
    steps = [
        InvestigationStep(
            incident_id=iid,
            agent_name="defense",
            action_taken="dns_analysis",
            tool_used="tshark",
            interpretation="long subdomains to rare resolver",
            raw_output="query length spike",
            confidence=0.77,
        ),
        InvestigationStep(
            incident_id=iid,
            agent_name="defense",
            action_taken="containment",
            tool_used="firewall",
            interpretation="blocked resolver IP",
            raw_output="203.0.113.9",
            confidence=0.9,
        ),
    ]
    profile = StudentProfile(name="Taylor", experience_level="beginner", preferred_learning_style="visual")
    agent = NarrativeGenerationAgent(bus, {})
    result = await agent.generate_narrative(steps, inc, profile)
    assert result.title
    assert result.story.arc.rising_action
    assert result.interactive_elements
    kinds = [e.kind for e in result.interactive_elements]
    assert len(set(kinds)) >= 2
    assert result.csta_standards
    assert result.concepts_taught
    assert result.estimated_duration_minutes >= 12
    assert "jigsaw" in result.teacher_notes.lower() or "mentor" in result.teacher_notes.lower()


@pytest.mark.asyncio
async def test_generate_narrative_ransomware_template() -> None:
    bus = MessageBus()
    iid = uuid4()
    inc = Incident(
        id=iid,
        title="Ransomware",
        description="encrypted files bitcoin ransom note",
        severity=IncidentSeverity.CRITICAL,
    )
    steps = [
        InvestigationStep(
            incident_id=iid,
            agent_name="defense",
            action_taken="backup_check",
            tool_used="immutability_scan",
            interpretation="immutable backup verified",
            raw_output="ok",
            confidence=0.95,
        ),
    ]
    agent = NarrativeGenerationAgent(bus, {})
    result = await agent.generate_narrative(
        steps,
        inc,
        StudentProfile(name="Riley", experience_level="advanced"),
    )
    assert "Locked" in result.title or "Case" in result.title
    assert len(result.csta_standards) >= 1
