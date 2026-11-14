# Phase 6, First Assignment: Final Report (Tasks 1 to 7)

Date: 2026-11-14. Scope: audit, corrections,
ranking, discovery design, experiment selection,
and one executed experiment. Production code
untouched; EXP-010 not rerun; the live miner, node,
autopilot and keeper were not stopped or altered.

## What was established

1. **The nonce-dependency structure of block 2 is
   now derived exactly** (EXP-016, MD-1): schedule
   separation exists exactly at W18 and W19 and is
   refuted from W20 by proof and measurement; the
   state is integer-affine in the nonce only at
   S_4 (a and e), functionally nonlinear in every
   word from S_8, fully bit-dependent by the sound
   mask bound at S_9, empirically sensitive
   everywhere by S_7. Tier: VERIFIED (proof grade;
   in this programme's tiers, an established
   mathematical result).
2. **Y-065 and Y-075 are closed**, with proof-grade
   evidence, recorded in the registry, in
   REJECTED_APPROACHES.md, and in the ceiling
   report's corrected section 3. Two of the
   programme's three UNPROVEN BREAKTHROUGH claims
   are now resolved, both negatively, which is what
   resolving means.
3. **The programme's own conclusions are now
   correctly scoped**: the 125-round count is the
   conventional evaluation's remainder, not a
   universal bound; the ceiling models are labelled
   implementation-model estimates in six separated
   categories with their assumptions collected; the
   memory conclusion is narrowed to DRAM bandwidth
   with the register, spill and stack evidence
   attached. The targets (500 GH/s, 140 TH/s) are
   unchanged everywhere and now carry a level-by-
   level resource model (PERFORMANCE_TARGET_MODEL
   .md) instead of adjectives.
4. **The discovery machinery exists and is
   seed-validated**: src/discovery_harness.py
   reproduces EXP-012's ternlog results from
   scratch through its own proof gate (P6C-001 to
   P6C-004). Workstream A now has an instrument,
   not only a reading list.
5. **All 108 Y hypotheses are ranked under a
   published, reproducible method**, and the
   fifteen Workstream B entries each carry an
   unresolved question (two of them now answered)
   and a designed experiment.

## What failed

- Nothing in this assignment failed outright; the
  honest negative results are the two refutations
  above, which are findings, not failures.
- Carried in from the audit, unresolved: the
  EXP-011 session-A data loss (unrecoverable; the
  figure is downgraded to transcription status
  permanently), the AVX-512 variance anomaly
  (mechanism still unknown, OP-3), and the
  programme's decision-procedure problem (three
  criterion failures), which EXP-017 is designed
  to settle and which remains open until it runs.

## Conclusions under the three tiers

- VERIFIED IMPROVEMENT: none claimed in this
  assignment. No kernel was benchmarked for
  integration and no rate improved. (EXP-016 is a
  verified mathematical result, listed under
  "established" rather than as a performance
  improvement, deliberately.)
- PROMISING HYPOTHESIS: the measurement stack
  (EXP-017: Y-101, Y-102, Y-103, Y-108 as a rule);
  register-resident dual-batch (EXP-018, Y-023);
  carry-save schedule pricing (EXP-019, Y-002 then
  Y-001); the heterogeneous pairing (Y-097) as the
  cheapest anomaly probe in the registry.
- UNPROVEN BREAKTHROUGH: the general graph
  question (OP-1) remains open with no surviving
  named candidate mechanism after EXP-016's
  closures; automated full-round rewriting
  (EXP-020) is the programme's instrument for it.
  Cross-nonce structure beyond dependence
  arguments (OP-7) is recorded as open and
  untouched. Neither objective (500 GH/s,
  140 TH/s) is approached by anything in this
  assignment, and nothing here is written as if it
  were: the target model shows the known families
  reaching the objectives only at fleet scale,
  and the breakthrough that would change that
  arithmetic has not been found.

## What happens next

In selection order: EXP-017 (measurement stack),
EXP-018 (register-resident dual-batch under the
new statistic), EXP-019 (carry-save price list
feeding the discovery cost model), EXP-020
(full-round rewriting campaign). After EXP-017,
every subsequent Phase 6 record carries a Y-108
manifest and append-only raw artifacts. The
Workstream B designs for Y-025, Y-047, Y-048,
Y-049, Y-056 and Y-093 stand ready at their stated
triggers.

## Files

Created: this phase6/ tree (PHASE6_RESEARCH_PLAN,
COMPUTATION_GRAPH_RESEARCH, HYPOTHESIS_RANKING,
MATHEMATICAL_DISCOVERIES, CPU_EXECUTION_RESEARCH,
PERFORMANCE_TARGET_MODEL, EXPERIMENT_RESULTS,
OPEN_PROBLEMS, REJECTED_APPROACHES, this report;
src/nonce_dependency.py, src/discovery_harness.py,
src/rank_hypotheses.py; analysis/exp016_dependency
_results.json, analysis/hypothesis_ranking.json,
analysis/ranking_table.md; proofs/exp016_z3_
results.json, proofs/discovery_demo_results.json).
Corrected in place: extreme_optimization/
PERFORMANCE_CEILING.md, PERFORMANCE_ROADMAP.md,
MATHEMATICAL_DISCOVERY.md, MEMORY_AND_CACHE_
RESEARCH.md, MASTER_RESEARCH_PLAN.md,
FINAL_RESEARCH_REPORT.md, EXP011_ONWARD_REPORT.md
(correction note appended), HYPOTHESIS_REGISTRY_Y
.md (status notes on Y-065 and Y-075), and
../header_and_midstate_analysis.md. Registries
updated: extreme_optimization/EXPERIMENT_REGISTRY
.md (EXP-016), ../experiment_registry.md (pointer),
../research_findings.md (Phase 6 pointer).

## Addendum (2026-11-14): EXP-017, the measurement stack

EXP-017 has run. The paired protocol (65,536-hash
blocks, randomised order, 160 pairs per session,
three sessions per comparison) and its
predeclared covariate-adjusted paired log-ratio
statistic are validated as instruments: both
equal-pair controls returned nulls in every
session and pooled, the historical min/max rule
passed a phantom difference in 0 of 6 control
sessions, and an injected +0.20 effect was
recovered with bias at most 0.0006. The covariate
adjustment was priced near-neutral (pooled CI
width ratios 0.970 to 0.999); the pairing carries
the decision value. Under the EXP-017 rule, and
only under it, both AVX-512 MB (pooled +1.2652,
3.55x) and streams=4 strided (+1.0298, 2.80x) are
significantly faster than production in every
session. Conclusions under the three tiers:

- VERIFIED IMPROVEMENT: the programme's decision
  capability. Kernel comparisons that three
  whole-round decisions could not settle are now
  decidable at 65,536-hash pairing on this VM,
  with controls certifying the null. The rate
  ordering above is a verified measurement under
  the stated contention, not an integration.
- PROMISING HYPOTHESIS: none new; the geo
  comparison's between-session variance
  component (0.0434) is a measured property to
  re-check in EXP-018's sessions, not assume.
- UNPROVEN BREAKTHROUGH: unchanged. Nothing in
  EXP-017 speaks to the computation graph.

A proposal to replace the integration decision
rule with the EXP-017 rule is recorded in
EXPERIMENT_RESULTS.md for the owner. It is not
enacted; production is unchanged, and no kernel
was integrated by this experiment. Full record:
EXPERIMENT_RESULTS.md, EXP-017; raw data in
benchmarks/exp017/.
