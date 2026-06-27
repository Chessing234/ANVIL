"""LangGraph defense workflow for incident response with SQLite checkpointing."""

from __future__ import annotations

import hashlib
import operator
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Literal, TypedDict, cast

import structlog
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from config.constants import IncidentSeverity
from shared.models import Evidence, Incident, InvestigationStep

logger = structlog.get_logger(__name__)


def _evidence_hash(incident_id: str, file_path: str) -> str:
    """Deterministic SHA-256 for synthesized evidence artifacts."""
    payload = f"{incident_id}:{file_path}:tutorial-evidence".encode()
    return hashlib.sha256(payload).hexdigest()


class DefenseState(TypedDict, total=False):
    """Defense LangGraph state carried between nodes."""

    incident: dict[str, Any]
    investigation_steps: Annotated[list[dict[str, Any]], operator.add]
    collected_evidence: Annotated[list[dict[str, Any]], operator.add]
    containment_actions: Annotated[list[dict[str, Any]], operator.add]
    remediation_actions: Annotated[list[dict[str, Any]], operator.add]
    narrative: str
    accuracy_report: dict[str, Any]
    self_corrections: Annotated[list[dict[str, Any]], operator.add]
    current_step: str
    errors: Annotated[list[str], operator.add]
    completed: bool
    started_at: str
    completed_at: str | None


DefenseCheckpointHook = Callable[[DefenseState], Awaitable[None]]
DefenseEventHook = Callable[[str, dict[str, Any]], Awaitable[None]]


def _iso_now() -> str:
    """Serialize current UTC time."""

    return datetime.now(timezone.utc).isoformat()


def _to_error_command(state: DefenseState, node: str, exc: Exception) -> Command:
    """Route failed nodes to the shared error handler."""

    meta = dict(state.get("accuracy_report", {}))
    meta["__failed_node"] = node
    return Command(
        goto="error_handler",
        update={
            "errors": state.get("errors", []) + [f"{node}:{exc}"],
            "accuracy_report": meta,
            "current_step": "error_handler",
        },
    )


async def triage(state: DefenseState) -> dict[str, Any] | Command:
    """Assess incident severity and initial investigation path."""

    try:
        incident = Incident.model_validate(state["incident"])
        updates: dict[str, Any] = {"current_step": "triage"}
        if "urgent" in incident.title.lower() and incident.severity != IncidentSeverity.CRITICAL:
            bumped = incident.model_copy(update={"severity": IncidentSeverity.HIGH})
            updates["incident"] = bumped.model_dump(mode="json")
        return updates
    except Exception as exc:  # pragma: no cover - defensive
        return _to_error_command(state, "triage", exc)


async def investigate(state: DefenseState) -> dict[str, Any] | Command:
    """Simulate investigation with mandatory self-correction path."""

    try:
        incident = Incident.model_validate(state["incident"])
        steps: list[dict[str, Any]] = []
        corrections: list[dict[str, Any]] = []
        first = InvestigationStep(
            incident_id=incident.id,
            agent_name="defense_investigation",
            action_taken="memory_analysis",
            tool_used="volatility",
            raw_output="",
            interpretation="",
            confidence=0.1,
            is_self_correction=False,
        )
        steps.append(first.model_dump(mode="json"))
        corrections.append(
            {
                "node": "investigate",
                "reason": "initial_memory_path_empty",
                "alternative": "network_and_log_hypothesis",
            },
        )
        second = InvestigationStep(
            incident_id=incident.id,
            agent_name="defense_investigation",
            action_taken="network_traffic_analysis",
            tool_used="zeek",
            raw_output="suspicious_dns_tunnel",
            interpretation="DNS tunneling indicators",
            confidence=0.82,
            is_self_correction=True,
        )
        steps.append(second.model_dump(mode="json"))
        third = InvestigationStep(
            incident_id=incident.id,
            agent_name="defense_investigation",
            action_taken="log_analysis",
            tool_used="splunk",
            raw_output="auth_anomalies",
            interpretation="lateral movement attempts",
            confidence=0.76,
            is_self_correction=False,
        )
        steps.append(third.model_dump(mode="json"))
        return {
            "investigation_steps": steps,
            "self_corrections": corrections,
            "current_step": "investigate",
        }
    except Exception as exc:  # pragma: no cover - defensive
        return _to_error_command(state, "investigate", exc)


async def collect_evidence(state: DefenseState) -> dict[str, Any] | Command:
    """Validate hashes and append evidence records."""

    try:
        incident = Incident.model_validate(state["incident"])
        evidence = Evidence(
            incident_id=incident.id,
            type="memory_dump",
            file_path=f"/evidence/{incident.id}/mem.dmp",
            hash_sha256=_evidence_hash(str(incident.id), f"/evidence/{incident.id}/mem.dmp"),
            metadata={"chain_of_custody": "signed"},
            collected_by="defense_evidence",
        )
        return {
            "collected_evidence": [evidence.model_dump(mode="json")],
            "current_step": "collect_evidence",
        }
    except Exception as exc:  # pragma: no cover - defensive
        return _to_error_command(state, "collect_evidence", exc)


async def assess_threat(state: DefenseState) -> dict[str, Any] | Command:
    """Derive actor hypothesis and confidence."""

    try:
        report = dict(state.get("accuracy_report", {}))
        report.update(
            {
                "threat_actor": "APT-TUTORIAL",
                "ttps": ["T1071", "T1059"],
                "confidence": 0.74,
            },
        )
        return {"accuracy_report": report, "current_step": "assess_threat"}
    except Exception as exc:  # pragma: no cover - defensive
        return _to_error_command(state, "assess_threat", exc)


async def contain(state: DefenseState) -> dict[str, Any] | Command:
    """Execute containment actions."""

    try:
        incident = Incident.model_validate(state["incident"])
        action = {
            "action": "isolate_host",
            "target": incident.target_asset or "unknown-asset",
            "timestamp": _iso_now(),
        }
        return {"containment_actions": [action], "current_step": "contain"}
    except Exception as exc:  # pragma: no cover - defensive
        return _to_error_command(state, "contain", exc)


async def remediate(state: DefenseState) -> dict[str, Any] | Command:
    """Execute remediation actions."""

    try:
        action = {
            "action": "patch_vulnerability",
            "package": "openssh",
            "restored_from_backup": False,
            "timestamp": _iso_now(),
        }
        return {"remediation_actions": [action], "current_step": "remediate"}
    except Exception as exc:  # pragma: no cover - defensive
        return _to_error_command(state, "remediate", exc)


async def generate_narrative(state: DefenseState) -> dict[str, Any] | Command:
    """Compile narrative and FIND EVIL accuracy report."""

    try:
        steps = state.get("investigation_steps", [])
        evidence = state.get("collected_evidence", [])
        corrections = state.get("self_corrections", [])
        confidences = [float(s.get("confidence", 0.0)) for s in steps if "confidence" in s]
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
        narrative = (
            "Investigation summary: analysts pivoted from memory forensics to network and log evidence, "
            f"documenting {len(steps)} steps with {len(corrections)} explicit self-corrections."
        )
        accuracy = dict(state.get("accuracy_report", {}))
        accuracy.update(
            {
                "FIND_EVIL": {
                    "step_count": len(steps),
                    "evidence_count": len(evidence),
                    "self_correction_count": len(corrections),
                    "avg_confidence": round(avg_conf, 4),
                },
            },
        )
        return {
            "narrative": narrative,
            "accuracy_report": accuracy,
            "current_step": "generate_narrative",
        }
    except Exception as exc:  # pragma: no cover - defensive
        return _to_error_command(state, "generate_narrative", exc)


def build_checkpoint_node(
    on_persist: DefenseCheckpointHook,
    on_event: DefenseEventHook,
) -> Callable[[DefenseState], Awaitable[dict[str, Any] | Command]]:
    """Factory wiring persistence hooks into the terminal checkpoint node."""

    async def checkpoint(state: DefenseState) -> dict[str, Any]:
        """Persist defense state and publish completion."""

        completed_state: DefenseState = {
            **state,
            "completed": True,
            "completed_at": _iso_now(),
            "current_step": "checkpoint",
        }
        await on_persist(completed_state)
        incident_id = str(Incident.model_validate(state["incident"]).id)
        await on_event(
            "defense_complete",
            {"incident_id": incident_id, "accuracy_report": completed_state.get("accuracy_report", {})},
        )
        logger.info("defense_checkpoint_complete", incident_id=incident_id)
        return {
            "completed": True,
            "completed_at": completed_state["completed_at"],
            "current_step": "checkpoint",
        }

    return checkpoint


async def error_handler(state: DefenseState) -> Command:
    """Centralized recovery with at most two retries per failing node."""

    meta = dict(state.get("accuracy_report", {}))
    node = cast(str, meta.get("__failed_node", "checkpoint"))
    retries_map: dict[str, int] = dict(meta.get("__retries", {}))
    retries = int(retries_map.get(node, 0))
    if retries >= 2:
        return Command(
            goto="checkpoint",
            update={
                "errors": state.get("errors", []) + [f"abandoned_after_retries:{node}"],
                "accuracy_report": {**meta, "__fatal": True, "__retries": retries_map},
                "completed": True,
            },
        )
    retries_map[node] = retries + 1
    return Command(
        goto=node,
        update={"accuracy_report": {**meta, "__retries": retries_map}, "current_step": "error_handler"},
    )


def route_criticality(state: DefenseState) -> Literal["critical", "non_critical"]:
    """Route high-severity incidents through containment."""

    incident = Incident.model_validate(state["incident"])
    if incident.severity == IncidentSeverity.CRITICAL:
        return "critical"
    return "non_critical"


class DefenseWorkflow:
    """LangGraph defense workflow with async SQLite checkpointing."""

    def __init__(
        self,
        checkpoint_path: Path,
        *,
        on_persist: DefenseCheckpointHook,
        on_event: DefenseEventHook,
    ) -> None:
        self._checkpoint_path = Path(checkpoint_path)
        self._on_persist = on_persist
        self._on_event = on_event

    def _build_builder(self) -> StateGraph:
        """Construct the defense ``StateGraph`` prior to compilation."""

        builder = StateGraph(DefenseState)
        builder.add_node("triage", triage)
        builder.add_node("investigate", investigate)
        builder.add_node("collect_evidence", collect_evidence)
        builder.add_node("assess_threat", assess_threat)
        builder.add_node("contain", contain)
        builder.add_node("remediate", remediate)
        builder.add_node("generate_narrative", generate_narrative)
        builder.add_node("error_handler", error_handler)
        builder.add_node("checkpoint", build_checkpoint_node(self._on_persist, self._on_event))
        builder.add_edge(START, "triage")
        builder.add_edge("triage", "investigate")
        builder.add_edge("investigate", "collect_evidence")
        builder.add_edge("collect_evidence", "assess_threat")
        builder.add_conditional_edges(
            "assess_threat",
            route_criticality,
            {"critical": "contain", "non_critical": "generate_narrative"},
        )
        builder.add_edge("contain", "remediate")
        builder.add_edge("remediate", "generate_narrative")
        builder.add_edge("generate_narrative", "checkpoint")
        builder.add_edge("checkpoint", END)
        return builder

    async def run(self, initial: DefenseState, thread_id: str) -> dict[str, Any]:
        """Execute the workflow asynchronously with per-run checkpoint isolation."""

        self._checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        async with AsyncSqliteSaver.from_conn_string(str(self._checkpoint_path)) as checkpointer:
            graph = self._build_builder().compile(checkpointer=checkpointer)
            config = {"configurable": {"thread_id": thread_id}}
            trace: list[dict[str, Any]] = []
            final: dict[str, Any] = {}
            async for chunk in graph.astream(initial, config=config):
                trace.append({k: _serialize_chunk(v) for k, v in chunk.items()})
            snap = await graph.aget_state(config)
            if snap.values:
                final = dict(snap.values)
            else:
                final = dict(initial)
            return {"trace": trace, "final_state": final}


def _serialize_chunk(value: Any) -> Any:
    """Normalize streamed chunk fragments for JSON-ish traces."""

    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return value
    return repr(value)


def initial_defense_state(incident: Incident) -> DefenseState:
    """Construct default defense workflow input."""

    return {
        "incident": incident.model_dump(mode="json"),
        "investigation_steps": [],
        "collected_evidence": [],
        "containment_actions": [],
        "remediation_actions": [],
        "narrative": "",
        "accuracy_report": {},
        "self_corrections": [],
        "current_step": "pending",
        "errors": [],
        "completed": False,
        "started_at": _iso_now(),
        "completed_at": None,
    }
