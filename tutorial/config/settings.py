"""Pydantic settings with ``TUTORIAL_`` environment prefix and validation."""

from __future__ import annotations

import json
import logging.config
from functools import lru_cache
from pathlib import Path
from typing import Any

import structlog
import yaml
from pydantic import AnyHttpUrl, BaseModel, Field, PositiveInt, TypeAdapter, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from shared.utils import merge_dicts


class LLMSettings(BaseModel):
    """LLM connectivity and generation parameters."""

    model_config = {"extra": "ignore"}

    model_name: str = Field(default="gpt-4o-mini", min_length=1)
    api_key: str = Field(default="", repr=False)
    base_url: AnyHttpUrl = Field(default="https://api.openai.com/v1")
    temperature_agents: float = Field(default=0.1, ge=0.0, le=2.0)
    temperature_creative: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: PositiveInt = Field(default=4096)
    timeout_seconds: PositiveInt = Field(default=120)


class AgentsSettings(BaseModel):
    """Agent pool and retry orchestration."""

    model_config = {"extra": "ignore"}

    max_concurrent_agents: PositiveInt = Field(default=8)
    retry_attempts: PositiveInt = Field(default=3)
    retry_backoff_seconds: float = Field(default=2.0, gt=0.0)
    per_agent_overrides_json: str = Field(
        default="{}",
        description="JSON object mapping agent_name -> partial config dict.",
    )

    @field_validator("per_agent_overrides_json")
    @classmethod
    def _valid_json_map(cls, value: str) -> str:
        """Ensure overrides are a JSON object."""

        parsed = json.loads(value)
        if not isinstance(parsed, dict):
            raise ValueError("per_agent_overrides_json must be a JSON object")
        return value

    def per_agent_overrides(self) -> dict[str, Any]:
        """Parsed per-agent override map."""

        return json.loads(self.per_agent_overrides_json)


class SecuritySettings(BaseModel):
    """Security tooling and SIEM integration."""

    model_config = {"extra": "ignore"}

    sift_workstation_path: Path | None = None
    splunk_host: AnyHttpUrl = Field(default="https://splunk.local:8089")
    splunk_token: str = Field(default="", repr=False)
    volatility_path: Path | None = None

    @field_validator("sift_workstation_path", "volatility_path")
    @classmethod
    def _optional_existing_path(cls, value: Path | None) -> Path | None:
        """When provided, paths must exist on disk."""

        if value is None:
            return None
        path = value.expanduser().resolve()
        if not path.exists():
            raise ValueError(f"Path does not exist: {path}")
        return path


class EducationSettings(BaseModel):
    """Curriculum and pacing configuration."""

    model_config = {"extra": "ignore"}

    csta_standards_path: Path | None = None
    difficulty_levels: PositiveInt = Field(default=5, le=10)
    min_lesson_duration_seconds: PositiveInt = Field(default=300)

    @field_validator("csta_standards_path")
    @classmethod
    def _csta_path(cls, value: Path | None) -> Path | None:
        if value is None:
            return None
        path = value.expanduser().resolve()
        if not path.exists():
            raise ValueError(f"CSTA standards path does not exist: {path}")
        return path


class DatabaseSettings(BaseModel):
    """Primary persistence configuration."""

    model_config = {"extra": "ignore"}

    url: str = Field(default="sqlite:///./tutorial.db", min_length=4)
    pool_size: PositiveInt = Field(default=5, le=100)
    echo: bool = False

    @field_validator("url")
    @classmethod
    def _supported_db_url(cls, value: str) -> str:
        lowered = value.lower()
        if not (
            lowered.startswith("sqlite:")
            or lowered.startswith("sqlite+")
            or lowered.startswith("postgresql:")
            or lowered.startswith("postgresql+")
        ):
            raise ValueError("database url must use sqlite or postgresql schemes")
        return value


class MessageBusSettings(BaseModel):
    """In-process async bus limits."""

    model_config = {"extra": "ignore"}

    max_queue_size: PositiveInt = Field(default=10_000, le=1_000_000)
    message_ttl_seconds: PositiveInt = Field(default=3600, le=86_400 * 7)


class StateMachineSettings(BaseModel):
    """Checkpoint storage for LangGraph execution."""

    model_config = {"extra": "ignore"}

    checkpoint_path: Path = Field(default=Path("./state_checkpoints.sqlite"))


class OrchestrationSettings(BaseModel):
    """Multi-agent orchestration persistence and pool limits."""

    model_config = {"extra": "ignore"}

    persistence_db_path: Path = Field(default=Path("./orchestration.db"))
    defense_checkpoint_db: Path = Field(default=Path("./checkpoints_defense.sqlite"))
    teaching_checkpoint_db: Path = Field(default=Path("./checkpoints_teaching.sqlite"))
    max_agents_per_type: PositiveInt = Field(default=2, le=64)
    pool_health_interval_seconds: float = Field(default=15.0, ge=1.0, le=300.0)
    heartbeat_stale_multiplier: float = Field(default=3.0, ge=1.5, le=10.0)


class MCPServerDefinition(BaseModel):
    """Single MCP stdio server entry used by the registry and connection manager."""

    model_config = {"extra": "ignore"}

    name: str = Field(min_length=1, pattern=r"^[a-zA-Z0-9_.-]+$")
    command: str = Field(min_length=1)
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] | None = None
    cwd: str | None = None


class MCPSettings(BaseModel):
    """MCP client/registry tuning and server manifest."""

    model_config = {"extra": "ignore"}

    enabled: bool = True
    registry_cache_path: Path = Field(default=Path("./mcp_registry.sqlite"))
    tool_call_timeout_seconds: float = Field(default=60.0, ge=1.0, le=600.0)
    max_connections_per_server: PositiveInt = Field(default=5, le=32)
    health_interval_seconds: float = Field(default=30.0, ge=5.0, le=7200.0)
    ping_enabled: bool = True
    servers_json: str = Field(default="[]", description="JSON array of MCPServerDefinition objects.")

    @field_validator("servers_json")
    @classmethod
    def _servers_json_array(cls, value: str) -> str:
        parsed = json.loads(value)
        if not isinstance(parsed, list):
            raise ValueError("servers_json must decode to a JSON array")
        return value

    def servers(self) -> list[MCPServerDefinition]:
        """Parsed MCP server endpoints."""

        return TypeAdapter(list[MCPServerDefinition]).validate_json(self.servers_json)


class LoggingSettings(BaseModel):
    """Logging bootstrap paths."""

    model_config = {"extra": "ignore"}

    config_path: Path = Field(default=Path("config/logging_config.yaml"))
    service_name: str = Field(default="tutorial", min_length=1)


class ApiSettings(BaseModel):
    """HTTP API / hackathon demo configuration."""

    model_config = {"extra": "ignore"}

    demo_api_key: str = Field(default="tutorial-demo-key", min_length=1)
    rate_limit_per_minute: int = Field(default=100, ge=1, le=10_000)
    evidence_upload_dir: Path = Field(default=Path("var/evidence_uploads"))
    cors_allow_origins: list[str] = Field(default_factory=lambda: ["*"])
    ws_poll_seconds: float = Field(
        default=18.0,
        ge=0.2,
        le=120.0,
        description="Seconds to wait for a bus event before emitting a synthetic heartbeat.",
    )


class Settings(BaseSettings):
    """Root application settings loaded from the environment."""

    model_config = SettingsConfigDict(
        env_prefix="TUTORIAL_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm: LLMSettings = Field(default_factory=LLMSettings)
    agents: AgentsSettings = Field(default_factory=AgentsSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    education: EducationSettings = Field(default_factory=EducationSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    message_bus: MessageBusSettings = Field(default_factory=MessageBusSettings)
    state_machine: StateMachineSettings = Field(default_factory=StateMachineSettings)
    orchestration: OrchestrationSettings = Field(default_factory=OrchestrationSettings)
    mcp: MCPSettings = Field(default_factory=MCPSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    api: ApiSettings = Field(default_factory=ApiSettings)

    def get_agent_config(self, agent_name: str) -> dict[str, Any]:
        """Return merged agent orchestration settings with optional per-agent overrides.

        Args:
            agent_name: Logical agent identifier used as a key in ``per_agent_overrides``.

        Returns:
            Dictionary suitable for passing into ``BaseAgent`` constructors.
        """

        base: dict[str, Any] = {
            "max_concurrent_agents": self.agents.max_concurrent_agents,
            "retry_attempts": self.agents.retry_attempts,
            "retry_backoff_seconds": self.agents.retry_backoff_seconds,
            "llm": {
                "model_name": self.llm.model_name,
                "api_key": self.llm.api_key,
                "base_url": str(self.llm.base_url),
                "temperature_agents": self.llm.temperature_agents,
                "temperature_creative": self.llm.temperature_creative,
                "max_tokens": self.llm.max_tokens,
                "timeout_seconds": self.llm.timeout_seconds,
            },
            "message_bus": {
                "max_queue_size": self.message_bus.max_queue_size,
                "message_ttl_seconds": self.message_bus.message_ttl_seconds,
            },
        }
        overrides = self.agents.per_agent_overrides().get(agent_name, {})
        return merge_dicts(base, overrides)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings singleton for import-time access."""

    return Settings()


def setup_logging(
    config_path: Path | None = None,
    *,
    log_level: int = logging.INFO,
    console_fallback: bool = False,
) -> None:
    """Configure stdlib logging and structlog processors from YAML.

    Args:
        config_path: Optional override for the logging YAML path.
        log_level: Root log level when YAML cannot be loaded.
        console_fallback: When True, use console renderer if YAML is missing.
    """

    settings = get_settings()
    path = config_path or settings.logging.config_path
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        timestamper,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    if path.exists():
        with path.open("r", encoding="utf-8") as handle:
            logging_config = yaml.safe_load(handle)
        logging.config.dictConfig(logging_config)
    else:
        logging.basicConfig(level=log_level)
        renderer: structlog.types.Processor = (
            structlog.dev.ConsoleRenderer(colors=True)
            if console_fallback
            else structlog.processors.JSONRenderer()
        )
        structlog.configure(
            processors=[
                *shared_processors,
                structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
            ],
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
        formatter = structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                renderer,
            ],
        )
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        root = logging.getLogger()
        root.handlers.clear()
        root.addHandler(handler)
        root.setLevel(log_level)

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
