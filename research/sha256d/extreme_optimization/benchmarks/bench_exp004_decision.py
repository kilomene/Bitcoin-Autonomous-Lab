#!/usr/bin/env python3
"""EXP-004 (X-067): integration decision re-run.

PREDECLARED VERDICT RULE (stated before this run, unchanged
from the programme's strict rule): integration of the H-01
family is justified only if, at 2 worker threads in this
round-robin interleaved session, streams=4's MINIMUM rate
exceeds production C's MAXIMUM rate (complete separation,
beyond spread). Any weaker separation, however consistent
the medians, does not integrate.

Method: bench_decision.py methodology extended: one
session, round-robin interleaved, contenders production C,
H-01 streams=2, H-01 streams=4, 9 rounds of 1M hashes at
2 threads and at 1 thread. attempted == count asserted per
run. Steal covariate (X-070 lite): /proc/stat aggregate
steal jiffies sampled at session start and end per thread
configuration, reported as a percentage of total CPU
jiffies over the same window. Node sync state and load
recorded at start and end.
"""
import ctypes
import json
import os
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
EO = os.path.dirname(HERE)
ROOT = "/home/hatch/workspace/bitcoin-autonomous-lab"
sys.path.insert(0, os.path.join(ROOT, "research/sha256d/experiments"))
from bench_harness import load_lib, run_batch, GENESIS, DIFF1_LE  # noqa: E402

COUNT = 1_000_000
ROUNDS = 9


def steal_snapshot():
    with open("/proc/stat") as fh:
        parts = fh.readline().split()[1:]
    vals = [int(x) for x in parts]
    return sum(vals), vals[7]  # total, steal


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
    mlib = ctypes.CDLL(os.path.join(
        ROOT, "research/sha256d/experiments/h02_shani/libbal_h01.so"))
    m_b2 = bind_m(mlib)

    def prod(n, t):
        rc, att, dt, _r = run_batch(c_b2, GENESIS, DIFF1_LE, 0, n, t)
        assert rc == 0 and att == n
        return n / dt

    contenders = [
        ("production_c", prod),
        ("h01_streams2", lambda n, t: run_m(m_b2, n, t, 2)),
        ("h01_streams4", lambda n, t: run_m(m_b2, n, t, 4)),
    ]
    out = {"experiment": "EXP-004 X-067 integration decision re-run",
           "predeclared_rule": ("streams=4 min > production max at "
                                "2 threads (complete separation)"),
           "design": f"round-robin interleaved, {ROUNDS} rounds x 1M",
           "load_average_at_start":
               open("/proc/loadavg").read().split()[:3],
           "threads": {}}
    for threads in (2, 1):
        tot0, st0 = steal_snapshot()
        t_start = time.time()
        rates = {name: [] for name, _f in contenders}
        for rep in range(ROUNDS):
            order = contenders[rep % len(contenders):] \
                + contenders[:rep % len(contenders)]
            for name, fn in order:
                rates[name].append(fn(COUNT, threads))
        tot1, st1 = steal_snapshot()
        wall = time.time() - t_start
        steal_pct = 100.0 * (st1 - st0) / max(tot1 - tot0, 1)
        entry = {"steal_pct_during_config": round(steal_pct, 2),
                 "wall_seconds": round(wall, 1)}
        for name, rs in rates.items():
            med = statistics.median(rs)
            entry[name] = {
                "rates_hs": [round(r) for r in rs],
                "median_hs": round(med),
                "min_hs": round(min(rs)), "max_hs": round(max(rs)),
                "spread_pct": round(
                    100.0 * (max(rs) - min(rs)) / med, 1)}
            print(f"t={threads} {name}", entry[name], flush=True)
        out["threads"][str(threads)] = entry
    out["load_average_at_end"] = \
        open("/proc/loadavg").read().split()[:3]
    t2 = out["threads"]["2"]
    sep = t2["h01_streams4"]["min_hs"] > t2["production_c"]["max_hs"]
    out["verdict"] = {
        "criterion": "streams4_min > production_max at 2 threads",
        "streams4_min_hs": t2["h01_streams4"]["min_hs"],
        "production_max_hs": t2["production_c"]["max_hs"],
        "separation_achieved": sep,
        "integration_justified": sep}
    print("VERDICT", out["verdict"], flush=True)
    with open(os.path.join(HERE, "exp004_decision.json"), "w") as fh:
        json.dump(out, fh, indent=2)
    print("wrote exp004_decision.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
