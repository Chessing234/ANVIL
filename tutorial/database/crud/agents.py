"""Agent registry CRUD and lightweight health summaries."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Agent, AgentStatus


class AgentHealth(BaseModel):
    """Per-agent health snapshot for orchestration dashboards."""

    model_config = {"extra": "forbid"}

    agent_id: uuid.UUID
    name: str
    status: str
    tasks_completed: int
    tasks_failed: int
    failure_rate: float
    avg_task_duration_ms: float
    uptime_seconds: float
    last_heartbeat_at: datetime | None = None


async def create(session: AsyncSession, agent_data: dict[str, Any]) -> Agent:
    cols = {c.key for c in Agent.__mapper__.column_attrs}
    data = {k: v for k, v in agent_data.items() if k in cols}
    if "id" not in data:
        data["id"] = uuid.uuid4()
    agent = Agent(**data)
    session.add(agent)
    await session.flush()
    return agent


async def update_metrics(session: AsyncSession, agent_id: uuid.UUID, metrics: dict[str, Any]) -> Agent:
    agent = await session.get(Agent, agent_id)
    if agent is None:
        raise KeyError(f"Agent not found: {agent_id}")
    cols = {c.key for c in Agent.__mapper__.column_attrs}
    for k, v in metrics.items():
        if k in cols and k != "id":
            setattr(agent, k, v)
    agent.last_heartbeat_at = datetime.now(timezone.utc)
    await session.flush()
    return agent


async def get_all_active(session: AsyncSession) -> list[Agent]:
    stmt = select(Agent).where(Agent.status == AgentStatus.ACTIVE).order_by(Agent.name.asc())
    rows = await session.execute(stmt)
    return list(rows.scalars().all())


async def list_all(session: AsyncSession) -> list[Agent]:
    """Return every registered agent row."""
    stmt = select(Agent).order_by(Agent.name.asc())
    rows = await session.execute(stmt)
    return list(rows.scalars().all())


async def get_by_name(session: AsyncSession, name: str) -> Agent | None:
    stmt = select(Agent).where(Agent.name == name).limit(1)
    return await session.scalar(stmt)


async def set_status_by_name(session: AsyncSession, name: str, status: AgentStatus) -> Agent:
    agent = await get_by_name(session, name)
    if agent is None:
        raise KeyError(f"Agent not found: {name}")
    agent.status = status
    await session.flush()
    return agent


async def get_health_summary(session: AsyncSession) -> list[AgentHealth]:
    """Return a row per agent with derived failure rate."""
    stmt = select(Agent).order_by(Agent.name.asc())
    rows = await session.execute(stmt)
    out: list[AgentHealth] = []
    for a in rows.scalars().all():
        total = a.tasks_completed + a.tasks_failed
        fail_rate = (a.tasks_failed / total) if total else 0.0
        out.append(
            AgentHealth(
                agent_id=a.id,
                name=a.name,
                status=a.status.value,
                tasks_completed=a.tasks_completed,
                tasks_failed=a.tasks_failed,
                failure_rate=fail_rate,
                avg_task_duration_ms=a.avg_task_duration_ms,
                uptime_seconds=a.uptime_seconds,
                last_heartbeat_at=a.last_heartbeat_at,
            )
        )
    return out
