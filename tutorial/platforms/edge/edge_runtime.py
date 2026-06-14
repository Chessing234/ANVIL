"""On-device inference runtime with SQLite persistence and optional central sync."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import aiosqlite
import httpx
import numpy as np
import structlog
from pydantic import BaseModel, Field

from platforms.edge.deployment.device_profiles import DEVICE_PROFILES

logger = structlog.get_logger(__name__)


class DeviceProfile(BaseModel):
    """Concrete device profile used by ``EdgeRuntime``."""

    model_config = {"extra": "forbid"}

    key: str = Field(min_length=1)
    ram_mb: int = Field(ge=128)
    cpu_cores: int = Field(ge=1)
    gpu: str | None = None
    model_variant: str = Field(min_length=1)
    max_concurrent_agents: int = Field(ge=1)
    inference_batch_size: int = Field(ge=1)
    model_path: str | None = None

    @classmethod
    def from_key(cls, profile_key: str, *, model_path: str | None = None) -> DeviceProfile:
        if profile_key not in DEVICE_PROFILES:
            raise KeyError(f"Unknown device profile: {profile_key}")
        payload = dict(DEVICE_PROFILES[profile_key])
        return cls(key=profile_key, model_path=model_path, **payload)


class DeviceStatus(BaseModel):
    """Edge node health snapshot."""

    model_config = {"extra": "forbid"}

    online: bool
    pending_sync: int
    last_sync_ts: float | None
    model_loaded: bool
    mean_latency_ms: float | None = None
    latency_budget_ms: float = 2000.0


class EdgeRuntime:
    """Local-first runtime: SQLite + optional ONNX inference + queued central sync."""

    def __init__(
        self,
        db_path: str | None = None,
        *,
        central_url: str | None = None,
        onnx_model_path: str | None = None,
    ) -> None:
        self._db_path = db_path or os.environ.get("EDGE_RUNTIME_DB", "edge_runtime.sqlite3")
        self._central = central_url or os.environ.get("EDGE_CENTRAL_URL", "")
        self._onnx = onnx_model_path or os.environ.get("EDGE_ONNX_MODEL", "")
        self._profile: DeviceProfile | None = None
        self._last_latency_ms: float | None = None

    async def initialize(self, device_profile: DeviceProfile) -> None:
        """Create schema, validate RAM budget, and record the active profile."""
        self._profile = device_profile
        if device_profile.model_path:
            size = Path(device_profile.model_path).stat().st_size
            budget = int(device_profile.ram_mb * 1024 * 1024 * 0.35)
            if size > budget:
                raise ValueError(
                    f"Model file ({size} bytes) exceeds ~35% RAM budget ({budget} bytes) for device"
                )
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS meta (
                    k TEXT PRIMARY KEY,
                    v TEXT NOT NULL
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS incidents (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created REAL NOT NULL
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS sync_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    op TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created REAL NOT NULL
                )
                """
            )
            await db.commit()
        await self._set_meta("profile", device_profile.model_dump_json())
        logger.info("edge_runtime_initialized", profile=device_profile.key)

    async def _set_meta(self, key: str, value: str) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO meta(k, v) VALUES(?, ?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                (key, value),
            )
            await db.commit()

    async def _enqueue(self, op: str, payload: dict[str, Any]) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO sync_queue(op, payload, created) VALUES(?, ?, ?)",
                (op, json.dumps(payload, sort_keys=True), time.time()),
            )
            await db.commit()

    async def run_agent(self, agent_type: str, input_data: dict[str, Any]) -> dict[str, Any]:
        """Execute a lightweight agent transform; uses ONNX Runtime when a model path is configured."""
        model_path = self._onnx or (self._profile.model_path if self._profile else "")
        if model_path and Path(model_path).exists() and Path(model_path).suffix.lower() == ".onnx":
            try:
                import onnxruntime as ort  # type: ignore import-not-found
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError("Install onnxruntime for ONNX inference") from exc
            so = ort.SessionOptions()
            so.intra_op_num_threads = max(1, (os.cpu_count() or 2) // 2)
            session = ort.InferenceSession(model_path, sess_options=so, providers=["CPUExecutionProvider"])
            input_meta = session.get_inputs()[0]
            name = input_meta.name
            dim = 1
            for d in input_meta.shape[1:]:
                if isinstance(d, int) and d > 0:
                    dim = d
                    break
            vec = np.random.randn(1, dim).astype(np.float32)
            t0 = time.perf_counter()
            out = session.run(None, {name: vec})
            latency_ms = (time.perf_counter() - t0) * 1000.0
            self._last_latency_ms = latency_ms
            await self._set_meta("last_latency_ms", f"{latency_ms:.4f}")
            if latency_ms > 2000.0:
                logger.warning("edge_latency_budget_exceeded", ms=latency_ms)
            return {
                "agent_type": agent_type,
                "backend": "onnxruntime",
                "latency_ms": latency_ms,
                "output_shape": [int(x) for x in out[0].shape],
                "input_echo": input_data,
            }

        # Deterministic local fallback (no cloud).
        summary = {
            "agent_type": agent_type,
            "backend": "local_rules",
            "severity": input_data.get("severity", "INFO"),
            "actions": ["collect_logs", "isolate_host"] if agent_type.endswith("response") else ["triage"],
            "latency_ms": 0.2,
            "input_echo": input_data,
        }
        self._last_latency_ms = float(summary["latency_ms"])
        return summary

    async def process_incident_local(self, incident_data: dict[str, Any]) -> dict[str, Any]:
        """Persist and triage an incident fully offline, then queue deltas for central sync."""
        incident_id = str(incident_data.get("id") or f"inc-{time.time_ns()}")
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO incidents(id, payload, status, created)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET payload=excluded.payload, status=excluded.status
                """,
                (
                    incident_id,
                    json.dumps(incident_data, sort_keys=True),
                    "open",
                    time.time(),
                ),
            )
            await db.commit()
        await self._enqueue("incident", {"id": incident_id, "payload": incident_data})
        analysis = await self.run_agent("incident_response", incident_data)
        return {"incident_id": incident_id, "analysis": analysis}

    async def sync_with_central(self) -> None:
        """Flush the local sync queue when ``EDGE_CENTRAL_URL`` is reachable."""
        if not self._central:
            logger.info("edge_sync_skipped", reason="no central url")
            await self._set_meta("last_sync_status", "skipped_no_url")
            return
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT id, op, payload FROM sync_queue ORDER BY id ASC LIMIT 50")
            rows = await cur.fetchall()
        if not rows:
            await self._set_meta("last_sync_status", "empty_queue")
            await self._set_meta("last_sync_ts", str(time.time()))
            return
        async with httpx.AsyncClient(timeout=10.0) as client:
            for row in rows:
                url = self._central.rstrip("/") + "/edge/ingest"
                try:
                    resp = await client.post(
                        url,
                        json={"op": row["op"], "payload": json.loads(row["payload"])},
                    )
                    resp.raise_for_status()
                except httpx.HTTPError as exc:
                    logger.warning("edge_ingest_failed", err=str(exc))
                    await self._set_meta("last_sync_status", "error")
                    return
                async with aiosqlite.connect(self._db_path) as db:
                    await db.execute("DELETE FROM sync_queue WHERE id=?", (row["id"],))
                    await db.commit()
        await self._set_meta("last_sync_ts", str(time.time()))
        await self._set_meta("last_sync_status", "ok")
        logger.info("edge_sync_completed", items=len(rows))

    async def get_local_status(self) -> DeviceStatus:
        """Return connectivity, queue depth, and latency telemetry."""
        pending = 0
        last_sync: float | None = None
        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute("SELECT COUNT(*) FROM sync_queue")
            pending = int((await cur.fetchone())[0])
            cur = await db.execute("SELECT v FROM meta WHERE k='last_sync_ts'")
            row = await cur.fetchone()
            if row and row[0]:
                last_sync = float(row[0])
        online = False
        if self._central:
            try:
                async with httpx.AsyncClient(timeout=3.0) as client:
                    resp = await client.get(self._central.rstrip("/") + "/health")
                    online = resp.status_code < 500
            except httpx.HTTPError:
                online = False
        mean_latency = self._last_latency_ms
        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute("SELECT v FROM meta WHERE k='last_latency_ms'")
            row = await cur.fetchone()
            if row and row[0]:
                mean_latency = float(row[0])
        model_loaded = bool(self._onnx or (self._profile and self._profile.model_path))
        return DeviceStatus(
            online=online,
            pending_sync=pending,
            last_sync_ts=last_sync,
            model_loaded=model_loaded,
            mean_latency_ms=mean_latency,
        )
