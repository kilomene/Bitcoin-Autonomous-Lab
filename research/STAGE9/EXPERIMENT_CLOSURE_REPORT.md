# Stage 9 Experiment Closure Report

Stage: 9.1. Date: 2026-11-18. Repository:
kilomene/Bitcoin-Autonomous-Lab, remote HEAD
883cf281be6c41617f27b8b44d1aa27e3c94df29 (see
REPOSITORY_BASELINE.md for the HEAD derivation, including the
18 churn commits after the last deliberate push at 11277e6f).
Machine-readable companion: EXPERIMENT_CLOSURE_LEDGER.json,
validated against EXPERIMENT_CLOSURE_LEDGER.schema.json by
validate_ledger.py. Validation result, run at build time:
VALID (jsonschema, draft 2020-12): 109 entries.

## 1. Method and mapping rules

- One ledger record per entry in the authoritative registry
  research/EXTREME_RESEARCH/EXPERIMENT_REGISTRY.json (109
  entries), id unchanged, each exactly once. The id families
  are: EXP-NNN experiments (including EXP-024b), EXP-030 phase
  records (PHASE-A to PHASE-H), PHASE001-H-N hypotheses, and
  R-NN portfolio register rows.
- The authoritative registry carries 7 statuses: PROVEN 41,
  INTEGRATED 30, REJECTED 15, NEW 10, EXPERIMENTAL 7,
  UNDER_INVESTIGATION 4, DEFERRED 2.
- Disposition mapping (exactly one principal disposition per
  record, from the Stage 9 set): INTEGRATED stays INTEGRATED;
  REJECTED stays REJECTED; DEFERRED stays DEFERRED;
  EXPERIMENTAL stays EXPERIMENTAL; UNDER_INVESTIGATION stays
  UNDER_INVESTIGATION; PROVEN becomes PROVEN_NOT_INTEGRATED
  (the result stands, but the production call path does not
  invoke it); NEW becomes DEFERRED (registered proposal, no
  execution recorded under that id), with five documented
  exceptions where the row was in fact executed under a later
  EXP id (section 3, discrepancy D-01). EXP-056 is assigned
  INCONCLUSIVE (section 2.5).
- Affects-production was decided from current source, not from
  the registry text: an entry counts as affecting production
  only if its module is reachable from mining/autopilot.py,
  mining/mainnet_live.py, mining/engine.py, mining/solo_server.py
  or gpu/engine.py as they stand at this HEAD, allowing for
  default-off switches to be recorded as integrated code with
  unchanged live behaviour (the nuance is written into the
  record, not hidden).
- Correctness was never read as performance: kernel-correctness
  entries with no production search-path measurement are
  PROVEN_NOT_INTEGRATED, and candidate-construction results are
  classed separately from hash throughput in every record
  (metric_class field).

## 2. Disposition counts

| Disposition | Count |
| --- | --- |
| INTEGRATED | 30 |
| PROVEN_NOT_INTEGRATED | 44 |
| REJECTED | 15 |
| EXPERIMENTAL | 8 |
| UNDER_INVESTIGATION | 4 |
| DEFERRED | 7 |
| INCONCLUSIVE | 1 |
| Total | 109 |

The 30 INTEGRATED records are exactly the authoritative
registry's INTEGRATED set, and that set was verified identical
to the derived registry agent/intelligence/
integration_registry.json (30 ids, set equality checked at
build time). The 44 PROVEN_NOT_INTEGRATED are the 41 registry
PROVEN entries plus R-27, R-33 and R-35, which were executed
under EXP-057, EXP-051 and EXP-049 (see D-01). The 8
EXPERIMENTAL are the 7 registry EXPERIMENTAL entries plus R-32
(executed as EXP-058). The 4 UNDER_INVESTIGATION are EXP-013,
PHASE001-H-6, EXP-052 and R-23 (executed as EXP-052). The 7
DEFERRED are R-21, R-28 and the five never-executed NEW rows
R-24, R-25, R-29, R-31, R-34. The single INCONCLUSIVE is
EXP-056.

## 3. A4 reconciliation against current source

### 3.1 EXP-052 adaptive backend dispatch (register R-23)

Current source: mining/bakeoff_dispatch.py (580 lines),
sha256 fc211512d3097781413e2bfb7b11210664eb347335573c1c6f59ba7656993c10.

- Resolver robustness: resolve_requested never measures and
  returns "auto" (the static dispatch order) on every doubt
  path inspected: switch disabled, cache missing, unreadable,
  schema or protocol mismatch, fingerprint mismatch, stale
  cache (max age 604,800 s), non-finite fields, margin below
  the predeclared 0.05, unknown winner, and a winner
  contradicted by the cache's own tier rows (the audit D-2 fix
  is present in validate_cache). The audit D-1 fix is also
  present: wrong-typed arguments fall back instead of raising
  (the margin coercion is guarded and returns the doubt
  verdict). The module docstring contract ("the resolver never
  raises and never measures") matches the code as read.
- Static fallback: the static pick is the gpu/engine.py tier
  order itself; "auto" is exactly today's behaviour, and with
  the switch off the cache is never even read.
- Host fingerprinting: host_fingerprint() keys the verdict
  cache to CPU identity data from /proc/cpuinfo plus thread
  count; any mismatch voids the cache by design. The one
  completed campaign ran on AMD EPYC 9D25 (flags hash
  51d3e983ddf6ac93) and resolved STATIC by dominance (pooled
  adjusted log ratios vs v512dual from -0.6264 for v512 down to
  -3.9732 for hashlib).
- Cross-host evidence: none. The Intel Xeon Platinum 8321HC
  rotation and a second AMD rotation are still outstanding;
  the ledger records them UNVERIFIED, and the campaign's own
  disclosed qualification stands: the control pooled CI
  [-0.1101, +0.1452] is wider than plus or minus log(1.05), so
  no challenger could have been certified at the 5 percent
  margin in that campaign (pooled resolution about 13 percent).
- Live enablement status: NOT enabled. BAKEOFF_DEFAULTS in
  mining/endpoint_config.py ship enabled=false;
  mining/mainnet_live.py consults the resolver only under that
  flag; .local/mining-endpoint.json carries no bakeoff section;
  no cache file exists at .local/bakeoff-dispatch.json.
  Enablement remains an owner decision.
- Disposition: UNDER_INVESTIGATION (partial completion on one
  host), for both EXP-052 and R-23.

### 3.2 EXP-053 and EXP-054 negative findings

Preserved without change. EXP-053 (prefix sharing inside the
dual-batch walker): ESTABLISHED NEGATIVE at its predeclared
resolution, pooled log ratio -0.0017; disposition REJECTED.
EXP-054 (interleave granularity): the flat curve is confirmed,
production G=1 stands, the displacement hypothesis is
ESTABLISHED NEGATIVE (G=2 +0.0016, G=4 -0.0521, G=8 -0.1505);
disposition REJECTED. Neither result was re-derived in this
stage (no benchmarks were run); both records keep their
recorded limitations, including the known EXP-053 bench-driver
defect D-1, which must be fixed before that driver is reused,
and the unmeasured Intel host. No new mathematical hypothesis
was presented in this stage, so neither is reopened.

### 3.3 EXP-055 coordinator (mining/coordinator.py, 1,224 lines)

Verified in current source:

- Lease ownership: CoordinatorCore issues leases with unique
  sequential ids (L<n>), a per-lease fencing token and an epoch;
  _check_report rejects reports with a wrong token or a stale
  epoch as STALE, and a report from a non-holder as NOT_HOLDER.
- Fencing: completed lease ids are kept as tombstones
  (_completed_ids) and reclaimed or superseded ids as dead ids
  (_dead_ids); a duplicate delivery against a completed id is
  counted (duplicate_deliveries), a report against a dead id is
  counted separately (unknown_lease_reports). The F-A fix is in
  the source: only ACTIVE leases live in the lease table,
  indexed per worker.
- Recovery: CoordinatorServer persists an operation journal
  (fsync per entry) plus atomic snapshots; on restart it loads
  the snapshot, replays the journal tail deterministically,
  recovers candidate state from the separate candidate journal,
  then applies the restart rule: every outstanding lease is
  reclaimed and the epoch bumps, so no lease survives a
  coordinator restart and workers must re-register.
- Duplicate work prevention: jobs are partitioned into slices
  and chunks with the invariant unique + pending + leased ==
  declared, asserted by assert_partition_invariant;
  CandidateQueue deduplicates by full candidate identity,
  journals before acknowledging (persist before acknowledge),
  and counts duplicates and candidates arriving from reclaimed
  leases instead of silently accepting them.
- Real multi-machine limitations (unchanged, recorded as
  UNVERIFIED in the ledger): all measurement is one VM,
  in-process or loopback. Multi-machine coordination, real
  network latency, cross-machine scaling, clock skew across
  machines, partial network failure and live deployment beside
  the production miner are all unproven. The coordinator is
  not imported by the live path. Fleet activation remains
  owner-gated.
- Disposition: PROVEN_NOT_INTEGRATED.

### 3.4 EXP-056 symbolic synthesis (H-033-02)

INCONCLUSIVE classification retained, exactly as the Stage 9
brief requires. The campaign exhausted its predeclared budget
(6,519.3 s of the 6,600 s box): Stage A full-space queries were
unknown at 1,500 s for both cones; Stage B closed 7 of 56
op-kind profiles per cone as UNSAT and exhausted 12 profiles
per cone in total; no SAT construction was found. That is a
solver budget result, not a proof of impossibility, and the
ledger says so. Still open per cone: 5 profiles unknown at
240 s, 44 profiles never queried, the full-space question
above 1,500 s per query, and Stage C (encoding B), never run.
The audit's two documentation defects (D-1, the shipped
control plant's selectors differing from the predeclared
plant; D-2, the Stage C cap arithmetic) were corrected in the
record as dated corrections with no verdict or number changed;
a control re-run against the corrected plant is owed if the
campaign resumes, and the drivers resume from checkpoint at
profile 12. H-033-02 stays UNPROVEN BREAKTHROUGH, narrowed.
Disposition: INCONCLUSIVE (registry status remains
UNDER_INVESTIGATION).

### 3.5 EXP-057 stratum aggregation (mining/aggregation.py, 718 lines)

Re-audited against current source, line by line against the
two defects its independent audit found and fixed before push:

- Authentication and session lifecycle: a worker exists only
  if the operator enrolled it (enroll_worker stores a token
  hash, never the token). open_session requires the fleet id
  to match, the worker to be enrolled, and the token hash to
  match; a token belonging to another worker simply does not
  match. Each session binds exactly one worker to exactly one
  tier-assigned extranonce1; the worker never chooses it, so a
  share cannot be credited to another worker's slot.
  submit_share raises IdentityError on an unknown or dead
  session and on a claimed_worker that differs from the
  session's bound worker, before any counting happens.
- D-1 (session orphaning) reconciled: in _AggHandler, a
  re-authorize on one connection captures the previous session
  id, binds the new session, then closes the previous one, and
  connection teardown closes the connection's final session.
  No session is left bound to a dead connection. The fix is
  present in the current source at the handler (lines around
  655 to 664) with its regression rationale in comments.
- Candidate persistence: snapshot() and restore() persist
  workers, counters, the duplicate seen-set, pending
  candidates and upstream submission count; on restore the
  session table is deliberately emptied and the epoch rule
  applies (sessions never survive a tier restart; workers
  re-authenticate). Verified candidates are queued in
  pending_candidates with their full verification record.
- Retry safety and D-2 (lossy candidate pop) reconciled:
  operator_submit_pending is the only submission path in the
  module. It requires the operator token, refuses when no
  submitter is configured, re-verifies the stored header
  through mining.candidate_verify.verify_candidate before
  submitting, and removes the candidate from the queue only
  after the submitter has returned, deleting by identity.
  On any failure (job gone, re-verification failure,
  submitter exception) the candidate stays queued. The fix
  is present in the current source (lines around 421 to 487)
  and matches the audit description.
- Submission authority: the tier never submits on its own
  authority. Workers cannot submit upstream at all; the sole
  path is the explicit operator call through the configured
  submitter callable.
- Accounting: per-worker and global counters reconcile through
  assert_accounting_identity against the EXP-037 statistics;
  duplicates are keyed on (worker, job, extranonce2, ntime,
  nonce) and counted, not silently dropped.
- Limitations (UNVERIFIED, in the ledger): loopback only; no
  real upstream pool, no multi-machine operation, no live
  deployment. Not imported by the live path.
- Disposition: PROVEN_NOT_INTEGRATED.

### 3.6 EXP-058 PID controller (mining/pid_control.py, 529 lines)

The missed scale-up requirement is preserved, not argued away.
The controller's only signal is the span completion interval.
The inner span loop (velocity form) drives log2(span); the
outer worker loop (absolute form) reads span saturation. The
structural finding stands in the source and the record: an
interval-only cascade cannot see spare capacity, because when
intervals are already at target there is no error signal that
distinguishes "correctly loaded" from "capacity to spare", so
the step_up scale-up leg is ESTABLISHED NEGATIVE for this
signal (register R-32). What promotion would need, stated as
the observability requirement: a signal that measures spare
capacity directly, for example a periodic bounded probe (a
short trial span at a higher worker count whose completion
interval is compared against the running interval), or a
measured hash-rate-per-worker signal with its own EXP-017
experiment, or host capacity telemetry (effective CPU from the
EXP-031 characterisation) fed in as a feedforward term. None
of these exists in the current source; make_work_controller
builds the interval-only cascade and nothing else. The module
ships disabled by default, is not imported by the live path,
and Gate 5 actuated a side workload only. Any hash-rate
effect is UNVERIFIED by design. Disposition: EXPERIMENTAL
(registry EXPERIMENTAL), and R-32 aligned to EXPERIMENTAL.

### 3.7 NOVA-ER-0006 incident registry (register R-30)

Verified against the current HEAD:

- mining/incident_registry.json holds exactly 20 append-only
  codes in 5 classes: 1001 to 1003 (miner lifecycle), 2001 to
  2005 (supervisor lifecycle), 3001 to 3004 (self-update),
  4001 to 4003 (work and report integrity), 5001 to 5005
  (upstream and verification). mining/incident_codes.py
  validates entries, enforces the append-only rule
  (check_append_only) and resolves codes defensively.
- Emission sites verified in current source: mining/autopilot.py
  emits 1001, 1002, 1003, 2001, 2002, 2003, 2004 and 3001 to
  3004 through log_incident with the heartbeat publishing
  incident_counts; mining/mining_statistics.py keys 4001 to
  4003 in record() and exposes record_incident and
  incident_snapshot, with snapshot() deliberately unchanged.
- Live proof at this HEAD: the running autopilot's heartbeat
  (.local/heartbeat.json, 2026-11-18T02:40:02Z) carries
  incident_counts {1003: 1, 2001: 1}. The registry item that
  was UNVERIFIED at build time (live emission) is therefore
  verified now.
- Audit scope reconciled: the independent audit
  (research/EXTREME_RESEARCH/NOVA_ER_0006_AUDIT.md, PASS WITH
  NOTES, 0 defects) was scoped to the change set against
  remote HEAD 6528aae0, before the push at 11277e6f. The code
  it audited is byte-identical at the current HEAD (sha256 of
  mining/incident_codes.py, mining/autopilot.py and
  mining/mining_statistics.py as tabled in the baseline), so
  its verdict carries to this HEAD for those files.
- Still UNVERIFIED, kept in the ledger: keeper-side mapping
  for 2005 (the keeper is not repo code); the 3001 to 3004
  update path end to end (never fired on this VM; the checkout
  has no .git, so the path is inert here); emission wiring at
  the 5xxx producers (codes assigned and replay-mapped over
  165 real log lines with zero unmapped, producers not wired
  by this change); 5003 has no instance in the operational
  evidence corpus.
- Disposition: INTEGRATED.

### 3.8 Stage 8 historical result vs current source state

The Stage 8 audit (research/EXTREME_RESEARCH/STAGE8_AUDIT.md,
PASS WITH NOTES, 0 defects) verified, against the regtest node
itself, four blocks at heights 1787 to 1790 on the best chain
and an isolated agent instance's own evidence log, at remote
HEAD 78a061e5385e86b953801af51b49bf5d57d72243, with Stage 8
itself local and unpushed at audit time. That is a historical,
independently audited result about that commit and that
isolated instance. It is not a claim about the current source:
the current HEAD is 883cf281, the Stage 8 code has since been
pushed and the suite (test-stage8) is one of the 51 test-all
prerequisites, but no Stage 8 demonstration was re-run in
Stage 9.1, and the known Stage 8 run-1 finding (the production
GBT path lacks the 10 s status publisher the demo miner
needed) remains open. Stage 9.5 owns any fresh autonomous
regtest demonstration; nothing in this closure upgrades the
Stage 8 verdict into a current-HEAD claim.

## 4. Discrepancies between registry claims and current source

Every discrepancy found, listed explicitly. None is a
production code defect; all are record-keeping gaps that this
closure corrects in the ledger without rewriting the
authoritative registry (registry edits are a separate,
audited step if the owner wants them).

- D-01 (five stale NEW rows): R-23, R-27, R-32, R-33 and R-35
  still carry registry status NEW although each was executed:
  R-23 as EXP-052, R-27 as EXP-057, R-32 as EXP-058, R-33 as
  EXP-051, R-35 as EXP-049. The ledger assigns each the
  disposition its execution earned and names the covering
  experiment in the record basis.
- D-02 (registry basis is old): the authoritative registry was
  generated 2026-11-15 against HEAD 18ff4eb0 plus a local
  delta. Its statuses predate EXP-047 to EXP-058 and the
  Stage 9 pushes. Entries added later (EXP-047 onward) carry
  their own reports, but the registry's framing text and
  several register rows (notably R-23's open question, written
  before EXP-052 ran) describe a pre-campaign world.
- D-03 (EXP-030 self-note): the EXP-030 entry itself records
  that the registry reservation block for EXP-030 to EXP-038
  was never updated from its RESERVED wording. Carried into
  the ledger as a known limitation; the phase records
  (EXP-030-PHASE-A to H) carry the real statuses.
- D-04 (Phase 001 table vs registry): PHASE001-H-8's entry
  records that the Phase 001 status table still lists H-8 as
  open while the registry marks it REJECTED (the EXP-041
  result). The registry and this ledger follow REJECTED.
  PHASE001-H-9's table wording likewise predates EXP-024b;
  the ledger follows the EXP-024b record.
- D-05 (AVX2 batch conflict, unresolved): EXP-032 and EXP-039
  measured the byte-identical AVX2 kernel at 1.409x and 1.252x
  with non-overlapping confidence intervals. Both entries
  record the conflict; neither was re-measured in this stage.
  It does not affect the live pick (v512dual dominates on this
  host class) but it is an open measurement-integrity item for
  Stage 9.7.
- D-06 (R-30 live-emission note is stale): the R-30 registry
  entry says live records carry codes only after the next
  natural autopilot restart. That restart has happened: the
  heartbeat at audit time already carries incident_counts.
  The ledger records live emission as verified.
- D-07 (INTEGRATED with default-off behaviour): R-26 and
  EXP-050's policy, and the EXP-025-adjacent prefetch hook
  (EXP-051, registry PROVEN), are integrated as code but
  disabled or opt-in by default, so live behaviour is
  unchanged. The registry's INTEGRATED for R-26 is accurate
  about code presence; the ledger adds the enablement state
  explicitly so no reader mistakes code presence for live
  effect. EXP-052's resolver is the same shape one step
  further out (code present, switch off, no cache planted).
- D-08 (HEAD movement without development): the remote HEAD
  advanced 18 commits past the last deliberate push, all
  runtime churn from one accidental unscoped helper run
  (detailed in the baseline). Anyone diffing 11277e6f against
  883cf281 sees only RAW_RESULTS and evidence churn; there is
  no hidden code change, and equally, no Stage 9 work is on
  the remote yet.
- D-09 (EXP-024 family double record): EXP-024 (EXPERIMENTAL,
  mask early-exit family) and EXP-024b (PROVEN, design C) are
  two records over one design family; design C was then
  superseded as the integration candidate by EXP-026 DualMask
  (INTEGRATED). Both records are kept; the ledger marks
  EXP-024 EXPERIMENTAL and EXP-024b PROVEN_NOT_INTEGRATED
  with the supersession in its measured result.
- D-10 (no CI record in the repository): there is no CI
  configuration in the tree, so "CI status" for the current
  HEAD is: none exists. Test evidence is the local Makefile
  suite only. Stage 9.2 or 9.3 should decide whether to add a
  repeatable record; this stage only reports the gap.

## 5. What this closure does not claim

- No test suite was re-run in Stage 9.1; current-HEAD test
  status is Stage 9.3's deliverable.
- No benchmark was re-run; every performance figure in the
  ledger is the registry's recorded figure, attributed as
  such, with its CI where the record states one.
- No mainnet block has been found; the success criterion
  (a real, independently verified, submitted, accepted
  mainnet block) remains unmet, and nothing in this closure
  changes that. Pool shares (1,040 accepted at audit start)
  are not blocks and are never presented as such.
- The 500 GH/s minimum objective and the 140 TH/s larger
  objective stand unchanged and unmet; the measured live rate
  on this host class remains in the tens of MH/s.

## 6. Corrections (2026-11-18, per STAGE9_1_AUDIT.md)

Correction note added after the independent audit in
research/STAGE9/STAGE9_1_AUDIT.md (verdict PASS WITH NOTES,
defects 1 and 2). The ledger records for EXP-050 and EXP-051
originally stated that the result "is not invoked by the
production call path" with affects_production_path false.
That wording was false and has been corrected in
EXPERIMENT_CLOSURE_LEDGER.json only; no disposition, count
or id changed.

- EXP-050: the EndpointHealthPolicy code is wired into
  mining/mainnet_live.py behind a default-off flag, is inert
  on the live stack, and has never run live. It is the same
  implementation recorded under R-26 as INTEGRATED.
- EXP-051: mining/prefetch.py is imported unconditionally
  by mining/engine.py and MiningEngine wires the queue
  behind use_prefetch=False (opt-in, off), so it has never
  been enabled live.

In both records the disposition PROVEN_NOT_INTEGRATED
stands under the ledger declared mapping rule (disposition
follows registry status), now stated explicitly in the
record basis so code presence is not confused with live
effect, in either direction. Discrepancy D-07 above already
described both hooks correctly as integrated code, disabled
or opt-in by default; D-07 is the correct reading, and the
generic mapping parenthetical in section 1 must be read
subject to this correction for these two records.
