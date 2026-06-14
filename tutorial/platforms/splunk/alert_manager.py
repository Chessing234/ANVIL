"""Alert lifecycle helpers with deduplication and incident correlation."""

from __future__ import annotations

import hashlib
import time
import uuid
from collections import defaultdict
from typing import Any

import structlog
from pydantic import BaseModel, Field

from platforms.splunk.spl_client import AlertConfig, AlertEvent, AlertSummary, AsyncSplunkClient, spl_validate_spl

logger = structlog.get_logger(__name__)


class _SuppressionEntry(BaseModel):
    model_config = {"extra": "forbid"}

    fingerprint: str
    last_seen: float = Field(default_factory=time.time)
    count: int = 1


class AlertManager:
    """Create and tune Splunk alerts with fatigue controls."""

    def __init__(self, client: AsyncSplunkClient, *, suppression_window_seconds: float = 600.0) -> None:
        self._client = client
        self._suppression_window = max(60.0, suppression_window_seconds)
        self._suppress: dict[str, _SuppressionEntry] = {}
        self._incidents: dict[str, list[str]] = defaultdict(list)

    @staticmethod
    def _fingerprint(name: str, spl: str) -> str:
        return hashlib.sha256(f"{name}|{spl}".encode()).hexdigest()[:24]

    def _should_suppress(self, fingerprint: str) -> bool:
        now = time.time()
        entry = self._suppress.get(fingerprint)
        if entry and now - entry.last_seen < self._suppression_window:
            entry.count += 1
            entry.last_seen = now
            self._suppress[fingerprint] = entry
            logger.info("splunk_alert_suppressed", fingerprint=fingerprint, count=entry.count)
            return True
        self._suppress[fingerprint] = _SuppressionEntry(fingerprint=fingerprint, last_seen=now, count=1)
        return False

    async def create_detection_alert(
        self,
        name: str,
        description: str,
        spl: str,
        threshold: int,
        action: str = "notify",
    ) -> str:
        """Persist a thresholded detection as a Splunk saved search / alert."""

        ok, issues = spl_validate_spl(spl)
        if not ok:
            raise ValueError(f"invalid_spl: {issues}")
        fp = self._fingerprint(name, spl)
        if self._should_suppress(fp):
            return f"suppressed:{fp}"
        enriched = f"{spl.strip()} | where count > {int(threshold)}"
        cfg = AlertConfig(
            name=name,
            search=enriched,
            description=description,
            actions=[action, "logevent"],
        )
        alert_id = await self._client.create_alert(cfg)
        logger.info("splunk_alert_created", name=name, alert_id=alert_id)
        return alert_id

    async def update_alert(self, alert_id: str, updates: dict[str, Any]) -> bool:
        name = alert_id.split(":", 1)[-1]
        await self._client.update_saved_search(name, updates)
        return True

    async def delete_alert(self, alert_id: str) -> bool:
        return await self._client.delete_alert(alert_id)

    async def list_active_alerts(self) -> list[AlertSummary]:
        rows = await self._client.list_saved_alerts()
        return [r for r in rows if not r.disabled]

    async def get_alert_fired_events(self, alert_id: str, timerange: str) -> list[AlertEvent]:
        _ = timerange
        return await self._client.get_alert_history(alert_id)

    def correlate_alerts_to_incident(self, alert_names: list[str]) -> str:
        """Group related alert names into a synthetic incident identifier."""

        incident_id = str(uuid.uuid4())
        self._incidents[incident_id].extend(alert_names)
        return incident_id
