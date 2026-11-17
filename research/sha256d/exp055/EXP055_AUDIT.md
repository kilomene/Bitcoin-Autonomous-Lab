# EXP-055 independent audit

Auditor: independent audit agent (not the author).
Date: 2026-11-17T09:52Z. Host: AMD EPYC 9D25 (confirmed
from /proc/cpuinfo at audit time). Remote HEAD at audit:
0d072d1327d73f0cecfd7c393b5db569a18aa687 (verified live
against the GitHub API during this audit). This audit
did not push anything.

## Verdict: PASS WITH NOTES

Defects: 0. The build's central claims survive
independent, adversarial checking: the predeclaration
is intact and pinned, the campaign arithmetic closes
exactly, proof obligations P1 to P6 hold at the
protocol level under probes the author did not write,
the Gate 5 recovery defect is genuinely fixed in the
shipped code (the original bug reproduced by hand
against the same artifacts), Gate 6's block is on the
lab regtest chain with its nonce inside the leased
range, the two EXP-043 fixes reproduce in form, and
the coordinator is not wired into any live path.

## 1. Predeclaration integrity and campaign provenance

- PREDECLARATION.md sha256 recomputed:
  b455d16ba878144d82abe90b531a58a1fcaa1333576d4c73098b3d59a5de93ea,
  exactly the value the task pins. The same hash is
  pinned in exp055_campaign.py, exp055_overhead.py and
  exp055_gate6.py, and the test suite verifies it at
  run time through the campaign driver's
  check_predeclaration().
- RAW_RESULTS matches the report's claimed runs:
  campaign_20261117T093000Z.json (Gates 1, 2, 3, 5),
  overhead_20261117T094237Z.json (Gate 4),
  gate6_20261117T094316Z.json (Gate 6), gates.log
  consistent with all three. Every figure quoted in
  EXP055_REPORT.md that this audit recomputed (Gate 3
  totals, Fix A 191 ns, Fix B 4.90 ms and 122,278
  bytes, per-operation medians, campaign per-position
  table) matches the record JSON of that gate.
- Gate 4 provenance: the discarded runs are all
  retained and honestly labelled. overhead_run_partial1
  (tuple-indexing crash in the fault driver),
  overhead_run_partial2 (STALE assertion from the
  steal-resync omission), overhead_20261117T093629Z
  (completed run, superseded geometry) and
  overhead_20261117T094046Z (completed run, superseded;
  its 32-worker figures still carry the timed-loop
  accounting poll the record run removed) are all on
  disk, and none of them is the campaign of record:
  gates.log and the report both name
  overhead_20261117T094237Z.json, whose numbers are
  the ones the report prints. The VM-replacement
  interruption is recorded in the report's judgment
  calls; the pre-replacement Gates 1, 2, 3, 5 campaign
  JSON was lost with that replacement and the
  post-replacement run is the record, also as
  recorded. See note N-1 on the run count.

## 2. Gate 1: proof obligations, attacked independently

Beyond rerunning the author's suite (section 9), the
auditor ran 21 probes of its own against the shipped
coordinator, over TCP with a real state directory and
in-process. None broke an obligation:

- Stale token after a persistent restart: after a
  crash (no close), the restarted coordinator returned
  STALE for both complete and progress with the
  pre-restart token; epoch bumped to 1; the in-flight
  lease was reclaimed.
- Duplicate candidate hand-off: submit returned
  ACCEPTED then DUPLICATE before the crash, DUPLICATE
  again after recovery from the candidate journal,
  the drain invoked the verifier exactly once, and a
  post-drain resubmission stayed DUPLICATE and was
  never re-verified (P6).
- Not-holder completion and progress with the correct
  token returned NOT_HOLDER and credited nothing;
  an unknown lease returned UNKNOWN_LEASE.
- Zombie replay: replaying a completed lease after a
  worker restart returned DUPLICATE (idempotent,
  credited once); replaying a reclaimed lease
  returned STALE and credited nothing (P3, P5).
- Steal adversarial: the victim's pre-steal token
  returned STALE after rotation; progress past the
  shrunk boundary with the rotated token was refused;
  progress inside the shrunk boundary with the
  rotated token returned OK; the partition invariant
  held throughout (P2).

## 3. Gate 2: independent model

Verified by inspection: exp055_model.py contains no
import statements at all and no reference to the
coordinator's code; mining/coordinator.py contains no
reference to the model. The implementations are
structurally different, as claimed: the model keeps
the full lease history and list-shaped chunks per
slice and computes coverage from interval lists; the
coordinator keeps chunk dicts, an active-lease index
per worker, a chunk-location map and compact
tombstones. The auditor reran the differential with
five seeds the author did not use (777001 to 777004
and 424242; the campaign of record used 20261120 and
up): 1,130 comparisons, ALL EQUAL. The regression
suite's reduced set (6 scripts, 1,205 comparisons)
also passed during this audit.

## 4. Gate 3: exactness recomputed from the JSON

Recomputed from campaign_20261117T093000Z.json
per-trial records, independently of the report:
66 trials (60 in-process, 6 TCP), sum of declared
positions 737,792, matching the claimed total;
every trial's unique coverage equals its declared
total (zero inexact trials); repeated computations
sum to 307,682 and are carried in their own counter
in every trial record, never inside unique coverage
(EXP-038 frontier honesty: unique grows only on
completion, and the per-trial identity was checked
trial by trial, not only in aggregate). Injection
tallies close exactly, per-trial sums against the
campaign totals: 2,807 deaths, 2,070 worker restarts,
1,037 expiries, 862 steals, 981 coordinator restarts,
4,102 zombie replays, 2,697 duplicate deliveries,
938 not-holder attempts, 1,160 duplicate candidate
submissions, 8,657 reclaims. The coordinator's
stale_reports total (4,102) equals the zombie count
exactly.

## 5. Gate 5 defect: fix verified, original bug reproduced

The shipped load path in CoordinatorServer.__init__
loads the snapshot state WITHOUT the restart rule,
replays the journal tail against that state, and
applies the restart rule once to the rebuilt state,
exactly as the report describes. The auditor
reconstructed the original order by hand (load,
apply restart rule, then replay) against a fresh
state directory built for this audit: the buggy order
replayed the post-snapshot completion onto a wiped
registry and lost it (unique coverage 128 of the
live 256) and regressed the token counter (1 against
the live 2). The shipped server, started on the same
artifacts, preserved the post-snapshot completion
(unique 256), preserved the token counter and
reported replayed_ops 2. The fix is real and is in
the shipped code. See note N-2 on classification.

## 6. Gate 6: regtest block verified on chain

Queried the lab regtest node directly during this
audit: getblockhash(2372) returns
2334ac9cd173fc867bea7449852751e227104cfa7dfc511ceaed3a4687f2c4fb,
the block is in the active chain (2 confirmations at
audit time), the nonce decoded from its stored
header is 524289, inside the leased range
[0, 1048576), and the EXP-036 verifier
(verify_candidate, regtest limit) classifies the
stored header block_candidate, matching the gate6
JSON's verdict record. verify_chain_acceptance now
reports the block in-chain rather than tip, because
blocks 2373 (hash
4db21600b02f445172c7fc3fb481cd31f5b458ab7da09887b792e66ccb7af539,
also verified at height 2373, the regression suite's
block from the build) and 2374 (produced by the
suite during this audit, nonce 131072, also inside
its leased range) now sit on top of it. Height
advanced exactly 2371 to 2372 in the record run.

## 7. EXP-043 fixes

Verified by code inspection and reproduced in form
(contention noise allowed, as briefed):

- The lease store holds only active leases:
  CoordinatorCore.leases plus _active_by_worker;
  _kill_lease removes the lease and leaves only a
  compact tombstone (_completed_ids mapping to the
  holder, or a _dead_ids entry). The event log is a
  bounded deque (1,024) and is never snapshotted.
- Audit measurement at history 2,000: the
  starvation holds-lease query is flat, 200 ns at
  history 0 and 200 ns at 2,000 completed leases
  (record: 191 ns at 0 and 8,000), while the EXP-035
  prototype's same query grew 551 ns to 153,560 ns
  over the same span (record at 8,000: 637,126 ns).
  After 2,000 completions the coordinator held 1
  active lease and 2,000 compact tombstones; the
  prototype retained 2,001 full records.
- Snapshots serialise live state only: snapshot()
  carries job, slices, active leases, workers,
  counters and tombstones, with no events key
  (asserted in the suite at 8,192 chunks and checked
  by the auditor at a history-loaded shape: 512 live
  chunks plus 2,000 dead issuances serialised to
  68,278 bytes with 2,000 dead tombstones and no
  event history). The record's history-loaded point
  (4.90 ms and 122,278 bytes against the prototype's
  248.0 ms at 8,000 dead issuances) is in the record
  JSON and matches the report.

## 8. Safety and production diff

- Not wired in: no production module imports the
  coordinator. A tree-wide search finds mining.coordinator
  referenced only by the exp055 harness and the
  regression suite; mining/mainnet_live.py,
  mining/autopilot.py (the autopilot lives at
  mining/autopilot.py), mining/solo_server.py,
  mining/engine.py and mining/endpoint_config.py
  contain no coordinator import (the two grep hits
  elsewhere are a pre-existing docstring word in
  stratum_client.py and a comment in engine.py).
  The live endpoint config (.local/mining-endpoint.json,
  mtime 2026-11-14) is unchanged and still pool mode.
- Loopback only: the coordinator binds 127.0.0.1 by
  default, the harness uses 127.0.0.1 or the
  in-process transport, and no other host appears
  anywhere in the build. No other machine was
  contacted; fleet activation (roadmap F2) remains
  owner-gated and untouched.
- Production blob diff against remote HEAD
  0d072d1327d73f0cecfd7c393b5db569a18aa687, computed
  by the auditor with an independent full-tree
  comparison (1,230 remote blobs, tree not
  truncated): content differs only in Makefile and
  the three registries, plus the excluded live file
  evidence/mainnet-live.jsonl; local-only files are
  exactly mining/coordinator.py, the exp055 set,
  tests/test_exp055_coordinator.py, and the
  sanctioned .so artifacts under exp032, exp041 and
  exp044; remote-only files: none. Nothing else in
  production moved.

## 9. Suites (run one at a time, never parallel)

- make test-exp055: 23 checks, ALL PASSED, including
  its Gate 5 scenario and a live Gate 6 run that
  produced regtest block 2374 during this audit.
- make test-exp038 (neighbour check): ALL PASSED.
  No shared-regtest contamination was encountered;
  the only chain advancement during the suites was
  test-exp055's own Gate 6 block, which is its
  designed behaviour.

## 10. Registries, Makefile, scans

- JSON registry (research/EXTREME_RESEARCH/
  EXPERIMENT_REGISTRY.json): 105 entries; EXP-055
  present with status PROVEN; last entries EXP-053,
  EXP-054, EXP-055.
- Markdown registries: the EXP-055 appends in
  research/sha256d/experiment_registry.md and
  research/sha256d/extreme_optimization/
  EXPERIMENT_REGISTRY.md are byte-identical (3,674
  bytes each, compared byte for byte from the append
  marker), and both end with Next unreserved ID:
  EXP-056.
- Makefile: test-exp055 target present; test-all
  carries 46 targets.
- Scans over the full push set (coordinator, exp055
  files, test suite, Makefile, three registries):
  U+2014 count zero; high-signal secret patterns
  zero.

## Notes

- N-1 (Gate 4 run count): the report says Gate 4
  took four runs to reach its record, but five run
  artifacts are retained (four partial logs and the
  record JSON, plus two superseded complete JSONs).
  The narrative's mapping onto the partial logs is
  not one-to-one explicit. Every artifact is
  retained, the record run is unambiguous, and no
  discarded run is presented as the record, so this
  is a narration wrinkle, not a provenance defect.
- N-2 (Gate 5 defect classification): the recovery
  defect was found by Gate 5's first execution and
  fixed before the campaign of record; the verdict
  rests on the predeclaration's build-work reading
  (a defect found and fixed during the build, before
  the campaign runs, is ordinary build work). The
  disclosure is complete (report judgment calls and
  the registry entry both record it), and the fixed
  behaviour is independently verified in section 5.
  A stricter reading of the verdict mapping would
  record Gate 5 as failed-then-fixed; the evidence
  either way is fully on record.
- N-3 (runtime state directories): RAW_RESULTS/
  gate5_state and gate6_state exist locally as
  runtime state. The report already excludes them
  from the push set; whoever pushes must honour
  that exclusion.
- N-4 (Fix A remainder, author's own disclosure,
  confirmed in the record JSON): at 8,000 history
  the full lease-grant call (coordinator 2,502 us)
  is dominated by the scan for the next pending
  chunk, a path both implementations inherit from
  the prototype and not one of the two EXP-043
  defects. The profiled cost centre itself, the
  holds-lease query, is flat, as section 7 shows.
- N-5 (suite side effect): make test-exp055 re-runs
  Gate 6 and Gate 5, so it advances the shared
  regtest chain by one block and rewrites the two
  state directories on every run. Expected, but
  anyone diffing RAW_RESULTS after a suite run will
  see a new gate6 JSON; this audit's run added
  gate6_20261117T095151Z.json (block 2374).

## UNVERIFIED register

- Multi-machine coordination: UNVERIFIED. No other
  machine was contacted by the build or this audit.
- Real-network latency: UNVERIFIED. All figures are
  loopback or in-process on this VM.
- Cross-machine scaling: UNVERIFIED. Worker counts
  are simulated workers on one contended VM.
- Real fleet behaviour, clock skew across machines,
  partial network failure, production template rates
  and chunk sizes: UNVERIFIED.
- Live deployment of the coordinator alongside the
  production miner: UNVERIFIED and not attempted;
  deployment and fleet activation stay owner-gated.
- Other hosts: UNVERIFIED. All measurement, the
  build's and this audit's, is the AMD EPYC 9D25
  host.
- Audit-scope limits: the auditor's Gate 2
  differential used 5 fresh seeds (1,130 comparisons)
  plus the suite's reduced 6, not a second full
  40-script run; the auditor's Fix A and Fix B timing
  reproductions used history 2,000 rather than the
  record's 8,000 point (the 8,000 store shape and
  snapshot figures stand in the record JSON and were
  recomputed for internal consistency, not re-measured
  at full scale).
