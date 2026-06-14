"""Student and progress CRUD tests."""

from __future__ import annotations

import pytest

from database.connection import DatabaseManager
from database.crud import incidents, lessons, students
from database.models import IncidentSeverity, IncidentStatus, LessonDifficulty, StudentExperience


@pytest.fixture()
async def db(tmp_path):
    path = tmp_path / "stu.sqlite"
    mgr = DatabaseManager(f"sqlite+aiosqlite:///{path}")
    await mgr.initialize()
    try:
        yield mgr
    finally:
        await mgr.close()


async def test_student_progress_and_weak_areas(db: DatabaseManager) -> None:
    async with db.session() as s:
        st = await students.create(
            s,
            {
                "name": "Sam",
                "email": "sam@example.com",
                "experience_level": StudentExperience.INTERMEDIATE,
                "skill_scores": {"dns": 0.8, "xss": 0.2},
            },
        )
        inc = await incidents.create(
            s,
            {
                "title": "I",
                "description": "d",
                "severity": IncidentSeverity.LOW,
                "status": IncidentStatus.OPEN,
            },
        )
        les = await lessons.create(
            s,
            {
                "incident_id": inc.id,
                "title": "Lesson",
                "difficulty": LessonDifficulty.BEGINNER,
            },
        )
        prog = await students.update_progress(
            s,
            st.id,
            les.id,
            {"completion_percentage": 100.0, "score": 92.0, "hints_used": 1, "time_spent_minutes": 12},
        )
        assert prog.completed_at is not None
        scores = await students.get_skill_scores(s, st.id)
        assert scores["dns"] == 0.8
        weak = await students.get_weak_areas(s, st.id)
        assert "xss" in weak
