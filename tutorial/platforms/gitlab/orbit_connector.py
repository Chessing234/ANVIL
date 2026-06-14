"""GitLab API v4 and Orbit-style automation connector (async, retries, mock mode)."""

from __future__ import annotations

import asyncio
import json
import os
import random
import uuid
from typing import Any

import aiohttp
import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


class FlowStep(BaseModel):
    """Single step inside an Orbit automation flow."""

    model_config = {"extra": "forbid"}

    name: str = Field(min_length=1)
    action: str = Field(min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)


class Agent(BaseModel):
    """GitLab Orbit AI agent descriptor."""

    model_config = {"extra": "forbid"}

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    skills: list[str] = Field(default_factory=list)


class Flow(BaseModel):
    """Orbit flow metadata."""

    model_config = {"extra": "forbid"}

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    steps: list[FlowStep] = Field(default_factory=list)


class Skill(BaseModel):
    """Reusable Orbit skill."""

    model_config = {"extra": "forbid"}

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    tools: list[str] = Field(default_factory=list)


class FlowResult(BaseModel):
    """Outcome of triggering a flow."""

    model_config = {"extra": "forbid"}

    flow_id: str = Field(min_length=1)
    status: str = Field(default="completed")
    outputs: dict[str, Any] = Field(default_factory=dict)


class ReviewResult(BaseModel):
    """AI-style merge request review summary."""

    model_config = {"extra": "forbid"}

    mr_id: str = Field(min_length=1)
    findings: list[str] = Field(default_factory=list)
    recommendation: str = ""


class Issue(BaseModel):
    """GitLab issue record."""

    model_config = {"extra": "forbid"}

    id: int = Field(ge=0)
    iid: int = Field(ge=0)
    web_url: str = ""
    title: str = ""


def _encode_project(project_id: str) -> str:
    return project_id.replace("/", "%2F")


class GitLabOrbitConnector:
    """Connects TUTORIAL to GitLab (API v4); Orbit entities are tracked as labeled issues when not mocked."""

    def __init__(
        self,
        base_url: str,
        *,
        access_token: str | None = None,
        default_project_id: str | None = None,
        mock: bool | None = None,
        timeout_seconds: float = 60.0,
        max_retries: int = 3,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._token = access_token or os.environ.get("GITLAB_TOKEN", "")
        self._default_project = default_project_id or os.environ.get("GITLAB_PROJECT_ID", "")
        if mock is True:
            self._mock = True
        elif mock is False:
            self._mock = False
        else:
            self._mock = os.environ.get("GITLAB_MOCK", "1") == "1"
        self._timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self._max_retries = max(1, max_retries)
        self._session: aiohttp.ClientSession | None = None
        self._lock = asyncio.Lock()
        self._mock_agents: dict[str, Agent] = {}
        self._mock_flows: dict[str, Flow] = {}
        self._mock_skills: dict[str, Skill] = {}
        self._mock_issues: list[Issue] = []
        self._mock_comments: list[tuple[str, int, str]] = []

    @classmethod
    def from_env(cls) -> GitLabOrbitConnector:
        return cls(
            os.environ.get("GITLAB_URL", "https://gitlab.com"),
            access_token=os.environ.get("GITLAB_TOKEN"),
            default_project_id=os.environ.get("GITLAB_PROJECT_ID"),
        )

    async def close(self) -> None:
        async with self._lock:
            if self._session and not self._session.closed:
                await self._session.close()
            self._session = None

    async def _ensure_session(self) -> aiohttp.ClientSession:
        async with self._lock:
            if self._session is None or self._session.closed:
                headers = {"PRIVATE-TOKEN": self._token} if self._token else {}
                self._session = aiohttp.ClientSession(timeout=self._timeout, headers=headers)
            return self._session

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
    ) -> dict[str, Any]:
        if self._mock:
            return {"mock": True, "path": path}
        session = await self._ensure_session()
        url = f"{self._base}{path}"
        last: BaseException | None = None
        for attempt in range(self._max_retries):
            try:
                async with session.request(method, url, params=params, json=json_body) as resp:
                    text = await resp.text()
                    if resp.status == 429 and attempt < self._max_retries - 1:
                        await asyncio.sleep(2**attempt + random.random())
                        continue
                    if resp.status >= 400:
                        raise RuntimeError(f"gitlab_http_{resp.status}: {text[:800]}")
                    if not text:
                        return {}
                    return json.loads(text)
            except (aiohttp.ClientError, TimeoutError, json.JSONDecodeError, RuntimeError) as exc:
                last = exc
                await asyncio.sleep(min(8.0, (2**attempt) + random.random()))
        raise RuntimeError(f"GitLab request failed after retries: {last}") from last

    async def _request_bytes(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> bytes:
        """Download binary or raw JSON artifact bytes from GitLab API v4."""
        if self._mock:
            path_lower = path.lower()
            if "gl-sast-report" in path_lower:
                payload = {
                    "version": "15.0.4",
                    "vulnerabilities": [
                        {
                            "id": "mock-sast-1",
                            "name": "SQL Injection",
                            "severity": "High",
                            "description": "User input concatenated into SQL.",
                            "location": {"file": "app/models.py", "start_line": 12},
                            "identifiers": [{"type": "cwe", "name": "CWE-89"}],
                        }
                    ],
                }
                return json.dumps(payload).encode()
            if "gl-dependency-scanning-report" in path_lower:
                payload = {
                    "dependency_files": [],
                    "vulnerabilities": [
                        {
                            "id": "mock-dep-1",
                            "name": "Vulnerable dependency",
                            "severity": "Medium",
                            "description": "Known CVE in transitive dependency.",
                        }
                    ],
                }
                return json.dumps(payload).encode()
            if "gl-secret-detection-report" in path_lower:
                payload = {
                    "vulnerabilities": [
                        {
                            "id": "mock-sec-1",
                            "severity": "Critical",
                            "description": "AWS key detected",
                            "location": {"file": ".env.example", "start_line": 3},
                        }
                    ]
                }
                return json.dumps(payload).encode()
            return b"{}"
        session = await self._ensure_session()
        url = f"{self._base}{path}"
        last: BaseException | None = None
        for attempt in range(self._max_retries):
            try:
                async with session.request(method, url, params=params) as resp:
                    data = await resp.read()
                    if resp.status == 429 and attempt < self._max_retries - 1:
                        await asyncio.sleep(2**attempt + random.random())
                        continue
                    if resp.status >= 400:
                        raise RuntimeError(f"gitlab_http_{resp.status}: {data[:800]!r}")
                    return data
            except (aiohttp.ClientError, TimeoutError, RuntimeError) as exc:
                last = exc
                await asyncio.sleep(min(8.0, (2**attempt) + random.random()))
        raise RuntimeError(f"GitLab bytes request failed after retries: {last}") from last

    async def list_pipeline_jobs(self, project_id: str, pipeline_id: int | str) -> list[dict[str, Any]]:
        """List jobs for a pipeline (used to locate security scan artifacts)."""
        if self._mock:
            return [
                {
                    "id": 9001,
                    "name": "sast",
                    "stage": "test",
                    "status": "success",
                    "artifacts_file": {"filename": "artifacts.zip"},
                },
                {
                    "id": 9002,
                    "name": "dependency_scanning",
                    "stage": "test",
                    "status": "success",
                },
                {
                    "id": 9003,
                    "name": "secret_detection",
                    "stage": "test",
                    "status": "success",
                },
            ]
        api_path = f"{self._project_path(project_id)}/pipelines/{pipeline_id}/jobs"
        data = await self._request("GET", api_path)
        if isinstance(data, list):
            return data
        return []

    async def download_job_artifact(
        self,
        project_id: str,
        job_id: int,
        artifact_path: str,
    ) -> bytes:
        """Download a single file from a job's artifacts bundle."""
        encoded = artifact_path.lstrip("/")
        api_path = (
            f"{self._project_path(project_id)}/jobs/{job_id}/artifacts/{encoded}"
        )
        return await self._request_bytes("GET", api_path)

    def _project_path(self, project_id: str | None) -> str:
        pid = project_id or self._default_project
        if not pid:
            raise ValueError("project_id is required")
        return f"/api/v4/projects/{_encode_project(pid)}"

    async def create_agent(self, name: str, description: str, skills: list[str]) -> Agent:
        aid = f"agent_{uuid.uuid4().hex[:10]}"
        if self._mock:
            agent = Agent(id=aid, name=name, description=description, skills=list(skills))
            self._mock_agents[aid] = agent
            return agent
        body = {
            "title": f"[Orbit Agent] {name}",
            "description": f"{description}\n\n```json\n{json.dumps({'type': 'orbit_agent', 'skills': skills})}\n```",
            "labels": "orbit,orbit-agent,tutorial",
        }
        data = await self._request(
            "POST",
            f"{self._project_path(None)}/issues",
            json_body=body,
        )
        return Agent(
            id=str(data.get("id", aid)),
            name=name,
            description=description,
            skills=list(skills),
        )

    async def create_flow(self, name: str, steps: list[FlowStep]) -> Flow:
        fid = f"flow_{uuid.uuid4().hex[:10]}"
        if self._mock:
            flow = Flow(id=fid, name=name, steps=list(steps))
            self._mock_flows[fid] = flow
            return flow
        body = {
            "title": f"[Orbit Flow] {name}",
            "description": "```json\n"
            + json.dumps({"type": "orbit_flow", "steps": [s.model_dump() for s in steps]})
            + "\n```",
            "labels": "orbit,orbit-flow,tutorial",
        }
        data = await self._request("POST", f"{self._project_path(None)}/issues", json_body=body)
        return Flow(id=str(data.get("id", fid)), name=name, steps=list(steps))

    async def create_skill(self, name: str, prompt: str, tools: list[str]) -> Skill:
        sid = f"skill_{uuid.uuid4().hex[:10]}"
        if self._mock:
            skill = Skill(id=sid, name=name, prompt=prompt, tools=list(tools))
            self._mock_skills[sid] = skill
            return skill
        body = {
            "title": f"[Orbit Skill] {name}",
            "description": f"{prompt}\n\nTools: {', '.join(tools)}",
            "labels": "orbit,orbit-skill,tutorial",
        }
        data = await self._request("POST", f"{self._project_path(None)}/issues", json_body=body)
        return Skill(id=str(data.get("id", sid)), name=name, prompt=prompt, tools=list(tools))

    async def trigger_flow(self, flow_id: str, context: dict[str, Any]) -> FlowResult:
        if self._mock:
            return FlowResult(flow_id=flow_id, status="completed", outputs=dict(context))
        body = {"ref": context.get("ref", "main"), "variables": [{"key": "ORBIT_FLOW_ID", "value": flow_id}]}
        data = await self._request("POST", f"{self._project_path(None)}/pipeline", json_body=body)
        return FlowResult(
            flow_id=flow_id,
            status=str(data.get("status", "created")),
            outputs={"pipeline_id": data.get("id"), "web_url": data.get("web_url")},
        )

    async def get_merge_request_changes(
        self, project_id: str, merge_request_iid: int
    ) -> list[dict[str, Any]]:
        """Return GitLab merge request ``changes`` entries (file paths + diffs)."""
        if self._mock:
            return [
                {
                    "old_path": "app.py",
                    "new_path": "app.py",
                    "diff": (
                        '+cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")\n'
                    ),
                }
            ]
        path = f"{self._project_path(project_id)}/merge_requests/{merge_request_iid}/changes"
        data = await self._request("GET", path)
        return list(data.get("changes", []))

    async def get_code_review(self, project_id: str, merge_request_iid: int) -> ReviewResult:
        if self._mock:
            return ReviewResult(
                mr_id=f"{project_id}!{merge_request_iid}",
                findings=["No blocking issues in mock review."],
                recommendation="Proceed with educational security checklist.",
            )
        path = f"{self._project_path(project_id)}/merge_requests/{merge_request_iid}/changes"
        data = await self._request("GET", path)
        changes = data.get("changes", [])
        notes: list[str] = []
        for ch in changes[:30]:
            new_path = str(ch.get("new_path", ""))
            if new_path:
                notes.append(f"Changed file: {new_path}")
        return ReviewResult(
            mr_id=f"{project_id}!{merge_request_iid}",
            findings=notes or ["No file changes returned."],
            recommendation="Review diffs with SecureCodingEducator for deeper analysis.",
        )

    async def create_issue(
        self,
        project_id: str,
        title: str,
        description: str,
        labels: list[str],
    ) -> Issue:
        if self._mock:
            iid = len(self._mock_issues) + 1
            issue = Issue(id=1000 + iid, iid=iid, web_url=f"https://mock/issue/{iid}", title=title)
            self._mock_issues.append(issue)
            return issue
        body = {
            "title": title,
            "description": description,
            "labels": ",".join(labels),
        }
        data = await self._request("POST", f"{self._project_path(project_id)}/issues", json_body=body)
        return Issue(
            id=int(data.get("id", 0)),
            iid=int(data.get("iid", 0)),
            web_url=str(data.get("web_url", "")),
            title=str(data.get("title", title)),
        )

    async def comment_on_mr(self, project_id: str, mr_iid: int, comment: str) -> None:
        if self._mock:
            self._mock_comments.append((project_id, mr_iid, comment))
            return
        body = {"body": comment}
        await self._request(
            "POST",
            f"{self._project_path(project_id)}/merge_requests/{mr_iid}/notes",
            json_body=body,
        )
