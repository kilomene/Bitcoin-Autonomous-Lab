# EXP-033: Bitcoin Header and SHA-256d Mathematical Investigation

Experiment: EXP-033, EXP-030 programme Phase H (directive
section 6). Date: 2026-11-15. Host: Intel Xeon Platinum
8321HC (AVX-512F/BW/VL/VNNI, no SHA extensions, no VBMI),
recorded in every session manifest. Solver: z3 5.4.1 via
the lab venv. Research only: no production code changed,
no kernel built, no benchmark run, the live miner,
autopilot and node untouched.

Three-tier discipline, applied throughout: a result is a
VERIFIED IMPROVEMENT only with an EXP-017 protocol
benchmark of a working kernel; this phase built no kernel
and measured no rate, so it claims no improvement of any
kind. A proven identity or a proven minimum is a
mathematical result, not a speedup. Labels used:
VERIFIED (proven or exactly re-derived), ESTABLISHED
NEGATIVE (refuted or closed at a stated bound), UNPROVEN
BREAKTHROUGH (plausible or merely unrefuted, no evidence
of a rate), INCONCLUSIVE (attack attempted, solver bound
reached, no verdict either way).

## 1. Scope and method

EXP-027 (Phase 6B Track B) closed the named outside
vocabulary spaces with proofs: GFNI affine forms, VPSHUFB
rotations, rotated and byte-swapped state, carry-save
beyond the schedule, addition networks, IFMA. Its census
found 0 nontrivial subterms shared across the round
boundary and 0 digest-independent outer rounds. Exactly
one sub-space was left explicitly OPEN: non-sharing
cross-round graph restructuring, blocked by search-space
size. Scope 1 of this phase attacks that sub-space with
three bounded instruments:

(a) Word-level e-graph equality saturation over the
two-round round function (the object EXP-027's census
operated on), with an inductive soundness check of the
saturated graph.

(b) CEGIS bounded program synthesis at instruction
granularity over the vocabulary V = {ADD, LUT(any 8-bit
immediate), ROTR(any k in 1..31), SHR(any k in 1..31)},
first at the full round-cone level, then at the Sigma
sub-DAG level where the search is small enough to be
decisive.

(c) A structural consumption census: where each produced
state word is consumed, bitwise and arithmetically, in
the following rounds.

Scope 2 re-derives the header mathematics from scratch
(symbolic taint over the message schedule and both
compressions, z3 proofs and refutations of the delta
identities, exact accounting), and examines whether any
exact representation change reduces total work for the
double hash as a whole, including the outer hash.

All foundations are pinned by TESTS/test_exp033_
foundations.py (reference compression equals hashlib
including SHA-256d on headers; the two-round DAG
evaluates exactly at cost 56; the W18 and W19 identities
hold on 20,000 samples; both incumbent cone programs are
exact on 20,000 samples each). All tests pass.

## 2. Scope 1: cross-round graph restructuring

### 2.1 E-graph equality saturation: no cheaper graph

Method (src/exp033_egraph.py): the exact two-round DAG
of exp033_common (baseline cost 56 under the EXP-020
census model: 34 for two rounds plus 22 for the two
schedule words they consume; single round 17, schedule
word 11) is saturated in a word-level e-graph under
rules R1 to R6: rotation composition and distribution
over LUTs and its inverse, constant folding, LUT
flattening over at most 3 distinct atom classes by exact
truth-table recomposition, add associativity in both
directions, add(x, 0), add(x, x) = shl, and LUT
degeneracies. Deliberately NO rule pushes bitwise
operations through ADD, because none is sound. Extraction
is by per-root dynamic programming over tree costs, with
hill-climbing from the incumbent; the incumbent itself
stays in the space, so extraction can never report worse
than baseline as a finding.

Soundness (src/exp033_egraph_verify.py): a fixed
representative per class was chosen and every enode in
every root-reachable class was evaluated against its
class representative on random inputs, with root
representatives anchored against the reference two-round
map. Joint case: 309,120 enode evaluations over 120
trials, 0 mismatches; anchors 200 trials, 0 mismatches.
Rounds-only case: 71,400 evaluations over 300 trials,
0 mismatches; anchors 200 trials, 0 mismatches. The
saturated graphs are sound: everything they identify is
a true equality.

Results (RAW_RESULTS/exp033_egraph_20261115T110602Z.json):

- Rounds-only case (baseline 34): saturation CONVERGED
  at round 8 (2,388 enodes, 336 classes, zero unions in
  the final round). Per-root DP tree costs identical
  before and after: [120, 16, 0, 0, 50, 10, 0, 0].
  Hill-climb extraction stayed at 34. Within this
  rewrite system, the two-round round function admits
  no cheaper graph. This is a closure, at the stated
  system, not a heuristic miss: the space was saturated
  to a fixed point.
- Joint case (two rounds plus the schedule pair,
  baseline 56): saturation hit the class cap at round 5
  (35,615 enodes, 7,658 classes) without converging.
  Per-root DP tree costs identical before and after:
  [219, 27, 0, 0, 105, 21, 0, 0]. Hill-climb extraction
  stayed at 56. (Greedy extraction reported 66 and 36
  in the two cases; those are known greedy artifacts,
  worse than the incumbents that remain in the space,
  and are not findings.) The joint statement is
  therefore bounded: no improvement exists in the part
  of the space explored up to the cap.

Verdict: ESTABLISHED NEGATIVE for non-sharing cross-round
restructuring expressible in the R1 to R6 word-level
rewrite system, complete for the rounds-only fixed point
and bounded by the class cap for the joint case.

### 2.2 Full-cone synthesis: incumbents proven, L = 5 attack inconclusive

The round decomposes into two cones. The a-cone maps
(T1, T2, a, b) to (a' = T1 + T2, Sigma0(a'), Maj(a', a,
b)); the e-cone maps (d, T1, e, f) to (e' = d + T1,
Sigma1(e'), Ch(e', e, f)). Each has a 6-instruction
incumbent over V (one ADD, three rotations, two LUTs).

Gates (RAW_RESULTS and PROOFS exp033_cone_synth_gates_
20261115T114122Z.json): each incumbent program matches
its cone target on 1,000,000 random differentials with
0 mismatches, and z3 proves each incumbent exact (UNSAT
on the inequality) for both cones. The targets and the
encoding are therefore validated, and cost 6 per cone is
proven achievable.

The decisive query, CEGIS at L = 5 for the a-cone with
an 82-example seed, returned synth UNKNOWN at the 600 s
solver timeout under this host's contention (RAW_RESULTS/
exp033_cone_synth_a_cone_20261115T114616Z.json). A
smaller-seed retry was also starved. Full-cone synthesis
at L = 5 is reported INCONCLUSIVE at the stated bound:
it is not evidence for a 5-instruction cone and not a
proof against one. The sharper instrument of section 2.3
is what settles most of the question.

### 2.3 Sigma sub-DAG synthesis: the Sigma minimum is exactly 4

Question: given the produced word x (a' or e') plus up
to four arbitrary side values (fillers f1 to f4,
universally quantified and independent of x), can
Sigma0(x), resp. Sigma1(x), be computed in 3 instructions
over V? The 4-instruction incumbent (three rotations and
one XOR3 LUT) is proven exact by z3 for both Sigmas, and
matches on 200,000 random differentials each with
0 mismatches (src/exp033_sigma_synth.py).

CEGIS at L = 3 returned UNSAT at iteration 0 on a
34-example seed for Sigma0 (RAW_RESULTS/exp033_sigma_
synth_sigma0_20261115T122610Z.json) and likewise for
Sigma1 (exp033_sigma_synth_sigma1_20261115T123152Z.json).
A universally correct 3-instruction program would match
every example, so UNSAT on the seed set proves none
exists: the Sigma minimum over V, given x and arbitrary
independent side values, is EXACTLY 4 for both Sigma0
and Sigma1. This complements EXP-020, which proved the
full round optimal at 28 vector ops within its searched
vocabulary; here the bound is at scalar word-op
granularity and covers operands drawn from any
independent side values, including ADD-based attempts to
fuse the sum into the Sigma evaluation.

Cone accounting that follows: any cone program whose
Sigma sub-DAG draws its side values independently of the
produced word needs at least 1 instruction producing
a' (resp. e'), plus at least 4 in the Sigma sub-DAG,
plus at least 1 producing Maj (resp. Ch), totalling 6,
exactly the incumbent. Two escape shapes are not
excluded by this argument alone, and are named
precisely:

(E1) Correlation exploitation: the Sigma sub-DAG uses
T1 and T2 as separate operands in a way that only works
because their sum is the produced word. The independent
filler model quantifies side values independently of x,
so it does not cover this shape.

(E2) Maj-routed Sigma: the Sigma output is routed
through the Maj (resp. Ch) value, so the Maj instruction
sits inside the Sigma sub-DAG and the 1 + 4 + 1
accounting then bounds only 5.

The direct attack on shape E1 is the cone-conditioned
synthesis: operand pool (s, T1, T2, a, b) with s = T1 +
T2 enforced per example, every example cone-realizable,
and every instruction of the sub-DAG counted, including
any spent on side-value intermediates. For Sigma1 it
returned UNSAT at iteration 0 on a 16-example seed
(RAW_RESULTS/exp033_sigma_synth_sigma1_cone_
20261115T131822Z.json), and for Sigma0 likewise UNSAT
at iteration 0 on a 16-example seed (RAW_RESULTS/
exp033_sigma_synth_sigma0_cone_20261115T132821Z.json;
two earlier Sigma0 attempts at 34 and 16 examples had
timed out at 900 s under heavier host contention,
RAW_RESULTS/exp033_sigma_synth_sigma0_cone_
20261115T124139Z.json and exp033_sigma_synth_sigma0_
cone_20261115T125903Z.json). No 3-instruction program
with the cone-realizable pool computes Sigma0(s) or
Sigma1(s) at all, so each cone's Sigma sub-DAG has at
least 4 instructions unconditionally, and shape E1 is
EXCLUDED for both cones. Each cone therefore costs 6
unless its Maj (resp. Ch) instruction itself sits
inside the Sigma sub-DAG, which is shape E2, the one
shape left open. No program of that shape is known or
was found; it is UNPROVEN BREAKTHROUGH territory, and
this phase does not claim its impossibility.

### 2.4 Structural argument: no bitwise-free window

The consumption census (section 3.1 data, recorded in
the taint results) shows every word produced by an
addition is consumed bitwise in the very next round and
arithmetically 3 rounds later: a' is consumed by Sigma0
and Maj in the next round, sits in state positions 0, 1,
2, 3 across successive states, and re-enters arithmetic
as the addend in e_new = d + T1 three rounds later; e'
is consumed by Sigma1 and Ch in the next round, sits in
positions 4, 5, 6, 7, and re-enters as the h addend in
T1 three rounds later. There is no round in which a
produced word is used only arithmetically. A redundant
or carry-save representation of a produced word would
have to be resolved to exact bits before the next round
in every case, which is the structural reason the
carry-save direction (already closed for the schedule
in EXP-027) has no purchase across the round boundary
either: the boundary is bitwise on both sides,
immediately. ESTABLISHED NEGATIVE for resolution
avoidance by representation deferral.

## 3. Scope 2: header mathematics re-derived

All results in this section are from src/exp033_taint.py
(symbolic taint over the exact reference compression),
RAW_RESULTS/exp033_taint_20261115T110152Z.json and
PROOFS/exp033_taint_proofs_20261115T110152Z.json.

### 3.1 Nonce taint: W18 is the boundary, and it is exact

In the second block of the inner hash, the nonce is
message word W3. Of the 48 expanded schedule words
W16..W63, exactly W18..W63 (46 words) are
nonce-dependent; W16 and W17 are nonce-free. The first
nonce-dependent expanded word is W18. In the state, the
block-2 state is nonce-free after 3 rounds; dependence
first appears after round 4, in words a and e only, and
the full state is nonce-dependent after 7 rounds.

The delta identities of EXP-016 were re-derived and
strengthened to proofs. Writing D(W) for the XOR delta
of a schedule word under a nonce change: D(W18) =
sigma0(nonce) and D(W19) = nonce hold on 100,000 of
100,000 random samples AND are z3-proven with fully
symbolic template words (UNSAT on the negation for
both). After 3 rounds, a and e are integer-affine in
the nonce with slope 1 (z3 UNSAT on the negation for
both). At W20 the linearity ends: the claim that D(W20)
is GF(2)-linear in the nonce delta is REFUTED by a z3
counterexample (n1 = 539234578, n2 = 1283462784), with
the model re-verified numerically: D(n1 xor n2) =
43171369 while D(n1) xor D(n2) = 3724592575. So the
schedule's nonce dependence is exactly linear for two
expanded words and nonlinear from W20 onward: there is
no linear-algebraic representation of the schedule past
W19, and no exact shortcut down that path.

### 3.2 The 67 of 192 accounting, restated honestly

One SHA-256d trial is 3 compressions, 192 round slots.
Per template, the conventional implementation computes
once: the full first inner block (64 rounds) and rounds
0 to 2 of the second inner block (3 rounds), totalling
67. Per nonce it computes the remaining 61 rounds of
the second inner block and the full outer block (64
rounds), totalling 125. This accounting was re-derived
from the taint boundary (the nonce enters at W3, first
consumed in round 3; W18 is the first expanded word it
touches). It is an accounting of the conventional
implementation. It is NOT a lower bound on any
implementation, and this phase found nothing that turns
it into one: sections 2.1 to 2.4 close the examined
restructuring directions at their stated bounds, but a
universal lower bound on SHA-256d work per nonce is not
claimed and does not follow.

### 3.3 The outer hash admits no precomputation

Digest taint over the outer compression: all 48 computed
schedule words W16..W63 are digest-dependent, all 64
rounds produce digest-dependent words, and the number
of digest-independent complete rounds is 0 (confirming
the EXP-027 census independently). The feed-forward is
8 word additions, already minimal. The inner digest
words pass into the outer message block unchanged (same
word order and endianness by construction of SHA-256d),
so there is no transformation cost to remove and no
representation change with anything to act on. Combined
with section 3.1, no part of the outer compression can
be computed before the inner digest exists, and no part
of the inner per-nonce work can be moved into the
per-template part beyond the conventional boundary.
ESTABLISHED NEGATIVE for outer-hash precomputation and
for exact representation changes of the double hash as a
whole, within every representation this phase and
EXP-027 examined.

### 3.4 Comparison early exit saves no rounds

A tempting exact shortcut is to abandon a trial early
once the digest is known to exceed the target. It saves
nothing: the proof-of-work comparison is decided by the
digest as an integer, its most significant word is a
feed-forward sum involving the final round's state, and
every digest word depends on all 64 outer rounds
(section 3.3). No proper prefix of the outer rounds
determines any digest word, so no partial verdict exists
before the full outer compression completes. Early exit
can save comparisons, never rounds. ESTABLISHED
NEGATIVE.

## 4. Verdict summary

| ID | Statement | Verdict |
|----|-----------|---------|
| H-033-01 | A cheaper two-round graph exists in the R1 to R6 word-level rewrite system | ESTABLISHED NEGATIVE (converged rounds-only; capped joint) |
| H-033-02 | A 5-instruction cone program over V exists | UNPROVEN BREAKTHROUGH (full-cone synthesis inconclusive; narrowed by H-033-03/04) |
| H-033-03 | Sigma0 in 3 instructions over V with independent side values | ESTABLISHED NEGATIVE (minimum exactly 4, proven) |
| H-033-04 | Sigma1 in 3 instructions over V with independent side values | ESTABLISHED NEGATIVE (minimum exactly 4, proven) |
| H-033-05 | A 5-instruction cone exists via shape E1 or E2 | UNPROVEN BREAKTHROUGH (E1 excluded for both cones by H-033-13 and H-033-14; only E2 remains, open for both) |
| H-033-13 | Sigma1 in 3 instructions even exploiting the s = d + T1 correlation | ESTABLISHED NEGATIVE (cone-conditioned CEGIS UNSAT, 16 examples) |
| H-033-14 | Sigma0 in 3 instructions even exploiting the s = T1 + T2 correlation | ESTABLISHED NEGATIVE (cone-conditioned CEGIS UNSAT, 16 examples) |
| H-033-06 | Conventional accounting is 67 of 192 per template, 125 per nonce | VERIFIED (re-derived; accounting, not a lower bound) |
| H-033-07 | W18 and W19 delta identities are exact | VERIFIED (100,000 samples and z3 UNSAT) |
| H-033-08 | Round-3 state words a and e are affine in the nonce, slope 1 | VERIFIED (z3 UNSAT) |
| H-033-09 | W20 delta is GF(2)-linear in the nonce delta | ESTABLISHED NEGATIVE (counterexample, re-verified) |
| H-033-10 | Part of the outer compression is digest-independent | ESTABLISHED NEGATIVE (48 of 48 and 64 of 64 dependent) |
| H-033-11 | A redundant representation defers resolution across the boundary | ESTABLISHED NEGATIVE (no bitwise-free window) |
| H-033-12 | Comparison early exit saves rounds | ESTABLISHED NEGATIVE (no partial verdict exists) |

Net position: the one sub-space EXP-027 left open is
closed at the bounds stated in sections 2.1, 2.3 and
2.4, with exactly one precisely named cone shape left
unrefuted and labelled (E2, for both cones). Nothing in this phase is a
VERIFIED IMPROVEMENT, because nothing was benchmarked
and no kernel exists. No result here moves the system
toward 500 GH/s or 140 TH/s by itself, and no hash rate
of any kind is claimed from this work. The mission
criterion remains what it was: a real, independently
verified, submitted and accepted Bitcoin block.

## 5. What remains open, honestly

- Cone shape E2 only (section 2.3): Sigma routed
  through the Maj or Ch value, unrefuted for both
  cones. A future attack needs a synthesis that counts
  the Boolean output inside the Sigma sub-DAG, a hand
  proof, or a full-cone solver budget far beyond this
  host's contention-limited timeouts.
- The joint e-graph case hit its class cap without
  converging; a larger cap or a DAG (not tree) cost
  model could strengthen section 2.1's joint statement.
- Restructuring in models outside this phase's bounds
  (bit-level circuits with cross-word carry structure
  not expressible as word operations, fusion across more
  than two rounds, vocabularies with vector rotates or
  funnel shifts as single ops) is untouched and remains
  UNPROVEN BREAKTHROUGH territory.
- EXP-020's production gap (29 emitted ops against the
  proven 28-op optimum) is a codegen matter, not a
  mathematical one, and is unchanged by this phase.

## 6. Deliverables and reproduction

- This report: MATHEMATICAL_INVESTIGATION.md
- HYPOTHESIS_REGISTRY.json (per-hypothesis statements,
  statuses, evidence pointers)
- EXPERIMENT_MANIFEST.json
- PROOFS/: exp033_taint_proofs_20261115T110152Z.json,
  exp033_cone_synth_gates_20261115T114122Z.json,
  exp033_sigma_synth_sigma0_20261115T122610Z.json,
  exp033_sigma_synth_sigma1_20261115T123152Z.json,
  exp033_sigma_synth_sigma0_cone_20261115T124139Z.json,
  exp033_sigma_synth_sigma0_cone_20261115T125903Z.json,
  exp033_sigma_synth_sigma0_cone_20261115T132821Z.json,
  exp033_sigma_synth_sigma1_cone_20261115T131822Z.json
- RAW_RESULTS/: the matching raw outputs, plus
  exp033_egraph_20261115T110602Z.json and
  exp033_egraph_verify_20261115T110717Z.json
- src/: exp033_common.py, exp033_taint.py,
  exp033_egraph.py, exp033_egraph_verify.py,
  exp033_cone_synth.py, exp033_sigma_synth.py
- TESTS/test_exp033_foundations.py: all pass.
  Run with the lab venv python (the cone module imports
  z3): ~/workspace/bitcoin-autonomous-lab/.local/
  z3venv/bin/python TESTS/test_exp033_foundations.py
  from this directory. The same venv python runs all
  src/ scripts.
