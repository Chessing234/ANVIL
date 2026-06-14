"""Knowledge graph CRUD tests."""

from __future__ import annotations

import pytest

from database.connection import DatabaseManager
from database.crud import knowledge
from database.models import KnowledgeCategory, KnowledgeEdgeRelation, LessonDifficulty


@pytest.fixture()
async def db(tmp_path):
    path = tmp_path / "kg.sqlite"
    mgr = DatabaseManager(f"sqlite+aiosqlite:///{path}")
    await mgr.initialize()
    try:
        yield mgr
    finally:
        await mgr.close()


async def test_knowledge_graph_flow(db: DatabaseManager) -> None:
    async with db.session() as s:
        a = await knowledge.create_node(
            s,
            {
                "id": "n_a",
                "name": "A",
                "description": "",
                "category": KnowledgeCategory.NETWORK,
                "difficulty": LessonDifficulty.BEGINNER,
            },
        )
        b = await knowledge.create_node(
            s,
            {
                "id": "n_b",
                "name": "B",
                "description": "",
                "category": KnowledgeCategory.NETWORK,
                "difficulty": LessonDifficulty.INTERMEDIATE,
            },
        )
        await knowledge.create_edge(
            s,
            {
                "source_id": a.id,
                "target_id": b.id,
                "relation_type": KnowledgeEdgeRelation.PREREQUISITE,
            },
        )
        rel = await knowledge.get_related_nodes(s, b.id)
        assert len(rel) == 1
        path_ids = await knowledge.get_learning_path(s, b.id)
        assert path_ids == ["n_a", "n_b"]
        await knowledge.update_mastery(s, b.id, "intermediate", 0.77)
        stats = await knowledge.get_statistics(s)
        assert stats.node_count >= 2
        assert stats.prerequisite_edge_count >= 1


async def test_get_node_missing(db: DatabaseManager) -> None:
    async with db.session() as s:
        assert await knowledge.get_node(s, "missing") is None
