// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title Lightweight access control (gas-conscious single owner).
abstract contract Ownable {
    address public owner;

    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);

    error OwnableUnauthorized(address caller);

    constructor() {
        owner = msg.sender;
        emit OwnershipTransferred(address(0), msg.sender);
    }

    modifier onlyOwner() {
        _checkOwner();
        _;
    }

    function _checkOwner() internal view {
        if (msg.sender != owner) revert OwnableUnauthorized(msg.sender);
    }

    function transferOwnership(address newOwner) external onlyOwner {
        if (newOwner == address(0)) revert OwnableUnauthorized(address(0));
        emit OwnershipTransferred(owner, newOwner);
        owner = newOwner;
    }
}

/// @title Reentrancy guard (checks-effects-interactions companion).
abstract contract ReentrancyGuard {
    uint256 private constant _NOT_ENTERED = 1;
    uint256 private constant _ENTERED = 2;
    uint256 private _status;

    error ReentrancyGuardReentrantCall();

    constructor() {
        _status = _NOT_ENTERED;
    }

    modifier nonReentrant() {
        if (_status == _ENTERED) revert ReentrancyGuardReentrantCall();
        _status = _ENTERED;
        _;
        _status = _NOT_ENTERED;
    }
}
