"""Process-wide bootstrap: databases, message bus, coordinator, API server, and shutdown."""

from __future__ import annotations

import asyncio
import contextlib
import signal
import time

import structlog
import uvicorn

from api.converters import database_url_to_async
from api.main import create_app
from config.settings import Settings, get_settings
from core.message_bus import MessageBus, get_message_bus
from database.connection import DatabaseManager
from database.seed_data import seed_database
from database.seed_rich_demo import seed_rich_demo
from orchestration.coordinator import TutorialCoordinator

logger = structlog.get_logger(__name__)


class Bootstrap:
    """CLI-oriented lifecycle manager with graceful failure handling."""

    def __init__(self) -> None:
        self._settings: Settings | None = None
        self._bus: MessageBus | None = None
        self._coordinator: TutorialCoordinator | None = None
        self._api_server: uvicorn.Server | None = None
        self._api_task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._started_core = False
        self._shutdown_once = False

    def _settings_or_raise(self) -> Settings:
        if self._settings is None:
            self._settings = get_settings()
        return self._settings

    async def init_database(self) -> None:
        """Create ORM tables (SQLite/Postgres) via SQLAlchemy metadata."""

        settings = self._settings_or_raise()
        url = database_url_to_async(settings.database.url)
        mgr = DatabaseManager(url, pool_size=settings.database.pool_size, echo=settings.database.echo)
        try:
            await mgr.initialize()
        except Exception:
            logger.exception("bootstrap_init_database_failed")
            await mgr.close()
            raise
        await mgr.close()

    async def seed_data(self) -> None:
        """Populate reference concepts, templates, and demo rows."""

        settings = self._settings_or_raise()
        url = database_url_to_async(settings.database.url)
        mgr = DatabaseManager(url, pool_size=settings.database.pool_size, echo=settings.database.echo)
        await mgr.initialize()
        try:
            async with mgr.session() as session:
                await seed_database(session)
                await seed_rich_demo(session)
        finally:
            await mgr.close()

    async def start_message_bus(self) -> None:
        """Start the async pub/sub bus (idempotent when reused from FastAPI lifespan)."""

        settings = self._settings_or_raise()
        self._bus = await get_message_bus(
            max_queue_size=settings.message_bus.max_queue_size,
            message_ttl_seconds=settings.message_bus.message_ttl_seconds,
        )
        await self._bus.start()

    async def start_integrations(self) -> None:
        """Reserved hook for warming external SIEM/RPA sessions (no-op in offline dev)."""

        logger.info("bootstrap_integrations_skipped_offline")

    async def start_knowledge_flywheel(self) -> None:
        """Graph persistence is owned by ``KnowledgeFlywheel`` inside the coordinator."""

        if self._coordinator is None:
            logger.warning("bootstrap_flywheel_no_coordinator")
            return
        await self._coordinator.reload_knowledge_graph()
        logger.info("bootstrap_knowledge_flywheel_ready")

    async def start_agents(self) -> None:
        """Initialize coordinator, agent pool, and workflow registries (without HTTP)."""

        settings = self._settings_or_raise()
        if self._bus is None:
            await self.start_message_bus()
        assert self._bus is not None
        self._coordinator = TutorialCoordinator(settings=settings, message_bus=self._bus)
        try:
            await self._coordinator.initialize()
        except Exception:
            logger.exception("bootstrap_start_agents_failed")
            with contextlib.suppress(Exception):
                await self._coordinator.shutdown()
            self._coordinator = None
            raise
        self._started_core = True
        await self.start_integrations()
        await self.start_knowledge_flywheel()

    async def start_api(self, host: str, port: int) -> None:
        """Run the FastAPI ASGI stack (lifespan manages database, bus, and coordinator)."""

        config = uvicorn.Config(
            create_app(),
            host=host,
            port=port,
            loop="asyncio",
            log_level="info",
        )
        self._api_server = uvicorn.Server(config)
        assert self._api_server is not None
        await self._api_server.serve()

    async def run_forever(self) -> None:
        """Block until SIGINT/SIGTERM when running agent-only stacks."""

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(NotImplementedError):
                loop.add_signal_handler(sig, self._stop.set)
        await self._stop.wait()

    async def _wait_active_investigations(self, timeout_seconds: float = 60.0) -> None:
        if self._coordinator is None:
            return
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            pending = [
                s
                for s in self._coordinator._incidents.values()
                if s.ticket.status not in {"completed", "failed"}
            ]
            if not pending:
                return
            await asyncio.sleep(0.25)
        logger.warning("bootstrap_shutdown_investigation_timeout", timeout_seconds=timeout_seconds)

    async def shutdown(self) -> None:
        """Reverse startup: stop API, agents, integrations, bus, and DB handles."""

        if self._shutdown_once:
            return
        self._shutdown_once = True

        if self._api_server is not None:
            self._api_server.should_exit = True
        if self._api_task is not None:
            self._api_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._api_task
            self._api_task = None

        await self._wait_active_investigations()
        if self._coordinator is not None:
            with contextlib.suppress(Exception):
                await self._coordinator.shutdown()
            self._coordinator = None

        if self._bus is not None and self._started_core:
            with contextlib.suppress(Exception):
                await self._bus.stop()
            self._bus = None

        self._started_core = False
        logger.info("bootstrap_shutdown_complete")

    async def run_full_stack_background_api(self, host: str, port: int) -> None:
        """Start uvicorn in a task and wait on ``run_forever`` (used for ``--mode full``)."""

        self._api_task = asyncio.create_task(self.start_api(host, port), name="uvicorn-serve")
        await asyncio.sleep(0.5)
        if self._api_task.done():
            exc = self._api_task.exception()
            raise RuntimeError("API server failed to start") from exc
        await self.run_forever()
