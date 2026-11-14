#!/usr/bin/env python3
"""Task 003 corrections: CPU and GPU final hardening tests.

Covers, against the actual current source:
- 003.1 mutex init/lock failure handling in bal_search.h and both
  C libraries (harness + ctypes failure injection + sanitizers).
- 003.2 mining/engine.py final-batch clamping: batch_count unit
  checks and full nonce-space coverage walks with a recording
  stub backend for awkward batch sizes.
- 003.3 bal-miner bench slices are disjoint and complete (ranges
  mode), bench output states unique space and own-slice repeats,
  winner output states first-found semantics.
- 003.4 a native C candidate that fails CPU verification triggers
  a recorded trusted rescan of the affected range, never a silent
  ordinary miss; a native hard failure propagates.
- 003.5 CUDA candidate overflow recovery (collect_candidates_
  complete) exercised through a Python stub with the same bounded
  semantics as the device primitive: below, at, and above
  capacity, very easy targets, range boundaries, exact recount.
- 003.6 cuda_production_selftest gates CUDA selection: a good
  stub passes, a corrupt-candidate stub fails, a diagnostic-only
  stub fails; with no device the real engine does not select CUDA.
- 003.7 bal_nonce_range_valid host checks (12 of 12 in the shared
  header the CUDA ABI calls).
- Cross-implementation differential sampling and a fresh regtest
  block mined with the corrected native CPU backend.

GPU device execution stays UNVERIFIED on this VM (no NVIDIA GPU);
nothing here pretends otherwise.

Run: python3 tests/test_task003_corrections.py
"""

import ctypes
import glob
import hashlib
import os
import random
import struct
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gpu.engine import (ComputeEngine, CandidateOverflowError,
                        collect_candidates_complete, cpu_digest,
                        cuda_production_selftest, verify_candidate)
from mining.cpu.build import build as build_c, build_intrin
from mining.engine import MiningEngine

ROOT = os.path.join(os.path.dirname(__file__), "..")
C_LIB = os.path.join(ROOT, ".local", "cpu", "libbal_batch.so")
I_LIB = os.path.join(ROOT, ".local", "cpu", "libbal_intrin.so")
NONCE_SPACE = 1 << 32
REGTEST_TARGET = 0x7FFFFF << 232
GENESIS = bytes.fromhex(
    "01000000" + "00" * 32
    + "3ba3edfd7a7b12b27ac72c3e67768f617fc81bc3888a51323a9fb8aa4b1e5e4a"
    + "29ab5f49" + "ffff001d" + "1dac2b7c")
GENESIS_NONCE = 2083236893
DIFF1 = 0xFFFF << 208
TMP = os.path.join(ROOT, ".local", "task003-tests")
os.makedirs(TMP, exist_ok=True)


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


# ----------------------------------------------------------------
# 003.1 mutex failure handling
# ----------------------------------------------------------------

def test_mutex_harness():
    src = os.path.join(ROOT, "tests", "task003_mutex_harness.c")
    exe = os.path.join(TMP, "mutex_harness")
    p = run(["gcc", "-O1", "-Wall", "-pthread", src, "-o", exe])
    assert p.returncode == 0, p.stderr
    p = run([exe])
    assert p.returncode == 0 and "MUTEX HARNESS OK" in p.stdout, p.stdout
    print("ok 003.1: mutex harness: normal init/publish/destroy, "
          "init failure propagated and not marked initialized, "
          "destroy after failed init is a no-op, lock failure "
          "publishes nothing and records the error")


def _load_search_lib(path, prefix):
    lib = ctypes.CDLL(path)
    getattr(lib, f"bal_{prefix}_search2").restype = ctypes.c_int
    getattr(lib, f"bal_{prefix}_search2").argtypes = [
        ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_uint,
        ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint32),
        ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint64)]
    getattr(lib, f"bal_{prefix}_test_set_mutex_fail_mask").argtypes = [
        ctypes.c_int]
    return lib


def test_mutex_library_injection():
    build_c(log=lambda *a: None)
    build_intrin(log=lambda *a: None)
    for path, prefix in ((C_LIB, "c"), (I_LIB, "i")):
        lib = _load_search_lib(path, prefix)
        search2 = getattr(lib, f"bal_{prefix}_search2")
        set_mask = getattr(lib, f"bal_{prefix}_test_set_mutex_fail_mask")
        nonce = ctypes.c_uint32(0)
        att = ctypes.c_uint64(0)
        digest = ctypes.create_string_buffer(32)
        tle = DIFF1.to_bytes(32, "little")
        # init failure: explicit -4, and the library recovers.
        set_mask(1)
        rc = search2(GENESIS, GENESIS_NONCE, 10, 2, tle,
                     ctypes.byref(nonce), digest, ctypes.byref(att))
        assert rc == -4, (path, rc)
        set_mask(0)
        rc = search2(GENESIS, GENESIS_NONCE - 3, 10, 2, tle,
                     ctypes.byref(nonce), digest, ctypes.byref(att))
        assert rc == 1 and nonce.value == GENESIS_NONCE, (path, rc)
        # lock failure on publish: explicit -3, no winner returned.
        set_mask(2)
        rc = search2(GENESIS, GENESIS_NONCE, 1, 1, tle,
                     ctypes.byref(nonce), digest, ctypes.byref(att))
        assert rc == -3, (path, rc)
        set_mask(0)
        rc = search2(GENESIS, GENESIS_NONCE, 1, 1, tle,
                     ctypes.byref(nonce), digest, ctypes.byref(att))
        assert rc == 1 and nonce.value == GENESIS_NONCE, (path, rc)
    print("ok 003.1: both C libraries: mutex init failure returns "
          "-4 with no search started, lock failure returns -3 with "
          "no winner, and both recover when injection is removed")


def test_sanitizers():
    drv = os.path.join(ROOT, "tests", "task003_san_driver.c")
    batch = os.path.join(ROOT, "mining", "cpu", "bal_batch.c")
    intrin = os.path.join(ROOT, "mining", "cpu", "bal_sha_intrin.c")
    harness = os.path.join(ROOT, "tests", "task003_mutex_harness.c")
    jobs = []
    for name, srcs, extra in (
            ("asan_c", [drv, batch], ["-fsanitize=address,undefined"]),
            ("asan_i", [drv, intrin],
             ["-fsanitize=address,undefined", "-DINTRIN", "-msha"]),
            ("asan_miner", [os.path.join(ROOT, "mining", "cpu",
                                         "bal_miner.c")],
             ["-fsanitize=address,undefined"]),
            ("asan_mutex", [harness], ["-fsanitize=address,undefined"]),
            ("tsan_c", [drv, batch], ["-fsanitize=thread"]),
            ("tsan_i", [drv, intrin],
             ["-fsanitize=thread", "-DINTRIN", "-msha"]),
            ("tsan_miner", [os.path.join(ROOT, "mining", "cpu",
                                         "bal_miner.c")],
             ["-fsanitize=thread"]),
            ("tsan_mutex", [harness], ["-fsanitize=thread"])):
        exe = os.path.join(TMP, "san_" + name)
        cmd = ["gcc", "-O1", "-g", "-pthread", "-Wno-deprecated-declarations",
               "-I", os.path.join(ROOT, "mining", "cpu")] + srcs + \
              ["-o", exe] + extra
        if "miner" in name:
            cmd += ["-lcrypto"]
        elif "mutex" not in name:
            cmd += ["-lcrypto"]
        jobs.append((name, exe, cmd))
    for name, exe, cmd in jobs:
        p = run(cmd)
        assert p.returncode == 0, (name, p.stderr[-2000:])
        if name.startswith("tsan"):
            p = run(["setarch", "-R", exe] +
                    (["search",
                      GENESIS.hex(),
                      "00000000ffff0000000000000000000000000000000000000000000000000000",
                      "2083236000", "2000", "4"]
                     if "miner" in name else []))
        elif "miner" in name:
            p = run([exe, "search", GENESIS.hex(),
                     "00000000ffff0000000000000000000000000000000000000000000000000000",
                     "2083236000", "2000", "4"])
        else:
            p = run([exe])
        out = p.stdout + p.stderr
        assert p.returncode == 0, (name, out[-2000:])
        assert "Sanitizer" not in out and "runtime error" not in out, \
            (name, out[-2000:])
    print("ok 003.1/7: ASan+UBSan clean (batch, intrinsics, miner, "
          "mutex harness); TSan clean under setarch -R for the same "
          "four, including the new mutex failure paths")


# ----------------------------------------------------------------
# 003.2 final nonce batch
# ----------------------------------------------------------------

def test_batch_count():
    bc = MiningEngine.batch_count
    assert bc(1, 0) == 1
    assert bc(1, NONCE_SPACE - 1) == 1
    assert bc(65536, NONCE_SPACE - 65536) == 65536
    assert bc(1_000_000, 4_294_000_000) == 967_296
    assert bc(65_535, NONCE_SPACE - 10) == 10
    assert bc(3_000_000_000, 3_000_000_000) == 1_294_967_296
    assert bc(1 << 40, 0) == NONCE_SPACE
    for bad in ((0, 0), (10, NONCE_SPACE), (10, -1)):
        try:
            bc(*bad)
            raise AssertionError(f"batch_count{bad} not rejected")
        except ValueError:
            pass
    print("ok 003.2: batch_count clamps the final batch for sizes "
          "1, 65535, 1000000 and larger-than-remaining, ends exactly "
          "at 2^32, and rejects invalid starts and sizes")


class StopWalk(Exception):
    pass


class RecordingCompute:
    backend = "stub"

    def __init__(self):
        self.ranges = []

    def search_first_counted(self, header, target, start, count):
        if self.ranges and start == 0:
            raise StopWalk  # second extranonce round begins
        assert 0 <= start and 0 < count and start + count <= NONCE_SPACE, \
            (start, count)
        self.ranges.append((start, count))
        return None, count, 0.0


def _coverage_walk(batch_size):
    rec = RecordingCompute()
    eng = MiningEngine(object(), "stub-address", compute=rec,
                       batch_size=batch_size)
    eng.get_template = lambda: {}
    cand = {"header": bytes(80), "body": b"", "target": 1,
            "height": 1, "fees": 0, "tx_count": 1, "witness_count": 0}
    eng.build_candidate = lambda template, extranonce=0: cand
    try:
        eng.mine_cycle(max_batches=10_000_000, deadline_seconds=3600)
        raise AssertionError("walk never started a second round")
    except StopWalk:
        pass
    pos = 0
    for start, count in rec.ranges:
        assert start == pos, (start, pos)
        assert count == min(batch_size, NONCE_SPACE - start)
        pos += count
    assert pos == NONCE_SPACE, pos
    return len(rec.ranges)


def test_coverage_walks():
    for bs in (65_535, 1_000_000, 3_000_000_000):
        n = _coverage_walk(bs)
        print(f"ok 003.2: full nonce-space walk with batch_size "
              f"{bs}: {n} batches, every nonce covered exactly "
              f"once, no gap, no overlap, no out-of-range batch")


# ----------------------------------------------------------------
# 003.3 bench ranges and winner semantics
# ----------------------------------------------------------------

def test_bench_ranges():
    p = run(["make", "-C", ROOT, "bal-miner"])
    assert p.returncode == 0, p.stderr
    miner = os.path.join(ROOT, "bal-miner")
    for threads in (1, 2, 3, 4, 7, 64):
        p = run([miner, "ranges", str(threads)])
        assert p.returncode == 0, p.stdout
        lines = p.stdout.splitlines()
        assert lines[-1] == "RANGES disjoint=1 covers=4294967296", lines
        spans = []
        for ln in lines[:-1]:
            parts = dict(kv.split("=") for kv in ln.split()[1:])
            spans.append((int(parts["begin"]), int(parts["end"])))
        assert spans[0][0] == 0 and spans[-1][1] == NONCE_SPACE
        for (b0, e0), (b1, e1) in zip(spans, spans[1:]):
            assert e0 == b1 and b0 < e0
        if threads > 1:
            sizes = [e - b for b, e in spans]
            # All slices equal except the last, which absorbs the
            # remainder of 2^32 / threads (fewer than `threads`
            # extra nonces): disjoint and complete is the property
            # that matters, with a bounded, documented imbalance.
            assert len(set(sizes[:-1])) == 1, sizes
            assert 0 <= sizes[-1] - sizes[0] < threads, sizes
    p = run([miner, "bench", "2", "4"])
    assert p.returncode == 0, p.stdout
    assert "unique_nonce_space=4294967296" in p.stdout, p.stdout
    assert "repeated=own-slice-only" in p.stdout, p.stdout
    p = run([miner, "search", GENESIS.hex(),
             "00000000ffff0000000000000000000000000000000000000000000000000000",
             "2083236000", "2000", "4"])
    assert p.returncode == 0, p.stdout
    assert f"nonce={GENESIS_NONCE}" in p.stdout, p.stdout
    assert "winner_semantics=first-found" in p.stdout, p.stdout
    print("ok 003.3: bench slices disjoint and complete for 1, 2, "
          "3, 4, 7, 64 workers (equal slices, last absorbs the "
          "sub-thread-count remainder), bench output separates "
          "unique space from own-slice repeats, search output "
          "states winner_semantics=first-found")


# ----------------------------------------------------------------
# 003.4 invalid native candidate
# ----------------------------------------------------------------

class FakeSearch2Lib:
    """ctypes-shaped stub for bal_c_search2 with injectable lies."""

    def __init__(self, mode):
        self.mode = mode

    def bal_c_search2(self, header, start, count, threads, tle,
                      out_nonce, out_digest, out_attempted):
        if self.mode == "hard_failure":
            return -7
        if self.mode == "corrupt_digest":
            out_nonce._obj.value = start + 5
            ctypes.memmove(out_digest, b"\x00" * 32, 32)
            out_attempted._obj.value = 6
            return 1
        if self.mode == "wrong_nonce":
            out_nonce._obj.value = start + 5
            d = cpu_digest(header, start + 7)
            ctypes.memmove(out_digest, d, 32)
            out_attempted._obj.value = 8
            return 1
        raise AssertionError(self.mode)


def _first_hit(header, target, start, count):
    for i in range(count):
        d = cpu_digest(header, start + i)
        if int.from_bytes(d, "little") <= target:
            return start + i, d, i + 1
    return None, None, count


def test_invalid_native_candidate():
    header = GENESIS
    target = REGTEST_TARGET
    want_nonce, _d, want_attempts = _first_hit(header, target, 0, 2000)
    assert want_nonce is not None
    for mode, native_att in (("corrupt_digest", 6), ("wrong_nonce", 8)):
        eng = ComputeEngine()
        assert eng.backend == "c"
        eng._c_lib = FakeSearch2Lib(mode)
        before = len(eng.fallback_events)
        hit, attempted, _s = eng.search_first_counted(
            header, target, 0, 2000)
        assert hit is not None and hit[0] == want_nonce, (mode, hit)
        assert verify_candidate(header, target, hit[0], hit[1])
        assert attempted == native_att + want_attempts, \
            (mode, attempted, native_att, want_attempts)
        assert len(eng.fallback_events) == before + 1
        ev = eng.fallback_events[-1]
        assert ev["retried_on"] == "cpu-hashlib-rescan", ev
        assert ev["native_attempted"] == native_att
        assert ev["rescan_attempted"] == want_attempts
        st = eng.last_search_stats
        assert st["rescanned"] is True and st["backend"] == "cpu-rescan", st
    # A native hard failure propagates; it is not softened.
    eng = ComputeEngine()
    eng._c_lib = FakeSearch2Lib("hard_failure")
    try:
        eng.search_first_counted(header, target, 0, 100)
        raise AssertionError("hard failure did not propagate")
    except RuntimeError as exc:
        assert "-7" in str(exc) or "returned" in str(exc)
    # The real native candidate passes with no rescan.
    eng = ComputeEngine()
    hit, _att, _s = eng.search_first_counted(
        header, DIFF1, GENESIS_NONCE - 3, 10)
    assert hit is not None and hit[0] == GENESIS_NONCE
    assert eng.last_search_stats["rescanned"] is False
    assert not any(e.get("retried_on") == "cpu-hashlib-rescan"
                   for e in eng.fallback_events)
    print("ok 003.4: corrupt digest and wrong nonce from the native "
          "backend both trigger a recorded CPU rescan that finds "
          "the true first hit with exact attempt accounting; hard "
          "failure propagates; the genuine native candidate needs "
          "no rescan")


# ----------------------------------------------------------------
# 003.5 CUDA overflow recovery through the shared driver
# ----------------------------------------------------------------

def _stub_once(header, target, capacity):
    def once(s, n):
        stored = []
        total = 0
        for nonce in range(s, s + n):
            d = cpu_digest(header, nonce)
            if int.from_bytes(d, "little") <= target:
                total += 1
                if len(stored) < capacity:
                    stored.append((nonce, d))
        if total > capacity:
            raise CandidateOverflowError(
                "stub overflow", total=total, start=s, count=n)
        return stored, {"candidates_found": total}
    return once


def _recount(header, target, start, count):
    out = {}
    for nonce in range(start, start + count):
        d = cpu_digest(header, nonce)
        if int.from_bytes(d, "little") <= target:
            out[nonce] = d
    return out


def test_overflow_recovery():
    header = GENESIS
    easy = 1 << 255
    # Below capacity: exact set, single pass accounting.
    cands, st = collect_candidates_complete(
        _stub_once(header, easy, 4096), easy, 0, 256, 4096)
    assert dict(cands) == _recount(header, easy, 0, 256)
    assert st["unique_coverage"] == 256 and st["overflow_events"] == 0
    # Exactly at capacity: no overflow, all candidates returned.
    allmatch = (1 << 256) - 1
    cands, st = collect_candidates_complete(
        _stub_once(header, allmatch, 8), allmatch, 0, 8, 8)
    assert len(cands) == 8 and st["overflow_events"] == 0
    # Above capacity with an all-match target: driver sizing alone
    # resolves it, every candidate present, no duplicates.
    cands, st = collect_candidates_complete(
        _stub_once(header, allmatch, 8), allmatch, 0, 100, 8)
    assert len(cands) == 100
    assert [n for n, _ in cands] == list(range(100))
    assert st["unique_coverage"] == 100
    # Forced overflow: the single-shot stub has a far smaller
    # effective capacity (3) than the driver was sized for (4096),
    # so the driver's large sub-batches overflow and must be split;
    # only the split sub-ranges are re-searched, accounted as
    # researched_hashes, never as unique coverage.
    cands, st = collect_candidates_complete(
        _stub_once(header, easy, 3), easy, 0, 1024, 4096)
    want = _recount(header, easy, 0, 1024)
    assert dict(cands) == want, (len(cands), len(want))
    assert len({n for n, _ in cands}) == len(cands)
    assert st["unique_coverage"] == 1024
    assert st["overflow_events"] >= 1, st
    assert st["researched_hashes"] > 0, st
    assert st["device_hashes"] == 1024 + st["researched_hashes"], st
    # Boundary: the tail of the nonce space, final nonce included.
    start = NONCE_SPACE - 64
    cands, st = collect_candidates_complete(
        _stub_once(header, easy, 4096), easy, start, 64, 4096)
    assert dict(cands) == _recount(header, easy, start, 64)
    assert st["unique_coverage"] == 64
    print("ok 003.5: overflow recovery: below/at/above capacity and "
          "all-match targets return the exact CPU-recounted "
          "candidate set with no duplicates; forced overflows split "
          "only the overflowing sub-range (researched_hashes "
          "accounted separately); final-nonce boundary exact")


# ----------------------------------------------------------------
# 003.6 production-path self-test gating
# ----------------------------------------------------------------

class StubCtx:
    CAND_CAP = 8192

    def __init__(self, mode="good"):
        self.mode = mode

    def search(self, header, target, start, count, threads=256):
        if self.mode == "diag_only":
            raise RuntimeError("production path unavailable")
        cands = []
        for nonce in range(start, start + count):
            d = cpu_digest(header, nonce)
            if int.from_bytes(d, "little") <= target:
                cands.append((nonce, d))
        if self.mode == "corrupt":
            cands = [(n, b"\x00" * 32) for n, _d in cands[:4]]
        if len(cands) > self.CAND_CAP:
            raise CandidateOverflowError(
                "stub overflow", total=len(cands), start=start,
                count=count)
        return cands, {"candidates_found": len(cands)}

    def batch_diag(self, header, target, start, count, threads=128):
        # The diagnostic path works fine even in diag_only mode:
        # it must NOT be able to authorize CUDA selection.
        return [cpu_digest(header, start + i) for i in range(count)]

    def search_complete(self, header, target, start, count,
                        threads=256):
        return collect_candidates_complete(
            lambda s, n: self.search(header, target, s, n),
            target, start, count, self.CAND_CAP)


def test_production_selftest():
    ok, reason = cuda_production_selftest(StubCtx("good"))
    assert ok, reason
    ok, reason = cuda_production_selftest(StubCtx("corrupt"))
    assert not ok and "verification" in reason, reason
    ok, reason = cuda_production_selftest(StubCtx("diag_only"))
    assert not ok and "production candidate search failed" in reason, reason
    have_device = len(glob.glob("/dev/nvidia[0-9]*")) > 0
    if not have_device:
        eng = ComputeEngine()
        assert eng.backend != "cuda"
        assert eng.describe()["cuda_context"] is False
        assert eng.cuda_fallback_reason or eng.fallback_reason
        try:
            ComputeEngine(requested="cuda-only")
            raise AssertionError("cuda-only did not fail")
        except RuntimeError:
            pass
    print("ok 003.6: production self-test passes a correct stub, "
          "rejects a corrupt-candidate stub and a diagnostic-only "
          "stub; on this GPU-less VM the engine does not select "
          "CUDA and cuda-only fails clearly")


# ----------------------------------------------------------------
# 003.7 range validation host checks + differential sampling
# ----------------------------------------------------------------

def test_range_validation_and_differential():
    from gpu.cuda.build import build as build_gpu
    res = build_gpu(log=lambda *a: None, require_cuda=False)
    assert res["host_checks"], res
    p = run([res["host_checks"]])
    assert p.returncode == 0, p.stderr
    lines = p.stdout.splitlines()
    assert lines[6] == "range_valid 12 of 12", lines
    assert lines[3] == "random_mismatches 0", lines
    # Differential: C batch (via ComputeEngine) vs hashlib on
    # randomized headers, including the final nonce.
    eng = ComputeEngine()
    assert eng.backend == "c"
    rng = random.Random(3003)
    for _ in range(25):
        header = bytes(rng.randrange(256) for _ in range(80))
        cands, stats = eng.batch_search(header, (1 << 256) - 1,
                                        NONCE_SPACE - 32, 32)
        got = {c["nonce"]: bytes.fromhex(c["hash"])[::-1]
               for c in cands}
        want = {n: cpu_digest(header, n)
                for n in range(NONCE_SPACE - 32, NONCE_SPACE)}
        assert got == want
    print("ok 003.7/4: shared subtraction-based range validation "
          "12 of 12 on the host build of the CUDA header; CPU and "
          "GPU-shared-source differential sampling matches hashlib "
          "on randomized headers including the final nonce")


# ----------------------------------------------------------------
# Performance snapshot (labelled, contention-aware)
# ----------------------------------------------------------------

def test_performance_snapshot():
    eng = ComputeEngine()
    header = bytes(80)
    hard = 1 << 200
    rates = {}
    import gpu.engine as ge
    lib = eng._c_lib
    for threads in (1, 2, 4):
        out_nonce = ctypes.c_uint32(0)
        att = ctypes.c_uint64(0)
        dig = ctypes.create_string_buffer(32)
        t0 = time.perf_counter()
        rc = lib.bal_c_search2(header, 0, 1 << 20, threads,
                               hard.to_bytes(32, "little"),
                               ctypes.byref(out_nonce), dig,
                               ctypes.byref(att))
        dt = time.perf_counter() - t0
        assert rc in (0, 1)
        rates[threads] = att.value / dt
    t0 = time.perf_counter()
    for _ in range(200):
        verify_candidate(GENESIS, REGTEST_TARGET, 7,
                         cpu_digest(GENESIS, 7))
    verify_us = (time.perf_counter() - t0) / 200 * 1e6
    print(f"ok perf: C search counted rates on this contended VM "
          f"(live mainnet miner and node running): "
          f"1t {rates[1]:,.0f} H/s, 2t {rates[2]:,.0f} H/s, "
          f"4t {rates[4]:,.0f} H/s; CPU candidate verification "
          f"{verify_us:.1f} us each; CUDA device throughput: none "
          f"exists (no GPU)")


# ----------------------------------------------------------------
# Regtest: fresh block through the corrected native CPU backend
# ----------------------------------------------------------------

def test_regtest_block():
    from node import node_manager
    from node.rpc_client import BitcoinRPC
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
    # batch_size 100000 does not divide 2^32: the production cycle
    # exercises the Task 003.2 clamping on the real path.
    eng = MiningEngine(rpc, payout, compute=compute,
                       batch_size=100_000)
    tip0 = rpc.get_block_count()
    out = eng.mine_cycle(max_batches=1000, deadline_seconds=600)
    assert out["accepted"], out
    assert out["backend"] == "c"
    assert rpc.get_best_block_hash() == out["hash"]
    assert rpc.get_block_count() == tip0 + 1
    print(f"ok regtest: fresh block accepted through the corrected "
          f"native CPU backend: height {out['height']} hash "
          f"{out['hash']} submitblock null, best-block match, "
          f"hashes {out['hashes']}")
    return out


def main():
    test_mutex_harness()
    test_mutex_library_injection()
    test_batch_count()
    test_coverage_walks()
    test_bench_ranges()
    test_invalid_native_candidate()
    test_overflow_recovery()
    test_production_selftest()
    test_range_validation_and_differential()
    test_sanitizers()
    test_performance_snapshot()
    out = test_regtest_block()
    print("ALL TASK 003 CORRECTION TESTS PASSED "
          f"(regtest block {out['hash']} at height {out['height']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
