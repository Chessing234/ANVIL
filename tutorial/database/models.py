"""SQLAlchemy ORM models for TUTORIAL persistence (incidents through message bus)."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


# --- Enums (stored as VARCHAR in SQLite) ---


class IncidentSeverity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentStatus(str, enum.Enum):
    OPEN = "open"
    TRIAGING = "triaging"
    INVESTIGATING = "investigating"
    CONTAINED = "contained"
    RESOLVED = "resolved"
    CLOSED = "closed"


class EvidenceType(str, enum.Enum):
    FILE = "file"
    MEMORY = "memory"
    NETWORK = "network"
    DISK = "disk"
    LOG = "log"
    OTHER = "other"


class LessonDifficulty(str, enum.Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class StudentExperience(str, enum.Enum):
    NOVICE = "novice"
    INTERMEDIATE = "intermediate"
    EXPERT = "expert"


class AgentType(str, enum.Enum):
    INVESTIGATION = "investigation"
    CONTAINMENT = "containment"
    TEACHING = "teaching"
    EVIDENCE = "evidence"
    ORCHESTRATOR = "orchestrator"
    OTHER = "other"


class AgentStatus(str, enum.Enum):
    ACTIVE = "active"
    IDLE = "idle"
    OFFLINE = "offline"


class KnowledgeCategory(str, enum.Enum):
    NETWORK = "network"
    CRYPTO = "crypto"
    MALWARE = "malware"
    WEB = "web"
    IDENTITY = "identity"
    DATA = "data"
    OPS = "operations"
    OTHER = "other"


class KnowledgeEdgeRelation(str, enum.Enum):
    PREREQUISITE = "prerequisite"
    RELATED = "related"
    BUILDS_ON = "builds_on"
    CONTRASTS = "contrasts"


class LearningSignalSourceType(str, enum.Enum):
    INCIDENT = "incident"
    LESSON = "lesson"
    STUDENT = "student"
    AGENT = "agent"
    SYSTEM = "system"


class LearningSignalType(str, enum.Enum):
    MASTERY = "mastery"
    STRUGGLE = "struggle"
    ENGAGEMENT = "engagement"
    COMPLETION = "completion"


class AgentActionType(str, enum.Enum):
    INVESTIGATION = "investigation"
    CONTAINMENT = "containment"
    LESSON = "lesson"
    SYNC = "sync"
    OTHER = "other"


class AgentActionResult(str, enum.Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"


# --- Models ---


class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (Index("ix_incident_status", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    severity: Mapped[IncidentSeverity] = mapped_column(Enum(IncidentSeverity), nullable=False)
    status: Mapped[IncidentStatus] = mapped_column(Enum(IncidentStatus), nullable=False, default=IncidentStatus.OPEN)
    source_ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    target_asset: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    incident_type: Mapped[str] = mapped_column(String(128), nullable=False, default="unknown")
    raw_evidence_refs: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    assigned_agents: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    tags: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    accuracy_report: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    investigation_steps: Mapped[list["InvestigationStep"]] = relationship(
        back_populates="incident", cascade="all, delete-orphan"
    )
    evidence_items: Mapped[list[Evidence]] = relationship(
        back_populates="incident", cascade="all, delete-orphan"
    )
    lessons: Mapped[list[Lesson]] = relationship(
        back_populates="incident", cascade="all, delete-orphan"
    )


class InvestigationStep(Base):
    __tablename__ = "investigation_steps"
    __table_args__ = (Index("ix_investigation_incident_id", "incident_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    agent_name: Mapped[str] = mapped_column(String(256), nullable=False)
    action_taken: Mapped[str] = mapped_column(Text, nullable=False)
    tool_used: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    raw_output: Mapped[str] = mapped_column(Text, nullable=False, default="")
    interpretation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    is_self_correction: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    correction_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    execution_time_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    incident: Mapped["Incident"] = relationship(back_populates="investigation_steps")


class Evidence(Base):
    __tablename__ = "evidence"
    __table_args__ = (Index("ix_evidence_hash", "hash_sha256"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    evidence_type: Mapped[EvidenceType] = mapped_column(Enum(EvidenceType), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    hash_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, nullable=False, default=dict)
    collected_by: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    custody_chain: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    storage_location: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    incident: Mapped["Incident"] = relationship(back_populates="evidence_items")


class Lesson(Base):
    __tablename__ = "lessons"
    __table_args__ = (Index("ix_lesson_difficulty", "difficulty"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    narrative: Mapped[str] = mapped_column(Text, nullable=False, default="")
    interactive_elements: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    difficulty: Mapped[LessonDifficulty] = mapped_column(Enum(LessonDifficulty), nullable=False)
    csta_standards: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    estimated_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    concept_coverage: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    teaching_effectiveness_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    incident: Mapped["Incident"] = relationship(back_populates="lessons")
    progress_rows: Mapped[list["StudentProgress"]] = relationship(
        back_populates="lesson", cascade="all, delete-orphan"
    )


class Student(Base):
    __tablename__ = "students"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    experience_level: Mapped[StudentExperience] = mapped_column(Enum(StudentExperience), nullable=False)
    preferred_learning_style: Mapped[str] = mapped_column(String(128), nullable=False, default="mixed")
    skill_scores: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    completed_lessons: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    streak_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_time_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    last_active_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    progress_rows: Mapped[list["StudentProgress"]] = relationship(
        back_populates="student", cascade="all, delete-orphan"
    )


class StudentProgress(Base):
    __tablename__ = "student_progress"
    __table_args__ = (UniqueConstraint("student_id", "lesson_id", name="uq_student_lesson_progress"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False
    )
    lesson_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False
    )
    completion_percentage: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    hints_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    time_spent_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    interactions: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    student: Mapped["Student"] = relationship(back_populates="progress_rows")
    lesson: Mapped["Lesson"] = relationship(back_populates="progress_rows")


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    agent_type: Mapped[AgentType] = mapped_column(Enum(AgentType), nullable=False)
    status: Mapped[AgentStatus] = mapped_column(Enum(AgentStatus), nullable=False, default=AgentStatus.IDLE)
    tasks_completed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tasks_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_task_duration_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    uptime_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    last_heartbeat_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    actions: Mapped[list["AgentAction"]] = relationship(
        back_populates="agent", cascade="all, delete-orphan"
    )


class KnowledgeNode(Base):
    __tablename__ = "knowledge_nodes"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    category: Mapped[KnowledgeCategory] = mapped_column(Enum(KnowledgeCategory), nullable=False)
    difficulty: Mapped[LessonDifficulty] = mapped_column(Enum(LessonDifficulty), nullable=False)
    mastery_distribution: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    incidents_demonstrating: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    lessons_teaching: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    outgoing_edges: Mapped[list["KnowledgeEdge"]] = relationship(
        "KnowledgeEdge",
        foreign_keys="KnowledgeEdge.source_id",
        back_populates="source_node",
        cascade="all, delete-orphan",
    )
    incoming_edges: Mapped[list["KnowledgeEdge"]] = relationship(
        "KnowledgeEdge",
        foreign_keys="KnowledgeEdge.target_id",
        back_populates="target_node",
        cascade="all, delete-orphan",
    )
    learning_signals: Mapped[list["LearningSignal"]] = relationship(
        "LearningSignal",
        foreign_keys="LearningSignal.concept_id",
        back_populates="concept",
        cascade="all, delete-orphan",
    )


class KnowledgeEdge(Base):
    __tablename__ = "knowledge_edges"
    __table_args__ = (Index("ix_knowledge_edge_source_target", "source_id", "target_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), nullable=False
    )
    target_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), nullable=False
    )
    relation_type: Mapped[KnowledgeEdgeRelation] = mapped_column(Enum(KnowledgeEdgeRelation), nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    source_node: Mapped["KnowledgeNode"] = relationship(
        "KnowledgeNode",
        foreign_keys=[source_id],
        back_populates="outgoing_edges",
    )
    target_node: Mapped["KnowledgeNode"] = relationship(
        "KnowledgeNode",
        foreign_keys=[target_id],
        back_populates="incoming_edges",
    )


class LearningSignal(Base):
    __tablename__ = "learning_signals"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_type: Mapped[LearningSignalSourceType] = mapped_column(Enum(LearningSignalSourceType), nullable=False)
    source_id: Mapped[str] = mapped_column(String(128), nullable=False)
    concept_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), nullable=False
    )
    signal_type: Mapped[LearningSignalType] = mapped_column(Enum(LearningSignalType), nullable=False)
    strength: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    context: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    concept: Mapped["KnowledgeNode"] = relationship(
        "KnowledgeNode", foreign_keys=[concept_id], back_populates="learning_signals"
    )


class AgentAction(Base):
    __tablename__ = "agent_actions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    action_type: Mapped[AgentActionType] = mapped_column(Enum(AgentActionType), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    result: Mapped[AgentActionResult] = mapped_column(Enum(AgentActionResult), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    blockchain_tx_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    agent: Mapped["Agent"] = relationship(back_populates="actions")


class MessageBusLog(Base):
    __tablename__ = "message_bus_log"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topic: Mapped[str] = mapped_column(String(256), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    source_agent: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    delivered_to: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
