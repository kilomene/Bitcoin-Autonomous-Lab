#!/usr/bin/env python3
"""EXP-009 follow-up measurements.

B/E redo: the first pass used the mainnet payout address
against the regtest node, whose validateaddress rejects it
(HRP mismatch). The redo takes a regtest address from the
node's own wallet, so build_candidate runs end to end
against real RPC round trips.

C redo: the median-based linear fit in the first pass was
not credible under this VM's contention (single spikes move
small-span medians by multiples). The redo uses minimum
times over 7 repeats per span size (the standard
contention-resistant statistic on a shared host) and
derives per-call overhead as min_time(small) minus the
hashing time the large-span minimum implies. Labelled
best-case: it bounds overhead from below, it does not
average it.
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
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "research/sha256d/experiments"))
from bench_harness import load_lib, run_batch, GENESIS, DIFF1_LE  # noqa: E402


def part_b_e(data):
    from node.rpc_client import BitcoinRPC
    from mining.engine import MiningEngine
    rpc = BitcoinRPC(timeout=15, retries=1)
    if "bal-regtest" not in rpc.call("listwallets"):
        try:
            rpc.call("loadwallet", "bal-regtest")
        except Exception:
            rpc.call("createwallet", "bal-regtest")
    w = BitcoinRPC(timeout=15, retries=1, wallet="bal-regtest")
    addr = w.call("getnewaddress")
    tpl = rpc.call("getblocktemplate", {"rules": ["segwit"]})
    times = []
    for _ in range(20):
        t0 = time.perf_counter()
        rpc.call("getblocktemplate", {"rules": ["segwit"]})
        times.append((time.perf_counter() - t0) * 1e3)
    eng = MiningEngine(rpc, addr)
    bt = []
    for en in range(10):
        t0 = time.perf_counter()
        eng.build_candidate(tpl, en)
        bt.append((time.perf_counter() - t0) * 1e3)
    va = []
    for _ in range(20):
        t0 = time.perf_counter()
        rpc.call("validateaddress", addr)
        va.append((time.perf_counter() - t0) * 1e3)
    data["B_build_candidate_real_rpc"] = {
        "node_txs_in_template": len(tpl.get("transactions", [])),
        "median_ms_per_call": round(statistics.median(bt), 3),
        "min_ms_per_call": round(min(bt), 3)}
    data["E_gbt_intake_real_rpc"] = {
        "median_ms": round(statistics.median(times), 2),
        "min_ms": round(min(times), 2),
        "validateaddress_median_ms": round(statistics.median(va), 3)}
    print("B/E redo", data["B_build_candidate_real_rpc"],
          data["E_gbt_intake_real_rpc"], flush=True)


def bind_mode(lib):
    fn = lib.bal_m_batch2m
    fn.restype = ctypes.c_int
    fn.argtypes = [ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
                   ctypes.c_uint, ctypes.c_int, ctypes.c_int,
                   ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
                   ctypes.POINTER(ctypes.c_uint64)]
    return fn


def bind_std(lib, name):
    fn = getattr(lib, name)
    fn.restype = ctypes.c_int
    fn.argtypes = [ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
                   ctypes.c_uint, ctypes.c_char_p, ctypes.c_char_p,
                   ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint64)]
    return fn


def bind_v(lib):
    fn = lib.bal_v_batch2
    fn.restype = ctypes.c_int
    fn.argtypes = [ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
                   ctypes.c_uint, ctypes.c_char_p, ctypes.c_char_p,
                   ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint64),
                   ctypes.POINTER(ctypes.c_uint64)]
    return fn


def part_c2(data):
    _c, c_b2, _s = load_lib(f"{ROOT}/.local/cpu/libbal_batch.so",
                            "bal_c")
    geo = ctypes.CDLL(os.path.join(SRC, "libbal_geo.so"))
    geo_b = bind_mode(geo)
    v5 = ctypes.CDLL(os.path.join(SRC, "libbal_v512.so"))
    v5_b = bind_v(v5)

    def prod(n, t):
        _rc, _att, dt, _r = run_batch(c_b2, GENESIS, DIFF1_LE, 0,
                                      n, t)
        return dt

    def geo4(n, t):
        h = ctypes.create_string_buffer(32 * n)
        f = ctypes.create_string_buffer(n)
        a = ctypes.c_uint64(0)
        t0 = time.perf_counter()
        rc = geo_b(GENESIS, 0, n, t, 4, 0, DIFF1_LE, h, f,
                   ctypes.byref(a))
        dt = time.perf_counter() - t0
        assert rc == 0 and a.value == n
        return dt

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
        return dt

    sizes = [4096, 16384, 65536, 262144, 1048576, 4194304]
    res = {}
    for name, fn in (("production_c", prod), ("geo_s4", geo4),
                     ("avx512_mb16", v512)):
        mins = {}
        for n in sizes:
            dts = [fn(n, 2) for _ in range(7)]
            mins[n] = min(dts)
        big = sizes[-1]
        rate = big / mins[big]
        overhead_s = mins[sizes[0]] - sizes[0] / rate
        entry = {
            "min_time_rates_hs": {str(n): round(n / mins[n])
                                  for n in sizes},
            "large_span_rate_hs": round(rate),
            "per_call_overhead_us_best_case":
                round(max(overhead_s, 0.0) * 1e6, 2)}
        for span, label in ((65536, "engine_batch_65536"),
                            (int(rate), "one_second_span")):
            t_span = span / rate
            entry[f"overhead_pct_at_{label}"] = round(
                100 * max(overhead_s, 0.0) /
                (max(overhead_s, 0.0) + t_span), 3)
            entry[f"span_for_{label}"] = span
        res[name] = entry
        print("C2", name, entry, flush=True)
    data["C2_span_interaction_min_based"] = res


def main():
    with open(os.path.join(HERE, "exp009_pipeline.json")) as fh:
        data = json.load(fh)
    part_b_e(data)
    part_c2(data)
    data["load_average_at_fix"] = \
        open("/proc/loadavg").read().split()[:3]
    with open(os.path.join(HERE, "exp009_pipeline.json"), "w") as fh:
        json.dump(data, fh, indent=2)
    print("updated exp009_pipeline.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
