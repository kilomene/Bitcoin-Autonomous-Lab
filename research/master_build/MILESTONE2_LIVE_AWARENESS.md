# Milestone 2: Live Mining Awareness

Date: 2026-11-15 PST (demonstration run 2026-11-16T00:33 to
00:35 UTC). Built on the Milestone 1 foundation in
agent/intelligence/. New module: agent/intelligence/awareness.py
(the Awareness class over the Milestone 1 Agent facade). New CLI
subcommand: `python3 -m agent.intelligence awareness [window_s]`.
New tests: tests/test_agent_awareness.py (make
test-agent-awareness, added to test-all, which now has 35
targets).

Hard boundary honoured: the awareness layer is read-only. It
never starts, stops, restarts or signals the miner, the
autopilot or the node. Every operation is gated on the existing
L1 read-only permission (inspect_status) and recorded in the
facade's audit log (.local/agent-audit.jsonl, operation
awareness_observe). No production file was modified: mining/,
gpu/, agent/autonomous.py and agent/interface.py are untouched.
Files edited outside the new module: agent/intelligence/
__main__.py (the awareness subcommand; the status subcommand's
behaviour is unchanged) and the Makefile (one new target).

## What was built

- snapshot(): one coherent live picture from real sources
  only: the autopilot heartbeat (.local/heartbeat.json), the
  EvidenceCounter census (.local/evidence-count.json), the
  miner status file (.local/mainnet-status.txt, parsed for
  job, backend, pool difficulty, session hashes and rate,
  shares submitted; fields a file does not carry are reported
  absent by name), the evidence log tail (the last status
  event republishes the live process's MiningStatistics
  snapshot, the EXP-037 categories), the node through a
  read-only getblockchaininfo RPC with a bounded 30 s timeout
  and a single attempt, and the endpoint config mode. Every
  source read is timed and the times are in the report.
- rate_observation(window_s): samples the census and the
  evidence tail twice across a real window. Primary figure:
  the delta of the live process's backend_hashes counter over
  the interval between the two distinct status events
  bracketing the window. Share rate: census accepted-share
  delta over the wall window. A difficulty-weighted implied
  rate is produced only when shares were accepted in the
  window and a pool share difficulty is recorded, and is
  labelled an estimate with its method.
- degradation_check(baseline): flags heartbeat staleness
  (threshold 120 s, the interface module's own constant),
  restarts above 0, rejected share ratio above 0.05, rate
  drop beyond a 0.25 fraction against the baseline, and the
  node falling behind its headers. Every flag names its
  evidence; checks whose inputs are absent are listed as not
  evaluated, never silently passed.
- coverage_report(): what unique coverage can honestly be
  stated for the live pool path, and what cannot (see the
  coverage section below).
- observe_cycle(): one full pass. It builds its baseline
  from a snapshot taken at cycle start, measures the rate,
  takes a final snapshot, checks degradation against that
  baseline, reports coverage, writes the cycle into the
  audit log and into the standing L1 task "live awareness
  observe" (task id live-awareness-observe in the planning
  registry, state active, one evidence entry per cycle), and
  returns the structured operational report. Agent overhead
  is timed per phase and reported.

## Demonstration run

Command: `python3 -m agent.intelligence awareness 120`
Run at 2026-11-16T00:33 to 00:35 UTC against the live system
(mining on public-pool.io, endpoint mode pool, backend
v512dual, worker htch-runtime). Full operational report
output, exactly as printed:

```json
{
  "kind": "awareness_operational_report",
  "ts_utc": "2026-11-16T00:35:34Z",
  "baseline_note": "the degradation baseline was constructed from the census and evidence status event at cycle start, inside this same cycle",
  "snapshot": {
    "ts_utc": "2026-11-16T00:35:34Z",
    "autopilot": {
      "running": true,
      "note": "live heartbeat",
      "autopilot_pid": 4904,
      "miner_pid": 4912,
      "miner_state": "running",
      "miner_uptime_s": 4208.3,
      "restarts": 0,
      "heartbeat_age_s": 24.5,
      "evidence_age_s": 5.9,
      "shares_accepted_total": 410
    },
    "evidence_census": {
      "present": true,
      "accepted": 410,
      "rejected": 8,
      "share_results": 418,
      "consistent": true
    },
    "miner_status_file": {
      "present": true,
      "job_id": "e457fda",
      "prevhash_prefix": "b1f80d083252",
      "pool_diff": 1.0,
      "session_hashes": 100311201088,
      "session_rate_hs": 23893531,
      "best_share_difficulty": 23.012,
      "shares_submitted": 23,
      "session_elapsed_s": 4198.0,
      "worker": "bc1q528egeqsvv8aa382j43edxskqw6x7zxc2xpcf3.htch-runtime",
      "pool_endpoint": "public-pool.io:21496",
      "backend": "v512dual",
      "absent_fields": []
    },
    "evidence_tail": {
      "last_status_event": {
        "ts": "2026-11-16T00:35:03.649602+00:00",
        "hashes": 100311201088,
        "session_rate_hs": 23893530.57,
        "best_share_difficulty": 23.012,
        "submitted": 23,
        "statistics": {
          "backend_hashes": 100311201088,
          "unique_headers": 144,
          "unique_nonces": 100311201088,
          "repeated_work": 0,
          "candidates": 24,
          "verification_hashes": 48,
          "valid_candidates": 24,
          "pool_shares_submitted": 23,
          "pool_shares_accepted": 23,
          "pool_shares_rejected": 0,
          "network_target_candidates": 0,
          "blocks_submitted": 0,
          "blocks_accepted": 0,
          "blocks_rejected": 0,
          "unique_coverage": 100092870656,
          "actual_computations": 100311201088,
          "duplicate_deliveries": 0,
          "stale_reports": 0
        },
        "statistics_errors": 0
      },
      "last_job_event": {
        "ts": "2026-11-16T00:35:05.001527+00:00",
        "event": "job",
        "job_id": "e459636",
        "generation": 146,
        "nbits": "17021673",
        "clean_jobs": false,
        "branches": 13
      },
      "last_share_result": {
        "ts": "2026-11-16T00:33:01.414473+00:00",
        "event": "share_result",
        "id": 26,
        "accepted": true,
        "error": null
      }
    },
    "node": {
      "reachable": true,
      "blocks": 448622,
      "headers": 976037,
      "initialblockdownload": true,
      "blocks_behind_headers": 527415,
      "error": null
    },
    "endpoint": {
      "mode": "pool",
      "pool_host": "public-pool.io",
      "pool_port": 21496,
      "solo_host": "127.0.0.1",
      "solo_port": 3333
    },
    "read_times_ms": {
      "heartbeat": 0.383,
      "census": 0.066,
      "status_file": 0.145,
      "evidence_tail": 91.596,
      "node_rpc": 19402.436,
      "endpoint": 3.659
    }
  },
  "rate_observation": {
    "window_requested_s": 120.0,
    "window_wall_s": 120.48,
    "shares_delta": 0,
    "share_rate_per_s": 0.0,
    "backend_hashes_delta": 2969567232,
    "backend_rate_hs": 24544788.25,
    "backend_interval_s": 120.99,
    "implied_difficulty_weighted_rate_hs": null,
    "pool_share_difficulty": 1.0,
    "method": "share rate: EvidenceCounter census accepted-share delta over the wall window. backend rate: delta of the live process MiningStatistics backend_hashes counter, republished in evidence log status events, over the interval between the two status events bracketing the window. no difficulty-weighted implied rate: no pool share difficulty recorded by the sampled sources, or no accepted shares in the window.",
    "notes": []
  },
  "degradation": {
    "flags": [],
    "not_evaluated": [],
    "thresholds": {
      "heartbeat_stale_s": 120.0,
      "rejected_ratio": 0.05,
      "rate_drop_fraction": 0.25
    }
  },
  "coverage": {
    "statistics_event_ts": "2026-11-16T00:35:03.649602+00:00",
    "census": {
      "accepted": 410,
      "rejected": 8,
      "share_results": 418
    }
  },
  "overhead": {
    "phase_times_s": {
      "baseline_snapshot_s": 11.7983,
      "rate_observation_s": 121.1968,
      "final_snapshot_s": 19.5063,
      "degradation_check_s": 0.0009,
      "coverage_report_s": 0.3001
    },
    "total_wall_s": 152.8024,
    "active_overhead_s_excluding_window": 32.8024,
    "observation_window_s": 120.0
  },
  "task": {
    "task_id": "live-awareness-observe",
    "state": "active",
    "evidence_added": "observe_cycle 2026-11-16T00:35:34Z accepted=410 rejected=8 backend_rate_hs=24544788.24754217 flags=[]"
  }
}
```

(The printed report carries a few additional fields elided
here for length: the autopilot section's raw heartbeat
fields, the census file's offset and head fingerprint, and
the coverage section's can_state and cannot_state texts,
which are reproduced in the coverage section below. Every
number above is copied from the run's own output.)

## Rate observation

Measured live backend rate: **24,544,788 H/s** (about
24.5 MH/s). Method: the live process's MiningStatistics
backend_hashes counter, republished in evidence log status
events, rose by 2,969,567,232 over the 120.99 s interval
between the two status events bracketing the 120 s window.
This is a live observation of the production search path
(category E conditions: the real miner, the real pool job,
this contended VM), not a benchmark.

Share rate over the same window: 0 accepted shares in
120.48 s of wall time (census delta 0). At pool difficulty 1
and about 24.5 MH/s the expected number of accepted shares
in 120 s is about 0.69, so a zero count is unremarkable and
says nothing about the hash rate either way. Because no
share was accepted inside the window, no
difficulty-weighted implied rate was computed for this
window; the recorded pool share difficulty was 1.0
(pool_diff in the miner status file). The miner's own
session-average rate field at the final status event read
23,893,531 H/s over its 4,198 s session, consistent with
the window measurement.

## Degradation check

Baseline: constructed inside this same cycle from the
census and the evidence status event at cycle start, as
observe_cycle is specified to do. For context against the
earlier Milestone 1 observation era: the census then read
406 to 407 accepted shares with 8 rejected; at this cycle's
final snapshot it reads 410 accepted, 8 rejected, 418 share
results, internally consistent.

Result: **no flags**, and no check was left unevaluated.
Heartbeat fresh (age 24.5 s at assembly; the age includes
the slow node RPC read inside the same snapshot, see
overhead), restarts 0, rejected ratio 8/418 = 0.0191 against
the 0.05 threshold, measured window rate 24.54 MH/s against
the baseline session-average 23.89 MH/s (no drop), node
reachable with its headers gap not growing against the
cycle-start baseline (448,622 blocks of 976,037 headers,
initial block download still in progress, the known
standing state).

## Coverage report

What can be stated, from the run's own output:

- The live process's MiningStatistics snapshot (EXP-037
  separated categories) as republished in the evidence log
  status event at 2026-11-16T00:35:03Z: backend_hashes
  100,311,201,088; unique_nonces 100,311,201,088;
  unique_coverage 100,092,870,656; actual_computations
  100,311,201,088; repeated_work 0; candidates 24, all 24
  valid after independent verification; pool shares
  submitted 23, accepted 23, rejected 0 in this session;
  network_target_candidates 0; blocks submitted, accepted
  and rejected all 0. These are the miner process's
  counters for its current session, not a lifetime census.
- The lifetime pool-verdict census (EvidenceCounter over
  the whole evidence log): accepted 410, rejected 8, share
  results 418. Accepted shares are pool verdicts, not
  blocks.

What cannot be stated:

- Exact searched-position coverage for the pool path.
  mining/work_checkpoint.py serves the GBT path only (its
  scope boundary: the Stratum pool path is untouched by it;
  its work separation is the pool-assigned job and
  extranonce split, ephemeral per session), so no frontier
  checkpoint exists for the live pool miner and no
  (extranonce, nonce) frontier can be quoted for it.
- Remaining work for the pool path: the pool assigns jobs
  and there is no finite declared search space per job from
  this side of the protocol.
- Any statistics figure fresher than the last evidence
  status event: MiningStatistics snapshots live only inside
  the miner process and reach this layer only as
  republished there.

## Agent overhead

Total cycle wall time 152.80 s, of which 120.48 s is the
deliberate observation window. Active overhead excluding
the window: 32.80 s. Almost all of it is the node RPC: the
baseline snapshot took 11.80 s and the final snapshot
19.51 s, and inside the final snapshot the read-only
getblockchaininfo alone took 19.40 s (the known slow-RPC
pattern while the node is in initial block download under
load; it answered inside the bounded 30 s timeout, so no
retry was needed in this run; during the test suite's live
smoke test the same read timed out at 30 s and was reported
honestly as unreachable). File reads are cheap by contrast:
heartbeat 0.38 ms, census 0.07 ms, status file 0.15 ms,
endpoint 3.66 ms; the evidence tail read is the largest
file cost at about 92 ms per read (512 KB tail window), and
the whole coverage phase took 0.30 s. The degradation
check itself took under 1 ms.

## Strategy gap at the measured live rate

strategy.gap_report fed with the best honestly obtainable
live rate figure, the window measurement above
(24,544,788.25 H/s, method stated in the rate section; this
is a live rate, so no recourse to the EXP-031/EXP-032
benchmark rates was needed):

```json
{
  "measured_rate_hs": 24544788.24754217,
  "target_min_hs": 500000000000.0,
  "target_large_hs": 140000000000000.0,
  "pct_of_min_target": 0.004908957649508434,
  "pct_of_large_target": 1.7531991605387264e-05,
  "gap_factor_min": 20370.923348669276,
  "gap_factor_large": 5703858.537627397
}
```

The measured live rate is 0.004909 percent of the 500 GH/s
minimum objective (a gap factor of about 20,371 such
systems) and 0.00001753 percent of the 140 TH/s larger
objective (gap factor about 5,703,859). Targets are
objectives, not established capabilities; nothing in this
milestone narrows that gap. No mainnet block has been
found; the balance remains 0 BTC; pool shares are not
blocks.

## Rejected-hypothesis refusal, from the real code path

A loop record proposing K+W constant folding was advanced
through agent/intelligence/loop.py against the real
research memory. The first advance (observe to hypothesise)
succeeded; the second was refused by the
rejected-hypothesis gate:

```text
state after first advance: hypothesise
REFUSAL: loop demo-kw-folding: hypothesis matches rejected
research memory entry EXP-014; re-proposing a rejected idea
is refused
CITATION: {
  "entry_id": "EXP-014",
  "title": "EXP-014: K+W constant folding for template-fixed MB rounds",
  "status": "REJECTED",
  "source": "research/sha256d/extreme_optimization/EXPERIMENT_REGISTRY.md"
}
```

One precision worth recording: the gate matches on the
recorded wording. Keywords ["K+W folding"] alone did NOT
fire, because the registry entry's text says "K+W constant
folding"; the keywords that fired were ["K+W", "constant
folding"]. The refusal above is from the run with those
keywords.

## Tests

- make test-agent-awareness: ALL AGENT AWARENESS TESTS
  PASSED (50 checks). Unit tests use injected fixture files
  (stale heartbeat flagged, rejected ratio flagged,
  unreachable node reported honestly, missing status fields
  reported absent, rate math on scripted samples,
  observe_cycle audit and task writes) plus one live smoke
  test against the real repo state (census consistency and
  the running verdict against heartbeat freshness).
- make test-agent-intelligence: ALL AGENT INTELLIGENCE
  TESTS PASSED (86 checks). No Milestone 1 regression.
- The status CLI subcommand was run after the change and
  prints the same live status as before (running, census
  409 accepted / 8 rejected / 417 at that moment).
- test-all now lists 35 targets (34 before, plus
  test-agent-awareness).

## What the agent still cannot see

- Pool-side job internals beyond what the miner itself
  publishes: the awareness layer sees the job id, generation,
  prevhash, nbits and ntime from the status file and the
  evidence log, and the pool endpoint from the config. It
  cannot see the pool's own accounting, the pool's view of
  the worker, or anything on the pool side of the Stratum
  connection.
- Anything fresher than the republication cadence: the
  heartbeat is 5 s, evidence status events land roughly
  once a minute, and the census updates as the autopilot
  counts. Between those, the layer is blind by construction.
- The exact searched frontier of the live pool miner (see
  the coverage section): no checkpoint exists for that
  path, so unique coverage rests on the miner's own
  separated counters, taken on trust from its status
  events, cross-checked only against the pool-verdict
  census.
- Why a share was rejected beyond the census count and the
  error field of individual share_result events; the pool
  gives no richer reason channel to this side.
- The node's mempool, peer set and template view: the
  awareness read is deliberately limited to
  getblockchaininfo (blocks, headers, initial block
  download). The node is also not the live miner's job
  source while the endpoint mode is pool; it matters here
  as the staged solo cutover's foundation.
- Whether the pool would accept a block: no block
  candidate has ever met the network target on this path
  (network_target_candidates is 0 in every session), so
  that leg remains unexercised, as before.
