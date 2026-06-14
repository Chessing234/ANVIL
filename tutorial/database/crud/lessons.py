"""Lesson CRUD and lightweight recommendations."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Lesson, LessonDifficulty, StudentExperience


async def create(session: AsyncSession, lesson_data: dict[str, Any]) -> Lesson:
    cols = {c.key for c in Lesson.__mapper__.column_attrs}
    data = {k: v for k, v in lesson_data.items() if k in cols}
    if "id" not in data:
        data["id"] = uuid.uuid4()
    lesson = Lesson(**data)
    session.add(lesson)
    await session.flush()
    return lesson


async def get_by_id(session: AsyncSession, lesson_id: uuid.UUID) -> Lesson | None:
    return await session.get(Lesson, lesson_id)


async def get_by_incident(session: AsyncSession, incident_id: uuid.UUID) -> list[Lesson]:
    stmt = select(Lesson).where(Lesson.incident_id == incident_id).order_by(Lesson.created_at.asc())
    rows = await session.execute(stmt)
    return list(rows.scalars().all())


async def get_by_difficulty(session: AsyncSession, difficulty: LessonDifficulty) -> list[Lesson]:
    stmt = select(Lesson).where(Lesson.difficulty == difficulty).order_by(Lesson.created_at.desc())
    rows = await session.execute(stmt)
    return list(rows.scalars().all())


async def list_all(
    session: AsyncSession,
    *,
    difficulty: LessonDifficulty | None = None,
    limit: int = 500,
    offset: int = 0,
) -> list[Lesson]:
    """Return lessons ordered by recency, optionally filtered by difficulty."""
    stmt = select(Lesson).order_by(Lesson.created_at.desc())
    if difficulty is not None:
        stmt = stmt.where(Lesson.difficulty == difficulty)
    stmt = stmt.offset(offset).limit(limit)
    rows = await session.execute(stmt)
    return list(rows.scalars().all())


async def update_effectiveness(session: AsyncSession, lesson_id: uuid.UUID, score: float) -> Lesson:
    lesson = await session.get(Lesson, lesson_id)
    if lesson is None:
        raise KeyError(f"Lesson not found: {lesson_id}")
    lesson.teaching_effectiveness_score = score
    await session.flush()
    return lesson


def _map_experience_to_difficulty(level: str | None) -> LessonDifficulty:
    if level == StudentExperience.EXPERT.value:
        return LessonDifficulty.ADVANCED
    if level == StudentExperience.NOVICE.value:
        return LessonDifficulty.BEGINNER
    return LessonDifficulty.INTERMEDIATE


async def get_recommended(session: AsyncSession, student_profile: dict[str, Any]) -> list[Lesson]:
    """Recommend lessons by aligning difficulty to declared experience (deterministic heuristic)."""
    level = student_profile.get("experience_level")
    target = _map_experience_to_difficulty(str(level) if level is not None else None)
    stmt = (
        select(Lesson)
        .where(Lesson.difficulty == target)
        .order_by(Lesson.teaching_effectiveness_score.desc().nullslast(), Lesson.created_at.desc())
        .limit(10)
    )
    rows = await session.execute(stmt)
    return list(rows.scalars().all())
