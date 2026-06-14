"""High-level async facades over MCP tools with validation and typed parsing."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import structlog

from integrations.connection_manager import ConnectionManager
from integrations.errors import MCPToolExecutionError
from integrations.mcp_types import (
    CodeAnalysisResult,
    ContainmentResult,
    DNSResult,
    EventCorrelation,
    LogEntry,
    MemoryAnalysisResult,
    NetworkAnalysisResult,
    ThreatClassification,
    WHOISResult,
    YaraMatch,
)

logger = structlog.get_logger(__name__)


def _require_file(path: str) -> Path:
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        raise ValueError(f"not a file: {path}")
    return p


class ForensicsTools:
    """Volatility / hashing / YARA style operations."""

    def __init__(
        self,
        manager: ConnectionManager,
        *,
        security_server: str = "security",
        sift_server: str = "sift",
    ) -> None:
        self._manager = manager
        self._security = security_server
        self._sift = sift_server

    async def analyze_memory(self, dump_path: str) -> MemoryAnalysisResult:
        """Prefer SIFT-branded analysis when available, otherwise fall back to security."""

        _require_file(dump_path)
        started = time.perf_counter()
        try:
            data = await self._manager.call_tool(self._sift, "sift_analyze_memory", {"dump_path": dump_path})
        except (KeyError, RuntimeError):
            data = await self._manager.call_tool(self._security, "analyze_memory", {"dump_path": dump_path})
        if data.get("ok") is False:
            raise MCPToolExecutionError(str(data.get("error", "memory_analysis_failed")), details=data)
        result = MemoryAnalysisResult.model_validate(data)
        logger.info("forensics_analyze_memory_ms", ms=round((time.perf_counter() - started) * 1000, 3))
        return result

    async def extract_strings(self, file_path: str, min_length: int = 4) -> list[str]:
        _require_file(file_path)
        started = time.perf_counter()
        data = await self._manager.call_tool(
            self._security,
            "strings_analysis",
            {"file_path": file_path, "min_length": min_length},
        )
        logger.info("forensics_strings_ms", ms=round((time.perf_counter() - started) * 1000, 3))
        if not data.get("ok", True):
            raise MCPToolExecutionError(data.get("error", "strings_failed"), details=data)
        return list(data.get("strings", []))

    async def compute_hashes(self, file_path: str) -> dict[str, str]:
        _require_file(file_path)
        started = time.perf_counter()
        data = await self._manager.call_tool(self._security, "hash_file", {"file_path": file_path})
        logger.info("forensics_hashes_ms", ms=round((time.perf_counter() - started) * 1000, 3))
        if not data.get("ok", True):
            raise MCPToolExecutionError(data.get("error", "hash_failed"), details=data)
        return {
            "md5": str(data["md5"]),
            "sha1": str(data["sha1"]),
            "sha256": str(data["sha256"]),
        }

    async def yara_scan(self, file_path: str, rules_path: str | None = None) -> list[YaraMatch]:
        _require_file(file_path)
        if rules_path is not None:
            _require_file(rules_path)
        started = time.perf_counter()
        payload: dict[str, Any] = {"file_path": file_path, "rules_path": rules_path}
        data = await self._manager.call_tool(self._security, "run_yara", payload)
        logger.info("forensics_yara_ms", ms=round((time.perf_counter() - started) * 1000, 3))
        if not data.get("ok", True):
            raise MCPToolExecutionError(str(data.get("error", "yara_failed")), details=data)
        matches_raw = data.get("matches", [])
        return [YaraMatch.model_validate(m) for m in matches_raw]


class NetworkTools:
    """PCAP and simple network intelligence."""

    def __init__(self, manager: ConnectionManager, *, security_server: str = "security") -> None:
        self._manager = manager
        self._security = security_server

    async def analyze_pcap(self, pcap_path: str) -> NetworkAnalysisResult:
        _require_file(pcap_path)
        started = time.perf_counter()
        data = await self._manager.call_tool(self._security, "analyze_pcap", {"pcap_path": pcap_path})
        logger.info("network_pcap_ms", ms=round((time.perf_counter() - started) * 1000, 3))
        return NetworkAnalysisResult.model_validate(data)

    async def dns_lookup(self, domain: str) -> DNSResult:
        if not domain.strip():
            raise ValueError("domain must be non-empty")
        started = time.perf_counter()
        data = await self._manager.call_tool(self._security, "dns_lookup", {"domain": domain.strip()})
        logger.info("network_dns_ms", ms=round((time.perf_counter() - started) * 1000, 3))
        return DNSResult.model_validate(data)

    async def whois_lookup(self, ip: str) -> WHOISResult:
        started = time.perf_counter()
        data = await self._manager.call_tool(self._security, "whois_lookup", {"ip": ip.strip()})
        logger.info("network_whois_ms", ms=round((time.perf_counter() - started) * 1000, 3))
        return WHOISResult.model_validate(data)


class LogTools:
    """Log parsing and correlation."""

    def __init__(self, manager: ConnectionManager, *, security_server: str = "security") -> None:
        self._manager = manager
        self._security = security_server

    async def parse_logs(self, log_path: str, log_type: str) -> list[LogEntry]:
        _require_file(log_path)
        started = time.perf_counter()
        data = await self._manager.call_tool(
            self._security,
            "parse_logs",
            {"log_path": log_path, "log_type": log_type},
        )
        logger.info("logs_parse_ms", ms=round((time.perf_counter() - started) * 1000, 3))
        entries = [LogEntry.model_validate(e) for e in data.get("entries", [])]
        return entries

    async def search_logs(self, query: str, source: str, time_range: tuple[str, str]) -> list[LogEntry]:
        _require_file(source)
        started = time.perf_counter()
        data = await self._manager.call_tool(
            self._security,
            "search_logs",
            {"query": query, "source": source, "time_range": list(time_range)},
        )
        logger.info("logs_search_ms", ms=round((time.perf_counter() - started) * 1000, 3))
        return [LogEntry.model_validate(e) for e in data.get("entries", [])]

    async def correlate_events(self, events: list[LogEntry]) -> list[EventCorrelation]:
        started = time.perf_counter()
        payload = {"events": [e.model_dump() for e in events]}
        data = await self._manager.call_tool(self._security, "correlate_events", payload)
        logger.info("logs_correlate_ms", ms=round((time.perf_counter() - started) * 1000, 3))
        return [EventCorrelation.model_validate(c) for c in data.get("correlations", [])]


class ContainmentTools:
    """Containment playbooks exposed as MCP tools."""

    def __init__(self, manager: ConnectionManager, *, security_server: str = "security") -> None:
        self._manager = manager
        self._security = security_server

    async def isolate_host(self, hostname: str) -> ContainmentResult:
        if not hostname.strip():
            raise ValueError("hostname required")
        started = time.perf_counter()
        data = await self._manager.call_tool(self._security, "isolate_host", {"hostname": hostname})
        logger.info("contain_isolate_ms", ms=round((time.perf_counter() - started) * 1000, 3))
        return ContainmentResult.model_validate(data)

    async def block_ip(self, ip: str, duration_minutes: int | None = None) -> ContainmentResult:
        started = time.perf_counter()
        data = await self._manager.call_tool(
            self._security,
            "block_ip",
            {"ip": ip, "duration_minutes": duration_minutes},
        )
        logger.info("contain_block_ms", ms=round((time.perf_counter() - started) * 1000, 3))
        return ContainmentResult.model_validate(data)

    async def kill_process(self, pid: int, hostname: str) -> ContainmentResult:
        if pid <= 0:
            raise ValueError("pid must be positive")
        started = time.perf_counter()
        data = await self._manager.call_tool(
            self._security,
            "kill_process",
            {"pid": pid, "hostname": hostname},
        )
        logger.info("contain_kill_ms", ms=round((time.perf_counter() - started) * 1000, 3))
        return ContainmentResult.model_validate(data)


class LLMTools:
    """LLM helpers routed through the LLM MCP server."""

    def __init__(self, manager: ConnectionManager, *, llm_server: str = "llm") -> None:
        self._manager = manager
        self._llm = llm_server

    async def generate_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.1,
    ) -> str:
        if not prompt.strip():
            raise ValueError("prompt required")
        started = time.perf_counter()
        data = await self._manager.call_tool(
            self._llm,
            "complete",
            {
                "prompt": prompt,
                "system_prompt": system_prompt,
                "temperature": temperature,
            },
        )
        logger.info("llm_generate_ms", ms=round((time.perf_counter() - started) * 1000, 3))
        if not data.get("ok", True):
            raise MCPToolExecutionError("completion_failed", details=data)
        return str(data.get("text", ""))

    async def analyze_code(self, code: str, language: str) -> CodeAnalysisResult:
        if not code.strip():
            raise ValueError("code required")
        started = time.perf_counter()
        sys_prompt = f"You are a static analysis assistant for {language}."
        text = await self.generate_text(code[:8000], system_prompt=sys_prompt, temperature=0.0)
        issues = [{"severity": "info", "detail": text[:2000]}]
        logger.info("llm_code_ms", ms=round((time.perf_counter() - started) * 1000, 3))
        return CodeAnalysisResult(language=language, issues=issues, summary=text[:500])

    async def classify_threat(self, description: str) -> ThreatClassification:
        if not description.strip():
            raise ValueError("description required")
        started = time.perf_counter()
        labels = ["benign", "suspicious", "malicious"]
        data = await self._manager.call_tool(
            self._llm,
            "classify",
            {"text": description, "labels": labels},
        )
        logger.info("llm_classify_ms", ms=round((time.perf_counter() - started) * 1000, 3))
        label = str(data.get("label", "unknown"))
        scores = {str(k): float(v) for k, v in dict(data.get("scores", {})).items()}
        confidence = float(max(scores.values()) if scores else 0.5)
        return ThreatClassification(label=label, confidence=confidence, rationale=json.dumps(scores)[:500])
