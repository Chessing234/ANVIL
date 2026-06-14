"""Evidence CRUD, integrity verification, and custody helpers."""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Evidence


async def create(session: AsyncSession, incident_id: uuid.UUID, evidence_data: dict[str, Any]) -> Evidence:
    payload = dict(evidence_data)
    if "metadata" in payload and "metadata_" not in payload:
        payload["metadata_"] = payload.pop("metadata")
    cols = {c.key for c in Evidence.__mapper__.column_attrs}
    data = {k: v for k, v in payload.items() if k in cols and k != "incident_id"}
    data["incident_id"] = incident_id
    if "id" not in data:
        data["id"] = uuid.uuid4()
    ev = Evidence(**data)
    session.add(ev)
    await session.flush()
    return ev


async def get_by_incident(session: AsyncSession, incident_id: uuid.UUID) -> list[Evidence]:
    stmt = select(Evidence).where(Evidence.incident_id == incident_id).order_by(Evidence.created_at.asc())
    rows = await session.execute(stmt)
    return list(rows.scalars().all())


async def verify_integrity(session: AsyncSession, evidence_id: uuid.UUID) -> bool:
    """Recompute SHA-256 for on-disk evidence (or validate empty path against stored hash)."""
    ev = await session.get(Evidence, evidence_id)
    if ev is None:
        return False
    path = Path(ev.file_path)
    if not path.is_file():
        return ev.hash_sha256 == "" or ev.file_size_bytes == 0
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest == ev.hash_sha256


async def get_chain_of_custody(session: AsyncSession, evidence_id: uuid.UUID) -> list[dict[str, Any]]:
    ev = await session.get(Evidence, evidence_id)
    if ev is None:
        return []
    chain = ev.custody_chain
    if isinstance(chain, list):
        return [dict(x) if isinstance(x, dict) else {"entry": x} for x in chain]
    return []
