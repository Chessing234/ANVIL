"""Replicate sanitized incident states inside a sandbox workspace."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import structlog

from agents.teaching.education_models import Challenge
from agents.teaching.tools.sandbox_builder import SandboxBuilder
from shared.models import InvestigationStep

logger = structlog.get_logger(__name__)


class ScenarioReplicator:
    """Creates realistic-looking but benign forensic scenarios for learners."""

    def __init__(self, builder: SandboxBuilder | None = None, config: dict | None = None) -> None:
        self._builder = builder or SandboxBuilder(config)

    def _work(self, container_id: str) -> Path:
        return self._builder._resolve_path(container_id) / "work"

    async def replicate_incident(
        self,
        container_id: str,
        investigation_steps: list[InvestigationStep],
    ) -> None:
        """Lay down benign logs, faux suspicious process metadata, and artifact summaries."""

        def _write() -> None:
            work = self._work(container_id)
            work.mkdir(parents=True, exist_ok=True)
            lines: list[str] = []
            for i, step in enumerate(sorted(investigation_steps, key=lambda s: s.timestamp)):
                lines.append(
                    json.dumps(
                        {
                            "seq": i,
                            "action": step.action_taken,
                            "tool": step.tool_used,
                            "interpretation": (step.interpretation or "")[:2000],
                            "confidence": step.confidence,
                        },
                    ),
                )
            (work / "investigation_timeline.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
            (work / "suspicious_process.txt").write_text(
                "pid=9999 comm=benign_lookup.bin args=strings /var/log/auth.log\n"
                "(benign binary renamed for training — not malware)\n",
                encoding="utf-8",
            )
            (work / "simulated_connections.txt").write_text(
                "proto=tcp dst=192.0.2.10:4444 state=LISTEN (local netcat lab listener; no internet)\n",
                encoding="utf-8",
            )
            high_entropy = "".join(f"{(i * 17) % 256:02x}" for i in range(128))
            (work / "entropy_sample.dat").write_text(
                f"# Benign high-entropy training blob\n{high_entropy}\n",
                encoding="utf-8",
            )
            logger.info("scenario_replicated", container_id=container_id, steps=len(investigation_steps))

        await asyncio.to_thread(_write)

    async def create_challenge_scenario(self, container_id: str, challenge: Challenge) -> None:
        """Prepare workspace checks for a specific ``Challenge``."""

        def _prep() -> None:
            work = self._work(container_id)
            marker = work / f"challenge_{challenge.id}.flag"
            marker.write_text(f"challenge={challenge.id}\nverification={challenge.verification_type}\n", encoding="utf-8")
            script_dir = work / "checks"
            script_dir.mkdir(exist_ok=True)
            (script_dir / f"{challenge.id}.sh").write_text(challenge.verification_script + "\n", encoding="utf-8")

        await asyncio.to_thread(_prep)
