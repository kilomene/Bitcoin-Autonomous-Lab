#!/usr/bin/env python3
"""EXP-032 supplementary probe: median rates outside the
EXP-017 protocol.

Purpose: configuration context the paired protocol does
not cover (the protocol fixes 2 threads and 65,536-hash
blocks): SHA-NI stream counts 1, 2 and 4 at 1 and 2
threads, AVX2 at 1, 2 and 4 threads, and the production
backends at 1 thread for scale reference. These are
simple medians of repeated counted batch calls on a
contended shared VM. They are labelled supplementary
everywhere they are quoted: no verdict rests on them.
"""
import ctypes
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = "/home/hatch/workspace/bitcoin-autonomous-lab"
sys.path.insert(0, os.path.join(ROOT, "research/sha256d/experiments"))
from bench_harness import load_lib, GENESIS, DIFF1_LE  # noqa: E402

COUNT = 65_536
REPEATS = 9


def median_rate(fn, threads, streams=None, is_counted=False):
    rates = []
    for _ in range(REPEATS):
        hashes = ctypes.create_string_buffer(32 * COUNT)
        flags = ctypes.create_string_buffer(COUNT)
        attempted = ctypes.c_uint64(0)
        backend = ctypes.c_uint64(0)
        args = [GENESIS, 0, COUNT, threads]
        if streams is not None:
            args.append(streams)
        args += [DIFF1_LE, hashes, flags, ctypes.byref(attempted)]
        t0 = time.perf_counter()
        if is_counted:
            rc = fn(*args, ctypes.byref(backend))
        else:
            rc = fn(*args)
        dt = time.perf_counter() - t0
        assert rc == 0 and attempted.value == COUNT, (rc,
                                                      attempted.value)
        rates.append(COUNT / dt)
    return {"median_hs": statistics.median(rates),
            "min_hs": min(rates), "max_hs": max(rates),
            "repeats": REPEATS, "count": COUNT}


def counted(fn):
    fn.restype = ctypes.c_int
    fn.argtypes = [
        ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
        ctypes.c_uint, ctypes.c_char_p, ctypes.c_char_p,
        ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint64),
        ctypes.POINTER(ctypes.c_uint64)]
    return fn


def main():
    cpu = os.path.join(ROOT, ".local/cpu")
    _l, c_fn, _s = load_lib(os.path.join(cpu, "libbal_batch.so"),
                            "bal_c")
    _l, i_fn, _s = load_lib(os.path.join(cpu, "libbal_intrin.so"),
                            "bal_i")
    vd = ctypes.CDLL(os.path.join(cpu, "libbal_v512dual.so"))
    vd_fn = counted(vd.bal_vd_batch2)
    avx2 = ctypes.CDLL(os.path.join(HERE, "libbal_avx2.so"))
    a_fn = counted(avx2.bal_a_batch2)
    h01 = ctypes.CDLL(os.path.join(HERE, "libbal_h01.so"))
    m_fn = h01.bal_m_batch2
    m_fn.restype = ctypes.c_int
    m_fn.argtypes = [
        ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
        ctypes.c_uint, ctypes.c_int, ctypes.c_char_p,
        ctypes.c_char_p, ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_uint64)]

    out = {"experiment": "EXP-032 supplementary probe",
           "utc": datetime.now(timezone.utc).isoformat(),
           "host": "AMD EPYC 9D25 (guest, htch-runtime)",
           "note": "medians of counted batch calls; NOT the "
                   "EXP-017 protocol; no verdict rests on "
                   "these numbers",
           "configs": {}}
    jobs = [
        ("c_batch_t1", c_fn, 1, None, False),
        ("c_batch_t2", c_fn, 2, None, False),
        ("shani_intrin_t1", i_fn, 1, None, False),
        ("shani_intrin_t2", i_fn, 2, None, False),
        ("v512dual_batch_t1", vd_fn, 1, None, True),
        ("v512dual_batch_t2", vd_fn, 2, None, True),
        ("avx2_batch_t1", a_fn, 1, None, True),
        ("avx2_batch_t2", a_fn, 2, None, True),
        ("avx2_batch_t4", a_fn, 4, None, True),
        ("shani_m1_t1", m_fn, 1, 1, False),
        ("shani_m2_t1", m_fn, 1, 2, False),
        ("shani_m4_t1", m_fn, 1, 4, False),
        ("shani_m1_t2", m_fn, 2, 1, False),
        ("shani_m2_t2", m_fn, 2, 2, False),
        ("shani_m4_t2", m_fn, 2, 4, False),
    ]
    for name, fn, threads, streams, is_counted in jobs:
        r = median_rate(fn, threads, streams, is_counted)
        out["configs"][name] = r
        print(f"{name}: median {r['median_hs']:,.0f} H/s "
              f"(min {r['min_hs']:,.0f}, max {r['max_hs']:,.0f})",
              flush=True)
    path = os.path.join(
        HERE, "RAW_RESULTS",
        "probe_" + datetime.now(timezone.utc).strftime(
            "%Y%m%dT%H%M%SZ") + ".json")
    with open(path, "x") as fh:
        json.dump(out, fh, indent=2)
    print("wrote", path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
