"""Splunk Dashboard (Simple XML) and JSON export for Security + Observability tracks."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from typing import Any

from pydantic import BaseModel, Field


class DashboardDefinition(BaseModel):
    """Dual-format dashboard bundle."""

    model_config = {"extra": "forbid"}

    label: str = Field(min_length=1)
    description: str = ""
    xml: str = Field(min_length=10)
    json_spec: dict[str, Any] = Field(default_factory=dict)


def _panel_xml(title: str, query: str, chart: str = "line") -> str:
    return f"""
  <row>
    <panel>
      <title>{title}</title>
      <chart>
        <title>{title}</title>
        <search>
          <query>{query}</query>
          <earliest>-24h</earliest>
          <latest>now</latest>
        </search>
        <option name="charting.chart">{chart}</option>
      </chart>
    </panel>
  </row>"""


def _wrap_dashboard(label: str, rows: str) -> str:
    return (
        f'<?xml version="1.0" encoding="utf-8"?>\n<dashboard version="1.1">\n'
        f"  <label>{label}</label>\n"
        f"  <description>Project TUTORIAL — {label}</description>\n"
        f"{rows}\n</dashboard>"
    )


def _validate_simple_xml(xml: str) -> None:
    ET.fromstring(xml)


class DashboardExporter:
    """Build Security, Education, and combined dashboards."""

    async def export_security_dashboard(self) -> DashboardDefinition:
        rows = "".join(
            [
                _panel_xml(
                    "Incident volume over time",
                    "index=security OR index=main | timechart span=1h count by sourcetype",
                ),
                _panel_xml(
                    "Detection rule effectiveness",
                    "index=security source=threat_detector | stats avg(confidence) as tp_proxy by rule_name",
                ),
                _panel_xml(
                    "Mean time to detect (proxy)",
                    "index=security | timechart span=1h avg(mttd_seconds)",
                    chart="area",
                ),
                _panel_xml(
                    "Active threats by severity",
                    "index=security | stats count by severity",
                    chart="pie",
                ),
                _panel_xml(
                    "Self-correction frequency",
                    "index=main source=sift | timechart span=1h sum(self_corrections)",
                ),
            ],
        )
        xml = _wrap_dashboard("Security Operations", rows)
        _validate_simple_xml(xml)
        spec = {
            "track": "security",
            "panels": [
                {"title": "Incident volume over time", "type": "line"},
                {"title": "Detection effectiveness", "type": "line"},
                {"title": "MTTD", "type": "area"},
                {"title": "Threats by severity", "type": "pie"},
                {"title": "Self-correction frequency", "type": "line"},
            ],
        }
        return DashboardDefinition(
            label="Security Operations",
            description="Security track — detection, response, and tuning telemetry.",
            xml=xml,
            json_spec=spec,
        )

    async def export_education_dashboard(self) -> DashboardDefinition:
        rows = "".join(
            [
                _panel_xml("Active students", "index=education | stats dc(student_id) as active"),
                _panel_xml(
                    "Lessons completed per day",
                    "index=education | timechart span=1d sum(lessons_completed)",
                ),
                _panel_xml(
                    "Concept mastery heatmap (proxy)",
                    "index=education | stats avg(mastery_score) by concept",
                    chart="column",
                ),
                _panel_xml(
                    "Knowledge graph growth",
                    "index=education | timechart span=1d sum(nodes_added)",
                ),
                _panel_xml(
                    "Student engagement metrics",
                    "index=education | stats avg(session_minutes) by cohort",
                ),
            ],
        )
        xml = _wrap_dashboard("Education Metrics", rows)
        _validate_simple_xml(xml)
        spec = {
            "track": "observability_education",
            "panels": [
                {"title": "Active students", "type": "single"},
                {"title": "Lessons per day", "type": "line"},
                {"title": "Mastery", "type": "column"},
                {"title": "Knowledge graph", "type": "line"},
                {"title": "Engagement", "type": "line"},
            ],
        }
        return DashboardDefinition(
            label="Education Metrics",
            description="Observability track — learning analytics and knowledge flywheel.",
            xml=xml,
            json_spec=spec,
        )

    async def export_combined_dashboard(self) -> DashboardDefinition:
        sec = await self.export_security_dashboard()
        edu = await self.export_education_dashboard()
        combined_label = "Security + Education Overview"
        rows = (
            '<row><panel><title>Security summary</title><html>'
            f"<div><![CDATA[{json.dumps(sec.json_spec)}]]></div>"
            "</html></panel></row>"
            '<row><panel><title>Education summary</title><html>'
            f"<div><![CDATA[{json.dumps(edu.json_spec)}]]></div>"
            "</html></panel></row>"
        )
        xml = _wrap_dashboard(combined_label, rows)
        _validate_simple_xml(xml)
        spec = {"track": "combined", "security": sec.json_spec, "education": edu.json_spec}
        return DashboardDefinition(
            label=combined_label,
            description="Joint submission — bridges SOC KPIs with learning science metrics.",
            xml=xml,
            json_spec=spec,
        )

    def export_json_only(self, definition: DashboardDefinition) -> bytes:
        """Serialize JSON spec for external UI hosts."""

        return json.dumps(definition.json_spec, indent=2).encode("utf-8")
