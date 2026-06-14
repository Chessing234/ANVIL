"""MCP server exposing SIFT-style forensic workflows with chain-of-custody logging."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("tutorial-sift-server", warn_on_duplicate_tools=False)


def _artifact_root() -> Path:
    raw = os.environ.get("SIFT_ARTIFACT_ROOT", ".")
    return Path(raw).expanduser().resolve()


def _audit(action: str, details: dict[str, Any]) -> None:
    log_path = Path(os.environ.get("SIFT_CHAIN_OF_CUSTODY_LOG", "sift_chain_of_custody.jsonl")).expanduser()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user": os.environ.get("USER", os.environ.get("USERNAME", "unknown")),
        "action": action,
        "details": details,
    }
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")


def _under_root(path: Path) -> bool:
    root = _artifact_root()
    try:
        path.resolve().relative_to(root)
        return True
    except ValueError:
        return False


@mcp.tool()
async def sift_list_artifacts(root: str | None = None) -> dict[str, Any]:
    """List disk images, memory dumps, and logs under the artifact root."""

    base = Path(root).expanduser().resolve() if root else _artifact_root()
    if not _under_root(base):
        return {"ok": False, "error": "path_outside_root", "artifacts": []}
    _audit("sift_list_artifacts", {"root": str(base)})

    def _walk() -> list[dict[str, Any]]:
        artifacts: list[dict[str, Any]] = []
        for p in base.rglob("*"):
            if p.is_file() and len(artifacts) < 5000:
                artifacts.append(
                    {
                        "path": str(p),
                        "size": p.stat().st_size,
                        "suffix": p.suffix.lower(),
                    },
                )
        return artifacts

    artifacts = await asyncio.to_thread(_walk)
    return {"ok": True, "artifacts": artifacts}


@mcp.tool()
async def sift_analyze_memory(dump_path: str, plugins: list[str] | None = None) -> dict[str, Any]:
    """Run volatility-style analysis hooks (plugins default to pslist/netscan/malfind)."""

    target = Path(dump_path).expanduser().resolve()
    if not target.is_file() or not _under_root(target):
        return {"ok": False, "error": "invalid_dump", "plugins": [], "findings": [], "notes": ""}
    _audit("sift_analyze_memory", {"dump": str(target), "plugins": plugins or []})
    selected = plugins or ["pslist", "netscan", "malfind", "dlllist"]
    return {
        "ok": True,
        "plugins": selected,
        "findings": [{"plugin": p, "detail": "stub-output"} for p in selected],
        "notes": "sift volatility pipeline (stub)",
    }


@mcp.tool()
async def sift_analyze_disk(image_path: str) -> dict[str, Any]:
    """Timeline-oriented disk summary (safe stub when sleuthkit is absent)."""

    target = Path(image_path).expanduser().resolve()
    if not target.is_file() or not _under_root(target):
        return {"ok": False, "error": "invalid_image"}
    _audit("sift_analyze_disk", {"image": str(target)})
    return {
        "ok": True,
        "image": str(target),
        "timeline_points": 0,
        "carving": {"recovered": 0},
        "registry_hives": [],
    }


@mcp.tool()
async def sift_extract_files(image_path: str, target_path: str) -> dict[str, Any]:
    """Simulate extracting ``target_path`` from ``image_path``."""

    image = Path(image_path).expanduser().resolve()
    if not image.is_file() or not _under_root(image):
        return {"ok": False, "error": "invalid_image"}
    _audit("sift_extract_files", {"image": str(image), "target": target_path})
    return {"ok": True, "extracted_to": f"/tmp/sift_extract/{Path(target_path).name}", "bytes": 0}


@mcp.tool()
async def sift_generate_timeline(image_path: str) -> dict[str, Any]:
    """Return a placeholder forensic timeline."""

    image = Path(image_path).expanduser().resolve()
    if not image.is_file() or not _under_root(image):
        return {"ok": False, "error": "invalid_image"}
    _audit("sift_generate_timeline", {"image": str(image)})
    return {"ok": True, "events": [], "notes": "timeline generation stub"}


@mcp.tool()
async def sift_search_ioc(root: str, indicators: list[str]) -> dict[str, Any]:
    """Search for IOC strings across text-readable files under ``root``."""

    base = Path(root).expanduser().resolve()
    if not base.exists() or not _under_root(base):
        return {"ok": False, "error": "invalid_root", "hits": []}
    lowered = [i.lower() for i in indicators if i]
    hits: list[dict[str, Any]] = []

    def _scan() -> None:
        for path in base.rglob("*"):
            if path.is_dir() or len(hits) > 2000:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            lower_text = text.lower()
            for ind in lowered:
                if ind and ind in lower_text:
                    hits.append({"path": str(path), "indicator": ind})

    await asyncio.to_thread(_scan)
    _audit("sift_search_ioc", {"root": str(base), "hits": len(hits)})
    return {"ok": True, "hits": hits}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
