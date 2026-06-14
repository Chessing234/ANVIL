"""Knowledge graph CRUD: nodes, edges, paths, and mastery overlays."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import KnowledgeEdge, KnowledgeEdgeRelation, KnowledgeNode


class KnowledgeStats(BaseModel):
    """High-level graph statistics."""

    model_config = {"extra": "forbid"}

    node_count: int = 0
    edge_count: int = 0
    prerequisite_edge_count: int = 0


async def create_node(session: AsyncSession, node_data: dict[str, Any]) -> KnowledgeNode:
    cols = {c.key for c in KnowledgeNode.__mapper__.column_attrs}
    data = {k: v for k, v in node_data.items() if k in cols}
    node = KnowledgeNode(**data)
    session.add(node)
    await session.flush()
    return node


async def create_edge(session: AsyncSession, edge_data: dict[str, Any]) -> KnowledgeEdge:
    cols = {c.key for c in KnowledgeEdge.__mapper__.column_attrs}
    data = {k: v for k, v in edge_data.items() if k in cols}
    if "id" not in data:
        data["id"] = uuid.uuid4()
    edge = KnowledgeEdge(**data)
    session.add(edge)
    await session.flush()
    return edge


async def get_node(session: AsyncSession, node_id: str) -> KnowledgeNode | None:
    return await session.get(KnowledgeNode, node_id)


async def get_related_nodes(session: AsyncSession, node_id: str) -> list[KnowledgeEdge]:
    """Return all edges where ``node_id`` is source or target."""
    stmt = (
        select(KnowledgeEdge)
        .where((KnowledgeEdge.source_id == node_id) | (KnowledgeEdge.target_id == node_id))
        .order_by(KnowledgeEdge.created_at.asc())
    )
    rows = await session.execute(stmt)
    return list(rows.scalars().all())


async def get_learning_path(session: AsyncSession, target_node_id: str) -> list[str]:
    """
    Return an ordered list of node ids from foundations to ``target_node_id``,
    following ``PREREQUISITE`` edges (source is prerequisite of target).
    """
    visited: set[str] = set()
    order: list[str] = []
    visiting: set[str] = set()

    async def visit(nid: str) -> None:
        if nid in visited:
            return
        if nid in visiting:
            return
        visiting.add(nid)
        stmt = select(KnowledgeEdge).where(
            KnowledgeEdge.target_id == nid,
            KnowledgeEdge.relation_type == KnowledgeEdgeRelation.PREREQUISITE,
        )
        rows = await session.execute(stmt)
        preds = [e.source_id for e in rows.scalars().all()]
        for p in preds:
            await visit(p)
        visiting.remove(nid)
        visited.add(nid)
        order.append(nid)

    await visit(target_node_id)
    return order


async def update_mastery(session: AsyncSession, node_id: str, student_level: str, score: float) -> KnowledgeNode:
    node = await session.get(KnowledgeNode, node_id)
    if node is None:
        raise KeyError(f"Knowledge node not found: {node_id}")
    dist = dict(node.mastery_distribution or {})
    dist[str(student_level)] = float(score)
    node.mastery_distribution = dist
    await session.flush()
    return node


async def list_all_nodes(session: AsyncSession) -> list[KnowledgeNode]:
    stmt = select(KnowledgeNode).order_by(KnowledgeNode.id.asc())
    rows = await session.execute(stmt)
    return list(rows.scalars().all())


async def list_all_edges(session: AsyncSession) -> list[KnowledgeEdge]:
    stmt = select(KnowledgeEdge).order_by(KnowledgeEdge.created_at.asc())
    rows = await session.execute(stmt)
    return list(rows.scalars().all())


async def get_statistics(session: AsyncSession) -> KnowledgeStats:
    n_nodes = int(await session.scalar(select(func.count()).select_from(KnowledgeNode)) or 0)
    n_edges = int(await session.scalar(select(func.count()).select_from(KnowledgeEdge)) or 0)
    n_pre = int(
        await session.scalar(
            select(func.count())
            .select_from(KnowledgeEdge)
            .where(KnowledgeEdge.relation_type == KnowledgeEdgeRelation.PREREQUISITE)
        )
        or 0
    )
    return KnowledgeStats(
        node_count=n_nodes,
        edge_count=n_edges,
        prerequisite_edge_count=n_pre,
    )
