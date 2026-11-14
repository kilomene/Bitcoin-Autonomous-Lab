#!/usr/bin/env python3
"""EXP-003 benchmark: H-01 multi-stream throughput and latency.

Same workload discipline as EXP-000 (genesis header, DIFF1
target, 1M hashes per run, 3 repeats, attempted == count
asserted): per-worker throughput is the threads=1 column,
total throughput the threads=2 column. Streams are inside one
worker; threads are OS workers. The two are never conflated.

Latency: median wall time of count=1 batch calls per stream
count (includes ctypes crossing and wave setup; an upper bound
on single-candidate latency, labelled as in EXP-000).
"""
import ctypes
import json
import os
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from bench_harness import GENESIS, DIFF1_LE  # noqa: E402

COUNT = 1_000_000
REPEATS = 3


def main():
    lib = ctypes.CDLL(os.path.join(HERE, "libbal_h01.so"))
    bfn = lib.bal_m_batch2
    bfn.restype = ctypes.c_int
    bfn.argtypes = [ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
                    ctypes.c_uint, ctypes.c_int, ctypes.c_char_p,
                    ctypes.c_char_p, ctypes.c_char_p,
                    ctypes.POINTER(ctypes.c_uint64)]

    def run(count, threads, streams):
        h = ctypes.create_string_buffer(32 * count)
        f = ctypes.create_string_buffer(count)
        a = ctypes.c_uint64(0)
        t0 = time.perf_counter()
        rc = bfn(GENESIS, 0, count, threads, streams, DIFF1_LE, h, f,
                 ctypes.byref(a))
        dt = time.perf_counter() - t0
        assert rc == 0 and a.value == count, (rc, a.value, count)
        return count / dt

    out = {"experiment": "EXP-003 H-01 multi-stream",
           "load_average_at_run":
               open("/proc/loadavg").read().split()[:3],
           "contention": ("live mainnet pool miner and pruned node "
                          "running; shared VM capped near 1.5 CPUs"),
           "accounting": ("unique_coverage == backend computations "
                          "(batch path, attempted asserted)"),
           "configs": {}}
    for streams in (1, 2, 4):
        for threads in (1, 2):
            rates = [run(COUNT, threads, streams)
                     for _ in range(REPEATS)]
            med = statistics.median(rates)
            entry = {"streams": streams, "threads": threads,
                     "rates_hs": [round(r) for r in rates],
                     "median_hs": round(med),
                     "min_hs": round(min(rates)),
                     "max_hs": round(max(rates)),
                     "spread_pct": round(
                         100.0 * (max(rates) - min(rates)) / med, 1),
                     "per_worker_median_hs": round(med / threads)}
            out["configs"][f"s{streams}_t{threads}"] = entry
            print(f"streams={streams} threads={threads}", entry)
    lat = {}
    for streams in (1, 2, 4):
        times = []
        for _ in range(2000):
            t0 = time.perf_counter()
            run(1, 1, streams)
            times.append(time.perf_counter() - t0)
        times.sort()
        lat[str(streams)] = {
            "median_us": round(statistics.median(times) * 1e6, 2),
            "p90_us": round(times[9 * len(times) // 10] * 1e6, 2)}
        print(f"latency streams={streams}", lat[str(streams)])
    out["latency_count1_batch_call"] = lat
    with open(os.path.join(HERE, "exp003_benchmarks.json"), "w") as fh:
        json.dump(out, fh, indent=2)
    print("wrote exp003_benchmarks.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
