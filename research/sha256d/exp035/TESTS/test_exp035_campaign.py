#!/usr/bin/env python3
"""EXP-035 controlled tests: lease manager and candidate
queue on this VM only, simulated workers, no fleet agent
is contacted or activated.

Two layers:
  * Targeted tests for each named fault: worker death
    mid-lease, lease expiry, duplicate completion replay,
    restart replay with a dead fencing token, coordinator
    restart, illegitimate completion attempts (steal
    attempts by non-holders), legitimate tail stealing,
    foreign-fleet rejection, starved-worker
    re-registration, candidate-queue dedup, stale
    generation drop, journal recovery.
  * A randomised campaign (seeded) that drives several
    simulated workers against one manager with all of
    the above injected at random, and asserts the
    predeclared proof obligations at the end of every
    trial:
      P1  the union of completed intervals equals the
          declared space exactly, per slice and in total;
      P2  completed intervals are pairwise disjoint;
      P3  duplicate, stale and not-holder reports are
          counted and never credited as unique coverage;
      P4  unique + pending + leased == declared total
          at completion, with pending == leased == 0;
      P5  the per-slice partition invariant holds at
          every assertion point.

Writes one JSON record under RAW_RESULTS/.
"""

import json
import os
import random
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
EXP035 = os.path.dirname(HERE)
sys.path.insert(0, EXP035)
from lease_manager import LeaseManager, LeaseError, \
    ForeignFleetError  # noqa: E402
from candidate_queue import CandidateQueue  # noqa: E402

FLEET = "nova-fleet-test"
RESULTS = {"targeted": {}, "campaign": {}}


def check_completed(mgr):
    """P1, P2, P4 for a finished job."""
    mgr.assert_partition_invariant()
    per_slice = {}
    for key, lo, hi in mgr.completed_intervals():
        per_slice.setdefault(key, []).append((lo, hi))
    total = 0
    for key, ivs in per_slice.items():
        ivs.sort()
        assert ivs[0][0] == 0, (key, ivs)
        assert ivs[-1][1] == mgr.job["nonce_count"], \
            (key, ivs)
        for (a_lo, a_hi), (b_lo, _b) in zip(ivs, ivs[1:]):
            assert a_hi == b_lo, ("gap/overlap", key, ivs)
        total += sum(hi - lo for lo, hi in ivs)
    assert total == mgr.declared_total(), \
        (total, mgr.declared_total())
    acc = mgr.accounting()
    assert acc["complete"], acc
    assert acc["unique_coverage"] == acc["declared_total"]
    assert acc["pending"] == 0 and acc["leased"] == 0
    assert acc["actual_computations"] \
        >= acc["unique_coverage"]
    return acc


def small_manager(nonce=256, chunk=64, slots=2,
                  versions=(0x20000000,), ntimes=(1700000000,),
                  counters=1):
    mgr = LeaseManager(FLEET)
    mgr.declare_job("job-1", 1, nonce, chunk, slots,
                    list(versions), list(ntimes),
                    counters_per_slot=counters)
    return mgr


# ----------------------------------------------------------------
# Targeted tests
# ----------------------------------------------------------------

def test_foreign_fleet_rejected():
    mgr = small_manager()
    try:
        mgr.register_worker("w-x", "other-fleet", 0.0)
        raise AssertionError("foreign fleet accepted")
    except ForeignFleetError:
        pass
    assert mgr.register_worker("w-0", FLEET, 0.0) \
        == "REGISTERED"


def test_duplicate_completion_idempotent():
    mgr = small_manager()
    mgr.register_worker("w-0", FLEET, 0.0)
    lease = mgr.lease("w-0", 0.0)
    assert mgr.complete("w-0", lease["lease_id"],
                        lease["token"]) == "OK"
    assert mgr.complete("w-0", lease["lease_id"],
                        lease["token"]) == "DUPLICATE"
    acc = mgr.accounting()
    assert acc["unique_coverage"] == 64, acc
    assert acc["duplicate_deliveries"] == 1, acc


def test_restart_replay_never_credited():
    mgr = small_manager()
    mgr.register_worker("w-0", FLEET, 0.0)
    mgr.register_worker("w-1", FLEET, 0.0)
    lease = mgr.lease("w-0", 0.0)
    assert mgr.progress("w-0", lease["lease_id"],
                        lease["token"], 32) == "OK"
    # Worker process restarts; coordinator reclaims at once.
    mgr.worker_restarted("w-0", 1.0)
    # The restarted worker replays its unfinished-work
    # completion claim from its old log. Dead token: STALE,
    # and no coverage is credited.
    assert mgr.complete("w-0", lease["lease_id"],
                        lease["token"]) == "STALE"
    acc = mgr.accounting()
    assert acc["unique_coverage"] == 0, acc
    assert acc["stale_reports"] == 1, acc
    # The chunk is re-leased inside the same extranonce
    # slot (w-0 re-registers and leases again); the
    # re-examined 32 positions land in repeated, not
    # unique. (w-1 would bind to a different slot and
    # lease a different slice, by design.)
    mgr.register_worker("w-0", FLEET, 2.0)
    lease2 = mgr.lease("w-0", 2.0)
    assert lease2["slice"] == lease["slice"]
    assert (lease2["lo"], lease2["hi"]) \
        == (lease["lo"], lease["hi"])
    assert mgr.complete("w-0", lease2["lease_id"],
                        lease2["token"]) == "OK"
    acc = mgr.accounting()
    assert acc["unique_coverage"] == 64, acc
    assert acc["repeated_computations"] == 32, acc


def test_lease_expiry_reclaim():
    mgr = small_manager()
    mgr.register_worker("w-0", FLEET, 0.0)
    lease = mgr.lease("w-0", 0.0, ttl=5.0)
    assert mgr.progress("w-0", lease["lease_id"],
                        lease["token"], 16) == "OK"
    reclaimed = mgr.expire(6.0)
    assert lease["lease_id"] in reclaimed
    assert mgr.complete("w-0", lease["lease_id"],
                        lease["token"]) == "STALE"
    acc = mgr.accounting()
    assert acc["unique_coverage"] == 0, acc


def test_coordinator_restart_tokens_die():
    mgr = small_manager()
    mgr.register_worker("w-0", FLEET, 0.0)
    mgr.register_worker("w-1", FLEET, 0.0)
    lease = mgr.lease("w-0", 0.0)
    assert mgr.progress("w-0", lease["lease_id"],
                        lease["token"], 64) == "OK"
    snap = mgr.snapshot()
    mgr2 = LeaseManager.restore(snap)
    # Pre-restart completion claim: never credited.
    assert mgr2.complete("w-0", lease["lease_id"],
                         lease["token"]) == "STALE"
    assert mgr2.accounting()["unique_coverage"] == 0
    # Workers re-register and finish the whole job.
    mgr2.register_worker("w-0", FLEET, 10.0)
    mgr2.register_worker("w-1", FLEET, 10.0)
    now = 10.0
    guard = 0
    while not mgr2.accounting()["complete"]:
        guard += 1
        assert guard < 10000
        for w in ("w-0", "w-1"):
            got = mgr2.lease(w, now)
            if got is not None:
                assert mgr2.complete(
                    w, got["lease_id"], got["token"]) \
                    == "OK"
    acc = check_completed(mgr2)
    assert acc["repeated_computations"] == 64, acc


def test_steal_and_token_rotation():
    mgr = small_manager(nonce=256, chunk=256, slots=2)
    mgr.register_worker("w-0", FLEET, 0.0)
    mgr.register_worker("w-1", FLEET, 0.0)
    lease = mgr.lease("w-0", 0.0)
    assert mgr.progress("w-0", lease["lease_id"],
                        lease["token"], 64) == "OK"
    stolen = mgr.steal("w-1", 1.0)
    assert stolen is not None
    mgr.assert_partition_invariant()
    # Victim's old token is dead.
    assert mgr.progress("w-0", lease["lease_id"],
                        lease["token"], 80) == "STALE"
    # A completion attempt carrying a token that is not
    # the lease's current token is STALE.
    res = mgr.complete("w-1", lease["lease_id"],
                       stolen["token"])
    assert res == "STALE", res
    # A non-holder attempt with the lease's current token
    # but the wrong worker identity is NOT_HOLDER, and
    # neither attempt credits coverage.
    before = mgr.accounting()["unique_coverage"]
    current = mgr.leases[lease["lease_id"]]["token"]
    res = mgr.complete("w-1", lease["lease_id"], current)
    assert res == "NOT_HOLDER", res
    assert mgr.accounting()["unique_coverage"] == before
    # Both halves complete exactly once.
    victim = mgr.leases[lease["lease_id"]]
    assert mgr.complete("w-0", lease["lease_id"],
                        victim["token"]) == "OK"
    assert mgr.complete("w-1", stolen["lease_id"],
                        stolen["token"]) == "OK"
    acc = mgr.accounting()
    assert acc["unique_coverage"] == 256, acc


def test_starved_worker_reregisters():
    mgr = LeaseManager(FLEET, starvation_window=10.0)
    mgr.declare_job("job-1", 1, 128, 64, 1,
                    [0x20000000], [1700000000])
    mgr.register_worker("w-0", FLEET, 0.0)
    got = mgr.lease("w-0", 0.0)
    assert mgr.complete("w-0", got["lease_id"],
                        got["token"]) == "OK"
    try:
        mgr.lease("w-0", 25.0)
        raise AssertionError("starved worker leased")
    except LeaseError:
        pass
    mgr.register_worker("w-0", FLEET, 25.0)
    assert mgr.lease("w-0", 25.0) is not None


def test_search_space_declaration():
    mgr = LeaseManager(FLEET)
    n = mgr.declare_job("job-9", 3, 1000, 100, 4,
                        [0x20000000, 0x20004000],
                        [1700000000, 1700000060],
                        counters_per_slot=2)
    # 4 slots x 2 counters x 2 versions x 2 ntimes
    assert n == 32, n
    assert mgr.declared_total() == 32 * 1000
    exts = {sl["extranonce2"] for sl in mgr.slices}
    assert len(exts) == 8  # 4 slots x 2 counters, disjoint
    for sl in mgr.slices:
        assert sl["extranonce2"] \
            == (sl["slot"] << 25) | sl["counter"]
    mgr.assert_partition_invariant()


def test_candidate_queue():
    q = CandidateQueue()
    base = {"job_id": "job-1", "generation": 1,
            "extranonce2": 0, "version": 0x20000000,
            "ntime": 1700000000, "nonce": 42,
            "lease_id": "L1", "worker_id": "w-0"}
    assert q.submit(dict(base)) == "ACCEPTED"
    assert q.submit(dict(base)) == "DUPLICATE"
    # Same nonce, different extranonce2: NOT a duplicate.
    other = dict(base, extranonce2=1 << 25)
    assert q.submit(other) == "ACCEPTED"
    # Stale generation is dropped at drain, never verified.
    old = dict(base, nonce=7, generation=0)
    q.seen[CandidateQueue.identity(old)] = old
    q.pending.append(old)
    calls = []

    def verifier(rec):
        calls.append(rec["nonce"])
        return "share"

    out = q.drain(verifier, current_generation=1,
                  lease_states={"L1": "reclaimed"})
    assert sorted(calls) == [42, 42], calls
    assert len(out) == 2
    st = q.stats()
    assert st["duplicates"] == 1, st
    assert st["verified"] == 2, st
    assert st["stale_generation_dropped"] == 1, st
    assert st["from_reclaimed_lease"] == 2, st


def test_candidate_queue_journal_recovery(tmp_journal):
    q = CandidateQueue(journal_path=tmp_journal)
    rec = {"job_id": "job-1", "generation": 1,
           "extranonce2": 0, "version": 0x20000000,
           "ntime": 1700000000, "nonce": 99,
           "lease_id": "L1", "worker_id": "w-0"}
    assert q.submit(rec) == "ACCEPTED"
    assert q.submit(rec) == "DUPLICATE"
    # Crash before drain: recovery requeues the record,
    # and a resubmission is still a duplicate.
    q2 = CandidateQueue.recover(tmp_journal)
    assert q2.stats()["pending"] == 1
    assert q2.submit(rec) == "DUPLICATE"
    out = q2.drain(lambda r: "block_candidate",
                   current_generation=1)
    assert len(out) == 1
    # Crash after verification: never verified twice.
    q3 = CandidateQueue.recover(tmp_journal)
    assert q3.stats()["pending"] == 0
    assert q3.submit(rec) == "DUPLICATE"


TARGETED = [
    ("foreign_fleet_rejected", test_foreign_fleet_rejected),
    ("duplicate_completion_idempotent",
     test_duplicate_completion_idempotent),
    ("restart_replay_never_credited",
     test_restart_replay_never_credited),
    ("lease_expiry_reclaim", test_lease_expiry_reclaim),
    ("coordinator_restart_tokens_die",
     test_coordinator_restart_tokens_die),
    ("steal_and_token_rotation",
     test_steal_and_token_rotation),
    ("starved_worker_reregisters",
     test_starved_worker_reregisters),
    ("search_space_declaration",
     test_search_space_declaration),
    ("candidate_queue", test_candidate_queue),
]


# ----------------------------------------------------------------
# Randomised campaign
# ----------------------------------------------------------------

class SimWorker:
    def __init__(self, wid):
        self.wid = wid
        self.lease = None      # local copy of lease dict
        self.examined = 0
        self.zombie = None     # dead lease kept for replay

    def sync(self, mgr):
        if self.lease is None:
            return
        rec = mgr.leases.get(self.lease["lease_id"])
        if rec is None or rec["state"] != "active":
            self.zombie = self.lease
            self.lease = None
            self.examined = 0
        else:
            self.lease = dict(rec)
            size = rec["hi"] - rec["lo"]
            if self.examined > size:
                self.examined = size


def campaign_trial(rng, trial_no):
    nworkers = rng.randint(2, 4)
    nonce = rng.choice([512, 1024, 2048])
    chunk = rng.choice([64, 128, 256])
    versions = [0x20000000, 0x20004000][:rng.randint(1, 2)]
    ntimes = [1700000000, 1700000060][:rng.randint(1, 2)]
    counters = rng.randint(1, 2)
    mgr = LeaseManager(FLEET, heartbeat_timeout=10.0,
                       starvation_window=10.0)
    mgr.declare_job("job-c%d" % trial_no, 1, nonce, chunk,
                    nworkers, versions, ntimes,
                    counters_per_slot=counters)
    queue = CandidateQueue()
    workers = [SimWorker("w%d" % i) for i in range(nworkers)]
    now = 0.0
    for w in workers:
        mgr.register_worker(w.wid, FLEET, now)
    inj = {"die": 0, "restart": 0, "dup": 0, "zombie": 0,
           "not_holder": 0, "steal": 0, "coord_restart": 0,
           "expire": 0, "cand_dup": 0}
    observed = {"dup": 0, "stale": 0, "not_holder": 0}
    guard = 0
    while not mgr.accounting()["complete"]:
        guard += 1
        assert guard < 200000, "campaign did not converge"
        now += rng.uniform(0.1, 1.5)
        if rng.random() < 0.10:
            before = len(mgr.events)
            mgr.expire(now)
            if any(e[0] == "reclaim"
                    for e in mgr.events[before:]):
                inj["expire"] += 1
        w = rng.choice(workers)
        mgr.heartbeat(w.wid, now) \
            if w.wid in mgr.workers and \
            mgr.workers[w.wid]["last_heartbeat"] is not None \
            else None
        w.sync(mgr)
        roll = rng.random()
        if w.lease is None:
            # Zombie replay attempt with a dead token.
            if w.zombie is not None and roll < 0.30:
                res = mgr.complete(w.wid,
                                   w.zombie["lease_id"],
                                   w.zombie["token"])
                assert res in ("STALE", "DUPLICATE"), res
                if res == "STALE":
                    observed["stale"] += 1
                inj["zombie"] += 1
                w.zombie = None
                continue
            rec = mgr.workers[w.wid]
            if rec["last_heartbeat"] is None:
                mgr.register_worker(w.wid, FLEET, now)
            try:
                got = mgr.lease(w.wid, now,
                                ttl=rng.choice([8.0, 30.0]))
            except LeaseError:
                mgr.register_worker(w.wid, FLEET, now)
                continue
            if got is not None:
                w.lease = got
                w.examined = 0
            continue
        # Worker holds a lease.
        size = w.lease["hi"] - w.lease["lo"]
        if roll < 0.08:
            mgr.fail_worker(w.wid)
            inj["die"] += 1
            w.sync(mgr)
        elif roll < 0.14:
            mgr.worker_restarted(w.wid, now)
            inj["restart"] += 1
            w.sync(mgr)
            mgr.register_worker(w.wid, FLEET, now)
        elif roll < 0.18:
            thief = rng.choice(workers)
            if thief.wid != w.wid:
                got = mgr.steal(thief.wid, now)
                if got is not None:
                    inj["steal"] += 1
                    thief.lease = got
                    thief.examined = 0
                    w.sync(mgr)
        elif roll < 0.22:
            # Illegitimate completion attempt by another
            # worker using the victim's lease id.
            other = rng.choice(workers)
            if other.wid != w.wid:
                res = mgr.complete(other.wid,
                                   w.lease["lease_id"],
                                   w.lease["token"])
                assert res in ("STALE", "NOT_HOLDER"), res
                if res == "NOT_HOLDER":
                    observed["not_holder"] += 1
                else:
                    observed["stale"] += 1
                inj["not_holder"] += 1
        elif roll < 0.25:
            snap = mgr.snapshot()
            mgr = LeaseManager.restore(snap)
            inj["coord_restart"] += 1
            for x in workers:
                x.sync(mgr)
                mgr.register_worker(x.wid, FLEET, now)
        elif roll < 0.45 or w.examined >= size:
            res = mgr.complete(w.wid, w.lease["lease_id"],
                               w.lease["token"])
            assert res == "OK", res
            if rng.random() < 0.35:
                res2 = mgr.complete(w.wid,
                                    w.lease["lease_id"],
                                    w.lease["token"])
                assert res2 == "DUPLICATE", res2
                observed["dup"] += 1
                inj["dup"] += 1
            # Occasionally report a candidate.
            if rng.random() < 0.30:
                rec = {"job_id": mgr.job["job_id"],
                       "generation": 1,
                       "extranonce2":
                           w.lease["extranonce2"],
                       "version": w.lease["version"],
                       "ntime": w.lease["ntime"],
                       "nonce": w.lease["lo"],
                       "lease_id": w.lease["lease_id"],
                       "worker_id": w.wid}
                assert queue.submit(rec) == "ACCEPTED"
                if rng.random() < 0.5:
                    assert queue.submit(rec) == "DUPLICATE"
                    inj["cand_dup"] += 1
            w.lease = None
            w.examined = 0
        else:
            step = rng.randint(1, max(1, size - w.examined))
            w.examined = min(size, w.examined + step)
            res = mgr.progress(w.wid, w.lease["lease_id"],
                               w.lease["token"], w.examined)
            assert res == "OK", res
        if guard % 500 == 0:
            mgr.assert_partition_invariant()
    acc = check_completed(mgr)
    # P3: every injected rejection class was observed and
    # counted; none of it is inside unique coverage
    # (unique == declared exactly, proven above).
    assert acc["duplicate_deliveries"] >= observed["dup"]
    assert acc["stale_reports"] >= observed["stale"]
    assert acc["not_holder_attempts"] \
        >= observed["not_holder"]
    calls = []
    queue.drain(lambda r: calls.append(r) or "share",
                current_generation=1)
    qst = queue.stats()
    assert qst["verified"] == len(calls)
    assert qst["duplicates"] == inj["cand_dup"]
    return {"trial": trial_no, "workers": nworkers,
            "declared_total": acc["declared_total"],
            "unique_coverage": acc["unique_coverage"],
            "actual": acc["actual_computations"],
            "repeated": acc["repeated_computations"],
            "duplicate_deliveries":
                acc["duplicate_deliveries"],
            "stale_reports": acc["stale_reports"],
            "not_holder_attempts":
                acc["not_holder_attempts"],
            "reclaims": acc["reclaims"],
            "injections": inj,
            "candidates_verified": qst["verified"]}


def main():
    for name, fn in TARGETED:
        fn()
        RESULTS["targeted"][name] = "PASS"
        print("PASS targeted:", name)
    journal = os.path.join(HERE, "_tmp_journal.jsonl")
    if os.path.exists(journal):
        os.remove(journal)
    test_candidate_queue_journal_recovery(journal)
    os.remove(journal)
    RESULTS["targeted"]["candidate_queue_journal_recovery"] \
        = "PASS"
    print("PASS targeted: candidate_queue_journal_recovery")

    rng = random.Random(20261115)
    trials = []
    for t in range(60):
        trials.append(campaign_trial(rng, t))
        print("PASS campaign trial", t,
              "declared", trials[-1]["declared_total"],
              "repeated", trials[-1]["repeated"])
    RESULTS["campaign"] = {
        "trials": len(trials),
        "all_passed": True,
        "total_declared": sum(t["declared_total"]
                              for t in trials),
        "total_repeated": sum(t["repeated"]
                              for t in trials),
        "total_duplicate_deliveries":
            sum(t["duplicate_deliveries"] for t in trials),
        "total_stale_reports":
            sum(t["stale_reports"] for t in trials),
        "total_not_holder_attempts":
            sum(t["not_holder_attempts"] for t in trials),
        "total_reclaims": sum(t["reclaims"]
                              for t in trials),
        "injections": {
            k: sum(t["injections"][k] for t in trials)
            for k in trials[0]["injections"]},
        "per_trial": trials}
    stamp = datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ")
    out = os.path.join(EXP035, "RAW_RESULTS",
                       "campaign_%s.json" % stamp)
    record = {"experiment": "EXP-035",
              "kind": "controlled local simulation",
              "host": os.uname().nodename,
              "when_utc": stamp,
              "results": RESULTS}
    with open(out, "w") as fh:
        json.dump(record, fh, indent=1, sort_keys=True)
    print("WROTE", out)
    print("ALL EXP-035 TESTS PASSED")


if __name__ == "__main__":
    main()
