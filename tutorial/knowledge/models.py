"""Pydantic models for the knowledge flywheel, graph, and feedback."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from config.constants import LessonDifficulty


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ConceptNode(BaseModel):
    """Single teachable/defensible cybersecurity concept."""

    model_config = {"extra": "forbid"}

    id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1, max_length=8000)
    category: str = Field(min_length=1, max_length=120)
    difficulty: LessonDifficulty
    prerequisites: list[str] = Field(default_factory=list)
    related: list[str] = Field(default_factory=list)
    incidents_demonstrating: list[str] = Field(default_factory=list)
    lessons_teaching: list[str] = Field(default_factory=list)
    mastery_distribution: dict[str, float] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class ConceptEdge(BaseModel):
    """Directed relationship between two concept graph entities."""

    model_config = {"extra": "forbid"}

    source: str = Field(min_length=1, max_length=128)
    target: str = Field(min_length=1, max_length=128)
    relation_type: str = Field(
        pattern="^(prerequisite_of|related_to|demonstrated_by|taught_by)$",
    )
    weight: float = Field(ge=0.0, le=1.0, default=0.5)
    evidence_count: int = Field(ge=0, default=1)


class LearningSignal(BaseModel):
    """Normalized learning observation feeding the flywheel."""

    model_config = {"extra": "forbid"}

    id: str = Field(min_length=1, max_length=64)
    source_type: str = Field(min_length=1, max_length=64)
    source_id: str = Field(min_length=1, max_length=128)
    concept_id: str = Field(min_length=1, max_length=128)
    signal_type: str = Field(min_length=1, max_length=64)
    strength: float = Field(ge=0.0, le=1.0)
    context: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=_utcnow)


class DefenseInsight(BaseModel):
    """Actionable insight derived from learner or defender behavior."""

    model_config = {"extra": "forbid"}

    id: str = Field(min_length=1, max_length=64)
    concept_id: str = Field(min_length=1, max_length=128)
    insight_type: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=4000)
    frequency: int = Field(ge=1, default=1)
    first_observed: datetime = Field(default_factory=_utcnow)
    last_observed: datetime = Field(default_factory=_utcnow)
    affected_lessons: list[str] = Field(default_factory=list)
    recommended_action: str = Field(min_length=1, max_length=2000)


class StudentProgress(BaseModel):
    """Structured per-lesson learner progress for feedback aggregation."""

    model_config = {"extra": "forbid"}

    lesson_id: str = Field(min_length=1)
    student_id: str = Field(min_length=1)
    completion_rate: float = Field(ge=0.0, le=1.0, default=0.0)
    time_spent_seconds: dict[str, float] = Field(default_factory=dict)
    hint_usage_count: int = Field(ge=0, default=0)
    quiz_scores: list[float] = Field(default_factory=list)
    self_reported_difficulty: float = Field(ge=1.0, le=5.0, default=3.0)


class DefenseFeedback(BaseModel):
    """Structured feedback from a completed investigation."""

    model_config = {"extra": "forbid"}

    investigation_id: str = Field(min_length=1)
    incident_id: str = Field(min_length=1)
    useful_tools: list[str] = Field(default_factory=list)
    not_useful_tools: list[str] = Field(default_factory=list)
    correct_hypotheses: list[str] = Field(default_factory=list)
    incorrect_hypotheses: list[str] = Field(default_factory=list)
    self_corrections: int = Field(ge=0, default=0)
    novel_techniques: list[str] = Field(default_factory=list)


class LessonFeedback(BaseModel):
    """Aggregatable signals from a lesson run."""

    model_config = {"extra": "forbid"}

    lesson_id: str = Field(min_length=1)
    progress: StudentProgress
    completion_rate: float = Field(ge=0.0, le=1.0)


class QuestionFeedback(BaseModel):
    """Captures a learner question for routing and gap detection."""

    model_config = {"extra": "forbid"}

    question: str = Field(min_length=1, max_length=4000)
    lesson_id: str = Field(min_length=1)
    student_level: str = Field(min_length=1, max_length=64)
    concept_hints: list[str] = Field(default_factory=list)
    reveals_gap: bool = False


class ConceptStruggle(BaseModel):
    """Statistical struggle hotspot."""

    model_config = {"extra": "forbid"}

    concept_id: str = Field(min_length=1)
    struggle_score: float = Field(ge=0.0, le=1.0)
    sample_size: int = Field(ge=0, default=0)


class GraphStats(BaseModel):
    """Summary analytics for observability dashboards."""

    model_config = {"extra": "forbid"}

    node_count: int = Field(ge=0)
    edge_count: int = Field(ge=0)
    density: float = Field(ge=0.0)
    category_coverage: dict[str, int] = Field(default_factory=dict)
    pagerank_top: list[tuple[str, float]] = Field(default_factory=list)
    community_count: int = Field(ge=0, default=0)
    bridge_concepts: list[str] = Field(default_factory=list)


class FeedbackReport(BaseModel):
    """Weekly rollup for operators."""

    model_config = {"extra": "forbid"}

    week_id: str = Field(min_length=1)
    total_signals: int = Field(ge=0)
    top_struggles: list[ConceptStruggle] = Field(default_factory=list)
    avg_teaching_effectiveness: float = Field(ge=0.0, le=1.0, default=0.0)
    notes: str = Field(default="", max_length=8000)
