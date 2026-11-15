#!/usr/bin/env python3
"""Live mainnet pool mining with the lab's fast engine.

Owner ordered 2026-11-13: the lab must mine for real on mainnet
and be seen mining. This runner connects the phase-1 Stratum
client (public pool, or our own solo server after the cutover)
to the current ComputeEngine (runtime
dispatched backend: AVX-512 multi-buffer where the CPUID probe
confirms it, otherwise the C midstate batch; early-exit search):
real mainnet jobs, real hashes, shares
submitted at pool difficulty, evidence logged as JSONL plus a
human-readable status file (.local/mainnet-status.txt) refreshed
every few seconds.

Usage: python3 mining/mainnet_live.py --duration 3600
       [--address bc1q...] (defaults to the lab wallet)

The Stratum endpoint comes from mining/endpoint_config.py:
--pool-host / --pool-port arguments, then BAL_POOL_HOST /
BAL_POOL_PORT, then .local/mining-endpoint.json (mode "pool" is
public-pool.io, mode "solo" is our own solo server), then the
public-pool default. The solo cutover is a flip of that file
plus a restart of this process; see docs/SOLO_CUTOVER.md.
"""

import argparse
import json
import os
import struct
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gpu import engine as gpu_engine
from gpu.engine import ComputeEngine
from mining.candidate_verify import verify_candidate
from mining.mining_statistics import (FrontierAccountant,
                                      MiningStatistics)
from mining.pow_engine import POW_LIMIT_MAINNET
from mining.stratum_client import StratumClient, Evidence, build_header

DEFAULT_ADDRESS = "bc1q528egeqsvv8aa382j43edxskqw6x7zxc2xpcf3"
ROOT = os.path.join(os.path.dirname(__file__), "..")
STATUS = os.path.join(ROOT, ".local", "mainnet-status.txt")
DIFF1_TARGET = 0xFFFF * (1 << 208)


def difficulty_of(digest):
    """Exact difficulty of a digest: DIFF1_TARGET / value."""
    v = int.from_bytes(digest, "little")
    if v == 0:
        return float("inf")
    return DIFF1_TARGET / v


def target_for_difficulty(diff):
    """The pool's share target, derived from the floating
    difficulty the pool itself set. This value decides only
    what is worth submitting as a share; it is never a
    consensus test. Block candidacy is decided by exact nBits
    semantics in mining/candidate_verify.py (EXP-036)."""
    return int(DIFF1_TARGET / diff)


def call_attempts(engine, hit, start):
    """Exact hash attempts of one engine.search_first call.

    The status counter accumulates real work, not requested
    work: the engine's counted stats
    (last_search_stats["attempted"], verified exact by the
    post-integration audit) are the source of truth. If a
    call path ever leaves no stats, count only what the
    result itself proves: a hit proves every nonce from the
    span start through the winner was examined, and a miss
    without stats proves no countable partial work, so 0.
    The requested span size is never counted: on an
    early-exit span it includes nonces never attempted
    (audit note N-1, resolved 2026-11-14).
    """
    stats = getattr(engine, "last_search_stats", None)
    if stats is not None and stats.get("attempted") is not None:
        return int(stats["attempted"])
    if hit is not None:
        return hit[0] - start + 1
    return 0


def record_candidate_event(recorder, verified, is_block_candidate,
                           worker, backend):
    """EXP-037 wiring: one backend hit, after EXP-036
    verification. Each outcome is its own counter, never
    summed: the candidate itself, the verification work (two
    full SHA-256d recomputations per verify_candidate call:
    hashlib dsha256 and the independent pure-Python
    double_sha256_pure), the candidates that passed exact
    verification (digests agree, header valid, share target
    met; the template-freshness submit gate is not part of
    verification and is not counted here), and the verified
    candidates the verifier classified as meeting the network
    target."""
    recorder.record("candidates", 1, worker=worker,
                    backend=backend)
    recorder.record("verification_hashes", 2, worker=worker,
                    backend=backend)
    if verified:
        recorder.record("valid_candidates", 1, worker=worker,
                        backend=backend)
    if is_block_candidate:
        recorder.record("network_target_candidates", 1,
                        worker=worker, backend=backend)


def record_share_result(recorder, accepted, worker, backend):
    """EXP-037 wiring: the pool's verdict on one submitted
    share, delivered by the StratumClient share-result hook as
    it happens. These counters are this process's session
    scope; the autopilot's EvidenceCounter census over the
    whole evidence log remains the lifetime source."""
    recorder.record("pool_shares_accepted" if accepted
                    else "pool_shares_rejected", 1,
                    worker=worker, backend=backend)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--duration", type=int, default=3600)
    ap.add_argument("--address", default=DEFAULT_ADDRESS)
    ap.add_argument("--worker", default=None,
                    help="pool worker name; default is this "
                         "machine's hostname, so every agent "
                         "mines under its own worker")
    ap.add_argument("--evidence", default="evidence/mainnet-live.jsonl")
    ap.add_argument("--pool-host", default=None,
                    help="Stratum host override; default resolution "
                         "is endpoint_config (env, config file, "
                         "public-pool)")
    ap.add_argument("--pool-port", type=int, default=None,
                    help="Stratum port override")
    args = ap.parse_args()

    if not args.worker:
        from mining.autopilot import default_worker
        args.worker = default_worker()
    from mining.endpoint_config import resolve_endpoint
    pool_host, pool_port, endpoint_mode, endpoint_cfg = \
        resolve_endpoint(args.pool_host, args.pool_port)
    ev = Evidence(args.evidence)
    user = f"{args.address}.{args.worker}"
    client = StratumClient(pool_host, pool_port, user, "x", ev)
    if endpoint_mode == "solo":
        # Our own server sets the difficulty itself; suggest the
        # configured value so the session log shows intent.
        client.suggest_difficulty = float(
            endpoint_cfg["solo"]["share_difficulty"])
    else:
        client.suggest_difficulty = 0.001  # pool clamps to its min: 1
    endpoint_line = (f"stratum endpoint: {pool_host}:{pool_port} "
                     f"(mode {endpoint_mode})")
    print(endpoint_line, flush=True)
    ev.log("endpoint_selected", host=pool_host, port=pool_port,
           mode=endpoint_mode)
    client.connect()
    threading.Thread(target=client.reader_loop, daemon=True).start()
    if not client.authorized.wait(timeout=30):
        print("authorization failed"); return 3
    print(f"authorized as {user}", flush=True)

    engine = ComputeEngine()
    desc = engine.describe()
    if desc["backend"] == "v512dual":
        reason_label = "AVX-512 DualMask"
        reason = desc.get("v512dual_reason")
    elif desc["backend"] == "v512":
        reason_label = "AVX-512 MB"
        reason = desc["v512_reason"]
    else:
        reason_label = "AVX-512 MB"
        reason = desc["v512_reason"]
    backend_line = (f"compute backend: {desc['backend']} "
                    f"(native impl: {desc['native_impl']}; "
                    f"{reason_label}: {reason})")
    print(backend_line, flush=True)
    ev.log("backend_selected", backend=desc["backend"],
           native_impl=desc["native_impl"],
           v512_reason=desc["v512_reason"],
           v512dual_reason=desc.get("v512dual_reason"))
    # EXP-037 statistics wiring: search accounting, candidate
    # events and share results are recorded as they happen,
    # into separated counters that are never summed (see
    # mining/mining_statistics.py). Recording goes through the
    # failure-isolated FrontierAccountant/SafeRecorder, so a
    # statistics defect can never stop mining; its error count
    # rides in the periodic status event below.
    stats = MiningStatistics()
    accountant = FrontierAccountant(stats)
    recorder = accountant.recorder
    client.on_share_result = lambda accepted: record_share_result(
        recorder, accepted, args.worker, desc["backend"])
    # Scan chunks sized to about one second of this machine's
    # measured rate, so a fresher template preempts the search
    # within about a second instead of after a long fixed chunk.
    import math
    probe_rate = gpu_engine.LAST_PROBE_RATE
    if probe_rate > 0:
        span_size = 1 << max(20, min(24, int(math.log2(probe_rate))))
    else:
        span_size = 1 << 22
    print(f"scan chunk: {span_size:,} nonces "
          f"(probe rate {probe_rate:,.0f} H/s)", flush=True)
    deadline = time.time() + args.duration
    total_hashes = 0
    t_start = time.time()
    last_log = 0
    en2_counter = 0
    best = 0.0
    submitted = 0
    while time.time() < deadline and not client.stop_flag:
        with client.lock:
            job, gen, diff = client.current_job, client.job_generation, client.difficulty
        if job is None or diff is None or not client.authorized.is_set():
            time.sleep(0.3); continue
        en2_counter += 1
        en2 = "%0*x" % (client.extranonce2_size * 2, en2_counter)
        header, _merkle, _cb = build_header(job, client.extranonce1, en2, 0, "wordswap")
        target = target_for_difficulty(float(diff))
        # scan in ~1 second chunks so a new job preempts quickly
        nonce = 0
        while nonce < (1 << 32):
            with client.lock:
                if client.job_generation != gen:
                    break
            span = min(span_size, (1 << 32) - nonce)
            span_start = nonce
            hit = engine.search_first(header, target, nonce, span)
            attempts = call_attempts(engine, hit, nonce)
            total_hashes += attempts
            accountant.record_search(
                header, span_start, attempts, hit is None,
                worker=args.worker, backend=desc["backend"])
            nonce += span
            if hit is not None:
                found, digest = hit
                # Confirm the candidate before anything is
                # submitted (EXP-036): the reconstructed header
                # goes through mining/candidate_verify.py, which
                # recomputes SHA-256d with hashlib AND with the
                # independent pure-Python implementation, and
                # judges the network target by exact nBits
                # semantics (check_pow). The backend digest must
                # agree with both recomputations, the header's
                # target must be a legal target, the exact
                # integer share compare must pass, and the
                # template must still be the freshest one. Only
                # confirmed candidates are sent, and block
                # candidacy comes from check_pow alone, never
                # from the float-derived pool target.
                check_header, _m, _c = build_header(
                    job, client.extranonce1, en2, found, "wordswap")
                v = verify_candidate(check_header, POW_LIMIT_MAINNET,
                                     share_target=target)
                hash_match = (digest == v["digest"]
                              and v["digests_agree"])
                with client.lock:
                    fresh = client.job_generation == gen
                confirmed = (hash_match
                             and v["valid_header"]
                             and v["meets_share_target"]
                             and fresh)
                is_block_candidate = v["meets_network_target"]
                record_candidate_event(
                    recorder,
                    hash_match and v["valid_header"]
                    and v["meets_share_target"],
                    is_block_candidate,
                    args.worker, desc["backend"])
                d = difficulty_of(digest)
                best = max(best, d)
                ev.log("candidate_confirmed" if confirmed
                       else "candidate_rejected",
                       nonce=found, difficulty=d,
                       job_id=job.get("job_id"),
                       independent_hash_match=hash_match,
                       meets_pool_target=v["meets_share_target"],
                       meets_network_target=is_block_candidate,
                       verify_reason=v["reason"],
                       template_still_fresh=fresh)
                if confirmed:
                    client.submit(job, en2, found)
                    submitted += 1
                    recorder.record("pool_shares_submitted", 1,
                                    worker=args.worker,
                                    backend=desc["backend"])
                    ev.log("share_submitted", nonce=found,
                           difficulty=d, job_id=job.get("job_id"),
                           is_block_candidate=is_block_candidate)
                    print(f"SHARE submitted nonce={found} "
                          f"diff={d:.2f}", flush=True)
                nonce = max(nonce, found + 1)
        now = time.time()
        if now - last_log > 10:
            last_log = now
            elapsed = now - t_start
            rate = total_hashes / max(elapsed, 1)
            line = (f"t={elapsed:6.0f}s job={job.get('job_id')} "
                    f"height_job prev={job.get('prevhash','')[:12]} "
                    f"pool_diff={diff} hashes={total_hashes:,} "
                    f"rate={rate:,.0f} H/s best={best:.4f} "
                    f"shares_submitted={submitted}")
            print(line, flush=True)
            with open(STATUS, "w") as f:
                f.write(f"MAINNET LIVE MINING\n{line}\n"
                        f"worker={user}\npool={pool_host}:{pool_port}\n"
                        f"{endpoint_line}\n{backend_line}\n")
            ev.log("status", hashes=total_hashes, rate=rate, best=best,
                   submitted=submitted,
                   statistics=stats.snapshot()["totals"],
                   statistics_errors=recorder.errors)
    print("duration complete", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
