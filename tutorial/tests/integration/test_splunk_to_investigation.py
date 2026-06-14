"""Integration: Splunk-style detection publishes incident-shaped traffic to the bus."""

from __future__ import annotations

import asyncio

import pytest

from config.constants import EventType, MessageBusTopics
from core.message_bus import MessageBus
from platforms.splunk.spl_client import AsyncSplunkClient
from platforms.splunk.threat_detector import ThreatDetector


@pytest.mark.asyncio
async def test_splunk_detection_emits_incident_event() -> None:
    bus = MessageBus(max_queue_size=50, message_ttl_seconds=30)
    await bus.start()
    seen: list[dict] = []

    async def on_msg(m) -> None:
        seen.append(m.payload)

    sid = bus.subscribe(MessageBusTopics.INCIDENTS, on_msg)
    mock_client = AsyncSplunkClient("https://mock:8089", auth_token="tok", mock=True)
    det = ThreatDetector(mock_client, message_bus=bus)
    findings = await det.analyze_traffic(index="main", timerange="-1h")
    assert findings
    await asyncio.sleep(0.05)
    assert any(p.get("event") == EventType.INCIDENT_DETECTED.value for p in seen)
    bus.unsubscribe(sid)
    await bus.stop()
