# Assembly Analysis (Stage 1 and Stage 5 groundwork)

All observations from objdump on the libraries as built on this
VM, 2026-11-14. Reproduce with objdump -d on the .so files
under .local/cpu/ and .local/shax/.

## Production library (mining/cpu/bal_batch.c, built by mining/cpu/build.py)

- The library itself contains ZERO sha256rnds2 instructions.
  All compression happens inside OpenSSL's SHA256_Transform,
  reached through 4 call sites; libcrypto.so.3 on this system
  contains 128 sha256rnds2 sites and dispatches to the SHA-NI
  implementation at runtime on this CPU.
- hash_nonce (the per-nonce wrapper: build block 2, transform,
  build the outer block, transform, serialize) compiles to
  408 instructions with a 416-byte stack frame under production
  flags. The frame holds the two 64-byte blocks plus OpenSSL
  context copies. This is the measurable wrapper overhead
  around 125 rounds of real work, and the reason a purpose-built
  SHA-NI kernel (H-01) is the registry's top hypothesis: the
  compression is already optimal-class, the path around it is
  generic streaming-API code.
- EXP-001 flag variants changed the wrapper measurably only for
  -march=x86-64 (534 instructions, 456-byte frame); native
  variants were instruction-identical in hash_nonce (408), which
  foreshadowed the sweep's outcome: the flags do not touch the
  bottleneck, because the bottleneck is inside libcrypto.

## Intrinsics library (mining/cpu/bal_sha_intrin.c)

- 3 sha256rnds2 sites, ZERO sha256msg1 or sha256msg2 sites.
  The message schedule is scalar C (schedule_impl), recomputed
  per nonce, exactly as its source comments state after the
  Task 001 audit corrected them. A SHA-NI kernel without the
  SHA message instructions pays scalar latency for 48
  generated schedule words per block, two blocks per nonce.
- The state snapshot is after round 1 (SHA256RNDS2 pair
  boundary), one round short of the canonical prefix ceiling
  derived in header_and_midstate_analysis.md.

## CUDA shared source (reference only here)

- gpu/cuda/kernels/sha256.h carries both a full 64-word
  schedule compressor and a circular 16-word variant
  (bal_compress_state_circ), host-validated in Tasks 002/003.
  On device it compiled to 32 registers and 64-byte stack in
  its best variant (Task 002 ptxas data). No device exists on
  this VM; nothing device-side is claimed in this programme
  stage.

## H-02 research kernel (experiments/h02_shani/libbal_h02.so, 2026-11-14)

Measured with experiments/h02_shani/asm_report.py (objdump).
Per-nonce hot function hash_p1 (snapshot-after-round-1
mode): 494 instructions, about 2,539 B, sha256rnds2 63
(exactly 31 block-2 pairs + 32 outer pairs), sha256msg1 24,
sha256msg2 24 (12 of each per compression), stack frame
0 B, 2 xmm stack ops, 4 stack refs, 0 calls, 43 memory
refs, and ZERO ror/shr/shl instructions: no scalar schedule
remnant in the hot path. hash_full: 496 insns, rnds2 64.
hash_p2 (snapshot after round 2): 530 insns, rnds2 62,
frame 0 B. bal_h_compress: 175 insns, rnds2 32, msg1 12,
msg2 12. The batch loop (h_worker) calls hash_p1 per nonce
(68 insns, frame 64 B); the search loop inlines it
(h_sworker 575 insns, frame 160 B, 22 xmm stack ops).
Whole binary: rnds2 350, msg1 132, msg2 132. Scalar twin
(libbal_h02_scalar.so): rnds2 286, msg1 0, msg2 0, as
designed; it is the equivalence reference for the MSG path.

## H-01 multi-stream kernel (libbal_h01.so, 2026-11-14)

The standalone 1-stream body (m_run_b2_1) is 176 insns,
rnds2 31, 7 xmm registers live, frame 0 B, zero stack ops.
The compiler inlined all other stream variants and the wave
machinery into walk_span.constprop.0: 2,985 insns, frame
1,056 B, 365 xmm stack ops, 566 stack refs. That is the
register-pressure signature the Stage 5 authorization
predicted for 4 streams: 4 streams x (2 state + 4 schedule
vectors plus K and scratch) cannot fit the 16 architectural
xmm registers, so state and schedule vectors spill to the
stack every wave. Measured throughput still rises with
stream count (registry EXP-003): the spills cost less than
the RNDS2 latency they hide on this core. Whole binary:
rnds2 474, msg1 180, msg2 180 (template init carries its
own 33 rnds2: 32 block-1 + 1 snapshot pair).

## Standing rules for future assembly work

1. Count instructions and stack in the function that runs per
   nonce, not in the whole library.
2. A source transformation that leaves the generated code
   unchanged is not an optimization; check before benchmarking.
3. Spills in the per-nonce function (stack traffic beyond the
   block buffers) are a reject signal for register-pressure
   reasons, to be recorded in the experiment entry.
4. perf counters are unavailable in this guest, so dependency
   chains are reasoned from the instruction listing and
   confirmed or refuted by wall-clock harness results, never
   reported as measured IPC.
