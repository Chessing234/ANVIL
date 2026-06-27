"""Student profile and recommendations HTTP API."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status

from api.converters import demo_credential_hash
from api.dependencies import CurrentUser, DbSession
from api.schemas import CredentialEntry, LessonRecommendation, StudentCreate, StudentDetail, StudentProgressItem, StudentResponse
from config.constants import DEMO_STUDENT_EMAIL, DEMO_STUDENT_ID
from database.crud import lessons as lessons_crud
from database.crud import students as students_crud
from database.models import StudentExperience

router = APIRouter()


def _student_response(row: object) -> StudentResponse:
    return StudentResponse(
        id=row.id,
        name=row.name,
        email=row.email,
        experience_level=row.experience_level.value,
        preferred_learning_style=row.preferred_learning_style,
        streak_days=row.streak_days,
        total_time_minutes=row.total_time_minutes,
        created_at=row.created_at,
        last_active_at=row.last_active_at,
    )


@router.post("/", response_model=StudentResponse, status_code=status.HTTP_201_CREATED)
async def create_student(data: StudentCreate, db: DbSession, _: CurrentUser) -> StudentResponse:
    """Register a learner."""
    try:
        level = StudentExperience(data.experience_level)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    row = await students_crud.create(
        db,
        {
            "name": data.name,
            "email": data.email,
            "experience_level": level,
            "preferred_learning_style": data.preferred_learning_style,
            "skill_scores": data.skill_scores,
        },
    )
    return _student_response(row)


@router.get("/demo", response_model=StudentResponse)
async def get_demo_student(db: DbSession, _: CurrentUser) -> StudentResponse:
    """Return the stable demo learner (seeded on startup)."""
    row = await students_crud.get_by_id(db, DEMO_STUDENT_ID)
    if row is None:
        row = await students_crud.get_by_email(db, DEMO_STUDENT_EMAIL)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Demo student not seeded")
    return _student_response(row)


@router.get("/{student_id}", response_model=StudentDetail)
async def get_student(student_id: uuid.UUID, db: DbSession, _: CurrentUser) -> StudentDetail:
    """Return a student and their progress rows."""
    row = await students_crud.get_by_id(db, student_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
    progress = await students_crud.list_progress(db, student_id)
    items = [StudentProgressItem.model_validate(p, from_attributes=True) for p in progress]
    return StudentDetail(student=_student_response(row), progress=items)


@router.get("/{student_id}/progress", response_model=list[StudentProgressItem])
async def get_student_progress(student_id: uuid.UUID, db: DbSession, _: CurrentUser) -> list[StudentProgressItem]:
    """Return progress rows for the learner."""
    if await students_crud.get_by_id(db, student_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
    progress = await students_crud.list_progress(db, student_id)
    return [StudentProgressItem.model_validate(p, from_attributes=True) for p in progress]


@router.get("/{student_id}/recommendations", response_model=list[LessonRecommendation])
async def get_recommendations(student_id: uuid.UUID, db: DbSession, _: CurrentUser) -> list[LessonRecommendation]:
    """Recommend lessons using the knowledge-backed heuristic."""
    row = await students_crud.get_by_id(db, student_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
    profile = {
        "experience_level": row.experience_level.value,
        "preferred_learning_style": row.preferred_learning_style,
    }
    recs = await lessons_crud.get_recommended(db, profile)
    return [
        LessonRecommendation(
            id=str(les.id),
            title=les.title,
            difficulty=les.difficulty.value,
            incident_id=str(les.incident_id),
        )
        for les in recs
    ]


@router.get("/{student_id}/credentials", response_model=list[CredentialEntry])
async def get_credentials(student_id: uuid.UUID, db: DbSession, _: CurrentUser) -> list[CredentialEntry]:
    """Return blockchain-style credentials derived from completed lesson progress."""
    row = await students_crud.get_by_id(db, student_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")

    entries: list[CredentialEntry] = []
    progress = await students_crud.list_progress(db, student_id)
    for prog in progress:
        if prog.completion_percentage < 100.0 and prog.completed_at is None:
            continue
        lesson = await lessons_crud.get_by_id(db, prog.lesson_id)
        if lesson is None:
            continue
        digest = demo_credential_hash(uuid.uuid5(uuid.NAMESPACE_URL, f"{student_id}:{prog.lesson_id}"))
        issued = prog.completed_at or datetime.now(timezone.utc)
        entries.append(
            CredentialEntry(
                credential_id=f"cred-{prog.lesson_id}",
                student_id=student_id,
                lesson_id=prog.lesson_id,
                concept_name=lesson.title,
                score=round(float(prog.score) * 100.0, 1) if prog.score <= 1.0 else round(float(prog.score), 1),
                category=str(lesson.difficulty.value),
                issued_at=issued.isoformat(),
                verification_hash=digest,
            ),
        )

    if not entries:
        digest = demo_credential_hash(student_id)
        entries.append(
            CredentialEntry(
                credential_id=f"cred-{student_id}",
                student_id=student_id,
                concept_name="SOC Foundations",
                score=100.0,
                category="ops",
                issued_at=datetime.now(timezone.utc).isoformat(),
                verification_hash=digest,
            ),
        )
    return entries
