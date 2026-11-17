# EXP-055 report: production wire protocol and persistent coordinator

Date: 2026-11-17. Experiment: EXP-055, portfolio
NOVA-ER-0015, roadmap F1. Predeclaration:
PREDECLARATION.md in this directory, sha256
b455d16ba878144d82abe90b531a58a1fcaa1333576d4c73098b3d59a5de93ea,
written before the build's campaign ran and pinned in
every driver. Raw record: RAW_RESULTS/
(campaign_20261117T093000Z.json,
overhead_20261117T094237Z.json,
gate6_20261117T094316Z.json, gates.log, run logs).

## Verdict: ALL GATES PASS

By the predeclaration's verdict mapping, EXP-055 is
COMPLETE. Classification: **PROVEN** for the
protocol-level properties measured on this VM: proof
obligations P1 to P6 at the protocol level, exact
coverage under a 66-trial randomised fault campaign,
differential accounting against an independent model,
persistent-coordinator restart behaviour, and one
regtest block produced through coordinator-assigned
work (a second followed in the regression suite).
Overhead is recorded in per-position cost form
against the EXP-043 baselines, with the two EXP-043
prototype defects carried in as measured fixes.

This is not a fleet claim. Fleet activation (roadmap
F2) stays owner-gated, no other machine was contacted,
activated or measured, and the UNVERIFIED register at
the end of this report stands in full.

## What was built

- mining/coordinator.py (new production component,
  beside mining/solo_server.py): a persistent
  coordinator holding the EXP-035 Work Lease Manager,
  worker registry and Candidate Queue behind a wire
  protocol. Frames are length-prefixed (4-byte
  big-endian length, UTF-8 JSON payload, 4-byte CRC32);
  a frame that fails its checksum or length bound is
  discarded and counted, never absorbed. Persistence
  is an append-only operation journal plus atomic
  snapshots (temp file, fsync, os.replace, the
  EXP-038 pattern); the candidate queue keeps its own
  persist-before-acknowledge journal. Runnable as a
  process: python3 -m mining.coordinator. The same
  frame-handling path serves the TCP listener and the
  in-process protocol transport used by the campaign,
  so every test operation passed through frame encode,
  checksum verification and decode.
- The EXP-035 semantics are unchanged (slices,
  fencing tokens, steal with victim token rotation,
  reclaim into examined_before, EXP-038 frontier
  honesty: the frontier of credited work advances only
  on completion). The single-machine ResourceRegistry
  in agent/intelligence/resources.py remains the local
  behaviour; nothing in the live mining paths imports
  the coordinator, and not deploying it is the
  rollback. Production miner, autopilot, solo server,
  endpoint config and live stack untouched.
- research/sha256d/exp055/: exp055_model.py (the
  independent Gate 2 model, written from the design
  document, interval-based, sharing no code with the
  coordinator), exp055_campaign.py (Gates 1, 2, 3, 5),
  exp055_overhead.py (Gate 4), exp055_gate6.py
  (Gate 6).
- tests/test_exp055_coordinator.py behind a new
  Makefile target test-exp055; test-all becomes 46.
  Suite result: 23 checks, ALL PASSED.

## Gate 1: proof obligations at the protocol level

The EXP-035 targeted set, re-run with every operation
carried over the wire protocol, over both transports:
22 of 22 PASS (11 tests in-process, 11 over TCP
loopback). Foreign fleet rejected; duplicate
completion idempotent; restart replay never credited
(repeated accounting exact at 32); lease expiry
reclaims; coordinator restart kills all pre-restart
tokens and the job then completes exactly (repeated
64); steal rotates the victim token (old token STALE,
wrong identity NOT_HOLDER, both halves completed
exactly once, 256 of 256); starved worker must
re-register; declaration arithmetic exact (32 slices,
32,000 declared); candidate queue dedup on the full
header identity; stale-generation candidates dropped
at drain, never verified; wire integrity (corrupted
frame discarded and counted; truncated frame never
dispatches: outright over the in-process transport,
and over TCP the server simply waits for the rest of
the stream, which is the correct stream behaviour).

## Gate 2: differential accounting

40 seeded operation scripts against the independent
model: 8,460 comparisons (every progress and
completion status, lease ids, tokens and shapes on
lease and steal, all twelve accounting counters, and
the completed-interval sets at checkpoints and at
script end). ALL EQUAL. The two implementations share
no code: the coordinator prunes finished leases into
compact tombstones and indexes active leases per
worker; the model keeps full history and computes
coverage from interval lists.

## Gate 3: randomised fault campaign

66 trials, all closing with exact coverage: 60 over
the in-process protocol transport (seed 20261117) and
6 over TCP loopback with separate connections (seed
20261118), in the EXP-035 campaign shape. Aggregate:
737,792 declared positions completed exactly (EXP-035
prototype campaign: 609,280 over 60 trials), with
307,682 repeated computations accounted separately.
Injections across the campaign: 2,807 worker deaths,
2,070 worker restarts, 1,037 expiry events, 862
legitimate steals, 981 coordinator restarts, 4,102
zombie restart replays (all STALE, none credited),
2,697 duplicate completion deliveries, 938 not-holder
attempts, 1,160 duplicate candidate submissions
(all detected; the verifier ran exactly once per
unique candidate identity in every trial). Reclaims:
8,657. Zero inexact trials: the portfolio failure
criterion (any single inexact coverage trial) did
not occur.

## Gate 4: overhead, per-position cost form

All figures are this VM (AMD EPYC 9D25, load average
7.5 to 16.4 during the overhead run, live miner and
node running), medians of 3 sessions. Nothing here is
a multi-machine figure.

Per-operation protocol round trips (nanoseconds):

| operation | in-process protocol | EXP-043 prototype raw call |
|---|---|---|
| register | 20,340 | 730 |
| heartbeat | 16,475 | 220 |
| lease grant | 28,793 | 3,100 to 4,700 |
| progress | 17,651 | 1,000 to 2,000 |
| complete | 19,525 | 2,600 to 4,400 |
| candidate submit (new) | 20,495 | 770 |
| candidate submit (dup) | 19,439 | 800 |

The difference is the protocol itself: framing, JSON,
checksum, dispatch and the coordinator lock, paid per
operation at roughly 17 to 29 microseconds on this
contended VM. TCP loopback round trips (sequential,
one driver process, separate connections per worker):
34 to 56 microseconds per operation at 1, 4 and 16
workers, flat within contention noise. The EXP-043
wire shim measured a 33 to 55 microsecond floor at 1
worker with concurrent worker processes and about
1 millisecond at 16 workers under process contention;
the two TCP measurements differ in method (sequential
versus concurrent drivers) and neither is a network
figure.

Fix A (prune the lease table), measured against the
prototype in the same session. The starvation check's
holds-lease query, the operation EXP-043 profiled at
67 percent of campaign CPU: coordinator 191 ns at
history 0 and 191 ns at 8,000 completed leases
(flat; the check reads the worker's own active set).
Prototype: 531 ns at history 0 and 637,126 ns at
8,000 (the unpruned history scan). After 8,000
completions the coordinator's lease store holds 1
active lease and 8,000 compact tombstones; the
prototype retains 8,016 full lease records. One
honest remainder: the full lease-grant call at that
history (coordinator 2,502 us, prototype 905 us over
the protocol and raw paths respectively) is dominated
in both by the scan for the next pending chunk across
the test shape's 8,064 one-chunk slices, a scan both
implementations inherit from the prototype's grant
path and not one of the two EXP-043 defects; at
small-state shapes the grant is the table figure
above.

Fix B (bound snapshot cost), same session. At zero
history a snapshot is live state in both
implementations and the two are within contention
noise of each other across runs (this run: 512
chunks, coordinator 2.18 ms vs prototype 18.9 ms;
2,048 chunks, 16.6 vs 30.6 ms; 8,192 chunks, 132.9
vs 91.2 ms; an earlier run read 74.7 vs 195.2 ms at
8,192). The defect EXP-043 named is history: with
512 live chunks plus 8,000 dead lease issuances, the
coordinator snapshot is 4.90 ms and 122,278 bytes
(8,000 compact tombstones, no event log), against
the prototype's 248.0 ms deep-copying 8,000 retained
lease records and 16,002 retained events: about 51x.
Snapshot size is proportional to live state plus
tombstone ids, never to event history. EXP-043's
own baselines for the prototype were 13.3 ms at 512
chunks, 126.8 ms at 2,048 and 420.3 ms at 8,192,
under its session's contention.

Campaign wall time per completed position, EXP-043
geometry (declared 131,072, 32 chunks per slice),
in-process protocol:

| workers | EXP-055 no-fault | EXP-055 fault-lite | EXP-043 no-fault | EXP-043 fault mix |
|---|---|---|---|---|
| 2 | 116 ns | 101 ns | 10 ns | 1,214 ns |
| 8 | 843 ns | 2,040 ns | 131 ns | 13,764 ns |
| 32 | 9,324 ns | 29,049 ns | 8,513 ns | 1,525,761 ns |

Read plainly: at low fault the protocol costs more
per position than the prototype's raw in-process
calls (the per-operation framing cost above, spread
over fewer positions per chunk at larger worker
counts). Under faults at scale the comparison
inverts: the EXP-043 fault mix at 32 workers spent
1.53 ms per position and its 128-worker trial never
completed inside 600 s, while the coordinator
completes its fault-lite points at 2,040 ns (8
workers) and 29,049 ns (32 workers). The fault mixes
differ and the difference is stated, not hidden:
EXP-043's mix spent a 40-restart budget per trial on
snapshot-heavy coordinator restarts; the EXP-055
fault-lite points inject deaths, restarts, expiries,
steals and duplicates but no coordinator restarts
(restart cost is the Fix B snapshot path, measured
separately). No scaling claim beyond this VM is
made from any of these figures.

## Gate 5: coordinator restart with in-flight leases

Over TCP with a real state directory: a mid-session
snapshot was written, more work completed after it,
then the coordinator was crashed with no shutdown
snapshot. The restarted coordinator replayed 2
journal operations past the snapshot, reached epoch
1, preserved the token counter, returned STALE for
the pre-restart in-flight token, reclaimed the
in-flight lease with its 64 examined positions moved
to repeated accounting on re-lease, preserved the
completed coverage including the post-snapshot
completion (256 of 1,024 at that point), and
recovered the candidate journal so the submitted
candidate stayed pending and deduplicated (P6). A
clean second restart reached epoch 2 and the
verified candidate was never re-verified. The job
then completed exactly: 1,024 of 1,024.

## Gate 6: regtest block through coordinator-assigned work

A job was declared from the regtest node's own
getblocktemplate (height 2372, one slice, one chunk
of 1,048,576 nonces). The worker leased the range
over TCP, searched only inside it through the
production v512dual backend, and found nonce 524,289
inside [0, 1048576). The candidate went through the
candidate protocol (duplicate submission detected),
the coordinator's EXP-036 verifier classified it
block_candidate, and only the coordinator side
submitted: submitblock returned null,
verify_chain_acceptance reported tip, and the height
advanced exactly 2371 to 2372. Block hash
2334ac9cd173fc867bea7449852751e227104cfa7dfc511ceaed3a4687f2c4fb.
The regression suite re-ran Gate 6 end to end and
produced the next block the same way: height 2373,
hash
4db21600b02f445172c7fc3fb481cd31f5b458ab7da09887b792e66ccb7af539,
nonce 524,288. The single-slice, single-chunk job
shape is stated as it is: the gate proves the
assignment, hand-off, verification and submission
path on a real template, not a multi-slice search.

## Judgment calls and discarded runs

- Gate 5's first execution caught a real defect in
  the build: snapshot recovery applied the restart
  rule before journal replay, so post-snapshot
  operations replayed against a wiped registry and
  failed silently (the token counter did not
  survive). Fixed in the load path: state loads
  without the rule, the journal replays against the
  live-shaped state, and the restart rule applies
  once to the fully rebuilt state. This was build
  work before the campaign of record, per the
  predeclaration; the campaign above ran after the
  fix. CoordinatorCore.restore (used by the in-place
  restart operation) is unchanged and correct for
  its no-journal case.
- Candidate operations are journaled in the
  operation journal for audit but skipped during
  replay: candidate state is owned by the candidate
  journal (recovered first), and re-executing a
  submit or drain would double-count submissions
  and re-run verification, breaking P6.
- A clean close() writes a snapshot, keeping epochs
  monotonic across clean restarts (Gate 5's epoch 2);
  the crash path (no close) is exercised separately
  in the same gate.
- Gate 4 took four runs to reach its record. The
  first was interrupted by a VM replacement (host
  still AMD EPYC 9D25 afterwards) and rerun whole,
  per the predeclaration. The second and third were
  discarded for harness defects found in the open
  (a tuple-indexing bug in the fault driver, and a
  steal-resync omission that made a correctly
  rotated token read as a failure; both harness
  bugs, not coordinator behaviour, and the partial
  logs are retained as overhead_run_partial1 to 4).
  The fourth used a fixed chunk geometry that did
  not match EXP-043's; the record run aligns the
  geometry (32 chunks per slice) and removes an
  accounting() poll from the timed loop, the same
  harness-noise correction EXP-043 recorded for its
  own first campaign run. All partial logs and the
  superseded overhead JSON are retained in
  RAW_RESULTS/.
- The full campaign (Gates 1, 2, 3, 5) also ran once
  before the VM replacement with identical Gate 3
  totals (737,792 positions, deterministic seeds);
  its JSON was lost with /tmp-era state and the
  post-replacement run is the record.

## Files

- mining/coordinator.py (new).
- research/sha256d/exp055/: PREDECLARATION.md,
  EXP055_REPORT.md, exp055_model.py,
  exp055_campaign.py, exp055_overhead.py,
  exp055_gate6.py, RAW_RESULTS/ (campaign, overhead
  and gate6 JSONs of record, gates.log, run logs
  including the discarded Gate 4 partials, gate5 and
  gate6 state directories excluded from the push set
  as runtime state).
- tests/test_exp055_coordinator.py (new); Makefile
  (test-exp055 target; test-all 46).
- The three registries (EXP-055 entry; next
  unreserved ID EXP-056). EXP-052 stays reserved for
  NOVA-ER-0012.

An independent audit is owed before any push; this
build was not pushed.

## UNVERIFIED register (stands in full)

- Multi-machine coordination: UNVERIFIED. No other
  machine was contacted, activated or measured.
- Real-network latency: UNVERIFIED. Loopback round
  trips are this-VM figures, not network figures.
- Cross-machine scaling: UNVERIFIED. The worker
  counts here are simulated workers on one contended
  VM; nothing shows how the coordinator behaves
  across machines, and the EXP-036 verifier budget
  concern (design matrix M27) remains a design rule,
  not a measurement.
- Real fleet behaviour, clock skew across machines
  (deadlines are coordinator-side by design, untested
  across real clocks), partial network failure, and
  production template rates and chunk sizes:
  UNVERIFIED.
- Live deployment of the coordinator alongside the
  production miner: UNVERIFIED and not attempted.
  Deployment and fleet activation are separate
  gated steps (roadmap F2 is the owner's decision).
- Other hosts: UNVERIFIED. All measurement is the
  AMD EPYC 9D25 host.
