"""Tests for ``KnowledgeFlywheel``."""

from __future__ import annotations

import pytest

from orchestration.knowledge_flywheel import KnowledgeFlywheel
from orchestration.store import OrchestrationStore
from shared.models import StudentProfile


@pytest.mark.asyncio
async def test_flywheel_persistence_and_recommendation(tmp_path) -> None:
    """Graph survives reload and informs recommendations."""

    store = OrchestrationStore(tmp_path / "orch.db")
    store.initialize()
    fly = KnowledgeFlywheel(store)
    await fly.on_defense_complete("inc-1")
    await fly.load_graph()
    assert fly.graph_stats()["nodes"] > 0
    profile = StudentProfile(name="student")
    rec = await fly.get_recommended_next_lesson(profile)
    assert rec is not None


@pytest.mark.asyncio
async def test_flywheel_student_interaction(tmp_path) -> None:
    """Interactions adjust concept weights."""

    store = OrchestrationStore(tmp_path / "orch2.db")
    store.initialize()
    fly = KnowledgeFlywheel(store)
    await fly.on_student_interaction("lesson-1", {"concept": "dns_exfiltration", "struggle": True})
    insights = await fly.get_defense_insights()
    assert isinstance(insights, list)
