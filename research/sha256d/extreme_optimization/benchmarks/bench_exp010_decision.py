#!/usr/bin/env python3
"""EXP-010 (Part A): decision closure, executed on the
owner's immediate order during mainnet initial block
download.

PREDECLARED VERDICT RULE (unchanged from EXP-004 and from
the armed watcher protocol, stated before this run): a
candidate passes only if, at 2 worker threads in this
round-robin interleaved session, its MINIMUM round rate
exceeds production C's MAXIMUM round rate (complete
separation, beyond spread). Any weaker separation, however
consistent the medians, does not integrate.

Method: one session, 2 worker threads, round-robin
interleaved across three contenders (production C, H-01
streams=4 strided, AVX-512 multi-buffer), 15 rounds of 1M
hashes each. attempted == count asserted per run. Every
individual run records the 1-minute load average at its
start and the aggregate CPU steal share of its own window
(/proc/stat deltas), so the AVX-512 variance question can
be answered from per-round data: do the multi-buffer
kernel's slow rounds coincide with steal or load spikes
(environmental), or do they also occur in calm rounds
(implementation behaviour)? Production C is carried
through the same analysis as a control.

Context: the owner ordered immediate execution ("Finish
it up now asap"), overriding the earlier wait-for-sync
condition. The mainnet node is still in initial block
download and the live pool miner is running; that
contention is part of the recorded result, not a caveat
added afterwards.

Statistics: median, min, max, spread, and a 95 percent
confidence interval for each median by percentile
bootstrap (10,000 resamples, seeded).
"""
import ctypes
import json
import os
import random
import statistics
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
EO = os.path.dirname(HERE)
SRC = os.path.join(EO, "src")
ROOT = "/home/hatch/workspace/bitcoin-autonomous-lab"
sys.path.insert(0, os.path.join(ROOT, "research/sha256d/experiments"))
from bench_harness import load_lib, run_batch, GENESIS, DIFF1_LE  # noqa: E402

COUNT = 1_000_000
ROUNDS = 15
THREADS = 2


def steal_snapshot():
    with open("/proc/stat") as fh:
        parts = fh.readline().split()[1:]
    vals = [int(x) for x in parts]
    return sum(vals), vals[7]  # total jiffies, steal jiffies


def load1():
    with open("/proc/loadavg") as fh:
        return float(fh.read().split()[0])


def node_state():
    cli = os.path.join(ROOT, "..", "bitcoin-core-dist",
                       "bitcoin-core-28.1", "bin", "bitcoin-cli")
    cli = os.path.normpath(cli)
    try:
        out = subprocess.run(
            [cli, f"-datadir={ROOT}/.local/mainnet",
             "-rpcclienttimeout=60", "getblockchaininfo"],
            capture_output=True, text=True, timeout=120)
        d = json.loads(out.stdout)
        return {"blocks": d["blocks"], "headers": d["headers"],
                "initialblockdownload": d["initialblockdownload"],
                "verificationprogress":
                    round(d["verificationprogress"], 4)}
    except Exception as exc:  # RPC slow under contention
        return {"error": f"{type(exc).__name__}: {exc}"}


def bind_geo(lib):
    fn = lib.bal_m_batch2m
    fn.restype = ctypes.c_int
    fn.argtypes = [ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
                   ctypes.c_uint, ctypes.c_int, ctypes.c_int,
                   ctypes.c_char_p, ctypes.c_char_p,
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


def bootstrap_median_ci(rates, seed=1010, resamples=10000):
    rng = random.Random(seed)
    n = len(rates)
    meds = []
    for _ in range(resamples):
        sample = [rates[rng.randrange(n)] for _ in range(n)]
        meds.append(statistics.median(sample))
    meds.sort()
    lo = meds[int(0.025 * resamples)]
    hi = meds[int(0.975 * resamples) - 1]
    return round(lo), round(hi)


def pearson(xs, ys):
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return 0.0
    return sxy / (sxx * syy) ** 0.5


def variance_analysis(obs):
    """obs: list of per-run dicts for one contender."""
    rates = [o["rate_hs"] for o in obs]
    steals = [o["steal_pct"] for o in obs]
    loads = [o["load1_at_start"] for o in obs]
    med_steal = statistics.median(steals)
    calm = [o["rate_hs"] for o in obs if o["steal_pct"] <= med_steal]
    spiked = [o["rate_hs"] for o in obs if o["steal_pct"] > med_steal]
    med_rate = statistics.median(rates)
    slow = [o for o in obs if o["rate_hs"] < 0.8 * med_rate]
    slow_spiked = sum(1 for o in slow if o["steal_pct"] > med_steal)
    return {
        "corr_rate_vs_steal": round(pearson(rates, steals), 3),
        "corr_rate_vs_load1": round(pearson(rates, loads), 3),
        "median_steal_pct": round(med_steal, 3),
        "calm_rounds": len(calm),
        "calm_median_hs": round(statistics.median(calm)) if calm else None,
        "spiked_rounds": len(spiked),
        "spiked_median_hs": round(statistics.median(spiked)) if spiked else None,
        "slow_rounds_below_80pct_of_median": len(slow),
        "slow_rounds_with_above_median_steal": slow_spiked,
    }


def main():
    _c, c_b2, _s = load_lib(f"{ROOT}/.local/cpu/libbal_batch.so",
                            "bal_c")
    geo = ctypes.CDLL(os.path.join(SRC, "libbal_geo.so"))
    geo_b = bind_geo(geo)
    v5 = ctypes.CDLL(os.path.join(SRC, "libbal_v512.so"))
    v5_b = bind_v(v5)

    def prod(n, t):
        rc, att, dt, _r = run_batch(c_b2, GENESIS, DIFF1_LE, 0, n, t)
        assert rc == 0 and att == n, (rc, att)
        return n / dt

    def geo4(n, t):
        h = ctypes.create_string_buffer(32 * n)
        f = ctypes.create_string_buffer(n)
        a = ctypes.c_uint64(0)
        t0 = time.perf_counter()
        rc = geo_b(GENESIS, 0, n, t, 4, 1, DIFF1_LE, h, f,
                   ctypes.byref(a))
        dt = time.perf_counter() - t0
        assert rc == 0 and a.value == n, (rc, a.value)
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
        assert rc == 0 and a.value == n and b.value == n, \
            (rc, a.value, b.value)
        return n / dt

    contenders = [("production_c", prod),
                  ("geo_s4_strided", geo4),
                  ("avx512_mb16", v512)]

    out = {"experiment": "EXP-010 Part A decision closure",
           "execution_context": (
               "Executed on the owner's immediate order during "
               "mainnet initial block download; the wait-for-sync "
               "condition was overridden by the owner. Contention "
               "from the syncing node and the live pool miner is "
               "part of the recorded result."),
           "predeclared_rule": ("candidate min > production max at "
                                "2 threads (complete separation)"),
           "design": (f"round-robin interleaved, {ROUNDS} rounds "
                      f"x 1M, {THREADS} threads, one session"),
           "node_at_start": node_state(),
           "load_average_at_start":
               open("/proc/loadavg").read().split()[:3],
           "observations": {name: [] for name, _f in contenders}}

    tot_s, st_s = steal_snapshot()
    for rep in range(ROUNDS):
        order = contenders[rep % len(contenders):] \
            + contenders[:rep % len(contenders)]
        for name, fn in order:
            ld = load1()
            tot0, st0 = steal_snapshot()
            rate = fn(COUNT, THREADS)
            tot1, st1 = steal_snapshot()
            steal_pct = 100.0 * (st1 - st0) / max(tot1 - tot0, 1)
            out["observations"][name].append({
                "round": rep,
                "rate_hs": round(rate),
                "load1_at_start": ld,
                "steal_pct": round(steal_pct, 3)})
            print(f"round {rep} {name} {round(rate)} "
                  f"load1={ld} steal={steal_pct:.2f}%",
                  flush=True)
    tot_e, st_e = steal_snapshot()
    out["session_steal_pct"] = round(
        100.0 * (st_e - st_s) / max(tot_e - tot_s, 1), 2)
    out["load_average_at_end"] = \
        open("/proc/loadavg").read().split()[:3]
    out["node_at_end"] = node_state()

    stats = {}
    for name, obs in out["observations"].items():
        rates = [o["rate_hs"] for o in obs]
        med = statistics.median(rates)
        lo, hi = bootstrap_median_ci(rates)
        stats[name] = {
            "median_hs": round(med),
            "median_ci95_hs": [lo, hi],
            "min_hs": round(min(rates)),
            "max_hs": round(max(rates)),
            "spread_pct": round(
                100.0 * (max(rates) - min(rates)) / med, 1)}
        print(name, stats[name], flush=True)
    out["stats"] = stats

    pmax = stats["production_c"]["max_hs"]
    verdict = {}
    for cand in ("geo_s4_strided", "avx512_mb16"):
        passed = stats[cand]["min_hs"] > pmax
        verdict[cand] = {
            "criterion": "candidate_min > production_max",
            "candidate_min_hs": stats[cand]["min_hs"],
            "production_max_hs": pmax,
            "passed": passed}
    out["verdict"] = verdict
    out["variance_analysis"] = {
        name: variance_analysis(obs)
        for name, obs in out["observations"].items()}
    print("VERDICT", verdict, flush=True)
    print("VARIANCE", json.dumps(out["variance_analysis"], indent=2),
          flush=True)
    with open(os.path.join(HERE, "exp010_partA_decision.json"),
              "w") as fh:
        json.dump(out, fh, indent=2)
    print("wrote exp010_partA_decision.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
