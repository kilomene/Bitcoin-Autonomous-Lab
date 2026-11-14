# Task 003: CPU and GPU Final Corrections, Edge-Case Hardening and Validation

Date: 2026-11-14. Repo: kilomene/Bitcoin-Autonomous-Lab (Phoenix
build, Bitcoin Core 28.1). Chain scope: regtest only for
integration; no mainnet work was done and the live mainnet
autopilot and node services were never stopped or altered (both
verified active after the work; the pool miner accepted shares
throughout).

Method rule followed throughout: the Task 001 and Task 002
reports were NOT trusted. Every item below was re-inspected in
the current source, reproduced where possible, fixed, and proven
with tests in tests/test_task003_corrections.py (new suite, wired
into the Makefile as target test-task003, the 18th target).

Environment facts, rechecked live: no NVIDIA GPU exists on this
VM (zero /dev/nvidia nodes, CUDA runtime error 35 from the built
library); CUDA toolkit 12.9 (nvcc 12.9.86) is present at
/usr/local/cuda. GPU execution gates therefore stay UNVERIFIED,
exactly as the spec requires; host compilation and host execution
of the identical shared kernel source are the proof available
here and are labelled as such.

## Reproductions before any fix

- 003.2 reproduced live: with batch_size 1,000,000 the mining
  loop's final start is 4,294,000,000 and it submitted count
  1,000,000, a range ending at 4,295,000,000, past 2^32. The real
  backend rejected it ("nonce range out of bounds"), so a full
  nonce-space walk with an awkward batch size crashed at the
  tail instead of completing.
- 003.4 reproduced live: a stub native library returning a
  candidate with a zeroed digest made search_first_counted
  return (None, 6, seconds) with zero fallback events: a corrupt
  native candidate silently became an ordinary miss even though
  the native search had stopped after 6 attempts of a 1,000
  nonce range.
- 003.3 reproduced live: `./bal-miner bench 10 2` reported
  2,600,000 hashes, about 1,300,000 per worker, against starting
  windows only 1,000,000 nonces apart, so roughly 300,000 nonces
  were computed twice by the two workers.
- 003.1, 003.5, 003.6, 003.7 confirmed by direct source
  inspection (quoted in the table): unchecked pthread_mutex_init
  return; overflow raising out of batch_search with the range
  abandoned; CUDA selectable from the legacy batch self-test
  while the persistent context was checked only through the
  diagnostic path and its failure did not deselect CUDA;
  start + count range checks in all three CUDA ABI entry points.

## Per-correction evidence table

### 003.1 Mutex initialization failures (mining/cpu/bal_search.h)

- Original defect: bal_ctx_init() called pthread_mutex_init()
  and ignored its return; bal_ctx_destroy() unconditionally
  destroyed the mutex; bal_ctx_publish() ignored lock and unlock
  results. Callers bal_c_search2 (mining/cpu/bal_batch.c) and
  bal_i_search2 (mining/cpu/bal_sha_intrin.c) started workers
  with no way to know initialization had failed.
- Correction: bal_ctx_init() now returns the pthread error code
  and marks the context initialized (mutex_ready) only on
  success; bal_ctx_destroy() destroys only an initialized mutex;
  bal_ctx_publish() returns -1 on lock/unlock failure, publishes
  nothing in that case, records a publish error, and raises the
  stop flag so the search ends in an explicit error. Both search
  entry points return -4 when context init fails (no worker is
  started) and -3 when winner publication failed. A test hook
  (bal_mutex_fail_mask, exported setters bal_c_test_set_mutex_
  fail_mask / bal_i_test_set_mutex_fail_mask) injects init and
  lock failures; production code never sets it.
- Regression tests: tests/task003_mutex_harness.c (normal
  init/publish/destroy, first publisher wins, failed init
  propagated and not marked initialized, destroy after failed
  init is a safe no-op, lock failure publishes nothing and
  records the error) and ctypes injection against both built
  libraries (-4 on init failure, -3 on lock failure, recovery
  after injection removed). All pass.
- Runtime validation: harness and library tests ran natively;
  the same harness plus a sanitizer driver ran under
  ASan/UBSan and TSan (see Sanitizers). No leaks or invalid
  mutex operations reported.
- Performance impact: none measurable; one checked return per
  init and per publish.
- Remaining limitation: pthread_mutex_destroy and pthread_join
  results remain unchecked, as before; a destroy failure has no
  safe recovery action in this design.

### 003.2 Final nonce-batch boundary (mining/engine.py)

- Original defect: MiningEngine.mine_cycle passed
  self.batch_size directly and advanced start += self.batch_size.
  For batch sizes that do not divide 2^32 the final batch
  exceeded the nonce space (reproduced above).
- Correction: new MiningEngine.batch_count(batch_size, start)
  returns min(batch_size, 2^32 - start) with validation; the
  loop passes that count to the backend and advances by it. The
  final nonce 0xFFFFFFFF is covered exactly once for every
  batch size.
- Regression tests: batch_count unit checks (sizes 1, 65,535,
  1,000,000, larger than the whole space, larger than the
  remaining range, end exactly at 2^32, invalid inputs rejected)
  and full nonce-space coverage walks using a recording stub
  backend: batch sizes 65,535 (65,538 batches), 1,000,000
  (4,295 batches) and 3,000,000,000 (2 batches) each cover
  [0, 2^32) exactly once with no gap, no overlap and no
  out-of-range batch.
- Runtime validation: the real regtest cycle below ran with
  batch_size 100,000 (does not divide 2^32) through the native
  backend.
- Performance impact: none; identical work, clamped tail.
- Remaining limitation: none known.

### 003.3 Benchmark overlap and winner semantics (mining/cpu/bal_miner.c)

- Original defect: bench workers started i * 1,000,000 nonces
  apart but ran unboundedly for the bench duration, hashing
  into the next worker's region (reproduced above) and
  eventually wrapping the 32-bit space silently. The winner
  was described in the file header, at the selection site, and
  in results/TASK001_CPU_CORRECTION.md as "deterministically
  the smallest found nonce", which readers could take as the
  lowest valid nonce in the range; it is not, because workers
  stop early when any worker finds a candidate.
- Correction: bench workers now own disjoint contiguous slices
  partitioning the whole 32-bit space (bench_slice(); equal
  slices, the last worker absorbs the sub-thread remainder) and
  wrap only inside their own slice, with wraps counted. BENCH
  output now states unique_nonce_space=4294967296 and
  repeated=own-slice-only, separating unique coverage from
  repeated computation; hashes= remains actual completed
  attempts per worker, summed. Winner wording corrected in the
  file header and at the selection site, the FOUND line now
  prints winner_semantics=first-found, and a Task 003 addendum
  in results/TASK001_CPU_CORRECTION.md corrects the earlier
  report. A `bal-miner ranges <threads>` diagnostic prints the
  slices for direct verification.
- Regression tests: ranges mode for 1, 2, 3, 4, 7 and 64
  workers proves disjoint, complete, ordered slices; bench
  output field checks; search output checks the genesis nonce
  and winner_semantics=first-found.
- Runtime validation: bench 3 s / 4 threads on the corrected
  build: hashes=1300000 unique_nonce_space=4294967296
  slice_wraps=0. The pre-fix 10 s / 2 thread bench's inflated
  total (2,600,000 with roughly 300,000 duplicates) is the
  before picture; throughput itself is unchanged within
  contention variance.
- Performance impact: none on search; bench now measures
  unique work honestly instead of counting duplicated nonces.
- Remaining limitation: bench slices are static for the run;
  a worker that finishes its slice early wraps and repeats its
  own nonces (counted as repeats) rather than stealing work.
  That is deliberate: bench measures per-worker throughput,
  not a coordinated search.

### 003.4 Invalid native candidate (gpu/engine.py)

- Original defect: in ComputeEngine.search_first_counted, when
  bal_c_search2 (or the legacy bal_c_search) returned a
  candidate that verify_candidate rejected, the code silently
  returned an ordinary no-hit result (reproduced above), even
  though the native search had stopped early and the remainder
  of the range was never searched.
- Correction: a failed verification is treated as a serious
  backend correctness failure. _recover_bad_candidate rescans
  the affected range with the trusted Python hashlib
  implementation, records a structured fallback event (range,
  native attempts, rescan attempts, retried_on
  cpu-hashlib-rescan), returns the rescan result, and the
  stats record rescanned=True, rescan_attempted, and backend
  cpu-rescan when a rescan produced the answer. Attempt
  accounting stays exact: total attempted = native attempted +
  rescan attempted. In batch_search (full-range enumeration,
  where coverage is complete by construction) failed candidates
  are now counted as verification_failures and recorded as
  fallback events instead of being dropped silently.
- Regression tests: stub native libraries injecting a corrupt
  digest and a wrong nonce both trigger the recorded rescan,
  which finds the true first hit of the range with exact
  accounting (attempted = native + rescan); a native hard
  failure (-7) propagates as an error; the genuine native
  candidate passes with rescanned=False and no rescan event.
- Runtime validation: the same tests run against the real C
  library for the genuine-candidate case; the regtest cycle
  below ran through this code path.
- Performance impact: zero on the honest path (verification
  was already performed); the rescan cost is paid only when a
  backend actually lies.
- Remaining limitation: the rescan is Python-speed (about
  100K H/s), so a lying backend on a huge range is slow to
  recover; it is never silently wrong, which is the point.

### 003.5 CUDA candidate overflow recovery (gpu/engine.py, gpu/cuda/engine.cu, gpu/cuda/kernels/sha256.h)

- Original defect: the production candidate capacity is 4,096;
  CudaContext.search raised a plain RuntimeError on overflow
  and ComputeEngine.batch_search re-raised it, abandoning the
  range. An easy regtest target over a 65,536 batch produces
  roughly 32,768 candidates, so this was guaranteed to lose
  searches exactly where regtest operates.
- Correction: adaptive sub-batching plus split-on-overflow
  recovery, implemented once in collect_candidates_complete
  and used by both the device context (CudaContext.
  search_complete) and the tests. Sub-batch size is chosen
  from the target with exact integer arithmetic so expected
  candidates stay at or below capacity/8. If a sub-range still
  overflows, only that sub-range is split in half and resolved
  recursively; the overflowing pass's partial records are
  discarded, its hashes are accounted as researched_hashes
  (never as unique coverage), the completing leaf sub-batches
  partition the original range exactly, and the returned
  candidates are deduplicated by nonce. CudaContext.search now
  raises the typed CandidateOverflowError carrying the true
  total. Early-exit callers are safe: search_first goes through
  batch enumeration or the C search, and batch_search's CUDA
  branch now uses search_complete, so an overflowing range
  yields its full verified candidate set instead of an
  exception.
- Regression tests (through the shared driver with a Python
  stub implementing the device primitive's exact bounded
  semantics): below capacity, exactly at capacity, above
  capacity, all-match target, forced overflow with a smaller
  effective stub capacity (splits happen, researched_hashes
  accounted, device_hashes = unique coverage + researched),
  and the final-nonce boundary range. Every returned set
  equals an independent Python recount exactly, with no
  duplicate nonces.
- Runtime validation: host-level only (no GPU on this VM);
  the device path and the tested path share
  collect_candidates_complete and the candidate primitive in
  kernels/sha256.h is the same source the kernel runs.
- Performance impact: on device, overflow frequency in the
  tests was driven to zero by sizing for ordinary targets and
  occurs only under capacity mismatch or extreme targets;
  split recovery re-searches only the overflowing sub-range.
  Device throughput itself: none exists to measure here.
- Remaining limitation: Gate for device execution stays
  UNVERIFIED until a physical GPU runs search_complete.

### 003.6 Production-path CUDA self-test (gpu/engine.py, gpu/cuda/engine.cu)

- Original defect: _try_cuda selected backend "cuda" from the
  legacy full-digest batch self-test; the persistent context
  was then checked only through the diagnostic batch_diag
  path, and if that failed the engine stayed on CUDA (legacy
  path) with only cuda_ctx_reason recorded. The production
  candidate-filtering path was never exercised before
  selection.
- Correction: cuda_producti
...[truncated 8537 chars]