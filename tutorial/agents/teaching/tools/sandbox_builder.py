"""Container-based sandbox builder: Docker (aiodocker) or isolated mock workspace."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any

import structlog

from agents.teaching.education_models import ContainerInfo, NetworkConfig, SandboxArtifact, Snapshot

logger = structlog.get_logger(__name__)

try:
    import aiodocker  # type: ignore[import-not-found]
except ImportError:
    aiodocker = None


def _use_real_docker() -> bool:
    return os.environ.get("TUTORIAL_USE_DOCKER_SANDBOX", "").strip() == "1" and aiodocker is not None


def _workspace_root(config: dict[str, Any]) -> Path:
    raw = config.get("sandbox_workspace_root") or os.environ.get("TUTORIAL_SANDBOX_ROOT")
    base = Path(raw).expanduser() if raw else Path(os.environ.get("TMPDIR", "/tmp")) / "tutorial_sandboxes"
    base.mkdir(parents=True, exist_ok=True)
    return base


class SandboxBuilder:
    """Builds isolated learner environments with no outbound network by default."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = dict(config or {})
        self._root = _workspace_root(self._config)
        self._snapshots: dict[str, dict[str, Any]] = {}

    async def create_container(self, image: str = "tutorial-sandbox:latest") -> ContainerInfo:
        """Create an isolated container or mock workspace."""

        cid = f"sbx-{uuid.uuid4().hex[:16]}"
        if _use_real_docker():
            return await self._create_docker_container(cid, image)
        path = self._root / cid
        path.mkdir(parents=True, exist_ok=True)
        (path / "work").mkdir(exist_ok=True)
        meta = {
            "container_id": cid,
            "image": image,
            "path": str(path),
            "mode": "mock",
            "network_isolated": True,
        }
        (path / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
        logger.info("sandbox_mock_container_created", container_id=cid)
        return ContainerInfo(container_id=cid, image=image, network_isolated=True)

    async def _create_docker_container(self, logical_id: str, image: str) -> ContainerInfo:
        assert aiodocker is not None
        client = aiodocker.Docker()
        try:
            host_config: dict[str, Any] = {
                "NetworkMode": "none",
                "Memory": 512 * 1024 * 1024,
                "NanoCpus": int(1e9),
                "StorageOpt": {"size": "5G"},
                "ReadonlyRootfs": False,
            }
            container_config: dict[str, Any] = {
                "Image": image,
                "Cmd": ["sleep", "infinity"],
                "HostConfig": host_config,
                "Labels": {"tutorial.sandbox": logical_id, "tutorial.isolation": "no-internet"},
                "Healthcheck": {
                    "Test": ["CMD-SHELL", "test -d /tmp"],
                    "Interval": 30_000_000_000,
                    "Timeout": 5_000_000_000,
                    "Retries": 3,
                },
            }
            container = await client.containers.create(config=container_config, name=logical_id)
            await container.start()
            docker_id = container.id or logical_id
            path = self._root / logical_id
            path.mkdir(parents=True, exist_ok=True)
            (path / "docker_id.txt").write_text(docker_id, encoding="utf-8")
            meta = {
                "container_id": logical_id,
                "docker_id": docker_id,
                "image": image,
                "path": str(path),
                "mode": "docker",
                "network_isolated": True,
            }
            (path / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
            return ContainerInfo(container_id=logical_id, image=image, network_isolated=True)
        finally:
            await client.close()

    def _resolve_path(self, container_id: str) -> Path:
        p = self._root / container_id
        if not p.is_dir():
            raise FileNotFoundError(f"unknown sandbox workspace: {container_id}")
        return p

    async def copy_artifacts(self, container_id: str, artifacts: list[SandboxArtifact]) -> None:
        """Materialize artifact descriptors as files under the sandbox workspace."""

        def _write() -> None:
            base = self._resolve_path(container_id) / "work"
            base.mkdir(parents=True, exist_ok=True)
            manifest: list[dict[str, Any]] = []
            for art in artifacts:
                rel = art.virtual_path.lstrip("/")
                dest = base / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                body = (
                    f"# Sandbox artifact (sanitized)\n"
                    f"id={art.id}\npath={art.virtual_path}\n{art.description}\n"
                )
                dest.write_text(body, encoding="utf-8")
                manifest.append(art.model_dump(mode="json"))
            (base / "_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        await asyncio.to_thread(_write)

    async def setup_network(self, container_id: str, config: NetworkConfig) -> None:
        """Record simulated network layout (mock) or enforce isolation (Docker)."""

        def _record() -> None:
            p = self._resolve_path(container_id)
            nc = {
                "internal_only": config.internal_only,
                "simulated_services": config.simulated_services,
            }
            (p / "network.json").write_text(json.dumps(nc), encoding="utf-8")

        await asyncio.to_thread(_record)
        if _use_real_docker():
            meta_path = self._resolve_path(container_id) / "meta.json"
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if not meta.get("network_isolated", True):
                raise RuntimeError("Docker sandboxes must remain network-isolated")

    async def install_tools(self, container_id: str, tools: list[str]) -> None:
        """Declare available forensic tools (mock writes a PATH helper script)."""

        def _install() -> None:
            base = self._resolve_path(container_id) / "work"
            script = "#!/bin/sh\n# Declared tools for this sandbox (educational)\necho " + " ".join(tools) + "\n"
            (base / ".declared_tools.sh").write_text(script, encoding="utf-8")
            (base / "tools.txt").write_text("\n".join(tools), encoding="utf-8")

        await asyncio.to_thread(_install)

    async def capture_state(self, container_id: str) -> Snapshot:
        """Capture a filesystem digest for reset."""

        def _digest() -> str:
            base = self._resolve_path(container_id) / "work"
            h = hashlib.sha256()
            for fp in sorted(base.rglob("*")):
                if fp.is_file():
                    h.update(str(fp.relative_to(base)).encode())
                    h.update(fp.read_bytes())
            return h.hexdigest()

        digest = await asyncio.to_thread(_digest)
        snap_id = f"snap-{uuid.uuid4().hex[:12]}"
        snap = Snapshot(id=snap_id, container_id=container_id, filesystem_digest=digest)
        snap_root = self._resolve_path(container_id) / "snapshots" / snap_id

        def _snapshot_copy() -> None:
            src = self._resolve_path(container_id) / "work"
            if snap_root.exists():
                shutil.rmtree(snap_root)
            snap_root.mkdir(parents=True, exist_ok=True)
            shutil.copytree(src, snap_root / "work")

        await asyncio.to_thread(_snapshot_copy)
        self._snapshots[f"{container_id}:{snap_id}"] = {"snap_root": str(snap_root / "work")}
        return snap

    async def reset_to_state(self, container_id: str, snapshot: Snapshot) -> None:
        """Reset workspace to a previously captured snapshot."""

        key = f"{container_id}:{snapshot.id}"
        data = self._snapshots.get(key)
        if not data:
            raise ValueError(f"snapshot not found for reset: {key}")

        def _reset() -> None:
            dst = self._resolve_path(container_id) / "work"
            src = Path(data["snap_root"])
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)

        await asyncio.to_thread(_reset)

    async def destroy(self, container_id: str) -> None:
        """Remove mock workspace or stop and remove Docker container."""

        path = self._root / container_id
        if not path.exists():
            return

        meta_file = path / "meta.json"
        if meta_file.exists():
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            if meta.get("mode") == "docker" and aiodocker is not None:
                docker_id = (path / "docker_id.txt").read_text(encoding="utf-8").strip()

                async def _rm() -> None:
                    client = aiodocker.Docker()
                    try:
                        c = client.containers.container(docker_id)
                        with contextlib.suppress(Exception):
                            await c.kill()
                        with contextlib.suppress(Exception):
                            await c.delete(force=True)
                    finally:
                        await client.close()

                await _rm()

        await asyncio.to_thread(shutil.rmtree, path, ignore_errors=True)

    async def health_check(self, container_id: str) -> bool:
        """Verify sandbox workspace exists and is readable."""

        def _ok() -> bool:
            try:
                p = self._resolve_path(container_id)
                return p.is_dir() and os.access(p, os.R_OK)
            except OSError:
                return False

        return await asyncio.to_thread(_ok)
