"""Tests for interactive element factory."""

from __future__ import annotations

from uuid import uuid4

import pytest

from agents.teaching.interactive_elements import InteractiveElementsFactory
from shared.models import InvestigationStep, StudentProfile


def _mk_step(incident_id, action: str, raw: str) -> InvestigationStep:
    return InvestigationStep(
        incident_id=incident_id,
        agent_name="defense",
        action_taken=action,
        tool_used="tool",
        interpretation="",
        raw_output=raw,
        confidence=0.7,
    )


@pytest.mark.asyncio
async def test_factory_variety_no_consecutive_same_kind() -> None:
    student = StudentProfile(name="Alex", experience_level="intermediate")
    factory = InteractiveElementsFactory(student)
    iid = uuid4()
    steps = [
        _mk_step(iid, "log_review", "4625 auth fail"),
        _mk_step(iid, "network", "dns tunnel long subdomain"),
        _mk_step(iid, "memory", "malfind injection"),
    ]
    scene_ids = ["s0", "s1", "s2", "s3"]
    m = factory.build_for_investigation(steps, scene_ids)
    kinds = [m[k].kind for k in scene_ids if k in m]
    for a, b in zip(kinds, kinds[1:], strict=False):
        assert a != b


@pytest.mark.asyncio
async def test_collect_flat_ordered() -> None:
    student = StudentProfile(name="Sam", experience_level="beginner")
    factory = InteractiveElementsFactory(student)
    iid = uuid4()
    steps = [_mk_step(iid, "logs", "fail")]
    order = ["s0", "s1"]
    m = factory.build_for_investigation(steps, order)
    flat = factory.collect_flat_ordered(m, order)
    assert flat
    assert flat[0].kind == "choice_point"
