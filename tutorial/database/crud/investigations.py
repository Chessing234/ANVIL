"""Investigation step CRUD and accuracy-style aggregates."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import InvestigationStep


async def create_step(
    session: AsyncSession, incident_id: uuid.UUID, step_data: dict[str, Any]
) -> InvestigationStep:
    cols = {c.key for c in InvestigationStep.__mapper__.column_attrs}
    data = {k: v for k, v in step_data.items() if k in cols and k != "incident_id"}
    data["incident_id"] = incident_id
    if "id" not in data:
        data["id"] = uuid.uuid4()
    step = InvestigationStep(**data)
    session.add(step)
    await session.flush()
    return step


async def get_steps_for_incident(session: AsyncSession, incident_id: uuid.UUID) -> list[InvestigationStep]:
    stmt = (
        select(InvestigationStep)
        .where(InvestigationStep.incident_id == incident_id)
        .order_by(InvestigationStep.timestamp.asc())
    )
    rows = await session.execute(stmt)
    return list(rows.scalars().all())


async def get_self_corrections(session: AsyncSession, incident_id: uuid.UUID) -> list[InvestigationStep]:
    stmt = (
        select(InvestigationStep)
        .where(
            InvestigationStep.incident_id == incident_id,
            InvestigationStep.is_self_correction.is_(True),
        )
        .order_by(InvestigationStep.timestamp.asc())
    )
    rows = await session.execute(stmt)
    return list(rows.scalars().all())


async def get_accuracy_metrics(session: AsyncSession, incident_id: uuid.UUID) -> dict[str, Any]:
    """Summarize investigation quality for reporting (confidence, corrections, latency)."""
    steps = await get_steps_for_incident(session, incident_id)
    if not steps:
        return {"steps": 0, "mean_confidence": None, "self_corrections": 0, "mean_execution_ms": None}
    confs = [s.confidence for s in steps]
    execs = [s.execution_time_ms for s in steps]
    corrections = sum(1 for s in steps if s.is_self_correction)
    return {
        "steps": len(steps),
        "mean_confidence": sum(confs) / len(confs),
        "self_corrections": corrections,
        "mean_execution_ms": sum(execs) / len(execs),
    }
