"""ORM ↔ domain helpers for API routes."""

from __future__ import annotations

import uuid

from config.constants import IncidentSeverity as SharedIncidentSeverity
from database import models as dbm
from shared.models import Incident as SharedIncident


def database_url_to_async(url: str) -> str:
    """Normalize settings URLs for ``sqlalchemy.ext.asyncio`` engines."""
    u = url.strip()
    if u.startswith("sqlite+") or u.startswith("postgresql+asyncpg"):
        return u
    if u.startswith("postgresql://"):
        return "postgresql+asyncpg://" + u.removeprefix("postgresql://")
    if u.startswith("sqlite:///"):
        return "sqlite+aiosqlite:///" + u.removeprefix("sqlite:///")
    if u.startswith("sqlite://"):
        return "sqlite+aiosqlite://" + u.removeprefix("sqlite://")
    return u


def orm_incident_to_shared(row: dbm.Incident) -> SharedIncident:
    """Map a SQLAlchemy ``Incident`` row to the defense workflow ``Incident`` model."""
    sev = SharedIncidentSeverity(str(row.severity.value))
    refs_raw = row.raw_evidence_refs or []
    refs: list[str] = [str(x) for x in refs_raw]
    agents_raw = row.assigned_agents or []
    agents: list[str] = [str(x) for x in agents_raw]
    return SharedIncident(
        id=row.id,
        title=row.title,
        description=row.description,
        severity=sev,
        source_ip=row.source_ip,
        target_asset=row.target_asset,
        raw_evidence_refs=refs,
        status=str(row.status.value if hasattr(row.status, "value") else row.status),
        assigned_agents=agents,
    )


def demo_credential_hash(student_id: uuid.UUID) -> str:
    """Deterministic pseudo-chain digest for credential demos."""
    return uuid.uuid5(uuid.NAMESPACE_URL, f"tutorial:credential:{student_id}").hex
