# Hypothesis Registry: X-Series

Registered 2026-11-14 under the Grand Research Mandate.
Numbering starts at X-001 to avoid any clash with the
H-series (H-01 to H-24) in ../experiment_registry.md,
which remains in force: its open entries are not repeated
here, and where an X entry touches an H entry's territory
the cross-reference is stated on the entry. In particular:
candidates-only batch output is H-04 (cross-reference
only, not re-registered); pinning is H-10; dynamic
chunking is H-11; timestamp rolling is H-13; Ch and Maj
reformulations as a general claim are H-06 (the X entries
below are specific applications outside that entry's
scope, or superoptimizer searches over the joint cone).

Rules applied to every entry:

- No re-listing of rejected ideas (compiler flag variants
  on the production wrapper, R-03; statistical or
  reduced-round shortcuts, R-01 and H-24; lite screening,
  R-02) unless a NEW mathematical or architectural
  justification is stated explicitly on the entry. The
  compiler entries X-043 to X-045 carry exactly such a
  justification: R-03 itself reopens the question for a
  different source file, and the hand kernels are one.
- Impact classes: negligible (under 1 percent), small
  (1 to 5 percent), moderate (5 to 30 percent), large
  (over 30 percent), transformative (would change the
  family's ranking). Each carries a one-line justification.
- Status vocabulary: untested, supported, rejected.
  Entries registered in order to be refuted say so; a
  completed refutation is a result, filed like any other.

## Ranking summary (top of the list, by expected value)

1. X-067 quiet-window decision re-run: unblocks or closes
   a measured 1.75x to 2.6x median advantage. Cheapest
   item in the registry relative to what it decides.
2. X-001 three-stream interleave: the unexplored point
   between the proven 2-stream gain and the spill-heavy
   4-stream build.
3. X-006 and X-007 hand-scheduled assembly: attacks the
   one measured cost (spills) of the current best kernel.
4. X-031 AVX-512 16-way multi-buffer: the largest untested
   implementation family on this CPU.
5. X-009 cross-nonce phase pipelining: overlaps the outer
   hash of one nonce with block 2 of the next inside one
   worker.
6. X-024 template-fixed message operands: exact, free
   inside a hand kernel, stacks with everything.
7. X-059 candidate construction caching: removes a real,
   code-cited per-extranonce repetition including an RPC
   call per candidate build.
8. X-016 inlined batch path: the batch loop calls the hot
   function per nonce where the search loop inlines it
   (assembly-observed asymmetry).
9. X-049 parameterized kernel generator: turns geometry
   questions into sweeps instead of hand builds.
10. X-070 steal-time covariate: raises the value of every
    benchmark this programme will ever run on a shared VM.

## Workstream B: stream geometry and SHA-NI kernel structure

### X-001: Three-stream interleave
- Statement: 3 interleaved SHA-NI streams per worker beat
  both 2 streams (less latency hidden) and 4 streams
  (fewer spills) per worker on this core.
- Mechanism: stream count trades hidden latency against
  register spills; 3 is the unmeasured point on the curve.
- Impact: moderate (the 2 to 4 step moved per-worker
  medians by about 30 percent; the optimum's location is
  worth that class). Difficulty: low (existing framework).
  Confidence: medium. Cost: hours. Status: untested.

### X-002: Six-stream interleave with a spill budget
- Statement: 6 streams, accepting planned spills, still
  gain over 4 streams because the core remains
  latency-bound at 4.
- Mechanism: more independent chains issue into remaining
  stalls; spills are L1 traffic, cheaper than stalls.
- Impact: small to moderate (EXP-003's curve is flattening
  but has not turned). Difficulty: low. Confidence: low
  to medium. Cost: hours. Status: untested.

### X-003: Eight-stream interleave, to locate the cliff
- Statement: at 8 streams per worker, spill traffic
  overwhelms latency hiding and per-worker throughput
  falls below the 4-stream figure.
- Mechanism: 8 streams need about 48 live vectors against
  16 registers; the wave becomes a stack workload.
- Impact: negligible as a product, high as information
  (it bounds the whole geometry family). Difficulty: low.
  Confidence: high. Cost: hours. Status: untested.

### X-004: Strided versus blocked nonce assignment
- Statement: assigning stream nonces strided (stream s
  takes nonces congruent to s mod streams) rather than in
  blocked chunks changes throughput measurably through
  wave remainder and store patterns.
- Mechanism: identical arithmetic; different memory and
  control shape per wave.
- Impact: small (assignment geometry is second-order, but
  the wave remainder interacts with early exit).
  Difficulty: low. Confidence: medium. Cost: hours.
  Status: untested.

### X-005: Wave size decoupled from stream count
- Statement: running waves of 8 nonces through 4 stream
  slots (double-buffered waves) beats waves of exactly
  the stream count, by keeping slots fed across wave
  boundaries.
- Mechanism: wave boundaries currently serialize slot
  refill; double buffering overlaps refill with compute.
- Impact: small to moderate (wave overhead is visible in
  the 2,985-instruction inlined body). Difficulty:
  medium. Confidence: medium. Cost: days. Status:
  untested.

### X-006: Hand-scheduled assembly, 2 streams, explicit allocation
- Statement: a hand-written 2-stream kernel with explicit
  register allocation beats the compiler's 2-stream build
  by keeping all state and schedule vectors resident.
- Mechanism: at 2 streams everything fits in 16 registers;
  the compiler's choices, not the register file, are the
  remaining spill source.
- Impact: moderate (removes the known loss in the current
  best family's cleanest configuration). Difficulty: high.
  Confidence: medium. Cost: days to weeks. Status:
  untested.

### X-007: Hand-scheduled assembly, 4 streams, spill layout
- Statement: a hand-written 4-stream kernel whose spill
  slots are laid out so one wave's spill traffic touches
  the fewest possible cache lines beats the compiler's
  4-stream build.
- Mechanism: spills are mandatory at 4 streams (365 xmm
  stack ops measured); their placement and reuse order
  are not.
- Impact: moderate (attacks the single measured cost of
  the current champion configuration). Difficulty: high.
  Confidence: medium. Cost: days to weeks. Status:
  untested.

### X-008: Intra-nonce phase overlap at the block boundary
- Statement: generating the outer hash's first schedule
  groups during block 2's final rounds (they depend only
  on early inner state words as they finalize) hides part
  of the outer hash's serial start.
- Mechanism: the outer schedule's first groups depend on
  inner digest words W0..W7, which finalize progressively
  during block 2's feed-forward; overlap is limited but
  real.
- Impact: small (a few schedule groups of 64 rounds; the
  boundary is one point per nonce). Difficulty: high
  (dependency bookkeeping). Confidence: low. Cost: days.
  Status: untested.

### X-009: Cross-nonce phase pipelining in one worker
- Statement: interleaving the outer hash of nonce n with
  block 2 of nonce n+1 in the same worker (two half-chains
  at different phases) beats same-phase stream layouts at
  equal stream count.
- Mechanism: the two phases have different instruction
  mixes (block 2 is schedule-heavy at its start, the
  outer hash is round-dense throughout); phase diversity
  fills ports and stalls better than identical chains.
- Impact: moderate (phase mixing is the classic software
  pipeline argument, untested in this kernel). Difficulty:
  medium. Confidence: medium. Cost: days. Status:
  untested.

### X-010: Schedule-ahead distance in the SHA-NI kernel
- Statement: the compiler does not already generate
  schedule group g+1 during the rounds consuming group g
  in hash_p1; increasing the schedule-ahead distance in
  source raises throughput.
- Mechanism: MSG latency, like RNDS2 latency, must be
  hidden by distance between production and consumption.
- Impact: small (the listing suggests partial overlap
  already). Difficulty: low (listing first, then source
  reorder). Confidence: medium. Cost: hours. Status:
  untested.

### X-011: K+W operand preparation overlap
- Statement: forming the K+W message operands one group
  earlier (into a small operand queue in registers) cuts
  the add latency off the RNDS2 feed path.
- Mechanism: the RNDS2 message operand add currently sits
  between schedule completion and round issue.
- Impact: small (one add per round pair on the feed path).
  Difficulty: medium. Confidence: medium. Cost: days.
  Status: untested.

### X-012: Alternating state orientation between round pairs
- Statement: alternating the org-form orientation every
  round pair eliminates the shuffle operations the H-02
  kernel uses to re-present state between pairs.
- Mechanism: RNDS2's output packing is fixed, but which
  physical register plays which role can alternate,
  trading shuffles for bookkeeping.
- Impact: small (shuffles are a visible minority of the
  494 hot instructions). Difficulty: medium. Confidence:
  medium. Cost: days. Status: untested.

### X-013: Alternate RNDS2 operand packing
- Statement: a different static packing of the eight state
  words across the two state registers reduces total
  shuffle count across a full compression versus the
  org form.
- Mechanism: the packing determines which words must move
  when the schedule operand format changes between block
  phases.
- Impact: negligible to small (the org form is already
  shuffle-lean; this is a completeness check).
  Difficulty: medium. Confidence: low. Cost: days.
  Status: untested.

### X-014: Branchless winner handling inside the wave loop
- Statement: replacing the per-wave winner test and publish
  branch with branchless selection measurably helps the
  search loop at easy targets, where hits are dense.
- Mechanism: at regtest-class targets the publish path is
  hot; at mainnet targets it is never taken and the branch
  is free, so the claim is target-conditional.
- Impact: small, target-conditional (zero at mainnet
  difficulty). Difficulty: low. Confidence: medium.
  Cost: hours. Status: untested.

### X-015: Target comparison overlapped with the next nonce
- Statement: issuing the finished digest's target
  comparison after the next nonce's first round pair has
  been issued (deferring the branch by one nonce) removes
  the compare from the chain's critical path in batch
  mode.
- Mechanism: the comparison depends only on the finished
  digest; nothing in the next nonce depends on it except
  the rare stop decision.
- Impact: small (a compare and a store per nonce, moved
  off the path). Difficulty: medium (accounting semantics
  must stay exact). Confidence: medium. Cost: days.
  Status: untested.

### X-016: Inline the batch hot path
- Statement: the H-02 batch loop calls hash_p1 per nonce
  while the search loop inlines it (assembly-observed);
  an inlined batch variant beats the calling variant.
- Mechanism: call overhead, register save/restore, and
  lost cross-boundary scheduling per nonce.
- Impact: small to moderate (per-nonce call overhead on a
  roughly 0.3 microsecond hash is not trivial).
  Difficulty: low. Confidence: high. Cost: hours.
  Status: untested.

### X-017: Hot-loop alignment and code placement
- Statement: aligning the per-nonce loop head to a
  64-byte boundary and keeping the loop body within one
  fetch window measurably changes throughput.
- Mechanism: fetch and decode alignment effects on a
  tight loop; measurable only by A/B on this core.
- Impact: negligible to small (tight loops usually align
  well by luck; this makes it deliberate). Difficulty:
  low. Confidence: low. Cost: hours. Status: untested.

### X-018: Search-shaped benchmarking of kernels
- Statement: kernel rankings under batch-shaped loads
  (all digests written, no early exit) differ from
  rankings under search-shaped loads (early exit, winner
  publish, sparse stores) enough to change a selection.
- Mechanism: the two shapes exercise different memory and
  branch behaviour; production mining is search-shaped.
- Impact: small as speed, large as selection hygiene (a
  wrong-shape benchmark can pick the wrong kernel).
  Difficulty: low. Confidence: medium. Cost: hours.
  Status: untested.

### X-019: Five-stream interleave (odd counts)
- Statement: 5 streams beat 4 per worker, because the
  latency curve has not saturated and odd counts break
  the wave symmetry that causes periodic spill bursts.
- Mechanism: as X-002, one step at a time, with wave
  remainder handling (5 = 4 + 1) already in the framework.
- Impact: small (between X-001's and X-002's claims).
  Difficulty: low. Confidence: low. Cost: hours.
  Status: untested.

## Workstream A: mathematical transformations

### X-020: GFNI affine forms of the schedule sigmas
- Statement: sigma0 and sigma1, being GF(2)-linear maps,
  are each implementable as a fixed affine transform via
  GFNI instructions plus shuffles, beating the
  rotate/shift/xor form inside a vector schedule.
- Mechanism: gfni is present (probe); one affine op per
  byte replaces several rotates in the vector sigma.
- Impact: small (schedule sigmas are a minority of vector
  round work; the win is confined to vector designs).
  Difficulty: medium (proof by the three-leg pattern
  first). Confidence: medium. Cost: days. Status:
  untested.

### X-021: Carry-save addition tree for T1 in vector rounds
- Statement: evaluating h + S1 + Ch + K + W as a
  carry-save tree with one final carry-propagate addition
  shortens the vector round's critical path versus a
  sequential add chain.
- Mechanism: full-adder stages are one XOR/AND level
  each; the serial carry chain is paid once per round
  instead of four times.
- Impact: moderate within vector designs (the add tree is
  on every round's critical path). Difficulty: medium.
  Confidence: medium. Cost: days. Status: untested.

### X-022: Carry-save state across round boundaries
- Statement: keeping the two state words that change per
  round (a and e) in carry-save (sum, carry) form across
  the round boundary, resolving only when a Boolean
  function needs the true value, shortens back-to-back
  round latency in a vector kernel.
- Mechanism: Ch and Maj need true values, so resolution
  is forced each round for a and e; the hypothesis
  survives only if the resolution overlaps the sigma
  computations. Stated precisely so it can fail cleanly.
- Impact: small if it works (the forced resolution may
  eat the whole gain, which is the experiment).
  Difficulty: high. Confidence: low. Cost: days.
  Status: untested.

### X-023: Outer-hash schedule partial evaluation
- Statement: in the outer block, W9..W14 are zero, W8 is
  0x80000000, W15 is 256, so the earliest expanded outer
  schedule words (W16 onward, until all four recurrence
  inputs are digest-dependent) lose terms and can be
  computed with fewer operations per nonce.
- Mechanism: exact term elimination from constant inputs;
  the count of simplified words is a derivation, done
  once, in writing, before any code.
- Impact: negligible to small (a handful of words in one
  of three compressions). Difficulty: low. Confidence:
  high (the identity is checkable by hand). Cost: hours.
  Status: untested.

### X-024: Template-fixed message operands, rounds 0 to 17
- Statement: in block 2, the schedule words W0..W17 are
  template constants (W16 and W17 are nonce-independent
  by the W18 derivation), so the K+W message operands for
  rounds 0..17 can be precomputed whole per template,
  removing their per-nonce formation from a hand kernel.
- Mechanism: operand preparation is per-nonce work today;
  18 of 125 rounds' operands need not be.
- Impact: small (operand formation is a few ops per round
  pair; bounded, exact, and free once coded). Difficulty:
  low inside the H-02 scaffold. Confidence: high. Cost:
  hours. Status: untested.

### X-025: Extranonce-major iteration geometry
- Statement: at high stream counts, iterating the
  extranonce dimension in the inner loop (streams bound
  to different extranonces of one template family) beats
  nonce-major iteration, because block-2's W0 changes are
  cheaper to schedule around than full nonce restarts.
- Mechanism: an extranonce step invalidates the midstate
  (67 rounds per template) but the per-stream setup is
  amortized differently; which dimension should be inner
  is a function of rate, and rate is changing.
- Impact: small (a geometry choice at the solo-server
  layer, not the kernel). Difficulty: medium.
  Confidence: low. Cost: days. Status: untested.

### X-026: Timestamp as the fast loop variable (refutation expected)
- Statement to test by derivation: patching W1
  (timestamp) per step instead of W3 (nonce) cannot
  preserve any prefix: W1 is consumed at round 1 and
  feeds expanded words from W16 (its t-15 entry), so the
  reusable prefix collapses from 3 rounds to 1.
- Mechanism: pure schedule-index derivation, no code.
- Impact: negligible as speed; closes a recurring
  suggestion permanently. Difficulty: low. Confidence:
  high. Cost: hours. Status: untested (analysis entry).

### X-027: Superoptimized joint Boolean cone
- Statement: an SMT-guided enumerative search over
  sequences of AVX-512 and scalar bitwise ops finds a
  joint evaluation of (S0, S1, Ch, Maj) with fewer ops
  or a shorter chain than the four functions evaluated
  separately in their proven best forms.
- Mechanism: the four functions share inputs; separate
  evaluation recomputes shared subterms (for example the
  pairwise ANDs and XORs of a, b, c).
- Impact: moderate within vector and scalar-round designs
  (four functions per round, 192 rounds per hash).
  Difficulty: high (search space control). Confidence:
  medium. Cost: weeks. Status: untested.

### X-028: Addition-tree reassociation under a port model
- Statement: among the association orders of the T1 and
  T2 addition trees, the compiler's choice is not the
  chain-depth-minimal one for this core's port layout,
  and an explicitly parenthesized order measures faster
  in a scalar-round kernel.
- Mechanism: addition is associative mod 2^32 (proven
  property); only the dependency shape changes.
- Impact: negligible to small (compilers are good at
  this; the entry exists because the check is cheap in a
  kernel we already own). Difficulty: low. Confidence:
  low. Cost: hours. Status: untested.

### X-029: Bitsliced SHA-256 (analytic bound, refutation expected)
- Statement to bound: a bitsliced implementation (32
  hashes transposed across bit positions, rotations free
  as renames) requires on the order of 32 full-adder
  networks per addition, and SHA-256d performs roughly
  15 word-additions per round across 192 rounds, putting
  its op count per hash orders above the SHA-NI and
  vector families.
- Mechanism: additions dominate; bitslicing taxes
  exactly additions.
- Impact: negligible as speed; the bound closes the idea
  with arithmetic instead of opinion. Difficulty: low
  (analysis). Confidence: high. Cost: hours. Status:
  untested (analysis entry).

### X-030: Feed-forward folded into the target comparison
- Statement: in batch and search paths, comparing
  (state + H0) against the target word-wise from the most
  significant word, without serializing the digest bytes
  first, saves the per-nonce serialization for the
  overwhelmingly common reject case.
- Mechanism: the feed-forward add and the byte-swap are
  per-word; the comparison can consume words as they are
  produced and stop at the first deciding word.
- Impact: small (the production wrapper serializes 32
  bytes per nonce inside its 408 instructions; a hand
  kernel can skip most of it). Difficulty: low.
  Confidence: medium. Cost: hours. Status: untested.

## Workstream B continued: the vector multi-buffer family

### X-031: AVX-512 16-way multi-buffer SHA-256d
- Statement: a 16-lane zmm multi-buffer implementation
  (vector rounds with vprold rotates, proven Ch/Maj
  alternative forms, vector schedule) beats the H-01
  streams=4 per-worker rate on this CPU.
- Mechanism: one instruction advances 16 hashes by one
  round-step; width replaces interleave depth.
- Impact: large if it wins (it would reorder the family
  ranking); honestly uncertain, per
  CPU_EXECUTION_RESEARCH.md section 3. Difficulty: high.
  Confidence: low to medium. Cost: weeks. Status:
  untested.

### X-032: AVX-512 8-way multi-buffer
- Statement: the 8-lane variant (one hash per 32-bit lane
  pair avoided; 8 active lanes in zmm or 8 in ymm with
  AVX-512VL) beats the 16-lane variant per hash because
  its schedule live range fits the register file without
  spills.
- Mechanism: half the width, a fraction of the register
  pressure; the same tradeoff as streams, one level down.
- Impact: moderate (it decides the family's configuration
  even if the family loses). Difficulty: high.
  Confidence: medium. Cost: weeks (shares X-031's
  scaffold). Status: untested.

### X-033: AVX2 8-way multi-buffer
- Statement: an AVX2 (ymm, shift-based rotates) 8-way
  multi-buffer beats production OpenSSL per worker, even
  if it loses to X-031, earning a dispatch slot for
  AVX2-only machines.
- Mechanism: width 8 with 3-op rotates; the H-series
  H-08 reasoning, now testable against a measured SHA-NI
  champion instead of a guess.
- Impact: moderate (fleet coverage, not this VM's peak).
  Difficulty: high. Confidence: medium. Cost: weeks.
  Status: untested.

### X-034: 128-bit 4-way multi-buffer (control)
- Statement: a 4-lane xmm multi-buffer is the
  register-pressure control for the family: if even it
  loses to H-02 per lane-equivalent, the family's problem
  is round op count, not pressure.
- Mechanism: diagnostic decomposition of the family's
  cost.
- Impact: negligible as speed, high as diagnosis.
  Difficulty: medium. Confidence: high. Cost: days.
  Status: untested.

### X-035: Hybrid phases: SHA-NI block 2, vector outer hash
- Statement: running block 2 through the SHA-NI kernel
  and the outer hash through a multi-buffer vector stage
  (batched across nonces) beats either family alone.
- Mechanism: the outer hash is the phase with no
  template structure and full blocks of independent work,
  the natural vector workload; block 2 keeps the
  midstate machinery.
- Impact: moderate (it composes two proven halves; the
  batching delay is the cost). Difficulty: high.
  Confidence: low. Cost: weeks. Status: untested.

### X-036: Vector rotate by shuffle versus vprold
- Statement: on this core, emulating 32-bit rotates with
  vbmi2 shuffles plus blends is slower than vprold by a
  margin large enough to settle the multi-buffer rotate
  implementation permanently.
- Mechanism: rotate cost is paid 6 times per round per
  lane set; small differences multiply by 192 rounds.
- Impact: small (a component decision inside X-031).
  Difficulty: low (micro-kernel). Confidence: high.
  Cost: hours. Status: untested.

### X-037: AVX-512 IFMA applicability (refutation expected)
- Statement to close: avx512ifma (52-bit fused
  multiply-add) has no application to SHA-256d rounds,
  which contain no multiplications and whose additions
  are 32-bit modular with carries that do not align to
  52-bit lanes in any useful packing.
- Mechanism: instruction semantics versus round anatomy;
  analysis only, with one packing attempt documented if
  a plausible one is proposed.
- Impact: negligible; closes a flag-driven suggestion
  (the flag is present, the fit is not). Difficulty: low.
  Confidence: high. Cost: hours. Status: untested
  (analysis entry).

### X-038: AVX-512 VNNI applicability (refutation expected)
- Statement to close: vpdpwssd-style dot products do not
  map onto SHA-256's Boolean and rotation structure; no
  round subexpression is a sum of products.
- Mechanism: round anatomy inspection; analysis only.
- Impact: negligible; same closure purpose as X-037.
  Difficulty: low. Confidence: high. Cost: hours.
  Status: untested (analysis entry).

### X-039: Lane refill by gather versus register transpose
- Statement: refilling multi-buffer lanes from 16
  separate header buffers with vpgatherdd is slower than
  loading four headers and transposing in registers,
  because mining headers share all but the nonce word.
- Mechanism: mining-specific: lanes differ only in W3 of
  block 2 (and the resulting state), so the transpose is
  mostly broadcast; the general library case (arbitrary
  messages) is what gather is for.
- Impact: small (refill happens once per lane-batch, not
  per round). Difficulty: medium. Confidence: medium.
  Cost: days. Status: untested.

### X-040: Multi-buffer lanes bound to different templates
- Statement: assigning the 16 lanes to 16 different
  templates (solo server serving many jobs) costs nothing
  per hash versus same-template lanes, because lanes are
  independent by construction.
- Mechanism: midstate and prefix are per-lane setup data;
  the round loop is template-agnostic.
- Impact: small (a solo-server design freedom, proven
  cheaply here rather than assumed). Difficulty: medium.
  Confidence: high. Cost: days. Status: untested.

### X-041: Sustained AVX-512 frequency behaviour
- Statement: sustained zmm-heavy work on this guest
  either does or does not degrade clocks (its own or the
  co-running miner's) over a 10-minute window; the
  experiment is a drift measurement, not a kernel.
- Mechanism: host power management is invisible from the
  guest (no cpufreq); wall-clock drift of a fixed SHA-NI
  reference loop before, during, and after zmm load is
  the observable.
- Impact: small as speed; gates every AVX-512 claim this
  programme makes. Difficulty: low. Confidence: high
  that the measurement is decisive either way. Cost:
  hours. Status: untested.

### X-042: Mask-predicated partial waves
- Statement: using AVX-512 mask registers to run partial
  multi-buffer waves (fewer than 16 active lanes) with
  zero dummy-lane hashes preserves exact coverage
  accounting and costs less than padding with throwaway
  nonces.
- Mechanism: predicated vector ops skip masked lanes;
  dummy lanes would pollute attempted counts (Task 003.9
  definitions forbid the confusion).
- Impact: small (tail handling correctness more than
  speed). Difficulty: medium. Confidence: medium.
  Cost: days. Status: untested.

## Workstream D: compiler, codegen, automated search

### X-043: Clang build of the hand kernels
- NEW JUSTIFICATION (per R-03's reopening condition):
  EXP-001 swept flags on the production wrapper, whose
  hot code is libcrypto's; the h02_shani kernels' hot
  code is ours, so a different compiler's scheduler and
  allocator are a genuinely new variable there.
- Statement: clang (once obtainable at $0) builds of
  h02_shani.c and h01_multistream.c beat the gcc builds'
  medians on the shared harness.
- Impact: small to moderate (compiler choice on a
  register-starved kernel is a real variable).
  Difficulty: medium (obtaining clang is the cost).
  Confidence: low. Cost: days. Status: untested.

### X-044: Profile-guided optimization of the H-01 kernel
- NEW JUSTIFICATION: as X-043; PGO was pointless on the
  wrapper file (EXP-001 reasoning) and is untested on a
  file whose hot loop is the product.
- Statement: a PGO build of h01_multistream.c, trained on
  harness workloads, beats its non-PGO build beyond
  spread.
- Impact: small (layout and branch hints on a hot,
  branch-light loop). Difficulty: low. Confidence: low.
  Cost: hours. Status: untested.

### X-045: Flag sweep restricted to the research kernels
- NEW JUSTIFICATION: R-03 settles flags for
  mining/cpu/bal_batch.c only and explicitly reopens for
  a different source file; this entry is that file class.
- Statement: among gcc flag sets, the production set
  (-O3 -march=native) is not optimal for h02_shani.c;
  unroll and scheduling flags move its median.
- Impact: small (the kernel is already close to its
  source's intent). Difficulty: low. Confidence: medium.
  Cost: hours (compiler_sweep.py protocol). Status:
  untested.

### X-046: Manual intrinsic reordering in H-02 source
- Statement: reordering the intrinsic statements in
  shani_core.h's round macro (schedule production hoisted
  relative to round consumption) changes the compiled
  schedule enough to measure, because gcc's scheduler
  respects the serial dependencies it can see and
  statement order breaks its ties.
- Mechanism: tie-breaking in instruction scheduling.
- Impact: small. Difficulty: low. Confidence: medium.
  Cost: hours. Status: untested.

### X-047: Aliasing and alignment annotations in H-01
- Statement: restrict-qualified pointers and aligned
  buffer types in h01_multistream.c reduce spill reloads
  in the compiled hot function (fewer than the measured
  365 xmm stack ops) at equal correctness.
- Mechanism: alias analysis is what licenses the compiler
  to keep vectors in registers across stores.
- Impact: small to moderate (reload count is the spill
  cost's other half). Difficulty: low. Confidence:
  medium. Cost: hours. Status: untested.

### X-048: SMT-verified peephole pass over the hot function
- Statement: a Souper-style peephole search over the
  compiled hash_p1 finds at least one verified
  instruction-sequence simplification the compiler
  missed.
- Mechanism: the hot function mixes SHA intrinsics (opaque
  to the peephole search) with ordinary shuffles, adds,
  and moves, where peephole wins live.
- Impact: small (a few instructions in 494, if any).
  Difficulty: high (tooling). Confidence: low. Cost:
  weeks. Status: untested.

### X-049: Parameterized kernel generator and sweep driver
- Statement: a generator emitting kernels for the grid
  (streams 1..8) x (wave shapes) x (assignment) x
  (prefix modes), each behind the standard gate set,
  finds the measured optimum of the SHA-NI family faster
  and more completely than hand-built variants.
- Mechanism: the variants differ in a few structural
  parameters; generating them removes per-variant
  handwriting cost and error.
- Impact: moderate as programme velocity (it converts
  X-001 to X-005, X-019 and more into one sweep).
  Difficulty: medium. Confidence: high. Cost: days to
  weeks. Status: untested.

### X-050: Link-time optimization across the research kernels
- Statement: LTO across h02_shani.c and its harness-side
  wrappers recovers the remaining call-boundary losses
  that X-016's inlining does not reach.
- Mechanism: cross-unit inlining and constant propagation
  of the template struct.
- Impact: negligible to small. Difficulty: low.
  Confidence: medium. Cost: hours. Status: untested.

### X-051: Hot and cold section split
- Statement: placing template setup, error paths, and
  test hooks in cold sections, with the per-nonce loop
  alone in the hot text, measurably helps at 4 streams,
  where the hot function is about 12 KB.
- Mechanism: I-cache and fetch-window locality
  (MEMORY_AND_CACHE_RESEARCH.md section 3.3).
- Impact: negligible to small. Difficulty: low.
  Confidence: low. Cost: hours. Status: untested.

### X-052: Vector width preference tuning for multi-buffer
- Statement: -mprefer-vector-width=256 versus 512 changes
  the AVX-512 multi-buffer build's performance
  materially, because the compiler's zmm scheduling under
  register pressure differs from hand-width choice.
- Mechanism: compiler heuristic versus measured pressure.
- Impact: small, conditional on X-031 existing.
  Difficulty: low. Confidence: medium. Cost: hours.
  Status: untested.

## Workstream C: memory, cache, data handling

### X-053: Non-temporal stores for the batch digest buffer
- Statement: writing batch digests with streaming stores
  raises batch throughput by keeping the 32 MB per 1M
  output out of the cache hierarchy the kernel's stack
  and operands live in.
- Mechanism: cache pollution avoidance; the consumer
  reads flags, not digests, in search-shaped use.
- Impact: negligible to small (digest stores are about
  106 MB/s at the best measured rate, about 4 percent of
  the measured copy floor; the win is pollution, not
  bandwidth). Difficulty: low. Confidence: low. Cost:
  hours. Status: untested. Distinct from H-04, which
  removes the writes; this keeps and reroutes them.

### X-054: Ring-buffer output with consumer overlap
- Statement: a small L2-resident ring of digest blocks,
  with the flag consumer overlapping the producer's next
  chunk, beats one monolithic output buffer at large
  batch counts.
- Mechanism: producer-consumer locality; the monolithic
  buffer's tail is cold by the time it is read.
- Impact: negligible to small. Difficulty: medium.
  Confidence: low. Cost: days. Status: untested.

### X-055: Interleaved digest and flag layout
- Statement: interleaving each digest with its flag byte
  (33-byte stride) makes the batch consumer's pass touch
  one stream instead of two, at a small producer cost.
- Mechanism: consumer locality versus producer stride;
  which side wins is a measurement.
- Impact: negligible. Difficulty: low. Confidence: low.
  Cost: hours. Status: untested.

### X-056: Next-template prefetch during the span tail
- Statement: prefetching the next template's midstate and
  operand tables during the current span's final wave
  removes the setup bubble at template switches.
- Mechanism: setup is per-template and tiny; the bubble
  is the pipeline drain, not the setup cost.
- Impact: negligible (templates live about 44 minutes at
  current rates; the bubble is amortized to nothing).
  Difficulty: low. Confidence: high that the effect is
  negligible; registered to close the suggestion with a
  bound. Cost: hours. Status: untested.

### X-057: Rolled versus unrolled stream body
- Statement: a rolled 4-stream body (stream loop inside,
  smaller code) beats the fully unrolled inlined body
  (2,985 instructions) once I-cache pressure is priced
  in.
- Mechanism: loop overhead per wave versus fetch
  locality; the two builds bound the tradeoff.
- Impact: small, in either direction. Difficulty: medium.
  Confidence: medium. Cost: days. Status: untested.

### X-058: Single-cache-line template struct
- Statement: packing the per-template data a worker reads
  per nonce (midstate, prefix state, operand tables,
  target) into one or two cache lines, 64-byte aligned,
  removes the remaining per-nonce load misses in hand
  kernels.
- Mechanism: the hot loop's 43 memory references
  (hash_p1) include template reads that should never
  miss.
- Impact: negligible to small (likely already resident;
  this makes it structural). Difficulty: low.
  Confidence: medium. Cost: hours. Status: untested.

## Workstream E: mining pipeline

### X-059: Candidate construction caching in MiningEngine
- Statement: MiningEngine.build_candidate re-verifies
  every template transaction (strip_witness plus two
  hashes per tx) and performs a validateaddress RPC call
  on every invocation, and mine_cycle invokes it once per
  extranonce step (up to 64 per template); caching the
  verified transaction set and the payout script per
  template removes nearly all of that repeated work.
- Mechanism: per-template facts are recomputed per
  extranonce although only the coinbase changes.
- Impact: small at current rates (construction is per
  extranonce round, not per nonce; the RPC round trip
  dominates the waste), growing with kernel speed.
  Difficulty: low. Confidence: high. Cost: days.
  Status: untested.

### X-060: Incremental merkle spine per extranonce
- Statement: when only the coinbase changes, the merkle
  root can be recomputed by rehashing only the left spine
  of the tree (log2(n) hashes) instead of the full root
  over all txids (n hashes), with identical results.
- Mechanism: the coinbase is leaf 0; only its path to the
  root changes.
- Impact: small (matters for large templates and fast
  extranonce stepping; trivial for empty regtest
  templates). Difficulty: low. Confidence: high.
  Cost: hours. Status: untested.

### X-061: In-place extranonce patching of the coinbase
- Statement: the serialized coinbase differs across
  extranonce steps only in the scriptSig extranonce
  bytes, so patching those bytes in a cached block body
  (and recomputing only the coinbase txid) reproduces
  build_candidate's output byte-for-byte at a fraction
  of the construction cost.
- Mechanism: byte-level invariance of the rest of the
  block body, verified against the existing builder.
- Impact: small (pairs with X-059 and X-060).
  Difficulty: low. Confidence: high. Cost: hours.
  Status: untested.

### X-062: Event-driven span preemption
- Statement: waking the search loop on a job-generation
  event (condition variable signalled by the Stratum
  reader) instead of at span boundaries cuts the stale
  window from about one span (about 1 s) to the event
  latency, at equal hash rate.
- Mechanism: the freshness information already arrives
  asynchronously; only the search loop's polling
  granularity is coarse.
- Impact: small (stale fraction is about 0.17 percent at
  1 s spans on mainnet timing; the win is bounded by
  that). Difficulty: medium. Confidence: high. Cost:
  days. Status: untested.

### X-063: Verification overlap at dense targets
- Statement: at regtest-class target densities, moving
  candidate verification to a second thread while the
  search continues raises net accepted-block rate,
  because verification (3.5 to 5.7 us per candidate,
  measured) otherwise serializes with search.
- Mechanism: producer-consumer split of the confirmation
  chain; at mainnet densities the queue is empty and the
  cost is one thread's existence.
- Impact: small, target-conditional (zero at mainnet
  difficulty). Difficulty: medium. Confidence: medium.
  Cost: days. Status: untested.

### X-064: Template double-buffering in mine_cycle
- Statement: issuing the GBT longpoll for the next
  template while the current cycle's nonce space is
  still being searched removes the serial template wait
  at cycle boundaries in mining/engine.py.
- Mechanism: wait_template already longpolls; the cycle
  currently fetches only at its start.
- Impact: small (one round trip per cycle, hidden).
  Difficulty: medium. Confidence: medium. Cost: days.
  Status: untested.

### X-065: Stratum extranonce2 pre-generation
- Statement: pre-generating the next several extranonce2
  values and their headers during the current search
  (the coinbase and merkle work for each is Python
  hashlib today) removes the per-round construction
  pause in mining/mainnet_live.py's job loop.
- Mechanism: construction is per job round, hashing is
  continuous; overlap them.
- Impact: negligible to small (construction is already
  amortized at 1 s spans). Difficulty: low. Confidence:
  medium. Cost: hours. Status: untested.

### X-066: Evidence and status I/O off the mining loop
- Statement: the live runner's status file writes and
  JSONL evidence appends, though throttled to 10 s,
  still occur on the mining thread; moving them to a
  writer thread measurably smooths the rate (fewer
  multi-millisecond stalls in the rate series).
- Mechanism: file I/O latency spikes land inside
  measured spans today.
- Impact: negligible to small (visible in spread, not
  median). Difficulty: low. Confidence: medium. Cost:
  hours. Status: untested.

## Workstream G: measurement, statistics, reproducibility

### X-067: Quiet-window integration decision re-run
- Statement: repeating the EXP-003 decision protocol
  (round-robin interleaved, 2 threads, production versus
  H-02 versus H-01 streams 2 and 4) in a window with the
  mainnet node past initial block download, with at
  least 9 repeats per contender and the node state
  recorded, separates the ranges that overlapped under
  load average 7.46 with production spread 142.3 percent.
- Mechanism: the signal (medians 1.75x to 2.6x) is
  consistent across three sessions; only the noise
  floor is in question.
- Impact: large as a decision (it gates the integration
  of the best verified kernel family). Difficulty: low.
  Confidence: medium that the window separates them;
  the experiment is decisive either way. Cost: hours of
  machine time. Status: untested.

### X-068: Drift across VM replacements
- Statement: the same kernel, benchmarked before and
  after a VM replacement (host change), shows a rate
  shift larger than within-session spread, quantifying
  how much of this programme's variance is host identity.
- Mechanism: the guest has been observed on different
  host CPUs across replacements; the probe fingerprint
  (X-069) makes the comparison well-defined.
- Impact: negligible as speed; large as metrology (it
  prices every cross-session comparison in the record).
  Difficulty: low. Confidence: medium. Cost: hours,
  opportunistically. Status: untested.

### X-069: Session fingerprinting of benchmark records
- Statement: attaching the machine probe JSON (or its
  hash) and the live load and steal figures to every
  benchmark record makes every historical result
  reproducible-or-flagged, at no runtime cost.
- Mechanism: process change in the harness, not the
  kernel.
- Impact: negligible as speed; foundational for
  Workstream G. Difficulty: low. Confidence: high.
  Cost: hours. Status: untested.

### X-070: Steal-time covariate
- Statement: recording guest steal time (visible in
  /proc/stat) during each benchmark run and regressing
  measured rate against steal explains a majority of the
  session spread, converting unusable wide-spread runs
  into corrected estimates with honest intervals.
- Mechanism: on a capped shared host, steal is the
  physical cause of most variance; measuring the cause
  beats repeating around it.
- Impact: moderate as metrology (it could retroactively
  sharpen EXP-000 to EXP-003's conclusions and lower the
  repeats every future experiment needs). Difficulty:
  low. Confidence: medium. Cost: days. Status: untested.

### X-071: Minimum detectable effect sizing
- Statement: for a target effect of 2.4 percent (the
  H-03 class) at this VM's observed spreads, the
  required repeat count under the current protocol is in
  the hundreds; computing this before running
  micro-experiments prevents inconclusive-by-design
  experiments.
- Mechanism: power arithmetic from measured spreads.
- Impact: negligible as speed; prevents wasted runs
  (H-03's inconclusive verdict is the motivating case).
  Difficulty: low. Confidence: high. Cost: hours.
  Status: untested.

### X-072: Paired-run ratio design
- Statement: benchmarking candidate and baseline in
  alternating short slices within one run and analysing
  per-slice ratios (rather than separate session
  medians) detects a 10 percent effect at this VM's
  noise level with a third of the repeats the decision
  run used.
- Mechanism: pairing cancels slow session drift, the
  dominant noise component (the decision run's interleave
  was a manual version of this).
- Impact: moderate as metrology. Difficulty: low.
  Confidence: medium. Cost: days. Status: untested.

### X-073: Thread and stream mix under the cap
- Statement: on this capped VM, the best (workers x
  streams) combination is not (2 x 4): (1 x 4), (2 x 2),
  and (3 x 2) each beat it in total throughput under some
  contention states, and the winner correlates with
  steal.
- Mechanism: workers oversubscribe the roughly 1.5
  effective CPUs; streams do not consume scheduler slots.
- Impact: small to moderate for this VM's totals (the
  per-worker ranking is settled; the mix is not).
  Difficulty: low. Confidence: medium. Cost: hours.
  Status: untested.

### X-074: Three worker threads for the H-01 kernel
- Statement: the H-01 kernel at 3 worker threads totals
  higher than at 2 on this VM, reversing the production
  path's tuned answer, because its per-worker efficiency
  changes the oversubscription tradeoff.
- Mechanism: tune_c_threads tuned the OpenSSL path; the
  stream kernel's cost shape differs.
- Impact: small. Difficulty: low. Confidence: medium.
  Cost: hours. Status: untested.

### X-075: Stop-flag granularity in multi-stream search
- Statement: checking the stop flag once per wave (the
  current wave-atomic design) versus once per stream
  inside the wave changes early-exit latency at dense
  targets without changing accounting correctness, if
  attempted is defined per completed stream.
- Mechanism: wave atomicity is an accounting choice, not
  a correctness requirement; finer stops waste less
  post-hit work.
- Impact: negligible at mainnet targets, small at dense
  targets. Difficulty: medium (accounting proofs must be
  redone). Confidence: medium. Cost: days. Status:
  untested.

### X-076: Chunk-claim size sweep in the research kernel
- Statement: dynamic chunk claiming (workers atomically
  claim chunks of a span) with chunk sizes swept from
  2^12 to 2^20 finds a size that beats static span
  partitioning under induced contention, at no cost on a
  quiet machine.
- Mechanism: the kernel-side version of H-11, with the
  chunk size as the measured variable rather than a
  design guess.
- Impact: small, contention-conditional. Difficulty:
  medium. Confidence: medium. Cost: days. Status:
  untested.

### X-077: Heterogeneous workers
- Statement: running one H-02-stream worker and one
  OpenSSL-path worker concurrently totals more than two
  of either, because their port and latency profiles
  differ and interleave at the machine level.
- Mechanism: machine-level complementarity, the thread
  analogue of X-009's phase argument.
- Impact: small. Difficulty: low. Confidence: low.
  Cost: hours. Status: untested.

## Workstream A continued: deeper structure

### X-078: Alternative MSG grouping (GENC-style)
- Statement: a schedule construction that completes the
  group two ahead instead of three (a different MSG1/MSG2
  phasing) reduces the alignr shuffle count per
  compression versus the GENA/GENB construction H-02
  uses.
- Mechanism: the alignr terms supply W[i+9]; their count
  depends on the phasing choice.
- Impact: negligible to small (shuffles counted in the
  hot function are the prize). Difficulty: medium.
  Confidence: low. Cost: days. Status: untested.

### X-079: Pre-rotated schedule copies to cut alignr use
- Statement: keeping a second, byte-rotated copy of the
  oldest schedule group in a spare register lets MSG2
  take its W[i+9] term without an alignr, at the cost of
  one extra register in a register-starved kernel.
- Mechanism: a deliberate register-for-instruction trade,
  only testable at 1 and 2 streams where registers exist.
- Impact: negligible to small. Difficulty: medium.
  Confidence: low. Cost: days. Status: untested.

### X-080: Nonce-affine decomposition of the block-2 schedule
- Statement (established algebra, untested application):
  the schedule is built from additions and GF(2)-linear
  sigmas, and block 2 has exactly one nonce-dependent
  input word (W3), so every expanded word is an affine
  function of W3: W_t = C_t + L_t(W3), with C_t a
  template constant and L_t a fixed GF(2)-linear map.
  The hypothesis is that some basis-precomputed form of
  the correction L_t(W3) beats the recurrence in a
  scalar or GPU-style kernel.
- Mechanism: precompute the correction schedules for the
  32 basis vectors of W3 per template; per nonce, sum
  the selected corrections. The honest obstacle, stated
  up front: naive selection costs up to 32 adds per
  word, worse than the recurrence; the entry exists to
  test structured forms (byte-wise bases, MSG-shaped
  corrections), not the naive one.
- Impact: negligible for SHA-NI (MSG already wins);
  small, speculative, for scalar and circular-schedule
  designs. Difficulty: high. Confidence: low. Cost:
  days to weeks. Status: untested.

### X-081: Best-so-far return from search
- Statement: a search entry point that also returns the
  lowest digest seen in the searched range (the
  bal-miner bench behaviour) costs under 1 percent
  versus the winner-only search, and removes the second
  pass pool software needs for best-share reporting.
- Mechanism: one compare per nonce against a running
  minimum, branchless.
- Impact: negligible as speed; a pipeline completeness
  feature priced honestly. Difficulty: low. Confidence:
  medium. Cost: hours. Status: untested.

### X-082: Measured dispatch ladder, extended
- Statement: extending ComputeEngine's self-test ladder
  to probe H-01 stream counts and H-02 (and later the
  vector family) at startup, keeping the measured winner
  per machine, beats any static default across the
  fleet's heterogeneous machines.
- Mechanism: the fleet's machines differ in cap, cores,
  and ISA; per-machine measurement is the only selection
  that survives that (the tune_c_threads pattern,
  generalized).
- Impact: moderate at fleet level (zero on a machine
  whose default was already right). Difficulty: medium.
  Confidence: high. Cost: days. Status: untested.

### X-083: Span-length crossover for kernel selection
- Statement: kernels with higher per-template setup
  (operand precompute, X-024) lose on short spans and win
  on long ones; the crossover span is measurable and
  dispatch should switch on it.
- Mechanism: setup amortizes over span length; the live
  miner's roughly 1 s spans sit at a specific point on
  that curve.
- Impact: small. Difficulty: low. Confidence: medium.
  Cost: hours. Status: untested.

### X-084: Fallback ladder equivalence verification
- Statement: every rung of the dispatch ladder produces
  bit-identical results on a fixed differential corpus
  run at selection time, not just its genesis self-test;
  a rung that fails is excluded with the reason recorded.
- Mechanism: genesis alone exercises one template; the
  corpus exercises template variation and boundaries.
- Impact: negligible as speed; a correctness gate for
  X-082. Difficulty: low. Confidence: high. Cost:
  hours. Status: untested.

### X-085: Sustained-rate decay of the fast kernels
- Statement: over a 10-minute continuous run, the H-01
  kernels' rate decays (or does not) relative to the
  OpenSSL path's, under the VM cap; if the faster kernel
  decays more, short-burst benchmarks overstate its
  mining value.
- Mechanism: host power and contention dynamics over
  minutes, invisible in 1M-hash bursts.
- Impact: small as speed; gates the mining relevance of
  every burst measurement. Difficulty: low. Confidence:
  medium. Cost: hours. Status: untested.

### X-086: Lock-free winner publication
- Statement: replacing the mutex-published winner
  (bal_search.h pattern, mirrored by the research
  kernels) with a single atomic compare-and-swap on a
  winner slot reduces publish latency at dense targets
  measurably, with identical first-published semantics.
- Mechanism: one CAS versus a lock round trip, on a path
  that is cold at mainnet targets and hot at regtest
  targets.
- Impact: negligible at mainnet targets, small at dense
  targets. Difficulty: medium (memory-ordering proof
  obligations). Confidence: medium. Cost: days. Status:
  untested.

### X-087: False sharing in per-worker counters
- Statement: the per-worker attempted counters and job
  structs in the C libraries share cache lines across
  workers; padding them to one line each measurably
  reduces the 2 and 4 thread spread.
- Mechanism: workers write attempted once per span, so
  the effect should be tiny; the entry prices a standard
  suspicion instead of assuming it.
- Impact: negligible (expected; cheap to settle).
  Difficulty: low. Confidence: medium. Cost: hours.
  Status: untested.

### X-088: Vectorized target comparison for batch consumers
- Statement: comparing a batch of digests against the
  target with AVX2 (most-significant word first, early
  termination per digest) beats the scalar byte loop in
  the batch consumer at 1M scale.
- Mechanism: the production meets() loop walks bytes from
  the top; most digests are decided by the first word.
- Impact: negligible to small (comparison is already
  off the search path; this is the enumeration consumer).
  Difficulty: low. Confidence: medium. Cost: hours.
  Status: untested.

### X-089: Target-specialized exact comparator
- Statement: for share-class targets (pool difficulty),
  whose top bytes have long fixed prefixes, a comparator
  specialized on the target's first differing word is
  measurably faster than the generic loop, and remains
  exact for every target by construction (generic path
  retained for arbitrary targets).
- Mechanism: specialization on a runtime-checked target
  shape, not an approximation.
- Impact: negligible (comparison cost is already minor).
  Difficulty: low. Confidence: medium. Cost: hours.
  Status: untested.

### X-090: Pre-swapped header storage for the OpenSSL wrapper
- Statement: storing the template header with block 2's
  fixed bytes pre-assembled (so hash_nonce's per-nonce
  block build is a 16-byte patch instead of field-by-field
  assembly) shrinks the production wrapper's 408
  instructions measurably.
- Mechanism: the wrapper rebuilds block bytes 64..79 per
  nonce although only 4 bytes vary.
- Impact: small within the production path (which the
  hand kernels may retire anyway). Difficulty: low.
  Confidence: medium. Cost: hours. Status: untested.

## Workstream F: automated discovery and formal closure

### X-091: Superoptimizer search over inter-pair shuffles
- Statement: an enumerative superoptimizer over the
  shuffle and move sequences between RNDS2 pairs (the
  non-SHA instruction glue of the H-02 kernel) finds a
  shorter verified sequence than the compiler emitted.
- Mechanism: the glue is small, pure, and exactly
  specified, the ideal superoptimizer target; SHA
  instructions themselves are treated as atoms.
- Impact: small (the glue is a minority of 494
  instructions). Difficulty: high. Confidence: medium.
  Cost: weeks. Status: untested.

### X-092: Peephole equivalence pass on shipped binaries
- Statement: running a Souper-style synthesis pass over
  the compiled research libraries (not just the hot
  function) finds verified simplifications in the batch
  and search scaffolding code.
- Mechanism: scaffolding code is ordinary integer C,
  where peephole synthesis has its documented wins.
- Impact: negligible to small. Difficulty: high.
  Confidence: low. Cost: weeks. Status: untested.

### X-093: Genetic search over stream interleave orders
- Statement: treating the interleave order of a wave
  (which stream's round pair issues at each slot) as a
  genome and evolving it against harness fitness finds
  orders beating the regular round-robin by a measurable
  margin; correctness is by construction (streams are
  independent), so no proof burden attaches to the
  search itself.
- Mechanism: issue order interacts with port contention
  in ways a fixed pattern does not explore.
- Impact: small to moderate. Difficulty: medium.
  Confidence: low. Cost: days (compute-bound search).
  Status: untested.

### X-094: Logic minimization of the joint Ch/Maj cone
- Statement: espresso-style two-level minimization,
  followed by multi-level factoring and z3 verification,
  finds a shared-subterm evaluation of Ch and Maj
  together with fewer ops than the proven separate forms
  (3 and 4 ops) evaluated independently.
- Mechanism: joint cones share terms the separate forms
  cannot; this is the systematic version of X-027 aimed
  at the two functions every vector round evaluates.
- Impact: small within vector designs (two functions of
  the roughly 30 ops per round). Difficulty: medium.
  Confidence: medium. Cost: days. Status: untested.

### X-095: Bayesian optimization over kernel parameters
- Statement: a Bayesian optimizer over the discrete
  parameter grid (streams, wave, chunk, assignment,
  unroll) reaches the family's measured optimum in fewer
  harness evaluations than grid sweep, with the harness
  as the only oracle.
- Mechanism: the response surface is smooth in most
  parameters; grid sweep wastes runs in flat regions.
- Impact: negligible as kernel speed; moderate as
  programme velocity once the generator (X-049) exists.
  Difficulty: medium. Confidence: medium. Cost: days.
  Status: untested.

### X-096: Cross-backend differential fuzzing at scale
- Statement: a fuzzing campaign of 10 million randomized
  templates across every backend and dispatch rung finds
  at least one divergence the gate sets missed, or
  raises the programme's confidence in their equivalence
  by two orders of magnitude of cases.
- Mechanism: rare divergences live in template corners
  (padding-adjacent values, boundary nonces) that
  structured gates under-sample.
- Impact: negligible as speed; high as correctness
  assurance for the dispatch era. Difficulty: low.
  Confidence: medium. Cost: days of machine time.
  Status: untested.

### X-097: Partial-state target early abort (formal closure)
- Statement to refute, permanently and in writing: no
  function of any proper prefix of the outer compression
  (any state before round 64, with or without the
  feed-forward of earlier words) can decide or
  probabilistically filter the target comparison exactly,
  because the most significant digest word is
  H0[0] + a_63, a_63 depends on all 64 rounds, and the
  lab's full-round output measurements (R-01) show no
  exploitable prefix correlation. This entry extends
  R-06 and H-16 to the remaining variants (inner-state
  aborts, per-word early exits) so each future proposal
  meets a written refutation, not a conversation.
- Impact: none as speed; prevents recurring wasted
  design work. Difficulty: low (the dependency argument
  plus the measured bias curve). Confidence: high.
  Cost: hours. Status: untested (closure entry).

### X-098: Winner-cluster start offsets (formal closure)
- Statement to refute: biasing worker start nonces
  toward regions where previous winners clustered cannot
  raise the per-hash success probability, because winners
  follow the geometric law of the search protocol
  (../results/RESEARCH.md: median scaled nonce 0.50) and
  each hash is an independent trial. The only real
  fleet-level effect is duplicated coverage when workers
  share a start, which is a partitioning question owned
  by H-15, not a heuristic.
- Impact: none as speed; closure. Difficulty: low.
  Confidence: high. Cost: hours. Status: untested
  (closure entry).

### X-099: Meet-in-the-middle split of SHA-256d (formal closure)
- Statement to refute: the double hash cannot be split
  into independently searchable halves, because the
  outer compression's input is the inner digest in full,
  the inner compression's feed-forward mixes the midstate
  into every digest word, and no intermediate value is
  checkable against the target before the outer hash
  completes. Any claimed split must name the checkable
  intermediate; none exists in the structure.
- Impact: none as speed; closure. Difficulty: low.
  Confidence: high. Cost: hours. Status: untested
  (closure entry).

### X-100: Nonce-chosen schedule cheapening (formal closure)
- Statement to refute: choosing nonces whose schedule
  words take special values (zeros, repeated patterns)
  cannot reduce per-hash cost in any lab implementation,
  because SHA-NI instruction cost is data-independent
  and the vector and scalar paths' operation counts are
  likewise fixed by the algorithm, not the data. Cheap
  schedules would require data-dependent execution,
  which none of the candidate families has.
- Impact: none as speed; closure. Difficulty: low.
  Confidence: high. Cost: hours. Status: untested
  (closure entry).

## Remaining pipeline and kernel entries

### X-101: Kernel-level ntime rolling inside the search loop
- Statement: rolling nTime inside the C search loop
  (patch W1, recompute the 3-round prefix in-kernel,
  continue) when a span exhausts the nonce space beats
  returning to Python for a fresh template in the
  MiningEngine path.
- Mechanism: the kernel-side counterpart of H-13; the
  roll cost is 3 rounds plus operand refresh, the
  return-to-Python cost is a boundary crossing plus
  candidate reconstruction.
- Impact: small (binds only when nonce space per
  template is the constraint, which at current rates it
  is not: about 44 minutes per space). Difficulty:
  medium (consensus time rules bind exactly).
  Confidence: medium. Cost: days. Status: untested.

### X-102: Producer-consumer phase pipeline across threads
- Statement: a two-thread pipeline (thread A computes
  block 2 for a stream of nonces, thread B computes
  outer hashes from a queue) beats two independent
  full-hash workers when the phases' port profiles
  conflict inside one thread.
- Mechanism: machine-level phase separation, the
  two-thread form of X-009; the queue and handoff are
  the costs it must beat.
- Impact: small to moderate if X-009's phase premise
  holds. Difficulty: medium. Confidence: low. Cost:
  days. Status: untested.

### X-103: Self-contained template setup in the research lib
- Statement: computing the block-1 midstate inside the
  research library with its own SHA-NI compression
  (bal_h_compress already exists for the FIPS gate)
  instead of any external call makes template setup
  constant-time-comparable and removes a hidden
  dependency from kernel benchmarks.
- Mechanism: setup symmetry; benchmark hygiene more than
  speed (setup is per template).
- Impact: negligible as speed. Difficulty: low.
  Confidence: high. Cost: hours. Status: untested.

### X-104: Multi-template single-call search
- Statement: a single library call searching several
  templates' spans (solo server serving multiple jobs)
  amortizes the roughly 31 microsecond boundary cost
  (EXP-000) across jobs and beats per-job calls at small
  span sizes.
- Mechanism: boundary cost is per call; multi-template
  calls divide it.
- Impact: small, at small spans only. Difficulty:
  medium. Confidence: medium. Cost: days. Status:
  untested.

### X-105: Dual-target flags in-kernel
- Statement: evaluating both the pool share target and
  the network target inside the kernel (two flag bits
  per nonce) removes the live runner's Python-side
  recomputation of meets_network_target for candidates
  and, in batch mode, a second consumer pass.
- Mechanism: one extra compare per nonce against a
  second constant target, in registers.
- Impact: negligible (candidates are rare at real
  targets). Difficulty: low. Confidence: high. Cost:
  hours. Status: untested.

### X-106: Wave-granularity work stealing between workers
- Statement: when one worker's span ends early (hit or
  exhaustion), letting it steal whole waves from a
  sibling's remaining span beats static partitioning
  under variable contention.
- Mechanism: wave granularity is the natural steal unit
  in the stream kernels; static partitions strand work
  behind a stalled worker.
- Impact: small, contention-conditional. Difficulty:
  medium. Confidence: medium. Cost: days. Status:
  untested.

### X-107: Cross-machine ranking portability (blocked on hardware)
- Statement: the family ranking measured here (H-01 over
  H-02 over OpenSSL) does not transfer unchanged to an
  Intel host, where RNDS2 latency and issue width
  differ; the experiment is the same decision protocol
  on a second machine.
- Mechanism: microarchitecture dependence of every
  latency claim in this registry.
- Impact: moderate as knowledge (it decides whether
  dispatch must be per-machine, X-082, or can be
  per-family). Difficulty: low where a machine exists.
  Confidence: medium. Cost: hours, when hardware exists.
  Status: untested, blocked on a second machine.

### X-108: Steal-aware yielding (speculative)
- Statement: when guest steal time spikes, a worker that
  briefly yields lets the co-running node and miner
  processes finish latency-critical work, raising
  whole-system useful output even at equal raw hash rate.
- Mechanism: system-level scheduling courtesy; the hash
  rate cost is real and the benefit is speculative.
- Impact: negligible, speculative. Difficulty: low.
  Confidence: low. Cost: hours. Status: untested.

### X-109: Fully unrolled block-2 body versus rolled
- Statement: unrolling the entire 61-round block-2 body
  (no loop) beats the rolled body at 1 and 2 streams,
  and loses at 4 streams on I-cache pressure, locating
  the unroll optimum per stream count.
- Mechanism: loop overhead per round group versus code
  size (the 4-stream body is already about 12 KB class).
- Impact: small. Difficulty: medium. Confidence:
  medium. Cost: days. Status: untested.

### X-110: Outer K-stream built during block 2
- Statement: laying out the outer hash's K+W operand
  stream as a contiguous array written during block 2's
  tail (rather than gathered per round pair) reduces the
  outer phase's operand stalls.
- Mechanism: operand streaming versus operand gathering;
  the outer phase is round-dense and operand-hungry.
- Impact: negligible to small. Difficulty: medium.
  Confidence: low. Cost: days. Status: untested.

### X-111: Prefix-only digest stores in batch mode
- Statement: storing only the top 8 bytes of each batch
  digest, materializing the full digest only for nonces
  whose prefix is within a factor of the target, cuts
  batch store traffic 4x with exact results (the full
  digest is recomputed for the rare near-miss, counted
  as verification work).
- Mechanism: store traffic reduction short of H-04's
  flags-only endpoint, for consumers that need best-hash
  tracking.
- Impact: negligible to small (the store stream is about
  4 percent of the copy floor today). Difficulty: low.
  Confidence: medium. Cost: hours. Status: untested.

### X-112: Vectorized merkle root for large templates
- Statement: computing a large template's merkle root
  with the SHA-NI compression batched over sibling pairs
  (the tree is a set of independent double hashes per
  level) beats the scalar Python merkle in mining/pow.py
  by enough to matter at solo-server template rates.
- Mechanism: the merkle tree is embarrassingly parallel
  per level; Python hashlib per node is the current cost.
- Impact: small (per template, not per nonce; matters
  only if template rates rise). Difficulty: medium.
  Confidence: high. Cost: days. Status: untested.

### X-113: Coinbase txid caching across templates
- Statement: within one height, consecutive templates
  often share the coinbase except for extranonce and
  fee-driven value changes; caching the coinbase txid
  across template fetches, invalidated by an exact byte
  comparison, removes one double hash per template.
- Mechanism: template-to-template invariance, the
  cross-template version of X-059.
- Impact: negligible (one hash per template).
  Difficulty: low. Confidence: high. Cost: hours.
  Status: untested.

### X-114: Function placement in the shipped miner binary
- Statement: ordering the shipped binary's functions so
  the mining hot path occupies contiguous pages (linker
  script or PGO-ordered linking) measurably reduces the
  live miner's rate spread.
- Mechanism: page and I-cache locality at process scale.
- Impact: negligible to small. Difficulty: low.
  Confidence: low. Cost: hours. Status: untested.

### X-115: Stream count selected per span length
- Statement: within the stream family, short spans favour
  fewer streams (wave remainder dominates) and long spans
  favour more; a span-length switch inside the kernel
  beats any fixed stream count across the live miner's
  span distribution.
- Mechanism: wave remainder cost is per span, latency
  gain is per nonce.
- Impact: small. Difficulty: low. Confidence: medium.
  Cost: hours. Status: untested.

### X-116: Schedule prefetch distance in multi-buffer
- Statement: in the vector multi-buffer kernel, computing
  the schedule k groups ahead of the rounds (software
  pipelining depth k swept from 1 to 4) has an optimum
  strictly inside that range, set by register pressure
  against schedule latency.
- Mechanism: the vector family's version of X-010, with
  more registers in play and more latency to hide.
- Impact: moderate within the family (it is the family's
  central scheduling knob). Difficulty: medium.
  Confidence: medium. Cost: days, once X-031 exists.
  Status: untested.

## Workstream index and registry statistics

Workstream attribution for every entry (section headings
above group most entries; this index is authoritative for
the rest):

- A, mathematical: X-020 to X-030, X-078, X-079, X-080
  (14 entries).
- B, CPU execution: X-001 to X-019, X-031 to X-042,
  X-082, X-083, X-084, X-086, X-090, X-102, X-103, X-106,
  X-109, X-110, X-115, X-116 (43 entries).
- C, memory and data handling: X-053 to X-058, X-087,
  X-088, X-089, X-111 (10 entries).
- D, compiler and code generation: X-043 to X-052, X-114
  (11 entries).
- E, mining pipeline: X-059 to X-066, X-081, X-101,
  X-104, X-105, X-108, X-112, X-113 (15 entries).
- F, automated discovery and formal verification:
  X-091 to X-100 (10 entries).
- G, measurement and reproducibility: X-067 to X-077,
  X-085, X-107 (13 entries).

Total: 116 entries. Four entries (X-026, X-029, X-037,
X-038) are registered expecting refutation by analysis;
four (X-097 to X-100) are formal closures of ideas the
evidence already settles, written so the settlement is
permanent. No entry duplicates an H-series entry;
cross-references are stated on the entries themselves.
