"""Collect and aggregate feedback into learning signals."""

from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite
import structlog

from knowledge.models import (
    ConceptStruggle,
    DefenseFeedback,
    FeedbackReport,
    LearningSignal,
    LessonFeedback,
    QuestionFeedback,
    StudentProgress,
)
from shared.models import HypothesisState, InvestigationResult, Lesson

logger = structlog.get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class FeedbackCollector:
    """Turns raw operational artifacts into structured learning signals."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        root = Path(db_path or Path.home() / ".cache" / "tutorial" / "feedback.sqlite")
        root.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = str(root)
        self._pending: deque[dict[str, Any]] = deque()
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(
                """
                CREATE TABLE IF NOT EXISTS feedback_pending (
                    id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """,
            )
            await db.commit()

    async def collect_defense_feedback(self, investigation_result: InvestigationResult) -> DefenseFeedback:
        useful = [t for t in investigation_result.tools_used if t]
        hypo_ok = [h.text for h in investigation_result.hypotheses if h.state == HypothesisState.CONFIRMED]
        hypo_bad = [h.text for h in investigation_result.hypotheses if h.state == HypothesisState.REJECTED]
        novel: list[str] = []
        for sc in investigation_result.self_corrections:
            novel.append(sc.new_approach[:200])
        fb = DefenseFeedback(
            investigation_id=str(investigation_result.incident_id),
            incident_id=str(investigation_result.incident_id),
            useful_tools=useful[:50],
            not_useful_tools=[],
            correct_hypotheses=hypo_ok,
            incorrect_hypotheses=hypo_bad,
            self_corrections=len(investigation_result.self_corrections),
            novel_techniques=novel[:20],
        )
        async with self._lock:
            self._pending.append({"type": "defense_feedback", "payload": fb.model_dump(mode="json")})
        return fb

    async def collect_lesson_feedback(self, lesson: Lesson, student_progress: StudentProgress) -> LessonFeedback:
        lf = LessonFeedback(
            lesson_id=str(lesson.id),
            progress=student_progress,
            completion_rate=student_progress.completion_rate,
        )
        async with self._lock:
            self._pending.append({"type": "lesson_feedback", "payload": lf.model_dump(mode="json")})
        return lf

    async def collect_student_question(
        self,
        question: str,
        lesson_id: str,
        student_level: str,
        concept_hints: list[str],
        *,
        reveals_gap: bool = False,
    ) -> QuestionFeedback:
        qf = QuestionFeedback(
            question=question,
            lesson_id=lesson_id,
            student_level=student_level,
            concept_hints=concept_hints,
            reveals_gap=reveals_gap,
        )
        async with self._lock:
            self._pending.append({"type": "question_feedback", "payload": qf.model_dump(mode="json")})
        return qf

    async def process_feedback_batch(self) -> list[LearningSignal]:
        """Drain pending feedback and emit normalized ``LearningSignal`` rows."""

        async with self._lock:
            batch = list(self._pending)
            self._pending.clear()
        signals: list[LearningSignal] = []
        for item in batch:
            if item["type"] == "defense_feedback":
                fb = DefenseFeedback.model_validate(item["payload"])
                for tool in fb.useful_tools[:10]:
                    signals.append(
                        LearningSignal(
                            id=f"sig-{uuid.uuid4().hex[:10]}",
                            source_type="defense_completion",
                            source_id=fb.incident_id,
                            concept_id=f"tool:{tool}",
                            signal_type="connection_found",
                            strength=0.55,
                            context={"tool": tool},
                        ),
                    )
                for h in fb.incorrect_hypotheses[:5]:
                    signals.append(
                        LearningSignal(
                            id=f"sig-{uuid.uuid4().hex[:10]}",
                            source_type="defense_completion",
                            source_id=fb.incident_id,
                            concept_id="hypothesis_calibration",
                            signal_type="gap_identified",
                            strength=0.62,
                            context={"hypothesis": h},
                        ),
                    )
            elif item["type"] == "lesson_feedback":
                lf = LessonFeedback.model_validate(item["payload"])
                strength = min(1.0, max(0.0, lf.completion_rate))
                signals.append(
                    LearningSignal(
                        id=f"sig-{uuid.uuid4().hex[:10]}",
                        source_type="lesson_completion",
                        source_id=lf.lesson_id,
                        concept_id="lesson_aggregate",
                        signal_type="mastery_increase" if strength > 0.65 else "mastery_decrease",
                        strength=strength,
                        context={"hints": lf.progress.hint_usage_count},
                    ),
                )
            elif item["type"] == "question_feedback":
                qf = QuestionFeedback.model_validate(item["payload"])
                for cid in qf.concept_hints[:5]:
                    signals.append(
                        LearningSignal(
                            id=f"sig-{uuid.uuid4().hex[:10]}",
                            source_type="student_question",
                            source_id=qf.lesson_id,
                            concept_id=cid,
                            signal_type="gap_identified" if qf.reveals_gap else "new_concept",
                            strength=0.5,
                            context={"question": qf.question[:500]},
                        ),
                    )
        return signals


class FeedbackAggregator:
    """Rolls up feedback for analytics and weekly reporting."""

    def __init__(self, collector: FeedbackCollector) -> None:
        self._collector = collector
        self._mastery_series: dict[str, list[float]] = defaultdict(list)
        self._lesson_scores: dict[str, list[float]] = defaultdict(list)

    def record_signal(self, signal: LearningSignal) -> None:
        self._mastery_series[signal.concept_id].append(signal.strength)
        self._lesson_scores[signal.source_id].append(signal.strength)

    async def get_concept_mastery_trend(self, concept_id: str, time_window: str = "30d") -> list[float]:
        _ = time_window
        return list(self._mastery_series.get(concept_id, []))

    async def get_common_struggles(self, lesson_id: str) -> list[ConceptStruggle]:
        scores = self._lesson_scores.get(lesson_id, [])
        if not scores:
            return []
        avg = sum(scores) / len(scores)
        return [
            ConceptStruggle(concept_id="lesson_aggregate", struggle_score=round(1.0 - avg, 3), sample_size=len(scores)),
        ]

    async def get_teaching_effectiveness(self, lesson_id: str) -> float:
        scores = self._lesson_scores.get(lesson_id, [])
        if not scores:
            return 0.72
        return min(1.0, max(0.0, sum(scores) / len(scores)))

    async def generate_weekly_report(self) -> FeedbackReport:
        week_id = _utcnow().strftime("%Y-W%W")
        struggles: list[ConceptStruggle] = []
        for cid, vals in self._mastery_series.items():
            if not vals:
                continue
            m = sum(vals) / len(vals)
            if m < 0.55:
                struggles.append(ConceptStruggle(concept_id=cid, struggle_score=1.0 - m, sample_size=len(vals)))
        struggles.sort(key=lambda s: s.struggle_score, reverse=True)
        all_scores = [v for vs in self._lesson_scores.values() for v in vs]
        avg_eff = sum(all_scores) / len(all_scores) if all_scores else 0.74
        return FeedbackReport(
            week_id=week_id,
            total_signals=sum(len(v) for v in self._mastery_series.values()),
            top_struggles=struggles[:10],
            avg_teaching_effectiveness=round(avg_eff, 3),
            notes="Automated rollup from in-process feedback buffers.",
        )
