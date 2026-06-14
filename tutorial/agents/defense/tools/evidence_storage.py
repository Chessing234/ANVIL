"""Secure on-disk evidence vault with optional XOR obfuscation and metadata sidecars."""

from __future__ import annotations

import asyncio
import json
import os
import secrets
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import structlog

from shared.models import Evidence

logger = structlog.get_logger(__name__)

DEFAULT_STORE_REL = Path.home() / ".tutorial_evidence_store"


def _xor_transform(data: bytes, key_material: bytes) -> bytes:
    """Deterministic XOR stream using SHA-256 blocks (stdlib-only obfuscation)."""

    import hashlib

    out = bytearray(len(data))
    offset = 0
    block_idx = 0
    while offset < len(data):
        block = hashlib.sha256(key_material + block_idx.to_bytes(4, "big")).digest()
        for j in range(len(block)):
            if offset + j >= len(data):
                break
            out[offset + j] = data[offset + j] ^ block[j]
        offset += len(block)
        block_idx += 1
    return bytes(out)


class EvidenceVault:
    """Stores evidence under ``incident_id/evidence_type/evidence_id/`` with integrity metadata."""

    def __init__(
        self,
        root: Path | None = None,
        *,
        vault_secret: str | None = None,
    ) -> None:
        raw = os.environ.get("EVIDENCE_STORE_PATH")
        self._root = Path(raw).expanduser() if raw else (root or DEFAULT_STORE_REL)
        self._root = self._root.resolve()
        self._vault_secret = vault_secret or os.environ.get("EVIDENCE_VAULT_SECRET", "tutorial-dev-secret-change-me")

    def _key(self, incident_id: UUID) -> bytes:
        import hashlib

        return hashlib.sha256(f"{self._vault_secret}:{incident_id}".encode()).digest()

    @staticmethod
    def _meta_path(data_path: Path) -> Path:
        return data_path.with_suffix(data_path.suffix + ".meta.json")

    def _find_artifact_sync(self, evidence_id: str) -> tuple[Path, dict[str, Any]]:
        self._root.mkdir(parents=True, exist_ok=True)
        for meta_file in self._root.rglob("*.meta.json"):
            if meta_file.parent.name != evidence_id:
                continue
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            stem = meta_file.name.replace(".meta.json", "")
            data_path = meta_file.parent / stem
            if data_path.is_file():
                return data_path, meta
        raise FileNotFoundError(evidence_id)

    async def store(
        self,
        file_path: str,
        incident_id: UUID,
        evidence_type: str,
        metadata: dict[str, Any],
        *,
        collected_by: str,
        encrypt: bool = True,
        evidence_id: UUID | None = None,
    ) -> Evidence:
        """Copy ``file_path`` into the vault and return catalogued ``Evidence``."""

        src = Path(file_path).expanduser().resolve()
        if not src.is_file():
            raise FileNotFoundError(str(src))

        def _write() -> Evidence:
            self._root.mkdir(parents=True, exist_ok=True)
            eid = evidence_id or uuid4()
            dest_dir = self._root / str(incident_id) / evidence_type / str(eid)
            dest_dir.mkdir(parents=True, exist_ok=True)
            data_path = dest_dir / "artifact.bin"
            plain = src.read_bytes()
            import hashlib

            digest = hashlib.sha256(plain).hexdigest()
            payload = _xor_transform(plain, self._key(incident_id)) if encrypt else plain
            data_path.write_bytes(payload)
            os.chmod(data_path, 0o600)
            meta: dict[str, Any] = {
                **metadata,
                "incident_id": str(incident_id),
                "evidence_id": str(eid),
                "vault_relative": str(data_path.relative_to(self._root)),
                "source_path": str(src),
                "encrypted": bool(encrypt),
                "hash_sha256": digest,
                "collected_by": collected_by,
            }
            EvidenceVault._meta_path(data_path).write_text(json.dumps(meta, indent=2), encoding="utf-8")
            os.chmod(EvidenceVault._meta_path(data_path), 0o600)
            return Evidence(
                id=eid,
                incident_id=incident_id,
                type=evidence_type,  # type: ignore[arg-type]
                file_path=str(data_path),
                hash_sha256=digest,
                metadata=meta,
                collected_by=collected_by,
            )

        return await asyncio.to_thread(_write)

    async def retrieve(self, evidence_id: str) -> Path:
        """Return the on-disk vault path for ``evidence_id`` (UUID string)."""

        def _get() -> Path:
            path, _meta = self._find_artifact_sync(evidence_id)
            return path

        return await asyncio.to_thread(_get)

    async def verify_integrity(self, evidence_id: str) -> bool:
        """Re-hash decrypted payload and compare to catalogued SHA-256."""

        def _check() -> bool:
            import hashlib

            path, meta = self._find_artifact_sync(evidence_id)
            incident_id = UUID(str(meta["incident_id"]))
            blob = path.read_bytes()
            plain = _xor_transform(blob, self._key(incident_id)) if meta.get("encrypted", True) else blob
            return hashlib.sha256(plain).hexdigest() == str(meta.get("hash_sha256", ""))

        try:
            return await asyncio.to_thread(_check)
        except FileNotFoundError:
            return False
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            logger.warning("vault_verify_failed", error=str(exc))
            return False

    async def list_evidence(self, incident_id: str | None = None) -> list[Evidence]:
        """List catalogued evidence, optionally filtered by ``incident_id``."""

        def _scan() -> list[Evidence]:
            found: list[Evidence] = []
            for meta_file in self._root.rglob("*.meta.json"):
                try:
                    data = json.loads(meta_file.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if incident_id and str(data.get("incident_id")) != incident_id:
                    continue
                try:
                    eid = UUID(meta_file.parent.name)
                    inc = UUID(str(data["incident_id"]))
                except (KeyError, ValueError):
                    continue
                et = meta_file.parent.parent.name
                stem = meta_file.name.replace(".meta.json", "")
                data_path = meta_file.parent / stem
                hx = str(data.get("hash_sha256", ""))
                if len(hx) != 64:
                    continue
                found.append(
                    Evidence(
                        id=eid,
                        incident_id=inc,
                        type=et,  # type: ignore[arg-type]
                        file_path=str(data_path),
                        hash_sha256=hx,
                        metadata=data,
                        collected_by=str(data.get("collected_by", "vault")),
                    ),
                )
            return found

        return await asyncio.to_thread(_scan)

    async def delete(self, evidence_id: str) -> bool:
        """Overwrite vault bytes then remove artifact and metadata."""

        try:
            path, _meta = await asyncio.to_thread(self._find_artifact_sync, evidence_id)
        except FileNotFoundError:
            return False
        meta_path = self._meta_path(path)

        def _wipe() -> None:
            if path.is_file():
                size = path.stat().st_size
                path.write_bytes(secrets.token_bytes(size))
                path.unlink()
            if meta_path.is_file():
                meta_path.unlink()
            try:
                path.parent.rmdir()
            except OSError:
                pass

        await asyncio.to_thread(_wipe)
        return True
