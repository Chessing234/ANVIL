"""MCP server exposing bundled security utilities (hashes, strings, logs, containment stubs)."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import mimetypes
import os
import re
import shutil
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("tutorial-security-tools", warn_on_duplicate_tools=False)


def _safe_path(raw: str) -> Path:
    path = Path(raw).expanduser().resolve()
    return path


@mcp.tool()
async def run_yara(file_path: str, rules_path: str | None = None) -> dict[str, Any]:
    """Run YARA against ``file_path`` when the ``yara`` binary is available."""

    target = _safe_path(file_path)
    if not target.is_file():
        return {"ok": False, "error": "file_not_found", "path": str(target)}
    if rules_path is None:
        return {"ok": False, "error": "rules_path_required", "matches": []}
    rules_p = Path(rules_path).expanduser().resolve()
    if not rules_p.is_file():
        return {"ok": False, "error": "rules_not_found", "matches": []}
    yara_bin = shutil.which("yara") or "yara"
    proc = await asyncio.create_subprocess_exec(
        yara_bin,
        str(rules_p),
        str(target),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60.0)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return {"ok": False, "error": "timeout", "matches": []}
    text = stdout.decode(errors="replace").strip()
    matches: list[dict[str, Any]] = []
    for line in text.splitlines():
        parts = line.split()
        if parts:
            matches.append({"rule": parts[0], "line": line})
    return {"ok": proc.returncode == 0, "matches": matches, "stderr": stderr.decode(errors="replace")}


@mcp.tool()
async def run_capa(file_path: str) -> dict[str, Any]:
    """Invoke CAPA when installed; otherwise return a descriptive stub."""

    target = _safe_path(file_path)
    if not target.is_file():
        return {"ok": False, "error": "file_not_found"}
    capa = shutil.which("capa")
    if capa is None:
        return {"ok": False, "error": "capa_not_installed", "capabilities": []}
    proc = await asyncio.create_subprocess_exec(
        capa,
        str(target),
        "-j",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120.0)
    try:
        data = json.loads(stdout.decode() or "{}")
    except json.JSONDecodeError:
        data = {"raw": stdout.decode(errors="replace")}
    return {"ok": proc.returncode == 0, "data": data, "stderr": stderr.decode(errors="replace")}


@mcp.tool()
async def strings_analysis(file_path: str, min_length: int = 4) -> dict[str, Any]:
    """Extract printable ASCII strings of at least ``min_length`` characters."""

    target = _safe_path(file_path)
    if not target.is_file():
        return {"ok": False, "error": "file_not_found"}
    ml = max(2, min(min_length, 256))
    data = await asyncio.to_thread(target.read_bytes)
    pattern = re.compile(rb"[\x20-\x7e]{%d,}" % ml)
    found = [m.group(0).decode("ascii", errors="ignore") for m in pattern.finditer(data)]
    return {"ok": True, "strings": found[:5000], "total": len(found)}


@mcp.tool()
async def file_type_detect(file_path: str) -> dict[str, Any]:
    """Guess MIME type using the stdlib ``mimetypes`` database."""

    target = _safe_path(file_path)
    if not target.is_file():
        return {"ok": False, "error": "file_not_found"}
    mime, _ = mimetypes.guess_type(str(target))
    return {"ok": True, "mime": mime or "application/octet-stream", "suffix": target.suffix}


@mcp.tool()
async def hash_file(file_path: str) -> dict[str, Any]:
    """Compute MD5, SHA-1, and SHA-256 for ``file_path``."""

    target = _safe_path(file_path)
    if not target.is_file():
        return {"ok": False, "error": "file_not_found"}
    md5 = hashlib.md5()
    sha1 = hashlib.sha1()
    sha256 = hashlib.sha256()

    def _read() -> None:
        with target.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                md5.update(chunk)
                sha1.update(chunk)
                sha256.update(chunk)

    await asyncio.to_thread(_read)
    return {
        "ok": True,
        "md5": md5.hexdigest(),
        "sha1": sha1.hexdigest(),
        "sha256": sha256.hexdigest(),
    }


@mcp.tool()
async def entropy_analysis(file_path: str, chunk_size: int = 4096) -> dict[str, Any]:
    """Compute Shannon entropy per chunk to highlight packed regions."""

    target = _safe_path(file_path)
    if not target.is_file():
        return {"ok": False, "error": "file_not_found"}
    cs = max(256, min(chunk_size, 1024 * 1024))

    def _scan() -> list[float]:
        scores: list[float] = []
        with target.open("rb") as handle:
            while chunk := handle.read(cs):
                if not chunk:
                    break
                counts = Counter(chunk)
                length = len(chunk)
                entropy = -sum(
                    (c / length) * math.log2(c / length) for c in counts.values() if c > 0
                )
                scores.append(entropy)
        return scores

    scores = await asyncio.to_thread(_scan)
    summary = {
        "mean": float(statistics.mean(scores)) if scores else 0.0,
        "max": float(max(scores)) if scores else 0.0,
        "chunks": len(scores),
    }
    return {"ok": True, "chunk_entropies": scores[:200], "summary": summary}


@mcp.tool()
async def exif_extract(file_path: str) -> dict[str, Any]:
    """Return EXIF metadata when Pillow is installed."""

    target = _safe_path(file_path)
    if not target.is_file():
        return {"ok": False, "error": "file_not_found"}
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS
    except ImportError:
        return {"ok": False, "error": "pillow_not_installed", "exif": {}}

    def _read_exif() -> dict[str, Any]:
        with Image.open(target) as img:
            raw = img.getexif() or {}
            decoded: dict[str, Any] = {}
            for k, v in raw.items():
                tag = TAGS.get(k, k)
                decoded[str(tag)] = str(v)
            return decoded

    exif = await asyncio.to_thread(_read_exif)
    return {"ok": True, "exif": exif}


@mcp.tool()
async def analyze_memory(dump_path: str) -> dict[str, Any]:
    """Summarize a memory dump; runs ``vol``/``vol.py`` when available."""

    target = _safe_path(dump_path)
    if not target.is_file():
        return {"ok": False, "error": "file_not_found", "plugins": [], "findings": []}
    vol = os.environ.get("VOLATILITY_PATH") or shutil.which("vol") or shutil.which("vol.py")
    if not vol:
        return {
            "ok": True,
            "plugins": ["stub"],
            "findings": [{"detail": "volatility_not_installed", "severity": "info"}],
            "notes": "Volatility binary not found; install volatility3 for live analysis.",
        }
    proc = await asyncio.create_subprocess_exec(
        vol,
        "-f",
        str(target),
        "windows.pslist",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60.0)
    return {
        "ok": proc.returncode == 0,
        "plugins": ["windows.pslist"],
        "findings": [{"detail": stdout.decode(errors="replace")[:4000]}],
        "notes": stderr.decode(errors="replace")[:1000],
    }


@mcp.tool()
async def parse_logs(log_path: str, log_type: str) -> dict[str, Any]:
    """Parse simple syslog / Apache / JSON-lines style logs."""

    target = _safe_path(log_path)
    if not target.is_file():
        return {"ok": False, "error": "file_not_found", "entries": []}
    lt = log_type.lower()
    entries: list[dict[str, Any]] = []

    def _parse() -> None:
        with target.open("r", encoding="utf-8", errors="replace") as handle:
            for idx, line in enumerate(handle):
                if idx > 5000:
                    break
                line = line.strip()
                if not line:
                    continue
                if lt == "json":
                    try:
                        payload = json.loads(line)
                        entries.append({"timestamp": payload.get("ts"), "message": json.dumps(payload)})
                    except json.JSONDecodeError:
                        entries.append({"timestamp": None, "message": line})
                elif lt in {"syslog", "splunk"}:
                    entries.append({"timestamp": None, "message": line, "severity": "info"})
                elif lt in {"windows", "windows event"}:
                    entries.append({"timestamp": None, "message": line, "severity": "informational"})
                elif lt == "apache":
                    entries.append({"timestamp": None, "message": line, "severity": "access"})
                else:
                    entries.append({"timestamp": None, "message": line})

    await asyncio.to_thread(_parse)
    return {"ok": True, "entries": entries}


@mcp.tool()
async def search_logs(query: str, source: str, time_range: list[str]) -> dict[str, Any]:
    """Filter previously parsed conceptual logs (demo grep over ``source`` file)."""

    target = _safe_path(source)
    if not target.is_file():
        return {"ok": False, "error": "file_not_found", "entries": []}
    q = query.lower()

    def _grep() -> list[dict[str, Any]]:
        hits: list[dict[str, Any]] = []
        with target.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if q in line.lower():
                    hits.append({"timestamp": None, "message": line.strip(), "fields": {"query": query}})
                if len(hits) > 2000:
                    break
        return hits

    matches = await asyncio.to_thread(_grep)
    return {"ok": True, "entries": matches, "time_range": time_range}


@mcp.tool()
async def correlate_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Lightweight correlation keyed by normalized message prefix."""

    buckets: dict[str, list[str]] = {}
    for ev in events:
        msg = str(ev.get("message", ""))[:32]
        buckets.setdefault(msg, []).append(str(ev.get("message", "")))
    correlations = [
        {"correlation_id": key or "empty", "events": vals[:20], "score": float(len(vals))}
        for key, vals in buckets.items()
        if len(vals) > 1
    ]
    return {"ok": True, "correlations": correlations}


@mcp.tool()
async def analyze_pcap(pcap_path: str) -> dict[str, Any]:
    """Summarize PCAP when ``tshark`` exists; otherwise return a stub."""

    target = _safe_path(pcap_path)
    if not target.is_file():
        return {"ok": False, "error": "file_not_found"}
    tshark = shutil.which("tshark")
    if not tshark:
        return {
            "ok": True,
            "protocols": {},
            "suspicious_flows": [],
            "notes": "tshark not installed; PCAP path validated only.",
        }
    proc = await asyncio.create_subprocess_exec(
        tshark,
        "-r",
        str(target),
        "-qz",
        "io,phs",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60.0)
    text = stdout.decode(errors="replace")
    protocols: dict[str, int] = {}
    for line in text.splitlines():
        if ":" in line:
            name, _, rest = line.partition(":")
            protocols[name.strip()] = protocols.get(name.strip(), 0) + 1
    return {
        "ok": proc.returncode == 0,
        "protocols": protocols,
        "suspicious_flows": [],
        "notes": stderr.decode(errors="replace")[:500],
    }


@mcp.tool()
async def dns_lookup(domain: str) -> dict[str, Any]:
    """Resolve ``domain`` using ``getaddrinfo``."""

    dom = domain.strip()
    if not dom:
        return {"ok": False, "error": "empty_domain", "domain": domain, "addresses": []}

    def _resolve() -> list[str]:
        import socket

        infos = socket.getaddrinfo(dom, None)
        return sorted({item[4][0] for item in infos})

    try:
        addresses = await asyncio.to_thread(_resolve)
        return {"ok": True, "domain": dom, "addresses": addresses, "error": None}
    except OSError as exc:
        return {"ok": False, "domain": dom, "addresses": [], "error": str(exc)}


@mcp.tool()
async def whois_lookup(ip: str) -> dict[str, Any]:
    """Return a stub WHOIS summary (live WHOIS varies by platform)."""

    if not re.match(r"^[\d.:a-fA-F]+$", ip.strip()):
        return {"ok": False, "ip": ip, "summary": "", "raw": "", "error": "invalid_ip"}
    return {"ok": True, "ip": ip.strip(), "summary": "stub-whois-record", "raw": "", "error": None}


@mcp.tool()
async def isolate_host(hostname: str) -> dict[str, Any]:
    """Simulate host isolation."""

    return {"ok": True, "action": "isolate_host", "detail": hostname, "metadata": {"simulated": True}}


@mcp.tool()
async def block_ip(ip: str, duration_minutes: int | None = None) -> dict[str, Any]:
    """Simulate firewall block."""

    return {
        "ok": True,
        "action": "block_ip",
        "detail": ip,
        "metadata": {"duration_minutes": duration_minutes},
    }


@mcp.tool()
async def kill_process(pid: int, hostname: str) -> dict[str, Any]:
    """Simulate remote process termination."""

    return {"ok": True, "action": "kill_process", "detail": f"{hostname}:{pid}", "metadata": {}}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
