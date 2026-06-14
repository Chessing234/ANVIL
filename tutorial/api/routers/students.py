"""Student profile and recommendations HTTP API."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status

from api.converters import demo_credential_hash
from api.dependencies import CurrentUser, DbSession
from api.schemas import CredentialEntry, LessonRecommendation, StudentCreate, StudentDetail, StudentProgressItem, StudentResponse
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
    """Return demo blockchain-style credentials."""
    row = await students_crud.get_by_id(db, student_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
    digest = demo_credential_hash(student_id)
    return [
        CredentialEntry(
            credential_id=f"cred-{student_id}",
            student_id=student_id,
            issued_at=datetime.now(timezone.utc).isoformat(),
            verification_hash=digest,
        )
    ]
