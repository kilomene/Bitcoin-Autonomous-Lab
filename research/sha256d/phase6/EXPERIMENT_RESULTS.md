# Phase 6, Experiment Results

Records follow the programme's mandate format:
hypothesis, mathematical basis, predicted effect,
implementation, correctness evidence, benchmark
methodology (where applicable), raw results,
statistical assessment, decision, follow-up.
Experiments not yet run are recorded as NOT RUN
with their design; a design is not a result.

## EXP-016: Nonce dependency derivation for block 2 (Task 2D)

- **Hypothesis.** The dependence of block 2's
  schedule and state on the nonce word W3 has an
  exact structure that either supports a
  nonce-separation work reduction (the premise of
  Y-065 and Y-075) or refutes it; the lab's
  precomputation ceiling (67 rounds) implies the
  boundary but has never been derived word by word.
- **Mathematical basis.** SHA-256 schedule
  recurrence and round function, analysed three
  ways: sound per-bit influence masks with a carry
  bound for modular addition; sampled functional
  classification (IND, AFF, LIN, NONLIN) plus delta
  linearity tests; z3 bit-vector proofs for the
  boundary cases. Full derivation:
  MATHEMATICAL_DISCOVERIES.md, MD-1.
- **Predicted effect.** If a separation existed
  past the first expanded words, Y-065 or Y-075
  would yield a graph with a shared nonce-free
  component and a cheap per-nonce component. The
  prediction registered before running (from the
  recurrence's shape): separation survives at most
  through W19 and dies at the first schedule word
  whose inputs mix an already nonce-dependent word
  through an addition and a sigma.
- **Implementation.** src/nonce_dependency.py
  (pure-Python reference SHA-256, influence masks,
  classification, delta tests, z3 via the
  repo-local solver environment). Runtime about
  16 s of CPU on this VM.
- **Correctness evidence.** The reference
  implementation matches hashlib bit-exactly on
  random messages and on the header, inner and
  outer shapes of the production miner (leg 1,
  both checks true). The z3 W20 counterexample was
  re-verified numerically inside the reference
  implementation, so the refutation does not rest
  on solver trust alone.
- **Benchmark methodology.** Not applicable: this
  is a derivation, not a kernel. Its outputs are
  mathematical claims with proof and sampling
  artifacts.
- **Raw results.** analysis/exp016_dependency_
  results.json; proofs/exp016_z3_results.json.
  Headline values: W16, W17 independent. W18 delta
  exactly sigma0(nonce), XOR-linear (violation rate
  0.0 over 300 pairs; z3 UNSAT). W19 delta exactly
  the nonce (violation rate 0.0; z3 UNSAT).
  W20 to W25 delta violation rate 1.0; W20 z3
  counterexample numerically verified (template
  recorded in the artifact; D(n1 xor n2) =
  43171369 versus D(n1) xor D(n2) = 3724592575).
  Round-3 (S_4 in the document's indexing, the
  state after the round consuming W3): a and e
  exactly C + nonce (z3 UNSAT for both). Sampled
  state classes: S_5 a, e NONLIN with b, f AFF;
  S_6 c, g AFF; S_7 d, h AFF; S_8 all eight NONLIN.
  Sound masks: a and e fully dependent (32 of 32
  bits) at S_6; all eight words at S_9. Empirical
  sensitivity complete at S_7. S_4 flip signature
  for a and e: diagonal mean 1.0, below-diagonal
  max 0.0, above-diagonal mean 0.066 (the integer
  addition carry signature).
- **Statistical assessment.** The sampled legs are
  not the evidence of record for the closures; the
  z3 results are (UNSAT for the positive forms, a
  verified counterexample for the negative). The
  sampling is reported because the mandate requires
  the derivation to be consistent with differential
  experiments: violation rates of exactly 0.0 and
  exactly 1.0 across 300 random pairs per word, and
  three independent templates agreeing on every
  classification, are consistent with the proofs.
  The sound-mask leg is one-sided by construction
  (over-approximation) and is used only for
  completeness rounds, never for independence
  claims in the direction that matters (independence
  is certified by template-only inputs, not by
  masks).
- **Decision.** Y-065 REFUTED as a work reduction;
  Y-075 REFUTED as a work reduction. Both closures
  recorded in the Y registry and in
  REJECTED_APPROACHES.md. The derivation itself is
  adopted as the programme's reference for nonce
  dependency (MD-1). Tier: ESTABLISHED.
- **Follow-up.** Y-066 and Y-090 lose their
  premise (Y-090's dependency readiness was set to
  1 in the ranking for this reason). Workstream A
  proceeds to directions EXP-016 does not address:
  EXP-019 (representation, not separation) and
  EXP-020 (whole-cone rewriting).

## EXP-017: The measurement stack (Y-101, Y-102, Y-103)

Status: COMPLETE (2026-11-14). Results are
recorded in the Results subsection below, from
the raw session artifacts in benchmarks/exp017/.
Designed in
PHASE6_RESEARCH_PLAN.md section 3. Sub-verdicts:
(a) Y-101, whether the predeclared steal and
runnable-load adjusted paired statistic gives
stable, decision-grade verdicts and whether its
covariates earn their place against the same
statistic without adjustment; (b) Y-102, whether
fine-grained paired interleaving at 65,536 hashes
per block supports those verdicts; (c) Y-103,
whether the equal-pair controls return nulls
under the full procedure and how the prior
min/max separation rule behaves on identical
arms. Raw artifacts land in benchmarks/exp017/
under append-only session names with Y-108
manifests.

### Predeclared statistic and decision rule (Y-101)

This definition was written before the EXP-017
validation comparisons were run. A comparison
names a reference arm A and a candidate arm B.
Each paired observation consists of one
65,536-hash counted batch by A and one by B, in
randomised AB or BA order, over the same nonce
range, with 2 worker threads. For pair i, let
tA and tB be the counted-call elapsed times.
The paired log-ratio is

  y_i = log(rate_B / rate_A) = log(tA / tB).

Immediately around each arm's call, the driver
samples aggregate /proc/stat and /proc/loadavg.
For that arm, the steal fraction f is the steal
jiffy delta divided by the total CPU jiffy delta
over the call interval, and runnable load l is
the mean of the endpoint counts of currently
runnable tasks. The pair covariates are
ds_i = fB - fA and dl_i = lB - lA, standardised
within the fitted data set, plus an order
covariate o_i equal to +0.5 when B runs first
and -0.5 when A runs first. The adjusted model
is the ordinary least squares fit

  y_i = alpha + beta_s ds_i + beta_l dl_i
        + beta_o o_i + error_i,

with a session fixed effect added for pooled
fits. The decision quantity is alpha, the
adjusted mean paired log-ratio at equal arm
covariates and balanced order. Its interval is
a 95 percent percentile bootstrap interval from
10,000 nonparametric resamples of pairs,
stratified by session for pooled fits, with
the model refitted on every resample. The same
bootstrap machinery, applied to the unmodelled
mean of y_i, gives the unadjusted statistic for
comparison. The fraction of pairs won by B is
the fraction with y_i > 0.

Predeclared decision rule fed by this statistic:
B is significantly faster than A in a session,
or pooled across sessions, exactly when the
adjusted 95 percent interval for alpha lies
entirely above 0. An equal-pair control passes
exactly when its adjusted interval contains 0
in every session and pooled. This rule is an
EXP-017 measurement rule only. It does not
replace the programme's integration criterion,
which remains the owner's to change.

The historical min/max rule is reconstructed
for the control audit by aggregating 16
consecutive blocks per arm into approximately
1M-hash pseudo-rounds and asking whether the
candidate-labelled arm's minimum pseudo-round
rate exceeds the reference-labelled arm's
maximum. That reconstruction is reported on
identical arms only, as a price on the old
rule, and is not used for EXP-017 verdicts.

### Results (2026-11-14)

- **Hypothesis.** A fine-grained paired design
  with a predeclared covariate-adjusted statistic
  can return stable verdicts on this VM where
  three whole-round min/max decisions failed.
- **Implementation.** benchmarks/
  exp017_paired_bench.py (driver) and
  exp017_analyze.py (statistic). No kernel and
  no production code changed. Kernels were
  rebuilt from unchanged sources for the geo and
  AVX-512 arms (source hashes in every session
  manifest, identical across all 12 sessions);
  the rebuilt geo s=4 strided and AVX-512 builds
  passed the full gate set in the run-up
  (108,000 randomized differentials each), and
  the production library was verified on 100,000
  digests against hashlib. The driver asserts
  attempted and backend equal the block size on
  every timed call; every session's coverage
  assertion holds exactly (10,485,760 hashes per
  arm per session).
- **Benchmark methodology.** Four comparisons,
  three independent sessions each, sessions
  rotated across comparisons: control_production
  (production vs itself), control_avx512_mb (MB
  vs itself), production_vs_avx512_mb,
  production_vs_geo_s4_strided. Each session:
  160 recorded pairs of 65,536-hash blocks at 2
  worker threads after 8 warmup pairs, randomised
  AB or BA order, per-call steal and runnable
  covariates. Session conditions: 1-minute load
  between 15.35 and 1.92 across the batch (load
  fell as the batch proceeded), node in IBD
  throughout, heights 410,864 to 410,947 of
  975,807 headers (node_state_supplement.json;
  several direct RPC readings timed out under
  benchmark load and were reconstructed from the
  node's debug.log UpdateTip entries, method
  stated in the supplement). Raw data:
  benchmarks/exp017/session_*.json (12 files,
  append-only); analysis:
  benchmarks/exp017/analysis_20261114T145128Z
  .json (10,000 bootstrap resamples).
- **Correctness evidence.** Gate results above,
  plus exact per-call accounting assertions in
  every session (no dummy coverage anywhere;
  the 65,536 block is a whole number of 16-lane
  MB groups).
- **Raw results, controls (Y-103).** Adjusted
  pooled log-ratios: production control +0.0137
  (95 percent CI -0.0786 to +0.1081, ratio
  1.014x, CI 0.924x to 1.114x); AVX-512 MB
  control +0.0077 (CI -0.1047 to +0.1167, ratio
  1.008x, CI 0.901x to 1.124x). Every one of the
  six control sessions individually contains 0
  as well. Fraction of pairs won by the
  candidate-labelled arm: 0.506 and 0.488.
  Historical min/max rule on identical arms:
  0 of 6 control sessions passed a phantom
  difference (candidate minimum pseudo-round
  rate below the reference maximum in all six,
  by wide margins). The old rule's measured
  failure mode on this data is false negatives,
  not false positives: it is a very conservative
  separation test, priced here on identical arms
  for the first time.
- **Raw results, real comparisons.** AVX-512 MB
  vs production, adjusted log-ratios per
  session: +1.2883 (CI 1.1021 to 1.4686),
  +1.3106 (CI 1.1118 to 1.5107), +1.1792 (CI
  0.9809 to 1.3806); pooled +1.2652 (CI 1.1546
  to 1.3767), ratio 3.55x (CI 3.17x to 3.97x),
  pairs won 0.815. Streams=4 strided vs
  production: +0.7918 (CI 0.6054 to 0.9695),
  +1.2385 (CI 1.0651 to 1.4052), +1.0678 (CI
  0.8967 to 1.2350); pooled +1.0298 (CI 0.9265
  to 1.1283), ratio 2.80x (CI 2.53x to 3.09x),
  pairs won 0.798. Under the predeclared
  EXP-017 rule, both candidates are
  significantly faster than production in every
  session and pooled. This is a measurement
  result under the stated conditions (live
  miner, syncing node, saturated runnable
  queue). It is NOT an integration: the
  programme's integration criterion is unchanged
  and remains the owner's to change.
- **Statistical assessment.** Variance
  decomposition of the paired log-ratio
  (within-session / between-session): MB
  control 1.591 / 0.000; production control
  1.118 / 0.000; MB vs production 1.610 /
  0.000; geo vs production 1.293 / 0.0434 (the
  only comparison with a real between-session
  component: its session means genuinely move,
  +0.787, +1.236, +1.068). Single block pairs
  are individually very noisy (a descheduled
  arm produces log-ratios of several units);
  the design works because 160 pairs average
  that noise within a session. Sessions needed
  for a 95 percent CI halfwidth of 0.10 log
  units at 160 pairs per session: 3 to 4 for
  the production and MB comparisons, 20 for
  the geo comparison (driven by its
  between-session component); for 0.05: 11 to
  16, and 80 respectively. At the effect sizes
  actually observed (1.03 to 1.27), three
  sessions are more than sufficient, as the
  intervals show.
- **Covariate adjustment, priced (Y-101).**
  The adjustment barely moves anything on this
  data: pooled point shifts versus the
  unadjusted statistic are at most 0.0004 log
  units in all four comparisons, and pooled CI
  width ratios (adjusted over unadjusted) are
  0.992 (production control), 0.993 (MB
  control), 0.970 (MB vs production), 0.999
  (geo vs production). The pairing itself, not
  the steal and load covariates, carries the
  decision value at 65,536-hash granularity,
  because adjacent arms sample nearly the same
  environment and the differences the covariates
  would explain are already small. The
  semi-synthetic injected-effect check passed:
  a known pooled effect of +0.20 added to
  residual-resampled control data was recovered
  with mean bias +0.00005 (MB control design)
  and -0.0006 (production control design) over
  1,000 simulations, the injected value inside
  the empirical recovery range both times. So
  the estimator is arithmetically sound; its
  covariates are, on this evidence, decoration.
- **Sub-verdicts.** Y-103 PASS: both equal-pair
  controls return decision-grade nulls in all
  sessions and pooled, and the old rule's
  phantom-pass rate on identical arms is 0 of
  6. Y-102 PASS at 65,536 hashes: fine-grained
  paired interleaving produced the same verdict
  in every session of every comparison, the
  stability three whole-round decisions never
  achieved. (No claim is made about other block
  sizes; 65,536 is the validated size.) Y-101
  PARTIAL: the statistic validates as an
  estimator and as a decision rule, but its
  named mechanism, steal and load adjustment,
  is measured near-neutral here; the validated
  instrument is the paired log-ratio with
  bootstrap, with adjustment retained as a
  harmless predeclared option.
- **Decision.** The measurement stack is
  adopted for Phase 6 experiment records from
  EXP-018 onward. No kernel decision is taken
  under it in this experiment.
- **Proposal to the owner (not applied).**
  Replace the integration decision rule
  (candidate minimum above production maximum
  in one session) with: a candidate is
  decision-grade faster when, under the
  EXP-017 protocol (65,536-hash paired blocks,
  at least 3 independent sessions, 2 worker
  threads), its adjusted 95 percent interval
  lies entirely above 0 in every session and
  pooled, with the full correctness gate set
  and a fresh regtest block still required
  before integration. On the EXP-017 data,
  both current candidates would pass that rule.
  The rule change is the owner's decision; this
  record proposes and does not enact it.
- **Follow-up.** EXP-018 (Y-023) is the first
  experiment decided under this statistic.
  Future sessions should keep the covariate
  recording (it costs nothing and a different
  environment may price it differently) and
  should treat the geo comparison's
  between-session component as a property to
  re-measure, not assume away.

## EXP-018: Register-resident dual-batch MB (Y-023)

Status: RUN 2026-11-14. Verdict: register
residency achieved at the near-zero level (one of
sixteen state vectors homed in a single stack
slot, the other fifteen with no stack traffic at
all), but the paired statistic does not show a
significant gain over single-batch MB in any
session or pooled, so under the predeclared
definitions Y-023 is NOT a verified improvement.
The finding is the second predeclared branch:
state traffic was not the binding cost. Tier:
PROMISING HYPOTHESIS with measured support.

- **Hypothesis.** EXP-011's dual-batch kernel
  produced the programme's highest single-session
  2-thread median (8.27M H/s) but never reproduced
  it, and its audit showed the dual body carrying
  48 vmovdqa64 with state handled through arrays.
  Y-023 asks whether a restructured dual-batch
  kernel that holds both batches' state sets in
  zmm registers across the round body removes
  enough of that traffic to produce a
  reproducible gain over single-batch MB.
- **Mathematical basis.** The SHA-256 round's
  state rotation is a relabelling: after a round,
  the new state is (T1+T2, a, b, c, d+T1, e, f,
  g). Writing the new A into the physical vector
  that held h and the new E into the physical
  vector that held d, then rotating the argument
  tuple at compile time, implements the rotation
  with no data movement at all. After eight
  rounds the physical orientation repeats, so an
  eight-round unit can loop eight times with the
  state in the same sixteen named vector
  variables throughout. Exact by construction;
  the gates decide equivalence.
- **Predicted effect.** State rename moves and
  state stack traffic fall to zero or near-zero
  in the hot loop; if EXP-011's irreproducibility
  was state-traffic driven, the dual-batch rate
  becomes reproducibly above single-batch MB
  under the EXP-017 statistic.
- **Implementation.** New source
  extreme_optimization/src/avx512_mb_reg.c
  (exports bal_r_batch2 and bal_r_search2,
  library libbal_r512.so), derived from the
  EXP-011 walker and group code, which are not
  modified; avx512_mb.c and avx512_mb2.c are
  untouched and production is byte-identical.
  The dual compress v_compress16x2_reg keeps
  both batches' states in sixteen named __m512i
  variables, generates both schedule rings just
  in time in stack arrays (16 state vectors plus
  two full rings cannot fit the 32-register
  file; residency is claimed for state, not for
  the rings), uses the EXP-012 VPTERNLOGD cones
  (XOR3 0x96, Ch 0xCA, Maj 0xE8), and advances
  both batches through an eight-round ring
  unit repeated eight times. Two structures
  were compiled and audited: a full 64-round
  unroll came out at 3,872 instructions with a
  3,776-byte frame and 214 zmm stack accesses in
  its low spill region (the compiler's long
  live ranges defeated residency), and was
  superseded by the eight-round repeating unit
  recorded below; the full-unroll numbers are
  kept here as the documented first attempt.
- **Assembly audit (primary metric).**
  benchmarks/exp018/asm_audit.json, produced by
  benchmarks/exp018_asm_audit.py from objdump;
  stack regions are taken from each function's
  own prologue memcpy destinations. EXP-018
  dual body v_compress16x2_reg: 1,014 static
  instructions (the eight-round unit, executed
  eight times per compression), frame 2,368
  bytes; vmovdqa64 99 total, of which 21 are
  stack-relative and all 21 fall inside the two
  schedule ring regions; zmm stack-operand
  instructions 90, of which 80 are schedule
  ring accesses (40 per ring) and 10 are in the
  spill area below the first ring, at offsets
  0x0 (2), 0x80 (5) and 0xc0 (3). Of those 10,
  only the 0xc0 slot carries state: exactly one
  of the sixteen state vectors is homed there
  (one store, one fused reload, one store in
  the loop body); the other fifteen state
  vectors have no stack traffic. State spill
  count: 1 vector, 1 slot, near-zero as
  predeclared. EXP-011 dual body
  v_compress16x2, rebuilt from unchanged source
  for this audit: 212 static instructions (the
  EXP-011 report recorded 239 under its own
  count), frame 2,112 bytes, vmovdqa64 48 (16
  entry loads, 16 exit stores, 16 register
  renames executed per loop iteration), zero
  stack-relative vmovdqa64; its schedule rings
  are stack arrays addressed through base
  pointers. Single-batch v_compress16: 111
  instructions, frame 1,088 bytes, vmovdqa64
  24, zero stack-relative. So the restructure
  removes the per-iteration rename moves and
  holds state resident, at the price of a
  larger static body; it does not remove the
  schedule ring traffic, which is comparable
  in all three bodies.
- **Correctness evidence.** Full gate set in
  extreme_optimization/tests/test_exp018.py,
  all passing before any benchmark: 108,000
  randomized SHA-256d differentials vs hashlib
  (bad 0); genesis digest and genesis search
  (nonce 2083236893); boundary nonces and odd
  counts; crossing range returns -2, empty
  range -1; template variations (version,
  prevhash, merkle root, timestamp, nBits);
  target exact equality accepted, target minus
  one rejected; regtest-easy candidate set
  equal to the Python recount (82 candidates
  in 20,000); exact accounting: batch attempted
  equals count, search miss attempted 5,000,
  genesis early exit attempted exactly 50,016
  (32-group atomic), partial group at count
  100,003 backend 100,016, sub-group at count
  5 backend 16, group-edge batch at 0xFFFFFFF0
  matching hashlib for all 16 nonces straddling
  2^32.
- **Benchmark methodology.** EXP-017 protocol
  only, via benchmarks/exp018_paired_bench.py
  and exp018_analyze.py (copies of the EXP-017
  tools with the EXP-018 arms). Paired 65,536
  hash blocks, randomised AB or BA order, 160
  recorded pairs per session after 8 warmup
  pairs, 2 worker threads, per-call steal and
  runnable-load covariates, adjusted paired
  log-ratio with OLS adjustment and a 10,000
  resample pairs bootstrap. Three independent
  sessions per real comparison plus one
  equal-pair control session (reg vs itself).
  Node in IBD throughout: session files record
  heights 411,173 to 411,194 of 975,810
  headers where the RPC answered; four of the
  seven session-start RPC reads returned
  unavailable under benchmark load and are
  recorded as such in the session files. Raw
  data: benchmarks/exp018/session_*.json (7
  files, append-only); analysis:
  benchmarks/exp018/analysis_20261114T151341Z
  .json.
- **Raw results, primary comparison (reg vs
  single-batch MB).** Adjusted log-ratios per
  session: +0.1536 (CI -0.0382 to +0.3540),
  +0.0330 (CI -0.1499 to +0.2185), +0.0521 (CI
  -0.1367 to +0.2336); pooled +0.0836 (CI
  -0.0247 to +0.1902), ratio 1.087x (CI 0.976x
  to 1.210x), pairs won 0.554. Session median
  rates: MB 5.39M, 5.69M, 5.64M H/s; reg 6.85M,
  6.45M, 6.37M H/s. The point estimate is
  positive in all three sessions, but every
  interval contains 0, so the comparison is
  not significant in any session or pooled.
- **Raw results, context comparison (reg vs
  production).** Adjusted log-ratios per
  session: +1.5629 (CI 1.3956 to 1.7307),
  +1.4893 (CI 1.3030 to 1.6699), +1.4630 (CI
  1.2811 to 1.6352); pooled +1.5027 (CI 1.4010
  to 1.6011), ratio 4.49x (CI 4.06x to 4.96x),
  pairs won 0.881: significant in every
  session and pooled, as expected for any
  member of the AVX-512 MB family against
  production under this rule.
- **Raw results, control.** Reg vs itself, one
  session: adjusted -0.0945 (CI -0.2770 to
  +0.0884), pairs won 0.512, a null as required;
  the historical min/max rule passed a phantom
  difference in 0 of 1 control sessions; the
  injected +0.20 effect was recovered with
  mean bias +0.0002 over 1,000 simulations.
- **Statistical assessment.** Within-session
  variance of the paired log-ratio: 1.495
  (primary), 1.279 (context), 1.442 (control);
  between-session component 0.000 in all three.
  Covariate adjustment priced near-neutral
  again: pooled CI width ratios (adjusted over
  unadjusted) 0.979 (primary), 0.990 (context),
  0.965 (control). The primary comparison's
  pooled interval halfwidth is about 0.107 log
  units, so an effect of the observed size
  (0.084) sits just inside the noise this
  design can resolve at three sessions; the
  variance decomposition estimates roughly 5
  sessions at 160 pairs would be needed for a
  0.10 halfwidth on this comparison, and the
  honest statement is that the data show a
  small positive point estimate that this
  experiment cannot separate from zero.
- **Decision.** Y-023 is not a verified
  improvement under its predeclared
  definitions: residency (the mechanical half)
  is achieved, significance (the rate half) is
  not. The recorded finding is that state
  traffic was not the binding cost in the
  dual-batch shape on this machine; the
  remaining schedule ring traffic and the
  round dependency chains are the costs that
  stay. No integration, production unchanged.
- **Follow-up.** The register-resident dual
  body is retained as a gated, benchmarked
  variant in the tree. If Y-024 (triple-batch)
  or a schedule-residency design is run, this
  record's audit method (regions from the
  prologue, spill slots listed by offset) is
  the template. A larger session count for the
  primary comparison is a possible revisit,
  but no further EXP-018 sessions were run:
  three sessions per comparison is the
  predeclared design, and adding sessions
  after seeing the intervals would change the
  design mid-experiment.

## EXP-019: Carry-save schedule pricing, then engine (Y-002, Y-001)

Status: COMPLETE (2026-11-14). The price list
was built and measured first, as designed; no
carry-save form passed the predeclared gate
(measured micro-cost win AND dependency-chain
win), so no kernel was built and Y-001's engine
was not attempted. Raw artifacts:
analysis/exp019_price_list.json, benchmarks/
exp019/ (three append-only sessions plus the
L1-resident supplement). Designed in
HYPOTHESIS_RANKING.md (Y-001, Y-002 entries).
The list feeds the discovery system's cost
model (COMPUTATION_GRAPH_RESEARCH.md
section 4), including one correction to that
model's inherited costing, recorded below.

### The question

For one expanded schedule word, the recurrence
W[t] = sigma1(W[t-2]) + W[t-7] + sigma0(W[t-15])
+ W[t-16] is a four-operand modular addition.
Operand roles: a = W[t-16], b = sigma0(W[t-15]),
c = W[t-7], d = sigma1(W[t-2]). Y-002 asks
whether one carry-save level prices below the
add tree the production compiler emits, per
consumption distance. Y-001 asks the same at
the whole-schedule level, with resolution
forced where a round or a sigma consumes the
word.

### Static price list (instruction counts and chains)

Counts are vector instructions per expanded
word for the addition network only (sigma
generation is common to all forms). A chain is
the longest dependency path in unit-latency
instruction stages. A software 3:2 compressor
on this instruction set costs THREE
instructions, not two: VPTERNLOGD for the
parity output, VPTERNLOGD for the majority
output, and VPSLLD to align the carry vector
to the bit positions it carries into. The
registry's Y-002 costing ("one carry-save
level, two ternlog ops") undercounts by the
shift; the emitted loops below confirm the
shift is present. Production and resolution
costs are separated, per the design.

| Form | Production ops | Resolution ops | Total ops | Production chain | Resolution chain | Total chain |
|---|---|---|---|---|---|---|
| current_serial (incumbent, as emitted) | 3 VPADDD | 0 | 3 | 3 | 0 | 3 |
| balanced_tree (control, Y-003 territory) | 3 VPADDD | 0 | 3 | 2 | 0 | 2 |
| cs1_resolved | 3 (2 VPTERNLOGD + 1 VPSLLD) | 2 VPADDD | 5 | 2 | 2 | 4 |
| csfull_resolved | 6 (4 VPTERNLOGD + 2 VPSLLD) | 1 VPADDD | 7 | 4 | 1 | 5 |
| sigma_led_cs1 | 3 (2 VPTERNLOGD + 1 VPSLLD) | 2 VPADDD | 5 | 2 | 2 | 4 |
| cs1 deferred (three-vector output) | 3 | 2 VPADDD | 5 | 2 | 2 | 4 |
| csfull deferred (pair output) | 6 | 1 VPADDD | 7 | 4 | 1 | 5 |

Assembly audit of the microbenchmark runner
loops (objdump, per iteration): current_serial
3 VPADDD; balanced_tree 3 VPADDD; cs1_resolved
2 VPTERNLOGD + 1 VPSLLD + 2 VPADDD;
csfull_resolved 4 VPTERNLOGD + 2 VPSLLD +
1 VPADDD; sigma_led_cs1 as cs1. The intended
forms survived compilation exactly. The
production kernel's own hot loop was also
re-audited: its schedule sum is emitted as
three serially dependent VPADDD (the source
expression is balanced, the emitted chain is
serial), so current_serial is the honest
incumbent, not a strawman.

Deferral changes nothing in the totals: the
deferred rows are the resolved rows with the
resolution adds moved later. And deferral has
a hard bound in this recurrence. In the fused
kernel, T1 consumes W[t] in the round that
generates it (separation 0). In any
schedule-ahead variant, sigma1 consumes W[t]
as an input to W[t+2] (separation 1), and a
sigma cannot consume a redundant pair: the
sigmas are bitwise operations on the true
word, and the bits of a sum are not a bitwise
function of a redundant pair's bits. Every
expanded word is therefore resolved at
separation 0 or 1, exactly where the measured
price of carry-save is worst.

### Measured price list

Method: src/exp019_price_micro.c (paired
microbenchmark; each repeat runs all five
forms once in randomized order over identical
data and identical chain state, forms verified
against scalar addition on 1,600,000 random
lanes, zero mismatches, and cross-checked by
per-block checksum agreement). A separation s
means s independent vector sums issue between
a word's production and its next dependent
use; the recurrence's actual separations are
0 (T1), 1 (sigma1 at t+2), 6 (direct at t+7),
14 (sigma0 at t+15) and 15 (direct at t+16).
Three sessions, 21 repeats per separation,
8,192 vector sums per block, 63 paired repeats
per point. Operand streams b, c, d are
L2-resident in the main list. Ratios are
candidate / current_serial ns per vector op
(mean log ratio, 95 percent bootstrap CI);
below 1 is faster than the incumbent.

Medians (ns per vector op), main list:

| Sep | Use | current | balanced | cs1 | csfull | sigma-led |
|---|---|---|---|---|---|---|
| 0 | T1 | 7.825 | 7.778 | 9.907 | 11.020 | 10.364 |
| 1 | sigma1 t+2 | 3.919 | 3.917 | 4.938 | 5.475 | 5.156 |
| 2 | | 2.620 | 2.619 | 3.328 | 3.748 | 3.503 |
| 3 | | 1.971 | 1.970 | 2.659 | 2.851 | 2.677 |
| 4 | | 2.039 | 1.963 | 2.392 | 2.545 | 2.454 |
| 5 | | 2.038 | 2.017 | 2.166 | 2.279 | 2.203 |
| 6 | direct t+7 | 2.029 | 2.028 | 2.060 | 2.133 | 2.077 |
| 7 | | 2.014 | 1.946 | 1.972 | 2.037 | 1.985 |
| 8 | | 2.029 | 2.011 | 1.922 | 1.969 | 1.932 |
| 9 | | 2.027 | 2.015 | 1.866 | 1.915 | 1.862 |
| 10 | | 2.027 | 2.021 | 1.760 | 1.868 | 1.730 |
| 11 | | 2.038 | 2.036 | 1.737 | 1.819 | 1.710 |
| 12 | | 2.041 | 2.038 | 1.727 | 1.788 | 1.708 |
| 13 | | 2.051 | 2.047 | 1.763 | 1.795 | 1.718 |
| 14 | sigma0 t+15 | 2.059 | 2.055 | 1.765 | 1.790 | 1.714 |
| 15 | direct t+16 | 2.071 | 2.044 | 1.752 | 1.784 | 1.718 |

Ratios at the recurrence's actual separations,
main list: separation 0: cs1 1.270 (CI 1.101
to 1.516), csfull 1.465 (1.242 to 1.787),
sigma-led 1.526 (1.228 to 1.980). Separation
1: cs1 1.168 (1.019 to 1.305), csfull 1.261
(1.106 to 1.390), sigma-led 1.233 (1.066 to
1.448). Separation 6: cs1 1.079 (1.013 to
1.153), csfull 1.145 (1.000 to 1.328),
sigma-led 1.022 (0.900 to 1.146). At
separations 8 to 15 the main list shows the
carry-save forms at 0.80 to 0.97; that effect
is addressed by the supplement below and does
not survive it.

L1-resident supplement (same protocol,
operand streams reduced to 24 KB so they sit
in L1, matching the kernel's stack-ring
operand residency; separations 0, 1, 6, 10,
13, 15): at separation 1, cs1 1.308 (CI 1.199
to 1.446), csfull 1.493 (1.308 to 1.830),
sigma-led 1.433 (1.220 to 1.857). At
separation 6: 1.307 (1.217 to 1.394), 1.443
(1.299 to 1.621), 1.307 (1.211 to 1.419). At
separation 10: 1.145 (1.084 to 1.205), 1.253
(1.187 to 1.317), 1.222 (1.092 to 1.450). At
separation 13: 1.119 (1.076 to 1.163), 1.287
(1.174 to 1.479), 1.114 (1.071 to 1.163). At
separation 15: 1.084 (1.046 to 1.137), 1.141
(1.123 to 1.165), 1.063 (1.039 to 1.105).
Separation 0 medians agree with the main list
(cs1 9.882 vs incumbent 7.823); its supplement
intervals are wide and consistent with the
main list. The wide-separation advantage in
the main list is therefore a property of the
L2 streaming pattern (each serial add carries
an L2 load on its chain, while the carry-save
loops load all operands up front), not of the
forms under kernel-faithful residency.

Session conditions: load average 5.10 to 6.06
at session starts; the mainnet node was
mid-restart during the sessions (RPC
unavailable at the session boundaries;
debug.log read-only shows block index loading
with block files up to height 412,014, IBD
continuing; the autopilot and miner were
running throughout and were not touched).

### Verdict

- **Decision.** No kernel built. The gate was
  a form winning on measured micro-cost AND
  dependency chain. Every carry-save form
  loses on chain (4 or 5 stages vs the
  incumbent's 3) and on total ops (5 or 7 vs
  3), and under kernel-faithful L1 residency
  every carry-save form also loses on measured
  cost at every separation from 1 up, with
  intervals excluding parity at separations
  6, 10, 13 and 15. At separations 0 and 1,
  the only separations at which resolution is
  ever forced, the main list already had them
  1.17 to 1.53 times the incumbent's cost.
- **Y-002: REJECTED** as a cheaper
  materialization of the four-operand sum.
  Its own success criterion, a measured
  per-distance winner table, is delivered
  above: the winner at every relevant distance
  is the incumbent. Tier: established negative.
- **Y-001: REJECTED** as a work reduction on
  this instruction set, at the pricing level.
  The engine was not built because its design
  point (Y-002) failed its gate and because
  the recurrence bounds deferral to separation
  1 at best, where the price is worst. Tier:
  established negative (pricing grade; no
  engine exists to benchmark, by the
  experiment's own order of work).
- **Cost-model correction.** The discovery
  system's cost model (COMPUTATION_GRAPH_
  RESEARCH.md section 4) should price a
  software 3:2 compressor at 3 instructions
  and a resolved four-operand carry-save sum
  at 5 (one level) or 7 (two levels), not at
  the registry's original ternlog-only count.
- **Side observation (not an EXP-019
  result).** The balanced_tree control read
  0.93 to 0.99 at separations 0 to 7 in the
  main list (intervals below 1 at separations
  2, 5, 7) but 1.06 to 1.20 in the L1
  supplement at separations 1 and up. The two
  regimes disagree, so no claim is made; the
  data point belongs to Y-003 if it is ever
  pursued.
- **Follow-up.** None for carry-save schedule
  generation on AVX-512. The price list stands
  as the cost model's resolution table.
  Production is byte-identical; nothing was
  integrated.

## EXP-020: Automated full-round rewriting (Y-014, Y-015; seeds Y-048, Y-049)

Status: COMPLETE (2026-11-14). Both engines ran
over the joint cone of one full round plus the
schedule cone that feeds it. The searches close
with the incumbent's graph form proven optimal
within the searched space (28 vector ops per
steady-state round in the AVX-512 vocabulary,
against a derived lower bound of 28), and with
exactly one op left on the table, which is a
compiler codegen gap, not a graph discovery:
gcc emits Maj as two chained VPTERNLOGD where
the proven form is one. That candidate (P6C-007)
promoted to a variant kernel under the
predeclared threshold, passed the full gate
set, and was benchmarked under the EXP-017
protocol: a positive point estimate in all
three sessions but not significant in any
session or pooled, so no verified improvement
is claimed and nothing is integrated. Raw
artifacts: analysis/exp020_search_results.json,
analysis/exp020_asm_audit.json,
proofs/exp020_candidates.json (P6C-005 to
P6C-009), benchmarks/exp020/ (four append-only
sessions plus the analysis). Tool:
src/exp020_round_search.py.

- **Hypothesis.** Y-014 (the saturation engine,
  per HYPOTHESIS_RANKING.md's numbering): an
  e-graph over the full round (S0, S1, Ch, Maj,
  the T1 and T2 addition trees evaluated jointly
  with shared subterms) finds an equivalent
  formulation with fewer vector operations or a
  shorter dependency chain than the production
  round. Y-015 (the SAT/SMT engine): solver-guided
  rewriting and bounded superoptimisation over
  the same cones find forms the fixed rewrite
  set cannot reach, including addition-tree
  shapes and cross-term sharing the cone-by-cone
  proofs of EXP-012 could not see. (Registry
  note: HYPOTHESIS_REGISTRY_Y.md titles the two
  mechanisms transposed relative to
  HYPOTHESIS_RANKING.md; this experiment ran
  both engines on identical cones and proof
  gates, so both entries are decided by it
  either way.)
- **Mathematical basis.** The round as a
  bit-vector expression DAG over the ten inputs
  (a..h, W, K), outputs a' and e', plus the
  schedule cone over (W[t-16], W[t-15], W[t-7],
  W[t-2]) with output W[t], in the per-lane
  scalar semantics of the multi-buffer kernel.
  Equivalence standard: z3 bit-vector UNSAT on
  all three outputs jointly, behind a
  1,000,000-sample differential filter. Cost
  model: the EXP-019 corrected census (every
  vector op 1 in its class; a 3:2 compressor
  level 3 ops; resolved carry-save sums 5 or 7)
  with critical-path depth as second objective.
  Methods hygiene, recorded because it mattered:
  the first draft of the reference DAG encoded
  Ch with the ANDNOT operands reversed, which
  is a different function (truth table 0x90,
  not 0xCA); the pipeline's own truth-table
  check caught it before any search ran, and
  the corrected reference was verified against
  an independent scalar round implementation
  (2,000 random states, 0 mismatches) and the
  scalar schedule recurrence (2,000 random
  templates, 0 mismatches).
- **Predeclared promotion threshold** (written
  into the search tool before the searches ran,
  per COMPUTATION_GRAPH_RESEARCH.md section 8):
  a candidate promotes to a variant kernel only
  if it is proven equivalent as above, its full
  round+schedule census is strictly below the
  incumbent EMITTED census (mechanically
  audited, 29 arithmetic ops), its depth does
  not regress past the extracted optimum, and
  the gain is not already present in the
  emitted code.
- **Incumbent.** Source form (classic library,
  production association): 38 ops, output
  depths a' 7, e' 7, W[t] 5. Emitted form
  (production object, gcc -O3 -mavx512f
  -mavx512bw, whole-function census of
  v_compress16, which contains exactly one
  round body): 29 arithmetic ops per
  steady-state round: 10 vprold/vprord,
  2 vpsrld, 7 vpternlogd (immediates 0x96 four
  times for the sigma XOR triples, 0xE4 for
  Ch, and 0x60 then 0x78 chained for Maj),
  10 vpaddd. gcc already folds every sigma
  triple and Ch into single ternlogs and
  already adds S1 last in T1; Maj is the one
  place it spends two ternlogs on a one-ternlog
  function.
- **Search A (saturation).** Rewrite set: the
  lab's proven Boolean rules, Ch/Maj alt forms
  recognised by truth table, term-level
  VPTERNLOGD folding (any Boolean expression
  over at most 3 frontier terms becomes one
  ternlog of those terms), De Morgan and
  ANDNOT introduction, commutativity, and
  associativity restricted to flattened add
  multisets of size at most 5 (cross-boundary
  association is Search B's BFS territory).
  Campaign 1 from the classic reference:
  388 expressions, 98 classes, 15 passes to
  fixpoint (the 500,000-node design budget was
  not binding). Extraction: classic library
  37 ops (depths 5, 5, 5; the entire classic
  saving over the source form is the Maj alt
  form, 5 to 4, plus depth-optimal
  reassociation); AVX-512 library 28 ops
  (depths a' 5, e' 5, W[t] 4). Campaign 2,
  seeded additionally with the ternlog forms:
  490 expressions, extracted 28 ops, no new
  winner. Under the design's stopping rule
  (two campaigns, no new proven candidate
  beating the incumbent graph), the round cone
  is characterised within this rewrite set and
  vocabulary.
- **Search B (SMT-guided and superoptimisation).**
  (1) Boolean function-set BFS, cost-weighted,
  all 256 three-input functions reached:
  classic minima Ch 3, Maj 4, XOR3 2,
  reproducing EXP-012 exactly; in the ternlog
  library every nonconstant function costs 1.
  (2) Addition-network BFS over disjoint
  subset-sum intermediates: T1 minimum 4 adds
  (exhaustive, 826 states), schedule sum
  minimum 3 adds (exhaustive, 54 states). The
  (a', e') pair BFS completed levels 0 to 3
  (97,357 states) before its 600 s deadline;
  the exact pair bound of 7 adds is completed
  by counting proof: in any adds-only network
  over the materialised atoms, a' (a 7-operand
  sum) needs at least 6 adds among its
  ancestors, e' (a 6-operand sum) at least 5,
  and the ancestors the two can share are
  subset sums of their 5 common atoms, at most
  4 adds; total at least 6 + 5 - 4 = 7, and 7
  is achieved by the incumbent structure.
  (3) Sigma lower bounds by symbolic offset
  support: the four sigmas' dependency supports
  are exactly three distinct offsets each
  (S0: 2, 13, 22 on a; S1: 6, 11, 25 on e;
  s0: 7, 18, 3 on W[t-15]; s1: 17, 19, 10 on
  W[t-2]), verified by symbolic propagation;
  a value whose bits depend on k distinct
  offsets of one variable, none of them 0,
  needs at least k offset-producing ops
  (induction on the DAG: a rotation permutes
  the support, a bitwise op unions supports,
  and the offset-op count dominates the
  support size not containing 0), plus at
  least one combining op per sigma. So each
  sigma costs at least 4, and the four cost
  at least 16 (12 offset ops + 4 combines).
  (4) Sharing analysis on the hash-consed
  reference: no nontrivial subexpression is
  shared between any two of S1, Ch, S0, Maj,
  s0, s1; the only sharing in the joint cone
  is T1 between a' and e', already in the
  incumbent. (5) Materialisation: z3 SAT
  counterexamples confirm the rotated terms
  cannot enter the addition network
  unmaterialised (rotr6 + rotr11 differs from
  rotr6 xor rotr11; the three-term sum differs
  from S1), and entering them separately
  costs more adds than the one combining
  ternlog. (6) Carry-save forms for T1 and
  the schedule sum, priced at EXP-019: T1
  plain 4 vs 6 (one level) or 8 (two);
  schedule plain 3 vs 5 or 7; rejected by the
  cost model (record P6C-009). (7) Bounded
  stochastic superoptimiser: 20,000 mutation
  proposals over the joint DAG seeded at the
  extracted optimum, 46 accepted moves, best
  score (28 ops, depth 5): nothing below the
  extraction.
- **Lower bound, assembled.** Offset ops at
  least 12, sigma combines at least 4, Ch and
  Maj at least 1 each in the ternlog library,
  adds at least 7 (round pair) + 3 (schedule)
  = 10. Total at least 28 vector ops per
  steady-state round in the vocabulary
  {VPADDD, VPTERNLOGD, classic bitwise,
  VPROLD, VPSRLD}. The extracted form achieves
  28, so it is optimal in that vocabulary.
  Out of the searched vocabulary, stated for
  scope: GFNI affine (its byte-local bit
  matrices cannot express these rotations on
  their own), VPSHUFB byte rotations (one op
  per offset, the same counting), and
  carry-save (priced above).
- **Proofs.** Both extracted forms: z3 UNSAT
  on (a', e', W[t]) jointly against the
  reference, and 1,000,000-sample differentials
  with 0 mismatches (records P6C-005, P6C-006).
- **Promotion and variant.** The extracted
  graph equals what gcc already emits except
  for Maj, so the single promotable candidate
  is P6C-007 (Maj as one VPTERNLOGD 0xE8):
  census 28 against the emitted 29, no depth
  regression. Variant kernel:
  extreme_optimization/src/avx512_mb_exp020.c,
  a production-shaped copy of
  mining/cpu/bal_avx512_mb.c with Ch and Maj
  written as single ternlog intrinsics
  (exports bal_p6_batch2 / bal_p6_search2);
  production is untouched. Its emitted census
  is mechanically 28 (6 vpternlogd:
  0x96 four times, 0xCA, 0xE8; audit in
  analysis/exp020_asm_audit.json). Full gate
  set in extreme_optimization/tests/
  test_exp020.py, all passing before any
  benchmark: 108,000 randomized differentials
  vs hashlib (bad 0), genesis digest and
  search, boundary nonces and odd counts,
  crossing and empty ranges rejected, template
  variations, target exact equality accepted
  and minus-one rejected, regtest-easy
  candidate set equal to the Python recount
  (82 in 20,000), exact accounting (search
  miss 5,000; genesis early exit exactly
  50,016; partial group at 100,003 backend
  100,016; sub-group at 5 backend 16;
  group-edge batch at 0xFFFFFFF0 matching
  hashlib for all 16 nonces).
- **Benchmark.** EXP-017 protocol only, via
  benchmarks/exp020_paired_bench.py and
  exp020_analyze.py: paired 65,536-hash
  blocks, randomised AB or BA order, 160
  recorded pairs per session after 8 warmup
  pairs, 2 worker threads, per-call steal and
  runnable-load covariates, adjusted paired
  log-ratio with 10,000-resample bootstrap.
  Three sessions of variant vs production MB
  plus one equal-pair control session
  (production MB vs itself). Session adjusted
  log-ratios: +0.0853 (CI -0.106 to +0.291),
  +0.0277 (CI -0.166 to +0.228), +0.0204 (CI
  -0.204 to +0.232); pooled +0.0493 (CI -0.067
  to +0.167), ratio 1.051x (CI 0.935x to
  1.182x), pairs won 0.515. Control: +0.0124
  (CI -0.201 to +0.218), pairs won 0.463, a
  null as required. Session median rates:
  production MB 5.73M, 4.91M, 5.36M H/s;
  variant 6.68M, 5.55M, 5.99M H/s. Node RPC
  reads at the session starts timed out under
  load and are recorded as unavailable in the
  session files (load average 11.44 / 7.74 /
  7.48 at the first session start); the miner
  and node were not touched. Raw data:
  benchmarks/exp020/session_*.json (4 files,
  append-only); analysis:
  benchmarks/exp020/analysis_20261114T165200Z
  .json.
- **Statistical assessment.** The point
  estimate is positive in all three sessions,
  but every interval contains 0, so under the
  adopted EXP-017 decision rule the variant is
  not significantly faster in any session or
  pooled. Within-session variance of the
  paired log-ratio 1.743, between-session
  0.000; the variance decomposition estimates
  about 17 sessions at 160 pairs for a 0.05
  log-unit halfwidth on this comparison, and
  the census-expected effect (1 op of 29,
  about 3.4 percent of arithmetic census,
  before dilution by the round's data
  movement) sits below what three sessions
  can resolve. As in EXP-018, no sessions
  were added after seeing the intervals: the
  three-session design is predeclared.
- **Sub-verdicts.** Y-014 (saturation engine):
  SUPPORTED as an instrument, NEGATIVE as a
  discovery: the saturation reached the
  vocabulary optimum from the classic
  reference and a second campaign found no
  new winner, so the round cone is
  characterised in the stated space: no
  cheaper equivalent full-round graph exists
  there. Y-015 (SMT-guided engine):
  SUPPORTED as an instrument, NEGATIVE as a
  discovery on this cone: its yields (Boolean
  minima re-derived, addition-network bounds,
  materialisation counterexamples, the
  superoptimiser's null) agree with Search A
  everywhere they overlap, and it produced no
  proven candidate the saturation missed,
  which was its comparative success criterion;
  its price is the pair BFS's incomplete
  depth (levels 0 to 3 of 7), recorded here
  rather than rounded up. P6C-007 (the Maj
  codegen gap): proven, priced, gated and
  benchmarked; NOT a verified improvement
  under the adopted rule.
- **Decision.** The full-round computation
  graph is closed at the vocabulary optimum:
  the remaining gap between the graph and the
  emitted code was one instruction, it is now
  measured, and it does not separate from
  noise under the decision statistic. No
  integration; production byte-identical.
  Tier: ESTABLISHED for the characterisation,
  the lower bound, and the benchmark null.
- **Follow-up.** Workstream A's round cone is
  characterised; the design's next cone is
  the two-round cone (cross-round sharing),
  which this experiment did not search and
  whose premise the sharing analysis weakens
  (nothing nontrivial is shared even within
  one round). The variant kernel is retained
  in the tree as a gated, benchmarked artifact.
  If a future compiler emits Maj as one
  ternlog for the classic form, P6C-007's
  delta disappears and this record is the
  evidence it existed.

## EXP-021: Heterogeneous worker pair (Y-097)

Status: COMPLETE (2026-11-14). The mixed pool
does not beat the best homogeneous pool at
either thread count, under either timing
semantics measured. At two threads the
homogeneous AVX-512 MB pool is significantly
faster than the mixed pool pooled, and the
mixed pool is statistically indistinguishable
from the homogeneous SHA-NI pool it half
consists of; at four threads the ordering is
strictly MB pool above mixed pool above
SHA-NI pool, pooled. The cross-family
contention-relief mechanism Y-097 proposes
does not appear in the worker-level rates
either: neither family's per-worker rate
improves measurably when its neighbours are
the other family. Raw artifacts:
benchmarks/exp021/ (18 append-only sessions,
the analysis, the secondary analysis, and a
100-pair smoke session filed under smoke/).
Tools: benchmarks/exp021_pool.py,
benchmarks/exp021_paired_bench.py,
benchmarks/exp021_analyze.py,
benchmarks/exp021_secondary.py. Gates:
extreme_optimization/tests/test_exp021.py.

- **Hypothesis.** Y-097: on this contended
  guest (about 1.5 effective CPUs under a
  4-vCPU cap), the two kernel families stress
  different resources (SHA-NI streams are
  latency-chain bound; the AVX-512 MB kernel
  is wide-vector bound), so a mixed worker
  pool, some threads running each family on
  disjoint nonce partitions of one search,
  beats the best homogeneous pool at the same
  total thread count, because the families
  contend less with each other than with
  themselves. Motivated by the EXP-007
  variance anomaly (flat AVX-512 response
  while scalar rates rose).
- **Design (predeclared).** Pools are lists
  of one-thread workers. MB worker:
  bal_v_batch2, threads=1 (the EXP-007
  kernel; libbal_v512.so). SHA-NI worker:
  bal_m_batch2m, threads=1, streams=4,
  mode=1 strided (the EXP-005 best
  per-worker geometry; libbal_geo.so). A
  pool partitions its nonce range into
  contiguous per-worker chunks of multiples
  of 16 summing exactly to the block; the
  pool driver (exp021_pool.py) launches the
  workers on a shared barrier and times the
  makespan. Two-thread pools: mb2 [mb, mb],
  mixed2 [mb, shani], shani2 [shani, shani];
  four-thread pools: mb4, mixed22 [mb, mb,
  shani, shani], shani4. All three pairwise
  comparisons at each thread count, three
  independent sessions each, 160 recorded
  pairs per session after 8 warmup pairs,
  65,536 hashes per worker per block
  (131,072 per two-thread block, 262,144 per
  four-thread block), randomised AB or BA
  order, same range for both arms of a pair.
  Statistic: the adopted EXP-017 one
  (paired log-ratio of pool rates, OLS
  adjustment on steal-difference,
  runnable-load-difference and order,
  10,000-resample pairs bootstrap).
  Success criterion, predeclared: Y-097 is
  a verified improvement (as a search
  configuration finding) only if the best
  mixed pool is significant against BOTH
  homogeneous pools in every session and
  pooled. One 100-pair smoke session of
  mixed2 vs mb2 was run first to validate
  the driver and is filed under
  benchmarks/exp021/smoke/; it is not part
  of the protocol sessions and is not
  pooled.
- **Correctness evidence.** The pool gate
  set ran before any benchmark
  (tests/test_exp021.py, all checks pass):
  candidate sets at the regtest-easy target
  (2^248) equal the independent Python
  recount and are identical across six
  splits of a 20,000 range (82 candidates),
  with every digest of every worker verified
  against hashlib; the genesis nonce is
  flagged by whichever family owns its
  partition (MB and SHA-NI owners, first
  and second partition slots, no other
  candidate in range); a range ending
  exactly at 2^32 and an unaligned start
  (12,345) verify in full; an empty
  partition (three workers, two waves)
  contributes attempted 0 and the union
  stays exact; single-worker pools of both
  families verify in full; randomised
  splits on a random template (12,000
  range, full digest check) and the three
  four-worker deployment shapes pass. The
  bench driver additionally asserts
  per-worker attempted, and MB backend
  counts, equal the partition plan on every
  timed call; no assertion fired in 18
  sessions (2,880 recorded pairs per arm
  side at two threads, the same at four).
- **Measured result (predeclared makespan
  statistic, adjusted).** Two threads,
  pooled log-ratios (candidate over
  reference): mixed2 vs mb2 -0.1884 (CI
  -0.294 to -0.082; ratio 0.828x; pairs won
  0.408), sessions -0.2308, -0.2700, -0.0708,
  the first two significant against the
  mixed pool, the third not significant;
  mixed2 vs shani2 +0.0125 (CI -0.087 to
  +0.109; 1.013x; won 0.506), sessions
  +0.0103, +0.0715, -0.0496, none
  significant; mb2 vs shani2 +0.3100 (CI
  +0.211 to +0.409; 1.363x; won 0.637),
  significant in all three sessions. Four
  threads: mixed22 vs mb4 -0.1285 (CI
  -0.203 to -0.054; 0.879x; won 0.388),
  sessions -0.0307, -0.1281, -0.2327 (the
  last significant against the mixed pool);
  mixed22 vs shani4 +0.1442 (CI +0.073 to
  +0.215; 1.155x; won 0.598), sessions
  +0.0946, +0.2123, +0.1290, the pooled
  result significant, one session
  significant; mb4 vs shani4 +0.2848 (CI
  +0.214 to +0.357; 1.329x; won 0.669),
  significant in all three sessions.
  Session median pool rates under the day's
  contention (runnable 13 to 16 throughout):
  two threads, mb2 2.07M to 4.46M, mixed2
  1.82M to 2.63M, shani2 1.68M to 1.98M;
  four threads, mb4 2.87M to 3.15M, mixed22
  2.80M to 3.05M, shani4 2.65M to 2.88M.
  Within-session variance of the paired
  log-ratio 0.69 to 1.45, between-session
  at most 0.005; covariate adjustment
  stayed near-neutral (CI width ratios
  0.94 to 0.98), as in EXP-017 and
  EXP-020. Node state per session is in
  the session files: nine of 36
  session-boundary RPC reads answered
  (blocks 412,169 to 412,223, headers
  975,822, initial block download
  continuing), the rest timed out under
  load and are recorded as unavailable.
  The miner, node, autopilot and keeper
  were never touched; pool-accepted shares
  advanced from 84 to 89 over the
  experiment window on the production
  miner's own work.
- **Secondary analysis (descriptive, not
  the verdict statistic).** A barrier block
  understates a mixed pool's production
  shape: mainnet_live assigns spans
  continuously, so a mixed pool's
  steady-state rate is the sum of its
  workers' concurrent rates, not the
  makespan of equal blocks. The driver
  recorded every worker's elapsed time, so
  exp021_secondary.py recomputes the
  implied continuous-assignment rate of
  every recorded call and reruns the same
  adjusted statistic over the recomputed
  log-ratios (artifact:
  benchmarks/exp021/secondary_implied_
  rates_20261114T183056Z.json). Pooled:
  mixed2 vs mb2 -0.1029 (CI -0.206 to
  +0.004; won 0.446), sessions -0.1675,
  -0.1877, +0.0376; mixed2 vs shani2
  +0.1176 (CI +0.020 to +0.218; won 0.540),
  significant pooled; mb2 vs shani2
  +0.3519 (CI +0.254 to +0.451). Four
  threads: mixed22 vs mb4 -0.1007 (CI
  -0.186 to -0.014; won 0.429), significant
  against the mixed pool pooled though no
  session is individually significant;
  mixed22 vs shani4 +0.2342 (CI +0.160 to
  +0.307), significant in all sessions;
  mb4 vs shani4 +0.3616 (CI +0.279 to
  +0.442). The ordering MB pool above
  mixed pool above SHA-NI pool is the same
  under both semantics; the deployment
  shape narrows the mixed pool's deficit
  at two threads (from -0.188 to -0.103)
  without changing its sign. Per-worker
  median rates by context (descriptive,
  across sessions): two-thread contexts,
  MB worker 3.10M in mb2 and 3.02M in
  mixed2, SHA-NI worker 1.76M in shani2
  and 1.68M in mixed2; four-thread
  contexts, MB worker 0.98M in mb4 and
  1.10M in mixed22, SHA-NI worker 0.83M
  in shani4 and 0.85M in mixed22. No
  family runs measurably faster beside
  the other family than beside itself;
  the small positive point values at four
  threads sit inside cross-session
  condition drift and are not claimed.
- **Statistical assessment.** The
  predeclared criterion fails on its
  first clause: the mixed pool is not
  above the MB pool anywhere it matters;
  pooled, it is significantly below it at
  both thread counts under the predeclared
  statistic, and below it under the
  secondary statistic as well (pooled at
  four threads, point estimate and two of
  three sessions at two). The makespan
  arithmetic explains the two-thread
  shape: with equal partitions the mixed
  block ends when its SHA-NI worker ends,
  so mixed2 tracks shani2 (pooled ratio
  1.013x, indistinguishable), while mb2's
  workers both run at the faster family's
  rate. The continuous-assignment shape
  removes that artefact and the mixed
  pool still does not reach the MB pool,
  because the sum of the two families'
  concurrent per-worker rates (about
  3.0M + 1.7M at two-thread contexts) is
  below two MB workers' sum (about
  6.2M). Diversification cannot beat
  concentration on the faster family
  when both draw on the same capped CPU
  budget and neither relieves the other;
  the EXP-007 anomaly does not cash out
  at pool level on this guest. As in
  EXP-018 and EXP-020, no sessions were
  added after seeing the intervals.
- **Decision.** Y-097 is NOT a verified
  improvement. The registry's success
  line (a heterogeneous total above both
  homogeneous totals, reproduced) is not
  met; the reproduced result is the
  opposite ordering against the MB pool.
  Tier: ESTABLISHED NEGATIVE for the
  heterogeneity mechanism on this guest,
  under both timing semantics, with the
  worker-level mechanism measured. No
  production integration and none
  recommended: the homogeneous MB pool
  remains the fastest measured search
  configuration, which is what production
  already runs. Production byte-identical.
- **Environment note (added on
  completion).** All EXP-021 gates and
  sessions ran on the programme's AMD
  EPYC 9D25 host (SHA extensions and the
  full AVX-512 set including VBMI
  exposed), 17:44 to 18:05 UTC. At about
  18:08 UTC the VM was replaced onto an
  Intel Xeon Platinum 8321HC host that
  exposes AVX-512F, BW, VL and VNNI but
  no SHA extensions and no VBMI. A
  post-hoc re-run of the gate set on the
  new host therefore faults (SIGILL) in
  both research libraries as built: the
  geo library executes SHA instructions
  the host lacks, and the research MB
  library, compiled -march=native on the
  EPYC host, contains VBMI permute
  instructions (vpermt2b, vpermi2b) in
  its staging code. Neither library can
  re-execute on the current host; the
  sources and per-session manifests are
  recorded, so a rebuild on a SHA and
  VBMI host reproduces the experiment.
  The production library was built with
  restricted flags (-mavx512f -mavx512bw,
  the audited integration) and the live
  miner re-selected v512 on the new host
  through its CPUID probe and digest
  self-test and is mining on it: the
  incident is an incidental end-to-end
  validation of the integration's
  dispatch design, and it changes no
  EXP-021 number, all of which predate
  the replacement.
- **Follow-up.** One refinement was
  visible but not run, recorded here
  rather than silently absorbed:
  rate-proportional partition sizing
  under continuous assignment. Its
  ceiling is the sum of concurrent
  per-worker rates, which the worker
  medians above bound below the MB
  pool's total at two threads and at
  about parity at four threads, so the
  prior is poor; it would need its own
  experiment ID and a fresh predeclared
  design if the owner wants it settled
  rather than bounded. The EXP-007
  variance anomaly itself remains
  attributed as in EXP-010 (the vector
  kernel's own behaviour under a
  saturated runnable queue), not to
  cross-family pipe contention.

## EXP-022: Flags-only MB batch via mask registers (Y-084)

Status: COMPLETE (2026-11-14). VERIFIED
IMPROVEMENT in batch scope under the adopted
EXP-017 rule: the flags-only batch form of the
AVX-512 multi-buffer kernel beats the
production batch kernel at every candidate
density tested, in every session and pooled,
at both thread counts measured. The gain is
largest where the registry predicted the
mechanism bites (sparse candidates: pooled
1.82x) and smallest where every lane is a
candidate (1.33x), because what is being
removed is the per-lane work production batch
spends on hashes whose digests nobody reads.
This is a batch-mode result only: the
production search path never paid the batch
epilogue, and no search-rate claim is made.
Raw artifacts: benchmarks/exp022/ (15
append-only sessions, the gates record, the
analysis). Tools: benchmarks/exp022_gates.py,
benchmarks/exp022_paired_bench.py,
benchmarks/exp022_analyze.py (statistic),
benchmarks/exp022_analyze_incremental.py
(scheduling only; see the analysis note).
Kernel: extreme_optimization/src/
avx512_mb_flags.c (research variant,
export bal_v_batchf2).

- **Hypothesis.** Y-084, as written in the
  registry: MB batch mode stores 32 bytes per
  hash that most consumers never read. The
  mechanism is a batch mode that computes the
  target comparison in vector form, stores one
  flag byte (or one mask bit) per hash, and
  extracts digests only for flagged lanes.
  The registry scopes the claim itself:
  moderate impact in batch-shaped consumers
  (verification, statistics), negligible in
  search mode. Success line as written:
  batch-mode gain at stated densities, with
  gates including candidate sets at three
  densities. The task framing's wider reading
  (masking lanes off mid-search to cover
  heterogeneous spans) is not what the
  registry claims, and is structurally void
  in this kernel shape besides: the 16 lanes
  advance in lockstep through both
  compressions, a lane's digest exists only
  when the group completes, and masking a
  lane's stores does not retire its round
  work, so no search-mode variant of the
  claim was built or measured.
- **Design (predeclared, before timing).**
  Primary comparison: flagsx (variant with
  flagged-digest extraction) versus
  production bal_v_batch2 at candidate
  density approx 0 (target_int 0), two
  threads. Verdict rule: VERIFIED
  IMPROVEMENT (batch scope) iff the primary
  comparison is significant (adjusted CI
  entirely above 0) in every session (at
  least 3) and pooled under the EXP-017
  statistic. Scope evidence, not part of
  the verdict rule: the same comparison at
  densities 2^-8 and 1, a pure-flags arm
  (digests NULL) at density approx 0, and
  the primary comparison at one thread.
  Blocks of 65,536 hashes, randomised AB/BA
  order, 120 pairs per session, attempted
  and backend asserted on every timed call.
- **Implementation.** avx512_mb_flags.c is
  the EXP-007 research kernel (byte-identical
  kernel logic to production in its batch
  and search paths) plus bal_v_batchf2. The
  flags group runs the same two
  compressions, then compares in vector
  form: v_meets scans digest bytes from
  index 31 down, so the comparison is a
  lexicographic unsigned compare of the
  eight words bswap32(state[7-j]) against
  bswap32(tword[7-j]), carried in opmask
  registers (per word, undecided lanes take
  the cmplt/cmpgt result; a lane meets iff
  it is never greater; equality meets, as
  in v_meets). The group result is one
  __mmask16, stored as two flag bytes per
  group into a per-span private bit array
  and merged into the caller's flag-bit
  array (bit i set iff nonce start+i meets
  the target). The digest transpose store
  happens only when a lane in the group is
  flagged, and only flagged lanes are
  extracted, into the same slot layout as
  bal_v_batch2. With digests NULL nothing
  is materialised. Accounting is identical
  to production: attempted == count,
  backend == sum over spans of
  ceil(span/16)*16, dummy lanes masked out.
  Both libraries were built on the current
  host with the restricted flag set
  (-O3 -mavx512f -mavx512bw, never
  -march=native), the baseline from the
  unmodified research source.
- **Gates (all PASS before timing;**
  benchmarks/exp022_gates.py, record in
  benchmarks/exp022/). G1: at the maximum
  target every lane is flagged, so 154,316
  nonces across four headers and both
  thread counts exercise full extraction;
  every digest equals hashlib exactly and
  accounting matches production. G2:
  candidate sets from the variant bit array
  equal the production flag-byte sets
  exactly at densities 0, 2^-16, 2^-8 and
  1 (0, 0, 216 and 65,536 candidates per
  65,536), at threads 1, 2 and 3; pure-flags
  bits identical to extract-mode bits;
  every extracted digest equals the
  production digest at its slot. G3: over
  the genesis window under the genesis
  target exactly one bit is set, at the
  genesis nonce, and the extracted digest
  equals hashlib of the genesis header.
  G4: target equality flags the nonce,
  target minus one does not, target plus
  one does, at seven sampled nonces across
  lane and group boundaries. G5: attempted
  and backend equal production's on 32
  (count, threads) pairs including counts
  1, 15, 16, 17, 31, 100, 1000 and 65537,
  whose span begins are not multiples of
  eight (the flag-bit merge alignment).
- **Measured result (adjusted pooled**
  log-ratio, EXP-017 statistic; ratio is
  exp of it). Primary, flagsx vs production
  at density approx 0, two threads: +0.5984
  (CI +0.5042 to +0.6905), 1.82x, pairs won
  0.742; sessions +0.5825, +0.6157, +0.5988,
  every session significant. Density 2^-8:
  +0.4628 (CI +0.3770 to +0.5484), 1.59x,
  won 0.736; sessions +0.4338, +0.4607,
  +0.4856, all significant. Density 1:
  +0.2854 (CI +0.2035 to +0.3663), 1.33x,
  won 0.639; sessions +0.2502, +0.3227,
  +0.2799, all significant. Pure flags at
  density approx 0: +0.6344 (CI +0.5377 to
  +0.7291), 1.89x, won 0.769, all sessions
  significant. Primary at one thread:
  +0.6033 (CI +0.5025 to +0.7032), 1.83x,
  won 0.731, all sessions significant.
  Median per-call rates move with host
  contention (production arm medians
  0.83M to 1.31M H/s across sessions,
  variant 1.12M to 2.44M); the paired
  statistic is the evidence, not the
  medians.
- **Mechanism (measured, not conjectured).**
  The effect is monotone in exactly the
  variable the mechanism names: the
  fraction of lanes whose digests are
  never read. At density approx 0 the
  variant does no extraction at all, and
  the entire production epilogue disappears
  with it: the eight zmm staging stores,
  the scalar per-lane byte extraction of
  all sixteen digests (512 byte stores per
  group), the 32-byte per-hash output copy
  and the scalar per-lane v_meets. In its
  place: eight vector compares folded into
  opmask registers and two flag bytes per
  group, plus the in-call bit merge. At
  density 1 the variant extracts every
  lane, like production, and the residual
  1.33x is what remains of the advantage:
  the vector compare against the scalar
  per-lane compare, the flag bits against
  the separate flag bytes, and one staging
  store written directly to output slots
  against production's staging plus copy.
  The pure-flags arm sits slightly above
  the extraction arm at the same density
  (+0.6344 vs +0.5984), the price of
  carrying the extraction path at all.
  The conclusion the registry's H-04
  observation pointed at is now measured
  on this kernel: in batch mode the
  production epilogue, not the compression,
  was roughly half the call.
- **Statistical assessment.** The
  predeclared criterion is met on its
  first clause and every scope comparison
  agrees in sign and significance: fifteen
  sessions, fifteen individually
  significant, five pooled intervals all
  excluding zero by wide margins. No
  sessions were added after seeing the
  intervals. Covariate adjustment is
  near-neutral throughout (pooled
  unadjusted +0.5976 vs adjusted +0.5984
  on the primary), as in EXP-017: pairing
  does the work. One analysis note: the
  monolithic exp022_analyze.py run stalled
  past twelve minutes under the
  replacement host's CPU pressure
  (pressure stall average above 80
  percent) and was killed without output;
  the recorded analysis was computed by
  exp022_analyze_incremental.py, which
  imports the same analyse_group statistic
  and the same per-group seed derivation
  and differs only in scheduling (primary
  group first, output rewritten after each
  group). The numbers are the adopted
  statistic either way.
- **Decision.** Y-084 is a VERIFIED
  IMPROVEMENT in batch scope under the
  adopted rule, at all three stated
  densities. No production change is made
  by this experiment: the live miner uses
  the search path, which this result does
  not touch, and production batch
  (bal_v_batch2) is consumed by the
  engine's verification and statistics
  paths, where adopting a flags-only
  output shape is an interface decision
  for the owner, recorded here as a
  recommendation: batch consumers that
  read flags and rare digests should be
  offered the flags form, worth about
  1.8x on sparse-candidate batch work on
  this host class. Production
  byte-identical.
- **Environment.** All EXP-022 work ran on
  the replacement host (Intel Xeon
  Platinum 8321HC at 1.40 GHz, AVX-512F,
  BW, VL and VNNI present, no SHA
  extensions, no VBMI), 19:05 to 19:35
  UTC, under heavy co-tenancy (load
  average 10 to 15, the live miner and
  node running throughout and never
  touched). The restricted flag set is
  what makes the experiment possible on
  this host at all: the EXP-021 libraries
  built -march=native on the EPYC host
  fault here, while both EXP-022 libraries
  use only AVX-512F and BW instructions.
  Session manifests record the host and
  the source and binary hashes.
- **Follow-up.** The registry's Y-096
  entry (production-shaped harness
  measurement of Y-084's flags-only
  output through mining/engine.py span
  patterns) is the natural next step if
  the owner wants an integration-grade
  comparison for the batch consumers;
  this experiment measured the kernel
  bench shape, as Y-084's own test line
  specifies. A flags-form search epilogue
  is not a follow-up: the search path
  already avoids the batch epilogue, and
  the mid-batch lane-retirement reading of
  the hypothesis is structurally void, as
  recorded under Hypothesis above.

## EXP-023: Midstate amortisation family (Y-076, Y-077, Y-079)

Status: COMPLETE (2026-11-14). Three verdicts.
Y-076 is REJECTED as specified (established
negative): its premise is false in the code as
built, proven by gate. Y-077 is a VERIFIED
IMPROVEMENT at the data level under the adopted
EXP-017 rule (pooled 18.49x for extranonce steps
at 500 transactions, 22.06x for job families),
with its compression-prefix sub-claim rejected
as immaterial. Y-079 is delivered as a VERIFIED
TABLE: all 32 field subsets plus two
supplementary boundary rows verified by
construction. No integration by this
experiment: the amortised builder is a research
prototype outside production files, and
adopting it in mining/engine.py is a
recommendation for the owner's decision.
Production byte-identical. Raw artifacts:
benchmarks/exp023/ (12 append-only sessions,
the gates record, the audit, four analyses).
Tools: benchmarks/exp023_snapshots.py (round
stepper and snapshot ladder),
benchmarks/exp023_amortized.py (two-level
prototype), benchmarks/exp023_gates.py,
benchmarks/exp023_audit.py,
benchmarks/exp023_paired_bench.py,
benchmarks/exp023_analyze.py (statistic,
reusing the EXP-017 analyser unchanged).

- **Claims and predeclared verdict rules.**
  Y-076 as written: in the solo server's shape
  each extranonce step changes the coinbase,
  hence the merkle root, hence block 1's second
  half; the midstate is rebuilt per step; cache
  block 1's first 64 bytes' compression (fixed
  per job) and rebuild only the second half,
  success being per-step setup reduced by the
  measured half-block share. Rule: VERIFIED
  only if (i) the audit finds a per-extranonce
  midstate rebuild in a lab serving path, (ii)
  the named cached quantity is extranonce
  independent (gate), and (iii) a paired bench
  shows the predicted reduction. Failure of
  (i) or (ii) closes it as an established
  negative with the evidence. Y-077 as written:
  pool jobs in a family share version and
  prevhash and differ in merkle root and time;
  template setup recomputes block 1 fully per
  job; a two-level midstate cache (family level:
  block 1's first-half compression, valid when
  version, prevhash and the merkle head align;
  job level: the rest) reduces per-job setup.
  Rule: the cache is a VERIFIED IMPROVEMENT iff
  per-unit setup over the predeclared
  comparisons is significant in every session
  and pooled under the EXP-017 statistic with
  byte-identical output; the compression-prefix
  level is assessed separately against its
  alignment condition and its priced ceiling.
  Y-079 as written: derive, per subset of
  {version, prevhash head, merkle tail, time,
  nbits}, the deepest valid snapshot (named
  menu: block-1 half, full midstate, block-2
  round 2, schedule round 17), verified per row
  by construction. Rule: VERIFIED TABLE iff
  every row's constructed deepest depth equals
  the derived depth.
- **Audit (what is actually recomputed today;**
  benchmarks/exp023_audit.py, counting stub RPC,
  zero latency, this host). In the GBT path,
  MiningEngine.build_candidate is called once
  per extranonce round by mine_cycle (64 rounds
  per template) and recomputes, on every call:
  every transaction's txid (strip and rehash)
  and wtxid (500 of each at 500 transactions),
  the witness commitment, the full merkle tree
  over [coinbase] + txids (503 double hashes at
  500 transactions), the block body join, one
  validateaddress RPC and one getblockchaininfo
  RPC (exactly one each per call, counted).
  Medians on this host: 0.047 ms per call at 0
  transactions, 0.247 at 10, 2.696 at 100,
  17.811 at 500; per template over 64 extranonce
  calls that is up to 1,139.9 ms of construction
  at 500 transactions, plus 128 RPC round trips
  (EXP-009 priced a real validateaddress round
  trip at 3.96 ms median, so the stub-priced
  figures are conservative for a live node).
  The genuinely extranonce-dependent residue of
  a call is the coinbase build, the coinbase
  spine of the merkle tree (9 double hashes at
  500 transactions, median 0.075 ms against
  2.97 ms for the full rebuild in the same audit
  pass) and header assembly: about 99.6 percent
  of the repeated per-call work at 500
  transactions is extranonce-independent
  reusable state. In the stratum path
  (mining/stratum_client.py build_header, the
  live miner's per-extranonce2 step) a step
  costs a median 117.9 us of coinbase and branch
  hashing, which is 3.4e-7 of the full nonce
  scan the step feeds at the recorded live rate:
  negligible either way, cache or no cache. In
  the solo server there is no midstate anywhere:
  jobs are built per template (refresh_job) and
  validate_share prices a submitted share at a
  median 24.3 ms at 500 transactions, dominated
  by its own full merkle rebuild; that is a
  per-share cost, not per-extranonce, and the
  server never steps an extranonce (the
  extranonce arrives inside submitted shares).
  The compression-prefix ceiling, priced with
  the round stepper in pure Python: a full
  block-1 compression costs 351.8 us, the R8
  prefix 48.2 us, so a block-1 prefix snapshot
  could save at most about 304 us per block-1
  compression in a Python path, and no lab path
  performs a per-step or per-job block-1
  compression for it to attach to (hashlib
  paths do not split blocks; the kernel
  computes the midstate once per search batch).
- **Gates (all PASS before timing;**
  benchmarks/exp023_gates.py). G-A: the round
  stepper's full compression equals
  PureSHA256's block result on 200 randomised
  blocks; inner digests completed from the MID,
  B2R2 and SCH17 snapshots equal hashlib on 200
  randomised headers, and the midstate equals
  PureSHA256's post-block-1 state (hashlib
  exposes no raw chaining state; the midstate
  is pinned by PureSHA256 and by completion
  against hashlib). G-B: 1,320 randomised
  (template, extranonce) cases byte-identical
  between build_candidate and the prototype
  (header, body, target, height, fees, tx
  count, witness count), covering 0 to 500
  transactions, segwit mixes, coinbaseaux
  flags and witness commitments; a mismatched
  template fingerprint raises instead of
  serving. G-C: the merkle spine equals
  mining.pow.merkle_root at 47 leaf counts.
  G-D (Y-076): over 20 randomised pairs, an
  extranonce-driven root change alters header
  bytes 36 onward and the midstate, and leaves
  the R8 state identical: block 1's first 64
  bytes are NOT fixed across extranonce steps,
  and the deepest extranonce-independent
  snapshot is R8 (rounds 0 to 8: version and
  prevhash), not the half block. G-E (Y-077):
  R11 is shared iff the merkle head (header
  bytes 36 to 47) aligns, both directions by
  construction. G-F (Y-079): all rows below.
- **Implementation.** exp023_amortized.py:
  FamilyContext pays the two per-call RPCs
  once per (node, payout); PreparedTemplate
  pays the transaction pass, the witness
  commitment, the value check and the merkle
  tree levels over a placeholder coinbase leaf
  once per template; build() then pays only
  the coinbase build, the coinbase spine walk
  (ceil(log2(n+1)) double hashes), header and
  body assembly per extranonce step. Audit
  medians: prepare 32.5 ms and step 0.068 ms
  at 500 transactions (prepare 9.1 ms, step
  0.087 ms at 100), so against build_candidate
  the cache breaks even at about 1.8 steps per
  template and pays from the second step on.
- **Measured result (adjusted pooled**
  log-ratio, EXP-017 statistic; the paired
  unit is 16 candidate builds; arm B builds
  its caches inside the timed region).
  steps500 (16 extranonce steps on one
  500-transaction template; Y-077 primary,
  level-2 reuse): sessions +2.9286, +3.0091,
  +2.8175, every session significant; pooled
  +2.9174 (CI +2.7884 to +3.0406), 18.49x (CI
  16.26x to 20.92x), pairs won 1.000.
  steps100: sessions +2.7885, +2.9499, +2.6858,
  every session significant; pooled +2.8011
  (CI +2.6223 to +2.9688), 16.46x (CI 13.77x
  to 19.47x), pairs won 0.993. family500 (16
  jobs of one family, one step each; Y-077's
  job-family shape): sessions +3.0708,
  +3.0663, +3.1539, every session significant;
  pooled +3.0938 (CI +2.9410 to +3.2438),
  22.06x (CI 18.93x to 25.63x), pairs won
  1.000. churn500 (boundary control: each
  job's tx set differs by five replaced
  transactions, so level 2 is rebuilt per job
  and only level 1 is reused): sessions
  -0.0882, +0.0719, -0.0816, none significant;
  pooled -0.0327 (CI -0.1207 to +0.0517),
  0.97x, pairs won 0.480. The boundary lands
  where the mechanism predicts: the win is
  the reused transaction pass and tree, and
  when the tx set churns every job there is
  nothing left to reuse but the family
  constants, which the zero-latency stub
  prices at about zero (against a live node
  the two saved RPC round trips per job
  would still apply).
- **Verdicts.** Y-076 REJECTED as specified,
  established negative, on both prongs of its
  rule: (i) no lab serving path rebuilds a
  midstate per extranonce step, so the named
  cost does not exist (the solo harness the
  registry names contains no midstate and no
  extranonce stepping, so its cache on/off
  test is not expressible there); (ii) the
  quantity it proposes to cache is not
  extranonce independent: the merkle root
  occupies block-1 bytes 36 to 63 and
  avalanches, the midstate changes with every
  extranonce step (G-D), and only the R8
  prefix (9 of 64 rounds) survives. Its
  success line (per-step setup reduced by the
  half-block share) therefore has no referent
  in this code. The whole-path objective
  behind it, amortising the extranonce
  dimension, is real and is what Y-077
  measures. Y-077 VERIFIED IMPROVEMENT at the
  data level (family constants, per-template
  transaction pass, merkle spine) under the
  adopted rule, in the serving path, as a
  prototype: integration into
  mining/engine.py is recommended to the
  owner, noting the churn boundary (the win
  requires steps per template above about 2,
  or jobs sharing a tx set; mine_cycle's 64
  extranonce rounds per template sit far
  above break-even). Y-077's stated
  compression-prefix mechanism is separately
  REJECTED as a material saving: valid
  without alignment only to R8, to R11 only
  under merkle-head alignment (probability
  2^-96 for unrelated roots), worth at most
  about 304 us per block-1 compression in a
  Python path and zero in the kernel path.
  Y-079 VERIFIED TABLE, below.
- **Y-079 verified table.** Fields as header
  word groups (canonical doc usage): version
  = block-1 W0; prevhash head = block-1
  W1..W8; merkle tail = the merkle root as one
  field, block-1 W9..W15 plus block-2 W0 (a
  root change avalanches over all eight
  words; the tail word's special role is
  supplementary row S1); time = block-2 W1;
  nbits = block-2 W2. The nonce always varies.
  Deepest valid snapshot, by the shallowest
  varying field (verified for all 32 subsets,
  3 randomised instances each, equality at the
  tabulated rung and inequality at every
  deeper rung):
    version varies: none (even R0 dies).
    prevhash varies: R0 (state after block-1
      round 0).
    merkle varies: R8 (after round 8).
    time varies: B2R0 (midstate plus block-2
      round 0).
    nbits varies: B2R1.
    none of the five varies: SCH17 (block-2
      state after round 2, plus schedule words
      W16 and W17).
  Against the registry's named menu (block-1
  half, full midstate, block-2 round 2,
  schedule round 17): block-1 half is R11,
  and it is the deepest valid snapshot for
  NO subset of the five fields: the common
  serving variations sit below it (a root
  change permits only R8, a prevhash change
  only R0, a version change nothing), and it
  becomes valid only under merkle-head
  alignment (supplementary row S2: a root
  change confined to bytes 12..27 leaves R11
  deepest, verified). Full midstate is the
  deepest named depth for time and nbits
  rolls (true depths B2R0 and B2R1 sit
  between the named rungs). Block-2 round 2
  and schedule round 17 are valid exactly
  when none of the five fields varies, and
  schedule round 17 is then the deepest.
  Supplementary row S1: a change confined to
  the merkle tail word (bytes 64..67) leaves
  the full midstate valid and kills B2R0,
  verified. The serving rule the table
  supports: cache R8 across root changes
  inside a job family, the midstate across
  time, nbits and tail-word rolls, and
  SCH17 across nonces only; never key a
  snapshot at R11 or deeper to a template
  pair whose root or prevhash may differ.
- **Environment.** All gates, audit and bench
  sessions ran on the Intel Xeon Platinum
  8321HC host (AVX-512F/BW/VL/VNNI, no SHA
  extensions, no VBMI) recorded in every
  session manifest, under co-tenancy with the
  live miner and node, never touched. The
  steps100, family500 and churn500 analyses
  were completed after a runtime restart
  replaced the host with an AMD EPYC 9D25;
  the analysis is deterministic arithmetic
  over the recorded session files and does
  not depend on the analysing host.
- **Follow-up.** If the owner adopts the
  amortised builder, the integration shape
  is: MiningEngine gains a prepared-template
  object keyed by template fingerprint,
  mine_cycle prepares once per template and
  steps per extranonce, and the solo server's
  validate_share can take the same cached
  tree (its 24.3 ms per share at 500
  transactions is the same full-rebuild cost
  in a second path). Neither change is made
  by this experiment.
