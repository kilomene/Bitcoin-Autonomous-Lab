# Phase 6B Production Integration Log

Opened 2026-11-14 with Assignment A. No Phase 6B
integration has occurred. Entries are appended when
an integration is executed, each recording: the
experiment and its decision record, the owner
decision, the files changed, the gate results
(differential, boundary, accounting, memory safety,
dispatch, fallback), the fresh regtest block
(height and hash), the deployment observation, and
the post-integration audit reference.

State carried in at phase open, for continuity:

- Production backend: v512 (AVX-512 multi-buffer),
  integrated 2026-11-14 under the owner's adoption
  of the EXP-017 decision rule. Full record:
  research/sha256d/phase6/PHASE6_FINAL_REPORT.md
  (integration addendum) and POST_INTEGRATION_AUDIT.md
  (verdict PASS WITH NOTES; its notes D-1, N-1, N-2
  are resolved, verified again in
  CURRENT_PRODUCTION_AUDIT.md section 8, K-6).
- Pending owner decisions (not integrations):
  EXP-022 flags output shape for the engine's batch
  consumers (batch scope only); EXP-023 Y-077
  data-level caching in mining/engine.py, additionally
  gated by EXP-025 in this phase.
- Known-good fallback preserved: the C backend
  (mining/cpu/bal_batch.c) remains a full production
  selection (requested="c"), and the pre-integration
  file copies are retained under
  .local/pre-avx512-integration/ on the VM (local
  only, not in the repository).

## Entry 1: EXP-026 candidate C2 (DualMask) integrated as backend "v512dual" (2026-11-14)

- Experiment and decision record: EXP-026
  (research/sha256d/phase6b/EXP026_AVX512_EXECUTION.md),
  verdict VERIFIED IMPROVEMENT under the owner's
  adopted EXP-017 rule: C2 DualMask pooled 1.718x vs
  the production single-batch search (density 0,
  2 threads, CI entirely above 0 in every session and
  pooled) and 1.444x vs its strongest single
  ingredient, mask C. EXP-024b afterwards certified
  the single-batch mask form at 1.398x and left
  DualMask as the leading integration candidate.
- Owner decision: explicit, 2026-11-14, in chat:
  "Integrate DualMask after EXP-024b finishes".
  EXP-024b completed before this integration began.
- Design: new production kernel
  mining/cpu/bal_avx512_dual.c, byte-identical to the
  research source
  research/sha256d/extreme_optimization/src/
  avx512_mb_exp026_dual.c except the header comment,
  the bal_search.h include path, and the production
  export renames (bal_vd_search2 from
  bal_v_e26d_search2, the DualMask counted search;
  bal_vd_batch2 from bal_r_batch2, the dual-batch
  enumeration in the same source; bal_vd_search2_exp018
  from bal_r_search2, retained for source parity and
  not called by the engine). Body identity after the
  rename mapping was verified by diff. New backend
  "v512dual" in the gpu/engine.py ComputeEngine seam.
  Dispatch order: CUDA (unchanged), then v512dual,
  then v512 (single-batch, preserved untouched), then
  C. Selection requires the library to load completely
  (every symbol checked with hasattr before any
  argtypes assignment, in engine.py and build.py, per
  audit defect D-1), the flag-free probe to confirm
  AVX-512F and AVX-512BW, and a self-test spanning the
  dual-batch shape (batch digest check plus a
  single-threaded 64-nonce counted search crossing
  both batches and the 32-lane boundary; single thread
  because the counted context publishes the first
  winner across spans, so a multi-span all-meet probe
  would be a race, a flakiness found and fixed during
  this integration's gate runs). Any failure degrades
  loudly to v512. requested="c" still pins C and
  requested="v512" still pins the single-batch kernel.
- Build: mining/cpu/build.py build_v512dual compiles
  the dual translation unit separately with the
  restricted flags -O3 -mavx512f -mavx512bw (never
  -march=native), links the flag-free probe, and
  smoke-tests before reporting. Objdump audit of the
  production libbal_v512dual.so: zero unambiguous
  AVX-512DQ, VBMI or IFMA mnemonics (vpmullq, vpermi2,
  vpermt2, vpmultishift, vpmadd52, vcvt*qq families
  all absent); the vextracti32x4 and vinserti64x4
  forms present are AVX-512F instructions, also
  present in the shipped v512 production library and
  emitted by gcc under the same restricted flag set.
  103 vpternlogd and 30 vpcmp instructions present,
  matching the research kernel's census in kind.
- Accounting: the engine mirrors the C2 dual-atomic
  semantics exactly (attempted counts real nonces of
  completed 32-lane dual groups plus single-group
  tails; backend_hashes counts lane computations
  including dummy lanes, never below attempted); bad
  candidates trigger the same fail-closed CPU rescan
  as the existing backends.
- Gates, all through the production path, all before
  live deployment (tests/test_avx512_dual_integration.py,
  wired into the suite as make test-avx512dual and
  into test-all):
  1. Differentials: 197,616 randomised digests via
     the production ComputeEngine batch ABI, 0
     mismatches vs hashlib, including batch sizes
     15/16/17/31/32/33/63/64/65 and spans ending
     exactly at 2^32.
  2. Candidate-set equivalence vs hashlib recount at
     mainnet-like density and at about 2^-12: exact.
  3. Accounting parity: on misses, attempted and
     backend_hashes exactly equal an independent
     simulation of the dual walker at ordinary and
     boundary sizes; on hits, backend_hashes is a
     whole number of 16-lane groups, never below
     attempted.
  4. Forced fallback three ways, in scratch copies
     only (probe-failure library, corrupted-source
     build failure, absent library): each lands on
     v512 and keeps mining genesis. Symbol-incomplete
     dual libraries are rejected as a whole with the
     missing entry points named (D-1 mirror), and the
     build smoke test returns its error instead of
     raising.
  5. Full suite (make -k test-all): 23 of 24 targets
     pass; the only failure is test-rtl, which fails
     because iverilog is absent on this VM
     (pre-existing environment failure, unchanged by
     this integration). Four pre-existing suites had
     their known-backend enumerations extended with
     "v512dual", and the v512 suite now pins
     requested="v512" where it gates the single-batch
     backend itself.
  6. Fresh regtest blocks through the production
     ComputeEngine with v512dual selected and
     accepted by Core: height 830, hash
     6c253d902f73eddd6e93dcf5a4efe077024b2d90ea3bef2e6963b6409263ae94
     (first gate run), and height 877, hash
     0808f4c9214d8fd9a6d6a029064d4057e8939f9a9b73a026a2b3ea0bb5757ce8
     (final gate run).
- Deployment: the miner child was restarted through
  the autopilot (SIGTERM to the miner child only;
  node, endpoint config and the solo cutover marker
  and watcher untouched). Verified from primary
  sources: .local/mainnet-status.txt reports
  "compute backend: v512dual (native impl:
  avx512-dual; AVX-512 DualMask: selected: ...)"; the
  new session rate reads 21.4 to 21.5M H/s against
  9.7 to 10.3M H/s in the previous v512 session's
  status readings (live readings under contention;
  the verified kernel-scope ratio is the EXP-026
  1.718x). Pool-accepted shares: 204 before deployment
  (evidence/mainnet-live.jsonl), first share on the
  new backend at 2026-11-15T06:57:29Z, nonce
  39483368, difficulty 1.267, job dfe8b64, accepted:
  true, bringing the total to 205. Heartbeat fresh,
  autopilot pid 3190, miner pid 30455, restarts 2
  (both from this deployment).
- Status line fix in the same pass:
  mining/mainnet_live.py printed the v512 selection
  reason unconditionally, which read "AVX-512 MB:
  None" under v512dual; it now prints the selected
  backend's own reason and logs both reasons in the
  backend_selected event. The gpu/engine.py docstring
  also corrects the stale audit note B6-A4 (the C
  SHA-NI engine does not serve the live Stratum path;
  the live path searches through ComputeEngine).
- Rollback: not needed. The fallback chain makes
  rollback a dispatch revert (remove or rename
  libbal_v512dual.so, or pin requested="v512", and
  restart the miner child through the autopilot);
  v512 and C are preserved untouched.
- Files changed: mining/cpu/bal_avx512_dual.c (new),
  mining/cpu/build.py, gpu/engine.py,
  mining/mainnet_live.py,
  tests/test_avx512_dual_integration.py (new),
  tests/test_avx512_integration.py,
  tests/test_gpu_compute.py, tests/test_gpu_correction.py,
  tests/test_deepening.py, tests/test_cpu_aspect.py,
  Makefile, and this log. PERFORMANCE_GAP_MODEL.md
  and PHASE6B_FINAL_REPORT.md were not edited
  (Assignment H owns both).
- Post-integration audit: COMPLETE, verdict PASS
  WITH NOTES (no defects; notes N-1 to N-3, cosmetic
  and observational): research/sha256d/phase6b/
  DUALMASK_POST_INTEGRATION_AUDIT.md.
