"""Rule-first concept extraction with optional LLM merge."""

from __future__ import annotations

import re
from collections.abc import Callable, Coroutine
from typing import Any

import structlog

from config.constants import LessonDifficulty
from knowledge.models import ConceptNode
from knowledge.knowledge_graph import KnowledgeGraph
from shared.models import InvestigationStep

logger = structlog.get_logger(__name__)

_TOOL_CONCEPTS: dict[str, list[str]] = {
    "volatility": ["volatile_memory_forensics", "network_connection_analysis"],
    "vol.py": ["volatile_memory_forensics"],
    "malfind": ["code_injection", "process_hollowing"],
    "netscan": ["network_connection_analysis"],
    "tshark": ["packet_analysis", "protocol_analysis"],
    "wireshark": ["packet_analysis"],
    "grep": ["log_analysis", "pattern_matching"],
    "yara": ["signature_based_detection"],
    "strings": ["static_artifact_analysis"],
}

_KEYWORD_CONCEPTS: list[tuple[re.Pattern[str], str, str, LessonDifficulty]] = [
    (re.compile(r"netscan|net\s+conn", re.I), "network_connection_analysis", "Network connection tables in memory.", LessonDifficulty.INTERMEDIATE),
    (re.compile(r"malfind|hollow", re.I), "process_hollowing", "Suspicious executable memory regions.", LessonDifficulty.ADVANCED),
    (re.compile(r"dns\s+tunnel|dns\s+exfil", re.I), "dns_tunneling", "DNS abused for covert channels.", LessonDifficulty.ADVANCED),
    (re.compile(r"ransom|encrypt", re.I), "ransomware_defense", "Ransomware behaviors and controls.", LessonDifficulty.INTERMEDIATE),
]


class ConceptExtractor:
    """Extracts ``ConceptNode`` objects from investigations, narratives, and tool output."""

    def __init__(
        self,
        graph: KnowledgeGraph | None = None,
        *,
        llm_extract_fn: Callable[[str], Coroutine[Any, Any, list[str]]] | None = None,
    ) -> None:
        self._graph = graph
        self._llm_extract_fn = llm_extract_fn

    async def extract_from_investigation(self, steps: list[InvestigationStep]) -> list[ConceptNode]:
        """Map investigation steps to canonical concepts (rules first, optional LLM)."""

        labels: dict[str, float] = {}
        for step in steps:
            blob = " ".join(
                x
                for x in (step.action_taken, step.tool_used or "", step.interpretation or "", step.raw_output or "")
                if x
            )
            tool = (step.tool_used or "").lower()
            for tkey, concepts in _TOOL_CONCEPTS.items():
                if tkey in tool:
                    for c in concepts:
                        labels[c] = min(1.0, labels.get(c, 0.0) + 0.35)
            for pat, cid, desc, diff in _KEYWORD_CONCEPTS:
                if pat.search(blob):
                    labels[cid] = min(1.0, labels.get(cid, 0.0) + 0.4)
        if self._llm_extract_fn:
            joined = "\n".join(s.action_taken for s in steps)[:6000]
            extra = await self._llm_extract_fn(joined)
            for e in extra[:12]:
                labels[e] = min(1.0, labels.get(e, 0.0) + 0.25)
        if not labels:
            labels["incident_triage"] = 0.5
        out: list[ConceptNode] = []
        for cid, conf in sorted(labels.items(), key=lambda kv: kv[1], reverse=True)[:15]:
            out.append(
                ConceptNode(
                    id=cid,
                    name=cid.replace("_", " ").title(),
                    description=f"Extracted from investigation (confidence={conf:.2f}).",
                    category="forensics",
                    difficulty=LessonDifficulty.INTERMEDIATE,
                ),
            )
        return out

    async def extract_from_narrative(self, narrative: str, allowed_ids: set[str] | None = None) -> list[ConceptNode]:
        """Extract concepts from narrative text; optionally restrict to ``allowed_ids``."""

        found: dict[str, float] = {}
        for pat, cid, desc, diff in _KEYWORD_CONCEPTS:
            if pat.search(narrative):
                found[cid] = min(1.0, found.get(cid, 0.0) + 0.45)
        if allowed_ids is not None:
            found = {k: v for k, v in found.items() if k in allowed_ids}
        if not found:
            return []
        return [
            ConceptNode(
                id=cid,
                name=cid.replace("_", " ").title(),
                description=desc,
                category="curriculum",
                difficulty=diff,
            )
            for cid, _ in found.items()
        ]

    async def extract_from_question(self, question: str) -> list[str]:
        """Return ranked concept ids referenced by a learner question."""

        scores: dict[str, float] = {}
        for pat, cid, _, _ in _KEYWORD_CONCEPTS:
            if pat.search(question):
                scores[cid] = scores.get(cid, 0.0) + 0.5
        q = question.lower()
        for token, cid in (
            ("packet", "packet_analysis"),
            ("hash", "hash_validation"),
            ("memory", "volatile_memory_forensics"),
        ):
            if token in q:
                scores[cid] = scores.get(cid, 0.0) + 0.3
        return [k for k, _ in sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:8]]

    async def extract_from_tool_output(self, tool_name: str, output: str) -> list[str]:
        """Lightweight mapping from tool output strings to concept ids."""

        concepts: set[str] = set()
        t = tool_name.lower()
        for tkey, cids in _TOOL_CONCEPTS.items():
            if tkey in t:
                concepts.update(cids)
        blob = (tool_name + " " + output).lower()
        if "injected" in blob or "vad" in blob:
            concepts.add("code_injection")
        if "tcp" in blob or "udp" in blob:
            concepts.add("packet_analysis")
        return sorted(concepts)

    async def validate_against_graph(self, candidates: list[ConceptNode]) -> list[ConceptNode]:
        """Drop unknown labels if graph is present and strict."""

        if self._graph is None:
            return candidates
        validated: list[ConceptNode] = []
        for c in candidates:
            existing = await self._graph.get_concept(c.id)
            if existing or c.id in {
                "dns_tunneling",
                "packet_analysis",
                "volatile_memory_forensics",
                "process_hollowing",
                "code_injection",
                "network_connection_analysis",
                "incident_triage",
            }:
                validated.append(c)
        return validated or candidates[:3]
