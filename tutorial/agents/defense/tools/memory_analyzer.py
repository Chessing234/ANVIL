"""Volatility3-oriented memory forensics with async subprocess execution."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from pathlib import Path
from typing import Any

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)

VOLATILITY_TIMEOUT_SECONDS = 300.0


class MemoryForensicsReport(BaseModel):
    """Structured memory analysis output."""

    model_config = {"extra": "allow"}

    ok: bool = True
    dump_path: str = ""
    plugins_run: list[str] = Field(default_factory=list)
    processes: list[dict[str, Any]] = Field(default_factory=list)
    network_connections: list[dict[str, Any]] = Field(default_factory=list)
    injections: list[dict[str, Any]] = Field(default_factory=list)
    anomalies: list[dict[str, Any]] = Field(default_factory=list)
    anomaly_scores: dict[str, float] = Field(default_factory=dict)
    stderr: str = ""
    notes: str = ""


class MemoryAnalyzer:
    """Run volatility3 when available; otherwise emit heuristic findings."""

    def __init__(self, *, volatility_timeout_seconds: float = VOLATILITY_TIMEOUT_SECONDS) -> None:
        self._timeout = volatility_timeout_seconds

    async def analyze(self, dump_path: str) -> MemoryForensicsReport:
        """Analyze ``dump_path`` with volatility3 plugins (async, bounded runtime)."""

        path = Path(dump_path).expanduser().resolve()
        if not path.is_file():
            return MemoryForensicsReport(
                ok=False,
                dump_path=str(path),
                notes="dump file not found",
            )

        vol = os.environ.get("VOLATILITY_PATH") or shutil.which("vol") or shutil.which("vol.py")
        plugins = [
            "windows.pslist",
            "windows.netscan",
            "windows.malfind",
            "windows.dlllist",
            "windows.cmdline",
            "windows.svcscan",
        ]
        if not vol:
            return self._heuristic_report(path, plugins, "volatility binary not found; heuristic scan only")

        aggregated: list[str] = []
        ran: list[str] = []
        for plugin in plugins:
            proc = await asyncio.create_subprocess_exec(
                vol,
                "-r",
                "json",
                "-f",
                str(path),
                plugin,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=self._timeout,
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                aggregated.append(f"{plugin}:TIMEOUT")
                continue
            ran.append(plugin)
            text = stdout.decode(errors="replace")[:50_000]
            aggregated.append(f"{plugin}:{text[:2000]}")
            if stderr:
                aggregated.append(f"{plugin}:stderr:{stderr.decode(errors='replace')[:1000]}")

        combined = "\n".join(aggregated)
        anomalies = self._derive_anomalies(combined)
        scores = {a["id"]: float(a.get("score", 0.5)) for a in anomalies}
        return MemoryForensicsReport(
            ok=True,
            dump_path=str(path),
            plugins_run=ran,
            processes=self._stub_structures(combined, "process"),
            network_connections=self._stub_structures(combined, "net"),
            injections=self._stub_structures(combined, "malfind"),
            anomalies=anomalies,
            anomaly_scores=scores,
            stderr="",
            notes="volatility json aggregate (truncated)",
        )

    def _heuristic_report(self, path: Path, plugins: list[str], note: str) -> MemoryForensicsReport:
        data = path.read_bytes()[:4096]
        entropy = self._shannon_entropy(data)
        anomalies: list[dict[str, Any]] = []
        if entropy > 7.5:
            anomalies.append(
                {
                    "id": "high_entropy_header",
                    "detail": "High entropy in first 4KiB — possible packing or encryption",
                    "score": 0.72,
                },
            )
        if b"MZ" in data[:1024]:
            anomalies.append(
                {
                    "id": "embedded_mz",
                    "detail": "MZ header visible in early bytes — inspect for embedded PE",
                    "score": 0.55,
                },
            )
        return MemoryForensicsReport(
            ok=True,
            dump_path=str(path),
            plugins_run=["heuristic"],
            anomalies=anomalies,
            anomaly_scores={a["id"]: float(a["score"]) for a in anomalies},
            notes=note,
            stderr="",
        )

    @staticmethod
    def _shannon_entropy(data: bytes) -> float:
        if not data:
            return 0.0
        from collections import Counter
        import math

        counts = Counter(data)
        length = len(data)
        return -sum((c / length) * math.log2(c / length) for c in counts.values() if c)

    @staticmethod
    def _derive_anomalies(combined: str) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        lower = combined.lower()
        if "svchost" in lower and "cmd.exe" in lower:
            found.append(
                {
                    "id": "unusual_parent_child",
                    "detail": "svchost spawning cmd.exe — validate command line",
                    "score": 0.68,
                },
            )
        if "malfind" in lower and "false" not in lower:
            found.append({"id": "possible_injection", "detail": "Malfind output non-empty", "score": 0.61})
        if not found:
            found.append({"id": "baseline", "detail": "No high-confidence anomalies from text heuristics", "score": 0.35})
        return found

    @staticmethod
    def _stub_structures(blob: str, kind: str) -> list[dict[str, Any]]:
        try:
            payload = json.loads(blob)
            if isinstance(payload, list):
                return [{"kind": kind, "row": item} for item in payload[:50]]
        except json.JSONDecodeError:
            pass
        return [{"kind": kind, "summary": blob[:500]}]
