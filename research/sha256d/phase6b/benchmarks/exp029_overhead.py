#!/usr/bin/env python3
"""EXP-029 coordination overhead, LOCAL PROTOTYPE ONLY.

In-process simulation on this one host: W worker threads
lease chunks from one RangeAllocator and actually
examine every nonce in their chunks with hashlib double
SHA-256 against a target no nonce meets (full scans, so
unique coverage is exact). The single-worker run over
the same range is the baseline. Aggregate efficiency is
unique coverage per second divided by the sum of the
per-worker rates measured in the same run's shape
(single-worker rate x W), stated in the record.

These numbers measure THIS prototype's allocator and
threading overhead on THIS contended guest. They are
not distributed-system results: no network, no second
machine, no sockets. Configurations not run carry no
numbers (EXP-029 criterion 2).
"""
import hashlib
import json
import os
import platform
import sys
import threading
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "exp029")
sys.path.insert(0, HERE)
from exp029_allocator import RangeAllocator  # noqa: E402

HEADER = bytes(range(80))


def examine(lo, hi):
    n = 0
    for nonce in range(lo, hi):
        h = bytearray(HEADER)
        h[76:80] = nonce.to_bytes(4, "little")
        hashlib.sha256(hashlib.sha256(bytes(h)).digest()).digest()
        n += 1
    return n


def run(workers, count, chunk):
    alloc = RangeAllocator("overhead", 0, count, chunk)
    per_worker = {f"w{i}": 0 for i in range(workers)}
    errors = []

    def body(name):
        try:
            while True:
                got = alloc.lease(name)
                if got is None:
                    if alloc.accounting()["complete"]:
                        return
                    time.sleep(0.001)
                    continue
                lo, hi = got
                per_worker[name] += examine(lo, hi)
                alloc.progress(name, lo, hi - lo)
                alloc.complete(name, lo)
        except Exception as exc:  # noqa: BLE001
            errors.append(repr(exc))

    threads = [threading.Thread(target=body, args=(f"w{i}",))
               for i in range(workers)]
    t0 = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    dt = time.perf_counter() - t0
    acc = alloc.accounting()
    assert not errors, errors
    assert acc["complete"] and acc["unique_coverage"] == count, acc
    assert sum(per_worker.values()) == count, per_worker
    return {"workers": workers, "count": count, "chunk": chunk,
            "seconds": dt, "unique_per_s": count / dt,
            "accounting": acc}


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    count = 120000
    base = run(1, count, 10000)
    runs = [base]
    for w in (2, 4):
        runs.append(run(w, count, 10000))
    fine = run(4, count, 1000)
    runs.append(fine)
    for r in runs:
        r["efficiency_vs_single"] = (
            r["unique_per_s"] / (base["unique_per_s"] * r["workers"]))
    record = {
        "experiment": "EXP-029",
        "kind": "coordination overhead, local in-process "
                "prototype only, NOT a distributed system",
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "host": {"model": platform.processor() or
                 "AMD EPYC 9D25 (see probe record)",
                 "machine": platform.machine(),
                 "vcpus": os.cpu_count(),
                 "note": "shared guest, about 1.5 effective "
                         "CPUs; live miner and node running"},
        "workload": "hashlib dsha256 full scans, target "
                    "unmeetable, exact coverage",
        "runs": runs,
        "reading": "Efficiency below 1 at 2 and 4 workers "
                   "is expected on this guest: the workers "
                   "oversubscribe about 1.5 effective CPUs, "
                   "so the figure prices thread contention "
                   "plus allocator overhead together and "
                   "cannot separate them. The allocator "
                   "itself is not the bottleneck claim "
                   "either way; a multi-machine efficiency "
                   "number is UNVERIFIED until run.",
        "verdict": "MEASURED (local prototype scope only)"}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(OUT_DIR, f"overhead_{stamp}.json")
    suffix = 2
    while os.path.exists(path):
        path = os.path.join(OUT_DIR, f"overhead_{stamp}_r{suffix}.json")
        suffix += 1
    with open(path, "x") as fh:
        json.dump(record, fh, indent=2)
    for r in runs:
        print(f"workers {r['workers']} chunk {r['chunk']}: "
              f"{r['unique_per_s']:.0f} unique/s, efficiency "
              f"{r['efficiency_vs_single']:.3f}")
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
