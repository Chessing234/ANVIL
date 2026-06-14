"""Aggregated health checks across database, bus, agents, integrations, and static assets."""

from __future__ import annotations

import asyncio
import contextlib
import time
from enum import StrEnum
from pathlib import Path

import httpx
import structlog
from pydantic import BaseModel, Field
from sqlalchemy import text

from config.constants import MessageBusTopics
from config.settings import Settings
from core.message_bus import MessageBus
from database.connection import DatabaseManager
from orchestration.coordinator import TutorialCoordinator
from shared.models import Message

logger = structlog.get_logger(__name__)


class ComponentStatus(StrEnum):
    """Per-component availability."""

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"


class OverallStatus(StrEnum):
    """Roll-up system status."""

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"


class ComponentHealth(BaseModel):
    """Single subsystem probe result."""

    model_config = {"extra": "forbid"}

    name: str
    status: ComponentStatus
    detail: str = ""
    latency_ms: float | None = None


class SystemHealthReport(BaseModel):
    """Structured output from ``HealthChecker.check_all``."""

    model_config = {"extra": "forbid"}

    overall: OverallStatus
    components: list[ComponentHealth]
    recommendations: list[str] = Field(default_factory=list)


class HealthChecker:
    """Probes every major runtime dependency and optionally publishes results to the bus."""

    def __init__(
        self,
        db_manager: DatabaseManager,
        message_bus: MessageBus,
        coordinator: TutorialCoordinator,
        settings: Settings,
        *,
        frontend_dist: Path | None = None,
    ) -> None:
        self._db = db_manager
        self._bus = message_bus
        self._coordinator = coordinator
        self._settings = settings
        base = Path(__file__).resolve().parents[1]
        self._frontend_dist = frontend_dist or (base / "frontend" / "dist")

    async def check_component(self, name: str) -> ComponentHealth:
        """Run a single named probe (used for targeted diagnostics)."""
        report = await self.check_all()
        for c in report.components:
            if c.name == name:
                return c
        return ComponentHealth(name=name, status=ComponentStatus.UNHEALTHY, detail="unknown component")

    async def check_all(self) -> SystemHealthReport:
        """Evaluate database, bus, agents, integrations, knowledge graph, API static assets."""

        components: list[ComponentHealth] = []
        recommendations: list[str] = []

        db_ok = False
        db_ms: float | None = None
        try:
            async with self._db.session() as session:
                t_db = time.perf_counter()
                res = await session.execute(text("SELECT 1"))
                db_ok = res.scalar() == 1
                db_ms = (time.perf_counter() - t_db) * 1000
        except Exception as exc:
            components.append(
                ComponentHealth(
                    name="database",
                    status=ComponentStatus.UNHEALTHY,
                    detail=str(exc),
                    latency_ms=None,
                ),
            )
            recommendations.append("Restore database connectivity and verify TUTORIAL_DATABASE__URL.")
        else:
            components.append(
                ComponentHealth(
                    name="database",
                    status=ComponentStatus.HEALTHY if db_ok else ComponentStatus.UNHEALTHY,
                    detail="query_ok" if db_ok else "unexpected scalar",
                    latency_ms=db_ms,
                ),
            )

        bus_ms: float | None = None
        bus_ok = False
        try:
            t_bus = time.perf_counter()
            stats = self._bus.get_stats()
            bus_ok = bool(stats) or stats == {}
            bus_ms = (time.perf_counter() - t_bus) * 1000
        except Exception as exc:
            components.append(
                ComponentHealth(name="message_bus", status=ComponentStatus.UNHEALTHY, detail=str(exc)),
            )
            recommendations.append("Restart the message bus or clear dead-letter backlog.")
        else:
            components.append(
                ComponentHealth(
                    name="message_bus",
                    status=ComponentStatus.HEALTHY if bus_ok else ComponentStatus.DEGRADED,
                    detail=str(stats),
                    latency_ms=bus_ms,
                ),
            )

        coord_ok = getattr(self._coordinator, "_initialized", False)
        metrics = None
        health_ms: float | None = None
        agent_detail = "coordinator_initialized" if coord_ok else "coordinator_not_initialized"
        try:
            t_m = time.perf_counter()
            metrics = await self._coordinator.get_system_health()
            health_ms = (time.perf_counter() - t_m) * 1000
            n_agents = len(metrics.all_agents)
            agent_detail = f"agents_reporting={n_agents}"
        except Exception as exc:
            agent_detail = str(exc)
            coord_ok = False
        components.append(
            ComponentHealth(
                name="agents",
                status=ComponentStatus.HEALTHY if coord_ok else ComponentStatus.UNHEALTHY,
                detail=agent_detail,
                latency_ms=health_ms,
            ),
        )
        components.append(
            ComponentHealth(
                name="api_server",
                status=ComponentStatus.HEALTHY if health_ms is not None else ComponentStatus.DEGRADED,
                detail="coordinator_health_probe",
                latency_ms=health_ms,
            ),
        )

        components.extend(await self._integration_components())

        graph_ok = False
        graph_detail = ""
        try:
            snap = await self._coordinator.get_flywheel_snapshot()
            nodes = int(snap["graph_stats"]["nodes"])
            edges = int(snap["graph_stats"]["edges"])
            graph_ok = nodes >= 0 and edges >= 0
            graph_detail = f"nodes={nodes},edges={edges}"
        except Exception as exc:
            graph_detail = str(exc)
        components.append(
            ComponentHealth(
                name="knowledge_graph",
                status=ComponentStatus.HEALTHY if graph_ok else ComponentStatus.DEGRADED,
                detail=graph_detail,
            ),
        )

        api_static = self._frontend_dist / "index.html"
        static_ok = api_static.is_file()
        components.append(
            ComponentHealth(
                name="frontend_build",
                status=ComponentStatus.HEALTHY if static_ok else ComponentStatus.DEGRADED,
                detail=str(self._frontend_dist) if static_ok else f"missing {api_static}",
            ),
        )
        if not static_ok:
            recommendations.append("Run `npm run build` in frontend/ to publish static assets.")

        if any(c.name.startswith("integration_") and c.status != ComponentStatus.HEALTHY for c in components):
            recommendations.append("Review MCP server definitions and network reachability for SIFT/Splunk/UiPath.")

        overall = OverallStatus.HEALTHY
        if any(c.status == ComponentStatus.UNHEALTHY for c in components):
            overall = OverallStatus.UNHEALTHY
        elif any(c.status == ComponentStatus.DEGRADED for c in components):
            overall = OverallStatus.DEGRADED

        return SystemHealthReport(overall=overall, components=components, recommendations=recommendations)

    async def _integration_components(self) -> list[ComponentHealth]:
        """SIFT path, Splunk HTTP, UiPath mock orchestrator, and MCP registry cache."""

        out: list[ComponentHealth] = []
        splunk_url = str(self._settings.security.splunk_host).rstrip("/")
        try:
            t0 = time.perf_counter()
            async with httpx.AsyncClient(timeout=2.0) as client:
                r = await client.get(splunk_url)
            ms = (time.perf_counter() - t0) * 1000
            out.append(
                ComponentHealth(
                    name="integration_splunk",
                    status=ComponentStatus.HEALTHY,
                    detail=f"http_status={r.status_code}",
                    latency_ms=ms,
                ),
            )
        except Exception as exc:
            out.append(
                ComponentHealth(
                    name="integration_splunk",
                    status=ComponentStatus.DEGRADED,
                    detail=str(exc),
                ),
            )

        sift_path = self._settings.security.sift_workstation_path
        if sift_path is None:
            out.append(
                ComponentHealth(
                    name="integration_sift",
                    status=ComponentStatus.DEGRADED,
                    detail="sift_workstation_path_unset",
                ),
            )
        elif sift_path.is_dir() or sift_path.is_file():
            out.append(
                ComponentHealth(
                    name="integration_sift",
                    status=ComponentStatus.HEALTHY,
                    detail=str(sift_path),
                ),
            )
        else:
            out.append(
                ComponentHealth(
                    name="integration_sift",
                    status=ComponentStatus.DEGRADED,
                    detail=f"missing_path={sift_path}",
                ),
            )

        try:
            from platforms.uipath.maestro_orchestrator import MaestroOrchestrator

            orch = MaestroOrchestrator(
                "https://mock.uipath.local",
                tenant_name="tenant",
                organization_name="org",
                mock=True,
            )
            t0 = time.perf_counter()
            robots = await orch.get_robots()
            ms = (time.perf_counter() - t0) * 1000
            out.append(
                ComponentHealth(
                    name="integration_uipath",
                    status=ComponentStatus.HEALTHY,
                    detail=f"robots={len(robots)}",
                    latency_ms=ms,
                ),
            )
        except Exception as exc:
            out.append(
                ComponentHealth(
                    name="integration_uipath",
                    status=ComponentStatus.DEGRADED,
                    detail=str(exc),
                ),
            )

        mcp_cache = self._settings.mcp.registry_cache_path
        if mcp_cache.exists():
            out.append(
                ComponentHealth(
                    name="integration_mcp_registry",
                    status=ComponentStatus.HEALTHY,
                    detail=str(mcp_cache),
                ),
            )
        else:
            out.append(
                ComponentHealth(
                    name="integration_mcp_registry",
                    status=ComponentStatus.DEGRADED,
                    detail=f"missing_cache={mcp_cache}",
                ),
            )
        return out

    async def run_periodic(self, interval_seconds: int = 60) -> None:
        """Publish ``check_all`` results to the system topic on a fixed cadence until cancelled."""

        try:
            while True:
                await asyncio.sleep(interval_seconds)
                report = await self.check_all()
                msg = Message(
                    topic=MessageBusTopics.SYSTEM,
                    payload={
                        "event": "health_check",
                        "overall": report.overall.value,
                        "components": [c.model_dump() for c in report.components],
                        "recommendations": report.recommendations,
                    },
                )
                with contextlib.suppress(Exception):
                    await self._bus.publish(MessageBusTopics.SYSTEM, msg)
                logger.info(
                    "health_check_tick",
                    overall=report.overall.value,
                    components=len(report.components),
                )
        except asyncio.CancelledError:
            logger.info("health_check_periodic_cancelled")
            raise
