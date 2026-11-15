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
from mining.mining_statistics import (CATEGORIES, FrontierAccountant,
                                      MiningStatistics, SafeRecorder,
                                      WindowedRate)
from mining.probability import (expected_hashes, expected_hashes_exact,
                                expected_seconds, median_seconds,
                                percentile_seconds, prob_at_least_one,
                                prob_at_least_one_exact,
                                prob_at_least_one_hashes,
                                quantile_seconds)


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


def test_probability_percentiles():
    """BR-011 acceptance anchors, as prescribed by
    research/probability/BITCOIN_MINING_PROBABILITY_MODEL.md
    section 8 when the functions were specified. The full
    battery lives in tests/test_probability_percentiles.py;
    the anchors are pinned here too because the model names
    this suite as their home."""
    from fractions import Fraction
    t1 = 0xFFFF << 208  # genesis (difficulty-1) target
    for r, d in ((20.6e6, 8.0e13), (1 << 32, 1.0)):
        mean = expected_seconds(r, d)
        assert abs(median_seconds(r, d)
                   - math.log(2) * mean) <= 1e-12 * mean
        assert abs(percentile_seconds(r, d, 90)
                   - math.log(10) * mean) <= 1e-12 * mean
        assert abs(percentile_seconds(r, d, 95)
                   - math.log(20) * mean) <= 1e-12 * mean
        assert abs(percentile_seconds(r, d, 99)
                   - math.log(100) * mean) <= 1e-12 * mean
        for q in (0.5, 0.9, 0.95, 0.99):
            back = prob_at_least_one(
                r, d, quantile_seconds(r, d, q))
            assert abs(back - q) < 1e-12, (r, d, q, back)
    exact = expected_hashes_exact(t1)
    assert exact == Fraction(1 << 256, t1 + 1)
    assert abs(float(exact) - 4295032833.000015) < 1e-5
    p_diff = prob_at_least_one_hashes(1, 1 << 32)
    p_exact = prob_at_least_one_exact(t1, 1 << 32)
    assert abs(p_diff - 0.6321205589) < 1e-9, p_diff
    assert abs(p_exact - 0.6321149454) < 1e-9, p_exact
    # The anchors differ in the fifth decimal and must stay
    # separate: each form fails the other's tolerance.
    assert abs(p_diff - 0.6321149454) > 1e-9
    assert abs(p_exact - 0.6321205589) > 1e-9
    print("ok: BR-011 percentile and exact-target anchors hold, "
          "with the two 63.2 percent anchors pinned separately")


def test_frontier_accountant_separation():
    stats = MiningStatistics()
    acc = FrontierAccountant(stats)
    h1, h2 = b"\x01" * 80, b"\x02" * 80
    unique, repeated = acc.record_search(
        h1, 0, 100, True, worker="w", backend="b")
    assert (unique, repeated) == (100, 0)
    assert stats.total("backend_hashes") == 100
    assert stats.total("actual_computations") == 100
    assert stats.total("unique_nonces") == 100
    assert stats.total("unique_coverage") == 100
    assert stats.total("unique_headers") == 1
    assert stats.total("repeated_work") == 0
    # The identical interval again: real work, all repeated,
    # and the unique counters do not move.
    unique, repeated = acc.record_search(
        h1, 0, 100, True, worker="w", backend="b")
    assert (unique, repeated) == (0, 100)
    assert stats.total("backend_hashes") == 200
    assert stats.total("actual_computations") == 200
    assert stats.total("unique_nonces") == 100
    assert stats.total("unique_coverage") == 100
    assert stats.total("repeated_work") == 100
    # A hit chunk: its new positions are examined (unique
    # nonces) but the chunk did not complete, so coverage does
    # not advance over it (EXP-035 completed chunks only).
    unique, repeated = acc.record_search(
        h1, 100, 50, False, worker="w", backend="b")
    assert (unique, repeated) == (50, 0)
    assert stats.total("unique_nonces") == 150
    assert stats.total("unique_coverage") == 100
    # A second header is a second unique header.
    acc.record_search(h2, 0, 10, True)
    assert stats.total("unique_headers") == 2
    snap = stats.snapshot()
    assert set(snap["totals"].keys()) == set(CATEGORIES)
    assert snap["per_worker"]["w"]["backend_hashes"] == 250
    assert snap["per_backend"]["b"]["repeated_work"] == 100
    assert acc.errors == 0
    print("ok: frontier accountant separates unique coverage, "
          "actual computations and repeated work exactly, "
          "and a hit chunk earns no coverage")


def test_safe_recorder_isolation():
    class BrokenStats:
        def record(self, *a, **kw):
            raise RuntimeError("statistics exploded")

    rec = SafeRecorder(BrokenStats())
    rec.record("backend_hashes", 5)
    rec.record("candidates", 1)
    assert rec.errors == 2, rec.errors
    # Even a caller-side mistake (unknown category) is
    # swallowed and counted, never raised into a search loop.
    stats = MiningStatistics()
    rec2 = SafeRecorder(stats)
    rec2.record("no_such_category", 1)
    assert rec2.errors == 1
    assert stats.total("backend_hashes") == 0
    rec2.record("backend_hashes", 7)
    assert rec2.errors == 1
    assert stats.total("backend_hashes") == 7
    print("ok: SafeRecorder swallows and counts every "
          "recording failure; mining never sees it")


_WIRING_SCRIPT = "0014" + "00" * 20
_WIRING_PAYOUT = "bcrt1qcheckpoint0000000000000000000000000000"


def _wiring_template():
    from mining.pow import target_from_nbits
    return {
        "version": 0x20000000,
        "previousblockhash": "11" * 32,
        "transactions": [],
        "coinbaseaux": {"flags": ""},
        "coinbasevalue": 5_000_000_000,
        "target": format(target_from_nbits(0x207FFFFF), "064x"),
        "bits": "207fffff",
        "height": 100,
        "mintime": 1,
        "curtime": 1700000000,
    }


class _WiringRPC:
    """Fake Core for the engine wiring test: serves one fixed
    regtest template and confirms submitted blocks in its best
    chain, computing the block hash the way Core would see
    it."""

    def __init__(self, template):
        self.template = template
        self.best = "00" * 32

    def call(self, method, *args):
        if method == "getblocktemplate":
            return dict(self.template)
        if method == "validateaddress":
            return {"isvalid": True,
                    "scriptPubKey": _WIRING_SCRIPT}
        if method == "submitblock":
            from mining.pow import dsha256
            block = bytes.fromhex(args[0])
            self.best = dsha256(block[:80])[::-1].hex()
            return None
        raise AssertionError(f"unexpected RPC call {method}")

    def get_blockchain_info(self):
        return {"chain": "regtest", "blocks": 99, "headers": 99}

    def get_best_block_hash(self):
        return self.best


class _MissCompute:
    backend = "fake"

    def search_first_counted(self, header, target, start, count):
        return None, count, 0.0


class _HitCompute:
    backend = "fake"

    def search_first_counted(self, header, target, start, count):
        return (start + 7, b"\x00" * 32), 8, 0.0


def test_engine_statistics_wiring():
    from mining.engine import MiningEngine
    template = _wiring_template()
    engine = MiningEngine(_WiringRPC(template), _WIRING_PAYOUT,
                          compute=_MissCompute(),
                          batch_size=1 << 16,
                          extranonce_space=(0, 1))
    result = engine.mine_cycle(max_batches=2,
                               deadline_seconds=10000)
    assert result["hashes"] == 2 * (1 << 16), result
    totals = engine.statistics.snapshot()["totals"]
    assert totals["backend_hashes"] == 2 * (1 << 16), totals
    assert totals["actual_computations"] == 2 * (1 << 16), totals
    assert totals["unique_nonces"] == 2 * (1 << 16), totals
    assert totals["unique_coverage"] == 2 * (1 << 16), totals
    assert totals["unique_headers"] == 1, totals
    assert totals["repeated_work"] == 0, totals
    assert totals["candidates"] == 0, totals
    # A second cycle over the same template without a
    # checkpoint re-examines the same positions: the work is
    # real (backend and actual grow) but it is repeated, and
    # the unique counters must not move.
    engine.mine_cycle(max_batches=2, deadline_seconds=10000)
    totals = engine.statistics.snapshot()["totals"]
    assert totals["backend_hashes"] == 4 * (1 << 16), totals
    assert totals["actual_computations"] == 4 * (1 << 16), totals
    assert totals["unique_nonces"] == 2 * (1 << 16), totals
    assert totals["unique_coverage"] == 2 * (1 << 16), totals
    assert totals["repeated_work"] == 2 * (1 << 16), totals
    print("ok: MiningEngine.mine_cycle records search "
          "accounting as it happens, and a checkpoint-less "
          "rescan lands in repeated_work, not in coverage")

    hit_engine = MiningEngine(_WiringRPC(template),
                              _WIRING_PAYOUT,
                              compute=_HitCompute(),
                              batch_size=1 << 16,
                              extranonce_space=(0, 1))
    result = hit_engine.mine_cycle(max_batches=2,
                                   deadline_seconds=10000)
    assert result["accepted"] is True, result
    totals = hit_engine.statistics.snapshot()["totals"]
    assert totals["candidates"] == 1, totals
    assert totals["blocks_submitted"] == 1, totals
    assert totals["blocks_accepted"] == 1, totals
    assert totals["blocks_rejected"] == 0, totals
    assert totals["backend_hashes"] == 8, totals
    assert totals["unique_nonces"] == 8, totals
    # The hit chunk did not complete: no coverage over it.
    assert totals["unique_coverage"] == 0, totals
    # Verifier-defined counters are not claimed by this path.
    assert totals["valid_candidates"] == 0, totals
    assert totals["network_target_candidates"] == 0, totals
    print("ok: a mine_cycle block records candidates, "
          "blocks_submitted and blocks_accepted separately, "
          "with no coverage for the unfinished hit chunk")


def test_mainnet_live_statistics_wiring():
    from mining import mainnet_live
    from mining.stratum_client import StratumClient

    stats = MiningStatistics()
    rec = SafeRecorder(stats)
    mainnet_live.record_candidate_event(
        rec, True, True, "worker1", "v512dual")
    mainnet_live.record_candidate_event(
        rec, False, False, "worker1", "v512dual")
    totals = stats.snapshot()["totals"]
    assert totals["candidates"] == 2, totals
    assert totals["verification_hashes"] == 4, totals
    assert totals["valid_candidates"] == 1, totals
    assert totals["network_target_candidates"] == 1, totals
    mainnet_live.record_share_result(rec, True, "worker1",
                                     "v512dual")
    mainnet_live.record_share_result(rec, False, "worker1",
                                     "v512dual")
    totals = stats.snapshot()["totals"]
    assert totals["pool_shares_accepted"] == 1, totals
    assert totals["pool_shares_rejected"] == 1, totals
    snap = stats.snapshot()
    assert snap["per_worker"]["worker1"]["candidates"] == 2
    assert snap["per_backend"]["v512dual"][
        "pool_shares_accepted"] == 1
    print("ok: mainnet_live candidate and share-result "
          "recorders land in separated counters, per worker "
          "and per backend")

    # The production hook: a StratumClient mining.submit
    # verdict reaches the recorder through on_share_result,
    # as it happens, in the reader path.
    class CollectingEvidence:
        def __init__(self):
            self.events = []

        def log(self, event, **fields):
            self.events.append((event, fields))

    stats2 = MiningStatistics()
    rec2 = SafeRecorder(stats2)
    client = StratumClient("127.0.0.1", 1, "u", "x",
                           CollectingEvidence())
    assert client.on_share_result is None
    client.on_share_result = lambda accepted: \
        mainnet_live.record_share_result(rec2, accepted, "w", "b")
    client.methods_by_id[7] = "mining.submit"
    client._handle({"id": 7, "result": True})
    client.methods_by_id[8] = "mining.submit"
    client._handle({"id": 8, "result": False})
    totals2 = stats2.snapshot()["totals"]
    assert totals2["pool_shares_accepted"] == 1, totals2
    assert totals2["pool_shares_rejected"] == 1, totals2
    # A failing hook cannot kill the reader path, and with no
    # hook set the client behaves exactly as before.
    client.on_share_result = lambda accepted: 1 / 0
    client.methods_by_id[9] = "mining.submit"
    client._handle({"id": 9, "result": True})
    client.on_share_result = None
    client.methods_by_id[10] = "mining.submit"
    client._handle({"id": 10, "result": True})
    assert totals2["pool_shares_accepted"] == 1, totals2
    print("ok: StratumClient share verdicts reach the "
          "statistics through the hook as they happen; a "
          "failing or absent hook changes nothing")


def main():
    with tempfile.TemporaryDirectory() as tmp:
        log, state = test_counter_beyond_old_window(tmp)
        test_counter_rotation_and_corruption(tmp, log, state)
        test_evidence_stats_function(tmp)
    test_real_log_matches_brute_force()
    test_statistics_separation()
    test_windowed_rate()
    test_probability()
    test_probability_percentiles()
    test_frontier_accountant_separation()
    test_safe_recorder_isolation()
    test_engine_statistics_wiring()
    test_mainnet_live_statistics_wiring()
    print("ALL EXP-037 STATISTICS TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
