#!/usr/bin/env python3
"""EXP-057 regression suite: stratum aggregation tier
(NOVA-ER-0017, register R-27).

Layers, in order:

  1. Gate 2 share validation differentials against
     verify_candidate (the full campaign corpus).
  2. Gate 3 identity spoofing and stale work injection
     at 2 and 4 workers (the campaign of record also
     runs 8), with exact accounting asserted inside.
  3. Gate 5 restart behaviour (snapshot, restore, dead
     sessions, dedup and pending candidate preserved).
  4. Gate 6: a fresh regtest block produced through the
     tier (the exp057_gate6 driver), including the
     tip-unmoved proof before the operator action.
  5. Audit defect regressions (2026-11-17): D-1, a TCP
     re-authorize must close the previous session (no
     orphan outliving its connection); D-2, a failed
     operator submission must retain the pending
     candidate (removal only on success).

The full Gate 3 campaign at all three predeclared
worker counts and the Gate 4 overhead study are the
campaign drivers in research/sha256d/exp057/, not this
suite; this suite is the regression form. Loopback and
in-process workers only: no other machine is contacted
(fleet activation is owner-gated).
"""

import json
import os
import random
import socket
import sys
import threading
import time

ROOT = "/home/hatch/workspace/bitcoin-autonomous-lab"
EXP057 = os.path.join(ROOT, "research/sha256d/exp057")
sys.path.insert(0, ROOT)
sys.path.insert(0, EXP057)

import exp057_campaign as camp  # noqa: E402
import exp057_gate6 as gate6  # noqa: E402
import mining.aggregation as agg  # noqa: E402
from mining.aggregation import (AggregationTCPServer,  # noqa: E402
                                IdentityError)

CHECKS = 0


def check(cond, label):
    global CHECKS
    CHECKS += 1
    if not cond:
        raise AssertionError("check failed: %s" % label)
    print("ok %d: %s" % (CHECKS, label), flush=True)


class _TcpClient:
    """Minimal stratum client for the D-1 regression:
    one connection, sequential request ids, notifications
    skipped while waiting for a response."""

    def __init__(self, port):
        self.sock = socket.create_connection(("127.0.0.1", port),
                                             timeout=30)
        self.f = self.sock.makefile("rwb")
        self._id = 0

    def rpc(self, method, params):
        self._id += 1
        self.f.write((json.dumps(
            {"id": self._id, "method": method,
             "params": params}) + "\n").encode())
        self.f.flush()
        while True:
            msg = json.loads(self.f.readline())
            if msg.get("id") == self._id:
                return msg

    def close(self):
        try:
            self.f.close()
        finally:
            self.sock.close()


def regression_d1_reauthorize_closes_previous():
    """Audit D-1, reproduced exactly: authorize as worker
    A on one TCP connection, re-authorize as worker B on
    the same connection, disconnect. The A session must
    already be closed at re-authorize (not orphaned), the
    orphaned id must be rejected in-process, and no
    session may remain after disconnect."""
    tier, _rpc = camp.make_tier()
    tier.enroll_worker("tcp-w1", "tok-tcp-w1")
    tier.enroll_worker("tcp-w2", "tok-tcp-w2")
    server = AggregationTCPServer(("127.0.0.1", 0), tier)
    port = server.server_address[1]
    th = threading.Thread(target=server.serve_forever,
                          daemon=True)
    th.start()
    client = _TcpClient(port)
    try:
        r = client.rpc("mining.authorize",
                       ["tcp-w1", "tok-tcp-w1"])
        assert r["result"] is True, r
        assert len(tier.sessions) == 1, tier.sessions
        orphan_id = next(iter(tier.sessions))
        assert tier.sessions[orphan_id]["worker_id"] == "tcp-w1"
        r = client.rpc("mining.authorize",
                       ["tcp-w2", "tok-tcp-w2"])
        assert r["result"] is True, r
        check(orphan_id not in tier.sessions
              and len(tier.sessions) == 1,
              "d1 re-authorize closed the previous session")
        new_id = next(iter(tier.sessions))
        assert tier.sessions[new_id]["worker_id"] == "tcp-w2"
        job = tier.current_job()
        try:
            tier.submit_share(orphan_id, job["job_id"],
                              "00000001", "00000000", "00000000")
            raise AssertionError("orphaned session judged a share")
        except IdentityError:
            pass
        check(True, "d1 orphaned session id rejected in-process")
    finally:
        client.close()
    deadline = time.time() + 10
    while tier.sessions and time.time() < deadline:
        time.sleep(0.05)
    try:
        check(not tier.sessions,
              "d1 no sessions remain after disconnect")
    finally:
        server.shutdown()
        server.server_close()


def regression_d2_failed_submit_retains_candidate():
    """Audit D-2: operator_submit_pending must retain the
    pending candidate on every failure (re-verification,
    submitter exception) and remove it only on success."""
    tier, _rpc = camp.make_tier()
    job = tier.current_job()
    calls = []
    tier.set_submitter(
        lambda j, res, v, w: calls.append(w) or {"accepted": True})
    # Planted candidate that fails the real EXP-036
    # re-verification (all-zero header, labelled planted).
    tier.pending_candidates.append({
        "job_id": job["job_id"], "worker": "w1",
        "header": "00" * 80, "coinbase": "00" * 40,
        "hash": "ab" * 32, "stale": False,
        "verify_reason": "planted-for-d2-regression"})
    try:
        tier.operator_submit_pending("op-token-057")
        raise AssertionError("planted candidate submitted")
    except RuntimeError:
        pass
    check(len(tier.pending_candidates) == 1
          and tier.pending_candidates[0]["verify_reason"]
          == "planted-for-d2-regression"
          and calls == [] and tier.upstream_submissions == 0,
          "d2 candidate retained after re-verification failure")
    # Submitter-exception and success paths need a candidate
    # that passes re-verification; the synthetic workbase
    # cannot produce a network-target header on demand, so
    # verify_candidate is patched at the module boundary
    # for this tier-local queue test only (restored below)
    # and the retention logic is what is under test.
    good = {"job_id": job["job_id"], "worker": "w1",
            "header": "11" * 80, "coinbase": "00" * 40,
            "hash": "cd" * 32, "stale": False,
            "verify_reason": "patched-for-d2-regression"}
    tier.pending_candidates.append(good)
    real_verify = agg.verify_candidate
    agg.verify_candidate = lambda *a, **k: {
        "meets_network_target": True, "digest": b"\x00" * 32,
        "value": 0, "reason": "patched-for-d2-regression"}
    try:
        def boom(j, res, v, w):
            raise RuntimeError("submitter boom")
        tier.set_submitter(boom)
        try:
            tier.operator_submit_pending("op-token-057", index=1)
            raise AssertionError("raising submitter accepted")
        except RuntimeError:
            pass
        check(len(tier.pending_candidates) == 2
              and tier.pending_candidates[1] is good
              and tier.upstream_submissions == 0,
              "d2 candidate retained after submitter exception")
        tier.set_submitter(
            lambda j, res, v, w: calls.append(w)
            or {"accepted": True})
        rec = tier.operator_submit_pending("op-token-057", index=1)
        check(rec["accepted"]
              and len(tier.pending_candidates) == 1
              and tier.pending_candidates[0]["verify_reason"]
              == "planted-for-d2-regression"
              and tier.upstream_submissions == 1,
              "d2 candidate removed only on successful submit")
    finally:
        agg.verify_candidate = real_verify


def main():
    camp.check_predeclaration()
    check(True, "predeclaration hash pinned and verified")
    rng = random.Random(20261117)
    r = camp.gate2(rng)
    check(r["agree"] == r["corpus"] and r["corpus"] >= 3000,
          "gate2 differentials agree on %d corpus entries"
          % r["corpus"])
    for n in (2, 4):
        r = camp.gate3_one(rng, n)
        check(r["identity_rejected"] == 7,
              "gate3 spoofs rejected at %d workers" % n)
        check(r["exp037_submitted"] > 0,
              "gate3 exact accounting at %d workers" % n)
    r = camp.gate5(rng)
    check(r["epoch_after"] == r["epoch_before"] + 1,
          "gate5 epoch bumps on restore")
    check(r["pending_preserved"] == 1,
          "gate5 pending candidate preserved")
    regression_d1_reauthorize_closes_previous()
    regression_d2_failed_submit_retains_candidate()
    rc = gate6.main()
    check(rc == 0, "gate6 regtest block through the tier")
    print("EXP-057 suite: %d checks, ALL PASSED" % CHECKS,
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
