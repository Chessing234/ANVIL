"""Tests for remediation agent and planner."""

from __future__ import annotations

from uuid import uuid4

import pytest

from agents.defense.remediation import RemediationAgent, RemediationPlanner
from config.constants import IncidentSeverity
from core.message_bus import MessageBus
from shared.models import Incident, IncidentContainmentResult


@pytest.mark.asyncio
async def test_remediation_planner_malware_path() -> None:
    planner = RemediationPlanner(require_staging_patch=True)
    inc = Incident(
        id=uuid4(),
        title="Malware",
        description="trojan infection on endpoint",
        severity=IncidentSeverity.MEDIUM,
    )
    containment = IncidentContainmentResult(
        incident_id=inc.id,
        actions_taken=[],
        rollback_plan="undo firewall",
        estimated_impact="low",
        narrative="malware removed from host",
    )
    plan = planner.build_plan(inc, containment)
    assert any("Patch" in s.title or "patch" in s.title.lower() for s in plan)
    assert any("cleanup" in s.title.lower() or "artifact" in s.title.lower() for s in plan)


@pytest.mark.asyncio
async def test_remediation_planner_ransomware_path() -> None:
    planner = RemediationPlanner()
    inc = Incident(
        id=uuid4(),
        title="Ransomware",
        description="encrypted files ransomware",
        severity=IncidentSeverity.CRITICAL,
    )
    containment = IncidentContainmentResult(
        incident_id=inc.id,
        actions_taken=[],
        rollback_plan="r",
        estimated_impact="high",
        narrative="ransom note found",
    )
    plan = planner.build_plan(inc, containment)
    assert any("backup" in s.title.lower() for s in plan)


@pytest.mark.asyncio
async def test_remediation_agent_remediate() -> None:
    bus = MessageBus()
    inc = Incident(
        id=uuid4(),
        title="Cleanup",
        description="malware",
        severity=IncidentSeverity.LOW,
    )
    containment = IncidentContainmentResult(
        incident_id=inc.id,
        actions_taken=[],
        rollback_plan="rollback",
        estimated_impact="low",
        narrative="contained",
    )
    agent = RemediationAgent(bus, {"dry_run": True})
    res = await agent.remediate(inc, containment)
    assert res.incident_id == inc.id
    assert res.plan_executed
    assert "dry-run" in res.verification_result.lower()
    assert res.time_to_remediate_seconds >= 0.0
