"""Bayesian Knowledge Tracing for adaptive difficulty with SQLite persistence."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite
import structlog

from agents.teaching.education_models import Interaction, SkillModel
from config.constants import LessonDifficulty

logger = structlog.get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


class AdaptiveEngine:
    """Tracks learner skills with BKT and persists state across sessions."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        root = Path(db_path or Path.home() / ".cache" / "tutorial" / "adaptive_engine.sqlite")
        root.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = str(root)
        self._init_lock = asyncio.Lock()

    async def _ensure_schema(self) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS skill_state (
                    student_id TEXT NOT NULL,
                    concept TEXT NOT NULL,
                    p_known REAL NOT NULL,
                    p_learn REAL NOT NULL,
                    p_guess REAL NOT NULL,
                    p_slip REAL NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (student_id, concept)
                )
                """,
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS interactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id TEXT NOT NULL,
                    concept TEXT NOT NULL,
                    correct INTEGER NOT NULL,
                    hint_used INTEGER NOT NULL,
                    response_time_seconds REAL NOT NULL,
                    timestamp TEXT NOT NULL
                )
                """,
            )
            await db.commit()

    async def _get_row(self, student_id: str, concept: str) -> SkillModel:
        await self._ensure_schema()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM skill_state WHERE student_id = ? AND concept = ?",
                (student_id, concept),
            )
            row = await cur.fetchone()
        if row is None:
            return SkillModel(student_id=student_id, concept=concept)
        return SkillModel(
            student_id=row["student_id"],
            concept=row["concept"],
            p_known=float(row["p_known"]),
            p_learn=float(row["p_learn"]),
            p_guess=float(row["p_guess"]),
            p_slip=float(row["p_slip"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    async def _save_row(self, model: SkillModel) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO skill_state (student_id, concept, p_known, p_learn, p_guess, p_slip, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(student_id, concept) DO UPDATE SET
                    p_known = excluded.p_known,
                    p_learn = excluded.p_learn,
                    p_guess = excluded.p_guess,
                    p_slip = excluded.p_slip,
                    updated_at = excluded.updated_at
                """,
                (
                    model.student_id,
                    model.concept,
                    model.p_known,
                    model.p_learn,
                    model.p_guess,
                    model.p_slip,
                    model.updated_at.isoformat(),
                ),
            )
            await db.commit()

    def _bkt_update(self, model: SkillModel, interaction: Interaction) -> SkillModel:
        """Apply one BKT observation (Corbett & Anderson style)."""

        p_k = model.p_known
        p_g = model.p_guess
        p_s = model.p_slip
        p_l = model.p_learn

        if interaction.correct:
            p_correct = p_k * (1.0 - p_s) + (1.0 - p_k) * p_g
            if p_correct <= 1e-9:
                p_k_new = p_k
            else:
                p_k_new = (p_k * (1.0 - p_s)) / p_correct
            p_k_new = _clamp01(p_k_new + (1.0 - p_k_new) * p_l)
        else:
            p_incorrect = p_k * p_s + (1.0 - p_k) * (1.0 - p_g)
            if p_incorrect <= 1e-9:
                p_k_new = p_k
            else:
                p_k_new = (p_k * p_s) / p_incorrect
            p_k_new = _clamp01(p_k_new)

        hint_penalty = 0.02 if interaction.hint_used else 0.0
        speed_penalty = 0.01 if interaction.response_time_seconds > 120.0 else 0.0
        p_k_new = _clamp01(p_k_new - hint_penalty - speed_penalty)

        return model.model_copy(update={"p_known": p_k_new, "updated_at": _utcnow()})

    async def update_model(self, student_id: str, interaction: Interaction) -> SkillModel:
        """Persist interaction and return updated ``SkillModel``."""

        async with self._init_lock:
            await self._ensure_schema()
        model = await self._get_row(student_id, interaction.concept)
        updated = self._bkt_update(model, interaction)
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO interactions (student_id, concept, correct, hint_used, response_time_seconds, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    interaction.student_id,
                    interaction.concept,
                    1 if interaction.correct else 0,
                    1 if interaction.hint_used else 0,
                    interaction.response_time_seconds,
                    interaction.timestamp.isoformat(),
                ),
            )
            await db.commit()
        await self._save_row(updated)
        logger.info("bkt_updated", student=student_id, concept=interaction.concept, p_known=updated.p_known)
        return updated

    async def recommend_difficulty(self, student_id: str, concept: str) -> LessonDifficulty:
        """Recommend difficulty from posterior mastery."""

        m = await self._get_row(student_id, concept)
        if m.p_known < 0.35:
            return LessonDifficulty.BEGINNER
        if m.p_known < 0.55:
            return LessonDifficulty.INTERMEDIATE
        if m.p_known < 0.75:
            return LessonDifficulty.ADVANCED
        return LessonDifficulty.EXPERT

    async def predict_mastery(self, student_id: str, concept: str) -> float:
        """Return ``P(known)`` (mastery probability)."""

        m = await self._get_row(student_id, concept)
        return float(m.p_known)

    async def get_weak_areas(self, student_id: str) -> list[str]:
        """Concepts with low ``p_known``."""

        await self._ensure_schema()
        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute(
                "SELECT concept FROM skill_state WHERE student_id = ? AND p_known < 0.35 ORDER BY p_known ASC",
                (student_id,),
            )
            rows = await cur.fetchall()
        return [r[0] for r in rows]

    async def get_ready_concepts(self, student_id: str) -> list[str]:
        """Concepts likely ready for new material (not too low, not mastered)."""

        await self._ensure_schema()
        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute(
                """
                SELECT concept FROM skill_state
                WHERE student_id = ? AND p_known >= 0.45 AND p_known < 0.85
                ORDER BY p_known DESC
                """,
                (student_id,),
            )
            rows = await cur.fetchall()
        return [r[0] for r in rows]

    async def export_snapshot(self, student_id: str) -> dict[str, Any]:
        """Serialize learner state for backup or analytics."""

        await self._ensure_schema()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM skill_state WHERE student_id = ?", (student_id,))
            skills = [dict(r) for r in await cur.fetchall()]
            cur2 = await db.execute("SELECT * FROM interactions WHERE student_id = ?", (student_id,))
            inter = [dict(r) for r in await cur2.fetchall()]
        return {"student_id": student_id, "skills": skills, "interactions": inter}

    async def import_snapshot(self, payload: dict[str, Any]) -> None:
        """Restore learner state (replaces rows for that student)."""

        student_id = str(payload["student_id"])
        await self._ensure_schema()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("DELETE FROM skill_state WHERE student_id = ?", (student_id,))
            await db.execute("DELETE FROM interactions WHERE student_id = ?", (student_id,))
            for row in payload.get("skills", []):
                await db.execute(
                    """
                    INSERT INTO skill_state (student_id, concept, p_known, p_learn, p_guess, p_slip, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        student_id,
                        row["concept"],
                        row["p_known"],
                        row["p_learn"],
                        row["p_guess"],
                        row["p_slip"],
                        row["updated_at"],
                    ),
                )
            for row in payload.get("interactions", []):
                await db.execute(
                    """
                    INSERT INTO interactions (student_id, concept, correct, hint_used, response_time_seconds, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        student_id,
                        row["concept"],
                        row["correct"],
                        row["hint_used"],
                        row["response_time_seconds"],
                        row["timestamp"],
                    ),
                )
            await db.commit()
