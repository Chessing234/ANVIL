"""Cosine-similarity retrieval over cached embeddings."""

from __future__ import annotations

import math

import structlog

from knowledge.embedding.embedder import ConceptEmbedder
from knowledge.knowledge_graph import KnowledgeGraph
from knowledge.models import ConceptNode
from shared.models import Lesson

logger = structlog.get_logger(__name__)


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return float(dot / (na * nb))


def _average_vec(vectors: list[list[float]]) -> list[float]:
    if not vectors:
        return []
    dim = len(vectors[0])
    acc = [0.0] * dim
    for v in vectors:
        for i, x in enumerate(v):
            acc[i] += x
    n = len(vectors)
    return [x / n for x in acc]


class SimilaritySearch:
    """Semantic-style search using deterministic embeddings and cosine similarity."""

    def __init__(self, embedder: ConceptEmbedder, graph: KnowledgeGraph) -> None:
        self._embedder = embedder
        self._graph = graph

    async def find_similar_concepts(self, query: str, top_k: int = 5) -> list[tuple[str, float]]:
        qv = await self._embedder.embed(query)
        ranked: list[tuple[str, float]] = []
        for cid, concept in await self._graph.list_concept_nodes():
            vec = await self._embedder.embed_concept(concept)
            ranked.append((cid, _cosine(qv, vec)))
        ranked.sort(key=lambda t: t[1], reverse=True)
        return ranked[:top_k]

    async def find_similar_lessons(self, lessons: list[Lesson], query: str, top_k: int = 5) -> list[tuple[str, float]]:
        qv = await self._embedder.embed(query)
        ranked: list[tuple[str, float]] = []
        for les in lessons:
            lv = await self._embedder.embed_lesson(les)
            ranked.append((str(les.id), _cosine(qv, lv)))
        ranked.sort(key=lambda t: t[1], reverse=True)
        return ranked[:top_k]

    async def find_related_incidents(self, incident_id: str, top_k: int = 5) -> list[tuple[str, float]]:
        """Rank other incidents by overlap of demonstrated concept embeddings."""

        base_concepts: list[str] = []
        for e in await self._graph.export_edges():
            if e.relation_type == "demonstrated_by" and e.target == f"incident:{incident_id}":
                base_concepts.append(e.source)
        if not base_concepts:
            return []
        vecs = [await self._embedder.embed(c) for c in base_concepts]
        centroid = _average_vec(vecs)
        candidates: dict[str, float] = {}
        for e in await self._graph.export_edges():
            if e.relation_type != "demonstrated_by":
                continue
            if not e.target.startswith("incident:"):
                continue
            other = e.target.removeprefix("incident:")
            if other == incident_id:
                continue
            cvec = await self._embedder.embed(e.source)
            candidates[other] = candidates.get(other, 0.0) + _cosine(centroid, cvec)
        ranked = sorted(candidates.items(), key=lambda kv: kv[1], reverse=True)
        logger.debug("related_incidents_ranked", base=incident_id, hits=len(ranked))
        return ranked[:top_k]

    async def detect_concept_overlap(self, new_concept: ConceptNode, top_k: int = 5) -> list[tuple[str, float]]:
        nv = await self._embedder.embed_concept(new_concept)
        ranked: list[tuple[str, float]] = []
        for cid, concept in await self._graph.list_concept_nodes():
            if cid == new_concept.id:
                continue
            vec = await self._embedder.embed_concept(concept)
            ranked.append((cid, _cosine(nv, vec)))
        ranked.sort(key=lambda t: t[1], reverse=True)
        return ranked[:top_k]
