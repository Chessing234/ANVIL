"""Pluggable analysis strategies for defense investigations."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from agents.defense.tools.ioc_matcher import IOCMatcher
from agents.defense.tools.log_analyzer import LogAnalyzer
from agents.defense.tools.memory_analyzer import MemoryAnalyzer
from agents.defense.tools.network_analyzer import NetworkAnalyzer
from shared.models import Evidence, Incident


class AnalysisStrategy(ABC):
    """Strategy interface executed against incident evidence."""

    strategy_id: str = "base"

    @abstractmethod
    async def run(self, incident: Incident, evidence: list[Evidence], overrides: dict[str, Any]) -> dict[str, Any]:
        """Execute analysis and return structured findings."""

    def _evidence_paths(self, evidence: list[Evidence], types: set[str]) -> list[Evidence]:
        return [e for e in evidence if e.type in types]


class MemoryAnalysisStrategy(AnalysisStrategy):
    """Volatility-oriented memory inspection."""

    strategy_id = "memory_volatility"

    def __init__(self, analyzer: MemoryAnalyzer | None = None) -> None:
        self._default_analyzer = analyzer

    async def run(self, incident: Incident, evidence: list[Evidence], overrides: dict[str, Any]) -> dict[str, Any]:
        _ = incident
        targets = self._evidence_paths(evidence, {"memory_dump"})
        if not targets:
            return {"strategy": self.strategy_id, "skipped": True, "reason": "no_memory_dump"}
        timeout = float(overrides.get("volatility_timeout", 300.0))
        analyzer = self._default_analyzer or MemoryAnalyzer(volatility_timeout_seconds=timeout)
        reports = []
        for ev in targets:
            rep = await analyzer.analyze(ev.file_path)
            meta = {
                "plugins": rep.plugins_run,
                "anomaly_scores": rep.anomaly_scores,
                "injection_hints": len(rep.injections),
            }
            reports.append({"evidence_id": str(ev.id), "report": rep.model_dump(), "correlation_meta": meta})
        return {"strategy": self.strategy_id, "reports": reports}


class NetworkAnalysisStrategy(AnalysisStrategy):
    """PCAP and traffic heuristics."""

    strategy_id = "network_pcap"

    def __init__(self, analyzer: NetworkAnalyzer | None = None) -> None:
        self._default_analyzer = analyzer

    async def run(self, incident: Incident, evidence: list[Evidence], overrides: dict[str, Any]) -> dict[str, Any]:
        _ = incident
        targets = self._evidence_paths(evidence, {"network_capture"})
        if not targets:
            return {"strategy": self.strategy_id, "skipped": True, "reason": "no_pcap"}
        timeout = float(overrides.get("tshark_timeout", 300.0))
        analyzer = self._default_analyzer or NetworkAnalyzer(tshark_timeout_seconds=timeout)
        out: list[dict[str, Any]] = []
        for ev in targets:
            res = await analyzer.analyze_pcap(ev.file_path)
            beacon_strict = bool(overrides.get("strict_beaconing", False))
            beacons = res.beaconing
            if beacon_strict:
                beacons = [b for b in beacons if float(b.get("score", 0)) >= 0.65]
            out.append(
                {
                    "evidence_id": str(ev.id),
                    "result": res.model_dump(),
                    "correlation_meta": {
                        "beaconing": beacons,
                        "dns_tunneling": res.dns_tunneling,
                        "large_transfers": res.large_transfers,
                    },
                },
            )
        return {"strategy": self.strategy_id, "results": out}


class LogCorrelationStrategy(AnalysisStrategy):
    """Log parsing and multi-source correlation."""

    strategy_id = "log_correlation"

    def __init__(self, analyzer: LogAnalyzer | None = None) -> None:
        self._analyzer = analyzer or LogAnalyzer()

    async def run(self, incident: Incident, evidence: list[Evidence], overrides: dict[str, Any]) -> dict[str, Any]:
        _ = incident, overrides
        targets = self._evidence_paths(evidence, {"log_file"})
        if not targets:
            return {"strategy": self.strategy_id, "skipped": True, "reason": "no_logs"}
        aggregated: list[dict[str, Any]] = []
        for ev in targets:
            log_type = str(ev.metadata.get("log_format", "generic"))
            entries = await self._analyzer.parse_logs(ev.file_path, log_type)
            correlations = await self._analyzer.correlate(entries)
            anomalies = await self._analyzer.detect_anomalies(entries)
            aggregated.append(
                {
                    "evidence_id": str(ev.id),
                    "entry_count": len(entries),
                    "correlations": [c.model_dump() for c in correlations],
                    "anomalies": [a.model_dump() for a in anomalies],
                },
            )
        return {"strategy": self.strategy_id, "aggregated": aggregated}


class IOCMatchingStrategy(AnalysisStrategy):
    """IOC and threat-intel style enrichment."""

    strategy_id = "ioc_matching"

    def __init__(self, matcher: IOCMatcher | None = None) -> None:
        self._matcher = matcher

    async def run(self, incident: Incident, evidence: list[Evidence], overrides: dict[str, Any]) -> dict[str, Any]:
        extra = overrides.get("extra_ioc_feed_paths") or []
        feeds = [Path(p) for p in extra if Path(p).is_file()]
        matcher = self._matcher or IOCMatcher(extra_feeds=feeds)
        matches: list[dict[str, Any]] = []
        for ev in evidence:
            path = Path(ev.file_path)
            if path.is_file():
                for m in await matcher.check_file(str(path)):
                    matches.append({"evidence_id": str(ev.id), "match": m.model_dump()})
            hx = ev.metadata.get("file_sha256") or ev.hash_sha256
            if isinstance(hx, str) and len(hx) == 64:
                for m in await matcher.check_hash(hx):
                    matches.append({"evidence_id": str(ev.id), "match": m.model_dump()})
        if incident.source_ip:
            for m in await matcher.check_ip(incident.source_ip):
                matches.append({"evidence_id": "incident_source_ip", "match": m.model_dump()})
        return {"strategy": self.strategy_id, "matches": matches}


class FileSystemAnalysisStrategy(AnalysisStrategy):
    """Lightweight disk image / folder inspection."""

    strategy_id = "filesystem_disk"

    async def run(self, incident: Incident, evidence: list[Evidence], overrides: dict[str, Any]) -> dict[str, Any]:
        _ = incident
        targets = self._evidence_paths(evidence, {"disk_image"})
        if not targets:
            return {"strategy": self.strategy_id, "skipped": True, "reason": "no_disk_image"}
        findings: list[dict[str, Any]] = []
        max_depth = int(overrides.get("fs_max_depth", 3))
        for ev in targets:
            root = Path(ev.file_path)
            suspicious: list[str] = []
            if root.is_dir():
                for p in root.rglob("*"):
                    if len(p.relative_to(root).parts) > max_depth:
                        continue
                    if p.suffix.lower() in {".ps1", ".exe", ".dll", ".bat"}:
                        suspicious.append(str(p))
            elif root.is_file():
                text = root.read_text(errors="ignore")[:4000]
                if "rdp" in text.lower():
                    suspicious.append("rdp_artifact_in_file")
            findings.append({"evidence_id": str(ev.id), "suspicious_paths": suspicious[:50]})
        return {"strategy": self.strategy_id, "findings": findings}


class StrategySelector:
    """Select and merge analysis strategies for an incident."""

    def __init__(
        self,
        *,
        memory: MemoryAnalysisStrategy | None = None,
        network: NetworkAnalysisStrategy | None = None,
        logs: LogCorrelationStrategy | None = None,
        ioc: IOCMatchingStrategy | None = None,
        filesystem: FileSystemAnalysisStrategy | None = None,
    ) -> None:
        self._memory = memory or MemoryAnalysisStrategy()
        self._network = network or NetworkAnalysisStrategy()
        self._logs = logs or LogCorrelationStrategy()
        self._ioc = ioc or IOCMatchingStrategy()
        self._fs = filesystem or FileSystemAnalysisStrategy()

    def select(self, incident: Incident, evidence: list[Evidence]) -> list[AnalysisStrategy]:
        """Pick strategies based on available artifact types."""

        _ = incident
        types = {e.type for e in evidence}
        chosen: list[AnalysisStrategy] = []
        if "memory_dump" in types:
            chosen.append(self._memory)
        if "network_capture" in types:
            chosen.append(self._network)
        if "log_file" in types:
            chosen.append(self._logs)
        if types & {"memory_dump", "network_capture", "log_file", "disk_image"}:
            chosen.append(self._ioc)
        if "disk_image" in types:
            chosen.append(self._fs)
        if not chosen:
            chosen.append(self._ioc)
        return chosen

    async def run_parallel(
        self,
        incident: Incident,
        evidence: list[Evidence],
        overrides: dict[str, Any],
    ) -> dict[str, Any]:
        """Run all selected strategies concurrently."""

        strategies = self.select(incident, evidence)
        results = await asyncio.gather(*(s.run(incident, evidence, overrides) for s in strategies))
        return {"strategies": [r.get("strategy") for r in results], "outputs": results}
