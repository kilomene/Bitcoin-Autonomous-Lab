# Experiment Register

NOVA SHA-X Master Assignment, deliverable 17. Date: 2026-11-15.

The unified register of the programme: every experiment EXP-000 to
EXP-038, the Phase 6B phase entry, and the Phase 001 entry, each
with its one-line question, its verdict tier, and a pointer to its
report. This register consolidates; it does not replace the two
standing registries (research/sha256d/experiment_registry.md and
research/sha256d/extreme_optimization/EXPERIMENT_REGISTRY.md),
which remain the detailed record. Where a summary here and a
detailed record disagree, the detailed record and its raw results
govern.

Verdict tiers: VERIFIED IMPROVEMENT (EXP-017 protocol, criterion
met), PROVEN (exact identity, solver proof, or property proof at a
stated scope), MEASURED (a number the programme measured, cited
with its conditions), PROMISING HYPOTHESIS (plausible, undecided),
UNPROVEN BREAKTHROUGH (unrefuted, no evidence of a rate),
ESTABLISHED NEGATIVE (refuted or closed at a stated bound),
NOT SIGNIFICANT / NOT VERIFIED (measured, criterion not met),
UNVERIFIED (never measured).

**Next unreserved experiment ID: EXP-039.**

## 1. The register

| ID | Question in one line | Verdict | Report |
|---|---|---|---|
| EXP-000 | What is the trusted production baseline? | MEASURED: production C batch 1-thread median 1,314,704 H/s; hashlib 304,444 H/s (AMD guest) | experiment_registry.md; baseline_performance.md |
| EXP-001 | Do compiler flags on the production wrapper hide a win? | ESTABLISHED NEGATIVE: five gcc flag sets, none beat production; wrapper code instruction-identical across native variants | compiler_experiments.md |
| EXP-002 | Does a direct SHA-NI kernel with the real MSG1/MSG2 schedule close the intrinsics gap? | MEASURED: correct; the MSG schedule alone is worth about 2.6x over a scalar schedule; stepping stone to H-01 | experiment_registry.md; phase6 records |
| EXP-003 | Does interleaving independent SHA-NI streams hide RNDS2 latency? | VERIFIED (in the EXP-017 decision set): H-01 streams-4 strided pooled 2.80x batch over production; per-worker 1-thread median 3.30M H/s | experiment_registry.md; phase6/EXPERIMENT_RESULTS.md |
| EXP-004 | Does the H-01 streams decision survive a re-run under the min/max separation rule? | Criterion FAILED a second time; NOT INTEGRATED (the rule itself was later retired by EXP-017) | extreme_optimization/EXPERIMENT_REGISTRY.md |
| EXP-005 | What is H-01's best stream geometry? | MEASURED: curve flat-topped from 3 to 6 streams; best streams=4 strided | extreme_optimization records |
| EXP-006 | Does a schedule-first hand-scheduled variant win by cutting spills? | ESTABLISHED NEGATIVE: spill ops cut 790 to 117, throughput unchanged; spill traffic is not the binding cost | extreme_optimization records |
| EXP-007 | Does a 16-way AVX-512 multi-buffer kernel beat the field? | MEASURED: fastest medians on this VM, widest variance, no separation claim under the old rule; became the v512 lineage | extreme_optimization records |
| EXP-008 | Does cross-nonce phase pipelining beat deeper interleaving? | ESTABLISHED NEGATIVE: matches a second same-phase stream, loses to deeper interleaving | extreme_optimization records |
| EXP-009 | Where does pipeline time go outside the kernel? | MEASURED (category E components): validateaddress round trip 3.963 ms median dominates construction below about 250 tx; span-size interaction none measurable; search 99.958 percent of stub mine-cycle wall | extreme_optimization records |
| EXP-010 | Part A decision closure under the min/max rule | Criterion FAILED for both candidates a third time; no integration; the failure of the rule itself, which EXP-017 replaced | extreme_optimization/EXP010_PART_A_REPORT.md |
| EXP-011 | Does dual-batch interleaved multi-buffer beat MB16? | PROMISING, unseparated (session ratios 0.58x to 2.27x); raw session A JSON was overwritten, so the figure is EXCLUDED from all models as evidence | extreme_optimization/EXP011_ONWARD_REPORT.md |
| EXP-012 | What are the VPTERNLOGD cone forms and classic minima for Ch, Maj, XOR3? | PROVEN closure: Ch = 0xCA, Maj = 0xE8, XOR3 = 0x96; classic op counts (3, 4, 2) minimal by z3 UNSAT | extreme_optimization records |
| EXP-013 | Does cross-lane prefix sharing in multi-buffer pay? | NOT VERIFIED: correct, effect below this VM's noise floor, ratios straddle 1.0; retained only as a combination ingredient | extreme_optimization records |
| EXP-014 | Does K+W constant folding pay? | ESTABLISHED NEGATIVE | extreme_optimization records |
| EXP-015 | Does a bitsliced SHA-256d pay? | ESTABLISHED NEGATIVE: about 0.03x of MB16, analytic bound confirmed by measurement | extreme_optimization records |
| EXP-016 | Where exactly does nonce dependence enter the schedule and state? | PROVEN: W[18] delta is exactly sigma0(nonce), W[19] delta is exactly the nonce, W[20] onward fully nonlinear; hypotheses Y-065 and Y-075 REFUTED as work reductions | phase6/MATHEMATICAL_DISCOVERIES.md (MD-1) |
| EXP-017 | What measurement protocol can decide integrations on a contended shared-CPU VM? | ADOPTED as the programme's decision rule (2026-11-14): 3+ sessions, paired 65,536-hash blocks, randomized AB/BA, adjusted bootstrap CI above 0 in every session and pooled, full correctness gates, fresh regtest block. Under it: v512 VERIFIED 3.55x batch; H-01 streams-4 strided VERIFIED 2.80x batch | phase6/ records; research/hashrate/HASHRATE_MEASUREMENT_SPECIFICATION.md section 3 |
| EXP-018 | Does a register-resident dual-batch (Y-023) beat the field? | Residency achieved; rate NOT SIGNIFICANT. Not integrated as such; lineage feeds EXP-026 | experiment_registry.md |
| EXP-019 | Does a carry-save schedule (Y-001/Y-002) pay? | ESTABLISHED NEGATIVE at the price gate: a software 3:2 compressor costs 3 instructions, not 2 | experiment_registry.md |
| EXP-020 | What is the cheapest exact form of the full round, machine-searched? | PROVEN optimum within the searched vocabulary: 28 vector ops per steady-state round, with an SMT lower bound of 28; production emits 29 (one gcc Maj codegen op); variant P6C-007 measured 1.051x NOT SIGNIFICANT, not integrated | phase6b/ records |
| EXP-021 | Does a heterogeneous worker pair (MB plus SHA-NI) beat homogeneous pools? | ESTABLISHED NEGATIVE: homogeneous multi-buffer pool wins head to head (pooled 1.363x at 2 threads) | experiment_registry.md |
| EXP-022 | Does a flags-only batch form (masks instead of materialised digests) pay? | VERIFIED in batch scope; INTEGRATED for engine batch consumers (production benchmark pooled 1.441x, batch only; the live search path contains no flags code) | phase6b/PRODUCTION_INTEGRATION_LOG.md Entry 3 |
| EXP-023 | Can midstate-family amortisation (template caching) pay exactly? | MIXED: Y-076 REJECTED as specified; Y-077 data-level caching VERIFIED at prototype level (became EXP-025); Y-079 VERIFIED TABLE | experiment_registry.md |
| EXP-024 | Does mask search (in-kernel opmask compare) beat materialised search? | Design B (predeclared primary) FAILED its criterion (pooled 1.169x, 1 of 3 sessions); design E span scan ESTABLISHED NEGATIVE (about 6.16x slower); flags batch rerun VERIFIED 1.649x in batch scope | phase6b/EXP024_MASK_SEARCH.md |
| EXP-024b | Does the single-batch mask form (design C) verify on a confirmation run? | VERIFIED IMPROVEMENT: pooled 1.398x, every session significant, search scope; NOT INTEGRATED (the certified single-batch fallback form exists only in research code) | phase6b/EXP024_MASK_SEARCH.md; EXPERIMENT_RESULTS.md |
| EXP-025 | Is the EXP-023 template cache correct, and what identity makes it exact? | The prototype was proven UNSAFE (5 stale serves, 2 validation bypasses, fingerprint unchanged); the repaired layered-identity design VERIFIED (19 of 19 adversarial cases, 1,320 differentials byte-identical, regtest block 912) and INTEGRATED into mining/engine.py (owner option A). Its steps500 pooled 23.02x is a candidate-construction rate, never a hash rate | phase6b/ records; mining/engine.py |
| EXP-026 | Does DualMask (dual-batch residency plus in-kernel mask compare) beat production search? | VERIFIED IMPROVEMENT: C2 pooled 1.718x vs production search, 1.444x vs its strongest ingredient, every session significant; INTEGRATED as backend v512dual; post-integration audit PASS WITH NOTES, zero defects. C1 TernMask ESTABLISHED NEGATIVE; C3/C4/C5 killed at the cost model | phase6b/EXP024_MASK_SEARCH.md; DUALMASK_POST_INTEGRATION_AUDIT.md |
| EXP-027 | Do representations outside the EXP-020 vocabulary beat the round? | ESTABLISHED NEGATIVE at stated scopes: GFNI affine forms, VPSHUFB rotations, rotated/byte-swapped state, carry-save beyond the schedule (every deferral distance exactly 0), addition networks, IFMA accumulation; census 0 nontrivial cross-round shared subterms, 0 digest-independent outer rounds. One sub-space left open (non-sharing restructuring), closed by EXP-033 | phase6b/EXP027_COMPUTATION_REPRESENTATIONS.md |
| EXP-028 | Does the AVX-512 F+BW kernel family port across host classes? | VERIFIED on two hosts (AMD EPYC 9D25; Intel Xeon Platinum 8321HC): restricted-flag builds plus CPUID re-probe survive host changes; research -march=native builds SIGILLed on the Intel host, production did not | phase6b/ records |
| EXP-029 | Is the distributed allocator's testable core exact? | PROVEN by property test: 120 randomised trials with death/duplicate/steal/restart injections, completed intervals union exactly to the declared range, pairwise disjoint; end-to-end regtest block 829. Multi-machine overhead, latency and linear scaling UNVERIFIED | phase6b/ records |
| EXP-030 | Umbrella programme: open-source mining intelligence, CPU transformation, autonomous mining, mathematics (Phases A to H) | COMPLETE and CLOSED 2026-11-15. Phase A: 53 findings, 34-row reference matrix; W1 (Qaxe judges blocks by floating-point difficulty) REJECTED as a pattern, Bitaxe exact-verification shape adopted; sub-experiments EXP-031 to EXP-038 below. Success criterion stated NOT MET in its final report | exp030/FINAL_REPORT.md |
| EXP-031 | What does this VM actually deliver? | MEASURED: guest claims 4 vCPUs, delivers about 2 effective CPUs (scaling saturates at 2 threads); baseline 61 to 64 percent busy; perf counters inaccessible (EPERM); ceiling mechanism unknown | exp031/CPU_VM_CHARACTERIZATION.md |
| EXP-032 | What are the verified fallback tiers, and do flags help on the real search path? | AVX2 MB batch VERIFIED 1.409x over C; SHA-NI streams-4 batch VERIFIED 2.861x over C (strongest verified fallback on SHA-NI hosts); production SHA-NI intrin ESTABLISHED NEGATIVE 0.517x; flags on the real search path ESTABLISHED NEGATIVE three ways (2.565x slower as search; dedicated entry 0.967x NOT SIGNIFICANT; 0.493x of dual); v512dual search vs C search re-confirmed VERIFIED 6.781x. The two tiers are NOT dispatched in production | exp032/EXP032_REPORT.md |
| EXP-033 | Can mathematics restructure SHA-256d below the conventional cost? | Non-sharing cross-round restructuring ESTABLISHED NEGATIVE at stated bounds (e-graph, no cheaper graph); Sigma0/Sigma1 minima PROVEN exact at 4; cone-conditioned synthesis UNSAT for both cones (shape E1 excluded); W[20] linearity REFUTED by z3 counterexample; outer precomputation ESTABLISHED NEGATIVE (0 digest-independent rounds); exactly one shape open: E2, UNPROVEN BREAKTHROUGH, full-cone attack INCONCLUSIVE, ceiling about 2 ops per round | exp033/MATHEMATICAL_INVESTIGATION.md |
| EXP-034 | Is the job and template engine exact against Core? | REAL DEFECT found and fixed: the solo server's coinbase split offset was located in the full coinbase and applied to the stripped coinbase, corrupting the served scriptSig on segwit templates (would have corrupted the armed cutover); opt-in extranonce_space added, default byte-identical; job construction vs Core VERIFIED; independent audit PASS, zero defects | exp034/JOB_TEMPLATE_ENGINE.md |
| EXP-035 | Can work distribution be exact under deaths, restarts and steals? | Design plus research prototype PROVEN in-process: 60 of 60 randomised campaign trials, 609,280 declared positions completed exactly (union equals declared space, pairwise disjoint) under 2,167 deaths, 1,564 restarts, 801 coordinator restarts, 806 expiries, 694 steals; 892 duplicate submissions all detected. Production integration deferred; multi-machine overhead, latency and scaling UNVERIFIED; fleet NOT activated | exp035/FINAL_REPORT.md; WORK_DISTRIBUTION_DESIGN.md |
| EXP-036 | Is every candidate judged exactly and every submission honestly accepted? | INTEGRATED: mining/candidate_verify.py (dual recomputation, modern SetCompact rejection, no float operations); solo submitblock None-as-success defect closed; pool and solo paths routed through it; independent audit PASS WITH NOTES, zero defects | exp036/BLOCK_SUBMISSION_DESIGN.md; mining/candidate_verify.py |
| EXP-037 | Are mining statistics and probability exact and honestly accounted? | INTEGRATED (modules): EvidenceCounter full-log census replaced the tail-window counter (248 accepted, 8 rejected at audit time); mining_statistics.py with separated, never-summed counters; probability formulas pinned to anchors and cross-checked against exact rational arithmetic. Known gap: statistics record() has no live caller; probability.py lacks percentile outputs | exp037/ records; mining/mining_statistics.py; mining/probability.py |
| EXP-038 | Can a restarted miner resume without claiming unfinished work? | INTEGRATED (opt-in): exact (extranonce, nonce) frontier keyed by layered identity plus extranonce space plus curtime basis; frontier advances only after a hitless batch; 24-configuration randomised restart campaign showed coverage pairwise disjoint and union-complete; independent audit (with EXP-037) PASS WITH NOTES, zero defects | exp038/ records; mining/work_checkpoint.py |

## 2. Phase entries

| Phase | Scope | Outcome |
|---|---|---|
| Phase 6B | Mask search and integration phase: EXP-024, EXP-024b, EXP-025, EXP-026, EXP-027, EXP-028, EXP-029, with the production integrations of v512dual (EXP-026) executed under the gate set and audited | COMPLETE. DualMask integrated and live; design C verified and held in research; representations closed; portability and allocator core proven. Final report: phase6b/PHASE6B_FINAL_REPORT.md |
| Phase 001 (Genesis Engine) | Exhaustive reverse engineering of the original Bitcoin v0.1.3 source (verified tree, cross-source CRC agreement), 22 deliverables: inventory, architecture, execution flow, transactions, coinbase and Merkle, header specification, constants, compression, schedule, dependency map, SHA-256d reconstruction, PoW mathematics, nonce search, threading, opportunities, hypotheses, benchmarking framework, correctness verification, comparative report, ranked hypotheses, next phase | COMPLETE 2026-11-15. Independent verification suite 36 of 36 checks passed. Headline results: two SHA-256 implementations coexisted in 0.1.3; the original miner reused no midstate (64 of 192 rounds per candidate provably redundant); nonce 0 is never hashed; the word "difficulty" does not occur in 0.1.3; no new open mathematical hypothesis emerged; E2 inherited as the only unrefuted shape. Record: research/phase001/ |

## 3. The rejected-hypotheses index

Settled questions, kept so the programme does not spend itself
twice. A rejection reopens only on evidence of a different kind
than what settled it, cited in a new registry entry.

From research/sha256d/rejected_hypotheses.md:

- **R-01 / H-24: statistical structure in full-round output.**
  Reduced-round bias (0.49 at 16 rounds, 0.08 at 20) is dead by 24
  rounds; full-round samples are clean; winners follow the
  geometric law. REJECTED.
- **R-02: a "lite" screen confirms blocks faster than the full
  hash.** Confirmation is the full double SHA-256; every output bit
  depends on all rounds. REJECTED.
- **R-03: compiler flags on the production wrapper hide a large
  win.** Settled by EXP-001. REJECTED for that file.
- **R-04: more threads than the tuned count must help.** Settled
  repeatedly; thread count is a measured setting on this VM class.
  REJECTED as a direction.
- **R-05: the intrinsics kernel's deficit is a tuning detail.**
  Structural (zero sha256msg instructions, scalar schedule per
  nonce); settled by assembly evidence and re-measured by EXP-032
  at 0.517x. REJECTED.
- **R-06 / H-16: early partial target checks can skip the outer
  hash.** No exact partial check exists in the dependency
  structure. REJECTED.

From EXP-016: **Y-065 and Y-075** (nonce-dependency work
reductions) REFUTED with proof-grade evidence.
From EXP-019: **Y-001 and Y-002** (carry-save schedule forms)
REJECTED at the price gate.
From EXP-023: **Y-076** (the cache as originally specified)
REJECTED; its repaired successor is EXP-025.

From EXP-027 (closures C1 to C6, each at its stated scope):
GFNI affine forms (C1); VPSHUFB rotations (C2); rotated and
byte-swapped state domains (C3); carry-save beyond the schedule
(C4); addition networks and IFMA accumulation (C5, priced out);
cross-round subterm sharing and outer precomputation (C6, census
0 and 0).

From EXP-033: non-sharing cross-round graph restructuring in the
R1 to R6 system (bounded by the joint case's class cap); shape E1
cone correlation (UNSAT, both cones); GF(2)-linear schedule past
W[19] (z3 counterexample at W[20]); comparison early exit as a
round saving.

From EXP-024/026: mask-search design B (criterion failed), design
E span scan (negative), C1 TernMask (negative), C3/C4/C5 (killed
at the cost model). From EXP-021: heterogeneous worker pairing.
From EXP-014: K+W folding. From EXP-015: bitslicing. From
EXP-006: schedule-first spill reduction. From EXP-008: phase
pipelining.

The one item that is NOT in this index, because it is not settled:
**E2** (EXP-033), UNPROVEN BREAKTHROUGH, attack INCONCLUSIVE.

## 4. Standing rules this register enforces

- Next unreserved experiment ID: **EXP-039**. New experiments take
  it onward; re-tests and integrations of existing experiments
  keep their existing numbers.
- A figure whose raw session record was overwritten or lost is
  excluded from evidence (the EXP-011 rule), however plausible it
  looks in transcription.
- Verdicts travel with their scope (batch or search, host,
  category) or they do not travel at all
  (research/hashrate/HASHRATE_MEASUREMENT_SPECIFICATION.md).
