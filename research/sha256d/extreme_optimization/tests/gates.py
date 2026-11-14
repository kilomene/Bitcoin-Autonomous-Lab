#!/usr/bin/env python3
"""Shared correctness gate set for the extreme_optimization
experiment batch (EXP-004 to EXP-009). Every kernel variant
must pass all gates before any benchmark number is reported:

  1. >= 100,000 randomized SHA-256d differentials vs hashlib.
  2. Genesis digest and genesis search.
  3. Boundary nonces and ranges (max-only, range ending
     exactly at 2^32, crossing rejected, empty rejected).
  4. Template variations: version, prevhash, merkle root,
     timestamp, nBits varied one at a time from genesis.
  5. Target comparison: exact equality accepted, target
     minus one rejected, regtest-easy candidate set equal
     to a Python recount through the flags path.
  6. Accounting: batch attempted == count; search miss
     attempted == range; early exit attempted consistent
     with the variant's declared wave semantics.

Target convention (identical to the trusted implementation
and to test_h02.py): a digest's value is
int.from_bytes(digest, "little"); the target argument is
that integer in 32-byte little-endian form.
"""
import hashlib

GENESIS = bytes.fromhex(
    "01000000" + "00" * 32
    + "3ba3edfd7a7b12b27ac72c3e67768f617fc81bc3888a51323a9fb8aa4b1e5e4a"
    + "29ab5f49" + "ffff001d" + "1dac2b7c")
GN = 2083236893
MAX_LE = ((1 << 256) - 1).to_bytes(32, "little")
DIFF1_LE = (0xFFFF << 208).to_bytes(32, "little")
FAILS = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}  {detail}")
    if not cond:
        FAILS.append(name)


def ref(hdr, n):
    return hashlib.sha256(hashlib.sha256(
        hdr[:76] + n.to_bytes(4, "little")).digest()).digest()


def run_gates(label, batch, search, rng, diff_trials=9,
              diff_count=12000, wave_exact=None):
    """batch(hdr, start, count, threads, target) ->
    (rc, attempted, raw_hashes, raw_flags);
    search(hdr, start, count, threads, target) ->
    (rc, nonce, digest, attempted). wave_exact: optional
    expected attempted for the genesis early-exit probe
    (threads=1, start=GN-50000, count=100000)."""
    total = 0
    bad = 0
    for _trial in range(diff_trials):
        hdr = bytes(rng.randbytes(80))
        start = rng.randrange(0, 2**31)
        rc, att, raw, _f = batch(hdr, start, diff_count, 2, MAX_LE)
        if rc != 0 or att != diff_count:
            bad += 1
            continue
        for i in range(diff_count):
            if raw[32 * i:32 * i + 32] != ref(hdr, start + i):
                bad += 1
                break
        total += diff_count
    check(f"{label} randomized >=100k differentials",
          bad == 0 and total >= 100_000,
          f"checked={total} bad={bad}")

    rc, att, raw, _f = batch(GENESIS, GN, 1, 1, MAX_LE)
    check(f"{label} genesis digest",
          rc == 0 and att == 1 and raw[:32] == ref(GENESIS, GN))
    rc, n, _d, _a = search(GENESIS, GN - 3, 10, 1, DIFF1_LE)
    check(f"{label} genesis search", rc == 1 and n == GN,
          f"rc={rc} nonce={n}")

    ok = True
    for start, count in ((0xFFFFFFFE, 2), (0xFFFFFFFF, 1),
                         (0xFFFFF000, 0x1000), (0, 999), (5, 1)):
        rc, att, raw, _f = batch(GENESIS, start, count, 1, MAX_LE)
        if rc != 0 or att != count:
            ok = False
            break
        for i in range(count):
            if raw[32 * i:32 * i + 32] != ref(GENESIS, start + i):
                ok = False
                break
    check(f"{label} boundaries and odd counts", ok)
    rc, _a, _r, _f = batch(GENESIS, 0xFFFFFFFF, 2, 1, MAX_LE)
    check(f"{label} crossing range rejected", rc == -2)
    rc, _a, _r, _f = batch(GENESIS, 0, 0, 1, MAX_LE)
    check(f"{label} empty range rejected", rc == -1)

    ok = True
    variants = {}
    v = bytearray(GENESIS); v[0:4] = (2).to_bytes(4, "little")
    variants["version"] = bytes(v)
    v = bytearray(GENESIS); v[4:36] = bytes(range(32))
    variants["prevhash"] = bytes(v)
    v = bytearray(GENESIS); v[36:68] = bytes(range(32, 64))
    variants["merkle"] = bytes(v)
    v = bytearray(GENESIS); v[68:72] = (1700000000).to_bytes(4, "little")
    variants["timestamp"] = bytes(v)
    v = bytearray(GENESIS); v[72:76] = bytes.fromhex("ffff001e")
    variants["nbits"] = bytes(v)
    for name, hdr in variants.items():
        rc, att, raw, _f = batch(hdr, 777, 2000, 2, MAX_LE)
        if rc != 0 or att != 2000:
            ok = False
            print("  variant rc/att fail:", name, rc, att)
            continue
        for i in range(2000):
            if raw[32 * i:32 * i + 32] != ref(hdr, 777 + i):
                ok = False
                print("  variant mismatch:", name, i)
                break
    check(f"{label} template variations", ok,
          ",".join(variants.keys()))

    d = ref(GENESIS, GN)
    rc, nonce, dig, _a = search(GENESIS, GN, 1, 1, d[::-1])
    check(f"{label} target exact equality meets",
          rc == 1 and nonce == GN and dig == d)
    val = int.from_bytes(d, "little") - 1
    rc, _n, _d2, _a = search(GENESIS, GN, 1, 1,
                             val.to_bytes(32, "little"))
    check(f"{label} target minus one rejects", rc == 0, f"rc={rc}")
    easy = (1 << 248).to_bytes(32, "little")
    rc, att, raw, fl = batch(GENESIS, 0, 20000, 2, easy)
    want_flags = bytes(
        1 if int.from_bytes(ref(GENESIS, i), "little") <= (1 << 248)
        else 0 for i in range(20000))
    check(f"{label} regtest-easy candidate set",
          rc == 0 and att == 20000 and fl == want_flags,
          f"candidates={sum(want_flags)}")

    rc, _n, _d, att = search(GENESIS, 0, 5000, 1, DIFF1_LE)
    check(f"{label} miss accounting == range",
          rc == 0 and att == 5000, f"att={att}")
    rc, n, dig, att = search(GENESIS, GN - 50000, 100000, 1, DIFF1_LE)
    ok = rc == 1 and n == GN and dig == ref(GENESIS, GN) \
        and 1 <= att <= 100000
    if wave_exact is not None:
        ok = ok and att == wave_exact
    check(f"{label} early-exit accounting", ok,
          f"att={att} expected={wave_exact}")
    return not FAILS
