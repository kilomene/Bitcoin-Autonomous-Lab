# Hypothesis Registry: Y-Series (Next Research Phase, Part B)

Opened 2026-11-14 under the Next Research Phase order,
Part B. Numbering is separate from the H-series (H-01 to
H-24, research/sha256d/experiment_registry.md) and the
X-series (X-001 to X-116, HYPOTHESIS_REGISTRY.md in this
directory). Hard rule, applied to every entry below: no
renamed repeat of an H-series, X-series, or rejected
(R-01 to R-06) idea. Where an entry extends a tested
idea, the predecessor is cited and the genuinely new
element is stated. Where an entry is registered expecting
refutation, it says so; a cheap closure is a result, not
a failure of imagination.

Field key, per the phase order: Limitation (the
computational limitation targeted), Mechanism (why it
might improve performance), Formal (whether and how
mathematical equivalence is established), Impact
(expected class with justification), Test (the deciding
experiment), Success (what counts as a successful
result), plus Workstream, Difficulty, Confidence, Cost.

Claim tiers follow MASTER_RESEARCH_PLAN.md: VERIFIED
IMPROVEMENT only when measured and reproduced;
PROMISING HYPOTHESIS when plausible and untested or
unreproduced; UNPROVEN BREAKTHROUGH when substantial
investigation stands between the idea and any justified
expectation. Every entry below starts as PROMISING
HYPOTHESIS or UNPROVEN BREAKTHROUGH; none starts higher.

## Workstream A: alternative computation graphs

### Y-001: Carry-save generation of the multi-buffer message schedule
- Limitation: in the AVX-512 multi-buffer kernel the
  schedule recurrence is a 4-input addition per expanded
  word (W[t-16] + s0 + W[t-7] + s1), a chain of 3 vector
  adds on the critical path of every round group.
- Mechanism: keep schedule words in carry-save form
  (sum and carry vectors) through the recurrence and
  convert to true values only where a round consumes
  the word, collapsing the 4-input add to 2 ternlog
  full-adder steps with no carry propagation.
- Formal: exact; carry-save addition identities are
  provable by z3 bit-vector UNSAT, and the consuming
  rounds force a conversion whose correctness the
  differential gates check.
- Impact: moderate. The schedule is roughly a third of
  the multi-buffer round work; halving its add depth is
  worth a few percent if conversion costs stay low.
- Test: implement in avx512_mb.c shape, gates, bench
  against EXP-007 baseline in one interleaved session.
- Success: median above the baseline beyond session
  spread at 2 threads, with the conversion count
  reported.
- Predecessor: X-021/X-022 proposed carry-save for T1
  and for state; the new element is schedule-side
  carry-save in the vector kernel, where the addends
  are known 16 rounds early.
- Workstream A / Difficulty high / Confidence medium /
  Cost medium.

### Y-002: Four-input schedule addition via one carry-save level, costed against the add tree
- Limitation: same 4-input schedule addition as Y-001,
  but the open question is narrower: is one carry-save
  level (two ternlog ops) actually cheaper than the
  3-add tree once the sum must be materialized for the
  round that consumes it immediately?
- Mechanism: for schedule words consumed in the same
  round they are produced, carry-save defers nothing;
  the experiment prices both shapes per consumption
  distance.
- Formal: exact, same adder identities as Y-001.
- Impact: small; it decides Y-001's design point rather
  than standing alone.
- Test: microbenchmark of both schedule-generation
  shapes over the real recurrence, all distances 0..15.
- Success: a measured per-distance winner table.
- Workstream A / Difficulty low / Confidence high /
  Cost low.

### Y-003: Balanced T1 addition tree under a measured vector port model
- Limitation: T1 accumulates five operands (h, S1, Ch,
  K, W) in a compiler-chosen association that may chain
  adds serially on one port.
- Mechanism: reassociate the sum into a balanced tree
  whose shape is chosen from the port and latency data
  measured on this core, and pin the shape with
  intrinsics so the compiler cannot undo it.
- Formal: exact; modular addition is associative and
  commutative, provable by z3 in one line.
- Impact: small. The adds are not the whole round, but
  T1 sits on the dependency chain that sets the round
  latency.
- Test: two pinned tree shapes in the MB kernel, gates,
  interleaved bench.
- Success: a reproduced median gain, or a recorded
  parity that closes the idea with evidence.
- Predecessor: X-028 studied reassociation for the
  SHA-NI scalar path; the new element is the vector
  port model and the pinned intrinsic tree in MB.
- Workstream A / Difficulty low / Confidence medium /
  Cost low.

### Y-004: Bitsliced schedule, vector rounds (hybrid representation)
- Limitation: EXP-015 showed full bitslicing loses to
  ripple-carry addition cost; but the schedule's sigma
  functions are rotation-only, which bitslicing does
  for free.
- Mechanism: generate block-2 schedule words in
  bitsliced form (rotations free, additions only in
  the recurrence), convert once per group to lane form
  for the vector rounds.
- Formal: exact by construction; the conversion is a
  transpose, checked by the differential gates.
- Impact: small to moderate; bounded by the schedule
  share of total work (about a third) times the
  conversion overhead, which the test prices.
- Test: hybrid prototype, gates, bench; conversion
  cost reported separately.
- Success: end-to-end median above the EXP-007
  baseline, not just a faster schedule in isolation.
- Predecessor: EXP-015 (full bitslice, refuted by
  measurement) and X-029; the new element is the
  hybrid split at the schedule boundary.
- Workstream A / Difficulty high / Confidence low /
  Cost medium.

### Y-005: Target comparison in the transposed domain
- Limitation: every MB group pays a transpose-out
  through a [8][16] staging array even when no lane is
  near the target; at hard targets almost all of that
  work is discarded.
- Mechanism: compare in the transposed layout: the
  top digest word (word 7) across all 16 lanes is one
  vector; a mask compare against the target's top word
  rejects whole groups without extraction, and only
  surviving lanes are extracted and fully compared.
- Formal: exact; comparison of the full digest is
  lexicographic from the top word in the lab's
  little-endian integer convention, and the filter
  only skips groups provably above target.
- Impact: small at mainnet targets (extraction is
  already rare in search mode), moderate in batch mode
  and at regtest densities where extraction dominates.
- Test: batch and search benches at three target
  densities, gates including the easy-target set.
- Success: batch-mode median gain at regtest density
  with exact candidate sets preserved.
- Workstream A / Difficulty medium / Confidence high /
  Cost low.

### Y-006: Sixteen-bit split addition with carry prediction in the vector kernel
- Limitation: 32-bit vector adds carry across the
  whole word; the dependency chain of T1 waits on full
  carry propagation in the adder hardware.
- Mechanism: split each word into 16-bit halves held
  in separate lane groups; compute both carry-out
  possibilities for the high half and select, trading
  more ops for a shorter chain.
- Formal: exact; carry-select addition is a standard
  identity, z3-provable.
- Impact: speculative small; modern adders are fast
  and the op count roughly doubles, so this is
  registered as a likely refutation with a real design.
- Test: one compress variant, gates, bench.
- Success: any reproduced gain; otherwise the refutation
  is recorded with the op counts.
- Workstream A / Difficulty high / Confidence low /
  Cost medium.

### Y-007: Double-density sub-lane representation (two 16-bit halves per lane)
- Limitation: a zmm lane holds one 32-bit word; the
  register file, not the ALU width, is what stream
  experiments keep running out of.
- Mechanism: pack the low and high halves of 32 hashes
  as 64 16-bit sub-lanes; Boolean work doubles in
  density; additions need explicit cross-half carry
  handling once per add.
- Formal: exact by construction if the carry handling
  is right; the differential gates are the arbiter.
- Impact: UNPROVEN BREAKTHROUGH class: if the carry
  tax is below the density gain, this changes the
  register economics of the whole family.
- Test: prototype of one compress; measure against
  EXP-007 baseline; report the carry tax separately.
- Success: a full SHA-256d group computed correctly at
  any speed within 2x of baseline, which would justify
  optimization effort.
- Workstream A / Difficulty very high / Confidence
  low / Cost high.

### Y-008: GFNI affine decomposition search for Ch and Maj
- Limitation: Ch and Maj are not affine over GF(2), so
  the GFNI instruction cannot compute them directly;
  the open question is whether an affine pre/post
  transform pair makes the quadratic core cheaper.
- Mechanism: search for affine transforms A, B with
  Ch = A o Q o B where Q is a fixed low-cost quadratic
  form, using the same exhaustive machinery as the
  EXP-012 cone search.
- Formal: any found decomposition is verified by the
  8-row table method and z3; absence is reported as a
  bounded-search negative, not a proof of impossibility.
- Impact: negligible to small after EXP-012 (ternlog
  already computes both in one instruction); the value
  is closing the GFNI question for the Boolean cone,
  complementing X-020's schedule-sigma result.
- Test: offline search only, no kernel work unless a
  decomposition beats one ternlog.
- Success: a decomposition with total cost below the
  ternlog form, or a documented negative.
- Workstream A / Difficulty medium / Confidence low /
  Cost low.

### Y-009: Arithmetic form of Maj as an addition identity (closure candidate)
- Limitation: none after EXP-012; registered so the
  identity Maj(a,b,c) = (a + b + c - (a xor b xor c))
  / 2 is priced once and not rediscovered.
- Mechanism: the identity replaces 1 ternlog with
  about 5 arithmetic ops; it cannot win on this core.
- Formal: exact identity, z3-provable in seconds.
- Impact: negligible; closure value only.
- Test: desk check plus the z3 proof; no kernel.
- Success: the priced comparison recorded.
- Workstream A / Difficulty low / Confidence high /
  Cost low.

### Y-010: Sigma functions via VBMI2 permutes plus ternlog
- Limitation: each sigma costs 3 vprold plus a ternlog
  in the current MB codegen; vprold throughput may
  bind at high stream counts.
- Mechanism: rotations by 8, 16 and 24 are byte
  permutes (VBMI2); decompose each sigma rotation set
  into a byte-permute part and a residual bit rotation,
  and count total ops against the vprold form.
- Formal: exact; rotation decomposition is an identity
  on bit positions, table-provable per bit.
- Impact: small; only the non-byte-aligned rotations
  remain as vprold, so the saving is bounded by about
  half the rotation ops in sigmas.
- Test: op-count derivation first; kernel only if the
  count wins by at least 20 percent.
- Success: a cheaper counted sigma, then a measured
  kernel gain.
- Workstream A / Difficulty medium / Confidence
  medium / Cost medium.

### Y-011: Per-byte table-driven rounds (closure candidate)
- Limitation: table-driven SHA-256 (T-table style) is
  a recurring suggestion; on this core it converts ALU
  work into L1 traffic.
- Mechanism: none claimed; the entry exists to price
  the idea against the measured 2.739 GB/s copy floor
  and L1 behaviour before anyone builds it.
- Formal: exact by construction if built.
- Impact: negligible; expected refutation by the
  memory analysis in MEMORY_AND_CACHE_RESEARCH.md.
- Test: analytic pricing only.
- Success: the priced refutation recorded.
- Workstream A / Difficulty low / Confidence high /
  Cost low.

### Y-012: Sparse-share decomposition of the nonce word
- Limitation: the nonce enters the schedule at W3 and
  contaminates every expanded word from W18 on; there
  is no structure in how it spreads.
- Mechanism: write the nonce as the XOR of two shares,
  one of which is constant across a span; by linearity
  of the sigma functions (they are GF(2)-linear), the
  schedule contribution of the constant share is
  precomputable, and only the varying share propagates.
- Formal: the sigma functions are linear over GF(2);
  the addition carries are the nonlinear part, so the
  decomposition is exact only where carry interaction
  is handled, which the write-up must do honestly.
- Impact: speculative; the linear part of the schedule
  is the cheap part already, so this is UNPROVEN
  BREAKTHROUGH class with a concrete first step.
- Test: derive the carry-interaction cost on paper;
  kernel only if the derivation shows a net win.
- Success: a derivation with a positive net count, or
  a recorded closure.
- Workstream A / Difficulty very high / Confidence
  low / Cost medium (analysis only).

## Workstream F: automated Boolean-circuit discovery

### Y-013: Joint (Ch, Maj) cone search with shared intermediates
- Limitation: EXP-012 minimized Ch and Maj separately;
  the round computes both from overlapping inputs
  (a, b, c for Maj; e, f, g for Ch are different words,
  but S0/S1 and the cones share rotated copies).
- Mechanism: search depth-2 ternlog circuits for the
  joint output set (Ch, Maj, and the sigma XORs) with
  shared intermediate nodes, minimizing total ternlog
  count for the whole cone rather than per function.
- Formal: every candidate circuit is proven by the
  8-row table method per output plus z3 at word level.
- Impact: small; separate minima already total 1 op
  each for Ch and Maj, so sharing can only win on the
  sigma side, bounded at 1 to 2 ops per round.
- Test: offline search with the EXP-012 machinery
  extended to multi-output circuits.
- Success: a joint circuit with fewer total ops than
  the sum of separate minima, proven.
- Predecessor: X-027 and X-094 (single-function logic
  minimization, closed by EXP-012); the new element is
  the joint multi-output search.
- Workstream F / Difficulty medium / Confidence
  medium / Cost low.

### Y-014: SAT-guided rewriting of one full round, rotations and adds included
- Limitation: EXP-012's search covered only the
  Boolean cone; a full round also contains rotations
  and additions whose interaction with the cone is
  unexplored by search.
- Mechanism: encode one round as a bit-vector problem
  over the AVX-512 op library (ternlog, vprold, vpaddd,
  shifts) and let a solver-guided enumerative search
  look for a shorter equivalent sequence for the
  (state, W) to state' map on a restricted slice
  (one round, fixed W).
- Formal: equivalence by z3 UNSAT on the full 32-bit
  slice; nothing is trusted from the search itself.
- Impact: moderate if anything is found; the round is
  the atom of all 192 rounds, so even 2 ops saved per
  round is about 5 percent of the MB kernel.
- Test: offline search with a strict time budget;
  kernel only on a proven shorter sequence.
- Success: a proven sequence shorter than the current
  round, or a bounded negative.
- Predecessor: X-027 (Boolean cone only) and X-048
  (SMT peephole over the SHA-NI hot function); the new
  element is the full-round vector slice.
- Workstream F / Difficulty high / Confidence low /
  Cost medium.

### Y-015: Equality saturation (e-graph) over the round expression
- Limitation: hand and SAT searches explore small
  neighbourhoods; the rewrite space of a full round is
  larger than either covers.
- Mechanism: build an e-graph of the round expression
  with the lab's proven identities (Boolean forms,
  reassociation, ternlog tables, rotation algebra) and
  extract the minimum-cost graph under the measured
  port cost model.
- Formal: every rewrite rule in the graph is itself
  proven (z3 or table method) before admission.
- Impact: moderate, same bound as Y-014; the two are
  alternative engines for the same space and only one
  needs to win.
- Test: offline; compare extracted cost against the
  current round's op count.
- Success: a cheaper extracted round, proven, or a
  recorded saturation at the current cost.
- Workstream F / Difficulty high / Confidence medium /
  Cost medium.

### Y-016: Genetic search over schedule-generation instruction sequences
- Limitation: the MB schedule generation is a fixed
  hand structure; its instruction-level shape was
  never searched.
- Mechanism: evolve sequences of vector ops computing
  the 48 expanded words from W0..W15, fitness =
  op count plus measured throughput on a microbench,
  with a hard z3/differential equivalence gate per
  candidate.
- Formal: candidates are only accepted through the
  gate; evolution proposes, proof disposes.
- Impact: small to moderate; schedule is about a
  third of MB round work.
- Test: offline evolution with the gate; kernel only
  for a gated winner.
- Success: a gated sequence beating the current
  schedule's op count.
- Predecessor: X-093 evolved interleave orders for
  streams; the new element is sequence evolution for
  the schedule itself.
- Workstream F / Difficulty high / Confidence low /
  Cost medium.

### Y-017: Joint small-sigma search (s0 and s1 sharing rotations)
- Limitation: s0 and s1 read overlapping schedule
  words (W[t-15] feeds s0, W[t-2] feeds s1, different
  words), so sharing is limited; but the rotation sets
  {7,18,3} and {17,19,10} have no common element,
  which the search should confirm rather than assume.
- Mechanism: exhaustive search over shared-rotation
  factorizations of the pair.
- Formal: table method per output bit.
- Impact: negligible expected; closure value.
- Test: offline exhaustive check.
- Success: a shared factorization, or the recorded
  proof that none exists within the searched class.
- Workstream F / Difficulty low / Confidence high /
  Cost low.

### Y-018: Learned ranking to prune rewrite search
- Limitation: Y-014/Y-015 search spaces grow faster
  than exhaustive methods; most candidates are losers.
- Mechanism: train a cheap ranker on the outcomes of
  past searches (this lab's EXP records) to order
  candidates by expected gain before the expensive
  proof and bench steps.
- Formal: no correctness role; the ranker only orders,
  the gates still decide.
- Impact: small and indirect; it multiplies the value
  of the other search entries if it works.
- Test: replay past searches and measure rank quality
  against recorded outcomes.
- Success: the ranker beats random ordering on replay
  by a stated margin.
- Workstream F / Difficulty medium / Confidence
  medium / Cost low.

### Y-019: Automatic proof obligations per transformation
- Limitation: every experiment in this programme so
  far hand-built its verification; the cost of proof
  is a recurring tax on discovery speed.
- Mechanism: a harness that, given a candidate kernel
  diff at the expression level, generates the z3
  obligations, the differential plan, and the gate
  script automatically.
- Formal: the harness generates obligations; z3 and
  the gates still discharge them.
- Impact: small in rate terms, large in throughput of
  experiments per week; classified as infrastructure.
- Test: regenerate the EXP-012 and EXP-014 verifications
  through the harness and compare with the hand-built
  ones.
- Success: identical verdicts with less hand work.
- Workstream F / Difficulty medium / Confidence high /
  Cost medium.

### Y-020: IFMA-domain add/XOR identities (closure candidate)
- Limitation: AVX-512 IFMA operates on 52-bit limbs;
  SHA-256 is 32-bit modular arithmetic, and the
  packing overhead was already argued in X-037.
- Mechanism: none claimed beyond completing the
  argument with a priced packing design for the T1
  chain specifically.
- Formal: exact if built; the pricing is analytic.
- Impact: negligible; closure.
- Test: analytic pricing.
- Success: the recorded closure.
- Workstream F / Difficulty low / Confidence high /
  Cost low.

### Y-021: Fused (S1, Ch) cone search
- Limitation: S1 and Ch both consume e (with f, g);
  they are computed as separate cones in every kernel
  so far.
- Mechanism: search for a joint circuit producing
  (S1, Ch) from (e, f, g) with shared rotated copies
  of e: the rotations of e are computed once either
  way, so the search targets the Boolean combination
  stage only.
- Formal: table method plus z3, as EXP-012.
- Impact: small; bounded by 1 to 2 ops per round.
- Test: offline search.
- Success: a proven joint cone cheaper than the
  separate cones' sum.
- Workstream F / Difficulty medium / Confidence
  medium / Cost low.

### Y-022: Partial evaluation of the outer-block schedule in MB
- Limitation: the outer block's schedule words
  W9..W15 are constants (padding and length), and
  several expanded words are sums involving only
  constants and the first inner-state words; the MB
  kernel computes the full recurrence anyway.
- Mechanism: expand the outer schedule symbolically
  per group and constant-fold every addend that does
  not depend on the inner digest, in the vector kernel.
- Formal: exact; the folding is the same recurrence
  with constants substituted, checked by the gates.
- Impact: small; the outer schedule is about a sixth
  of per-nonce work, and only part of it folds.
- Test: symbolic expansion offline, then a kernel
  variant, gates, bench.
- Success: a measured gain, or a priced parity.
- Predecessor: X-023 proposed outer schedule partial
  evaluation as analysis in the SHA-NI context; the
  new element is the MB implementation and measurement.
- Workstream A / Difficulty medium / Confidence
  medium / Cost medium.

## Workstream B: advanced AVX-512 multi-buffer scheduling

### Y-023: Register-resident dual-batch MB (full unroll)
- Limitation: EXP-011's dual-batch compress body
  (239 instructions) still carries 48 vmovdqa64: both
  batches' state and schedule rings live in memory, so
  the interleave hides round latency but pays stack
  traffic per round.
- Mechanism: fully unroll the dual compress so both
  batches' a..h and schedule windows are register
  resident; 32 zmm of state plus schedule is beyond
  the 32-register file once K and temporaries count,
  so the design question is which subset stays resident
  and which spills cheapest.
- Formal: exact by construction; gates decide.
- Impact: moderate to large; this is the direct
  continuation of the batch's strongest signal
  (EXP-011) against its measured cost.
- Test: unrolled variant, assembly audit first (spill
  count is the primary metric), gates, bench.
- Success: spill traffic per dual round clearly below
  EXP-011's, and a reproduced median above mb16.
- Predecessor: EXP-011 (dual batch, rolled); the new
  element is the register residency design.
- Workstream B / Difficulty high / Confidence medium /
  Cost medium.
- Status: RUN as EXP-018 (2026-11-14). Residency
  achieved at the near-zero level: the shipped
  eight-round ring-relabeled body (src/
  avx512_mb_reg.c) homes exactly one of sixteen
  state vectors in a single stack slot; a full
  64-round unroll was compiled first and spilled
  heavily (214 spill-region accesses), which is
  the measured answer to this entry's design
  question: the register file holds the design
  only when live ranges are kept short. Rate:
  adjusted pooled +0.0836 vs single-batch MB
  (CI -0.0247 to +0.1902), not significant, so
  state traffic was not the binding cost and
  Y-023 is not a verified improvement. Tier:
  PROMISING HYPOTHESIS with measured support.
  Full record: ../phase6/EXPERIMENT_RESULTS.md,
  EXP-018.

### Y-024: Triple-batch MB interleave (spill cliff locator)
- Limitation: the MB family's interleave depth is
  unmapped beyond 2 batches (EXP-011); SHA-NI streams
  peaked at 4 with heavy spills (EXP-005).
- Mechanism: three interleaved 16-lane batches per
  worker; expected to fall off the register cliff,
  which is itself the measurement that bounds Y-023.
- Formal: exact by construction.
- Impact: small directly; it prices the cliff for the
  whole family.
- Test: extend the dual walker to 3 batches, gates,
  bench, assembly audit.
- Success: the cliff location recorded with numbers.
- Workstream B / Difficulty medium / Confidence high /
  Cost low.

### Y-025: Schedule-ahead distance sweep in MB
- Limitation: the MB schedule is generated just in
  time inside each round; whether generating it d
  rounds ahead (d = 1..8) hides its latency is
  unmeasured in this family.
- Mechanism: parameterize the generation distance in
  the compress loop and sweep it; the schedule ring
  positions shift, the arithmetic is identical.
- Formal: exact by construction.
- Impact: small to moderate; latency effects were the
  whole story in the SHA-NI family (EXP-003).
- Test: parameterized kernel, sweep, gates per point.
- Success: a distance with a reproduced median above
  distance 0, or a flat curve recorded.
- Predecessor: X-116 named schedule prefetch distance
  in MB as a note and X-010 did ahead-distance in the
  SHA-NI kernel; the new element is the MB sweep.
- Workstream B / Difficulty medium / Confidence
  medium / Cost medium.

### Y-026: Heterogeneous-width batching (zmm batch plus ymm batch in one worker)
- Limitation: a worker running one zmm batch uses
  the wide pipes at one batch's latency; a second
  full zmm batch (EXP-011) doubles register demand.
- Mechanism: interleave one 16-lane zmm batch with
  one 8-lane ymm batch (AVX-512VL forms of the same
  ops); the narrow batch adds latency hiding at half
  the register cost.
- Formal: exact by construction.
- Impact: moderate if the register economics work;
  bounded by the narrow batch's throughput share.
- Test: mixed-width compress, gates, bench.
- Success: total per-worker median above both the
  single zmm batch and EXP-011's dual at equal
  accounting.
- Workstream B / Difficulty high / Confidence medium /
  Cost medium.

### Y-027: Two 8-lane half-width batches interleaved
- Limitation: same register pressure question as
  Y-026 from the other side: two independent 8-lane
  batches (ymm) may interleave better than one
  16-lane batch because their state fits registers
  with room to spare.
- Mechanism: dual 8-lane MB with register-resident
  state; compare against 16-lane single and dual.
- Formal: exact by construction.
- Impact: moderate; this is the MB analogue of the
  EXP-005 geometry sweep, at lane granularity.
- Test: 8-lane variant with dual mode, gates, bench.
- Success: a per-worker median above the 16-lane
  single batch, reproduced.
- Workstream B / Difficulty medium / Confidence
  medium / Cost medium.

### Y-028: Mask-predicated partial groups (closure candidate)
- Limitation: partial MB groups compute dummy lanes
  at full cost; AVX-512 masks can predicate the ops.
- Mechanism: masked forms of the round ops for the
  tail group; the expectation is that masked-off
  lanes cost the same issue slots, making this a
  closure, but the power and port behaviour on this
  core is unmeasured.
- Formal: exact; masks only suppress lanes whose
  outputs are discarded, and accounting already
  separates coverage from backend computations.
- Impact: negligible expected; closure value.
- Test: masked tail variant, gates, bench at counts
  chosen to stress partial groups.
- Success: the measured answer, either way.
- Predecessor: X-042 proposed masks for SHA-NI wave
  tails; the new element is the MB tail measurement.
- Workstream B / Difficulty medium / Confidence high /
  Cost low.

### Y-029: In-register transpose between block 2 and the outer hash
- Limitation: every MB group stores the inner state
  to a [8][16] staging array and loads it back as the
  outer schedule's first words (v_group in
  avx512_mb.c), a store/load round trip per group.
- Mechanism: the outer schedule needs the state words
  in word-major order, which is exactly the layout
  the compress already holds in registers; the only
  reason for staging is the scalar digest extraction
  at the end. Feed the outer compress directly from
  the block-2 output registers and extract once.
- Formal: exact; it is a data-movement change only.
- Impact: small to moderate; 16 vector stores plus 16
  loads per 16 hashes is about 2 memory ops per hash
  removed from the hot path.
- Test: restructured group function, gates, bench.
- Success: a reproduced median gain, or parity with
  the staging cost priced.
- Workstream B / Difficulty medium / Confidence
  high / Cost medium.

### Y-030: Group-strided nonce assignment for finer search granularity
- Limitation: MB search is group-atomic over 16
  consecutive nonces; the attempted overshoot at a
  hit averages half a group, and at easy targets the
  overshoot is real work.
- Mechanism: assign lane l of group g the nonce
  base + g + 16*l (strided across groups) so a span
  drains more evenly and stop checks land on finer
  effective boundaries; coverage stays exact and
  disjoint by construction.
- Formal: exact; a permutation of the nonce space.
- Impact: small; it prices overshoot, which EXP-009
  bounded but did not eliminate.
- Test: strided group mode, gates with wave-exact
  accounting for the new geometry, bench at two
  target densities.
- Success: lower attempted overshoot at equal rate,
  or a recorded parity.
- Predecessor: X-004/EXP-005 strided assignment in
  the SHA-NI stream family; the new element is
  group-level striding in MB.
- Workstream B / Difficulty low / Confidence medium /
  Cost low.

### Y-031: Fused outer-of-n with block-2-of-n+1 in the vector family
- Limitation: EXP-008 found no phase premium in the
  SHA-NI family because both phases use the same
  round machinery; the vector family's phases have
  different widths of live state, so the question is
  genuinely open here.
- Mechanism: pipeline one group's outer compression
  against the next group's block-2 compression in
  one worker, interleaved at round granularity.
- Formal: exact by construction.
- Impact: small expected (the EXP-008 prior is
  negative); registered because the register profile
  differs enough that the prior does not settle it.
- Test: fused group walker, gates, bench.
- Success: a reproduced gain, or the second negative
  that closes phase fusion across families.
- Predecessor: X-009/EXP-008 (SHA-NI phase pipeline,
  parity); the new element is the vector family.
- Workstream B / Difficulty high / Confidence low /
  Cost medium.

### Y-032: Vectorized block-1 for short-span amortization
- Limitation: block 1 is scalar per template; at
  short spans (small pools of work, frequent template
  churn) its cost is not amortized and the scalar
  path is the slowest code in the building.
- Mechanism: compute the midstate with the vector
  kernel itself (one lane used) or a SHA-NI compress,
  and price the crossover span where it matters.
- Formal: exact; same compression, different engine.
- Impact: negligible at mining span sizes; small in
  churn-heavy solo-server shapes.
- Test: span-size sweep with template setup priced
  per span (extends EXP-009's span work to setup).
- Success: the crossover span recorded with numbers.
- Workstream B / Difficulty low / Confidence high /
  Cost low.

### Y-033: Register-resident schedule ring via full unroll (single batch)
- Limitation: the rolled MB compress carries its
  16-word schedule ring in memory (part of the 24
  vmovdqa64 in the 116-instruction loop body).
- Mechanism: fully unroll one batch's compress so
  the ring lives in registers across all 64 rounds;
  code size grows by about 64x for the compress,
  which prices the instruction-cache side.
- Formal: exact by construction.
- Impact: moderate; this is Y-023's single-batch
  sibling and the two should be measured together to
  separate unroll gains from interleave gains.
- Test: unrolled variant, assembly audit (code size,
  spills), gates, bench.
- Success: a reproduced gain with code size reported.
- Workstream B / Difficulty medium / Confidence
  medium / Cost medium.

### Y-034: Sigma rotations by shift pairs under port pressure
- Limitation: the sigma functions use vprold; if the
  rotate port is the binding constraint at high
  interleave, shift-pair decomposition (2 shifts +
  1 or, or a ternlog) could rebalance ports.
- Mechanism: replace vprold with shift pairs in the
  sigma cones only, and measure; total ops rise, so
  this wins only under a proven port bound.
- Formal: exact; rotation = (x >> n) | (x << (32-n))
  is an identity, z3-provable.
- Impact: small; a port-rebalancing bet.
- Test: variant compress, gates, bench; port story
  stated before running.
- Success: a reproduced gain, or the port hypothesis
  weakened with numbers.
- Predecessor: X-036 asked shuffle versus vprold;
  the new element is shift-pair decomposition under
  an explicit port model.
- Workstream B / Difficulty low / Confidence medium /
  Cost low.

### Y-035: Next-template header prefetch during the span tail
- Limitation: template switches stall the walker
  while the next header and template struct are
  built; at high kernel rates the stall fraction
  grows (EXP-009 interaction).
- Mechanism: prefetch and prebuild the next template
  during the last groups of the current span, in the
  walker, not the pipeline.
- Formal: exact; scheduling only.
- Impact: small; bounded by the setup cost measured
  in Y-032.
- Test: walker variant, end-to-end bench with
  template churn at several rates.
- Success: churn-shaped end-to-end gain.
- Workstream E / Difficulty medium / Confidence
  medium / Cost low.

### Y-036: In-vector top-word target pre-filter for search
- Limitation: MB search extracts and scalar-checks
  lanes group by group; at regtest densities the
  extraction and hashlib confirmation path is the
  binding interaction (EXP-009).
- Mechanism: compare digest word 7 across lanes in
  vector form (the digest's top word in the lab's
  comparison convention), extract only lanes whose
  top word is at or below the target's, and confirm
  those with the full comparison.
- Formal: exact; the full comparison is monotone in
  the top word first, so the filter never drops a
  true candidate (the same argument as Y-005, in the
  search path instead of batch).
- Impact: moderate at regtest and easy-target
  densities, negligible at mainnet difficulty;
  registered with that scope stated.
- Test: search variant, gates at three densities,
  bench of search (not batch) throughput.
- Success: search-mode gain at easy density with
  exact candidate sets.
- Workstream B / Difficulty medium / Confidence
  high / Cost medium.

## Workstream B/D: new multi-stream arrangements

### Y-037: Heterogeneous worker: SHA-NI streams fused with an MB batch in one thread
- Limitation: the two kernel families peak under
  different resources (SHA-NI streams on the SHA
  pipes, MB on the vector pipes); a single-family
  worker leaves the other family's pipes idle.
- Mechanism: one thread time-slices a 2-stream
  SHA-NI kernel and a 16-lane MB batch at group
  granularity, aiming for pipe-level complementarity.
- Formal: exact by construction; both kernels are
  already gate-verified separately.
- Impact: moderate to large if the pipes are truly
  disjoint on this core; that premise is the thing
  being tested.
- Test: fused worker, gates on both paths, bench
  against each family alone at equal total accounting.
- Success: per-worker median above the better family
  alone, reproduced.
- Predecessor: X-077 heterogeneous workers (across
  threads); the new element is within one thread.
- Workstream B / Difficulty high / Confidence medium /
  Cost high.

### Y-038: Shared schedule builder for SHA-NI streams
- Limitation: every SHA-NI stream builds its own
  block-2 schedule with MSG instructions; the
  schedules differ only in the nonce word from W18
  onward in structure, and rounds 0..17 are shared.
- Mechanism: build the shared schedule prefix once
  (already EXP-013's finding in MB) and, beyond it,
  batch the per-stream schedule generation for 4
  streams into one vector pass that feeds the SHA-NI
  rounds.
- Formal: exact; schedule words are schedule words,
  whichever engine computes them, gates decide.
- Impact: small to moderate; bounded by the schedule
  share of SHA-NI work (EXP-002 priced MSG vs scalar
  at 2.6x, so schedule method matters in this family).
- Test: hybrid prototype, gates, bench.
- Success: a reproduced gain over EXP-005's champion
  geometry.
- Workstream B / Difficulty very high / Confidence
  low / Cost high.

### Y-039: MB lanes as the schedule engine for SHA-NI streams
- Limitation: the mirror image of Y-038: the vector
  unit is idle during SHA-NI stream work.
- Mechanism: the MB kernel computes full block-2
  schedules for 16 future SHA-NI nonces per pass
  while SHA-NI streams consume earlier schedules;
  a producer-consumer pair inside one thread,
  alternating at group granularity.
- Formal: exact by construction and gates.
- Impact: speculative; the alternation overhead may
  eat the gain, which is why it is separate from
  Y-038 (different data flow, different cost shape).
- Test: alternating prototype, gates, bench.
- Success: end-to-end per-worker gain over streams
  alone.
- Workstream B / Difficulty very high / Confidence
  low / Cost high.

### Y-040: Adaptive stream count across a span (drain-down geometry)
- Limitation: fixed stream counts pay full wave
  overshoot at span tails and at early exits
  (EXP-005 priced wave atomicity).
- Mechanism: run the span body at the best stream
  count, then drain the tail at 2 and 1 streams so
  the last waves are small; attempted accounting
  stays exact per segment.
- Formal: exact; a partition of the nonce space into
  segments with different geometries.
- Impact: small; matters most at short spans and
  easy targets.
- Test: adaptive walker, gates including tail
  boundaries, bench across span sizes.
- Success: lower overshoot at equal or better rate.
- Workstream B / Difficulty medium / Confidence
  medium / Cost low.

### Y-041: Per-stream hit channels (finer stop granularity)
- Limitation: wave-atomic publication means a hit
  waits for its whole wave (EXP-003/EXP-005
  accounting); at dense targets the extra hashes are
  measurable.
- Mechanism: each stream checks a per-stream stop
  flag between round groups, not just at wave
  boundaries, with the attempted count defined as
  the sum of per-stream examined counts.
- Formal: exact; the winner is still a full SHA-256d
  at or under target, and the accounting definition
  is stated before measuring.
- Impact: small; a latency and accounting refinement,
  not a rate change at hard targets.
- Test: variant walker, gates with the new accounting
  asserted exactly, bench at regtest density.
- Success: reduced attempted overshoot with the new
  semantics proven on the genesis probe.
- Predecessor: X-075 stop-flag granularity (named,
  untested); the new element is the per-stream
  channel design and its accounting proof.
- Workstream B / Difficulty medium / Confidence
  medium / Cost low.

### Y-042: Two workers sharing one MB batch ring (closure candidate)
- Limitation: none established; registered because
  shared-ring designs recur in mining code and their
  false-sharing cost on this VM is unmeasured.
- Mechanism: two threads pull groups from one shared
  batch context; the expectation is that lock and
  cache-line contention loses to the current
  per-worker partition (bal_partition).
- Formal: exact by construction.
- Impact: negligible expected; closure value.
- Test: shared-ring walker, gates, bench at 2
  threads against the partitioned baseline.
- Success: the measured comparison, either way.
- Workstream B / Difficulty medium / Confidence
  high / Cost low.

### Y-043: Dual-batch interleave granularity sweep
- Limitation: EXP-011 interleaved at round
  granularity (A round t, B round t); coarser
  alternation (blocks of 2, 4, 8 rounds) trades
  latency hiding against instruction-cache and
  register locality, and the optimum is unknown.
- Mechanism: parameterize the alternation block size
  in the dual compress and sweep it.
- Formal: exact by construction.
- Impact: small to moderate; a cheap sweep on top of
  the batch's most promising kernel.
- Test: parameterized dual kernel, gates per point,
  bench.
- Success: a block size with a reproduced median
  above round granularity, or a flat curve recorded.
- Predecessor: EXP-011 fixed round granularity; the
  new element is the granularity parameter.
- Workstream B / Difficulty low / Confidence medium /
  Cost low.

### Y-044: Multi-template streams in one worker
- Limitation: solo-server shapes serve several jobs
  at once; today each worker owns one template, so
  template diversity costs whole workers.
- Mechanism: streams within one worker carry
  different templates (different midstates and
  schedule prefixes), sharing only the round code.
- Formal: exact by construction; per-stream template
  state is independent.
- Impact: small for rate, moderate for the solo
  server's job-serving shape; registered under the
  whole-path rule.
- Test: multi-template stream variant, gates with
  mixed templates, bench at 2 and 4 job mixes.
- Success: aggregate rate at mixed templates within
  a few percent of the single-template rate.
- Predecessor: X-104 multi-template single-call API;
  the new element is stream-level template diversity.
- Workstream E / Difficulty medium / Confidence
  medium / Cost medium.

### Y-045: Ping-pong wave double-buffering in H-01
- Limitation: winner publication and wave setup
  serialize with hashing at wave boundaries in the
  stream walker.
- Mechanism: double-buffer the wave state so the
  next wave's setup overlaps the current wave's
  tail; publication moves off the critical path.
- Formal: exact; scheduling only.
- Impact: small; bounded by the wave-boundary cost
  share, which EXP-009's span data bounds below
  0.1 percent at production spans, so this is a
  short-span refinement only.
- Test: walker variant, bench across span sizes.
- Success: a gain at short spans, or the priced
  parity.
- Workstream B / Difficulty medium / Confidence
  medium / Cost low.

### Y-046: Kernel-family partitioning of the nonce space by range shape
- Limitation: dispatch today is per-process (one
  backend per run); nothing assigns range shapes to
  families (long ranges to MB, short tails to
  streams).
- Mechanism: a dispatcher that splits each span by
  length: bulk to the MB kernel, the sub-group tail
  to a stream kernel, eliminating dummy-lane work
  and wave overshoot at boundaries.
- Formal: exact; a partition of the nonce space.
- Impact: small; bounded by tail fractions, which
  shrink as spans grow.
- Test: dispatcher prototype over the existing
  libraries, gates, bench across span sizes.
- Success: end-to-end gain at realistic span mixes.
- Workstream E / Difficulty medium / Confidence
  medium / Cost medium.

## Workstream D: instruction-sequence superoptimisation and codegen

### Y-047: Bounded superoptimizer for one SHA-NI round pair
- Limitation: the H-02 round pair (2 RNDS2 plus the
  schedule and shuffle glue) was hand-written; its
  glue sequence was never searched.
- Mechanism: enumerative superoptimization over the
  glue instruction set (ALIGNR, shuffles, MOVs) for a
  fixed round pair, with z3 equivalence on the pair's
  input-output map.
- Formal: z3 UNSAT per candidate; the search proposes,
  the proof disposes.
- Impact: small; glue is a minor share next to RNDS2
  itself, bounded by the H-02 assembly record.
- Test: offline search with a stated bound; kernel
  only on a proven shorter glue.
- Success: a proven shorter sequence, or a bounded
  negative.
- Predecessor: X-091 searched inter-pair shuffles;
  the new element is the full glue set with RNDS2 in
  the frame.
- Workstream D / Difficulty high / Confidence low /
  Cost medium.

### Y-048: Superoptimizer for the MB T1 addition chain under a port model
- Limitation: T1's five-operand sum is compiler
  associated; Y-003 pins a tree by hand, but the
  space of associations times operand orders is
  larger than hand search.
- Mechanism: enumerate associations and operand
  orders, score by the measured port/latency model,
  verify the winner's equivalence by the associativity
  proof, and pin it.
- Formal: exact; modular addition algebra, z3.
- Impact: small; T1 chain length is one component of
  round latency.
- Test: offline enumeration plus one pinned kernel.
- Success: a pinned shape beating the compiler's,
  reproduced, or parity recorded.
- Workstream D / Difficulty medium / Confidence
  medium / Cost low.

### Y-049: Enumerated register assignment for the unrolled 2-stream kernel
- Limitation: EXP-006 showed hand scheduling loses
  to the compiler at 2 streams in the schedule-first
  shape; the assignment space was sampled, not
  enumerated.
- Mechanism: generate the 2-stream unrolled kernel
  under a grid of explicit register assignments
  (via a parameterized generator), gate each, and
  bench the survivors.
- Formal: exact by construction per candidate.
- Impact: moderate if any assignment beats the
  compiler's; the prior (EXP-006) is negative, so
  confidence is low and the cost is capped by the
  generator doing the work.
- Test: generator plus sweep, assembly audit per
  survivor.
- Success: one assignment with a reproduced gain,
  or the assignment space closed with data.
- Predecessor: X-006/X-007 (manual assembly) and
  X-049 (parameterized generator, untested); the new
  element is the assignment grid over the unrolled
  2-stream body.
- Workstream D / Difficulty high / Confidence low /
  Cost medium.

### Y-050: Measured uop latency table as the scheduling ground truth
- Limitation: every scheduling hypothesis in this
  programme reasons about latencies it has not
  measured on this core (perf counters are absent in
  this guest).
- Mechanism: build latency and throughput tables for
  the ~20 instructions the kernels use, from timed
  dependency chains and independent streams (the
  freq_gate.c pattern extended), and publish them as
  the cost model other entries consume.
- Formal: not an equivalence question; it is a
  measurement method with stated error bars.
- Impact: indirect but broad; it converts several
  PROMISING entries' reasoning into priced claims.
- Test: the table itself, cross-validated by
  predicting two known kernel rates within a stated
  tolerance.
- Success: predictions within tolerance, or the
  method's limits recorded.
- Workstream G / Difficulty medium / Confidence
  high / Cost medium.

### Y-051: Source-parameter sweep for the MB compress (unroll, inline, ring placement)
- Limitation: EXP-001 closed compiler flags for the
  production wrapper, and X-045 reopened them only
  narrowly; the MB compress's source-level parameters
  (unroll factor, ring in array vs struct, inline
  depth) are a different, untested space.
- Mechanism: a build matrix over source parameters
  (not flags alone), each variant gated and benched
  in one session.
- Formal: exact by construction per variant.
- Impact: small to moderate; compiler interaction
  effects of this size have appeared before
  (EXP-006's inline asymmetry).
- Test: the matrix, with assembly audits.
- Success: a parameter point beating the shipped
  shape, reproduced.
- Workstream D / Difficulty low / Confidence medium /
  Cost medium.

### Y-052: Assembly-profile regression gate for research kernels
- Limitation: kernel performance here is a property
  of generated code that silently changes with
  compiler and flags; EXP-012 showed the compiler
  had already made a key optimization once, invisibly.
- Mechanism: a check that diffs each research
  library's hot-function instruction profile against
  its recorded profile and fails loudly on drift.
- Formal: not applicable; it is an integrity check.
- Impact: indirect; it protects every future
  comparison in the programme.
- Test: run against the current tree; the recorded
  profiles are the EXP-002/007/011..015 audits.
- Success: the gate exists, passes on the current
  tree, and catches an injected drift in testing.
- Workstream G / Difficulty low / Confidence high /
  Cost low.

### Y-053: Hot/cold layout for the MB walker
- Limitation: the MB walker inlines both compresses
  into a large body (the x512/k512 builds inline
  everything into v_walk); code placement effects on
  this core are unmeasured for this family.
- Mechanism: section-split the walker's cold paths
  (setup, publication) from the hot loop and measure.
- Formal: exact; layout only.
- Impact: small expected; the SHA-NI family's X-051
  was inconclusive, and this is the MB counterpart.
- Test: layout variant, bench, code-size report.
- Success: a reproduced gain or a recorded parity.
- Workstream D / Difficulty low / Confidence medium /
  Cost low.

### Y-054: Superoptimized digest extraction for MB groups
- Limitation: group exit transposes 16 digests
  through memory (see Y-029); where extraction is
  still needed, its instruction sequence is
  compiler-default.
- Mechanism: search vpermt2d-based extraction
  sequences that produce the [lane][word] layout
  with fewer ops than the store/load staging.
- Formal: exact; a permutation is a permutation,
  verified by the gates' digest comparisons.
- Impact: small; pairs with Y-029 (if Y-029 lands,
  this prices what remains).
- Test: offline sequence search, then a group-exit
  variant, gates, bench.
- Success: fewer extraction ops and a measured gain
  at batch shapes.
- Workstream D / Difficulty medium / Confidence
  medium / Cost medium.

## Workstream B/F: register pressure and dependency chains

### Y-055: State rematerialization in the MB round (closure candidate)
- Limitation: all 8 state words are live across each
  round; rematerializing a word instead of keeping
  it would free a register.
- Mechanism: the state update is a rotation of words
  with two additions; no word is a cheap function of
  the others, so rematerialization has nothing to
  recompute from. Registered to close the idea with
  the dependency argument written down.
- Formal: the closure is a dependency argument, not
  a transformation.
- Impact: negligible; closure.
- Test: desk argument only.
- Success: the recorded closure.
- Workstream B / Difficulty low / Confidence high /
  Cost low.

### Y-056: Schedule generation distance in a single MB batch
- Limitation: distinct from Y-025 (dual-batch
  pipelining): in a single batch the just-in-time
  schedule word feeds T1 immediately, putting the
  schedule's add chain directly on the round's
  critical path.
- Mechanism: generate schedule words k rounds ahead
  into the ring (k = 1..4) so the T1 chain starts
  from a ready word; identical arithmetic, different
  timing.
- Formal: exact by construction.
- Impact: small to moderate; this is the single-batch
  version of the latency story that ran the SHA-NI
  family.
- Test: parameterized compress, sweep, gates.
- Success: a k with a reproduced gain, or flatness
  recorded.
- Workstream B / Difficulty low / Confidence medium /
  Cost low.

### Y-057: One-round-ahead Boolean precompute for Ch
- Limitation: Ch for round t+1 needs e(t+1), which
  depends on T1(t); but f and g for t+1 are known a
  round early, and Ch's alt form g ^ (e & (f ^ g))
  has a subexpression (f ^ g) that is fully known
  early.
- Mechanism: compute (f ^ g) for the next round
  during the current round's schedule slot, leaving
  Ch at 2 ops on the critical path instead of 3 in
  classic form (or 1 ternlog now; the entry survives
  as a latency argument for non-ternlog targets and
  as a chain-shortening in the scalar family).
- Formal: exact; the alt form is already proven
  (tools/boolean_proof.py).
- Impact: negligible on AVX-512 after EXP-012;
  small on SHA-NI-adjacent scalar paths. Registered
  with that scope.
- Test: desk derivation plus a scalar-path variant
  only if the derivation shows a chain shortening.
- Success: the priced derivation.
- Workstream A / Difficulty low / Confidence high /
  Cost low.

### Y-058: Carry-select T1 addition in the vector kernel
- Limitation: the T1 dependency chain includes a
  full 32-bit add of (h + S1 + Ch) with (K + W);
  adder latency is on the round's critical path.
- Mechanism: split the final T1 add into 16-bit
  halves with both carry possibilities computed in
  parallel and selected by the low half's carry,
  shortening the serial chain at the cost of extra
  ops (the vector version of Y-006, applied only to
  the final add rather than all adds).
- Formal: exact; carry-select identity, z3.
- Impact: speculative small; op count rises, chain
  shortens, the trade is empirical.
- Test: one compress variant, gates, bench.
- Success: a reproduced gain, or the trade priced
  and closed.
- Workstream B / Difficulty high / Confidence low /
  Cost medium.

### Y-059: Schedule word rematerialization versus ring storage
- Limitation: the MB ring keeps 16 schedule vectors
  live; at high interleave the ring is what spills
  (EXP-011's mov count).
- Mechanism: for the deepest interleave shapes,
  recompute selected schedule words from their
  recurrence inputs instead of loading them from
  the spilled ring, trading ALU ops for stack
  traffic at a measured exchange rate.
- Formal: exact; recomputation is the same recurrence.
- Impact: moderate in the dual/triple shapes if the
  exchange rate favours ALU on this core.
- Test: dual-batch variant with rematerialized
  W[t-7] (the deepest ring read), gates, bench,
  assembly audit.
- Success: fewer stack ops and a reproduced gain.
- Workstream B / Difficulty high / Confidence
  medium / Cost medium.

### Y-060: Feed-forward folded into the final round
- Limitation: each compress ends with 8 separate
  vector adds (feed-forward) that sit between the
  phases of every group.
- Mechanism: fold the feed-forward add of the input
  state into the final round's T1/T2 bookkeeping
  where the algebra allows (the last round's a and
  e updates can absorb the input word for their
  positions; the other six still need adds, so the
  saving is partial and must be derived, not assumed).
- Formal: exact where the derivation holds; z3 on
  the affected positions.
- Impact: negligible to small (at most 8 of ~1800
  ops per group); registered for completeness of
  the op census.
- Test: derivation first; kernel only if the fold
  covers at least 4 of 8 positions.
- Success: the derivation, and a gain if built.
- Workstream A / Difficulty medium / Confidence
  medium / Cost low.

### Y-061: Alternating state orientation in the MB round
- Limitation: the MB round renames state words
  every round (h=g, g=f, ...); in the rolled loop
  these are register moves the compiler mostly
  eliminates, but in unrolled variants they become
  real copies.
- Mechanism: alternate the logical orientation each
  round (two round-body forms) so the rename is a
  compile-time relabelling with zero copies, in the
  unrolled shapes of Y-023/Y-033.
- Formal: exact; relabelling.
- Impact: small, and only inside unrolled variants;
  it is a component of those designs, registered
  separately so its effect can be isolated.
- Test: unrolled variant with and without
  alternation, assembly audit (mov count), bench.
- Success: the isolated mov and rate deltas.
- Predecessor: X-012 (alternating orientation for
  RNDS2 packing); the new element is the vector
  unrolled body.
- Workstream B / Difficulty medium / Confidence
  high / Cost low.

### Y-062: Stall-proxy instrumentation for dependency audits
- Limitation: with no perf counters in this guest,
  dependency-chain claims (including several in this
  registry) rest on reasoning, not observation.
- Mechanism: build kernel variants with deliberate
  serialization points (a dependent dummy op at a
  chosen round position) and measure the rate cost
  curve; the curve's shape identifies where the
  chain actually binds.
- Formal: not an equivalence question; a measurement
  method. The instrumented variants are never
  benchmarked as candidates.
- Impact: indirect; it disciplines Y-050's cost
  model and every latency claim in the programme.
- Test: the cost curve for the MB round at several
  insertion points.
- Success: a curve consistent (or inconsistent)
  with the latency story, recorded either way.
- Workstream G / Difficulty medium / Confidence
  medium / Cost medium.

### Y-063: Operand order forcing for bypass-friendly T2
- Limitation: T2 = S0 + Maj feeds only the a update,
  while T1 feeds both; if the adder scheduling makes
  T2 wait on T1's operands, the a chain lengthens.
- Mechanism: force T2's computation to issue before
  T1's final add via intrinsic ordering in a pinned
  variant (the compiler may already do this; the
  assembly audit decides whether there is anything
  to force).
- Formal: exact; ordering only.
- Impact: negligible expected; the audit is the
  deliverable.
- Test: assembly audit first; variant only if the
  audit shows T2 late.
- Success: the audit verdict.
- Workstream B / Difficulty low / Confidence high /
  Cost low.

### Y-064: Split-zmm dual batch (two 8-lane batches in one zmm's halves)
- Limitation: distinct from Y-027 (ymm halves via
  VL forms): a zmm batch's lanes are independent,
  so one 16-lane batch can be run as two 8-lane
  sub-batches with independent schedules inside the
  same registers, if the schedule generation is
  restructured per half.
- Mechanism: schedule words for the two halves are
  computed with the same vector ops (the halves
  share op issue), so the gain would come only from
  independent state progression; the honest prior is
  that this is identical work, and the entry exists
  to record why lane splitting inside one register
  is not interleaving.
- Formal: exact by construction.
- Impact: negligible expected; closure with a
  mechanism-level argument.
- Test: desk argument; kernel only if the argument
  fails to close it.
- Success: the recorded closure.
- Workstream B / Difficulty low / Confidence high /
  Cost low.

## Workstream A: message-schedule restructuring

### Y-065: Nonce-affine schedule decomposition in MB (rounds 18 and up)
- Limitation: from W18 on, every schedule word is a
  sum mixing template constants with nonce-dependent
  terms, and the vector kernel recomputes the whole
  sum per nonce group.
- Mechanism: the small sigmas are GF(2)-linear, so
  each expanded word decomposes as W[t] = C[t] +
  L[t](nonce part) + carry corrections, where C[t]
  is a per-template constant and L is linear over
  GF(2) in the bits of the earlier nonce-dependent
  words. Precompute C[t] per template; per group,
  compute only the linear part and the carries.
- Formal: the linear part is exact by GF(2) algebra;
  the carry corrections are the honest difficulty
  and must be derived, with z3 checking the final
  decomposition per word index.
- Impact: potentially moderate to large: if the
  carry correction is cheap, most of the schedule's
  add work for rounds 18..63 leaves the per-group
  path. Classified UNPROVEN BREAKTHROUGH until the
  carry derivation exists.
- Test: derivation for W18..W25 first (the words
  whose nonce dependence is shallowest), priced
  against the current schedule cost; kernel only on
  a positive derivation.
- Success: a priced decomposition with net saving,
  or a derivation showing the carries eat it.
- Predecessor: X-080 derived nonce-affine structure
  for the SHA-NI scalar schedule; the new element
  is the vector decomposition with carry accounting.
- Workstream A / Difficulty very high / Confidence
  low / Cost medium (derivation), high (kernel).
- STATUS (2026-11-14, EXP-016): DERIVED AND REFUTED
  as a work reduction. The affine separation
  W_t = C_t + L_t(nonce) holds exactly for W18
  (L = sigma0, XOR-linear) and W19 (L = identity,
  integer-affine) and fails from W20 onward: the
  delta map's linearity violation rate is 1.0 on
  sampled pairs, and a z3 counterexample for W20
  was verified numerically. The carry correction
  the mechanism hoped to price cheaply is the
  computation itself. Closed; see
  ../phase6/MATHEMATICAL_DISCOVERIES.md and
  ../phase6/REJECTED_APPROACHES.md.

### Y-066: Schedule delta compression for multi-template search
- Limitation: in multi-template shapes (Y-044), each
  template's full schedule state is carried per
  stream; the shared prefix structure means most of
  that state is common.
- Mechanism: store one base schedule state and
  per-template deltas for the words that differ
  (from the first differing message word onward),
  expanding deltas on use.
- Formal: exact; storage representation only.
- Impact: small; a memory-footprint refinement for
  a shape that does not exist yet, sequenced after
  Y-044.
- Test: representation prototype with the Y-044
  walker, footprint and rate measured.
- Success: footprint reduction at rate parity.
- Workstream C / Difficulty medium / Confidence
  medium / Cost low.

### Y-067: Outer schedule staging during block-2 tail rounds
- Limitation: the outer block's first 8 schedule
  words are the inner state, known only at block-2
  end; but its words 8..15 are constants, and the
  staging (Y-029) still serializes the phases.
- Mechanism: prebuild the constant part of the
  outer schedule block and the feed-forward operands
  during block-2's final rounds, so the phase
  transition is a pure register hand-off.
- Formal: exact; scheduling and staging only.
- Impact: small; it shaves the phase boundary, not
  a round.
- Test: group variant with Y-029, gates, bench; the
  isolated delta measured against Y-029 alone.
- Success: the isolated delta, either sign, recorded.
- Predecessor: X-110 (outer K-stream during block 2,
  SHA-NI context); the new element is MB staging.
- Workstream B / Difficulty medium / Confidence
  medium / Cost low.

### Y-068: SHA-NI schedule engine feeding vector rounds (shared prefix)
- Limitation: the shared schedule prefix (rounds
  0..17 words) is computed per group in vector form
  in MB, but it is template-constant; EXP-013/014
  already scalar-share it. The remaining question is
  whether the per-group vector schedule for rounds
  18+ could start from MSG-built words.
- Mechanism: use SHA256MSG1/MSG2 on the template's
  scalar words to produce the shared expanded words
  faster than the scalar recurrence during template
  setup (setup cost only, not per group).
- Formal: exact; the MSG construction is the H-02
  proven path.
- Impact: negligible for rate (setup is amortized);
  registered to close the hybrid-schedule question
  at the setup boundary.
- Test: setup microbench, scalar recurrence vs MSG.
- Success: the priced setup comparison.
- Workstream B / Difficulty low / Confidence high /
  Cost low.

### Y-069: Block schedule generation (16-word jumps)
- Limitation: the rolling ring generates one word
  per round step; a block form generating 16 words
  per step changes the dependency shape and may
  vectorize differently across the ring boundary.
- Mechanism: unroll the recurrence by 16: each block
  step consumes the previous 16 words and produces
  the next 16 with a fixed op DAG; compare its op
  count and chain depth with the ring's.
- Formal: exact; the same recurrence, regrouped.
- Impact: small; the op count is provably the same
  count of sigmas and adds, so only chain shape can
  differ, and the entry says so.
- Test: DAG cost derivation, then a variant if the
  chain shortens.
- Success: the derivation, and a gain if built.
- Workstream A / Difficulty medium / Confidence
  medium / Cost low.

### Y-070: Constant-addend folding inside the schedule recurrence
- Limitation: EXP-014 folded K+W for rounds; inside
  the schedule itself, several recurrence addends
  are template constants for many rounds (any
  expanded word built only from constant inputs,
  which holds beyond W17 wherever the nonce's
  influence has not yet reached through the
  t-7 and t-16 taps).
- Mechanism: compute the reachability of nonce
  dependence per schedule index exactly (the
  dependency sets, as in the W18 analysis), and
  fold every addend that is constant for a given
  index into a per-template constant.
- Formal: exact; dependency sets are computed from
  the recurrence, and folding is substitution.
- Impact: small to moderate; the dependency analysis
  will show exactly how many addends fold, and the
  count is the result either way.
- Test: dependency-set computation (a small script),
  then folding in the MB schedule, gates, bench.
- Success: the fold count and a measured delta.
- Predecessor: EXP-014 folded the round operands;
  the new element is folding inside the recurrence
  itself, driven by an exact dependency analysis.
- Workstream A / Difficulty medium / Confidence
  high / Cost medium.

### Y-071: Next-template schedule during current search
- Limitation: template setup (midstate plus schedule
  prefix) is serial work between spans; at high
  rates and short spans it is a visible seam
  (EXP-009 interaction class).
- Mechanism: compute the next template's setup on
  the second worker thread while the first finishes
  the current span (or interleaved in one worker at
  group boundaries), double-buffering template state.
- Formal: exact; scheduling only.
- Impact: small; bounded by setup cost share from
  Y-032's pricing.
- Test: pipeline-shaped bench with churn.
- Success: seam cost removed at churn shapes.
- Workstream E / Difficulty medium / Confidence
  medium / Cost low.

### Y-072: Nonce-incremental schedule update for rolled templates
- Limitation: when a template rolls (ntime +1, or
  extranonce step), the block-2 schedule is rebuilt
  from scratch although only W1 (or the merkle
  words) changed.
- Mechanism: propagate the delta of the changed
  message word through the recurrence analytically:
  the delta's path through the sigmas is GF(2)-linear,
  with carries as the correction term (the same
  structure as Y-065, applied across templates
  instead of across lanes).
- Formal: linear part exact; carry corrections must
  be derived and z3-checked per roll type.
- Impact: moderate in rolled-template serving
  shapes (solo server), negligible for single-span
  mining; scoped accordingly.
- Test: derivation for the ntime roll, then a setup
  microbench.
- Success: setup cost per roll reduced by a measured
  factor, or the carry cost recorded as the blocker.
- Predecessor: X-101 (kernel-level ntime rolling);
  the new element is delta propagation through the
  schedule instead of recomputation.
- Workstream A / Difficulty high / Confidence low /
  Cost medium.

### Y-073: Sparsity-exploiting scalar schedule for template setup
- Limitation: template setup computes two scalar
  compressions (block 1 and the scalar midstate
  path) whose schedule words include long runs of
  padding zeros; the scalar recurrence computes
  sigmas of zero words repeatedly.
- Mechanism: a setup-only schedule builder that
  tracks which words are structurally zero or
  constant and skips their sigma work.
- Formal: exact; zero words have zero sigmas, and
  the tracking is by construction from the header
  layout.
- Impact: negligible for mining rate; small for
  setup latency in churn shapes; completes the
  setup-cost picture with Y-032.
- Test: setup microbench.
- Success: the priced setup saving.
- Workstream C / Difficulty low / Confidence high /
  Cost low.

### Y-074: Reduced-window schedule formulation (closure candidate)
- Limitation: a recurring suggestion that rounds
  32..63 need only a window of recent words; the
  recurrence already reads only W[t-16..t-2], which
  IS the window. Registered to close the suggestion
  with the observation that the ring already
  implements it.
- Mechanism: none; closure by inspection of the
  recurrence.
- Formal: the ring and the full schedule produce
  identical words, which the existing kernels
  already prove by their gates.
- Impact: negligible; closure.
- Test: none beyond the written argument.
- Success: the recorded closure.
- Workstream A / Difficulty low / Confidence high /
  Cost low.

## Workstream A/E: intermediate-state reuse

### Y-075: Round-3 delta decomposition for a deeper prefix
- Limitation: the proven prefix ceiling stops after
  round 2 of block 2 because round 3 consumes the
  nonce word W3; the state after round 3 is written
  off as fully nonce-dependent.
- Mechanism: decompose the post-round-3 state as
  (shared state) + (a delta that flows only through
  round 3's T1): every state word after round 3 is
  either the shared value or the shared value plus
  T1(3), and T1(3) itself is a shared part plus W3.
  A kernel could carry the state in (base, delta)
  form for a few rounds until the delta contaminates
  the Boolean cones, converting some per-nonce work
  into shared work.
- Formal: the decomposition is exact algebra on the
  round function; the contamination point (where
  delta enters Ch/Maj/sigma inputs) is derivable
  and z3-checkable per round.
- Impact: UNPROVEN BREAKTHROUGH class; bounded above
  by a few rounds of 125, so even total success is
  single-digit percent, and the entry says so.
- Test: derivation of the contamination depth; if
  the delta stays additive for at least 4 rounds,
  a prototype is justified.
- Success: the derivation with an exact depth, and
  a prototype if the depth pays.
- Predecessor: the 67/192 ceiling derivation and
  EXP-013 (prefix through round 2, implemented);
  the new element is carrying the round-3 delta
  symbolically past the ceiling's boundary.
- Workstream A / Difficulty very high / Confidence
  low / Cost medium (derivation).
- STATUS (2026-11-14, EXP-016): DERIVED AND REFUTED
  as a work reduction. The (base, delta) state form
  is exact after round 3, where the delta is the
  pair (a, e) = C + nonce (integer-affine, z3
  proven); round 4, the first round that consumes
  the pair, already produces fresh words that are
  nonlinear in the nonce, because Ch, Maj and the
  big sigmas act on carry-mixed bits. The affine
  words surviving at rounds 5 to 7 are unmodified
  register copies awaiting consumption, not shared
  computed work. The exact point the delta form
  dies is thus the ceiling's own boundary, restated.
  Closed; see ../phase6/MATHEMATICAL_DISCOVERIES.md
  and ../phase6/REJECTED_APPROACHES.md.

### Y-076: Extranonce-dimension midstate amortization in the solo shape
- Limitation: in the solo server's shape, each
  extranonce step changes the coinbase, hence the
  merkle root, hence block 1's second half; the
  midstate is rebuilt per step.
- Mechanism: block 1's first 64 bytes are fixed per
  job; cache that half-compression and rebuild only
  the second half per extranonce step, pricing the
  saving in the serving path (not the kernel).
- Formal: exact; block chaining.
- Impact: small in kernel terms, moderate in
  serving latency at high job churn; whole-path
  scope.
- Test: serving-shaped bench in the solo server
  harness with the cache on and off.
- Success: per-step setup cost reduced by the
  measured half-block share.
- Predecessor: X-025 (extranonce-major geometry)
  and X-060 (incremental merkle spine); the new
  element is the half-block midstate cache priced
  in the serving path.
- Workstream E / Difficulty low / Confidence high /
  Cost low.

### Y-077: Two-level midstate cache for job families
- Limitation: pool jobs in a family share version
  and prevhash and differ in merkle root and time;
  template setup recomputes block 1 fully per job.
- Mechanism: cache the compression of block 1's
  first half (48 of the first 64 bytes are
  job-family constant when version, prevhash and
  the merkle head align) and complete per job.
- Formal: exact; block chaining with a stated
  alignment condition.
- Impact: small; setup-side only.
- Test: setup microbench over synthetic job families.
- Success: the per-job setup saving, with the
  alignment condition stated.
- Workstream E / Difficulty low / Confidence high /
  Cost low.

### Y-078: Outer-state reuse across nonces (closure candidate)
- Limitation: none; registered to close the idea
  that the outer hash of one nonce could seed
  another's: the outer input is the inner digest,
  which is a full-round function of the nonce, so
  no two nonces share any outer intermediate.
- Mechanism: none; the closure is the dependency
  argument (every outer word depends on all 64
  inner rounds, per R-06's structure).
- Formal: dependency argument, same form as R-06.
- Impact: negligible; closure.
- Test: none.
- Success: the recorded closure.
- Workstream A / Difficulty low / Confidence high /
  Cost low.

### Y-079: Snapshot-depth decision table by template field
- Limitation: prefix sharing (EXP-013) works when
  templates share their first words; which snapshot
  depth each combination of shared fields permits
  has never been tabulated, so serving code cannot
  choose safely.
- Mechanism: derive, per subset of {version,
  prevhash head, merkle tail, time, nbits}, the
  deepest valid snapshot (block-1 half, full
  midstate, block-2 round 2, schedule round 17),
  and verify each row by construction in a test.
- Formal: exact; each row is a dependency argument
  plus a gate test with templates differing only in
  the stated fields.
- Impact: small; it turns EXP-013 from a kernel
  trick into a serving rule.
- Test: the table plus one gate test per row.
- Success: the verified table.
- Workstream A / Difficulty low / Confidence high /
  Cost low.

### Y-080: Register-passed outer input in the SHA-NI family
- Limitation: the H-01/H-02 kernels write the inner
  digest out and read it back as the outer block;
  Y-029 removes the same seam in MB, but the SHA-NI
  family's seam is inside its round packing.
- Mechanism: keep the inner state in the RNDS2
  packing and start the outer rounds directly,
  with the padding words injected as immediates.
- Formal: exact; data movement only.
- Impact: small; bounded by the digest store/load
  per nonce in the stream kernels.
- Test: stream variant, assembly audit, bench.
- Success: a reproduced gain in the stream family,
  or the seam priced as negligible there.
- Workstream B / Difficulty medium / Confidence
  medium / Cost medium.

### Y-081: Template setup cost share at production spans (pricing)
- Limitation: several entries (Y-032, Y-071, Y-073)
  spend effort on setup; the setup share at the
  autopilot's actual span sizes has not been priced
  since EXP-009's span study, which priced call
  overhead, not setup.
- Mechanism: measure setup (GBT parse, template
  build, midstate, prefix) as a fraction of span
  wall time across the live span distribution.
- Formal: not applicable; measurement.
- Impact: indirect; it rations the setup-side
  entries with a number.
- Test: instrumented run over recorded live spans.
- Success: the setup share table.
- Workstream G / Difficulty low / Confidence high /
  Cost low.

### Y-082: Warm-start schedule for ntime rolls in the kernel walker
- Limitation: distinct from Y-072 (analytic delta):
  the walker itself can roll ntime inside a search
  (X-101's territory) but rebuilds the schedule
  prefix per roll even though only W1 changed.
- Mechanism: keep the template's schedule prefix
  and recompute only the words whose dependency
  sets contain W1 (the dependency computation of
  Y-070 gives the exact set), inside the walker.
- Formal: exact; dependency-set-driven recomputation.
- Impact: small; roll-heavy shapes only.
- Test: walker variant with roll gates, bench at
  roll rates matching pool behaviour.
- Success: per-roll cost reduced by the measured
  dependency-set fraction.
- Workstream B / Difficulty medium / Confidence
  medium / Cost medium.

## Workstream C/I: alternative data representations

### Y-083: Byte-domain nonce counter for MB group setup
- Limitation: every MB group byte-shuffles 16 nonce
  words (the swmask shuffle in v_group) to build W3.
- Mechanism: generate nonces directly in byte-swapped
  form: keep a byte-domain counter whose increments
  produce the W3 vector without a per-group shuffle,
  using vector adds on pre-swapped lane offsets.
- Formal: exact; the byte swap of (base + lane) is
  not linear in base, so the construction must
  handle carries across bytes explicitly, which is
  the honest content of the entry.
- Impact: small; one shuffle per group of 16 is
  already minor, so this is a completeness entry.
- Test: group-setup microbench, gates.
- Success: setup ops per group reduced, gates exact.
- Workstream C / Difficulty medium / Confidence
  medium / Cost low.

### Y-084: Flags-only MB batch via mask registers
- Limitation: MB batch mode stores 32 bytes per
  hash that most consumers never read (the H-04
  observation, in the vector family).
- Mechanism: batch mode that computes the target
  comparison in vector form, stores one flag byte
  (or one mask bit) per hash, and extracts digests
  only for flagged lanes.
- Formal: exact; the comparison is the same
  comparison, and flagged extraction reproduces the
  digest for audit.
- Impact: moderate in batch-shaped consumers
  (verification, statistics), negligible in search
  mode; scoped accordingly.
- Test: batch variant, gates including candidate
  sets at three densities, bench.
- Success: batch-mode gain at stated densities.
- Predecessor: H-04 (flags-only for the SHA-NI/C
  batch path); the new element is the mask-register
  MB realization.
- Workstream C / Difficulty medium / Confidence
  high / Cost medium.

### Y-085: Orientation parity carried in the H-01 walker
- Limitation: H-01 waves repack state orientation
  at wave boundaries (the RNDS2 packing alternates
  per round pair).
- Mechanism: track orientation parity in the walker
  state and let consecutive waves start in whichever
  orientation the previous wave ended, eliminating
  the repack at boundaries.
- Formal: exact; bookkeeping.
- Impact: small; boundary cost only.
- Test: walker variant, assembly audit, bench at
  short spans where boundaries are frequent.
- Success: the boundary cost delta.
- Workstream B / Difficulty medium / Confidence
  medium / Cost low.

### Y-086: Consumer-shaped digest layout (word-7-first AoS)
- Limitation: the solo server's candidate check and
  the watch-only tracker read the digest's top word
  first and the rest rarely; the batch layout is
  word-0-first per hash.
- Mechanism: an optional batch output layout with
  all top words contiguous (SoA for word 7, AoS for
  the rest) matching the consumer's read pattern.
- Formal: exact; layout only.
- Impact: small and consumer-side; whole-path scope.
- Test: end-to-end bench with the solo server's
  check in the loop.
- Success: end-to-end gain at batch shapes, or the
  layout priced as irrelevant.
- Workstream C / Difficulty low / Confidence medium /
  Cost low.

### Y-087: IFMA 52-bit packing for paired additions (closure candidate)
- Limitation: X-037 closed IFMA applicability at
  the note level; the priced version is owed for
  the additions specifically: pack two 32-bit
  addends into 52-bit limbs and use vpmadd52 to
  add two word-pairs per instruction.
- Mechanism: the packing requires splitting every
  word and recombining carries; the analytic count
  says the split/recombine costs more than the
  saved adds at 32-bit width.
- Formal: exact if built; the closure is the count.
- Impact: negligible; closure with numbers.
- Test: analytic count, verified against a
  microprototype of one addition chain.
- Success: the priced closure.
- Workstream A / Difficulty medium / Confidence
  high / Cost low.

### Y-088: Boolean work on the floating-point vector pipes (speculative)
- Limitation: the integer vector pipes carry all
  Boolean work in MB; this core also has FP vector
  units that sit idle during hashing.
- Mechanism: reinterpret bit patterns through the
  AVX-512DQ floating-point logical ops (vandpd
  family) to spread Boolean work across more
  execution resources, if the domain-crossing cost
  allows.
- Formal: exact; the ops are bitwise on the same
  bits, verified by gates.
- Impact: UNPROVEN BREAKTHROUGH class with a low
  prior: domain crossings usually cost what they
  save, but the pipe map of this specific core has
  never been measured for it.
- Test: microbench of domain-crossed ternlog
  equivalents first; kernel only on a microbench win.
- Success: a microbench win, or the crossing priced
  and closed.
- Workstream B / Difficulty medium / Confidence
  low / Cost medium.

### Y-089: Constant schedule tables in cache (closure candidate)
- Limitation: none; the fixed-position schedule
  words are already immediates or broadcasts in
  every kernel, so a cached table adds traffic, not
  speed. Registered to close the table idea in
  schedule form (companion to Y-011).
- Mechanism: none.
- Formal: not applicable.
- Impact: negligible; closure.
- Test: none beyond the written argument.
- Success: the recorded closure.
- Workstream C / Difficulty low / Confidence high /
  Cost low.

### Y-090: Gray-code nonce order for delta-sparse schedules
- Limitation: consecutive nonces differ in many low
  bits after byte swap; if a future delta-schedule
  method (Y-065/Y-072) profits from sparse deltas,
  the search order itself can manufacture sparsity.
- Mechanism: iterate nonces in Gray-code order so
  consecutive candidates differ in exactly one bit;
  coverage is a permutation of the space, exactness
  unaffected.
- Formal: exact; a bijection on the nonce space.
- Impact: speculative and conditional on Y-065 or
  Y-072 landing; zero standalone.
- Test: only as a rider on a delta-method prototype.
- Success: measured delta-cost reduction in that
  prototype.
- Workstream A / Difficulty low / Confidence low /
  Cost low.

### Y-091: Per-word target thresholds for the in-vector filter
- Limitation: Y-036's filter uses the top word
  only; at densities where many lanes pass the top
  word, the second word decides.
- Mechanism: precompute the target's word-by-word
  threshold structure so the vector filter can
  apply a two-word lexicographic screen with masks
  before any extraction.
- Formal: exact; lexicographic comparison is
  decided by the first differing word, and the
  screen only removes lanes provably above target.
- Impact: small; a density-dependent refinement of
  Y-036.
- Test: filter variant, gates at densities chosen
  to stress the second word, bench.
- Success: extraction count reduced at the stated
  densities with exact candidate sets.
- Workstream B / Difficulty medium / Confidence
  high / Cost low.

### Y-092: Endian-free whole-kernel formulation (closure candidate)
- Limitation: a recurring question whether working
  in little-endian word form throughout would save
  the byte swaps; the swaps happen once per word at
  load and once at store, not per round.
- Mechanism: none; the closure counts the swaps in
  the existing kernels (one shuffle per group in
  MB, header preparation per template in SHA-NI)
  and shows the per-round cost is identical in
  either endianness.
- Formal: the round function is defined on words;
  endianness is a representation at the boundary,
  which the count demonstrates.
- Impact: negligible; closure.
- Test: the written count.
- Success: the recorded closure.
- Workstream A / Difficulty low / Confidence high /
  Cost low.

## Workstream J: combinations of verified optimisations

### Y-093: Share plus dual-batch (EXP-013 inside EXP-011)
- Limitation: EXP-013 (prefix sharing) and EXP-011
  (dual batch) were measured separately; their
  interaction is unknown, and EXP-013's effect was
  below the noise floor alone.
- Mechanism: apply the shared prefix and shared
  schedule words inside both batches of the dual
  kernel; the savings are per batch, the interleave
  is orthogonal.
- Formal: exact by construction; gates.
- Impact: small to moderate; justified only because
  both parents are already built and gated.
- Test: combined variant, gates, interleaved bench
  against both parents in one session.
- Success: a median above both parents, or the
  interaction recorded as additive-null.
- Workstream J / Difficulty low / Confidence medium /
  Cost low.

### Y-094: Explicit ternlog plus full unroll (codegen guarantee)
- Limitation: EXP-012's parity result depends on
  this gcc's choices; a different compiler or flag
  set could silently lose the ternlog forms (the
  X-043 clang question).
- Mechanism: combine the explicit-ternlog source
  with the unrolled shape (Y-033) so the Boolean
  cost is guaranteed by construction in the shape
  where codegen pressure is highest.
- Formal: exact; the ternlog forms are proven
  (EXP-012).
- Impact: small; a portability and guarantee entry,
  not a rate bet on this compiler.
- Test: build under gcc and any available second
  compiler, assembly audit both, bench.
- Success: identical instruction profile across
  compilers, with rates recorded.
- Workstream J / Difficulty medium / Confidence
  high / Cost medium.

### Y-095: K+W folding plus schedule-addend folding
- Limitation: EXP-014 (round-operand folding) showed
  no gain as implemented, and Y-070 (recurrence
  folding) is untested; combining two unproven
  folds is registered only as a sequenced pair, not
  a parallel bet.
- Mechanism: if Y-070's dependency analysis shows a
  large foldable set, the combined fold changes the
  schedule's shape enough that EXP-014's negative
  may not transfer.
- Formal: exact; both folds are substitutions.
- Impact: speculative small; explicitly conditional.
- Test: only after Y-070 reports its fold count.
- Success: a combined gain, or the pair closed.
- Workstream J / Difficulty medium / Confidence
  low / Cost low.

### Y-096: MB champion plus flags-only batch at integration shape
- Limitation: kernel benches measure batch with
  full digest stores; the production-shaped consumer
  (search plus rare extraction) has a different cost
  profile (EXP-009's lesson).
- Mechanism: pair whichever MB variant leads with
  Y-084's flags-only output and measure through a
  production-shaped harness (mining/engine.py span
  patterns), not the kernel bench.
- Formal: exact; same gates plus the harness's own
  accounting checks.
- Impact: moderate as a decision input; it is the
  shape an integration decision would actually
  consume.
- Test: production-shaped bench after the Part A
  decision closes.
- Success: an integration-grade comparison recorded.
- Workstream J / Difficulty medium / Confidence
  high / Cost medium.

### Y-097: Heterogeneous worker pair under the VM cap
- Limitation: the VM cap (about 1.5 effective CPUs)
  makes the two worker threads share less than two
  cores; homogeneous pairs may contend on the same
  pipes.
- Mechanism: run one MB worker and one SHA-NI
  stream worker concurrently and measure the pair's
  total against both homogeneous pairs.
- Formal: exact; scheduling only.
- Impact: moderate if pipe contention is real on
  this guest; the EXP-007 variance anomaly (flat
  AVX-512 response while scalar rose) hints the
  resource interaction is not simple.
- Test: pair bench, three configurations, one
  session, totals compared.
- Success: a heterogeneous total above both
  homogeneous totals, reproduced.
- Predecessor: X-073 (thread and stream mix under
  the cap, homogeneous); the new element is the
  cross-family pair.
- Workstream G / Difficulty low / Confidence medium /
  Cost low.

### Y-098: Prefix sharing inside the dual-batch walker
- Limitation: Y-093 combines at the kernel level;
  this entry is the walker-level version: the dual
  walker's two batches currently each start from
  the full midstate broadcast, and the shared
  prefix applies per batch identically.
- Mechanism: hoist the prefix state computation to
  the walker so both batches and the outer staging
  share one setup; identical arithmetic, less
  repeated setup per group.
- Formal: exact; hoisting.
- Impact: small; setup per group is already minor,
  so this is a completeness combination.
- Test: walker variant, gates, bench.
- Success: the isolated delta recorded.
- Workstream J / Difficulty low / Confidence medium /
  Cost low.

### Y-099: Best kernel plus the X-059 pipeline fix, repriced end to end
- Limitation: kernel gains and pipeline costs were
  priced separately (EXP-007 vs EXP-009); the
  integration question is about their sum in the
  production path.
- Mechanism: measure mining/engine.py end to end
  with the leading research kernel behind the
  backend dispatch and the candidate-construction
  cache (X-059) applied, against the current
  production path, in a regtest-shaped harness.
- Formal: exact; both components are separately
  verified before the combined run.
- Impact: moderate as the decision-grade number
  for integration; not a kernel claim.
- Test: end-to-end harness, full suite, regtest
  block through the combined path.
- Success: an end-to-end rate and a block accepted,
  recorded as one claim.
- Workstream J / Difficulty medium / Confidence
  high / Cost high.

### Y-100: Pairwise interaction matrix over the verified set
- Limitation: combinations in this programme are
  currently chosen by intuition; interactions
  (spill interactions, port interactions) have
  surprised twice (EXP-006, EXP-011).
- Mechanism: measure all pairwise combinations of
  the small verified set (prefix sharing, ternlog
  source form, dual batch, strided assignment,
  schedule-ahead) in one designed session and fit
  interaction terms instead of assuming additivity.
- Formal: exact; each cell is gated before benching.
- Impact: indirect; it converts combination choice
  from intuition to a table.
- Test: the designed session (about 10 cells).
- Success: the interaction table published in the
  registry.
- Workstream G / Difficulty medium / Confidence
  high / Cost medium.

## Workstream G/E: pipeline and measurement interactions

### Y-101: Steal-normalized decision statistic
- Limitation: benchmark decisions on this VM keep
  failing on contention spread (EXP-004 twice);
  raw medians mix kernel rate with neighbour load.
- Mechanism: record steal and runnable-load traces
  at fine granularity during each run and report
  the rate per unit of non-stolen, non-contended
  CPU time as a second decision statistic alongside
  the raw median.
- Formal: not an equivalence question; a statistic
  with a stated estimator, validated on a known-equal
  pair (EXP-012's ternlog parity pair is the control).
- Impact: indirect but decision-critical; it is
  the cheapest path to decisions this VM can
  actually settle.
- Test: reprocess the EXP-011..015 raw runs with
  the statistic and check the control pair reads
  as equal.
- Success: the control pair separates correctly
  (equal within tolerance) while a known-unequal
  pair (bitslice) separates widely.
- Predecessor: X-070 (steal as covariate, recorded);
  the new element is steal as the decision statistic
  with a control-pair validation.
- Workstream G / Difficulty medium / Confidence
  high / Cost low.
- Status (2026-11-14, EXP-017): PARTIAL. The
  paired log-ratio statistic with bootstrap
  validated as an estimator (injected +0.20
  recovered with bias at most 0.0006; controls
  null; real verdicts stable across sessions),
  but the steal and runnable-load adjustment
  itself was measured near-neutral: pooled CI
  width ratios 0.970 to 0.999 versus the
  unadjusted statistic, point shifts at most
  0.0004. The pairing carries the decision
  value at 65,536-hash granularity. Covariate
  recording continues; adjustment is retained
  as a predeclared option, not a proven gain.

### Y-102: Fine-grained paired interleaving (100k blocks)
- Limitation: round-robin at 1M granularity still
  lets multi-minute load drift alias into kernel
  differences (visible in the EXP-011..015 sessions).
- Mechanism: interleave contenders in 100k-hash
  blocks with randomized order, and analyse paired
  ratios per block; drift slower than a block pair
  cancels.
- Formal: not applicable; an experimental design.
- Impact: indirect; variance reduction for every
  future comparison on this VM.
- Test: rerun a known comparison (mb16 vs its
  ternlog twin, expected ratio 1.0) and a known
  unequal one (mb16 vs bitslice) under the design.
- Success: tighter ratio intervals than the 1M
  design on the same session length.
- Predecessor: X-072 (paired-run ratio design at
  run granularity); the new element is block-level
  pairing with randomized order.
- Workstream G / Difficulty low / Confidence high /
  Cost low.
- Status (2026-11-14, EXP-017): SUPPORTED at
  65,536 hashes. Paired interleaving at that
  block size returned the same verdict in every
  session of every comparison (controls null,
  both real comparisons significant), the
  stability three whole-round decisions never
  achieved. No claim is made about other block
  sizes; 65,536 is the validated size. Adopted
  as the Phase 6 paired protocol.

### Y-103: Equal-pair control methodology (the ternlog pair as instrument)
- Limitation: the programme has no standing control
  for "how large a difference can this session
  even detect".
- Mechanism: adopt the EXP-012 pair (two kernels
  with near-identical codegen, 111 vs 116 hot-loop
  instructions) as a permanent control: every
  future bench session runs the control pair and
  reports its apparent difference as the session's
  noise scale.
- Formal: not applicable; methodology.
- Impact: indirect; it converts every future
  "gain" claim into a ratio against a measured
  noise scale.
- Test: apply retroactively to the EXP-011..015
  sessions' data and state what would have been
  claimable.
- Success: the retroactive analysis published.
- Workstream G / Difficulty low / Confidence high /
  Cost low.
- Status (2026-11-14, EXP-017): SUPPORTED in its
  EXP-017 form (identical implementations as the
  two arms, the strongest form of the control):
  both controls returned decision-grade nulls in
  all sessions and pooled under the paired
  statistic, and the historical min/max rule
  passed a phantom difference in 0 of 6 control
  sessions, pricing that rule's failure mode as
  false negatives rather than false positives.
  The equal-pair control is now a standing part
  of the Phase 6 paired protocol.

### Y-104: Node-sync interaction with kernel benchmarks
- Limitation: the mainnet node's initial sync has
  been a contention source in every session since
  EXP-004; its specific cost to kernel benches is
  asserted, not isolated.
- Mechanism: repeat a fixed kernel comparison
  before and after sync completes (the Part A
  watcher's window provides the after), with all
  other conditions held as constant as the VM
  allows, and attribute the delta.
- Formal: not applicable; measurement.
- Impact: indirect; it prices the environment the
  Part A decision will run in.
- Test: the before record exists (EXP-004..015);
  the after run is one session post-sync.
- Success: the attributed delta recorded.
- Workstream G / Difficulty low / Confidence high /
  Cost low (one session, post-sync).

### Y-105: Confirmation path repricing at MB rates
- Limitation: EXP-009 priced hashlib confirmation
  at 1.1 us per candidate and 2.8 percent of a core
  at 6.5M H/s; the MB search path's extraction
  (Y-036) changes the input rate to confirmation.
- Mechanism: measure the full search path (kernel
  plus filter plus confirmation plus publication)
  at regtest density with the MB kernel, and find
  the density where confirmation, not hashing,
  binds.
- Formal: exact; measurement only.
- Impact: small at mainnet, moderate for regtest
  and testnet-shaped work; whole-path scope.
- Test: search-path bench across densities.
- Success: the binding-density curve recorded.
- Workstream E / Difficulty low / Confidence high /
  Cost low.

### Y-106: Template freshness cost at MB rates
- Limitation: at 6M H/s a span of one second of
  work is 6M hashes; GBT longpoll wake latency and
  template age translate directly into stale work,
  priced in EXP-009 only at production rates.
- Mechanism: reprice the stale-work fraction at MB
  rates with the live longpoll behaviour, and test
  whether shorter spans (more frequent freshness
  checks) pay at the new rate.
- Formal: not applicable; measurement.
- Impact: small; a real end-to-end term in the
  solo shape.
- Test: span/freshness sweep in the live-shaped
  harness.
- Success: the optimal freshness point at MB rates.
- Workstream E / Difficulty low / Confidence
  medium / Cost low.

### Y-107: Solo-server accounting overhead at MB worker rates
- Limitation: the solo server tracks workers and
  shares per worker; at MB rates the share arrival
  rate rises and the tracker's per-share cost is
  unmeasured.
- Mechanism: load the solo server with synthetic
  MB-rate workers and price the tracking path
  (share validation is itself a SHA-256d, so the
  server spends hashes to check hashes).
- Formal: exact; the validation is the same hash.
- Impact: small to moderate for the serving shape;
  it bounds how much of the fleet's rate the
  server eats.
- Test: synthetic load bench against the solo
  server.
- Success: the per-share server cost recorded.
- Workstream E / Difficulty medium / Confidence
  medium / Cost medium.

### Y-108: Pinned benchmark manifest for every record
- Limitation: session conditions are recorded
  unevenly across EXP-000..015 (some JSONs carry
  load, some do not; library hashes are not
  recorded at all).
- Mechanism: a manifest file per benchmark run:
  CPU flags digest, library sha256 for every
  contender, compiler version, load and steal
  trace summary, kernel parameters; generated by
  the bench harness automatically.
- Formal: not applicable; infrastructure.
- Impact: indirect; reproducibility of every
  future claim.
- Test: regenerate one past session's manifest
  from its artifacts and check completeness.
- Success: the manifest generator merged into the
  harness and used on the next session.
- Workstream G / Difficulty low / Confidence high /
  Cost low.

## Registry statistics

Total: 108 entries (Y-001 to Y-108). Distribution:
alternative computation graphs 12, automated Boolean
discovery 10, advanced MB scheduling 14, multi-stream
arrangements 10, superoptimisation and codegen 8,
register pressure and dependency chains 10, message
schedule restructuring 10, intermediate-state reuse
8, data representations 10, combinations 8, pipeline
and measurement 8. Entries registered expecting
refutation or as closures: Y-006, Y-009, Y-011,
Y-017, Y-020, Y-028, Y-042, Y-055, Y-064, Y-074,
Y-078, Y-087, Y-089, Y-092 (14). Entries classified
UNPROVEN BREAKTHROUGH: Y-007, Y-012, Y-065, Y-075,
Y-088 (5). Every other entry is a PROMISING
HYPOTHESIS until its test reports.
