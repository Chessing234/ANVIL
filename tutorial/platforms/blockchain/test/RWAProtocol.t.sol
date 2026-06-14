// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {RWAProtocol} from "../contracts/RWAProtocol.sol";
import {CheatCodes} from "./CheatCodes.sol";

contract RWAProtocolTest {
    function test_pool_validate_pays_resolver() public {
        RWAProtocol rwa = new RWAProtocol();
        CheatCodes.vm().deal(address(this), 50 ether);

        bytes32 poolId = rwa.createPool{value: 2 ether}("incident-42");
        assert(uint256(poolId) != 0);

        rwa.submitResolution(poolId, "QmResolution");
        (, , , address resolver,, bool isResolved,,) = rwa.pools(poolId);
        assert(resolver == address(this));
        assert(!isResolved);

        rwa.validateAndPay(poolId, "QmResolution");
        (, , , address resolver2,, bool isResolved2,,) = rwa.pools(poolId);
        assert(resolver2 == address(this));
        assert(isResolved2);
    }

    function test_stake_increments_priority() public {
        RWAProtocol rwa = new RWAProtocol();
        CheatCodes.vm().deal(address(this), 5 ether);
        rwa.stakeForPriority{value: 1 ether}();
        assert(rwa.stakerPriorityWei(address(this)) == 1 ether);
    }

    receive() external payable {}
}
