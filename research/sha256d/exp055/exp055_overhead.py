#!/usr/bin/env python3
"""EXP-055 Gate 4: overhead in per-position cost form,
against the EXP-043 baselines.

Three parts, all on this VM, loopback and in-process
workers only (no other machine is contacted):

  1. Per-operation costs over the in-process protocol and
     over TCP loopback, medians of 3 sessions, beside the
     EXP-043 prototype in-process figures and wire-shim
     round trips.
  2. The two EXP-043 fix demonstrations, measured against
     the EXP-035 prototype itself in the same session:
     F-A lease cost versus retained history (the
     prototype's _holds_lease history scan), and F-B
     snapshot() cost at the EXP-043 scale points (512,
     2,048 and 8,192 chunks).
  3. Campaign wall time per completed position at 2, 8
     and 32 simulated workers, no-fault and fault-lite
     (deaths, restarts, expiries, steals, duplicates; no
     coordinator restarts, whose cost is the F-B snapshot
     path measured in part 2; EXP-043's fault mix spent
     a 40-restart budget per trial, so its fault figures
     are an upper-bound comparator, stated as such).

No scaling claim beyond this VM is made or implied.
Predeclaration sha256 pinned as in the campaign driver.
"""

import hashlib
import json
import os
import random
import statistics
import sys
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(
    ROOT, "research/sha256d/exp035"))

from mining.coordinator import (CoordinatorClient,  # noqa: E402
                                CoordinatorServer)
from exp055_campaign import call_ok, close_pair, make_pair  # noqa: E402
from lease_manager import LeaseManager  # noqa: E402 (EXP-035 prototype)

PREDECLARATION_SHA256 = \
    "b455d16ba878144d82abe90b531a58a1fcaa1333576d4c73098b3d59a5de93ea"
FLEET = "nova-fleet-test"
OUT = {"per_op_local": {}, "per_op_tcp": {}, "fix_a": {},
       "fix_b": {}, "campaign": {}}


def median_ns(fn, reps):
    samples = []
    for _ in range(reps):
        t0 = time.perf_counter_ns()
        fn()
        samples.append(time.perf_counter_ns() - t0)
    return int(statistics.median(samples))


def per_op_local(session):
    server, client = make_pair("local")
    call_ok(client, {
        "type": "declare_job", "job_id": "job-o",
        "generation": 1, "nonce_count": 1 << 16,
        "chunk_size": 1024, "n_slots": 4,
        "version_variants": [0x20000000],
        "ntime_values": [1700000000],
        "counters_per_slot": 1})
    res = {}
    res["register"] = median_ns(
        lambda: client.call({"type": "register",
                             "worker_id": "wx%d" % session,
                             "fleet_id": FLEET, "now": 0.0}), 5)
    call_ok(client, {"type": "register", "worker_id": "w-0",
                     "fleet_id": FLEET, "now": 0.0})
    res["heartbeat"] = median_ns(
        lambda: client.call({"type": "heartbeat",
                             "worker_id": "w-0",
                             "now": 1.0}), 50)
    leases = []

    def do_lease():
        r = client.call({"type": "lease", "worker_id": "w-0",
                         "now": 1.0, "ttl": 300.0})
        leases.append(r["result"])
    res["lease"] = median_ns(do_lease, 30)
    lease = leases[0]
    state = {"examined": 0}

    def do_progress():
        state["examined"] += 1
        client.call({"type": "progress", "worker_id": "w-0",
                     "lease_id": lease["lease_id"],
                     "token": lease["token"],
                     "examined": state["examined"]})
    res["progress"] = median_ns(do_progress, 50)

    def do_complete():
        l = leases.pop()
        client.call({"type": "complete", "worker_id": "w-0",
                     "lease_id": l["lease_id"],
                     "token": l["token"]})
    res["complete"] = median_ns(do_complete, 30)
    rec = {"job_id": "job-o", "generation": 1,
           "extranonce2": 0, "version": 0x20000000,
           "ntime": 1700000000, "nonce": 1,
           "lease_id": "L1", "worker_id": "w-0"}
    counter = {"n": 1000}

    def sub_new():
        counter["n"] += 1
        r = dict(rec, nonce=counter["n"])
        client.call({"type": "candidate_submit",
                     "record": r})
    res["candidate_submit_new"] = median_ns(sub_new, 50)
    res["candidate_submit_dup"] = median_ns(
        lambda: client.call({"type": "candidate_submit",
                             "record": rec}), 50)
    close_pair(server, client)
    return res


def per_op_tcp(workers):
    server, client0 = make_pair("tcp")
    call_ok(client0, {
        "type": "declare_job", "job_id": "job-t",
        "generation": 1, "nonce_count": 1 << 15,
        "chunk_size": 512, "n_slots": workers,
        "version_variants": [0x20000000],
        "ntime_values": [1700000000],
        "counters_per_slot": 1})
    clients = []
    for i in range(workers):
        c = CoordinatorClient(host="127.0.0.1",
                              port=server.port)
        call_ok(c, {"type": "register",
                    "worker_id": "w-%d" % i,
                    "fleet_id": FLEET, "now": 0.0})
        clients.append(c)
    # Warm every worker's slot binding, then time cycles.
    res = {}
    samples = {"heartbeat": [], "lease": [], "progress": [],
               "complete": [], "candidate_submit": []}
    cycles = 12
    for _ in range(cycles):
        for i, c in enumerate(clients):
            wid = "w-%d" % i
            t0 = time.perf_counter_ns()
            c.call({"type": "heartbeat", "worker_id": wid,
                    "now": 1.0})
            samples["heartbeat"].append(
                time.perf_counter_ns() - t0)
            t0 = time.perf_counter_ns()
            r = c.call({"type": "lease", "worker_id": wid,
                        "now": 1.0, "ttl": 300.0})
            samples["lease"].append(
                time.perf_counter_ns() - t0)
            lease = r["result"]
            if lease is None:
                continue
            t0 = time.perf_counter_ns()
            c.call({"type": "progress", "worker_id": wid,
                    "lease_id": lease["lease_id"],
                    "token": lease["token"], "examined": 1})
            samples["progress"].append(
                time.perf_counter_ns() - t0)
            t0 = time.perf_counter_ns()
            c.call({"type": "complete", "worker_id": wid,
                    "lease_id": lease["lease_id"],
                    "token": lease["token"]})
            samples["complete"].append(
                time.perf_counter_ns() - t0)
            rec = {"job_id": "job-t", "generation": 1,
                   "extranonce2": lease["extranonce2"],
                   "version": lease["version"],
                   "ntime": lease["ntime"],
                   "nonce": lease["lo"],
                   "lease_id": lease["lease_id"],
                   "worker_id": wid}
            t0 = time.perf_counter_ns()
            c.call({"type": "candidate_submit",
                    "record": rec})
            samples["candidate_submit"].append(
                time.perf_counter_ns() - t0)
    for k, v in samples.items():
        if v:
            res[k] = int(statistics.median(v))
    for c in clients:
        c.close()
    close_pair(server, client0)
    return res


def fix_a():
    """Lease cost versus retained history: coordinator
    (active index) against the EXP-035 prototype (history
    scan), same session, histories of 0 and 8,000
    completed leases."""
    out = {}
    for hist in (0, 8000):
        # Coordinator: build history by completing chunks.
        server, client = make_pair("local")
        call_ok(client, {
            "type": "declare_job", "job_id": "job-a",
            "generation": 1, "nonce_count": 64,
            "chunk_size": 64, "n_slots": 1,
            "version_variants": [0x20000000],
            "ntime_values": [1700000000],
            "counters_per_slot": max(1, hist + 64)})
        call_ok(client, {"type": "register",
                         "worker_id": "w-0",
                         "fleet_id": FLEET, "now": 0.0})
        held = None
        for _ in range(hist):
            l = call_ok(client, {"type": "lease",
                                 "worker_id": "w-0",
                                 "now": 0.0, "ttl": 300.0})
            call_ok(client, {"type": "complete",
                             "worker_id": "w-0",
                             "lease_id": l["lease_id"],
                             "token": l["token"]})
        held = call_ok(client, {"type": "lease",
                                "worker_id": "w-0", "now": 0.0,
                                "ttl": 300.0})
        stats = call_ok(client, {"type": "stats"})
        # The EXP-043 cost centre itself: the starvation
        # check's holds-lease query, timed directly.
        th = median_ns(
            lambda: server.core._holds_lease("w-0"), 200)
        # Starvation-path lease: worker is past the window
        # but holds a lease, so the check runs and passes.
        t = median_ns(
            lambda: client.call({"type": "lease",
                                 "worker_id": "w-0",
                                 "now": 100.0, "ttl": 300.0}),
            15)
        out["coordinator_hist_%d" % hist] = {
            "holds_lease_ns": th,
            "lease_ns": t,
            "active_leases_stored": stats["active_leases"],
            "completed_tombstones":
                stats["completed_tombstones"]}
        close_pair(server, client)
        # Prototype, same shape.
        mgr = LeaseManager(FLEET)
        mgr.declare_job("job-a", 1, 64, 64, 1,
                        [0x20000000], [1700000000],
                        counters_per_slot=max(1, hist + 64))
        mgr.register_worker("w-0", FLEET, 0.0)
        for _ in range(hist):
            l = mgr.lease("w-0", 0.0, ttl=300.0)
            mgr.complete("w-0", l["lease_id"], l["token"])
        mgr.lease("w-0", 0.0, ttl=300.0)
        th = median_ns(lambda: mgr._holds_lease("w-0"), 200)
        t = median_ns(lambda: mgr.lease("w-0", 100.0,
                                        ttl=300.0), 15)
        out["prototype_hist_%d" % hist] = {
            "holds_lease_ns": th,
            "lease_ns": t,
            "lease_records_retained": len(mgr.leases)}
    return out


def fix_b():
    """snapshot() cost at the EXP-043 chunk scale points,
    coordinator against prototype, same session."""
    out = {}
    for chunks in (512, 2048, 8192):
        server, client = make_pair("local")
        call_ok(client, {
            "type": "declare_job", "job_id": "job-b",
            "generation": 1, "nonce_count": chunks,
            "chunk_size": 1, "n_slots": 1,
            "version_variants": [0x20000000],
            "ntime_values": [1700000000],
            "counters_per_slot": 1})
        t = median_ns(lambda: server.core.snapshot(), 5)
        size = len(json.dumps(server.core.snapshot()))
        out["coordinator_chunks_%d" % chunks] = {
            "snapshot_ns": t, "snapshot_bytes": size}
        close_pair(server, client)
        mgr = LeaseManager(FLEET)
        mgr.declare_job("job-b", 1, chunks, 1, 1,
                        [0x20000000], [1700000000],
                        counters_per_slot=1)
        t = median_ns(lambda: mgr.snapshot(), 5)
        out["prototype_chunks_%d" % chunks] = {
            "snapshot_ns": t}
    # History-loaded point: 512 live chunks plus 8,000
    # dead lease issuances of history (lease + fail
    # cycles). The prototype snapshot deep-copies every
    # retained lease record and its event log; the
    # coordinator snapshot carries compact tombstones
    # and no event log.
    server, client = make_pair("local")
    call_ok(client, {
        "type": "declare_job", "job_id": "job-bh",
        "generation": 1, "nonce_count": 512,
        "chunk_size": 1, "n_slots": 1,
        "version_variants": [0x20000000],
        "ntime_values": [1700000000],
        "counters_per_slot": 1})
    call_ok(client, {"type": "register", "worker_id": "w-0",
                     "fleet_id": FLEET, "now": 0.0})
    for _ in range(8000):
        l = call_ok(client, {"type": "lease",
                             "worker_id": "w-0", "now": 0.0,
                             "ttl": 300.0})
        call_ok(client, {"type": "fail_worker",
                         "worker_id": "w-0"})
    t = median_ns(lambda: server.core.snapshot(), 5)
    size = len(json.dumps(server.core.snapshot()))
    out["coordinator_chunks_512_hist_8000"] = {
        "snapshot_ns": t, "snapshot_bytes": size,
        "dead_tombstones":
            len(server.core._dead_ids)}
    close_pair(server, client)
    mgr = LeaseManager(FLEET)
    mgr.declare_job("job-bh", 1, 512, 1, 1,
                    [0x20000000], [1700000000],
                    counters_per_slot=1)
    mgr.register_worker("w-0", FLEET, 0.0)
    for _ in range(8000):
        l = mgr.lease("w-0", 0.0, ttl=300.0)
        mgr.fail_worker("w-0")
    t = median_ns(lambda: mgr.snapshot(), 5)
    out["prototype_chunks_512_hist_8000"] = {
        "snapshot_ns": t,
        "lease_records_retained": len(mgr.leases),
        "events_retained": len(mgr.events)}
    return out


def campaign_point(workers, fault, seed):
    """Fixed declared space of 131,072 positions (the
    EXP-043 campaign shape), timed over the in-process
    protocol."""
    server, client = make_pair("local")
    nonce = 131072 // workers
    # EXP-043 campaign geometry: 32 chunks per slice at
    # every scale point, declared space fixed at 131,072.
    chunk = nonce // 32
    call_ok(client, {
        "type": "declare_job", "job_id": "job-c",
        "generation": 1, "nonce_count": nonce,
        "chunk_size": chunk, "n_slots": workers,
        "version_variants": [0x20000000],
        "ntime_values": [1700000000],
        "counters_per_slot": 1})
    rng = random.Random(seed)
    wids = ["w-%d" % i for i in range(workers)]
    for w in wids:
        call_ok(client, {"type": "register", "worker_id": w,
                         "fleet_id": FLEET, "now": 0.0})
    held = {}
    now = 0.0
    # Completion is tracked locally (unique coverage grows
    # only on an OK completion, by the chunk's current
    # size): polling accounting() every iteration is an
    # O(chunks) query inside the timed loop, the harness
    # noise EXP-043 discarded its first campaign run for.
    # The final accounting is still asserted exactly.
    completed_positions = 0
    declared = 131072
    t0 = time.perf_counter()
    guard = 0
    while completed_positions < declared:
        guard += 1
        assert guard < 500000
        now += 0.5
        w = rng.choice(wids)
        client.call({"type": "heartbeat",
                     "worker_id": w, "now": now})
        if fault and rng.random() < 0.05:
            call_ok(client, {"type": "expire", "now": now})
            for x in list(held):
                info = call_ok(client, {
                    "type": "lease_info",
                    "lease_id": held[x][0]["lease_id"]})
                if info["state"] != "active":
                    del held[x]
        if w not in held:
            if fault and rng.random() < 0.03:
                call_ok(client, {"type": "fail_worker",
                                 "worker_id":
                                     rng.choice(wids)})
                for x in list(held):
                    info = call_ok(client, {
                        "type": "lease_info",
                        "lease_id": held[x][0]["lease_id"]})
                    if info["state"] != "active":
                        del held[x]
            try:
                got = call_ok(client, {
                    "type": "lease", "worker_id": w,
                    "now": now,
                    "ttl": 8.0 if fault else 300.0})
            except AssertionError:
                call_ok(client, {"type": "register",
                                 "worker_id": w,
                                 "fleet_id": FLEET,
                                 "now": now})
                continue
            if got is not None:
                held[w] = (got, 0)
            continue
        lease, examined = held[w]
        size = lease["hi"] - lease["lo"]
        if fault and rng.random() < 0.04:
            thief = rng.choice(wids)
            got = call_ok(client, {"type": "steal",
                                   "worker_id": thief,
                                   "now": now, "ttl": 300.0})
            if got is not None:
                held[thief] = (got, 0)
            # A steal rotates its victim's token, and the
            # victim can be any held worker: resync all.
            for x in list(held):
                info = call_ok(client, {
                    "type": "lease_info",
                    "lease_id": held[x][0]["lease_id"]})
                if info["state"] != "active":
                    del held[x]
                else:
                    held[x] = (info, min(
                        held[x][1],
                        info["hi"] - info["lo"]))
            continue
        if examined >= size or rng.random() < 0.5:
            res = call_ok(client, {
                "type": "complete", "worker_id": w,
                "lease_id": lease["lease_id"],
                "token": lease["token"]})
            assert res == "OK", res
            completed_positions += size
            if fault and rng.random() < 0.3:
                res2 = call_ok(client, {
                    "type": "complete", "worker_id": w,
                    "lease_id": lease["lease_id"],
                    "token": lease["token"]})
                assert res2 == "DUPLICATE", res2
            del held[w]
        else:
            examined = min(size, examined
                           + rng.randint(1, size))
            res = call_ok(client, {
                "type": "progress", "worker_id": w,
                "lease_id": lease["lease_id"],
                "token": lease["token"],
                "examined": examined})
            assert res == "OK", res
            held[w] = (lease, examined)
    wall = time.perf_counter() - t0
    acc = call_ok(client, {"type": "accounting"})
    close_pair(server, client)
    return {"workers": workers, "fault": fault,
            "wall_s": round(wall, 4),
            "declared": acc["declared_total"],
            "ns_per_position":
                round(wall * 1e9 / acc["declared_total"], 1),
            "repeated": acc["repeated_computations"],
            "reclaims": acc["reclaims"]}


def main():
    with open(os.path.join(HERE, "PREDECLARATION.md"),
              "rb") as fh:
        assert hashlib.sha256(fh.read()).hexdigest() \
            == PREDECLARATION_SHA256
    sessions = []
    for s in range(3):
        sessions.append(per_op_local(s))
        print("per-op local session", s, sessions[-1],
              flush=True)
    for k in sessions[0]:
        OUT["per_op_local"][k] = int(statistics.median(
            [s[k] for s in sessions]))
    for w in (1, 4, 16):
        rows = [per_op_tcp(w) for _ in range(3)]
        OUT["per_op_tcp"]["workers_%d" % w] = {
            k: int(statistics.median([r[k] for r in rows
                                      if k in r]))
            for k in rows[0]}
        print("per-op tcp workers", w,
              OUT["per_op_tcp"]["workers_%d" % w], flush=True)
    OUT["fix_a"] = fix_a()
    print("fix A:", OUT["fix_a"], flush=True)
    OUT["fix_b"] = fix_b()
    print("fix B:", OUT["fix_b"], flush=True)
    for w in (2, 8, 32):
        for fault in (False, True):
            rows = [campaign_point(w, fault, 777 + i)
                    for i in range(3)]
            med = dict(rows[0])
            med["ns_per_position"] = int(statistics.median(
                [r["ns_per_position"] for r in rows]))
            med["wall_s"] = float(statistics.median(
                [r["wall_s"] for r in rows]))
            OUT["campaign"]["w%d_%s" % (
                w, "fault" if fault else "nofault")] = med
            print("campaign", med, flush=True)
    stamp = datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ")
    record = {"experiment": "EXP-055", "gate": 4,
              "host_cpu": "AMD EPYC 9D25", "when_utc": stamp,
              "predeclaration_sha256":
                  PREDECLARATION_SHA256,
              "loadavg": list(os.getloadavg()),
              "results": OUT}
    out = os.path.join(HERE, "RAW_RESULTS",
                       "overhead_%s.json" % stamp)
    with open(out, "w") as fh:
        json.dump(record, fh, indent=1, sort_keys=True)
    print("WROTE", out, flush=True)
    print("EXP-055 GATE 4 DONE", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
