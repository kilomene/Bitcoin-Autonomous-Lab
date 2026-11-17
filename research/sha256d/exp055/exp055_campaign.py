#!/usr/bin/env python3
"""EXP-055 Gates 1, 2, 3 and 5: protocol-level proof
obligations, differential accounting, the randomised fault
campaign, and persistent-coordinator restart.

Every operation in Gates 1 to 3 is carried over the wire
protocol (frame encode, CRC32 checksum, dispatch, frame
decode), over an in-process transport and, for Gate 1, the
Gate 3 TCP subset and Gate 5, over TCP loopback with
separate client connections. No other machine is contacted;
fleet activation is owner-gated (roadmap F2) and out of
scope. Predeclaration: PREDECLARATION.md in this directory,
sha256 pinned below and recorded in the run manifest.
"""

import hashlib
import json
import os
import random
import sys
import threading
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from mining.coordinator import (CoordinatorClient,  # noqa: E402
                                CoordinatorServer,
                                encode_frame)
from exp055_model import Model, ModelError  # noqa: E402

PREDECLARATION_SHA256 = \
    "b455d16ba878144d82abe90b531a58a1fcaa1333576d4c73098b3d59a5de93ea"
FLEET = "nova-fleet-test"
RESULTS = {"gate1": {}, "gate2": {}, "gate3": {}, "gate5": {}}


def check_predeclaration():
    with open(os.path.join(HERE, "PREDECLARATION.md"),
              "rb") as fh:
        digest = hashlib.sha256(fh.read()).hexdigest()
    assert digest == PREDECLARATION_SHA256, (
        "predeclaration hash mismatch: %s" % digest)
    return digest


# ------------------------------------------------------------------
# Transport helpers
# ------------------------------------------------------------------

def start_tcp(server):
    t = threading.Thread(target=server.serve,
                         args=("127.0.0.1", 0), daemon=True)
    t.start()
    for _ in range(200):
        if getattr(server, "port", None):
            return server.port
        time.sleep(0.01)
    raise RuntimeError("TCP server did not bind")


def stop_tcp(server):
    try:
        server._tcp.close()
    except Exception:
        pass


def make_pair(transport, verifier=None, state_dir=None):
    server = CoordinatorServer(FLEET, state_dir=state_dir,
                               verifier=verifier)
    if transport == "tcp":
        port = start_tcp(server)
        return server, CoordinatorClient(host="127.0.0.1",
                                         port=port)
    return server, CoordinatorClient(server=server)


def close_pair(server, client):
    try:
        client.close()
    except Exception:
        pass
    stop_tcp(server)
    server.close()


def call_ok(client, msg):
    resp = client.call(msg)
    assert resp.get("ok"), resp
    return resp["result"]


def check_completed(client):
    """P1, P2, P4 for a finished job, from protocol queries."""
    assert call_ok(client, {"type": "partition_check"}) is True
    per_slice = {}
    for key, lo, hi in call_ok(
            client, {"type": "completed_intervals"}):
        per_slice.setdefault(tuple(key), []).append((lo, hi))
    acc = call_ok(client, {"type": "accounting"})
    total = 0
    for key, ivs in per_slice.items():
        ivs.sort()
        assert ivs[0][0] == 0, (key, ivs)
        for (a_lo, a_hi), (b_lo, _b) in zip(ivs, ivs[1:]):
            assert a_hi == b_lo, ("gap/overlap", key, ivs)
        total += sum(hi - lo for lo, hi in ivs)
    assert total == acc["declared_total"], \
        (total, acc["declared_total"])
    assert acc["complete"], acc
    assert acc["unique_coverage"] == acc["declared_total"]
    assert acc["pending"] == 0 and acc["leased"] == 0
    assert acc["actual_computations"] >= acc["unique_coverage"]
    return acc


def small_pair(transport, nonce=256, chunk=64, slots=2,
               versions=(0x20000000,), ntimes=(1700000000,),
               counters=1, verifier=None):
    server, client = make_pair(transport, verifier=verifier)
    call_ok(client, {
        "type": "declare_job", "job_id": "job-1",
        "generation": 1, "nonce_count": nonce,
        "chunk_size": chunk, "n_slots": slots,
        "version_variants": list(versions),
        "ntime_values": list(ntimes),
        "counters_per_slot": counters})
    return server, client


def reg(client, wid, now=0.0):
    return call_ok(client, {"type": "register",
                            "worker_id": wid,
                            "fleet_id": FLEET, "now": now})


def do_lease(client, wid, now, ttl=30.0):
    return call_ok(client, {"type": "lease", "worker_id": wid,
                            "now": now, "ttl": ttl})


def do_complete(client, wid, lease, token=None):
    return call_ok(client, {
        "type": "complete", "worker_id": wid,
        "lease_id": lease["lease_id"],
        "token": lease["token"] if token is None else token})


def do_progress(client, wid, lease, examined):
    return call_ok(client, {
        "type": "progress", "worker_id": wid,
        "lease_id": lease["lease_id"],
        "token": lease["token"], "examined": examined})


# ------------------------------------------------------------------
# Gate 1: targeted tests at the protocol level
# ------------------------------------------------------------------

def t_foreign_fleet_rejected(client, server):
    resp = client.call({"type": "register", "worker_id": "w-x",
                        "fleet_id": "other-fleet", "now": 0.0})
    assert resp["ok"] is False \
        and resp["error"] == "FOREIGN_FLEET", resp
    assert reg(client, "w-0") == "REGISTERED"


def t_duplicate_completion_idempotent(client, server):
    reg(client, "w-0")
    lease = do_lease(client, "w-0", 0.0)
    assert do_complete(client, "w-0", lease) == "OK"
    assert do_complete(client, "w-0", lease) == "DUPLICATE"
    acc = call_ok(client, {"type": "accounting"})
    assert acc["unique_coverage"] == 64, acc
    assert acc["duplicate_deliveries"] == 1, acc


def t_restart_replay_never_credited(client, server):
    reg(client, "w-0")
    reg(client, "w-1")
    lease = do_lease(client, "w-0", 0.0)
    assert do_progress(client, "w-0", lease, 32) == "OK"
    call_ok(client, {"type": "worker_restarted",
                     "worker_id": "w-0", "now": 1.0})
    assert do_complete(client, "w-0", lease) == "STALE"
    acc = call_ok(client, {"type": "accounting"})
    assert acc["unique_coverage"] == 0, acc
    assert acc["stale_reports"] == 1, acc
    reg(client, "w-0", 2.0)
    lease2 = do_lease(client, "w-0", 2.0)
    assert lease2["slice"] == lease["slice"]
    assert (lease2["lo"], lease2["hi"]) \
        == (lease["lo"], lease["hi"])
    assert do_complete(client, "w-0", lease2) == "OK"
    acc = call_ok(client, {"type": "accounting"})
    assert acc["unique_coverage"] == 64, acc
    assert acc["repeated_computations"] == 32, acc


def t_lease_expiry_reclaim(client, server):
    reg(client, "w-0")
    lease = do_lease(client, "w-0", 0.0, ttl=5.0)
    assert do_progress(client, "w-0", lease, 16) == "OK"
    reclaimed = call_ok(client, {"type": "expire", "now": 6.0})
    assert lease["lease_id"] in reclaimed
    assert do_complete(client, "w-0", lease) == "STALE"
    acc = call_ok(client, {"type": "accounting"})
    assert acc["unique_coverage"] == 0, acc


def t_coordinator_restart_tokens_die(client, server):
    reg(client, "w-0")
    reg(client, "w-1")
    lease = do_lease(client, "w-0", 0.0)
    assert do_progress(client, "w-0", lease, 64) == "OK"
    call_ok(client, {"type": "restart"})
    assert do_complete(client, "w-0", lease) == "STALE"
    assert call_ok(client, {"type": "accounting"})[
        "unique_coverage"] == 0
    reg(client, "w-0", 10.0)
    reg(client, "w-1", 10.0)
    guard = 0
    while not call_ok(client, {"type": "accounting"})[
            "complete"]:
        guard += 1
        assert guard < 10000
        for w in ("w-0", "w-1"):
            got = do_lease(client, w, 10.0)
            if got is not None:
                assert do_complete(client, w, got) == "OK"
    acc = check_completed(client)
    assert acc["repeated_computations"] == 64, acc


def t_steal_and_token_rotation(client, server):
    reg(client, "w-0")
    reg(client, "w-1")
    lease = do_lease(client, "w-0", 0.0)
    assert do_progress(client, "w-0", lease, 64) == "OK"
    stolen = call_ok(client, {"type": "steal",
                              "worker_id": "w-1", "now": 1.0})
    assert stolen is not None
    assert call_ok(client, {"type": "partition_check"}) is True
    assert do_progress(client, "w-0", lease, 80) == "STALE"
    res = do_complete(client, "w-1", lease,
                      token=stolen["token"])
    assert res == "STALE", res
    info = call_ok(client, {"type": "lease_info",
                            "lease_id": lease["lease_id"]})
    before = call_ok(client, {"type": "accounting"})[
        "unique_coverage"]
    res = do_complete(client, "w-1", lease,
                      token=info["token"])
    assert res == "NOT_HOLDER", res
    assert call_ok(client, {"type": "accounting"})[
        "unique_coverage"] == before
    victim = call_ok(client, {"type": "lease_info",
                              "lease_id": lease["lease_id"]})
    assert do_complete(client, "w-0", lease,
                       token=victim["token"]) == "OK"
    assert do_complete(client, "w-1", stolen) == "OK"
    acc = call_ok(client, {"type": "accounting"})
    assert acc["unique_coverage"] == 256, acc


def t_starved_worker_reregisters(client, server):
    call_ok(client, {
        "type": "declare_job", "job_id": "job-1",
        "generation": 1, "nonce_count": 128, "chunk_size": 64,
        "n_slots": 1, "version_variants": [0x20000000],
        "ntime_values": [1700000000], "counters_per_slot": 1})
    reg(client, "w-0")
    got = do_lease(client, "w-0", 0.0)
    assert do_complete(client, "w-0", got) == "OK"
    resp = client.call({"type": "lease", "worker_id": "w-0",
                        "now": 25.0, "ttl": 30.0})
    assert resp["ok"] is False \
        and resp["error"] == "LEASE_ERROR", resp
    reg(client, "w-0", 25.0)
    assert do_lease(client, "w-0", 25.0) is not None


def t_search_space_declaration(client, server):
    n = call_ok(client, {
        "type": "declare_job", "job_id": "job-9",
        "generation": 3, "nonce_count": 1000,
        "chunk_size": 100, "n_slots": 4,
        "version_variants": [0x20000000, 0x20004000],
        "ntime_values": [1700000000, 1700000060],
        "counters_per_slot": 2})
    assert n == 32, n
    acc = call_ok(client, {"type": "accounting"})
    assert acc["declared_total"] == 32 * 1000, acc
    assert call_ok(client, {"type": "partition_check"}) is True


def t_candidate_queue(client, server):
    reg(client, "w-0")
    lease = do_lease(client, "w-0", 0.0)
    base = {"job_id": "job-1", "generation": 1,
            "extranonce2": lease["extranonce2"],
            "version": lease["version"],
            "ntime": lease["ntime"], "nonce": 42,
            "lease_id": lease["lease_id"],
            "worker_id": "w-0"}

    def sub(rec):
        return call_ok(client, {"type": "candidate_submit",
                                "record": rec})
    assert sub(dict(base)) == "ACCEPTED"
    assert sub(dict(base)) == "DUPLICATE"
    other = dict(base, extranonce2=(1 << 25))
    assert sub(other) == "ACCEPTED"
    drained = call_ok(client, {"type": "candidate_drain"})
    assert len(drained) == 2, drained
    st = call_ok(client, {"type": "queue_stats"})
    assert st["duplicates"] == 1, st
    assert st["verified"] == 2, st


def t_candidate_stale_generation(client, server):
    reg(client, "w-0")
    lease = do_lease(client, "w-0", 0.0)
    rec = {"job_id": "job-1", "generation": 0,
           "extranonce2": lease["extranonce2"],
           "version": lease["version"],
           "ntime": lease["ntime"], "nonce": 7,
           "lease_id": lease["lease_id"], "worker_id": "w-0"}
    assert call_ok(client, {"type": "candidate_submit",
                            "record": rec}) == "ACCEPTED"
    drained = call_ok(client, {"type": "candidate_drain"})
    assert drained == [], drained
    st = call_ok(client, {"type": "queue_stats"})
    assert st["stale_generation_dropped"] == 1, st
    assert st["verified"] == 0, st


def t_wire_integrity(client, server):
    good = encode_frame({"type": "ping"})
    bad = bytearray(good)
    bad[6] ^= 0xFF
    resp = client.call_raw(bytes(bad))
    assert resp["ok"] is False \
        and resp["error"] == "BAD_FRAME", resp
    if client.server is not None:
        # In-process transport: a truncated frame is a
        # complete input and is rejected outright.
        resp = client.call_raw(good[:6])
        assert resp["ok"] is False \
            and resp["error"] == "BAD_FRAME", resp
    else:
        # TCP is a stream: a truncated frame is simply
        # incomplete, the server waits, and nothing is
        # dispatched. Send one on a throwaway connection,
        # close it, and prove the coordinator is unmoved.
        import socket as _socket
        raw = _socket.create_connection(
            ("127.0.0.1", server.port))
        raw.sendall(good[:6])
        raw.close()
    stats = call_ok(client, {"type": "stats"})
    assert stats["bad_frames"] >= 1, stats
    assert call_ok(client, {"type": "ping"}) == "PONG"


GATE1 = [
    ("foreign_fleet_rejected", t_foreign_fleet_rejected,
     dict()),
    ("duplicate_completion_idempotent",
     t_duplicate_completion_idempotent, dict()),
    ("restart_replay_never_credited",
     t_restart_replay_never_credited, dict()),
    ("lease_expiry_reclaim", t_lease_expiry_reclaim, dict()),
    ("coordinator_restart_tokens_die",
     t_coordinator_restart_tokens_die, dict()),
    ("steal_and_token_rotation", t_steal_and_token_rotation,
     dict(nonce=256, chunk=256, slots=2)),
    ("starved_worker_reregisters",
     t_starved_worker_reregisters, dict()),
    ("search_space_declaration", t_search_space_declaration,
     dict()),
    ("candidate_queue", t_candidate_queue, dict()),
    ("candidate_stale_generation",
     t_candidate_stale_generation, dict()),
    ("wire_integrity", t_wire_integrity, dict()),
]


def run_gate1():
    for transport in ("local", "tcp"):
        for name, fn, kw in GATE1:
            verifier_calls = []
            server, client = small_pair(
                transport,
                verifier=lambda rec, c=verifier_calls:
                    c.append(rec) or "share", **kw)
            try:
                fn(client, server)
            finally:
                close_pair(server, client)
            key = "%s/%s" % (transport, name)
            RESULTS["gate1"][key] = "PASS"
            print("PASS gate1:", key, flush=True)


# ------------------------------------------------------------------
# Gate 2: differential accounting against the independent model
# ------------------------------------------------------------------

ACC_KEYS = ("declared_total", "unique_coverage",
            "actual_computations", "repeated_computations",
            "duplicate_deliveries", "stale_reports",
            "not_holder_attempts", "unknown_lease_reports",
            "reclaims", "pending", "leased", "complete")


def gate2_script(seed):
    rng = random.Random(seed)
    server, client = make_pair("local")
    model = Model(FLEET)
    workers = ["w0", "w1", "w2"]
    held = {}          # wid -> lease dict (coordinator view)
    dead = []          # lease dicts no longer held live
    now = 0.0
    gen = 0
    comparisons = 0

    def cmp_accounting(where):
        nonlocal comparisons
        a = call_ok(client, {"type": "accounting"})
        b = model.accounting()
        for k in ACC_KEYS:
            assert a[k] == b[k], (where, k, a[k], b[k], seed)
        ca = call_ok(client, {"type": "completed_intervals"})
        cb = model.completed_intervals()
        na = sorted((tuple(k), lo, hi) for k, lo, hi in ca)
        assert na == cb, (where, "intervals", seed)
        comparisons += 1

    def both(fn_c, fn_m, where):
        """Run one op on both; statuses or error-ness must
        agree, and returned lease shapes must be identical."""
        nonlocal comparisons
        try:
            rc = fn_c()
            ec = None
        except AssertionError:
            raise
        except Exception as exc:  # protocol error object path
            rc, ec = None, type(exc).__name__
        if isinstance(rc, dict) and rc.get("__error__"):
            ec = rc["__error__"]
            rc = None
        try:
            rm = fn_m()
            em = None
        except ModelError as exc:
            rm, em = None, type(exc).__name__
        assert (ec is None) == (em is None), \
            (where, ec, em, seed)
        comparisons += 1
        return rc, rm

    def c_call(msg):
        resp = client.call(msg)
        if not resp.get("ok"):
            return {"__error__": resp["error"]}
        return resp["result"]

    gen += 1
    args = dict(job_id="job-g2", generation=gen,
                nonce_count=rng.choice([256, 512]),
                chunk_size=rng.choice([64, 128]),
                n_slots=3,
                version_variants=[0x20000000],
                ntime_values=[1700000000],
                counters_per_slot=1)
    both(lambda: c_call({"type": "declare_job", **args}),
         lambda: model.declare_job(
             args["job_id"], args["generation"],
             args["nonce_count"], args["chunk_size"],
             args["n_slots"], args["version_variants"],
             args["ntime_values"], args["counters_per_slot"]),
         "declare")
    for w in workers:
        both(lambda w=w: c_call(
            {"type": "register", "worker_id": w,
             "fleet_id": FLEET, "now": now}),
            lambda w=w: model.register_worker(w, FLEET, now),
            "register")
    # A foreign registration must fail on both.
    resp = client.call({"type": "register", "worker_id": "wx",
                        "fleet_id": "nope", "now": now})
    assert resp["ok"] is False
    try:
        model.register_worker("wx", "nope", now)
        raise AssertionError("model accepted foreign fleet")
    except ModelError:
        pass

    steps = rng.randint(120, 220)
    for step in range(steps):
        now += rng.uniform(0.1, 2.0)
        roll = rng.random()
        w = rng.choice(workers)
        if roll < 0.06:
            both(lambda: c_call({"type": "expire", "now": now}),
                 lambda: model.expire(now), "expire")
            for wid in list(held):
                info = call_ok(client, {
                    "type": "lease_info",
                    "lease_id": held[wid]["lease_id"]})
                if info["state"] != "active":
                    dead.append(held.pop(wid))
        elif roll < 0.10:
            both(lambda w=w: c_call(
                {"type": "worker_restarted", "worker_id": w,
                 "now": now}),
                lambda w=w: model.worker_restarted(w, now),
                "worker_restarted")
            if w in held:
                dead.append(held.pop(w))
            both(lambda w=w: c_call(
                {"type": "register", "worker_id": w,
                 "fleet_id": FLEET, "now": now}),
                lambda w=w: model.register_worker(
                    w, FLEET, now), "reregister")
        elif roll < 0.14:
            both(lambda: c_call({"type": "restart"}),
                 lambda: model.coordinator_restart(),
                 "coordinator_restart")
            dead.extend(held.values())
            held.clear()
            for wid in workers:
                both(lambda wid=wid: c_call(
                    {"type": "register", "worker_id": wid,
                     "fleet_id": FLEET, "now": now}),
                    lambda wid=wid: model.register_worker(
                        wid, FLEET, now), "reregister2")
        elif roll < 0.18:
            both(lambda w=w: c_call(
                {"type": "fail_worker", "worker_id": w}),
                lambda w=w: model.fail_worker(w),
                "fail_worker")
            if w in held:
                dead.append(held.pop(w))
        elif roll < 0.24 and dead:
            zombie = rng.choice(dead)
            rc, rm = both(
                lambda zombie=zombie: c_call(
                    {"type": "complete", "worker_id": w,
                     "lease_id": zombie["lease_id"],
                     "token": zombie["token"]}),
                lambda zombie=zombie: model.complete(
                    w, zombie["lease_id"], zombie["token"]),
                "zombie_complete")
            assert rc == rm, ("zombie", rc, rm, seed)
        elif roll < 0.30 and w not in held:
            ttl = rng.choice([8.0, 30.0])
            rc, rm = both(
                lambda w=w, ttl=ttl: c_call(
                    {"type": "lease", "worker_id": w,
                     "now": now, "ttl": ttl}),
                lambda w=w, ttl=ttl: model.lease(
                    w, now, ttl=ttl), "lease")
            if isinstance(rc, dict) and rc:
                assert rc["lease_id"] == rm["lease_id"] \
                    and rc["token"] == rm["token"] \
                    and rc["lo"] == rm["lo"] \
                    and rc["hi"] == rm["hi"], (rc, rm, seed)
                held[w] = rc
        elif roll < 0.36:
            thief = rng.choice(workers)
            rc, rm = both(
                lambda thief=thief: c_call(
                    {"type": "steal", "worker_id": thief,
                     "now": now}),
                lambda thief=thief: model.steal(thief, now),
                "steal")
            if isinstance(rc, dict) and rc:
                assert rc["lease_id"] == rm["lease_id"] \
                    and rc["token"] == rm["token"], (rc, rm)
                held[thief] = rc
            # Victim lease shapes may have rotated: resync
            # every held lease from both sides' live records.
            for wid in list(held):
                info = call_ok(client, {
                    "type": "lease_info",
                    "lease_id": held[wid]["lease_id"]})
                ml = model.leases.get(held[wid]["lease_id"])
                assert ml is not None
                assert info["state"] == ml["state"], \
                    (info, ml, seed)
                if info["state"] != "active":
                    dead.append(held.pop(wid))
                else:
                    assert info["token"] == ml["token"] \
                        and info["hi"] == ml["hi"], (info, ml)
                    held[wid] = info
        elif w in held:
            lease = held[w]
            size = lease["hi"] - lease["lo"]
            if roll < 0.68:
                examined = rng.randint(0, size)
                rc, rm = both(
                    lambda lease=lease, examined=examined:
                        c_call({"type": "progress",
                                "worker_id": w,
                                "lease_id": lease["lease_id"],
                                "token": lease["token"],
                                "examined": examined}),
                    lambda lease=lease, examined=examined:
                        model.progress(
                            w, lease["lease_id"],
                            lease["token"], examined),
                    "progress")
                assert rc == rm, ("progress", rc, rm, seed)
            else:
                rc, rm = both(
                    lambda lease=lease: c_call(
                        {"type": "complete", "worker_id": w,
                         "lease_id": lease["lease_id"],
                         "token": lease["token"]}),
                    lambda lease=lease: model.complete(
                        w, lease["lease_id"], lease["token"]),
                    "complete")
                assert rc == rm, ("complete", rc, rm, seed)
                if rc == "OK":
                    dead.append(held.pop(w))
                    if rng.random() < 0.5:
                        rc2, rm2 = both(
                            lambda lease=lease: c_call(
                                {"type": "complete",
                                 "worker_id": w,
                                 "lease_id": lease["lease_id"],
                                 "token": lease["token"]}),
                            lambda lease=lease: model.complete(
                                w, lease["lease_id"],
                                lease["token"]),
                            "duplicate_complete")
                        assert rc2 == rm2 == "DUPLICATE", \
                            (rc2, rm2, seed)
        else:
            both(lambda w=w: c_call(
                {"type": "heartbeat", "worker_id": w,
                 "now": now}),
                lambda w=w: model.heartbeat(w, now),
                "heartbeat")
        if step % 25 == 0:
            cmp_accounting("step %d" % step)
    cmp_accounting("final")
    close_pair(server, client)
    return comparisons


def run_gate2():
    total = 0
    for i in range(40):
        total += gate2_script(20261120 + i)
        print("PASS gate2: script", i, flush=True)
    RESULTS["gate2"] = {"scripts": 40, "comparisons": total,
                        "all_equal": True}
    print("PASS gate2: 40 scripts,", total, "comparisons",
          flush=True)


# ------------------------------------------------------------------
# Gate 3: randomised fault campaign (EXP-035 shape, protocol level)
# ------------------------------------------------------------------

class SimWorker:
    def __init__(self, wid):
        self.wid = wid
        self.lease = None
        self.examined = 0
        self.zombie = None
        self.registered = True

    def sync(self, client):
        if self.lease is None:
            return
        info = call_ok(client, {
            "type": "lease_info",
            "lease_id": self.lease["lease_id"]})
        if info["state"] != "active":
            self.zombie = self.lease
            self.lease = None
            self.examined = 0
        else:
            self.lease = info
            size = info["hi"] - info["lo"]
            if self.examined > size:
                self.examined = size


def campaign_trial(client, server, rng, trial_no,
                   verifier_calls):
    nworkers = rng.randint(2, 4)
    nonce = rng.choice([512, 1024, 2048])
    chunk = rng.choice([64, 128, 256])
    versions = [0x20000000, 0x20004000][:rng.randint(1, 2)]
    ntimes = [1700000000, 1700000060][:rng.randint(1, 2)]
    counters = rng.randint(1, 2)
    call_ok(client, {
        "type": "declare_job",
        "job_id": "job-c%d" % trial_no, "generation": 1,
        "nonce_count": nonce, "chunk_size": chunk,
        "n_slots": nworkers, "version_variants": versions,
        "ntime_values": ntimes, "counters_per_slot": counters})
    workers = [SimWorker("w%d" % i) for i in range(nworkers)]
    now = 0.0
    for w in workers:
        reg(client, w.wid, now)
    inj = {"die": 0, "restart": 0, "dup": 0, "zombie": 0,
           "not_holder": 0, "steal": 0, "coord_restart": 0,
           "expire": 0, "cand_dup": 0}
    observed = {"dup": 0, "stale": 0, "not_holder": 0}
    submitted_identities = set()
    guard = 0
    while not call_ok(client, {"type": "accounting"})[
            "complete"]:
        guard += 1
        assert guard < 200000, "campaign did not converge"
        now += rng.uniform(0.1, 1.5)
        if rng.random() < 0.10:
            reclaimed = call_ok(client, {"type": "expire",
                                         "now": now})
            if reclaimed:
                inj["expire"] += 1
        w = rng.choice(workers)
        if w.registered:
            resp = client.call({"type": "heartbeat",
                                "worker_id": w.wid, "now": now})
            assert resp.get("ok"), resp
        w.sync(client)
        roll = rng.random()
        if w.lease is None:
            if w.zombie is not None and roll < 0.30:
                res = do_complete(client, w.wid, w.zombie)
                assert res in ("STALE", "DUPLICATE"), res
                if res == "STALE":
                    observed["stale"] += 1
                inj["zombie"] += 1
                w.zombie = None
                continue
            if not w.registered:
                reg(client, w.wid, now)
                w.registered = True
            try:
                got = do_lease(client, w.wid, now,
                               ttl=rng.choice([8.0, 30.0]))
            except AssertionError:
                reg(client, w.wid, now)
                continue
            if got is not None:
                w.lease = got
                w.examined = 0
            continue
        size = w.lease["hi"] - w.lease["lo"]
        if roll < 0.08:
            call_ok(client, {"type": "fail_worker",
                             "worker_id": w.wid})
            inj["die"] += 1
            w.sync(client)
        elif roll < 0.14:
            call_ok(client, {"type": "worker_restarted",
                             "worker_id": w.wid, "now": now})
            inj["restart"] += 1
            w.registered = False
            w.sync(client)
            reg(client, w.wid, now)
            w.registered = True
        elif roll < 0.18:
            thief = rng.choice(workers)
            if thief.wid != w.wid:
                got = call_ok(client, {
                    "type": "steal", "worker_id": thief.wid,
                    "now": now})
                if got is not None:
                    inj["steal"] += 1
                    thief.lease = got
                    thief.examined = 0
                    thief.registered = True
                    w.sync(client)
        elif roll < 0.22:
            other = rng.choice(workers)
            if other.wid != w.wid:
                res = do_complete(client, other.wid, w.lease)
                assert res in ("STALE", "NOT_HOLDER"), res
                if res == "NOT_HOLDER":
                    observed["not_holder"] += 1
                else:
                    observed["stale"] += 1
                inj["not_holder"] += 1
        elif roll < 0.25:
            call_ok(client, {"type": "restart"})
            inj["coord_restart"] += 1
            for x in workers:
                x.sync(client)
                reg(client, x.wid, now)
                x.registered = True
        elif roll < 0.45 or w.examined >= size:
            res = do_complete(client, w.wid, w.lease)
            assert res == "OK", res
            if rng.random() < 0.35:
                res2 = do_complete(client, w.wid, w.lease)
                assert res2 == "DUPLICATE", res2
                observed["dup"] += 1
                inj["dup"] += 1
            if rng.random() < 0.30:
                rec = {"job_id": "job-c%d" % trial_no,
                       "generation": 1,
                       "extranonce2": w.lease["extranonce2"],
                       "version": w.lease["version"],
                       "ntime": w.lease["ntime"],
                       "nonce": w.lease["lo"],
                       "lease_id": w.lease["lease_id"],
                       "worker_id": w.wid}
                ident = (rec["job_id"], rec["generation"],
                         rec["extranonce2"], rec["version"],
                         rec["ntime"], rec["nonce"])
                if ident not in submitted_identities:
                    submitted_identities.add(ident)
                    assert call_ok(client, {
                        "type": "candidate_submit",
                        "record": rec}) == "ACCEPTED"
                    if rng.random() < 0.5:
                        assert call_ok(client, {
                            "type": "candidate_submit",
                            "record": rec}) == "DUPLICATE"
                        inj["cand_dup"] += 1
            w.lease = None
            w.examined = 0
        else:
            step = rng.randint(1, max(1, size - w.examined))
            w.examined = min(size, w.examined + step)
            res = do_progress(client, w.wid, w.lease,
                              w.examined)
            assert res == "OK", res
        if guard % 500 == 0:
            assert call_ok(client, {
                "type": "partition_check"}) is True
    acc = check_completed(client)
    assert acc["duplicate_deliveries"] >= observed["dup"]
    assert acc["stale_reports"] >= observed["stale"]
    assert acc["not_holder_attempts"] >= observed["not_holder"]
    before = len(verifier_calls)
    call_ok(client, {"type": "candidate_drain"})
    qst = call_ok(client, {"type": "queue_stats"})
    assert qst["verified"] == len(verifier_calls) - 0, qst
    assert len(verifier_calls) == len(submitted_identities), \
        (len(verifier_calls), len(submitted_identities))
    assert qst["duplicates"] == inj["cand_dup"], qst
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
            "candidates_verified": qst["verified"],
            "verifier_calls_before_drain": before}


def run_gate3():
    trials = []
    rng = random.Random(20261117)
    for t in range(60):
        calls = []
        server, client = make_pair(
            "local",
            verifier=lambda rec, c=calls: c.append(rec)
            or "share")
        try:
            rec = campaign_trial(client, server, rng, t, calls)
        finally:
            close_pair(server, client)
        trials.append(rec)
        print("PASS gate3 local trial", t, "declared",
              rec["declared_total"], "repeated",
              rec["repeated"], flush=True)
    rng = random.Random(20261118)
    tcp_trials = []
    for t in range(6):
        calls = []
        server, client = make_pair(
            "tcp",
            verifier=lambda rec, c=calls: c.append(rec)
            or "share")
        try:
            rec = campaign_trial(client, server, rng,
                                 1000 + t, calls)
        finally:
            close_pair(server, client)
        tcp_trials.append(rec)
        print("PASS gate3 tcp trial", t, "declared",
              rec["declared_total"], flush=True)
    all_trials = trials + tcp_trials
    RESULTS["gate3"] = {
        "local_trials": len(trials),
        "tcp_trials": len(tcp_trials),
        "all_exact": True,
        "total_declared": sum(t["declared_total"]
                              for t in all_trials),
        "total_repeated": sum(t["repeated"]
                              for t in all_trials),
        "total_duplicate_deliveries":
            sum(t["duplicate_deliveries"] for t in all_trials),
        "total_stale_reports":
            sum(t["stale_reports"] for t in all_trials),
        "total_not_holder_attempts":
            sum(t["not_holder_attempts"] for t in all_trials),
        "total_reclaims": sum(t["reclaims"]
                              for t in all_trials),
        "injections": {
            k: sum(t["injections"][k] for t in all_trials)
            for k in all_trials[0]["injections"]},
        "per_trial": all_trials}
    print("PASS gate3:", len(all_trials), "trials,",
          RESULTS["gate3"]["total_declared"],
          "positions exact", flush=True)


# ------------------------------------------------------------------
# Gate 5: persistent coordinator restart with in-flight leases
# ------------------------------------------------------------------

def run_gate5():
    import shutil
    state = os.path.join(HERE, "RAW_RESULTS", "gate5_state")
    if os.path.exists(state):
        shutil.rmtree(state)
    calls = []
    verifier = lambda rec: calls.append(rec) or "share"  # noqa
    s1 = CoordinatorServer(FLEET, state_dir=state,
                           verifier=verifier)
    port = start_tcp(s1)
    c1 = CoordinatorClient(host="127.0.0.1", port=port)
    reg(c1, "w-0", 0.0)
    reg(c1, "w-1", 0.0)
    call_ok(c1, {
        "type": "declare_job", "job_id": "job-g5",
        "generation": 1, "nonce_count": 512,
        "chunk_size": 128, "n_slots": 2,
        "version_variants": [0x20000000],
        "ntime_values": [1700000000], "counters_per_slot": 1})
    lease0 = do_lease(c1, "w-0", 0.0)
    assert do_progress(c1, "w-0", lease0, 64) == "OK"
    lease1 = do_lease(c1, "w-1", 0.0)
    assert do_complete(c1, "w-1", lease1) == "OK"
    rec = {"job_id": "job-g5", "generation": 1,
           "extranonce2": lease0["extranonce2"],
           "version": lease0["version"],
           "ntime": lease0["ntime"], "nonce": lease0["lo"],
           "lease_id": lease0["lease_id"], "worker_id": "w-0"}
    assert call_ok(c1, {"type": "candidate_submit",
                        "record": rec}) == "ACCEPTED"
    assert call_ok(c1, {"type": "candidate_submit",
                        "record": rec}) == "DUPLICATE"
    s1.write_snapshot()
    acc_before = call_ok(c1, {"type": "accounting"})
    assert acc_before["unique_coverage"] == 128, acc_before
    # More work AFTER the snapshot: only the journal tail
    # can carry it across the crash below.
    lease1b = do_lease(c1, "w-1", 1.0)
    assert do_complete(c1, "w-1", lease1b) == "OK"
    token_before = s1.core._token_seq
    # Crash: no shutdown snapshot, journals simply stop.
    c1.close()
    stop_tcp(s1)
    s1._journal_fh.close()
    s1._journal_fh = None
    s1.core.queue.close()

    s2 = CoordinatorServer(FLEET, state_dir=state,
                           verifier=verifier)
    port = start_tcp(s2)
    c2 = CoordinatorClient(host="127.0.0.1", port=port)
    out = {"replayed_ops": s2.replayed_ops,
           "epoch_after_restart": s2.core.epoch,
           "token_counter_preserved":
               s2.core._token_seq >= token_before}
    assert s2.replayed_ops >= 2, out
    assert s2.core.epoch == 1, s2.core.epoch
    assert s2.core._token_seq >= token_before
    # Pre-restart token is dead; coverage survived,
    # including the post-snapshot completion (128 + 128).
    assert do_complete(c2, "w-0", lease0) == "STALE"
    acc = call_ok(c2, {"type": "accounting"})
    assert acc["unique_coverage"] == 256, acc
    info = call_ok(c2, {"type": "lease_info",
                        "lease_id": lease0["lease_id"]})
    assert info["state"] == "reclaimed", info
    # Candidate journal recovery: still pending, still deduped.
    qst = call_ok(c2, {"type": "queue_stats"})
    assert qst["pending"] == 1, qst
    assert call_ok(c2, {"type": "candidate_submit",
                        "record": rec}) == "DUPLICATE"
    drained = call_ok(c2, {"type": "candidate_drain"})
    assert len(drained) == 1 and len(calls) == 1, (drained,
                                                  calls)
    # The reclaimed chunk's progress becomes repeated work.
    reg(c2, "w-0", 10.0)
    reg(c2, "w-1", 10.0)
    lease0b = do_lease(c2, "w-0", 10.0)
    assert (lease0b["lo"], lease0b["hi"]) \
        == (lease0["lo"], lease0["hi"])
    assert do_complete(c2, "w-0", lease0b) == "OK"
    acc = call_ok(c2, {"type": "accounting"})
    assert acc["repeated_computations"] == 64, acc
    c2.close()
    stop_tcp(s2)
    s2.close()

    # Second restart: verified candidate is never re-verified.
    s3 = CoordinatorServer(FLEET, state_dir=state,
                           verifier=verifier)
    port = start_tcp(s3)
    c3 = CoordinatorClient(host="127.0.0.1", port=port)
    assert call_ok(c3, {"type": "candidate_submit",
                        "record": rec}) == "DUPLICATE"
    qst = call_ok(c3, {"type": "queue_stats"})
    assert qst["pending"] == 0, qst
    reg(c3, "w-0", 20.0)
    reg(c3, "w-1", 20.0)
    guard = 0
    while not call_ok(c3, {"type": "accounting"})["complete"]:
        guard += 1
        assert guard < 10000
        for w in ("w-0", "w-1"):
            got = do_lease(c3, w, 20.0)
            if got is not None:
                assert do_complete(c3, w, got) == "OK"
    acc = check_completed(c3)
    out.update({"final_unique": acc["unique_coverage"],
                "final_declared": acc["declared_total"],
                "second_epoch": s3.core.epoch})
    c3.close()
    stop_tcp(s3)
    s3.close()
    RESULTS["gate5"] = out
    print("PASS gate5:", out, flush=True)


def main():
    digest = check_predeclaration()
    t0 = time.time()
    run_gate1()
    run_gate2()
    run_gate3()
    run_gate5()
    stamp = datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ")
    record = {"experiment": "EXP-055",
              "kind": "protocol-level coordinator campaign",
              "host_cpu": "AMD EPYC 9D25",
              "when_utc": stamp,
              "predeclaration_sha256": digest,
              "elapsed_s": round(time.time() - t0, 2),
              "loadavg": list(os.getloadavg()),
              "results": RESULTS}
    out = os.path.join(HERE, "RAW_RESULTS",
                       "campaign_%s.json" % stamp)
    with open(out, "w") as fh:
        json.dump(record, fh, indent=1, sort_keys=True)
    print("WROTE", out, flush=True)
    print("ALL EXP-055 CAMPAIGN GATES (1, 2, 3, 5) PASSED",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
