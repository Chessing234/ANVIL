"""SQLite persistence for orchestration registries and workflow snapshots."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def _utc_iso() -> str:
    """Return current UTC timestamp in ISO format."""

    return datetime.now(timezone.utc).isoformat()


class OrchestrationStore:
    """Synchronous SQLite store wrapped by the coordinator via ``asyncio.to_thread``."""

    def __init__(self, db_path: Path) -> None:
        self._path = Path(db_path)

    def _connect(self) -> sqlite3.Connection:
        """Open a SQLite connection with sensible defaults."""

        self._path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._path))
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        """Create schema if missing."""

        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS incidents (
                    incident_id TEXT PRIMARY KEY,
                    ticket_json TEXT NOT NULL,
                    latest_state_json TEXT NOT NULL,
                    trace_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS lessons (
                    lesson_id TEXT PRIMARY KEY,
                    incident_id TEXT NOT NULL,
                    ticket_json TEXT NOT NULL,
                    latest_state_json TEXT NOT NULL,
                    trace_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS kg_nodes (
                    node_id TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    weight REAL NOT NULL,
                    metadata_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS kg_edges (
                    src TEXT NOT NULL,
                    dst TEXT NOT NULL,
                    rel_type TEXT NOT NULL,
                    weight REAL NOT NULL,
                    PRIMARY KEY (src, dst, rel_type)
                );
                """,
            )
            conn.commit()
        logger.info("orchestration_store_initialized", path=str(self._path))

    def upsert_incident(
        self,
        incident_id: str,
        ticket: Mapping[str, Any],
        latest_state: Mapping[str, Any],
        trace: list[dict[str, Any]],
        status: str,
    ) -> None:
        """Persist incident registry row."""

        payload = (
            incident_id,
            json.dumps(dict(ticket)),
            json.dumps(dict(latest_state)),
            json.dumps(trace),
            status,
            _utc_iso(),
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO incidents (incident_id, ticket_json, latest_state_json, trace_json, status, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(incident_id) DO UPDATE SET
                    ticket_json=excluded.ticket_json,
                    latest_state_json=excluded.latest_state_json,
                    trace_json=excluded.trace_json,
                    status=excluded.status,
                    updated_at=excluded.updated_at
                """,
                payload,
            )
            conn.commit()

    def fetch_incident(self, incident_id: str) -> dict[str, Any] | None:
        """Load a single incident row."""

        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM incidents WHERE incident_id = ?",
                (incident_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "incident_id": row["incident_id"],
            "ticket": json.loads(row["ticket_json"]),
            "latest_state": json.loads(row["latest_state_json"]),
            "trace": json.loads(row["trace_json"]),
            "status": row["status"],
            "updated_at": row["updated_at"],
        }

    def upsert_lesson(
        self,
        lesson_id: str,
        incident_id: str,
        ticket: Mapping[str, Any],
        latest_state: Mapping[str, Any],
        trace: list[dict[str, Any]],
        status: str,
    ) -> None:
        """Persist lesson registry row."""

        payload = (
            lesson_id,
            incident_id,
            json.dumps(dict(ticket)),
            json.dumps(dict(latest_state)),
            json.dumps(trace),
            status,
            _utc_iso(),
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO lessons (lesson_id, incident_id, ticket_json, latest_state_json, trace_json, status, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(lesson_id) DO UPDATE SET
                    incident_id=excluded.incident_id,
                    ticket_json=excluded.ticket_json,
                    latest_state_json=excluded.latest_state_json,
                    trace_json=excluded.trace_json,
                    status=excluded.status,
                    updated_at=excluded.updated_at
                """,
                payload,
            )
            conn.commit()

    def fetch_lesson(self, lesson_id: str) -> dict[str, Any] | None:
        """Load a single lesson row."""

        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM lessons WHERE lesson_id = ?",
                (lesson_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "lesson_id": row["lesson_id"],
            "incident_id": row["incident_id"],
            "ticket": json.loads(row["ticket_json"]),
            "latest_state": json.loads(row["latest_state_json"]),
            "trace": json.loads(row["trace_json"]),
            "status": row["status"],
            "updated_at": row["updated_at"],
        }

    def fetch_lessons_for_incident(self, incident_id: str) -> list[dict[str, Any]]:
        """Return orchestration lesson rows for an incident, newest first."""

        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM lessons WHERE incident_id = ? ORDER BY updated_at DESC",
                (incident_id,),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            out.append(
                {
                    "lesson_id": row["lesson_id"],
                    "incident_id": row["incident_id"],
                    "ticket": json.loads(row["ticket_json"]),
                    "latest_state": json.loads(row["latest_state_json"]),
                    "trace": json.loads(row["trace_json"]),
                    "status": row["status"],
                    "updated_at": row["updated_at"],
                },
            )
        return out

    def load_knowledge_nodes(self) -> list[dict[str, Any]]:
        """Return all knowledge graph nodes."""

        with self._connect() as conn:
            rows = conn.execute("SELECT node_id, label, weight, metadata_json FROM kg_nodes").fetchall()
        return [
            {
                "node_id": r["node_id"],
                "label": r["label"],
                "weight": r["weight"],
                "metadata": json.loads(r["metadata_json"]),
            }
            for r in rows
        ]

    def load_knowledge_edges(self) -> list[dict[str, Any]]:
        """Return all knowledge graph edges."""

        with self._connect() as conn:
            rows = conn.execute("SELECT src, dst, rel_type, weight FROM kg_edges").fetchall()
        return [
            {"src": r["src"], "dst": r["dst"], "rel_type": r["rel_type"], "weight": r["weight"]}
            for r in rows
        ]

    def replace_knowledge_graph(self, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> None:
        """Atomically replace persisted knowledge graph contents."""

        with self._connect() as conn:
            conn.execute("DELETE FROM kg_edges")
            conn.execute("DELETE FROM kg_nodes")
            conn.executemany(
                "INSERT INTO kg_nodes (node_id, label, weight, metadata_json) VALUES (?, ?, ?, ?)",
                [
                    (
                        n["node_id"],
                        n["label"],
                        float(n["weight"]),
                        json.dumps(n.get("metadata", {})),
                    )
                    for n in nodes
                ],
            )
            conn.executemany(
                "INSERT INTO kg_edges (src, dst, rel_type, weight) VALUES (?, ?, ?, ?)",
                [
                    (e["src"], e["dst"], e["rel_type"], float(e["weight"]))
                    for e in edges
                ],
            )
            conn.commit()
