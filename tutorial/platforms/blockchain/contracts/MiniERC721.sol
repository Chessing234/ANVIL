// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Ownable} from "./Security.sol";

interface IERC721Receiver {
    function onERC721Received(address operator, address from, uint256 tokenId, bytes calldata data)
        external
        returns (bytes4);
}

/// @dev Minimal ERC721 (no enumerable) — self-contained for hackathon deployments.
abstract contract MiniERC721 is Ownable {
    string private _name;
    string private _symbol;

    mapping(uint256 => address) private _owners;
    mapping(address => uint256) private _balances;
    mapping(uint256 => address) private _tokenApprovals;
    mapping(address => mapping(address => bool)) private _operatorApprovals;
    mapping(uint256 => string) private _tokenURIs;
    uint256 private _totalMinted;

    event Transfer(address indexed from, address indexed to, uint256 indexed tokenId);
    event Approval(address indexed owner, address indexed approved, uint256 indexed tokenId);
    event ApprovalForAll(address indexed owner, address indexed operator, bool approved);

    error ERC721InvalidReceiver(address to);
    error ERC721NonexistentToken(uint256 tokenId);
    error ERC721TokenAlreadyMinted(uint256 tokenId);
    error ERC721IncorrectOwner(address sender, uint256 tokenId, address actualOwner);

    constructor(string memory name_, string memory symbol_) Ownable() {
        _name = name_;
        _symbol = symbol_;
    }

    function name() external view returns (string memory) {
        return _name;
    }

    function symbol() external view returns (string memory) {
        return _symbol;
    }

    function totalSupply() external view returns (uint256) {
        return _totalMinted;
    }

    function balanceOf(address account) external view returns (uint256) {
        return _balances[account];
    }

    function ownerOf(uint256 tokenId) public view returns (address) {
        address owner_ = _owners[tokenId];
        if (owner_ == address(0)) revert ERC721NonexistentToken(tokenId);
        return owner_;
    }

    function tokenURI(uint256 tokenId) public view returns (string memory) {
        ownerOf(tokenId);
        return _tokenURIs[tokenId];
    }

    function getApproved(uint256 tokenId) external view returns (address) {
        ownerOf(tokenId);
        return _tokenApprovals[tokenId];
    }

    function isApprovedForAll(address holder, address operator) external view returns (bool) {
        return _operatorApprovals[holder][operator];
    }

    function approve(address to, uint256 tokenId) external {
        address owner_ = ownerOf(tokenId);
        if (msg.sender != owner_ && !_operatorApprovals[owner_][msg.sender]) {
            revert ERC721IncorrectOwner(msg.sender, tokenId, owner_);
        }
        _tokenApprovals[tokenId] = to;
        emit Approval(owner_, to, tokenId);
    }

    function setApprovalForAll(address operator, bool approved) external {
        _operatorApprovals[msg.sender][operator] = approved;
        emit ApprovalForAll(msg.sender, operator, approved);
    }

    function transferFrom(address from, address to, uint256 tokenId) public virtual {
        _transfer(from, to, tokenId, false);
    }

    function safeTransferFrom(address from, address to, uint256 tokenId) external {
        _transfer(from, to, tokenId, true);
    }

    function _mint(address to, uint256 tokenId, string memory uri_) internal {
        if (to == address(0)) revert ERC721InvalidReceiver(address(0));
        if (_owners[tokenId] != address(0)) revert ERC721TokenAlreadyMinted(tokenId);
        unchecked {
            _balances[to] += 1;
        }
        _owners[tokenId] = to;
        _tokenURIs[tokenId] = uri_;
        _totalMinted += 1;
        emit Transfer(address(0), to, tokenId);
    }

    function _transfer(address from, address to, uint256 tokenId, bool doSafeCheck) internal {
        address owner_ = ownerOf(tokenId);
        if (owner_ != from) revert ERC721IncorrectOwner(from, tokenId, owner_);
        if (to == address(0)) revert ERC721InvalidReceiver(address(0));
        if (!_isAuthorized(owner_, msg.sender, tokenId)) {
            revert ERC721IncorrectOwner(msg.sender, tokenId, owner_);
        }
        delete _tokenApprovals[tokenId];
        unchecked {
            _balances[from] -= 1;
            _balances[to] += 1;
        }
        _owners[tokenId] = to;
        emit Transfer(from, to, tokenId);
        if (doSafeCheck && to.code.length > 0) {
            (bool ok, bytes memory ret) = to.call(
                abi.encodeCall(IERC721Receiver.onERC721Received, (msg.sender, from, tokenId, ""))
            );
            if (
                !ok || ret.length < 32
                    || abi.decode(ret, (bytes4)) != IERC721Receiver.onERC721Received.selector
            ) {
                revert ERC721InvalidReceiver(to);
            }
        }
    }

    function _isAuthorized(address owner_, address spender, uint256 tokenId) internal view returns (bool) {
        return spender == owner_ || _tokenApprovals[tokenId] == spender || _operatorApprovals[owner_][spender];
    }
}
