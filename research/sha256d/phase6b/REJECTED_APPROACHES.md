# Phase 6B Rejected Approaches

Opened 2026-11-14 with Assignment A. This file
carries the rejections Phase 6B inherits (so they are
not re-run under new names) and will accumulate
Phase 6B's own. Full records live in the experiment
registry and the Phase 6 documents; this file is the
index, with the binding reason in one line each.

Inherited, still binding:

- Compiler flag search as an optimisation route
  (EXP-001): no variant beat production; the hot
  compression lives in libcrypto for the C backend.
- Hand-scheduled SHA-NI schedule-first kernel as
  champion (EXP-006): spill reduction repaid by
  store/load traffic; lost to the unscheduled
  original.
- Cross-nonce phase pipelining on this core
  (EXP-008): parity at every width and geometry.
- K+W constant folding (EXP-014): the fold is a
  per-template constant rebuild plus a live add;
  rejected at model and measurement.
- Bitsliced 32-lane transposed kernel (EXP-015):
  about 0.03x of the multi-buffer kernel; the
  transpose and Boolean adders cost more than the
  lane doubling returns.
- Carry-save for the message schedule, Y-001 and
  Y-002 (EXP-019): priced at 3 instructions per
  resolution (not 2 as first claimed), every
  carry-save form loses at every consumption
  separation in the faithful model; established
  negative. (Carry-save in OTHER cones is EXP-027
  territory and is not covered by this rejection.)
- Heterogeneous worker pairing, MB beside SHA-NI
  (EXP-021): mixed pools measured below the
  homogeneous MB pool at 2 and 4 threads; no
  cross-family relief exists on this guest.
- Y-076 multi-template shared prefixes as specified
  (EXP-023): the reuse lives in data objects, not in
  compression prefixes; the prefix mechanism is
  separately rejected as immaterial (no lab path
  performs a per-step block-1 compression for it to
  attach to).
- Y-065 and Y-075 nonce-separation work reductions
  (EXP-016): refuted by derivation; W20 onward is
  fully nonlinear and state affinity dies at S_8.
- The old min/max separation decision rule
  (EXP-004, EXP-010): failed three times on variance,
  retired by owner decision in favour of the EXP-017
  protocol. It must not be revived as a gate.
- Masking lanes off mid-batch to cover heterogeneous
  spans (the wide reading of Y-084, closed in
  EXP-022's record): lanes advance in lockstep; a
  masked lane's round work is not retired. The
  narrow flags form is NOT rejected; it is verified
  in batch scope and is EXP-024's ingredient.

Phase 6B additions (2026-11-15):

- Span-complete mask collection for search
  (EXP-024 designs D/E): finishing the span before
  extracting candidates costs 6.16x the median time
  to candidate against early exit; established
  negative for search. (The mask compare itself is
  not rejected; it is verified, see EXP-024b.)
- Adaptive lowest-lane extraction as a performance
  claim (EXP-024 design C's distinguishing feature):
  the same-process interleave measured C over B at
  1.011x, null; the B/C margin in EXP-024 was a
  layout and scheduling effect. The extraction
  strategy stays in the code; the claim is retired.
- Explicit VPTERNLOGD cone substitution as a
  combination (EXP-026 C1 TernMask): 0.764x against
  its own strongest ingredient, and no distinct
  codegen over the mask kernel; established
  negative as a combination.
- Register schedule ring, phase pipelining as a
  combination ingredient, and hand-scheduled
  assembly for the combined kernel (EXP-026 C3, C4,
  C5): rejected at the written cost model before
  compilation (spill cost beyond 32 zmm; EXP-008
  parity; EXP-006 negative respectively).
- The EXP-023 cache prototype as written
  (EXP-025): proven unsafe, five stale serves and
  two validation bypasses demonstrated. Never
  integrate that form; the repaired layered
  identity is a different design and is not covered
  by this rejection.
- GFNI affine forms for Ch and Maj, and any
  single-instruction per-byte affine form for
  Sigma0 (EXP-027): refuted by z3 counterexamples
  and the Sigma0 fan-in census. GFNI sigma networks
  are costed out (floor 11 ops, construction 35,
  incumbent 4), not refuted as mathematics.
- Pure VPSHUFB rotations (EXP-027): exhaustive
  search, 0 survivors for ROTR13 and Sigma0. The
  mixed shuffle plus shift/or form is exact but
  costs 4 ops against 1 VPROLD at a measured 2.00x
  price; costed out.
- Rotated and byte-swapped state representations
  (EXP-027): addition does not commute with the
  transform (z3 SAT counterexamples, numerically
  rechecked), so the representation pays rotations
  to save rotations.
- Carry-save beyond the message schedule
  (EXP-027): every round addition has deferral
  distance exactly 0, so at the standing
  3-instruction compressor price every deferred
  form loses to VPADDD in every cone, not only in
  the schedule recurrence EXP-019 priced.
- Kogge-Stone and other lookahead addition networks
  (EXP-027): about 18 ops per add against 1 VPADDD;
  the binary-add counting floor is already met by
  the incumbent. Delayed carry is rejected by the
  same distance-0 result. The 52-bit IFMA
  accumulation form is exact but 5 ops against 4;
  costed out.
- Unrolled direct schedule form and GF(2)-linear
  schedule forms (EXP-027): 259,905 tree nodes at
  W63 against the recurrence DAG's 384 ops; the
  linear form is refuted by EXP-016's W20 result.
