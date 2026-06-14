"""Scheduled SPL-based threat detection with correlation and bus publishing."""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import structlog
from pydantic import BaseModel, Field

from config.constants import EventType, MessageBusTopics
from core.message_bus import MessageBus
from platforms.splunk.spl_client import AsyncSplunkClient, spl_validate_spl
from shared.models import Message

logger = structlog.get_logger(__name__)

_DETECTION_INTERVAL_SECONDS = 300.0


class ThreatFinding(BaseModel):
    """Single correlated detection."""

    model_config = {"extra": "forbid"}

    id: str = Field(min_length=4)
    rule_name: str = Field(min_length=1)
    severity: str = Field(pattern="^(LOW|MEDIUM|HIGH|CRITICAL)$")
    description: str = Field(min_length=1)
    affected_assets: list[str] = Field(default_factory=list)
    iocs: list[str] = Field(default_factory=list)
    raw_events: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    recommended_action: str = Field(min_length=1)
    spl_query: str = Field(min_length=1)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class _DetectionRule(BaseModel):
    model_config = {"extra": "forbid"}

    name: str
    spl: str
    base_severity: str = "MEDIUM"
    description: str = ""


DEFAULT_RULES: list[_DetectionRule] = [
    _DetectionRule(
        name="brute_force",
        base_severity="HIGH",
        description="Spike in authentication failures per source and user.",
        spl=(
            "index=security sourcetype=auth action=failure earliest=-1h latest=now "
            "| bin _time span=5m "
            "| stats count by _time, src_ip, user "
            "| where count > 10"
        ),
    ),
    _DetectionRule(
        name="beaconing",
        base_severity="MEDIUM",
        description="Outbound connection volume anomaly vs historical baseline.",
        spl=(
            "index=network sourcetype=firewall earliest=-1h latest=now "
            "| bin _time span=1h "
            "| stats count by _time, dest_ip "
            "| eventstats avg(count) as avg, stdev(count) as stdev by dest_ip "
            "| where count > (avg + 3*stdev) AND avg > 0"
        ),
    ),
    _DetectionRule(
        name="data_exfiltration",
        base_severity="CRITICAL",
        description="Very large cumulative egress per internal source.",
        spl=(
            "index=network sourcetype=firewall bytes_out > 100000000 earliest=-1h latest=now "
            "| stats sum(bytes_out) as total by src_ip "
            "| where total > 1000000000"
        ),
    ),
    _DetectionRule(
        name="privilege_escalation",
        base_severity="HIGH",
        description="Repeated sensitive privilege use events.",
        spl=(
            "index=windows (EventCode=4673 OR EventCode=4674 OR EventCode=4648) earliest=-1h latest=now "
            "| stats count by user, process_name "
            "| where count > 5"
        ),
    ),
]


def _extract_iocs(rows: list[dict[str, Any]]) -> list[str]:
    keys = ("src_ip", "dest_ip", "DestinationIp", "query", "user", "process_name")
    found: set[str] = set()
    for row in rows[:50]:
        for k in keys:
            v = row.get(k)
            if v and isinstance(v, str) and len(v) > 2:
                found.add(f"{k}={v}")
    return sorted(found)[:32]


def _severity_rank(s: str) -> int:
    return {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}.get(s, 1)


def _rank_to_severity(r: int) -> str:
    if r >= 4:
        return "CRITICAL"
    if r == 3:
        return "HIGH"
    if r == 2:
        return "MEDIUM"
    return "LOW"


class ThreatDetector:
    """Runs SPL detection rules, correlates by IOC, and publishes incidents."""

    def __init__(
        self,
        client: AsyncSplunkClient,
        message_bus: MessageBus | None = None,
        *,
        rules: list[_DetectionRule] | None = None,
        interval_seconds: float = _DETECTION_INTERVAL_SECONDS,
    ) -> None:
        self._client = client
        self._bus = message_bus
        self._rules = rules or list(DEFAULT_RULES)
        self._interval = max(60.0, interval_seconds)
        self._history: list[ThreatFinding] = []
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    @property
    def history(self) -> list[ThreatFinding]:
        return list(self._history)

    async def analyze_traffic(self, index: str = "main", timerange: str = "-1h") -> list[ThreatFinding]:
        """Execute all detection rules against Splunk (mock-aware)."""

        findings: list[ThreatFinding] = []
        for rule in self._rules:
            ok, issues = spl_validate_spl(rule.spl)
            if not ok:
                logger.warning("splunk_detection_rule_invalid", rule=rule.name, issues=issues)
                continue
            spl = rule.spl.replace("index=security", f"index={index}").replace("index=network", f"index={index}")
            spl = spl.replace("index=windows", f"index={index}")
            res = await self._client.search(spl, earliest=timerange, latest="now", max_results=200)
            if not res.rows:
                continue
            confidence = min(1.0, 0.45 + 0.05 * len(res.rows))
            finding = ThreatFinding(
                id=str(uuid.uuid4()),
                rule_name=rule.name,
                severity=rule.base_severity,
                description=rule.description,
                affected_assets=list(
                    {str(r.get("src_ip") or r.get("user") or r.get("dest_ip") or "") for r in res.rows if r},
                )[:20],
                iocs=_extract_iocs(res.rows),
                raw_events=res.rows[:25],
                confidence=confidence,
                recommended_action="Triage in Splunk, isolate affected hosts, and validate against CMDB.",
                spl_query=spl,
            )
            findings.append(finding)
        findings = self._correlate(findings)
        self._history.extend(findings)
        if self._bus and findings:
            msg = Message(
                topic=MessageBusTopics.INCIDENTS,
                payload={
                    "event": EventType.INCIDENT_DETECTED.value,
                    "source": "splunk_threat_detector",
                    "findings": [f.model_dump(mode="json") for f in findings],
                },
                source_agent="splunk_threat_detector",
            )
            published = await self._bus.publish(MessageBusTopics.INCIDENTS, msg)
            logger.info("splunk_threat_bus_publish", published=published, count=len(findings))
        return findings

    def _correlate(self, findings: list[ThreatFinding]) -> list[ThreatFinding]:
        """Boost severity when the same IOC hits multiple rules."""

        ioc_hits: dict[str, list[str]] = defaultdict(list)
        for f in findings:
            for ioc in f.iocs:
                ioc_hits[ioc].append(f.rule_name)
        out: list[ThreatFinding] = []
        for f in findings:
            boost = 0
            for ioc in f.iocs:
                if len(ioc_hits[ioc]) > 1:
                    boost = max(boost, 1)
            new_rank = min(4, _severity_rank(f.severity) + boost)
            out.append(f.model_copy(update={"severity": _rank_to_severity(new_rank)}))
        return out

    async def run_scheduled(self) -> None:
        """Background loop invoking ``analyze_traffic`` every ``interval_seconds``."""

        while not self._stop.is_set():
            try:
                await self.analyze_traffic()
            except Exception as exc:
                logger.error("splunk_detection_cycle_failed", error=str(exc))
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._interval)
            except TimeoutError:
                continue

    def start_background(self) -> None:
        if self._task is None or self._task.done():
            self._stop.clear()
            self._task = asyncio.create_task(self.run_scheduled())

    async def stop_background(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
