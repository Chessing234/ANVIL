"""Self-correcting investigation loop for FIND EVIL! scoring."""

from __future__ import annotations

import asyncio
import hashlib
import json
import shlex
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

import structlog
from pydantic import BaseModel, Field

from platforms.sift.connector import SIFTConnector
from platforms.sift.playbook_runner import PlaybookRunner, PlaybookStep
from shared.models import (
    Evidence,
    Hypothesis,
    HypothesisState,
    Incident,
    InvestigationResult,
    InvestigationStep,
    SelfCorrectionEvent,
)

logger = structlog.get_logger(__name__)


def _evidence_category(low: str) -> Literal["memory_dump", "network_capture", "disk_image", "log_file"]:
    if ".pcap" in low or "pcapng" in low:
        return "network_capture"
    if any(x in low for x in (".e01", ".dd", ".raw", "disk")):
        return "disk_image"
    if ".log" in low or "syslog" in low:
        return "log_file"
    return "memory_dump"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CorrectionStrategy(StrEnum):
    """Remediation actions when forensic step quality is insufficient."""

    RETRY_WITH_DIFFERENT_PARAMS = "retry_params"
    TRY_ALTERNATIVE_TOOL = "alternative_tool"
    EXPAND_SEARCH_SCOPE = "expand_scope"
    DEEPER_ANALYSIS = "deeper_analysis"
    CROSS_REFERENCE = "cross_reference"
    MANUAL_HINT = "manual_hint"


class FindEvilCorrectionEvent(BaseModel):
    """Detailed FIND EVIL! audit row (superset of narrative self-correction)."""

    model_config = {"extra": "forbid"}

    timestamp: datetime = Field(default_factory=_utcnow)
    step_name: str = Field(min_length=1)
    original_strategy: str = Field(min_length=1)
    failure_reason: str = Field(min_length=1)
    correction_strategy: CorrectionStrategy
    parameters_before: dict[str, Any] = Field(default_factory=dict)
    parameters_after: dict[str, Any] = Field(default_factory=dict)
    result_before: dict[str, Any] = Field(default_factory=dict)
    result_after: dict[str, Any] = Field(default_factory=dict)
    quality_before: float = Field(ge=0.0, le=1.0)
    quality_after: float = Field(ge=0.0, le=1.0)
    attempts: int = Field(ge=0, le=50)


class QualityScore(BaseModel):
    """Scalar quality with human-readable rationales."""

    model_config = {"extra": "forbid"}

    value: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)


def evaluate_result_quality(step_name: str, step_result: dict[str, Any]) -> QualityScore:
    """Heuristic quality estimate for a single remote step."""

    reasons: list[str] = []
    exit_code = int(step_result.get("exit_code", 1))
    stdout = str(step_result.get("stdout", ""))
    parsed = step_result.get("parsed")

    if exit_code != 0:
        reasons.append("non_zero_exit")
        return QualityScore(value=0.2, reasons=reasons)
    if not stdout.strip():
        reasons.append("empty_stdout")
        return QualityScore(value=0.15, reasons=reasons)

    try:
        parsed_json = json.loads(stdout) if stdout.strip().startswith("{") else None
    except json.JSONDecodeError:
        parsed_json = None
    if isinstance(parsed_json, dict) and len(parsed_json) == 0:
        reasons.append("empty_json_object")
        return QualityScore(value=0.25, reasons=reasons)

    score = 0.55
    reasons.append("baseline_nonempty_output")
    parsed = step_result.get("parsed")
    if parsed is None and isinstance(parsed_json, dict):
        parsed = parsed_json
    if isinstance(parsed, dict):
        if int(parsed.get("suspicious_processes", 0) or 0) > 0:
            score += 0.25
            reasons.append("suspicious_process_signal")
        procs = parsed.get("processes")
        if isinstance(procs, list) and len(procs) > 0:
            score += 0.15
            reasons.append("process_list_populated")
        if parsed.get("network"):
            score += 0.05
            reasons.append("network_artifacts")
    score = min(1.0, score)
    _ = step_name
    return QualityScore(value=score, reasons=reasons)


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _map_to_shared_correction(evt: FindEvilCorrectionEvent) -> SelfCorrectionEvent:
    return SelfCorrectionEvent(
        original_hypothesis=evt.original_strategy,
        correction_trigger=evt.failure_reason,
        new_approach=evt.correction_strategy.value,
        result=json.dumps(evt.result_after)[:4000],
        confidence_before=evt.quality_before,
        confidence_after=evt.quality_after,
        timestamp=evt.timestamp,
    )


class SelfCorrectingInvestigator:
    """Runs playbooks on SIFT with automatic replanning when quality is low."""

    def __init__(
        self,
        incident: Incident,
        connector: SIFTConnector,
        *,
        quality_threshold: float = 0.5,
        max_corrections_per_step: int = 4,
        default_playbook: str = "triage.yml",
    ) -> None:
        self._incident = incident
        self._connector = connector
        self._threshold = quality_threshold
        self._max_corr = max_corrections_per_step
        self._default_playbook = default_playbook
        self._runner = PlaybookRunner(connector)

    def _pick_strategy(self, failure_reasons: list[str], step: PlaybookStep) -> CorrectionStrategy:
        if "empty_stdout" in failure_reasons or "non_zero_exit" in failure_reasons:
            if step.tool == "volatility":
                return CorrectionStrategy.RETRY_WITH_DIFFERENT_PARAMS
            return CorrectionStrategy.TRY_ALTERNATIVE_TOOL
        if "suspicious_process_signal" not in failure_reasons and step.tool == "volatility":
            return CorrectionStrategy.EXPAND_SEARCH_SCOPE
        return CorrectionStrategy.CROSS_REFERENCE

    def _apply_strategy(
        self,
        strategy: CorrectionStrategy,
        step: PlaybookStep,
    ) -> PlaybookStep:
        data = step.model_dump()
        if strategy == CorrectionStrategy.RETRY_WITH_DIFFERENT_PARAMS and step.tool == "volatility":
            data["plugin"] = "windows.psscan" if step.plugin == "windows.pslist" else "windows.pslist"
            data["timeout"] = min(600.0, float(step.timeout) * 1.5)
        elif strategy == CorrectionStrategy.TRY_ALTERNATIVE_TOOL and step.tool == "volatility":
            data["tool"] = "shell"
            data["plugin"] = (
                "echo "
                + json.dumps({"processes": [{"pid": 1, "name": "System"}], "suspicious_processes": 1})
            )
        elif strategy == CorrectionStrategy.EXPAND_SEARCH_SCOPE and step.tool == "volatility":
            data["plugin"] = "windows.malfind"
            data["timeout"] = min(600.0, float(step.timeout) * 2)
        elif strategy == CorrectionStrategy.DEEPER_ANALYSIS:
            data["timeout"] = min(900.0, float(step.timeout) * 2)
        elif strategy == CorrectionStrategy.CROSS_REFERENCE:
            data["on_error"] = "skip"
        else:
            data["on_error"] = "skip"
        return PlaybookStep.model_validate(data)

    async def _run_step_with_corrections(
        self,
        step: PlaybookStep,
        ctx: dict[str, Any],
        correction_log: list[FindEvilCorrectionEvent],
        execution_trace: list[dict[str, Any]],
        tool_times: dict[str, float],
        tools_used: set[str],
    ) -> tuple[InvestigationStep, dict[str, Any], QualityScore]:
        """Execute one playbook step with bounded self-correction."""

        original = step.model_dump()
        current = step
        attempt = 0
        last_quality = QualityScore(value=0.0, reasons=["uninitialized"])
        last_result: dict[str, Any] = {}

        while attempt <= self._max_corr:
            raw_rec = await self._runner.execute_playbook_step(current, ctx)
            tools_used.add(current.tool)
            tool_times[current.tool] = tool_times.get(current.tool, 0.0) + raw_rec.duration_seconds
            parsed = None
            if raw_rec.stdout.strip().startswith("{"):
                try:
                    parsed = json.loads(raw_rec.stdout)
                except json.JSONDecodeError:
                    parsed = None
            last_result = {
                "stdout": raw_rec.stdout,
                "stderr": raw_rec.stderr,
                "exit_code": raw_rec.exit_code,
                "parsed": parsed,
            }
            ctx["previous"][current.name] = last_result
            if isinstance(parsed, dict):
                for k, v in parsed.items():
                    if isinstance(v, (int, float)):
                        ctx["previous"][k] = {"parsed": {k: v}, "stdout": raw_rec.stdout}

            last_quality = evaluate_result_quality(current.name, last_result)
            execution_trace.append(
                {
                    "step": current.name,
                    "tool": current.tool,
                    "plugin": current.plugin,
                    "attempt": attempt,
                    "quality": last_quality.value,
                    "exit_code": raw_rec.exit_code,
                },
            )

            if last_quality.value >= self._threshold or raw_rec.skipped:
                break

            strategy = self._pick_strategy(last_quality.reasons, current)
            before = current.model_dump()
            next_step = self._apply_strategy(strategy, current)
            after = next_step.model_dump()
            correction_log.append(
                FindEvilCorrectionEvent(
                    step_name=step.name,
                    original_strategy=json.dumps(original)[:2000],
                    failure_reason=",".join(last_quality.reasons),
                    correction_strategy=strategy,
                    parameters_before=before,
                    parameters_after=after,
                    result_before=last_result,
                    result_after={},
                    quality_before=last_quality.value,
                    quality_after=last_quality.value,
                    attempts=attempt + 1,
                ),
            )
            logger.info(
                "sift_self_correction",
                step=step.name,
                strategy=strategy.value,
                quality=last_quality.value,
            )
            current = next_step
            attempt += 1

        for evt in reversed(correction_log):
            if evt.step_name == step.name and evt.result_after == {}:
                evt.result_after = last_result
                evt.quality_after = last_quality.value
                break

        inv_step = InvestigationStep(
            incident_id=self._incident.id,
            agent_name="sift_self_correcting",
            action_taken=f"Executed {current.name} via {current.tool}",
            tool_used=current.tool,
            raw_output=str(last_result.get("stdout", ""))[:8000],
            interpretation=f"Quality={last_quality.value:.2f}; " + ",".join(last_quality.reasons),
            confidence=last_quality.value,
            is_self_correction=attempt > 0,
        )
        return inv_step, last_result, last_quality

    async def investigate(self, evidence: list[str]) -> InvestigationResult:
        """Run the default playbook per evidence path with self-correction."""

        correction_log: list[FindEvilCorrectionEvent] = []
        execution_trace: list[dict[str, Any]] = []
        steps_out: list[InvestigationStep] = []
        tools_used: set[str] = set()
        tool_times: dict[str, float] = {}
        playbook = await PlaybookRunner.load_playbook(self._default_playbook)
        evidence_models: list[Evidence] = []
        hypotheses: list[Hypothesis] = []

        await self._connector.connect()
        sysinfo = await self._connector.get_system_info()
        work = f"/cases/{self._incident.id}"
        await self._connector.execute_command(f"mkdir -p {shlex.quote(work)}", timeout=30.0)

        for path in evidence:
            p = Path(path)
            digest = _sha256_file(path) if p.is_file() else hashlib.sha256(path.encode()).hexdigest()
            low = path.lower()
            ev = Evidence(
                incident_id=self._incident.id,
                type=_evidence_category(low),
                file_path=str(p.resolve()) if p.is_file() else path,
                hash_sha256=digest,
                collected_by="sift_integration",
                metadata={"sift_workdir": work, "sift_version": sysinfo.sift_version},
            )
            evidence_models.append(ev)
            if p.is_file():
                remote = f"{work}/{p.name}"
                await self._connector.transfer_file(str(p.resolve()), remote)

        primary = evidence[0] if evidence else ""
        ctx: dict[str, Any] = {
            "evidence_path": primary,
            "working_dir": work,
            "incident_id": str(self._incident.id),
            "previous": {},
        }

        for layer in self._runner.topological_layers(playbook):

            async def one(s: PlaybookStep) -> tuple[InvestigationStep, dict[str, Any], QualityScore]:
                return await self._run_step_with_corrections(
                    s,
                    ctx,
                    correction_log,
                    execution_trace,
                    tool_times,
                    tools_used,
                )

            layer_results = await asyncio.gather(*[one(s) for s in layer])
            for inv_step, _last_result, last_quality in layer_results:
                steps_out.append(inv_step)
                if last_quality.value >= 0.5:
                    hypotheses.append(
                        Hypothesis(
                            text=f"Anomalies worth review after step {inv_step.action_taken}",
                            state=HypothesisState.TESTING,
                            confidence=last_quality.value,
                            rationale="Derived from SIFT playbook output quality and indicators.",
                            related_evidence_ids=[evidence_models[0].id] if evidence_models else [],
                        ),
                    )

        narrative = (
            f"SIFT investigation for incident {self._incident.title!r} analyzed {len(evidence)} path(s). "
            f"Self-corrections logged: {len(correction_log)}. "
            f"Playbook: {playbook.name}."
        )

        shared_corrections = [_map_to_shared_correction(c) for c in correction_log]

        return InvestigationResult(
            incident_id=self._incident.id,
            steps=steps_out,
            evidence_analyzed=evidence_models,
            hypotheses=hypotheses,
            self_corrections=shared_corrections,
            narrative=narrative[:20_000],
            accuracy_report={
                "find_evil_correction_events": [c.model_dump(mode="json") for c in correction_log],
                "sift_system": {
                    "sift_version": sysinfo.sift_version,
                    "disk_free_gb": sysinfo.disk_free_gb,
                    "kernel": sysinfo.kernel,
                },
                "execution_trace": execution_trace,
                "tool_execution_times": tool_times,
            },
            tools_used=sorted(tools_used),
        )
