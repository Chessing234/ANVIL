"""Integration: SQLAlchemy relationships honor FK and cascade rules."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select

from api.converters import database_url_to_async
from config.settings import get_settings
from database.connection import DatabaseManager
from database.models import (
    Incident,
    IncidentSeverity,
    IncidentStatus,
    Lesson,
    LessonDifficulty,
    Student,
    StudentExperience,
    StudentProgress,
)


@pytest.mark.asyncio
async def test_lesson_cascades_with_incident(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "cascade.sqlite"
    monkeypatch.setenv("TUTORIAL_DATABASE__URL", f"sqlite+aiosqlite:///{db_path}")
    get_settings.cache_clear()
    settings = get_settings()
    url = database_url_to_async(settings.database.url)
    mgr = DatabaseManager(url, pool_size=2, echo=False)
    await mgr.initialize()
    inc_id = uuid.uuid4()
    lesson_id = uuid.uuid4()
    student_id = uuid.uuid4()
    progress_id = uuid.uuid4()
    try:
        async with mgr.session() as session:
            session.add(
                Incident(
                    id=inc_id,
                    title="Cascade parent",
                    description="d",
                    severity=IncidentSeverity.MEDIUM,
                    status=IncidentStatus.OPEN,
                    incident_type="test",
                ),
            )
            session.add(
                Lesson(
                    id=lesson_id,
                    incident_id=inc_id,
                    title="Child lesson",
                    narrative="n",
                    difficulty=LessonDifficulty.BEGINNER,
                ),
            )
            session.add(
                Student(
                    id=student_id,
                    name="Casey",
                    email="casey@tutorial.test",
                    experience_level=StudentExperience.NOVICE,
                ),
            )
            session.add(
                StudentProgress(
                    id=progress_id,
                    student_id=student_id,
                    lesson_id=lesson_id,
                    completion_percentage=0.5,
                    score=0.5,
                    hints_used=0,
                    time_spent_minutes=1,
                    interactions=[],
                ),
            )
        async with mgr.session() as session:
            row = await session.get(Incident, inc_id)
            assert row is not None
            await session.delete(row)
        async with mgr.session() as session:
            assert await session.get(Lesson, lesson_id) is None
            cnt = await session.scalar(
                select(func.count()).select_from(StudentProgress).where(StudentProgress.lesson_id == lesson_id),
            )
            assert int(cnt or 0) == 0
    finally:
        await mgr.close()
        get_settings.cache_clear()
