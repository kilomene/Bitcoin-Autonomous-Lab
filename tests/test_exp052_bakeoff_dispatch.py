#!/usr/bin/env python3
"""EXP-052 regression suite: bake-off hardening into
production dispatch (NOVA-ER-0012, register R-23).

Layers, in order:

  1. Predeclaration pin: the sha256 pinned in the
     campaign driver equals the file on disk.
  2. Decision rule units: the pure decide() function
     on synthetic analyses (displacement, control
     resolution failure, one-session failure, and the
     multi-qualifier argmax).
  3. Gate 3 (adversarial): every predeclared doubt
     case resolves to the static order with a doubt
     reason and never raises; the switch-off case
     never consults the cache; a valid STATIC verdict
     resolves to "auto" with the static reason; a
     valid winner cache resolves to the winner; total
     probe failure yields PROBE_FAILURE and writes no
     cache.
  3b. Audit regressions (EXP052_AUDIT.md defects
     D-1 and D-2): wrong-typed resolver arguments
     (non-mapping config or fingerprint, non-numeric
     now, integer cache path) fall back to the static
     order without raising, and a winner contradicted
     by the cache's own tier rows (ineligible, missing,
     or resolved to a different backend) is doubt.
  4. Gate 5 (dispatch seam, isolated): the restricted
     protocol run (tiers v512 and shani, static v512,
     1 session, 40 pairs) through the campaign driver
     into a temporary directory produces a genuine
     cache; the resolver honours it; corrupting it or
     tampering its fingerprint falls back to static;
     the switch off ignores it. The real campaign
     cache, when present, resolves per its verdict.
  5. Seam defaults: the endpoint config's bake-off
     section defaults to disabled, and the resolver
     with no configuration returns "auto".

The campaign of record is research/sha256d/exp052/
exp052_campaign.py; this suite is the regression
form. No other machine is contacted. The live
endpoint config is never read or written by this
suite except through load_config's merged defaults
(layer 5 reads values only).
"""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time

ROOT = "/home/hatch/workspace/bitcoin-autonomous-lab"
EXP052 = os.path.join(ROOT, "research/sha256d/exp052")
sys.path.insert(0, ROOT)
sys.path.insert(0, EXP052)

import exp052_campaign as camp  # noqa: E402
from mining import bakeoff_dispatch as bd  # noqa: E402
from mining.endpoint_config import (bakeoff_config,  # noqa: E402
                                    load_config)

CHECKS = 0
FP = {"cpu_model": "Test CPU 9000", "flags_hash": "0" * 16,
      "logical_cpus": 4}
NOW = 1_700_000_000.0


def check(cond, label):
    global CHECKS
    CHECKS += 1
    if not cond:
        raise AssertionError("check failed: %s" % label)
    print("ok %d: %s" % (CHECKS, label), flush=True)


def tier_rows():
    return [{"tier": t, "eligible": True,
             "resolved_backend": bd.DENOTED_BACKEND[t],
             "fault": None, "correctness": True,
             "median_rate_hs": 1_000_000.0}
            for t in bd.TIER_ORDER]


def valid_record(winner="v512", margin=bd.PREDECLARED_MARGIN,
                 timestamp=NOW):
    return bd.build_cache_record(
        FP, "v512dual", winner, tier_rows(),
        {"qualified": [winner] if winner else [],
         "control_ok": True, "reasons": ["synthetic"]},
        "test-campaign", margin=margin,
        timestamp=timestamp)


def enabled_cfg(path):
    return {"enabled": True, "cache_path": path,
            "max_age_s": bd.DEFAULT_MAX_AGE_S,
            "margin": bd.PREDECLARED_MARGIN}


def resolve(cfg, path, fingerprint=FP, now=NOW + 60):
    return bd.resolve_requested(cfg, cache_path=path,
                                fingerprint=fingerprint,
                                now=now)


def write(path, data):
    with open(path, "w", encoding="utf-8") as f:
        if isinstance(data, str):
            f.write(data)
        else:
            json.dump(data, f)


def expect_doubt(cfg, path, label, fingerprint=FP,
                 now=NOW + 60):
    requested, reason = resolve(cfg, path,
                                fingerprint=fingerprint,
                                now=now)
    check(requested == "auto" and
          reason.startswith("doubt:"),
          f"Gate 3 {label}: static on doubt ({reason})")


def analysis_for(per_session_cis, pooled_ci, control_ci,
                 challenger="v512"):
    comp = {"challenger": challenger,
            "per_session": [
                {"adjusted": {"mean_log_ratio": 0.1,
                              "ci95": ci}}
                for ci in per_session_cis],
            "pooled": {"adjusted": {
                "mean_log_ratio": 0.1, "ci95": pooled_ci}}}
    return {"comparisons": {"x_vs_v512dual": comp},
            "control": {"pooled": {"adjusted": {
                "ci95": control_ci}}}}


def main():
    # Layer 1: predeclaration pin.
    digest = hashlib.sha256(open(
        os.path.join(EXP052, "PREDECLARATION.md"),
        "rb").read()).hexdigest()
    check(digest == camp.PREDECLARATION_SHA256 ==
          "4dfba1104beac6de13ea6433ed68271f6f692d59657b7ea"
          "5478aeae9212f88d9",
          "predeclaration hash pinned and verified")

    # Layer 2: decision rule units. Bound log(1.05).
    bound = 0.0488
    good = analysis_for([[0.06, 0.2]] * 3, [0.07, 0.18],
                        [-0.02, 0.03])
    out = bd.decide(good)
    check(out["winner"] == "v512" and out["control_ok"],
          "decide: challenger clearing the margin in "
          "every session and pooled wins")
    bad_control = analysis_for([[0.06, 0.2]] * 3,
                               [0.07, 0.18], [-0.09, 0.12])
    out = bd.decide(bad_control)
    check(out["winner"] is None and not out["control_ok"],
          "decide: control CI wider than the margin "
          "certifies nobody")
    one_bad = analysis_for(
        [[0.06, 0.2], [0.01, 0.2], [0.06, 0.2]],
        [0.07, 0.18], [-0.02, 0.03])
    check(bd.decide(one_bad)["winner"] is None,
          "decide: one session below the margin blocks "
          "displacement")
    two = analysis_for([[0.06, 0.2]] * 3, [0.07, 0.18],
                       [-0.02, 0.03])
    two["comparisons"]["y_vs_v512dual"] = {
        "challenger": "shani",
        "per_session": [{"adjusted": {
            "mean_log_ratio": 0.3, "ci95": [0.08, 0.4]}}] * 3,
        "pooled": {"adjusted": {
            "mean_log_ratio": 0.3, "ci95": [0.09, 0.35]}}}
    check(bd.decide(two)["winner"] == "shani",
          "decide: of two qualifiers the highest pooled "
          "estimate wins")
    check(bound < bd.PREDECLARED_MARGIN + 0.001,
          "decide: log(1.05) bound consistent with the "
          "predeclared margin")

    tmp = tempfile.mkdtemp(prefix="exp052-test-")
    cache_path = os.path.join(tmp, "cache.json")
    cfg = enabled_cfg(cache_path)

    # Layer 3 baseline: a valid winner cache resolves
    # to the winner; a valid STATIC cache to "auto".
    write(cache_path, valid_record(winner="v512"))
    requested, reason = resolve(cfg, cache_path)
    check(requested == "v512" and
          reason.startswith("winner:"),
          "Gate 3 baseline: valid winner cache resolves "
          f"to the winner ({reason})")
    write(cache_path, valid_record(winner=None))
    requested, reason = resolve(cfg, cache_path)
    check(requested == "auto" and
          reason.startswith("static:"),
          "Gate 3 case 12: valid STATIC verdict resolves "
          "to the static order")

    # Case 1: cache missing.
    expect_doubt(cfg, os.path.join(tmp, "absent.json"),
                 "case 1 (cache missing)")
    # Case 2: not JSON.
    write(cache_path, "this is not json {")
    expect_doubt(cfg, cache_path, "case 2 (not JSON)")
    # Case 3: missing keys; wrong types.
    write(cache_path, {"schema": 1})
    expect_doubt(cfg, cache_path,
                 "case 3a (missing keys)")
    rec = valid_record()
    rec["winner"] = 42
    write(cache_path, rec)
    expect_doubt(cfg, cache_path,
                 "case 3b (winner wrong type)")
    # Case 4 and 5: fingerprint mismatches.
    write(cache_path, valid_record())
    other = dict(FP, cpu_model="Other CPU")
    expect_doubt(cfg, cache_path,
                 "case 4 (cpu model mismatch)",
                 fingerprint=other)
    other = dict(FP, flags_hash="f" * 16)
    expect_doubt(cfg, cache_path,
                 "case 5 (flags hash mismatch)",
                 fingerprint=other)
    # Case 6: stale.
    expect_doubt(cfg, cache_path, "case 6 (stale cache)",
                 now=NOW + bd.DEFAULT_MAX_AGE_S + 120)
    # Case 7: unknown winner.
    write(cache_path, valid_record(winner="nope"))
    expect_doubt(cfg, cache_path,
                 "case 7 (unknown winner)")
    # Case 8: non-finite values.
    raw = json.dumps(valid_record())
    raw = raw.replace('"margin": 0.05', '"margin": NaN')
    write(cache_path, raw)
    expect_doubt(cfg, cache_path,
                 "case 8a (NaN margin token)")
    rec = valid_record()
    rec["tiers"][0]["median_rate_hs"] = "fast"
    write(cache_path, rec)
    expect_doubt(cfg, cache_path,
                 "case 8b (string in a numeric field)")
    # Case 9: margin below predeclared; protocol drift.
    write(cache_path, valid_record(margin=0.01))
    expect_doubt(cfg, cache_path,
                 "case 9a (cached margin below "
                 "predeclared)")
    rec = valid_record()
    rec["protocol"] = "exp999-other"
    write(cache_path, rec)
    expect_doubt(cfg, cache_path,
                 "case 9b (protocol mismatch)")
    # Future timestamp is doubt too.
    write(cache_path, valid_record(timestamp=NOW + 10_000))
    expect_doubt(cfg, cache_path,
                 "case 6b (timestamp in the future)")

    # Case 10: total probe failure. The runner records
    # doubt and writes no cache.
    def raising_factory(requested, threads):
        raise RuntimeError("no engines today")
    rows, engines = bd.probe_tiers(
        engine_factory=raising_factory)
    check(all(not r["eligible"] and r["fault"]
              for r in rows) and not engines,
          "Gate 3 case 10a: probe_tiers records every "
          "fault and excludes every tier")
    check(bd.static_pick(
        engine_factory=raising_factory) == (None, None),
        "Gate 3 case 10b: static_pick reports total "
        "probe failure")
    saved_factory = bd._default_engine_factory
    bd._default_engine_factory = raising_factory
    try:
        probe_cache = os.path.join(tmp, "probe-cache.json")
        record = camp.run_campaign(
            os.path.join(tmp, "probe-sessions"),
            probe_cache, restricted=True)
    finally:
        bd._default_engine_factory = saved_factory
    check(record["outcome"] == "PROBE_FAILURE" and
          not os.path.exists(probe_cache),
          "Gate 3 case 10c: the runner records "
          "PROBE_FAILURE and writes no cache")

    # Case 11: switch off with a valid winner cache.
    write(cache_path, valid_record(winner="v512"))
    off_cfg = {"enabled": False, "cache_path": cache_path}
    requested, reason = bd.resolve_requested(
        off_cfg, fingerprint=FP, now=NOW + 60)
    check(requested == "auto" and
          reason.startswith("disabled:"),
          "Gate 3 case 11: switch off returns the "
          "static order without consulting the cache")

    # Layer 3b: audit regressions (EXP052_AUDIT.md).
    # D-1: wrong-typed resolver arguments are doubt,
    # never an exception out of the resolver.
    write(cache_path, valid_record(winner="v512"))
    for bad_cfg, kind in [(42, "int"), ("nope", "str"),
                          ([1, 2], "list")]:
        requested, reason = bd.resolve_requested(
            bad_cfg, cache_path=cache_path,
            fingerprint=FP, now=NOW + 60)
        check(requested == "auto" and
              reason.startswith("doubt:"),
              f"D-1: non-mapping bakeoff_cfg ({kind}) "
              "falls back to static without raising "
              f"({reason})")
    requested, reason = bd.resolve_requested(
        cfg, cache_path=cache_path, fingerprint=42,
        now=NOW + 60)
    check(requested == "auto" and
          reason.startswith("doubt:"),
          "D-1: non-mapping fingerprint falls back to "
          f"static without raising ({reason})")
    requested, reason = bd.resolve_requested(
        cfg, cache_path=cache_path, fingerprint=FP,
        now="soon")
    check(requested == "auto" and
          reason.startswith("doubt:"),
          "D-1: non-numeric now falls back to static "
          f"without raising ({reason})")
    requested, reason = bd.resolve_requested(
        cfg, cache_path=99999, fingerprint=FP,
        now=NOW + 60)
    check(requested == "auto" and
          reason.startswith("doubt:"),
          "D-1: integer cache_path is doubt, never an "
          "open() file descriptor "
          f"({reason})")
    # D-2: a winner contradicted by the cache's own
    # tier rows is doubt.
    rec = valid_record(winner="cuda")
    for row in rec["tiers"]:
        if row["tier"] == "cuda":
            row["eligible"] = False
            row["resolved_backend"] = "cpu"
            row["fault"] = "synthetic ineligible winner"
    write(cache_path, rec)
    expect_doubt(cfg, cache_path,
                 "D-2a (winner ineligible in its own "
                 "tier row)")
    rec = valid_record(winner="v512")
    rec["tiers"] = [r for r in rec["tiers"]
                    if r["tier"] != "v512"]
    write(cache_path, rec)
    expect_doubt(cfg, cache_path,
                 "D-2b (winner has no tier row)")
    rec = valid_record(winner="v512")
    for row in rec["tiers"]:
        if row["tier"] == "v512":
            row["resolved_backend"] = "c"
    write(cache_path, rec)
    expect_doubt(cfg, cache_path,
                 "D-2c (winner row resolved to a "
                 "different backend)")

    # Layer 4: Gate 5, isolated restricted run.
    g5 = os.path.join(tmp, "gate5")
    os.makedirs(g5)
    g5_cache = os.path.join(g5, "cache.json")
    g5_record = os.path.join(g5, "record.json")
    proc = subprocess.run(
        [sys.executable,
         os.path.join(EXP052, "exp052_campaign.py"),
         "--tiers", "v512,shani", "--static", "v512",
         "--sessions", "1", "--pairs", "40",
         "--out-dir", os.path.join(g5, "sessions"),
         "--cache-out", g5_cache,
         "--record-out", g5_record],
        capture_output=True, text=True, timeout=1200)
    check(proc.returncode == 0,
          "Gate 5: restricted protocol run completes "
          f"(rc={proc.returncode}; "
          f"{proc.stdout.strip()[-200:]})")
    record = json.load(open(g5_record))
    check(record["restricted"] and
          record["outcome"] == "COMPLETE",
          "Gate 5: restricted record is complete and "
          "marked restricted")
    live_fp = bd.host_fingerprint()
    g5_cfg = {"enabled": True, "cache_path": g5_cache,
              "max_age_s": bd.DEFAULT_MAX_AGE_S,
              "margin": bd.PREDECLARED_MARGIN}
    requested, reason = bd.resolve_requested(
        g5_cfg, fingerprint=live_fp)
    winner = record["winner"]
    if winner is None:
        check(requested == "auto" and
              reason.startswith("static:"),
              "Gate 5b: resolver honours the restricted "
              "STATIC verdict")
    else:
        check(requested == winner and
              reason.startswith("winner:"),
              "Gate 5b: resolver honours the restricted "
              f"winner {winner}")
    from gpu.engine import ComputeEngine
    engine = ComputeEngine(requested=requested, threads=2)
    if winner is not None:
        check(engine.backend == bd.DENOTED_BACKEND[winner],
              "Gate 5b: the constructed engine reports "
              "the winner's backend")
    else:
        auto_engine = ComputeEngine(requested="auto",
                                    threads=2)
        check(engine.backend == auto_engine.backend,
              "Gate 5b: the constructed engine matches "
              "the static (auto) engine's backend")
    # Corruption and fingerprint tamper fall back.
    write(g5_cache, "garbage {")
    requested, reason = bd.resolve_requested(
        g5_cfg, fingerprint=live_fp)
    check(requested == "auto" and
          reason.startswith("doubt:"),
          "Gate 5c: corrupted isolated cache falls "
          "back to static")
    subprocess.run(
        [sys.executable,
         os.path.join(EXP052, "exp052_campaign.py"),
         "--tiers", "v512,shani", "--static", "v512",
         "--sessions", "1", "--pairs", "40",
         "--out-dir", os.path.join(g5, "sessions"),
         "--cache-out", g5_cache,
         "--record-out", g5_record],
        capture_output=True, text=True, timeout=1200)
    data = json.load(open(g5_cache))
    data["fingerprint"]["flags_hash"] = "e" * 16
    write(g5_cache, data)
    requested, reason = bd.resolve_requested(
        g5_cfg, fingerprint=live_fp)
    check(requested == "auto" and
          reason.startswith("doubt:"),
          "Gate 5d: fingerprint-tampered cache falls "
          "back to static")
    # Switch off ignores a winner cache entirely.
    requested, reason = bd.resolve_requested(
        {"enabled": False, "cache_path": g5_cache},
        fingerprint=live_fp)
    check(requested == "auto" and
          reason.startswith("disabled:"),
          "Gate 5e: switch off ignores the isolated "
          "cache")

    # The real campaign cache resolves per its verdict.
    real_cache = os.path.join(
        EXP052, "RAW_RESULTS", "bakeoff-dispatch-cache.json")
    check(os.path.exists(real_cache),
          "campaign of record cache exists")
    requested, reason = bd.resolve_requested(
        {"enabled": True, "cache_path": real_cache,
         "max_age_s": bd.DEFAULT_MAX_AGE_S,
         "margin": bd.PREDECLARED_MARGIN},
        fingerprint=live_fp)
    real = json.load(open(real_cache))
    if real["winner"] is None:
        check(requested == "auto" and
              reason.startswith("static:"),
              "Gate 5a: campaign cache resolves to its "
              "STATIC verdict")
    else:
        check(requested == real["winner"] and
              reason.startswith("winner:"),
              "Gate 5a: campaign cache resolves to its "
              f"winner {real['winner']}")

    # Layer 5: seam defaults.
    merged = bakeoff_config(load_config())
    check(merged["enabled"] is False and
          merged["margin"] == bd.PREDECLARED_MARGIN,
          "endpoint config: bake-off section defaults "
          "to disabled at the predeclared margin")
    requested, reason = bd.resolve_requested()
    check(requested == "auto" and
          reason.startswith("disabled:"),
          "resolver with no configuration returns the "
          "static order")

    print("EXP-052 suite: %d checks, ALL PASSED" % CHECKS,
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
