"""Tests for personalization and adaptive difficulty."""

from __future__ import annotations

from uuid import uuid4

import pytest

from agents.teaching.education_models import Interaction, LessonContent
from agents.teaching.personalization import PersonalizationEngine
from agents.teaching.tools.adaptive_engine import AdaptiveEngine
from config.constants import LessonDifficulty
from shared.models import StudentProfile


@pytest.mark.asyncio
async def test_personalization_scaffolding_and_hints(tmp_path) -> None:
    db = tmp_path / "ad.sqlite"
    adaptive = AdaptiveEngine(db_path=db)
    engine = PersonalizationEngine(adaptive_engine=adaptive, default_success_rate=0.5)
    content = LessonContent(
        title="Forensics 101",
        narrative_summary="summary",
        scene_ids=["s1", "s2"],
        concept_labels=["network", "encryption"],
        default_difficulty=LessonDifficulty.INTERMEDIATE,
        sandbox_challenge_ids=["c1"],
        pacing_minutes=40,
    )
    beginner = StudentProfile(name="B", experience_level="beginner", preferred_learning_style="visual")
    expert = StudentProfile(name="E", experience_level="expert", preferred_learning_style="kinesthetic")
    pb = await engine.personalize(content, beginner)
    pe = await engine.personalize(content, expert)
    assert pb.hint_schedule[0].show_after_minutes < pe.hint_schedule[0].show_after_minutes


@pytest.mark.asyncio
async def test_bkt_persistence_and_recommendation(tmp_path) -> None:
    db = tmp_path / "bkt.sqlite"
    eng = AdaptiveEngine(db_path=db)
    sid = str(uuid4())
    concept = "packet_analysis"
    for _ in range(4):
        await eng.update_model(
            sid,
            Interaction(student_id=sid, concept=concept, correct=True, hint_used=False, response_time_seconds=10.0),
        )
    m = await eng.predict_mastery(sid, concept)
    assert m > 0.4
    diff = await eng.recommend_difficulty(sid, concept)
    assert diff in {
        LessonDifficulty.BEGINNER,
        LessonDifficulty.INTERMEDIATE,
        LessonDifficulty.ADVANCED,
        LessonDifficulty.EXPERT,
    }
    await eng.update_model(
        sid,
        Interaction(student_id=sid, concept=concept, correct=False, hint_used=True, response_time_seconds=200.0),
    )
    weak = await eng.get_weak_areas(sid)
    assert isinstance(weak, list)

    snap = await eng.export_snapshot(sid)
    db2 = tmp_path / "bkt2.sqlite"
    eng2 = AdaptiveEngine(db_path=db2)
    await eng2.import_snapshot(snap)
    assert await eng2.predict_mastery(sid, concept) == pytest.approx(await eng.predict_mastery(sid, concept), rel=1e-6)
