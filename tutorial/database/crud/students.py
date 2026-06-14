"""Student and progress CRUD."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Student, StudentProgress

_WEAK_THRESHOLD = 0.55


async def create(session: AsyncSession, student_data: dict[str, Any]) -> Student:
    """Insert a student; ``email`` must be unique."""
    cols = {c.key for c in Student.__mapper__.column_attrs}
    data = {k: v for k, v in student_data.items() if k in cols}
    if "id" not in data:
        data["id"] = uuid.uuid4()
    student = Student(**data)
    session.add(student)
    await session.flush()
    return student


async def get_by_id(session: AsyncSession, student_id: uuid.UUID) -> Student | None:
    return await session.get(Student, student_id)


async def list_progress(session: AsyncSession, student_id: uuid.UUID) -> list[StudentProgress]:
    """Return all progress rows for a student."""
    stmt = (
        select(StudentProgress)
        .where(StudentProgress.student_id == student_id)
        .order_by(StudentProgress.updated_at.desc())
    )
    rows = await session.execute(stmt)
    return list(rows.scalars().all())


async def update_progress(
    session: AsyncSession,
    student_id: uuid.UUID,
    lesson_id: uuid.UUID,
    progress_data: dict[str, Any],
) -> StudentProgress:
    """Create or update ``StudentProgress`` for a student/lesson pair."""
    stmt = select(StudentProgress).where(
        StudentProgress.student_id == student_id,
        StudentProgress.lesson_id == lesson_id,
    )
    row = await session.scalar(stmt)
    cols = {c.key for c in StudentProgress.__mapper__.column_attrs}
    fields = {k: v for k, v in progress_data.items() if k in cols and k not in {"id", "student_id", "lesson_id"}}
    if row is None:
        pid = progress_data.get("id") or uuid.uuid4()
        row = StudentProgress(id=pid, student_id=student_id, lesson_id=lesson_id, **fields)
        session.add(row)
    else:
        for k, v in fields.items():
            setattr(row, k, v)
    if row.completion_percentage >= 100.0 and row.completed_at is None:
        row.completed_at = datetime.now(timezone.utc)
    student = await session.get(Student, student_id)
    if student is not None:
        student.last_active_at = datetime.now(timezone.utc)
    await session.flush()
    return row


async def get_skill_scores(session: AsyncSession, student_id: uuid.UUID) -> dict[str, Any]:
    student = await session.get(Student, student_id)
    if student is None:
        raise KeyError(f"Student not found: {student_id}")
    return dict(student.skill_scores)


async def get_weak_areas(session: AsyncSession, student_id: uuid.UUID) -> list[str]:
    """Return concept/skill keys whose stored scores fall below the weak threshold."""
    scores = await get_skill_scores(session, student_id)
    weak: list[str] = []
    for key, val in scores.items():
        try:
            num = float(val)
        except (TypeError, ValueError):
            continue
        if num < _WEAK_THRESHOLD:
            weak.append(str(key))
    return sorted(weak)
