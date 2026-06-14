"""Tests for feedback collection."""

from __future__ import annotations

from uuid import uuid4

import pytest

from knowledge.feedback_loops import FeedbackAggregator, FeedbackCollector
from knowledge.models import StudentProgress
from shared.models import Hypothesis, HypothesisState, InvestigationResult, Lesson
from config.constants import LessonDifficulty


@pytest.mark.asyncio
async def test_feedback_batch_signals(tmp_path) -> None:
    col = FeedbackCollector(tmp_path / "f.sqlite")
    await col.initialize()
    agg = FeedbackAggregator(col)
    iid = uuid4()
    inv = InvestigationResult(
        incident_id=iid,
        steps=[],
        narrative="n",
        tools_used=["tshark"],
        hypotheses=[
            Hypothesis(text="ok", state=HypothesisState.CONFIRMED, confidence=0.9),
            Hypothesis(text="bad", state=HypothesisState.REJECTED, confidence=0.1),
        ],
    )
    await col.collect_defense_feedback(inv)
    les = Lesson(incident_id=iid, title="t", narrative="n", difficulty=LessonDifficulty.BEGINNER)
    prog = StudentProgress(lesson_id=str(les.id), student_id="s1", completion_rate=0.8)
    await col.collect_lesson_feedback(les, prog)
    sigs = await col.process_feedback_batch()
    assert sigs
    for s in sigs:
        agg.record_signal(s)
    eff = await agg.get_teaching_effectiveness(str(les.id))
    assert 0.0 <= eff <= 1.0
    report = await agg.generate_weekly_report()
    assert report.week_id
