"""FastAPI application factory and ASGI entrypoint."""

from __future__ import annotations

import asyncio
import contextlib
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.converters import database_url_to_async
from api.middleware import RateLimitMiddleware, RequestLoggingMiddleware
from api.routers import agents, incidents, investigations, knowledge, lessons, students, system, websocket
from config.settings import get_settings
from core.message_bus import get_message_bus
from database.connection import DatabaseManager
from database.seed_data import seed_database
from database.seed_rich_demo import seed_rich_demo
from orchestration.coordinator import TutorialCoordinator
from tutorial.health_check import HealthChecker

logger = structlog.get_logger(__name__)


def _error_payload(message: str, detail: str) -> dict[str, str]:
    return {
        "error": message,
        "detail": detail,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def create_app() -> FastAPI:
    """Construct the FastAPI application with middleware, routers, and lifespan hooks."""

    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings
        db_url = database_url_to_async(settings.database.url)
        db_manager = DatabaseManager(
            db_url,
            pool_size=settings.database.pool_size,
            echo=settings.database.echo,
        )
        await db_manager.initialize()
        app.state.db_manager = db_manager
        async with db_manager.session() as session:
            await seed_database(session)
            await seed_rich_demo(session)
        Path(settings.api.evidence_upload_dir).mkdir(parents=True, exist_ok=True)

        bus = await get_message_bus(
            max_queue_size=settings.message_bus.max_queue_size,
            message_ttl_seconds=settings.message_bus.message_ttl_seconds,
        )
        await bus.start()
        app.state.message_bus = bus

        coordinator = TutorialCoordinator(settings=settings, message_bus=bus)
        await coordinator.initialize()
        app.state.coordinator = coordinator
        health_checker = HealthChecker(db_manager, bus, coordinator, settings)
        app.state.health_checker = health_checker
        health_task = asyncio.create_task(health_checker.run_periodic(60), name="tutorial-health-periodic")
        logger.info("tutorial_api_startup_complete")
        yield
        health_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await health_task
        await coordinator.shutdown()
        await bus.stop()
        await db_manager.close()
        logger.info("tutorial_api_shutdown_complete")

    app = FastAPI(
        title="TUTORIAL API",
        description="The World's First Agentic AI That Learns by Teaching",
        version="1.0.0",
        lifespan=lifespan,
    )

    @app.exception_handler(HTTPException)
    async def _http_exc_handler(_request: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail
        if not isinstance(detail, str):
            detail = str(detail)
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(http_error_label(exc.status_code), detail),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _starlette_http_exc_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(http_error_label(exc.status_code), detail),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=_error_payload("validation_error", str(exc.errors())),
        )

    @app.exception_handler(Exception)
    async def _unhandled_exc_handler(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_api_exception", err=str(exc))
        return JSONResponse(
            status_code=500,
            content=_error_payload("internal_error", "An unexpected error occurred."),
        )

    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(RateLimitMiddleware, requests_per_minute=settings.api.rate_limit_per_minute)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(incidents.router, prefix="/api/v1/incidents", tags=["incidents"])
    app.include_router(investigations.router, prefix="/api/v1/investigations", tags=["investigations"])
    app.include_router(lessons.router, prefix="/api/v1/lessons", tags=["lessons"])
    app.include_router(students.router, prefix="/api/v1/students", tags=["students"])
    app.include_router(agents.router, prefix="/api/v1/agents", tags=["agents"])
    app.include_router(knowledge.router, prefix="/api/v1/knowledge", tags=["knowledge"])
    app.include_router(system.router, prefix="/api/v1/system", tags=["system"])
    app.include_router(websocket.router, prefix="/api/v1/ws", tags=["websocket"])
    return app


def http_error_label(code: int) -> str:
    """Short machine-readable error key."""
    if code == 404:
        return "not_found"
    if code == 401:
        return "unauthorized"
    if code == 403:
        return "forbidden"
    if code == 429:
        return "rate_limit_exceeded"
    return "http_error"


app = create_app()
