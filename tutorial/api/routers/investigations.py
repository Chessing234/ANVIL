"""Investigation, evidence, and custody HTTP API."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from api.dependencies import CurrentUser, DbSession
from api.schemas import CustodyReportResponse, EvidenceResponse, InvestigationStepResponse
from database.crud import evidence as evidence_crud
from database.crud import investigations as inv_crud
from database.crud import incidents as incidents_crud

router = APIRouter()


@router.get("/{incident_id}/steps", response_model=list[InvestigationStepResponse])
async def get_investigation_steps(incident_id: uuid.UUID, db: DbSession, _: CurrentUser) -> list[InvestigationStepResponse]:
    """Return ordered investigation steps."""
    if await incidents_crud.get_by_id(db, incident_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    steps = await inv_crud.get_steps_for_incident(db, incident_id)
    return [InvestigationStepResponse.model_validate(s, from_attributes=True) for s in steps]


@router.get("/{incident_id}/self-corrections", response_model=list[InvestigationStepResponse])
async def get_self_corrections(incident_id: uuid.UUID, db: DbSession, _: CurrentUser) -> list[InvestigationStepResponse]:
    """Return self-correction steps for FIND EVIL! reporting."""
    if await incidents_crud.get_by_id(db, incident_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    steps = await inv_crud.get_self_corrections(db, incident_id)
    return [InvestigationStepResponse.model_validate(s, from_attributes=True) for s in steps]


@router.get("/{incident_id}/evidence", response_model=list[EvidenceResponse])
async def get_evidence(incident_id: uuid.UUID, db: DbSession, _: CurrentUser) -> list[EvidenceResponse]:
    """Return evidence rows for an incident."""
    if await incidents_crud.get_by_id(db, incident_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    items = await evidence_crud.get_by_incident(db, incident_id)
    return [EvidenceResponse.model_validate(e, from_attributes=True) for e in items]


@router.get("/{incident_id}/chain-of-custody", response_model=CustodyReportResponse)
async def get_chain_of_custody(incident_id: uuid.UUID, db: DbSession, _: CurrentUser) -> CustodyReportResponse:
    """Return custody documentation for each evidence item."""
    if await incidents_crud.get_by_id(db, incident_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    items = await evidence_crud.get_by_incident(db, incident_id)
    chains: dict[str, list] = {}
    for e in items:
        chains[str(e.id)] = await evidence_crud.get_chain_of_custody(db, e.id)
    return CustodyReportResponse(incident_id=str(incident_id), chains=chains)
