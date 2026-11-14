#!/usr/bin/env python3
"""EXP-007 confirmation run: is the AVX-512 multi-buffer's
median lead in the combined EXP-005..008 session real?
Round-robin interleaved in one new session: production C,
geo streams=4 strided (the best SHA-NI geometry of the
combined session), avx512_mb16. 2 threads, 7 rounds x 1M.
attempted == count (and backend == count) asserted."""
import ctypes
import json
import os
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
EO = os.path.dirname(HERE)
SRC = os.path.join(EO, "src")
ROOT = "/home/hatch/workspace/bitcoin-autonomous-lab"
sys.path.insert(0, os.path.join(ROOT, "research/sha256d/experiments"))
from bench_harness import load_lib, run_batch, GENESIS, DIFF1_LE  # noqa: E402

COUNT = 1_000_000
ROUNDS = 7


def main():
    _c, c_b2, _s = load_lib(f"{ROOT}/.local/cpu/libbal_batch.so",
                            "bal_c")
    geo = ctypes.CDLL(os.path.join(SRC, "libbal_geo.so"))
    geo_b = geo.bal_m_batch2m
    geo_b.restype = ctypes.c_int
    geo_b.argtypes = [ctypes.c_char_p, ctypes.c_uint64,
                      ctypes.c_uint64, ctypes.c_uint, ctypes.c_int,
                      ctypes.c_int, ctypes.c_char_p,
                      ctypes.c_char_p, ctypes.c_char_p,
                      ctypes.POINTER(ctypes.c_uint64)]
    v5 = ctypes.CDLL(os.path.join(SRC, "libbal_v512.so"))
    v5_b = v5.bal_v_batch2
    v5_b.restype = ctypes.c_int
    v5_b.argtypes = [ctypes.c_char_p, ctypes.c_uint64,
                     ctypes.c_uint64, ctypes.c_uint, ctypes.c_char_p,
                     ctypes.c_char_p, ctypes.c_char_p,
                     ctypes.POINTER(ctypes.c_uint64),
                     ctypes.POINTER(ctypes.c_uint64)]

    def prod(n, t):
        rc, att, dt, _r = run_batch(c_b2, GENESIS, DIFF1_LE, 0, n, t)
        assert rc == 0 and att == n
        return n / dt

    def geo4s(n, t):
        h = ctypes.create_string_buffer(32 * n)
        f = ctypes.create_string_buffer(n)
        a = ctypes.c_uint64(0)
        t0 = time.perf_counter()
        rc = geo_b(GENESIS, 0, n, t, 4, 1, DIFF1_LE, h, f,
                   ctypes.byref(a))
        dt = time.perf_counter() - t0
        assert rc == 0 and a.value == n
        return n / dt

    def v512(n, t):
        h = ctypes.create_string_buffer(32 * n)
        f = ctypes.create_string_buffer(n)
        a = ctypes.c_uint64(0)
        b = ctypes.c_uint64(0)
        t0 = time.perf_counter()
        rc = v5_b(GENESIS, 0, n, t, DIFF1_LE, h, f,
                  ctypes.byref(a), ctypes.byref(b))
        dt = time.perf_counter() - t0
        assert rc == 0 and a.value == n and b.value == n
        return n / dt

    contenders = [("production_c", prod), ("geo_s4_strided", geo4s),
                  ("avx512_mb16", v512)]
    rates = {name: [] for name, _f in contenders}
    for rep in range(ROUNDS):
        order = contenders[rep % 3:] + contenders[:rep % 3]
        for name, fn in order:
            rates[name].append(fn(COUNT, 2))
    out = {"experiment": "EXP-007 confirmation run",
           "load_average_at_start":
               open("/proc/loadavg").read().split()[:3],
           "threads": 2, "contenders": {}}
    for name, rs in rates.items():
        med = statistics.median(rs)
        out["contenders"][name] = {
            "rates_hs": [round(r) for r in rs],
            "median_hs": round(med), "min_hs": round(min(rs)),
            "max_hs": round(max(rs)),
            "spread_pct": round(100.0 * (max(rs) - min(rs)) / med, 1)}
        print(name, out["contenders"][name], flush=True)
    out["load_average_at_end"] = \
        open("/proc/loadavg").read().split()[:3]
    with open(os.path.join(HERE, "exp007_confirm.json"), "w") as fh:
        json.dump(out, fh, indent=2)
    print("wrote exp007_confirm.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
