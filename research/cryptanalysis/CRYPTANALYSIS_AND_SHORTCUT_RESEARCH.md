# Cryptanalysis and Shortcut Research

NOVA SHA-X Master Assignment, deliverable 14 (work package BR-014,
cryptanalytic research). Date: 2026-11-15.

This document is the programme's complete cryptanalysis status: what
classes of shortcut have been investigated against exact SHA-256d
mining, how each was closed and at what scope, what remains open, and
the standing rules that keep reduced-round results from being
misread as full-round results.

Tier labels, used throughout: VERIFIED IMPROVEMENT (measured under
the EXP-017 protocol and reproduced), PROMISING HYPOTHESIS
(plausible, awaiting a deciding experiment), UNPROVEN BREAKTHROUGH
(unrefuted, no evidence of a rate), ESTABLISHED NEGATIVE (refuted or
closed at a stated bound). A closure is valid only at its stated
scope; a scope is part of the result.

The standing rule, stated once and applied everywhere below:
**reduced-round results never imply full-round relevance.** SHA-256d
as mined applies the full 64-round compression twice. A property
measured at 16, 20 or 24 rounds is a property of a different, weaker
function. It may characterize the safety margin of the real
construction; it is never evidence about the real construction's
cost, and no document in this programme may cite it as such.

## 1. The statistical class: output bias and prediction

The oldest shortcut hope: if full-round SHA-256d output carried any
exploitable bias, a miner could search a biased subset of candidates
and win more often than the geometric law allows.

What the programme measured (the lab's own reduced-round
measurements, research/sha256d/rejected_hypotheses.md R-01, mirrored
as H-24 REJECTED):

- A parametrized reduced-round SHA-256 shows a one-bit output bias
  of about 0.49 at 16 rounds and about 0.08 at 20 rounds.
- From 24 rounds on the bias is indistinguishable from noise (0.0077
  at 24, flat through 64).
- A fresh 1M-hash sample at full rounds shows bit fraction 0.49998
  and worst-byte p about 0.015: no deviation.
- Chain winners under the lab's own search follow the geometric law
  of the search protocol (median scaled nonce 0.50 observed).

Verdict: ESTABLISHED NEGATIVE. Every statistical foothold measured
dies roughly 40 rounds before the function ends. The bias curve is
retained as a safety-margin characterization (it shows how much
round margin the construction carries), never as an attack surface.
Any future statistical proposal must present evidence of a different
kind than a reduced-round bias measurement, per the rejected
hypotheses reopening rule.

## 2. The screening class: partial evaluation and early exit

The second hope: reject most candidates with a partial computation,
paying the full hash only for survivors.

- **Partial screens (R-02, R-06).** Confirmation IS the full double
  SHA-256 at or under target. Every output bit of the outer hash
  depends on all 64 outer rounds plus feed-forward, so any partial
  screen produces candidates that still require the full
  computation. There is no cheaper exact verdict.
- **Comparison early exit (EXP-033 section 3.4).** No proper prefix
  of the outer rounds determines any digest word: every digest word
  is a feed-forward sum over the final state. Early exit can save
  comparisons (word compares after the digest exists), never rounds.
- **Digest-prefix filtering (H-16 analysis).** The target compares
  the full outer digest; the most significant digest word is only
  known after the final round, so comparison order creates no
  shortcut.

Verdict: ESTABLISHED NEGATIVE for the class. The legitimate meaning
of "lite" in this programme is wasting none of the full work
(midstate reuse, exact accounting, in-kernel mask compare), which
the production path already does. Probabilistic skipping of any kind
is prohibited by the programme's non-negotiables: exact SHA-256d for
every candidate, no exceptions.

## 3. The precomputation class: what can be computed before the nonce

The third hope: move work out of the per-candidate path.

What is proven possible (the conventional accounting, EXP-033
section 3.2, restated in research/sha256d/
SHA256D_MATHEMATICAL_SPECIFICATION.md section 7.4): for a fixed
template, 64 rounds of pass 1 chunk 1 plus rounds 0 to 2 of chunk 2
are nonce-independent, 67 of 192 rounds, and production caches
exactly that prefix (the midstate plus the fixed rounds). This is an
accounting of the conventional implementation, **not a lower
bound**: nothing in the programme proves that no different
computation of SHA-256d could reuse more, and no document may cite
125 rounds per candidate as proven minimum work.

What is closed:

- **Outer-hash precomputation: ESTABLISHED NEGATIVE.** The number of
  digest-independent complete outer rounds is 0; all 48 computed
  outer schedule words are digest-dependent (EXP-027 C6 census,
  EXP-033 section 3.3). No part of the outer compression can be
  computed before the inner digest exists.
- **Schedule linearity past W[19]: REFUTED.** The nonce's influence
  is exactly linear for precisely two expanded words (W[18] delta is
  exactly sigma0(nonce); W[19] delta is exactly the nonce; both
  PROVEN, EXP-016, re-proven by EXP-033 with z3 over symbolic
  template words). The claim that the W[20] delta is GF(2)-linear in
  the nonce delta is refuted by a z3 counterexample (EXP-033
  section 3.1). There is no linear-algebraic representation of the
  schedule past W[19], and no exact shortcut down that path.
- **Template-side caching beyond identity:** the EXP-025 work showed
  the boundary from the engineering side: a candidate-construction
  cache is exact only under a layered cryptographic identity, and
  its measured gains are construction rates, never hash rates
  (research/hashrate/HASHRATE_MEASUREMENT_SPECIFICATION.md
  section 1).

## 4. The representation class: computing the same function differently

The fourth hope: a different exact representation of the round
function (different operations, different data layout) that costs
less than the incumbent. This is the class EXP-020, EXP-027 and
EXP-033 searched most deeply.

Proven optima inside the searched vocabulary:

- The joint round-plus-schedule cost is optimal at **28 vector
  operations** per steady-state round within the vocabulary
  {VPADDD, VPTERNLOGD, classic bitwise, VPROLD, VPSRLD} (EXP-020:
  e-graph extraction achieving 28, plus an assembled lower bound of
  12 offset ops + 4 combines + 2 ternlog + 10 adds). Production
  emits 29; the gap is one compiler codegen op on Maj, not a graph
  discovery.
- Sigma0 and Sigma1 each have minimum **exactly 4 instructions**
  over {ADD, LUT(any immediate), ROTR, SHR}, proven by CEGIS UNSAT
  at length 3 with incumbents proven exact (EXP-033). The
  cone-conditioned form (exploiting the correlation s = T1 + T2,
  shape E1) is also UNSAT for both cones.
- Addition counting floors are met by the incumbents: a
  five-operand sum needs at least 4 binary adds, a four-operand sum
  at least 3 (EXP-027 C5).

Established negatives, each at its stated scope:

- **Non-sharing cross-round graph restructuring** in the R1 to R6
  word-level rewrite system: e-graph equality saturation found no
  cheaper graph for the two-round round function (rounds-only case
  converged to a fixed point; the joint rounds-plus-schedule case
  hit its class cap with identical extraction costs, so the joint
  statement is bounded by that cap). EXP-033 section 2.1.
  ESTABLISHED NEGATIVE at that bound.
- **Cross-round subterm sharing:** census found 0 nontrivial
  subterms shared across the round boundary. EXP-027 C6.
  ESTABLISHED NEGATIVE.
- **Carry-save and redundant representations across the round
  boundary:** every word produced by an addition is consumed
  bitwise in the very next round and arithmetically 3 rounds later;
  the deferral distance of every round addition is exactly 0, and a
  software 3:2 compressor costs 3 instructions against the adds it
  would save. EXP-027 C4, EXP-019 (schedule pricing), EXP-033
  section 2.4. ESTABLISHED NEGATIVE.
- **GFNI affine forms:** the sigma maps are GF(2)-linear (proven)
  but any GFNI construction costs at least 11 ops against the 4-op
  incumbent; Ch and Maj are not GF(2)-affine at all
  (counterexamples exhibited). EXP-027 C1. ESTABLISHED NEGATIVE.
- **VPSHUFB rotations:** pure shuffle forms refuted exhaustively;
  the mixed form is exact but measured at 2.00x the VPROLD price.
  EXP-027 C2. ESTABLISHED NEGATIVE.
- **Rotated and byte-swapped state domains:** refuted by
  counterexample; neither commutes with addition, so every addition
  forces a de-rotation and re-rotation. EXP-027 C3. ESTABLISHED
  NEGATIVE.
- **Bitsliced state:** closed by measurement at about 0.03x of the
  multi-buffer kernel. EXP-015. ESTABLISHED NEGATIVE.
- **K+W constant folding:** no gain as implemented. EXP-014.
  ESTABLISHED NEGATIVE for that shape.
- **IFMA accumulation (VPMADD52):** priced at 5 ops against 4
  VPADDD for the T1 sum and 4 against 3 for the schedule sum.
  EXP-027. ESTABLISHED NEGATIVE at the price gate.

## 5. The one open shape: E2

**E2: Maj-routed (resp. Ch-routed) Sigma.** The cone accounting
behind the Sigma minima (1 instruction producing the new state
word, at least 4 in the Sigma sub-DAG, at least 1 producing Maj or
Ch, totalling the incumbent 6) bounds a 5-instruction cone only if
the Maj/Ch instruction sits outside the Sigma sub-DAG. If the Sigma
output is routed through the Maj (resp. Ch) value, so the Boolean
instruction sits inside the Sigma sub-DAG, the accounting does not
exclude a 5-instruction cone.

Status, exactly as EXP-033 section 2.3 left it:

- Shape E1 (correlation exploitation through T1 and T2 as separate
  operands) is EXCLUDED for both cones.
- Shape E2 is unrefuted for both cones.
- The direct full-cone synthesis attack at length 5 was
  INCONCLUSIVE: solver timeout at the stated bound (600 s under
  host contention), which is evidence in neither direction.
- No program of the E2 shape is known.
- Its ceiling, if it exists, is at most about 2 ops per round
  across both cones, against a 28-op round: bounded and small
  either way.

Tier: **UNPROVEN BREAKTHROUGH.** Plausible only in the sense of not
yet refuted. It carries no rate, no evidence of existence, and no
claim on any throughput target. It must never be reported as an
improvement, a finding of fact about SHA-256d's true cost, or
progress toward 500 GH/s or 140 TH/s. Its deciding procedure is
known (a synthesis formulation that counts the Boolean output
inside the Sigma sub-DAG, or a much larger solver budget) and is
ranked fifth, not first, in the next-phase list precisely because
its ceiling is small and its decidability is partial (Phase 001,
RANKED_RESEARCH_HYPOTHESES.md, Rank 5).

## 6. Explicitly untouched territory

Recorded so the map's edge is visible (EXP-033 section 5;
SHA256D_MATHEMATICAL_SPECIFICATION.md section 8.4): restructuring
in models outside the searched bounds is unsearched and remains
UNPROVEN BREAKTHROUGH territory with no evidence for or against:
bit-level circuits with cross-word carry structure not expressible
as word operations, fusion across more than two rounds, and
vocabularies with vector rotates or funnel shifts as single ops.
Naming this territory is not a research programme and carries no
expected value; it is a statement of where the closures stop.

## 7. The speculative tier, named and bounded

For completeness: differential or linear cryptanalysis of
full-round SHA-256, collision or preimage attacks on SHA-256d, and
chosen-input structural attacks sit in the SPECULATIVE
CRYPTANALYSIS tier (Phase 001, CRYPTOGRAPHIC_RESEARCH_
OPPORTUNITIES.md section 7). Standing facts: no published result
threatens full-round SHA-256 preimage resistance; the lab's own
reduced-round measurements show the statistical footholds dying
roughly 40 rounds before the function ends; no item in this tier
has any supporting evidence from programme work. Any future work
here begins as literature study under BR-014, not as an experiment
with an expected payoff, and nothing in this tier may be presented
as a breakthrough direction.

## 8. Summary of the cryptanalysis position

- Statistical shortcuts: closed by measurement (bias dead by 24
  rounds; full-round samples clean; winners geometric).
- Screening shortcuts: closed by dependency proof (no partial
  verdict exists; early exit saves comparisons, never rounds).
- Precomputation beyond the conventional prefix: closed for the
  outer hash (0 digest-independent rounds) and for schedule
  linearity (refuted at W[20]); the 67-of-192 figure is accounting,
  not a bound.
- Representation shortcuts: closed at stated scopes by EXP-020,
  EXP-027 and EXP-033, with the round proven optimal at 28 vector
  ops within the searched vocabulary.
- One shape remains: E2, UNPROVEN BREAKTHROUGH, attack
  INCONCLUSIVE, ceiling about 2 ops per round.
- Everything beyond the searched models is named as untouched
  territory, not as opportunity.

The honest conclusion of this work package: within every model the
programme has been able to search, exact SHA-256d costs what the
conventional implementation costs, and the wins that exist are
engineering wins (width, residency, dispatch, caching under exact
identity), not cryptanalytic ones. That is a result, and it is the
reason the programme's effort is allocated the way
MASTER_RESEARCH_FINDINGS.md records.
