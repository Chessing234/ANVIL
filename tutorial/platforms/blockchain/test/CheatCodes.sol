// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @dev Minimal Foundry cheat interface (no forge-std dependency in-repo).
interface Vm {
    function deal(address account, uint256 newBalance) external;
}

library CheatCodes {
    /// @dev Canonical address used by Foundry/Hevm cheatcodes.
    function vm() internal pure returns (Vm) {
        return Vm(0x7109709ECfa91a62626fF4237597141e356Ae0A6);
    }
}
