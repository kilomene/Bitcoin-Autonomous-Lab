#!/usr/bin/env python3
"""EXP-009: pipeline and interaction study (measurement only).

Quantifies the end-to-end mining path around the kernels:

A. Candidate construction (X-059 measured, not cited):
   MiningEngine.build_candidate timed against a counting
   stub RPC (zero network latency: isolates the Python work,
   including the per-transaction txid/wtxid re-verification)
   at 0, 10, 100 and 500 template transactions, with the
   stub's RPC call counts per invocation recorded. The
   mine_cycle extranonce loop calls build_candidate up to
   64 times per template; the per-template worst case is
   derived from the per-call numbers.
B. Real-RPC delta: the same call against the repo's regtest
   node when it is running (validateaddress and
   getblockchaininfo become real round trips).
C. Span-size interaction: effective rate of production C,
   geo streams=4 and the phase pipeline at span sizes from
   4,096 to 4,194,304 nonces (2 threads), plus a linear fit
   time = fixed_overhead + count / asymptotic_rate. The
   production live paths size spans two ways: MiningEngine
   batches at a fixed 65,536, and mainnet_live sizes scan
   chunks to about one second of the probe rate (2^20 to
   2^24). Overhead percentages are reported at both sizings
   for each kernel.
D. Candidate confirmation cost: hashlib double-SHA-256
   recomputation per candidate (the confirmation the live
   runner performs), as microseconds per candidate and as a
   share of throughput at regtest-density candidate rates.
E. Template intake: getblocktemplate round trip against
   the regtest node when available.
F. Live-shaped wall-time split: a real MiningEngine
   mine_cycle against the stub RPC (hard target, fixed
   batch budget), with build_candidate and search wrapped
   in timers, giving the engine-side split for the
   production backend. The research kernels are not wired
   into ComputeEngine (EXP-004 gate), so their split is
   reported from part C, not simulated inside the engine.
"""
import ctypes
import hashlib
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

from mining.engine import MiningEngine, txid_of  # noqa: E402
from mining.pow import coinbase_subsidy  # noqa: E402
from bench_harness import load_lib, run_batch, GENESIS, DIFF1_LE  # noqa: E402

OUT = {"experiment": "EXP-009 pipeline and interaction study",
       "load_average_at_start":
           open("/proc/loadavg").read().split()[:3]}

PAYOUT = "bc1q528egeqsvv8aa382j43edxskqw6x7zxc2xpcf3"
SPK = "0014" + "11" * 20  # stub scriptPubKey (form only)


class StubRPC:
    """Zero-latency counting RPC for construction timing."""

    def __init__(self, template):
        self.template = template
        self.counts = {}

    def call(self, method, *args):
        self.counts[method] = self.counts.get(method, 0) + 1
        if method == "getblocktemplate":
            return self.template
        if method == "validateaddress":
            return {"isvalid": True, "scriptPubKey": SPK}
        if method == "getblockchaininfo":
            return {"chain": "regtest"}
        if method == "submitblock":
            return None
        raise ValueError(method)

    def get_blockchain_info(self):
        return self.call("getblockchaininfo")

    def get_best_block_hash(self):
        return "00" * 32

    def with_timeout(self, _t):
        return self


def synth_template(ntx):
    """A structurally valid GBT-shaped template whose tx
    entries pass build_candidate's txid re-verification."""
    raw_tx = bytes.fromhex(
        "01000000" + "01" + "00" * 32 + "ffffffff" + "00"
        + "ffffffff" + "01" + "00e1f50500000000" + "00"
        + "00000000")
    txid_hex = txid_of(raw_tx)[::-1].hex()
    height = 1000
    subsidy = coinbase_subsidy(height, 150)
    fee = 1000
    template = {
        "version": 0x20000000,
        "previousblockhash": "00" * 32,
        "transactions": [
            {"txid": txid_hex, "data": raw_tx.hex(), "fee": fee}
            for _ in range(ntx)],
        "coinbaseaux": {"flags": ""},
        "coinbasevalue": subsidy + fee * ntx,
        "target": "7fffff0000000000000000000000000000000000000000"
                  "000000000000000000",
        "mintime": 1, "curtime": 1700000000,
        "bits": "207fffff", "height": height,
    }
    return template


def part_a():
    res = {}
    for ntx in (0, 10, 100, 500):
        stub = StubRPC(synth_template(ntx))
        eng = MiningEngine(stub, PAYOUT)
        times = []
        for en in range(20):
            t0 = time.perf_counter()
            eng.build_candidate(stub.template, en)
            times.append(time.perf_counter() - t0)
        med = statistics.median(times)
        res[f"txs_{ntx}"] = {
            "median_ms_per_call": round(med * 1e3, 3),
            "min_ms": round(min(times) * 1e3, 3),
            "max_ms": round(max(times) * 1e3, 3),
            "rpc_counts_per_20_calls": dict(stub.counts),
            "per_template_64_extranonce_ms": round(med * 64 * 1e3, 1)}
        print("A", ntx, res[f"txs_{ntx}"], flush=True)
    OUT["A_build_candidate_stub"] = res


def part_b_e():
    try:
        from node.rpc_client import BitcoinRPC
        rpc = BitcoinRPC(timeout=10, retries=1)
        t0 = time.perf_counter()
        tpl = rpc.call("getblocktemplate", {"rules": ["segwit"]})
        gbt_ms = (time.perf_counter() - t0) * 1e3
        times = []
        for _ in range(20):
            t0 = time.perf_counter()
            rpc.call("getblocktemplate", {"rules": ["segwit"]})
            times.append((time.perf_counter() - t0) * 1e3)
        eng = MiningEngine(rpc, PAYOUT)
        bt = []
        for en in range(10):
            t0 = time.perf_counter()
            eng.build_candidate(tpl, en)
            bt.append((time.perf_counter() - t0) * 1e3)
        OUT["B_build_candidate_real_rpc"] = {
            "node_txs_in_template": len(tpl.get("transactions", [])),
            "median_ms_per_call": round(statistics.median(bt), 3)}
        OUT["E_gbt_intake_real_rpc"] = {
            "first_call_ms": round(gbt_ms, 2),
            "median_ms": round(statistics.median(times), 2)}
        print("B/E real rpc", OUT["B_build_candidate_real_rpc"],
              OUT["E_gbt_intake_real_rpc"], flush=True)
    except Exception as exc:  # node down: record, do not fake
        OUT["B_build_candidate_real_rpc"] = {
            "status": f"regtest node unavailable: {exc!r}"}
        OUT["E_gbt_intake_real_rpc"] = {
            "status": "regtest node unavailable"}
        print("B/E unavailable:", exc, flush=True)


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


def part_c():
    _c, c_b2, _s = load_lib(f"{ROOT}/.local/cpu/libbal_batch.so",
                            "bal_c")
    geo = ctypes.CDLL(os.path.join(SRC, "libbal_geo.so"))
    geo_b = bind_mode(geo)
    pha = ctypes.CDLL(os.path.join(SRC, "libbal_phase.so"))
    pha_b = bind_std(pha, "bal_p_batch2")

    def prod(n, t):
        rc, att, dt, _r = run_batch(c_b2, GENESIS, DIFF1_LE, 0, n, t)
        assert rc == 0 and att == n
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

    def phase(n, t):
        h = ctypes.create_string_buffer(32 * n)
        f = ctypes.create_string_buffer(n)
        a = ctypes.c_uint64(0)
        t0 = time.perf_counter()
        rc = pha_b(GENESIS, 0, n, t, DIFF1_LE, h, f,
                   ctypes.byref(a))
        dt = time.perf_counter() - t0
        assert rc == 0 and a.value == n
        return dt

    sizes = [4096, 16384, 65536, 262144, 1048576, 4194304]
    res = {}
    for name, fn in (("production_c", prod), ("geo_s4", geo4),
                     ("phase_pipe", phase)):
        pts = []
        for n in sizes:
            dts = sorted(fn(n, 2) for _ in range(3))
            pts.append((n, dts[1]))
        # least squares fit dt = overhead + n / rate
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        mx = sum(xs) / len(xs)
        my = sum(ys) / len(ys)
        slope = sum((x - mx) * (y - my) for x, y in pts) / \
            sum((x - mx) ** 2 for x in xs)
        intercept = my - slope * mx
        rate = 1.0 / slope if slope > 0 else 0.0
        entry = {
            "median_rates_hs": {
                str(n): round(n / dt) for n, dt in pts},
            "fit_fixed_overhead_us": round(intercept * 1e6, 2),
            "fit_asymptotic_rate_hs": round(rate),
        }
        for span, label in ((65536, "engine_batch_65536"),
                            (None, "one_second_span")):
            s = span if span else max(int(rate), 1)
            overhead = intercept / (intercept + s / rate) * 100 \
                if rate > 0 else None
            entry[f"overhead_pct_at_{label}"] = \
                round(overhead, 4) if overhead is not None else None
            entry[f"span_for_{label}"] = s
        res[name] = entry
        print("C", name, entry, flush=True)
    OUT["C_span_interaction"] = res


def part_d():
    times = []
    hdr = GENESIS[:76] + (12345).to_bytes(4, "little")
    for _ in range(20000):
        t0 = time.perf_counter()
        hashlib.sha256(hashlib.sha256(hdr).digest()).digest()
        times.append(time.perf_counter() - t0)
    med = statistics.median(times)
    OUT["D_candidate_confirmation"] = {
        "median_us_per_candidate_hashlib": round(med * 1e6, 2),
        "note": ("at a regtest-easy target (2^248) about one "
                 "candidate per 256 hashes reaches confirmation; "
                 "share = candidates_per_second x cost, computed "
                 "in the report from measured kernel rates")}
    print("D", OUT["D_candidate_confirmation"], flush=True)


def part_f():
    stub = StubRPC(synth_template(0))
    # Hard target: no hit, the cycle spends its batch budget.
    stub.template["target"] = "00000001" + "00" * 28
    eng = MiningEngine(stub, PAYOUT, batch_size=65536)
    timers = {"build_s": 0.0, "search_s": 0.0}
    orig_build = eng.build_candidate
    orig_search = eng.compute.search_first_counted

    def timed_build(template, extranonce_int=0):
        t0 = time.perf_counter()
        out = orig_build(template, extranonce_int)
        timers["build_s"] += time.perf_counter() - t0
        return out

    def timed_search(header, target, start, count):
        t0 = time.perf_counter()
        out = orig_search(header, target, start, count)
        timers["search_s"] += time.perf_counter() - t0
        return out

    eng.build_candidate = timed_build
    eng.compute.search_first_counted = timed_search
    t0 = time.perf_counter()
    result = eng.mine_cycle(max_batches=24, deadline_seconds=600)
    wall = time.perf_counter() - t0
    OUT["F_mine_cycle_split_stub"] = {
        "wall_s": round(wall, 3),
        "build_candidate_pct": round(
            100 * timers["build_s"] / wall, 3),
        "search_pct": round(100 * timers["search_s"] / wall, 3),
        "other_pct": round(
            100 * (wall - timers["build_s"] - timers["search_s"])
            / wall, 3),
        "cycle_result": {k: result.get(k) for k in
                         ("accepted", "reason", "hashes", "batches",
                          "backend")}}
    print("F", OUT["F_mine_cycle_split_stub"], flush=True)


def main():
    part_a()
    part_b_e()
    part_c()
    part_d()
    part_f()
    OUT["load_average_at_end"] = \
        open("/proc/loadavg").read().split()[:3]
    with open(os.path.join(HERE, "exp009_pipeline.json"), "w") as fh:
        json.dump(OUT, fh, indent=2)
    print("wrote exp009_pipeline.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
