"""Tests for ``BaseAgent`` lifecycle and registry semantics."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from config.constants import AgentType, ErrorRecoveryAction, EventType
from core.base_agent import BaseAgent, GLOBAL_REGISTRY
from core.exceptions import AgentStartupError, AgentTimeoutError
from core.message_bus import MessageBus
from shared.models import Message


class DummyAgent(BaseAgent):
    """Minimal concrete agent for exercising lifecycle hooks."""

    def __init__(self, name: str, bus: MessageBus, iterations: int = 3) -> None:
        super().__init__(name, AgentType.DEFENSE_INVESTIGATION, bus, {})
        self._iterations = iterations
        self._counter = 0

    async def _run_iteration(self) -> None:
        self._counter += 1
        if self._counter > self._iterations:
            await asyncio.sleep(10_000.0)
        await asyncio.sleep(0.001)


class FailingAgent(BaseAgent):
    """Agent that fails until manually retired."""

    def __init__(self, name: str, bus: MessageBus) -> None:
        super().__init__(name, AgentType.TEACHING_NARRATIVE, bus, {})
        self.failures = 0

    async def _run_iteration(self) -> None:
        self.failures += 1
        raise ValueError("forced failure")

    async def handle_error(self, error: Exception) -> ErrorRecoveryAction:
        await super().handle_error(error)
        if self.failures < 2:
            return ErrorRecoveryAction.RETRY
        return ErrorRecoveryAction.HALT


@pytest.mark.asyncio
async def test_agent_start_stop_lifecycle() -> None:
    """Agents register, run iterations, and clean up on stop."""

    bus = MessageBus()
    await bus.start()
    agent = DummyAgent("alpha", bus, iterations=2)
    await agent.start()
    await asyncio.sleep(0.1)
    await agent.stop()
    assert agent.metrics.tasks_completed >= 1
    assert GLOBAL_REGISTRY.get("alpha") is None


@pytest.mark.asyncio
async def test_pause_resume() -> None:
    """Pause halts iterations until resume."""

    bus = MessageBus()
    await bus.start()
    agent = DummyAgent("beta", bus, iterations=100)
    await agent.start()
    await asyncio.sleep(0.05)
    await agent.pause()
    completed_before = agent.metrics.tasks_completed
    await asyncio.sleep(0.05)
    assert agent.metrics.tasks_completed == completed_before
    await agent.resume()
    await asyncio.sleep(0.05)
    assert agent.metrics.tasks_completed > completed_before
    await agent.stop()


@pytest.mark.asyncio
async def test_duplicate_registration_raises() -> None:
    """Registry rejects duplicate logical names."""

    bus = MessageBus()
    await bus.start()
    first = DummyAgent("dup", bus, iterations=5)
    second = DummyAgent("dup", bus, iterations=5)
    await first.start()
    try:
        with pytest.raises(AgentStartupError):
            await second.start()
    finally:
        await first.stop()


@pytest.mark.asyncio
async def test_error_recovery_retry_and_halt() -> None:
    """Error hook can retry before halting the loop."""

    bus = MessageBus()
    await bus.start()
    agent = FailingAgent("gamma", bus)
    await agent.start()
    await asyncio.sleep(0.2)
    await agent.stop()
    assert agent.failures >= 1


@pytest.mark.asyncio
async def test_publish_event_emits_system_topic() -> None:
    """``publish_event`` publishes structured payloads."""

    bus = MessageBus()
    await bus.start()
    seen: list[dict[str, Any]] = []

    async def watcher(msg: Message) -> None:
        seen.append(msg.payload)

    bus.subscribe("tutorial.system", watcher)
    agent = DummyAgent("delta", bus, iterations=5)
    await agent.publish_event(EventType.INCIDENT_DETECTED, {"id": "1"})
    await asyncio.sleep(0.05)
    assert any(item.get("event") == EventType.INCIDENT_DETECTED for item in seen)
    await bus.stop()


@pytest.mark.asyncio
async def test_request_help_requires_responder() -> None:
    """``request_help`` raises when RPC times out."""

    bus = MessageBus()
    await bus.start()
    agent = DummyAgent("epsilon", bus, iterations=1)
    await agent.start()
    with pytest.raises(AgentTimeoutError):
        await agent.request_help("missing", {"detail": "x"}, timeout=0.2)
    await agent.stop()
