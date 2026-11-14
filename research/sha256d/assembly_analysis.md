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
