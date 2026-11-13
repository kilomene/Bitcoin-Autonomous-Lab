#!/usr/bin/env python3
"""Correctness proofs against known, real Bitcoin data.

1. Hashing the real genesis block header with double SHA-256 must
   reproduce its known block hash, and that hash must meet the genesis
   target. This proves the hashing path is Bitcoin's, not a lookalike.

2. The Stratum header builder must reproduce the genesis header when fed
   the genesis fields in Stratum form, including its known nonce.

Run: python3 tests/test_known_blocks.py
"""

import hashlib
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "mining"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from stratum_client import build_header, dsha256, target_for_difficulty, DIFF1_TARGET
from mining.pow import merkle_root, target_from_nbits, difficulty_from_nbits, coinbase_subsidy

GENESIS_HEADER_HEX = (
    "01000000"
    "0000000000000000000000000000000000000000000000000000000000000000"
    "3ba3edfd7a7b12b27ac72c3e67768f617fc81bc3888a51323a9fb8aa4b1e5e4a"
    "29ab5f49"
    "ffff001d"
    "1dac2b7c"
)
GENESIS_HASH = "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f"
GENESIS_NONCE = 2083236893
GENESIS_MERKLE_DISPLAY = "4a5e1e4baab89f3a32518a88c31bc87f618f76673e2cc77ab2127b7afdeda33b"


def test_genesis_hash():
    header = bytes.fromhex(GENESIS_HEADER_HEX)
    assert len(header) == 80
    digest = dsha256(header)
    display = digest[::-1].hex()
    assert display == GENESIS_HASH, display
    # Genesis target from nbits 1d00ffff equals the difficulty-1 target.
    assert int(display, 16) <= DIFF1_TARGET
    print("ok: genesis header hashes to its known block hash")


def test_diff1_target():
    assert target_for_difficulty(1.0) == DIFF1_TARGET
    assert target_for_difficulty(2.0) == DIFF1_TARGET // 2
    print("ok: difficulty to target conversion")


def test_build_header_genesis_shape():
    # Build a header through the Stratum path using genesis values.
    # The genesis coinbase is reconstructed in two halves around the
    # extranonces so the builder assembles the exact genesis coinbase:
    # coinb1 + en1 + en2 + coinb2 must equal the genesis coinbase tx,
    # whose hash (internal order) is the merkle root itself.
    coinbase_tx_hex = (
        "01000000010000000000000000000000000000000000000000000000000000000000000000"
        "ffffffff4d04ffff001d0104455468652054696d65732030332f4a616e2f323030392043"
        "68616e63656c6c6f72206f6e206272696e6b206f66207365636f6e64206261696c6f7574"
        "20666f722062616e6b73ffffffff0100f2052a01000000434104678afdb0fe5548271967"
        "f1a67130b7105cd6a828e03909a67962e0ea1f61deb649f6bc3f4cef38c4f35504e51ec1"
        "12de5c384df7ba0b8d578a4c702b6bf11d5fac00000000"
    )
    coinbase = bytes.fromhex(coinbase_tx_hex)
    assert dsha256(coinbase)[::-1].hex() == GENESIS_MERKLE_DISPLAY
    half = 40
    job = {
        "job_id": "genesis",
        "prevhash": "00" * 32,
        "coinb1": coinbase[:half].hex(),
        "coinb2": coinbase[half + 8:].hex(),
        "merkle_branch": [],
        "version": "00000001",
        "nbits": "1d00ffff",
        "ntime": "495fab29",
    }
    # en1 is 4 bytes and en2 is 4 bytes in this synthetic job
    en1 = coinbase[half:half + 4].hex()
    en2 = coinbase[half + 4:half + 8].hex()
    header, merkle, built_coinbase = build_header(
        job, en1, en2, GENESIS_NONCE, "wordswap")
    assert built_coinbase == coinbase
    assert header == bytes.fromhex(GENESIS_HEADER_HEX), header.hex()
    assert dsha256(header)[::-1].hex() == GENESIS_HASH
    print("ok: stratum header builder reproduces the genesis header exactly")


def test_pow_module():
    # nbits expansion and difficulty agree with the Stratum helpers.
    assert target_from_nbits(0x1D00FFFF) == DIFF1_TARGET
    assert abs(difficulty_from_nbits(0x1D00FFFF) - 1.0) < 1e-12
    # Merkle root of the single genesis coinbase is its own txid.
    coinbase_txid_internal = dsha256(bytes.fromhex(
        "01000000010000000000000000000000000000000000000000000000000000000000000000"
        "ffffffff4d04ffff001d0104455468652054696d65732030332f4a616e2f323030392043"
        "68616e63656c6c6f72206f6e206272696e6b206f66207365636f6e64206261696c6f7574"
        "20666f722062616e6b73ffffffff0100f2052a01000000434104678afdb0fe5548271967"
        "f1a67130b7105cd6a828e03909a67962e0ea1f61deb649f6bc3f4cef38c4f35504e51ec1"
        "12de5c384df7ba0b8d578a4c702b6bf11d5fac00000000"))
    assert merkle_root([coinbase_txid_internal]) == coinbase_txid_internal
    assert coinbase_subsidy(0) == 5_000_000_000
    assert coinbase_subsidy(210000) == 2_500_000_000
    assert coinbase_subsidy(840000) == 312_500_000
    print("ok: mining.pow primitives (target, merkle, subsidy)")


if __name__ == "__main__":
    test_genesis_hash()
    test_diff1_target()
    test_build_header_genesis_shape()
    test_pow_module()
    print("ALL TESTS PASSED")
