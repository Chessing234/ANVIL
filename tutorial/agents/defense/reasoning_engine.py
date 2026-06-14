"""Self-correcting multi-path reasoning using LangGraph."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any, TypedDict

import structlog
from langgraph.graph import END, START, StateGraph

from agents.defense.hypothesis_manager import HypothesisManager
from shared.models import (
    CorrectionAction,
    Evidence,
    Hypothesis,
    Incident,
    IncidentSeverity,
    InvestigationContext,
    ReasoningResult,
)

logger = structlog.get_logger(__name__)


class _ReasoningState(TypedDict, total=False):
    evidence_summary: dict[str, Any]
    path_a_confidence: float
    path_a_detail: str
    path_b_confidence: float
    path_b_detail: str
    path_c_confidence: float
    path_c_detail: str
    divergence: bool
    needs_self_correction: bool
    final_confidence: float
    final_conclusion: str
    paths: dict[str, Any]


class ReasoningEngine:
    """Chain-of-thought with dual-path consistency and consolidation."""

    def __init__(
        self,
        mcp_registry: Any | None = None,
        llm_reason: Callable[[str], Awaitable[str | None]] | None = None,
    ) -> None:
        self._mcp_registry = mcp_registry
        self._llm_reason = llm_reason
        self._compiled = self._build_graph().compile()

    def _build_graph(self) -> StateGraph:
        builder = StateGraph(_ReasoningState)
        builder.add_node("path_a", self._node_path_a)
        builder.add_node("path_b", self._node_path_b)
        builder.add_node("compare", self._node_compare)
        builder.add_node("path_c", self._node_path_c)
        builder.add_node("consolidate", self._node_consolidate)
        builder.add_edge(START, "path_a")
        builder.add_edge("path_a", "path_b")
        builder.add_edge("path_b", "compare")
        builder.add_conditional_edges(
            "compare",
            self._route_after_compare,
            {"deep": "path_c", "done": "consolidate"},
        )
        builder.add_edge("path_c", "consolidate")
        builder.add_edge("consolidate", END)
        return builder

    @staticmethod
    async def _node_path_a(state: _ReasoningState) -> dict[str, Any]:
        summary = state.get("evidence_summary", {})
        anomalies = int(summary.get("anomaly_count", 0))
        ioc_hits = int(summary.get("ioc_match_count", 0))
        conf = min(1.0, 0.25 + anomalies * 0.12 + ioc_hits * 0.15)
        detail = f"path_a: anomalies={anomalies} ioc_hits={ioc_hits}"
        return {"path_a_confidence": conf, "path_a_detail": detail}

    @staticmethod
    async def _node_path_b(state: _ReasoningState) -> dict[str, Any]:
        summary = state.get("evidence_summary", {})
        dns = int(summary.get("dns_tunnel_signals", 0))
        beacons = int(summary.get("beacon_signals", 0))
        conf = min(1.0, 0.22 + dns * 0.18 + beacons * 0.14)
        detail = f"path_b: dns_tunnel_signals={dns} beacon_signals={beacons}"
        return {"path_b_confidence": conf, "path_b_detail": detail}

    @staticmethod
    async def _node_compare(state: _ReasoningState) -> dict[str, Any]:
        a = float(state.get("path_a_confidence", 0.0))
        b = float(state.get("path_b_confidence", 0.0))
        gap = abs(a - b)
        divergence = gap > 0.3
        weak = max(a, b) < 0.35
        needs = divergence or weak
        return {"divergence": divergence, "needs_self_correction": needs}

    @staticmethod
    def _route_after_compare(state: _ReasoningState) -> str:
        if state.get("needs_self_correction"):
            return "deep"
        return "done"

    @staticmethod
    async def _node_path_c(state: _ReasoningState) -> dict[str, Any]:
        a = float(state.get("path_a_confidence", 0.0))
        b = float(state.get("path_b_confidence", 0.0))
        summary = state.get("evidence_summary", {})
        extra = 0.1 if state.get("divergence") else 0.05
        cross = int(summary.get("cross_source_agreement", 0))
        conf = min(1.0, (a + b) / 2 + extra + min(0.2, cross * 0.05))
        detail = "path_c: reconciled divergent paths with cross-source weighting"
        return {"path_c_confidence": conf, "path_c_detail": detail}

    async def _node_consolidate(self, state: _ReasoningState) -> dict[str, Any]:
        a = float(state.get("path_a_confidence", 0.0))
        b = float(state.get("path_b_confidence", 0.0))
        c = state.get("path_c_confidence")
        if c is not None:
            final = float(c)
        else:
            final = (a + b) / 2
        conclusion = (
            "Investigation reasoning consolidated across independent analytic paths. "
            f"{state.get('path_a_detail','')}; {state.get('path_b_detail','')}"
        )
        if state.get("path_c_detail"):
            conclusion += f"; {state.get('path_c_detail')}"
        if self._llm_reason is not None and len(json.dumps(state.get("evidence_summary", {}))) > 400:
            llm_bit = await self._llm_reason(
                "Summarize in one sentence the most likely adversary action given: " + conclusion,
            )
            if llm_bit:
                conclusion += " LLM cross-check: " + llm_bit.strip()
        if self._mcp_registry is not None:
            try:
                listed = self._mcp_registry.list_tools()
                logger.debug("reasoning_mcp_registry_present", tool_count=len(listed))
            except Exception:
                logger.debug("reasoning_mcp_registry_present", tool_count=-1)
        paths = {
            "a": {"confidence": a, "detail": state.get("path_a_detail", "")},
            "b": {"confidence": b, "detail": state.get("path_b_detail", "")},
            "c": {"confidence": c, "detail": state.get("path_c_detail")},
        }
        return {"final_confidence": final, "final_conclusion": conclusion, "paths": paths}

    async def reason(self, context: InvestigationContext) -> ReasoningResult:
        """Run LangGraph reasoning with self-consistency checking."""

        initial: _ReasoningState = {
            "evidence_summary": dict(context.evidence_summary),
        }
        out = await self._compiled.ainvoke(initial)
        needs = bool(out.get("needs_self_correction"))
        return ReasoningResult(
            conclusion=str(out.get("final_conclusion", "inconclusive")),
            confidence=float(out.get("final_confidence", 0.0)),
            paths=dict(out.get("paths", {})),
            needs_self_correction=needs,
        )

    async def self_correct(self, failed_reasoning: ReasoningResult) -> CorrectionAction:
        """Plan a different strategy when reasoning or hypotheses underperform."""

        if failed_reasoning.needs_self_correction or failed_reasoning.confidence < 0.5:
            return CorrectionAction(
                reason="low_or_divergent_confidence",
                strategy_id="network_pcap",
                parameter_overrides={"strict_beaconing": True, "tshark_timeout": 300.0},
                new_hypothesis_seeds=[
                    "DNS tunneling or covert channel over UDP/53",
                    "Periodic beaconing to uncommon ports",
                ],
            )
        return CorrectionAction(
            reason="broaden_ioc_and_memory_depth",
            strategy_id="ioc_matching",
            parameter_overrides={"extra_ioc_feed_paths": [], "volatility_timeout": 300.0},
            new_hypothesis_seeds=["Expanded IOC sweep and deeper volatility pass"],
        )

    async def generate_hypotheses(self, evidence_summary: dict[str, Any]) -> list[Hypothesis]:
        """Derive ranked hypotheses from an evidence summary."""

        title = str(evidence_summary.get("incident_title", "security investigation"))
        description = json.dumps(evidence_summary, default=str)[:18_000]
        incident = Incident(title=title, description=description, severity=IncidentSeverity.MEDIUM)
        return HypothesisManager().create_initial(incident)

    async def evaluate_hypothesis(self, hypothesis: Hypothesis, evidence: list[Evidence]) -> float:
        """Return a confidence score for ``hypothesis`` given ``evidence``."""

        result = HypothesisManager().test(hypothesis, evidence)
        return float(result.score)
