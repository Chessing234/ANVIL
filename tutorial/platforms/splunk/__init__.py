"""Splunk Enterprise integration for Agentic Ops (security + observability)."""

from platforms.splunk.alert_manager import AlertManager
from platforms.splunk.dashboard_exporter import DashboardDefinition, DashboardExporter
from platforms.splunk.mcp_server import mcp as splunk_mcp
from platforms.splunk.query_builder import SPLQuery, SPLQueryBuilder, SplunkContext
from platforms.splunk.spl_client import (
    AlertConfig,
    AlertEvent,
    AlertSummary,
    AsyncSplunkClient,
    Dashboard,
    DashboardSummary,
    FieldExtraction,
    FieldStats,
    IndexInfo,
    IndexStats,
    SearchResult,
    SplunkHealth,
    ThreatIntelResult,
)
from platforms.splunk.threat_detector import ThreatDetector, ThreatFinding

__all__ = [
    "AlertConfig",
    "AlertEvent",
    "AlertManager",
    "AlertSummary",
    "AsyncSplunkClient",
    "Dashboard",
    "DashboardDefinition",
    "DashboardExporter",
    "DashboardSummary",
    "FieldExtraction",
    "FieldStats",
    "IndexInfo",
    "IndexStats",
    "SPLQuery",
    "SPLQueryBuilder",
    "SearchResult",
    "SplunkContext",
    "SplunkHealth",
    "ThreatDetector",
    "ThreatFinding",
    "ThreatIntelResult",
    "splunk_mcp",
]
