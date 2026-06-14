// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {AgentRegistry} from "../contracts/AgentRegistry.sol";
import {CheatCodes} from "./CheatCodes.sol";

contract AgentRegistryTest {
    function test_register_and_reputation_history() public {
        AgentRegistry reg = new AgentRegistry();
        address signing = address(uint160(uint256(keccak256("signing"))));

        uint256 agentId = reg.registerAgent("did:tutorial:hunter:1111", "Unit", "hunter", signing);
        assert(agentId == 1);
        assert(reg.agentIdForDid("did:tutorial:hunter:1111") == 1);

        reg.updateReputation(agentId, "lesson", "success");

        AgentRegistry.AgentAction[] memory page = reg.getAgentActions(agentId, 0, 10);
        assert(page.length == 1);
        assert(keccak256(bytes(page[0].actionType)) == keccak256(bytes("lesson")));
    }

    function test_duplicate_did_reverts() public {
        AgentRegistry reg = new AgentRegistry();
        address signing = address(uint160(uint256(keccak256("signing2"))));
        reg.registerAgent("did:tutorial:dup:2222", "A", "t", signing);
        (bool ok,) = address(reg).call(
            abi.encodeWithSelector(
                AgentRegistry.registerAgent.selector,
                "did:tutorial:dup:2222",
                "B",
                "t",
                signing
            )
        );
        assert(!ok);
    }
}
