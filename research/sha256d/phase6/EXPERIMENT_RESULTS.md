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

Status: NOT RUN. Designed in PHASE6_RESEARCH_PLAN
.md section 3 and HYPOTHESIS_RANKING.md. Primary
metric is the assembly spill audit (state spills:
target zero, against EXP-011's 48 vmovdqa64);
the rate decision waits for EXP-017. Artifacts,
when run: benchmarks/exp018/ plus the assembly
record in the kernel's experiment file.

## EXP-019: Carry-save schedule pricing, then engine (Y-002, Y-001)

Status: NOT RUN. Designed in HYPOTHESIS_RANKING
.md (Y-001, Y-002 entries). Deliverable of the
first half is a per-distance price list for one
carry-save level, with resolution costs separated;
the list feeds the discovery system's cost model
(COMPUTATION_GRAPH_RESEARCH.md section 4).
Artifacts, when run: analysis/exp019_price_list
.json and benchmarks/exp019/.

## EXP-020: Automated full-round rewriting (Y-014, Y-015; seeds Y-048, Y-049)

Status: NOT RUN. The discovery machinery's first
component is built and seed-validated
(src/discovery_harness.py; candidates P6C-001 to
P6C-004 in proofs/discovery_demo_results.json, all
proof-gated, none benchmarked). The experiment
proper (full-round cone, both engines, promotion
rules of COMPUTATION_GRAPH_RESEARCH.md section 8)
runs when EXP-017 exists to decide its survivors.
