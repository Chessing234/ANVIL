"""System health and administration HTTP API."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request, Response, status
from sqlalchemy import func, select, text

from api.dependencies import CoordinatorDep, CurrentUser, DbSession
from api.schemas import SystemMetricsResponse
from database.models import Agent, Incident, Lesson, Student

router = APIRouter()


@router.get("/flywheel")
async def flywheel_snapshot(coordinator: CoordinatorDep, _: CurrentUser) -> dict[str, Any]:
    """Orchestration knowledge graph stats and flywheel signals (defense → teaching loop)."""
    return await coordinator.get_flywheel_snapshot()


@router.get("/health")
async def health_check(request: Request, response: Response) -> dict[str, object]:
    """Liveness probe combining database connectivity and coordinator readiness."""
    db_manager = request.app.state.db_manager
    coordinator: object = request.app.state.coordinator
    database_healthy = False
    try:
        async with db_manager.session() as s:
            res = await s.execute(text("SELECT 1"))
            database_healthy = res.scalar() == 1
    except Exception:
        database_healthy = False
    coord_ok = bool(getattr(coordinator, "_initialized", False))
    ok = database_healthy and coord_ok
    response.status_code = status.HTTP_200_OK if ok else status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ok" if ok else "degraded",
        "database": database_healthy,
        "coordinator_initialized": coord_ok,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/metrics", response_model=SystemMetricsResponse)
async def get_metrics(db: DbSession, _: CurrentUser) -> SystemMetricsResponse:
    """Return aggregate entity counts."""
    ni = int(await db.scalar(select(func.count()).select_from(Incident)) or 0)
    nl = int(await db.scalar(select(func.count()).select_from(Lesson)) or 0)
    ns = int(await db.scalar(select(func.count()).select_from(Student)) or 0)
    na = int(await db.scalar(select(func.count()).select_from(Agent)) or 0)
    return SystemMetricsResponse(incidents=ni, lessons=nl, students=ns, agents=na)


@router.post("/shutdown", status_code=status.HTTP_200_OK)
async def shutdown(coordinator: CoordinatorDep, _: CurrentUser) -> dict[str, str]:
    """Request a graceful coordinator shutdown."""
    await coordinator.shutdown()
    return {"status": "shutdown_requested"}
