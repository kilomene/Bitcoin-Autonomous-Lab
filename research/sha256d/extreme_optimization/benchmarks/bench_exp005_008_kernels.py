#!/usr/bin/env python3
"""Combined kernel benchmark for EXP-005, EXP-006, EXP-007
and EXP-008. One session, round-robin interleaved, so every
contender sees the same contention drift. Batch runs of 1M
hashes on the genesis header; attempted == count asserted
for every run (for the AVX-512 kernel backend == count too,
since 1M is a whole number of 16-lane groups).

Contenders:
  production_c     trusted baseline (.local/cpu bal_c)
  geo_s{1,2,3,4,6}_blocked, geo_s4_strided   EXP-005
  hsf_s{2,3,4}     EXP-006 schedule-first
  phase_pipe       EXP-008 cross-nonce phase pipeline
  avx512_mb16      EXP-007 AVX-512 multi-buffer

Rates are actual counted attempts per second. Spreads on
this VM are part of the result.
"""
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
ROUNDS = 5


def bind_std(lib, name):
    fn = getattr(lib, name)
    fn.restype = ctypes.c_int
    fn.argtypes = [ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
                   ctypes.c_uint, ctypes.c_char_p, ctypes.c_char_p,
                   ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint64)]
    return fn


def bind_mode(lib):
    fn = lib.bal_m_batch2m
    fn.restype = ctypes.c_int
    fn.argtypes = [ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
                   ctypes.c_uint, ctypes.c_int, ctypes.c_int,
                   ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
                   ctypes.POINTER(ctypes.c_uint64)]
    return fn


def bind_v(lib):
    fn = lib.bal_v_batch2
    fn.restype = ctypes.c_int
    fn.argtypes = [ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
                   ctypes.c_uint, ctypes.c_char_p, ctypes.c_char_p,
                   ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint64),
                   ctypes.POINTER(ctypes.c_uint64)]
    return fn


def timed(fn, *args):
    t0 = time.perf_counter()
    out = fn(*args)
    return time.perf_counter() - t0, out


def main():
    _c, c_b2, _s = load_lib(f"{ROOT}/.local/cpu/libbal_batch.so",
                            "bal_c")
    geo = ctypes.CDLL(os.path.join(SRC, "libbal_geo.so"))
    geo_b = bind_mode(geo)
    hsf = ctypes.CDLL(os.path.join(SRC, "libbal_hsf.so"))
    hsf_b = bind_mode(hsf)
    pha = ctypes.CDLL(os.path.join(SRC, "libbal_phase.so"))
    pha_b = bind_std(pha, "bal_p_batch2")
    v5 = ctypes.CDLL(os.path.join(SRC, "libbal_v512.so"))
    v5_b = bind_v(v5)

    def prod(n, t):
        rc, att, dt, _r = run_batch(c_b2, GENESIS, DIFF1_LE, 0, n, t)
        assert rc == 0 and att == n, (rc, att)
        return n / dt

    def mk_mode(fn, streams, mode):
        def run(n, t):
            h = ctypes.create_string_buffer(32 * n)
            f = ctypes.create_string_buffer(n)
            a = ctypes.c_uint64(0)
            dt, rc = timed(fn, GENESIS, 0, n, t, streams, mode,
                           DIFF1_LE, h, f, ctypes.byref(a))
            assert rc == 0 and a.value == n, (rc, a.value)
            return n / dt
        return run

    def phase(n, t):
        h = ctypes.create_string_buffer(32 * n)
        f = ctypes.create_string_buffer(n)
        a = ctypes.c_uint64(0)
        dt, rc = timed(pha_b, GENESIS, 0, n, t, DIFF1_LE, h, f,
                       ctypes.byref(a))
        assert rc == 0 and a.value == n, (rc, a.value)
        return n / dt

    def v512(n, t):
        h = ctypes.create_string_buffer(32 * n)
        f = ctypes.create_string_buffer(n)
        a = ctypes.c_uint64(0)
        b = ctypes.c_uint64(0)
        dt, rc = timed(v5_b, GENESIS, 0, n, t, DIFF1_LE, h, f,
                       ctypes.byref(a), ctypes.byref(b))
        assert rc == 0 and a.value == n and b.value == n, \
            (rc, a.value, b.value)
        return n / dt

    contenders = [("production_c", prod)]
    for s in (1, 2, 3, 4, 6):
        contenders.append((f"geo_s{s}_blocked", mk_mode(geo_b, s, 0)))
    contenders.append(("geo_s4_strided", mk_mode(geo_b, 4, 1)))
    contenders.append(("geo_s3_strided", mk_mode(geo_b, 3, 1)))
    for s in (2, 3, 4):
        contenders.append((f"hsf_s{s}", mk_mode(hsf_b, s, 0)))
    contenders.append(("phase_pipe", phase))
    contenders.append(("avx512_mb16", v512))

    out = {"experiment": "EXP-005/006/007/008 combined kernel bench",
           "load_average_at_start":
               open("/proc/loadavg").read().split()[:3],
           "design": f"round-robin interleaved, {ROUNDS} rounds x 1M",
           "threads": {}}
    for threads in (1, 2):
        rates = {name: [] for name, _f in contenders}
        for rep in range(ROUNDS):
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
            print(f"t={threads} {name}", entry[name], flush=True)
        out["threads"][str(threads)] = entry
    out["load_average_at_end"] = \
        open("/proc/loadavg").read().split()[:3]
    with open(os.path.join(HERE, "exp005_008_kernels.json"),
              "w") as fh:
        json.dump(out, fh, indent=2)
    print("wrote exp005_008_kernels.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
