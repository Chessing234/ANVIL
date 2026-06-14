"""Tests for the defense InvestigationAgent and supporting components."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from agents.defense.hypothesis_manager import HypothesisManager
from agents.defense.investigation import InvestigationAgent
from agents.defense.reasoning_engine import ReasoningEngine
from config.constants import IncidentSeverity, MessageBusTopics
from core.message_bus import MessageBus
from shared.models import Evidence, Incident, InvestigationContext, Message
from shared.utils import compute_file_hash


def _write_evidence_bundle(tmp_path: Path, incident_id: UUID) -> list[Evidence]:
    mem = tmp_path / "mem.dmp"
    mem.write_bytes(b"MZ" + b"\x00" * 2000)

    pcap = tmp_path / "net.json"
    pcap.write_text(
        json.dumps(
            {
                "protocol_stats": {"udp": 12},
                "top_talkers": [{"endpoint": "10.0.0.1", "count": 50}],
                "unusual_ports": [44444],
                "beaconing": [{"pair": "10.0.0.1->10.0.0.2", "mean_gap": 1.0, "variance": 0.2, "score": 0.72}],
                "dns_tunneling": [{"indicator": "longlabel.example", "score": 0.65}],
                "large_transfers": [],
            },
        ),
        encoding="utf-8",
    )

    log_lines = []
    for i in range(6):
        log_lines.append(
            json.dumps(
                {
                    "_time": f"2024-06-01T12:00:0{i}Z",
                    "event_id": "4625",
                    "message": "fail login attempt",
                    "user": "svc_test",
                },
            ),
        )
    log = tmp_path / "auth.jsonl"
    log.write_text("\n".join(log_lines), encoding="utf-8")

    disk = tmp_path / "disk_notes.txt"
    disk.write_text("RDP inbound from 198.51.100.9 and suspicious.ps1 execution", encoding="utf-8")

    items: list[tuple[str, Path]] = [
        ("memory_dump", mem),
        ("network_capture", pcap),
        ("log_file", log),
        ("disk_image", disk),
    ]
    out: list[Evidence] = []
    for kind, path in items:
        h = compute_file_hash(str(path))
        meta: dict[str, object] = {}
        if kind == "log_file":
            meta["log_format"] = "splunk"
        out.append(
            Evidence(
                incident_id=incident_id,
                type=kind,  # type: ignore[arg-type]
                file_path=str(path),
                hash_sha256=h,
                metadata=meta,
                collected_by="test_fixture",
            ),
        )
    return out


@pytest.mark.asyncio
async def test_investigation_agent_end_to_end(tmp_path: Path) -> None:
    incident_id = uuid4()
    incident = Incident(
        id=incident_id,
        title="Malware and DNS investigation",
        description="Malware indicators with dns tunneling and exfiltration concerns.",
        severity=IncidentSeverity.HIGH,
        source_ip="203.0.113.50",
    )
    evidence = _write_evidence_bundle(tmp_path, incident_id)
    bus = MessageBus()
    agent = InvestigationAgent(
        bus,
        {},
        None,
        ReasoningEngine(mcp_registry=None, llm_reason=None),
        name=f"investigation-{uuid4().hex[:8]}",
    )
    result = await agent.investigate(incident, evidence)
    assert result.incident_id == incident_id
    assert result.narrative
    assert result.accuracy_report["self_corrections"] > 0
    assert result.accuracy_report["evidence_items_analyzed"] == 4
    assert result.accuracy_report["total_steps"] >= 5
    assert result.self_corrections


@pytest.mark.asyncio
async def test_reasoning_engine_paths() -> None:
    engine = ReasoningEngine()
    incident = Incident(
        title="test",
        description="dns beacon",
        severity=IncidentSeverity.MEDIUM,
    )
    ctx = InvestigationContext(
        incident=incident,
        evidence=[],
        evidence_summary={
            "anomaly_count": 2,
            "ioc_match_count": 1,
            "dns_tunnel_signals": 1,
            "beacon_signals": 1,
            "cross_source_agreement": 1,
        },
    )
    out = await engine.reason(ctx)
    assert 0.0 <= out.confidence <= 1.0
    assert out.conclusion
    assert "a" in out.paths and "b" in out.paths


@pytest.mark.asyncio
async def test_hypothesis_manager_lifecycle() -> None:
    hm = HypothesisManager()
    inc = Incident(
        title="Phishing email leads to malware",
        description="User opened attachment; dns c2 observed.",
        severity=IncidentSeverity.MEDIUM,
    )
    hyps = hm.create_initial(inc)
    assert 3 <= len(hyps) <= 5
    merged = hm.merge(hyps)
    ranked = hm.rank(merged)
    pruned = hm.prune(ranked, 0.0)
    assert pruned


@pytest.mark.asyncio
async def test_investigation_agent_bus_dispatch(tmp_path: Path, isolated_message_bus: MessageBus) -> None:
    bus = isolated_message_bus
    incident_id = uuid4()
    incident = Incident(
        id=incident_id,
        title="Network intrusion",
        description="Suspicious traffic and malware dns patterns.",
        severity=IncidentSeverity.CRITICAL,
        source_ip="198.51.100.10",
    )
    evidence = _write_evidence_bundle(tmp_path, incident_id)
    agent = InvestigationAgent(
        bus,
        {},
        None,
        ReasoningEngine(mcp_registry=None, llm_reason=None),
        name=f"investigation-bus-{uuid4().hex[:8]}",
    )
    await agent.start()
    try:
        msg = Message(
            topic=MessageBusTopics.INVESTIGATIONS,
            payload={
                "incident": incident.model_dump(mode="json"),
                "evidence": [e.model_dump(mode="json") for e in evidence],
            },
            source_agent="pytest",
        )
        await bus.publish(MessageBusTopics.INVESTIGATIONS, msg)
        for _ in range(50):
            if agent.metrics.tasks_completed >= 1:
                break
            await asyncio.sleep(0.05)
        assert agent.metrics.tasks_completed >= 1
    finally:
        await agent.stop()
