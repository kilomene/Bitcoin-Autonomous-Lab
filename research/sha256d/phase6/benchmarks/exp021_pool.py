#!/usr/bin/env python3
"""EXP-021 (Y-097) mixed worker pool: shared library.

A pool is a list of worker specs. Each worker is one OS
thread (a Python thread around one counted batch call;
ctypes releases the GIL for the duration of the call)
running one kernel family over its own contiguous,
disjoint partition of a nonce range:

  ("mb", None)     AVX-512 multi-buffer kernel,
                   bal_v_batch2 with threads=1
                   (libbal_v512.so, the EXP-007 kernel
                   whose twin is the production v512
                   backend).
  ("shani", 4)     SHA-NI multi-stream kernel,
                   bal_m_batch2m with threads=1,
                   streams=4, mode=1 (strided): the
                   best per-worker geometry of
                   EXP-005 (libbal_geo.so).

Partitions are contiguous chunks whose sizes are
multiples of 16 (the MB wave size), summing exactly
to the requested total; the size remainder goes to
the earliest workers one wave at a time. A worker
whose chunk is empty is not launched and contributes
attempted 0. Workers start on a shared barrier so
the pool elapsed time is the makespan: the span
from the earliest worker start to the latest worker
finish. Per-worker attempted comes from the kernels'
own counted outputs, never from the request.

Used by the correctness gates
(extreme_optimization/tests/test_exp021.py) and the
paired benchmark driver (exp021_paired_bench.py).
Production code is not touched by either.
"""
import ctypes
import os
import threading
import time

ROOT = "/home/hatch/workspace/bitcoin-autonomous-lab"
EO_SRC = os.path.join(ROOT, "research/sha256d/extreme_optimization/src")

MB = ("mb", None)
SHANI = ("shani", 4)

_geo = ctypes.CDLL(os.path.join(EO_SRC, "libbal_geo.so"))
_geo_fn = _geo.bal_m_batch2m
_geo_fn.restype = ctypes.c_int
_geo_fn.argtypes = [
    ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
    ctypes.c_uint, ctypes.c_int, ctypes.c_int,
    ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
    ctypes.POINTER(ctypes.c_uint64)]

_v512 = ctypes.CDLL(os.path.join(EO_SRC, "libbal_v512.so"))
_mb_fn = _v512.bal_v_batch2
_mb_fn.restype = ctypes.c_int
_mb_fn.argtypes = [
    ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
    ctypes.c_uint, ctypes.c_char_p, ctypes.c_char_p,
    ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint64),
    ctypes.POINTER(ctypes.c_uint64)]


def partition(start, total, k):
    """Split [start, start+total) into k contiguous
    chunks of multiples of 16 summing to total.
    Returns a list of (part_start, part_count)."""
    assert total % 16 == 0, "pool totals are wave multiples"
    assert k >= 1
    units = total // 16
    per, rem = divmod(units, k)
    out = []
    pos = start
    for i in range(k):
        count = (per + (1 if i < rem else 0)) * 16
        out.append((pos, count))
        pos += count
    assert pos == start + total
    return out


def _worker(spec, header, pstart, pcount, target, barrier,
            results, idx, materialize):
    family, streams = spec
    hashes = ctypes.create_string_buffer(32 * max(pcount, 1))
    flags = ctypes.create_string_buffer(max(pcount, 1))
    attempted = ctypes.c_uint64(0)
    backend = ctypes.c_uint64(0)
    barrier.wait()
    t0 = time.perf_counter()
    if family == "mb":
        rc = _mb_fn(header, pstart, pcount, 1, target, hashes,
                    flags, ctypes.byref(attempted),
                    ctypes.byref(backend))
    elif family == "shani":
        rc = _geo_fn(header, pstart, pcount, 1, streams, 1,
                     target, hashes, flags,
                     ctypes.byref(attempted))
        backend.value = attempted.value
    else:
        raise ValueError(f"unknown family {family}")
    t1 = time.perf_counter()
    rec = {
        "family": family,
        "streams": streams,
        "part_start": pstart,
        "part_count": pcount,
        "rc": rc,
        "attempted": attempted.value,
        "backend_attempted": backend.value,
        "start_s": t0,
        "end_s": t1,
        "elapsed_s": t1 - t0,
    }
    if materialize:
        rec["hashes"] = hashes.raw[:32 * pcount]
        rec["flags"] = flags.raw[:pcount]
    results[idx] = rec


def run_pool(specs, header, start, total, target,
             materialize=False):
    """Run one pool over [start, start+total) and return
    the pool record: makespan elapsed, total rate, and
    the per-worker records in spec order."""
    parts = partition(start, total, len(specs))
    active = [(i, spec, ps, pc)
              for i, (spec, (ps, pc)) in enumerate(zip(specs, parts))
              if pc > 0]
    results = {}
    if active:
        barrier = threading.Barrier(len(active))
        threads = []
        for i, spec, ps, pc in active:
            th = threading.Thread(
                target=_worker,
                args=(spec, header, ps, pc, target, barrier,
                      results, i, materialize))
            th.start()
            threads.append(th)
        for th in threads:
            th.join()
    workers = []
    for i, (spec, (ps, pc)) in enumerate(zip(specs, parts)):
        if pc > 0:
            workers.append(results[i])
        else:
            rec = {
                "family": spec[0], "streams": spec[1],
                "part_start": ps, "part_count": 0, "rc": 0,
                "attempted": 0, "backend_attempted": 0,
                "start_s": None, "end_s": None, "elapsed_s": 0.0}
            if materialize:
                rec["hashes"] = b""
                rec["flags"] = b""
            workers.append(rec)
    if active:
        t_start = min(w["start_s"] for w in workers if w["part_count"])
        t_end = max(w["end_s"] for w in workers if w["part_count"])
        elapsed = t_end - t_start
    else:
        elapsed = 0.0
    return {
        "specs": [list(s) for s in specs],
        "start": start,
        "total_count": total,
        "elapsed_s": elapsed,
        "rate_hs": (total / elapsed) if elapsed > 0 else 0.0,
        "attempted_total": sum(w["attempted"] for w in workers),
        "workers": workers,
    }
