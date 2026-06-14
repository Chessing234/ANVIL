"""Tests for ``TeachingWorkflow``."""

from __future__ import annotations

from pathlib import Path

from uuid import uuid4

import pytest

from orchestration.teaching_workflow import TeachingWorkflow, initial_teaching_state
from shared.models import InvestigationStep, StudentProfile


@pytest.mark.asyncio
async def test_teaching_workflow_runs(tmp_path: Path) -> None:
    """Teaching graph reaches checkpoint with assembled lesson."""

    incident_id = uuid4()
    profile = StudentProfile(name="stem-learner", experience_level="advanced")
    step = InvestigationStep(
        incident_id=incident_id,
        agent_name="defense",
        action_taken="dns_review",
        tool_used="wireshark",
        raw_output="ok",
        interpretation="tunnel",
        confidence=0.9,
    )
    initial = initial_teaching_state(
        str(incident_id),
        [step.model_dump(mode="json")],
        "case narrative",
        profile,
    )

    async def persist(state: dict[str, object]) -> None:
        return None

    async def on_event(kind: str, payload: dict[str, object]) -> None:
        return None

    wf = TeachingWorkflow(tmp_path / "t.sqlite", on_persist=persist, on_event=on_event)
    result = await wf.run(initial, thread_id="lesson-1")
    final = result["final_state"]
    assert final.get("lesson")
    assert final.get("completed") is True
