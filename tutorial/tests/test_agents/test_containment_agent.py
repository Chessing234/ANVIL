"""Tests for containment agent and executor safety."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from agents.defense.containment import ContainmentAgent, ContainmentExecutor
from agents.defense.tools.containment_tools import IPBlocker
from config.constants import IncidentSeverity
from core.message_bus import MessageBus
from shared.models import (
    ContainmentSafetyLevel,
    Hypothesis,
    Incident,
    InvestigationResult,
    InvestigationStep,
)


def _minimal_investigation(incident_id, narrative: str) -> InvestigationResult:
    return InvestigationResult(
        incident_id=incident_id,
        steps=[
            InvestigationStep(
                incident_id=incident_id,
                agent_name="inv",
                action_taken="t",
                raw_output=narrative,
                interpretation="",
                confidence=0.8,
            ),
        ],
        evidence_analyzed=[],
        hypotheses=[Hypothesis(text="malware on disk", rationale="r", confidence=0.7)],
        self_corrections=[],
        narrative=narrative,
        accuracy_report={},
        tools_used=[],
    )


@pytest.mark.asyncio
async def test_containment_executor_dry_run(tmp_path: Path) -> None:
    ex = ContainmentExecutor(dry_run=True, confirmed_actions={}, state_dir=tmp_path / "cs")

    async def _ok():
        from agents.defense.tools.containment_tools import ToolExecutionResult

        return ToolExecutionResult(True, "sim", rollback_commands=["undo"])

    rec = await ex.run_action("test", ContainmentSafetyLevel.AUTO, _ok)
    assert rec.dry_run is True
    assert rec.executed is False
    assert "undo" in rec.rollback_plan


@pytest.mark.asyncio
async def test_containment_confirmation_required(tmp_path: Path) -> None:
    ex = ContainmentExecutor(dry_run=False, confirmed_actions={}, state_dir=tmp_path / "cs2")

    async def _boom():
        from agents.defense.tools.containment_tools import ToolExecutionResult

        return ToolExecutionResult(True, "x", rollback_commands=["r"])

    rec = await ex.run_action("iso", ContainmentSafetyLevel.CONFIRM, _boom)
    assert rec.blocked_reason == "confirmation_required"


@pytest.mark.asyncio
async def test_containment_agent_dry_run_blocks_ip(tmp_path: Path) -> None:
    bus = MessageBus()
    iid = uuid4()
    inc = Incident(
        id=iid,
        title="Block attacker",
        description="c2 dns traffic",
        severity=IncidentSeverity.HIGH,
        source_ip="198.51.100.99",
    )
    inv = _minimal_investigation(iid, "pid: 9999 on host")
    agent = ContainmentAgent(
        bus,
        {"dry_run": True, "containment_state_dir": str(tmp_path / "cstate")},
    )
    res = await agent.contain(inc, inv)
    assert res.incident_id == iid
    assert any(a.name.startswith("block_ip") for a in res.actions_taken)
    assert res.rollback_plan


@pytest.mark.asyncio
async def test_containment_critical_host_requires_confirmation(tmp_path: Path) -> None:
    bus = MessageBus()
    iid = uuid4()
    inc = Incident(
        id=iid,
        title="Prod",
        description="critical",
        severity=IncidentSeverity.CRITICAL,
        target_asset="prod-db-01",
    )
    inv = _minimal_investigation(iid, "malware dns")
    agent = ContainmentAgent(
        bus,
        {
            "dry_run": False,
            "critical_hosts": ["prod-db-01"],
            "containment_state_dir": str(tmp_path / "cstate2"),
        },
    )
    res = await agent.contain(inc, inv)
    iso = [a for a in res.actions_taken if a.name.startswith("isolate_host")]
    assert iso
    assert iso[0].blocked_reason == "confirmation_required"


@pytest.mark.asyncio
async def test_ip_blocker_roundtrip(tmp_path: Path) -> None:
    b = IPBlocker(state_dir=tmp_path / "ip")
    r = await b.block("10.0.0.5", dry_run=False)
    assert r.success
    r2 = await b.unblock("10.0.0.5")
    assert r2.success
