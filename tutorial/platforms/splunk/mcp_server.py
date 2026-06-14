"""stdio MCP server exposing Splunk REST operations for Agentic Ops."""

from __future__ import annotations

import os
import re
from typing import Any

from mcp.server.fastmcp import FastMCP

from platforms.splunk.dashboard_exporter import DashboardExporter
from platforms.splunk.query_builder import SPLQueryBuilder, SplunkContext
from platforms.splunk.spl_client import (
    AlertConfig,
    AsyncSplunkClient,
    FieldExtraction,
    ThreatIntelResult,
    spl_validate_spl,
)

mcp = FastMCP("tutorial-splunk-server", warn_on_duplicate_tools=False)

_client: AsyncSplunkClient | None = None


def _splunk_client() -> AsyncSplunkClient:
    global _client
    if _client is None:
        _client = AsyncSplunkClient.from_env()
    return _client


@mcp.tool()
async def spl_search(
    query: str,
    earliest: str = "-24h",
    latest: str = "now",
    max_results: int = 100,
) -> dict[str, Any]:
    """Execute SPL search, return results as JSON."""

    ok, issues = spl_validate_spl(query)
    if not ok:
        return {"ok": False, "issues": issues, "result": None}
    res = await _splunk_client().search(query, earliest=earliest, latest=latest, max_results=max_results)
    return {"ok": True, "result": res.model_dump(mode="json")}


@mcp.tool()
async def spl_get_alert(alert_name: str) -> dict[str, Any]:
    """Get saved search / alert configuration."""

    cfg = await _splunk_client().get_saved_search_config(alert_name)
    return {"ok": True, "alert": cfg.model_dump(mode="json")}


@mcp.tool()
async def spl_list_alerts() -> dict[str, Any]:
    """List configured Splunk saved searches suitable for alerting."""

    rows = await _splunk_client().list_saved_alerts()
    return {"ok": True, "alerts": [r.model_dump(mode="json") for r in rows]}


@mcp.tool()
async def spl_create_alert(
    name: str,
    search: str,
    condition: str,
    actions: list[str],
) -> dict[str, Any]:
    """Create a new detection alert (saved search + alert actions)."""

    ok, issues = spl_validate_spl(search)
    if not ok:
        return {"ok": False, "issues": issues, "created": False}
    spl = f"{search.strip()} | where {condition}"
    ok2, issues2 = spl_validate_spl(spl)
    if not ok2:
        return {"ok": False, "issues": issues2, "created": False}
    cfg = AlertConfig(name=name, search=spl, actions=actions or ["logevent"])
    await _splunk_client().create_alert(cfg)
    return {"ok": True, "created": True, "name": name}


@mcp.tool()
async def spl_get_dashboard(dashboard_name: str) -> dict[str, Any]:
    """Fetch dashboard definition from Splunk."""

    dash = await _splunk_client().get_dashboard_definition(dashboard_name)
    return {"ok": True, "dashboard": dash.model_dump(mode="json")}


@mcp.tool()
async def spl_list_indexes() -> dict[str, Any]:
    """List Splunk indexes."""

    rows = await _splunk_client().list_indexes()
    return {"ok": True, "indexes": [r.model_dump(mode="json") for r in rows]}


@mcp.tool()
async def spl_get_field_stats(index: str, field: str, timerange: str) -> dict[str, Any]:
    """Return distinct/null stats for a field."""

    stats = await _splunk_client().field_stats(index, field, timerange)
    return {"ok": True, "stats": stats.model_dump(mode="json")}


@mcp.tool()
async def spl_extract_fields(sourcetype: str, sample_event: str) -> dict[str, Any]:
    """Infer simple EXTRACT-regex style field mappings from a sample event."""

    pairs = re.findall(r"(\w+)=([^\s]+)", sample_event)
    out: list[FieldExtraction] = []
    for name, _val in pairs[:20]:
        out.append(
            FieldExtraction(
                name=name,
                pattern=rf"(?P<{name}>[^\s]+)",
                sourcetype=sourcetype,
            ),
        )
    if not out and sample_event:
        out.append(
            FieldExtraction(
                name="raw_message",
                pattern=r"(?P<raw_message>.+)",
                sourcetype=sourcetype,
            ),
        )
    return {"ok": True, "extractions": [e.model_dump(mode="json") for e in out]}


@mcp.tool()
async def spl_get_threat_intel(ioc_type: str, ioc_value: str) -> dict[str, Any]:
    """Check an IOC against a lightweight embedded intel policy."""

    verdict = "unknown"
    confidence = 0.2
    low = ioc_value.lower()
    if ioc_type.lower() == "ip" and low.startswith("198.51.100."):
        verdict = "malicious"
        confidence = 0.92
    elif ioc_type.lower() == "domain" and "evil" in low:
        verdict = "malicious"
        confidence = 0.88
    elif ioc_type.lower() == "hash" and len(ioc_value) == 64:
        verdict = "suspicious"
        confidence = 0.55
    res = ThreatIntelResult(
        ioc_type=ioc_type,
        ioc_value=ioc_value,
        verdict=verdict,
        sources=["tutorial_embedded_intel"],
        confidence=confidence,
    )
    return {"ok": True, "intel": res.model_dump(mode="json")}


@mcp.tool()
async def spl_health() -> dict[str, Any]:
    """Splunk connectivity probe."""

    h = await _splunk_client().health_check()
    return {"ok": h.ok, "health": h.model_dump(mode="json")}


@mcp.tool()
async def spl_generate_spl(natural_language: str) -> dict[str, Any]:
    """Generate SPL from natural language using templates / optional LLM."""

    builder = SPLQueryBuilder(SplunkContext())
    q = await builder.generate_spl(natural_language)
    return {"ok": True, "query": q.model_dump(mode="json")}


@mcp.tool()
async def spl_export_security_dashboard() -> dict[str, Any]:
    """Export Security Operations dashboard (XML + JSON spec)."""

    exp = DashboardExporter()
    d = await exp.export_security_dashboard()
    return {"ok": True, "dashboard": d.model_dump(mode="json")}


@mcp.tool()
async def spl_export_education_dashboard() -> dict[str, Any]:
    """Export Education / observability dashboard."""

    exp = DashboardExporter()
    d = await exp.export_education_dashboard()
    return {"ok": True, "dashboard": d.model_dump(mode="json")}


@mcp.tool()
async def spl_export_combined_dashboard() -> dict[str, Any]:
    """Export combined Security + Education dashboard for dual-track submission."""

    exp = DashboardExporter()
    d = await exp.export_combined_dashboard()
    return {"ok": True, "dashboard": d.model_dump(mode="json")}


def main() -> None:
    _ = os.environ.get("SPLUNK_HOST", "https://localhost:8089")
    mcp.run()


if __name__ == "__main__":
    main()
