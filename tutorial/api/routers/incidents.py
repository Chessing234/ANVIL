"""Incident lifecycle HTTP API."""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

import structlog
from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from api.converters import orm_incident_to_shared
from api.dependencies import CoordinatorDep, CurrentUser, DbSession, SettingsDep
from api.schemas import IncidentCreate, IncidentDetail, IncidentResponse
from api.workflow_persistence import sync_defense_and_teach_post_submit
from database.crud import evidence as evidence_crud
from database.crud import incidents as incidents_crud
from database.models import EvidenceType, Incident, IncidentStatus

logger = structlog.get_logger(__name__)

router = APIRouter()


def _enum_str(value: object) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _incident_row_to_response(row: Incident) -> IncidentResponse:
    return IncidentResponse(
        id=row.id,
        title=row.title,
        description=row.description,
        severity=_enum_str(row.severity),
        status=_enum_str(row.status),
        source_ip=row.source_ip,
        target_asset=row.target_asset,
        incident_type=row.incident_type,
        raw_evidence_refs=list(row.raw_evidence_refs or []),
        created_at=row.created_at,
        updated_at=row.updated_at,
        completed_at=row.completed_at,
        assigned_agents=list(row.assigned_agents or []),
        tags=list(row.tags or []),
    )


@router.post("/", response_model=IncidentResponse, status_code=status.HTTP_201_CREATED)
async def create_incident(
    data: IncidentCreate,
    db: DbSession,
    _: CurrentUser,
) -> IncidentResponse:
    """Submit a new security incident for investigation."""
    payload = data.model_dump(mode="json")
    row = await incidents_crud.create(db, payload)
    return _incident_row_to_response(row)


@router.get("/", response_model=list[IncidentResponse])
async def list_incidents(
    db: DbSession,
    _: CurrentUser,
    filter_status: IncidentStatus | None = Query(default=None, alias="status"),
    severity: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[IncidentResponse]:
    """List incidents with optional filters."""
    from database.models import IncidentSeverity

    sev = IncidentSeverity(severity) if severity is not None else None
    rows = await incidents_crud.get_all(db, status=filter_status, severity=sev, limit=limit, offset=offset)
    return [_incident_row_to_response(r) for r in rows]


@router.get("/{incident_id}", response_model=IncidentDetail)
async def get_incident(incident_id: uuid.UUID, db: DbSession, _: CurrentUser) -> IncidentDetail:
    """Return incident detail including investigation and evidence."""
    stmt = (
        select(Incident)
        .where(Incident.id == incident_id)
        .options(
            selectinload(Incident.investigation_steps),
            selectinload(Incident.evidence_items),
            selectinload(Incident.lessons),
        )
    )
    row = await db.scalar(stmt)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    from api.schemas import EvidenceResponse, InvestigationStepResponse, LessonSummaryResponse

    steps = [
        InvestigationStepResponse.model_validate(s, from_attributes=True) for s in row.investigation_steps
    ]
    evs = [EvidenceResponse.model_validate(e, from_attributes=True) for e in row.evidence_items]
    lessons = [
        LessonSummaryResponse(
            id=les.id,
            incident_id=les.incident_id,
            title=les.title,
            difficulty=les.difficulty.value,
            estimated_duration_minutes=les.estimated_duration_minutes,
            created_at=les.created_at,
        )
        for les in row.lessons
    ]
    return IncidentDetail(
        incident=_incident_row_to_response(row),
        investigation_steps=steps,
        evidence=evs,
        lessons=lessons,
    )


@router.post("/{incident_id}/investigate", status_code=status.HTTP_202_ACCEPTED)
async def start_investigation(
    incident_id: uuid.UUID,
    db: DbSession,
    coordinator: CoordinatorDep,
    _: CurrentUser,
) -> dict[str, str]:
    """Run the autonomous defense workflow for a persisted incident."""
    row = await incidents_crud.get_by_id(db, incident_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    await incidents_crud.update_status(db, incident_id, IncidentStatus.INVESTIGATING)
    shared = orm_incident_to_shared(row)
    ticket = await coordinator.submit_incident(shared)
    await sync_defense_and_teach_post_submit(db, incident_id, coordinator)
    final_status = (
        IncidentStatus.RESOLVED if ticket.status == "completed" else IncidentStatus.TRIAGING
    )
    await incidents_crud.update_status(db, incident_id, final_status)
    logger.info("investigation_completed", incident_id=str(incident_id), ticket_status=ticket.status)
    return {"incident_id": str(incident_id), "defense_status": ticket.status}


@router.get("/{incident_id}/accuracy-report")
async def get_accuracy_report(incident_id: uuid.UUID, db: DbSession, _: CurrentUser) -> dict:
    """Return stored accuracy metadata."""
    row = await incidents_crud.get_by_id(db, incident_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    if row.accuracy_report is None:
        return {"incident_id": str(incident_id), "accuracy_report": None}
    return {"incident_id": str(incident_id), "accuracy_report": row.accuracy_report}


@router.post("/{incident_id}/evidence", status_code=status.HTTP_201_CREATED)
async def upload_evidence(
    incident_id: uuid.UUID,
    db: DbSession,
    settings: SettingsDep,
    _: CurrentUser,
    file: UploadFile = File(...),
    evidence_type: EvidenceType = EvidenceType.FILE,
    collected_by: str = "api-client",
    storage_location: str = "local",
) -> dict[str, str]:
    """Persist an uploaded evidence file and metadata."""
    row = await incidents_crud.get_by_id(db, incident_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    base = Path(settings.api.evidence_upload_dir).resolve() / str(incident_id)
    base.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename or "artifact.bin").name
    dest = base / safe_name
    data = await file.read()
    digest = hashlib.sha256(data).hexdigest()
    dest.write_bytes(data)
    ev = await evidence_crud.create(
        db,
        incident_id,
        {
            "evidence_type": evidence_type,
            "file_path": str(dest),
            "hash_sha256": digest,
            "file_size_bytes": len(data),
            "metadata_": {"original_filename": file.filename},
            "collected_by": collected_by,
            "custody_chain": [{"actor": collected_by, "action": "upload"}],
            "storage_location": storage_location,
        },
    )
    return {"evidence_id": str(ev.id), "hash_sha256": digest}
