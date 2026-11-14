#!/usr/bin/env python3
"""EXP-002 (H-02) correctness gates for the direct SHA-NI kernel.

Every gate from the Stage 5 authorization, run against the
research library (and its scalar-schedule twin). Any failure
raises and the run is void: benchmarks are meaningless until
this file passes end to end.

Gates:
  1. FIPS SHA-256 vectors through bal_h_compress (abc, empty,
     million-byte 'a').
  2. Genesis header exact hash + nonce search.
  3. >= 100,000 randomized SHA-256d differentials vs hashlib
     (p1, full, p2 variants), zero mismatches.
  4. Cross-check vs the production C backend on identical work.
  5. Boundary nonces (0, 1, 0xFFFFFFFE, 0xFFFFFFFF, max-only
     range, range ending exactly at 2^32, invalid range codes).
  6. Template variations: merkle root, prevhash, version,
     timestamp, nBits varied independently; stale-prefix bugs
     would show up here.
  7. Target comparison: exact-equality accepted, target minus
     one rejected, regtest-easy candidate set equals a Python
     recount.
  8. Accounting: miss returns exactly the range size; an
     early-exit hit returns the true examined count.
  9. Scalar-schedule twin library: identical outputs to the
     MSG library on the same randomized work (the schedule
     equivalence check), plus its own hashlib differential.
"""
import ctypes
import hashlib
import os
import random
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from bench_harness import load_lib, verify_batch, verify_genesis_search  # noqa: E402

GENESIS = bytes.fromhex(
    "01000000" + "00" * 32
    + "3ba3edfd7a7b12b27ac72c3e67768f617fc81bc3888a51323a9fb8aa4b1e5e4a"
    + "29ab5f49" + "ffff001d" + "1dac2b7c")
GENESIS_NONCE = 2083236893
GENESIS_HASH = bytes.fromhex(
    "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f")
MAX_LE = ((1 << 256) - 1).to_bytes(32, "little")
DIFF1_LE = (0xFFFF << 208).to_bytes(32, "little")
H0 = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
      0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19]

FAILS = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}  {detail}")
    if not cond:
        FAILS.append(name)


def ref_dsha(header80):
    return hashlib.sha256(hashlib.sha256(header80).digest()).digest()


def batch(lib, fn_name, header, start, count, threads, target):
    fn = getattr(lib, fn_name)
    fn.restype = ctypes.c_int
    fn.argtypes = [ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
                   ctypes.c_uint, ctypes.c_char_p, ctypes.c_char_p,
                   ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint64)]
    hashes = ctypes.create_string_buffer(32 * count)
    flags = ctypes.create_string_buffer(count)
    att = ctypes.c_uint64(0)
    rc = fn(header, start, count, threads, target, hashes, flags,
            ctypes.byref(att))
    return rc, att.value, hashes.raw, flags.raw


def search(lib, header, start, count, threads, target):
    fn = lib.bal_h_search2
    fn.restype = ctypes.c_int
    fn.argtypes = [ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
                   ctypes.c_uint, ctypes.c_char_p,
                   ctypes.POINTER(ctypes.c_uint32), ctypes.c_char_p,
                   ctypes.POINTER(ctypes.c_uint64)]
    nonce = ctypes.c_uint32(0)
    dig = ctypes.create_string_buffer(32)
    att = ctypes.c_uint64(0)
    rc = fn(header, start, count, threads, target, ctypes.byref(nonce),
            dig, ctypes.byref(att))
    return rc, nonce.value, dig.raw, att.value


def sha256_via_compress(lib, data):
    """Full SHA-256 built on the exported one-block compression."""
    comp = lib.bal_h_compress
    comp.restype = None
    comp.argtypes = [ctypes.POINTER(ctypes.c_uint32), ctypes.c_char_p,
                     ctypes.POINTER(ctypes.c_uint32)]
    msg = bytearray(data)
    bitlen = len(msg) * 8
    msg.append(0x80)
    while len(msg) % 64 != 56:
        msg.append(0)
    msg += struct.pack(">Q", bitlen)
    state = (ctypes.c_uint32 * 8)(*H0)
    out = (ctypes.c_uint32 * 8)()
    for off in range(0, len(msg), 64):
        comp(state, bytes(msg[off:off + 64]), out)
        state = (ctypes.c_uint32 * 8)(*list(out))
    return b"".join(struct.pack(">I", w) for w in state)


def rand_header(rng):
    h = bytearray(rng.randbytes(80))
    return bytes(h)


def main():
    lib = ctypes.CDLL(os.path.join(HERE, "libbal_h02.so"))
    _l, b2, s2 = load_lib(os.path.join(HERE, "libbal_h02.so"), "bal_h")
    rng = random.Random(20261114)

    # Gate 1: FIPS vectors through the compression core.
    ok = sha256_via_compress(lib, b"abc") == bytes.fromhex(
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
    check("gate1 FIPS abc", ok)
    ok = sha256_via_compress(lib, b"") == bytes.fromhex(
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")
    check("gate1 FIPS empty", ok)
    ok = sha256_via_compress(lib, b"a" * 1_000_000) == bytes.fromhex(
        "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0")
    check("gate1 FIPS million-a", ok)

    # Gate 2: genesis.
    rc, att, raw, _f = batch(lib, "bal_h_batch2", GENESIS,
                             GENESIS_NONCE, 1, 1, MAX_LE)
    check("gate2 genesis digest",
          rc == 0 and raw[::-1] == GENESIS_HASH,
          f"rc={rc}")
    ok, msg = verify_genesis_search(s2, 2)
    check("gate2 genesis search", ok, msg)

    # Gate 3: randomized differentials, all three variants.
    total = 0
    bad = 0
    for fn_name in ("bal_h_batch2", "bal_h_batch2_full", "bal_h_batch2_p2"):
        for _trial in range(10):
            hdr = rand_header(rng)
            start = rng.randrange(0, 2**31)
            count = 4000
            rc, att, raw, _f = batch(lib, fn_name, hdr, start, count,
                                     2, MAX_LE)
            if rc != 0 or att != count:
                bad += 1
                continue
            for i in range(count):
                want = ref_dsha(hdr[:76]
                                + (start + i).to_bytes(4, "little"))
                if raw[32 * i:32 * i + 32] != want:
                    bad += 1
                    break
            total += count
    check("gate3 randomized differential >=100k",
          bad == 0 and total >= 100_000, f"checked={total} bad={bad}")

    # Gate 4: cross-check vs production C backend.
    plib, pb2, _ps = load_lib(
        "/home/hatch/workspace/bitcoin-autonomous-lab"
        "/.local/cpu/libbal_batch.so", "bal_c")
    hdr = rand_header(rng)
    rc1, _a1, raw1, _f1 = batch(lib, "bal_h_batch2", hdr, 12345, 5000,
                                2, MAX_LE)
    hashes = ctypes.create_string_buffer(32 * 5000)
    flags = ctypes.create_string_buffer(5000)
    att = ctypes.c_uint64(0)
    rc2 = pb2(hdr, 12345, 5000, 2, MAX_LE, hashes, flags,
              ctypes.byref(att))
    check("gate4 production cross-check",
          rc1 == 0 and rc2 == 0 and raw1 == hashes.raw)

    # Gate 5: boundaries.
    cases = [
        ("nonce 0", 0, 1), ("nonce 1", 1, 1),
        ("0xFFFFFFFE count 2", 0xFFFFFFFE, 2),
        ("max only", 0xFFFFFFFF, 1),
        ("ends at 2^32", 0xFFFFF000, 0x1000),
    ]
    ok_all = True
    for name, start, count in cases:
        rc, att, raw, _f = batch(lib, "bal_h_batch2", GENESIS, start,
                                 count, 2, MAX_LE)
        if rc != 0 or att != count:
            ok_all = False
            print("  boundary rc/att fail:", name, rc, att)
            continue
        for i in range(count):
            want = ref_dsha(GENESIS[:76]
                            + (start + i).to_bytes(4, "little"))
            if raw[32 * i:32 * i + 32] != want:
                ok_all = False
                print("  boundary digest fail:", name, i)
                break
    check("gate5 boundary nonces", ok_all)
    rc, _a, _r, _f = batch(lib, "bal_h_batch2", GENESIS, 0xFFFFFFFF,
                           2, 1, MAX_LE)
    check("gate5 crossing range rejected", rc == -2, f"rc={rc}")
    rc, _a, _r, _f = batch(lib, "bal_h_batch2", GENESIS, 0, 0, 1, MAX_LE)
    check("gate5 empty range rejected", rc == -1, f"rc={rc}")

    # Gate 6: template variations (each field independently).
    base = bytearray(GENESIS)
    variants = {}
    v = bytearray(base); v[36:68] = rng.randbytes(32); variants["merkle"] = bytes(v)
    v = bytearray(base); v[4:36] = rng.randbytes(32); variants["prevhash"] = bytes(v)
    v = bytearray(base); v[0:4] = rng.randbytes(4); variants["version"] = bytes(v)
    v = bytearray(base); v[68:72] = rng.randbytes(4); variants["timestamp"] = bytes(v)
    v = bytearray(base); v[72:76] = rng.randbytes(4); variants["nbits"] = bytes(v)
    ok_all = True
    for name, hdr in variants.items():
        rc, att, raw, _f = batch(lib, "bal_h_batch2", hdr, 777, 2000,
                                 2, MAX_LE)
        if rc != 0:
            ok_all = False
            continue
        for i in range(2000):
            want = ref_dsha(hdr[:76] + (777 + i).to_bytes(4, "little"))
            if raw[32 * i:32 * i + 32] != want:
                ok_all = False
                print("  variant mismatch:", name, i)
                break
    check("gate6 template variations", ok_all,
          ",".join(variants.keys()))

    # Gate 7: target comparison.
    d = ref_dsha(GENESIS[:76] + GENESIS_NONCE.to_bytes(4, "little"))
    tgt = d[::-1]  # little-endian form of the exact digest value
    rc, nonce, dig, _a = search(lib, GENESIS, GENESIS_NONCE, 1, 1, tgt)
    check("gate7 exact equality meets", rc == 1 and nonce == GENESIS_NONCE)
    val = int.from_bytes(d, "little") - 1
    tgt_low = val.to_bytes(32, "little")
    rc, _n, _d2, _a = search(lib, GENESIS, GENESIS_NONCE, 1, 1, tgt_low)
    check("gate7 target minus one rejects", rc == 0, f"rc={rc}")
    # regtest-easy candidate set equals Python recount (flags path)
    easy = (1 << 248).to_bytes(32, "little")
    rc, att, raw, fl = batch(lib, "bal_h_batch2", GENESIS, 0, 20000,
                             2, easy)
    want_flags = bytes(
        1 if int.from_bytes(
            ref_dsha(GENESIS[:76] + i.to_bytes(4, "little")), "little")
        <= (1 << 248) else 0 for i in range(20000))
    check("gate7 regtest-easy candidate set",
          rc == 0 and fl == want_flags,
          f"candidates={sum(want_flags)}")

    # Gate 8: accounting.
    rc, _n, _d, att = search(lib, GENESIS, 0, 5000, 1, DIFF1_LE)
    check("gate8 miss attempted == range",
          rc == 0 and att == 5000, f"rc={rc} att={att}")
    rc, nonce, _d, att = search(lib, GENESIS, GENESIS_NONCE - 50000,
                                100000, 1, DIFF1_LE)
    check("gate8 early-exit examined count",
          rc == 1 and nonce == GENESIS_NONCE and att == 50001,
          f"rc={rc} att={att}")

    # Gate 9: scalar-schedule twin equivalence.
    slib = ctypes.CDLL(os.path.join(HERE, "libbal_h02_scalar.so"))
    ok_all = True
    for _trial in range(5):
        hdr = rand_header(rng)
        start = rng.randrange(0, 2**31)
        _r1, _a1, raw_msg, _f = batch(lib, "bal_h_batch2", hdr, start,
                                      4000, 2, MAX_LE)
        _r2, _a2, raw_sc, _f2 = batch(slib, "bal_h_batch2", hdr, start,
                                      4000, 2, MAX_LE)
        if raw_msg != raw_sc:
            ok_all = False
            break
    check("gate9 MSG vs scalar schedule identical outputs", ok_all)
    ok_b, _m = verify_batch(slib and load_lib(
        os.path.join(HERE, "libbal_h02_scalar.so"), "bal_h")[1], 20000)
    check("gate9 scalar twin vs hashlib", ok_b)

    print()
    if FAILS:
        print("FAILED GATES:", FAILS)
        return 1
    print("ALL H-02 CORRECTNESS GATES PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
