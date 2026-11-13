#!/usr/bin/env python3
"""Live mainnet pool mining with the lab's fast engine.

Owner ordered 2026-11-13: the lab must mine for real on mainnet
and be seen mining. This runner connects the phase-1 Stratum
client (public-pool.io) to the current ComputeEngine (C midstate
batch, early-exit search): real mainnet jobs, real hashes, shares
submitted at pool difficulty, evidence logged as JSONL plus a
human-readable status file (.local/mainnet-status.txt) refreshed
every few seconds.

Usage: python3 mining/mainnet_live.py --duration 3600
       [--address bc1q...] (defaults to the lab wallet)
"""

import argparse
import json
import os
import struct
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gpu.engine import ComputeEngine
from mining.stratum_client import StratumClient, Evidence, build_header

DEFAULT_ADDRESS = "bc1q528egeqsvv8aa382j43edxskqw6x7zxc2xpcf3"
ROOT = os.path.join(os.path.dirname(__file__), "..")
STATUS = os.path.join(ROOT, ".local", "mainnet-status.txt")


def difficulty_of(digest):
    v = int.from_bytes(digest, "little")
    return (1 << 256) / (v + 1) * (0xFFFF / (1 << 48)) if v else float("inf")


def target_for_difficulty(diff):
    base = 0xFFFF * (1 << 208)
    return int(base / diff)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--duration", type=int, default=3600)
    ap.add_argument("--address", default=DEFAULT_ADDRESS)
    ap.add_argument("--worker", default="bal1")
    ap.add_argument("--evidence", default="evidence/mainnet-live.jsonl")
    args = ap.parse_args()

    ev = Evidence(args.evidence)
    user = f"{args.address}.{args.worker}"
    client = StratumClient("public-pool.io", 21496, user, "x", ev)
    client.suggest_difficulty = 0.001  # pool clamps to its min: 1
    client.connect()
    threading.Thread(target=client.reader_loop, daemon=True).start()
    if not client.authorized.wait(timeout=30):
        print("authorization failed"); return 3
    print(f"authorized as {user}", flush=True)

    engine = ComputeEngine()
    deadline = time.time() + args.duration
    total_hashes = 0
    t_start = time.time()
    last_log = 0
    en2_counter = 0
    best = 0.0
    submitted = 0
    while time.time() < deadline and not client.stop_flag:
        with client.lock:
            job, gen, diff = client.current_job, client.job_generation, client.difficulty
        if job is None or diff is None:
            time.sleep(0.3); continue
        en2_counter += 1
        en2 = "%0*x" % (client.extranonce2_size * 2, en2_counter)
        header, _merkle, _cb = build_header(job, client.extranonce1, en2, 0, "wordswap")
        target = target_for_difficulty(float(diff))
        # scan in 2^24 chunks so a new job preempts quickly
        nonce = 0
        while nonce < (1 << 32):
            with client.lock:
                if client.job_generation != gen:
                    break
            span = min(1 << 24, (1 << 32) - nonce)
            hit = engine.search_first(header, target, nonce, span)
            total_hashes += span
            nonce += span
            if hit is not None:
                found, digest = hit
                d = difficulty_of(digest)
                best = max(best, d)
                client.submit(job, en2, found)
                submitted += 1
                ev.log("share_submitted", nonce=found, difficulty=d,
                       job_id=job.get("job_id"))
                print(f"SHARE submitted nonce={found} diff={d:.2f}", flush=True)
                nonce = max(nonce, found + 1)
        now = time.time()
        if now - last_log > 10:
            last_log = now
            elapsed = now - t_start
            rate = total_hashes / max(elapsed, 1)
            line = (f"t={elapsed:6.0f}s job={job.get('job_id')} "
                    f"height_job prev={job.get('prevhash','')[:12]} "
                    f"pool_diff={diff} hashes={total_hashes:,} "
                    f"rate={rate:,.0f} H/s best={best:.4f} "
                    f"shares_submitted={submitted}")
            print(line, flush=True)
            with open(STATUS, "w") as f:
                f.write(f"MAINNET LIVE MINING\n{line}\n"
                        f"worker={user}\npool=public-pool.io:21496\n")
            ev.log("status", hashes=total_hashes, rate=rate, best=best,
                   submitted=submitted)
    print("duration complete", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
