"""Pydantic request and response models for the HTTP API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from database.models import EvidenceType, IncidentSeverity, IncidentStatus


class IncidentCreate(BaseModel):
    """Payload for creating a persisted incident."""

    model_config = {"extra": "forbid"}

    title: str = Field(min_length=1, max_length=512)
    description: str = Field(min_length=1)
    severity: IncidentSeverity
    status: IncidentStatus = IncidentStatus.OPEN
    source_ip: str | None = Field(default=None, max_length=64)
    target_asset: str | None = Field(default=None, max_length=512)
    incident_type: str = Field(default="unknown", max_length=128)
    raw_evidence_refs: list[Any] = Field(default_factory=list)
    assigned_agents: list[Any] = Field(default_factory=list)
    tags: list[Any] = Field(default_factory=list)


class IncidentResponse(BaseModel):
    """Incident summary returned from the API."""

    model_config = {"extra": "forbid", "from_attributes": True}

    id: uuid.UUID
    title: str
    description: str
    severity: str
    status: str
    source_ip: str | None
    target_asset: str | None
    incident_type: str
    raw_evidence_refs: list[Any]
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    assigned_agents: list[Any]
    tags: list[Any]


class InvestigationStepResponse(BaseModel):
    """Single investigation step."""

    model_config = {"extra": "forbid", "from_attributes": True}

    id: uuid.UUID
    incident_id: uuid.UUID
    agent_name: str
    action_taken: str
    tool_used: str
    raw_output: str
    interpretation: str
    confidence: float
    timestamp: datetime
    is_self_correction: bool
    correction_reason: str | None
    execution_time_ms: int


class EvidenceResponse(BaseModel):
    """Evidence metadata."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    incident_id: uuid.UUID
    evidence_type: str
    file_path: str
    hash_sha256: str
    file_size_bytes: int
    metadata: dict[str, Any] = Field(validation_alias="metadata_")
    collected_by: str
    custody_chain: list[Any]
    storage_location: str
    created_at: datetime
    verified_at: datetime | None


class LessonSummaryResponse(BaseModel):
    """Minimal lesson row."""

    model_config = {"extra": "forbid", "from_attributes": True}

    id: uuid.UUID
    incident_id: uuid.UUID
    title: str
    difficulty: str
    estimated_duration_minutes: int
    created_at: datetime


class IncidentDetail(BaseModel):
    """Incident with nested investigation and evidence context."""

    incident: IncidentResponse
    investigation_steps: list[InvestigationStepResponse]
    evidence: list[EvidenceResponse]
    lessons: list[LessonSummaryResponse]


class LessonResponse(BaseModel):
    """Lesson list item."""

    model_config = {"extra": "forbid", "from_attributes": True}

    id: uuid.UUID
    incident_id: uuid.UUID
    title: str
    narrative: str
    difficulty: str
    estimated_duration_minutes: int
    created_at: datetime


class LessonDetail(BaseModel):
    """Full lesson payload."""

    model_config = {"extra": "forbid", "from_attributes": True}

    id: uuid.UUID
    incident_id: uuid.UUID
    title: str
    narrative: str
    interactive_elements: list[Any]
    difficulty: str
    csta_standards: list[Any]
    estimated_duration_minutes: int
    concept_coverage: dict[str, Any]
    teaching_effectiveness_score: float | None
    created_at: datetime
    updated_at: datetime


class LessonGenerateRequest(BaseModel):
    """Request body for generating a lesson from defense outcomes."""

    model_config = {"extra": "forbid"}

    incident_id: uuid.UUID
    student_name: str = Field(default="learner", min_length=1, max_length=200)
    experience_level: str = Field(default="intermediate", min_length=1, max_length=100)
    preferred_learning_style: str = Field(default="visual", min_length=1, max_length=100)


class LessonGenerateResponse(BaseModel):
    """Teaching ticket summary."""

    model_config = {"extra": "forbid"}

    incident_id: uuid.UUID
    lesson_id: uuid.UUID
    teaching_thread_id: str
    status: str


class InteractionData(BaseModel):
    """Student interaction payload."""

    model_config = {"extra": "forbid"}

    student_id: uuid.UUID
    interaction: dict[str, Any]


class SandboxInfoResponse(BaseModel):
    """Sandbox metadata for a lesson."""

    model_config = {"extra": "forbid"}

    lesson_id: uuid.UUID
    sandbox_mode: str = Field(default="docker")
    workspace_hint: str = Field(default="Use the teaching sandbox agent for isolated execution.")
    resources: dict[str, Any] = Field(default_factory=dict)


class StudentCreate(BaseModel):
    """Create a learner profile."""

    model_config = {"extra": "forbid"}

    name: str = Field(min_length=1, max_length=256)
    email: str = Field(min_length=3, max_length=320)
    experience_level: str = Field(min_length=1)
    preferred_learning_style: str = Field(default="mixed", max_length=128)
    skill_scores: dict[str, Any] = Field(default_factory=dict)


class StudentResponse(BaseModel):
    """Student summary."""

    model_config = {"extra": "forbid", "from_attributes": True}

    id: uuid.UUID
    name: str
    email: str
    experience_level: str
    preferred_learning_style: str
    streak_days: int
    total_time_minutes: int
    created_at: datetime
    last_active_at: datetime | None


class StudentProgressItem(BaseModel):
    """Progress row."""

    model_config = {"extra": "forbid", "from_attributes": True}

    id: uuid.UUID
    lesson_id: uuid.UUID
    completion_percentage: float
    score: float
    hints_used: int
    time_spent_minutes: int
    interactions: list[Any]
    completed_at: datetime | None


class StudentDetail(BaseModel):
    """Student with progress."""

    student: StudentResponse
    progress: list[StudentProgressItem]


class LessonRecommendation(BaseModel):
    """Lightweight lesson suggestion."""

    model_config = {"extra": "forbid"}

    id: str
    title: str
    difficulty: str
    incident_id: str


class CredentialEntry(BaseModel):
    """Mock blockchain credential."""

    model_config = {"extra": "forbid"}

    credential_id: str
    student_id: uuid.UUID
    issued_at: str
    chain: str = Field(default="tutorial-demo")
    verification_hash: str
    lesson_id: uuid.UUID | None = None
    concept_name: str | None = None
    score: float | None = None
    category: str | None = None


class AgentStatusResponse(BaseModel):
    """Agent row for dashboards."""

    model_config = {"extra": "forbid", "from_attributes": True}

    id: uuid.UUID
    name: str
    agent_type: str
    status: str
    tasks_completed: int
    tasks_failed: int
    avg_task_duration_ms: float
    uptime_seconds: float
    last_heartbeat_at: datetime | None


class AgentMetricsResponse(BaseModel):
    """Derived metrics for a named agent."""

    model_config = {"extra": "forbid"}

    name: str
    tasks_completed: int
    tasks_failed: int
    avg_task_duration_ms: float
    uptime_seconds: float
    failure_rate: float


class KnowledgeNodeResponse(BaseModel):
    """Knowledge graph node."""

    model_config = {"extra": "forbid", "from_attributes": True}

    id: str
    name: str
    description: str
    category: str
    difficulty: str
    mastery_distribution: dict[str, Any]
    incidents_demonstrating: list[Any]
    lessons_teaching: list[Any]


class KnowledgeEdgeResponse(BaseModel):
    """Knowledge graph edge."""

    model_config = {"extra": "forbid", "from_attributes": True}

    id: uuid.UUID
    source_id: str
    target_id: str
    relation_type: str
    weight: float
    evidence_count: int


class KnowledgeGraphResponse(BaseModel):
    """Full graph snapshot."""

    model_config = {"extra": "forbid"}

    nodes: list[KnowledgeNodeResponse]
    edges: list[KnowledgeEdgeResponse]


class LearningPathResponse(BaseModel):
    """Ordered concept ids."""

    model_config = {"extra": "forbid"}

    target: str
    path: list[str]
    student_id: uuid.UUID | None = None


class SystemMetricsResponse(BaseModel):
    """Aggregate counters."""

    model_config = {"extra": "forbid"}

    incidents: int
    lessons: int
    students: int
    agents: int


class CustodyReportResponse(BaseModel):
    """Per-evidence custody keyed by evidence id."""

    model_config = {"extra": "forbid"}

    incident_id: str
    chains: dict[str, list[Any]]


class User(BaseModel):
    """Authenticated API caller (demo API key)."""

    model_config = {"extra": "forbid"}

    api_key_id: str = Field(default="demo")


class EvidenceUploadForm(BaseModel):
    """Optional fields accompanying multipart evidence upload."""

    model_config = {"extra": "forbid"}

    evidence_type: EvidenceType = EvidenceType.FILE
    collected_by: str = Field(default="api-client", max_length=256)
    storage_location: str = Field(default="local", max_length=512)

    @field_validator("evidence_type", mode="before")
    @classmethod
    def _coerce_evidence(cls, v: Any) -> Any:
        if isinstance(v, str):
            return EvidenceType(v)
        return v
