"""Unattended 24/7 queue monitoring with safe automation and scaling hooks."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import structlog

from config.constants import IncidentSeverity
from platforms.uipath.maestro_orchestrator import (
    MaestroOrchestrator,
    TUTORIAL_QUEUE_HEALTH,
    TUTORIAL_QUEUE_SECURITY_INCIDENTS,
    TUTORIAL_QUEUE_STUDENT,
)
from platforms.uipath.workflow_generator import WorkflowGenerator
from shared.models import Incident

logger = structlog.get_logger(__name__)

_MONITOR_INTERVAL = 30.0
_SCALE_QUEUE_DEPTH = 50


class UnattendedRunner:
    """Polls Orchestrator queues, starts jobs, and escalates based on depth and night mode."""

    def __init__(
        self,
        orchestrator: MaestroOrchestrator,
        workflow_generator: WorkflowGenerator,
        *,
        night_mode: bool = False,
        monitor_interval_seconds: float = _MONITOR_INTERVAL,
    ) -> None:
        self._orch = orchestrator
        self._wf = workflow_generator
        self._night = night_mode
        self._interval = max(1.0, monitor_interval_seconds)
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._scale_signals: list[dict[str, Any]] = []

    @property
    def scale_signals(self) -> list[dict[str, Any]]:
        return list(self._scale_signals)

    async def start_monitoring(self) -> None:
        """Begin continuous monitoring loop (``_MONITOR_INTERVAL`` seconds)."""

        self._stop.clear()
        self._task = asyncio.create_task(self._loop())
        logger.info("uipath_unattended_started", night_mode=self._night)

    async def stop_monitoring(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self._orch.close()
        logger.info("uipath_unattended_stopped")

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self._cycle()
            except Exception as exc:
                logger.error("uipath_unattended_cycle_error", error=str(exc))
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._interval)
            except TimeoutError:
                continue

    async def _cycle(self) -> None:
        critical = await self._orch.get_queue_items(TUTORIAL_QUEUE_SECURITY_INCIDENTS, status="New")
        normal = await self._orch.get_queue_items(TUTORIAL_QUEUE_STUDENT, status="New")
        health = await self._orch.get_queue_items(TUTORIAL_QUEUE_HEALTH, status="New")
        ordered = sorted(
            critical,
            key=lambda i: {"Critical": 0, "High": 1, "Normal": 2, "Low": 3}.get(i.priority, 2),
        )
        for item in ordered[:10]:
            await self._handle_security_item(item)
        for item in normal[:5]:
            await self._orch.start_job("Tutorial.StudentPersonalization", robot_id=None)
            if item.id is not None:
                await self._orch.dequeue_item(TUTORIAL_QUEUE_STUDENT, item.id)
        for item in health[:5]:
            await self._orch.start_job("Tutorial.AgentHealth", robot_id=None)
            if item.id is not None:
                await self._orch.dequeue_item(TUTORIAL_QUEUE_HEALTH, item.id)
        depth = len(critical) + len(normal)
        if depth > _SCALE_QUEUE_DEPTH:
            sig = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "depth": depth,
                "requested_robots": min(5, depth // 20),
            }
            self._scale_signals.append(sig)
            logger.warning("uipath_scale_up_requested", **sig)

    async def _handle_security_item(self, item: Any) -> None:
        """Generate BPMN workflow, start Maestro job, and complete mock items safely."""

        payload = dict(item.data)
        sev_raw = str(payload.get("severity", "medium")).lower()
        try:
            sev = IncidentSeverity(sev_raw)
        except ValueError:
            sev = IncidentSeverity.MEDIUM
        inc = Incident(
            title=str(payload.get("title", "Security incident")),
            description=str(payload.get("description", "Automated queue item")),
            severity=sev,
        )
        wf = await self._wf.generate_workflow(inc)
        job = await self._orch.start_job("Tutorial.IncidentResponse", robot_id=None)
        await self._orch.set_job_completed(job, success=True)
        if item.id is not None:
            await self._orch.dequeue_item(TUTORIAL_QUEUE_SECURITY_INCIDENTS, item.id)
        _ = wf.workflow_id
        if self._night:
            logger.info("uipath_night_mode_handled", item=item.id, job=job)
