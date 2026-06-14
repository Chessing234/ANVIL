"""Lesson CRUD tests."""

from __future__ import annotations

import pytest

from database.connection import DatabaseManager
from database.crud import incidents, lessons
from database.models import IncidentSeverity, IncidentStatus, LessonDifficulty, StudentExperience


@pytest.fixture()
async def db(tmp_path):
    path = tmp_path / "les.sqlite"
    mgr = DatabaseManager(f"sqlite+aiosqlite:///{path}")
    await mgr.initialize()
    try:
        yield mgr
    finally:
        await mgr.close()


async def test_lesson_crud_and_recommendations(db: DatabaseManager) -> None:
    async with db.session() as s:
        inc = await incidents.create(
            s,
            {
                "title": "I",
                "description": "d",
                "severity": IncidentSeverity.LOW,
                "status": IncidentStatus.OPEN,
            },
        )
        lesson = await lessons.create(
            s,
            {
                "incident_id": inc.id,
                "title": "L1",
                "narrative": "story",
                "difficulty": LessonDifficulty.INTERMEDIATE,
                "teaching_effectiveness_score": 0.9,
            },
        )
        lid = lesson.id
        by_i = await lessons.get_by_incident(s, inc.id)
        assert len(by_i) == 1
        by_d = await lessons.get_by_difficulty(s, LessonDifficulty.INTERMEDIATE)
        assert any(x.id == lid for x in by_d)
        await lessons.update_effectiveness(s, lid, 0.95)
        rec = await lessons.get_recommended(s, {"experience_level": StudentExperience.INTERMEDIATE.value})
        assert any(x.id == lid for x in rec)
