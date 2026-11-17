#!/usr/bin/env python3
"""EXP-052 campaign driver (Gate 4) and bake-off runner.

Runs the predeclared EXP-017-shaped bake-off protocol
against the live host: per-tier correctness gates
(the EXP-049 self-check), 3 sessions of paired
65,536-hash blocks per comparison (every eligible
challenger against the static pick, plus the control,
static against a second instance of itself), the
EXP-017 adjusted bootstrap analysis, the predeclared
decision rule, and the verdict cache write.

Session integrity: each (comparison, session) unit is
written atomically on completion under
RAW_RESULTS/sessions/ (or --out-dir); a unit with a
complete file is never repeated and the skip is
disclosed in the campaign record; an interrupted unit
leaves no file and is re-run whole. Sessions run
strictly one at a time. The campaign wall budget is
3,600 s of measurement; exceeding it stops the
campaign and records INCOMPLETE.

The cache is written to --cache-out (default
RAW_RESULTS/bakeoff-dispatch-cache.json). The live
resolver path (.local/bakeoff-dispatch.json) is
deliberately never written by this driver: planting
deployment state is an operator act, and the dispatch
switch is off besides.

Restricted mode (--tiers / --static / --sessions /
--pairs) exists for the Gate 5 seam trial: the same
code path over a declared subset, with its outputs in
the caller's isolated directory and "restricted": true
in its record. It is never the campaign of record.

The predeclaration's sha256 is verified against the
pinned value before anything is measured; a mismatch
aborts the run.
"""
import argparse
import hashlib
import json
import os
import random
import statistics
import sys
import time
from datetime import datetime, timezone

ROOT = "/home/hatch/workspace/bitcoin-autonomous-lab"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
from mining import bakeoff_dispatch as bd  # noqa: E402
from mining import bench_mode  # noqa: E402
import exp052_analyze as an  # noqa: E402

PREDECLARATION_SHA256 = (
    "4dfba1104beac6de13ea6433ed68271f6f692d59657b7ea5478aeae9212f88d9")
WALL_BUDGET_S = 3_600.0


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_json_atomic(path, data):
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, sort_keys=True)
    os.replace(tmp, path)


def _unit_path(out_dir, name, session_idx):
    return os.path.join(
        out_dir, f"{name}_s{session_idx + 1}.json")


def run_campaign(out_dir, cache_out, tiers=None,
                 static=None, sessions=bd.SESSIONS,
                 pairs=bd.PAIRS_PER_SESSION,
                 restricted=False):
    started = time.time()
    campaign_id = datetime.now(timezone.utc).strftime(
        "exp052-%Y%m%dT%H%M%SZ")
    record = {"campaign_id": campaign_id,
              "restricted": restricted,
              "predeclaration_sha256":
                  PREDECLARATION_SHA256,
              "started_at": datetime.now(
                  timezone.utc).isoformat(),
              "fingerprint": bd.host_fingerprint(),
              "sessions_planned": sessions,
              "pairs_per_session": pairs,
              "block_hashes": bd.BLOCK_HASHES,
              "threads": bd.MEASURE_THREADS,
              "skipped_units": [], "measured_units": [],
              "voided_pairs": 0}
    fingerprint = record["fingerprint"]

    rows, engines = bd.probe_tiers()
    if tiers is not None:
        keep = set(tiers)
        rows = [r for r in rows if r["tier"] in keep]
        engines = {t: e for t, e in engines.items()
                   if t in keep}
    record["tier_probe"] = rows

    if static is None:
        static_tier, static_backend = bd.static_pick()
    else:
        static_tier = static
        row = next((r for r in rows
                    if r["tier"] == static), None)
        static_backend = row["resolved_backend"] if row \
            else None
    record["static_pick"] = static_tier
    record["static_backend"] = static_backend
    if static_tier is None or static_tier not in engines:
        record["outcome"] = "PROBE_FAILURE"
        record["outcome_reason"] = (
            "the static pick could not be constructed; "
            "total probe failure, no cache written")
        return record

    # Gate 4 correctness, per tier, before measurement.
    correctness = {}
    for row in rows:
        tier = row["tier"]
        if not row["eligible"]:
            continue
        check = bench_mode.self_check(engines[tier])
        correctness[tier] = check
        row["correctness"] = bool(check["passed"])
    record["correctness"] = {
        t: {"passed": c["passed"],
            "batch_digests_verified":
                c["batch_digests_verified"],
            "batch_digests_mismatched":
                c["batch_digests_mismatched"],
            "genesis_digest_matches":
                c["genesis_digest_matches"]}
        for t, c in correctness.items()}
    if not correctness[static_tier]["passed"]:
        record["outcome"] = "GATE4_FAILURE"
        record["outcome_reason"] = (
            "the static pick failed the Gate 4 "
            "correctness gates; campaign aborted before "
            "measurement, no cache written")
        return record

    challengers = [r["tier"] for r in rows
                   if r["eligible"] and r["tier"] != static_tier
                   and correctness.get(
                       r["tier"], {}).get("passed")]
    excluded = [r["tier"] for r in rows
                if r["eligible"] and r["tier"] != static_tier
                and not correctness.get(
                    r["tier"], {}).get("passed")]
    record["challengers"] = challengers
    record["excluded_correctness"] = excluded
    comparisons = [(f"{t}_vs_{static_tier}", t)
                   for t in challengers]
    comparisons.append(("control", static_tier))

    os.makedirs(out_dir, exist_ok=True)
    units = {}
    incomplete = False
    for name, challenger in comparisons:
        sessions_data = []
        for s_idx in range(sessions):
            unit_file = _unit_path(out_dir, name, s_idx)
            if os.path.exists(unit_file):
                with open(unit_file, "r",
                          encoding="utf-8") as f:
                    unit = json.load(f)
                sessions_data.append(unit)
                record["skipped_units"].append(
                    f"{name} session {s_idx + 1} "
                    "(complete file present, not repeated)")
                continue
            if time.time() - started > WALL_BUDGET_S:
                incomplete = True
                break
            rng = random.Random(
                bd.seed_for(f"{name}:session{s_idx + 1}"))
            engine_b = engines[challenger] \
                if challenger != static_tier else \
                bd._default_engine_factory(
                    static_tier, bd.MEASURE_THREADS)
            sess = bd.measure_session(
                engines[static_tier], engine_b, pairs, rng)
            sess["session_id"] = f"{name}-s{s_idx + 1}"
            sess["comparison"] = name
            sess["challenger"] = challenger
            sess["static_pick"] = static_tier
            sess["fingerprint"] = fingerprint
            sess["predeclaration_sha256"] = \
                PREDECLARATION_SHA256
            _write_json_atomic(unit_file, sess)
            sessions_data.append(sess)
            record["measured_units"].append(
                f"{name} session {s_idx + 1}")
            record["voided_pairs"] += sess["voided_pairs"]
        units[name] = {"challenger": challenger,
                       "sessions": sessions_data}
        if incomplete:
            break
    record["wall_s"] = round(time.time() - started, 1)
    if incomplete or any(
            len(u["sessions"]) < sessions
            for u in units.values()):
        record["outcome"] = "INCOMPLETE"
        record["outcome_reason"] = (
            "the campaign did not complete every "
            "(comparison, session) unit inside the wall "
            "budget; completed units are retained and "
            "never repeated, no cache written")
        return record

    analysis = an.analyse_all(units)
    decision = bd.decide(analysis)
    record["analysis"] = analysis
    record["decision"] = decision

    # Per-tier median rates across every recorded arm.
    rates = {r["tier"]: [] for r in rows}
    for comp in units.values():
        for sess in comp["sessions"]:
            for p in sess["pairs"]:
                rates[static_tier].append(p["a"]["rate_hs"])
                rates[comp["challenger"]].append(
                    p["b"]["rate_hs"])
    for row in rows:
        vals = rates.get(row["tier"]) or []
        row["median_rate_hs"] = (
            statistics.median(vals) if vals else None)

    cache = bd.build_cache_record(
        fingerprint, static_tier, decision["winner"],
        rows, {"qualified": decision["qualified"],
               "control_ok": decision["control_ok"],
               "reasons": decision["reasons"]},
        campaign_id)
    bd.write_cache(cache_out, cache)
    record["cache_written"] = cache_out
    record["winner"] = decision["winner"]
    record["outcome"] = "COMPLETE"
    record["outcome_reason"] = (
        "campaign complete; verdict "
        + (f"winner {decision['winner']}"
           if decision["winner"] else
           "STATIC (the static order stands for this "
           "host)"))
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="EXP-052 bake-off campaign driver")
    parser.add_argument("--out-dir", default=os.path.join(
        HERE, "RAW_RESULTS", "sessions"))
    parser.add_argument("--cache-out", default=os.path.join(
        HERE, "RAW_RESULTS", "bakeoff-dispatch-cache.json"))
    parser.add_argument("--record-out", default=None)
    parser.add_argument("--tiers", default=None,
                        help="comma-separated subset "
                             "(restricted Gate 5 mode)")
    parser.add_argument("--static", default=None)
    parser.add_argument("--sessions", type=int,
                        default=bd.SESSIONS)
    parser.add_argument("--pairs", type=int,
                        default=bd.PAIRS_PER_SESSION)
    args = parser.parse_args(argv)
    pred = os.path.join(HERE, "PREDECLARATION.md")
    actual = sha256_file(pred)
    if actual != PREDECLARATION_SHA256:
        print(f"ABORT: predeclaration sha256 {actual} "
              f"!= pinned {PREDECLARATION_SHA256}")
        return 2
    restricted = args.tiers is not None or \
        args.static is not None or \
        args.sessions != bd.SESSIONS or \
        args.pairs != bd.PAIRS_PER_SESSION
    tiers = args.tiers.split(",") if args.tiers else None
    record = run_campaign(
        args.out_dir, args.cache_out, tiers=tiers,
        static=args.static, sessions=args.sessions,
        pairs=args.pairs, restricted=restricted)
    record_out = args.record_out or os.path.join(
        HERE, "RAW_RESULTS",
        f"campaign_{record['campaign_id']}.json")
    _write_json_atomic(record_out, record)
    print(json.dumps(
        {"campaign_id": record["campaign_id"],
         "outcome": record["outcome"],
         "outcome_reason": record["outcome_reason"],
         "winner": record.get("winner"),
         "wall_s": record.get("wall_s"),
         "record": record_out}, indent=1))
    return 0 if record["outcome"] == "COMPLETE" else 1


if __name__ == "__main__":
    sys.exit(main())
