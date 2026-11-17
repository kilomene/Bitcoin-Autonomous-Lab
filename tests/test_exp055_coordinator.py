#!/usr/bin/env python3
"""EXP-055 regression suite: production wire protocol and
persistent coordinator (NOVA-ER-0015, roadmap F1).

Layers, in order:

  1. Gate 1 targeted tests at the protocol level over the
     in-process transport (the full set from
     research/sha256d/exp055/exp055_campaign.py), plus the
     wire-integrity and candidate tests over TCP loopback.
  2. Gate 2 differential accounting against the
     independent model, reduced set (6 seeded scripts; the
     campaign of record runs 40).
  3. The two EXP-043 fix demonstrations in assertion
     form: F-A (the lease store holds only active leases
     after 2,000 completions; tombstones are compact) and
     F-B (a snapshot at 8,192 chunks carries live state
     only and restores exactly).
  4. Gate 5 persistent-coordinator restart with in-flight
     leases, full scenario (state directory, crash with
     journal-tail replay, clean second restart).
  5. Gate 6: a fresh regtest block produced through
     coordinator-assigned work (the exp055_gate6 driver).

The full Gate 3 campaign (66 trials) and Gate 4 overhead
study are the campaign drivers in research/sha256d/
exp055/, not this suite; this suite is the regression
form. Loopback and in-process workers only: no other
machine is contacted (fleet activation is owner-gated).
"""

import os
import sys

ROOT = "/home/hatch/workspace/bitcoin-autonomous-lab"
EXP055 = os.path.join(ROOT, "research/sha256d/exp055")
sys.path.insert(0, ROOT)
sys.path.insert(0, EXP055)

import exp055_campaign as camp  # noqa: E402
from mining.coordinator import (CoordinatorClient,  # noqa: E402
                                CoordinatorServer)

CHECKS = 0


def check(cond, label):
    global CHECKS
    CHECKS += 1
    if not cond:
        raise AssertionError("check failed: %s" % label)
    print("ok %d: %s" % (CHECKS, label), flush=True)


def main():
    camp.check_predeclaration()
    check(True, "predeclaration hash pinned and verified")

    # Layer 1: Gate 1 targeted, in-process transport.
    for name, fn, kw in camp.GATE1:
        server, client = camp.small_pair(
            "local", **kw)
        try:
            fn(client, server)
        finally:
            camp.close_pair(server, client)
        check(True, "gate1 local: %s" % name)
    # Layer 1b: TCP subset.
    for name, fn, kw in camp.GATE1:
        if name not in ("wire_integrity", "candidate_queue",
                        "coordinator_restart_tokens_die",
                        "steal_and_token_rotation"):
            continue
        server, client = camp.small_pair("tcp", **kw)
        try:
            fn(client, server)
        finally:
            camp.close_pair(server, client)
        check(True, "gate1 tcp: %s" % name)

    # Layer 2: Gate 2 differential, reduced set.
    total = 0
    for i in range(6):
        total += camp.gate2_script(20261120 + i)
    check(total > 500,
          "gate2 reduced: %d comparisons, all equal" % total)

    # Layer 3: EXP-043 fixes, assertion form.
    server, client = camp.make_pair("local")
    camp.call_ok(client, {
        "type": "declare_job", "job_id": "job-fix",
        "generation": 1, "nonce_count": 64,
        "chunk_size": 64, "n_slots": 1,
        "version_variants": [0x20000000],
        "ntime_values": [1700000000],
        "counters_per_slot": 2200})
    camp.reg(client, "w-0")
    for _ in range(2000):
        l = camp.do_lease(client, "w-0", 0.0, ttl=300.0)
        assert camp.do_complete(client, "w-0", l) == "OK"
    stats = camp.call_ok(client, {"type": "stats"})
    check(stats["active_leases"] == 0,
          "F-A: lease store holds 0 active leases after "
          "2,000 completions (history is tombstones only)")
    check(stats["completed_tombstones"] == 2000,
          "F-A: 2,000 compact completed tombstones retained "
          "for DUPLICATE classification")
    camp.close_pair(server, client)

    srv = CoordinatorServer(camp.FLEET)
    camp.call_ok(CoordinatorClient(server=srv), {
        "type": "declare_job", "job_id": "job-big",
        "generation": 1, "nonce_count": 8192,
        "chunk_size": 1, "n_slots": 1,
        "version_variants": [0x20000000],
        "ntime_values": [1700000000],
        "counters_per_slot": 1})
    snap = srv.core.snapshot()
    import json as _json
    blob = _json.dumps(snap)
    check("events" not in snap and len(blob) < 2_000_000,
          "F-B: snapshot at 8,192 chunks is live state "
          "only (%d bytes, no event log)" % len(blob))
    restored = CoordinatorServer(camp.FLEET)
    restored.core._load_state(snap)
    check(restored.core.accounting()["declared_total"]
          == 8192,
          "F-B: snapshot restores the declared space "
          "exactly")
    srv.close()
    restored.close()

    # Layer 4: Gate 5 full scenario.
    camp.RESULTS["gate5"] = {}
    camp.run_gate5()
    check(camp.RESULTS["gate5"]["final_unique"] == 1024,
          "gate5: persistent restart, job completed "
          "exactly after crash recovery")

    # Layer 5: Gate 6 regtest block through the coordinator.
    import exp055_gate6
    rc = exp055_gate6.main()
    check(rc == 0,
          "gate6: regtest block through coordinator-"
          "assigned work accepted on chain")

    print("ALL EXP-055 TESTS PASSED (%d checks)" % CHECKS,
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
