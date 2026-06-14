"""Concrete containment primitives with pre/post checks, timeouts, and rollback hooks."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

@dataclass
class ToolExecutionResult:
    """Outcome of a containment primitive including rollback hints."""

    success: bool
    detail: str
    rollback_commands: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class HostIsolator:
    """Host network isolation (iptables-style simulation for tests)."""

    def __init__(self, *, state_dir: Path | None = None) -> None:
        self._state_dir = Path(state_dir) if state_dir else Path.cwd() / ".containment_state"
        self._state_dir.mkdir(parents=True, exist_ok=True)

    async def isolate(self, hostname: str, *, dry_run: bool) -> ToolExecutionResult:
        if not hostname.strip():
            return ToolExecutionResult(False, "empty hostname", ["noop"])
        path = self._state_dir / f"isolate_{hostname}.json"
        if dry_run:
            return ToolExecutionResult(
                True,
                f"dry-run: would isolate {hostname}",
                rollback_commands=[f"delete:{path}"],
                metadata={"path": str(path)},
            )

        def _write() -> None:
            path.write_text(json.dumps({"hostname": hostname, "isolated": True}), encoding="utf-8")

        await asyncio.to_thread(_write)
        return ToolExecutionResult(
            True,
            f"recorded isolation for {hostname}",
            rollback_commands=[f"unisolate:{hostname}"],
            metadata={"path": str(path)},
        )

    async def rollback_isolate(self, hostname: str) -> ToolExecutionResult:
        path = self._state_dir / f"isolate_{hostname}.json"

        def _rm() -> None:
            if path.is_file():
                path.unlink()

        await asyncio.to_thread(_rm)
        return ToolExecutionResult(True, f"removed isolation record for {hostname}", [])


class ProcessTerminator:
    """Process termination with dependency awareness (no real kill in dry-run)."""

    async def kill(self, pid: int, hostname: str, *, dry_run: bool) -> ToolExecutionResult:
        if pid <= 0:
            return ToolExecutionResult(False, "invalid pid", ["noop"])
        if dry_run:
            return ToolExecutionResult(
                True,
                f"dry-run: would signal pid {pid} on {hostname}",
                rollback_commands=[f"cannot-revive-pid:{pid}"],
            )
        return ToolExecutionResult(
            True,
            f"simulated SIGTERM to pid {pid} on {hostname} (tutorial stub)",
            rollback_commands=["restart_service_if_needed"],
            metadata={"pid": pid, "hostname": hostname},
        )


class IPBlocker:
    """IP blocklist management (local state file)."""

    def __init__(self, *, state_dir: Path | None = None) -> None:
        self._state_dir = Path(state_dir) if state_dir else Path.cwd() / ".containment_state"
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._file = self._state_dir / "blocked_ips.txt"

    async def block(self, ip: str, *, dry_run: bool) -> ToolExecutionResult:
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            return ToolExecutionResult(False, f"invalid ip {ip}", ["noop"])

        if dry_run:
            return ToolExecutionResult(True, f"dry-run: would block {ip}", rollback_commands=[f"unblock:{ip}"])

        def _append() -> None:
            existing = self._file.read_text(encoding="utf-8").splitlines() if self._file.is_file() else []
            if ip not in existing:
                with self._file.open("a", encoding="utf-8") as fh:
                    fh.write(ip + "\n")

        await asyncio.to_thread(_append)
        return ToolExecutionResult(True, f"blocked {ip}", rollback_commands=[f"unblock:{ip}"])

    async def unblock(self, ip: str) -> ToolExecutionResult:
        if not self._file.is_file():
            return ToolExecutionResult(True, "no blocklist", [])

        def _filter() -> None:
            lines = [ln for ln in self._file.read_text(encoding="utf-8").splitlines() if ln.strip() != ip]
            self._file.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

        await asyncio.to_thread(_filter)
        return ToolExecutionResult(True, f"unblocked {ip}", [])


class AccountManager:
    """Disable or enable accounts (stub records)."""

    def __init__(self, *, state_dir: Path | None = None) -> None:
        self._state_dir = Path(state_dir) if state_dir else Path.cwd() / ".containment_state"
        self._state_dir.mkdir(parents=True, exist_ok=True)

    async def disable(self, username: str, *, dry_run: bool) -> ToolExecutionResult:
        if not username.strip():
            return ToolExecutionResult(False, "empty username", ["noop"])
        path = self._state_dir / f"account_{username}.json"
        if dry_run:
            return ToolExecutionResult(True, f"dry-run: disable {username}", rollback_commands=[f"enable:{username}"])
        path.write_text(json.dumps({"user": username, "disabled": True}), encoding="utf-8")
        return ToolExecutionResult(True, f"disabled {username}", rollback_commands=[f"enable:{username}"])

    async def enable(self, username: str) -> ToolExecutionResult:
        path = self._state_dir / f"account_{username}.json"
        if path.is_file():
            path.unlink()
        return ToolExecutionResult(True, f"enabled {username}", [])


class FileQuarantiner:
    """Move suspicious files into quarantine with preserved metadata."""

    def __init__(self, quarantine_root: Path) -> None:
        self._root = Path(quarantine_root)
        self._root.mkdir(parents=True, exist_ok=True)

    async def quarantine(self, path: str, *, dry_run: bool) -> ToolExecutionResult:
        src = Path(path).expanduser().resolve()
        if not src.is_file():
            return ToolExecutionResult(False, f"missing file {path}", ["noop"])
        meta = {"original": str(src), "size": src.stat().st_size}
        dest = self._root / f"{src.name}.{abs(hash(src)) % 10_000_000}"
        if dry_run:
            return ToolExecutionResult(
                True,
                f"dry-run: quarantine {src} -> {dest}",
                rollback_commands=[f"restore:{src}:{dest}"],
                metadata=meta,
            )

        def _move() -> None:
            shutil.move(str(src), str(dest))
            side = dest.with_suffix(dest.suffix + ".orig.json")
            side.write_text(json.dumps(meta), encoding="utf-8")

        await asyncio.to_thread(_move)
        return ToolExecutionResult(
            True,
            f"quarantined to {dest}",
            rollback_commands=[f"restore:{src}:{dest}"],
            metadata={"dest": str(dest)},
        )


class DNSSinkholer:
    """Local DNS sinkhole entries (hosts-style file for simulation)."""

    def __init__(self, hosts_path: Path) -> None:
        self._hosts_path = Path(hosts_path)
        self._hosts_path.parent.mkdir(parents=True, exist_ok=True)

    async def sinkhole(self, domain: str, *, dry_run: bool, sink_ip: str = "0.0.0.0") -> ToolExecutionResult:
        if not domain.strip():
            return ToolExecutionResult(False, "empty domain", ["noop"])
        line = f"{sink_ip}\t{domain}\n"
        if dry_run:
            return ToolExecutionResult(True, f"dry-run: sinkhole {domain}", rollback_commands=[f"unsink:{domain}"])
        with self._hosts_path.open("a", encoding="utf-8") as fh:
            fh.write(f"# tutorial-sinkhole {domain}\n{line}")
        return ToolExecutionResult(True, f"sinkholed {domain}", rollback_commands=[f"unsink:{domain}"])

