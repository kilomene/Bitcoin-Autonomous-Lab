# Phase 6B Master Plan: Extreme Throughput Research

Programme: NOVA SHA-X, Bitcoin Autonomous Lab.
Phase opened: 2026-11-14, by owner directive "NOVA SHA-X,
EXP-024 and Phase 6B".
Starting point: the integrated AVX-512 multi-buffer
production backend ("v512", mining/cpu/bal_avx512_mb.c,
dispatched from gpu/engine.py).
Status of this document: plan of record for Phase 6B.
It plans; it reports no results. Results live in
EXPERIMENT_RESULTS.md and in the per-experiment files.

## 1. Mission and targets (unchanged, at full height)

We are building an exceptionally fast Bitcoin mining
software system for exact SHA-256d on existing processors.
No new CPU, ASIC, FPGA processor or chip is in scope.

System performance objectives:

| Objective | Required throughput |
|---|---|
| Minimum objective | 500 GH/s |
| Larger objective | 140 TH/s |

Neither objective may be silently reduced. No result
below 500 GH/s is a completion criterion or a final
ceiling. Results below the objectives are intermediate
milestones and are labelled intermediate in every
document that cites them.

Every report in this phase distinguishes, and never
merges:

1. Experimental improvement.
2. Verified kernel throughput.
3. Verified CPU throughput.
4. Verified complete-system throughput.
5. Aggregate distributed throughput.
6. Actual Bitcoin mining performance.

An aggregate theoretical estimate is never reported as
a measured result. A candidate-construction rate is
never reported as a SHA-256 hash rate. A benchmark
improvement is never described as achieving the mission.

Classification of every claim, three tiers, standing:

- VERIFIED IMPROVEMENT: actually measured and reproduced
  under the adopted decision rule (section 5).
- PROMISING HYPOTHESIS: plausible, with some measured or
  proven support, awaiting a reproducing measurement.
- UNPROVEN BREAKTHROUGH: a claim that needs substantial
  investigation before any performance language is used.

Ambition never upgrades a tier. Only reproduced
measurement does.

## 2. Two parallel tracks

### Track A, near-term engineering

Improve the actual mining implementation:

- EXP-024: mask-based early-exit search in the real
  production search path.
- EXP-025: repair of the EXP-023 cache identity before
  any cache integration is trusted.
- EXP-026: deeper AVX-512 execution research, including
  combined designs, costed before they are built.
- Production integration under the rules of section 6.
- Mining pipeline efficiency, CPU portability,
  reliability.

### Track B, breakthrough discovery

Search for fundamentally different exact computational
strategies:

- EXP-027: new computational representations, outside
  the instruction vocabulary closed by EXP-020.
- New mathematical representations, cross-round
  optimisation, automated computation-graph discovery,
  alternative instruction vocabularies, new software
  execution architectures.

Track B receives meaningful research effort even when
Track A produces attractive incremental improvements.
Incremental optimisation must not become the whole
project: a 3, 5, 10 or 20 percent kernel gain is useful
and is not, by itself, the mission.

Supporting workstreams:

- EXP-028: cross-architecture software research
  (portable implementations, runtime detection, safe
  fallbacks).
- EXP-029: parallel and distributed CPU execution
  (exact nonce coverage, no duplicate work counted as
  unique).

## 3. Execution order

- Assignment A: repository audit. Deliverable:
  CURRENT_PRODUCTION_AUDIT.md in this directory.
  Status: complete, 2026-11-14 (audit executed
  2026-11-15 UTC on the live tree; see the audit file).
- Assignment B: EXP-024, mask-based early-exit search.
- Assignment C: EXP-025, EXP-023 cache correctness.
  No cache optimisation enters production without it.
- Assignment D: EXP-026, AVX-512 execution research.
- Assignment E: EXP-027, computation representations
  (Track B launch; runs in parallel with Track A from
  this point, per directive section 11).
- Assignment F: EXP-028 and EXP-029, multi-architecture
  and distributed roadmaps.
- Assignment G: performance gap assessment,
  PERFORMANCE_GAP_MODEL.md maintained from evidence.
- Assignment H: final report, PHASE6B_FINAL_REPORT.md.

Do not start by rewriting the entire miner. Experimental
implementations stay separate from production until they
pass their gates (section 6).

## 4. Experiment records

Every experiment carries: unique experiment ID, source
commit (here: the remote tree head at experiment start,
recorded by blob comparison because this checkout has
no .git directory), hypothesis declared before testing,
success criterion declared before testing, mathematical
basis, implementation details, proof or differential
test evidence, machine-code evidence, benchmark
methodology, raw results preserved append-only under
uniquely named session files, statistical analysis,
decision, follow-up.

The registry of record is
research/sha256d/extreme_optimization/EXPERIMENT_REGISTRY.md.
EXP-024 to EXP-029 are reserved there with status
RESERVED / NOT STARTED as of this plan.

## 5. Benchmarking and evidence rules (directive section 12)

The EXP-017 methodology is the approved decision
framework unless explicitly revised by the owner:

- At least three independent sessions.
- Paired 65,536-hash blocks, or a justified equivalent.
- Randomised arm ordering (AB/BA).
- Equal-pair controls, which must return nulls.
- Predeclared analysis; pooled and per-session
  confidence intervals.
- A performance claim is significant exactly when the
  adjusted confidence interval lies entirely above 0
  in every session and pooled.
- Correct accounting of actual work: requested hashes
  are never reported as completed hashes; candidate
  builds are never reported as hashes; duplicate work
  is never reported as unique coverage; verification
  work is never reported as primary backend throughput;
  theoretical performance is never reported as measured
  performance.
- Record for every session: exact code state, compiler
  and flags, CPU model and exposed instruction
  features, actual CPU allocation, runnable load and
  steal, node synchronisation state, thread count,
  vector width, batch size, actual unique nonce
  coverage, actual backend hashes, verification hashes
  separately.
- Raw JSON is preserved immediately, append-only,
  uniquely named. Sessions are never added after seeing
  an unfavourable result unless a new experiment is
  formally declared.

## 6. Production integration rules (directive section 14)

A production change requires all of:

1. Mathematical correctness.
2. Full differential tests.
3. Boundary tests.
4. Accounting tests.
5. Memory-safety tests (sanitizers where available).
6. Runtime dispatch tests.
7. Fallback tests.
8. Independent performance validation under section 5.
9. Fresh regtest block acceptance through the
   production path.
10. A documented post-integration audit.

The existing production implementation is preserved as
a known-good fallback. Feature detection is explicit
and runtime (the v512 CPUID probe pattern). No part of
the program is compiled with machine-specific flags
that make it unusable on other supported CPUs; the
restricted-flag translation-unit pattern of
mining/cpu/build.py is the model. Rejected
implementations and historical evidence are never
deleted.

Bitcoin correctness is non-negotiable (directive
section 13): exact SHA-256d, exact 80-byte headers,
exact target, correct coinbase, extranonce, Merkle
roots and SegWit witness commitments, independent
candidate verification before submission, block
submission to Bitcoin Core and acceptance confirmed
against the node best chain. No consensus changes, no
alternative hash function, no probabilistic skipping,
no approximation that can miss a valid block.

## 7. Documents of this phase

In research/sha256d/phase6b/:

1. PHASE6B_MASTER_PLAN.md (this file).
2. CURRENT_PRODUCTION_AUDIT.md (Assignment A).
3. EXP024_MASK_SEARCH.md.
4. EXP025_CACHE_CORRECTNESS.md.
5. EXP026_AVX512_EXECUTION.md.
6. EXP027_COMPUTATION_REPRESENTATIONS.md.
7. EXP028_CPU_ARCHITECTURES.md.
8. EXP029_DISTRIBUTED_EXECUTION.md.
9. PERFORMANCE_GAP_MODEL.md.
10. HYPOTHESIS_RANKING.md.
11. EXPERIMENT_RESULTS.md.
12. OPEN_PROBLEMS.md.
13. REJECTED_APPROACHES.md.
14. PRODUCTION_INTEGRATION_LOG.md.
15. PHASE6B_FINAL_REPORT.md.
