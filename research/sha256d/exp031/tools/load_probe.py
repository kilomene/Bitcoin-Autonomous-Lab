#!/usr/bin/env python3
"""EXP-031 resource-characterisation load probe.

Runs a fixed SHA-256d workload through the production
ComputeEngine (gpu/engine.py, backend selected exactly as in
production) at 1, 2 and 4 threads, strictly sequentially, and
records for each configuration:

- wall-clock seconds and the engine's own attempted count, so
  the rate is actual work over wall time, never requested work;
- /proc/stat deltas over the same window (busy percent and
  steal percent), so host contention during the run is part
  of the record, not a hidden variable;
- the scaling ratios and the effective-CPU estimate
  (aggregate rate divided by the 1-thread rate).

Conditions are part of the measurement: the live miner, the
node and the autopilot keep running throughout (this tool
never touches them), so every rate here is a rate achievable
ALONGSIDE the production load on this shared VM, not an
idle-machine figure. The fixed range uses target 1, which a
real digest meets with probability about 2^-256, so the scan
covers the full range; the returned attempted count is the
authority either way.

Usage:
    python3 load_probe.py [--range 16777216] [--out PATH]
"""
import argparse
import json
import os
import sys
import time

REPO_ROOT = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "..", ".."))
sys.path.insert(0, REPO_ROOT)


def read_stat():
    cpus = {}
    with open("/proc/stat") as fh:
        for line in fh:
            parts = line.split()
            if parts and parts[0] == "cpu":
                vals = [int(x) for x in parts[1:11]]
                keys = ("user", "nice", "system", "idle",
                        "iowait", "irq", "softirq", "steal",
                        "guest", "guest_nice")
                cpus = dict(zip(keys, vals))
    return cpus


def stat_delta(before, after):
    deltas = {k: after[k] - before[k] for k in before}
    total = sum(deltas.values())
    if total <= 0:
        return {"total_jiffies": total}
    out = {k: round(100.0 * v / total, 2)
           for k, v in deltas.items()}
    out["busy_percent"] = round(
        100.0 * (total - deltas["idle"] - deltas["iowait"])
        / total, 2)
    out["steal_percent"] = out["steal"]
    return out


def main():
    parser = argparse.ArgumentParser(
        description="EXP-031 sequential load probe")
    parser.add_argument("--range", type=int, default=1 << 24,
                        help="fixed nonce range per configuration")
    parser.add_argument("--threads", default="1,2,4",
                        help="comma-separated thread counts, "
                             "run in the given order")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    import gpu.engine as engine_mod
    from gpu.engine import ComputeEngine

    heartbeat_path = os.path.join(
        REPO_ROOT, ".local", "heartbeat.json")
    heartbeat = None
    if os.path.exists(heartbeat_path):
        try:
            with open(heartbeat_path) as fh:
                heartbeat = json.load(fh)
        except (OSError, ValueError):
            heartbeat = None

    engine = ComputeEngine()
    header = bytes(range(80))
    target = 1  # full scan in practice; attempted is authority

    configs = []
    for threads in [int(x) for x in args.threads.split(",")]:
        engine.c_threads = threads
        engine.c_threads_tuned = True
        time.sleep(1.0)  # settle between configurations
        before = read_stat()
        wall0 = time.perf_counter()
        hit, attempted, seconds = engine.search_first_counted(
            header, target, 0, args.range)
        wall = time.perf_counter() - wall0
        after = read_stat()
        configs.append({
            "threads": threads,
            "range": args.range,
            "hit": None if hit is None else hit[0],
            "attempted": attempted,
            "engine_seconds": round(seconds, 4),
            "wall_seconds": round(wall, 4),
            "hashrate_attempted_over_wall":
                round(attempted / wall, 1) if wall > 0 else None,
            "stat_during_run": stat_delta(before, after),
            "last_search_stats": {
                k: engine.last_search_stats.get(k)
                for k in ("backend", "threads",
                          "backend_hashes", "unique_coverage")
                if engine.last_search_stats},
        })
        print(f"threads={threads} attempted={attempted} "
              f"wall={wall:.2f}s rate="
              f"{attempted / wall:,.0f} H/s", flush=True)

    rates = {c["threads"]: c["hashrate_attempted_over_wall"]
             for c in configs}
    base = rates.get(1)
    scaling = {}
    effective = {}
    if base:
        for n, rate in rates.items():
            scaling[str(n)] = round(rate / base, 3)
            effective[str(n)] = round(rate / base, 3)

    report = {
        "tool": "exp031/load_probe.py",
        "generated_utc": time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "conditions": (
            "live miner, node and autopilot running "
            "concurrently and untouched; all rates are "
            "alongside-production-load rates on a shared, "
            "contended VM, not idle-machine figures"),
        "heartbeat_at_start": heartbeat,
        "engine_describe": engine.describe(),
        "range_per_config": args.range,
        "configurations": configs,
        "scaling_vs_1_thread": scaling,
        "effective_cpus_estimate": {
            "definition": "aggregate rate at N threads divided "
                          "by the 1-thread rate, same window "
                          "conditions",
            "values": effective,
            "evidence": "estimated (derived from measured "
                        "rates under contention); not a "
                        "hardware property",
        },
    }
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.out:
        with open(args.out, "w") as fh:
            fh.write(text + "\n")
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
