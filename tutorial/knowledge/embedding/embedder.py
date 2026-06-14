"""Text and concept embeddings with SQLite-backed cache."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
from pathlib import Path

import aiosqlite

from knowledge.models import ConceptNode
from shared.models import Lesson

_DEFAULT_DIM = 64


def _hash_embedding(text: str, dim: int = _DEFAULT_DIM) -> list[float]:
    """Deterministic pseudo-embedding from SHA-256 chunks (no external API)."""

    h = hashlib.sha256(text.encode("utf-8")).digest()
    repeats = (dim + len(h) - 1) // len(h)
    buf = (h * repeats)[:dim]
    vec = [((b / 255.0) * 2.0 - 1.0) for b in buf]
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


class ConceptEmbedder:
    """Embeds text and caches vectors in SQLite."""

    def __init__(self, db_path: str | Path | None = None, *, dim: int = _DEFAULT_DIM) -> None:
        root = Path(db_path or Path.home() / ".cache" / "tutorial" / "embeddings.sqlite")
        root.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = str(root)
        self._dim = dim
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(
                """
                CREATE TABLE IF NOT EXISTS embedding_cache (
                    content_hash TEXT PRIMARY KEY,
                    dim INTEGER NOT NULL,
                    vector_json TEXT NOT NULL,
                    source_preview TEXT NOT NULL
                );
                """,
            )
            await db.commit()

    def _hash_content(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    async def embed(self, text: str) -> list[float]:
        """Return a normalized embedding vector for ``text`` (cached)."""

        ch = self._hash_content(text)
        async with self._lock:
            async with aiosqlite.connect(self._db_path) as db:
                cur = await db.execute(
                    "SELECT vector_json FROM embedding_cache WHERE content_hash = ? AND dim = ?",
                    (ch, self._dim),
                )
                row = await cur.fetchone()
                if row:
                    return json.loads(row[0])
                vec = _hash_embedding(text, self._dim)
                await db.execute(
                    """
                    INSERT INTO embedding_cache (content_hash, dim, vector_json, source_preview)
                    VALUES (?, ?, ?, ?)
                    """,
                    (ch, self._dim, json.dumps(vec), text[:500]),
                )
                await db.commit()
        return vec

    async def embed_concept(self, concept: ConceptNode) -> list[float]:
        return await self.embed(f"{concept.name}\n{concept.description}")

    async def embed_lesson(self, lesson: Lesson) -> list[float]:
        body = f"{lesson.title}\n{lesson.narrative}"
        return await self.embed(body[:12_000])

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for t in texts:
            out.append(await self.embed(t))
        return out
