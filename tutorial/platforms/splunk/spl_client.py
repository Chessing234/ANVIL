"""Async Splunk REST client with job polling, retries, and search rate limiting."""

from __future__ import annotations

import asyncio
import json
import os
import random
import urllib.parse
from datetime import datetime, timezone
from typing import Any

import aiohttp
import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)

_MAX_CONCURRENT_SEARCHES = 10


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SearchResult(BaseModel):
    """Normalized Splunk search results."""

    model_config = {"extra": "forbid"}

    sid: str | None = None
    query: str
    earliest: str
    latest: str
    row_count: int = Field(ge=0)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    messages: list[str] = Field(default_factory=list)


class AlertConfig(BaseModel):
    """Saved-search alert configuration subset."""

    model_config = {"extra": "forbid"}

    name: str = Field(min_length=1)
    search: str = Field(min_length=1)
    cron_schedule: str = Field(default="*/5 * * * *")
    description: str = ""
    disabled: bool = False
    actions: list[str] = Field(default_factory=list)


class AlertSummary(BaseModel):
    """Lightweight alert listing row."""

    model_config = {"extra": "forbid"}

    name: str
    app: str = "search"
    disabled: bool = False
    alert_type: str = "always"


class AlertEvent(BaseModel):
    """Single alert firing or audit record."""

    model_config = {"extra": "forbid"}

    alert_id: str = Field(min_length=1)
    fired_at: datetime = Field(default_factory=_utcnow)
    result_count: int = Field(ge=0, default=0)
    digest: str = ""


class DashboardSummary(BaseModel):
    """Dashboard listing entry."""

    model_config = {"extra": "forbid"}

    name: str
    label: str = ""
    app: str = "search"


class Dashboard(BaseModel):
    """Dashboard definition payload."""

    model_config = {"extra": "forbid"}

    name: str
    eai_data: str = ""
    label: str = ""


class IndexInfo(BaseModel):
    """Index metadata."""

    model_config = {"extra": "forbid"}

    name: str
    total_event_count: int = 0
    frozen: bool = False


class FieldStats(BaseModel):
    """Numeric summary for a field."""

    model_config = {"extra": "forbid"}

    index: str
    field: str
    timerange: str
    distinct_count: int = 0
    null_count: int = 0


class IndexStats(BaseModel):
    """High-level index statistics."""

    model_config = {"extra": "forbid"}

    index: str
    event_count: int = 0
    size_bytes: int = 0


class SplunkHealth(BaseModel):
    """Splunk server / connectivity health."""

    model_config = {"extra": "forbid"}

    ok: bool
    version: str = ""
    server_name: str = ""
    message: str = ""


class FieldExtraction(BaseModel):
    """Proposed field extraction rule."""

    model_config = {"extra": "forbid"}

    name: str
    pattern: str
    sourcetype: str = ""


class ThreatIntelResult(BaseModel):
    """IOC lookup response."""

    model_config = {"extra": "forbid"}

    ioc_type: str
    ioc_value: str
    verdict: str = Field(default="unknown", pattern="^(clean|suspicious|malicious|unknown)$")
    sources: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)


def _mock_search_rows(query: str) -> list[dict[str, Any]]:
    q = query.lower()
    if "failure" in q or "failed_login" in q or "action=failure" in q:
        return [
            {"_time": "2024-01-01T12:00:00", "src_ip": "10.0.0.5", "user": "alice", "count": 12},
        ]
    if "beacon" in q or "dns" in q:
        return [{"_time": "2024-01-01T13:00:00", "query": "evil.example", "count": 400}]
    if "firewall" in q and "eventstats" in q:
        return [{"_time": "2024-01-01T14:00:00", "dest_ip": "198.51.100.9", "src_ip": "10.0.0.5", "count": 500}]
    if "bytes_out" in q and "sum(bytes_out)" in q.replace(" ", ""):
        return [{"src_ip": "10.0.0.7", "total": 2_000_000_000}]
    if "eventcode=4673" in q.replace(" ", "") or "4673" in q:
        return [{"user": "bob", "process_name": "powershell.exe", "count": 8}]
    if "sysmon" in q and "eventcode=3" in q.replace(" ", ""):
        return [{"DestinationIp": "198.51.100.2", "Image": "curl.exe"}]
    return [{"_raw": "sample", "host": "web01", "sourcetype": "access_combined"}]


class AsyncSplunkClient:
    """Splunk REST client using aiohttp with bounded concurrency and retries."""

    def __init__(
        self,
        base_url: str,
        auth_token: str | None = None,
        *,
        session_key: str | None = None,
        verify_ssl: bool = True,
        mock: bool | None = None,
        timeout_seconds: float = 120.0,
        max_retries: int = 3,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._token = auth_token or os.environ.get("SPLUNK_TOKEN", "")
        self._session_key = session_key
        self._verify = verify_ssl
        if mock is True:
            self._mock = True
        elif mock is False:
            self._mock = False
        else:
            self._mock = os.environ.get("SPLUNK_MOCK", "1") == "1"
        self._timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self._max_retries = max(1, max_retries)
        self._session: aiohttp.ClientSession | None = None
        self._search_sem = asyncio.Semaphore(_MAX_CONCURRENT_SEARCHES)
        self._lock = asyncio.Lock()

    @classmethod
    def from_env(cls) -> AsyncSplunkClient:
        """Build client from ``SPLUNK_HOST``, ``SPLUNK_TOKEN``, and optional mock flags."""

        host = os.environ.get("SPLUNK_HOST", "https://localhost:8089")
        return cls(host, auth_token=os.environ.get("SPLUNK_TOKEN"))

    def _auth_headers(self) -> dict[str, str]:
        if self._token:
            return {"Authorization": f"Splunk {self._token}"}
        if self._session_key:
            return {"Authorization": f"Splunk {self._session_key}"}
        return {}

    async def _ensure_session(self) -> aiohttp.ClientSession:
        async with self._lock:
            if self._session is None or self._session.closed:
                connector = aiohttp.TCPConnector(ssl=self._verify)
                self._session = aiohttp.ClientSession(
                    timeout=self._timeout,
                    connector=connector,
                    headers=self._auth_headers(),
                )
            return self._session

    async def close(self) -> None:
        async with self._lock:
            if self._session and not self._session.closed:
                await self._session.close()
            self._session = None

    async def _refresh_session_headers(self) -> None:
        async with self._lock:
            if self._session and not self._session.closed:
                await self._session.close()
            self._session = None
        await self._ensure_session()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self._mock:
            return {"mock": True, "path": path, "method": method}
        session = await self._ensure_session()
        url = f"{self._base}{path}"
        last_err: BaseException | None = None
        for attempt in range(self._max_retries):
            try:
                async with session.request(
                    method,
                    url,
                    params=params,
                    data=data,
                ) as resp:
                    if resp.status == 401 and attempt < self._max_retries - 1:
                        await self._refresh_session_headers()
                        session = await self._ensure_session()
                        continue
                    text = await resp.text()
                    if resp.status >= 400:
                        raise RuntimeError(f"splunk_http_{resp.status}: {text[:500]}")
                    if "application/json" in resp.headers.get("Content-Type", ""):
                        return json.loads(text) if text else {}
                    return {"text": text}
            except (aiohttp.ClientError, TimeoutError, RuntimeError) as exc:
                last_err = exc
                await asyncio.sleep(min(30.0, (2**attempt) + random.random()))
        raise RuntimeError(f"Splunk request failed after retries: {last_err}") from last_err

    async def search(
        self,
        query: str,
        earliest: str = "-24h",
        latest: str = "now",
        max_results: int = 100,
    ) -> SearchResult:
        """Run SPL via async job create → poll → results."""

        async with self._search_sem:
            if self._mock:
                rows = _mock_search_rows(query)
                return SearchResult(
                    sid="mock-sid",
                    query=query,
                    earliest=earliest,
                    latest=latest,
                    row_count=len(rows),
                    rows=rows[:max_results],
                )
            create = await self._request(
                "POST",
                "/services/search/jobs",
                data={
                    "search": query,
                    "earliest_time": earliest,
                    "latest_time": latest,
                    "output_mode": "json",
                },
            )
            sid = str(create.get("sid") or create.get("entry", [{}])[0].get("content", {}).get("sid", ""))
            if not sid and isinstance(create.get("entry"), list) and create["entry"]:
                sid = str(create["entry"][0].get("name", ""))
            if not sid:
                raise RuntimeError("splunk_missing_sid")
            for _ in range(120):
                status = await self._request(
                    "GET",
                    f"/services/search/jobs/{urllib.parse.quote(sid, safe='')}",
                    params={"output_mode": "json"},
                )
                content = status.get("entry", [{}])[0].get("content", {}) if status.get("entry") else {}
                if str(content.get("isDone", "0")) == "1":
                    break
                await asyncio.sleep(0.5)
            results = await self._request(
                "GET",
                f"/services/search/jobs/{urllib.parse.quote(sid, safe='')}/results",
                params={"output_mode": "json", "count": max_results},
            )
            rows = results.get("results", []) if isinstance(results, dict) else []
            return SearchResult(
                sid=sid,
                query=query,
                earliest=earliest,
                latest=latest,
                row_count=len(rows),
                rows=rows,
            )

    async def search_oneShot(self, query: str, timerange: str = "-1h") -> list[dict[str, Any]]:
        """Run a oneshot search (no persistent job SID)."""

        async with self._search_sem:
            if self._mock:
                return _mock_search_rows(query)[:500]
            data = {
                "search": query,
                "earliest_time": timerange,
                "latest_time": "now",
                "output_mode": "json",
                "exec_mode": "oneshot",
            }
            resp = await self._request("POST", "/services/search/jobs/export", data=data)
            if isinstance(resp, dict) and "results" in resp:
                return list(resp["results"])
            if isinstance(resp, dict) and "text" in resp:
                lines = [ln for ln in str(resp["text"]).splitlines() if ln.strip().startswith("{")]
                out: list[dict[str, Any]] = []
                for ln in lines[:500]:
                    try:
                        out.append(json.loads(ln))
                    except json.JSONDecodeError:
                        continue
                return out
            return []

    async def create_alert(self, config: AlertConfig) -> str:
        """Create a saved search with alerting metadata; returns identifier."""

        if self._mock:
            return f"alert:{config.name}"
        await self._request(
            "POST",
            "/servicesNS/-/search/saved/searches",
            data={
                "name": config.name,
                "search": config.search,
                "description": config.description,
                "is_scheduled": "1",
                "cron_schedule": config.cron_schedule,
                "disabled": "1" if config.disabled else "0",
                "alert.track": "1",
                "actions": ",".join(config.actions) if config.actions else "",
                "output_mode": "json",
            },
        )
        return f"saved:{config.name}"

    async def delete_alert(self, alert_id: str) -> bool:
        if self._mock:
            return True
        name = alert_id.split(":", 1)[-1]
        await self._request(
            "DELETE",
            f"/servicesNS/-/search/saved/searches/{urllib.parse.quote(name, safe='')}",
        )
        return True

    async def get_alert_history(self, alert_id: str) -> list[AlertEvent]:
        if self._mock:
            return [
                AlertEvent(alert_id=alert_id, result_count=3, digest="mock"),
            ]
        name = alert_id.split(":", 1)[-1]
        data = await self._request(
            "GET",
            f"/servicesNS/-/search/saved/searches/{urllib.parse.quote(name, safe='')}/history",
            params={"output_mode": "json"},
        )
        events: list[AlertEvent] = []
        for entry in data.get("entry", []) if isinstance(data, dict) else []:
            c = entry.get("content", {})
            events.append(
                AlertEvent(
                    alert_id=alert_id,
                    fired_at=_utcnow(),
                    result_count=int(c.get("triggered_alert_count", 0) or 0),
                    digest=str(c.get("digest", "")),
                ),
            )
        return events

    async def list_dashboards(self) -> list[DashboardSummary]:
        if self._mock:
            return [
                DashboardSummary(name="security_ops", label="Security Operations"),
                DashboardSummary(name="education_metrics", label="Education"),
            ]
        data = await self._request("GET", "/servicesNS/-/data/ui/views", params={"output_mode": "json"})
        out: list[DashboardSummary] = []
        for entry in data.get("entry", []) if isinstance(data, dict) else []:
            name = str(entry.get("name", ""))
            content = entry.get("content", {})
            out.append(
                DashboardSummary(
                    name=name,
                    label=str(content.get("label", name)),
                    app=str(content.get("eai:appName", "search")),
                ),
            )
        return out

    async def export_dashboard(self, dashboard_name: str, format: str = "json") -> bytes:
        if self._mock:
            payload = {"name": dashboard_name, "format": format, "panels": []}
            return json.dumps(payload).encode("utf-8")
        data = await self._request(
            "GET",
            f"/servicesNS/-/data/ui/views/{urllib.parse.quote(dashboard_name, safe='')}",
            params={"output_mode": format},
        )
        if format == "json":
            return json.dumps(data).encode("utf-8")
        text = data.get("text", "") if isinstance(data, dict) else ""
        return str(text).encode("utf-8")

    async def get_index_stats(self, index: str) -> IndexStats:
        if self._mock:
            return IndexStats(index=index, event_count=1_000_000, size_bytes=500_000_000)
        q = f"| rest /services/data/indexes/{index} splunk_server=local | fields title, totalEventCount, currentDBSizeMB"
        res = await self.search_oneShot(q, "-24h")
        if res and isinstance(res[0], dict):
            row = res[0]
            return IndexStats(
                index=index,
                event_count=int(float(row.get("totalEventCount", 0) or 0)),
                size_bytes=int(float(row.get("currentDBSizeMB", 0) or 0) * 1_000_000),
            )
        return IndexStats(index=index)

    async def update_saved_search(self, name: str, updates: dict[str, Any]) -> None:
        """Apply field updates to an existing saved search."""

        if self._mock:
            return
        form: dict[str, str] = {"output_mode": "json"}
        for k, v in updates.items():
            form[str(k)] = str(v)
        await self._request(
            "POST",
            f"/servicesNS/-/search/saved/searches/{urllib.parse.quote(name, safe='')}",
            data=form,
        )

    async def health_check(self) -> SplunkHealth:
        if self._mock:
            return SplunkHealth(ok=True, version="9.2.0", server_name="mock-splunk", message="mock")
        try:
            data = await self._request("GET", "/services/server/info/server-info", params={"output_mode": "json"})
            entry = data.get("entry", [{}])[0] if data.get("entry") else {}
            c = entry.get("content", {})
            return SplunkHealth(
                ok=True,
                version=str(c.get("generator.version", "")),
                server_name=str(c.get("serverName", "")),
                message="connected",
            )
        except Exception as exc:
            return SplunkHealth(ok=False, message=str(exc)[:500])

    async def list_saved_alerts(self) -> list[AlertSummary]:
        """List saved searches that have alerting enabled."""

        if self._mock:
            return [
                AlertSummary(name="brute_force", disabled=False, alert_type="number of events"),
                AlertSummary(name="beaconing", disabled=False, alert_type="custom"),
            ]
        data = await self._request(
            "GET",
            "/servicesNS/-/search/saved/searches",
            params={"output_mode": "json", "count": 500},
        )
        out: list[AlertSummary] = []
        for entry in data.get("entry", []) if isinstance(data, dict) else []:
            c = entry.get("content", {})
            if str(c.get("alert.track", "0")) == "1" or str(c.get("is_scheduled", "0")) == "1":
                out.append(
                    AlertSummary(
                        name=str(entry.get("name", "")),
                        disabled=str(c.get("disabled", "0")) == "1",
                        alert_type=str(c.get("alert_type", "always")),
                    ),
                )
        return out

    async def get_saved_search_config(self, name: str) -> AlertConfig:
        """Return saved search / alert configuration."""

        if self._mock:
            return AlertConfig(
                name=name,
                search="index=_internal | head 5",
                description="mock",
                actions=["email", "logevent"],
            )
        data = await self._request(
            "GET",
            f"/servicesNS/-/search/saved/searches/{urllib.parse.quote(name, safe='')}",
            params={"output_mode": "json"},
        )
        entry = data.get("entry", [{}])[0] if data.get("entry") else {}
        c = entry.get("content", {})
        return AlertConfig(
            name=name,
            search=str(c.get("search", "")),
            description=str(c.get("description", "")),
            cron_schedule=str(c.get("cron_schedule", "*/5 * * * *")),
            disabled=str(c.get("disabled", "0")) == "1",
            actions=[a for a in str(c.get("action.email.to", "")).split(",") if a],
        )

    async def list_indexes(self) -> list[IndexInfo]:
        if self._mock:
            return [
                IndexInfo(name="main", total_event_count=5000),
                IndexInfo(name="security", total_event_count=1200),
            ]
        data = await self._request("GET", "/services/data/indexes", params={"output_mode": "json"})
        out: list[IndexInfo] = []
        for entry in data.get("entry", []) if isinstance(data, dict) else []:
            c = entry.get("content", {})
            out.append(
                IndexInfo(
                    name=str(entry.get("name", "")),
                    total_event_count=int(float(c.get("totalEventCount", 0) or 0)),
                    frozen=str(c.get("frozenTimePeriodInSecs", "0")) != "0",
                ),
            )
        return out

    async def field_stats(self, index: str, field: str, timerange: str) -> FieldStats:
        if self._mock:
            return FieldStats(index=index, field=field, timerange=timerange, distinct_count=42, null_count=2)
        q = (
            f"search index={index} earliest={timerange} latest=now "
            f"| fieldsummary {field} | fields distinct_count, null_count"
        )
        rows = await self.search_oneShot(q, timerange)
        if rows and isinstance(rows[0], dict):
            r = rows[0]
            return FieldStats(
                index=index,
                field=field,
                timerange=timerange,
                distinct_count=int(float(r.get("distinct_count", 0) or 0)),
                null_count=int(float(r.get("null_count", 0) or 0)),
            )
        return FieldStats(index=index, field=field, timerange=timerange)

    async def get_dashboard_definition(self, dashboard_name: str) -> Dashboard:
        if self._mock:
            return Dashboard(name=dashboard_name, label=dashboard_name, eai_data="<dashboard/>")
        data = await self._request(
            "GET",
            f"/servicesNS/-/data/ui/views/{urllib.parse.quote(dashboard_name, safe='')}",
            params={"output_mode": "json"},
        )
        entry = data.get("entry", [{}])[0] if data.get("entry") else {}
        c = entry.get("content", {})
        return Dashboard(
            name=dashboard_name,
            eai_data=str(c.get("eai:data", "")),
            label=str(c.get("label", dashboard_name)),
        )


def spl_validate_spl(query: str) -> tuple[bool, list[str]]:
    """Reject obviously unsafe SPL fragments before execution."""

    issues: list[str] = []
    stripped = query.strip()
    if not stripped:
        issues.append("empty_query")
        return False, issues
    lower = stripped.lower()
    banned = ("delete ", "shutdown", "clear index", "outputcsv", "runshellscript", "script ")
    for b in banned:
        if b in lower:
            issues.append(f"banned:{b.strip()}")
    if stripped.startswith("|"):
        issues.append("leading_pipe")
    return (len(issues) == 0), issues
