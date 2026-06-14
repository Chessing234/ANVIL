"""Tests for ``DefenseWorkflow``."""

from __future__ import annotations

from pathlib import Path

import pytest

from config.constants import IncidentSeverity
from orchestration.defense_workflow import DefenseWorkflow, initial_defense_state
from shared.models import Incident


@pytest.mark.asyncio
async def test_defense_workflow_non_critical(tmp_path: Path) -> None:
    """Non-critical incidents skip containment branch."""

    incident = Incident(title="low", description="desc", severity=IncidentSeverity.LOW)
    initial = initial_defense_state(incident)
    calls: list[dict[str, object]] = []

    async def persist(state: dict[str, object]) -> None:
        calls.append(dict(state))

    async def on_event(kind: str, payload: dict[str, object]) -> None:
        return None

    wf = DefenseWorkflow(tmp_path / "d.sqlite", on_persist=persist, on_event=on_event)
    result = await wf.run(initial, thread_id="t1")
    final = result["final_state"]
    assert final.get("completed") is True
    assert final.get("narrative")
    assert result["trace"]


@pytest.mark.asyncio
async def test_defense_workflow_critical(tmp_path: Path) -> None:
    """Critical incidents traverse containment and remediation."""

    incident = Incident(title="critical", description="desc", severity=IncidentSeverity.CRITICAL)
    initial = initial_defense_state(incident)

    async def persist(state: dict[str, object]) -> None:
        return None

    async def on_event(kind: str, payload: dict[str, object]) -> None:
        return None

    wf = DefenseWorkflow(tmp_path / "d2.sqlite", on_persist=persist, on_event=on_event)
    result = await wf.run(initial, thread_id="t2")
    final = result["final_state"]
    assert final.get("containment_actions")
