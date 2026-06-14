"""Integration: UiPath queue items flow through the agent bridge."""

from __future__ import annotations

import asyncio

import pytest

from core.message_bus import MessageBus
from platforms.uipath.agent_bridge import AgentBridge
from platforms.uipath.maestro_orchestrator import MaestroOrchestrator, TUTORIAL_QUEUE_SECURITY_INCIDENTS


@pytest.mark.asyncio
async def test_uipath_queue_triggers_bridge() -> None:
    bus = MessageBus(max_queue_size=50, message_ttl_seconds=30)
    mock_maestro = MaestroOrchestrator(
        "https://mock.uipath.local",
        tenant_name="tenant",
        organization_name="org",
        mock=True,
    )
    bridge = AgentBridge(mock_maestro, bus, poll_interval_seconds=0.05)
    await bridge.start_sync()
    qid = await mock_maestro.create_queue_item(
        TUTORIAL_QUEUE_SECURITY_INCIDENTS,
        {"title": "Queue-driven case", "description": "UiPath→TUTORIAL", "severity": "high"},
        priority="High",
    )
    assert qid
    await asyncio.sleep(0.15)
    items = await mock_maestro.get_queue_items(TUTORIAL_QUEUE_SECURITY_INCIDENTS)
    assert len(items) >= 1
    await bridge.stop_sync()
