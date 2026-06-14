"""Tests for ``KnowledgeGraph``."""

from __future__ import annotations

from uuid import uuid4

import pytest

from config.constants import LessonDifficulty
from knowledge.embedding.embedder import ConceptEmbedder
from knowledge.embedding.similarity import SimilaritySearch
from knowledge.knowledge_graph import KnowledgeGraph
from knowledge.models import ConceptEdge, ConceptNode
from shared.models import Incident, IncidentSeverity, Lesson, StudentProfile


@pytest.mark.asyncio
async def test_graph_crud_path_and_stats(tmp_path) -> None:
    db = tmp_path / "kg.sqlite"
    g = KnowledgeGraph(db)
    await g.initialize()
    await g.add_concept(
        ConceptNode(
            id="a",
            name="A",
            description="alpha",
            category="forensics",
            difficulty=LessonDifficulty.BEGINNER,
            prerequisites=[],
        ),
    )
    await g.add_concept(
        ConceptNode(
            id="b",
            name="B",
            description="beta",
            category="forensics",
            difficulty=LessonDifficulty.INTERMEDIATE,
            prerequisites=["a"],
        ),
    )
    await g.add_edge(ConceptEdge(source="a", target="b", relation_type="prerequisite_of", weight=0.5, evidence_count=1))
    assert await g.find_path("a", "b") == ["a", "b"]
    assert "a" in await g.get_prerequisite_chain("b")
    stats = await g.get_statistics()
    assert stats.node_count >= 2
    assert stats.edge_count >= 1


@pytest.mark.asyncio
async def test_similarity_ranking(tmp_path) -> None:
    db = tmp_path / "kg_sim.sqlite"
    g = KnowledgeGraph(db)
    await g.initialize()
    emb = ConceptEmbedder(tmp_path / "e.sqlite")
    await emb.initialize()
    await g.add_concept(
        ConceptNode(
            id="dns_tunneling",
            name="DNS Tunneling",
            description="Covert channels over DNS queries.",
            category="network_security",
            difficulty=LessonDifficulty.ADVANCED,
        ),
    )
    await g.add_concept(
        ConceptNode(
            id="packet_analysis",
            name="Packet Analysis",
            description="Dissecting PCAPs for IOCs.",
            category="network_security",
            difficulty=LessonDifficulty.INTERMEDIATE,
        ),
    )
    sim = SimilaritySearch(emb, g)
    hits = await sim.find_similar_concepts("DNS covert channel in subdomain lengths", top_k=2)
    top_ids = [h[0] for h in hits]
    assert "dns_tunneling" in top_ids


@pytest.mark.asyncio
async def test_import_merge_and_gap(tmp_path) -> None:
    db = tmp_path / "kg2.sqlite"
    g = KnowledgeGraph(db)
    await g.initialize()
    iid = uuid4()
    inc = Incident(
        id=iid,
        title="DNS tunnel alert",
        description="long dns queries to rare domain",
        severity=IncidentSeverity.HIGH,
    )
    n = await g.import_from_incidents([inc])
    assert n >= 1
    await g.add_concept(
        ConceptNode(
            id="dns_tunneling_dup",
            name="Dup",
            description="dup",
            category="network_security",
            difficulty=LessonDifficulty.INTERMEDIATE,
            incidents_demonstrating=[str(iid)],
        ),
    )
    await g.merge_concepts("dns_tunneling", "dns_tunneling_dup")
    assert await g.get_concept("dns_tunneling_dup") is None
    gaps = await g.detect_gaps()
    assert isinstance(gaps, list)


@pytest.mark.asyncio
async def test_lesson_import(tmp_path) -> None:
    db = tmp_path / "kg3.sqlite"
    g = KnowledgeGraph(db)
    await g.initialize()
    les = Lesson(
        incident_id=uuid4(),
        title="Lesson",
        narrative="encryption and tls discussion",
        difficulty=LessonDifficulty.INTERMEDIATE,
        csta_standards=["CY-6-8-1"],
    )
    c = await g.import_from_lessons([les])
    assert c >= 1


@pytest.mark.asyncio
async def test_learning_frontier(tmp_path) -> None:
    db = tmp_path / "kg4.sqlite"
    g = KnowledgeGraph(db)
    await g.initialize()
    await g.add_concept(
        ConceptNode(
            id="p1",
            name="P1",
            description="d",
            category="c",
            difficulty=LessonDifficulty.BEGINNER,
            prerequisites=[],
        ),
    )
    await g.add_concept(
        ConceptNode(
            id="p2",
            name="P2",
            description="d",
            category="c",
            difficulty=LessonDifficulty.INTERMEDIATE,
            prerequisites=["p1"],
        ),
    )
    prof = StudentProfile(name="t", skill_scores={"p1": 80})
    front = await g.get_learning_frontier(prof)
    assert "p2" in front
