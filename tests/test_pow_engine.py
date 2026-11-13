#!/usr/bin/env python3
"""Task 003 tests: the independent PoW engine.

Pure Python SHA-256 against hashlib on randomized and edge inputs,
consensus target rules, the six real mainnet header fixtures, and a
full cross-verification of every header on the live regtest chain.
"""

import hashlib
import json
import os
import random
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mining.pow_engine import (POW_LIMIT_MAINNET, POW_LIMIT_REGTEST,
                               PureSHA256, check_pow, compact_decode,
                               compact_encode, difficulty,
                               double_sha256_pure, sha256_pure)

FIXTURES = os.path.join(os.path.dirname(__file__),
                        "fixtures_mainnet_headers.json")


def test_pure_sha256():
    rng = random.Random(42)
    for length in (0, 1, 3, 55, 56, 57, 63, 64, 65, 119, 120, 128, 1000):
        data = bytes(rng.randrange(256) for _ in range(length))
        assert sha256_pure(data) == hashlib.sha256(data).digest(), length
        s = PureSHA256()
        for i in range(0, len(data), 7):
            s.update(data[i:i + 7])
        assert s.digest() == hashlib.sha256(data).digest(), ("stream", length)
    assert sha256_pure(b"abc").hex() == \
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    big = b"a" * 1_000_000
    assert sha256_pure(big).hex() == \
        "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0"
    print("ok: pure SHA-256 matches hashlib incl. padding edges and "
          "the FIPS million-byte vector")


def test_targets():
    for bits in (0x1d00ffff, 0x207fffff, 0x1b0404cb, 0x1705ae3a):
        value, neg, over = compact_decode(bits)
        assert not neg and not over
        assert compact_encode(value) == bits, hex(bits)
    # negative: sign bit set with nonzero mantissa
    _, neg, _ = compact_decode(0x01800001)
    assert neg
    # overflow: size 35 with wide mantissa
    _, _, over = compact_decode(0x2300ffff)
    assert over
    assert difficulty(0x1d00ffff) == 1.0
    assert difficulty(0x207fffff) < 1.0
    print("ok: compact target decode, encode round trip, negative and "
          "overflow detection, difficulty")


def test_mainnet_fixtures():
    fixtures = json.load(open(FIXTURES))
    assert len(fixtures) == 6
    for f in fixtures:
        header = bytes.fromhex(f["header_hex"])
        ok, reason = check_pow(header, POW_LIMIT_MAINNET)
        assert ok, (f["height"], reason)
        digest = double_sha256_pure(header)
        assert digest[::-1].hex() == f["hash"], f["height"]
    # tamper: flip the nonce of block 100000, PoW must fail high-hash
    bad = bytearray(bytes.fromhex(fixtures[1]["header_hex"]))
    bad[79] ^= 0xFF
    ok, reason = check_pow(bytes(bad), POW_LIMIT_MAINNET)
    assert not ok and reason == "high-hash", reason
    print("ok: 6 real mainnet headers verified by the pure engine; "
          "tampered header rejected as high-hash")


def test_regtest_chain_cross_verify():
    from node import node_manager
    from node.rpc_client import BitcoinRPC
    node_manager.start()
    rpc = BitcoinRPC()
    tip = rpc.get_block_count()
    checked = 0
    for height in range(tip + 1):
        bhash = rpc.get_block_hash(height)
        raw = rpc.call("getblockheader", bhash, False)
        header = bytes.fromhex(raw)
        ok, reason = check_pow(header, POW_LIMIT_REGTEST)
        assert ok, (height, reason)
        assert double_sha256_pure(header)[::-1].hex() == bhash, height
        checked += 1
    print(f"ok: all {checked} live regtest headers cross-verified "
          f"against Core (pure engine hash and PoW agree)")


def main():
    test_pure_sha256()
    test_targets()
    test_mainnet_fixtures()
    test_regtest_chain_cross_verify()
    print("ALL POW ENGINE TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
