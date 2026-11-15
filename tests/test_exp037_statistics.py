#!/usr/bin/env python3
"""EXP-037 tests: mining statistics and probability engine.

Pins three things:

1. The evidence census fix. mining/autopilot.py's
   EvidenceCounter counts share_result events over the WHOLE
   evidence log, incrementally and with a persisted offset,
   where the old code read only the last 2,000,000 bytes and
   silently dropped early accepted shares once the log grew
   past the window (on the production log of 2026-11-15 the
   tail window counted 222 of a true 247). Proven on a
   synthetic log larger than the old window with accepted
   shares inside the dropped region, plus incremental append,
   partial-line, rotation, truncation, corrupt-state and
   missing-log cases, and a brute-force comparison on the
   real production log when present.

2. The statistics engine's separation rule: every directive
   section 10 / EXP-035 section 7 category is its own counter
   (per worker and per backend too), unknown categories are
   refused, and no snapshot field sums categories together.

3. The probability formulas adopted from
   research/probability.py into mining/probability.py, pinned
   against independently known values and cross-checked
   against the research module they were adopted from.
"""

import calendar
import json
import math
import os
import sys
import tempfile
import time

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)

from mining.autopilot import EvidenceCounter, evidence_stats
from mining.mining_statistics import (CATEGORIES, MiningStatistics,
                                      WindowedRate)
from mining.probability import (expected_hashes, expected_seconds,
                                prob_at_least_one)


def ev_line(event, ts, **kw):
    ev = {"event": event, "ts": ts}
    ev.update(kw)
    return json.dumps(ev) + "\n"


def epoch(ts):
    return float(calendar.timegm(
        time.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S")))


def test_counter_beyond_old_window(tmp):
    log = os.path.join(tmp, "log.jsonl")
    state = os.path.join(tmp, "state.json")
    early_ts = "2026-11-15T05:00:00.000000+00:00"  # the max ts,
    # placed in the region the old tail window dropped
    with open(log, "w") as f:
        for _ in range(7):
            f.write(ev_line("share_result", early_ts,
                            accepted=True))
        f.write(ev_line("share_result", early_ts, accepted=False))
        f.write(ev_line("status", early_ts))
        pad = "x" * 200
        n = 0
        while f.tell() < 2_300_000:
            f.write(ev_line("job", "2026-11-15T01:00:00+00:00",
                            pad=pad, n=n))
            n += 1
        for _ in range(3):
            f.write(ev_line("share_result",
                            "2026-11-15T02:00:00+00:00",
                            accepted=True))
        for _ in range(2):
            f.write(ev_line("share_result",
                            "2026-11-15T02:00:00+00:00",
                            accepted=False))
    assert os.path.getsize(log) > 2_000_000
    c = EvidenceCounter(log, state)
    accepted, last_epoch = c.update()
    assert accepted == 10, accepted
    assert c.rejected == 3, c.rejected
    assert c.share_results == 13, c.share_results
    assert last_epoch == epoch(early_ts), (last_epoch, early_ts)
    # The old tail-window algorithm undercounts this exact log:
    with open(log, "rb") as f:
        f.seek(-2_000_000, os.SEEK_END)
        tail = f.read().decode("utf-8", "replace")
    old = sum(1 for line in tail.splitlines()
              if '"share_result"' in line and '"accepted": true'
              in line)
    assert old < 10, old
    print(f"ok: whole-log census counts 10 accepted / 3 rejected "
          f"past the old window (old algorithm found {old}); "
          f"last_epoch from the dropped region")

    # Incremental append: no rescan, no double count.
    with open(log, "a") as f:
        for _ in range(2):
            f.write(ev_line("share_result",
                            "2026-11-15T06:00:00+00:00",
                            accepted=True))
    accepted, last_epoch = c.update()
    assert accepted == 12, accepted
    assert last_epoch == epoch("2026-11-15T06:00:00+00:00")
    accepted2, _ = c.update()
    assert accepted2 == 12, accepted2
    print("ok: incremental append counted once, idle poll "
          "counts nothing twice")

    # A partial final line is not consumed until completed.
    line = ev_line("share_result", "2026-11-15T07:00:00+00:00",
                   accepted=True)
    with open(log, "a") as f:
        f.write(line[:20])
    accepted, _ = c.update()
    assert accepted == 12, accepted
    with open(log, "a") as f:
        f.write(line[20:])
    accepted, _ = c.update()
    assert accepted == 13, accepted
    print("ok: partial line held back, completed line counted")

    # A fresh counter instance resumes from the persisted
    # state instead of rescanning (offset survives restart).
    c2 = EvidenceCounter(log, state)
    accepted, _ = c2.update()
    assert accepted == 13, accepted
    print("ok: persisted offset survives a new counter instance")
    return log, state


def test_counter_rotation_and_corruption(tmp, log, state):
    # Rotation: a new, smaller log with a different head is a
    # new census, not an append.
    with open(log, "w") as f:
        for _ in range(4):
            f.write(ev_line("share_result",
                            "2026-11-16T00:00:00+00:00",
                            accepted=True))
    c = EvidenceCounter(log, state)
    accepted, _ = c.update()
    assert accepted == 4, accepted
    assert c.share_results == 4, c.share_results
    print("ok: rotation to a new log recounts from zero")

    # Truncation below the recorded offset also recounts.
    big = os.path.join(tmp, "big.jsonl")
    big_state = os.path.join(tmp, "big-state.json")
    with open(big, "w") as f:
        for i in range(50):
            f.write(ev_line("share_result",
                            "2026-11-15T00:00:00+00:00",
                            accepted=True, pad="y" * 500, n=i))
    c = EvidenceCounter(big, big_state)
    assert c.update()[0] == 50
    with open(big, "w") as f:
        for _ in range(3):
            f.write(ev_line("share_result",
                            "2026-11-15T00:00:00+00:00",
                            accepted=True, pad="y" * 500))
    c = EvidenceCounter(big, big_state)
    assert c.update()[0] == 3, c.accepted
    print("ok: truncation below the offset recounts")

    # Corrupt state file: fall back to a full recount.
    with open(state, "w") as f:
        f.write("this is not json")
    c = EvidenceCounter(log, state)
    accepted, _ = c.update()
    assert accepted == 4, accepted
    print("ok: corrupt state file falls back to a full recount")

    # Missing log: zero census, no exception.
    c = EvidenceCounter(os.path.join(tmp, "nope.jsonl"),
                        os.path.join(tmp, "nope-state.json"))
    assert c.update() == (0, 0.0)
    print("ok: missing log counts zero")


def test_evidence_stats_function(tmp):
    log = os.path.join(tmp, "fn.jsonl")
    state = os.path.join(tmp, "fn-state.json")
    with open(log, "w") as f:
        f.write(ev_line("share_result",
                        "2026-11-15T00:00:00+00:00", accepted=True))
        f.write(ev_line("share_result",
                        "2026-11-15T00:00:01+00:00",
                        accepted=False))
    accepted, last_epoch = evidence_stats(log, state)
    assert accepted == 1, accepted
    assert last_epoch == epoch("2026-11-15T00:00:01+00:00")
    print("ok: evidence_stats(path, state) keeps its contract")


def test_real_log_matches_brute_force():
    log = os.path.join(ROOT, "evidence", "mainnet-live.jsonl")
    if not os.path.exists(log):
        print("skip: no production evidence log in this tree")
        return
    truth_accepted = 0
    truth_last = 0.0
    with open(log, "rb") as f:
        for raw in f:
            try:
                ev = json.loads(raw.decode("utf-8", "replace"))
            except ValueError:
                continue
            if ev.get("event") == "share_result" \
                    and ev.get("accepted"):
                truth_accepted += 1
            if ev.get("ts"):
                truth_last = max(truth_last, epoch(ev["ts"]))
    with tempfile.TemporaryDirectory() as tmp:
        c = EvidenceCounter(log, os.path.join(tmp, "s.json"))
        accepted, last_epoch = c.update()
    assert accepted == truth_accepted, (accepted, truth_accepted)
    assert last_epoch == truth_last, (last_epoch, truth_last)
    print(f"ok: production log census {accepted} accepted "
          f"matches an independent brute-force count")


def test_statistics_separation():
    stats = MiningStatistics()
    for cat in CATEGORIES:
        stats.record(cat, 3, worker="w1", backend="v512dual")
    snap = stats.snapshot()
    assert set(snap.keys()) == {"categories", "totals",
                                "per_worker", "per_backend"}, \
        snap.keys()
    assert set(snap["totals"].keys()) == set(CATEGORIES)
    assert all(v == 3 for v in snap["totals"].values())
    assert snap["per_worker"]["w1"]["backend_hashes"] == 3
    assert snap["per_backend"]["v512dual"]["blocks_accepted"] == 3
    # No field anywhere in the snapshot sums categories: the
    # only numeric leaves are the per-category counters.
    stats.record("backend_hashes", 100, worker="w2")
    assert stats.total("backend_hashes") == 103
    assert stats.total("verification_hashes") == 3
    try:
        stats.record("hashes", 1)
        raise AssertionError("unknown category accepted")
    except ValueError:
        pass
    try:
        stats.record("backend_hashes", -1)
        raise AssertionError("negative count accepted")
    except ValueError:
        pass
    stats.record("backend_hashes", 0)
    assert stats.total("backend_hashes") == 103
    print("ok: categories stay separate, per worker and per "
          "backend; unknown and negative records refused")


def test_windowed_rate():
    r = WindowedRate()
    assert r.rate(60) == 0.0
    r.add(0, 0)
    r.add(60, 6000)
    r.add(120, 18000)
    r.add(3600, 360000)
    assert r.rate(60, now=120) == 200.0, r.rate(60, now=120)
    assert r.rate(120, now=120) == 150.0, r.rate(120, now=120)
    assert r.rate(3600, now=3600) == 100.0, r.rate(3600, now=3600)
    try:
        r.add(3601, 5)
        raise AssertionError("backwards counter accepted")
    except ValueError:
        pass
    print("ok: windowed rates derive from counter samples only")


def test_probability():
    assert expected_hashes(1) == float(1 << 32)
    assert expected_hashes(2.5) == 2.5 * (1 << 32)
    assert expected_seconds(1 << 32, 1) == 1.0
    assert expected_seconds(1, 1) == float(1 << 32)
    assert expected_seconds(0, 1) == math.inf
    p1 = prob_at_least_one(1 << 32, 1, 1)  # lambda == 1
    assert abs(p1 - 0.6321205588285577) < 1e-15, p1
    p2 = prob_at_least_one(1 << 32, 2, 4)  # lambda == 2
    assert abs(p2 - 0.8646647167633873) < 1e-15, p2
    assert prob_at_least_one(1 << 32, 1, 0) == 0.0
    assert prob_at_least_one(0, 1, 100) == 0.0
    try:
        expected_hashes(0)
        raise AssertionError("zero difficulty accepted")
    except ValueError:
        pass
    # Adoption fidelity: the production module agrees with the
    # research module it adopts on every shared function.
    from research.probability import (expected_seconds as r_es,
                                      prob_within as r_pw)
    for h, d, t in ((1e6, 1.0, 3600), (20.6e6, 8e13, 86400),
                    (1 << 32, 3.0, 12345)):
        assert expected_seconds(h, d) == r_es(h, d)
        assert prob_at_least_one(h, d, t) == r_pw(h, d, t)
    print("ok: probability formulas pinned to known values "
          "and identical to the research originals")


def main():
    with tempfile.TemporaryDirectory() as tmp:
        log, state = test_counter_beyond_old_window(tmp)
        test_counter_rotation_and_corruption(tmp, log, state)
        test_evidence_stats_function(tmp)
    test_real_log_matches_brute_force()
    test_statistics_separation()
    test_windowed_rate()
    test_probability()
    print("ALL EXP-037 STATISTICS TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
