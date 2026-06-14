"""Tests for evidence collection, custody chain, and vault."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from agents.defense.evidence_collection import EvidenceCollectionAgent
from agents.defense.tools.chain_of_custody import CustodyChain
from agents.defense.tools.evidence_storage import EvidenceVault
from config.constants import IncidentSeverity
from core.message_bus import MessageBus
from shared.models import Incident, InvestigationStep
from shared.utils import compute_file_hash


@pytest.mark.asyncio
async def test_custody_chain_append_and_verify(tmp_path: Path) -> None:
    db = tmp_path / "custody.sqlite3"
    chain = CustodyChain(db)
    from shared.models import CustodyAction, CustodyEntry

    eid = str(uuid4())
    h = "a" * 64
    await chain.append(
        CustodyEntry(
            action=CustodyAction.COLLECTED,
            performed_by="tester",
            evidence_id=eid,
            hash_before=None,
            hash_after=h,
            location="/tmp/src",
            notes="collected",
        ),
    )
    await chain.append(
        CustodyEntry(
            action=CustodyAction.COPIED,
            performed_by="tester",
            evidence_id=eid,
            hash_before=h,
            hash_after=h,
            location="/tmp/dst",
            notes="copy ok",
        ),
    )
    assert await chain.verify_chain(eid)
    rep = await chain.generate_report(eid)
    assert eid in rep
    xfer = await chain.transfer_custody(eid, "tester", "analyst")
    assert xfer.action.value == "TRANSFERRED"


@pytest.mark.asyncio
async def test_evidence_vault_store_verify_list_delete(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    src = tmp_path / "sample.log"
    src.write_text("hello evidence", encoding="utf-8")
    vault = EvidenceVault(vault_root, vault_secret="unit-test-secret")
    incident_id = uuid4()
    ev = await vault.store(
        str(src),
        incident_id,
        "log_file",
        {"note": "t"},
        collected_by="pytest",
        encrypt=True,
    )
    assert await vault.verify_integrity(str(ev.id))
    listed = await vault.list_evidence(str(incident_id))
    assert len(listed) == 1
    path = await vault.retrieve(str(ev.id))
    assert path.is_file()
    assert await vault.delete(str(ev.id))


@pytest.mark.asyncio
async def test_evidence_collection_agent_collect(tmp_path: Path) -> None:
    bus = MessageBus()
    artifact = tmp_path / "net.pcap"
    artifact.write_bytes(b"\x00\x01\x02" * 100)
    h = compute_file_hash(str(artifact))
    incident = Incident(
        id=uuid4(),
        title="Test",
        description="Collect PCAP",
        severity=IncidentSeverity.MEDIUM,
        raw_evidence_refs=[str(artifact)],
    )
    step = InvestigationStep(
        incident_id=incident.id,
        agent_name="investigator",
        action_taken="network",
        raw_output=f"found {artifact}",
        interpretation="pcap",
        confidence=0.9,
    )
    custody_db = tmp_path / "c.sqlite3"
    vault_root = tmp_path / "vault2"
    agent = EvidenceCollectionAgent(
        bus,
        {
            "custody_db_path": str(custody_db),
            "evidence_vault_root": str(vault_root),
            "staging_dir": str(tmp_path / "stage"),
            "encrypt_evidence": True,
        },
    )
    out = await agent.collect(incident, [step])
    assert len(out) == 1
    assert out[0].hash_sha256 == h
    vault = EvidenceVault(vault_root, vault_secret="tutorial-dev-secret-change-me")
    assert await vault.verify_integrity(str(out[0].id))
    chain = CustodyChain(custody_db)
    assert await chain.verify_chain(str(out[0].id))
