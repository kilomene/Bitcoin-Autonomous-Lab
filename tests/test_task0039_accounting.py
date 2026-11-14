#!/usr/bin/env python3
"""Task 003.9: final mining accounting correction and benchmark
accuracy.

What this suite proves, with the definitions of gpu/engine.py's
module docstring:

- The CUDA identity device_hashes == unique_coverage +
  researched_hashes holds on the CUDA candidate-recovery path
  (driver and CudaContext stats), and ONLY there: on CPU and C
  paths device_hashes is exactly 0 and the identity is not
  applied; work is backend_hashes plus verification_hashes.
- backend_hashes counts only the selected backend's own
  computations. Independent candidate verification (one hash per
  presented candidate) and trusted rescans are counted only in
  verification_hashes; nothing is counted in two categories.
- Early-exit accounting: a native C hit reports the counted
  attempts (far below the request), not the requested range.
- HEADLINE REGRESSION: ComputeEngine.benchmark counts ACTUAL
  backend computations, not the requested batch size. The old
  implementation accumulated `hashes += batch`; with a backend
  whose actual computations differ from the request (CUDA
  overflow recovery), the benchmark must report the actual
  total and base its rate on it.
- Zero-work and failed-batch benchmarks produce explicit
  failure or all-zero stats, never a clean-looking total.

GPU device execution stays UNVERIFIED on this VM (no NVIDIA
GPU); every CUDA case below runs against a stub implementing
the device primitive's bounded semantics over real digests,
exactly as in Tasks 003 and 003.8.

Run: python3 tests/test_task0039_accounting.py
"""

import ctypes
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import gpu.engine as ge
from gpu.engine import (ComputeEngine, CandidateOverflowError,
                        collect_candidates_complete, cpu_digest,
                        verify_candidate)

REGTEST_TARGET = 0x7FFFFF << 232
GENESIS = bytes.fromhex(
    "01000000" + "00" * 32
    + "3ba3edfd7a7b12b27ac72c3e67768f617fc81bc3888a51323a9fb8aa4b1e5e4a"
    + "29ab5f49" + "ffff001d" + "1dac2b7c")
GENESIS_NONCE = 2083236893
DIFF1 = 0xFFFF << 208


def recount(header, target, start, count):
    out = {}
    for i in range(count):
        d = cpu_digest(header, start + i)
        if int.from_bytes(d, "little") <= target:
            out[start + i] = d
    return out


class FakeCudaCtx:
    """CudaContext stand-in with device-identical bounded
    semantics over real digests. The driver sizes sub-batches
    from driver_capacity, while a single shot enforces
    effective_cap (the device buffer), raising
    CandidateOverflowError when a shot produces more candidates
    than fit: the same split personality the Task 003.8 forced
    overflow case uses. With flood_threshold set, a shot over
    that many nonces always reports overflow, simulating a
    candidate flood under the benchmark's hard target."""

    def __init__(self, driver_capacity=4096, effective_cap=None,
                 flood_threshold=None):
        self.CAND_CAP = driver_capacity
        self._effective = effective_cap
        self._flood = flood_threshold
        self.computed = 0

    def search(self, header, target, start, count, threads=256):
        self.computed += count
        cands = []
        for i in range(count):
            n = start + i
            d = cpu_digest(header, n)
            if int.from_bytes(d, "little") <= target:
                cands.append((n, d))
        cap = self._effective if self._effective is not None \
            else self.CAND_CAP
        if (self._flood is not None and count > self._flood) \
                or len(cands) > cap:
            raise CandidateOverflowError(
                "stub candidate overflow", total=len(cands),
                start=start, count=count)
        return cands, {"kernel_ms": 0.0,
                       "candidate_count": len(cands),
                       "requested_hashes": count,
                       "unique_coverage": count,
                       "device_hashes": count,
                       "backend_hashes": count,
                       "verification_hashes": 0,
                       "researched_hashes": 0,
                       "overflow_splits": 0}

    def search_complete(self, header, target, start, count,
                        threads=256):
        return collect_candidates_complete(
            lambda s, n: self.search(header, target, s, n,
                                     threads),
            target, start, count, self.CAND_CAP)


def cuda_engine(ctx):
    eng = ComputeEngine()
    eng.backend = "cuda"
    eng._cuda_ctx = ctx
    return eng


# ----------------------------------------------------------------
# 1. CUDA stub, no overflow: every field exact, identity holds
# ----------------------------------------------------------------

def test_cuda_no_overflow():
    target = 1 << 240
    start, count = 0, 2000
    want = recount(GENESIS, target, start, count)
    eng = cuda_engine(FakeCudaCtx())
    cands, st = eng.batch_search(GENESIS, target, start, count)
    got = {c["nonce"]: bytes.fromhex(c["hash"])[::-1]
           for c in cands}
    assert got == want
    assert st["requested_hashes"] == count
    assert st["unique_coverage"] == count
    assert st["device_hashes"] == count
    assert st["backend_hashes"] == count
    assert st["researched_hashes"] == 0
    assert st["overflow_splits"] == 0
    assert st["candidate_count"] == len(want)
    # One independent verification computation per candidate,
    # counted only as verification work.
    assert st["verification_hashes"] == len(want), st
    assert st["hashes"] == st["backend_hashes"] + \
        st["verification_hashes"]
    assert st["device_hashes"] == st["unique_coverage"] + \
        st["researched_hashes"]
    assert st["hashrate"] == st["device_hashes"] / st["seconds"]
    print("ok 003.9 cuda no-overflow: requested/unique/device/"
          "backend all exact, verification counted separately "
          f"({len(want)} candidates, {st['verification_hashes']} "
          "verification hashes)")


# ----------------------------------------------------------------
# 2. CUDA stub with overflow: device work exceeds coverage by
#    exactly the researched part; identity holds on this path
# ----------------------------------------------------------------

def test_cuda_overflow_accounting():
    target = 1 << 255
    start, count = 0, 1024
    want = recount(GENESIS, target, start, count)
    assert len(want) == 512
    eng = cuda_engine(FakeCudaCtx(effective_cap=3))
    cands, st = eng.batch_search(GENESIS, target, start, count)
    got = {c["nonce"]: bytes.fromhex(c["hash"])[::-1]
           for c in cands}
    assert got == want
    assert st["unique_coverage"] == count
    assert st["requested_hashes"] == count
    assert st["device_hashes"] == 8864, st
    assert st["researched_hashes"] == 7840, st
    assert st["overflow_splits"] == 220, st
    assert st["overflow_splits"] > 1  # multiple splits
    assert st["device_hashes"] > st["unique_coverage"]
    assert st["device_hashes"] == st["unique_coverage"] + \
        st["researched_hashes"]
    assert st["backend_hashes"] == st["device_hashes"]
    assert st["candidate_count"] == 512
    assert st["verification_hashes"] == 512, st
    assert st["hashrate"] == st["device_hashes"] / st["seconds"]
    print("ok 003.9 cuda overflow: device 8864 = unique 1024 + "
          "researched 7840 across 220 splits; backend == device; "
          "512 candidates cost exactly 512 verification hashes, "
          "counted nowhere else")


def test_multiple_splits_all_match():
    target = (1 << 256) - 1
    count = 64
    ctx = FakeCudaCtx(effective_cap=3)
    cands, st = ctx.search_complete(GENESIS, target, 0, count)
    assert [n for n, _d in cands] == list(range(count))
    assert st["unique_coverage"] == count
    assert st["overflow_splits"] >= 10, st
    assert st["device_hashes"] == st["unique_coverage"] + \
        st["researched_hashes"]
    assert st["backend_hashes"] == st["device_hashes"]
    assert st["requested_hashes"] == count
    print(f"ok 003.9 multiple splits: all-match range of {count} "
          f"resolved through {st['overflow_splits']} splits, "
          f"device {st['device_hashes']} = unique {count} + "
          f"researched {st['researched_hashes']}")


# ----------------------------------------------------------------
# 3. CPU and C paths: device_hashes is 0, the CUDA identity is
#    not applied, verification is separate
# ----------------------------------------------------------------

def test_cpu_fallback_accounting():
    target = 1 << 255
    start, count = 0, 2000
    want = recount(GENESIS, target, start, count)
    eng = ComputeEngine(requested="cpu")
    assert eng.backend == "cpu"
    cands, st = eng.batch_search(GENESIS, target, start, count)
    got = {c["nonce"]: bytes.fromhex(c["hash"])[::-1]
           for c in cands}
    assert got == want
    assert st["device_hashes"] == 0, st
    assert st["backend_hashes"] == count
    assert st["unique_coverage"] == count
    assert st["requested_hashes"] == count
    assert st["verification_hashes"] == len(want), st
    assert st["candidate_count"] == len(want)
    assert st["hashes"] == st["backend_hashes"] + \
        st["verification_hashes"]
    # The CUDA identity must NOT hold here: no device work
    # exists, so device (0) != unique + researched (count).
    assert st["device_hashes"] != st["unique_coverage"] + \
        st["researched_hashes"]
    assert st["hashrate"] == st["backend_hashes"] / st["seconds"]
    print("ok 003.9 cpu fallback: backend 2000, device 0 (no "
          "device work claimed), verification "
          f"{st['verification_hashes']} separate; CUDA identity "
          "correctly not applied")


def test_native_c_batch_accounting():
    target = 1 << 255
    start, count = 0, 2000
    want = recount(GENESIS, target, start, count)
    eng = ComputeEngine()
    assert eng.backend == "c", eng.describe()
    cands, st = eng.batch_search(GENESIS, target, start, count)
    got = {c["nonce"]: bytes.fromhex(c["hash"])[::-1]
           for c in cands}
    assert got == want
    assert st["device_hashes"] == 0
    assert st["backend_hashes"] == count
    assert st["unique_coverage"] == count
    assert st["requested_hashes"] == count
    assert st["candidate_count"] == len(want)
    assert st["verification_hashes"] == len(want), st
    print("ok 003.9 native C batch: backend 2000 counted "
          "exactly, device 0, one verification hash per "
          "presented candidate")


def test_full_range_coverage_odd_count():
    target = REGTEST_TARGET
    count = 4097
    want = recount(GENESIS, target, 0, count)
    eng = ComputeEngine(requested="cpu")
    cands, st = eng.batch_search(GENESIS, target, 0, count)
    assert len(cands) == len(want)
    assert st["unique_coverage"] == st["requested_hashes"] \
        == count
    print("ok 003.9 full-range coverage: unique_coverage == "
          f"requested == {count} on a completed enumeration")


# ----------------------------------------------------------------
# 4. Early-exit accounting through the counted C entry point
# ----------------------------------------------------------------

def test_early_exit_accounting():
    eng = ComputeEngine()
    assert eng.backend == "c"
    hit, attempted, _s = eng.search_first_counted(
        GENESIS, DIFF1, GENESIS_NONCE - 3, 100000)
    assert hit and hit[0] == GENESIS_NONCE
    st = eng.last_search_stats
    assert st["requested_hashes"] == 100000
    assert st["backend_hashes"] == attempted, st
    assert attempted < 100000 // 10, attempted
    assert st["unique_coverage"] == attempted
    assert st["device_hashes"] == 0
    assert st["verification_hashes"] == 1, st
    assert st["candidate_count"] == 1
    assert st["hashrate"] == st["backend_hashes"] / st["seconds"]
    # Miss: the whole range was examined, counted exactly.
    hit, attempted, _s = eng.search_first_counted(
        GENESIS, 1, 5000, 30000)
    assert hit is None and attempted == 30000
    st = eng.last_search_stats
    assert st["backend_hashes"] == 30000
    assert st["unique_coverage"] == 30000
    assert st["verification_hashes"] == 0
    assert st["candidate_count"] == 0
    assert st["device_hashes"] == 0
    print(f"ok 003.9 early-exit: genesis hit reports "
          f"backend_hashes == counted attempts (far below the "
          "100000 requested), unique_coverage == attempts, "
          "exactly 1 verification hash; miss counts exactly "
          "30000 with zero verification work")


class FakeSearch2Lib:
    """ctypes-shaped stub for bal_c_search2 (as in Task 003)."""

    def bal_c_search2(self, header, start, count, threads, tle,
                      out_nonce, out_digest, out_attempted):
        out_nonce._obj.value = start + 5
        ctypes.memmove(out_digest, b"\x00" * 32, 32)
        out_attempted._obj.value = 6
        return 1


def _first_hit_attempts(header, target, start, count):
    for i in range(count):
        d = cpu_digest(header, start + i)
        if int.from_bytes(d, "little") <= target:
            return i + 1
    return count


def test_early_exit_rescan_accounting():
    target = REGTEST_TARGET
    want_attempts = _first_hit_attempts(GENESIS, target, 0, 2000)
    eng = ComputeEngine()
    assert eng.backend == "c"
    eng._c_lib = FakeSearch2Lib()
    hit, attempted, _s = eng.search_first_counted(
        GENESIS, target, 0, 2000)
    assert hit is not None
    assert verify_candidate(GENESIS, target, hit[0], hit[1])
    st = eng.last_search_stats
    assert attempted == 6 + want_attempts, st
    # Backend work is the native 6 only; the failed candidate's
    # verification (1) and the whole rescan (want_attempts) are
    # verification-layer computations.
    assert st["backend_hashes"] == 6, st
    assert st["verification_hashes"] == 1 + want_attempts, st
    assert st["device_hashes"] == 0
    assert st["candidate_count"] == 1
    # The exact union of backend-examined and rescan-examined
    # nonces is not measurable; it must be reported as such,
    # never invented.
    assert st["unique_coverage"] is None, st
    assert st["unique_coverage_note"], st
    print("ok 003.9 early-exit rescan: backend 6, verification "
          f"1 + {want_attempts} rescan, device 0, coverage "
          "honestly marked unavailable after the rescan")


# ----------------------------------------------------------------
# 5. Fail-closed batch accounting under the new definitions
# ----------------------------------------------------------------

def test_batch_rescan_accounting_split():
    target = REGTEST_TARGET
    start, count = 0, 2000
    want = recount(GENESIS, target, start, count)
    first_nonce = min(want)
    eng = ComputeEngine()
    assert eng.backend == "c"
    eng._c_batch_flagged = lambda *a, **k: [
        (first_nonce, b"\x00" * 32)]
    cands, st = eng.batch_search(GENESIS, target, start, count)
    got = {c["nonce"]: bytes.fromhex(c["hash"])[::-1]
           for c in cands}
    assert got == want
    assert st["backend_hashes"] == count, st
    assert st["device_hashes"] == 0
    # 1 presented-candidate verification + count rescan
    # enumeration digests + 1 re-verification per rescan find.
    assert st["verification_hashes"] == 1 + count + len(want), st
    assert st["verification_rescan_hashes"] == count
    assert st["hashes"] == st["backend_hashes"] + \
        st["verification_hashes"]
    print("ok 003.9 fail-closed split: backend 2000, "
          f"verification {st['verification_hashes']} "
          "(1 presented + 2000 rescan + "
          f"{len(want)} re-verifications), no double counting")


# ----------------------------------------------------------------
# 6. HEADLINE: benchmark counts actual computations
# ----------------------------------------------------------------

FIXED_STATS = {"backend": "cuda", "seconds": 2.0,
               "requested_hashes": 1024, "unique_coverage": 1024,
               "backend_hashes": 5120, "device_hashes": 5120,
               "verification_hashes": 3, "researched_hashes": 4096,
               "overflow_splits": 15, "candidate_count": 3}


def test_benchmark_counts_actual_not_requested():
    """Requested batch 1024, actual backend computations 5120
    (overflow recovery repeated work). The pre-003.9 benchmark
    accumulated the request and would have reported
    1024 / 2.0 = 512.0 H/s; the corrected benchmark must
    report 5120 / 2.0 = 2560.0 H/s and expose the split."""
    eng = ComputeEngine(requested="cpu")
    eng.batch_search = lambda *a, **k: ([], dict(FIXED_STATS))
    rep = eng.benchmark_report(seconds_hint_batches=1,
                               batch=1024)
    assert rep["failed"] is False
    assert rep["requested_hashes"] == 1024
    assert rep["backend_hashes"] == 5120, rep
    assert rep["device_hashes"] == 5120
    assert rep["unique_coverage"] == 1024
    assert rep["hashrate"] == 2560.0, rep
    assert rep["coverage_per_second"] == 512.0
    assert rep["device_hashes_per_second"] == 2560.0
    assert rep["verification_hashes"] == 3
    assert rep["researched_share"] == 4096 / 5120
    assert rep["overflow_splits"] == 15
    assert eng.benchmark(1, 1024) == 2560.0
    print("ok 003.9 HEADLINE benchmark: requested 1024 but "
          "actual backend computations 5120; benchmark reports "
          "2560.0 H/s actual (old requested-count code would "
          "have reported 512.0), coverage 512.0/s separate, "
          "researched share 0.8 visible")


def test_benchmark_overflow_integration():
    """End-to-end through the real driver: a flooding stub
    forces overflow splits inside every benchmark batch, so
    actual device computations (5120 per batch) exceed the
    request (1024 per batch) deterministically."""
    ctx = FakeCudaCtx(flood_threshold=64)
    eng = cuda_engine(ctx)
    rep = eng.benchmark_report(seconds_hint_batches=2,
                               batch=1024)
    assert rep["failed"] is False, rep
    assert rep["batches_completed"] == 2
    assert rep["requested_hashes"] == 2048
    assert rep["unique_coverage"] == 2048
    assert rep["device_hashes"] == 10240, rep
    assert rep["backend_hashes"] == 10240
    assert rep["researched_hashes"] == 8192
    assert rep["overflow_splits"] == 30
    assert rep["device_hashes"] == rep["unique_coverage"] + \
        rep["researched_hashes"]
    assert rep["hashrate"] == rep["device_hashes"] / \
        rep["elapsed_seconds"]
    print("ok 003.9 benchmark integration: 2 batches requested "
          "2048, actual device computations 10240 after 30 "
          "overflow splits; rate is based on the actual total")


def test_benchmark_cpu_has_no_device_component():
    eng = ComputeEngine(requested="cpu")
    rep = eng.benchmark_report(seconds_hint_batches=1, batch=512)
    assert rep["failed"] is False
    assert rep["backend"] == "cpu"
    assert rep["device_hashes"] == 0
    assert rep["device_hashes_per_second"] == 0.0
    assert rep["device_hashes_note"]
    assert rep["backend_hashes"] == 512
    assert rep["unique_coverage"] == 512
    assert rep["hashrate"] == rep["backend_hashes"] / \
        rep["elapsed_seconds"] > 0
    print("ok 003.9 benchmark cpu: backend rate from actual "
          "CPU computations only; device totals exactly 0 "
          "with an explicit note")


def test_benchmark_zero_and_failed():
    eng = ComputeEngine(requested="cpu")
    rep = eng.benchmark_report(seconds_hint_batches=0,
                               batch=1024)
    assert rep["failed"] is False
    assert rep["batches_completed"] == 0
    assert rep["backend_hashes"] == 0
    assert rep["requested_hashes"] == 0
    assert rep["hashrate"] == 0.0
    # A zero-size batch is rejected by batch_search validation;
    # the report marks the failure and shows no phantom hashes.
    rep = eng.benchmark_report(seconds_hint_batches=1, batch=0)
    assert rep["failed"] is True and rep["error"], rep
    assert rep["backend_hashes"] == 0
    assert rep["batches_completed"] == 0
    try:
        eng.benchmark(1, 0)
        raise AssertionError("benchmark did not raise")
    except RuntimeError:
        pass
    # Failure mid-run: first batch counts, the run is marked
    # failed, and benchmark() raises rather than returning a
    # clean-looking partial rate.
    calls = {"n": 0}

    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            return [], dict(FIXED_STATS)
        raise RuntimeError("simulated backend failure")

    eng2 = ComputeEngine(requested="cpu")
    eng2.batch_search = flaky
    rep = eng2.benchmark_report(seconds_hint_batches=3,
                                batch=1024)
    assert rep["failed"] is True
    assert "simulated backend failure" in rep["error"]
    assert rep["batches_completed"] == 1
    assert rep["backend_hashes"] == 5120
    try:
        eng2.benchmark(3, 1024)
        raise AssertionError("benchmark did not raise")
    except RuntimeError:
        pass
    print("ok 003.9 benchmark zero/failed: zero batches give "
          "all-zero stats; an invalid batch and a mid-run "
          "failure are marked failed with partial totals kept "
          "separate, and benchmark() raises explicitly")


# ----------------------------------------------------------------
# 7. Regtest: fresh block through the native CPU backend
# ----------------------------------------------------------------

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
    assert compute.backend == "c", compute.describe()
    eng = MiningEngine(rpc, payout, compute=compute,
                       batch_size=100_000)
    tip0 = rpc.get_block_count()
    out = eng.mine_cycle(max_batches=1000, deadline_seconds=600)
    assert out["accepted"], out
    assert out["backend"] == "c"
    assert rpc.get_best_block_hash() == out["hash"]
    assert rpc.get_block_count() == tip0 + 1
    print(f"ok 003.9 regtest: fresh block accepted through the "
          f"native CPU backend: height {out['height']} hash "
          f"{out['hash']} submitblock null, best-block match")
    return out


def main():
    test_cuda_no_overflow()
    test_cuda_overflow_accounting()
    test_multiple_splits_all_match()
    test_cpu_fallback_accounting()
    test_native_c_batch_accounting()
    test_full_range_coverage_odd_count()
    test_early_exit_accounting()
    test_early_exit_rescan_accounting()
    test_batch_rescan_accounting_split()
    test_benchmark_counts_actual_not_requested()
    test_benchmark_overflow_integration()
    test_benchmark_cpu_has_no_device_component()
    test_benchmark_zero_and_failed()
    out = test_regtest_block()
    print("ALL TASK 003.9 TESTS PASSED "
          f"(regtest block {out['hash']} at height "
          f"{out['height']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
