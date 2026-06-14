"""Real World Asset style incident response markets (bounties, staking, payouts)."""

from __future__ import annotations

import os
import secrets
from typing import Any

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


class IncidentPoolModel(BaseModel):
    """Serialized view of an on-chain incident pool."""

    model_config = {"extra": "forbid"}

    pool_id: str = Field(min_length=1)
    incident_id: str = Field(min_length=1)
    bounty_wei: int = Field(ge=0)
    resolver: str = Field(default="")
    resolution_hash: str = Field(default="")
    resolved: bool = False


class RWAIntegration:
    """Creates bounty pools, accepts resolutions, validates payouts, and tracks agent earnings."""

    _ABI: list[dict[str, Any]] = [
        {
            "name": "createPool",
            "type": "function",
            "stateMutability": "payable",
            "inputs": [{"name": "incidentId", "type": "string"}],
            "outputs": [{"name": "", "type": "bytes32"}],
        },
        {
            "name": "submitResolution",
            "type": "function",
            "stateMutability": "nonpayable",
            "inputs": [
                {"name": "poolId", "type": "bytes32"},
                {"name": "resolutionHash", "type": "string"},
            ],
            "outputs": [],
        },
        {
            "name": "validateAndPay",
            "type": "function",
            "stateMutability": "nonpayable",
            "inputs": [
                {"name": "poolId", "type": "bytes32"},
                {"name": "expectedHash", "type": "string"},
            ],
            "outputs": [],
        },
        {
            "name": "stakeForPriority",
            "type": "function",
            "stateMutability": "payable",
            "inputs": [],
            "outputs": [],
        },
        {
            "name": "agentEarningsWei",
            "type": "function",
            "stateMutability": "view",
            "inputs": [{"name": "", "type": "address"}],
            "outputs": [{"name": "", "type": "uint256"}],
        },
        {
            "name": "pools",
            "type": "function",
            "stateMutability": "view",
            "inputs": [{"name": "", "type": "bytes32"}],
            "outputs": [
                {"name": "incidentId", "type": "string"},
                {"name": "creator", "type": "address"},
                {"name": "bounty", "type": "uint256"},
                {"name": "resolver", "type": "address"},
                {"name": "resolutionHash", "type": "string"},
                {"name": "isResolved", "type": "bool"},
                {"name": "createdAt", "type": "uint256"},
                {"name": "resolvedAt", "type": "uint256"},
            ],
        },
        {
            "type": "event",
            "name": "PoolCreated",
            "inputs": [
                {"indexed": True, "name": "poolId", "type": "bytes32"},
                {"indexed": False, "name": "incidentId", "type": "string"},
                {"indexed": True, "name": "creator", "type": "address"},
                {"indexed": False, "name": "bounty", "type": "uint256"},
            ],
        },
    ]

    def __init__(
        self,
        *,
        rpc_url: str | None = None,
        rwa_address: str | None = None,
        operator_private_key: str | None = None,
        mock: bool | None = None,
    ) -> None:
        self._rpc = rpc_url or os.environ.get("WEB3_RPC_URL", "")
        self._rwa = rwa_address or os.environ.get("RWA_PROTOCOL_ADDRESS", "")
        self._pk = operator_private_key or os.environ.get("RWA_OPERATOR_PRIVATE_KEY", "")
        self._resolver_pk = os.environ.get("RWA_RESOLVER_PRIVATE_KEY") or self._pk
        if mock is True:
            self._mock = True
        elif mock is False:
            self._mock = False
        else:
            self._mock = os.environ.get("BLOCKCHAIN_MOCK", "1") == "1"
        self._pools: dict[str, IncidentPoolModel] = {}
        self._submissions: dict[str, str] = {}
        self._stakes: dict[str, float] = {}
        self._earnings: dict[str, float] = {}

    async def _async_web3(self) -> Any:
        try:
            from web3 import AsyncWeb3  # type: ignore import-not-found
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Install tutorial[blockchain] for live RWA operations") from exc
        if not self._rpc or not self._rwa:
            raise RuntimeError("WEB3_RPC_URL and RWA_PROTOCOL_ADDRESS must be set for live mode")
        return AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(self._rpc))

    async def _contract(self, w3: Any) -> Any:
        return w3.eth.contract(address=w3.to_checksum_address(self._rwa), abi=self._ABI)

    async def _send_value(self, w3: Any, fn: Any, *, value_wei: int) -> Any:
        if not self._pk:
            raise RuntimeError("RWA_OPERATOR_PRIVATE_KEY is required for live pool operations")
        pk = self._pk.strip()
        if not pk.startswith("0x"):
            pk = "0x" + pk
        account = w3.eth.account.from_key(pk)
        tx = await fn.build_transaction(
            {
                "from": account.address,
                "value": value_wei,
                "nonce": await w3.eth.get_transaction_count(account.address),
                "chainId": await w3.eth.chain_id,
            }
        )
        signed = account.sign_transaction(tx)
        tx_hash = await w3.eth.send_raw_transaction(signed.raw_transaction)
        return await w3.eth.wait_for_transaction_receipt(tx_hash)

    async def _send(self, w3: Any, fn: Any) -> Any:
        if not self._pk:
            raise RuntimeError("RWA_OPERATOR_PRIVATE_KEY is required for live transactions")
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

    async def _send_with_key(self, w3: Any, fn: Any, private_key: str) -> Any:
        pk = private_key.strip()
        if not pk:
            raise RuntimeError("private key missing for resolution transaction")
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

    async def create_incident_pool(self, incident_id: str, bounty: float) -> str:
        """Create a bounty pool; ``bounty`` is denominated in native gas tokens (ETH/MNT)."""
        if bounty <= 0:
            raise ValueError("bounty must be positive")
        wei = int(round(bounty * 10**18))
        if self._mock:
            pool_id = "0x" + secrets.token_hex(32)
            self._pools[pool_id] = IncidentPoolModel(
                pool_id=pool_id,
                incident_id=incident_id,
                bounty_wei=wei,
            )
            logger.info("incident_pool_mock", pool_id=pool_id, incident=incident_id)
            return pool_id

        w3 = await self._async_web3()
        contract = await self._contract(w3)
        fn = contract.functions.createPool(incident_id)
        receipt = await self._send_value(w3, fn, value_wei=wei)
        decoded = contract.events.PoolCreated().process_receipt(receipt)
        if not decoded:
            raise RuntimeError("PoolCreated event not found in receipt")
        pool_id_bytes = decoded[0]["args"]["poolId"]
        return w3.to_hex(pool_id_bytes)

    async def submit_resolution(self, agent_did: str, pool_id: str, resolution_hash: str) -> None:
        """Record a resolver candidate for a pool (mock tracks ``agent_did`` for earnings attribution)."""
        if self._mock:
            if pool_id not in self._pools:
                raise ValueError("unknown pool_id")
            self._submissions[pool_id] = resolution_hash
            self._pools[pool_id].resolver = agent_did
            self._pools[pool_id].resolution_hash = resolution_hash
            logger.info("resolution_submitted_mock", pool_id=pool_id, agent=agent_did)
            return

        w3 = await self._async_web3()
        contract = await self._contract(w3)
        fn = contract.functions.submitResolution(bytes.fromhex(pool_id[2:]), resolution_hash)
        await self._send_with_key(w3, fn, self._resolver_pk)

    async def validate_resolution(self, pool_id: str, resolution_hash: str) -> bool:
        """Validate a submitted resolution and release funds (owner/oracle on-chain)."""
        if self._mock:
            pool = self._pools.get(pool_id)
            if not pool:
                return False
            if pool.resolved:
                return False
            if self._submissions.get(pool_id) != resolution_hash:
                return False
            pool.resolved = True
            if pool.resolver:
                self._earnings[pool.resolver] = self._earnings.get(pool.resolver, 0.0) + pool.bounty_wei / 10**18
            logger.info("resolution_validated_mock", pool_id=pool_id)
            return True

        w3 = await self._async_web3()
        contract = await self._contract(w3)
        fn = contract.functions.validateAndPay(bytes.fromhex(pool_id[2:]), resolution_hash)
        try:
            await self._send(w3, fn)
            return True
        except Exception:  # noqa: BLE001
            return False

    async def stake_for_priority(self, organization: str, amount: float) -> None:
        """Stake native tokens to increase priority weight for an organization address."""
        if amount <= 0:
            raise ValueError("amount must be positive")
        wei = int(round(amount * 10**18))
        org = organization.lower()
        if self._mock:
            self._stakes[org] = self._stakes.get(org, 0.0) + amount
            logger.info("stake_mock", org=org, amount=amount)
            return

        w3 = await self._async_web3()
        contract = await self._contract(w3)
        operator = w3.eth.account.from_key(self._pk).address
        if w3.to_checksum_address(organization) != w3.to_checksum_address(operator):
            raise RuntimeError(
                "stake_for_priority in live mode currently requires organization address "
                "to match RWA_OPERATOR_PRIVATE_KEY for the demo integration"
            )
        fn = contract.functions.stakeForPriority()
        await self._send_value(w3, fn, value_wei=wei)

    async def get_agent_earnings(self, agent_did: str) -> float:
        """Return cumulative native-token earnings for the resolver DID/identifier."""
        if self._mock:
            return float(self._earnings.get(agent_did, 0.0))

        w3 = await self._async_web3()
        contract = await self._contract(w3)
        if not agent_did.startswith("0x") or len(agent_did) != 42:
            raise ValueError("live mode expects agent_did to be a resolver 0x address string")
        wei = int(await contract.functions.agentEarningsWei(w3.to_checksum_address(agent_did)).call())
        return wei / 10**18
