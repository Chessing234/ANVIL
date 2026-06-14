// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Ownable, ReentrancyGuard} from "./Security.sol";

/// @title AgentRegistry — on-chain identity, reputation, and audit trail for TUTORIAL agents.
/// @dev Optimized with `bytes32` keys for hot-path lookups; full DID retained in storage.
contract AgentRegistry is Ownable, ReentrancyGuard {
    struct Agent {
        string did;
        string name;
        string agentType;
        address owner;
        address signingKey;
        uint256 reputation;
        uint256 investigationsCompleted;
        uint256 lessonsGenerated;
        bool isActive;
        uint256 registeredAt;
    }

    struct AgentAction {
        string actionType;
        string payloadHash;
        uint256 timestamp;
        string result;
    }

    uint256 private _nextAgentId = 1;
    mapping(uint256 => Agent) private _agents;
    mapping(bytes32 => uint256) private _didHashToAgentId;
    mapping(uint256 => AgentAction[]) private _actions;
    mapping(bytes32 => bool) private _reportSigned;

    event AgentRegistered(uint256 indexed agentId, string did, address indexed ownerAddr);
    event ReportSigned(uint256 indexed agentId, bytes32 indexed reportHash, address indexed signer);
    event ReputationUpdated(uint256 indexed agentId, string action, string result, uint256 reputation);

    error AgentRegistryInvalidInput();
    error AgentRegistryDidExists();
    error AgentRegistryUnknownAgent();
    error AgentRegistryBadSignature();
    error AgentRegistryDuplicateReport();

    function registerAgent(
        string calldata did,
        string calldata name_,
        string calldata agentType_,
        address signingKey_
    ) external nonReentrant returns (uint256 agentId) {
        if (bytes(did).length == 0 || bytes(name_).length == 0 || signingKey_ == address(0)) {
            revert AgentRegistryInvalidInput();
        }
        bytes32 key = keccak256(bytes(did));
        if (_didHashToAgentId[key] != 0) revert AgentRegistryDidExists();

        agentId = _nextAgentId++;
        _didHashToAgentId[key] = agentId;
        _agents[agentId] = Agent({
            did: did,
            name: name_,
            agentType: agentType_,
            owner: msg.sender,
            signingKey: signingKey_,
            reputation: 0,
            investigationsCompleted: 0,
            lessonsGenerated: 0,
            isActive: true,
            registeredAt: block.timestamp
        });

        emit AgentRegistered(agentId, did, msg.sender);
    }

    function submitReportSignature(uint256 agentId, bytes32 reportHash, uint8 v, bytes32 r, bytes32 s)
        external
        nonReentrant
    {
        Agent storage agent = _requireAgent(agentId);
        if (reportHash == bytes32(0)) revert AgentRegistryInvalidInput();

        bytes32 ethSigned = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", reportHash));
        address recovered = ecrecover(ethSigned, v, r, s);
        if (recovered != agent.signingKey) revert AgentRegistryBadSignature();

        bytes32 onceKey = keccak256(abi.encodePacked(agentId, reportHash));
        if (_reportSigned[onceKey]) revert AgentRegistryDuplicateReport();
        _reportSigned[onceKey] = true;

        _actions[agentId].push(
            AgentAction({
                actionType: "investigation",
                payloadHash: _toHex(reportHash),
                timestamp: block.timestamp,
                result: "signed"
            })
        );
        unchecked {
            agent.investigationsCompleted += 1;
        }
        emit ReportSigned(agentId, reportHash, recovered);
    }

    function verifyReportSignature(uint256 agentId, bytes32 reportHash, uint8 v, bytes32 r, bytes32 s)
        external
        view
        returns (bool)
    {
        Agent memory agent = _agents[agentId];
        if (agent.owner == address(0)) return false;
        bytes32 ethSigned = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", reportHash));
        address recovered = ecrecover(ethSigned, v, r, s);
        return recovered == agent.signingKey;
    }

    function getAgentActions(uint256 agentId, uint256 start, uint256 count)
        external
        view
        returns (AgentAction[] memory page)
    {
        _requireAgent(agentId);
        AgentAction[] storage actions = _actions[agentId];
        uint256 total = actions.length;
        if (start >= total) {
            return new AgentAction[](0);
        }
        uint256 end = start + count;
        if (end > total) end = total;
        uint256 n = end - start;
        page = new AgentAction[](n);
        for (uint256 i = 0; i < n; i++) {
            page[i] = actions[start + i];
        }
    }

    function updateReputation(uint256 agentId, string calldata action, string calldata result)
        external
        onlyOwner
        nonReentrant
    {
        Agent storage agent = _requireAgent(agentId);
        unchecked {
            agent.reputation += 1;
            if (keccak256(bytes(action)) == keccak256(bytes("lesson"))) {
                agent.lessonsGenerated += 1;
            }
        }
        _actions[agentId].push(
            AgentAction({actionType: action, payloadHash: "", timestamp: block.timestamp, result: result})
        );
        emit ReputationUpdated(agentId, action, result, agent.reputation);
    }

    function agentById(uint256 agentId) external view returns (Agent memory) {
        return _agents[agentId];
    }

    function agentIdForDid(string calldata did) external view returns (uint256) {
        return _didHashToAgentId[keccak256(bytes(did))];
    }

    function _requireAgent(uint256 agentId) internal view returns (Agent storage agent) {
        agent = _agents[agentId];
        if (agent.owner == address(0)) revert AgentRegistryUnknownAgent();
    }

    function _toHex(bytes32 value) private pure returns (string memory) {
        bytes16 symbols = "0123456789abcdef";
        bytes memory str = new bytes(66);
        str[0] = "0";
        str[1] = "x";
        for (uint256 i = 0; i < 32; i++) {
            str[2 + i * 2] = symbols[uint8(value[i] >> 4)];
            str[3 + i * 2] = symbols[uint8(value[i] & 0x0f)];
        }
        return string(str);
    }
}
