"""Investigations, evidence, agents, and seed smoke tests."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from database.connection import DatabaseManager
from database.crud import agents, evidence, incidents, investigations
from database.models import AgentStatus, AgentType, EvidenceType, IncidentSeverity, IncidentStatus
from database.seed_data import seed_database


@pytest.fixture()
async def db(tmp_path):
    path = tmp_path / "aux.sqlite"
    mgr = DatabaseManager(f"sqlite+aiosqlite:///{path}")
    await mgr.initialize()
    try:
        yield mgr
    finally:
        await mgr.close()


async def test_investigations_and_evidence(db: DatabaseManager, tmp_path: Path) -> None:
    fp = tmp_path / "ev.bin"
    data = b"hello-evidence"
    fp.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()

    async with db.session() as s:
        inc = await incidents.create(
            s,
            {
                "title": "Case",
                "description": "d",
                "severity": IncidentSeverity.MEDIUM,
                "status": IncidentStatus.INVESTIGATING,
            },
        )
        step = await investigations.create_step(
            s,
            inc.id,
            {
                "agent_name": "agent-1",
                "action_taken": "scan",
                "confidence": 0.7,
                "is_self_correction": True,
                "correction_reason": "false positive",
                "execution_time_ms": 120,
            },
        )
        assert step.incident_id == inc.id
        steps = await investigations.get_steps_for_incident(s, inc.id)
        assert len(steps) == 1
        corr = await investigations.get_self_corrections(s, inc.id)
        assert len(corr) == 1
        metrics = await investigations.get_accuracy_metrics(s, inc.id)
        assert metrics["self_corrections"] == 1

        ev = await evidence.create(
            s,
            inc.id,
            {
                "evidence_type": EvidenceType.FILE,
                "file_path": str(fp),
                "hash_sha256": digest,
                "file_size_bytes": len(data),
                "metadata": {"note": "unit"},
                "custody_chain": [{"who": "agent-1", "action": "collect"}],
            },
        )
        assert ev.metadata_.get("note") == "unit"
        assert await evidence.verify_integrity(s, ev.id) is True
        chain = await evidence.get_chain_of_custody(s, ev.id)
        assert chain[0]["who"] == "agent-1"


async def test_agents_and_seed(db: DatabaseManager) -> None:
    async with db.session() as s:
        ag = await agents.create(
            s,
            {
                "name": "unit-agent",
                "agent_type": AgentType.INVESTIGATION,
                "status": AgentStatus.ACTIVE,
                "tasks_completed": 4,
                "tasks_failed": 1,
            },
        )
        await agents.update_metrics(s, ag.id, {"tasks_completed": 10, "avg_task_duration_ms": 42.5})
        active = await agents.get_all_active(s)
        assert any(x.id == ag.id for x in active)
        health = await agents.get_health_summary(s)
        assert any(h.agent_id == ag.id for h in health)

        counts = await seed_database(s)
        assert counts["knowledge_nodes"] >= 0
        assert counts["incidents"] >= 0
