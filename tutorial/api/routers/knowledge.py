"""Knowledge graph HTTP API."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from api.dependencies import CurrentUser, DbSession
from api.schemas import KnowledgeEdgeResponse, KnowledgeGraphResponse, KnowledgeNodeResponse, LearningPathResponse
from database.crud import knowledge as knowledge_crud

router = APIRouter()


@router.get("/graph", response_model=KnowledgeGraphResponse)
async def get_knowledge_graph(db: DbSession, _: CurrentUser) -> KnowledgeGraphResponse:
    """Return all nodes and edges."""
    nodes = await knowledge_crud.list_all_nodes(db)
    edges = await knowledge_crud.list_all_edges(db)
    return KnowledgeGraphResponse(
        nodes=[KnowledgeNodeResponse.model_validate(n, from_attributes=True) for n in nodes],
        edges=[KnowledgeEdgeResponse.model_validate(e, from_attributes=True) for e in edges],
    )


@router.get("/concepts/{concept_id}", response_model=KnowledgeNodeResponse)
async def get_concept(concept_id: str, db: DbSession, _: CurrentUser) -> KnowledgeNodeResponse:
    """Return a single concept node."""
    node = await knowledge_crud.get_node(db, concept_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Concept not found")
    return KnowledgeNodeResponse.model_validate(node, from_attributes=True)


@router.get("/learning-path", response_model=LearningPathResponse)
async def get_learning_path(
    target: str,
    db: DbSession,
    _: CurrentUser,
    student_id: uuid.UUID | None = None,
) -> LearningPathResponse:
    """Compute prerequisite ordering toward ``target``."""
    path = await knowledge_crud.get_learning_path(db, target)
    return LearningPathResponse(target=target, path=path, student_id=student_id)


@router.get("/statistics")
async def get_knowledge_statistics(db: DbSession, _: CurrentUser) -> dict[str, int]:
    """Return node/edge counts."""
    stats = await knowledge_crud.get_statistics(db)
    return stats.model_dump()
