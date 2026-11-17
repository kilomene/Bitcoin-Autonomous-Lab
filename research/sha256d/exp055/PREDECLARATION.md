# EXP-055 predeclaration (written before the build's campaign runs)

Written: 2026-11-17T09:16Z, before any EXP-055 campaign,
overhead or regtest measurement was taken. This file's
sha256 is pinned in the campaign, overhead and gate
drivers and in the test suite manifest at run time (the
EXP-049 audit note N-1 lesson: preserve the declaration
and record its hash in every run manifest). EXP-055 is
portfolio NOVA-ER-0015 (roadmap F1): the EXP-035 work
distribution design built as a production wire protocol
and persistent coordinator.

## Question and hypothesis

Can the EXP-035 design (research/sha256d/exp035/
WORK_DISTRIBUTION_DESIGN.md, proof obligations P1 to P6
in PROOFS/PROOF_OBLIGATIONS.md) be built as a running
system: a persistent coordinator process, a wire
protocol for worker registration, leases, progress,
completion and candidate hand-off, building on the
single-machine semantics of agent/intelligence/
resources.py, such that the proof obligations hold at
the protocol level, a randomised fault campaign at
least at the EXP-035 standard passes with exact
coverage, and the overhead is measured in per-position
cost form against the EXP-043 baselines before any
scaling claim?

Portfolio hypothesis: the protocol-level build
preserves the prototype's exactness properties; the
open risk is overhead and the two known EXP-043
prototype defects, not the design.

## The two EXP-043 fixes, carried in as fixes

EXP-043 named two prototype defects. This build must
carry both in as fixes, demonstrated by measurement,
not notes:

- F-A (prune the lease table): the prototype's
  starvation check scans every lease record ever
  issued, and completed lease records are never
  pruned, so lease cost grows with retained history.
  Fix shape: the coordinator's lease store holds only
  active leases, indexed per worker, so the
  starvation check is over the worker's own active
  set; completed and dead lease identities are
  retained only as compact tombstones (lease id and
  holder) sufficient to classify DUPLICATE and STALE
  reports; the event log is bounded and is not part
  of a snapshot.
- F-B (bound snapshot cost): the prototype's
  snapshot() deep-copies the entire retained state
  including the unbounded event log (420.3 ms at
  8,192 chunks in EXP-043). Fix shape: a snapshot
  serialises live state only (job, slices and chunks,
  active leases, worker registry, counters, compact
  tombstones), so its cost is proportional to live
  state, and Gate 4 measures it at the EXP-043 scale
  points (512, 2,048 and 8,192 chunks) against those
  baselines.

## Wire protocol shape (fixed here, from design section 9)

- Frames are length-prefixed: a 4-byte big-endian
  payload length, the UTF-8 JSON payload, and a
  4-byte big-endian CRC32 of the payload. A frame that
  fails its checksum or length bound is discarded and
  counted, never absorbed.
- Every mutating report carries (worker_id, lease_id,
  fencing_token) as applicable and is judged by the
  EXP-035 token rules (STALE, NOT_HOLDER, DUPLICATE,
  UNKNOWN_LEASE), unchanged.
- Coordinator persistence is an append-only operation
  journal plus periodic atomic snapshots (temp file,
  fsync, os.replace, the EXP-038 pattern). Recovery
  loads the snapshot, replays the journal after it,
  then applies the design's restart rule: epoch bumps,
  every outstanding lease is reclaimed, workers must
  re-register. Candidate records use the EXP-035
  candidate journal (persist before acknowledge) and
  its recovery rules.
- Deadlines are coordinator-side: every operation
  carries the caller's clock reading as an explicit
  field, and the coordinator's received value is the
  only one that decides expiry (the design's skew
  mitigation). Tests drive a simulated clock through
  the same field; production workers pass wall time.

## Layout judgment (recorded here, before the build)

The coordinator is a production component and lives in
mining/coordinator.py beside mining/solo_server.py (the
lab's other server component), runnable as a persistent
process (python3 -m mining.coordinator). It is a new
component beside the existing paths: the production
miner, autopilot, solo server, endpoint config and the
live stack are untouched, and not deploying the
coordinator is the rollback (portfolio). The EXP-055
harness (independent model, campaign, overhead and
Gate 6 drivers) lives in research/sha256d/exp055/, and
the regression suite is tests/test_exp055_coordinator.py
behind a new Makefile target test-exp055 (test-all
becomes 46).

## Gates, fixed in advance

- Gate 1 (proof obligations at the protocol level):
  the EXP-035 targeted test set, re-run with every
  operation carried over the wire protocol (frame
  encode, checksum, dispatch, frame decode), over an
  in-process transport and over TCP loopback: foreign
  fleet rejection, duplicate completion idempotence,
  restart replay never credited (with exact repeated
  accounting), lease expiry reclaim, coordinator
  restart killing all pre-restart tokens, steal with
  victim token rotation (old token STALE, wrong
  identity NOT_HOLDER), starved-worker re-registration,
  search-space declaration arithmetic, candidate queue
  semantics, candidate journal recovery, plus wire
  integrity (a corrupted frame is discarded and
  counted; a truncated frame never dispatches).
  P1 to P6 are asserted as in EXP-035: exact union,
  pairwise disjointness and the partition invariant,
  duplicates never credited, the accounting identity,
  restart honesty, candidate integrity (verifier
  invoked exactly once per unique candidate identity).
- Gate 2 (differential accounting): an independent
  model of the design (research/sha256d/exp055/
  exp055_model.py, written from the design document,
  interval-based, sharing no code with the
  coordinator) executes the same seeded operation
  scripts as the coordinator over the protocol: 40
  seeded scripts mixing register, declare, lease,
  progress, complete, steal, expire, worker death,
  worker restart, coordinator restart and duplicate
  and zombie injections. After every script, and at
  checkpoints inside long scripts, the coordinator's
  accounting (unique, pending, leased, declared,
  actual, repeated, duplicate, stale, not-holder,
  unknown, reclaims) must equal the model's exactly,
  and every completion and progress status returned
  over the wire must equal the model's classification.
  Any divergence is a Gate 2 failure.
- Gate 3 (randomised fault campaign, at least the
  EXP-035 standard): 60 trials over the in-process
  protocol transport (seed 20261117) plus 6 trials over
  TCP loopback with separate client connections (seed
  20261118), in the EXP-035 campaign shape (2 to 4
  workers, deaths, restarts, expiries, steals, zombie
  replays, duplicate deliveries, not-holder attempts,
  coordinator restarts, candidate submissions with
  duplicates). Every trial must close with exact
  coverage: union of completed intervals equals the
  declared space exactly, per slice and in total.
  FAILURE CRITERION, predeclared: any single trial
  with inexact coverage is a failure criterion event
  for the whole experiment (portfolio failure
  criterion); it is recorded honestly, the verdict
  mapping below applies, and no trial is rerun or
  edited to hide it (a trial interrupted by a VM
  replacement is rerun whole, as in EXP-054, and the
  interruption is recorded).
- Gate 4 (overhead, per-position cost form, against
  EXP-043 baselines): per-operation costs over the
  in-process protocol and over TCP loopback (medians
  of 3 sessions), the two fix demonstrations of F-A
  and F-B at the EXP-043 scale points, and campaign
  wall time per completed position at 2, 8 and 32
  simulated workers, no-fault and under the fault mix,
  against the EXP-043 campaign table. No scaling claim
  beyond what is measured on this VM is permitted by
  this declaration: loopback and in-process figures
  are this-VM figures, and multi-machine coordination,
  real-network latency and cross-machine scaling stay
  UNVERIFIED whatever Gate 4 measures.
- Gate 5 (coordinator restart with in-flight leases):
  over TCP, with the persistent coordinator backed by
  a real state directory: workers hold in-flight
  leases with recorded progress; the coordinator
  process object is stopped and a new one is started
  from the same state directory; pre-restart tokens
  must all return STALE, in-flight leases must be
  reclaimed with their progress moved to repeated
  accounting, completed coverage and the token counter
  must survive, candidate journal recovery must
  preserve P6, and the job must then complete exactly
  through fresh leases.
- Gate 6 (regtest block through coordinator-assigned
  work): a fresh regtest block whose winning nonce
  lies inside a nonce range leased to a worker through
  the wire protocol for a job declared from the node's
  own getblocktemplate; the worker searches only its
  leased range, hands the candidate to the coordinator
  through the candidate protocol, the coordinator
  verifies it with the EXP-036 verifier
  (mining/candidate_verify.py, regtest limit) and only
  the coordinator side submits; the block counts only
  when the node holds it on its active chain
  (verify_chain_acceptance) and the height advanced
  by exactly one.

## Verdict mapping, predeclared

- ALL GATES PASS: EXP-055 is COMPLETE, classification
  PROVEN for the protocol-level properties measured
  (P1 to P6 at the protocol level on this VM, exact
  coverage under the Gate 3 campaign, Gate 5 restart
  behaviour, one Gate 6 regtest block), with overhead
  figures recorded from Gate 4. This is not a fleet
  claim: F2 activation stays owner-gated, and the
  UNVERIFIED register below stands in full.
- ANY GATE FAILS, including any single inexact
  coverage trial at Gate 3: EXP-055 is recorded as
  FAILED with the failing gate and evidence, the
  design returns to EXP-035 status per the portfolio
  failure criterion, and the coordinator is not
  proposed for any integration. A defect found and
  fixed during the build, before the campaign runs,
  is ordinary build work and is recorded in the
  report's judgment calls; a defect found by a gate
  is a gate failure unless the gate's own text above
  says otherwise.

## Hard lines and scope

- Fleet activation is owner-gated (roadmap F2). This
  build contacts, activates or measures NO other
  machine. Loopback and in-process workers on this VM
  only. The portfolio's optional two-machine overhead
  measurement is out of scope.
- Exact SHA-256d only; no consensus property is
  touched; Gate 6 runs on regtest only.
- Production files are untouched whatever the verdict,
  except by addition: mining/coordinator.py is new,
  and the Makefile and the three registries gain the
  EXP-055 entries. The live miner, autopilot and node
  run throughout and are never restarted by this
  experiment; their contention is part of the measured
  environment and is recorded.
- Host: AMD EPYC 9D25 (confirmed from /proc/cpuinfo at
  build start). No GPU exists and none is claimed.
  Results on other hosts are UNVERIFIED.

## UNVERIFIED register (predeclared, stands regardless of outcome)

- Multi-machine coordination: UNVERIFIED. No other
  machine is contacted.
- Real-network latency: UNVERIFIED. Loopback is not a
  network measurement.
- Cross-machine scaling: UNVERIFIED. Worker counts
  here are simulated workers on one contended VM.
- Real fleet behaviour, clock skew across machines,
  partial network failure, and production template
  rates and chunk sizes: UNVERIFIED.
- Live deployment of the coordinator alongside the
  production miner: UNVERIFIED and not attempted;
  deployment is a separate gated step.
