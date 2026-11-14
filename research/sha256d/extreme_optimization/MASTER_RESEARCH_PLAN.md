# Master Research Plan: NOVA SHA-X Extreme Optimization

Opened 2026-11-14 under the Grand Research Mandate. This
plan governs the work in this directory. It builds on the
existing programme record in research/sha256d/ (Stages 1 to
5 of the original charter are complete; see
../research_roadmap.md) and extends it toward one objective:
the fastest exact Bitcoin SHA-256d mining software that can
be built, proven, and measured on existing CPU hardware.

The mandate's performance targets, 500 GH/s and then
140 TH/s, are treated as engineering objectives to be
assessed quantitatively, not as claims. The honest
assessment is in PERFORMANCE_ROADMAP.md, section 4: both
targets are aggregate-fleet scale. The credible mission on
any one machine is to close toward the per-core ceiling the
fixed round structure imposes, and to prove fleet
aggregation separately, on real machines, if and when they
exist. Ambition sets the direction; evidence sets the
claims.

## Governance

1. Production protection rule. Production code
   (mining/cpu/bal_batch.c, mining/cpu/bal_sha_intrin.c,
   gpu/engine.py, mining/engine.py, mining/mainnet_live.py
   and the live supervision stack) is never the sketchpad.
   Candidates are built in the research tree or as separate
   libraries. A candidate reaches production only when it
   passes the full correctness gate set, beats the incumbent
   median beyond spread overlap at the tuned configuration
   in an interleaved decision run, keeps the full test
   suite green, and mines a fresh regtest block accepted by
   Bitcoin Core through the changed backend. This rule is
   what kept H-01 out of production in EXP-003 despite
   favourable medians, and it stays.
2. Registry discipline. Every hypothesis is registered
   before it is built (H-series in
   ../experiment_registry.md, X-series in
   HYPOTHESIS_REGISTRY.md here). Every experiment gets a
   permanent entry in EXPERIMENT_REGISTRY.md with the full
   field set of mandate section 10. Rejected and refuted
   ideas stay in the record with their evidence
   (../rejected_hypotheses.md is the model).
3. Evidence standard. No number is reported without its
   experiment record. Medians with spread, never best runs.
   Coverage and actual computations are never conflated
   (Task 003.9 accounting definitions). Estimates are
   labelled estimates with assumptions shown. Anything not
   executed on hardware that exists here is marked
   UNVERIFIED (the GPU, FPGA, and ASIC gates from Tasks 002
   and 003 remain exactly that).
4. No fabrication boundary. The mandate's targets are not
   permission to inflate. A rate is claimed only for the
   configuration that measured it: per worker, per thread
   count, per machine, and aggregate, each labelled.
5. Live-system boundary. The live mainnet pool miner, the
   pruned mainnet node, the autopilot, and the keeper are
   not experiment subjects. Experiments run alongside them
   and state the contention that creates, exactly as
   EXP-000 to EXP-003 did.

## Claim classification (three tiers, binding)

Added 2026-11-14 by owner instruction. Every result,
hypothesis status, and claim in this programme's records
carries exactly one of three labels. Ambition language
never upgrades a tier; only reproduced measurement does.

- VERIFIED IMPROVEMENT: actually measured and reproduced
  under the stated conditions, with the conditions
  (hardware, thread count, contention, spread) recorded
  alongside the number.
- PROMISING HYPOTHESIS: mathematically or architecturally
  plausible, with a stated mechanism, awaiting
  implementation or testing.
- UNPROVEN BREAKTHROUGH: an idea needing substantial
  investigation before any expectation is warranted.

Retroactive labelling of the programme's headline claims
(as of the EXP-004 to EXP-009 batch):

- The MSG1/MSG2 schedule gain (about 2.6x over a scalar
  schedule at equal rounds, EXP-002): VERIFIED
  IMPROVEMENT.
- Stream interleaving (H-01; 2.36x per worker at 2
  streams, EXP-003): VERIFIED IMPROVEMENT under its
  stated conditions. Its production integration remains
  gated by the beyond-spread decision rule, which
  EXP-004 did not pass.
- The AVX-512 16-way multi-buffer (EXP-007): VERIFIED
  IMPROVEMENT on a median basis at 2 threads, reproduced
  in two interleaved sessions under contention; it holds
  no separation (min over max) claim, and its variance is
  the widest measured.
- Hand-scheduled assembly as a route past the stream
  kernels: PROMISING HYPOTHESIS. EXP-006's schedule-first
  restructuring cut spill traffic but not time, so the
  premise is weakened, not confirmed.
- Cross-nonce phase pipelining (EXP-008): measured at
  parity with a second same-phase stream; the phase
  diversity premium is not supported on this core. It
  stays PROMISING HYPOTHESIS only for other cores.
- Anything beyond the per-core ceiling narrative of
  PERFORMANCE_ROADMAP.md (fleet-scale rates, order-of-
  magnitude single-core jumps): UNPROVEN BREAKTHROUGH.

## Workstreams

The mandate's seven workstreams, mapped to concrete
activities and artifacts in this repo.

### Workstream A: Mathematical and cryptographic optimization

- Maintain the mathematical map (MATHEMATICAL_DISCOVERY.md).
- Prove or refute transformation candidates with the
  three-leg proof pattern (../tools/boolean_proof.py):
  exhaustive bit proof, randomized differential, z3 UNSAT.
- Current open fronts: schedule partial evaluation beyond
  the state prefix (X-024, X-080), outer-hash schedule
  simplification from its constant words (X-023), GFNI
  affine forms of the schedule sigmas (X-020), carry-save
  addition in vector rounds (X-021, X-022), superoptimizer
  search over the round's Boolean cone (X-027, X-094).
- Settled and out of bounds: reduced-round and statistical
  shortcuts (R-01, H-24), partial target pre-checks (R-06),
  nonce-order heuristics (X-098, refutation class).

### Workstream B: CPU instruction and execution optimization

- The SHA-NI line: H-02 single-stream kernel and H-01
  multi-stream kernels exist and are measured
  (EXP-002, EXP-003). Next: stream geometry (X-001 to
  X-005), hand-scheduled assembly (X-006, X-007),
  cross-phase pipelining (X-008, X-009, X-102).
- The vector line: AVX-512 and AVX2 multi-buffer prototypes
  (X-031 to X-034), the largest untested implementation
  family on this CPU.
- Runtime selection: measured per-machine dispatch
  (X-082 to X-084), extending the tune_c_threads pattern
  already in gpu/engine.py.

### Workstream C: Memory, cache, and data-handling optimization

- Maintain MEMORY_AND_CACHE_RESEARCH.md. The standing
  finding is that mining on this machine is compute and
  latency bound and that DRAM bandwidth does not bind;
  the workstream's job is to keep that finding honest as
  kernels change (spill traffic at high stream counts,
  digest store traffic, I-cache pressure of unrolled
  stream bodies: X-053 to X-058, X-109). CORRECTED by
  Phase 6 (2026-11-14): the original "not memory bound"
  phrasing is narrowed to DRAM bandwidth everywhere it
  appears; register, spill, stack and L1 state traffic
  are measured first-order costs (EXP-005, EXP-006,
  EXP-011) and belong to this workstream's research, not
  only its audit.

### Workstream D: Compiler, assembly, and automated code generation

- Compiler protocol from ../compiler_experiments.md,
  reopened for the hand kernels per R-03's own condition
  (X-043 to X-045, X-050 to X-052).
- A parameterized kernel generator and sweep driver over
  stream count, wave shape, and schedule variant
  (X-049, X-095), which is the Stage 6 automation the
  original roadmap already called for.
- SMT-verified peephole and superoptimizer passes over the
  compiled hot functions (X-048, X-091, X-092).

### Workstream E: Mining pipeline optimization

- Maintain ../mining_pipeline_optimization.md findings and
  BOTTLENECK_ANALYSIS.md here. The audit found no
  structural waste at current rates, but candidate
  construction re-work per extranonce step is real and
  coded (X-059 to X-061), and every kernel speedup
  re-prices the span, preemption, and verification
  tradeoffs (H-05, H-13, H-14 remain the governing
  entries).
- The solo server cutover (own node as work source, when
  its sync completes) is this workstream's forcing event.

### Workstream F: Automated mathematical discovery and formal verification

- Extend the prover pattern from Boolean identities to
  schedule identities and addition-tree reassociations
  (X-020, X-027, X-028, X-094).
- Maintain the refutation file: ideas that can be closed
  by derivation alone are closed cheaply and permanently
  (X-097, X-099, X-100), so implementation effort is never
  spent on them.

### Workstream G: Performance measurement, statistics, reproducibility

- Own the harness contract (../experiments/bench_harness.py)
  and the decision-run protocol (X-067).
- Measurement hygiene programme: session fingerprinting
  (X-069), steal-time covariate (X-070), paired-run design
  (X-072), minimum-detectable-effect sizing before
  micro-experiments (X-071), cross-replacement drift
  quantification (X-068).
- This workstream is the gatekeeper for every claim the
  other six produce.

## Phasing

Phase 0 (this assignment): investigation and documentation.
Complete with the eleven documents in this directory.

Phase 1: measurement hygiene and the integration decision.
The quiet-window decision re-run for H-01 streams=4
(X-067) is the single highest-value next action: it either
unlocks integration of a kernel whose medians run 1.75x to
2.6x above production, or it closes the question honestly.

Phase 2: kernel geometry. Stream counts 3, 5, 6, wave
shapes, assignment geometries, and the hand-scheduled
assembly variants, all inside the existing h02_shani
framework extended into src/.

Phase 3: the vector family. AVX-512 multi-buffer prototype
first (X-031), AVX2 second (X-033), hybrids third (X-035).

Phase 4: pipeline repricing. With a faster kernel decided,
re-run the Stage 7 tradeoffs: spans, preemption, candidate
construction caching, flags-only output end to end.

Phase 5: automation. The parameterized generator and sweep
driver (X-049) turns Phases 2 and 3 from hand-run
experiments into a standing search, with Workstream F
verification in the loop.

Phase 6: fleet questions, only if hardware appears. Per-
machine dispatch is already the design (each agent tunes
its own machine); aggregate measurement requires aggregate
machines and is not simulated.

## What success looks like at each phase

Not a hashrate promise. Success is: a registry entry with
correctness evidence, benchmark evidence with spreads, an
assembly record, and a decision with its reason. The
programme's compounding asset is the verified map of what
works on real silicon and what does not, with production
improving only when the map says it is safe.
