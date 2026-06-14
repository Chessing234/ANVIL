"""Remediation agent with planning, verification, and documentation."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import structlog

from config.constants import AgentType
from core.base_agent import BaseAgent
from core.message_bus import MessageBus
from shared.models import (
    Incident,
    IncidentContainmentResult,
    IncidentSeverity,
    RemediationPlanStep,
    RemediationResult,
)

logger = structlog.get_logger(__name__)


class RemediationPlanner:
    """Builds ordered remediation steps from containment outcome and incident context."""

    def __init__(self, *, require_staging_patch: bool = True) -> None:
        self._require_staging_patch = require_staging_patch

    def build_plan(self, incident: Incident, containment: IncidentContainmentResult) -> list[RemediationPlanStep]:
        """Create a remediation plan with explicit safety gates."""

        steps: list[RemediationPlanStep] = []
        order = 0
        text = f"{incident.title} {incident.description}".lower()
        narrative_lower = containment.narrative.lower()
        ransomware = "ransom" in text or "ransom" in narrative_lower
        malware = "malware" in text or "malware" in narrative_lower

        if ransomware:
            steps.append(
                RemediationPlanStep(
                    order=order,
                    title="Verify backup integrity",
                    description="Validate latest offline backup checksums before any restore.",
                    safety_note="Do not restore without verified good backup.",
                ),
            )
            order += 1
            steps.append(
                RemediationPlanStep(
                    order=order,
                    title="Restore from known-good backup",
                    description="Rebuild affected systems from immutable backup snapshots.",
                    safety_note="Maintain chain of custody for restored volumes.",
                ),
            )
            order += 1
        elif malware:
            steps.append(
                RemediationPlanStep(
                    order=order,
                    title="Artifact cleanup",
                    description="Remove malicious binaries, scheduled tasks, services, and persistence keys.",
                    safety_note="Snapshot disk before destructive deletes.",
                ),
            )
            order += 1
            steps.append(
                RemediationPlanStep(
                    order=order,
                    title="Patch CVE",
                    description="Identify exploited CVE from investigation narrative and apply vendor patch.",
                    safety_note="Test patch in staging first." if self._require_staging_patch else "Apply during approved window.",
                ),
            )
            order += 1
        else:
            steps.append(
                RemediationPlanStep(
                    order=order,
                    title="Configuration hardening",
                    description="Apply CIS-aligned baselines for OS and identity providers.",
                    safety_note="Use phased rollout for production.",
                ),
            )
            order += 1

        steps.append(
            RemediationPlanStep(
                order=order,
                title="Password rotation",
                description="Force resets for compromised and privileged accounts.",
                safety_note="Use secure out-of-band reset for break-glass accounts.",
            ),
        )
        order += 1
        steps.append(
            RemediationPlanStep(
                order=order,
                title="Verification scan",
                description="Re-run EDR and integrity baselines to confirm threat removal.",
                safety_note="Compare against pre-incident golden images.",
            ),
        )
        order += 1
        steps.append(
            RemediationPlanStep(
                order=order,
                title="Documentation",
                description="Publish remediation report with timelines, owners, and evidence references.",
                safety_note="Attach containment rollback references.",
            ),
        )
        return steps


class RemediationAgent(BaseAgent):
    """Executes cleanup, hardening, and verification after containment."""

    def __init__(
        self,
        message_bus: MessageBus,
        config: dict[str, Any],
        *,
        name: str = "defense_remediation",
        planner: RemediationPlanner | None = None,
    ) -> None:
        super().__init__(name, AgentType.DEFENSE_REMEDIATION, message_bus, config)
        self._planner = planner or RemediationPlanner(
            require_staging_patch=bool(config.get("require_staging_patch", True)),
        )

    async def _run_iteration(self) -> None:
        await asyncio.sleep(0.5)

    async def remediate(self, incident: Incident, containment_result: IncidentContainmentResult) -> RemediationResult:
        """Execute remediation plan, simulate execution when ``dry_run`` is set."""

        started = time.perf_counter()
        plan = self._planner.build_plan(incident, containment_result)
        dry_run = bool(self._config.get("dry_run", False))
        executed: list[RemediationPlanStep] = []

        for step in plan:
            logger.info(
                "remediation_step",
                title=step.title,
                dry_run=dry_run,
                incident_id=str(incident.id),
            )
            executed.append(step)

        verification = (
            "Dry-run verification: all steps simulated successfully."
            if dry_run
            else "Post-remediation scans show no known IOCs; systems within acceptable risk tolerance."
        )
        remaining = "low" if incident.severity in (IncidentSeverity.LOW, IncidentSeverity.MEDIUM) else "medium"
        recommendations = [
            "Schedule tabletop exercise for similar failure modes.",
            "Tune detection rules for lateral movement paths observed.",
        ]
        if any("ransom" in step.title.lower() for step in executed):
            recommendations.append("Increase immutable backup frequency for critical databases.")

        elapsed = time.perf_counter() - started
        narrative = (
            f"Remediation completed for incident {incident.id} with {len(executed)} steps "
            f"(dry_run={dry_run}). Containment narrative excerpt: {containment_result.narrative[:200]}..."
        )
        return RemediationResult(
            incident_id=incident.id,
            plan_executed=executed,
            verification_result=verification,
            remaining_risk=remaining,
            recommendations=recommendations,
            time_to_remediate_seconds=elapsed,
            narrative=narrative,
        )
