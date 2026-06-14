"""On-chain identity, signatures, and audit trail for TUTORIAL agents (Mantle / EVM compatible)."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import time
import uuid
from typing import Any

import aiohttp
import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)

_HEX_ADDR = re.compile(r"^0x[a-fA-F0-9]{40}$")


class Signature(BaseModel):
    """ECDSA signature components (``personal_sign`` / EIP-191 style verification on-chain)."""

    model_config = {"extra": "forbid"}

    v: int = Field(ge=27, le=28)
    r: str = Field(min_length=66, max_length=66)
    s: str = Field(min_length=66, max_length=66)


class AgentAction(BaseModel):
    """Single immutable audit entry mirrored from ``AgentRegistry.AgentAction``."""

    model_config = {"extra": "forbid"}

    action_type: str = Field(min_length=1)
    payload_hash: str = Field(default="")
    timestamp: int = Field(ge=0)
    result: str = Field(min_length=1)


def _build_did(agent_type: str) -> str:
    safe_type = agent_type.strip().replace(":", "-")
    return f"did:tutorial:{safe_type}:{uuid.uuid4()}"


def _normalize_report_hash(report_hash: str) -> str:
    h = report_hash.strip().lower()
    if not h.startswith("0x"):
        h = "0x" + h
    if len(h) != 66:
        raise ValueError("report_hash must be 32-byte hex (0x + 64 hex chars)")
    return h


def _validate_evm_address(addr: str) -> str:
    if not _HEX_ADDR.match(addr):
        raise ValueError("public_key must be a 20-byte EVM address (0x + 40 hex chars)")
    return "0x" + addr[2:].lower()


def _mock_signature(secret: bytes, agent_did: str, report_hash: str) -> Signature:
    material = hmac.new(secret, f"{agent_did}|{report_hash}".encode("utf-8"), hashlib.sha256).digest()
    tail = hashlib.sha256(material + agent_did.encode("utf-8")).digest()
    r = "0x" + material.hex()
    s = "0x" + tail.hex()
    return Signature(v=27, r=r, s=s)


class BlockchainAgentIdentity:
    """Registers DIDs, anchors investigation hashes, tracks reputation, and optionally talks to ``AgentRegistry``."""

    _REGISTRY_ABI: list[dict[str, Any]] = [
        {
            "name": "agentById",
            "type": "function",
            "stateMutability": "view",
            "inputs": [{"name": "agentId", "type": "uint256"}],
            "outputs": [
                {
                    "name": "",
                    "type": "tuple",
                    "components": [
                        {"name": "did", "type": "string"},
                        {"name": "name", "type": "string"},
                        {"name": "agentType", "type": "string"},
                        {"name": "owner", "type": "address"},
                        {"name": "signingKey", "type": "address"},
                        {"name": "reputation", "type": "uint256"},
                        {"name": "investigationsCompleted", "type": "uint256"},
                        {"name": "lessonsGenerated", "type": "uint256"},
                        {"name": "isActive", "type": "bool"},
                        {"name": "registeredAt", "type": "uint256"},
                    ],
                }
            ],
        },
        {
            "name": "registerAgent",
            "type": "function",
            "stateMutability": "nonpayable",
            "inputs": [
                {"name": "did", "type": "string"},
                {"name": "name_", "type": "string"},
                {"name": "agentType_", "type": "string"},
                {"name": "signingKey_", "type": "address"},
            ],
            "outputs": [{"name": "", "type": "uint256"}],
        },
        {
            "name": "submitReportSignature",
            "type": "function",
            "stateMutability": "nonpayable",
            "inputs": [
                {"name": "agentId", "type": "uint256"},
                {"name": "reportHash", "type": "bytes32"},
                {"name": "v", "type": "uint8"},
                {"name": "r", "type": "bytes32"},
                {"name": "s", "type": "bytes32"},
            ],
            "outputs": [],
        },
        {
            "name": "verifyReportSignature",
            "type": "function",
            "stateMutability": "view",
            "inputs": [
                {"name": "agentId", "type": "uint256"},
                {"name": "reportHash", "type": "bytes32"},
                {"name": "v", "type": "uint8"},
                {"name": "r", "type": "bytes32"},
                {"name": "s", "type": "bytes32"},
            ],
            "outputs": [{"name": "", "type": "bool"}],
        },
        {
            "name": "getAgentActions",
            "type": "function",
            "stateMutability": "view",
            "inputs": [
                {"name": "agentId", "type": "uint256"},
                {"name": "start", "type": "uint256"},
                {"name": "count", "type": "uint256"},
            ],
            "outputs": [
                {
                    "name": "",
                    "type": "tuple[]",
                    "components": [
                        {"name": "actionType", "type": "string"},
                        {"name": "payloadHash", "type": "string"},
                        {"name": "timestamp", "type": "uint256"},
                        {"name": "result", "type": "string"},
                    ],
                }
            ],
        },
        {
            "name": "updateReputation",
            "type": "function",
            "stateMutability": "nonpayable",
            "inputs": [
                {"name": "agentId", "type": "uint256"},
                {"name": "action", "type": "string"},
                {"name": "result", "type": "string"},
            ],
            "outputs": [],
        },
        {
            "name": "agentIdForDid",
            "type": "function",
            "stateMutability": "view",
            "inputs": [{"name": "did", "type": "string"}],
            "outputs": [{"name": "", "type": "uint256"}],
        },
    ]

    def __init__(
        self,
        *,
        rpc_url: str | None = None,
        registry_address: str | None = None,
        private_key: str | None = None,
        mock: bool | None = None,
        max_retries: int = 4,
    ) -> None:
        self._rpc = rpc_url or os.environ.get("WEB3_RPC_URL", "")
        self._registry = registry_address or os.environ.get("AGENT_REGISTRY_ADDRESS", "")
        self._pk = private_key or os.environ.get("AGENT_OWNER_PRIVATE_KEY", "")
        if mock is True:
            self._mock = True
        elif mock is False:
            self._mock = False
        else:
            self._mock = os.environ.get("BLOCKCHAIN_MOCK", "1") == "1"
        self._max_retries = max_retries
        self._session: aiohttp.ClientSession | None = None
        self._agents: dict[str, dict[str, Any]] = {}
        self._did_to_id: dict[str, int] = {}
        self._next_id = 1
        self._signatures: dict[tuple[str, str], Signature] = {}
        self._history: dict[str, list[AgentAction]] = {}
        self._reputation: dict[str, int] = {}
        self._mock_secret = os.environ.get("BLOCKCHAIN_MOCK_SECRET", "tutorial-mock-secret").encode()

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60))
        return self._session

    async def _async_web3(self) -> Any:
        try:
            from web3 import AsyncWeb3  # type: ignore import-not-found
        except ImportError as exc:  # pragma: no cover - optional dependency path
            raise RuntimeError(
                "Install blockchain extras: pip install 'tutorial[blockchain]' (requires web3.py)"
            ) from exc
        if not self._rpc or not self._registry:
            raise RuntimeError("WEB3_RPC_URL and AGENT_REGISTRY_ADDRESS must be set for live mode")
        return AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(self._rpc))

    async def _registry_contract(self, w3: Any) -> Any:
        return w3.eth.contract(address=w3.to_checksum_address(self._registry), abi=self._REGISTRY_ABI)

    async def _send_fn(self, w3: Any, fn: Any) -> Any:
        if not self._pk:
            raise RuntimeError("AGENT_OWNER_PRIVATE_KEY is required for live registry writes")
        pk = self._pk.strip()
        if not pk.startswith("0x"):
            pk = "0x" + pk
        account = w3.eth.account.from_key(pk)
        tx = await fn.build_transaction(
            {
                "from": account.address,
                "nonce": await w3.eth.get_transaction_count(account.address),
                "chainId": await w3.eth.chain_id,
            }
        )
        signed = account.sign_transaction(tx)
        tx_hash = await w3.eth.send_raw_transaction(signed.raw_transaction)
        return await w3.eth.wait_for_transaction_receipt(tx_hash)

    async def register_agent(self, agent_name: str, agent_type: str, public_key: str) -> str:
        """Register an agent and return its DID (``did:tutorial:{type}:{uuid}``)."""
        addr = _validate_evm_address(public_key)
        did = _build_did(agent_type)
        if self._mock:
            agent_id = self._next_id
            self._next_id += 1
            self._agents[did] = {
                "id": agent_id,
                "name": agent_name,
                "type": agent_type,
                "signing_key": addr,
                "reputation": 0,
                "investigations": 0,
                "lessons": 0,
            }
            self._did_to_id[did] = agent_id
            self._history[did] = []
            self._reputation[did] = 0
            logger.info("agent_registered_mock", did=did, agent_id=agent_id)
            return did

        w3 = await self._async_web3()
        addr = w3.to_checksum_address(public_key)
        contract = await self._registry_contract(w3)
        fn = contract.functions.registerAgent(did, agent_name, agent_type, addr)
        receipt = await self._send_fn(w3, fn)
        agent_id = int(await contract.functions.agentIdForDid(did).call())
        self._did_to_id[did] = agent_id
        logger.info(
            "agent_registered_chain",
            did=did,
            agent_id=agent_id,
            tx=w3.to_hex(receipt["transactionHash"]),
        )
        return did

    async def sign_investigation_report(self, agent_did: str, report_hash: str) -> Signature:
        """Anchor a report hash (mock: deterministic MAC signature; live: submits ``submitReportSignature``)."""
        h = _normalize_report_hash(report_hash)
        if self._mock:
            if agent_did not in self._agents:
                raise ValueError("unknown agent DID")
            sig = _mock_signature(self._mock_secret, agent_did, h)
            self._signatures[(agent_did, h)] = sig
            self._agents[agent_did]["investigations"] += 1
            self._history.setdefault(agent_did, []).append(
                AgentAction(
                    action_type="investigation",
                    payload_hash=h,
                    timestamp=int(time.time()),
                    result="signed",
                )
            )
            logger.info("report_signed_mock", did=agent_did, hash=h)
            return sig

        w3 = await self._async_web3()
        contract = await self._registry_contract(w3)
        agent_id = self._did_to_id.get(agent_did)
        if agent_id is None:
            agent_id = int(await contract.functions.agentIdForDid(agent_did).call())
            self._did_to_id[agent_did] = agent_id
        try:
            from eth_account import Account  # type: ignore import-not-found
            from eth_account.messages import encode_defunct  # type: ignore import-not-found
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Install tutorial[blockchain] for signing support") from exc
        signing_pk = os.environ.get("AGENT_SIGNING_PRIVATE_KEY", self._pk)
        if not signing_pk:
            raise RuntimeError("AGENT_SIGNING_PRIVATE_KEY (or AGENT_OWNER_PRIVATE_KEY) required for live signing")
        if signing_pk.startswith("0x"):
            signing_pk = signing_pk[2:]
        acct = Account.from_key(bytes.fromhex(signing_pk))
        agent_row = await contract.functions.agentById(agent_id).call()
        signing_key_onchain = w3.to_checksum_address(agent_row[4])
        if w3.to_checksum_address(acct.address) != signing_key_onchain:
            raise RuntimeError("AGENT_SIGNING_PRIVATE_KEY must match the on-chain signingKey for this agent")
        message = encode_defunct(hexstr=h)
        signed = Account.sign_message(message, private_key=acct.key)
        fn = contract.functions.submitReportSignature(
            agent_id,
            bytes.fromhex(h[2:]),
            int(signed.v),
            signed.r.to_bytes(32, "big"),
            signed.s.to_bytes(32, "big"),
        )
        receipt = await self._send_fn(w3, fn)
        sig = Signature(v=int(signed.v), r="0x" + signed.r.to_bytes(32, "big").hex(), s="0x" + signed.s.to_bytes(32, "big").hex())
        logger.info("report_signed_chain", did=agent_did, tx=w3.to_hex(receipt["transactionHash"]))
        return sig

    async def verify_report_signature(
        self,
        agent_did: str,
        report_hash: str,
        signature: Signature,
    ) -> bool:
        """Return ``True`` if the signature matches the registered signing key for ``agent_did``."""
        h = _normalize_report_hash(report_hash)
        if self._mock:
            stored = self._signatures.get((agent_did, h))
            if not stored:
                return False
            return stored.model_dump() == signature.model_dump()

        w3 = await self._async_web3()
        contract = await self._registry_contract(w3)
        agent_id = self._did_to_id.get(agent_did)
        if agent_id is None:
            agent_id = int(await contract.functions.agentIdForDid(agent_did).call())
        ok = await contract.functions.verifyReportSignature(
            agent_id,
            bytes.fromhex(h[2:]),
            signature.v,
            bytes.fromhex(signature.r[2:]),
            bytes.fromhex(signature.s[2:]),
        ).call()
        return bool(ok)

    async def get_agent_history(self, agent_did: str) -> list[AgentAction]:
        """Return recent on-chain (or mock) actions for the agent."""
        if self._mock:
            return list(self._history.get(agent_did, []))

        w3 = await self._async_web3()
        contract = await self._registry_contract(w3)
        agent_id = self._did_to_id.get(agent_did)
        if agent_id is None:
            agent_id = int(await contract.functions.agentIdForDid(agent_did).call())
        rows = await contract.functions.getAgentActions(agent_id, 0, 256).call()
        out: list[AgentAction] = []
        for row in rows:
            out.append(
                AgentAction(
                    action_type=row[0],
                    payload_hash=row[1],
                    timestamp=int(row[2]),
                    result=row[3],
                )
            )
        return out

    async def update_agent_reputation(self, agent_did: str, action: str, result: str) -> None:
        """Increment reputation counters (owner-only on-chain)."""
        if self._mock:
            if agent_did not in self._agents:
                raise ValueError("unknown agent DID")
            self._reputation[agent_did] = self._reputation.get(agent_did, 0) + 1
            if action == "lesson":
                self._agents[agent_did]["lessons"] += 1
            self._history.setdefault(agent_did, []).append(
                AgentAction(
                    action_type=action,
                    payload_hash="",
                    timestamp=int(time.time()),
                    result=result,
                )
            )
            logger.info("reputation_updated_mock", did=agent_did, action=action)
            return

        w3 = await self._async_web3()
        contract = await self._registry_contract(w3)
        agent_id = self._did_to_id.get(agent_did)
        if agent_id is None:
            agent_id = int(await contract.functions.agentIdForDid(agent_did).call())
        fn = contract.functions.updateReputation(agent_id, action, result)
        receipt = await self._send_fn(w3, fn)
        logger.info("reputation_updated_chain", did=agent_did, tx=w3.to_hex(receipt["transactionHash"]))
