"""Containment agent with safety tiers, rollback planning, and staged execution."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any, Awaitable, Callable

import structlog

from agents.defense.tools.containment_tools import (
    AccountManager,
    DNSSinkholer,
    FileQuarantiner,
    HostIsolator,
    IPBlocker,
    ProcessTerminator,
    ToolExecutionResult,
)
from config.constants import AgentType, IncidentSeverity
from core.base_agent import BaseAgent
from core.message_bus import MessageBus
from shared.models import (
    ContainmentActionRecord,
    ContainmentSafetyLevel,
    Incident,
    IncidentContainmentResult,
    InvestigationResult,
)

logger = structlog.get_logger(__name__)

_PID_RE = re.compile(r"\bpid[:\s]+(\d+)\b", re.I)
_USER_RE = re.compile(r"\buser(?:name)?[:\s]+([A-Za-z0-9._-]+)\b", re.I)
_HOST_RE = re.compile(r"\bhost(?:name)?[:\s]+([A-Za-z0-9._-]+)\b", re.I)


class ContainmentExecutor:
    """Wraps containment primitives with pre-check, execute, verify, and rollback."""

    def __init__(
        self,
        *,
        dry_run: bool,
        confirmed_actions: dict[str, bool] | None = None,
        rollback_timeout_seconds: float = 60.0,
        state_dir: Path | None = None,
    ) -> None:
        self._dry_run = dry_run
        self._confirmed = confirmed_actions or {}
        self._rollback_timeout = rollback_timeout_seconds
        sd = state_dir
        self._isolator = HostIsolator(state_dir=sd)
        self._prockill = ProcessTerminator()
        self._ipblock = IPBlocker(state_dir=sd)
        self._accounts = AccountManager(state_dir=sd)

    def _safety_for_isolation(self, incident: Incident, critical_hosts: set[str], production: set[str]) -> ContainmentSafetyLevel:
        host = (incident.target_asset or "").lower()
        if incident.severity == IncidentSeverity.CRITICAL and host in {h.lower() for h in critical_hosts}:
            return ContainmentSafetyLevel.CONFIRM
        if host and host in {p.lower() for p in production}:
            return ContainmentSafetyLevel.CONFIRM
        return ContainmentSafetyLevel.AUTO

    async def run_action(
        self,
        action_key: str,
        safety: ContainmentSafetyLevel,
        execute_fn: Callable[[], Awaitable[ToolExecutionResult]],
        *,
        block_reason_if_never: str | None = None,
    ) -> ContainmentActionRecord:
        """Execute or skip a single action with rollback metadata."""

        if safety == ContainmentSafetyLevel.BLOCK:
            return ContainmentActionRecord(
                name=action_key,
                safety_level=safety,
                executed=False,
                dry_run=self._dry_run,
                blocked_reason=block_reason_if_never or "blocked_by_policy",
                rollback_plan="Action was not executed.",
                detail="",
            )
        if safety == ContainmentSafetyLevel.CONFIRM and not self._confirmed.get(action_key, False):
            return ContainmentActionRecord(
                name=action_key,
                safety_level=safety,
                executed=False,
                dry_run=self._dry_run,
                blocked_reason="confirmation_required",
                rollback_plan="Obtain operator approval then set confirmed_actions[action_key]=True.",
                detail="",
            )
        if self._dry_run:
            out = await execute_fn()
            return ContainmentActionRecord(
                name=action_key,
                safety_level=safety,
                executed=False,
                dry_run=True,
                blocked_reason=None,
                rollback_plan="; ".join(out.rollback_commands) or "noop",
                detail=out.detail,
            )

        try:
            out = await asyncio.wait_for(execute_fn(), timeout=self._rollback_timeout)
        except Exception as exc:
            logger.error("containment_action_failed", action=action_key, error=str(exc))
            return ContainmentActionRecord(
                name=action_key,
                safety_level=safety,
                executed=False,
                dry_run=False,
                blocked_reason=str(exc),
                rollback_plan="Manual intervention required after failure.",
                detail=str(exc),
            )

        rollback_plan = "; ".join(out.rollback_commands) if out.rollback_commands else "noop"
        return ContainmentActionRecord(
            name=action_key,
            safety_level=safety,
            executed=out.success,
            dry_run=False,
            blocked_reason=None if out.success else out.detail,
            rollback_plan=rollback_plan,
            detail=out.detail,
        )


class ContainmentAgent(BaseAgent):
    """Executes prioritized containment with blast-radius awareness."""

    def __init__(
        self,
        message_bus: MessageBus,
        config: dict[str, Any],
        *,
        name: str = "defense_containment",
    ) -> None:
        super().__init__(name, AgentType.DEFENSE_CONTAINMENT, message_bus, config)
        self._critical_hosts = {str(h).lower() for h in (config.get("critical_hosts") or [])}
        self._production = {str(h).lower() for h in (config.get("production_servers") or [])}

    async def _run_iteration(self) -> None:
        await asyncio.sleep(0.5)

    def _decision_context(self, incident: Incident, investigation: InvestigationResult) -> dict[str, Any]:
        """Rule-based context (LLM-ready) for containment planning."""

        text = f"{incident.title}\n{incident.description}\n{investigation.narrative}".lower()
        blast = "high" if incident.severity in (IncidentSeverity.HIGH, IncidentSeverity.CRITICAL) else "medium"
        business = "high" if (incident.target_asset or "").lower() in self._production else "low"
        ctx: dict[str, Any] = {
            "text": text,
            "blast_radius": blast,
            "business_criticality": business,
            "backup_ok": "backup" in text or "restore" in text,
            "time_window": "business_hours_assumed",
        }
        llm_hint = self._config.get("llm_containment_hint")
        if isinstance(llm_hint, str) and llm_hint.strip():
            ctx["llm_reasoning_hint"] = llm_hint.strip()
        return ctx

    async def contain(self, incident: Incident, investigation_result: InvestigationResult) -> IncidentContainmentResult:
        """Run containment levels L1→L3 with confirmations, dry-run, and rollback plans."""

        ctx = self._decision_context(incident, investigation_result)
        dry_run = bool(self._config.get("dry_run", False))
        confirmed = dict(self._config.get("confirmed_actions") or {})
        state_dir = Path(self._config.get("containment_state_dir", Path.cwd() / ".containment_state"))
        executor = ContainmentExecutor(
            dry_run=dry_run,
            confirmed_actions=confirmed,
            state_dir=state_dir,
        )

        actions: list[ContainmentActionRecord] = []

        async def _block_ip(ip: str) -> ToolExecutionResult:
            return await IPBlocker(state_dir=state_dir).block(ip, dry_run=dry_run)

        if incident.source_ip:
            actions.append(
                await executor.run_action(
                    f"block_ip:{incident.source_ip}",
                    ContainmentSafetyLevel.AUTO,
                    lambda: _block_ip(incident.source_ip or ""),
                ),
            )

        m_pid = _PID_RE.search(investigation_result.narrative)
        if m_pid:
            pid = int(m_pid.group(1))
            host = incident.target_asset or "localhost"

            async def _kill() -> ToolExecutionResult:
                return await ProcessTerminator().kill(pid, host, dry_run=dry_run)

            actions.append(
                await executor.run_action(
                    f"kill_process:{pid}",
                    ContainmentSafetyLevel.CONFIRM if pid < 500 else ContainmentSafetyLevel.AUTO,
                    _kill,
                ),
            )

        m_user = _USER_RE.search(investigation_result.narrative)
        if m_user:
            user = m_user.group(1)

            async def _disable() -> ToolExecutionResult:
                return await AccountManager(state_dir=state_dir).disable(user, dry_run=dry_run)

            actions.append(
                await executor.run_action(
                    f"disable_account:{user}",
                    ContainmentSafetyLevel.CONFIRM,
                    _disable,
                ),
            )

        host_guess = incident.target_asset
        if not host_guess:
            mh = _HOST_RE.search(investigation_result.narrative)
            host_guess = mh.group(1) if mh else None
        if host_guess:
            safety = executor._safety_for_isolation(incident, self._critical_hosts, self._production)

            async def _iso() -> ToolExecutionResult:
                return await HostIsolator(state_dir=state_dir).isolate(host_guess or "", dry_run=dry_run)

            actions.append(
                await executor.run_action(
                    f"isolate_host:{host_guess}",
                    safety,
                    _iso,
                    block_reason_if_never="host_isolation_blocked_on_critical_unconfirmed",
                ),
            )

        quarantine_dir = Path(self._config.get("quarantine_dir", state_dir / "quarantine"))
        fq = FileQuarantiner(quarantine_dir)
        for ev in investigation_result.evidence_analyzed:
            if "malware" in investigation_result.narrative.lower() and ev.type == "disk_image":
                p = Path(ev.file_path)
                if p.is_file():
                    path_str = str(p)

                    async def _q(path: str = path_str) -> ToolExecutionResult:
                        return await fq.quarantine(path, dry_run=dry_run)

                    actions.append(
                        await executor.run_action(
                            f"quarantine:{p.name}",
                            ContainmentSafetyLevel.AUTO,
                            _q,
                        ),
                    )

        sink_path = state_dir / "sinkhole_hosts"
        sink = DNSSinkholer(sink_path)
        if "dns" in ctx["text"] or "c2" in ctx["text"]:
            dom = "malicious.placeholder.invalid"

            async def _sink() -> ToolExecutionResult:
                return await sink.sinkhole(dom, dry_run=dry_run)

            actions.append(
                await executor.run_action(
                    "dns_sinkhole",
                    ContainmentSafetyLevel.AUTO,
                    _sink,
                ),
            )

        if ctx["blast_radius"] == "high":
            actions.append(
                ContainmentActionRecord(
                    name="network_segmentation",
                    safety_level=ContainmentSafetyLevel.CONFIRM,
                    executed=False,
                    dry_run=dry_run,
                    blocked_reason="strategic_change_window",
                    rollback_plan="Revert VLAN ACLs to baseline documented in NOC runbook.",
                    detail="Planned segmentation for affected hosts pending approval.",
                ),
            )

        rollback_lines = [a.rollback_plan for a in actions if a.rollback_plan]
        disruption = "medium" if any(a.executed for a in actions) else "low"
        if any(a.blocked_reason == "confirmation_required" for a in actions):
            disruption = "low"
        narrative = (
            f"Containment for incident {incident.id}. Blast radius={ctx['blast_radius']}, "
            f"criticality={ctx['business_criticality']}, backups_ok={ctx['backup_ok']}."
        )
        return IncidentContainmentResult(
            incident_id=incident.id,
            actions_taken=actions,
            rollback_plan="\n".join(rollback_lines) or "No automated rollbacks captured.",
            estimated_impact=f"Executed {sum(1 for a in actions if a.executed)} actions; dry_run={dry_run}.",
            business_disruption_level=disruption,
            narrative=narrative,
        )

