"""Agent monitoring HTTP API."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from api.dependencies import CoordinatorDep, CurrentUser, DbSession
from api.schemas import AgentMetricsResponse, AgentStatusResponse
from database.crud import agents as agents_crud
from database.models import AgentStatus

router = APIRouter()


def _agent_row_response(a: object) -> AgentStatusResponse:
    return AgentStatusResponse(
        id=a.id,
        name=a.name,
        agent_type=a.agent_type.value,
        status=a.status.value,
        tasks_completed=a.tasks_completed,
        tasks_failed=a.tasks_failed,
        avg_task_duration_ms=a.avg_task_duration_ms,
        uptime_seconds=a.uptime_seconds,
        last_heartbeat_at=a.last_heartbeat_at,
    )


@router.get("/", response_model=list[AgentStatusResponse])
async def list_agents(db: DbSession, _: CurrentUser) -> list[AgentStatusResponse]:
    """List registered agents and their persisted status."""
    rows = await agents_crud.list_all(db)
    return [_agent_row_response(r) for r in rows]


@router.get("/{agent_name}/metrics", response_model=AgentMetricsResponse)
async def get_agent_metrics(agent_name: str, db: DbSession, _: CurrentUser) -> AgentMetricsResponse:
    """Return aggregate metrics for a named agent."""
    agent = await agents_crud.get_by_name(db, agent_name)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    total = agent.tasks_completed + agent.tasks_failed
    fail_rate = (agent.tasks_failed / total) if total else 0.0
    return AgentMetricsResponse(
        name=agent.name,
        tasks_completed=agent.tasks_completed,
        tasks_failed=agent.tasks_failed,
        avg_task_duration_ms=agent.avg_task_duration_ms,
        uptime_seconds=agent.uptime_seconds,
        failure_rate=fail_rate,
    )


@router.post("/{agent_name}/pause", status_code=status.HTTP_200_OK)
async def pause_agent(
    agent_name: str,
    db: DbSession,
    coordinator: CoordinatorDep,
    _: CurrentUser,
) -> dict[str, str]:
    """Mark an agent offline in persistence (demo pause)."""
    _ = coordinator  # reserved for future orchestration hooks
    try:
        await agents_crud.set_status_by_name(db, agent_name, AgentStatus.OFFLINE)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found") from exc
    return {"agent": agent_name, "status": "paused"}


@router.post("/{agent_name}/resume", status_code=status.HTTP_200_OK)
async def resume_agent(
    agent_name: str,
    db: DbSession,
    coordinator: CoordinatorDep,
    _: CurrentUser,
) -> dict[str, str]:
    """Mark an agent active again."""
    _ = coordinator
    try:
        await agents_crud.set_status_by_name(db, agent_name, AgentStatus.ACTIVE)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found") from exc
    return {"agent": agent_name, "status": "resumed"}
