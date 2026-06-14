"""Lesson and curriculum HTTP API."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from starlette.responses import Response

from api.dependencies import CoordinatorDep, CurrentUser, DbSession
from api.workflow_persistence import sync_latest_lesson_for_incident
from api.schemas import (
    InteractionData,
    LessonDetail,
    LessonGenerateRequest,
    LessonGenerateResponse,
    LessonResponse,
    SandboxInfoResponse,
)
from database.crud import lessons as lessons_crud
from database.crud import students as students_crud
from database.models import LessonDifficulty
from shared.models import StudentProfile

router = APIRouter()


def _lesson_summary(row: object) -> LessonResponse:
    return LessonResponse(
        id=row.id,
        incident_id=row.incident_id,
        title=row.title,
        narrative=row.narrative,
        difficulty=row.difficulty.value,
        estimated_duration_minutes=row.estimated_duration_minutes,
        created_at=row.created_at,
    )


@router.post("/generate", response_model=LessonGenerateResponse, status_code=status.HTTP_201_CREATED)
async def generate_lesson(
    data: LessonGenerateRequest,
    db: DbSession,
    coordinator: CoordinatorDep,
    _: CurrentUser,
) -> LessonGenerateResponse:
    """Generate an interactive lesson anchored to a defended incident."""
    profile = StudentProfile(
        name=data.student_name,
        experience_level=data.experience_level,
        preferred_learning_style=data.preferred_learning_style,
    )
    ticket = await coordinator.submit_lesson_request(str(data.incident_id), profile)
    await sync_latest_lesson_for_incident(db, data.incident_id, coordinator)
    return LessonGenerateResponse(
        incident_id=ticket.incident_id,
        lesson_id=ticket.lesson_id,
        teaching_thread_id=ticket.teaching_thread_id,
        status=ticket.status,
    )


@router.get("/", response_model=list[LessonResponse])
async def list_lessons(
    db: DbSession,
    _: CurrentUser,
    difficulty: str | None = None,
) -> list[LessonResponse]:
    """List persisted lessons, optionally filtered by difficulty."""
    if difficulty is None:
        rows = await lessons_crud.list_all(db)
    else:
        rows = await lessons_crud.get_by_difficulty(db, LessonDifficulty(difficulty))
    return [_lesson_summary(r) for r in rows]


@router.get("/{lesson_id}/curriculum-mapping")
async def get_curriculum_mapping(lesson_id: uuid.UUID, db: DbSession, _: CurrentUser) -> dict[str, object]:
    """Return CSTA standards linked to a persisted lesson (curriculum alignment)."""
    row = await lessons_crud.get_by_id(db, lesson_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lesson not found")
    standards = [str(x) for x in (row.csta_standards or [])]
    return {
        "lesson_id": str(lesson_id),
        "incident_id": str(row.incident_id),
        "standards_covered": standards,
        "concept_coverage": dict(row.concept_coverage or {}),
    }


@router.get("/{lesson_id}", response_model=LessonDetail)
async def get_lesson(lesson_id: uuid.UUID, db: DbSession, _: CurrentUser) -> LessonDetail:
    """Return lesson narrative and interactive elements."""
    row = await lessons_crud.get_by_id(db, lesson_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lesson not found")
    return LessonDetail(
        id=row.id,
        incident_id=row.incident_id,
        title=row.title,
        narrative=row.narrative,
        interactive_elements=list(row.interactive_elements or []),
        difficulty=row.difficulty.value,
        csta_standards=list(row.csta_standards or []),
        estimated_duration_minutes=row.estimated_duration_minutes,
        concept_coverage=dict(row.concept_coverage or {}),
        teaching_effectiveness_score=row.teaching_effectiveness_score,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post("/{lesson_id}/start", status_code=status.HTTP_201_CREATED)
async def start_lesson(
    lesson_id: uuid.UUID,
    student_id: uuid.UUID,
    db: DbSession,
    _: CurrentUser,
) -> dict[str, str]:
    """Initialize progress tracking for a student."""
    row = await lessons_crud.get_by_id(db, lesson_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lesson not found")
    if await students_crud.get_by_id(db, student_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
    await students_crud.update_progress(
        db,
        student_id,
        lesson_id,
        {"completion_percentage": 0.0, "score": 0.0, "hints_used": 0, "time_spent_minutes": 0, "interactions": []},
    )
    return {"lesson_id": str(lesson_id), "student_id": str(student_id), "status": "started"}


@router.post("/{lesson_id}/interaction")
async def record_interaction(
    lesson_id: uuid.UUID,
    data: InteractionData,
    db: DbSession,
    _: CurrentUser,
) -> Response:
    """Append a structured interaction to the student's progress row."""
    if await lessons_crud.get_by_id(db, lesson_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lesson not found")
    from sqlalchemy import select

    from database.models import StudentProgress

    stmt = select(StudentProgress).where(
        StudentProgress.student_id == data.student_id,
        StudentProgress.lesson_id == lesson_id,
    )
    prog = await db.scalar(stmt)
    if prog is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Progress not found; call /start first")
    interactions = list(prog.interactions or [])
    interactions.append(data.interaction)
    await students_crud.update_progress(
        db,
        data.student_id,
        lesson_id,
        {"interactions": interactions},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{lesson_id}/sandbox", response_model=SandboxInfoResponse)
async def get_sandbox(lesson_id: uuid.UUID, db: DbSession, _: CurrentUser) -> SandboxInfoResponse:
    """Describe sandbox expectations for the lesson."""
    row = await lessons_crud.get_by_id(db, lesson_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lesson not found")
    return SandboxInfoResponse(
        lesson_id=row.id,
        sandbox_mode="docker",
        resources={"difficulty": row.difficulty.value, "incident_id": str(row.incident_id)},
    )
