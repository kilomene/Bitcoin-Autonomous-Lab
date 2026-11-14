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

Status: NOT RUN. Designed in PHASE6_RESEARCH_PLAN
.md section 3. Sub-verdicts: (a) the steal-
normalised statistic recovers an injected effect
size within its stated interval; (b) the paired
block size (10k, 100k, or 1M hashes) at which
control runs return decision-grade nulls across
sessions; (c) the equal-pair control (Y-103)
returns a null under the full procedure. Raw
artifacts, when run, land in benchmarks/exp017/
under append-only session names with Y-108
manifests.

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
