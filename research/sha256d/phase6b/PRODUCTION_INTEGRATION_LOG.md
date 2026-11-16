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

## Entry 2: EXP-025 repaired template cache integrated into mining/engine.py (2026-11-14)

- Experiment and decision record: EXP-025
  (research/sha256d/phase6b/EXP025_CACHE_CORRECTNESS.md),
  verdict ACCEPTED as a correctness repair. EXP-025
  demonstrated the EXP-023 prototype cache unsafe as
  written (5 stale serves, 2 validation bypasses
  against its 8-field fingerprint) and proved the
  repaired layered identity complete against the full
  dependency matrix (19 adversarial cases, 1,320
  byte-identical differentials, regtest block 826
  through the research path). Performance record,
  EXP-017 protocol: steps500 pooled 23.02x VERIFIED
  as a candidate-construction rate (never a hash
  rate); family500 pooled 1.083x NOT VERIFIED (a full
  identity recomputation costs about 79 percent of an
  uncached build at 500 transactions).
- Owner decision: explicit, 2026-11-14 23:40 PST,
  option A ("integrate the EXP-025 repaired cache"),
  chosen from the two open Phase 6B decisions.
- Design: the repaired design is ported into
  production mining/engine.py itself (no new module,
  so the cache's use of build_coinbase and the
  engine's use of the cache cannot form an import
  cycle). Layered dsha256 keys exactly as repaired:
  family_key (payout address, scriptPubKey, chain,
  halving interval), tx_key (count, then per
  transaction in order txid, wtxid, fee, plus the
  default_witness_commitment string as a validation
  input), coinbase_key (family_key, height,
  coinbasevalue, flags, witness commitment with an
  explicit none marker), header_key (version,
  previousblockhash, bits, target); identity is
  dsha256 of the three subkeys. Key domain tags are
  production strings (bal/template-cache/v1 family);
  the construction is otherwise the research design
  unchanged. mintime, curtime and the extranonce are
  per-build inputs, never cached.
- Serving rule: MiningEngine.build_candidate (cache
  enabled, the default) routes through the
  identity-keyed TemplateCache; every serve recomputes
  the template's identity from scratch with the
  uncached path's own validations (txid
  re-verification, witness commitment cross-check,
  coinbasevalue equals subsidy plus fees) and raises
  TemplateError on any mismatch or invalid input. A
  stale serve or validation bypass is impossible by
  construction, up to SHA-256 collision resistance.
  MiningEngine.mine_cycle uses the steps shape: it
  prepares the fetched template once (identity
  verified at prepare time) and steps extranonces off
  the prepared entry; the loop holds the template
  object itself and never hands it out between steps.
  If a caller or subclass overrides build_candidate,
  mine_cycle calls the override per round exactly as
  before this integration. The TemplateCache is
  bounded at 128 entries (oldest evicted), a
  production hygiene addition that does not change
  identity semantics.
- Fallback preserved: the original construction is
  kept unchanged as build_candidate_uncached, and
  MiningEngine(use_template_cache=False) routes every
  build to it, mirroring how the v512 integration
  preserved the C backend.
- Call sites and live impact: MiningEngine consumers
  are the GBT loop in mine_cycle, agent/autonomous.py
  and mining/cpu/miner.py (regtest and research
  paths), the solo tooling does not construct through
  MiningEngine (mining/solo_server.py builds Stratum
  jobs from templates itself), and the live pool
  miner mining/mainnet_live.py does not import
  mining/engine.py at all (it is Stratum plus
  ComputeEngine only, verified from its imports and
  from .local/mainnet-status.txt). No production
  consumer that is currently running loads this code,
  so the live miner was NOT restarted. Evidence at
  integration close: heartbeat fresh, autopilot pid
  3190, miner pid 30455 unchanged, restarts still 2,
  shares 211 and rising on public-pool.io. The node,
  the autopilot, the solo cutover endpoint config,
  marker and watcher cron were not touched.
- Gates, all through the production path, all before
  the deployment decision (tests/test_template_cache.py,
  wired into the suite as make test-template-cache
  and into test-all):
  1. Adversarial invalidation (G-A): 19 of 19 cases
     pass, including the EXP-025 defect cases D1 to
     D7 (middle tx replaced, witness-only change with
     txid fixed, reorder, flags change, target change,
     fee raised with value fixed, wrong witness
     commitment). Each valid mutation is refused as a
     sibling serve, prepares a new identity entry, and
     is byte-identical to the uncached path; each
     invalid mutation raises TemplateError on both
     paths with no new prepare; the curtime-only case
     is served under the same identity, byte-identical.
  2. Randomised differentials (G-C): 1,320 (template,
     extranonce) cases over 11 configurations (0, 1,
     2, 3, 10, 100 and 500 transactions, segwit
     fractions 0, 0.5 and 1.0, flags, witness
     commitments), byte-identical to the uncached
     production path on header, body and every scalar
     field; 11 cache prepares (one per configuration).
  3. Validation parity (G-D): 6 invalid shapes (wrong
     txid field, missing data, missing txid,
     coinbasevalue mismatch, fee raised with value
     fixed, wrong witness commitment) each raise
     TemplateError on the uncached path, the cached
     first serve, the cached sibling serve and the
     cached prepare.
  4. Positive controls (G-B): identical inputs reuse
     the cache (prepares 1, hits 1) with byte-identical
     output; a reused entry stays byte-identical
     across boundary extranonces (0, 1, 2, 3, 2^32-1)
     and 20 random extranonces; the steps shape
     prepares once for 64 extranonce steps, all
     byte-identical; the uncached fallback is
     byte-identical with zero cache activity.
  5. Fresh regtest block through the production
     MiningEngine with the cache active (mine_cycle
     steps fast path), accepted by Core as best
     block: height 912, hash
     6138ae771cf95279e72bd0a16322b75c8500f66a64879c08ff8da004f9711900
     (dedicated gate run; cache prepares 1,
     identity_checks 1). Suite re-runs mined further
     blocks through the same path (height 978 in the
     final suite run).
  6. Full suite (make -k test-all, now 25 targets
     with the new one): final run 24 of 25 targets
     pass; the only failure is test-rtl, which fails
     because iverilog is absent on this VM
     (pre-existing environment failure, unchanged).
     The first suite run also failed test-task0039 on
     a thread-timing assertion inside
     ComputeEngine.search_first_counted (attempted
     40185 against a bound of 10000, under full-suite
     plus live-miner contention). Correction per the
     post-integration audit N-1: test-task0039 does
     import MiningEngine for its regtest section; the
     flaked assertion itself lives in gpu/engine.py
     accounting (ComputeEngine.search_first_counted),
     untouched by this integration. It passed
     standalone immediately after (including its own
     regtest block through the integrated engine),
     and it passed in the final suite run. Recorded
     here as a contention flake, not hidden.
- Scope honesty: the verified gain is the steps
  shape only (EXP-025: pooled 23.02x
  candidate-construction rate, not a hash rate, and
  no system rate changes by this integration). The
  family shape is NOT verified and no gain is claimed
  for per-call build_candidate serves, which pay the
  full identity recomputation per call by design. No
  new benchmark was run for this integration; none
  was required, and none is claimed.
- Files changed: mining/engine.py,
  tests/test_template_cache.py (new), Makefile, and
  this log.
- Post-integration audit: NOT performed by the
  integration author; an independent audit is the
  required next step before anything else moves
  (owner rule, 2026-11-14).
- Post-integration audit: COMPLETE, verdict PASS
  WITH NOTES (zero defects; notes N-1 to N-6,
  documentation precision and inherited design
  boundaries): research/sha256d/phase6b/
  CACHE_POST_INTEGRATION_AUDIT.md.

## Entry 3: EXP-022 flags batch adopted for the engine batch consumers (2026-11-15)

- Experiment and decision record: EXP-022 (Y-084;
  Phase 6 EXPERIMENT_RESULTS.md and benchmarks/
  exp022 records; reproduction in
  research/sha256d/phase6b/EXP024_MASK_SEARCH.md),
  verdict VERIFIED IMPROVEMENT
  in batch scope: the flags-only AVX-512 multi-buffer
  batch entry bal_v_batchf2 (vector lexicographic
  target compare in opmask registers, digests
  extracted only for flagged lanes) measured pooled
  1.82x against the production batch at density about
  0 under the EXP-017 protocol (1.59x at 2^-8, 1.33x
  at density 1, 1.83x at 1 thread), with 154,316
  nonces byte-exact against hashlib and candidate
  sets identical to production at densities 0, 2^-16,
  2^-8 and 1. EXP-024 reproduced the batch comparison
  at pooled 1.649x [1.466, 1.860], every session
  significant.
- Owner decision: explicit, 2026-11-15, option B
  ("adopt the EXP-022 flags output shape for the
  engine's batch consumers"), the last open Phase 6B
  item, ordered after option A closed.
- Consumer trace (established from source before any
  change): the production batch surface is
  ComputeEngine.batch_search in gpu/engine.py. For
  the native backends it calls the selected backend's
  flagged batch wrapper with want_all=False: it
  consumes only the flagged (nonce, digest) pairs,
  CPU-verifies each one, and fails closed to a
  trusted rescan on any bad pair. Its direct callers
  are gpu/benchmark.py (benchmark_report) and the
  test suites. The dashboard and the agent reach
  batch_search only through ComputeEngine.benchmark(),
  which calls it to produce a benchmark figure;
  neither mines through it: production mining reaches
  the kernels through search_first_counted and
  search_first (mining/engine.py), not batch_search.
  (Correction, 2026-11-15: the original sentence
  listed the dashboard and agent engines as callers
  without this distinction and read broader than the
  current call graph; the entry's scope claim, batch
  consumers only, was and remains exact.) For the AVX-512 backends those pairs
  previously came from a digest-materialising kernel:
  bal_v_batch2 (v512) or bal_vd_batch2 (v512dual)
  write all 32 digest bytes per hash plus a flag byte
  per hash, and Python walks the flag bytes. That is
  the consumer the flags entry now serves. Callers
  that genuinely need full digests for non-candidate
  lanes stay on the materialising batch, identified
  honestly: the backend selection self-tests
  (_try_v512, _try_v512dual verify every digest of a
  256-nonce batch against hashlib), the want_all
  batch wrappers (_v_batch, _vd_batch, _c_batch and
  their test and diagnostic callers, including
  mining/cpu/miner.py's _c_batch use), and the build
  smoke tests. The C backend batch is not an AVX-512
  path and already returns a flags array; untouched.
  The CUDA batch paths are untouched. The search
  entry points (bal_v_search2, bal_vd_search2,
  bal_c_search2) and the search dispatch order are
  untouched, as is the template cache in
  mining/engine.py (Entry 2).
- Design: new production translation unit
  mining/cpu/bal_avx512_flags.c, built by
  mining/cpu/build.py (build_v512flags) into
  .local/cpu/libbal_v512flags.so as its own library,
  following the v512dual pattern exactly: kernel TU
  compiled separately with the restricted flags
  -O3 -mavx512f -mavx512bw (never -march=native),
  flag-free probe TU (bal_avx512_probe.c) linked in,
  build failure loud and separate, never failing the
  production C build. Provenance against the research
  original (research/sha256d/extreme_optimization/
  src/avx512_mb_flags.c) is recorded in the file
  header: the export name bal_v_batchf2 is carried
  over unchanged; the research file's bal_v_batch2
  and bal_v_search2 sections and the v_group and
  v_meets helpers are not copied (they stay in
  bal_avx512_mb.c, untouched, as the preserved
  fallback); every retained section is byte-identical
  to the research original (verified by diff at
  integration time). Selection in gpu/engine.py
  (_try_v512flags) is independent of search backend
  selection and follows the same discipline: probe
  first (AVX-512F + AVX-512BW), hasattr completeness
  check on bal_v_batchf2 BEFORE any argtypes
  assignment (audit D-1 rule), then a hashlib
  self-test in extract and pure modes with exact
  accounting. Routing: batch_search sends an AVX-512
  backend's enumeration through the flags entry when
  selected; any flags failure falls through to the
  selected backend's preserved materialising batch
  for that call. The pins requested="c" and
  requested="cpu" select no flags path. Batch stats
  record which path served under "batch_path"
  ("flags" or "materialised"); all other stats are
  unchanged, and the flags counted accounting matches
  bal_v_batch2 exactly, so backend_hashes is the same
  figure whichever path serves.
- Gates, all through the production path
  (tests/test_avx512_flags_integration.py):
  1. Differentials: 491,520 batch differentials in
     total. At density 1 (20 trials of 8,192 nonces,
     163,840 digests) the flags path's extracted
     digests are byte-identical to hashlib AND to the
     preserved production batch's full digest array;
     at about 2^-8 (65,536 nonces) and about 2^-16
     (262,144 nonces) the candidate sets and flagged
     digests agree three ways (flags, preserved,
     hashlib recount).
  2. Candidate-set equivalence through batch_search
     at densities 0 (target 1), about 2^-16, about
     2^-8 and 1: sets equal to the hashlib recount,
     batch_path "flags", unique_coverage == count,
     candidate_count and verification_hashes equal to
     the recount size, device_hashes 0.
  3. Boundaries: sizes 15/16/17/31/32/33/63/64/65 at
     starts 0, 12345 and NONCE_SPACE - count (spans
     ending exactly at 2^32), digests byte-exact at
     density 1 and candidate sets exact at about
     2^-8; target equality meets and target minus
     one misses through batch_search.
  4. Accounting parity: on identical inputs (miss
     and hit cases, counts 12345 to 100000) the
     flags ABI's (attempted, backend) equals the
     v512 batch ABI's and the v512dual batch ABI's
     exactly, and equals an independent simulation
     of the shared contract (attempted == count,
     backend == sum over bal_partition spans of
     ceil(span/16)*16).
  5. Forced fallback: probe-failure library,
     symbol-incomplete library (rejected with
     bal_v_batchf2 named; the build smoke test
     returns its designed error, D-1 mirror),
     corrupted-source build failure in a scratch
     tree (no library produced), absent library, and
     a runtime flags failure after selection each
     leave batch_search on the preserved materialised
     batch with exact candidate sets.
  6. Regtest: fresh block mined through the
     production ComputeEngine (auto engine, v512dual
     search) and accepted by Core as best block:
     height 985, hash
     5434bf9ffb565e163973295bf96c56cb2699c49ff31e37f539194d256b5fb3ae
     (dedicated gate run). The accepted block's
     header was then re-enumerated through the
     flags-routed batch_search, which returned the
     block nonce among its verified candidates.
     Suite re-runs mined further blocks through the
     same path (height 1019 in the full-suite run).
  7. Full suite (make -k test-all, now 26 targets
     with the new test-avx512flags): 25 of 26 targets
     pass; the only failure is test-rtl, which fails
     because iverilog is absent on this VM
     (pre-existing environment failure, unchanged).
     No contention flake occurred in this run; every
     other target passed on the first run, including
     test-task0039 and the Entry 2 template cache
     suite.
  8. Objdump census of the built
     libbal_v512flags.so: zero unambiguous AVX-512DQ,
     VBMI or IFMA mnemonics (no vpmullq, no
     vpermi2/vpermt2 families, no vpmultishiftqb, no
     vpmadd52 forms, no vcvt*qq forms).
- Benchmark confirmation (EXP-017 protocol, batch
  scope): production flags batch vs production
  batch, density about 0 (target 0), 2 threads,
  65,536-hash paired blocks, randomised AB/BA order,
  3 sessions of 120 pairs, run one at a time on this
  host (AMD EPYC 9D25 guest, live miner running).
  Pooled adjusted ratio 1.441x [1.261, 1.645],
  significant in every session (1.436x [1.176,
  1.777]; 1.450x [1.148, 1.831]; 1.462x [1.147,
  1.858]) and pooled; pairs won 67.8 percent.
  Records: research/sha256d/phase6b/benchmarks/
  exp022f/ (sessions and analysis_20261115T085306Z).
  The confirmation figure is below the EXP-022
  research figure (1.82x) and the EXP-024
  reproduction (1.649x): those were measured with
  the research libraries on a less contended host.
  The production confirmation is reported as
  measured; it confirms the direction and the
  significance of the batch-scope improvement for
  the integrated build, and no larger figure is
  claimed for it.
- Scope honesty: this is a BATCH-scope improvement
  only. The live miner's search path (v512dual,
  EXP-026) never paid the batch epilogue and is not
  changed by this work; no search rate and no
  mainnet number changes. Every ratio in this entry
  is a batch ratio. The live miner was not restarted
  (heartbeat at close 2026-11-15T09:03:13Z: autopilot
  pid 3136, miner pid 3140, uptime continuous,
  restarts 0, 222 shares accepted, exactly as at the
  pre-work baseline read).
- Files changed: mining/cpu/bal_avx512_flags.c
  (new), mining/cpu/build.py (additive:
  build_v512flags, _smoke_v512flags, VFLIB),
  gpu/engine.py (flags selection, routing,
  batch_path stat, describe fields, docstring note),
  tests/test_avx512_flags_integration.py (new),
  Makefile (test-avx512flags target, test-all now 26
  targets), research/sha256d/phase6b/benchmarks/
  exp022f_paired_bench.py and exp022f_analyze.py and
  exp022f/ session and analysis records (new), and
  this log.
- Post-integration audit: NOT performed by the
  integration author; an independent audit is the
  required next step before anything else moves
  (owner rule, 2026-11-14).
- Independent post-integration audit (2026-11-15):
  PASS WITH NOTES, zero defects; see
  research/sha256d/phase6b/FLAGS_POST_INTEGRATION_AUDIT.md
  (auditor's own 246,768 differentials, five forced
  fallbacks, regtest block 1025, one-session
  benchmark spot-check consistent with the pooled
  figure).

## Entry 4: Stage 0 discrepancy D9 fixed: the live miner's backend line names the selected backend's own probe (2026-11-16)

- Nature: cosmetic logging only. No change to backend
  selection, dispatch order, search, accounting or share
  handling; no benchmark is implicated and none was run.
- Defect: mining/mainnet_live.py labelled the backend
  reason "AVX-512 MB" and read desc["v512_reason"] for
  every backend that was not v512dual or v512, so on a
  host selecting shani, avx2 or C, the session backend
  line (printed at startup and written into the status
  file the awareness layer reads) would name the v512
  probe as the reason source. Recorded as discrepancy
  D9 in research/EXTREME_RESEARCH/
  REPOSITORY_RECONCILIATION.md.
- Fix: a new module-level helper,
  mainnet_live.backend_reason(desc), returns the (label,
  reason) pair for the selected backend from the
  per-backend reason fields gpu/engine.py already
  maintains on the describe() dict (v512dual_reason,
  v512_reason, shani_reason, avx2_reason,
  cuda_context_reason). The C tier has no probe-reason
  field of its own; its backend value is set only after
  the library loads and its digests match the Python
  recount in ComputeEngine._try_c, and its line states
  exactly that. main() takes its label and reason from
  the helper. The backend_selected evidence event is
  unchanged: it records the v512 and v512dual probe
  reasons under their own field names, which was
  already accurate.
- Files changed: mining/mainnet_live.py (helper added,
  inline labelling replaced), tests/
  test_mainnet_live_accounting.py (two D9 checks added:
  simulated describe() dicts pinning every backend's
  label and reason, and real describe() dicts from the
  production engine), research/EXTREME_RESEARCH/
  REPOSITORY_RECONCILIATION.md (D9 marked FIXED), and
  this log.
- Tests: the new checks fail on the pre-fix code
  (backend_reason absent; the pre-fix inline logic,
  replayed against a simulated shani describe(), prints
  "AVX-512 MB" with the v512 probe's reason) and pass on
  the fixed code. Post-fix regression on AMD EPYC 9D25:
  36 of 37 make test-all targets pass. The only failure
  is test-rtl, on the missing iverilog binary, a
  pre-existing environment failure on this VM unrelated
  to this change. test-agent-awareness passed with 51
  checks (the node RPC answered during the run; the
  count is 50 when it does not, per D8).
- Live miner: not restarted. The running process keeps
  the pre-fix code in memory, so the fix takes effect
  at its next natural restart. Miner pid 7872 and
  restarts 0 throughout; shares accepted 483 before the
  work and 486 after.
- Post-integration audit: NOT performed by the author
  of this fix; an independent audit is the required
  next step before anything else moves (owner rule,
  2026-11-14).

## Entry 5: Stage 6, item 2: solo vardiff (register R-12) integrated into production, and discrepancy D10 closed (2026-11-16)

- Nature: production integration of the verified
  research prototype in research/vardiff/ (41 of 41
  checks at prototype scope), following the integration
  path its DESIGN.md section 9 specifies, step for step.
  One unrelated optimisation at a time; nothing else in
  the solo path changed behaviour.
- Step 1, the component: VarDiffController now lives in
  mining/solo_server.py, and SoloServer gains a
  vardiff=None parameter. With vardiff=None the server
  is the pre-integration server: submit_share dispatches
  to the pre-integration body verbatim, the handler and
  broadcast paths keep their original shapes, and the
  only visible difference is one added stats key. Passing
  both an explicit share_difficulty and a controller is
  refused. The controller's semantics are the
  prototype's, unchanged: per-connection difficulty keyed
  by extranonce1, 15 s target interval, EMA alpha 0.35,
  deadband [target/1.25, target x 1.25], increases gated
  by 2 confirmations plus a 30 s grace and capped at
  1.5x, decreases capped at 2x, floor 0.002, ceiling 1.0,
  idle decay on job changes after 60 s idle, full
  adjustment logging.
- Step 2, the server state: per-connection state,
  per-job difficulty snapshots, the bounded 8-job
  history, stale and duplicate accounting and the
  adjustment log moved into SoloServer alongside the
  workers table. SoloTCPServer takes a handler_class
  parameter, and the prototype handler's deltas landed
  in the production handler: connection registration,
  per-connection set_difficulty on subscribe, a pending
  set_difficulty notice after a submit response when an
  adjustment is due, and a per-client set_difficulty
  ahead of the job notify on broadcast (the last two
  only when vardiff is active). Stale shares are
  classified via the history and never accepted as
  shares; duplicates are their own category; a stale
  share that meets the network target still goes through
  the block pipeline.
- Step 3, D10 closed: the SoloServer constructor default
  share_difficulty=0.01 is removed. With neither an
  explicit difficulty nor a controller, the difficulty
  resolves from mining/endpoint_config.py
  (SOLO_SHARE_DIFFICULTY = 0.02), which is now the single
  source. A repo-wide grep reconciles every remaining
  mention of either value: production readers
  (scripts/solo_cutover.py, mining/mainnet_live.py) read
  the endpoint config; tests pass 0.01 explicitly as a
  chosen test difficulty; the remaining mentions are
  historical narrative in docs and the D10 record itself.
  The D10 entry in research/EXTREME_RESEARCH/
  REPOSITORY_RECONCILIATION.md is marked FIXED.
- Step 4, configuration: mining/endpoint_config.py
  carries the vardiff parameters (target interval, EMA
  alpha, deadband, up hysteresis and confirmations, up
  and down caps, decay) alongside SOLO_SHARE_DIFFICULTY,
  which is the controller's initial value, with a
  solo_vardiff_config() merge helper. The config default
  is vardiff DISABLED: the armed solo cutover keeps
  today's fixed-difficulty behaviour until an operator
  enables vardiff after the independent audit below.
  mining/solo_mainnet.py builds the controller from the
  config when enabled and constructs the server exactly
  as before when not. Rollback at every point:
  vardiff=None in code, or the config switch off.
- Step 5, gates, all run 2026-11-16 on AMD EPYC 9D25
  (hostname htch-runtime), production suite
  tests/test_solo_vardiff.py (make test-solo-vardiff),
  final recorded run 59 of 59 checks passed:
  Gate 2 differential: a pristine copy of the
  pre-integration solo_server.py was taken from remote
  HEAD 3ebbaeb216bc1260cfca22c63b9af60d780a971e through
  the GitHub contents API (27,536 bytes, sha256
  518ef05c5c7d49fdf6408e68494fecde24a1c55b337c59576696f77a2a37ab44,
  byte-identical to the local pre-integration file) and
  is pinned as tests/fixtures/
  solo_server_pre_integration.py. Against a scripted stub
  stream (valid shares, a low-difficulty share, a bad
  extranonce2 size, an unknown job, ntime before mintime,
  ntime too far in the future), the production server
  with vardiff off produces identical jobs, identical
  decisions and identical counters. Gate 3 adversarial:
  oscillation injection (adjustments bounded, difficulty
  in bounds), a rate step followed in both directions,
  a stale flood (25 stale shares, all classified, none
  accepted, sub-kinds recorded), a duplicate flood (one
  acceptance, 24 duplicates, no adjustment). EXP-036
  separation, shown at unit and server level: the
  verify_candidate network verdict is identical across
  share targets, and two connections holding different
  snapshot difficulties on the same job split their
  classifications exactly as their snapshots dictate,
  with no submission reaching the node below the network
  target; vardiff difficulty is a share-acceptance
  criterion only and candidate judging is untouched.
  Gate 5: server start, refresh and recovery with
  vardiff live, including the JobRefresher broadcasting
  a new-tip job that the client then mines. Gate 6:
  regtest blocks accepted by Core through the production
  path in both modes, each confirmed on the best chain
  under the EXP-036 rule; the recorded run mined blocks
  1658 to 1679 (22 blocks), the first of them, height
  1658, hash
  000000227d0e82d1d8e8270b7979cdc7c037c84bef231d0028651fcf7b439e76,
  through the vardiff-active server, and the pinned
  default mode's block verified by the suite's tip and
  best-hash checks. Gate 4 does not apply (no rate is
  claimed for this change). Gate 1 and the differential
  half of Gate 2 are the suite's stub sections (the
  prototype's 41 checks ported to the production
  classes, plus the exactness and D10 pins).
- Run history, recorded honestly: run 1 scored 57 of 59;
  the two failures were the live convergence direction
  checks (fast client upward, slow client downward).
  A control run of the prototype's own suite the same
  day failed its own two equivalent checks with near
  identical figures (load average about 16 on a guest
  delivering about 2 effective CPUs), while the
  production server behaved identically to the
  prototype; the two instances were therefore
  recalibrated to decisive settings, following the
  prototype's own ceiling-instance precedent (a 60 s
  target for the fast client, a heavier duty cycle for
  the slow client), with the reasoning recorded in the
  suite. Run 2 was lost to a VM replacement after 11 of
  18 live checks had passed, no result claimed from it.
  Run 3 passed 52 checks and then died on a harness bind
  collision (an ephemeral client socket in TIME_WAIT on
  the next scenario's port); the harness now waits out
  the TIME_WAIT, production socket behaviour untouched.
  Run 4 is the recorded 59 of 59.
- EXP-038: unaffected, verified two ways. By code read:
  the solo Stratum path never imports or calls
  mining/work_checkpoint.py, and vardiff assigns no
  nonce ranges and advances no frontier (the DESIGN.md
  section 6 boundary). By suite: test-exp038 passes in
  the regression below.
- Regression: 36 of 38 make test-all targets pass. The
  two failures are neither caused by nor related to this
  change. test-rtl fails on the missing iverilog binary,
  the known pre-existing environment failure. test-
  autopilot fails on its environment precondition: the
  suite is designed to skip when a live autopilot owns
  the checkout, but its skip check reads a pid from
  .local/autopilot.lock, which the autopilot flocks but
  leaves empty, so the skip cannot fire while the live
  stack is up; the suite then reads the live heartbeat
  and its restart assertion cannot hold. The autopilot
  and its test share no code path with this change, and
  the live autopilot has run the new endpoint_config
  code without disturbance throughout. Agent suites in
  the same regression: intelligence 86, awareness 50
  (the node RPC did not answer during that run; 51 when
  it does, per D8), operations 10,309, security 112
  checks, all passing.
- Live miner: not restarted or signalled by this work.
  Shares accepted 487 and rejected 8 before, 517 and 8
  after. One VM replacement during the work cycle
  replaced the miner process under the environment's own
  supervision (autopilot restarts 0 in its own
  accounting); the fix and the integration take effect
  for the solo leg only when the armed cutover fires.
- Files changed: mining/solo_server.py,
  mining/endpoint_config.py, mining/solo_mainnet.py,
  tests/test_solo_vardiff.py (new),
  tests/fixtures/solo_server_pre_integration.py (new),
  Makefile (test-solo-vardiff added; test-all is now 38
  targets), research/EXTREME_RESEARCH/
  REPOSITORY_RECONCILIATION.md (D10 marked FIXED),
  research/vardiff/PORTFOLIO_SUMMARY.md (dated appendix),
  both experiment registries (R-12 marked INTEGRATED),
  and this log. The solo cutover files, the endpoint
  config on disk, and scripts/solo_cutover.py were not
  touched; cutover semantics are identical.
- Post-integration audit: NOT performed by the author
  of this integration; an independent audit is the
  required next step (owner rule, 2026-11-14), and the
  DESIGN step 5 gate: vardiff stays disabled in the
  endpoint config until that audit has passed and an
  operator enables it.
