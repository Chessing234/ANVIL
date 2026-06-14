// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {MiniERC721} from "./MiniERC721.sol";
import {ReentrancyGuard} from "./Security.sol";

/// @title CredentialNFT — ERC-721 education credentials with on-chain lesson/score metadata.
contract CredentialNFT is MiniERC721, ReentrancyGuard {
    uint256 private _nextTokenId = 1;
    mapping(address => uint256[]) private _tokensOfStudent;
    mapping(uint256 => address) private _studentOf;
    mapping(uint256 => string) private _lessonOf;
    mapping(uint256 => uint256) private _scoreBpsOf;

    event CredentialMinted(
        uint256 indexed tokenId, address indexed student, string lessonId, uint256 scoreBps
    );

    error CredentialInvalidStudent();
    error CredentialInvalidScore();

    constructor() MiniERC721("TUTORIAL Credential", "TCRED") {}

    function mintCredential(address student, string calldata lessonId, uint256 scoreBps)
        external
        onlyOwner
        nonReentrant
        returns (uint256 tokenId)
    {
        if (student == address(0)) revert CredentialInvalidStudent();
        if (scoreBps > 10_000) revert CredentialInvalidScore();

        tokenId = _nextTokenId++;
        string memory uri_ = string.concat("ipfs://tutorial/credentials/", _toHex(keccak256(abi.encodePacked(
                lessonId,
                scoreBps,
                student,
                tokenId
            ))));
        _mint(student, tokenId, uri_);
        _tokensOfStudent[student].push(tokenId);
        _studentOf[tokenId] = student;
        _lessonOf[tokenId] = lessonId;
        _scoreBpsOf[tokenId] = scoreBps;
        emit CredentialMinted(tokenId, student, lessonId, scoreBps);
    }

    function credentialMeta(uint256 tokenId)
        external
        view
        returns (string memory lessonId, uint256 scoreBps, address student)
    {
        ownerOf(tokenId);
        return (_lessonOf[tokenId], _scoreBpsOf[tokenId], _studentOf[tokenId]);
    }

    function tokensOfStudent(address student) external view returns (uint256[] memory) {
        return _tokensOfStudent[student];
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
