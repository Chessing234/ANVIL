"""Orchestrates multi-phase forensic execution on a SIFT host over SSH."""

from __future__ import annotations

import asyncio
import json
import shlex
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog
from pydantic import BaseModel, Field

from platforms.sift.connector import SIFTConnector
from shared.models import Incident

logger = structlog.get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MemoryAnalysisResult(BaseModel):
    """Structured output from Volatility 3 style memory triage."""

    model_config = {"extra": "forbid"}

    dump_path: str
    processes: list[dict[str, Any]] = Field(default_factory=list)
    network_connections: list[dict[str, Any]] = Field(default_factory=list)
    injected_regions: list[dict[str, Any]] = Field(default_factory=list)
    loaded_dlls: list[dict[str, Any]] = Field(default_factory=list)
    raw_plugins: dict[str, str] = Field(default_factory=dict)


class DiskAnalysisResult(BaseModel):
    """Partition and file listing oriented disk triage."""

    model_config = {"extra": "forbid"}

    image_path: str
    partition_layout: str
    file_listing_excerpt: str
    deleted_file_hints: list[str] = Field(default_factory=list)
    timeline_excerpt: str = ""


class TimelineResult(BaseModel):
    """Chronological events from Plaso pipeline."""

    model_config = {"extra": "forbid"}

    disk_image: str
    events: list[dict[str, Any]] = Field(default_factory=list)
    source: str = "plaso"


class NetworkAnalysisResult(BaseModel):
    """Protocol and conversation centric PCAP triage."""

    model_config = {"extra": "forbid"}

    pcap_path: str
    protocol_stats: dict[str, int] = Field(default_factory=dict)
    conversations: list[dict[str, Any]] = Field(default_factory=list)
    suspicious: list[str] = Field(default_factory=list)


class LogAnalysisResult(BaseModel):
    """Normalized log-derived events."""

    model_config = {"extra": "forbid"}

    log_dir: str
    events: list[dict[str, Any]] = Field(default_factory=list)
    anomalies: list[str] = Field(default_factory=list)


class SIFTInvestigationResult(BaseModel):
    """Envelope returned by :meth:`SIFTExecutionEngine.run_investigation`."""

    model_config = {"extra": "forbid"}

    investigation_id: str = Field(min_length=8)
    incident_id: str
    started_at: datetime
    completed_at: datetime
    working_dir: str
    memory: dict[str, MemoryAnalysisResult] = Field(default_factory=dict)
    disk: dict[str, DiskAnalysisResult] = Field(default_factory=dict)
    timelines: dict[str, TimelineResult] = Field(default_factory=dict)
    network: dict[str, NetworkAnalysisResult] = Field(default_factory=dict)
    logs: dict[str, LogAnalysisResult] = Field(default_factory=dict)
    execution_log: list[dict[str, Any]] = Field(default_factory=list)
    tools_used: list[str] = Field(default_factory=list)


class SIFTExecutionEngine:
    """Runs evidence through SIFT tooling remotely with timeouts and parallelism."""

    def __init__(self, connector: SIFTConnector) -> None:
        self._c = connector

    async def _run_with_retry(self, command: str, timeout: float, retries: int = 2) -> dict[str, Any]:
        last: Exception | None = None
        for attempt in range(retries + 1):
            try:
                res = await self._c.execute_command(command, timeout=timeout)
                return {
                    "stdout": res.stdout,
                    "stderr": res.stderr,
                    "exit_code": res.exit_code,
                    "duration_seconds": res.duration_seconds,
                }
            except TimeoutError as exc:
                last = exc
                await asyncio.sleep(0.5 * (attempt + 1))
        raise TimeoutError(str(last)) from last

    async def analyze_memory(self, dump_path: str, *, timeout: float = 300.0) -> MemoryAnalysisResult:
        """Run a focused Volatility bundle against ``dump_path`` on SIFT."""

        plugins = [
            "windows.pslist",
            "windows.pstree",
            "windows.netscan",
            "windows.malfind",
            "windows.dlllist",
            "windows.cmdline",
            "windows.svcscan",
        ]
        raw: dict[str, str] = {}
        for plugin in plugins:
            cmd = f"vol.py -r json -f {shlex.quote(dump_path)} {plugin}"
            out = await self._run_with_retry(cmd, timeout=timeout / max(1, len(plugins) // 2))
            raw[plugin] = out["stdout"]
        merged: dict[str, Any] = {}
        for text in raw.values():
            if text.strip().startswith("{"):
                try:
                    data = json.loads(text)
                    if isinstance(data, dict):
                        merged.update(data)
                except json.JSONDecodeError:
                    continue
        return MemoryAnalysisResult(
            dump_path=dump_path,
            processes=list(merged.get("processes", [])) if isinstance(merged.get("processes"), list) else [],
            network_connections=list(merged.get("network", [])) if isinstance(merged.get("network"), list) else [],
            injected_regions=list(merged.get("injected", [])) if isinstance(merged.get("injected"), list) else [],
            loaded_dlls=list(merged.get("dlls", [])) if isinstance(merged.get("dlls"), list) else [],
            raw_plugins=raw,
        )

    async def analyze_disk(self, image_path: str, *, timeout: float = 400.0) -> DiskAnalysisResult:
        """Run SleuthKit helpers for layout and file listing."""

        mmls = await self._run_with_retry(f"mmls {shlex.quote(image_path)}", timeout=timeout / 3)
        fls = await self._run_with_retry(f"fls -r {shlex.quote(image_path)} | head -n 500", timeout=timeout / 3)
        fsstat = await self._run_with_retry(f"fsstat {shlex.quote(image_path)}", timeout=timeout / 3)
        deleted_hints = [ln for ln in fls["stdout"].splitlines() if "*" in ln][:50]
        return DiskAnalysisResult(
            image_path=image_path,
            partition_layout=mmls["stdout"][:4000],
            file_listing_excerpt=fls["stdout"][:8000],
            deleted_file_hints=deleted_hints,
            timeline_excerpt=fsstat["stdout"][:2000],
        )

    async def generate_timeline(self, disk_image: str, *, timeout: float = 600.0) -> TimelineResult:
        """Execute log2timeline and psort on SIFT."""

        work = f"/cases/timeline_{uuid.uuid4().hex[:8]}"
        await self._c.execute_command(f"mkdir -p {shlex.quote(work)}", timeout=30.0)
        dump = f"{work}/plaso.dump"
        await self._run_with_retry(
            f"log2timeline.py --storage_file {shlex.quote(dump)} {shlex.quote(disk_image)}",
            timeout=timeout * 0.7,
        )
        psort = await self._run_with_retry(
            f"psort.py -o json_line -w {shlex.quote(work + '/events.jsonl')} {shlex.quote(dump)} | head -n 200",
            timeout=timeout * 0.3,
        )
        events: list[dict[str, Any]] = []
        for line in psort["stdout"].splitlines():
            if line.strip().startswith("{"):
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return TimelineResult(disk_image=disk_image, events=events, source="plaso")

    async def analyze_network(self, pcap_path: str, *, timeout: float = 240.0) -> NetworkAnalysisResult:
        """Summarize PCAP via tshark on SIFT."""

        stats = await self._run_with_retry(
            f"tshark -r {shlex.quote(pcap_path)} -q -z io,phs",
            timeout=timeout / 2,
        )
        conv = await self._run_with_retry(
            f"tshark -r {shlex.quote(pcap_path)} -q -z conv,tcp",
            timeout=timeout / 2,
        )
        proto: dict[str, int] = {}
        for line in stats["stdout"].splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[-1].isdigit():
                proto[parts[0]] = int(parts[-1])
        suspicious: list[str] = []
        if "beacon" in conv["stdout"].lower():
            suspicious.append("possible_beaconing")
        return NetworkAnalysisResult(
            pcap_path=pcap_path,
            protocol_stats=proto,
            conversations=[{"summary": conv["stdout"][:2000]}],
            suspicious=suspicious,
        )

    async def analyze_logs(self, log_dir: str, *, timeout: float = 180.0) -> LogAnalysisResult:
        """Grep-style triage for common log formats on SIFT."""

        cmd = (
            f"find {shlex.quote(log_dir)} -maxdepth 4 -type f "
            r"\( -name '*.log' -o -name '*.evtx' -o -name 'auth.log' \) "
            "-print | head -n 40 | xargs tail -n 80 2>/dev/null"
        )
        out = await self._run_with_retry(cmd, timeout=timeout)
        events = [{"line": ln} for ln in out["stdout"].splitlines() if ln.strip()][:500]
        anomalies = ["burst_failures"] if "fail" in out["stdout"].lower() else []
        return LogAnalysisResult(log_dir=log_dir, events=events, anomalies=anomalies)

    async def run_investigation(self, evidence_paths: list[str], incident: Incident) -> SIFTInvestigationResult:
        """Full pipeline: setup, ingest, analyze in parallel buckets, aggregate."""

        inv_id = uuid.uuid4().hex
        started = _utcnow()
        log: list[dict[str, Any]] = []
        tools: set[str] = set()

        await self._c.connect()
        info = await self._c.get_system_info()
        log.append({"phase": "environment", "detail": {"sift_version": info.sift_version, "kernel": info.kernel}})
        work = f"/cases/{incident.id}"
        await self._c.execute_command(f"mkdir -p {shlex.quote(work)}", timeout=60.0)
        log.append({"phase": "workspace", "path": work})

        for local in evidence_paths:
            p = Path(local)
            if p.is_file():
                ok = await self._c.transfer_file(str(p.resolve()), f"{work}/{p.name}")
                log.append({"phase": "ingest", "file": local, "ok": ok})
                hx = await self._c.execute_command(
                    f"sha256sum {shlex.quote(f'{work}/{p.name}')}",
                    timeout=120.0,
                )
                log.append({"phase": "hash", "output": hx.stdout[:500]})

        remote_paths = [f"{work}/{Path(ep).name}" if Path(ep).is_file() else ep for ep in evidence_paths]

        async def mem_task(path: str) -> tuple[str, MemoryAnalysisResult]:
            tools.add("volatility3")
            return path, await self.analyze_memory(path)

        async def disk_task(path: str) -> tuple[str, DiskAnalysisResult]:
            tools.add("sleuthkit")
            return path, await self.analyze_disk(path)

        async def timeline_task(path: str) -> tuple[str, TimelineResult]:
            tools.add("plaso")
            return path, await self.generate_timeline(path)

        async def net_task(path: str) -> tuple[str, NetworkAnalysisResult]:
            tools.add("tshark")
            return path, await self.analyze_network(path)

        async def log_task(path: str) -> tuple[str, LogAnalysisResult]:
            tools.add("log_grep")
            return path, await self.analyze_logs(path)

        mem_jobs: list[Any] = []
        disk_jobs: list[Any] = []
        timeline_jobs: list[Any] = []
        net_jobs: list[Any] = []
        log_jobs: list[Any] = []
        for rp in remote_paths:
            low = rp.lower()
            if any(x in low for x in (".mem", "memory")):
                mem_jobs.append(mem_task(rp))
            elif any(x in low for x in (".pcap", "pcapng")):
                net_jobs.append(net_task(rp))
            elif any(x in low for x in (".e01", ".dd", ".raw")):
                disk_jobs.append(disk_task(rp))
                timeline_jobs.append(timeline_task(rp))
            elif "log" in low:
                log_jobs.append(log_task(rp))

        memory: dict[str, MemoryAnalysisResult] = {}
        disk: dict[str, DiskAnalysisResult] = {}
        timelines: dict[str, TimelineResult] = {}
        network: dict[str, NetworkAnalysisResult] = {}
        logs: dict[str, LogAnalysisResult] = {}

        if mem_jobs:
            for path, res in await asyncio.gather(*mem_jobs):
                memory[path] = res
            log.append({"phase": "memory_parallel", "count": len(mem_jobs)})
        if disk_jobs:
            for path, res in await asyncio.gather(*disk_jobs):
                disk[path] = res
            log.append({"phase": "disk_parallel", "count": len(disk_jobs)})
        if timeline_jobs:
            for path, res in await asyncio.gather(*timeline_jobs):
                timelines[path] = res
            log.append({"phase": "timeline_parallel", "count": len(timeline_jobs)})
        if net_jobs:
            for path, res in await asyncio.gather(*net_jobs):
                network[path] = res
            log.append({"phase": "network_parallel", "count": len(net_jobs)})
        if log_jobs:
            for path, res in await asyncio.gather(*log_jobs):
                logs[path] = res
            log.append({"phase": "logs_parallel", "count": len(log_jobs)})

        completed = _utcnow()
        return SIFTInvestigationResult(
            investigation_id=inv_id,
            incident_id=str(incident.id),
            started_at=started,
            completed_at=completed,
            working_dir=work,
            memory=memory,
            disk=disk,
            timelines=timelines,
            network=network,
            logs=logs,
            execution_log=log,
            tools_used=sorted(tools),
        )