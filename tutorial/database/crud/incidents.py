"""Incident CRUD and aggregate statistics."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import structlog
from pydantic import BaseModel, Field
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Incident, IncidentSeverity, IncidentStatus

logger = structlog.get_logger(__name__)


class IncidentStats(BaseModel):
    """Aggregate incident metrics for dashboards."""

    model_config = {"extra": "forbid"}

    by_status: dict[str, int] = Field(default_factory=dict)
    by_severity: dict[str, int] = Field(default_factory=dict)
    avg_resolution_seconds: float | None = None


async def create(session: AsyncSession, incident_data: dict[str, Any]) -> Incident:
    """Persist a new incident row."""
    payload = dict(incident_data)
    if "id" not in payload:
        payload["id"] = uuid.uuid4()
    cols = {c.key for c in Incident.__mapper__.column_attrs}
    inc = Incident(**{k: v for k, v in payload.items() if k in cols})
    session.add(inc)
    await session.flush()
    logger.info("incident_created", incident_id=str(inc.id))
    return inc


async def get_by_id(session: AsyncSession, incident_id: uuid.UUID) -> Optional[Incident]:
    return await session.get(Incident, incident_id)


async def get_all(
    session: AsyncSession,
    *,
    status: IncidentStatus | None = None,
    severity: IncidentSeverity | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Incident]:
    stmt: Select[tuple[Incident]] = select(Incident).order_by(Incident.created_at.desc())
    if status is not None:
        stmt = stmt.where(Incident.status == status)
    if severity is not None:
        stmt = stmt.where(Incident.severity == severity)
    stmt = stmt.offset(offset).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def update_status(session: AsyncSession, incident_id: uuid.UUID, new_status: IncidentStatus) -> Incident:
    inc = await session.get(Incident, incident_id)
    if inc is None:
        raise KeyError(f"Incident not found: {incident_id}")
    inc.status = new_status
    if new_status in (IncidentStatus.RESOLVED, IncidentStatus.CLOSED) and inc.completed_at is None:
        inc.completed_at = datetime.now(timezone.utc)
    await session.flush()
    return inc


async def update_accuracy_report(
    session: AsyncSession, incident_id: uuid.UUID, report: dict[str, Any]
) -> Incident:
    inc = await session.get(Incident, incident_id)
    if inc is None:
        raise KeyError(f"Incident not found: {incident_id}")
    inc.accuracy_report = report
    await session.flush()
    return inc


async def get_active(session: AsyncSession) -> list[Incident]:
    stmt = (
        select(Incident)
        .where(Incident.status.not_in((IncidentStatus.RESOLVED, IncidentStatus.CLOSED)))
        .order_by(Incident.created_at.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_statistics(session: AsyncSession) -> IncidentStats:
    """Compute counts by status/severity and average resolution duration."""
    by_status: dict[str, int] = {}
    for st in IncidentStatus:
        cnt = await session.scalar(select(func.count()).select_from(Incident).where(Incident.status == st))
        by_status[st.value] = int(cnt or 0)
    by_severity: dict[str, int] = {}
    for sev in IncidentSeverity:
        cnt = await session.scalar(select(func.count()).select_from(Incident).where(Incident.severity == sev))
        by_severity[sev.value] = int(cnt or 0)

    stmt = select(
        func.avg(
            func.julianday(Incident.completed_at) - func.julianday(Incident.created_at)
        )
    ).where(Incident.completed_at.is_not(None))
    avg_days = await session.scalar(stmt)
    avg_seconds = float(avg_days) * 86400.0 if avg_days is not None else None
    return IncidentStats(by_status=by_status, by_severity=by_severity, avg_resolution_seconds=avg_seconds)
