"""Immutable SQLite-backed chain of custody for forensic evidence."""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime
from pathlib import Path

import structlog

from shared.models import CustodyAction, CustodyEntry

logger = structlog.get_logger(__name__)


class CustodyChain:
    """Append-only custody log with integrity verification and reporting."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path).expanduser().resolve()
        self._lock = asyncio.Lock()

    def _connect(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path))
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS custody_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                action TEXT NOT NULL,
                performed_by TEXT NOT NULL,
                evidence_id TEXT NOT NULL,
                hash_before TEXT,
                hash_after TEXT,
                location TEXT NOT NULL,
                notes TEXT NOT NULL DEFAULT ''
            )
            """,
        )
        conn.commit()
        return conn

    def _append_sync(self, entry: CustodyEntry) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO custody_entries
                (timestamp, action, performed_by, evidence_id, hash_before, hash_after, location, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.timestamp.isoformat(),
                    entry.action.value,
                    entry.performed_by,
                    entry.evidence_id,
                    entry.hash_before,
                    entry.hash_after,
                    entry.location,
                    entry.notes,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    async def append(self, entry: CustodyEntry) -> int:
        """Append a custody record and return its row id."""

        async with self._lock:
            return await asyncio.to_thread(self._append_sync, entry)

    def _list_for_evidence_sync(self, evidence_id: str) -> list[CustodyEntry]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT * FROM custody_entries WHERE evidence_id = ? ORDER BY id ASC",
                (evidence_id,),
            )
            rows = cur.fetchall()
        out: list[CustodyEntry] = []
        for r in rows:
            ts = datetime.fromisoformat(str(r["timestamp"]))
            out.append(
                CustodyEntry(
                    timestamp=ts,
                    action=CustodyAction(str(r["action"])),
                    performed_by=str(r["performed_by"]),
                    evidence_id=str(r["evidence_id"]),
                    hash_before=r["hash_before"],
                    hash_after=r["hash_after"],
                    location=str(r["location"]),
                    notes=str(r["notes"] or ""),
                ),
            )
        return out

    async def entries_for(self, evidence_id: str) -> list[CustodyEntry]:
        """Return all custody entries for an evidence id in chronological order."""

        async with self._lock:
            return await asyncio.to_thread(self._list_for_evidence_sync, evidence_id)

    async def verify_chain(self, evidence_id: str) -> bool:
        """Verify custody continuity and hash consistency for ``evidence_id``."""

        entries = await self.entries_for(evidence_id)
        if not entries:
            return False
        last_after: str | None = None
        for e in entries:
            if e.hash_before and last_after is not None and e.hash_before != last_after:
                logger.warning("custody_hash_gap", evidence_id=evidence_id, action=e.action.value)
                return False
            if e.hash_after:
                last_after = e.hash_after
        return True

    async def transfer_custody(self, evidence_id: str, from_agent: str, to_agent: str) -> CustodyEntry:
        """Record a formal transfer between agents."""

        entry = CustodyEntry(
            action=CustodyAction.TRANSFERRED,
            performed_by=from_agent,
            evidence_id=evidence_id,
            hash_before=None,
            hash_after=None,
            location="n/a",
            notes=f"Custody transferred from {from_agent} to {to_agent}",
        )
        await self.append(entry)
        return entry

    async def generate_report(self, evidence_id: str) -> str:
        """Return a human-readable chain-of-custody report."""

        entries = await self.entries_for(evidence_id)
        lines = [f"Chain of custody for evidence_id={evidence_id}", "=" * 60]
        for e in entries:
            lines.append(
                f"[{e.timestamp.isoformat()}] {e.action.value} by {e.performed_by} @ {e.location}\n"
                f"  hash_before={e.hash_before!s} hash_after={e.hash_after!s}\n"
                f"  notes: {e.notes}",
            )
        return "\n".join(lines)
