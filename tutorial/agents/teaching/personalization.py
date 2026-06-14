"""Adapt lesson content to learner profiles using pedagogy rules and BKT signals."""

from __future__ import annotations


import structlog

from agents.teaching.education_models import (
    Adjustment,
    HintTiming,
    LessonContent,
    PersonalizedContent,
    Resource,
)
from agents.teaching.tools.adaptive_engine import AdaptiveEngine
from config.constants import LessonDifficulty
from shared.models import StudentProfile

logger = structlog.get_logger(__name__)


class AdaptiveTimer:
    """Adjusts pacing toward the 70–80% success band using recent performance."""

    def __init__(self, base_minutes: int, recent_success_rate: float) -> None:
        self._base = base_minutes
        self._rate = recent_success_rate

    def adjusted_minutes(self) -> int:
        if self._rate < 0.55:
            return min(600, int(self._base * 1.35))
        if self._rate > 0.9:
            return max(10, int(self._base * 0.85))
        return self._base


class DifficultyRamp:
    """Maps success rate to a lesson difficulty adjustment delta."""

    def __init__(self, success_rate: float) -> None:
        self._rate = success_rate

    def suggested_shift(self) -> int:
        """Return -1..+1 shift across difficulty ordinals."""

        if self._rate < 0.45:
            return -1
        if self._rate > 0.88:
            return 1
        return 0


_ORDER = [
    LessonDifficulty.BEGINNER,
    LessonDifficulty.INTERMEDIATE,
    LessonDifficulty.ADVANCED,
    LessonDifficulty.EXPERT,
]


def _shift_difficulty(base: LessonDifficulty, delta: int) -> LessonDifficulty:
    idx = _ORDER.index(base)
    return _ORDER[max(0, min(len(_ORDER) - 1, idx + delta))]


class PersonalizationEngine:
    """Produces ``PersonalizedContent`` aligned with experience, style, pacing, and interests."""

    def __init__(
        self,
        adaptive_engine: AdaptiveEngine | None = None,
        *,
        default_success_rate: float | None = None,
    ) -> None:
        self._adaptive = adaptive_engine or AdaptiveEngine()
        self._default_success_rate = default_success_rate

    async def _aggregate_success(self, student: StudentProfile) -> float:
        """Derive a coarse success rate from stored interactions (defaults when empty)."""

        snap = await self._adaptive.export_snapshot(str(student.id))
        inter = snap.get("interactions", [])
        if not inter:
            return self._default_success_rate if self._default_success_rate is not None else 0.72
        correct = sum(1 for row in inter if row.get("correct"))
        return correct / max(1, len(inter))

    async def personalize(self, content: LessonContent, student: StudentProfile) -> PersonalizedContent:
        """Return tailored scaffolding, hints, pacing, and enrichment resources."""

        success_rate = await self._aggregate_success(student)
        timer = AdaptiveTimer(content.pacing_minutes, success_rate)
        pacing = timer.adjusted_minutes()

        ramp = DifficultyRamp(success_rate)
        shift = ramp.suggested_shift()
        base_diff = content.default_difficulty
        exp = student.experience_level.lower()
        if exp == "beginner":
            shift -= 1
        elif exp == "expert":
            shift += 1
        challenge_difficulty = _shift_difficulty(base_diff, shift)

        adjustments: list[Adjustment] = []
        hint_schedule: list[HintTiming] = []
        style = student.preferred_learning_style.lower()

        for i, sid in enumerate(content.scene_ids):
            if style == "visual":
                adjustments.append(
                    Adjustment(
                        scene_id=sid,
                        adjustment_type="visual_scaffold",
                        detail="Add ASCII timeline and color-coded IOC table in facilitator notes.",
                    ),
                )
            elif style in ("reading", "writing", "reading/writing"):
                adjustments.append(
                    Adjustment(
                        scene_id=sid,
                        adjustment_type="text_scaffold",
                        detail="Insert margin questions and a structured note-taking outline.",
                    ),
                )
            elif style == "kinesthetic":
                adjustments.append(
                    Adjustment(
                        scene_id=sid,
                        adjustment_type="hands_on",
                        detail="Prioritize sandbox CLI tasks referencing this scene.",
                    ),
                )
            elif style == "auditory":
                adjustments.append(
                    Adjustment(
                        scene_id=sid,
                        adjustment_type="discussion",
                        detail="Add pair-and-share prompts (audio narration planned).",
                    ),
                )

        interests = {k.lower(): v for k, v in student.skill_scores.items() if v >= 60}
        resources: list[Resource] = []
        if any("net" in k for k in interests):
            resources.append(
                Resource(
                    title="Network forensics primer",
                    url="https://example.invalid/edu/network-forensics",
                    resource_type="reading",
                ),
            )
        if any("malware" in k or "reverse" in k for k in interests):
            resources.append(
                Resource(
                    title="Safe static analysis workflow",
                    url="https://example.invalid/edu/safe-static-analysis",
                    resource_type="reading",
                ),
            )
        if any(k in ("biology", "finance", "physics") for k in interests):
            resources.append(
                Resource(
                    title="Cross-domain analogy bank",
                    url="https://example.invalid/edu/cross-domain-cyber",
                    resource_type="reading",
                ),
            )

        challenge_ids = content.sandbox_challenge_ids or ["c1", "c2"]
        for hid, cid in enumerate(challenge_ids):
            delay = 0.0 if exp == "beginner" else 3.0
            hint_schedule.append(HintTiming(hint_id=f"hint-{cid}", show_after_minutes=delay + hid * 2.0))

        prereq: list[str] = []
        for concept in content.concept_labels[:3]:
            mastery = await self._adaptive.predict_mastery(str(student.id), concept)
            if mastery < 0.45:
                prereq.append(f"review:{concept}")

        logger.info("personalized_lesson", student=str(student.id), pacing=pacing, difficulty=challenge_difficulty)
        return PersonalizedContent(
            narrative_adjustments=adjustments,
            hint_schedule=hint_schedule,
            challenge_difficulty=challenge_difficulty,
            pacing_minutes=pacing,
            supplementary_resources=resources,
            prerequisite_lessons=prereq,
        )
