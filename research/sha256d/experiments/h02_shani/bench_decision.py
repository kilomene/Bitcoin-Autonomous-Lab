#!/usr/bin/env python3
"""Integration-decision benchmark: interleaved round-robin.

Sessions on this VM drift by more than the effects being
measured, so the decision run alternates backends inside one
session: production C, H-02 (1 stream), H-01 streams=2,
H-01 streams=4, each for 5 repeats of 1M hashes at threads=2
(the tuned production configuration) and threads=1, in
rotating order. Medians and spreads are computed over the
interleaved samples. attempted == count asserted per run.
"""
import ctypes
import json
import os
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from bench_harness import load_lib, run_batch, GENESIS, DIFF1_LE  # noqa: E402

ROOT = "/home/hatch/workspace/bitcoin-autonomous-lab"
COUNT = 1_000_000
REPEATS = 5


def bind_m(lib):
    fn = lib.bal_m_batch2
    fn.restype = ctypes.c_int
    fn.argtypes = [ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
                   ctypes.c_uint, ctypes.c_int, ctypes.c_char_p,
                   ctypes.c_char_p, ctypes.c_char_p,
                   ctypes.POINTER(ctypes.c_uint64)]
    return fn


def run_m(fn, count, threads, streams):
    h = ctypes.create_string_buffer(32 * count)
    f = ctypes.create_string_buffer(count)
    a = ctypes.c_uint64(0)
    t0 = time.perf_counter()
    rc = fn(GENESIS, 0, count, threads, streams, DIFF1_LE, h, f,
            ctypes.byref(a))
    dt = time.perf_counter() - t0
    assert rc == 0 and a.value == count, (rc, a.value)
    return count / dt


def main():
    _c, c_b2, _s = load_lib(f"{ROOT}/.local/cpu/libbal_batch.so",
                            "bal_c")
    _h, h_b2, _s2 = load_lib(os.path.join(HERE, "libbal_h02.so"),
                             "bal_h")
    mlib = ctypes.CDLL(os.path.join(HERE, "libbal_h01.so"))
    m_b2 = bind_m(mlib)
    # run_batch returns (rc, attempted, dt, raw).
    def prod(n, t):
        rc, att, dt, _r = run_batch(c_b2, GENESIS, DIFF1_LE, 0, n, t)
        assert rc == 0 and att == n
        return n / dt

    def h02(n, t):
        rc, att, dt, _r = run_batch(h_b2, GENESIS, DIFF1_LE, 0, n, t)
        assert rc == 0 and att == n
        return n / dt

    contenders = [
        ("production_c", prod),
        ("h02_shani_1stream", h02),
        ("h01_streams2", lambda n, t: run_m(m_b2, n, t, 2)),
        ("h01_streams4", lambda n, t: run_m(m_b2, n, t, 4)),
    ]
    out = {"experiment": "EXP-002/003 integration decision run",
           "load_average_at_run":
               open("/proc/loadavg").read().split()[:3],
           "contention": ("live mainnet pool miner and pruned node "
                          "running; shared VM capped near 1.5 CPUs"),
           "design": "round-robin interleaved, 5 repeats x 1M",
           "threads": {}}
    for threads in (1, 2):
        rates = {name: [] for name, _f in contenders}
        for rep in range(REPEATS):
            order = contenders[rep % len(contenders):] \
                + contenders[:rep % len(contenders)]
            for name, fn in order:
                rates[name].append(fn(COUNT, threads))
        entry = {}
        for name, rs in rates.items():
            med = statistics.median(rs)
            entry[name] = {
                "rates_hs": [round(r) for r in rs],
                "median_hs": round(med),
                "min_hs": round(min(rs)), "max_hs": round(max(rs)),
                "spread_pct": round(
                    100.0 * (max(rs) - min(rs)) / med, 1)}
            print(f"t={threads} {name}", entry[name])
        out["threads"][str(threads)] = entry
    with open(os.path.join(HERE, "exp_decision_benchmarks.json"),
              "w") as fh:
        json.dump(out, fh, indent=2)
    print("wrote exp_decision_benchmarks.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
