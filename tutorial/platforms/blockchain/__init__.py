"""Blockchain integrations for Turing Test hackathon tracks (identity, credentials, RWA)."""

from platforms.blockchain.agent_identity import AgentAction, BlockchainAgentIdentity, Signature
from platforms.blockchain.credential_nft import Credential, CredentialNFT
from platforms.blockchain.rwa_integration import IncidentPoolModel, RWAIntegration

TURING_TEST_TRACKS = (
    "Agents & Society",
    "Alignment & Safety",
    "DeFi / RWA",
    "Education & Credentials",
    "Infrastructure & Tooling",
    "Creative & Media",
)

__all__ = [
    "AgentAction",
    "BlockchainAgentIdentity",
    "Credential",
    "CredentialNFT",
    "IncidentPoolModel",
    "RWAIntegration",
    "Signature",
    "TURING_TEST_TRACKS",
]
