# Phase 002 Closing Audit: independent audit of all Phase 002 work

Auditor: independent agent (authored none of the audited
work). Date: 2026-11-15. Host: AMD EPYC 9D25, 4 vCPUs.
Scope: the eight items of the Phase 002 closing brief:
the EXP-039 integration's post-audit stability, the
step 4 probability and statistics wiring, the corrections
wave, EXP-040, EXP-041, EXP-042, EXP-043, and the global
checks. Every decisive claim below was re-derived by the
auditor from the code, the raw result files, or fresh
suite runs; nothing rests on the phase's own reports
alone. No production code and no audited document was
modified by this audit. The remote head is still
737e41c8: nothing in Phase 002 has been pushed, and this
audit pushed nothing.

## Verdict: PASS WITH NOTES

Defects: 0. Notes: 5 (N-1 to N-5).

## Item 1: EXP-039 audit still stands. CONFIRMED

The EXP-039 audit (research/sha256d/exp039/
EXP039_AUDIT.md, PASS WITH NOTES, zero defects) completed
at 20:16 UTC. A full mtime scan of gpu/ and mining/ shows
no source file modified after 20:16 UTC: gpu/engine.py
last changed 19:47 UTC, the newest mining/cpu/ file
(build.py) 19:38 UTC, both before the audit ran. Every
later Phase 002 front (EXP-040 through EXP-043) worked
only inside its own research directory, so nothing they
did can invalidate the audit. The current gpu/engine.py
still carries the audited dispatch (the shani and avx2
tiers documented at lines 42 to 78, selection as audited:
CUDA, v512dual, v512, shani, avx2, C, hashlib).

## Item 2: step 4, probability percentiles and statistics wiring. CONFIRMED

Anchors recomputed by the auditor at 50-digit precision
(mpmath), independently of the module and its tests:
the exact-target anchor 1 - (1 - p(T1))^(2^32) with
p(T1) = (0xffff x 2^208 + 1) / 2^256 is 0.632114945434,
and the difficulty-form anchor 1 - (1 - 2^-32)^(2^32) is
0.632120558871. They are different numbers, differing at
the sixth decimal, as the model states. Against them:
prob_at_least_one_exact(T1, 2^32) returns 0.632114945434
(error 2.3e-17 against my anchor) and fails the
difficulty anchor by more than 1e-6;
prob_at_least_one_hashes(1, 2^32) returns 0.632120558871
(error 3.7e-17) and fails the exact anchor likewise.
expected_hashes_exact(T1) is the exact Fraction
2^256 / (T1 + 1) = 4295032833.000015..., no float
involved. Quantiles are exact ln multiples of the mean
(median ln 2, p90 ln 10, p95 ln 20, p99 ln 100; relative
error at most 4e-16) and round-trip through
prob_at_least_one back to q. PERIOD_SECONDS matches the
model (day 86400, week 604800, month 2629800, year
31557600, ten_years 315576000); q outside (0, 1) and
unknown period names raise ValueError. The suites pin
the two anchors separately, including an explicit check
that the difficulty form fails the exact anchor's
tolerance (tests/test_exp037_statistics.py line 346).
Both suites run by the auditor: test_probability_
percentiles.py, ALL PASSED (73 checks, matching the
claim); test_exp037_statistics.py, ALL PASSED, including
the whole-log census and the wiring tests.

Wiring, by inspection plus the auditor's own behavioural
probes: MiningStatistics.snapshot() returns exactly
{categories, totals, per_worker, per_backend}; there is
deliberately no combined total (the docstring states the
categories overlap and summing would double-count).
SafeRecorder swallows wrapped record() exceptions and
counts them in .errors (auditor probe: 2 forced failures,
errors = 2, no raise). FrontierAccountant: a chunk
recorded with completed=False (a hit) credits
unique_nonces but zero unique_coverage; only a completed
chunk credits coverage; re-examined positions land in
repeated_work (auditor probe reproduced all three).
StratumClient.on_share_result defaults to None (line
203) and is invoked only when set, inside try/except, so
default consumers see zero behaviour change.
MiningEngine's statistics parameter defaults to None
(mining/engine.py line 467) and constructs a
FrontierAccountant only when reached through the wired
path (lines 527 to 529).

## Item 3: corrections wave. CONFIRMED (with N-1 and N-2)

Seven of the eleven fixes spot-checked against primary
sources:

- Test count: at correction time the Makefile held 30
  named test suites besides the base test target, so the
  corrected figure was right when written; see N-1 for
  the closing-state drift.
- README rate relabel: the 6,617,558 H/s figure now reads
  as a category D batch measurement from the C-backend
  era, "not an end to end rate" (README lines 78, 113).
- Worker identity: README line 73 gives the worker as the
  lab address with the htch-runtime hostname suffix via
  default_worker(), with the session 1 bal1 form noted.
- ARCHITECTURE decision 2 now reads "mainnet live since
  2026-11-13" with the paused text marked as the ended
  phase, and the visibility section records the
  repository as public per the owner's 2026-11-13
  resolution.
- evidence/SUMMARY.md now states E3 with the correction
  census (347 events, 339 accepted, 8 rejected). The
  auditor's own full-log census at audit time: 391
  events, 383 accepted, 8 rejected. The delta since the
  correction is exactly +44 events, all accepted, which
  is precisely what a live log does between two counts;
  the rejected count is unchanged at 8.
- PRODUCTION_INTEGRATION_LOG.md (research/sha256d/
  phase6b/) Entry 3 carries the dated 2026-11-15
  correction: batch_search's direct callers are
  gpu/benchmark.py and the test suites; dashboard and
  agent reach it only through ComputeEngine.benchmark();
  production mining reaches the kernels through
  search_first_counted.

Cold test runs by the auditor, sequentially, each with
no regtest node running beforehand (so the bal-regtest
wallet started unloaded and the fixed loadwallet-first
helper path was the one exercised): make test-regtest,
ALL REGTEST TESTS PASSED; make test-engine, ALL
INTELLIGENCE ENGINE TESTS PASSED.

## Item 4: EXP-040 category F. CONFIRMED

The auditor recomputed every headline figure from the
nine campaign session JSONs in RAW_RESULTS (the three
shakedown files excluded, as the report does), using the
report's own definition (per run, cycle wall minus the
search stage):

- Scenario A (empty): 24 runs, pooled median 0.065 s per
  block, per-session medians 0.043 / 0.156 / 0.040,
  median non-search overhead 43.5 ms, median fraction
  0.930, blocks per hour 55,338 by median and 6,586
  aggregate. All match the report.
- Scenario B (501 transactions): 24 runs, pooled median
  0.215 s, overhead 206.3 ms, fraction 0.992, 16,769 by
  median and 16,152 aggregate. Match.
- Scenario C (amplified): 15 runs, pooled median
  3.299 s, overhead 49.5 ms, fraction 0.015, median
  counted hashes 16,841,664 (report: about 16.8M). Match.

All 63 timed runs have accepted = true, failed = 0, and
a passing EXP-036 verification record; heights span
1345 to 1417 as claimed. Zero production changes: the
harness (category_f.py) imports MiningEngine and wraps
its own instance's seams, and the Item 1 mtime scan
covers the EXP-040 window (20:21 to 20:44 UTC) with no
gpu/ or mining/ file touched. The hashrate
specification's category F entries (section 2 row and
the section 9 results block) carry the same figures:
0.065 s and 43.5 ms empty, 0.215 s and 206.3 ms loaded,
49.5 ms amplified.

## Item 5: EXP-041, the 29 vs 28 operation gap. CONFIRMED

From the saved census (RAW_RESULTS/census.json, objdump
of the v_compress16 loop body): production v512 totals
29 vector ALU ops per round (12 offsets, 7 ternlog, 10
adds), with Maj as the 0x60 + 0x78 ternlog pair and Ch
already a single 0xe4. The tmaj variant totals 28 with
Maj as a single 0xe8; tfull totals 28 (0xca Ch, 0xe8
Maj); base, alta, altb, altc and both flag builds all
stay at 29. The production DualMask search body
(v_compress16x2_reg) totals 448 ops over its unrolled
body, 28 per batch-round, with 0xe8 present: the report's
new fact checks out in the saved data. Verdicts from the
final analysis JSON (21 session files): tmaj batch
pooled log-ratio -0.0006, CI [-0.106, +0.106]; tfull
batch +0.0301, CI [-0.079, +0.140]; tmaj search vs v512
-0.0213, CI [-0.123, +0.080]; no session and no pooled
comparison meets the EXP-017 significance rule, so both
28-op variants are ESTABLISHED NULL, exactly as
reported; tmaj search vs v512dual is -0.5900 (the dual
about 1.80x faster). The controls behave as the report
discloses (same-library self control a clean null at
-0.0018; the cross-library rebuild control noisy).
Production sources untouched: the build manifest records
production_source_sha256 ff28ce496a043c3ad... for
mining/cpu/bal_avx512_mb.c, and the auditor's sha256sum
of the current file is identical, byte for byte.

## Item 6: EXP-042, the E2 attack. CONFIRMED

Soundness discipline verified from the run JSONs and
logs, not just the report:

- Control (cone a, L = 3): verdict
  candidate_passed_differential, a real program found
  and independently verified, so the encoder is proven
  capable of finding programs when they exist. A control
  that cannot succeed would make every later UNSAT
  meaningless; this one can and did.
- Gates: for both cones the incumbent 4-instruction form
  is exact (200,000 Python differentials, 0 bad) and its
  negation is z3 UNSAT.
- E2 cone queries: synthesis UNSAT at L = 3 over the
  declared pool (s, p, q, x, y, m), iteration 0, 16
  cone-realizable examples per cone, a-cone 540.3 s,
  e-cone 214.0 s, z3 5.4.1. The bounds are stated
  exactly (vocabulary V, cone length 5, sum produced by
  a single ADD, Boolean output by a single LUT), and the
  refutation is claimed only inside them.
- Full-cone catch-all at L = 5: both runs end
  synth_unknown (1,504.2 s and 1,402.2 s, 22 examples)
  and are reported INCONCLUSIVE in the report's own
  words, never as negatives.
- The EXP-033 hypothesis registry note is append-only in
  structure: H-033-05 gained a new field
  (exp042_update_2026_11_15) and its original statement
  and evidence text are intact, including the original
  sentence that E2 remained open at EXP-033's close.
- Reproducibility: the solver scripts
  (src/exp042_e2_synth.py, src/exp042_fullcone.py), the
  per-stage run JSONs, the PROOFS copies and the solver
  logs all exist and are internally consistent. The
  long solver executions were not repeated by this
  audit, so reproducibility is script-verified,
  execution-not-repeated (see N-3).

## Item 7: EXP-043, coordination overhead study. CONFIRMED

Headline per-operation medians recomputed by the auditor
from the three micro session JSONs (median across the 3
sessions of each session median): heartbeat 220 ns at 1
worker and 370 ns at 128 workers, exact; declare_job
22.5 / 203.6 / 767.6 / 2970.4 us at 64 / 512 / 2,048 /
8,192 chunks (report rounds to 23 / 204 / 768 / 2,970);
snapshot 1.68 / 13.28 / 126.81 / 420.35 ms at the same
sizes (report 1.7 / 13.3 / 126.8 / 420.3); candidate
submit new 771 ns, duplicate 802 ns, journalled
18,438 ns with p95 223,486 ns (report 0.77 / 0.80 /
18.4 us, p95 223 us). Campaign figures from the
campaign JSON: fault-trial wall medians 0.159 s (2
workers), 1.804 s (8), 199.99 s (32), all reproduced;
no-fault walls 0.001 / 0.017 / 1.116 / 76.6 s likewise.
The 128-worker fault trial is a single trial with
status CAPPED, wall 600.8027 s, unique_coverage 14,280
of 131,072 declared positions (10.89 percent), 210,944
loop iterations, 15,553 reclaims, 13,571 stale reports,
16,065 lease records retained, accounting_closed false.
It appears in no median and no average: it is recorded
as a failed run in the report, in the campaign table
(with n/a cells), and in the EXP-035 addendum. The
addendum to research/sha256d/exp035/FINAL_REPORT.md is
a new final section (line 68 of 102) appended after the
original closing section; the original sections are
intact and the addendum's "still open, unchanged"
paragraph preserves the register. The updated UNVERIFIED
register in EXP043_REPORT.md still lists, precisely:
multi-machine coordination overhead, propagation latency
over any real network, and linear scaling across
machines, plus the unbuilt production wire protocol and
the unactivated fleet.

## Item 8: global checks. CONFIRMED

- Long dash scan: the auditor scanned 279 text files
  covering everything Phase 002 created or modified
  (mining/, gpu/, tests/, docs/, evidence/, README.md,
  the Makefile, both registries, research/hashrate/,
  research/probability/, and the exp033, exp035, exp039,
  exp040, exp041, exp042 and exp043 trees), excluding
  binaries and __pycache__. U+2014 occurrences: zero.
  This report also contains none.
- Registries: both research/sha256d/
  experiment_registry.md and research/sha256d/
  extreme_optimization/EXPERIMENT_REGISTRY.md carry a
  dated record section for each of EXP-039, EXP-040,
  EXP-041, EXP-042 and EXP-043, and both end at "Next
  unreserved ID: EXP-044".
- Live mining undisturbed: read-only status at audit
  close shows autopilot pid 3702, miner pid 3705,
  miner_state running, restarts 0, heartbeat current.
  These are the keeper-restarted processes from 13:20
  PST, expected and not a finding. This audit restarted
  nothing; its test runs used the separate regtest node
  only.

## Notes

- N-1: the README and docs/EVIDENCE.md test counts (30
  targets) are stale in the closing tree. EXP-039 and
  EXP-040 each added a suite to test-all after the
  corrections wave fixed the count, so test-all now has
  33 prerequisites (32 named suites besides the base
  test target). The correction was accurate when made;
  the two counts should be updated when Phase 002 is
  pushed.
- N-2: the README's dated 2026-11-15 update paragraph
  states the dispatch order as CUDA, v512dual, v512, C,
  hashlib, omitting the shani and avx2 tiers EXP-039
  integrated later the same day. Accurate when written
  (the corrections ran before the integration finished);
  the sentence should gain the two tiers at push time.
- N-3: EXP-042's long solver runs (540 s cone query,
  1,400 to 1,500 s full-cone runs) were not re-executed
  by this audit. Their JSONs, logs and scripts are
  present and consistent, and the verdicts' logic does
  not depend on trusting them beyond that, but the
  record should read: reproducibility script-verified,
  execution-not-repeated.
- N-4: EXP-039's own audit notes carry over unchanged
  and are not re-opened here: Intel-host and AVX2-only
  refusal unexecuted, the AVX2 batch conditions
  discrepancy vs EXP-032 unresolved, bootstrap interval
  deltas from the RNG stream. Later Phase 002 work did
  not touch the code they describe (Item 1).
- N-5: EXP-043's register_worker headline (0.73 us)
  recomputes to 761 ns under the auditor's
  median-of-medians aggregation, a 4 percent difference
  attributable to aggregation choice on a
  contention-dominated cell; every other headline median
  reproduced to rounding. No conclusion in the report
  turns on this cell.

## What this audit did not do

It did not re-run the EXP-039 audit (Item 1 covers only
its continued validity), did not re-execute the EXP-042
solver queries, did not run the full 33-target suite,
and did not push anything. The push of the Phase 002
tree, with the N-1 and N-2 one-line documentation
updates, is the separate step that follows this verdict.
