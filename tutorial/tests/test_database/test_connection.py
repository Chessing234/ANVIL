"""Tests for ``DatabaseManager`` lifecycle and health checks."""

from __future__ import annotations

import pytest

from database.connection import DatabaseManager


@pytest.fixture()
async def db(tmp_path):
    path = tmp_path / "conn.sqlite"
    mgr = DatabaseManager(f"sqlite+aiosqlite:///{path}")
    await mgr.initialize()
    try:
        yield mgr
    finally:
        await mgr.close()


async def test_initialize_and_health(db: DatabaseManager) -> None:
    assert await db.health_check() is True


async def test_session_commit_and_rollback(db: DatabaseManager) -> None:
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy import text

    from database.models import Student, StudentExperience

    async with db.session() as s:
        s.add(
            Student(
                name="A",
                email="a@example.com",
                experience_level=StudentExperience.NOVICE,
            )
        )
    async with db.session() as s:
        s.add(
            Student(
                name="B",
                email="a@example.com",
                experience_level=StudentExperience.NOVICE,
            )
        )
        with pytest.raises(IntegrityError):
            await s.flush()

    async with db.session() as s:
        n = await s.scalar(text("select count(*) from students"))
        assert int(n) == 1
