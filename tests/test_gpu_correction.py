#!/usr/bin/env python3
"""Task 002 GPU/CUDA correction tests.

What can be proven on a machine with NO NVIDIA GPU, and what cannot:

Proven here (host-exact evidence):
- The shared CUDA SHA-256 source, compiled for the host, produces
  exact SHA-256d through the NEW midstate path and the NEW circular
  16-word schedule path (genesis, fixed sample, 300 randomized
  headers x 5 nonce boundaries, all cross-checked in C and the
  sample cross-checked against hashlib here).
- The bounded candidate-recording primitive: total count, capacity,
  overflow flag, and 8-thread concurrent recording.
- Build states are separated and honest; a full build without a
  CUDA compiler exits nonzero; --host-only exits 0.
- CUDA-only mode fails clearly when CUDA cannot execute.
- Fallback execution is reported as the backend that really ran.
- Nonce range boundaries on the live engine (the complete 32-bit
  space, no wrap).
- The benchmark harness runs and labels non-GPU numbers as such.

NOT proven here (requires a physical NVIDIA GPU): Gate 6 device
execution and Gate 7 GPU-candidate regtest acceptance. Those stay
UNVERIFIED in results/TASK002_GPU_CORRECTION.md; nothing in this
file pretends otherwise.
"""

import glob
import hashlib
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gpu.benchmark import run_benchmark
from gpu.cuda.build import build
from gpu.engine import ComputeEngine, cpu_digest, verify_candidate

GENESIS_HASH = ("000000000019d6689c085ae165831e934ff763ae46a"
                "2a6c172b3f1b60a8ce26f")
REGTEST_TARGET = 0x7FFFFF << 232


def genesis_header():
    return bytes.fromhex(
        "01000000" + "00" * 32
        + "3ba3edfd7a7b12b27ac72c3e67768f617fc81bc3888a51323a9fb8aa4b1e5e4a"
        + "29ab5f49" + "ffff001d" + "1dac2b7c")


def lcg_bytes(n, seed=42):
    state = seed
    out = bytearray()
    for _ in range(n):
        state = (state * 1664525 + 1013904223) & 0xFFFFFFFF
        out.append((state >> 24) & 0xFF)
    return bytes(out)


def main():
    have_device = len(glob.glob("/dev/nvidia[0-9]*")) > 0

    # --- Build states and exit codes (Phase 8) ---
    res = build(log=lambda *a: None, require_cuda=False)
    st = res["states"]
    assert st["host_build"] == "ok", st
    assert res["host_checks"], res
    assert st["execution_verified"] is False, st
    if res["nvcc"]:
        assert st["cuda_build"] == "ok", st
        assert st["runtime"] in ("no_device", "device_available",
                                 "runtime_error_35"), st
    else:
        assert st["cuda_build"] == "unavailable", st
        assert build(log=lambda *a: None,
                     require_cuda=True)["ok"] is False
    proc = subprocess.run(
        [sys.executable, os.path.join("gpu", "cuda", "build.py"),
         "--host-only"], capture_output=True, text=True,
        cwd=os.path.join(os.path.dirname(__file__), ".."))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    proc = subprocess.run(
        [sys.executable, os.path.join("gpu", "cuda", "build.py")],
        capture_output=True, text=True,
        cwd=os.path.join(os.path.dirname(__file__), ".."))
    assert proc.returncode == (0 if res["nvcc"] else 1), (
        proc.returncode, res["nvcc"])
    print(f"ok: build states separated {st}; exit codes honest "
          f"(host-only 0, full {proc.returncode})")

    # --- Host checks: midstate, circular schedule, candidates ---
    out = subprocess.run([res["host_checks"]], capture_output=True,
                         text=True)
    assert out.returncode == 0, out.stderr
    lines = out.stdout.splitlines()
    assert lines[0] == GENESIS_HASH, lines[0]
    assert lines[1] == GENESIS_HASH, lines[1]
    assert lines[2].startswith("sample ")
    sample_hex = lines[2].split()[1]
    sample_header = lcg_bytes(80)
    expect = hashlib.sha256(hashlib.sha256(
        sample_header[:76] + struct.pack("<I", 12345)).digest()).digest()
    assert sample_hex == expect.hex(), (sample_hex, expect.hex())
    assert lines[3] == "random_mismatches 0", lines[3]
    parts = lines[4].split()
    assert parts[0] == "cand"
    total = int(parts[2])
    expected_total = 0
    header = genesis_header()
    for n in range(2000):
        if int.from_bytes(cpu_digest(header, n), "little") <= REGTEST_TARGET:
            expected_total += 1
    assert total == expected_total, (total, expected_total)
    assert int(parts[4]) == min(total, 3)
    assert int(parts[6]) == (1 if total > 3 else 0)
    parts = lines[5].split()
    assert parts[0] == "concurrent"
    assert int(parts[2]) == 40000 and int(parts[4]) == 100
    assert int(parts[6]) == 1
    print(f"ok: host midstate and circular paths genesis-exact and "
          f"sample-exact vs hashlib; randomized mismatches 0; "
          f"candidate bound/overflow exact ({total} found, cap 3); "
          f"concurrent recording exact (40000 into cap 100)")

    # --- Target boundary logic on the reference path ---
    eng = ComputeEngine()
    for tgt, should_hit in ((REGTEST_TARGET, True),):
        cands, stats = eng.batch_search(header, tgt, 0, 4096)
        assert bool(cands) == should_hit
        for c in cands:
            d = cpu_digest(header, c["nonce"])
            assert int.from_bytes(d, "little") <= tgt
    # Equality meets: search a range for the genesis nonce itself
    # with target exactly equal to its digest value.
    g = cpu_digest(header, 2083236893)
    gv = int.from_bytes(g, "little")
    cands, _ = eng.batch_search(header, gv, 2083236893, 1)
    assert len(cands) == 1 and cands[0]["nonce"] == 2083236893
    cands, _ = eng.batch_search(header, gv - 1, 2083236893, 1)
    assert cands == []
    print("ok: target boundaries (below, equal meets, above) exact")

    # --- Nonce boundaries through the live engine (Phase 6) ---
    hit, attempted, _ = eng.search_first_counted(
        header, REGTEST_TARGET, 0xFFFFFFFF, 1)
    assert attempted == 1
    hit, attempted, _ = eng.search_first_counted(
        header, REGTEST_TARGET, 0xFFFFFFFE, 2)
    # Both boundary nonces meet this easy target, so either
    # may be the published winner, and an early-exit backend
    # may legitimately never examine the other: attempted
    # counts examined nonces only (1 or 2). The boundary
    # invariant is that the range is accepted, the hit is one
    # of the two boundary nonces, verifies, and nothing wraps.
    assert hit and hit[0] in (0xFFFFFFFE, 0xFFFFFFFF), hit
    assert verify_candidate(header, REGTEST_TARGET, hit[0],
                            hit[1])
    assert 1 <= attempted <= 2, attempted
    for bad_start, bad_count in ((0xFFFFFFFF, 2), (0, 0),
                                 (1 << 32, 1)):
        try:
            eng.search_first_counted(header, REGTEST_TARGET,
                                     bad_start, bad_count)
            raise AssertionError("range not rejected")
        except ValueError:
            pass
    print("ok: nonce boundaries 0xFFFFFFFE/0xFFFFFFFF handled, "
          "wrapping and empty ranges rejected")

    # --- Honest fallback and CUDA-only failure (Phases 7, 8) ---
    if not have_device:
        assert eng.backend in ("c", "cpu", "v512"), eng.describe()
        assert eng.describe()["cuda_context"] is False
        _, stats = eng.batch_search(header, REGTEST_TARGET, 0, 1024)
        assert stats["backend"] == eng.backend != "cuda", stats
        try:
            ComputeEngine(requested="cuda-only")
            raise AssertionError("cuda-only did not fail")
        except RuntimeError as exc:
            assert "CUDA-only" in str(exc)
        print(f"ok: no device; engine honestly on {eng.backend}, "
              f"cuda-only mode fails clearly, context absent")
    else:
        assert eng.backend == "cuda", eng.describe()
        print("ok: device present; CUDA backend selected")

    # --- Benchmark harness honesty (Phase 9) ---
    bench = run_benchmark(batches=2, batch=8192, engine=eng)
    assert bench["median_hashrate"] > 0
    if not have_device:
        assert bench["is_gpu_measurement"] is False
        assert "NOT a GPU measurement" in bench["label"]
        assert "not comparable yet" in bench["cpu_vs_gpu_comparison"]
    print(f"ok: benchmark harness: median {bench['median_hashrate']:,.0f} "
          f"H/s, label: {bench['label']}")

    print("ALL GPU CORRECTION TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
