"""SSH (or mock) connectivity to a SANS SIFT workstation."""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import structlog

logger = structlog.get_logger(__name__)

try:
    import asyncssh
except ImportError:
    asyncssh = None  # type: ignore[misc, assignment]


@dataclass
class CommandResult:
    """Result of a remote (or mocked) shell invocation."""

    stdout: str
    stderr: str
    exit_code: int
    duration_seconds: float


@dataclass
class FileEntry:
    """Single row from a remote directory listing."""

    name: str
    path: str
    size_bytes: int
    is_directory: bool


@dataclass
class SIFTSystemInfo:
    """Snapshot of SIFT host capabilities."""

    sift_version: str
    installed_tools: list[str]
    disk_free_gb: float
    kernel: str = ""


class _SSHBackend(Protocol):
    async def run(self, command: str, *, timeout: float) -> CommandResult: ...

    async def close(self) -> None: ...


@dataclass
class _MockBackend:
    """In-process backend used when no SIFT VM is reachable (CI / tests)."""

    workdir: Path = field(default_factory=lambda: Path(os.environ.get("TMPDIR", "/tmp")) / "sift_mock")
    command_log: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.workdir.mkdir(parents=True, exist_ok=True)

    async def run(self, command: str, *, timeout: float) -> CommandResult:
        _ = timeout
        self.command_log.append(command)
        started = time.perf_counter()
        if command.strip().startswith("echo "):
            body = command.split("echo", 1)[1].strip()
            return CommandResult(stdout=body + "\n", stderr="", exit_code=0, duration_seconds=time.perf_counter() - started)
        if "volatility" in command or "vol.py" in command:
            if "windows.pslist" in command:
                return CommandResult(
                    stdout="{}",
                    stderr="",
                    exit_code=0,
                    duration_seconds=time.perf_counter() - started,
                )
            payload = {
                "processes": [{"pid": 4, "name": "System"}],
                "network": [{"proto": "tcp", "local": "0.0.0.0:445"}],
                "suspicious_processes": 1,
            }
            return CommandResult(
                stdout=json.dumps(payload),
                stderr="",
                exit_code=0,
                duration_seconds=time.perf_counter() - started,
            )
        if "mmls" in command or "fls" in command:
            return CommandResult(
                stdout="GUID Partition Table\nOffset Sector: 2048\n",
                stderr="",
                exit_code=0,
                duration_seconds=time.perf_counter() - started,
            )
        if "tshark" in command:
            return CommandResult(
                stdout='{"frames": 120, "tcp": 80}\n',
                stderr="",
                exit_code=0,
                duration_seconds=time.perf_counter() - started,
            )
        if "log2timeline" in command or "psort" in command:
            return CommandResult(
                stdout="timeline: 42 events\n",
                stderr="",
                exit_code=0,
                duration_seconds=time.perf_counter() - started,
            )
        if "find " in command and "tail" in command:
            return CommandResult(
                stdout="2024-01-02 fail authentication failure\n",
                stderr="",
                exit_code=0,
                duration_seconds=time.perf_counter() - started,
            )
        if "grep" in command or "journalctl" in command or "evtx" in command:
            return CommandResult(
                stdout="2024-01-01T00:00:00Z EventID=4624\n",
                stderr="",
                exit_code=0,
                duration_seconds=time.perf_counter() - started,
            )
        if "sha256sum" in command:
            return CommandResult(
                stdout="ab" * 32 + "  artifact\n",
                stderr="",
                exit_code=0,
                duration_seconds=time.perf_counter() - started,
            )
        if "fsstat" in command:
            return CommandResult(
                stdout="File System Information\n",
                stderr="",
                exit_code=0,
                duration_seconds=time.perf_counter() - started,
            )
        if "uname" in command:
            return CommandResult(
                stdout="6.5.0-generic\n/dev/sda1  50G  10G  40G  20% /\n",
                stderr="",
                exit_code=0,
                duration_seconds=time.perf_counter() - started,
            )
        if "compgen" in command:
            return CommandResult(
                stdout="vol.py\ntshark\nmmls\nfls\n",
                stderr="",
                exit_code=0,
                duration_seconds=time.perf_counter() - started,
            )
        if "lsb_release" in command:
            return CommandResult(
                stdout="Description:\tSIFT Workstation 4.0\n",
                stderr="",
                exit_code=0,
                duration_seconds=time.perf_counter() - started,
            )
        return CommandResult(stdout="", stderr="", exit_code=0, duration_seconds=time.perf_counter() - started)

    async def close(self) -> None:
        return


@dataclass
class _AsyncSSHBackend:
    """Real asyncssh session with keepalive and bounded retries."""

    connection: Any
    host: str

    async def run(self, command: str, *, timeout: float) -> CommandResult:
        started = time.perf_counter()
        result = await asyncio.wait_for(self.connection.run(command, check=False), timeout=timeout)
        out = result.stdout or ""
        err = result.stderr or ""
        code = int(result.exit_status or 0)
        return CommandResult(stdout=out, stderr=err, exit_code=code, duration_seconds=time.perf_counter() - started)

    async def close(self) -> None:
        self.connection.close()
        await self.connection.wait_closed()


class SIFTConnector:
    """Persistent SSH connector to a SIFT VM with mock mode for automated tests."""

    def __init__(
        self,
        *,
        mock: bool | None = None,
        max_reconnect_attempts: int = 3,
    ) -> None:
        if mock is True:
            self._mock = True
        elif mock is False:
            self._mock = False
        else:
            self._mock = os.environ.get("TUTORIAL_SIFT_MOCK", "1") == "1"
        self._max_reconnect = max(1, max_reconnect_attempts)
        self._backend: _SSHBackend | None = None
        self._host: str = ""
        self._lock = asyncio.Lock()

    @staticmethod
    def is_sift_available() -> bool:
        """Return True if common SIFT binaries exist on *this* machine (quick probe)."""

        for exe in ("vol", "vol.py", "tshark", "mmls"):
            for p in os.environ.get("PATH", "").split(os.pathsep):
                candidate = Path(p) / exe
                if candidate.is_file():
                    return True
        return False

    async def connect(
        self,
        host: str = "localhost",
        port: int = 22,
        username: str = "sansforensics",
        key_path: str | None = None,
    ) -> _SSHBackend:
        """Open SSH session (or mock backend) with automatic keepalive."""

        async with self._lock:
            if self._backend is not None:
                return self._backend
            self._host = host
            if self._mock:
                self._backend = _MockBackend()
                logger.info("sift_connector_mock", host=host)
                return self._backend
            if asyncssh is None:
                raise RuntimeError("asyncssh is required for real SIFT SSH connections")
            last_err: Exception | None = None
            for attempt in range(1, self._max_reconnect + 1):
                try:
                    conn_kwargs: dict[str, Any] = {
                        "host": host,
                        "port": port,
                        "username": username,
                        "known_hosts": None,
                        "server_host_key_algs": ["ssh-rsa", "rsa-sha2-256", "rsa-sha2-512", "ssh-ed25519"],
                        "keepalive_interval": 30,
                    }
                    if key_path:
                        conn_kwargs["client_keys"] = [key_path]
                    conn = await asyncssh.connect(**conn_kwargs)
                    self._backend = _AsyncSSHBackend(connection=conn, host=host)
                    logger.info("sift_connector_ssh", host=host, attempt=attempt)
                    return self._backend
                except (OSError, asyncssh.Error) as exc:
                    last_err = exc
                    logger.warning("sift_ssh_connect_failed", attempt=attempt, error=str(exc))
                    await asyncio.sleep(min(2.0 * attempt, 8.0))
            raise RuntimeError(f"SIFT SSH connect failed after {self._max_reconnect} attempts") from last_err

    async def _ensure_backend(self) -> _SSHBackend:
        if self._backend is None:
            return await self.connect()
        return self._backend

    async def execute_command(self, command: str, timeout: float = 300.0) -> CommandResult:
        """Run ``command`` on SIFT with timeout and single reconnect on transport failure."""

        backend = await self._ensure_backend()
        try:
            return await backend.run(command, timeout=timeout)
        except (TimeoutError, asyncio.CancelledError):
            raise
        except Exception as exc:
            logger.error("sift_command_failed", command=command[:200], error=str(exc))
            if not self._mock and self._max_reconnect > 1:
                await self.disconnect()
                self._backend = None
                backend = await self.connect(self._host)
                return await backend.run(command, timeout=timeout)
            raise

    async def transfer_file(self, local_path: str, remote_path: str) -> bool:
        """Copy local file into mock workspace or upload via SFTP when using SSH."""

        src = Path(local_path)
        if not src.is_file():
            return False
        be = await self._ensure_backend()
        if isinstance(be, _MockBackend):
            dest = be.workdir / Path(remote_path).name
            dest.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(shutil.copy2, src, dest)
            return True
        if asyncssh is None:
            return False
        async with be.connection.start_sftp_client() as sftp:
            await sftp.put(local_path, remote_path)
        return True

    async def transfer_file_from_remote(self, remote_path: str, local_path: str) -> bool:
        """Download remote artifact."""

        be = await self._ensure_backend()
        dest = Path(local_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(be, _MockBackend):
            src = be.workdir / Path(remote_path).name
            if not src.is_file():
                dest.write_text("", encoding="utf-8")
                return True
            await asyncio.to_thread(shutil.copy2, src, dest)
            return True
        if asyncssh is None:
            return False
        async with be.connection.start_sftp_client() as sftp:
            await sftp.get(remote_path, local_path)
        return True

    async def list_directory(self, path: str) -> list[FileEntry]:
        """Return parsed directory listing (mock uses local workdir)."""

        be = await self._ensure_backend()
        if isinstance(be, _MockBackend):
            root = be.workdir / Path(path).name if path != "/" else be.workdir
            if not root.exists():
                return []
            out: list[FileEntry] = []
            for child in sorted(root.iterdir()):
                stat = child.stat()
                out.append(
                    FileEntry(
                        name=child.name,
                        path=str(child),
                        size_bytes=int(stat.st_size),
                        is_directory=child.is_dir(),
                    ),
                )
            return out
        res = await self.execute_command(f"ls -la {path!s}", timeout=60.0)
        entries: list[FileEntry] = []
        for line in res.stdout.splitlines():
            m = re.match(r"^[-dlrwx]{10}\s+\d+\s+\S+\s+\S+\s+(\d+)\s+.*\s(\S+)$", line)
            if not m:
                continue
            size = int(m.group(1))
            name = m.group(2)
            is_dir = line.startswith("d")
            entries.append(FileEntry(name=name, path=f"{path.rstrip('/')}/{name}", size_bytes=size, is_directory=is_dir))
        return entries

    async def file_exists(self, path: str) -> bool:
        res = await self.execute_command(f"test -e {path!s} && echo ok", timeout=30.0)
        return "ok" in res.stdout

    async def get_system_info(self) -> SIFTSystemInfo:
        res = await self.execute_command("uname -r && df -BG / | tail -1", timeout=30.0)
        lines = res.stdout.strip().splitlines()
        kernel = lines[0] if lines else ""
        disk_gb = 50.0
        if len(lines) > 1:
            parts = lines[1].split()
            for p in parts:
                if p.endswith("G") and p[:-1].isdigit():
                    disk_gb = float(p[:-1])
                    break
        tools_res = await self.execute_command("compgen -c | sort -u | head -n 200", timeout=30.0)
        tools = sorted({t for t in tools_res.stdout.splitlines() if t.strip()})
        ver_res = await self.execute_command("lsb_release -d 2>/dev/null || echo SIFT", timeout=15.0)
        return SIFTSystemInfo(
            sift_version=ver_res.stdout.strip(),
            installed_tools=tools[:80],
            disk_free_gb=disk_gb,
            kernel=kernel,
        )

    async def disconnect(self) -> None:
        async with self._lock:
            if self._backend is not None:
                await self._backend.close()
                self._backend = None
