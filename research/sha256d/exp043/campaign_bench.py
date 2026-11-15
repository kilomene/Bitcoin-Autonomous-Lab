#!/usr/bin/env python3
"""EXP-043 part 2: simulated multi-worker campaign timing.

Reruns the EXP-035 randomised campaign shape (same fault
classes, same proof obligations) at increasing simulated
worker counts against a fixed total declared space, and
measures wall time per campaign and per completed
position. All workers are simulated in-process on this
one VM; no fleet agent is contacted or activated.

Coverage accounting must close exactly in every trial:
the union of completed intervals equals the declared
space, pairwise disjoint, duplicates and repeated work
in their own counters (the EXP-035 check_completed
assertions, copied here so this script is self-contained).
A trial whose accounting does not close is recorded as a
FAILED run, never averaged in.
"""

import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from exp043_common import FLEET, loadavg, manifest, \
    write_result  # noqa: E402

from lease_manager import LeaseManager, LeaseError  # noqa: E402
from candidate_queue import CandidateQueue  # noqa: E402

VERSIONS = [0x20000000, 0x20004000]
NTIMES = [1700000000, 1700000060]
TOTAL_SPACE = 131072
CHUNKS_PER_SLICE = 32
# Coordinator restarts are the one fault whose cost grows
# with total retained state (snapshot deepcopy plus a
# reclaim scan per active lease). At EXP-035 trial sizes
# a flat 3 percent per-iteration rate meant a handful of
# restarts; at EXP-043 sizes it would mean over a
# thousand, and the study would measure nothing else for
# an hour. The rate is kept at 3 percent until this many
# restarts have fired in a trial, then stops; the count
# is recorded per trial so the cap is visible in the
# data, never hidden.
COORD_RESTART_BUDGET = 40


def check_completed(mgr):
    """EXP-035 P1, P2, P4, copied from
    TESTS/test_exp035_campaign.py."""
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


class SimWorker:
    """Copied from EXP-035 TESTS/test_exp035_campaign.py."""

    def __init__(self, wid):
        self.wid = wid
        self.lease = None
        self.examined = 0
        self.zombie = None

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


def run_trial(seed, n_workers, faults, wall_cap_s=None):
    rng = random.Random(seed)
    nonce = TOTAL_SPACE // n_workers
    chunk = nonce // CHUNKS_PER_SLICE
    t0 = time.perf_counter()
    mgr = LeaseManager(FLEET, heartbeat_timeout=10.0,
                       starvation_window=10.0)
    mgr.declare_job("job-exp043", 1, nonce, chunk,
                    n_workers, VERSIONS[:1], NTIMES[:1],
                    counters_per_slot=1)
    queue = CandidateQueue()
    workers = [SimWorker("w%d" % i)
               for i in range(n_workers)]
    now = 0.0
    for w in workers:
        mgr.register_worker(w.wid, FLEET, now)
    setup_s = time.perf_counter() - t0

    inj = {"die": 0, "restart": 0, "dup": 0, "zombie": 0,
           "not_holder": 0, "steal": 0, "coord_restart": 0,
           "expire": 0, "cand_dup": 0}
    guard = 0
    # Completion is tracked in O(1): every OK completion
    # credits exactly the completing lease's current
    # (hi - lo), which the manager keeps in sync with the
    # chunk (a steal shrinks the victim lease first). The
    # EXP-035 driver instead polled accounting() on every
    # iteration; at EXP-043 sizes that scan is itself a
    # top cost (profiled at 19 percent of a W=32 trial),
    # and it is harness noise, not prototype overhead, so
    # it is not in the timed loop here. Exactness is not
    # given up: check_completed still asserts the full
    # partition at the end of every completed trial.
    covered = 0
    capped = False
    t0 = time.perf_counter()
    while covered < TOTAL_SPACE:
        guard += 1
        assert guard < 5000000, "campaign did not converge"
        if wall_cap_s is not None and guard % 1024 == 0 \
                and time.perf_counter() - t0 > wall_cap_s:
            capped = True
            break
        now += rng.uniform(0.1, 1.5)
        if faults and rng.random() < 0.10:
            before = len(mgr.events)
            mgr.expire(now)
            if any(e[0] == "reclaim"
                    for e in mgr.events[before:]):
                inj["expire"] += 1
        w = rng.choice(workers)
        if w.wid in mgr.workers and \
                mgr.workers[w.wid]["last_heartbeat"] \
                is not None:
            mgr.heartbeat(w.wid, now)
        w.sync(mgr)
        roll = rng.random()
        if w.lease is None:
            if faults and w.zombie is not None \
                    and roll < 0.30:
                res = mgr.complete(w.wid,
                                   w.zombie["lease_id"],
                                   w.zombie["token"])
                assert res in ("STALE", "DUPLICATE"), res
                inj["zombie"] += 1
                w.zombie = None
                continue
            rec = mgr.workers[w.wid]
            if rec["last_heartbeat"] is None:
                mgr.register_worker(w.wid, FLEET, now)
            try:
                got = mgr.lease(
                    w.wid, now,
                    ttl=rng.choice([8.0, 30.0]) if faults
                    else 30.0)
            except LeaseError:
                mgr.register_worker(w.wid, FLEET, now)
                continue
            if got is not None:
                w.lease = got
                w.examined = 0
            continue
        size = w.lease["hi"] - w.lease["lo"]
        if faults and roll < 0.08:
            mgr.fail_worker(w.wid)
            inj["die"] += 1
            w.sync(mgr)
        elif faults and roll < 0.14:
            mgr.worker_restarted(w.wid, now)
            inj["restart"] += 1
            w.sync(mgr)
            mgr.register_worker(w.wid, FLEET, now)
        elif faults and roll < 0.18:
            thief = rng.choice(workers)
            if thief.wid != w.wid:
                got = mgr.steal(thief.wid, now)
                if got is not None:
                    inj["steal"] += 1
                    thief.lease = got
                    thief.examined = 0
                    w.sync(mgr)
        elif faults and roll < 0.22:
            other = rng.choice(workers)
            if other.wid != w.wid:
                res = mgr.complete(other.wid,
                                   w.lease["lease_id"],
                                   w.lease["token"])
                assert res in ("STALE", "NOT_HOLDER"), res
                inj["not_holder"] += 1
        elif faults and roll < 0.25 and \
                inj["coord_restart"] < COORD_RESTART_BUDGET:
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
            lease_rec = mgr.leases[w.lease["lease_id"]]
            covered += lease_rec["hi"] - lease_rec["lo"]
            if faults and rng.random() < 0.35:
                res2 = mgr.complete(w.wid,
                                    w.lease["lease_id"],
                                    w.lease["token"])
                assert res2 == "DUPLICATE", res2
                inj["dup"] += 1
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
                if faults and rng.random() < 0.5:
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
    wall_s = time.perf_counter() - t0
    if capped:
        # A capped trial is a FAILED run by the study's
        # own rule: its accounting does not close. It is
        # recorded with the coverage it reached, never
        # averaged in with completed trials.
        acc = mgr.accounting()
        return {
            "seed": seed, "workers": n_workers,
            "faults": faults, "status": "CAPPED",
            "wall_cap_s": wall_cap_s,
            "declared_total": acc["declared_total"],
            "unique_coverage": acc["unique_coverage"],
            "coverage_fraction":
                acc["unique_coverage"]
                / acc["declared_total"],
            "actual": acc["actual_computations"],
            "repeated": acc["repeated_computations"],
            "reclaims": acc["reclaims"],
            "duplicate_deliveries":
                acc["duplicate_deliveries"],
            "stale_reports": acc["stale_reports"],
            "not_holder_attempts":
                acc["not_holder_attempts"],
            "candidates_verified": 0,
            "injections": inj,
            "loop_iterations": guard,
            "leases_retained": len(mgr.leases),
            "events_retained": len(mgr.events),
            "setup_s": round(setup_s, 4),
            "wall_s": round(wall_s, 4),
            "ns_per_completed_position":
                int(wall_s * 1e9
                    / max(1, acc["unique_coverage"])),
            "accounting_closed": False,
        }
    acc = check_completed(mgr)
    assert covered == acc["unique_coverage"], \
        (covered, acc["unique_coverage"])
    calls = []
    queue.drain(lambda r: calls.append(r) or "share",
                current_generation=1)
    qst = queue.stats()
    assert qst["verified"] == len(calls)
    return {
        "seed": seed, "workers": n_workers,
        "faults": faults, "status": "OK",
        "declared_total": acc["declared_total"],
        "unique_coverage": acc["unique_coverage"],
        "actual": acc["actual_computations"],
        "repeated": acc["repeated_computations"],
        "reclaims": acc["reclaims"],
        "duplicate_deliveries": acc["duplicate_deliveries"],
        "stale_reports": acc["stale_reports"],
        "not_holder_attempts": acc["not_holder_attempts"],
        "candidates_verified": qst["verified"],
        "injections": inj,
        "loop_iterations": guard,
        "leases_retained": len(mgr.leases),
        "events_retained": len(mgr.events),
        "setup_s": round(setup_s, 4),
        "wall_s": round(wall_s, 4),
        "ns_per_completed_position":
            int(wall_s * 1e9 / acc["declared_total"]),
        "accounting_closed": True,
    }


def main():
    payload = manifest("campaign_in_process")
    payload["total_space"] = TOTAL_SPACE
    payload["coord_restart_budget_per_trial"] = \
        COORD_RESTART_BUDGET
    payload["trials"] = []
    for n_workers in (2, 8, 32, 128):
        # At 128 workers the fault-mix trial is run once
        # with a 600 s wall cap: the prototype's per-grant
        # history scan (profiled, see EXP043_REPORT) makes
        # an uncapped run a multi-hour outlier, and a
        # capped non-completion is itself the measurement
        # at that scale. It is recorded as CAPPED with its
        # accounting open, never averaged with completed
        # trials.
        fault_plan = [(43000 + n_workers * 100 + t, None)
                      for t in range(3)]
        if n_workers == 128:
            fault_plan = [(44300, 600)]
        for seed, cap in fault_plan:
            try:
                r = run_trial(seed, n_workers, faults=True,
                              wall_cap_s=cap)
            except AssertionError as exc:
                r = {"seed": seed, "workers": n_workers,
                     "faults": True, "status": "FAILED",
                     "error": str(exc)[:200],
                     "accounting_closed": False}
            payload["trials"].append(r)
            print("trial", r.get("status"), "w",
                  n_workers, "seed", seed,
                  r.get("wall_s"), "s", flush=True)
        try:
            r = run_trial(43900 + n_workers, n_workers,
                          faults=False)
        except AssertionError as exc:
            r = {"seed": 43900 + n_workers,
                 "workers": n_workers, "faults": False,
                 "status": "FAILED",
                 "error": str(exc)[:200],
                 "accounting_closed": False}
        payload["trials"].append(r)
        print("trial", r.get("status"), "w", n_workers,
              "no-fault", r.get("wall_s"), "s", flush=True)
    payload["loadavg_at_end"] = loadavg()
    path = write_result("campaign", payload)
    print("WROTE", path)


if __name__ == "__main__":
    main()
