"""Tests for ``ConceptExtractor``."""

from __future__ import annotations

from uuid import uuid4

import pytest

from knowledge.concept_extractor import ConceptExtractor
from knowledge.knowledge_graph import KnowledgeGraph
from shared.models import InvestigationStep


@pytest.mark.asyncio
async def test_extract_investigation_tool_rules(tmp_path) -> None:
    g = KnowledgeGraph(tmp_path / "cx.sqlite")
    await g.initialize()
    ex = ConceptExtractor(g)
    iid = uuid4()
    steps = [
        InvestigationStep(
            incident_id=iid,
            agent_name="agent",
            action_taken="memory",
            tool_used="volatility netscan",
            interpretation="malfind suspicious",
            raw_output="tcp stream",
            confidence=0.8,
        ),
    ]
    nodes = await ex.extract_from_investigation(steps)
    ids = {n.id for n in nodes}
    assert "network_connection_analysis" in ids or "volatile_memory_forensics" in ids


@pytest.mark.asyncio
async def test_extract_question_and_tool_output() -> None:
    ex = ConceptExtractor(None)
    q = await ex.extract_from_question("How does DNS tunneling work in our PCAP?")
    assert "dns_tunneling" in q
    out = await ex.extract_from_tool_output("malfind", "MZ header in injected region")
    assert "code_injection" in out
