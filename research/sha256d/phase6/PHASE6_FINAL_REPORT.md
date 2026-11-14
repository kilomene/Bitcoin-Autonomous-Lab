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

## Addendum (2026-11-14): EXP-018, register-resident dual-batch (Y-023)

EXP-018 has run, the first kernel experiment
decided under the EXP-017 statistic. The new
kernel (extreme_optimization/src/
avx512_mb_reg.c) holds both batches' state
sets in sixteen named zmm variables across an
eight-round ring-relabeled unit: the assembly
audit shows exactly one state vector homed in
a single stack slot and no stack traffic for
the other fifteen, so the mechanical half of
Y-023 (residency) is achieved; a full 64-round
unroll compiled first and spilled heavily,
which bounds how the register file can hold
this design. The rate half is not achieved:
against single-batch MB the adjusted pooled
log-ratio is +0.0836 (CI -0.0247 to +0.1902),
positive in all three sessions, significant
in none; against production it is +1.5027
(4.49x), significant everywhere; the control
is null. Conclusions under the three tiers:

- VERIFIED IMPROVEMENT: none from this
  experiment. The residency construction and
  its audit are verified mechanical results,
  but Y-023's predeclared definition requires
  the rate significance as well, and it is
  absent.
- PROMISING HYPOTHESIS: Y-023 itself, still.
  The point estimate against single-batch MB
  is +8.7 percent with pairs won 0.554, but
  the interval crosses zero; the measured
  finding is that state traffic was not the
  binding cost in the dual-batch shape on
  this machine.
- UNPROVEN BREAKTHROUGH: unchanged.

No integration; production is unchanged. Full
record: EXPERIMENT_RESULTS.md, EXP-018; raw
data in benchmarks/exp018/.

## Addendum, 2026-11-14: owner decision, integration of the AVX-512 multi-buffer kernel

The owner decided on 2026-11-14: the EXP-017
statistic is ADOPTED as the programme's
integration decision rule, replacing the old
min/max separation rule, and the AVX-512
multi-buffer kernel is the integration target.
The adopted rule: a candidate integrates when,
under the EXP-017 protocol (paired
65,536-hash blocks, randomized AB/BA order,
adjusted paired log-ratio), the adjusted 95
percent CI lies entirely above 0 in every
session and pooled over at least 3 independent
sessions, all correctness gates pass, and a
fresh regtest block is mined through the
production path and accepted by Core. The
EXP-017 evidence for this kernel: pooled
log-ratio +1.2652 against production (3.55x,
CI 3.17x to 3.97x), significant in every
session, both equal-pair controls null.

Integration as built: the kernel's production
translation unit is mining/cpu/bal_avx512_mb.c
(byte-identical to the EXP-007 research source
except the header comment and the bal_search.h
include path), built by mining/cpu/build.py
into .local/cpu/libbal_v512.so with the
restricted flags -mavx512f -mavx512bw, never
-march=native, and linked with the flag-free
CPUID probe mining/cpu/bal_avx512_probe.c.
The required feature set, AVX-512F plus
AVX-512BW, was determined from the kernel's
intrinsics (vprold and vpternlogd are F;
_mm512_shuffle_epi8 is BW) and confirmed by an
objdump audit of the production object (zero
VBMI, DQ or IFMA mnemonics anywhere in it).
ComputeEngine selects the new backend "v512"
only when the probe confirms both features
and a 256-nonce batch reproduces hashlib
digests exactly; any failure at any step falls
back cleanly to the OpenSSL C backend, an
explicit requested="c" still selects C alone,
and machines without AVX-512 behave exactly
as before. Accounting follows the counted
contract with wave semantics: attempted counts
the real nonces of completed 16-lane waves,
backend_hashes counts actual lane computations
including dummy lanes.

Gates, all through the production path
(tests/test_avx512_integration.py, now make
test-avx512 and part of test-all): dispatch
and fallback verified; 196,608 randomized
differentials against hashlib, zero mismatch;
candidate sets equal to independent recounts;
genesis, boundary nonces including the final
nonce, target equality and minus-one, and
independent candidate verification all pass;
fresh regtest block mined with the MB backend
selected and accepted, height 630, hash
20efd9330ba7d17fade70fb87e582de702573534354f
05709fdf0356fa45181d (a second fresh block
followed during the full-suite run: height
700, hash 214e7788eeaac3152e65235e7a816f23f
bd825630d81d25da92343b8bce1eef9). Full
test-all: 20 of 21 targets pass; the only
failure is test-rtl (iverilog absent from
this VM, pre-existing environment, unchanged).
An in-situ EXP-017-protocol paired smoke of
the integrated path (one session, labelled
smoke): 2.76x against the C backend, CI 1.86x
to 4.05x, 32 of 40 pairs won.

Deployment: code pushed and tree-verified
first (missing_or_diff [], extra_managed []),
then the live miner child was terminated and
the autopilot respawned it onto the new code
(miner pid 89317). Verification: heartbeat
fresh, autopilot status running, the miner
log and status file show backend v512
(avx512-mb) selected, the hash counter
advancing (402,653,184 hashes at t=30s of the
new session, session rate 13.28M H/s against
3.33M H/s in the previous C session under
comparable contention), shares_accepted_total
60. The mainnet node was not restarted and
its sync was not disturbed (blocks 411,570
and progressing at verification time).

Classification: VERIFIED IMPROVEMENT under
the adopted rule. The C backend remains the
fallback on every machine without the
required features, and the pre-integration
production files are preserved under
.local/pre-avx512-integration/ for rollback.
