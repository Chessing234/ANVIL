"""Async SQLAlchemy engine, session factory, and lifecycle helpers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from database.models import Base

logger = structlog.get_logger(__name__)


class DatabaseManager:
    """Manages pooled async connections, schema creation, and transactional sessions."""

    def __init__(
        self,
        database_url: str = "sqlite+aiosqlite:///./tutorial.db",
        *,
        pool_size: int = 20,
        echo: bool = False,
    ) -> None:
        self._database_url = database_url
        if database_url.startswith("sqlite"):
            self.engine: AsyncEngine = create_async_engine(
                database_url,
                echo=echo,
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )

            @event.listens_for(self.engine.sync_engine, "connect")
            def _sqlite_pragma(dbapi_connection, _connection_record) -> None:  # noqa: ANN001
                cur = dbapi_connection.cursor()
                cur.execute("PRAGMA foreign_keys=ON")
                cur.close()

        else:
            self.engine = create_async_engine(
                database_url,
                echo=echo,
                pool_size=pool_size,
                max_overflow=max(5, pool_size // 4),
                pool_pre_ping=True,
            )
        self.session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=True,
            autocommit=False,
        )

    async def initialize(self) -> None:
        """Create all ORM tables if they do not exist."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("database_initialized", url=self._database_url.split("@")[-1])

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Provide a transactional ``AsyncSession`` (commit on success, rollback on error)."""
        session = self.session_factory()
        try:
            async with session.begin():
                yield session
        finally:
            await session.close()

    async def health_check(self) -> bool:
        """Return ``True`` when a trivial query succeeds (pool connectivity)."""
        try:
            async with self.session() as s:
                result = await s.execute(text("SELECT 1"))
                return result.scalar() == 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("database_health_failed", err=str(exc))
            return False

    async def close(self) -> None:
        """Dispose the engine and release pool connections."""
        await self.engine.dispose()
        logger.info("database_engine_disposed")
