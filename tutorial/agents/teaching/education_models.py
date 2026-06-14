"""Models for sandboxes, curriculum mapping, and personalized learning."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field

from config.constants import LessonDifficulty


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SandboxStatus(StrEnum):
    BUILDING = "building"
    READY = "ready"
    RUNNING = "running"
    DESTROYED = "destroyed"


class Hint(BaseModel):
    model_config = {"extra": "forbid"}

    id: str = Field(min_length=1, max_length=64)
    text: str = Field(min_length=1, max_length=4000)
    unlock_after_minutes: float = Field(ge=0.0, default=0.0)


class SandboxArtifact(BaseModel):
    model_config = {"extra": "forbid"}

    id: str = Field(min_length=1, max_length=64)
    virtual_path: str = Field(min_length=1, max_length=1024)
    description: str = Field(min_length=1, max_length=2000)
    original_hash: str | None = Field(default=None, max_length=64)
    sanitized: bool = True


class Challenge(BaseModel):
    model_config = {"extra": "forbid"}

    id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1, max_length=4000)
    verification_type: str = Field(pattern=r"^(find_file|run_command|answer_question)$")
    verification_script: str = Field(min_length=1, max_length=8000)
    concept_tested: str = Field(min_length=1, max_length=200)
    difficulty: LessonDifficulty
    points: int = Field(ge=0, le=10_000)
    hints: list[str] = Field(default_factory=list)
    next_challenge_id: str | None = Field(default=None, max_length=64)


class Sandbox(BaseModel):
    model_config = {"extra": "forbid"}

    id: str = Field(min_length=1, max_length=64)
    incident_id: str = Field(min_length=1, max_length=64)
    container_id: str | None = None
    status: SandboxStatus = SandboxStatus.BUILDING
    artifacts: list[SandboxArtifact] = Field(default_factory=list)
    challenges: list[Challenge] = Field(default_factory=list)
    provided_tools: list[str] = Field(default_factory=list)
    hints: list[Hint] = Field(default_factory=list)
    time_limit_minutes: int = Field(ge=5, le=240, default=45)
    sanitized: bool = False
    access_url: str | None = Field(default=None, max_length=2000)
    created_at: datetime = Field(default_factory=_utcnow)
    destroyed_at: datetime | None = None
    isolation_notes: str = Field(default="", max_length=4000)


class CSTAStandard(BaseModel):
    model_config = {"extra": "forbid"}

    id: str = Field(min_length=1, max_length=32)
    category: str = Field(min_length=1, max_length=8)
    grade_band: str = Field(pattern="^(K-2|3-5|6-8|9-12)$")
    description: str = Field(min_length=1, max_length=2000)
    keywords: list[str] = Field(default_factory=list)


class LearningObjective(BaseModel):
    model_config = {"extra": "forbid"}

    id: str = Field(min_length=1, max_length=64)
    text: str = Field(min_length=1, max_length=2000)
    aligned_standard_ids: list[str] = Field(default_factory=list)
    bloom_level: str = Field(default="apply", min_length=1, max_length=32)


class RubricCriterion(BaseModel):
    model_config = {"extra": "forbid"}

    criterion: str = Field(min_length=1, max_length=500)
    weight: float = Field(ge=0.0, le=1.0)
    mastery_description: str = Field(min_length=1, max_length=2000)


class AssessmentRubric(BaseModel):
    model_config = {"extra": "forbid"}

    title: str = Field(min_length=1, max_length=200)
    criteria: list[RubricCriterion] = Field(default_factory=list)
    passing_score: float = Field(ge=0.0, le=1.0, default=0.7)


class StandardCoverage(BaseModel):
    model_config = {"extra": "forbid"}

    standard: CSTAStandard
    lesson_segments: list[str] = Field(default_factory=list)
    assessment_method: str = Field(min_length=1, max_length=500)
    mastery_criteria: str = Field(min_length=1, max_length=2000)


class CurriculumMapping(BaseModel):
    model_config = {"extra": "forbid"}

    standards_covered: list[StandardCoverage] = Field(default_factory=list)
    learning_objectives: list[LearningObjective] = Field(default_factory=list)
    assessment_rubric: AssessmentRubric
    concept_prerequisites: dict[str, list[str]] = Field(default_factory=dict)
    recommended_sequence: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class CoverageReport(BaseModel):
    model_config = {"extra": "forbid"}

    fully_mapped: bool
    unmapped_concepts: list[str] = Field(default_factory=list)
    standards_count: int = Field(ge=0)


class LessonContent(BaseModel):
    model_config = {"extra": "forbid"}

    title: str = Field(min_length=1, max_length=500)
    narrative_summary: str = Field(min_length=1, max_length=20_000)
    scene_ids: list[str] = Field(default_factory=list)
    concept_labels: list[str] = Field(default_factory=list)
    default_difficulty: LessonDifficulty = LessonDifficulty.BEGINNER
    sandbox_challenge_ids: list[str] = Field(default_factory=list)
    pacing_minutes: int = Field(default=45, ge=5, le=600)


class Adjustment(BaseModel):
    model_config = {"extra": "forbid"}

    scene_id: str = Field(min_length=1)
    adjustment_type: str = Field(min_length=1, max_length=64)
    detail: str = Field(min_length=1, max_length=4000)


class HintTiming(BaseModel):
    model_config = {"extra": "forbid"}

    hint_id: str = Field(min_length=1)
    show_after_minutes: float = Field(ge=0.0)


class Resource(BaseModel):
    model_config = {"extra": "forbid"}

    title: str = Field(min_length=1, max_length=300)
    url: str = Field(min_length=1, max_length=2000)
    resource_type: str = Field(default="reading", min_length=1, max_length=64)


class PersonalizedContent(BaseModel):
    model_config = {"extra": "forbid"}

    narrative_adjustments: list[Adjustment] = Field(default_factory=list)
    hint_schedule: list[HintTiming] = Field(default_factory=list)
    challenge_difficulty: LessonDifficulty
    pacing_minutes: int = Field(ge=5, le=600)
    supplementary_resources: list[Resource] = Field(default_factory=list)
    prerequisite_lessons: list[str] = Field(default_factory=list)


class Interaction(BaseModel):
    model_config = {"extra": "forbid"}

    student_id: str = Field(min_length=1)
    concept: str = Field(min_length=1, max_length=200)
    correct: bool
    hint_used: bool = False
    response_time_seconds: float = Field(ge=0.0)
    timestamp: datetime = Field(default_factory=_utcnow)


class SkillModel(BaseModel):
    model_config = {"extra": "forbid"}

    student_id: str
    concept: str
    p_known: float = Field(ge=0.0, le=1.0, default=0.35)
    p_learn: float = Field(ge=0.0, le=1.0, default=0.25)
    p_guess: float = Field(ge=0.0, le=1.0, default=0.2)
    p_slip: float = Field(ge=0.0, le=1.0, default=0.1)
    updated_at: datetime = Field(default_factory=_utcnow)


class ContainerInfo(BaseModel):
    model_config = {"extra": "forbid"}

    container_id: str = Field(min_length=1)
    image: str = Field(min_length=1)
    network_isolated: bool = True


class NetworkConfig(BaseModel):
    model_config = {"extra": "forbid"}

    internal_only: bool = True
    simulated_services: list[str] = Field(default_factory=list)


class Snapshot(BaseModel):
    model_config = {"extra": "forbid"}

    id: str = Field(min_length=1)
    container_id: str = Field(min_length=1)
    filesystem_digest: str = Field(min_length=1, max_length=128)
    captured_at: datetime = Field(default_factory=_utcnow)
