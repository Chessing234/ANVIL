"""Agent lifecycle pooling with health monitoring and graceful drain."""

from __future__ import annotations

import asyncio
import contextlib
from collections import defaultdict, deque
from collections.abc import Callable
from datetime import datetime, timezone
import structlog

from config.constants import TIMEOUTS, AgentType
from config.settings import Settings
from core.base_agent import BaseAgent
from shared.models import PoolStatus

logger = structlog.get_logger(__name__)


class AgentPool:
    """Manage ``BaseAgent`` instances keyed by ``AgentType`` with bounded concurrency."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._factories: dict[AgentType, Callable[[], BaseAgent]] = {}
        self._idle: dict[AgentType, deque[BaseAgent]] = defaultdict(deque)
        self._busy: set[BaseAgent] = set()
        self._lock = asyncio.Lock()
        self._draining = False
        self._drain_complete = asyncio.Event()
        self._drain_complete.set()
        self._health_task: asyncio.Task[None] | None = None
        self._stopped = False

    def register_factory(self, agent_type: AgentType, factory: Callable[[], BaseAgent]) -> None:
        """Register a factory used to instantiate agents for ``agent_type``.

        Args:
            agent_type: Logical cluster specialization.
            factory: Zero-argument callable returning a configured ``BaseAgent``.
        """

        self._factories[agent_type] = factory
        logger.info("agent_pool_factory_registered", agent_type=str(agent_type))

    async def start_health_monitor(self) -> None:
        """Begin periodic heartbeat validation."""

        if self._health_task is not None:
            return
        self._health_task = asyncio.create_task(self._health_loop(), name="agent-pool-health")

    async def stop_health_monitor(self) -> None:
        """Stop the background health monitor."""

        if self._health_task is None:
            return
        self._health_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._health_task
        self._health_task = None

    async def _health_loop(self) -> None:
        """Restart agents whose heartbeats are stale."""

        try:
            while True:
                await asyncio.sleep(self._settings.orchestration.pool_health_interval_seconds)
                await self._reap_stale_agents()
        except asyncio.CancelledError:
            logger.info("agent_pool_health_cancelled")
            raise

    def _max_for_type(self, agent_type: AgentType) -> int:
        """Maximum instances allowed for ``agent_type``."""

        return int(self._settings.orchestration.max_agents_per_type)

    def _is_stale(self, agent: BaseAgent) -> bool:
        """Return True when the agent heartbeat is too old."""

        metrics = agent.metrics
        if metrics.last_heartbeat is None:
            return False
        age = datetime.now(timezone.utc) - metrics.last_heartbeat
        limit = TIMEOUTS.AGENT_HEARTBEAT_INTERVAL * self._settings.orchestration.heartbeat_stale_multiplier
        return age.total_seconds() > limit

    async def _reap_stale_agents(self) -> None:
        """Replace stale agents while holding the pool lock."""

        async with self._lock:
            candidates = list(self._busy) + [a for q in self._idle.values() for a in q]
        for agent in candidates:
            if not self._is_stale(agent):
                continue
            agent_type = agent.agent_type
            logger.warning("agent_pool_restart_stale", agent=agent.name)
            await self._restart_agent(agent, agent_type)

    async def _restart_agent(self, agent: BaseAgent, agent_type: AgentType) -> None:
        """Stop and recreate a single agent."""

        async with self._lock:
            if agent in self._busy:
                self._busy.remove(agent)
            for t in list(self._idle.keys()):
                self._idle[t] = deque(a for a in self._idle[t] if a is not agent)
        with contextlib.suppress(Exception):
            await agent.stop()
        try:
            replacement = self._factories[agent_type]()
        except KeyError as exc:
            logger.error("agent_pool_missing_factory", agent_type=str(agent_type), error=str(exc))
            return
        await replacement.start()
        async with self._lock:
            self._idle[agent_type].append(replacement)

    async def acquire(self, agent_type: AgentType) -> BaseAgent:
        """Borrow an idle agent or instantiate a new one within limits.

        Args:
            agent_type: Requested specialization.

        Returns:
            Running ``BaseAgent`` instance.

        Raises:
            RuntimeError: When the pool is draining or factories are missing.
        """

        if self._draining:
            raise RuntimeError("agent pool is draining")
        factory = self._factories.get(agent_type)
        if factory is None:
            raise RuntimeError(f"no factory registered for {agent_type}")
        async with self._lock:
            if self._idle[agent_type]:
                agent = self._idle[agent_type].popleft()
                self._busy.add(agent)
                return agent
            busy_n = len(self._busy_for_type(agent_type))
            idle_n = len(self._idle[agent_type])
            if busy_n + idle_n >= self._max_for_type(agent_type):
                raise RuntimeError(f"max agents reached for {agent_type}")
        agent = factory()
        await agent.start()
        async with self._lock:
            self._busy.add(agent)
        return agent

    def _busy_for_type(self, agent_type: AgentType) -> list[BaseAgent]:
        """List busy agents matching ``agent_type``."""

        return [agent for agent in self._busy if agent.agent_type == agent_type]

    async def release(self, agent: BaseAgent) -> None:
        """Return a borrowed agent to the idle queue."""

        async with self._lock:
            if agent in self._busy:
                self._busy.remove(agent)
            self._idle[agent.agent_type].append(agent)

    async def scale(self, agent_type: AgentType, count: int) -> None:
        """Pre-warm up to ``count`` idle agents for ``agent_type``.

        Args:
            agent_type: Target specialization.
            count: Desired idle instances after scaling completes.
        """

        factory = self._factories.get(agent_type)
        if factory is None:
            raise RuntimeError(f"no factory registered for {agent_type}")
        async with self._lock:
            current_idle = len(self._idle[agent_type])
            deficit = max(0, count - current_idle)
            capacity = self._max_for_type(agent_type) - len(self._busy_for_type(agent_type)) - len(
                self._idle[agent_type],
            )
            to_create = min(deficit, max(0, capacity))
        for _ in range(to_create):
            agent = factory()
            await agent.start()
            async with self._lock:
                self._idle[agent_type].append(agent)

    def get_status(self) -> dict[AgentType, PoolStatus]:
        """Summarize occupancy for every registered ``AgentType``."""

        snapshot: dict[AgentType, PoolStatus] = {}
        for agent_type in self._factories:
            busy = len(self._busy_for_type(agent_type))
            idle = len(self._idle[agent_type])
            snapshot[agent_type] = PoolStatus(
                active=busy,
                idle=idle,
                max_agents=self._max_for_type(agent_type),
            )
        return snapshot

    async def iter_agents(self) -> list[BaseAgent]:
        """Return all agents tracked by the pool."""

        async with self._lock:
            return list(self._busy) + [a for q in self._idle.values() for a in q]

    async def drain(self) -> None:
        """Stop accepting new acquisitions and shut down all agents."""

        self._draining = True
        self._drain_complete.clear()
        try:
            while True:
                async with self._lock:
                    if not self._busy:
                        break
                await asyncio.sleep(0.02)
            await self.stop_health_monitor()
            async with self._lock:
                agents = list(self._busy) + [a for q in self._idle.values() for a in q]
                self._busy.clear()
                for t in list(self._idle.keys()):
                    self._idle[t].clear()
            for agent in agents:
                with contextlib.suppress(Exception):
                    await agent.stop()
        finally:
            self._stopped = True
            self._draining = False
            self._drain_complete.set()
            logger.info("agent_pool_drained")

    async def restart_one_idle_agent(self) -> bool:
        """Stop and recreate one idle agent (any registered type) for recovery testing."""

        async with self._lock:
            chosen_type: AgentType | None = None
            agent: BaseAgent | None = None
            for agent_type, q in self._idle.items():
                if q:
                    agent = q.popleft()
                    chosen_type = agent_type
                    break
        if agent is None or chosen_type is None:
            return False
        await self._restart_agent(agent, chosen_type)
        return True

    async def wait_for_drain(self, timeout: float | None = None) -> bool:
        """Block until the pool finishes draining."""

        try:
            await asyncio.wait_for(self._drain_complete.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False
