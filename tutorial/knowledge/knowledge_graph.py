"""Async knowledge graph with NetworkX analytics and SQLite persistence."""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite
import networkx as nx
import structlog

from config.constants import LessonDifficulty
from knowledge.models import ConceptEdge, ConceptNode, GraphStats
from shared.models import Incident, Lesson, StudentProfile

logger = structlog.get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


class KnowledgeGraph:
    """Concept relationship graph persisted in SQLite and analyzed with NetworkX."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._g = nx.MultiDiGraph()
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Create schema and load graph from disk."""

        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(
                """
                CREATE TABLE IF NOT EXISTS kg_concepts (
                    id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS kg_edges (
                    source TEXT NOT NULL,
                    target TEXT NOT NULL,
                    relation_type TEXT NOT NULL,
                    weight REAL NOT NULL,
                    evidence_count INTEGER NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (source, target, relation_type)
                );
                """,
            )
            await db.commit()
        await self._load_from_db()

    async def _load_from_db(self) -> None:
        async with self._lock:
            self._g.clear()
            async with aiosqlite.connect(self._db_path) as db:
                db.row_factory = aiosqlite.Row
                cur = await db.execute("SELECT id, payload_json FROM kg_concepts")
                for r in await cur.fetchall():
                    node = ConceptNode.model_validate(json.loads(r["payload_json"]))
                    self._g.add_node(node.id, concept=node.model_dump(mode="json"))
                cur2 = await db.execute(
                    "SELECT source, target, relation_type, weight, evidence_count FROM kg_edges",
                )
                for e in await cur2.fetchall():
                    rel = e["relation_type"]
                    for n in (e["source"], e["target"]):
                        if not self._g.has_node(n):
                            self._g.add_node(n, concept=None)
                    self._g.add_edge(
                        e["source"],
                        e["target"],
                        key=rel,
                        relation_type=rel,
                        weight=float(e["weight"]),
                        evidence_count=int(e["evidence_count"]),
                    )
        logger.info("knowledge_graph_loaded", nodes=self._g.number_of_nodes(), edges=self._g.number_of_edges())

    def _concept_dict(self, node_id: str) -> dict[str, Any]:
        data = self._g.nodes[node_id].get("concept")
        if not data:
            raise KeyError(node_id)
        return dict(data)

    async def add_concept(self, concept: ConceptNode) -> str:
        """Insert or replace a concept node."""

        async with self._lock:
            now = _utcnow()
            c = concept.model_copy(update={"updated_at": now})
            payload = c.model_dump(mode="json")
            self._g.add_node(c.id, concept=payload)
            async with aiosqlite.connect(self._db_path) as db:
                cur = await db.execute("SELECT created_at FROM kg_concepts WHERE id = ?", (c.id,))
                row = await cur.fetchone()
                created = _iso(c.created_at) if row is None else row[0]
                await db.execute(
                    """
                    INSERT INTO kg_concepts (id, payload_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        payload_json = excluded.payload_json,
                        updated_at = excluded.updated_at
                    """,
                    (c.id, json.dumps(payload), created, _iso(c.updated_at)),
                )
                await db.commit()
        return c.id

    async def add_edge(self, edge: ConceptEdge) -> None:
        """Add or strengthen an edge (multiple relation types per node pair allowed)."""

        async with self._lock:
            w = float(edge.weight)
            ev = int(edge.evidence_count)
            if self._g.has_edge(edge.source, edge.target, key=edge.relation_type):
                cur = self._g.edges[edge.source, edge.target, edge.relation_type]
                ev = int(cur.get("evidence_count", 1)) + edge.evidence_count
                w = min(1.0, float(cur.get("weight", 0.5)) + 0.05)
            self._g.add_edge(
                edge.source,
                edge.target,
                key=edge.relation_type,
                relation_type=edge.relation_type,
                weight=w,
                evidence_count=max(1, ev),
            )
            async with aiosqlite.connect(self._db_path) as db:
                await db.execute(
                    """
                    INSERT INTO kg_edges (source, target, relation_type, weight, evidence_count, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source, target, relation_type) DO UPDATE SET
                        weight = excluded.weight,
                        evidence_count = excluded.evidence_count,
                        updated_at = excluded.updated_at
                    """,
                    (
                        edge.source,
                        edge.target,
                        edge.relation_type,
                        w,
                        max(1, ev),
                        _iso(_utcnow()),
                    ),
                )
                await db.commit()

    async def get_concept(self, concept_id: str) -> ConceptNode | None:
        async with self._lock:
            if not self._g.has_node(concept_id):
                return None
            return ConceptNode.model_validate(self._concept_dict(concept_id))

    async def get_related(self, concept_id: str, relation_type: str | None = None) -> list[ConceptEdge]:
        async with self._lock:
            out: list[ConceptEdge] = []
            for u, v, k, data in self._g.out_edges(concept_id, keys=True, data=True):
                rt = str(data.get("relation_type", k))
                if relation_type and rt != relation_type:
                    continue
                out.append(
                    ConceptEdge(
                        source=u,
                        target=v,
                        relation_type=rt,
                        weight=float(data.get("weight", 0.5)),
                        evidence_count=int(data.get("evidence_count", 1)),
                    ),
                )
            for u, v, k, data in self._g.in_edges(concept_id, keys=True, data=True):
                rt = str(data.get("relation_type", k))
                if relation_type and rt != relation_type:
                    continue
                out.append(
                    ConceptEdge(
                        source=u,
                        target=v,
                        relation_type=rt,
                        weight=float(data.get("weight", 0.5)),
                        evidence_count=int(data.get("evidence_count", 1)),
                    ),
                )
            return out

    async def find_path(self, from_concept: str, to_concept: str) -> list[str]:
        """Shortest path along directed multiedges (ignores parallel multiplicity)."""

        async with self._lock:
            if from_concept not in self._g or to_concept not in self._g:
                return []
            simple = nx.DiGraph()
            for u, v, data in self._g.edges(data=True):
                if simple.has_edge(u, v):
                    continue
                simple.add_edge(u, v, weight=float(data.get("weight", 1.0)))
            try:
                return nx.shortest_path(simple, from_concept, to_concept)
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                return []

    async def get_prerequisite_chain(self, concept_id: str) -> list[str]:
        """All prerequisite concepts (recursive) for ``concept_id``."""

        async with self._lock:
            H = nx.DiGraph()
            for u, v, k, data in self._g.edges(keys=True, data=True):
                if data.get("relation_type") == "prerequisite_of":
                    H.add_edge(u, v)
            if concept_id not in H:
                return []
            return sorted(nx.ancestors(H, concept_id))

    async def get_learning_frontier(self, student_profile: StudentProfile) -> list[str]:
        """Concepts whose prerequisites appear mastered in ``skill_scores``."""

        async with self._lock:
            mastered = {k for k, score in student_profile.skill_scores.items() if score >= 60}
            frontier: list[str] = []
            for node_id, data in self._g.nodes(data=True):
                if not isinstance(node_id, str) or node_id.startswith(("incident:", "lesson:")):
                    continue
                concept = data.get("concept") or {}
                prereqs = list(concept.get("prerequisites") or [])
                if not prereqs:
                    if node_id not in mastered:
                        frontier.append(node_id)
                    continue
                if all(p in mastered for p in prereqs) and node_id not in mastered:
                    frontier.append(node_id)
            return list(dict.fromkeys(frontier))[:50]

    async def detect_gaps(self) -> list[str]:
        """Concepts missing lessons or real-world incident links."""

        async with self._lock:
            gaps: list[str] = []
            for nid, data in self._g.nodes(data=True):
                if str(nid).startswith(("incident:", "lesson:")):
                    continue
                concept = data.get("concept") or {}
                if not concept:
                    continue
                if not concept.get("lessons_teaching") or not concept.get("incidents_demonstrating"):
                    gaps.append(str(nid))
            return gaps

    async def get_statistics(self) -> GraphStats:
        async with self._lock:
            n = self._g.number_of_nodes()
            m = self._g.number_of_edges()
            simple = nx.DiGraph()
            for u, v in self._g.edges():
                simple.add_edge(u, v)
            dens = float(nx.density(simple)) if n > 1 else 0.0
            cat: dict[str, int] = defaultdict(int)
            for _, data in self._g.nodes(data=True):
                c = data.get("concept") or {}
                if not c:
                    cat["_structural"] += 1
                else:
                    cat[str(c.get("category", "unknown"))] += 1
            pr: dict[str, float] = {}
            if n > 0:
                U = simple.to_undirected()
                try:
                    pr = nx.pagerank(U, max_iter=200, tol=1e-4)
                except nx.PowerIterationFailedConvergence:
                    deg = dict(U.degree())
                    tot = sum(deg.values()) or 1
                    pr = {node: float(d) / tot for node, d in deg.items()}
            top = sorted(pr.items(), key=lambda kv: kv[1], reverse=True)[:8]
            comm_count = 0
            bridges: list[str] = []
            if n > 2:
                U2 = simple.to_undirected()
                comms = nx.community.greedy_modularity_communities(U2)
                comm_count = len(list(comms))
                bc = nx.betweenness_centrality(U2, k=min(15, n))
                bridges = [nid for nid, score in sorted(bc.items(), key=lambda kv: kv[1], reverse=True)[:5]]
            return GraphStats(
                node_count=n,
                edge_count=m,
                density=dens,
                category_coverage=dict(cat),
                pagerank_top=top,
                community_count=comm_count,
                bridge_concepts=bridges,
            )

    async def import_from_incidents(self, incidents: list[Incident]) -> int:
        """Upsert lightweight concepts from incident text."""

        added = 0
        for inc in incidents:
            blob = f"{inc.title} {inc.description}".lower()
            tags: list[str] = []
            for key, cid in (
                ("dns", "dns_tunneling"),
                ("ransom", "ransomware_defense"),
                ("phish", "phishing"),
                ("malware", "malware_analysis"),
                ("lateral", "lateral_movement"),
                ("credential", "credential_abuse"),
            ):
                if key in blob:
                    tags.append(cid)
            if not tags:
                tags = ["incident_triage"]
            iid = str(inc.id)
            for cid in tags:
                existing = await self.get_concept(cid)
                if existing:
                    ids = list(dict.fromkeys([*existing.incidents_demonstrating, iid]))
                    await self.add_concept(existing.model_copy(update={"incidents_demonstrating": ids}))
                else:
                    await self.add_concept(
                        ConceptNode(
                            id=cid,
                            name=cid.replace("_", " ").title(),
                            description=f"Observed in incident context: {inc.title[:200]}",
                            category="network_security" if "dns" in cid else "forensics",
                            difficulty=LessonDifficulty.INTERMEDIATE,
                            incidents_demonstrating=[iid],
                        ),
                    )
                    added += 1
                await self.add_edge(
                    ConceptEdge(
                        source=cid,
                        target=f"incident:{iid}",
                        relation_type="demonstrated_by",
                        weight=0.55,
                        evidence_count=1,
                    ),
                )
        return added

    async def import_from_lessons(self, lessons: list[Lesson]) -> int:
        """Link lessons to CSTA-derived concept stubs."""

        count = 0
        for les in lessons:
            lid = str(les.id)
            for std in les.csta_standards or ["generic_security"]:
                cid = f"std_{std}".replace("-", "_").lower()[:120]
                existing = await self.get_concept(cid)
                narr = les.narrative[:4000]
                if existing:
                    lt = list(dict.fromkeys([*existing.lessons_teaching, lid]))
                    await self.add_concept(
                        existing.model_copy(update={"lessons_teaching": lt, "description": narr[:2000]}),
                    )
                else:
                    await self.add_concept(
                        ConceptNode(
                            id=cid,
                            name=f"Standard {std}",
                            description=narr[:2000],
                            category="curriculum",
                            difficulty=les.difficulty,
                            lessons_teaching=[lid],
                        ),
                    )
                    count += 1
                await self.add_edge(
                    ConceptEdge(
                        source=cid,
                        target=f"lesson:{lid}",
                        relation_type="taught_by",
                        weight=0.65,
                        evidence_count=1,
                    ),
                )
        return count

    async def merge_concepts(self, keep_id: str, merge_id: str) -> None:
        """Merge ``merge_id`` into ``keep_id`` (deduplication)."""

        async with self._lock:
            if not self._g.has_node(keep_id) or not self._g.has_node(merge_id):
                return
            try:
                keep = ConceptNode.model_validate(self._concept_dict(keep_id))
                merge = ConceptNode.model_validate(self._concept_dict(merge_id))
            except KeyError:
                return
            merged = keep.model_copy(
                update={
                    "related": list(dict.fromkeys([*keep.related, merge_id, *merge.related])),
                    "incidents_demonstrating": list(
                        dict.fromkeys([*keep.incidents_demonstrating, *merge.incidents_demonstrating]),
                    ),
                    "lessons_teaching": list(dict.fromkeys([*keep.lessons_teaching, *merge.lessons_teaching])),
                    "updated_at": _utcnow(),
                },
            )
            seen: dict[tuple[str, str, str], tuple[str, str, str, float, int, str]] = {}
            for u, v, k, data in self._g.edges(keys=True, data=True):
                if u == merge_id:
                    u = keep_id
                if v == merge_id:
                    v = keep_id
                if u == v:
                    continue
                rel = str(k)
                key = (u, v, rel)
                w = float(data.get("weight", 0.5))
                ev = int(data.get("evidence_count", 1))
                if key in seen:
                    pu, pv, pr, pw, pev, pts = seen[key]
                    seen[key] = (pu, pv, pr, min(1.0, pw + 0.02), pev + ev, pts)
                else:
                    seen[key] = (u, v, rel, w, ev, _iso(_utcnow()))
            edge_rows = list(seen.values())
            self._g.remove_node(merge_id)
            self._g.remove_node(keep_id)
            self._g.add_node(keep_id, concept=merged.model_dump(mode="json"))
            for u, v, rel, w, ev, ts in edge_rows:
                self._g.add_edge(u, v, key=rel, relation_type=rel, weight=w, evidence_count=ev)
            async with aiosqlite.connect(self._db_path) as db:
                await db.execute("DELETE FROM kg_edges WHERE source = ? OR target = ?", (merge_id, merge_id))
                await db.execute("DELETE FROM kg_concepts WHERE id IN (?, ?)", (merge_id, keep_id))
                await db.commit()
            payload = merged.model_dump(mode="json")
            async with aiosqlite.connect(self._db_path) as db:
                await db.execute(
                    """
                    INSERT INTO kg_concepts (id, payload_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (keep_id, json.dumps(payload), _iso(merged.created_at), _iso(merged.updated_at)),
                )
                await db.executemany(
                    """
                    INSERT INTO kg_edges (source, target, relation_type, weight, evidence_count, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source, target, relation_type) DO UPDATE SET
                        weight = excluded.weight,
                        evidence_count = excluded.evidence_count,
                        updated_at = excluded.updated_at
                    """,
                    edge_rows,
                )
                await db.commit()

    async def pagerank_scores(self) -> dict[str, float]:
        async with self._lock:
            if self._g.number_of_nodes() == 0:
                return {}
            simple = nx.DiGraph()
            for u, v in self._g.edges():
                simple.add_edge(u, v)
            try:
                return nx.pagerank(simple.to_undirected(), max_iter=200, tol=1e-4)
            except nx.PowerIterationFailedConvergence:
                U = simple.to_undirected()
                deg = dict(U.degree())
                tot = sum(deg.values()) or 1
                return {node: float(d) / tot for node, d in deg.items()}

    async def export_edges(self) -> list[ConceptEdge]:
        """Return all edges as structured models (for analytics and similarity)."""

        async with self._lock:
            out: list[ConceptEdge] = []
            for u, v, k, data in self._g.edges(keys=True, data=True):
                out.append(
                    ConceptEdge(
                        source=str(u),
                        target=str(v),
                        relation_type=str(data.get("relation_type", k)),
                        weight=float(data.get("weight", 0.5)),
                        evidence_count=int(data.get("evidence_count", 1)),
                    ),
                )
            return out

    async def list_concept_nodes(self) -> list[tuple[str, ConceptNode]]:
        """Return ``(node_id, concept)`` pairs for concept-like nodes only."""

        async with self._lock:
            pairs: list[tuple[str, ConceptNode]] = []
            for nid, data in self._g.nodes(data=True):
                if str(nid).startswith(("incident:", "lesson:")):
                    continue
                cdata = data.get("concept")
                if not cdata:
                    continue
                pairs.append((str(nid), ConceptNode.model_validate(cdata)))
            return pairs
