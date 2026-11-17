# EXP-056: the H-033-02 residual cone closure attempt (portfolio NOVA-ER-0016)

Date: 2026-11-17. Host: AMD EPYC 9D25 (recorded from
/proc/cpuinfo; the live mainnet miner, node and
autopilot were never touched, restarted or interacted
with; all work was solver processes inside the lab
tree, one at a time, nice priority 19). Solver: z3
5.4.1 (Python package z3-solver 5.4.1, lab venv
.local/z3venv), the same solver as EXP-033 and
EXP-042. Predeclaration: PREDECLARATION.md, sha256
95b39893c5e13fa7559c33dc3696ce05b6e17baadbd5c603f22b4165259b50a6,
written and hashed before any solver run and pinned
in every driver. No production code was changed.
Nothing was pushed. No other machine was contacted.
No rate is claimed or implied.

## Solver budget, stated before the results

Time box: at most 6,600 s (110 minutes, 1.83
solver-hours) of solver wall in total across every
z3 query, and at most 12,600 s (3.5 hours) of
campaign wall clock. Actual solver wall consumed:
6,519.3 s of the 6,600 s box (98.8 percent), itemised
in section 5. Campaign wall clock: the checkpoint
opened 2026-11-17T11:06:50Z and the last query closed
at 13:16:52Z, about 7,800 s, inside the cap. One
interruption is disclosed in judgment call 3: a VM
replacement killed the first Stage A a-cone attempt
mid-query; its partial wall (about 380 s) produced
no verdict, is not in the accounted total (the
drivers account completed queries only), and the
checkpoint resumed the campaign with no query
repeated and none lost.

## 1. The question

EXP-042 closed H-033-05 and, with EXP-033, fixed the
round-cone minimum at exactly 6 instructions over
V = {ADD, LUT(any imm), ROTR(any k), SHR(any k)},
k in 1..31, under stated bounds: straight-line
programs of length 5, the sum s produced by a single
ADD of the two sum inputs, the Boolean output
produced by a single LUT. EXP-042 section 6 listed
what remains open in hypothesis H-033-02 (a
5-instruction program computes a full round cone,
a-cone (T1, T2, a, b) -> (s, Sigma0(s), Maj(s, a, b))
or e-cone (d, T1, e, f) -> (s, Sigma1(s),
Ch(s, e, f))): 5-instruction programs outside those
bounds, namely (i) s produced by two or more
instructions, (ii) the Boolean output produced by
two or more instructions with Sigma computed in the
remaining instructions over a pool including those
intermediates, and (iii) any mixture. The only
instrument covering that residual generality, the
full-cone CEGIS at L = 5 with no decomposition
assumptions, was inconclusive in EXP-033 (600 s,
82-example seed) and EXP-042 (1,500 s and 1,400 s,
22-example seed). EXP-056 attacks exactly that
residue, nothing broader: the full length-5 space
over V for both cones, with no decomposition
assumptions. Nothing EXP-033 or EXP-042 closed is
reopened as a separate question; the closed bounds
are a subset of this space and are covered only as
part of the whole.

## 2. Instrument and soundness discipline

The synthesiser (src/exp056_cone_synth.py) is the
EXP-033 full-cone CEGIS encoding (imported unchanged
for cone targets, incumbents, concrete evaluation
and exact verification) plus predeclared
canonicalisation constraints, each argued sound in
the predeclaration before any run:

- C1, unused-slot fixing (slots and fields an op
  does not read are fixed to canonical constants).
- C2, ADD operand ordering (commutativity).
- C3, output selector distinctness (sound on the
  seed: the driver asserts the three targets are
  pairwise distinguished by the seed examples, and
  the assertion held for both cones).
- C4, every instruction used (without loss of
  generality by the delete-dead-code and LUT-copy
  padding argument in the predeclaration; the
  encoded form counts reads through any selector
  slot, which only weakens the constraint).
- C5, the Stage B profile split: fixing the op-kind
  count multiset partitions the space into 56
  disjoint profiles whose union is the whole space.

Seed: 16 examples per cone (10 edge, 2
Boolean-stress, 4 random from random.Random
(20261119)), fixed in the predeclaration. A
synthesis UNSAT on the seed is a proof at the
stated scope, as in EXP-033. A SAT candidate would
have been believed only after exact z3 verification
over symbolic cone inputs plus a 1,000,000-sample
plain-Python differential through an independent
evaluator; no candidate was produced, so the
protocol was exercised only by the control.

Gates G0, run before any campaign result was read,
both cones: PASS. Incumbent differentials:
1,000,000 random inputs per cone, 0 mismatches.
Incumbent z3 exact verifications: negation UNSAT
for both cones (2.1 s and 2.5 s of solver wall).

Control C0, run next: PASS, against the planted
program as implemented; the plant deviates from
the predeclaration, corrected in section 11. The
canonicalised encoding, synthesising the planted
control program's behaviour over the 16-example
seed, returned SAT at 284.5 s; the found program
(a different decomposition from the plant) was
proven exactly equivalent to the plant as
implemented in z3 (negation UNSAT) and matched it
on 200,000 random inputs in plain Python, 0
mismatches. The predeclaration defines the plant
P5 with i4 = ADD(i3, i1), selectors (7, 5), all
instructions used and all four op kinds present;
the shipped P5_PROGRAM instead has i4 selectors
(6, 5), ADD(i2, i1), so the only SHR (i3) is
never read and the implemented plant's function
is computable by 4 instructions. The control
therefore demonstrated the encoding's
SAT-capability against the implemented (easier)
target, and its equivalence result is verified
for that target; a control re-run against the
corrected predeclared plant is owed if the
campaign ever resumes. The canonicalised
encoding is demonstrated SAT-capable at L = 5 on
this pool shape, and its UNSAT verdicts below
are believed. The predeclared plain-encoding
fallback was not needed.

## 3. Stage A: full-space queries

Canonicalised full-cone CEGIS, per-query timeout
1,500 s, seed 16, iteration 0 for both cones:

- a-cone: unknown at 1,502.7 s. INCONCLUSIVE.
- e-cone: unknown at 1,506.1 s. INCONCLUSIVE.

This is the same outcome shape as the EXP-033 and
EXP-042 full-cone runs, now under the canonicalised
encoding at the same per-query scale. No CEGIS
iteration beyond 0 was reached (iteration advances
only on a SAT candidate).

## 4. Stage B: op-kind profile split

One iteration-0 query per profile, per-query
timeout 240 s, seed 16, profiles in the predeclared
order (ADD count descending, then LUT, then ROTR,
then SHR). Profiles are written (ADD, LUT, ROTR,
SHR). Twelve profiles per cone were exhausted
before the solver box was spent; the verdicts were
identical for the two cones:

  idx  profile     a-cone            e-cone
  0    (5,0,0,0)   UNSAT 35.7 s      UNSAT 19.4 s
  1    (4,1,0,0)   UNSAT 209.9 s     UNSAT 134.8 s
  2    (4,0,1,0)   UNSAT 39.6 s      UNSAT 18.6 s
  3    (4,0,0,1)   UNSAT 35.6 s      UNSAT 13.1 s
  4    (3,2,0,0)   unknown 242.5 s   unknown 242.6 s
  5    (3,1,1,0)   unknown 243.6 s   unknown 243.6 s
  6    (3,1,0,1)   unknown 241.7 s   unknown 241.8 s
  7    (3,0,2,0)   UNSAT 78.2 s      UNSAT 51.1 s
  8    (3,0,1,1)   UNSAT 54.2 s      UNSAT 85.4 s
  9    (3,0,0,2)   UNSAT 5.7 s       UNSAT 15.6 s
  10   (2,3,0,0)   unknown 241.2 s   unknown 241.7 s
  11   (2,2,1,0)   unknown 242.0 s   unknown 243.8 s

Closed (UNSAT, a proof for that profile at this
scope) for BOTH cones: (5,0,0,0), (4,1,0,0),
(4,0,1,0), (4,0,0,1), (3,0,2,0), (3,0,1,1),
(3,0,0,2). The pattern in the queried set is exact:
every queried profile with no LUT closed, and the
single one-LUT profile with 4 ADDs closed; every
other queried profile (a LUT present with at most
3 ADDs, or 2 or more LUTs) timed out. That pattern
is an observation about solver behaviour on this
instrument, not a theorem, and no claim is made
from it beyond the 7 closed profiles themselves.
All six 3-ADD profiles (indices 4 to 9) were
queried: the three with no LUT closed, the three
with a LUT timed out.

Open after Stage B, per cone: the 5 queried profiles
above that returned unknown, and profiles 12 to 55
(44 profiles) that were never queried: exactly
every profile with at most 2 ADDs except (2,3,0,0)
and (2,2,1,0) (indices 10 and 11, queried,
unknown). The unqueried set is reproducible from
src/exp056_cone_synth.py all_profiles(), indices
12..55, and is recorded in the checkpoint.

Stage C (encoding B, rotation by selection) was
NOT RUN: when Stage B ended, 80.7 s of the solver
box strictly remained (6,600 - 6,519.3). The
campaign driver's Stage C launcher computes its
cap from the box plus its 60 s slack (6,600 + 60
- 6,519.3 = 140.7 s), which is not below the
driver's 120 s launch minimum (and is far below
the predeclared 1,200 s cap), so invoking stageC
would have launched an encoding-B query at a
140.7 s cap. Stage C was not invoked and remains
never run, as carried in section 6. The box, not
a verdict, ended the campaign. (This paragraph
corrects the rationale as first written; see
section 11.)

## 5. Solver budget accounting

  Gates (both cones, z3 exact verifies; the stage
  also ran 2,000,000 plain-Python differentials):
  4.6 s.
  Control (synthesis 284.5 s; exact verify under
  0.1 s; plus a 200,000-sample differential):
  284.5 s.
  Stage A: a-cone 1,502.7 s; e-cone 1,506.1 s.
  Stage B: a-cone 1,669.9 s over 12 profiles;
  e-cone 1,551.5 s over 12 profiles.
  Total: 6,519.3 s of the 6,600 s box.

All solver processes ran one at a time on the
shared VM, alongside the live mainnet miner and the
syncing node; contention is part of the recorded
conditions and affects only how long queries took,
never what UNSAT means.

## 6. Verdict and what remains open

Verdict: INCONCLUSIVE at the predeclared budget,
the portfolio failure criterion for NOVA-ER-0016,
applied exactly as predeclared. No SAT construction
was found, and the residual space was not exhausted,
so neither closing branch applies.

Classification: H-033-02 stays open with status
UNPROVEN BREAKTHROUGH, narrowed by exactly the 7
closed op-kind profiles per cone recorded in
section 4 (of the 56 profiles that partition the
space). EXP-056 registry status: UNDER_INVESTIGATION.
A dated exp056 update note has been appended to the
H-033-02 entry in the EXP-033 hypothesis registry,
as EXP-042 did for H-033-05; the hypothesis
statement and status are unchanged.

What remains open, stated exactly, per cone:
(a) the full-space question itself (Stage A
unknown at 1,500 s per query under both the plain
and the canonicalised encodings, here and in
EXP-033 and EXP-042);
(b) Stage B profiles 4, 5, 6, 10, 11 ((3,2,0,0),
(3,1,1,0), (3,1,0,1), (2,3,0,0), (2,2,1,0)),
queried at 240 s and unknown;
(c) Stage B profiles 12 to 55, never queried;
(d) Stage C's encoding B, never run.
Any future attempt starts from the checkpoint:
the drivers resume and never repeat a completed
query, and the 7 closed profiles per cone do not
need to be run again.

## 7. Judgment calls

1. Inter-cone split of the Stage B box. The
   predeclaration fixed the stage order and the
   per-query caps but did not fix how the Stage B
   remainder divides between the cones. The a-cone
   Stage B run was stopped by the operator between
   queries after 12 profiles (solver total
   4,967.8 s) so the e-cone received the same depth
   (12 profiles) from the remaining box, instead of
   the a-cone consuming the whole remainder. The
   checkpoint makes the stop lossless: the a-cone
   end-of-stage summary file was materialised from
   the checkpoint afterwards and is flagged as such
   in RAW_RESULTS. This allocation is an operator
   decision recorded here, not a predeclared rule.
2. Build-time smoke test. Before the campaign of
   record, a single 6-example synthesis query
   against the planted target only (30.7 s, SAT,
   extraction verified against its seed by hand)
   validated the new driver code. It touched no
   cone target, is not a campaign query, and is not
   in the accounted total; the campaign's own gates
   and control were still run in full, in order,
   before any cone result was read.
3. VM replacement interruption. The first Stage A
   a-cone attempt was killed by a VM replacement
   about 380 s into its first query (host before
   and after: AMD EPYC 9D25). The checkpoint design
   absorbed it: no verdict was recorded for the
   partial query, the campaign resumed from the
   checkpoint, and the partial wall is disclosed in
   the budget section rather than accounted.
4. The Makefile test-exp056 target invokes the lab
   venv python (.local/z3venv/bin/python), not
   python3, because z3 exists only in that venv;
   every other test target uses python3. The suite
   header records this.
5. Stage B queries are iteration-0 only, as
   predeclared: a profile UNSAT at iteration 0 is a
   proof for that profile, and no profile produced
   a SAT candidate that would have started a CEGIS
   iteration.

## 8. Suites

Run one at a time, after the campaign:

- make test-exp056: 16 checks, ALL PASSED
  (predeclaration pin, profile order, canonicalisation
  value preservation on 200 random programs, 100k
  incumbent differentials per cone, campaign record
  consistency including the closed profile sets, the
  H-033-02 registry note).
- make test-exp055 (neighbour): 23 checks, ALL
  PASSED (its Gate 6 produced regtest block 2387).

Makefile test-all count: 48 to 49 (test-exp056
added). Registries: JSON registry 108 entries,
EXP-056 UNDER_INVESTIGATION; both markdown
registries carry the byte-identical EXP-056 append,
closing with next unreserved ID EXP-059 and EXP-052
noted as the standing reservation for NOVA-ER-0012.

## 9. UNVERIFIED register

- The 5 unknown profiles per cone ((3,2,0,0),
  (3,1,1,0), (3,1,0,1), (2,3,0,0), (2,2,1,0)) at
  budgets above 240 s per query: UNVERIFIED, open.
- Profiles 12 to 55 per cone (44 profiles, every
  profile with at most 2 ADDs beyond the two
  queried at indices 10 and 11): UNVERIFIED, never
  queried, open.
- The full-space question at per-query budgets
  above 1,500 s, and under encoding B (Stage C,
  never run): UNVERIFIED, open.
- Length-5 programs over any vocabulary larger
  than V (for example including SHL or multi-operand
  add): out of scope by definition, UNVERIFIED.
- Length below 5 in the residual generality:
  covered only through the C4 padding argument if
  the length-5 space closes; since it did not
  close, lengths below 5 in the residual generality
  are exactly as open as the length-5 space.
- Behaviour on other hosts, including Intel:
  UNVERIFIED. Solver verdicts are host-independent
  as mathematics, but every run here is the AMD
  EPYC 9D25 host under live-stack contention.
- Any production consequence of a construction:
  none was found; had one been found, integration
  would have remained a separate owner-gated step
  and is UNVERIFIED and not attempted.

## 10. Files and reproducibility

  PREDECLARATION.md: the predeclared space, stages,
  box, stopping rules and classification branches.
  src/exp056_cone_synth.py: the canonicalised
  synthesiser, the planted control program, the
  profile enumeration.
  src/exp056_campaign.py: the staged campaign
  driver (gates, control, stageA, stageB, stageC,
  status), checkpointing after every query.
  RAW_RESULTS/: one JSON per completed stage, the
  console logs, and exp056_checkpoint.json (the
  complete per-query record and resume state).
  PROOFS/exp056_proofs_summary.json: the gates,
  control and per-profile UNSAT record, materialised
  from the checkpoint.
  EXP056_REPORT.md: this report.

Rerun or resume, from research/sha256d/exp056, with
the lab venv python (~/workspace/bitcoin-autonomous-lab/
.local/z3venv/bin/python), one invocation at a time:

  src/exp056_campaign.py gates
  src/exp056_campaign.py control
  src/exp056_campaign.py stageA a_cone
  src/exp056_campaign.py stageA e_cone
  src/exp056_campaign.py stageB a_cone
  src/exp056_campaign.py stageB e_cone
  src/exp056_campaign.py stageC
  src/exp056_campaign.py status

Completed queries are skipped from the checkpoint;
the solver box accounting is cumulative, so a
resumed campaign still stops at the predeclared
box unless a future predeclaration raises it.

## 11. Corrections (2026-11-17)

Added after the independent audit
(EXP056_AUDIT.md, verdict PASS WITH NOTES, 2
defects), before push. No number, verdict, tally
or classification in this report changes; the two
corrections are to descriptions of what was run.

D-1, the control plant. Section 2 as first
written described the control target as "the
predeclared planted 5-instruction program P5".
That is inaccurate. The predeclaration defines
P5 with i4 = ADD(i3, i1), selectors (7, 5), all
instructions used and all four op kinds present.
The shipped P5_PROGRAM in src/exp056_cone_synth.py
has i4 selectors (6, 5), ADD(i2, i1): the only
SHR (i3) is never read and is not an output, so
the implemented plant's function is computable
by 4 instructions (ROTR, ADD, LUT, ADD). The
control therefore demonstrated the encoding's
SAT-capability against the implemented (easier)
target, not against a target that genuinely
requires 5 instructions as predeclared, and its
equivalence result (z3 negation UNSAT; 200,000
differentials, 0 bad) is verified for that
implemented target. No UNSAT verdict and not the
INCONCLUSIVE classification depends on the
control; UNSAT soundness rests on the
canonicalisation argument of section 2. A
control re-run against the corrected predeclared
plant is owed if the campaign ever resumes under
a future predeclaration. Section 2 now states
this inline, and the same correction has been
applied to the EXP-056 entries in the JSON
registry and both markdown registries, and to
the exp056 note on H-033-02 in the EXP-033
hypothesis registry.

D-2, the Stage C rationale. Section 4 as first
written said Stage C was not run because the
80.7 s remaining was "below the 120 s minimum
the campaign driver requires to launch a Stage C
query". That misstates the shipped driver:
do_stageC computes its cap from the box plus the
60 s slack (6,600 + 60 - 6,519.3 = 140.7 s), and
140.7 is not below 120, so invoking stageC would
have launched an encoding-B query at a 140.7 s
cap rather than refusing. Stage C remains never
run, exactly as the open register in section 6
already carried it; only the rationale sentence
was wrong, and section 4 now states the true
arithmetic.
