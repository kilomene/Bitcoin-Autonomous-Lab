#!/usr/bin/env python3
"""EXP-023 audit: how much per-extranonce / per-template
work in the lab's own code paths is recomputed reusable
state. Counts are deterministic (instrumented wrappers and
the counting stub RPC); timings are medians on this host,
reported as audit context. The verdict-bearing numbers are
the paired benchmarks (exp023_paired_bench.py).

Parts:
  A  build_candidate medians at 0/10/100/500 tx on this
     host, with exact RPC counts per call (EXP-009 redo).
  B  Component split of one build_candidate call at
     500 tx: where the per-call time actually goes.
  C  Merkle: full tree rebuild per step (current) vs the
     coinbase spine walk over cached levels (prototype).
  D  Stratum serving path: build_header cost per
     extranonce2 step, and its share of the nonce scan
     the step feeds.
  E  Solo server: validate_share cost per share at
     500 tx (per-share, not per-extranonce; recorded so
     the serving path is fully priced).
  F  Compression-prefix pricing: the most a block-1
     prefix snapshot (R8 or R11) could ever save in a
     Python serving path, from the round-stepper.
  G  Amortised prototype medians: prepare once vs per
     step, at 100 and 500 tx.
"""
import json
import os
import random
import statistics
import sys
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = "/home/hatch/workspace/bitcoin-autonomous-lab"
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import exp023_snapshots as S  # noqa: E402
import mining.engine as engine_mod  # noqa: E402
from exp023_amortized import (FamilyContext, PAYOUT,  # noqa: E402
                              PreparedTemplate, StubRPC,
                              synth_template)
from mining.engine import MiningEngine  # noqa: E402
from mining.pow import merkle_root  # noqa: E402
from mining.pow_engine import H0  # noqa: E402
from mining.solo_server import SoloServer  # noqa: E402
from mining.stratum_client import build_header  # noqa: E402

OUT_DIR = os.path.join(HERE, "exp023")
os.makedirs(OUT_DIR, exist_ok=True)
OUT = {"experiment": "EXP-023 audit",
       "recorded_utc": datetime.now(timezone.utc).isoformat(),
       "host": os.uname().nodename}


def median_ms(fn, reps):
    times = []
    for _ in range(reps):
        t0 = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t0)
    return statistics.median(times) * 1e3


def part_a(rng):
    res = {}
    for ntx in (0, 10, 100, 500):
        template = synth_template(rng, ntx)
        stub = StubRPC(template)
        eng = MiningEngine(stub, PAYOUT)
        stub.counts = {}
        med = median_ms(lambda: eng.build_candidate(template, 7), 15)
        counts = {k: v / 15 for k, v in stub.counts.items()}
        res[f"txs_{ntx}"] = {
            "median_ms_per_call": round(med, 3),
            "rpc_calls_per_call": counts,
            "per_template_64_extranonce_ms": round(med * 64, 1),
        }
        print("A", ntx, res[f"txs_{ntx}"], flush=True)
    OUT["A_build_candidate"] = res


def part_b(rng):
    template = synth_template(rng, 500, segwit_fraction=0.5,
                              with_commitment=True)
    stub = StubRPC(template)
    eng = MiningEngine(stub, PAYOUT)
    totals = {}
    counts = {}
    originals = {}
    for name in ("txid_of", "wtxid_of", "merkle_root",
                 "build_coinbase", "address_script_pubkey"):
        orig = getattr(engine_mod, name)
        originals[name] = orig

        def wrap(fn, label):
            def inner(*a, **kw):
                t0 = time.perf_counter()
                out = fn(*a, **kw)
                totals[label] = totals.get(label, 0.0) + \
                    (time.perf_counter() - t0)
                counts[label] = counts.get(label, 0) + 1
                return out
            return inner
        setattr(engine_mod, name, wrap(orig, name))
    orig_gbi = engine_mod.MiningEngine.get_template  # untouched
    rpc_orig = StubRPC.call
    rpc_totals = {"t": 0.0, "n": 0}

    def counting_call(self, method, *args):
        t0 = time.perf_counter()
        out = rpc_orig(self, method, *args)
        rpc_totals["t"] += time.perf_counter() - t0
        rpc_totals["n"] += 1
        return out
    StubRPC.call = counting_call
    reps = 15
    t0 = time.perf_counter()
    for en in range(reps):
        eng.build_candidate(template, en)
    total = time.perf_counter() - t0
    for name, orig in originals.items():
        setattr(engine_mod, name, orig)
    StubRPC.call = rpc_orig
    split = {k: {"ms_per_call": round(v / reps * 1e3, 3),
                 "calls_per_build": counts[k] / reps}
             for k, v in totals.items()}
    split["rpc_stub_zero_latency"] = {
        "ms_per_call": round(rpc_totals["t"] / reps * 1e3, 4),
        "calls_per_build": rpc_totals["n"] / reps}
    accounted = sum(v["ms_per_call"] for v in split.values())
    split["total_ms_per_call"] = round(total / reps * 1e3, 3)
    split["unattributed_ms_per_call"] = round(
        total / reps * 1e3 - accounted, 3)
    OUT["B_component_split_500tx"] = split
    print("B", split, flush=True)


def part_c(rng):
    template = synth_template(rng, 500)
    stub = StubRPC(template)
    fam = FamilyContext(stub, PAYOUT)
    prep = PreparedTemplate(fam, template)
    cb = rng.randbytes(32)
    full = median_ms(lambda: merkle_root([cb] + prep.txids), 50)
    spine = median_ms(lambda: prep.root_with_coinbase(cb), 200)
    levels = [len(l) for l in prep.levels]
    OUT["C_merkle_500tx"] = {
        "full_rebuild_median_ms": round(full, 4),
        "spine_walk_median_ms": round(spine, 4),
        "tree_level_sizes": levels,
        "full_rebuild_dsha_calls": sum(
            (s + 1) // 2 for s in levels[:-1]),
        "spine_dsha_calls": len(levels) - 1,
    }
    print("C", OUT["C_merkle_500tx"], flush=True)


def part_d(rng):
    job = {
        "job_id": "1", "prevhash": rng.randbytes(32).hex(),
        "coinb1": rng.randbytes(60).hex(),
        "coinb2": rng.randbytes(60).hex(),
        "merkle_branch": [rng.randbytes(32).hex() for _ in range(11)],
        "version": "20000000", "nbits": "170fffff",
        "ntime": "6553f100", "clean_jobs": True,
    }
    en1 = rng.randbytes(4).hex()
    med_us = median_ms(lambda: build_header(
        job, en1, "00000001", 0, "wordswap"), 300) * 1e3
    # A step feeds a full 2^32 nonce scan; at the recorded
    # live session rate of 12.46M H/s (EXP-017 integration
    # session) that scan is about 344 seconds.
    scan_s = (1 << 32) / 12.46e6
    OUT["D_stratum_step"] = {
        "build_header_median_us": round(med_us, 1),
        "branches": 11,
        "scan_seconds_at_recorded_live_rate": round(scan_s, 1),
        "step_share_of_scan": med_us / 1e6 / scan_s,
    }
    print("D", OUT["D_stratum_step"], flush=True)


def part_e(rng):
    template = synth_template(rng, 500)
    srv = SoloServer(StubRPC(template), PAYOUT,
                     share_difficulty=0.02)
    job = srv.refresh_job()
    en1 = b"\x01\x00\x00\x00"
    med = median_ms(lambda: srv.validate_share(
        job, en1, "0000002a", format(template["curtime"], "08x"),
        "00000000"), 30)
    OUT["E_solo_validate_share_500tx"] = {
        "median_ms_per_share": round(med, 3),
        "note": "per submitted share, not per extranonce "
                "step; the server never steps extranonces",
    }
    print("E", OUT["E_solo_validate_share_500tx"], flush=True)


def part_f(rng):
    block = rng.randbytes(64)
    # Prefix arms are priced with only the raw 16 message
    # words in the schedule (rounds below 16 need no
    # schedule expansion), the full arm with the complete
    # 64-word schedule: the honest cost of each depth.
    raw_w = list(__import__("struct").unpack(">16I", block)) + [0] * 48
    full_w = S.schedule_words(block)
    res = {}
    for label, rounds, w in (("rounds_9_R8", 9, raw_w),
                             ("rounds_12_R11", 12, raw_w),
                             ("rounds_64_full", 64, full_w)):
        med_us = median_ms(
            lambda: S.working_after(H0, block, rounds, w), 60) * 1e3
        res[label] = round(med_us, 1)
    res["max_prefix_saving_R8_us"] = round(
        res["rounds_64_full"] - res["rounds_9_R8"], 1)
    OUT["F_prefix_pricing_us_pure_python"] = res
    print("F", res, flush=True)


def part_g(rng):
    res = {}
    for ntx in (100, 500):
        template = synth_template(rng, ntx, segwit_fraction=0.5,
                                  with_commitment=True)
        stub = StubRPC(template)
        fam = FamilyContext(stub, PAYOUT)
        prep_ms = median_ms(lambda: PreparedTemplate(fam, template), 15)
        prep = PreparedTemplate(fam, template)
        step_ms = median_ms(lambda: prep.build(7, now=2_000_000_000), 100)
        res[f"txs_{ntx}"] = {
            "prepare_median_ms": round(prep_ms, 3),
            "step_median_ms": round(step_ms, 4),
        }
        print("G", ntx, res[f"txs_{ntx}"], flush=True)
    OUT["G_amortised"] = res


def main():
    rng = random.Random(23024)
    part_a(rng)
    part_b(rng)
    part_c(rng)
    part_d(rng)
    part_e(rng)
    part_f(rng)
    part_g(rng)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(OUT_DIR, f"audit_{stamp}.json")
    with open(path, "x") as fh:
        json.dump(OUT, fh, indent=2)
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
