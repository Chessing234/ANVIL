// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {CredentialNFT} from "../contracts/CredentialNFT.sol";

contract CredentialNFTTest {
    function test_mint_and_meta() public {
        CredentialNFT nft = new CredentialNFT();
        address student = address(uint160(uint256(keccak256("student"))));

        uint256 tid = nft.mintCredential(student, "lesson-dns-101", 9200);
        assert(tid == 1);
        assert(nft.ownerOf(tid) == student);

        (string memory lesson, uint256 score, address who) = nft.credentialMeta(tid);
        assert(who == student);
        assert(score == 9200);
        assert(keccak256(bytes(lesson)) == keccak256(bytes("lesson-dns-101")));

        uint256[] memory ids = nft.tokensOfStudent(student);
        assert(ids.length == 1 && ids[0] == 1);
    }
}
