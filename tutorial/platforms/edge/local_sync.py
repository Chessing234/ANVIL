"""Delta sync engine for intermittent connectivity (knowledge, lessons, progress)."""

from __future__ import annotations

import json
import time
from typing import Any

import aiosqlite
import httpx
import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


class SyncResult(BaseModel):
    """Outcome of a single sync channel."""

    model_config = {"extra": "forbid"}

    entity: str = Field(min_length=1)
    pushed: int = Field(ge=0)
    pulled: int = Field(ge=0)
    conflicts: int = Field(ge=0)


class SyncStatus(BaseModel):
    """Queue depth and connectivity snapshot."""

    model_config = {"extra": "forbid"}

    pending_knowledge: int = Field(ge=0)
    pending_lessons: int = Field(ge=0)
    pending_progress: int = Field(ge=0)
    last_sync_ts: float | None = None
    online: bool = False


class LocalSync:
    """Local-first sync with delta queues and explicit conflict merge rules."""

    def __init__(self, db_path: str | None = None, *, central_url: str | None = None) -> None:
        self._db_path = db_path or "edge_local_sync.sqlite3"
        self._central = central_url or ""

    async def _init_db(self) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS kg_delta (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    payload TEXT NOT NULL,
                    created REAL NOT NULL,
                    synced INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS lessons (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated REAL NOT NULL,
                    synced INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS progress (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated REAL NOT NULL,
                    synced INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS meta (
                    k TEXT PRIMARY KEY,
                    v TEXT NOT NULL
                )
                """
            )
            await db.commit()

    async def _pending_count(self, table: str) -> int:
        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute(f"SELECT COUNT(*) FROM {table} WHERE synced=0")
            return int((await cur.fetchone())[0])

    async def sync_knowledge_graph(self) -> SyncResult:
        """Push queued knowledge-graph deltas; pull remote updates when online."""
        await self._init_db()
        pushed = 0
        pulled = 0
        conflicts = 0
        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute("SELECT id, payload FROM kg_delta WHERE synced=0 ORDER BY id ASC")
            rows = await cur.fetchall()
        if self._central and rows:
            async with httpx.AsyncClient(timeout=10.0) as client:
                for row_id, payload in rows:
                    url = self._central.rstrip("/") + "/sync/kg"
                    resp = await client.post(url, json=json.loads(payload))
                    if resp.status_code >= 400:
                        continue
                    remote = resp.json()
                    if not isinstance(remote, dict):
                        remote = {}
                    merged, c = self._merge_kg(json.loads(payload), remote)
                    conflicts += c
                    async with aiosqlite.connect(self._db_path) as db:
                        await db.execute("UPDATE kg_delta SET synced=1 WHERE id=?", (row_id,))
                        await db.execute(
                            "INSERT INTO meta(k, v) VALUES(?, ?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                            ("kg_last_remote", json.dumps(merged, sort_keys=True)),
                        )
                        await db.commit()
                    pushed += 1
                    pulled += int(bool(remote))
        else:
            async with aiosqlite.connect(self._db_path) as db:
                for row_id, _payload in rows:
                    await db.execute("UPDATE kg_delta SET synced=1 WHERE id=?", (row_id,))
                    await db.commit()
                    pushed += 1
        await self._touch_last_sync()
        logger.info("kg_sync", pushed=pushed, pulled=pulled, conflicts=conflicts)
        return SyncResult(entity="knowledge_graph", pushed=pushed, pulled=pulled, conflicts=conflicts)

    async def sync_lessons(self) -> SyncResult:
        """Sync lesson catalog entries (server wins on overlapping lesson ids)."""
        await self._init_db()
        pushed = 0
        pulled = 0
        conflicts = 0
        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute("SELECT id, payload FROM lessons WHERE synced=0 ORDER BY id ASC")
            rows = await cur.fetchall()
        if self._central and rows:
            async with httpx.AsyncClient(timeout=10.0) as client:
                for lesson_id, payload in rows:
                    url = self._central.rstrip("/") + "/sync/lessons"
                    resp = await client.post(url, json={"id": lesson_id, "payload": json.loads(payload)})
                    remote_payload = resp.json() if resp.status_code < 400 else {}
                    if not isinstance(remote_payload, dict):
                        remote_payload = {}
                    local_obj = {"id": lesson_id, "payload": json.loads(payload)}
                    remote_obj = {"id": lesson_id, "payload": remote_payload}
                    merged = await self.resolve_conflicts(local_obj, remote_obj)
                    conflicts += int(remote_payload != {} and remote_payload != json.loads(payload))
                    async with aiosqlite.connect(self._db_path) as db:
                        await db.execute(
                            "UPDATE lessons SET payload=?, updated=?, synced=1 WHERE id=?",
                            (json.dumps(merged["payload"], sort_keys=True), time.time(), lesson_id),
                        )
                        await db.commit()
                    pushed += 1
                    pulled += int(bool(remote_payload))
        else:
            async with aiosqlite.connect(self._db_path) as db:
                for lesson_id, _ in rows:
                    await db.execute("UPDATE lessons SET synced=1 WHERE id=?", (lesson_id,))
                    await db.commit()
                    pushed += 1
        await self._touch_last_sync()
        return SyncResult(entity="lessons", pushed=pushed, pulled=pulled, conflicts=conflicts)

    async def sync_student_progress(self) -> SyncResult:
        """Upload progress deltas (local wins on overlapping progress keys)."""
        await self._init_db()
        pushed = 0
        pulled = 0
        conflicts = 0
        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute("SELECT id, payload FROM progress WHERE synced=0 ORDER BY id ASC")
            rows = await cur.fetchall()
        if self._central and rows:
            async with httpx.AsyncClient(timeout=10.0) as client:
                for student_id, payload in rows:
                    url = self._central.rstrip("/") + "/sync/progress"
                    resp = await client.post(url, json={"id": student_id, "payload": json.loads(payload)})
                    remote_payload = resp.json() if resp.status_code < 400 else {}
                    if not isinstance(remote_payload, dict):
                        remote_payload = {}
                    local_obj = {"id": student_id, "payload": json.loads(payload)}
                    remote_obj = {"id": student_id, "payload": remote_payload}
                    merged = await self.resolve_conflicts(local_obj, remote_obj)
                    conflicts += int(bool(remote_payload))
                    async with aiosqlite.connect(self._db_path) as db:
                        await db.execute(
                            "UPDATE progress SET payload=?, updated=?, synced=1 WHERE id=?",
                            (json.dumps(merged["payload"], sort_keys=True), time.time(), student_id),
                        )
                        await db.commit()
                    pushed += 1
                    pulled += int(bool(remote_payload))
        else:
            async with aiosqlite.connect(self._db_path) as db:
                for student_id, _ in rows:
                    await db.execute("UPDATE progress SET synced=1 WHERE id=?", (student_id,))
                    await db.commit()
                    pushed += 1
        await self._touch_last_sync()
        return SyncResult(entity="student_progress", pushed=pushed, pulled=pulled, conflicts=conflicts)

    def _merge_kg(self, local: dict[str, Any], remote: dict[str, Any]) -> tuple[dict[str, Any], int]:
        merged = dict(remote)
        merged.update({k: v for k, v in local.items() if not str(k).startswith("content_")})
        conflicts = 0
        for key in set(local) & set(remote):
            if str(key).startswith("content_") and local[key] != remote[key]:
                merged[key] = remote[key]
                conflicts += 1
        return merged, conflicts

    async def resolve_conflicts(self, local: dict[str, Any], remote: dict[str, Any]) -> dict[str, Any]:
        """Merge payloads: server wins for ``content_*`` keys, local wins for ``progress_*`` keys."""
        out: dict[str, Any] = {"payload": {}}
        local_payload = dict(local.get("payload", {}))
        remote_payload = dict(remote.get("payload", {}))
        keys = set(local_payload) | set(remote_payload)
        merged: dict[str, Any] = {}
        for key in sorted(keys):
            lk = local_payload.get(key)
            rk = remote_payload.get(key)
            if key.startswith("content_"):
                merged[key] = rk if rk is not None else lk
            elif key.startswith("progress_"):
                merged[key] = lk if lk is not None else rk
            else:
                merged[key] = rk if rk is not None else lk
        out["payload"] = merged
        return out

    async def get_sync_status(self) -> SyncStatus:
        """Return pending queue sizes and last successful sync timestamp."""
        await self._init_db()
        kg = await self._pending_count("kg_delta")
        lessons = await self._pending_count("lessons")
        progress = await self._pending_count("progress")
        last_sync: float | None = None
        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute("SELECT v FROM meta WHERE k='last_sync_ts'")
            row = await cur.fetchone()
            if row:
                last_sync = float(row[0])
        online = False
        if self._central:
            try:
                async with httpx.AsyncClient(timeout=3.0) as client:
                    resp = await client.get(self._central.rstrip("/") + "/health")
                    online = resp.status_code < 500
            except httpx.HTTPError:
                online = False
        return SyncStatus(
            pending_knowledge=kg,
            pending_lessons=lessons,
            pending_progress=progress,
            last_sync_ts=last_sync,
            online=online,
        )

    async def _touch_last_sync(self) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO meta(k, v) VALUES('last_sync_ts', ?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                (str(time.time()),),
            )
            await db.commit()

    async def enqueue_knowledge_delta(self, payload: dict[str, Any]) -> None:
        """Queue a knowledge-graph delta for later sync."""
        await self._init_db()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO kg_delta(payload, created, synced) VALUES(?, ?, 0)",
                (json.dumps(payload, sort_keys=True), time.time()),
            )
            await db.commit()

    async def upsert_lesson(self, lesson_id: str, payload: dict[str, Any]) -> None:
        """Insert or update a lesson row and mark it dirty for sync."""
        await self._init_db()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO lessons(id, payload, updated, synced)
                VALUES(?, ?, ?, 0)
                ON CONFLICT(id) DO UPDATE SET payload=excluded.payload, updated=excluded.updated, synced=0
                """,
                (lesson_id, json.dumps(payload, sort_keys=True), time.time()),
            )
            await db.commit()

    async def upsert_progress(self, student_id: str, payload: dict[str, Any]) -> None:
        """Insert or update student progress and mark it dirty for sync."""
        await self._init_db()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO progress(id, payload, updated, synced)
                VALUES(?, ?, ?, 0)
                ON CONFLICT(id) DO UPDATE SET payload=excluded.payload, updated=excluded.updated, synced=0
                """,
                (student_id, json.dumps(payload, sort_keys=True), time.time()),
            )
            await db.commit()
