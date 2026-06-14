"""Verifiable education credentials as ERC-721 compatible NFTs (Mantle / EVM)."""

from __future__ import annotations

import os
import time
from typing import Any

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


class Credential(BaseModel):
    """Portable proof of lesson completion."""

    model_config = {"extra": "forbid"}

    token_id: str = Field(min_length=1)
    student_address: str = Field(min_length=1)
    lesson_id: str = Field(min_length=1)
    score: float = Field(ge=0.0, le=100.0)
    valid: bool = True
    metadata_uri: str = Field(default="")


class CredentialNFT:
    """Mint and verify on-chain credentials; mock backend mirrors contract semantics."""

    _ABI: list[dict[str, Any]] = [
        {
            "name": "mintCredential",
            "type": "function",
            "stateMutability": "nonpayable",
            "inputs": [
                {"name": "student", "type": "address"},
                {"name": "lessonId", "type": "string"},
                {"name": "scoreBps", "type": "uint256"},
            ],
            "outputs": [{"name": "", "type": "uint256"}],
        },
        {
            "name": "credentialMeta",
            "type": "function",
            "stateMutability": "view",
            "inputs": [{"name": "tokenId", "type": "uint256"}],
            "outputs": [
                {"name": "lessonId", "type": "string"},
                {"name": "scoreBps", "type": "uint256"},
                {"name": "student", "type": "address"},
            ],
        },
        {
            "name": "tokensOfStudent",
            "type": "function",
            "stateMutability": "view",
            "inputs": [{"name": "student", "type": "address"}],
            "outputs": [{"name": "", "type": "uint256[]"}],
        },
        {
            "name": "tokenURI",
            "type": "function",
            "stateMutability": "view",
            "inputs": [{"name": "tokenId", "type": "uint256"}],
            "outputs": [{"name": "", "type": "string"}],
        },
    ]

    def __init__(
        self,
        *,
        rpc_url: str | None = None,
        nft_address: str | None = None,
        minter_private_key: str | None = None,
        mock: bool | None = None,
    ) -> None:
        self._rpc = rpc_url or os.environ.get("WEB3_RPC_URL", "")
        self._nft = nft_address or os.environ.get("CREDENTIAL_NFT_ADDRESS", "")
        self._pk = minter_private_key or os.environ.get("CREDENTIAL_MINTER_PRIVATE_KEY", "")
        if mock is True:
            self._mock = True
        elif mock is False:
            self._mock = False
        else:
            self._mock = os.environ.get("BLOCKCHAIN_MOCK", "1") == "1"
        self._next_id = 1
        self._owners: dict[int, str] = {}
        self._lesson: dict[int, str] = {}
        self._score_bps: dict[int, int] = {}
        self._by_student: dict[str, list[int]] = {}

    async def _async_web3(self) -> Any:
        try:
            from web3 import AsyncWeb3  # type: ignore import-not-found
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Install tutorial[blockchain] for live NFT operations") from exc
        if not self._rpc or not self._nft:
            raise RuntimeError("WEB3_RPC_URL and CREDENTIAL_NFT_ADDRESS must be set for live mode")
        return AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(self._rpc))

    async def _contract(self, w3: Any) -> Any:
        return w3.eth.contract(address=w3.to_checksum_address(self._nft), abi=self._ABI)

    async def _send(self, w3: Any, fn: Any) -> Any:
        if not self._pk:
            raise RuntimeError("CREDENTIAL_MINTER_PRIVATE_KEY is required for minting on-chain")
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

    async def mint_credential(self, student_address: str, lesson_id: str, score: float) -> str:
        """Mint a credential NFT; returns ``token_id`` as decimal string."""
        if score < 0 or score > 100:
            raise ValueError("score must be between 0 and 100")
        score_bps = int(round(score * 100))
        if self._mock:
            tid = self._next_id
            self._next_id += 1
            self._owners[tid] = student_address.lower()
            self._lesson[tid] = lesson_id
            self._score_bps[tid] = score_bps
            self._by_student.setdefault(student_address.lower(), []).append(tid)
            logger.info("credential_minted_mock", token_id=tid, lesson=lesson_id)
            return str(tid)

        w3 = await self._async_web3()
        contract = await self._contract(w3)
        fn = contract.functions.mintCredential(
            w3.to_checksum_address(student_address),
            lesson_id,
            score_bps,
        )
        receipt = await self._send(w3, fn)
        _ = receipt
        ids = await contract.functions.tokensOfStudent(w3.to_checksum_address(student_address)).call()
        token_id = str(int(ids[-1]))
        logger.info("credential_minted_chain", token_id=token_id)
        return token_id

    async def verify_credential(self, token_id: str) -> Credential:
        """Return structured credential details and validity."""
        tid = int(token_id)
        if self._mock:
            if tid not in self._owners:
                return Credential(
                    token_id=token_id,
                    student_address="0x0000000000000000000000000000000000000000",
                    lesson_id="",
                    score=0.0,
                    valid=False,
                )
            student = self._owners[tid]
            return Credential(
                token_id=token_id,
                student_address=student,
                lesson_id=self._lesson[tid],
                score=self._score_bps[tid] / 100.0,
                valid=True,
                metadata_uri=f"ipfs://tutorial/credentials/{tid}",
            )

        w3 = await self._async_web3()
        contract = await self._contract(w3)
        try:
            _ = await contract.functions.ownerOf(tid).call()
        except Exception:  # noqa: BLE001 - broad for missing token across providers
            return Credential(
                token_id=token_id,
                student_address="0x0000000000000000000000000000000000000000",
                lesson_id="",
                score=0.0,
                valid=False,
            )
        lesson, score_bps, student = await contract.functions.credentialMeta(tid).call()
        uri = await contract.functions.tokenURI(tid).call()
        return Credential(
            token_id=token_id,
            student_address=str(student),
            lesson_id=str(lesson),
            score=float(int(score_bps)) / 100.0,
            valid=True,
            metadata_uri=str(uri),
        )

    async def get_student_credentials(self, student_address: str) -> list[Credential]:
        """Return all credentials owned by ``student_address``."""
        key = student_address.lower()
        if self._mock:
            out: list[Credential] = []
            for tid in self._by_student.get(key, []):
                out.append(await self.verify_credential(str(tid)))
            return out

        w3 = await self._async_web3()
        contract = await self._contract(w3)
        ids = await contract.functions.tokensOfStudent(w3.to_checksum_address(student_address)).call()
        creds: list[Credential] = []
        for raw in ids:
            creds.append(await self.verify_credential(str(int(raw))))
        return creds

    async def get_credential_metadata(self, token_id: str) -> dict[str, Any]:
        """Return OpenSea-style metadata enriched with CSTA / difficulty defaults."""
        base = await self.verify_credential(token_id)
        if not base.valid:
            return {"valid": False, "token_id": token_id}
        completed = int(time.time())
        return {
            "name": f"Cybersecurity Fundamentals — {base.lesson_id}",
            "description": "Completed interactive TUTORIAL lesson (verifiable on-chain credential).",
            "image": f"ipfs://tutorial/credentials/{token_id}/badge.svg",
            "attributes": [
                {"trait_type": "Category", "value": "Network Security"},
                {"trait_type": "Difficulty", "value": "Intermediate"},
                {"trait_type": "Score", "value": int(round(base.score))},
                {
                    "trait_type": "Concepts",
                    "value": ["DNS", "Exfiltration", "Wireshark"],
                },
                {"trait_type": "CSTA_Standard", "value": "3A-NI-07"},
                {"trait_type": "Completed", "display_type": "date", "value": completed},
            ],
        }
