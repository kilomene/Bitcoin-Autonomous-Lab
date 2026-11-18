#!/usr/bin/env python3
"""Stage 9 fleet staging driver.

Runs the full fleet path on loopback, isolated from the
live stack: a stub Stratum pool, the fleet gateway
(mining/fleet_gateway.py) holding the pool session and
hosting the coordinator, and two independent fleet worker
processes (mining/fleet_worker.py) leasing disjoint
chunks. The driver then audits the three independent
records (coordinator accounting, gateway evidence, stub
pool log, plus both worker logs) against each other, and
runs a small fencing and duplicate probe suite against
the same coordinator after the main run's evidence is
snapshotted.

Nothing here touches the live miner, the autopilot, the
endpoint config, or the real pool: the gateway is pointed
at the stub by explicit --pool-host/--pool-port, and every
staging process binds 127.0.0.1 only. The live heartbeat
is read before and after, read-only, to prove the live
stack was undisturbed.
"""

import json
import os
import subprocess
import sys
import time

REPO = "/home/hatch/workspace/bitcoin-autonomous-lab"
SCRATCH = os.path.join(REPO, ".local", "stage9", "fleet", "run")
STUB_PORT = 14031
COORD_PORT = 14032
FLEET = "nova-fleet-staging"
NONCE_COUNT = 1 << 23          # per slice
CHUNK_SIZE = 1 << 20
N_SLOTS = 2
DECLARED = NONCE_COUNT * N_SLOTS

sys.path.insert(0, REPO)
from mining.coordinator import CoordinatorClient  # noqa: E402


def read_jsonl(path):
    out = []
    if not os.path.exists(path):
        return out
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def heartbeat():
    try:
        with open(os.path.join(REPO, ".local", "heartbeat.json")) as fh:
            d = json.load(fh)
        return {k: d.get(k) for k in
                ("ts", "miner_state", "shares_accepted_total",
                 "autopilot_pid", "miner_pid")}
    except Exception as exc:
        return {"error": str(exc)}


def wait_for(fn, timeout, what):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            v = fn()
        except Exception:
            v = None
        if v:
            return v
        time.sleep(1.0)
    raise TimeoutError("timed out waiting for %s" % what)


def main():
    os.makedirs(SCRATCH, exist_ok=True)
    summary = {"started_at": time.time(),
               "live_before": heartbeat(), "checks": {},
               "failures": []}

    def check(name, cond, detail=None):
        summary["checks"][name] = {"pass": bool(cond),
                                   "detail": detail}
        if not cond:
            summary["failures"].append(name)

    procs = []
    try:
        stub_log = os.path.join(SCRATCH, "stub.jsonl")
        gw_evidence = os.path.join(SCRATCH, "gateway.jsonl")
        for p in (stub_log, gw_evidence):
            if os.path.exists(p):
                os.remove(p)
        stub = subprocess.Popen(
            [sys.executable,
             os.path.join(REPO, ".local", "stage9", "fleet",
                          "stub_pool.py"),
             "--port", str(STUB_PORT),
             "--share-difficulty", "0.0002",
             "--log", stub_log],
            stdout=open(os.path.join(SCRATCH, "stub.stdout"),
                        "w"),
            stderr=subprocess.STDOUT)
        procs.append(stub)
        wait_for(lambda: os.path.exists(stub_log)
                 and read_jsonl(stub_log), 30, "stub up")

        gw = subprocess.Popen(
            [sys.executable,
             os.path.join(REPO, "mining", "fleet_gateway.py"),
             "--pool-host", "127.0.0.1",
             "--pool-port", str(STUB_PORT),
             "--coord-host", "127.0.0.1",
             "--coord-port", str(COORD_PORT),
             "--fleet", FLEET,
             "--state-dir", os.path.join(SCRATCH, "gw-state"),
             "--evidence", gw_evidence,
             "--worker", "fleet-gw",
             "--nonce-count", str(NONCE_COUNT),
             "--chunk-size", str(CHUNK_SIZE),
             "--n-slots", str(N_SLOTS),
             "--duration", "1800"],
            stdout=open(os.path.join(SCRATCH, "gateway.stdout"),
                        "w"),
            stderr=subprocess.STDOUT)
        procs.append(gw)

        client = wait_for(
            lambda: CoordinatorClient(host="127.0.0.1",
                                      port=COORD_PORT),
            60, "coordinator port")

        def declared():
            out = client.call({"type": "accounting"})
            return out["result"]["job_id"] == "stub-0001" \
                and out["result"]
        acc0 = wait_for(declared, 120, "job declared")
        summary["declared"] = acc0

        workers = []
        for wid in ("w-fleet-a", "w-fleet-b"):
            log = os.path.join(SCRATCH, "worker-%s.jsonl" % wid)
            if os.path.exists(log):
                os.remove(log)
            wp = subprocess.Popen(
                [sys.executable,
                 os.path.join(REPO, "mining", "fleet_worker.py"),
                 "--gateway-host", "127.0.0.1",
                 "--gateway-port", str(COORD_PORT),
                 "--fleet", FLEET,
                 "--worker-id", wid,
                 "--log", log,
                 "--exit-on-complete",
                 "--duration", "1500",
                 "--lease-ttl", "300"],
                stdout=open(os.path.join(
                    SCRATCH, "worker-%s.stdout" % wid), "w"),
                stderr=subprocess.STDOUT)
            workers.append(wp)
            procs.append(wp)

        def complete():
            out = client.call({"type": "accounting"})
            return out["result"]["complete"] and out["result"]
        acc = wait_for(complete, 1500, "job complete")
        summary["accounting_pre_probes"] = acc
        intervals = client.call(
            {"type": "completed_intervals"})["result"]
        queue_pre = client.call({"type": "queue_stats"})["result"]
        summary["queue_pre_probes"] = queue_pre
        summary["partition_check"] = client.call(
            {"type": "partition_check"})["result"]

        for wp in workers:
            wp.wait(timeout=300)
        summary["worker_exit_codes"] = [wp.returncode
                                        for wp in workers]

        # ---- cross-audit of the independent records --------
        check("accounting_complete",
              acc["complete"] and acc["unique_coverage"] == DECLARED
              and acc["declared_total"] == DECLARED
              and acc["pending"] == 0 and acc["leased"] == 0,
              acc)
        check("accounting_no_duplicates_or_stale",
              acc["duplicate_deliveries"] == 0
              and acc["stale_reports"] == 0
              and acc["not_holder_attempts"] == 0
              and acc["unknown_lease_reports"] == 0
              and acc["reclaims"] == 0
              and acc["repeated_computations"] == 0, acc)

        by_slot = {}
        for key, lo, hi in intervals:
            by_slot.setdefault(key[0], []).append((lo, hi))
        disjoint_cover = True
        if sorted(by_slot) != [0, 1]:
            disjoint_cover = False
        for slot, ivs in by_slot.items():
            ivs.sort()
            if ivs[0][0] != 0 or ivs[-1][1] != NONCE_COUNT:
                disjoint_cover = False
            for (a_lo, a_hi), (b_lo, _b) in zip(ivs, ivs[1:]):
                if a_hi != b_lo:
                    disjoint_cover = False
        check("intervals_disjoint_and_covering", disjoint_cover,
              {str(k): v for k, v in by_slot.items()})

        worker_records = {}
        total_attempts = 0
        total_candidates = 0
        worker_slots = {}
        for wid in ("w-fleet-a", "w-fleet-b"):
            recs = read_jsonl(os.path.join(
                SCRATCH, "worker-%s.jsonl" % wid))
            done = [r for r in recs
                    if r["event"] == "chunk_completed"]
            worker_records[wid] = done
            total_attempts += sum(r["attempts"] for r in done)
            total_candidates += sum(r["candidates"] for r in done)
            slots = {r["slot"] for r in done}
            worker_slots[wid] = sorted(slots)
            check("worker_%s_single_slot" % wid, len(slots) == 1,
                  worker_slots[wid])
            check("worker_%s_all_complete_ok" % wid,
                  all(r["complete_result"] == "OK" for r in done)
                  and len(done) == NONCE_COUNT // CHUNK_SIZE,
                  {"chunks": len(done)})
        check("workers_distinct_slots",
              worker_slots["w-fleet-a"] != worker_slots["w-fleet-b"],
              worker_slots)
        check("attempts_equal_declared",
              total_attempts == DECLARED,
              {"total_attempts": total_attempts,
               "declared": DECLARED})

        check("queue_accounting",
              queue_pre["submitted"] == total_candidates
              and queue_pre["verified"] == total_candidates
              and queue_pre["duplicates"] == 0
              and queue_pre["pending"] == 0
              and queue_pre["stale_generation_dropped"] == 0
              and set(queue_pre["classifications"])
              <= {"share", "block_candidate"}
              and sum(queue_pre["classifications"].values())
              == total_candidates,
              queue_pre)

        # The gateway's Evidence file also carries the
        # StratumClient's own share_result lines (no
        # "worker" field); the gateway's per-worker verdict
        # lines are the ones with it. Verdict collection in
        # the gateway is asynchronous, so wait for the last
        # verdict to land before auditing them.
        def gw_worker_results():
            evs = read_jsonl(gw_evidence)
            res = [e for e in evs
                   if e["event"] == "share_result"
                   and "worker" in e]
            return res if len(res) >= total_candidates \
                else None
        gw_results = wait_for(gw_worker_results, 120,
                              "gateway verdicts collected")
        gw_events = read_jsonl(gw_evidence)
        gw_submitted = [e for e in gw_events
                        if e["event"] == "share_submitted"]
        gw_client_results = [e for e in gw_events
                             if e["event"] == "share_result"
                             and "worker" not in e]
        check("gateway_submitted_equals_candidates",
              len(gw_submitted) == total_candidates,
              {"gateway_submitted": len(gw_submitted),
               "candidates": total_candidates})
        check("gateway_all_shares_accepted",
              len(gw_results) == total_candidates
              and all(e["accepted"] for e in gw_results),
              {"results": len(gw_results)})
        check("client_level_results_match",
              len(gw_client_results) == total_candidates
              and all(e["accepted"] for e in gw_client_results),
              {"client_results": len(gw_client_results)})
        # The gateway republishes its EXP-037 totals on a
        # 10 s status cadence; wait for the first status
        # event whose totals reflect all collected verdicts
        # before judging them.
        def stats_caught_up():
            evs = read_jsonl(gw_evidence)
            sts = [e for e in evs if e["event"] == "status"]
            if sts and sts[-1]["statistics"].get(
                    "pool_shares_accepted") == total_candidates:
                return sts[-1]["statistics"]
            return None
        caught = wait_for(stats_caught_up, 40,
                          "gateway status totals caught up")
        gw_events = read_jsonl(gw_evidence)
        status_events = [e for e in gw_events
                         if e["event"] == "status"]
        last_stats = caught or (status_events[-1]["statistics"]
                                if status_events else {})
        check("gateway_exp037_totals",
              last_stats.get("pool_shares_submitted")
              == total_candidates
              and last_stats.get("pool_shares_accepted")
              == total_candidates
              and last_stats.get("pool_shares_rejected", 0) == 0,
              last_stats)

        stub_events = read_jsonl(stub_log)
        judged = [e for e in stub_events
                  if e["event"] == "submit_judged"]
        accepted = [e for e in judged if e["accepted"]]
        dup = [e for e in judged if e.get("duplicate")]
        rejected = [e for e in judged
                    if not e["accepted"] and not e.get("duplicate")]
        keys = {(e["job_id"], e["extranonce2"], e["nonce"])
                for e in accepted}
        check("stub_accepted_equals_candidates",
              len(accepted) == total_candidates
              and len(keys) == total_candidates,
              {"accepted": len(accepted),
               "distinct_keys": len(keys)})
        check("stub_zero_duplicates_zero_rejected",
              len(dup) == 0 and len(rejected) == 0,
              {"duplicates": len(dup), "rejected": len(rejected)})
        summary["candidates_total"] = total_candidates
        summary["stub_totals"] = {"judged": len(judged),
                                  "accepted": len(accepted),
                                  "duplicates": len(dup),
                                  "rejected": len(rejected)}

        # ---- fencing / duplicate probes (after snapshots) --
        probes = {}
        client.call({"type": "declare_job",
                     "job_id": "probe-0001", "generation": 777,
                     "nonce_count": 4096, "chunk_size": 1024,
                     "n_slots": 2,
                     "version_variants": [0x20000000],
                     "ntime_values": [int(time.time())],
                     "counters_per_slot": 1})
        r = client.call({"type": "register",
                         "worker_id": "w-probe",
                         "fleet_id": "other-fleet",
                         "now": time.time()})
        probes["foreign_fleet_register"] = r
        client.call({"type": "register", "worker_id": "w-probe",
                     "fleet_id": FLEET, "now": time.time()})
        client.call({"type": "heartbeat", "worker_id": "w-probe",
                     "now": time.time()})
        client.call({"type": "register", "worker_id": "w-probe2",
                     "fleet_id": FLEET, "now": time.time()})
        client.call({"type": "heartbeat",
                     "worker_id": "w-probe2", "now": time.time()})
        lease = client.call({"type": "lease",
                             "worker_id": "w-probe",
                             "now": time.time(),
                             "ttl": 30.0})["result"]
        probes["lease"] = lease
        probes["not_holder"] = client.call(
            {"type": "complete", "worker_id": "w-probe2",
             "lease_id": lease["lease_id"],
             "token": lease["token"]})["result"]
        probes["stale_wrong_token"] = client.call(
            {"type": "complete", "worker_id": "w-probe",
             "lease_id": lease["lease_id"],
             "token": lease["token"] + 999999})["result"]
        rec = {"job_id": "probe-0001", "generation": 777,
               "extranonce2": lease["extranonce2"],
               "version": 0x20000000,
               "ntime": lease["ntime"], "nonce": 12345,
               "lease_id": lease["lease_id"],
               "worker_id": "w-probe"}
        probes["candidate_first"] = client.call(
            {"type": "candidate_submit", "record": rec})["result"]
        probes["candidate_replay"] = client.call(
            {"type": "candidate_submit", "record": rec})["result"]
        probes["complete_ok"] = client.call(
            {"type": "complete", "worker_id": "w-probe",
             "lease_id": lease["lease_id"],
             "token": lease["token"]})["result"]
        probes["complete_replay"] = client.call(
            {"type": "complete", "worker_id": "w-probe",
             "lease_id": lease["lease_id"],
             "token": lease["token"]})["result"]
        summary["probes"] = probes
        check("probe_foreign_fleet_refused",
              probes["foreign_fleet_register"].get("ok") is False
              and probes["foreign_fleet_register"].get("error")
              == "FOREIGN_FLEET", probes["foreign_fleet_register"])
        check("probe_not_holder", probes["not_holder"] == "NOT_HOLDER")
        check("probe_stale_wrong_token",
              probes["stale_wrong_token"] == "STALE")
        check("probe_candidate_duplicate",
              probes["candidate_first"] == "ACCEPTED"
              and probes["candidate_replay"] == "DUPLICATE")
        check("probe_complete_then_duplicate",
              probes["complete_ok"] == "OK"
              and probes["complete_replay"] == "DUPLICATE")
        summary["accounting_post_probes"] = client.call(
            {"type": "accounting"})["result"]
        client.close()
    except Exception as exc:
        summary["failures"].append("driver_exception: %r" % (exc,))
        summary["exception"] = repr(exc)
    finally:
        for p in procs:
            try:
                p.terminate()
            except Exception:
                pass
        for p in procs:
            try:
                p.wait(timeout=20)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass
    summary["live_after"] = heartbeat()
    lb, la = summary["live_before"], summary["live_after"]
    summary["checks"]["live_stack_undisturbed"] = {
        "pass": lb.get("autopilot_pid") == la.get("autopilot_pid")
        and lb.get("miner_pid") == la.get("miner_pid")
        and la.get("shares_accepted_total", 0)
        >= lb.get("shares_accepted_total", 0),
        "detail": {"before": lb, "after": la}}
    if not summary["checks"]["live_stack_undisturbed"]["pass"]:
        summary["failures"].append("live_stack_undisturbed")
    summary["finished_at"] = time.time()
    summary["verdict"] = "PASS" if not summary["failures"] else "FAIL"
    with open(os.path.join(SCRATCH, "summary.json"), "w") as fh:
        json.dump(summary, fh, indent=2, sort_keys=True)
    print(json.dumps({"verdict": summary["verdict"],
                      "failures": summary["failures"],
                      "candidates_total":
                      summary.get("candidates_total"),
                      "checks": {k: v["pass"] for k, v
                                 in summary["checks"].items()}},
                     indent=2, sort_keys=True))
    return 0 if not summary["failures"] else 1


if __name__ == "__main__":
    sys.exit(main())
