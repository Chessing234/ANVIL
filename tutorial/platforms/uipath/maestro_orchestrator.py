"""UiPath Orchestrator / Maestro-style API client with queues, jobs, and robots."""

from __future__ import annotations

import asyncio
import os
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)

TUTORIAL_QUEUE_SECURITY_INCIDENTS = "SecurityIncidents"
TUTORIAL_QUEUE_EVIDENCE = "EvidenceCollection"
TUTORIAL_QUEUE_LESSON = "LessonGeneration"
TUTORIAL_QUEUE_STUDENT = "StudentInteractions"
TUTORIAL_QUEUE_HEALTH = "AgentHealthChecks"
TUTORIAL_QUEUE_ROBOT_INBOUND = "RobotInboundTutorial"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class QueueItem(BaseModel):
    """Orchestrator queue item with SLA metadata."""

    model_config = {"extra": "forbid"}

    id: int | None = None
    queue_name: str = Field(min_length=1)
    status: str = Field(default="New", min_length=1)
    priority: str = Field(default="Normal", pattern="^(Low|Normal|High|Critical)$")
    due_date: datetime | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str = Field(min_length=1)
    defer_date: datetime | None = None


class JobStatus(BaseModel):
    """UiPath job execution state."""

    model_config = {"extra": "forbid"}

    job_id: str = Field(min_length=1)
    state: str = Field(min_length=1)
    message: str = ""
    robot_name: str = ""


class RobotInfo(BaseModel):
    """Attended or unattended robot metadata."""

    model_config = {"extra": "forbid"}

    id: int
    name: str
    machine_name: str = ""
    type: str = Field(default="Unattended", pattern="^(Attended|Unattended)$")


class ProcessInfo(BaseModel):
    """Released process (package) metadata."""

    model_config = {"extra": "forbid"}

    id: str
    name: str
    environment: str = ""


class MaestroOrchestrator:
    """Async Orchestrator REST client with retries, used as Maestro integration surface."""

    def __init__(
        self,
        base_url: str,
        *,
        tenant_name: str,
        organization_name: str,
        folder_id: int = 0,
        access_token: str | None = None,
        mock: bool | None = None,
        timeout_seconds: float = 60.0,
        max_retries: int = 3,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._tenant = tenant_name
        self._org = organization_name
        self._folder_id = folder_id
        self._token = access_token or os.environ.get("UIPATH_ORCH_TOKEN", "")
        if mock is True:
            self._mock = True
        elif mock is False:
            self._mock = False
        else:
            self._mock = os.environ.get("UIPATH_MOCK", "1") == "1"
        self._timeout = httpx.Timeout(timeout_seconds)
        self._max_retries = max(1, max_retries)
        self._client: httpx.AsyncClient | None = None
        self._lock = asyncio.Lock()
        self._mock_queues: dict[str, list[QueueItem]] = {q: [] for q in _default_queue_names()}
        self._mock_jobs: dict[str, JobStatus] = {}
        self._mock_triggers: dict[str, str] = {}
        self._mock_robots: list[RobotInfo] = [
            RobotInfo(id=1, name="SOC-Unattended-1", machine_name="vm-soc-01", type="Unattended"),
            RobotInfo(id=2, name="SOC-Attended-Analyst", machine_name="laptop-analyst", type="Attended"),
        ]
        self._mock_processes: list[ProcessInfo] = [
            ProcessInfo(id="proc_incident", name="Tutorial.IncidentResponse", environment="Production"),
            ProcessInfo(id="proc_threat", name="Tutorial.ThreatHunting", environment="Production"),
            ProcessInfo(id="proc_evidence", name="Tutorial.EvidenceCollection", environment="Production"),
            ProcessInfo(id="proc_lesson", name="Tutorial.LessonGeneration", environment="Production"),
        ]

    @classmethod
    def from_env(cls) -> MaestroOrchestrator:
        return cls(
            os.environ.get("UIPATH_ORCH_URL", "https://cloud.uipath.com"),
            tenant_name=os.environ.get("UIPATH_TENANT", "default"),
            organization_name=os.environ.get("UIPATH_ORG", "default"),
            folder_id=int(os.environ.get("UIPATH_FOLDER_ID", "0")),
            access_token=os.environ.get("UIPATH_ORCH_TOKEN"),
        )

    def _orch_path(self, suffix: str) -> str:
        return (
            f"{self._base}/{self._tenant}/{self._org}/odata"
            f"{suffix}"
        )

    async def _ensure_client(self) -> httpx.AsyncClient:
        async with self._lock:
            if self._client is None or self._client.is_closed:
                headers = {"Authorization": f"Bearer {self._token}", "X-UIPATH-OrganizationUnitId": str(self._folder_id)}
                self._client = httpx.AsyncClient(timeout=self._timeout, headers=headers)
            return self._client

    async def close(self) -> None:
        async with self._lock:
            if self._client and not self._client.is_closed:
                await self._client.aclose()
            self._client = None

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        if self._mock:
            return {"mock": True, "path": path}
        client = await self._ensure_client()
        last: BaseException | None = None
        for attempt in range(self._max_retries):
            try:
                resp = await client.request(method, path, **kwargs)
                if resp.status_code == 401 and attempt < self._max_retries - 1:
                    await asyncio.sleep(1.0 + random.random())
                    continue
                resp.raise_for_status()
                if resp.content:
                    return resp.json()
                return {}
            except (httpx.HTTPError, TimeoutError) as exc:
                last = exc
                await asyncio.sleep(min(16.0, (2**attempt) + random.random()))
        raise RuntimeError(f"UiPath Orchestrator request failed: {last}") from last

    def _normalize_priority(self, priority: str) -> str:
        key = priority.strip().lower()
        return {"low": "Low", "normal": "Normal", "high": "High", "critical": "Critical"}.get(key, "Normal")

    async def create_queue_item(
        self,
        queue_name: str,
        data: dict[str, Any],
        priority: str = "Normal",
    ) -> str:
        """Create a queue item for unattended robots (returns item key or id)."""

        correlation = str(data.get("correlation_id") or uuid.uuid4())
        due = data.get("due_date")
        due_dt = datetime.fromisoformat(due) if isinstance(due, str) else _utcnow() + timedelta(hours=4)
        item = QueueItem(
            queue_name=queue_name,
            status="New",
            priority=self._normalize_priority(priority),
            due_date=due_dt,
            data=dict(data),
            correlation_id=correlation,
        )
        if self._mock:
            item.id = random.randint(1000, 999999)
            self._mock_queues.setdefault(queue_name, []).append(item)
            logger.info("uipath_queue_item_mock", queue=queue_name, id=item.id)
            return str(item.id)
        payload = {
            "queueName": queue_name,
            "specificContent": data,
            "reference": correlation,
            "priority": priority,
        }
        path = self._orch_path("/QueueItems/UiPathODataSvc.AddQueueItem")
        result = await self._request("POST", path, json=payload)
        return str(result.get("Id", result.get("id", correlation)))

    async def get_queue_items(self, queue_name: str, status: str = "New") -> list[QueueItem]:
        """Retrieve queue items filtered by status."""

        if self._mock:
            return [i for i in self._mock_queues.get(queue_name, []) if i.status == status]
        path = self._orch_path("/QueueItems")
        params = {"$filter": f"Status eq '{status}' and QueueDefinitionId ne null", "$top": 100}
        data = await self._request("GET", path, params=params)
        items: list[QueueItem] = []
        for row in data.get("value", []):
            items.append(
                QueueItem(
                    id=int(row.get("Id", 0)),
                    queue_name=queue_name,
                    status=str(row.get("Status", status)),
                    priority=str(row.get("Priority", "Normal")),
                    data=dict(row.get("SpecificContent", {})),
                    correlation_id=str(row.get("Reference", "")),
                ),
            )
        return items

    async def start_job(self, process_name: str, robot_id: str | None = None) -> str:
        """Start a process on a robot; returns job id."""

        job_id = f"job_{uuid.uuid4().hex[:12]}"
        if self._mock:
            self._mock_jobs[job_id] = JobStatus(
                job_id=job_id,
                state="Running",
                message="mock",
                robot_name=robot_id or "default",
            )
            return job_id
        body: dict[str, Any] = {
            "startInfo": {
                "ReleaseKey": process_name,
                "Strategy": "Specific",
                "RobotIds": [int(robot_id)] if robot_id and robot_id.isdigit() else [],
                "JobsCount": 1,
                "Source": "Agent",
            },
        }
        path = self._orch_path("/Jobs/UiPath.Server.Configuration.OData.StartJobs")
        result = await self._request("POST", path, json=body)
        return str(result.get("value", [{}])[0].get("Id", job_id))

    async def get_job_status(self, job_id: str) -> JobStatus:
        if self._mock:
            st = self._mock_jobs.get(job_id)
            if st:
                return st
            return JobStatus(job_id=job_id, state="Unknown", message="not found")
        path = self._orch_path(f"/Jobs({job_id})")
        data = await self._request("GET", path)
        return JobStatus(
            job_id=job_id,
            state=str(data.get("State", "Unknown")),
            message=str(data.get("Info", "")),
            robot_name=str(data.get("RobotName", "")),
        )

    async def create_trigger(self, process_name: str, queue_name: str, schedule: str) -> str:
        """Create a trigger binding process to queue consumption or schedule string."""

        tid = f"trg_{uuid.uuid4().hex[:10]}"
        if self._mock:
            self._mock_triggers[tid] = f"{process_name}|{queue_name}|{schedule}"
            return tid
        body = {
            "Name": tid,
            "ReleaseName": process_name,
            "QueueDefinitionName": queue_name,
            "CronExpression": schedule if schedule.startswith("0") else "",
        }
        path = self._orch_path("/ProcessSchedules")
        result = await self._request("POST", path, json=body)
        return str(result.get("Id", tid))

    async def get_robots(self) -> list[RobotInfo]:
        if self._mock:
            return list(self._mock_robots)
        path = self._orch_path("/Robots")
        data = await self._request("GET", path, params={"$top": 200})
        out: list[RobotInfo] = []
        for row in data.get("value", []):
            out.append(
                RobotInfo(
                    id=int(row.get("Id", 0)),
                    name=str(row.get("Name", "")),
                    machine_name=str(row.get("MachineName", "")),
                    type="Attended" if row.get("Type") == "Studio" else "Unattended",
                ),
            )
        return out

    async def get_processes(self) -> list[ProcessInfo]:
        if self._mock:
            return list(self._mock_processes)
        path = self._orch_path("/Releases")
        data = await self._request("GET", path, params={"$top": 200})
        out: list[ProcessInfo] = []
        for row in data.get("value", []):
            out.append(
                ProcessInfo(
                    id=str(row.get("Key", row.get("Id", ""))),
                    name=str(row.get("ProcessKey", row.get("Name", ""))),
                    environment=str(row.get("EnvironmentName", "")),
                ),
            )
        return out

    async def set_job_completed(self, job_id: str, success: bool = True) -> None:
        """Mark mock job terminal (used by runners to avoid hanging jobs)."""

        if job_id in self._mock_jobs:
            self._mock_jobs[job_id] = JobStatus(
                job_id=job_id,
                state="Successful" if success else "Faulted",
                message="completed",
                robot_name=self._mock_jobs[job_id].robot_name,
            )

    async def dequeue_item(self, queue_name: str, item_id: int) -> None:
        """Mark queue item processed in mock store."""

        for it in self._mock_queues.get(queue_name, []):
            if it.id == item_id:
                it.status = "Successful"


def _default_queue_names() -> list[str]:
    return [
        TUTORIAL_QUEUE_SECURITY_INCIDENTS,
        TUTORIAL_QUEUE_EVIDENCE,
        TUTORIAL_QUEUE_LESSON,
        TUTORIAL_QUEUE_STUDENT,
        TUTORIAL_QUEUE_HEALTH,
        TUTORIAL_QUEUE_ROBOT_INBOUND,
    ]
