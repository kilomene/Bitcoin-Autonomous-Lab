#!/usr/bin/env python3
"""Differential verification for the Stage 1 reference
implementation (sha256d_reference.py).

Three-way comparison, correctness only (no timing):

  A. Reference SHA-256 / SHA-256d vs hashlib, over random
     messages at padding-boundary lengths and over headers.
  B. Reference SHA-256d vs the production ComputeEngine batch
     path (gpu/engine.py), over the genesis header, the Stage 1
     reconstructed headers, random headers, and nonce spans
     that include the boundary nonces 0, 1 and 2^32 - 1.
  C. Target decoding and the hash <= target verdict: the
     header tool's integer target_from_bits against the
     production mining.pow_engine compact_decode, check_pow
     and the EXP-036 verify_candidate, over the reconstructed
     headers, mutated-bits near-boundary cases, compact
     encodings with exponent <= 3, and the sign bit set. (The
     exact-equality point, hash == target, cannot be exercised
     with a crafted header without inverting SHA-256; it is
     covered by decode equality plus the fact that both
     verdicts use the same integer comparison, rejection iff
     value > target, so equality accepts in both.)
  D. Midstate split: reference midstate over header bytes 0 to
     63, finished with sha256_from_midstate, equals the full
     reference SHA-256, for every header used above.

Every comparison counts its cases; any mismatch prints the case
and exits non-zero. Run from the repository root:

  python3 research/EXTREME_RESEARCH/tools/differential_check.py
"""

import hashlib
import os
import random
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)

from sha256d_reference import sha256 as ref_sha256
from sha256d_reference import sha256d as ref_sha256d
from sha256d_reference import midstate, sha256_from_midstate
import header_reconstruction as hr

ALL = (1 << 256) - 1
NONCE_SPACE = 1 << 32

def _hdr(version_u32, prev_display, merkle_display, time_, bits,
         nonce):
    """Rebuild an 80-byte header from the decoded fields the
    reconstruction tool printed (display hashes are reversed to
    internal byte order). validate_fixtures() then pins each
    rebuilt header to the block hash Core reported, so a
    transcription error in any field fails loudly here rather
    than silently testing the wrong bytes."""
    return hr.serialize_header({
        "version_u32": version_u32,
        "prev_hash": bytes.fromhex(prev_display)[::-1],
        "merkle_root": bytes.fromhex(merkle_display)[::-1],
        "time": time_,
        "bits": bits,
        "nonce": nonce,
    })


HEADERS = {
    "genesis": hr.genesis_block_raw()[:80],
    "mainnet-450150": _hdr(
        0x20000000,
        "0000000000000000006548469e7f37f0f091c45b64c8c1b8461381"
        "997cef9296",
        "4a42eb87438d7e2760f6ee7cd78a65c958cc0a3177dca38c1c46f8"
        "6e0daf2305",
        1485467049, 0x1802CC47, 80691141),
    "mainnet-450160": _hdr(
        0x20000000,
        "000000000000000000cbc869a110f3f24d9d4bfd80c4319f640ceb"
        "1b6c25f5ff",
        "395dc468fcb6e04a0931674fb94ae74a800a119e69ad0298612c35"
        "adf3cc591f",
        1485473003, 0x1802CC47, 1582863893),
    "mainnet-450170": _hdr(
        0x20000002,
        "0000000000000000014ee19c7d6c65573a763555b2725a6963d4c6"
        "6ac15b510e",
        "08ec55c5117cce94c3e0470fee7443472a95db0544ac82e3284d65"
        "2d8e993d81",
        1485477599, 0x1802CC47, 2696763457),
    "regtest-1491": _hdr(
        0x20000000,
        "4675cf28bad4a3d8c6530f4f74ef2611be729f3efb3a5530a632e6"
        "00390d80fb",
        "ff52dba7035790155745e3ab430f6214b7dccbed7c91a885529cd4"
        "5526e0bf87",
        1794791052, 0x207FFFFF, 1),
}


FIXTURE_HASHES = {
    "genesis": "000000000019d6689c085ae165831e934ff763ae46a2a6c172b"
               "3f1b60a8ce26f",
    "mainnet-450150": "000000000000000002290daa601d1f212b899685db"
                      "16bd1f9e822221aa71b0ac",
    "mainnet-450160": "000000000000000001218f9e0b7f22f30c34aec051d"
                      "bb60b7f9d59ce6ab007c0",
    "mainnet-450170": "000000000000000000d4c7e6e38e3eefa52cea6e06"
                      "258a69994bf25c1b26affa",
    "regtest-1491": "21c78c0ba7626411f969ef3a9cf7dd437b49f7d872a13"
                    "ed969aa761daa18a875",
}


def validate_fixtures():
    for name, header in HEADERS.items():
        assert len(header) == 80, (name, len(header))
        got = hr.display_hash(hl_sha256d(header))
        assert got == FIXTURE_HASHES[name], (name, got)
    print("fixtures: %d headers pinned to Core block hashes"
          % len(HEADERS))


def with_nonce(header, nonce):
    return header[:76] + struct.pack("<I", nonce)


def hl_sha256d(data):
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def part_a(rng):
    n = 0
    lengths = [0, 1, 2, 3, 31, 32, 55, 56, 57, 63, 64, 65, 80,
               92, 119, 120, 127, 128, 129, 255, 256, 1000, 4097]
    for ln in lengths:
        for _ in range(4):
            msg = bytes(rng.randrange(256) for _ in range(ln))
            assert ref_sha256(msg) == hashlib.sha256(msg).digest(), ln
            assert ref_sha256d(msg) == hl_sha256d(msg), ln
            n += 2
    for name, header in HEADERS.items():
        for nonce in (0, 1, 2, 2083236893, NONCE_SPACE - 1):
            h = with_nonce(header, nonce)
            assert ref_sha256(h) == hashlib.sha256(h).digest(), name
            assert ref_sha256d(h) == hl_sha256d(h), name
            n += 2
    print("A reference vs hashlib: %d comparisons, 0 mismatches" % n)
    return n


def engine_batch(eng, header, start, count):
    tier = eng.backend
    table = {
        "v512dual": ("_vd_batch", "_vd_lib"),
        "v512": ("_v_batch", "_v_lib"),
        "shani": ("_m_batch", "_m_lib"),
        "avx2": ("_a_batch", "_a_lib"),
        "c": ("_c_batch", "_c_lib"),
    }
    if tier not in table:
        raise RuntimeError("unexpected backend " + tier)
    meth, libattr = table[tier]
    lib = getattr(eng, libattr)
    return getattr(eng, meth)(lib, header, ALL, start, count)


def part_b(rng):
    from gpu.engine import ComputeEngine
    eng = ComputeEngine()
    print("B production backend selected: %s" % eng.backend)
    total = 0

    def run(header, start, count, label):
        nonlocal total
        got = engine_batch(eng, header, start, count)
        assert got is not None, label
        assert len(got) == count, label
        for i in range(count):
            nonce = start + i
            h = with_nonce(header, nonce)
            want = hl_sha256d(h)
            assert got[i] == want, (label, nonce)
            # Reference agreement on a stride sample plus all
            # boundary nonces, to bound pure-Python cost.
            if i % 64 == 0 or nonce in (0, 1, NONCE_SPACE - 1):
                assert ref_sha256d(h) == want, (label, nonce)
            total += 1

    genesis = HEADERS["genesis"]
    run(genesis, 0, 8192, "genesis 0..8191")
    for start, count in [(0, 1), (1, 1), (0, 17), (7, 100),
                         (NONCE_SPACE - 16, 16),
                         (NONCE_SPACE - 1, 1)]:
        run(genesis, start, count, "genesis edge %d+%d" % (start, count))
    for name, header in HEADERS.items():
        if name == "genesis":
            continue
        run(header, 0, 2048, name + " 0..2047")
        run(header, NONCE_SPACE - 2048, 2048, name + " tail")
    for k in range(6):
        header = bytes(rng.randrange(256) for _ in range(80))
        start = rng.randrange(0, NONCE_SPACE - 4096)
        run(header, start, 4096, "random header %d" % k)
    print("B reference+hashlib vs ComputeEngine batch (%s): "
          "%d digests, 0 mismatches" % (eng.backend, total))
    return total


def part_c():
    from mining.pow_engine import (compact_decode, compact_encode,
                                   check_pow, POW_LIMIT_MAINNET,
                                   POW_LIMIT_REGTEST)
    from mining.candidate_verify import verify_candidate
    n = 0
    rng = random.Random(777)
    cases = [0x1D00FFFF, 0x1802CC47, 0x207FFFFF, 0x1B0404CB,
             0x01123456, 0x02123456, 0x03123456, 0x04123456,
             0x01003456, 0x1E0FFFF0, 0x01000000]
    for _ in range(200):
        cases.append(rng.randrange(0, 1 << 32) & 0xFF7FFFFF)
    for bits in cases:
        mine = hr.target_from_bits(bits)
        theirs, negative, _overflow = compact_decode(bits)
        assert not negative, hex(bits)
        assert mine == theirs, (hex(bits), mine, theirs)
        n += 1
    # Sign-bit encoding: production flags it negative; the tool
    # refuses it outright. Both reject.
    _v, negative, _o = compact_decode(0x1D80FFFF)
    assert negative
    try:
        hr.target_from_bits(0x1D80FFFF)
        raise AssertionError("sign-bit encoding not refused")
    except ValueError:
        n += 1
    # Verdict agreement on the reconstructed headers, through
    # both production verdict paths.
    limits = {"genesis": POW_LIMIT_MAINNET,
              "mainnet-450150": POW_LIMIT_MAINNET,
              "mainnet-450160": POW_LIMIT_MAINNET,
              "mainnet-450170": POW_LIMIT_MAINNET,
              "regtest-1491": POW_LIMIT_REGTEST}
    for name, header in HEADERS.items():
        bits = struct.unpack("<I", header[72:76])[0]
        digest = hl_sha256d(header)
        value = int.from_bytes(digest, "little")
        mine_ok = value <= hr.target_from_bits(bits)
        ok_exact, reason = check_pow(header, limits[name])
        verdict = verify_candidate(header, limits[name])
        assert mine_ok and ok_exact and reason == "ok", name
        assert verdict["meets_network_target"] is True, name
        assert verdict["digests_agree"] is True, name
        n += 3
        # Near-boundary reject: re-encode the digest itself as
        # the target. The compact form truncates, so the decoded
        # target is the largest representable value <= digest;
        # when it is strictly below the digest, both verdicts
        # must reject by that smallest representable margin.
        bits2 = compact_encode(value)
        t2, _neg, _ov = compact_decode(bits2)
        if t2 < value:
            mutated = header[:72] + struct.pack("<I", bits2) \
                + header[76:80]
            ok2, reason2 = check_pow(mutated, limits[name])
            assert not ok2 and reason2 == "high-hash", name
            assert not (value <= hr.target_from_bits(bits2)), name
            n += 2
    print("C target decoding and verdicts vs mining.pow_engine "
          "and candidate_verify: %d comparisons, 0 mismatches" % n)
    return n


def part_d(rng):
    n = 0
    subjects = list(HEADERS.values())
    for _ in range(10):
        subjects.append(bytes(rng.randrange(256) for _ in range(80)))
    for header in subjects:
        state = midstate(header[:64])
        got = sha256_from_midstate(state, header[64:])
        assert got == ref_sha256(header)
        n += 1
    print("D midstate split vs full reference SHA-256: "
          "%d comparisons, 0 mismatches" % n)
    return n


def main():
    validate_fixtures()
    rng = random.Random(20261115)
    total = 0
    total += part_a(rng)
    total += part_b(rng)
    total += part_c()
    total += part_d(rng)
    print("TOTAL: %d comparisons, 0 mismatches" % total)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
