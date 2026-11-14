# Task 003.8: Final CUDA ABI Hardening, Validation and Mining Accounting

Date: 2026-11-14. Repo: kilomene/Bitcoin-Autonomous-Lab (Phoenix
build, Bitcoin Core 28.1). Chain scope: regtest only for
integration; no mainnet work was done and the live mainnet
autopilot, miner and node services were never stopped or altered.

Method: every item was re-inspected in the current source, the
defects that could be reproduced on this machine were reproduced
before fixing, and each correction is proven by tests in the new
suite tests/test_task0038_abi.py (wired into the Makefile as
target test-task0038, the 19th target).

Environment facts, rechecked live: no NVIDIA GPU exists on this
VM (zero /dev/nvidia nodes; the built library's device count
returns CUDA error 35). The CUDA toolkit was absent from the
system paths after a VM replacement; nvcc 12.9.86 was restored
at $0 by downloading NVIDIA's official Ubuntu 24.04 packages and
extracting them repo-locally (the system package manager is
blocked by an unrelated pre-existing broken package, which was
not touched), at .local/cuda129, selected through the existing
BAL_NVCC mechanism. With it, the updated gpu/cuda/engine.cu
compiles cleanly and the hardened ABI was tested against the
freshly built library itself. GPU device execution, GPU
performance and GPU regtest acceptance remain UNVERIFIED.

## Reproductions before any fix

- bal_cuda_ctx_create pointer defect, reproduced against the
  pre-fix built library: calling with an invalid max_count
  (2^25) returned -5 but left the caller's output pointer at its
  sentinel value 0x1234, because the old code validated the size
  caps before ever writing *out_ctx. A failed creation could
  therefore leave an uninitialized or stale pointer behind.
- bal_cuda_batch argument defects, confirmed by source
  inspection and by the pre-fix ABI's behavior: the entry point
  checked only count and threads, then passed header, target_le,
  hashes and flags straight into cudaMemcpy. No null check, no
  maximum batch, and the count * 32 allocation size was an
  unchecked size_t multiplication (a count of 0xFFFFFFFF would
  request a 128 GiB digest buffer and rely on the allocator to
  refuse).
- CudaContext.search_complete performed no validation of its
  own: it called set_work (which calls target.to_bytes, raising
  an incidental OverflowError for an oversized int, and accepting
  anything else) and relied on ComputeEngine.batch_search and
  the C ABI to catch bad input.
- Accounting gap, measured pre-fix on the Task 003 forced
  overflow scenario (below): the stats had no candidate_count
  and no overflow_splits field, and no split of time between
  initial work and overflow recovery.
- Batch verification gap, confirmed in source: in
  ComputeEngine.batch_search, a C or CUDA batch candidate that
  failed CPU verification was counted and recorded, but the
  remaining pairs were still trusted and returned; the range was
  NOT independently re-covered. The generic digest-enumeration
  path silently dropped a target-meeting digest that failed
  verification.

## Corrections

### 1. Legacy CUDA ABI hardening (gpu/cuda/engine.cu, gpu/cuda/kernels/sha256.h)

- New shared validator bal_cuda_batch_validate in
  kernels/sha256.h, called by bal_cuda_batch before any pointer
  is dereferenced or copied and before any CUDA memory
  operation. It rejects, with documented codes: null header,
  target_le, hashes or flags (-1); zero count or thread count
  outside [1, 1024] (-1); a nonce range failing the Task 003.7
  subtraction-based bal_nonce_range_valid (-4); a count over
  the documented maximum (-6); and allocation-size overflow
  (-5, via bal_checked_mul_size, a division-guarded checked
  multiplication also added to the shared header).
- Documented maximum legacy batch: BAL_CUDA_LEGACY_MAX_BATCH =
  2^24 nonces. The legacy path materializes every digest, so
  this bounds its digest output at 512 MiB and flags at 16 MiB;
  larger searches belong on the persistent context or in
  caller-sized chunks. The constant and the full error-code
  table (0, -1, -2, -3, -4, -5, -6; positive values are CUDA
  runtime codes) are documented in kernels/sha256.h, in the
  engine.cu header comment, and in docs/CUDA.md.
- Allocation sizes in bal_cuda_batch now come from the
  validator's checked computation (hash_bytes, flag_bytes) and
  are used for both allocation and the copies back.
- Cleanup: every post-validation exit path passes through one
  cleanup block that attempts every free; if the batch itself
  succeeded but a free fails, the free error is now reported
  instead of hidden (previously all four frees were ignored).
- Same-class audit of the persistent-context ABI:
  bal_cuda_ctx_search now validates the candidate output
  buffers (cand_nonces, cand_digests) BEFORE any CUDA
  operation, not after the kernel when stored records exist;
  bal_cuda_ctx_batch_diag now validates header and target_le
  explicitly; bal_cuda_ctx_create computes all count-derived
  allocation sizes with checked multiplication (see item 2).

### 2. bal_cuda_ctx_create output-pointer behavior (gpu/cuda/engine.cu)

- out_ctx is validated first and *out_ctx is set to nullptr
  IMMEDIATELY, before the argument and size-cap checks, so
  every failure path (invalid argument -1, size limit -5, host
  allocation -2, any CUDA error) leaves the caller's pointer
  null. Partial state on CUDA failure is destroyed through the
  existing bal_cuda_ctx_destroy path, and success writes the
  pointer exactly once at the end.
- Proven against the freshly compiled library: sentinel
  pointer 0x1234 becomes null for max_count 2^25 (-5), for
  cand_cap 2^23 (-5), and for max_count 0 (-1); valid arguments
  on this GPU-less VM return the CUDA runtime error 35 with
  the pointer still null; a null out_ctx returns -1.

### 3. Public Python API validation (gpu/engine.py)

- New module-level validators used at the CudaContext
  boundary: validate_header (bytes-like, exactly 80 bytes),
  validate_target (int in [0, 2^256), or exactly 32 raw
  little-endian bytes as bytes, bytearray or memoryview; bools,
  floats, strings, wrong lengths, negative and oversized ints
  rejected), validate_nonce_range (plain ints, count at least
  1, subtraction-based rule start at most 2^32 - count), and
  validate_threads (plain int within [1, 1024]).
- CudaContext.search_complete validates header, target, start,
  count and threads BEFORE set_work or any other backend call.
  search, batch_diag and set_work validate the same way;
  search additionally rejects count over the context max_count
  ( directing the caller to search_complete, which now passes
  max_chunk=self._max_count to the recovery driver so each
  single-shot stays inside the device buffers). The constructor
  validates max_count (plain int within [1, 2^24]) before any
  library call. Every error is a TypeError or ValueError
  naming the offending parameter.
- Proven with counting stubs: 29 invalid inputs plus a
  crossing range are each rejected with ZERO backend calls;
  valid boundaries (start 0, the final nonce alone, the whole
  nonce space ending exactly at 2^32, targets as raw bytes and
  bytearray) are accepted.

### 4. Attempt accounting (gpu/engine.py, gpu/benchmark.py)

- collect_candidates_complete now threads one accounting
  structure with exactly the five fields: unique_coverage,
  device_hashes, researched_hashes, overflow_splits and
  candidate_count (overflow_events is retained as an alias of
  overflow_splits for older callers). The invariant
  device_hashes == unique_coverage + researched_hashes holds
  on every completed call and is asserted in tests. Split
  depth is capped at MAX_OVERFLOW_SPLIT_DEPTH = 32 (enough to
  halve any 32-bit range to single nonces); a backend that
  overflows at a single nonce or at the cap raises an explicit
  CandidateOverflowError. The driver also validates its own
  arguments, validates every returned candidate (nonce inside
  the searched sub-range, 32-byte digest), caps single-shot
  sizes via the new optional max_chunk, and records
  initial_search_seconds, recovery_search_seconds,
  search_seconds and kernel_ms_total.
- CudaContext.search reports the same five fields for a
  single shot, and now also refuses a reported candidate
  count over capacity even if the overflow flag is missing,
  and rejects a candidate nonce outside the searched range.
- ComputeEngine.batch_search stats now carry the same fields
  on every path, plus backend_hashes (actual computations
  across backend and recovery), coverage_per_second,
  verification_rescan_hashes and a coverage_status string.
  On the CUDA path, hashes and hashrate are device_hashes
  based (actual GPU computations per elapsed second), never
  unique coverage; unique coverage is reported separately.
  On CPU paths device_hashes is 0 and backend_hashes carries
  the actual count.
- CPU naming mapping (documented, no renames, so Task 001
  callers are untouched): last_search_stats.attempted is the
  actual backend hash computations (the device_hashes
  analogue), requested is the range size, and
  rescan_attempted is the verification-recovery repeat count
  (the researched analogue for the CPU early-exit path).
  unique_coverage is only claimed for completed full-range
  operations (batch_search, search_complete).
- gpu/benchmark.py reports backend_hashes, device_hashes,
  unique_coverage, coverage_per_second (with a median across
  runs), researched_hashes, overflow_splits and
  candidate_count per run, and states both rate definitions
  in its output.

### 5. Fail-closed batch verification (gpu/engine.py)

- New _check_pairs gate for batch enumeration: every backend
  pair must be inside the searched range, unique, and pass
  CPU verification. Any failure poisons the whole enumeration.
- New _rescan_all_candidates: on a poisoned C or CUDA batch,
  the backend's pairs are discarded and the WHOLE range is
  independently re-covered with the trusted Python hashlib
  implementation; a structured fallback event records the
  failure count and the rescan attempts, and the stats mark
  rescanned, rescan_attempted, verification_rescan_hashes and
  coverage_status "complete: trusted CPU rescan after
  verification failure". After a verification failure, batch
  enumeration therefore DOES provide complete independent
  coverage of the range, by the rescan.
- The generic digest-enumeration path now counts
  target-meeting digests that fail verification instead of
  silently dropping them: legacy CUDA digests are recovered
  by the same trusted rescan; a failure inside the CPU
  fallback's own enumeration raises an explicit RuntimeError
  (there is no independent implementation left to rescan
  with, and a false no-hit is never reported).
- The early-exit path (search_first_counted) already failed
  closed since Task 003.4 and is unchanged.

## Before-and-after accounting example

Forced-overflow scenario, identical before and after: GENESIS
header, target 2^255, range [0, 1024), single-shot stub with
effective capacity 3 under a driver sized for capacity 4096,
512 true candidates by independent recount.

Before (Task 003 code, measured this session before the fix):
stats {sub_batches: 222, overflow_events: 220,
researched_hashes: 7840, unique_coverage: 1024,
device_hashes: 8864}. No candidate_count field, no
overflow_splits field, no timing split: a reader could not
see how many candidates were returned for verification, nor
how much time recovery cost.

After (this task, same scenario): stats {sub_batches: 222,
overflow_events: 220, overflow_splits: 220,
researched_hashes: 7840, unique_coverage: 1024,
device_hashes: 8864, candidate_count: 512,
initial_search_seconds: 0.0021, recovery_search_seconds:
0.0656, search_seconds: 0.0677}. The work itself is
unchanged (the correction is accounting and safety, not a
speed change): device_hashes 8864 = unique_coverage 1024 +
researched_hashes 7840; the researched share of actual
computations is 88.5 percent, and recovery took 96.9 percent
of the host-stub search time. Derived rates on the host stub
(Python, NOT GPU measurements): unique coverage 15,121 per
second versus actual computations 130,891 per second, which
is exactly the distinction the old stats could not express.

Batch example (this task's fail-closed test): a corrupt C
enumeration of [0, 2000) at the regtest target reports
unique_coverage 2000, backend_hashes 4000 (2000 backend +
2000 rescan), verification_rescan_hashes 2000,
candidate_count 1 (the one pair the backend presented),
verification_failures 1, and returns the exact recounted
candidate set (1021 candidates) from the rescan. A corrupt CUDA
enumeration of the same range keeps device_hashes at the
GPU's actual 2000 while backend_hashes is 4000, so GPU work
is never inflated by CPU recovery work.

## Performance report (Task 003.8 definitions)

All numbers are from this shared, capped VM (about 1.5 CPUs)
with the live mainnet miner and node running; host numbers are
labelled host measurements and are never GPU performance.

- Unique coverage per second vs actual computations per
  second, fallback C backend through gpu/benchmark.py
  (3 batches of 65,536, target 2^240): median 888,931 per
  second for both (this path has no repeats, so
  backend_hashes equals unique_coverage by construction);
  device_hashes 0 (not a GPU), candidate_count 4 in the first
  run. Label from the harness itself: "NOT a GPU measurement".
- CPU search counted rates (Task 003 perf snapshot, rerun
  this session): 1 thread 1,729,296 H/s, 2 threads 1,741,547
  H/s, 4 threads 1,852,815 H/s (actual counted attempts).
- CPU verification throughput: 4.6 microseconds per candidate
  (about 217,000 verifications per second), measured this
  session.
- Overflow recovery overhead (host stub, forced case above):
  researched share 88.5 percent of actual computations;
  recovery search time 0.0656 s of 0.0677 s total. At
  ordinary targets the target-sized sub-batching keeps
  overflow frequency at zero in the test scenarios.
- CUDA device throughput, GPU coverage rates and GPU
  verification overhead: none exist. UNVERIFIED.

No performance improvement is claimed for any correction in
this task; the benchmark fix removes mislabelled rates rather
than speeding anything up.

## Tests and validation

- New suite tests/test_task0038_abi.py: PASS (all sections).
  It covers host ABI validation 14 of 14; sanitizers;
  compiled-library ABI codes and out_ctx behavior; the
  Python invalid-input table with zero backend calls; valid
  boundary inputs; CudaContext.search validation and
  constructor validation; accounting at exact capacity, one
  over capacity, forced multi-split overflow (220 splits),
  a 65,536 range, smallest ranges, an always-overflowing
  backend raising explicitly, and max_chunk capping;
  fail-closed C, CUDA and CPU-fallback batch verification;
  and a fresh regtest block.
- Task 003 suite (tests/test_task003_corrections.py): PASS,
  including its own fresh regtest block at height 559.
- GPU suites (test_gpu_correction, test_gpu_compute): PASS.
- Full suite: 19 targets, 18 PASS and 1 FAIL. The single
  failure is test-rtl, solely because iverilog is not
  installed on this VM (environment, unrelated, not hidden or
  weakened). One environment incident during the run is
  disclosed in full: the first make test-all stopped at
  test-deepening because the local peer regtest node's
  txindex was inconsistent with its rolled-back chain state
  ("txindex: best block of the index not found" in its
  debug.log, a pre-existing .local data state, not a code
  defect). The peer's stale chain directories were moved
  aside (kept under .local/regtest2/data/stale-backup-0038)
  and the suite was rerun: test-deepening PASS, with the peer
  resyncing the full chain from the primary node. No
  repository code was changed for this. All other targets
  passed in the make test-all run or in immediate individual
  reruns (test, test-regtest, test-engine, test-pow,
  test-gpu, test-gpu-correction, test-mining,
  test-adversarial, test-deepening, test-cpu,
  test-cpu-correction, test-solo, test-research,
  test-autopilot, test-judgement, test-installer,
  test-task003, test-task0038).
- Compilers: g++ -O2 -Wall -Wextra -Werror builds
  host_sha256.cpp and host_checks.cpp cleanly; nvcc 12.9.86
  compiles the updated engine.cu cleanly into
  libbal_cuda.so (cuda_build ok, runtime_error_35, as
  expected with no device).
- Sanitizers: host_checks clean under ASan+UBSan and under
  TSan (setarch -R, as this VM requires). The Task 003
  sanitizer set (CPU libraries, miner, mutex harness) was
  rerun as part of its suite and remains clean. Device
  sanitizer runs remain impossible without a GPU:
  UNVERIFIED.
- Fresh regtest evidence for this task: block height 558,
  hash 00bb5030e64c2450893d7cf083fa7b3cd824277503d2d889db1cdddcb8b7a0c5,
  mined through mining/engine.py with the native CPU backend
  (ComputeEngine backend "c", batch_size 100,000),
  submitblock returned null, and the node's best block equals
  the block hash. Machine-readable evidence:
  evidence/regtest/task0038-cuda-abi.json.

## Files changed

- gpu/cuda/kernels/sha256.h: error-code table,
  BAL_CUDA_LEGACY_MAX_BATCH, bal_checked_mul_size,
  bal_cuda_batch_validate.
- gpu/cuda/engine.cu: legacy batch uses the shared validator
  and checked sizes, cleanup reports free errors, ctx_create
  clears *out_ctx immediately and uses checked sizes,
  ctx_search validates candidate buffers up front,
  ctx_batch_diag validates header and target explicitly.
- gpu/cuda/host_checks.cpp: Task 003.8 ABI validation cases
  (output line "legacy_abi_validate 14 of 14").
- gpu/engine.py: public API validators; CudaContext
  validation (search_complete, search, batch_diag, set_work,
  constructor) and single-shot accounting and range guards;
  collect_candidates_complete five-field accounting, split
  depth cap, timing split, max_chunk, candidate validation;
  batch_search fail-closed rescan recovery and full
  accounting on every path; CPU stats naming mapping
  documented.
- gpu/benchmark.py: Task 003.8 accounting fields and rate
  definitions in the harness output.
- docs/CUDA.md: Task 003.8 section with the maximum batch
  and the C ABI error-code table.
- tests/test_task0038_abi.py: new suite.
- Makefile: test-task0038 target, wired into test-all
  (19 targets).
- results/TASK0038_CUDA_ABI_HARDENING.md: this report.
- evidence/regtest/task0038-cuda-abi.json: machine-readable
  evidence.

No CPU subsystem files were changed. No existing test was
weakened or removed.

## Acceptance checklist

- Legacy CUDA ABI validates inputs and allocation sizes
  safely: PASS (shared validator host-proven 14 of 14 and
  proven against the freshly compiled library: null pointers
  -1, bad threads -1, range crossing -4, over-max and
  overflow-attempt counts -6, all before any CUDA operation).
- CUDA context creation has correct output-pointer behavior:
  PASS (proven against the compiled library: the pointer is
  null after size, argument and runtime failures; the pre-fix
  sentinel reproduction is recorded above).
- Public Python CUDA APIs reject invalid inputs: PASS
  (29 invalid inputs plus a crossing range, each with zero
  backend calls; valid boundaries accepted).
- Overflow recovery preserves complete nonce coverage: PASS
  (exact recounts at multiple scales, no duplicates, split
  depth cap, explicit error from an always-overflowing
  backend; device execution of the same logic UNVERIFIED).
- Repeated computation is accounted for separately from
  unique coverage: PASS (five fields and the invariant on
  every completed search_complete and batch_search path;
  before-and-after example above).
- Reported hashrates use clearly defined actual work: PASS
  (CUDA-path hashrate is device_hashes per second; coverage
  per second reported separately; benchmark harness states
  both definitions).
- Candidate verification failures cannot silently become
  false no-hit results: PASS (batch enumerations are
  discarded and independently re-covered by the trusted
  rescan; the CPU fallback enumeration raises explicitly;
  the early-exit path keeps its Task 003.4 behavior).
- All available regression and safety tests pass: PASS
  (18 of 19 targets; test-rtl fails only on absent iverilog;
  sanitizers clean as listed).
- Unavailable physical GPU tests are explicitly marked
  UNVERIFIED: PASS, they are: GPU device execution
  UNVERIFIED, GPU performance UNVERIFIED, GPU regtest block
  acceptance UNVERIFIED (no NVIDIA GPU exists on this VM).

## Remaining limitations

- No physical NVIDIA GPU: every device-side behavior of the
  hardened ABI (kernel execution under the new validation,
  device sanitizer runs, GPU throughput, a GPU-produced
  regtest candidate) is UNVERIFIED until the repo runs on a
  machine with a supported GPU. The validation logic itself
  is host-proven and library-proven because it runs before
  any CUDA call.
- The CUDA toolkit on this VM is a repo-local extraction
  under .local/cuda129 (not a system install), selected via
  BAL_NVCC; a fresh VM replacement will need it restored
  again (the official packages are in .local/cuda-dl).
- The trusted rescan after a batch verification failure runs
  at Python speed; it is a correctness recovery, not a
  performance path, and it is paid only when a backend lies.
- bal_cuda_ctx_destroy and pthread join results remain
  unchecked, as recorded in Task 003; a destroy failure has
  no safe recovery action in this design.

## Task 003.9 scoping note (2026-11-14, appended, history unchanged)

Two statements in this report were written under the Task
003.8 accounting definitions and are superseded by the Task
003.9 definitions (results/TASK0039_FINAL_ACCOUNTING_CORRECTION.md):

- The invariant device_hashes == unique_coverage +
  researched_hashes is a property of the CUDA candidate
  recovery driver only (where the wrapped backend is the CUDA
  device). It was never a property of CPU or C statistics;
  Task 003.9 scopes it explicitly in the driver docstring and
  the module docstring, and tests assert device_hashes == 0 on
  CPU and C paths.
- backend_hashes in this report included trusted-rescan work
  ("actual computations across backend and recovery", for
  example "backend_hashes 4000 (2000 backend + 2000 rescan)"
  in the batch example). Under Task 003.9, backend_hashes is
  the selected backend's own computations only (2000 in that
  example); the rescan and every candidate verification are
  reported separately as verification_hashes, and the legacy
  "hashes" total is backend_hashes + verification_hashes, each
  computation counted in exactly one category. Two assertions
  in tests/test_task0038_abi.py were updated to the new split
  (with added verification_hashes assertions); no other 003.8
  result changes.
