"""PCAP-oriented network forensics with optional tshark/pyshark."""

from __future__ import annotations

import asyncio
import math
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)

TSHARK_TIMEOUT_SECONDS = 300.0


class NetworkAnalysisResult(BaseModel):
    """Structured PCAP analysis."""

    model_config = {"extra": "allow"}

    ok: bool = True
    pcap_path: str = ""
    protocol_stats: dict[str, int] = Field(default_factory=dict)
    top_talkers: list[dict[str, Any]] = Field(default_factory=list)
    unusual_ports: list[int] = Field(default_factory=list)
    beaconing: list[dict[str, Any]] = Field(default_factory=list)
    dns_tunneling: list[dict[str, Any]] = Field(default_factory=list)
    large_transfers: list[dict[str, Any]] = Field(default_factory=list)
    notes: str = ""


class NetworkAnalyzer:
    """Analyze PCAPs via tshark when available; otherwise parse minimal summaries."""

    def __init__(self, *, tshark_timeout_seconds: float = TSHARK_TIMEOUT_SECONDS) -> None:
        self._timeout = tshark_timeout_seconds

    async def analyze_pcap(self, pcap_path: str) -> NetworkAnalysisResult:
        path = Path(pcap_path).expanduser().resolve()
        if not path.is_file():
            return NetworkAnalysisResult(ok=False, pcap_path=str(path), notes="pcap missing")

        tshark = shutil.which("tshark")
        if tshark:
            return await self._tshark(path, tshark)

        text = path.read_text(errors="ignore")
        if text.strip().startswith("{"):
            import json

            try:
                data = json.loads(text)
                return NetworkAnalysisResult(
                    ok=True,
                    pcap_path=str(path),
                    protocol_stats=data.get("protocol_stats", {}),
                    top_talkers=data.get("top_talkers", []),
                    unusual_ports=data.get("unusual_ports", []),
                    beaconing=data.get("beaconing", []),
                    dns_tunneling=data.get("dns_tunneling", []),
                    large_transfers=data.get("large_transfers", []),
                    notes="loaded synthetic summary json",
                )
            except json.JSONDecodeError:
                pass

        return NetworkAnalysisResult(
            ok=True,
            pcap_path=str(path),
            protocol_stats={"unknown": 1},
            notes="tshark unavailable; no structured summary — heuristic empty",
        )

    async def _tshark(self, path: Path, tshark: str) -> NetworkAnalysisResult:
        fields = "-e", "ip.src", "-e", "ip.dst", "-e", "frame.len", "-e", "udp.srcport", "-e", "udp.dstport"
        proc = await asyncio.create_subprocess_exec(
            tshark,
            "-r",
            str(path),
            "-T",
            "fields",
            *fields,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self._timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return NetworkAnalysisResult(ok=False, pcap_path=str(path), notes="tshark timeout")

        lines = stdout.decode(errors="replace").splitlines()
        talkers: Counter[str] = Counter()
        proto_like: Counter[str] = Counter()
        lengths: list[int] = []
        for line in lines:
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            src, dst, flen, usp, dsp = (parts + ["", "", ""])[:5]
            talkers[src] += 1
            talkers[dst] += 1
            try:
                lengths.append(int(flen))
            except ValueError:
                continue
            if usp or dsp:
                proto_like["udp"] += 1
            else:
                proto_like["other"] += 1

        unusual_ports = sorted({int(p) for p in (usp, dsp) if p.isdigit() and int(p) > 49152})

        beaconing = self._detect_beaconing(lines)
        dns_tunneling = self._dns_tunnel_heuristic(path)
        large_transfers = self._large_transfer(lengths)

        return NetworkAnalysisResult(
            ok=True,
            pcap_path=str(path),
            protocol_stats=dict(proto_like),
            top_talkers=[{"endpoint": k, "count": v} for k, v in talkers.most_common(5)],
            unusual_ports=unusual_ports[:10],
            beaconing=beaconing,
            dns_tunneling=dns_tunneling,
            large_transfers=large_transfers,
            notes=stderr.decode(errors="replace")[:500],
        )

    @staticmethod
    def _detect_beaconing(lines: list[str]) -> list[dict[str, Any]]:
        intervals: defaultdict[str, list[float]] = defaultdict(list)
        prev_ts = 0.0
        for idx, line in enumerate(lines[:500]):
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            key = f"{parts[0]}->{parts[1]}"
            intervals[key].append(float(idx - prev_ts))
            prev_ts = float(idx)
        beacons: list[dict[str, Any]] = []
        for key, vals in intervals.items():
            if len(vals) < 4:
                continue
            mean = sum(vals) / len(vals)
            var = sum((v - mean) ** 2 for v in vals) / len(vals)
            if var < 0.5 and mean > 0:
                beacons.append({"pair": key, "mean_gap": mean, "variance": var, "score": 0.7})
        return beacons[:5]

    @staticmethod
    def _dns_tunnel_heuristic(path: Path) -> list[dict[str, Any]]:
        text = path.read_bytes()[:2048].decode(errors="ignore")
        if "dns" in text.lower() and len(text) > 400:
            return [{"indicator": "long_dns_like_blob", "score": 0.62}]
        return []

    @staticmethod
    def _large_transfer(lengths: list[int]) -> list[dict[str, Any]]:
        if not lengths:
            return []
        mx = max(lengths)
        if mx > 500_000:
            return [{"max_frame_bytes": mx, "score": 0.74}]
        return []


def shannon_entropy(data: bytes) -> float:
    if not data:
        return 0.0
    counts = Counter(data)
    length = len(data)
    return -sum((c / length) * math.log2(c / length) for c in counts.values() if c)
