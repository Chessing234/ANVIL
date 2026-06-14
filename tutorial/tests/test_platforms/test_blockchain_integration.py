"""Tests for blockchain identity, credential NFTs, and RWA incident pools."""

from __future__ import annotations

import json

import pytest

from platforms.blockchain import (
    BlockchainAgentIdentity,
    CredentialNFT,
    RWAIntegration,
    Signature,
)


@pytest.fixture
async def identity() -> BlockchainAgentIdentity:
    agent = BlockchainAgentIdentity(mock=True)
    yield agent
    await agent.close()


@pytest.mark.asyncio
async def test_agent_identity_register_sign_verify(identity: BlockchainAgentIdentity) -> None:
    did = await identity.register_agent(
        "UnitAgent",
        "hunter",
        "0x1111111111111111111111111111111111111111",
    )
    assert did.startswith("did:tutorial:hunter:")
    report_hash = "0x" + "aa" * 32
    sig = await identity.sign_investigation_report(did, report_hash)
    assert isinstance(sig, Signature)
    assert await identity.verify_report_signature(did, report_hash, sig)
    bad = Signature(v=27, r="0x" + "11" * 32, s="0x" + "22" * 32)
    assert not await identity.verify_report_signature(did, report_hash, bad)


@pytest.mark.asyncio
async def test_agent_identity_history_and_reputation(identity: BlockchainAgentIdentity) -> None:
    did = await identity.register_agent("Neo", "teacher", "0x2222222222222222222222222222222222222222")
    await identity.update_agent_reputation(did, "lesson", "success")
    hist = await identity.get_agent_history(did)
    assert any(a.action_type == "lesson" for a in hist)


@pytest.mark.asyncio
async def test_credential_nft_mint_verify_metadata() -> None:
    nft = CredentialNFT(mock=True)
    tid = await nft.mint_credential("0x3333333333333333333333333333333333333333", "dns-tunneling", 92.0)
    cred = await nft.verify_credential(tid)
    assert cred.valid
    assert cred.score == 92.0
    meta = await nft.get_credential_metadata(tid)
    dumped = json.dumps(meta)
    assert "CSTA_Standard" in dumped
    assert meta["attributes"][2]["trait_type"] == "Score"


@pytest.mark.asyncio
async def test_rwa_incident_pool_flow() -> None:
    rwa = RWAIntegration(mock=True)
    pid = await rwa.create_incident_pool("INC-001", 1.5)
    assert pid.startswith("0x")
    await rwa.submit_resolution("did:tutorial:agent:x", pid, "QmResolution")
    ok = await rwa.validate_resolution(pid, "QmResolution")
    assert ok
    earnings = await rwa.get_agent_earnings("did:tutorial:agent:x")
    assert earnings == pytest.approx(1.5)


@pytest.mark.asyncio
async def test_rwa_stake_for_priority() -> None:
    rwa = RWAIntegration(mock=True)
    await rwa.stake_for_priority("0x4444444444444444444444444444444444444444", 0.25)
    # internal map keyed lowercased
    assert rwa._stakes["0x4444444444444444444444444444444444444444"] == 0.25  # noqa: SLF001


def test_blockchain_package_exports() -> None:
    import platforms.blockchain as bc

    assert hasattr(bc, "BlockchainAgentIdentity")
    assert hasattr(bc, "CredentialNFT")
    assert hasattr(bc, "RWAIntegration")
    assert len(bc.TURING_TEST_TRACKS) == 6
