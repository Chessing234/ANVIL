"""Generate isolated, sanitized forensic sandboxes from investigations."""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from typing import Any

import structlog

from agents.teaching.education_models import (
    Challenge,
    Hint,
    NetworkConfig,
    Sandbox,
    SandboxArtifact,
    SandboxStatus,
)
from agents.teaching.narrative_types import NarrativeResult
from agents.teaching.tools.sandbox_builder import SandboxBuilder
from agents.teaching.tools.sandbox_sanitizers import SanitizationAudit, run_full_pipeline
from agents.teaching.tools.scenario_replicator import ScenarioReplicator
from config.constants import AgentType
from core.base_agent import BaseAgent
from core.message_bus import MessageBus
from shared.models import InvestigationStep

logger = structlog.get_logger(__name__)

_DEFAULT_TOOLS = ("strings", "grep", "file", "hexdump", "awk", "tcpdump", "jq", "find")


def _collect_concepts(narrative: NarrativeResult) -> list[str]:
    labels: list[str] = []
    for m in narrative.concepts_taught:
        labels.append(m.concept_id)
    arc = narrative.story.arc
    scenes = [
        arc.setup,
        *arc.rising_action,
        arc.climax,
        *arc.falling_action,
        arc.resolution,
    ]
    for scene in scenes:
        for c in scene.concepts_demonstrated:
            labels.append(c.label)
    return list(dict.fromkeys(labels))


def _build_challenges(narrative: NarrativeResult) -> list[Challenge]:
    concept_labels = _collect_concepts(narrative)
    if not concept_labels:
        concept_labels = ["incident triage"]
    out: list[Challenge] = []
    for i, label in enumerate(concept_labels[:5]):
        cid = f"chal-{uuid.uuid4().hex[:10]}"
        script = (
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            f'test -f "work/challenge_{cid}.flag"\n'
        )
        next_c: str | None = None
        if i + 1 < len(concept_labels[:5]):
            next_c = f"pending-{i+1}"
        out.append(
            Challenge(
                id=cid,
                title=f"Practice: {label}",
                description=f"Use forensic discipline to validate indicators related to {label}.",
                verification_type="find_file",
                verification_script=script,
                concept_tested=label,
                difficulty=narrative.difficulty_level,
                points=10 + i * 5,
                hints=[
                    "Start from investigation_timeline.jsonl.",
                    "Correlate suspicious_process.txt with simulated_connections.txt.",
                ],
                next_challenge_id=next_c,
            ),
        )
    return out


class SandboxGenerationAgent(BaseAgent):
    """Builds container-isolated training environments without real malware or outbound access."""

    def __init__(
        self,
        message_bus: MessageBus,
        config: dict[str, Any],
        *,
        name: str = "teaching_sandbox",
        builder: SandboxBuilder | None = None,
        replicator: ScenarioReplicator | None = None,
    ) -> None:
        super().__init__(name, AgentType.TEACHING_SANDBOX, message_bus, config)
        self._builder = builder or SandboxBuilder(config)
        self._replicator = replicator or ScenarioReplicator(self._builder, config)

    async def _run_iteration(self) -> None:
        await asyncio.sleep(0.5)

    def _extract_artifacts(
        self,
        investigation_steps: list[InvestigationStep],
        audit: SanitizationAudit,
    ) -> list[SandboxArtifact]:
        arts: list[SandboxArtifact] = []
        for idx, step in enumerate(sorted(investigation_steps, key=lambda s: s.timestamp)):
            body = "\n".join(
                x
                for x in (
                    step.raw_output or "",
                    step.interpretation or "",
                    step.action_taken,
                )
                if x
            )
            safe_body, _ = run_full_pipeline(body[:8000], audit)
            digest = None
            if body:
                digest = hashlib.sha256(body.encode()).hexdigest()[:32]
            arts.append(
                SandboxArtifact(
                    id=f"art-{step.id.hex[:8]}",
                    virtual_path=f"/lab/evidence/step_{idx:02d}.txt",
                    description=(safe_body[:400] + "…") if len(safe_body) > 400 else (safe_body or "empty step"),
                    original_hash=digest,
                    sanitized=True,
                ),
            )
        if not arts:
            safe, _ = run_full_pipeline("No investigation steps supplied.", audit)
            arts.append(
                SandboxArtifact(
                    id="art-placeholder",
                    virtual_path="/lab/evidence/overview.txt",
                    description=safe[:2000],
                    sanitized=True,
                ),
            )
        return arts

    async def generate_sandbox(
        self,
        investigation_steps: list[InvestigationStep],
        narrative: NarrativeResult,
    ) -> Sandbox:
        """Run the full pipeline: extract → sanitize → container → scenario → challenges → verify."""

        audit = SanitizationAudit()
        raw_bundle = "\n".join(
            "\n".join(filter(None, (s.raw_output, s.interpretation, s.action_taken)))
            for s in investigation_steps
        )
        sanitized_full, audit = run_full_pipeline(raw_bundle, audit)

        incident_id = str(investigation_steps[0].incident_id) if investigation_steps else "unknown"
        sandbox_id = f"sbx-{uuid.uuid4().hex[:12]}"
        artifacts = self._extract_artifacts(investigation_steps, audit)

        info = await self._builder.create_container(self._config.get("sandbox_image", "tutorial-sandbox:latest"))
        await self._builder.setup_network(
            info.container_id,
            NetworkConfig(internal_only=True, simulated_services=["local-nc"]),
        )
        await self._builder.copy_artifacts(info.container_id, artifacts)
        await self._replicator.replicate_incident(info.container_id, investigation_steps)

        challenges = _build_challenges(narrative)
        for ch in challenges:
            await self._replicator.create_challenge_scenario(info.container_id, ch)

        tools = list(self._config.get("sandbox_tools", _DEFAULT_TOOLS))
        await self._builder.install_tools(info.container_id, tools)

        ok = await self._builder.health_check(info.container_id)
        if not ok:
            raise RuntimeError("sandbox health check failed")

        hints = [
            Hint(id="h1", text="Enumerate artifacts under /work before pivoting.", unlock_after_minutes=0.0),
            Hint(id="h2", text="Timeline JSONL is authoritative for sequencing.", unlock_after_minutes=5.0),
        ]

        audit_note = json.dumps(
            {
                "sanitization_steps": len(audit.entries),
                "reversible": True,
                "aggregate_preview": sanitized_full[:200],
            },
        )
        return Sandbox(
            id=sandbox_id,
            incident_id=incident_id,
            container_id=info.container_id,
            status=SandboxStatus.READY,
            artifacts=artifacts,
            challenges=challenges,
            provided_tools=tools,
            hints=hints,
            time_limit_minutes=min(240, max(15, narrative.estimated_duration_minutes + 10)),
            sanitized=True,
            access_url=f"https://terminal.example.invalid/{sandbox_id}",
            isolation_notes=(
                "NetworkMode=none equivalent in mock; no outbound internet; artifacts sanitized. "
                f"audit={audit_note}"
            ),
        )
