"""IOC matching with built-in lists and optional external feeds."""

from __future__ import annotations

import hashlib
import ipaddress
import json
from pathlib import Path

import structlog

from shared.models import IOCMatch

logger = structlog.get_logger(__name__)


class IOCMatcher:
    """Match files, hashes, IPs, and domains against local and remote intel."""

    def __init__(self, extra_feeds: list[Path] | None = None) -> None:
        self._builtin_hashes = {
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855": ("benign_empty", "INTERNAL", 0.1),
            "d41d8cd98f00b204e9800998ecf8427e": ("md5_empty", "INTERNAL", 0.1),
        }
        self._builtin_ips = {"203.0.113.50": ("sinkhole", "CUSTOM", 0.82)}
        self._builtin_domains = {"evil.example": ("c2_domain", "CUSTOM", 0.88)}
        self._feeds = list(extra_feeds or [])

    async def check_file(self, file_path: str) -> list[IOCMatch]:
        path = Path(file_path).expanduser().resolve()
        if not path.is_file():
            return []
        data = path.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        matches = await self.check_hash(sha)
        lowered = data[:2048].decode(errors="ignore").lower()
        if "powershell" in lowered and "bypass" in lowered:
            matches.append(
                IOCMatch(
                    indicator="powershell_bypass_token",
                    threat_type="execution",
                    confidence=0.7,
                    source="CONTENT_HEURISTIC",
                    recommended_action="review_script_block",
                ),
            )
        return matches

    async def check_hash(self, hash_value: str) -> list[IOCMatch]:
        hv = hash_value.lower().strip()
        matches: list[IOCMatch] = []
        if hv in self._builtin_hashes:
            threat, src, conf = self._builtin_hashes[hv]
            matches.append(
                IOCMatch(
                    indicator=hv,
                    threat_type=threat,
                    confidence=conf,
                    source=src,
                    recommended_action="informational",
                ),
            )
        for feed in self._feeds:
            try:
                payload = json.loads(feed.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            for row in payload.get("hashes", []):
                if row.get("value", "").lower() == hv:
                    matches.append(
                        IOCMatch(
                            indicator=hv,
                            threat_type=str(row.get("type", "unknown")),
                            confidence=float(row.get("confidence", 0.6)),
                            source=str(row.get("source", feed.name)),
                            recommended_action=str(row.get("action", "block_hash")),
                        ),
                    )
        return matches

    async def check_ip(self, ip: str) -> list[IOCMatch]:
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            return []
        matches: list[IOCMatch] = []
        if ip in self._builtin_ips:
            threat, src, conf = self._builtin_ips[ip]
            matches.append(
                IOCMatch(
                    indicator=ip,
                    threat_type=threat,
                    confidence=conf,
                    source=src,
                    recommended_action="block_ip",
                ),
            )
        for feed in self._feeds:
            try:
                payload = json.loads(feed.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            for row in payload.get("ips", []):
                if row.get("value") == ip:
                    matches.append(
                        IOCMatch(
                            indicator=ip,
                            threat_type=str(row.get("type", "unknown")),
                            confidence=float(row.get("confidence", 0.65)),
                            source=str(row.get("source", feed.name)),
                            recommended_action=str(row.get("action", "block_ip")),
                        ),
                    )
        return matches

    async def check_domain(self, domain: str) -> list[IOCMatch]:
        dom = domain.lower().strip()
        matches: list[IOCMatch] = []
        if dom in self._builtin_domains:
            threat, src, conf = self._builtin_domains[dom]
            matches.append(
                IOCMatch(
                    indicator=dom,
                    threat_type=threat,
                    confidence=conf,
                    source=src,
                    recommended_action="sinkhole_dns",
                ),
            )
        for feed in self._feeds:
            try:
                payload = json.loads(feed.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            for row in payload.get("domains", []):
                if row.get("value", "").lower() == dom:
                    matches.append(
                        IOCMatch(
                            indicator=dom,
                            threat_type=str(row.get("type", "unknown")),
                            confidence=float(row.get("confidence", 0.65)),
                            source=str(row.get("source", feed.name)),
                            recommended_action=str(row.get("action", "block_domain")),
                        ),
                    )
        return matches
