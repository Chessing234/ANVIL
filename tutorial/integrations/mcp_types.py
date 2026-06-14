"""Shared dataclasses and Pydantic models for MCP integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


@dataclass(slots=True)
class ToolDefinition:
    """Client-side view of an MCP tool listing entry."""

    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(slots=True)
class ToolResult:
    """Normalized tool invocation outcome."""

    data: dict[str, Any]
    is_error: bool = False
    error_message: str | None = None


@dataclass
class RegisteredTool:
    """Catalog entry mapping a logical tool to a backing MCP server."""

    name: str
    server_name: str
    category: str
    description: str
    input_schema: dict[str, Any]
    agent_types: list[str] = field(default_factory=list)


@dataclass
class ConnectionHealth:
    """Per-server connection health snapshot."""

    server_name: str
    healthy: bool
    last_ping_ms: float | None
    error: str | None


# --- Forensics / security structured outputs ---


class MemoryAnalysisResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    ok: bool = True
    plugins: list[str] = Field(default_factory=list)
    findings: list[dict[str, Any]] = Field(default_factory=list)
    notes: str = ""


class YaraMatch(BaseModel):
    model_config = ConfigDict(extra="allow")

    rule: str
    offset: int | None = None
    matched_data: str | None = None


class NetworkAnalysisResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    ok: bool = True
    protocols: dict[str, int] = Field(default_factory=dict)
    suspicious_flows: list[dict[str, Any]] = Field(default_factory=list)
    notes: str = ""


class DNSResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    domain: str
    addresses: list[str] = Field(default_factory=list)
    error: str | None = None


class WHOISResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    ip: str
    summary: str = ""
    raw: str = ""
    error: str | None = None


class LogEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    timestamp: str | None = None
    source: str = ""
    message: str = ""
    severity: str | None = None
    fields: dict[str, Any] = Field(default_factory=dict)


class EventCorrelation(BaseModel):
    model_config = ConfigDict(extra="allow")

    correlation_id: str
    events: list[str] = Field(default_factory=list)
    score: float = 0.0


class ContainmentResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    ok: bool
    action: str
    detail: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class CodeAnalysisResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    language: str
    issues: list[dict[str, Any]] = Field(default_factory=list)
    summary: str = ""


class ThreatClassification(BaseModel):
    model_config = ConfigDict(extra="allow")

    label: str
    confidence: float = 0.0
    rationale: str = ""
