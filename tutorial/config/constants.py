"""Shared constants, enums, and message-bus topic names for Project TUTORIAL."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum

# Stable demo learner used by seed data, credentials API, and the frontend wallet.
DEMO_STUDENT_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")
DEMO_STUDENT_EMAIL = "seed.student@tutorial.local"


class AgentStatus(StrEnum):
    """Lifecycle status for agents."""

    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"
    COMPLETED = "completed"


class IncidentSeverity(StrEnum):
    """Incident severity levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class LessonDifficulty(StrEnum):
    """Pedagogical difficulty tiers."""

    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


class AgentType(StrEnum):
    """Kinds of defense and teaching agents."""

    DEFENSE_INVESTIGATION = "defense_investigation"
    DEFENSE_CONTAINMENT = "defense_containment"
    DEFENSE_EVIDENCE = "defense_evidence"
    DEFENSE_REMEDIATION = "defense_remediation"
    TEACHING_NARRATIVE = "teaching_narrative"
    TEACHING_SANDBOX = "teaching_sandbox"
    TEACHING_CURRICULUM = "teaching_curriculum"
    TEACHING_PERSONALIZATION = "teaching_personalization"


class EventType(StrEnum):
    """Standard event types published on the message bus."""

    INCIDENT_DETECTED = "incident_detected"
    INVESTIGATION_STARTED = "investigation_started"
    EVIDENCE_COLLECTED = "evidence_collected"
    CONTAINMENT_EXECUTED = "containment_executed"
    LESSON_GENERATED = "lesson_generated"
    LESSON_COMPLETED = "lesson_completed"
    AGENT_ERROR = "agent_error"
    SYSTEM_HEARTBEAT = "system_heartbeat"


class ErrorRecoveryAction(StrEnum):
    """Pluggable recovery strategies after agent errors."""

    RETRY = "retry"
    ESCALATE = "escalate"
    HALT = "halt"
    IGNORE = "ignore"


@dataclass(frozen=True, slots=True)
class TimeoutConstants:
    """Standard timeouts (seconds) for external calls and coordination."""

    HTTP_DEFAULT: float = 60.0
    SUBPROCESS_DEFAULT: float = 120.0
    MESSAGE_BUS_RPC: float = 30.0
    AGENT_HEARTBEAT_INTERVAL: float = 30.0
    DOWNLOAD_DEFAULT: float = 60.0


@dataclass(frozen=True, slots=True)
class RetryConstants:
    """Default retry counts for orchestration layers."""

    DEFAULT_MAX_ATTEMPTS: int = 3
    DEFAULT_BACKOFF_SECONDS: float = 2.0


@dataclass(frozen=True, slots=True)
class SeverityColors:
    """Hex colors for UI visualization of incident severity."""

    LOW: str = "#2e7d32"
    MEDIUM: str = "#f9a825"
    HIGH: str = "#ef6c00"
    CRITICAL: str = "#b71c1c"


class MessageBusTopics:
    """Canonical topic names for async pub/sub."""

    INCIDENTS = "tutorial.incidents"
    INVESTIGATIONS = "tutorial.investigations"
    EVIDENCE = "tutorial.evidence"
    LESSONS = "tutorial.lessons"
    AGENTS = "tutorial.agents"
    SYSTEM = "tutorial.system"
    RPC_PREFIX = "tutorial.rpc"


TIMEOUTS = TimeoutConstants()
RETRIES = RetryConstants()
SEVERITY_COLORS = SeverityColors()
