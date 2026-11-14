#!/usr/bin/env python3
"""AVX-512 multi-buffer production integration gates.

The EXP-007 AVX-512 16-way multi-buffer kernel was integrated
as a production ComputeEngine backend ("v512") on 2026-11-14,
under the owner's adopted EXP-017 decision rule. This suite is
the standing gate for that integration. It proves, through the
PRODUCTION engine path (never the research harness):

- Runtime CPUID dispatch: the auto engine selects "v512" only
  when the flag-free probe in libbal_v512.so confirms AVX-512F
  and AVX-512BW (the exact feature set of the kernel's
  restricted-flag build); requesting "c" still selects the C
  backend alone; on a CPU without the features the engine
  falls back cleanly and records why.
- Digest exactness: well over 100,000 randomized differentials
  against hashlib through the production batch ABI, candidate
  sets equal to an independent hashlib recount, genesis exact,
  boundary nonces (including the final nonce 0xFFFFFFFF),
  target equality meets and target minus one misses.
- Accounting parity with the counted contract: wave-exact
  attempted on early exit, backend_hashes counting actual lane
  computations (dummy lanes included, never below attempted),
  unique_coverage exact on full enumeration, device_hashes
  exactly 0 (no device exists on this path).
- A fresh regtest block mined through the production engine
  with the MB backend selected and accepted by Core.

On a machine without AVX-512 the kernel-specific gates are
skipped with a printed reason and the fallback gates still
run: the suite must pass on every machine the lab supports.

Run: python3 tests/test_avx512_integration.py
"""

import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gpu.engine import ComputeEngine, cpu_digest, verify_candidate
from mining.cpu.build import build as build_c, build_v512

GENESIS = bytes.fromhex(
    "01000000" + "00" * 32
    + "3ba3edfd7a7b12b27ac72c3e67768f617fc81bc3888a51323a9fb8aa4b1e5e4a"
    + "29ab5f49" + "ffff001d" + "1dac2b7c")
GENESIS_NONCE = 2083236893
DIFF1 = 0xFFFF << 208
NONCE_SPACE = 1 << 32


def recount(header, target, start, count):
    out = {}
    for i in range(count):
        d = cpu_digest(header, start + i)
        if int.from_bytes(d, "little") <= target:
            out[start + i] = d
    return out


def test_dispatch(supported):
    eng_c = ComputeEngine(requested="c")
    assert eng_c.backend == "c", eng_c.describe()
    eng = ComputeEngine()
    if supported:
        assert eng.backend == "v512", eng.describe()
        assert eng.describe()["native_impl"] == "avx512-mb"
        assert eng.describe()["v512_backend"] is True
        print("ok dispatch: auto engine selects v512 via the "
              "CPUID probe; requested='c' still selects C alone")
    else:
        assert eng.backend in ("c", "cpu"), eng.describe()
        assert eng.v512_reason and "CPUID" in eng.v512_reason, \
            eng.v512_reason
        print("ok dispatch: CPU lacks AVX-512F/BW; engine fell "
              f"back cleanly to {eng.backend} with the reason "
              "recorded")
    return eng


def test_differentials(eng):
    """Randomized differentials through the production batch
    ABI: every digest of every batch compared to hashlib."""
    rng = random.Random(0xA512)
    total = 0
    for trial in range(24):
        header = bytes(rng.randrange(256) for _ in range(80))
        count = 8192
        start = rng.randrange(0, NONCE_SPACE - count)
        pairs = eng._v_batch_flagged(eng._v_lib, header,
                                     (1 << 256) - 1, start, count,
                                     want_all=True)
        assert pairs is not None and len(pairs) == count
        for nonce, digest in pairs:
            assert digest == cpu_digest(header, nonce), \
                (trial, nonce)
        total += count
        attempted, backend = eng._v_last_counts
        assert attempted == count and backend == count, \
            (attempted, backend, count)
    assert total >= 100_000, total
    print(f"ok differentials: {total:,} randomized digests "
          "through the production v512 batch ABI match hashlib "
          "exactly, counted actuals exact")


def test_candidate_sets(eng):
    rng = random.Random(0xB512)
    for trial in range(12):
        header = bytes(rng.randrange(256) for _ in range(80))
        target = 1 << rng.choice((232, 240, 248))
        start = rng.randrange(0, 1 << 24)
        count = 4096
        want = recount(header, target, start, count)
        cands, st = eng.batch_search(header, target, start, count)
        got = {c["nonce"]: bytes.fromhex(c["hash"])[::-1]
               for c in cands}
        assert got == want, trial
        assert st["backend"] == "v512", st
        assert st["unique_coverage"] == count, st
        assert st["device_hashes"] == 0, st
        assert st["candidate_count"] == len(want), st
        assert st["verification_hashes"] == len(want), st
        assert count <= st["backend_hashes"] <= count + 16 * 32, st
    print("ok candidate sets: batch_search candidate sets equal "
          "the independent hashlib recount on randomized "
          "headers and targets; accounting fields exact in kind")


def test_search_gates(eng):
    hit, attempted, _s = eng.search_first_counted(
        GENESIS, DIFF1, GENESIS_NONCE - 3, 100000)
    assert hit and hit[0] == GENESIS_NONCE
    st = eng.last_search_stats
    assert st["backend"] == "v512" and st["counted"], st
    assert st["candidate_count"] == 1, st
    assert st["verification_hashes"] == 1, st
    assert st["unique_coverage"] == attempted, st
    assert st["backend_hashes"] >= attempted, st
    assert st["backend_hashes"] % 16 == 0, st
    # Full miss: the whole range was examined, counted exactly.
    hit, attempted, _s = eng.search_first_counted(
        GENESIS, 1, 5000, 30000)
    assert hit is None and attempted == 30000, attempted
    # Independent verification of the found candidate.
    hit2, _a, _s = eng.search_first_counted(
        GENESIS, DIFF1, GENESIS_NONCE - 3, 100)
    assert hit2 and verify_candidate(GENESIS, DIFF1, hit2[0],
                                     hit2[1])
    # Boundary nonces, including the final nonce of the space.
    hit, attempted, _s = eng.search_first_counted(
        GENESIS, (1 << 256) - 1, NONCE_SPACE - 1, 1)
    assert hit and hit[0] == NONCE_SPACE - 1 and attempted == 1
    pairs = eng._v_batch_flagged(eng._v_lib, GENESIS,
                                 (1 << 256) - 1,
                                 NONCE_SPACE - 32, 32,
                                 want_all=True)
    assert pairs[-1][0] == NONCE_SPACE - 1
    assert pairs[-1][1] == cpu_digest(GENESIS, NONCE_SPACE - 1)
    # Target equality meets; target minus one misses.
    g = cpu_digest(GENESIS, GENESIS_NONCE)
    gv = int.from_bytes(g, "little")
    cands, _st = eng.batch_search(GENESIS, gv, GENESIS_NONCE, 1)
    assert len(cands) == 1 and cands[0]["nonce"] == GENESIS_NONCE
    cands, _st = eng.batch_search(GENESIS, gv - 1, GENESIS_NONCE, 1)
    assert cands == []
    print("ok search gates: genesis exact, early-exit wave "
          "accounting sound, candidate verified independently, "
          "final-nonce boundary exact, target equality meets "
          "and minus-one misses")


def test_regtest_block():
    from node import node_manager
    from node.rpc_client import BitcoinRPC
    from mining.engine import MiningEngine
    node_manager.start()
    rpc = BitcoinRPC()
    if "bal-regtest" not in rpc.call("listwallets"):
        try:
            rpc.call("loadwallet", "bal-regtest")
        except Exception:
            rpc.call("createwallet", "bal-regtest")
    wallet = BitcoinRPC(wallet="bal-regtest")
    payout = wallet.call("getnewaddress", "", "bech32")
    compute = ComputeEngine()
    assert compute.backend == "v512", compute.describe()
    eng = MiningEngine(rpc, payout, compute=compute,
                       batch_size=100_000)
    tip0 = rpc.get_block_count()
    out = eng.mine_cycle(max_batches=1000, deadline_seconds=600)
    assert out["accepted"], out
    assert out["backend"] == "v512", out
    assert rpc.get_best_block_hash() == out["hash"]
    assert rpc.get_block_count() == tip0 + 1
    print(f"ok regtest: fresh block accepted through the "
          f"production AVX-512 MB backend: height {out['height']} "
          f"hash {out['hash']} submitblock null, best-block match")
    return out


def main():
    built = build_c(log=lambda *a: None)
    assert built["lib"], built
    v = build_v512(log=lambda *a: None)
    assert v["ok"], v
    supported = bool(v["supported"])
    eng = test_dispatch(supported)
    if supported:
        test_differentials(eng)
        test_candidate_sets(eng)
        test_search_gates(eng)
        test_regtest_block()
    else:
        print("kernel gates skipped: this CPU cannot execute "
              "the AVX-512 multi-buffer kernel")
    print("ALL AVX512 INTEGRATION TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
