"""Abstract base agent with lifecycle management, metrics, and coordination hooks."""

from __future__ import annotations

import asyncio
import contextlib
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

import structlog

from config.constants import (
    TIMEOUTS,
    AgentStatus,
    AgentType,
    ErrorRecoveryAction,
    EventType,
    MessageBusTopics,
)
from core.exceptions import AgentStartupError, AgentTimeoutError
from core.message_bus import MessageBus
from shared.models import AgentMetrics, Message

logger = structlog.get_logger(__name__)

_ALLOWED_TRANSITIONS: dict[AgentStatus, set[AgentStatus]] = {
    AgentStatus.IDLE: {AgentStatus.RUNNING},
    AgentStatus.RUNNING: {
        AgentStatus.PAUSED,
        AgentStatus.ERROR,
        AgentStatus.COMPLETED,
        AgentStatus.IDLE,
    },
    AgentStatus.PAUSED: {AgentStatus.RUNNING, AgentStatus.ERROR, AgentStatus.COMPLETED, AgentStatus.IDLE},
    AgentStatus.ERROR: {AgentStatus.IDLE, AgentStatus.RUNNING, AgentStatus.COMPLETED},
    AgentStatus.COMPLETED: {AgentStatus.IDLE},
}


class AgentRegistry:
    """Process-wide registry preventing duplicate agent names."""

    def __init__(self) -> None:
        self._agents: dict[str, BaseAgent] = {}
        self._lock = asyncio.Lock()

    async def register(self, agent: BaseAgent) -> None:
        """Register ``agent`` or raise if its name is taken.

        Args:
            agent: Agent instance to track.

        Raises:
            AgentStartupError: If the name already exists.
        """

        async with self._lock:
            if agent.name in self._agents:
                raise AgentStartupError(f"agent name already registered: {agent.name}")
            self._agents[agent.name] = agent

    async def unregister(self, agent: BaseAgent) -> None:
        """Remove ``agent`` from the registry if present."""

        async with self._lock:
            self._agents.pop(agent.name, None)

    def get(self, name: str) -> BaseAgent | None:
        """Lookup agent by ``name``."""

        return self._agents.get(name)

    def all_agents(self) -> dict[str, BaseAgent]:
        """Return a shallow copy of registered agents."""

        return dict(self._agents)

    async def clear(self) -> None:
        """Remove all agents (intended for isolated tests)."""

        async with self._lock:
            self._agents.clear()


GLOBAL_REGISTRY = AgentRegistry()


class BaseAgent(ABC):
    """Abstract agent with standardized lifecycle, metrics, and messaging."""

    def __init__(self, name: str, agent_type: AgentType, message_bus: MessageBus, config: dict[str, Any]) -> None:
        self.name = name
        self._agent_type = agent_type
        self._message_bus = message_bus
        self._config = config
        self._status = AgentStatus.IDLE
        self._status_lock = asyncio.Lock()
        self._main_task: asyncio.Task[None] | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._started_at: float | None = None
        self._tasks_completed = 0
        self._tasks_failed = 0
        self._durations_ms: list[float] = []
        self._last_heartbeat: datetime | None = None
        self._pause_event = asyncio.Event()
        self._pause_event.set()
        self._pause_requested = False
        self._iteration_guard = asyncio.Lock()

    @property
    def agent_type(self) -> AgentType:
        """Concrete agent classification."""

        return self._agent_type

    @property
    def status(self) -> AgentStatus:
        """Current lifecycle status."""

        return self._status

    @property
    def metrics(self) -> AgentMetrics:
        """Snapshot of operational metrics."""

        uptime = 0.0
        if self._started_at is not None:
            uptime = max(0.0, time.perf_counter() - self._started_at)
        avg_duration = 0.0
        if self._durations_ms:
            avg_duration = sum(self._durations_ms) / len(self._durations_ms)
        return AgentMetrics(
            agent_name=self.name,
            tasks_completed=self._tasks_completed,
            tasks_failed=self._tasks_failed,
            avg_task_duration_ms=avg_duration,
            uptime_seconds=uptime,
            last_heartbeat=self._last_heartbeat,
            current_status=self._status,
        )

    async def start(self) -> None:
        """Begin main loop and heartbeat publishing."""

        self._pause_requested = False
        self._pause_event.set()
        await GLOBAL_REGISTRY.register(self)
        await self._transition(AgentStatus.RUNNING)
        self._started_at = time.perf_counter()
        self._main_task = asyncio.create_task(self._main_loop_wrapper(), name=f"{self.name}-main")
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop(), name=f"{self.name}-heartbeat")

    async def stop(self) -> None:
        """Cancel background tasks and mark completion."""

        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._heartbeat_task
            self._heartbeat_task = None
        if self._main_task is not None:
            self._main_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._main_task
            self._main_task = None
        await GLOBAL_REGISTRY.unregister(self)
        await self._transition(AgentStatus.COMPLETED)
        await self._transition(AgentStatus.IDLE)

    async def pause(self) -> None:
        """Pause iterative processing while keeping tasks alive."""

        async with self._iteration_guard:
            self._pause_requested = True
            self._pause_event.clear()
            await self._transition(AgentStatus.PAUSED)

    async def resume(self) -> None:
        """Resume processing after ``pause``."""

        async with self._iteration_guard:
            await self._transition(AgentStatus.RUNNING)
            self._pause_requested = False
            self._pause_event.set()

    async def handle_error(self, error: Exception) -> ErrorRecoveryAction:
        """Determine recovery strategy after an error.

        Args:
            error: Exception raised from the main loop.

        Returns:
            Recovery directive interpreted by ``_main_loop_wrapper``.
        """

        logger.error("agent_error", agent=self.name, error=str(error))
        await self._transition(AgentStatus.ERROR)
        return ErrorRecoveryAction.HALT

    async def publish_event(self, event_type: EventType, payload: dict[str, Any]) -> None:
        """Publish a structured domain event."""

        message = Message(
            topic=MessageBusTopics.SYSTEM,
            payload={"event": event_type, "agent": self.name, **payload},
            source_agent=self.name,
        )
        await self._message_bus.publish(MessageBusTopics.SYSTEM, message)

    async def request_help(self, from_agent: str, problem: dict[str, Any], timeout: float = 30.0) -> dict[str, Any]:
        """Perform a lightweight RPC to another agent namespace.

        Args:
            from_agent: Target agent name.
            problem: Serializable problem statement.
            timeout: RPC timeout in seconds.

        Returns:
            Aggregated response payload.

        Raises:
            AgentTimeoutError: If no response arrives before ``timeout``.
        """

        topic = f"{MessageBusTopics.AGENTS}.{from_agent}.help"
        message = Message(
            topic=topic,
            payload={"problem": problem, "requester": self.name},
            source_agent=self.name,
        )
        responses = await self._message_bus.publish_wait(topic, message, timeout=timeout)
        if not responses:
            raise AgentTimeoutError(f"no response from {from_agent} within {timeout}s")
        merged: dict[str, Any] = {}
        for item in responses:
            merged.update(item.payload)
        return merged

    @abstractmethod
    async def _run_iteration(self) -> None:
        """Execute a single unit of agent work."""

    async def _main_loop_wrapper(self) -> None:
        """Run iterations until cancellation with pause and error handling."""

        try:
            while True:
                await self._pause_event.wait()
                async with self._iteration_guard:
                    if self._status == AgentStatus.COMPLETED:
                        break
                    if self._pause_requested:
                        continue
                    iteration_started = time.perf_counter()
                    try:
                        await self._run_iteration()
                        self._tasks_completed += 1
                        self._durations_ms.append((time.perf_counter() - iteration_started) * 1000)
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        self._tasks_failed += 1
                        action = await self.handle_error(exc)
                        if action == ErrorRecoveryAction.HALT:
                            break
                        if action == ErrorRecoveryAction.RETRY:
                            continue
                        if action == ErrorRecoveryAction.ESCALATE:
                            await self.publish_event(
                                EventType.AGENT_ERROR,
                                {"detail": str(exc), "escalated": True},
                            )
                            break
                        if action == ErrorRecoveryAction.IGNORE:
                            continue
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            logger.info("agent_main_cancelled", agent=self.name)
            raise

    async def _heartbeat_loop(self) -> None:
        """Emit periodic heartbeat events for observability."""

        try:
            while True:
                await asyncio.sleep(TIMEOUTS.AGENT_HEARTBEAT_INTERVAL)
                self._last_heartbeat = datetime.now(timezone.utc)
                await self.publish_event(
                    EventType.SYSTEM_HEARTBEAT,
                    {"metrics": self.metrics.model_dump(mode="json")},
                )
        except asyncio.CancelledError:
            logger.info("agent_heartbeat_cancelled", agent=self.name)
            raise

    async def _transition(self, new_status: AgentStatus) -> None:
        """Validate and apply a status transition."""

        async with self._status_lock:
            if new_status == self._status:
                return
            allowed = _ALLOWED_TRANSITIONS.get(self._status, set())
            if new_status not in allowed:
                raise AgentStartupError(
                    f"invalid transition {self._status} -> {new_status} for agent {self.name}",
                )
            self._status = new_status
