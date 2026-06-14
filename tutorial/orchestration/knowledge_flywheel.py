"""Defense-to-teaching knowledge flywheel with persisted NetworkX graph."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import networkx as nx
import structlog

from orchestration.store import OrchestrationStore
from shared.models import StudentProfile

logger = structlog.get_logger(__name__)

DefenseCompleteHandler = Callable[[str], Awaitable[None]]
LessonCompleteHandler = Callable[[str], Awaitable[None]]


class KnowledgeFlywheel:
    """Maintain concept graph edges and coordinate post-workflow hooks."""

    def __init__(self, store: OrchestrationStore) -> None:
        self._store = store
        self._graph = nx.DiGraph()
        self._lock = asyncio.Lock()
        self._on_defense_complete: DefenseCompleteHandler | None = None
        self._on_lesson_complete: LessonCompleteHandler | None = None
        self._student_struggles: list[dict[str, Any]] = []
        self._defense_insights: list[dict[str, Any]] = []

    def set_defense_complete_handler(self, handler: DefenseCompleteHandler | None) -> None:
        """Register callback invoked after defense workflows finish."""

        self._on_defense_complete = handler

    def set_lesson_complete_handler(self, handler: LessonCompleteHandler | None) -> None:
        """Register callback invoked after teaching workflows finish."""

        self._on_lesson_complete = handler

    def _graph_to_payloads(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Serialize NetworkX graph into store rows."""

        nodes_payload: list[dict[str, Any]] = []
        for node_id, data in self._graph.nodes(data=True):
            nodes_payload.append(
                {
                    "node_id": str(node_id),
                    "label": str(data.get("label", node_id)),
                    "weight": float(data.get("weight", 0.5)),
                    "metadata": dict(data.get("metadata", {})),
                },
            )
        edges_payload: list[dict[str, Any]] = []
        for src, dst, data in self._graph.edges(data=True):
            edges_payload.append(
                {
                    "src": str(src),
                    "dst": str(dst),
                    "rel_type": str(data.get("rel_type", "related_to")),
                    "weight": float(data.get("weight", 0.5)),
                },
            )
        return nodes_payload, edges_payload

    async def persist_graph(self) -> None:
        """Persist the knowledge graph via ``OrchestrationStore``."""

        async with self._lock:
            nodes, edges = self._graph_to_payloads()
            await asyncio.to_thread(self._store.replace_knowledge_graph, nodes, edges)

    def load_graph_sync(self) -> None:
        """Reload graph data synchronously."""

        self._graph.clear()
        nodes = self._store.load_knowledge_nodes()
        edges = self._store.load_knowledge_edges()
        for node in nodes:
            self._graph.add_node(
                node["node_id"],
                label=node["label"],
                weight=float(node["weight"]),
                metadata=dict(node.get("metadata", {})),
            )
        for edge in edges:
            self._graph.add_edge(
                edge["src"],
                edge["dst"],
                rel_type=edge["rel_type"],
                weight=float(edge["weight"]),
            )
        logger.info(
            "knowledge_graph_loaded",
            nodes=self._graph.number_of_nodes(),
            edges=self._graph.number_of_edges(),
        )

    async def load_graph(self) -> None:
        """Async graph reload."""

        async with self._lock:
            await asyncio.to_thread(self.load_graph_sync)

    async def on_lesson_generated(self, lesson_id: str, payload: dict[str, Any]) -> None:
        """Record planned lessons inside the knowledge graph."""

        async with self._lock:
            node_id = f"planned_lesson:{lesson_id}"
            self._graph.add_node(node_id, label=f"Planned {lesson_id}", weight=0.5, metadata=payload)
            nodes, edges = self._graph_to_payloads()
            await asyncio.to_thread(self._store.replace_knowledge_graph, nodes, edges)

    async def on_defense_complete(self, incident_id: str) -> None:
        """Ingest defense outputs and queue teaching."""

        async with self._lock:
            signals = {
                "incident_id": incident_id,
                "learning_signals": ["new_ttps", "novel_dns_pattern"],
            }
            self._graph.add_node(
                f"incident:{incident_id}",
                label=f"Incident {incident_id}",
                weight=0.4,
                metadata=signals,
            )
            for concept in ("dns_exfiltration", "memory_forensics"):
                if not self._graph.has_node(concept):
                    self._graph.add_node(concept, label=concept.replace("_", " ").title(), weight=0.55, metadata={})
                self._graph.add_edge(
                    f"incident:{incident_id}",
                    concept,
                    rel_type="related_to",
                    weight=0.6,
                )
            nodes, edges = self._graph_to_payloads()
            await asyncio.to_thread(self._store.replace_knowledge_graph, nodes, edges)
        if self._on_defense_complete:
            await self._on_defense_complete(incident_id)

    async def on_lesson_complete(self, lesson_id: str) -> None:
        """Fold lesson analytics back into the knowledge graph."""

        async with self._lock:
            summary = {
                "lesson_id": lesson_id,
                "struggles": list(self._student_struggles),
                "completion_rate": 0.78,
            }
            self._defense_insights.append(
                {
                    "lesson_id": lesson_id,
                    "concepts_to_reinforce": ["packet_analysis", "hash_validation"],
                },
            )
            node_id = f"lesson:{lesson_id}"
            self._graph.add_node(node_id, label=f"Lesson {lesson_id}", weight=0.65, metadata=summary)
            for concept in ("packet_analysis", "hash_validation"):
                if not self._graph.has_node(concept):
                    self._graph.add_node(concept, label=concept.replace("_", " ").title(), weight=0.5, metadata={})
                self._graph.add_edge(
                    node_id,
                    concept,
                    rel_type="taught_by",
                    weight=0.7,
                )
            nodes, edges = self._graph_to_payloads()
            await asyncio.to_thread(self._store.replace_knowledge_graph, nodes, edges)
        if self._on_lesson_complete:
            await self._on_lesson_complete(lesson_id)

    async def on_student_interaction(self, lesson_id: str, interaction: dict[str, Any]) -> None:
        """Record real-time sandbox interactions for trending concepts."""

        async with self._lock:
            entry = {"lesson_id": lesson_id, **interaction}
            self._student_struggles.append(entry)
            concept = str(interaction.get("concept", "unknown"))
            if not self._graph.has_node(concept):
                self._graph.add_node(concept, label=concept, weight=0.45, metadata={})
            self._graph.nodes[concept]["weight"] = max(
                0.1,
                float(self._graph.nodes[concept].get("weight", 0.5)) - 0.05,
            )
            nodes, edges = self._graph_to_payloads()
            await asyncio.to_thread(self._store.replace_knowledge_graph, nodes, edges)

    async def get_recommended_next_lesson(self, student_profile: StudentProfile) -> str | None:
        """Recommend the next concept lesson using simple graph weights."""

        async with self._lock:
            if self._graph.number_of_nodes() == 0:
                return None
            candidates = [
                (str(n), float(d.get("weight", 0.5)))
                for n, d in self._graph.nodes(data=True)
                if not str(n).startswith(("lesson:", "incident:"))
            ]
            if not candidates:
                return None
            candidates.sort(key=lambda item: item[1])
            return candidates[0][0]

    async def get_defense_insights(self) -> list[dict[str, Any]]:
        """Return aggregated defense tuning hints."""

        async with self._lock:
            return list(self._defense_insights)

    async def collect_learning_signals(self) -> list[dict[str, Any]]:
        """Summarize learning_signal payloads attached to incident graph nodes."""

        async with self._lock:
            out: list[dict[str, Any]] = []
            for node_id, data in self._graph.nodes(data=True):
                meta = dict(data.get("metadata", {}))
                signals = meta.get("learning_signals")
                if isinstance(signals, list) and signals:
                    out.append({"node_id": str(node_id), "learning_signals": list(signals)})
            return out

    def graph_stats(self) -> dict[str, int]:
        """Return node and edge counts."""

        return {"nodes": self._graph.number_of_nodes(), "edges": self._graph.number_of_edges()}
