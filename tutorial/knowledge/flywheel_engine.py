"""Event-driven knowledge flywheel connecting defense outcomes and teaching quality."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite
import structlog

from agents.teaching.education_models import Interaction
from agents.teaching.tools.adaptive_engine import AdaptiveEngine
from config.constants import LessonDifficulty, MessageBusTopics
from core.message_bus import MessageBus
from knowledge.concept_extractor import ConceptExtractor
from knowledge.embedding.embedder import ConceptEmbedder
from knowledge.embedding.similarity import SimilaritySearch
from knowledge.feedback_loops import FeedbackAggregator, FeedbackCollector
from knowledge.knowledge_graph import KnowledgeGraph
from knowledge.models import ConceptEdge, ConceptNode, DefenseInsight, StudentProgress
from shared.models import InvestigationResult, Lesson, Message, StudentProfile

logger = structlog.get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _baseline_concepts() -> list[ConceptNode]:
    rows = [
        ("injection", "Injection flaws", "OWASP: untrusted data interpreted as code.", "application_security", LessonDifficulty.ADVANCED),
        ("broken_auth", "Broken authentication", "OWASP: weak session and credential handling.", "application_security", LessonDifficulty.INTERMEDIATE),
        ("sensitive_data", "Sensitive data exposure", "OWASP: crypto and privacy failures.", "application_security", LessonDifficulty.INTERMEDIATE),
        ("xxe", "XML external entities", "OWASP: unsafe XML processors.", "application_security", LessonDifficulty.ADVANCED),
        ("broken_access", "Broken access control", "OWASP: IDOR and privilege bugs.", "application_security", LessonDifficulty.INTERMEDIATE),
        ("misconfig", "Security misconfiguration", "OWASP: unsafe defaults and verbose errors.", "application_security", LessonDifficulty.BEGINNER),
        ("xss", "Cross-site scripting", "OWASP: untrusted content in browsers.", "application_security", LessonDifficulty.INTERMEDIATE),
        ("deserial", "Insecure deserialization", "OWASP: unsafe object graphs.", "application_security", LessonDifficulty.EXPERT),
        ("known_vuln", "Using components with known vulnerabilities", "OWASP: supply chain hygiene.", "application_security", LessonDifficulty.INTERMEDIATE),
        ("logging_fail", "Insufficient logging and monitoring", "OWASP: detection gaps.", "forensics", LessonDifficulty.INTERMEDIATE),
        ("t1059", "MITRE T1059 Command and Scripting Interpreter", "Execution via scripts and shells.", "malware_analysis", LessonDifficulty.ADVANCED),
        ("t1071", "MITRE T1071 Application Layer Protocol", "C2 over web/DNS/mail protocols.", "network_security", LessonDifficulty.ADVANCED),
        ("t1486", "MITRE T1486 Data Encrypted for Impact", "Ransomware-style encryption impact.", "malware_analysis", LessonDifficulty.ADVANCED),
        ("dns_tunneling", "DNS tunneling", "Covert channels over DNS.", "network_security", LessonDifficulty.ADVANCED),
        ("packet_analysis", "Packet analysis", "Protocol dissection and IOC extraction.", "network_security", LessonDifficulty.INTERMEDIATE),
    ]
    out: list[ConceptNode] = []
    for cid, name, desc, cat, diff in rows:
        out.append(
            ConceptNode(
                id=cid,
                name=name,
                description=desc,
                category=cat,
                difficulty=diff,
                prerequisites=[],
                related=[],
            ),
        )
    for i in range(len(out) - 1):
        out[i + 1].prerequisites.append(out[i].id)
    return out


_BASELINE_LIST: list[ConceptNode] | None = None


def _get_baseline() -> list[ConceptNode]:
    global _BASELINE_LIST
    if _BASELINE_LIST is None:
        _BASELINE_LIST = _baseline_concepts()
    return _BASELINE_LIST


class FlywheelEngine:
    """Closes the loop between incident response, lessons, and learner telemetry."""

    def __init__(
        self,
        graph: KnowledgeGraph,
        message_bus: MessageBus,
        *,
        config: dict[str, Any] | None = None,
        embedder: ConceptEmbedder | None = None,
        adaptive: AdaptiveEngine | None = None,
    ) -> None:
        self._graph = graph
        self._bus = message_bus
        self._config = dict(config or {})
        fb_path = self._config.get("feedback_db_path")
        self._collector = FeedbackCollector(fb_path)
        self._aggregator = FeedbackAggregator(self._collector)
        emb_path = self._config.get("embedding_db_path")
        self._embedder = embedder or ConceptEmbedder(emb_path)
        self._similarity = SimilaritySearch(self._embedder, graph)
        self._extractor = ConceptExtractor(graph)
        ad_path = self._config.get("adaptive_db_path")
        self._adaptive = adaptive or AdaptiveEngine(ad_path)
        self._action_db = Path(self._config.get("flywheel_action_db", Path.home() / ".cache" / "tutorial" / "flywheel_actions.sqlite"))
        self._action_db.parent.mkdir(parents=True, exist_ok=True)
        self._subscription_ids: list[str] = []
        self._lock = asyncio.Lock()
        self._metrics: dict[str, float] = {
            "concepts_added_week": 0.0,
            "lessons_enhanced_week": 0.0,
            "mastery_improvement_rate": 0.0,
            "incident_to_lesson_hours": 0.0,
            "coverage_ratio": 0.0,
        }

    async def initialize(self) -> None:
        """Load graph, seed baselines, and prepare auxiliary stores."""

        await self._graph.initialize()
        await self._collector.initialize()
        await self._embedder.initialize()
        await self._ensure_action_schema()
        await self._seed_if_empty()

    async def _ensure_action_schema(self) -> None:
        async with aiosqlite.connect(self._action_db) as db:
            await db.executescript(
                """
                CREATE TABLE IF NOT EXISTS flywheel_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action_json TEXT NOT NULL,
                    inverse_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS flywheel_metrics (
                    week_id TEXT PRIMARY KEY,
                    concepts_added REAL NOT NULL,
                    lessons_enhanced REAL NOT NULL,
                    mastery_delta REAL NOT NULL,
                    coverage REAL NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS lesson_enhancements (
                    lesson_id TEXT NOT NULL,
                    insight_id TEXT NOT NULL,
                    patch_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (lesson_id, insight_id)
                );
                """,
            )
            await db.commit()

    async def _log_action(self, action: dict[str, Any], inverse: dict[str, Any]) -> None:
        async with aiosqlite.connect(self._action_db) as db:
            await db.execute(
                "INSERT INTO flywheel_actions (action_json, inverse_json, created_at) VALUES (?, ?, ?)",
                (json.dumps(action), json.dumps(inverse), _iso(_utcnow())),
            )
            await db.commit()

    async def _seed_if_empty(self) -> None:
        stats = await self._graph.get_statistics()
        if stats.node_count > 0:
            return
        baseline = _get_baseline()
        for c in baseline:
            await self._graph.add_concept(c)
            await self._log_action(
                {"type": "seed_concept", "id": c.id},
                {"type": "remove_concept", "id": c.id},
            )
        for i in range(len(baseline) - 1):
            a = baseline[i]
            b = baseline[i + 1]
            await self._graph.add_edge(
                ConceptEdge(source=a.id, target=b.id, relation_type="prerequisite_of", weight=0.4, evidence_count=1),
            )
        self._metrics["concepts_added_week"] += float(len(baseline))
        logger.info("flywheel_seeded", concepts=len(_get_baseline()))

    def register_handlers(self, bus: MessageBus) -> None:
        """Subscribe to ``SYSTEM`` topic for flywheel-specific envelopes (event-driven)."""

        sid = bus.subscribe(MessageBusTopics.SYSTEM, self._on_bus_message)
        self._subscription_ids.append(sid)
        logger.info("flywheel_handlers_registered", subscription_id=sid)

    async def unregister_handlers(self, bus: MessageBus) -> None:
        for sid in list(self._subscription_ids):
            bus.unsubscribe(sid)
        self._subscription_ids.clear()

    async def _on_bus_message(self, message: Message) -> None:
        payload = message.payload
        if not payload.get("flywheel_dispatch"):
            return
        kind = payload.get("kind")
        if kind == "defense_complete":
            inv = None
            if payload.get("investigation_result"):
                inv = InvestigationResult.model_validate(payload["investigation_result"])
            await self.on_defense_complete(str(payload["incident_id"]), inv)
        elif kind == "lesson_complete":
            les = None
            prog = None
            if payload.get("lesson"):
                les = Lesson.model_validate(payload["lesson"])
            if payload.get("student_progress"):
                prog = StudentProgress.model_validate(payload["student_progress"])
            await self.on_lesson_complete(str(payload["lesson_id"]), les, prog)
        elif kind == "student_interaction":
            await self.on_student_interaction(dict(payload))

    async def on_defense_complete(
        self,
        incident_id: str,
        investigation_result: InvestigationResult | None = None,
    ) -> None:
        """Ingest investigation concepts and surface teaching opportunities."""

        async with self._lock:
            concepts: list[ConceptNode] = []
            if investigation_result:
                concepts = await self._extractor.extract_from_investigation(investigation_result.steps)
                await self._collector.collect_defense_feedback(investigation_result)
            else:
                concepts = [
                    ConceptNode(
                        id="incident_triage",
                        name="Incident triage",
                        description="Default concept when investigation payload is absent.",
                        category="forensics",
                        difficulty=LessonDifficulty.BEGINNER,
                        incidents_demonstrating=[incident_id],
                    ),
                ]
            validated = await self._extractor.validate_against_graph(concepts)
            for c in validated:
                existing = await self._graph.get_concept(c.id)
                inc_list = list(existing.incidents_demonstrating) if existing else []
                if incident_id not in inc_list:
                    inc_list.append(incident_id)
                merged = (existing or c).model_copy(
                    update={"incidents_demonstrating": inc_list, "updated_at": _utcnow()},
                )
                await self._graph.add_concept(merged)
                await self._graph.add_edge(
                    ConceptEdge(
                        source=c.id,
                        target=f"incident:{incident_id}",
                        relation_type="demonstrated_by",
                        weight=0.62,
                        evidence_count=1,
                    ),
                )
                await self._log_action(
                    {"type": "upsert_concept", "id": c.id, "incident": incident_id},
                    {"type": "remove_incident_edge", "concept": c.id, "incident": incident_id},
                )
            gaps = await self._graph.detect_gaps()
            for c in validated:
                node = await self._graph.get_concept(c.id)
                lesson_count = len(node.lessons_teaching) if node else 0
                if c.id in gaps or lesson_count == 0:
                    msg = Message(
                        topic=MessageBusTopics.SYSTEM,
                        payload={
                            "event": "teaching_opportunity",
                            "concept_id": c.id,
                            "incident_id": incident_id,
                            "priority": 0.8 if c.id in gaps else 0.55,
                        },
                        source_agent="flywheel",
                    )
                    await self._bus.publish(MessageBusTopics.SYSTEM, msg)
            self._metrics["concepts_added_week"] += float(len(validated))
            await self._persist_metrics()

    async def on_lesson_complete(
        self,
        lesson_id: str,
        lesson: Lesson | None = None,
        student_progress: StudentProgress | None = None,
    ) -> None:
        """Fold lesson analytics back and emit defense insights for struggling concepts."""

        async with self._lock:
            if lesson and student_progress:
                await self._collector.collect_lesson_feedback(lesson, student_progress)
                dist = lesson.student_progress.get("mastery_by_concept", {}) if lesson.student_progress else {}
                for cid, score in dist.items():
                    node = await self._graph.get_concept(str(cid))
                    if node:
                        md = dict(node.mastery_distribution)
                        key = f"student:{student_progress.student_id}"
                        md[key] = float(score)
                        await self._graph.add_concept(node.model_copy(update={"mastery_distribution": md}))
                if student_progress.completion_rate < 0.55 or student_progress.hint_usage_count >= 6:
                    insight = DefenseInsight(
                        id=f"ins-{uuid.uuid4().hex[:10]}",
                        concept_id="lesson_aggregate",
                        insight_type="student_struggle",
                        description=f"Low completion or high hint usage on lesson {lesson_id}.",
                        frequency=1,
                        first_observed=_utcnow(),
                        last_observed=_utcnow(),
                        affected_lessons=[lesson_id],
                        recommended_action="Add worked example and shorten prerequisite chain.",
                    )
                    await self._emit_defense_insight(insight)
            signals = await self._collector.process_feedback_batch()
            for s in signals:
                self._aggregator.record_signal(s)
            self._metrics["lessons_enhanced_week"] += 1.0
            await self._persist_metrics()

    async def _emit_defense_insight(self, insight: DefenseInsight) -> None:
        msg = Message(
            topic=MessageBusTopics.SYSTEM,
            payload={"event": "defense_insight", **insight.model_dump(mode="json")},
            source_agent="flywheel",
        )
        await self._bus.publish(MessageBusTopics.SYSTEM, msg)

    async def on_student_interaction(self, payload: dict[str, Any]) -> None:
        """Update adaptive mastery and emit reinforcement signals on struggle."""

        student_id = str(payload.get("student_id", "anonymous"))
        concept = str(payload.get("concept", "unknown"))
        wrong = int(payload.get("wrong_attempts", 0))
        correct = bool(payload.get("correct", False))
        inter = Interaction(
            student_id=student_id,
            concept=concept,
            correct=correct,
            hint_used=bool(payload.get("hint_used", False)),
            response_time_seconds=float(payload.get("response_time_seconds", 1.0)),
        )
        await self._adaptive.update_model(student_id, inter)
        if wrong >= 3:
            msg = Message(
                topic=MessageBusTopics.SYSTEM,
                payload={
                    "event": "student_struggle",
                    "concept": concept,
                    "wrong_attempts": wrong,
                },
                source_agent="flywheel",
            )
            await self._bus.publish(MessageBusTopics.SYSTEM, msg)
        if correct and float(payload.get("response_time_seconds", 999)) < 20:
            msg = Message(
                topic=MessageBusTopics.SYSTEM,
                payload={"event": "well_taught", "concept": concept},
                source_agent="flywheel",
            )
            await self._bus.publish(MessageBusTopics.SYSTEM, msg)

    async def auto_enhance_lesson(self, lesson_id: str, insight: DefenseInsight) -> None:
        """Record a reversible enhancement patch derived from a ``DefenseInsight``."""

        patch = {"supplementary": insight.recommended_action, "insight": insight.id}
        async with aiosqlite.connect(self._action_db) as db:
            await db.execute(
                """
                INSERT INTO lesson_enhancements (lesson_id, insight_id, patch_json, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(lesson_id, insight_id) DO UPDATE SET patch_json = excluded.patch_json
                """,
                (lesson_id, insight.id, json.dumps(patch), _iso(_utcnow())),
            )
            await db.commit()
        await self._log_action(
            {"type": "lesson_enhance", "lesson_id": lesson_id, "insight": insight.id},
            {"type": "lesson_enhance_undo", "lesson_id": lesson_id, "insight": insight.id},
        )

    async def suggest_new_lesson(self, concept_ids: list[str]) -> dict[str, Any]:
        """Return a ranked suggestion payload when multiple uncovered concepts cluster."""

        overlap = []
        for cid in concept_ids[:5]:
            c = await self._graph.get_concept(cid)
            if c:
                overlap.append(await self._similarity.detect_concept_overlap(c, top_k=3))
        return {"concept_ids": concept_ids, "overlap": overlap, "priority": 0.7}

    async def optimize_learning_path(self, student_id: str, profile: StudentProfile) -> list[str]:
        """Combine graph prerequisites with adaptive readiness."""

        frontier = await self._graph.get_learning_frontier(profile)
        ready = await self._adaptive.get_ready_concepts(student_id)
        merged: list[str] = []
        for c in frontier + ready:
            if c not in merged:
                merged.append(c)
        return merged[:25]

    async def cross_pollinate(self, incident_id: str) -> list[tuple[str, float]]:
        """Suggest cross-referenced incidents based on shared concept embeddings."""

        return await self._similarity.find_related_incidents(incident_id, top_k=5)

    def metrics(self) -> dict[str, float]:
        return dict(self._metrics)

    async def _persist_metrics(self) -> None:
        stats = await self._graph.get_statistics()
        week = _utcnow().strftime("%Y-W%W")
        cov = min(1.0, stats.node_count / 50.0)
        self._metrics["coverage_ratio"] = cov
        async with aiosqlite.connect(self._action_db) as db:
            await db.execute(
                """
                INSERT INTO flywheel_metrics (week_id, concepts_added, lessons_enhanced, mastery_delta, coverage, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(week_id) DO UPDATE SET
                    concepts_added = concepts_added + excluded.concepts_added,
                    lessons_enhanced = lessons_enhanced + excluded.lessons_enhanced,
                    mastery_delta = excluded.mastery_delta,
                    coverage = excluded.coverage,
                    updated_at = excluded.updated_at
                """,
                (
                    week,
                    float(self._metrics["concepts_added_week"]),
                    float(self._metrics["lessons_enhanced_week"]),
                    float(self._metrics["mastery_improvement_rate"]),
                    cov,
                    _iso(_utcnow()),
                ),
            )
            await db.commit()
