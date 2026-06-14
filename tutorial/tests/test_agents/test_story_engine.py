"""Tests for ``StoryEngine`` arc construction."""

from __future__ import annotations

from uuid import uuid4

import pytest

from agents.teaching.story_engine import StoryEngine
from agents.teaching.tools.narrative_templates import infer_incident_category, select_template
from config.constants import IncidentSeverity
from shared.models import Incident, InvestigationStep


def _steps(incident_id):
    s1 = InvestigationStep(
        incident_id=incident_id,
        agent_name="defense",
        action_taken="log_correlation",
        tool_used="splunk",
        interpretation="multiple 4625 failures",
        raw_output="fail fail",
        confidence=0.8,
    )
    s2 = InvestigationStep(
        incident_id=incident_id,
        agent_name="defense",
        action_taken="network_analysis",
        tool_used="tshark",
        interpretation="dns tunneling indicators",
        raw_output="long dns queries",
        confidence=0.82,
    )
    return [s1, s2]


@pytest.mark.asyncio
async def test_create_arc_maps_all_investigation_steps() -> None:
    iid = uuid4()
    inc = Incident(
        id=iid,
        title="DNS exfiltration case",
        description="Unusual outbound dns traffic data exfiltration",
        severity=IncidentSeverity.HIGH,
    )
    steps = _steps(iid)
    engine = StoryEngine()
    arc = engine.create_arc(steps, inc, student_level="intermediate")
    refs = {arc.setup.investigation_step_ref}
    refs.update(s.investigation_step_ref for s in arc.rising_action)
    refs.update(s.investigation_step_ref for s in arc.falling_action)
    refs.add(arc.climax.investigation_step_ref)
    refs.add(arc.resolution.investigation_step_ref)
    refs.discard(None)
    assert {str(s.id) for s in steps}.issubset(refs)


@pytest.mark.asyncio
async def test_infer_template_ransomware() -> None:
    inc = Incident(
        id=uuid4(),
        title="Ransomware outbreak",
        description="files encrypted bitcoin ransom",
        severity=IncidentSeverity.CRITICAL,
    )
    assert infer_incident_category(inc) == "ransomware"
    tpl = select_template("ransomware")
    assert "Locked" in tpl.title


@pytest.mark.asyncio
async def test_wrap_story_synopsis() -> None:
    iid = uuid4()
    inc = Incident(
        id=iid,
        title="Malware",
        description="trojan infection",
        severity=IncidentSeverity.MEDIUM,
    )
    engine = StoryEngine()
    tpl = select_template(infer_incident_category(inc))
    arc = engine.create_arc(_steps(iid), inc)
    story = engine.wrap_story(arc, inc, tpl)
    assert "detective" in story.detective_hook.lower()
    assert inc.title in story.synopsis or "case" in story.synopsis.lower()
