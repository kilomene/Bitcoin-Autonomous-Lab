#!/usr/bin/env python3
"""EXP-045 correctness gates.

Gate rule (mandate for this experiment): before any timing,
every library must pass a hashlib differential on at least
100,000 digests through its own harness. EXP-045 has two
harnesses (direct ctypes, as both EXP-032 and EXP-039 batch
drivers called the counted entries, and the production
ComputeEngine.batch_search seam) and three batch libraries
in play (production C, research-built AVX2, production-built
AVX2), so six arm paths are gated here:

  direct_c, direct_avx2_research, direct_avx2_prod,
  seam_c, seam_avx2_prod, seam_avx2_research

The seam_avx2_research arm exists because the research
library carries no CPUID probe symbol, so production
dispatch (gpu/engine.py _try_avx2) would refuse it. The
gate (and the bench driver) construct a ComputeEngine
pinned to avx2 through the normal dispatch, then replace
the engine's loaded library object with a ctypes handle
on the research library whose bal_a_batch2 argtypes are
set exactly as _try_avx2 sets them. Only the library
object differs; every line of engine machinery that runs
is production code. This is recorded wherever the arm is
used.

Each arm is checked over 131,072 genesis-header digests
(two 65,536 batches) at the all-ones target, so every
digest is materialised and compared byte for byte with
hashlib. The two AVX2 libraries additionally pass a
65,536-digest random-header batch through the direct
harness. Any mismatch fails the gate and no benchmark
session may run.
"""
import ctypes
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

ROOT = "/home/hatch/workspace/bitcoin-autonomous-lab"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "research/sha256d/experiments"))
sys.path.insert(0, ROOT)
from bench_harness import load_lib, GENESIS  # noqa: E402

CPU_DIR = os.path.join(ROOT, ".local/cpu")
C_LIB = os.path.join(CPU_DIR, "libbal_batch.so")
AVX2_PROD_LIB = os.path.join(CPU_DIR, "libbal_avx2.so")
AVX2_RESEARCH_LIB = os.path.join(
    ROOT, "research/sha256d/exp032/libbal_avx2.so")
MAX_TARGET_INT = (1 << 256) - 1
MAX_LE = MAX_TARGET_INT.to_bytes(32, "little")
BLOCK = 65_536


def ref_digest(header, nonce):
    return hashlib.sha256(hashlib.sha256(
        header[:76] + nonce.to_bytes(4, "little")).digest()).digest()


def counted(fn):
    fn.restype = ctypes.c_int
    fn.argtypes = [
        ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
        ctypes.c_uint, ctypes.c_char_p, ctypes.c_char_p,
        ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint64),
        ctypes.POINTER(ctypes.c_uint64)]
    return fn


def direct_avx2_batch(fn, header, start, count, threads=2):
    hashes = ctypes.create_string_buffer(32 * count)
    flags = ctypes.create_string_buffer(count)
    attempted = ctypes.c_uint64(0)
    backend = ctypes.c_uint64(0)
    rc = fn(header, start, count, threads, MAX_LE, hashes, flags,
            ctypes.byref(attempted), ctypes.byref(backend))
    return rc, attempted.value, backend.value, hashes.raw


def check_raw(raw, header, start, count):
    for i in range(count):
        if raw[32 * i:32 * i + 32] != ref_digest(header, start + i):
            return start + i
    return None


def gate_direct_c():
    _lib, batch2, _s = load_lib(C_LIB, "bal_c")
    checked = 0
    for start in (0, BLOCK):
        hashes = ctypes.create_string_buffer(32 * BLOCK)
        flags = ctypes.create_string_buffer(BLOCK)
        attempted = ctypes.c_uint64(0)
        rc = batch2(GENESIS, start, BLOCK, 2, MAX_LE, hashes, flags,
                    ctypes.byref(attempted))
        assert rc == 0 and attempted.value == BLOCK, (rc, attempted)
        bad = check_raw(hashes.raw, GENESIS, start, BLOCK)
        assert bad is None, f"direct_c mismatch at nonce {bad}"
        checked += BLOCK
    return checked


def gate_direct_avx2(path, random_header):
    lib = ctypes.CDLL(path)
    fn = counted(lib.bal_a_batch2)
    checked = 0
    for header, start in ((GENESIS, 0), (GENESIS, BLOCK),
                          (random_header, 0)):
        rc, attempted, backend, raw = direct_avx2_batch(
            fn, header, start, BLOCK)
        assert rc == 0 and attempted == BLOCK, (rc, attempted)
        assert backend >= attempted, (backend, attempted)
        bad = check_raw(raw, header, start, BLOCK)
        assert bad is None, f"{path} mismatch at nonce {bad}"
        checked += BLOCK
    return checked


def make_engines():
    os.environ.setdefault("BAL_C_THREADS", "2")
    import gpu.engine as engine_mod
    from gpu.engine import ComputeEngine
    assert engine_mod.C_THREADS == 2, engine_mod.C_THREADS
    eng_c = ComputeEngine(requested="c")
    assert eng_c.backend == "c", eng_c.backend
    eng_a = ComputeEngine(requested="avx2")
    assert eng_a.backend == "avx2", eng_a.backend
    eng_r = ComputeEngine(requested="avx2")
    assert eng_r.backend == "avx2", eng_r.backend
    lib = ctypes.CDLL(AVX2_RESEARCH_LIB)
    fn = lib.bal_a_batch2
    fn.restype = ctypes.c_int
    fn.argtypes = [
        ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
        ctypes.c_uint, ctypes.c_char_p, ctypes.c_char_p,
        ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint64),
        ctypes.POINTER(ctypes.c_uint64)]
    eng_r._a_lib = lib
    return eng_c, eng_a, eng_r


def gate_seam(eng, label):
    checked = 0
    for start in (0, BLOCK):
        cands, stats = eng.batch_search(
            GENESIS, MAX_TARGET_INT, start, BLOCK)
        assert stats["unique_coverage"] == BLOCK, stats
        assert stats["batch_path"] == "materialised", stats
        assert len(cands) == BLOCK, (label, len(cands))
        by_nonce = {c["nonce"]: c["hash"] for c in cands}
        assert len(by_nonce) == BLOCK, label
        for nonce in range(start, start + BLOCK):
            want = ref_digest(GENESIS, nonce)[::-1].hex()
            assert by_nonce[nonce] == want, (
                label, nonce, by_nonce[nonce], want)
        checked += BLOCK
    return checked


def main():
    random_header = os.urandom(80)
    results = {}
    results["direct_c"] = gate_direct_c()
    print(f"direct_c: {results['direct_c']} digests OK", flush=True)
    results["direct_avx2_research"] = gate_direct_avx2(
        AVX2_RESEARCH_LIB, random_header)
    print(f"direct_avx2_research: "
          f"{results['direct_avx2_research']} digests OK", flush=True)
    results["direct_avx2_prod"] = gate_direct_avx2(
        AVX2_PROD_LIB, random_header)
    print(f"direct_avx2_prod: "
          f"{results['direct_avx2_prod']} digests OK", flush=True)
    eng_c, eng_a, eng_r = make_engines()
    results["seam_c"] = gate_seam(eng_c, "seam_c")
    print(f"seam_c: {results['seam_c']} digests OK", flush=True)
    results["seam_avx2_prod"] = gate_seam(eng_a, "seam_avx2_prod")
    print(f"seam_avx2_prod: {results['seam_avx2_prod']} digests OK",
          flush=True)
    results["seam_avx2_research"] = gate_seam(
        eng_r, "seam_avx2_research")
    print(f"seam_avx2_research: {results['seam_avx2_research']} "
          f"digests OK", flush=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    record = {
        "experiment": "EXP-045",
        "gate_utc": datetime.now(timezone.utc).isoformat(),
        "host_cpu": open("/proc/cpuinfo").read().split(
            "model name")[1].split(":")[1].split("\n")[0].strip(),
        "random_header_hex": random_header.hex(),
        "digests_checked": results,
        "total_digests": sum(results.values()),
        "verdict": "ALL PASS",
        "libraries": {
            "c": C_LIB, "avx2_prod": AVX2_PROD_LIB,
            "avx2_research": AVX2_RESEARCH_LIB},
    }
    out_dir = os.path.join(HERE, "RAW_RESULTS")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"gates_{stamp}.json")
    suffix = 2
    while os.path.exists(path):
        path = os.path.join(out_dir, f"gates_{stamp}_r{suffix}.json")
        suffix += 1
    with open(path, "x") as fh:
        json.dump(record, fh, indent=2)
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
