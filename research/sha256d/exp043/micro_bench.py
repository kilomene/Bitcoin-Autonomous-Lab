#!/usr/bin/env python3
"""EXP-043 part 1: in-process operation cost micro-benchmarks.

Times the EXP-035 prototype's own calls with
time.perf_counter_ns: worker registration, heartbeat,
lease grant, progress report, completion, expiry sweep
(idle scan and mass reclaim), steal, coordinator snapshot
and restore (the checkpoint path), job declaration, and
the candidate queue operations (submit new, submit
duplicate, journalled submit, drain, journal recovery).

Everything is in-process on this one VM. No production
code is touched, no fleet agent is contacted. Simulated
workers are local method calls.

Run once per session; the study runs it at least 3 times
and reports medians across sessions.
"""

import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from exp043_common import FLEET, dist, manifest, \
    write_result  # noqa: E402

from lease_manager import LeaseManager  # noqa: E402
from candidate_queue import CandidateQueue  # noqa: E402

NS = time.perf_counter_ns
VERSION = 0x20000000
NTIME = 1700000000


def timed(fn):
    t0 = NS()
    out = fn()
    return out, NS() - t0


def fresh_manager(n_workers, nonce_per_slice, chunk):
    mgr = LeaseManager(FLEET)
    mgr.declare_job("job-micro", 1, nonce_per_slice, chunk,
                    n_workers, [VERSION], [NTIME])
    wids = ["w%d" % i for i in range(n_workers)]
    for wid in wids:
        mgr.register_worker(wid, FLEET, 0.0)
    return mgr, wids


def lease_all(mgr, wid, now=0.0):
    out = []
    while True:
        got = mgr.lease(wid, now)
        if got is None:
            return out
        out.append(got)


def bench_register():
    """Sequential registration of 512 workers into one
    manager; per-call samples bucketed by registry size."""
    mgr = LeaseManager(FLEET)
    samples = []
    for i in range(512):
        _, dt = timed(lambda: mgr.register_worker(
            "w%d" % i, FLEET, 0.0))
        samples.append(dt)
    buckets = {}
    for lo, hi in ((0, 8), (8, 32), (32, 128), (128, 512)):
        buckets["reg_%d_%d" % (lo, hi)] = dist(samples[lo:hi])
    return buckets


def bench_config(n_workers, nonce_per_slice, chunk,
                 label):
    """One (workers, space) scale point."""
    res = {"label": label, "workers": n_workers,
           "nonce_per_slice": nonce_per_slice,
           "chunk": chunk,
           "total_space": n_workers * nonce_per_slice,
           "total_chunks": n_workers
           * (nonce_per_slice // chunk)}

    # Job declaration (setup cost), 5 fresh repetitions.
    decl = []
    for _ in range(5):
        m = LeaseManager(FLEET)
        _, dt = timed(lambda: m.declare_job(
            "job-micro", 1, nonce_per_slice, chunk,
            n_workers, [VERSION], [NTIME]))
        decl.append(dt)
    res["declare_job"] = dist(decl)

    mgr, wids = fresh_manager(n_workers, nonce_per_slice,
                              chunk)
    first, last = wids[0], wids[-1]

    # Heartbeats round-robin across the registry.
    hb = []
    for i in range(2000):
        wid = wids[i % n_workers]
        _, dt = timed(lambda: mgr.heartbeat(wid, 0.0))
        hb.append(dt)
    res["heartbeat"] = dist(hb)

    # Lease grants: first worker and last worker each drain
    # their own slice; every grant timed individually.
    grants = {}
    slice_tags = [("first_slice", first)]
    if last != first:
        slice_tags.append(("last_slice", last))
    for tag, wid in slice_tags:
        samples = []
        while True:
            got, dt = timed(lambda: mgr.lease(wid, 0.0))
            if got is None:
                break
            samples.append(dt)
        k = max(1, len(samples) // 8)
        grants[tag] = {
            "all": dist(samples),
            "first_eighth_median_ns":
                dist(samples[:k])["median_ns"],
            "last_eighth_median_ns":
                dist(samples[-k:])["median_ns"],
        }
    res["lease_grant"] = grants

    # Progress reports on the last worker's first lease:
    # examined climbs 1..chunk, each report timed.
    last_leases = [l for l in mgr.leases.values()
                   if l["worker"] == last
                   and l["state"] == "active"]
    lease = last_leases[0]
    prog = []
    for examined in range(1, chunk + 1):
        _, dt = timed(lambda: mgr.progress(
            last, lease["lease_id"], lease["token"],
            examined))
        prog.append(dt)
    res["progress"] = dist(prog)

    # Completions: last worker's remaining leases, then
    # first worker's leases, each timed.
    comp = {}
    for tag, wid in (("last_slice", last),
                     ("first_slice", first)):
        samples = []
        mine = [l for l in mgr.leases.values()
                if l["worker"] == wid
                and l["state"] == "active"]
        for l in mine:
            _, dt = timed(lambda: mgr.complete(
                wid, l["lease_id"], l["token"]))
            samples.append(dt)
        comp[tag] = dist(samples)
    res["complete"] = comp

    # Coordinator checkpoint: snapshot and restore at this
    # scale, mid-state (half the chunks leased again).
    for wid in wids:
        lease_all(mgr, wid)
    snaps = []
    for _ in range(20):
        _, dt = timed(mgr.snapshot)
        snaps.append(dt)
    res["snapshot"] = dist(snaps)
    rests = []
    for _ in range(10):
        snap = mgr.snapshot()
        _, dt = timed(lambda: LeaseManager.restore(snap))
        rests.append(dt)
    res["restore"] = dist(rests)
    return res


def bench_expire():
    """Expiry sweep cost: idle scan over many active
    leases, and mass reclaim when all deadlines pass."""
    res = {}
    for n_workers, nonce, chunk in ((32, 8192, 128),
                                    (128, 8192, 128)):
        label = "w%d" % n_workers
        mgr, wids = fresh_manager(n_workers, nonce, chunk)
        for wid in wids:
            lease_all(mgr, wid)
        n_active = sum(1 for l in mgr.leases.values()
                       if l["state"] == "active")
        idle = []
        for _ in range(5):
            out, dt = timed(lambda: mgr.expire(0.0))
            assert out == []
            idle.append(dt)
        _, dt = timed(lambda: mgr.expire(10000.0))
        n_reclaimed = sum(1 for l in mgr.leases.values()
                          if l["state"] == "reclaimed")
        res[label] = {
            "active_leases": n_active,
            "expire_idle_scan": dist(idle),
            "expire_mass_reclaim_total_ns": dt,
            "expire_mass_reclaim_count": n_reclaimed,
            "per_reclaim_ns": dt // max(1, n_reclaimed),
        }
    return res


def bench_steal(samples=200):
    """Steal: victim holds one large chunk, half reported;
    each sample uses a fresh manager so the state is
    identical."""
    out = []
    for _ in range(samples):
        mgr = LeaseManager(FLEET)
        mgr.declare_job("job-steal", 1, 65536, 65536, 2,
                        [VERSION], [NTIME])
        mgr.register_worker("victim", FLEET, 0.0)
        mgr.register_worker("thief", FLEET, 0.0)
        lease = mgr.lease("victim", 0.0)
        mgr.progress("victim", lease["lease_id"],
                     lease["token"], 32768)
        _, dt = timed(lambda: mgr.steal("thief", 0.0))
        out.append(dt)
    return dist(out)


def bench_candidate_queue():
    res = {}

    def rec(nonce, lease_id="L1"):
        return {"job_id": "job-micro", "generation": 1,
                "extranonce2": 0, "version": VERSION,
                "ntime": NTIME, "nonce": nonce,
                "lease_id": lease_id, "worker_id": "w0"}

    # Submit new: 20,000 unique records, bucketed by the
    # size of the seen-history the dedup check runs
    # against.
    q = CandidateQueue()
    samples = []
    for i in range(20000):
        _, dt = timed(lambda: q.submit(rec(i)))
        samples.append(dt)
    res["submit_new_all"] = dist(samples)
    for lo, hi in ((0, 100), (900, 1000), (9900, 10000),
                   (19900, 20000)):
        res["submit_new_seen_%d" % hi] = dist(samples[lo:hi])

    # Duplicate submissions against the full history.
    dups = []
    for i in range(5000):
        _, dt = timed(lambda: q.submit(rec(i)))
        dups.append(dt)
    res["submit_duplicate"] = dist(dups)
    assert q.stats()["duplicates"] == 5000

    # Journalled submit: the persist-before-acknowledge
    # write (open, append one JSON line, close) per event.
    jpath = os.path.join("/tmp",
                         "exp043_journal_%d.jsonl" % os.getpid())
    if os.path.exists(jpath):
        os.remove(jpath)
    qj = CandidateQueue(journal_path=jpath)
    jsamples = []
    for i in range(5000):
        _, dt = timed(lambda: qj.submit(rec(i)))
        jsamples.append(dt)
    res["submit_journalled"] = dist(jsamples)

    # Journal recovery (checkpoint read path).
    for n in (1000, 5000):
        jp = os.path.join("/tmp",
                          "exp043_rec_%d_%d.jsonl"
                          % (os.getpid(), n))
        if os.path.exists(jp):
            os.remove(jp)
        qq = CandidateQueue(journal_path=jp)
        for i in range(n):
            qq.submit(rec(i))
        _, dt = timed(lambda: CandidateQueue.recover(jp))
        res["journal_recover_%d" % n] = {
            "total_ns": dt, "records": n,
            "per_record_ns": dt // n}
        os.remove(jp)
    os.remove(jpath)

    # Drain throughput with a trivial verifier.
    for n in (1000, 20000):
        qd = CandidateQueue()
        for i in range(n):
            qd.submit(rec(i))
        _, dt = timed(lambda: qd.drain(
            lambda r: "share", current_generation=1))
        res["drain_%d" % n] = {"total_ns": dt,
                               "records": n,
                               "per_record_ns": dt // n}
    return res


def main():
    payload = manifest("micro_bench_in_process")
    payload["register"] = bench_register()
    payload["configs"] = [
        bench_config(w, 8192, 128, "workers_%d" % w)
        for w in (1, 8, 32, 128)
    ]
    payload["space_sweep"] = [
        bench_config(8, nonce, nonce // 64,
                     "space_%d" % (8 * nonce))
        for nonce in (128, 8192, 131072)
    ]
    payload["expire"] = bench_expire()
    payload["steal"] = bench_steal()
    payload["candidate_queue"] = bench_candidate_queue()
    from exp043_common import loadavg
    payload["loadavg_at_end"] = loadavg()
    path = write_result("micro", payload)
    print("WROTE", path)


if __name__ == "__main__":
    main()
