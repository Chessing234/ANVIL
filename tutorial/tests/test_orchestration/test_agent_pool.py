"""Tests for ``AgentPool``."""

from __future__ import annotations

import pytest
import uuid

from config.constants import AgentType
from config.settings import Settings
from core.base_agent import BaseAgent
from core.message_bus import MessageBus
from orchestration.agent_pool import AgentPool


class _PoolAgent(BaseAgent):
    """Minimal concrete agent."""

    def __init__(self, agent_type: AgentType, bus: MessageBus) -> None:
        super().__init__(f"pool-{agent_type.value}-{uuid.uuid4().hex[:10]}", agent_type, bus, {})

    async def _run_iteration(self) -> None:
        return None


@pytest.mark.asyncio
async def test_pool_acquire_release_and_status() -> None:
    """Factories produce agents bounded by configured caps."""

    settings = Settings(orchestration__max_agents_per_type=2)
    bus = MessageBus()
    await bus.start()
    pool = AgentPool(settings)
    pool.register_factory(AgentType.DEFENSE_INVESTIGATION, lambda: _PoolAgent(AgentType.DEFENSE_INVESTIGATION, bus))
    agent = await pool.acquire(AgentType.DEFENSE_INVESTIGATION)
    status = pool.get_status()
    assert status[AgentType.DEFENSE_INVESTIGATION].active == 1
    await pool.release(agent)
    status2 = pool.get_status()
    assert status2[AgentType.DEFENSE_INVESTIGATION].active == 0
    assert status2[AgentType.DEFENSE_INVESTIGATION].idle >= 1
    await pool.drain()
    await bus.stop()


@pytest.mark.asyncio
async def test_pool_scale_and_drain() -> None:
    """Scaling pre-warms idle agents until limits are hit."""

    settings = Settings(orchestration__max_agents_per_type=2)
    bus = MessageBus()
    await bus.start()
    pool = AgentPool(settings)
    pool.register_factory(AgentType.TEACHING_NARRATIVE, lambda: _PoolAgent(AgentType.TEACHING_NARRATIVE, bus))
    await pool.scale(AgentType.TEACHING_NARRATIVE, 2)
    snap = pool.get_status()[AgentType.TEACHING_NARRATIVE]
    assert snap.idle + snap.active <= 2
    await pool.drain()
    await bus.stop()
