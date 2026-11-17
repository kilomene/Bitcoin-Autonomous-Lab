#!/usr/bin/env python3
"""Incident code registry suite (NOVA-ER-0006, register R-30).

Gate 3: unknown codes are refused at validation time
(resolve, annotate, prefix, MiningStatistics
.record_incident) and a refusal changes no counter; the
registry's append-only discipline is enforced
(check_append_only detects mutation, removal, reorder,
reuse and middle insertion, and accepts a pure append);
the shipped registry equals the pinned baseline; every
code emitted at a predeclared site exists in the
registry (site coverage scan of mining/autopilot.py
and the statistics keying table).

Statistics keying: recording stale_reports,
duplicate_deliveries and leases_abandoned keys exactly
4001, 4002 and 4003; other categories key nothing;
snapshot() keeps exactly its EXP-037 pinned key set.

Gate 5: a byte-copy of the mining package in a temp
directory runs the real autopilot against a stub
miner; its own log carries the lifecycle codes end to
end, a second instance is refused with the 2004 code,
and its heartbeat incident_counts match its coded log
lines. Then a replay over the real recorded corpus
(.local/autopilot.log and evidence/mainnet-live.jsonl,
read only) maps every incident-class record to exactly
one code. The live tree is never written by this
suite.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)

from mining import incident_codes as ic
from mining.mining_statistics import (
    CATEGORY_INCIDENT_CODES, MiningStatistics, SafeRecorder)

CHECKS = 0


def check(cond, label):
    global CHECKS
    CHECKS += 1
    assert cond, label
    print(f"ok {CHECKS}: {label}")


BASELINE = [
    (1001, "MINER_EXITED"), (1002, "MINER_STALE_EVIDENCE"),
    (1003, "MINER_STARTED"), (2001, "SUPERVISOR_STARTED"),
    (2002, "SUPERVISOR_STOPPED"), (2003, "OPERATOR_STOP"),
    (2004, "INSTANCE_REFUSED"), (2005, "SUPERVISOR_LOST"),
    (3001, "UPDATE_AVAILABLE"),
    (3002, "UPDATE_PULL_FAILED"), (3003, "UPDATE_REFUSED"),
    (3004, "UPDATE_APPLIED"), (4001, "REPORT_STALE"),
    (4002, "REPORT_DUPLICATE"), (4003, "WORK_ABANDONED"),
    (5001, "SHARE_REJECTED"), (5002, "UPSTREAM_DISCONNECT"),
    (5003, "BACKEND_REFUSED"), (5004, "CANDIDATE_REFUSED"),
    (5005, "TEMPLATE_REFUSED"),
]


def test_registry_and_baseline():
    entries = ic.load_registry()
    check([(e["code"], e["name"]) for e in entries]
          == BASELINE,
          "shipped registry equals the pinned baseline "
          "(20 codes, append-only pin)")
    check(ic.check_append_only(entries, entries) == [],
          "shipped registry is a pure append of itself")
    check(all(ic.is_known(c) for c, _ in BASELINE)
          and not ic.is_known(9999)
          and not ic.is_known("1001"),
          "is_known agrees with the registry")
    rec = {}
    out = ic.annotate(rec, 4001)
    check(out is rec and rec["incident_code"] == 4001,
          "annotate sets incident_code on a dict record")
    check(ic.prefix(1001) == "[1001] ",
          "prefix renders the [code] token")


def test_gate3_refusal():
    stats = MiningStatistics()
    before = stats.incident_snapshot()
    for bad in (9999, 0, -1, "1001", None, 10.5):
        for fn in (lambda: ic.resolve(bad),
                   lambda: ic.prefix(bad),
                   lambda: ic.annotate({}, bad),
                   lambda: stats.record_incident(bad)):
            try:
                fn()
            except ValueError:
                pass
            else:
                raise AssertionError(
                    f"unknown code {bad!r} was not refused")
    check(True, "resolve, prefix, annotate and "
                "record_incident all refuse unknown codes "
                "(9999, 0, -1, str, None, float)")
    check(stats.incident_snapshot() == before,
          "a refused record_incident changes no counter")
    rec = SafeRecorder()
    rec.record_incident(9999)
    check(rec.errors == 1
          and rec.incident_snapshot()["totals"] == {},
          "SafeRecorder refuses-and-counts an unknown "
          "code without raising (EXP-037 contract)")
    rec.record_incident(1001, 2)
    check(rec.incident_snapshot()["totals"]
          == {"1001": 2} and rec.errors == 1,
          "SafeRecorder keys a known code normally")


def test_gate3_append_only():
    entries = ic.load_registry()

    def variant(mutate):
        copied = [dict(e) for e in entries]
        mutate(copied)
        return copied

    def edited(copied):
        copied[0]["description"] = "rewritten meaning"
    check(ic.check_append_only(entries, variant(edited)),
          "append-only check detects an in-place edit "
          "of a shipped entry")

    check(ic.check_append_only(entries, entries[:-1]),
          "append-only check detects a removed entry")

    def swapped(copied):
        copied[0], copied[1] = copied[1], copied[0]
    check(ic.check_append_only(entries, variant(swapped)),
          "append-only check detects a reordering")

    def reused(copied):
        copied[-1]["code"] = 5006
        copied[-1]["name"] = "SOMETHING_ELSE"
    check(ic.check_append_only(entries, variant(reused)),
          "append-only check detects a code being "
          "renumbered or reused")

    def inserted(copied):
        copied.insert(3, {"code": 1004, "name": "MIDDLE",
                          "class": "miner lifecycle",
                          "description": "inserted",
                          "emission": "none"})
    check(ic.check_append_only(entries, variant(inserted)),
          "append-only check detects a middle insertion")

    appended = entries + [{"code": 5006, "name": "FUTURE",
                           "class": "upstream and "
                                    "verification",
                           "description": "appended later",
                           "emission": "none yet"}]
    check(ic.check_append_only(entries, appended) == [],
          "append-only check accepts a pure append")


def test_statistics_keying():
    check(CATEGORY_INCIDENT_CODES == {
        "stale_reports": 4001,
        "duplicate_deliveries": 4002,
        "leases_abandoned": 4003},
        "keying table is exactly the predeclared K1-K3")
    check(all(ic.is_known(c) for c in
              CATEGORY_INCIDENT_CODES.values()),
          "every keying-table code exists in the registry")
    stats = MiningStatistics()
    stats.record("stale_reports", 2, worker="w1",
                 backend="agg")
    stats.record("duplicate_deliveries", 3)
    stats.record("leases_abandoned", 1)
    stats.record("backend_hashes", 7, worker="w1")
    snap = stats.incident_snapshot()
    check(snap["totals"] == {"4001": 2, "4002": 3,
                             "4003": 1},
          "incident categories key exactly 4001, 4002, "
          "4003; backend_hashes keys nothing")
    check(snap["per_worker"] == {"w1": {"4001": 2}},
          "incident per-worker view keys by code")
    check(snap["per_backend"] == {"agg": {"4001": 2}},
          "incident per-backend view keys by code")
    check(stats.incident_total(4001) == 2
          and stats.incident_total(5001) == 0,
          "incident_total reads the ledger")
    check(set(stats.snapshot().keys()) == {
        "categories", "totals", "per_worker",
        "per_backend"},
        "snapshot() keeps exactly its EXP-037 pinned "
        "key set (incidents are a separate view)")
    stats.record_incident(1001, 4, worker="w2")
    check(stats.incident_snapshot()["totals"]["1001"]
          == 4, "record_incident keys a direct code")


def test_site_coverage():
    src = open(os.path.join(
        ROOT, "mining", "autopilot.py")).read()
    literals = {int(m.group(1)) for m in re.finditer(
        r"log_incident\((\d+)", src)}
    check(literals == {1001, 1002, 1003, 2001, 2002,
                       2003, 3001, 3002, 3003, 3004},
          "autopilot log_incident site set equals the "
          "predeclared S1-S6, S8-S11 set")
    check(all(ic.is_known(c) for c in literals),
          "every site literal exists in the registry")
    check("prefix(2004)" in src,
          "the S7 lock-refusal print carries code 2004")
    stems = ("miner started pid=", "miner {state} after",
             "evidence stale", "stop file present",
             "autopilot stopped", "autopilot up pid=",
             "update available", "pull failed",
             "smoke test FAILED", "updated to")
    bad = []
    for line in src.splitlines():
        if any(stem in line for stem in stems) and \
                "log_incident(" not in line:
            bad.append(line.strip())
    check(not bad, "no incident message is left on a "
                   f"bare log() call: {bad}")


def gate5_isolated():
    tmp = tempfile.mkdtemp(prefix="bal-incident-gate5-")
    proc = None
    try:
        mining_dst = os.path.join(tmp, "mining")
        os.makedirs(mining_dst)
        for name in ("__init__.py", "autopilot.py",
                     "incident_codes.py",
                     "incident_registry.json",
                     "mining_statistics.py"):
            shutil.copy(os.path.join(ROOT, "mining", name),
                        mining_dst)
        os.makedirs(os.path.join(tmp, "evidence"))
        with open(os.path.join(
                tmp, "evidence", "mainnet-live.jsonl"),
                "w") as f:
            f.write(json.dumps(
                {"event": "job",
                 "ts": "2020-01-01T00:00:00Z"}) + "\n")
        env = dict(os.environ)
        env["BAL_AP_POLL_S"] = "0.5"
        env["BAL_AP_HEARTBEAT_S"] = "1"
        env["BAL_AP_STALE_S"] = "3"
        env["BAL_AP_MINER_CMD"] = json.dumps(
            [sys.executable, "-c",
             "import time; time.sleep(60)"])
        autopilot_py = os.path.join(mining_dst,
                                    "autopilot.py")
        log_path = os.path.join(tmp, ".local",
                                "autopilot.log")

        def log_text():
            try:
                return open(log_path).read()
            except OSError:
                return ""

        proc = subprocess.Popen(
            [sys.executable, autopilot_py], cwd=tmp,
            env=env, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True)
        deadline = time.time() + 45
        text = ""
        while time.time() < deadline:
            text = log_text()
            if "[1002]" in text and "[1001]" in text \
                    and text.count("[1003]") >= 2:
                break
            time.sleep(0.5)
        check("[2001]" in text and "[1003]" in text
              and "[1002]" in text and "[1001]" in text,
              "isolated instance: coded lines for "
              "supervisor start, miner start, stale "
              "kill and miner exit, in its own log")
        out = subprocess.run(
            [sys.executable, autopilot_py], cwd=tmp,
            env=env, capture_output=True, text=True,
            timeout=30)
        check(out.returncode == 0 and
              "[2004] another autopilot already owns "
              "this checkout" in out.stdout,
              "isolated instance: a second starter is "
              "refused with the [2004] code")
        open(os.path.join(tmp, ".local",
                          "autopilot.stop"), "w").close()
        rc = proc.wait(timeout=30)
        proc = None
        text = log_text()
        check(rc == 0 and "[2003]" in text
              and "[2002]" in text,
              "isolated instance: operator stop and "
              "supervisor stop carry codes 2003, 2002")
        counts = {}
        for line in text.splitlines():
            m = re.search(r"autopilot: \[(\d+)\] ", line)
            if m:
                counts[m.group(1)] = \
                    counts.get(m.group(1), 0) + 1
        hb = json.load(open(os.path.join(
            tmp, ".local", "heartbeat.json")))
        # The final heartbeat is written before the
        # [2002] stop line is logged (the pre-existing
        # teardown order), so 2002 lags by exactly that
        # one line; every other code must match exactly.
        expected = dict(counts)
        expected["2002"] = expected.get("2002", 0) - 1
        if expected["2002"] == 0:
            del expected["2002"]
        check(hb.get("incident_counts") == expected,
              "isolated heartbeat incident_counts match "
              "the coded log lines (2002 lagging by its "
              "own final line, by teardown order)")
        return counts
    finally:
        if proc is not None:
            proc.kill()
        shutil.rmtree(tmp, ignore_errors=True)


AP_SHAPES = [
    ("miner started", 1003), ("miner exited", 1001),
    ("evidence stale", 1002), ("autopilot up", 2001),
    ("autopilot stopped", 2002),
    ("stop file present", 2003),
    ("update available", 3001), ("pull failed", 3002),
    ("smoke test FAILED", 3003), ("updated to", 3004),
    ("another autopilot already owns", 2004),
]

REFUSAL_MARKERS = ("refus", "unavailable", "failed",
                   "not supported", "missing")


def replay():
    counts = {}
    unmapped = []
    log_lines = 0
    with open(os.path.join(
            ROOT, ".local", "autopilot.log")) as f:
        for line in f:
            m = re.search(r"autopilot: (?:\[(\d+)\] )?"
                          r"(.*)", line.strip())
            if not m:
                continue
            log_lines += 1
            if m.group(1):
                code = int(m.group(1))
            else:
                code = None
                for stem, c in AP_SHAPES:
                    if m.group(2).startswith(stem):
                        code = c
                        break
            if code is None or not ic.is_known(code):
                unmapped.append(line.strip())
            else:
                counts[code] = counts.get(code, 0) + 1
    check(not unmapped and log_lines > 0,
          f"replay: every one of the {log_lines} real "
          f"autopilot log lines maps to exactly one "
          f"code; unmapped: {unmapped[:3]}")
    ev_counts = {}
    with open(os.path.join(
            ROOT, "evidence", "mainnet-live.jsonl")) as f:
        for line in f:
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            event = ev.get("event")
            code = None
            if event == "share_result" and \
                    not ev.get("accepted"):
                code = 5001
            elif event in ("connection_error",
                           "reconnect_failed", "connected",
                           "reconnected"):
                code = 5002
            elif event == "candidate_rejected":
                code = 5004
            elif event == "template_rejected":
                code = 5005
            elif event == "backend_selected":
                reasons = " ".join(
                    str(v) for k, v in ev.items()
                    if k.endswith("_reason")).lower()
                if any(mk in reasons
                       for mk in REFUSAL_MARKERS):
                    code = 5003
            if code is not None:
                ev_counts[code] = \
                    ev_counts.get(code, 0) + 1
    check(ev_counts.get(5001, 0) >= 8
          and ev_counts.get(5002, 0) >= 119
          and ev_counts.get(5004, 0) >= 18
          and ev_counts.get(5005, 0) >= 2,
          "replay: evidence fault classes map to "
          f"exactly one code each: {ev_counts}")
    check(ev_counts.get(5003, 0) == 0,
          "replay: no backend-refusal instance exists "
          "in the operational evidence corpus (5003 "
          "coded, no instance, as the design records)")
    merged = dict(counts)
    for c, n in ev_counts.items():
        merged[c] = merged.get(c, 0) + n
    return merged


def main():
    test_registry_and_baseline()
    test_gate3_refusal()
    test_gate3_append_only()
    test_statistics_keying()
    test_site_coverage()
    iso_counts = gate5_isolated()
    print(f"isolated instance code counts: "
          f"{dict(sorted(iso_counts.items()))}")
    merged = replay()
    print(f"replay per-code counts: "
          f"{dict(sorted(merged.items()))}")
    print(f"ALL INCIDENT CODE TESTS PASSED "
          f"({CHECKS} checks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
