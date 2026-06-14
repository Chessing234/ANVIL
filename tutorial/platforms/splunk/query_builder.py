"""Natural-language to SPL translation with templates, validation, and optional LLM."""

from __future__ import annotations

import os
import re
from typing import Any

import httpx
import structlog
from pydantic import BaseModel, Field

from platforms.splunk.spl_client import spl_validate_spl

logger = structlog.get_logger(__name__)


class SplunkContext(BaseModel):
    """Deployment context passed into SPL generation."""

    model_config = {"extra": "forbid"}

    default_index: str = "main"
    security_index: str = "security"
    network_index: str = "network"
    windows_index: str = "windows"
    common_sourcetypes: list[str] = Field(
        default_factory=lambda: ["auth", "sysmon", "dns", "firewall", "access_combined"],
    )
    common_fields: list[str] = Field(
        default_factory=lambda: ["src_ip", "dest_ip", "user", "action", "EventCode", "query"],
    )


class SPLQuery(BaseModel):
    """Generated SPL with provenance metadata."""

    model_config = {"extra": "forbid"}

    spl: str = Field(min_length=1)
    explanation: str = ""
    validated: bool = False
    validation_issues: list[str] = Field(default_factory=list)


class QueryTemplateLibrary:
    """Curated SPL templates for security analytics."""

    _TEMPLATES: dict[str, str] = {
        "brute_force": (
            "index={{security_index}} sourcetype=auth action=failure earliest={{earliest}} latest=now "
            "| bin _time span=5m "
            "| stats count by _time, src_ip, user "
            "| where count > {{threshold}}"
        ),
        "lateral_movement": (
            "index={{windows_index}} (EventCode=4624 OR EventCode=4648) earliest={{earliest}} "
            "| stats dc(ComputerName) as hops by user "
            "| where hops > 3"
        ),
        "data_exfiltration": (
            "index={{network_index}} sourcetype=firewall bytes_out > {{min_bytes}} earliest={{earliest}} "
            "| stats sum(bytes_out) as total by src_ip "
            "| where total > {{exfil_threshold}}"
        ),
        "malware_beaconing": (
            "index={{network_index}} sourcetype=dns earliest={{earliest}} "
            "| bin _time span=1h "
            "| stats count by _time, query "
            "| eventstats avg(count) as avg, stdev(count) as stdev by query "
            "| where count > (avg + 3*stdev) AND avg > 0"
        ),
        "privilege_escalation": (
            "index={{windows_index}} (EventCode=4673 OR EventCode=4674 OR EventCode=4648) earliest={{earliest}} "
            "| stats count by user, process_name "
            "| where count > {{threshold}}"
        ),
    }

    def get_template(self, scenario: str) -> str:
        key = scenario.lower().strip().replace(" ", "_")
        if key not in self._TEMPLATES:
            raise KeyError(f"unknown template scenario: {scenario}")
        return self._TEMPLATES[key]

    def fill_template(self, template: str, params: dict[str, Any]) -> str:
        out = template
        for k, v in params.items():
            out = out.replace("{{" + k + "}}", str(v))
        return out


class SPLQueryBuilder:
    """Build SPL from natural language using few-shot + templates, with optional LLM."""

    def __init__(self, context: SplunkContext | None = None) -> None:
        self._ctx = context or SplunkContext()
        self.templates = QueryTemplateLibrary()

    _FEW_SHOT = """You output ONLY a single Splunk SPL search string, no markdown.
Examples:
User: Show me failed login attempts from the last 24 hours
SPL: index=security sourcetype=auth action=failure earliest=-24h latest=now | stats count by src_ip, user | sort -count

User: Find processes that made network connections to suspicious IPs
SPL: index=main sourcetype=sysmon EventCode=3 earliest=-24h latest=now | lookup threat_intel_ip ip as DestinationIp OUTPUT threat_level | where threat_level="high"

User: Show beaconing patterns in DNS queries
SPL: index=network sourcetype=dns earliest=-24h latest=now | bin _time span=1h | stats count by _time, query | eventstats avg(count) as avg, stdev(count) as stdev by query | where count > (avg + 3*stdev)
"""

    async def _llm_generate(self, natural_language: str) -> str:
        api_key = os.environ.get("SPLUNK_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise RuntimeError("no_llm_key")
        base = os.environ.get("SPLUNK_OPENAI_BASE_URL", os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"))
        model = os.environ.get("SPLUNK_OPENAI_MODEL", "gpt-4o-mini")
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model": model,
            "temperature": 0.1,
            "max_tokens": 512,
            "messages": [
                {"role": "system", "content": self._FEW_SHOT},
                {
                    "role": "user",
                    "content": (
                        f"Indexes: main, {self._ctx.security_index}, {self._ctx.network_index}. "
                        f"Sourcetypes: {', '.join(self._ctx.common_sourcetypes)}. "
                        f"Request: {natural_language}"
                    ),
                },
            ],
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(f"{base.rstrip('/')}/chat/completions", headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
            return str(data["choices"][0]["message"]["content"]).strip()

    def _heuristic_spl(self, text: str) -> str:
        low = text.lower()
        sec = self._ctx.security_index
        net = self._ctx.network_index
        _win = self._ctx.windows_index
        if "failed login" in low or ("failure" in low and "login" in low):
            return (
                f"index={sec} sourcetype=auth action=failure earliest=-24h latest=now "
                "| stats count by src_ip, user | sort -count"
            )
        if "sysmon" in low or ("process" in low and "network" in low):
            return (
                "index=main sourcetype=sysmon EventCode=3 earliest=-24h latest=now "
                '| lookup threat_intel_ip ip as DestinationIp OUTPUT threat_level '
                '| where threat_level="high"'
            )
        if "beacon" in low or ("dns" in low and "pattern" in low):
            return (
                f"index={net} sourcetype=dns earliest=-24h latest=now "
                "| bin _time span=1h | stats count by _time, query "
                "| eventstats avg(count) as avg, stdev(count) as stdev by query "
                "| where count > (avg + 3*stdev)"
            )
        if "exfil" in low or "large transfer" in low:
            return (
                f"index={net} sourcetype=firewall bytes_out > 100000000 earliest=-24h latest=now "
                "| stats sum(bytes_out) as total by src_ip | where total > 1000000000"
            )
        if "windows" in low or "eventlog" in low or "4688" in low:
            return (
                f"index={_win} sourcetype=WinEventLog earliest=-24h latest=now "
                "| stats count by EventCode, ComputerName | sort -count"
            )
        return (
            f"index={self._ctx.default_index} earliest=-24h latest=now "
            "| head 100 | fieldsummary | fields field, distinct_count"
        )

    async def generate_spl(self, natural_language: str, context: SplunkContext | None = None) -> SPLQuery:
        """Generate SPL from natural language, preferring LLM when keys are configured."""

        logger.debug("spl_generate_ctx", context_override=context is not None)
        spl_raw = ""
        try:
            spl_raw = await self._llm_generate(natural_language)
        except Exception as exc:
            logger.info("spl_builder_llm_skipped", error=str(exc))
            spl_raw = self._heuristic_spl(natural_language)
        spl = spl_raw.strip().strip("`").splitlines()[0] if spl_raw else ""
        if spl.startswith("spl:"):
            spl = spl[4:].strip()
        ok, issues = spl_validate_spl(spl)
        return SPLQuery(
            spl=spl,
            explanation=self.explain_query(spl),
            validated=ok,
            validation_issues=issues,
        )

    def explain_query(self, spl: str) -> str:
        """Describe each major stage of an SPL pipeline in plain English."""

        parts = [p.strip() for p in spl.split("|")]
        desc: list[str] = []
        for i, p in enumerate(parts):
            if i == 0:
                desc.append(f"Initial dataset: {p}")
            elif p.lower().startswith("stats"):
                desc.append(f"Aggregation: {p}")
            elif p.lower().startswith("where"):
                desc.append(f"Filter: {p}")
            elif p.lower().startswith("lookup"):
                desc.append(f"Enrichment: {p}")
            else:
                desc.append(f"Transform: {p}")
        return " ; ".join(desc) if desc else "Single-stage search."

    def optimize_query(self, spl: str) -> str:
        """Suggest performance-oriented adjustments (conservative heuristics)."""

        suggestions: list[str] = []
        if not re.search(r"\bindex\s*=", spl, re.I):
            suggestions.append(f"Add explicit index (e.g. index={self._ctx.default_index}) to limit scan scope.")
        if "| head" not in spl.lower() and "stats" not in spl.lower():
            suggestions.append("Consider adding | head or stats early after filters to bound rows.")
        if "join" in spl.lower():
            suggestions.append("Replace join with lookup or subsearch if possible for better performance.")
        return " ".join(suggestions) if suggestions else "Query already targets indexes; keep time bounds tight."


def spl_syntax_quick_check(spl: str) -> bool:
    """Return True if SPL passes lightweight structural validation."""

    ok, _ = spl_validate_spl(spl)
    return ok
