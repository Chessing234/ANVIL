"""Incident CRUD and statistics tests."""

from __future__ import annotations

import uuid

import pytest

from database.connection import DatabaseManager
from database.crud import incidents
from database.models import IncidentSeverity, IncidentStatus


@pytest.fixture()
async def db(tmp_path):
    path = tmp_path / "inc.sqlite"
    mgr = DatabaseManager(f"sqlite+aiosqlite:///{path}")
    await mgr.initialize()
    try:
        yield mgr
    finally:
        await mgr.close()


async def test_incident_crud_and_stats(db: DatabaseManager) -> None:
    async with db.session() as s:
        inc = await incidents.create(
            s,
            {
                "title": "Phish",
                "description": "d",
                "severity": IncidentSeverity.MEDIUM,
                "status": IncidentStatus.OPEN,
            },
        )
        iid = inc.id
        got = await incidents.get_by_id(s, iid)
        assert got is not None
        await incidents.update_status(s, iid, IncidentStatus.RESOLVED)
        await incidents.update_accuracy_report(s, iid, {"precision": 0.9})
        await incidents.create(
            s,
            {
                "title": "Malware",
                "description": "x",
                "severity": IncidentSeverity.HIGH,
                "status": IncidentStatus.CLOSED,
            },
        )

    async with db.session() as s:
        stats = await incidents.get_statistics(s)
        assert stats.by_status[IncidentStatus.RESOLVED.value] >= 1
        assert stats.by_severity[IncidentSeverity.HIGH.value] >= 1
        active = await incidents.get_active(s)
        assert all(x.status not in (IncidentStatus.RESOLVED, IncidentStatus.CLOSED) for x in active)


async def test_get_all_filters(db: DatabaseManager) -> None:
    async with db.session() as s:
        await incidents.create(
            s,
            {
                "title": "T1",
                "description": "d",
                "severity": IncidentSeverity.LOW,
                "status": IncidentStatus.OPEN,
            },
        )
        rows = await incidents.get_all(s, status=IncidentStatus.OPEN, severity=IncidentSeverity.LOW, limit=5)
        assert len(rows) == 1


async def test_get_by_id_missing(db: DatabaseManager) -> None:
    async with db.session() as s:
        assert await incidents.get_by_id(s, uuid.uuid4()) is None
