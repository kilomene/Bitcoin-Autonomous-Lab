#!/usr/bin/env python3
"""Combined benchmark for EXP-011 to EXP-015. One session,
round-robin interleaved, batch runs of 1M hashes on the
genesis header, attempted == count asserted for every run
(backend == count as well for the 16-lane and 32-lane
kernels, since 1M is a whole number of groups).

Contenders:
  production_c    trusted baseline (.local/cpu bal_c)
  geo_s4_strided  EXP-005 champion SHA-NI geometry
  avx512_mb16     EXP-007 multi-buffer baseline
  mb2_dual        EXP-011 dual-batch interleaved MB
  mb_tern         EXP-012 explicit VPTERNLOGD MB
  mb_share        EXP-013 cross-lane sharing MB
  mb_kw           EXP-014 K+W folding MB
  bitslice32      EXP-015 bitsliced 32-lane

Rates are actual counted attempts per second. Session
conditions (load average, steal jiffies) are recorded in
the output JSON.
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


def steal_jiffies():
    with open("/proc/stat") as fh:
        for line in fh:
            if line.startswith("cpu "):
                return int(line.split()[8])
    return -1


def bind_std(lib, name):
    fn = getattr(lib, name)
    fn.restype = ctypes.c_int
    fn.argtypes = [ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
                   ctypes.c_uint, ctypes.c_char_p, ctypes.c_char_p,
                   ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint64),
                   ctypes.POINTER(ctypes.c_uint64)]
    return fn


def bind_mode(lib):
    fn = lib.bal_m_batch2m
    fn.restype = ctypes.c_int
    fn.argtypes = [ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
                   ctypes.c_uint, ctypes.c_int, ctypes.c_int,
                   ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
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

    def prod(n, t):
        rc, att, dt, _r = run_batch(c_b2, GENESIS, DIFF1_LE, 0, n, t)
        assert rc == 0 and att == n, (rc, att)
        return n / dt

    def geo_s4(n, t):
        h = ctypes.create_string_buffer(32 * n)
        f = ctypes.create_string_buffer(n)
        a = ctypes.c_uint64(0)
        dt, rc = timed(geo_b, GENESIS, 0, n, t, 4, 1,
                       DIFF1_LE, h, f, ctypes.byref(a))
        assert rc == 0 and a.value == n, (rc, a.value)
        return n / dt

    def mk(name, prefix):
        lib = ctypes.CDLL(os.path.join(SRC, name))
        fn = bind_std(lib, f"bal_{prefix}_batch2")

        def run(n, t):
            h = ctypes.create_string_buffer(32 * n)
            f = ctypes.create_string_buffer(n)
            a = ctypes.c_uint64(0)
            b = ctypes.c_uint64(0)
            dt, rc = timed(fn, GENESIS, 0, n, t, DIFF1_LE, h, f,
                           ctypes.byref(a), ctypes.byref(b))
            assert rc == 0 and a.value == n and b.value == n, \
                (rc, a.value, b.value)
            return n / dt
        return run

    contenders = [
        ("production_c", prod),
        ("geo_s4_strided", geo_s4),
        ("avx512_mb16", mk("libbal_v512.so", "v")),
        ("mb2_dual", mk("libbal_w512.so", "w")),
        ("mb_tern", mk("libbal_t512.so", "t")),
        ("mb_share", mk("libbal_x512.so", "x")),
        ("mb_kw", mk("libbal_k512.so", "k")),
        ("bitslice32", mk("libbal_zbs.so", "z")),
    ]
    only = sys.argv[1:] or None
    if only:
        contenders = [c for c in contenders if c[0] in only]

    out = {"experiment": "EXP-011..015 combined kernel bench",
           "load_average_at_start":
               open("/proc/loadavg").read().split()[:3],
           "steal_jiffies_at_start": steal_jiffies(),
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
    out["steal_jiffies_at_end"] = steal_jiffies()
    with open(os.path.join(HERE, "exp011_onward_kernels.json"),
              "w") as fh:
        json.dump(out, fh, indent=2)
    print("wrote exp011_onward_kernels.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
