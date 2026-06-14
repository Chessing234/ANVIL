"""Tests for Splunk MCP, SPL builder, threat detection, and dashboards."""

from __future__ import annotations

import asyncio
import xml.etree.ElementTree as ET

import pytest

from config.constants import EventType, MessageBusTopics
from core.message_bus import MessageBus
from platforms.splunk.alert_manager import AlertManager
from platforms.splunk.dashboard_exporter import DashboardExporter
from platforms.splunk.mcp_server import mcp as splunk_mcp
from platforms.splunk.query_builder import SPLQueryBuilder, SplunkContext, spl_syntax_quick_check
from platforms.splunk.spl_client import AsyncSplunkClient, spl_validate_spl
from platforms.splunk.threat_detector import ThreatDetector


@pytest.fixture
def mock_splunk() -> AsyncSplunkClient:
    return AsyncSplunkClient("https://mock:8089", auth_token="test-token", mock=True)


def test_mcp_tools_registered() -> None:
    tools = asyncio.run(splunk_mcp.list_tools())
    names = {t.name for t in tools}
    assert "spl_search" in names
    assert "spl_list_alerts" in names
    assert "spl_generate_spl" in names
    assert "spl_export_security_dashboard" in names


@pytest.mark.asyncio
async def test_spl_search_validation_and_execution(mock_splunk: AsyncSplunkClient) -> None:
    ok, issues = spl_validate_spl("delete index=*")
    assert not ok
    res = await mock_splunk.search("index=security action=failure", earliest="-1h", max_results=10)
    assert res.row_count >= 1


@pytest.mark.asyncio
async def test_spl_query_builder_failed_login() -> None:
    builder = SPLQueryBuilder(SplunkContext(security_index="security"))
    q = await builder.generate_spl("Show me failed login attempts from the last 24 hours")
    assert "index=security" in q.spl
    assert "failure" in q.spl.lower() or "auth" in q.spl.lower()
    assert spl_syntax_quick_check(q.spl)
    expl = builder.explain_query(q.spl)
    assert "Initial dataset" in expl


@pytest.mark.asyncio
async def test_threat_detection_and_bus(mock_splunk: AsyncSplunkClient) -> None:
    bus = MessageBus()
    await bus.start()
    seen: list[dict] = []

    async def on_msg(m) -> None:
        seen.append(m.payload)

    sid = bus.subscribe(MessageBusTopics.INCIDENTS, on_msg)
    det = ThreatDetector(mock_splunk, message_bus=bus)
    findings = await det.analyze_traffic(index="main", timerange="-1h")
    assert isinstance(findings, list)
    assert len(findings) >= 1
    assert findings[0].confidence > 0.4
    await asyncio.sleep(0.05)
    assert any(EventType.INCIDENT_DETECTED.value == p.get("event") for p in seen)
    bus.unsubscribe(sid)
    await bus.stop()


@pytest.mark.asyncio
async def test_alert_manager_create(mock_splunk: AsyncSplunkClient) -> None:
    mgr = AlertManager(mock_splunk, suppression_window_seconds=1.0)
    aid = await mgr.create_detection_alert(
        "unit_brute",
        "test",
        "index=security sourcetype=auth action=failure | stats count by src_ip",
        threshold=3,
    )
    assert aid.startswith("alert:") or aid.startswith("saved:")
    active = await mgr.list_active_alerts()
    assert isinstance(active, list)


@pytest.mark.asyncio
async def test_dashboard_xml_valid() -> None:
    exp = DashboardExporter()
    sec = await exp.export_security_dashboard()
    assert "<dashboard" in sec.xml
    ET.fromstring(sec.xml)
    edu = await exp.export_education_dashboard()
    ET.fromstring(edu.xml)
    combo = await exp.export_combined_dashboard()
    ET.fromstring(combo.xml)
    assert combo.json_spec.get("track") == "combined"
