"""Evidence collection agent with chain-of-custody and vault storage."""

from __future__ import annotations

import asyncio
import re
import shutil
from pathlib import Path
from typing import Any
from uuid import uuid4

import structlog

from agents.defense.tools.chain_of_custody import CustodyChain
from agents.defense.tools.evidence_storage import EvidenceVault
from config.constants import AgentType, EventType
from core.base_agent import BaseAgent
from core.message_bus import MessageBus
from shared.models import CustodyAction, CustodyEntry, Evidence, Incident, InvestigationStep
from shared.utils import compute_file_hash

logger = structlog.get_logger(__name__)

_PATH_RE = re.compile(r"(?:^|\s)(/[^\s\n\"']+\.(?:pcap|cap|dmp|raw|img|vhd|vmdk|log|txt|json|jsonl|evtx))\b")


def _infer_evidence_type(path: Path) -> str:
    suf = path.suffix.lower()
    if suf in {".pcap", ".cap"}:
        return "network_capture"
    if suf in {".dmp", ".raw"}:
        return "memory_dump"
    if suf in {".img", ".vhd", ".vmdk"}:
        return "disk_image"
    return "log_file"


class EvidenceCollectionAgent(BaseAgent):
    """Collects forensic artifacts with hashing, custody logging, and vault storage."""

    def __init__(
        self,
        message_bus: MessageBus,
        config: dict[str, Any],
        *,
        name: str = "defense_evidence_collection",
        vault: EvidenceVault | None = None,
        custody_chain: CustodyChain | None = None,
    ) -> None:
        super().__init__(name, AgentType.DEFENSE_EVIDENCE, message_bus, config)
        custody_path = Path(
            str(config.get("custody_db_path", Path(config.get("evidence_root", ".")) / "custody.sqlite3")),
        )
        self._custody = custody_chain or CustodyChain(custody_path)
        self._vault = vault or EvidenceVault(Path(config.get("evidence_vault_root")) if config.get("evidence_vault_root") else None)

    async def _run_iteration(self) -> None:
        """Idle unless driven by explicit ``collect`` calls from orchestration."""

        await asyncio.sleep(0.5)

    def _identify_sources(self, incident: Incident, steps: list[InvestigationStep]) -> list[Path]:
        seen: set[str] = set()
        paths: list[Path] = []
        for ref in incident.raw_evidence_refs:
            p = Path(ref).expanduser()
            key = str(p.resolve()) if p.is_file() else str(p)
            if key not in seen:
                seen.add(key)
                paths.append(p)
        for step in steps:
            blob = " ".join(filter(None, [step.raw_output or "", step.interpretation or "", step.action_taken]))
            for m in _PATH_RE.finditer(blob):
                p = Path(m.group(1)).expanduser()
                key = str(p.resolve()) if p.is_file() else str(p)
                if key not in seen:
                    seen.add(key)
                    paths.append(p)
        return paths

    async def _copy_artifact(self, src: Path, dst: Path, evidence_type: str) -> None:
        """Forensically sound copy: ``dd`` for disk images on Unix when available, else buffered copy."""

        dst.parent.mkdir(parents=True, exist_ok=True)
        if evidence_type == "disk_image" and shutil.which("dd"):
            proc = await asyncio.create_subprocess_exec(
                "dd",
                f"if={src}",
                f"of={dst}",
                "bs=1m",
                "conv=noerror,sync",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                await asyncio.wait_for(proc.wait(), timeout=300.0)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                raise
            if proc.returncode != 0:
                raise RuntimeError("dd copy failed")
            return

        def _shutil_copy() -> None:
            shutil.copy2(src, dst)

        await asyncio.to_thread(_shutil_copy)

    async def collect(self, incident: Incident, investigation_steps: list[InvestigationStep]) -> list[Evidence]:
        """Identify sources from investigation output, copy with integrity checks, vault, and custody log."""

        collected: list[Evidence] = []
        sources = self._identify_sources(incident, investigation_steps)
        lines: list[str] = []

        for src in sources:
            if not src.is_file():
                lines.append(f"SKIP missing: {src}")
                logger.warning("evidence_missing", path=str(src))
                continue
            evidence_type = _infer_evidence_type(src)
            eid = uuid4()
            hb = compute_file_hash(str(src))
            await self._custody.append(
                CustodyEntry(
                    action=CustodyAction.COLLECTED,
                    performed_by=self.name,
                    evidence_id=str(eid),
                    hash_before=None,
                    hash_after=hb,
                    location=str(src.resolve()),
                    notes=f"Source identified as {evidence_type}",
                ),
            )
            staging = Path(self._config.get("staging_dir", "/tmp/tutorial_evidence_stage"))
            staging.mkdir(parents=True, exist_ok=True)
            staged = staging / f"{incident.id}_{src.name}"
            await self._copy_artifact(src.resolve(), staged, evidence_type)
            ha = compute_file_hash(str(staged))
            if ha != hb:
                lines.append(f"HASH_MISMATCH {src}: before={hb} after={ha}")
                await self._custody.append(
                    CustodyEntry(
                        action=CustodyAction.VERIFIED,
                        performed_by=self.name,
                        evidence_id=str(eid),
                        hash_before=hb,
                        hash_after=ha,
                        location=str(staged),
                        notes="Integrity mismatch after copy — aborting vault for this artifact",
                    ),
                )
                if staged.is_file():
                    staged.unlink()
                continue

            await self._custody.append(
                CustodyEntry(
                    action=CustodyAction.COPIED,
                    performed_by=self.name,
                    evidence_id=str(eid),
                    hash_before=hb,
                    hash_after=ha,
                    location=str(staged),
                    notes="Verified copy to staging",
                ),
            )

            ev = await self._vault.store(
                str(staged),
                incident.id,
                evidence_type,
                {"original_path": str(src.resolve()), "staging_path": str(staged)},
                collected_by=self.name,
                encrypt=bool(self._config.get("encrypt_evidence", True)),
                evidence_id=eid,
            )
            lines.append(f"STORED {ev.id} type={evidence_type} hash={ev.hash_sha256}")
            await self._custody.append(
                CustodyEntry(
                    action=CustodyAction.VERIFIED,
                    performed_by=self.name,
                    evidence_id=str(ev.id),
                    hash_before=hb,
                    hash_after=ev.hash_sha256,
                    location=ev.file_path,
                    notes="Vault storage integrity hash (plaintext pre-encryption)",
                ),
            )
            collected.append(ev)
            if staged.is_file():
                staged.unlink()

        report = "\n".join(lines) if lines else "No artifacts collected."
        if collected:
            collected[0].metadata["evidence_collection_report"] = report
        await self.publish_event(
            EventType.EVIDENCE_COLLECTED,
            {"incident_id": str(incident.id), "report": report, "count": len(collected)},
        )
        return collected
