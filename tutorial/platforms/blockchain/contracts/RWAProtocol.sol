// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Ownable, ReentrancyGuard} from "./Security.sol";

/// @title RWAProtocol — incident response bounties, staking for priority, and agent payouts.
contract RWAProtocol is Ownable, ReentrancyGuard {
    struct IncidentPool {
        string incidentId;
        address creator;
        uint256 bounty;
        address resolver;
        string resolutionHash;
        bool isResolved;
        uint256 createdAt;
        uint256 resolvedAt;
    }

    mapping(bytes32 => IncidentPool) public pools;
    mapping(address => uint256) public stakerPriorityWei;
    mapping(address => uint256) public agentEarningsWei;
    mapping(address => uint256) public creatorNonce;

    event PoolCreated(bytes32 indexed poolId, string incidentId, address indexed creator, uint256 bounty);
    event ResolutionSubmitted(bytes32 indexed poolId, address indexed resolver, string resolutionHash);
    event ResolutionValidated(bytes32 indexed poolId, address indexed resolver, uint256 payout);
    event StakedForPriority(address indexed org, uint256 amount);

    error RWABadInput();
    error RWAPoolMissing();
    error RWAPoolAlreadyResolved();
    error RWANoSubmission();
    error RWAMismatch();
    error RWATransferFailed();

    function createPool(string calldata incidentId) external payable nonReentrant returns (bytes32 poolId) {
        if (bytes(incidentId).length == 0 || msg.value == 0) revert RWABadInput();
        uint256 nonce = ++creatorNonce[msg.sender];
        poolId = keccak256(abi.encodePacked(incidentId, msg.sender, block.chainid, nonce));
        IncidentPool storage p = pools[poolId];
        if (p.creator != address(0)) revert RWABadInput();

        p.incidentId = incidentId;
        p.creator = msg.sender;
        p.bounty = msg.value;
        p.createdAt = block.timestamp;
        emit PoolCreated(poolId, incidentId, msg.sender, msg.value);
    }

    function submitResolution(bytes32 poolId, string calldata resolutionHash) external nonReentrant {
        IncidentPool storage p = pools[poolId];
        if (p.creator == address(0)) revert RWAPoolMissing();
        if (p.isResolved) revert RWAPoolAlreadyResolved();
        if (bytes(resolutionHash).length == 0) revert RWABadInput();
        if (p.resolver != address(0)) revert RWABadInput();

        p.resolver = msg.sender;
        p.resolutionHash = resolutionHash;
        emit ResolutionSubmitted(poolId, msg.sender, resolutionHash);
    }

    function validateAndPay(bytes32 poolId, string calldata expectedHash) external onlyOwner nonReentrant {
        IncidentPool storage p = pools[poolId];
        if (p.creator == address(0)) revert RWAPoolMissing();
        if (p.isResolved) revert RWAPoolAlreadyResolved();
        if (p.resolver == address(0)) revert RWANoSubmission();
        if (keccak256(bytes(p.resolutionHash)) != keccak256(bytes(expectedHash))) revert RWAMismatch();

        uint256 payout = p.bounty;
        address resolver = p.resolver;
        p.isResolved = true;
        p.resolvedAt = block.timestamp;
        p.bounty = 0;

        agentEarningsWei[resolver] += payout;

        (bool ok,) = payable(resolver).call{value: payout}("");
        if (!ok) revert RWATransferFailed();

        emit ResolutionValidated(poolId, resolver, payout);
    }

    function stakeForPriority() external payable nonReentrant {
        if (msg.value == 0) revert RWABadInput();
        stakerPriorityWei[msg.sender] += msg.value;
        emit StakedForPriority(msg.sender, msg.value);
    }
}
