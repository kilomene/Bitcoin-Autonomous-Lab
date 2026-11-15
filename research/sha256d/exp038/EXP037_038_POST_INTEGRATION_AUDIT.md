# EXP-037 / EXP-038: Independent Post-Integration Audit

Date: 2026-11-15. Auditor: an independent agent, not the
author of the EXP-037 / EXP-038 integration. Scope: the
production changes of both phases (mining/autopilot.py
EvidenceCounter, mining/mining_statistics.py,
mining/probability.py, mining/work_checkpoint.py, the
MiningEngine checkpoint integration in mining/engine.py, and
the enablement in agent/autonomous.py), audited against
research/sha256d/exp037/STATISTICAL_MODEL.md,
research/sha256d/exp037/FINAL_REPORT.md,
research/sha256d/exp038/AUTONOMOUS_OPERATIONS.md and
research/sha256d/exp038/FINAL_REPORT.md.

One audit file covers both phases (the parent brief allowed
one or two; the two phases share the engine and the suite,
so one file keeps the cross-references in one place).

## Verdict: PASS WITH NOTES, zero defects

No defect was found in any production code under audit.
Every load-bearing claim of both phases was re-derived from
the auditor's own tests, not the author's: an independent
brute-force census of the real production log, an
adversarial EvidenceCounter suite, a 4,000-record statistics
reconciliation campaign, probability checks against exact
rational arithmetic and an expm1 reference, and a
24-configuration engine-level checkpoint restart campaign
including hit paths and a crash simulation that the author's
tests do not cover. Seven notes follow the evidence; none
blocks the work. One corrects a number in the phase
reporting (the Makefile test-all count, note N-1).

## 1. EvidenceCounter (EXP-037)

Auditor's brute force over the real production log
(evidence/mainnet-live.jsonl, parsed line by line with an
independent implementation) at audit time: 248 accepted,
8 rejected, 256 share_result events, last event epoch
1794742896.0. A fresh EvidenceCounter with a temporary state
file matched all four numbers exactly, and a second poll
after further live appends matched the brute force over
exactly the prefix the counter had consumed. (The counts
grow while the miner runs; 247 accepted in the phase report
was the same census earlier in the day.)

The persisted production state (.local/evidence-count.json:
accepted 247, rejected 8, share_results 255, offset
2,300,771) was verified prefix-consistent: brute force over
the first 2,300,771 bytes of the log reproduces those exact
counts and last epoch, and its recorded head fingerprint
matches the log's first 8,192 bytes. When the autopilot
next restarts, the new code resumes from that state and
advances incrementally to the true total.

Auditor's adversarial cases, all behaving correctly:

- State file with a valid offset but a wrong head
  fingerprint: full recount, exact counts.
- State offset beyond end of file: full recount, exact.
- Same-size log replacement with a different head: detected
  via the fingerprint, recounted to the new truth (30/0/30
  against brute force).
- Share line split across two appends, the second append
  completing it and adding a second full line in the same
  write: nothing counted early, both lines counted exactly
  once on completion.
- Append-during-count: a writer thread appending share
  lines while update() polled 30 times over a 3,000-line
  log; the final poll equalled brute force exactly
  (48 accepted, 25 rejected, 73 total).
- Empty log and partial-line-only log: zero census, no
  exception.
- Missing log, corrupt (unparseable) state: zero census and
  full-recount fallback respectively (also covered by the
  author's tests; re-verified in the rotation cases of the
  auditor's suite).

Two probes are recorded as notes N-2 and N-3: the disclosed
undetectable replacement shape is stale by exactly the
changed amount and nothing more, and a parseable state file
with tampered counts is trusted.

## 2. MiningStatistics (EXP-037)

Category separation is real. The auditor's campaign recorded
4,000 randomised records (all 20 categories, random counts
including zeros, random worker and backend tags) and kept an
independent ledger: snapshot totals, per-worker and
per-backend breakdowns all reconciled exactly. A recursive
walk of the snapshot found every numeric leaf keyed by a
category name: there is no combined-total field anywhere in
the structure, and no production code consumes the snapshot
at all yet (grep-verified; the follow-on wiring is disclosed
as not done in STATISTICAL_MODEL.md section 7). Unknown
categories (including near-misses like "Backend_hashes" and
"total"), negative counts, non-integer counts (1.5, 2.0,
"3", None) and total() of an unknown category are all
refused with ValueError. A zero record is a no-op and
creates no breakdown slot. WindowedRate spot checks beyond
the author's (exact rates over bracketing samples, backwards
cumulative refused) pass.

## 3. Probability (EXP-037)

All three formulas verified against independent computation:

- expected_hashes: exact rational equality (Fraction) for
  integer difficulties 1, 2, 7, 1000, 123456789, and within
  float precision for 0.5, 2.5, 8.5e13, 1e14, 1e23.
- expected_seconds: relative error below 1e-12 against
  rational arithmetic across seven (rate, difficulty)
  pairs including D = 1, D = 1e23 and D = 1e-6; zero and
  negative rates return math.inf, as documented.
- prob_at_least_one: matches an expm1-based reference
  across eight (rate, difficulty, time) triples spanning
  lambda from 2.3e-10 to 2; the pinned anchor at one
  expected time reproduces 0.6321205588285577 exactly.
- Extremes raise nothing and stay sane: expected_hashes
  (1e308) is inf, expected_seconds(1e6, 1e308) is inf,
  prob(1e6, 1e308, 1e6) is 0.0, prob(1e308, 1, 1e308) is
  1.0 (lambda overflows to inf, exp(-inf) is 0).
- Non-positive difficulty is refused by all three entry
  points.

One numerical note (N-4): for lambda below about 1e-16 the
1 - exp(-lambda) form returns exactly 0.0 where the true
probability is about lambda (probe: module 0.0, expm1
reference 2.33e-22). The error understates the probability,
never overstates it, and the form is inherited verbatim
from research/probability.py, so adoption fidelity is
exact; it is simply not documented in the module.

## 4. Work checkpoint (EXP-038): the honesty property

The author's tests cover budget interruption, restart
resume, completion, mismatch and corruption at a small
scale. The auditor's campaign is independent and wider:

- Randomised restart campaign, 24 configurations (spaces
  (0,1), (0,2), (0,3), (3,2), (0,4); batch sizes 2^32,
  2^31, 2^32/3, 2^30; random first-process budgets from 0
  to the full batch count): in every configuration the two
  processes' searched ranges were pairwise disjoint and
  their union was exactly the declared space, and a third
  process on the completed space searched nothing and
  reported zero hashes.
- Hit honesty, the case the author's engine tests do not
  exercise: a hit in the very first batch leaves NO
  checkpoint file at all; a hit in round 1 leaves the
  frontier at (1, 0, complete=False), covering only the
  completed round 0, and a restarted engine rescans exactly
  the hit round; a mid-round hit (batch 2 of round 0)
  leaves the frontier at the end of batch 1,
  (0, 2^31). A hit batch's space is never checkpointed as
  completed. Hits were submitted through a fake RPC that
  confirms the block like a real node, and accepted=True
  was observed in the result.
- Crash simulation: a compute backend raising mid-cycle
  (round 1's batch) propagates the exception out of
  mine_cycle (no silent swallow), the checkpoint on disk
  covers only completed round 0, and a restarted engine
  completes the space disjointly.
- Isolation: a checkpoint written for template A is not
  honoured for template B (different identity), not
  honoured under a different extranonce space, and not
  honoured for a template differing ONLY in curtime: the
  auditor first proved that such a template has the same
  EXP-025 layered identity (so the refusal is the
  curtime-basis rule itself, not the identity check), and
  the engine started fresh with the time-basis reason in
  the result.
- Corruption: eight malformed checkpoint variants
  (truncated JSON, wrong schema version, frontier nonce
  equal to 2^32, negative frontier extranonce, missing
  frontier fields, non-hex identity, empty file, JSON
  array instead of object) each started fresh with a
  reason, never crashed, never falsely resumed.
- checkpoint_path=None: across all three result shapes
  (exhausted, budget, hit), the no-checkpoint result keys
  contain no "checkpoint" key, and enabling the checkpoint
  adds exactly that one key; hit results agree on nonce,
  hashes, batches, accepted and block hash between the two
  modes.
- Enablement census: agent/autonomous.py is the only
  production caller passing checkpoint_path (to
  .local/work-checkpoint.json); the pool path does not use
  MiningEngine and is untouched, as documented.

Two mechanism observations are recorded as notes N-5 and
N-6 (the curtime basis versus the effective header time,
and the end-of-space frontier classification). Neither
produces a false completion claim for any position.

## 5. Makefile truth

Counted from the Makefile itself: test-all lists 30
prerequisites: test, test-regtest, test-engine, test-pow,
test-gpu, test-gpu-correction, test-mining, test-adversarial,
test-deepening, test-cpu, test-cpu-correction, test-rtl,
test-solo, test-solo-cutover, test-research, test-autopilot,
test-judgement, test-installer, test-task003, test-task0038,
test-task0039, test-avx512, test-avx512dual,
test-mainnet-live, test-template-cache, test-avx512flags,
test-exp036, test-exp034, test-exp037, test-exp038.

Reconciliation of the numbers in circulation: 27 was
correct in the EXP-036 era (30 minus test-exp034,
test-exp037, test-exp038); 28 was correct in the EXP-034
era (30 minus test-exp037, test-exp038); the current tree
has 30. The EXP-037/038 reporting of "28 targets" and
"25 of 28" is therefore understated by two: with the three
environment failures below, the suite state consistent
with the evidence is 27 of 30. See note N-1.

## 6. Suite state, first-hand

Run by the auditor on this host: test-exp037 PASS,
test-exp038 PASS, test-autopilot PASS (its live-instance
case skips because a live autopilot owns this checkout),
test-mining PASS, test-exp034 PASS, test-exp036 PASS.

Environment failures, confirmed first-hand and unrelated
to these phases (both phases' changes are pure Python and
cannot raise them):

- test-rtl: fails with "iverilog: not found"; the
  simulator is not installed on this host.
- test-cpu-correction: killed by SIGILL (Illegal
  instruction).
- test-task003: killed by SIGILL (Illegal instruction).

Host: Intel(R) Xeon(R) Platinum 8321HC; /proc/cpuinfo
flags include avx2 and avx512f and carry NO sha_ni flag,
so the -msha intrinsics binaries those two targets build
cannot execute here. The auditor did not re-run the
remaining 21 test-all targets; their state is as the
phase reports left them, and nothing in these phases
touches them.

## Notes

- N-1 (reporting accuracy): the phase reporting's suite
  denominator is wrong for the current tree. test-all has
  30 targets, not 28 (section 5). The code, the Makefile
  and both new targets are correct; only the count quoted
  in the phase summary is stale, apparently carried from
  the EXP-034 era. Any future "x of y" suite claim should
  be counted from the Makefile at the time of the run.
- N-2 (state integrity): EvidenceCounter authenticates
  the log (head fingerprint plus offset) but trusts the
  counts stored in a parseable state file. Auditor probe:
  a state file with the correct offset and fingerprint
  but accepted inflated by 1,000 was believed verbatim
  (returned 1030 against a true 30). Syntactic corruption
  falls back to a recount exactly as documented; semantic
  corruption of the counts is undetectable by the design.
  The state file is written only by the autopilot itself
  via atomic replace and sits in the same trust domain as
  the log, so no accidental in-system path produces it;
  if that ever changes, a checksum over the state payload
  or a periodic full recount closes it.
- N-3 (disclosed limitation behaves as disclosed): the
  one replacement shape the EvidenceCounter docstring and
  STATISTICAL_MODEL.md section 2 declare undetectable
  (same size, first 8,192 bytes identical, tail changed)
  was probed: the counter stayed stale by exactly the one
  changed share (30 reported against a true 29), with no
  wild divergence, and re-synced as soon as the head
  changed. The disclosure is accurate.
- N-4 (probability underflow): prob_at_least_one returns
  exactly 0.0 for lambda below about 1e-16 (the
  1 - exp(-lambda) cancellation), where the true value is
  about lambda. Conservative in direction, inherited
  verbatim from the research original, and immaterial to
  any decision the lab makes at those magnitudes, but the
  module does not document it. A one-line docstring note,
  or computing -math.expm1(-lambda), closes it.
- N-5 (time basis precision): the checkpoint's curtime
  basis is the template's curtime field, while the header
  time actually built is max(mintime + 1, min(now,
  curtime)) (EXP-025's per-build rule, unchanged by this
  phase). When wall-clock now is below the template
  curtime, builds under one recorded basis tick with the
  wall clock: demonstrated with one prepared template
  producing header times 1800000000 and 1800000100 at two
  build times under a recorded basis of 1900000000, and
  pinning to 1900000000 once now passes it. The frontier's
  claim is over (extranonce, nonce) positions, every one
  of which was genuinely searched, and an uninterrupted
  cycle ticks the same way, so no completion is falsely
  claimed; but the operations document's sentence that a
  resumed scan "never claims coverage recorded under a
  different time basis" is stronger than the mechanism in
  that regime. Worth one clarifying sentence in
  AUTONOMOUS_OPERATIONS.md.
- N-6 (end-of-space frontier): WorkCheckpoint.resume
  accepts a frontier exactly at the end of the space
  without the complete flag and returns "resume" at that
  point; the engine's loop over the resulting empty range
  then records complete=True. Verified behaviour in the
  campaign: no rescan, no crash, correct final state.
  Cosmetic classification only.
- N-7 (live effect timing, as disclosed): the running
  autopilot (pid 2895) still executes the pre-fix code in
  memory and its heartbeat showed the tail-window figure
  (221 accepted) during the audit, against a true census
  of 248. The fix, and the verified persisted count state
  it will resume from, take effect at the autopilot's next
  natural restart, exactly as both phase reports state.
  Nothing was restarted for this audit.

## What was not done

No production code was modified by this audit, nothing was
restarted, no benchmarks were run, and nothing was pushed.
The auditor's scripts were run from /tmp and are not part
of the repository; their assertions and outputs are
summarised above with the numbers observed.
