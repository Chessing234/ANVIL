# TUTORIAL × Blockchain (Turing Test)

Solidity sources live in `contracts/` and target **EVM-compatible** networks (including **Mantle testnet** for the Turing Test). Python modules under this package default to **`BLOCKCHAIN_MOCK=1`** so CI and laptops work without RPC credentials.

## Foundry (Solidity tests)

```bash
cd tutorial/platforms/blockchain
forge test
```

Contracts are self-contained (no external npm/git dependencies). `test/CheatCodes.sol` exposes the canonical Hevm address for `deal` in `forge test`.

## Python (live RPC)

```bash
pip install 'tutorial[blockchain]'
export BLOCKCHAIN_MOCK=0
export WEB3_RPC_URL="https://rpc.sepolia.mantle.xyz"   # example — use your Mantle RPC
export AGENT_REGISTRY_ADDRESS=0x...
export CREDENTIAL_NFT_ADDRESS=0x...
export RWA_PROTOCOL_ADDRESS=0x...
```

Use `AGENT_OWNER_PRIVATE_KEY`, `CREDENTIAL_MINTER_PRIVATE_KEY`, `RWA_OPERATOR_PRIVATE_KEY`, and (for resolutions) `RWA_RESOLVER_PRIVATE_KEY`. For `submitReportSignature`, `AGENT_SIGNING_PRIVATE_KEY` must match the **signingKey** address used when the agent was registered.
