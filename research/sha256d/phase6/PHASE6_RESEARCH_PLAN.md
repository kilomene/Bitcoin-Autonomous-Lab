# NOVA SHA-X, Phase 6: Breakthrough Computation Research

## 0. Standing orders for this phase

- Objectives, unchanged and not negotiable inside
  the programme: 500 GH/s is the minimum system
  objective; 140 TH/s is the larger objective.
  Neither is lowered, replaced, redefined, or
  declared achieved without reproducible evidence.
  Every intermediate result is labelled
  intermediate.
- Every claim carries one of three tiers:
  VERIFIED IMPROVEMENT (measured and reproduced
  under the programme's decision rules),
  PROMISING HYPOTHESIS (plausible, awaiting test),
  UNPROVEN BREAKTHROUGH (would change the
  computation fundamentally; needs substantial
  investigation before any performance language is
  used about it).
- Exact SHA-256d only. Any candidate must produce
  bit-identical digests; correctness evidence
  precedes any benchmark number.
- Production code is not modified by research.
  Integration is a separate, later decision under
  EXP-010's predeclared criterion standard.
- This phase investigates the whole computational
  path: candidate construction, schedule, state,
  compression, comparison, confirmation, and the
  interactions between kernel rate and pipeline
  cost (EXP-009 showed confirmation is the binding
  interaction at high kernel rates, not a footnote).

## 1. Task 1 audit of the existing programme

Method: the audit read the production path
(mining/cpu/bal_batch.c, the OpenSSL midstate
library; gpu/engine.py), the experimental sources
(extreme_optimization/src/*.c, experiments/h02_shani),
the harnesses (benchmarks/*.py), the raw JSON behind
every headline number, and the research documents
themselves. Findings are classified as ESTABLISHED
(measured repeatedly or proven), OBSERVED ONCE
(single session or single method; may be real, not
yet programme-grade evidence), PROVEN (formal),
REJECTED (measured or derived against), UNTESTED.

### 1.1 Genuinely established

- The production path and its accounting
  (Task 003.9 definitions: requested, unique,
  backend, device, researched, verification hashes;
  candidate and overflow counters). The GPU engine
  produces zero device hashes on this machine
  (no device exists) and says so.
- The precomputation ceiling, 67 of 192 rounds,
  and the exact first-nonce-dependent schedule word
  (W18), re-derived independently in EXP-016.
- The Boolean cone results (MD-2): Ch and Maj at
  proven minima; ternlog immediates unique;
  alternative forms equivalent. Proven three ways.
- Compiler flags do not move the production path
  (EXP-001): the hot compression is libcrypto's,
  not ours. Measured across a full sweep.
- A single SHA-NI stream is latency-bound; streams
  multiply throughput until spill and issue costs
  stop them (EXP-003: 1.06M, 2.52M, 3.30M H/s at 1,
  2, 4 streams per worker, 1 thread). Reproduced
  across the batch's sessions.
- The schedule can be generated entirely by
  SHA256MSG1/MSG2 with zero scalar schedule words;
  the MSG schedule alone was worth about 2.6x at
  equal rounds against the scalar-schedule twin
  (EXP-002: 2T medians 1,966,395 versus 751,524),
  with a scalar-twin equivalence proof.
- Hand-scheduling the register allocation does not
  beat the compiler's (EXP-006); the schedule
  store and reload round trip costs what spills
  cost. Measured negative, assembly-audited.
- Phase pipelining at SHA-NI scale is parity
  (EXP-008); candidate construction costs about
  17.8 microseconds per transaction and search is
  99.958 percent of wall time (EXP-009); a real
  node answers validateaddress in about 3.96 ms
  median, which is why production confirms against
  its own template, not the node.
- The decision experiment has now failed its
  predeclared criterion three times (EXP-004,
  the batch rerun, EXP-010): no research kernel
  separates from production under the min/max rule
  at 2 threads on this VM. The decision is closed
  for this machine, and the pattern of failures is
  itself the audit's most important measurement
  finding (section 1.5).

### 1.2 Observed once only (not programme-grade yet)

- EXP-011 dual-batch MB: the highest 2-thread
  median the programme has recorded (8.27M H/s,
  session A) and cross-session ratios from 0.58x
  to 2.27x against the single-batch kernel in the
  same code. One session says breakthrough-adjacent;
  the set of sessions says unsettled. Additionally,
  session A's raw JSON was overwritten by session B
  before archiving; the 8.27M figure survives only
  as a transcription in the batch report. That is
  an evidence-preservation lapse this phase's Workstream F
  rules now prohibit (section 4).
- EXP-013 cross-lane prefix sharing: an effect
  below the VM noise floor in both sessions.
  Consistent with a small real effect and with no
  effect; undecidable with current methodology.
- EXP-007's AVX-512 variance anomaly (flat vector
  response while scalar rates rose with steal):
  EXP-010's covariate analysis weakened the steal
  explanation (rate vs steal correlation +0.221 for
  the vector kernel, -0.521 for the control) but did
  not replace it with a mechanism. The anomaly is
  observed; its cause is untested. Y-097 and Y-037
  aim at it.
- Every "calm window" median in the programme:
  medians from different sessions of the same
  kernel differ by up to about 2x, so any single
  session's median is an observation, not a
  constant of the machine.

### 1.3 Mathematically proven

- Boolean cone minima and ternlog uniqueness
  (EXP-012, proofs/boolean_cone_search.py).
- Boolean alternative-form equivalences
  (mathematical_foundations.md, three methods).
- EXP-016 (this phase): round-3 a and e are exactly
  C + nonce; the W18 delta is exactly sigma0(nonce);
  the W19 delta is exactly the nonce; the W20 delta
  is not XOR-linear (z3 counterexample, numerically
  verified). Full statement in
  MATHEMATICAL_DISCOVERIES.md (MD-1).
- The 67-round precomputation ceiling is a proof
  about the conventional evaluation's dependency
  structure (a word or round is reusable exactly
  when no input path reaches the nonce), and EXP-016
  re-derives its boundary from the schedule side.

### 1.4 Experimentally rejected (do not reopen without new evidence)

- Reduced-round and statistical shortcuts (R-01):
  bias measured dead by round 24; not exact.
- Lite screening, partial-state abort (R-02, R-06):
  confirmation is the full hash; nothing exact is
  saved.
- Compiler-flag tuning of the production wrapper
  (R-03, EXP-001).
- Thread counts beyond the cap (R-04).
- K+W folding as implemented (EXP-014): the fold
  relocates an addition into the latency-exposed
  slot it was meant to vacate.
- Bitslicing on this core (EXP-015): 0.11 to
  0.19M H/s, about 0.03x the MB kernel. The Boolean
  cone minima that make bitslicing attractive
  elsewhere are already captured by ternlog here.
- The combination run of EXP-013 plus EXP-014 was
  correctly never run: neither ingredient succeeded
  individually, and combining unproven transforms
  produces uninterpretable results.

### 1.5 The audit's sharpest findings

1. **The 125-round claim was overbroad.** Three
   documents stated or implied a proven universal
   lower bound on equivalent implementations. No
   such proof exists or was ever produced; the
   number is the conventional evaluation's
   remaining count. Corrected in place (Task 2A);
   the correction matters because the claim, left
   standing, would have defined Workstream A out of
   existence by definition rather than by evidence.
2. **The memory conclusion was overbroad in the
   same shape.** "Memory is not the constraint"
   rested on DRAM bandwidth alone, while the
   programme's own assembly audits show register,
   spill and stack costs deciding three separate
   experiments (EXP-005, EXP-006, EXP-011). Worse,
   MEMORY_AND_CACHE_RESEARCH.md contained its own
   reopening criterion (state traffic becoming the
   visible cost in a vector kernel's assembly
   record), and EXP-011 met it without anyone
   updating the conclusion. Corrected in place
   (Task 2C).
3. **The ceiling models were presented with more
   authority than their category allows.** Set A
   divides a static instruction count by an assumed
   IPC; set C assumes sustained vector issue rates
   on an unobservable host microarchitecture. The
   numbers are useful planning estimates; several
   passages read them as physical law ("the entire
   remaining software prize on one core").
   PERFORMANCE_CEILING.md now carries per-set
   category labels and a collected assumptions
   section (Task 2B).
4. **The programme's binding constraint is
   measurement, not ideas.** Three decision
   failures (EXP-004, batch rerun, EXP-010) share
   one shape: candidate medians clearly above
   production, separation destroyed by variance.
   The registry's own methodology entries (Y-101,
   Y-102, Y-103, Y-108) describe the fix and have
   never been run. Until they are, every kernel
   experiment in this programme is spending effort
   the decision procedure cannot bank. This is why
   the measurement stack is selected as EXP-017,
   ahead of more glamorous kernel work.
5. **One evidence-preservation lapse.** EXP-011
   session A's raw data was overwritten (section
   1.2). The batch report discloses it honestly,
   which is to the programme's credit, but the
   highest median ever recorded now rests on a
   transcription. Workstream F rule, effective this
   phase: raw artifacts are append-only, named by
   session, and archived before any rerun starts.
6. **EXP-010's variance attribution is the best
   current model and it is incomplete.** Steal
   does not explain the AVX-512 spread (207.7
   percent against production's 115.8 percent
   under identical conditions), and the report's
   own residual explanation (implementation
   behaviour under a saturated runnable queue) is
   a label, not a mechanism. Per-round statistics
   built on these distributions have repeatedly
   failed to decide; the fine-grained paired
   design (Y-102) exists precisely to replace
   per-round inference with within-block
   inference.

### 1.6 Experiments that deserve continuation

- EXP-011's direction (dual-batch MB), but only
  after the measurement stack exists, and in its
  registered form Y-023 (register-resident), which
  attacks the measured defect (memory-backed
  state) rather than repeating the measurement.
- EXP-002's MSG-schedule kernel as a component:
  its schedule is proven equivalent and its
  behaviour under interleaving is the subject of
  Y-038/Y-039 class questions; as a standalone
  kernel it is closed.
- EXP-007's multi-buffer kernel as the platform
  for Workstream D work (it is the fastest measured
  family); its variance is a methodology problem,
  not a kernel defect anyone has demonstrated.
- EXP-009's pipeline accounting, extended by
  Y-105 (confirmation repricing at MB rates) when
  a kernel decision next succeeds.

### 1.7 Directions with graph-changing potential

Ranked by whether success would change the
computation graph rather than its implementation:

1. **Automated discovery over the round cone**
   (Workstream C machinery, COMPUTATION_GRAPH_
   RESEARCH.md): equality saturation plus bounded
   superoptimisation over the T1 and T2 addition
   networks and the Boolean cones, with z3 proof
   per candidate. This is the only direction that
   searches graph space systematically instead of
   by intuition. Its first targets are the
   five-operand addition chains (where depth 3 is
   proven minimal and the remaining freedom is
   tree shape and operand order) and cross-round
   subexpression sharing.
2. **Carry-save and redundant representations of
   the schedule additions** (Y-001, Y-002): the
   schedule's additions are the one place the
   conventional graph performs carry propagation
   that a redundant representation could defer.
   EXP-016 sharpens this: it cannot help via nonce
   separation (dead), but per-distance carry-save
   inside the recurrence is untouched by that
   result.
3. **Full-round algebraic rewriting with proof**
   (Y-014, Y-015): whether the (T1, T2) pair over a
   whole round admits a cheaper equivalent network
   is unknown; the cone results (EXP-012) bound
   only the Boolean part in isolation, not the
   joint arithmetic-Boolean cone.
4. **Cross-nonce and cross-round sharing beyond
   the prefix** (Y-066 family): EXP-016 shows the
   state is fully nonlinearly mixed from round 8;
   any sharing would have to exploit structure
   other than dependence sparsity. Low plausibility,
   genuinely graph-changing if real.
5. **Hybrid SHA-NI plus AVX-512 execution**
   (Workstream D): does not change the graph, but
   changes which physical pipes execute it, and the
   EXP-007 anomaly hints the resource model is
   wrong somewhere. Included here because a wrong
   resource model misprices every graph candidate
   the discovery system produces.

## 2. Corrections applied by this assignment (Task 2)

- A (125 rounds): PERFORMANCE_CEILING.md sections
  2.1, 2.5, Q1, Q3, Q6, Q8 and its section 3;
  PERFORMANCE_ROADMAP.md section 2;
  MATHEMATICAL_DISCOVERY.md sections 5, 7.6, 8;
  header_and_midstate_analysis.md Information
  Ceiling; FINAL_RESEARCH_REPORT.md proven table;
  EXP011_ONWARD_REPORT.md correction note
  (appended; historical text preserved).
- B (ceiling categories): PERFORMANCE_CEILING.md
  carries a six-category key (measured performance,
  static instruction counts, estimated dynamic
  counts, theoretical models, architecture-specific
  bounds, unproven assumptions), per-set labels,
  and a new section 2.6 collecting every unproven
  assumption. Numbers unchanged; authority
  relabelled.
- C (memory): PERFORMANCE_CEILING.md section 1.2;
  MEMORY_AND_CACHE_RESEARCH.md head note, section
  3.1, section 5; MASTER_RESEARCH_PLAN.md
  Workstream C; FINAL_RESEARCH_REPORT.md table.
- D (nonce dependency): derived in EXP-016;
  MATHEMATICAL_DISCOVERIES.md MD-1; verdicts
  recorded on Y-065 and Y-075 in the registry and
  in REJECTED_APPROACHES.md.

## 3. The first five Phase 6 experiments (Task 5)

Selected by expected research value: what the
programme knows afterwards that it does not know
now, weighted by how many later decisions the
knowledge unlocks. Ease was explicitly not the
criterion; EXP-018 and EXP-020 are among the
hardest items in the registry.

### EXP-016 (executed in this assignment): nonce dependency derivation

The foundation under Y-065, Y-075, Y-066, Y-090 and
every nonce-separation idea. Result: both target
hypotheses refuted as work reductions with proof
grade evidence; exact dependence rounds established
(nonlinearity complete at state S_8, full sound
masks at S_9, schedule delta dead from W20).
Record: EXPERIMENT_RESULTS.md; mathematics:
MATHEMATICAL_DISCOVERIES.md MD-1.

### EXP-017: the measurement stack (Y-101 + Y-102 + Y-103)

One experiment, three sub-verdicts: a
steal-normalised decision statistic validated
against injected load (Y-101); fine-grained paired
interleaving at 100k-hash blocks (Y-102); and the
equal-pair control, the identical kernel under two
names, which must return a decision-grade null and
certifies the harness itself (Y-103). Research
value: every subsequent kernel claim in the
programme becomes decidable or honestly
undecidable. Without it, EXP-018 and EXP-020
cannot conclude. Design: pinned manifest per
Y-108 from the first run.

### EXP-018: register-resident dual-batch MB (Y-023)

EXP-011's dual-batch shape rebuilt so state never
leaves registers across a full unrolled dual body:
32 zmm hold 16 states, schedule staged in the
remaining register budget, spill count as the
primary reported metric (target: zero state spills,
against EXP-011's 48 vmovdqa64). Decided under
EXP-017's statistic. Research value: it tests the
programme's best median and its best-measured
defect simultaneously; either outcome (the rate is
real and becomes decidable, or register pressure
provably forbids the shape) restructures Workstream
D.

### EXP-019: carry-save schedule generation, priced per distance (Y-002 then Y-001)

Y-002 first: keep one carry-save level across four
named schedule distances, measure the saving per
distance, so the representation's price list exists
before anyone builds the full engine (Y-001).
Research value: the schedule recurrence is the
only component whose conventional form performs
carry propagation that a redundant representation
could defer, and EXP-016 leaves this direction
untouched (it killed nonce separation, not
representation). A per-distance price list is a
permanent asset for the discovery system, which
needs exactly such costs to rank its candidates.

### EXP-020: automated full-round rewriting (Y-014 + Y-015)

The discovery system of COMPUTATION_GRAPH_RESEARCH
.md turned on the full round: equality saturation
over the joint Boolean and arithmetic cone,
SAT/SMT-guided rewriting under the lab's rewrite
set, bounded superoptimisation of the T1 and T2
addition networks, z3 UNSAT proof per survivor,
assembly audit per compiled candidate. Research
value: highest in the programme. It converts
Workstream A from a list of intuitions into a
search with a proof gate, and its negative results
(if the round is already optimal in the searched
space) are themselves theorems worth having.
Promotion rule: a candidate that is proven,
compiles, and wins under EXP-017's statistic
becomes a kernel experiment with its own EXP
number; nothing promotes on saturation output
alone.

### Deferred, with reasons

Y-047 (bounded superoptimiser for one SHA-NI round
pair) is subsumed by EXP-020's machinery at vector
width; it returns if EXP-020's search space proves
too large at 16 lanes. Y-056 and Y-025 (schedule
generation distance in MB) wait for EXP-019's price
list, which is their input. Y-093 (GPU re-audit) is
environmental: it executes itself the day a device
appears and is meaningless before. Y-048 and Y-049
(multi-buffer arithmetic variants) are candidates
for the discovery system's seed set rather than
standalone experiments.

## 4. Workstream map for this phase

- A (computation graphs): MD-1 closures; EXP-019,
  EXP-020; OPEN_PROBLEMS.md OP-1 to OP-4.
- B (revisited hypotheses): all fifteen named
  entries carry an unresolved question and a
  designed experiment in HYPOTHESIS_RANKING.md.
- C (automated discovery): COMPUTATION_GRAPH_
  RESEARCH.md; first component built
  (src/discovery_harness.py, candidates P6C-001 to
  P6C-004, all proof-gated).
- D (extreme CPU execution): CPU_EXECUTION_
  RESEARCH.md; EXP-018.
- E (target model): PERFORMANCE_TARGET_MODEL.md.
- F (benchmark discipline): EXP-017; append-only
  raw artifacts; pinned manifests (Y-108 adopted
  as standing rule from this phase).
- G (exact mining correctness): unchanged
  production accounting; every Phase 6 kernel
  candidate inherits the rule that correctness
  evidence precedes benchmarks, and confirmation
  remains the full hash against a real node or the
  production template path.

## 5. What this assignment did not do

No production code changed. EXP-010 was not rerun.
No kernel was integrated. The five-experiment list
contains one executed experiment (EXP-016) and
four designed ones; their scaffolding records are
in EXPERIMENT_RESULTS.md, marked NOT RUN, because
a designed experiment reported as anything else
would violate this programme's evidence rules.
