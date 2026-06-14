"""Cross-cutting Pydantic models for agents, incidents, and lessons."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator

from config.constants import AgentStatus, IncidentSeverity, LessonDifficulty


def _utcnow() -> datetime:
    """Return timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc)


class Message(BaseModel):
    """Message envelope exchanged on the async bus."""

    model_config = {"extra": "forbid"}

    id: UUID = Field(default_factory=uuid4)
    topic: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=_utcnow)
    source_agent: str = Field(default="system", min_length=1)
    correlation_id: UUID = Field(default_factory=uuid4)


class Incident(BaseModel):
    """Security incident record shared across defense agents."""

    model_config = {"extra": "forbid"}

    id: UUID = Field(default_factory=uuid4)
    title: str = Field(min_length=1, max_length=500)
    description: str = Field(min_length=1, max_length=20_000)
    severity: IncidentSeverity
    source_ip: str | None = Field(default=None, max_length=64)
    target_asset: str | None = Field(default=None, max_length=500)
    raw_evidence_refs: list[str] = Field(default_factory=list)
    status: str = Field(default="open", min_length=1, max_length=100)
    created_at: datetime = Field(default_factory=_utcnow)
    assigned_agents: list[str] = Field(default_factory=list)


class InvestigationStep(BaseModel):
    """Single investigative action with interpretive metadata."""

    model_config = {"extra": "forbid"}

    id: UUID = Field(default_factory=uuid4)
    incident_id: UUID
    agent_name: str = Field(min_length=1)
    action_taken: str = Field(min_length=1)
    tool_used: str | None = Field(default=None, max_length=200)
    raw_output: str | None = None
    interpretation: str | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    timestamp: datetime = Field(default_factory=_utcnow)
    is_self_correction: bool = False


class Evidence(BaseModel):
    """Forensic artifact metadata."""

    model_config = {"extra": "forbid"}

    id: UUID = Field(default_factory=uuid4)
    incident_id: UUID
    type: str = Field(
        pattern="^(memory_dump|network_capture|disk_image|log_file)$",
    )
    file_path: str = Field(min_length=1)
    hash_sha256: str = Field(min_length=64, max_length=64)
    metadata: dict[str, Any] = Field(default_factory=dict)
    collected_by: str = Field(min_length=1)
    timestamp: datetime = Field(default_factory=_utcnow)


class Lesson(BaseModel):
    """Generated STEM lesson linked to real incident context."""

    model_config = {"extra": "forbid"}

    id: UUID = Field(default_factory=uuid4)
    incident_id: UUID
    title: str = Field(min_length=1, max_length=500)
    narrative: str = Field(min_length=1)
    interactive_steps: list[dict[str, Any]] = Field(default_factory=list)
    difficulty: LessonDifficulty
    csta_standards: list[str] = Field(default_factory=list)
    estimated_duration_minutes: int = Field(ge=1, le=600, default=30)
    created_at: datetime = Field(default_factory=_utcnow)
    student_progress: dict[str, Any] = Field(default_factory=dict)


class StudentProfile(BaseModel):
    """Learner model used for personalization."""

    model_config = {"extra": "forbid"}

    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=200)
    experience_level: str = Field(default="beginner", min_length=1, max_length=100)
    preferred_learning_style: str = Field(default="visual", min_length=1, max_length=100)
    completed_lessons: list[UUID] = Field(default_factory=list)
    skill_scores: dict[str, int] = Field(default_factory=dict)
    streak_days: int = Field(default=0, ge=0, le=10_000)

    @field_validator("skill_scores")
    @classmethod
    def _scores_in_range(cls, value: dict[str, int]) -> dict[str, int]:
        """Ensure skill scores remain between 0 and 100 inclusive."""

        for key, score in value.items():
            if not 0 <= score <= 100:
                raise ValueError(f"skill score for {key} must be between 0 and 100")
        return value


class AgentMetrics(BaseModel):
    """Operational metrics surfaced for observability."""

    model_config = {"extra": "forbid"}

    agent_name: str = Field(min_length=1)
    tasks_completed: int = Field(default=0, ge=0)
    tasks_failed: int = Field(default=0, ge=0)
    avg_task_duration_ms: float = Field(default=0.0, ge=0.0)
    uptime_seconds: float = Field(default=0.0, ge=0.0)
    last_heartbeat: datetime | None = None
    current_status: AgentStatus = AgentStatus.IDLE


class SystemHealth(BaseModel):
    """Aggregate health snapshot for dashboards."""

    model_config = {"extra": "forbid"}

    timestamp: datetime = Field(default_factory=_utcnow)
    all_agents: list[AgentMetrics] = Field(default_factory=list)
    message_bus_stats: dict[str, Any] = Field(default_factory=dict)
    pending_incidents: int = Field(default=0, ge=0)
    active_lessons: int = Field(default=0, ge=0)
    knowledge_graph_nodes: int = Field(default=0, ge=0)
    knowledge_graph_edges: int = Field(default=0, ge=0)


class IncidentTicket(BaseModel):
    """Ticket returned when an incident enters the defense orchestration pipeline."""

    model_config = {"extra": "forbid"}

    ticket_id: UUID = Field(default_factory=uuid4)
    incident_id: UUID
    status: str = Field(default="queued", min_length=1, max_length=32)
    defense_thread_id: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=_utcnow)


class LessonTicket(BaseModel):
    """Ticket returned when a lesson generation workflow is scheduled."""

    model_config = {"extra": "forbid"}

    ticket_id: UUID = Field(default_factory=uuid4)
    lesson_id: UUID = Field(default_factory=uuid4)
    incident_id: UUID
    status: str = Field(default="queued", min_length=1, max_length=32)
    teaching_thread_id: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=_utcnow)


class IncidentStatus(BaseModel):
    """Aggregated incident lifecycle and defense workflow trace."""

    model_config = {"extra": "forbid"}

    incident_id: str = Field(min_length=1)
    ticket: IncidentTicket
    defense_trace: list[dict[str, Any]] = Field(default_factory=list)
    latest_state: dict[str, Any] = Field(default_factory=dict)


class LessonStatus(BaseModel):
    """Aggregated lesson generation trace."""

    model_config = {"extra": "forbid"}

    lesson_id: str = Field(min_length=1)
    ticket: LessonTicket
    teaching_trace: list[dict[str, Any]] = Field(default_factory=list)
    latest_state: dict[str, Any] = Field(default_factory=dict)


class PoolStatus(BaseModel):
    """Per-``AgentType`` pool occupancy snapshot."""

    model_config = {"extra": "forbid"}

    active: int = Field(ge=0)
    idle: int = Field(ge=0)
    max_agents: int = Field(ge=0)


class HypothesisState(StrEnum):
    """Lifecycle for investigative hypotheses."""

    CREATED = "created"
    TESTING = "testing"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    MERGED = "merged"


class Hypothesis(BaseModel):
    """A single investigative hypothesis under test."""

    model_config = {"extra": "forbid"}

    id: UUID = Field(default_factory=uuid4)
    text: str = Field(min_length=1, max_length=2000)
    state: HypothesisState = HypothesisState.CREATED
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    rationale: str = Field(default="", max_length=5000)
    related_evidence_ids: list[UUID] = Field(default_factory=list)


class HypothesisResult(BaseModel):
    """Outcome of testing one hypothesis against evidence."""

    model_config = {"extra": "forbid"}

    hypothesis_id: UUID
    supporting: list[str] = Field(default_factory=list)
    contradicting: list[str] = Field(default_factory=list)
    score: float = Field(ge=0.0, le=1.0)


class SelfCorrectionEvent(BaseModel):
    """Auditable self-correction for FIND EVIL! judging."""

    model_config = {"extra": "forbid"}

    original_hypothesis: str = Field(min_length=1)
    correction_trigger: str = Field(min_length=1)
    new_approach: str = Field(min_length=1)
    result: str = Field(min_length=1)
    confidence_before: float = Field(ge=0.0, le=1.0)
    confidence_after: float = Field(ge=0.0, le=1.0)
    timestamp: datetime = Field(default_factory=_utcnow)


class InvestigationContext(BaseModel):
    """Payload passed into the reasoning engine."""

    model_config = {"extra": "forbid"}

    incident: Incident
    evidence: list[Evidence] = Field(default_factory=list)
    evidence_summary: dict[str, Any] = Field(default_factory=dict)
    prior_hypotheses: list[dict[str, Any]] = Field(default_factory=list)


class ReasoningResult(BaseModel):
    """Output of a multi-path reasoning pass."""

    model_config = {"extra": "forbid"}

    conclusion: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    paths: dict[str, Any] = Field(default_factory=dict)
    needs_self_correction: bool = False


class CorrectionAction(BaseModel):
    """Planned remediation when reasoning or hypotheses fail."""

    model_config = {"extra": "forbid"}

    reason: str = Field(min_length=1)
    strategy_id: str = Field(min_length=1)
    parameter_overrides: dict[str, Any] = Field(default_factory=dict)
    new_hypothesis_seeds: list[str] = Field(default_factory=list)


class Anomaly(BaseModel):
    """Detected anomaly in log or telemetry streams."""

    model_config = {"extra": "forbid"}

    kind: str = Field(min_length=1)
    description: str = Field(min_length=1)
    severity: str = Field(default="medium", min_length=1, max_length=32)
    evidence_ref: str | None = Field(default=None, max_length=500)


class IOCMatch(BaseModel):
    """Single IOC match with recommended response."""

    model_config = {"extra": "forbid"}

    indicator: str = Field(min_length=1)
    threat_type: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    source: str = Field(min_length=1)
    recommended_action: str = Field(min_length=1)


class InvestigationResult(BaseModel):
    """Structured outcome of an autonomous investigation."""

    model_config = {"extra": "forbid"}

    incident_id: UUID
    steps: list[InvestigationStep] = Field(default_factory=list)
    evidence_analyzed: list[Evidence] = Field(default_factory=list)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    self_corrections: list[SelfCorrectionEvent] = Field(default_factory=list)
    narrative: str = Field(min_length=1)
    accuracy_report: dict[str, Any] = Field(default_factory=dict)
    tools_used: list[str] = Field(default_factory=list)


class CustodyAction(StrEnum):
    """Actions recorded on the immutable chain-of-custody log."""

    COLLECTED = "COLLECTED"
    ACCESSED = "ACCESSED"
    COPIED = "COPIED"
    VERIFIED = "VERIFIED"
    TRANSFERRED = "TRANSFERRED"


class CustodyEntry(BaseModel):
    """Single append-only chain-of-custody record."""

    model_config = {"extra": "forbid"}

    timestamp: datetime = Field(default_factory=_utcnow)
    action: CustodyAction
    performed_by: str = Field(min_length=1, max_length=200)
    evidence_id: str = Field(min_length=1, max_length=64)
    hash_before: str | None = Field(default=None, max_length=64)
    hash_after: str | None = Field(default=None, max_length=64)
    location: str = Field(min_length=1, max_length=2000)
    notes: str = Field(default="", max_length=10_000)


class ContainmentSafetyLevel(StrEnum):
    """Whether a containment action may run automatically."""

    AUTO = "AUTO"
    CONFIRM = "CONFIRM"
    BLOCK = "BLOCK"


class ContainmentActionRecord(BaseModel):
    """One executed or skipped containment action with rollback metadata."""

    model_config = {"extra": "forbid"}

    name: str = Field(min_length=1, max_length=200)
    safety_level: ContainmentSafetyLevel
    executed: bool
    dry_run: bool = False
    blocked_reason: str | None = Field(default=None, max_length=2000)
    rollback_plan: str = Field(min_length=1, max_length=10_000)
    detail: str = Field(default="", max_length=10_000)


class IncidentContainmentResult(BaseModel):
    """Outcome of incident containment orchestration (defense agent envelope)."""

    model_config = {"extra": "forbid"}

    incident_id: UUID
    actions_taken: list[ContainmentActionRecord] = Field(default_factory=list)
    rollback_plan: str = Field(min_length=1)
    estimated_impact: str = Field(min_length=1, max_length=5000)
    business_disruption_level: str = Field(
        default="low",
        pattern="^(none|low|medium|high|critical)$",
    )
    narrative: str = Field(default="", max_length=20_000)


class RemediationPlanStep(BaseModel):
    """Ordered remediation step."""

    model_config = {"extra": "forbid"}

    order: int = Field(ge=0)
    title: str = Field(min_length=1, max_length=500)
    description: str = Field(min_length=1, max_length=5000)
    safety_note: str = Field(default="", max_length=2000)


class RemediationResult(BaseModel):
    """Outcome of post-containment remediation."""

    model_config = {"extra": "forbid"}

    incident_id: UUID
    plan_executed: list[RemediationPlanStep] = Field(default_factory=list)
    verification_result: str = Field(min_length=1, max_length=5000)
    remaining_risk: str = Field(min_length=1, max_length=2000)
    recommendations: list[str] = Field(default_factory=list)
    time_to_remediate_seconds: float = Field(ge=0.0)
    narrative: str = Field(default="", max_length=20_000)
