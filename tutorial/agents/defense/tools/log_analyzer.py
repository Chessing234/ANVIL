"""Log parsing, correlation, and anomaly detection."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import structlog
from pydantic import BaseModel, Field

from shared.models import Anomaly

logger = structlog.get_logger(__name__)


class LogEntry(BaseModel):
    """Normalized log row."""

    model_config = {"extra": "allow"}

    timestamp: datetime | None = None
    source_ip: str | None = None
    dest_ip: str | None = None
    user: str | None = None
    event_id: str | None = None
    message: str = ""
    raw: str = ""
    log_type: str = ""


class EventCorrelation(BaseModel):
    """Correlated events cluster."""

    key: str
    entries: list[LogEntry] = Field(default_factory=list)
    summary: str = ""


class LogAnalyzer:
    """Parse Windows EVTX-like JSON exports, syslog, Apache combined, IIS, Splunk JSON."""

    async def parse_logs(self, log_path: str, log_type: str) -> list[LogEntry]:
        path = Path(log_path).expanduser().resolve()
        if not path.is_file():
            return []

        text = path.read_text(errors="ignore")
        log_type_norm = log_type.lower()
        if log_type_norm in {"splunk", "json"}:
            return self._parse_json_lines(text, log_type_norm)
        if log_type_norm in {"windows", "evtx", "winevent"}:
            return self._parse_windows_like(text)
        if log_type_norm == "syslog":
            return self._parse_syslog(text)
        if log_type_norm in {"apache", "combined"}:
            return self._parse_apache(text)
        if log_type_norm == "iis":
            return self._parse_iis(text)
        return self._parse_generic(text, log_type_norm)

    async def correlate(self, events: list[LogEntry]) -> list[EventCorrelation]:
        by_user: defaultdict[str, list[LogEntry]] = defaultdict(list)
        by_ip: defaultdict[str, list[LogEntry]] = defaultdict(list)
        for ev in events:
            if ev.user:
                by_user[ev.user].append(ev)
            if ev.source_ip:
                by_ip[ev.source_ip].append(ev)
        correlations: list[EventCorrelation] = []
        for user, items in by_user.items():
            if len(items) >= 2:
                correlations.append(
                    EventCorrelation(key=f"user:{user}", entries=items, summary="multi-event user timeline"),
                )
        for ip, items in by_ip.items():
            if len(items) >= 3:
                correlations.append(
                    EventCorrelation(key=f"ip:{ip}", entries=items, summary="repeated activity from IP"),
                )
        return correlations

    async def detect_anomalies(self, events: list[LogEntry]) -> list[Anomaly]:
        anomalies: list[Anomaly] = []

        def _ref(parts: list[str]) -> str:
            joined = ";".join(parts)[:500]
            return joined

        failed = [e for e in events if "fail" in e.message.lower() or "4625" in (e.event_id or "")]
        if len(failed) >= 5:
            anomalies.append(
                Anomaly(
                    kind="bruteforce",
                    description="Multiple authentication failures",
                    severity="high",
                    evidence_ref=_ref([e.raw for e in failed[:5]]),
                ),
            )
        priv = [e for e in events if "4672" in (e.event_id or "") or "admin" in e.message.lower()]
        if priv:
            anomalies.append(
                Anomaly(
                    kind="priv_escalation",
                    description="Privileged logon or admin activity",
                    severity="medium",
                    evidence_ref=_ref([e.raw for e in priv[:3]]),
                ),
            )
        lateral = [e for e in events if "rdp" in e.message.lower() or "3389" in e.message]
        if lateral:
            anomalies.append(
                Anomaly(
                    kind="lateral_movement",
                    description="RDP references detected",
                    severity="medium",
                    evidence_ref=_ref([e.raw for e in lateral[:3]]),
                ),
            )
        exfil = [e for e in events if "upload" in e.message.lower() or "exfil" in e.message.lower()]
        if exfil:
            anomalies.append(
                Anomaly(
                    kind="exfiltration",
                    description="Possible exfiltration language in logs",
                    severity="high",
                    evidence_ref=_ref([e.raw for e in exfil]),
                ),
            )
        return anomalies

    def _parse_json_lines(self, text: str, log_type: str) -> list[LogEntry]:
        entries: list[LogEntry] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = obj.get("_time") or obj.get("timestamp")
            parsed_ts = self._parse_ts(str(ts)) if ts else None
            entries.append(
                LogEntry(
                    timestamp=parsed_ts,
                    source_ip=str(obj.get("src", obj.get("source_ip", ""))) or None,
                    user=str(obj.get("user", "")) or None,
                    event_id=str(obj.get("event_id", "")) or None,
                    message=str(obj.get("message", "")),
                    raw=line,
                    log_type=log_type,
                ),
            )
        return entries

    def _parse_windows_like(self, text: str) -> list[LogEntry]:
        entries: list[LogEntry] = []
        for line in text.splitlines():
            m = re.search(r"(?P<ts>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})", line)
            eid = re.search(r"EventID[=:](?P<eid>\d+)", line, re.I)
            entries.append(
                LogEntry(
                    timestamp=self._parse_ts(m.group("ts")) if m else None,
                    event_id=eid.group("eid") if eid else None,
                    message=line,
                    raw=line,
                    log_type="windows",
                ),
            )
        return entries

    def _parse_syslog(self, text: str) -> list[LogEntry]:
        entries: list[LogEntry] = []
        for line in text.splitlines():
            m = re.match(
                r"(?P<mon>[A-Za-z]{3}\s+\d{1,2}\s\d{2}:\d{2}:\d{2})\s+(?P<host>\S+)\s+(?P<proc>\S+):\s(?P<body>.*)",
                line,
            )
            if m:
                ts = self._parse_ts(m.group("mon"))
                body = m.group("body")
            else:
                ts = None
                body = line
            entries.append(LogEntry(timestamp=ts, message=body, raw=line, log_type="syslog"))
        return entries

    def _parse_apache(self, text: str) -> list[LogEntry]:
        entries: list[LogEntry] = []
        pattern = re.compile(
            r'^(?P<ip>\S+) \S+ \S+ \[(?P<ts>[^\]]+)\] "(?P<req>[^"]*)" (?P<status>\d{3})',
        )
        for line in text.splitlines():
            m = pattern.match(line)
            if not m:
                continue
            entries.append(
                LogEntry(
                    timestamp=self._parse_ts(m.group("ts").replace(":", " ", 1)),
                    source_ip=m.group("ip"),
                    message=f"{m.group('req')} status={m.group('status')}",
                    raw=line,
                    log_type="apache",
                ),
            )
        return entries

    def _parse_iis(self, text: str) -> list[LogEntry]:
        entries: list[LogEntry] = []
        for line in text.splitlines():
            parts = line.split(",")
            if len(parts) < 3:
                continue
            entries.append(
                LogEntry(
                    timestamp=self._parse_ts(parts[0]) if parts[0] else None,
                    source_ip=parts[1],
                    message=",".join(parts[2:]),
                    raw=line,
                    log_type="iis",
                ),
            )
        return entries

    def _parse_generic(self, text: str, log_type: str) -> list[LogEntry]:
        return [LogEntry(message=line, raw=line, log_type=log_type) for line in text.splitlines() if line.strip()]

    @staticmethod
    def _parse_ts(value: str) -> datetime | None:
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%d/%b/%Y:%H:%M:%S %z",
            "%b %d %H:%M:%S",
        ):
            try:
                return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return None
