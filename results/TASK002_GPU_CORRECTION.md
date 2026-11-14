# TASK 002: GPU/CUDA Mining Engine Correction, Optimization and Validation

Date: 2026-11-14. Scope: the GPU subsystem only. The CPU subsystem
(Task 001) was not modified; the only shared file touched is
gpu/engine.py, which hosts both the CUDA dispatch and the CPU
fallback, and the Task 001 counted interfaces
(search_first_counted, last_search_stats) are unchanged.

## Environment facts, verified live on this VM

- No NVIDIA GPU: zero /dev/nvidia nodes, no nvidia-smi, no driver
  library. The CUDA runtime returns error 35
  (cudaErrorInsufficientDriver) on a device count query through the
  built library. No GPU hash has ever been produced on this machine
  and none is claimed anywhere in this report.
- CUDA toolkit: absent at task start (a VM replacement had removed
  /usr/local/cuda and the NVIDIA apt source). Restored during this
  task at $0 from NVIDIA's official Ubuntu 24.04 repository:
  cuda-keyring 1.1, cuda-nvcc-12-9 (nvcc 12.9.86), cuda-cudart-dev-12-9,
  cuda-cccl-12-9, cuda-sanitizer-12-9 (compute-sanitizer). The new
  engine.cu compiles cleanly with it.
- Consequence, per the owner's own gate definitions: Gate 6 is
  UNVERIFIED and Gate 7 is UNVERIFIED. The device side of Gate 4
  cannot be measured here. Everything provable without a device was
  proven; the rest is marked, not papered over.

## Phase 1 audit: execution path and defects found

Path traced: mining request (mining/engine.py, mainnet_live.py)
to ComputeEngine backend selection (gpu/engine.py) to ctypes into
libbal_cuda.so (gpu/cuda/engine.cu) to device allocation, kernel
(kernels/sha256.h), target comparison, result transfer, Python-side
rescan, CPU verification, engine response.

Defects verified against the actual source:

- D1. Per-batch device churn: bal_cuda_batch performed 4 cudaMalloc,
  2 host-to-device copies, a full device synchronize, a device-to-host
  copy of ALL digests (32 bytes per nonce) plus flags, and 4 cudaFree
  per batch. cudaFree return values were ignored.
- D2. Device flags computed but unused: the Python layer received
  flags, ignored them, and rescanned every digest in Python
  (int.from_bytes per nonce), so the device-side target comparison
  saved nothing.
- D3. No midstate: every nonce recomputed the full inner SHA-256
  including the first 64-byte block, which is nonce-independent.
- D4. build.py always exited 0, including on compiler failure, and
  reported host validation and CUDA compilation as one blob.
- D5. Kernel schedule: a 64-word message schedule array per thread
  (ptxas: 52 registers, 496 bytes of stack for a full-header kernel
  at sm_80), no circular-schedule alternative.
- D6. No candidate bound, counter, or overflow concept anywhere:
  correctness of "find candidates" relied on transferring everything.
- D7. No streams, no events, no kernel timing, no pinned memory:
  all transfers synchronous, kernel time unmeasurable.
- D8. diagnostics.py verdict claimed the toolkit "builds and
  validates" unconditionally, which became false when the toolkit
  was removed by a VM replacement.
- D9. Runtime CUDA failure handling existed (fall back to CPU) but
  recorded no structured event: no affected range, no retry record.
- D10. A requested CUDA execution could silently become a CPU
  execution in the default mode with only a reason string; there
  was no strict CUDA-only mode that fails.

## Corrections implemented

### Shared kernel source (gpu/cuda/kernels/sha256.h)

- Compression core refactored to bal_compress_state /
  bal_compress_state_circ over an explicit state, so the streaming
  API, the midstate path, and the schedule variant share one round
  function and one set of constants.
- Circular 16-word schedule variant: the schedule lives in a
  16-word ring (slot i&15), mathematically identical, far less
  per-thread state (compile-time data below).
- Midstate path: bal_sha256d_midstate compresses header bytes 0..63
  from the IV once per header prefix; bal_sha256d_from_midstate
  builds the second block from the 16-byte tail (bytes 64..79),
  patches the nonce little-endian at tail offsets 12..15, applies
  the exact 80-byte padding (0x80, zeros, bit length 640), runs the
  outer SHA-256. The split is exactly at the consensus block
  boundary; bytes 64..79 (merkle tail, timestamp, nBits) travel
  with the per-nonce work, so a midstate is stale the moment any
  byte of header[0..63] changes, and set_work is keyed to the exact
  (header, target) pair in Python and re-uploaded on any change in
  the C ABI. No round is shortened, approximated, or skipped.
- Candidate primitive bal_record_candidate: one function used by
  the CUDA kernel and the host validation binary. An atomic counter
  counts every candidate, a slot index is claimed atomically before
  any write, a write happens only when the claimed index is inside
  the allocated capacity, and an overflow flag is set otherwise.
  Callers must treat overflow as an incomplete search, never as a
  clean truncated list.

### CUDA host library (gpu/cuda/engine.cu)

- New persistent context ABI: bal_cuda_ctx_create / set_work /
  search / batch_diag / destroy. All buffers (midstate, tail,
  target, counter, overflow, candidate array, diagnostic buffers)
  are allocated once, reused across batches, and freed on destroy;
  destroy returns the first free error instead of ignoring cleanup
  failures. A dedicated stream and two CUDA events are part of the
  context; kernel time is measured with the events.
- Production kernel bal_search_kernel: midstate path, GPU-side
  target comparison with the shared bal_meets_target
  (little-endian numeric order, equality meets), candidate records
  only. Host retrieval reads the 4-byte counter and overflow flag
  first, then only the stored records.
- Diagnostic kernel bal_diag_kernel returns every digest and flag
  for self-tests and differential debugging. It is not the
  production path.
- Every CUDA call is checked, including cudaGetLastError after
  launches and stream synchronization errors. Numeric codes only
  cross the ABI; no device names or identifiers.
- Legacy bal_cuda_batch and bal_cuda_device_count are retained
  with unchanged behavior for older callers; the audit findings
  against the legacy path are documented above and new code does
  not use it.
- Streams: one stream per context, all transfers and launches on
  it. Pinned host memory was investigated and deliberately not
  adopted: candidate records are tiny (the only regular
  device-to-host traffic), and the large diagnostic transfers are
  not the production path, so pinning would add lifetime complexity
  for no measurable production benefit. Without a device this is a
  design judgement, recorded as such, not a measurement.

### Python layer (gpu/engine.py)

- CudaContext wrapper over the new ABI. On engine init the context
  is verified through the diagnostic path against CPU digests
  before any production use; failure leaves the legacy path or the
  CPU fallback, with the reason recorded (cuda_context_reason).
- Production CUDA batch path returns only candidates; every
  candidate is CPU verified (digest, nonce, target) before it is
  returned. Candidate overflow raises RuntimeError: the search is
  refused, not truncated.
- Runtime CUDA failure records a structured fallback event (range,
  reason, retried_on) and the retried work reports the backend
  that actually ran it. Stats now carry fallback_events and, on
  the CUDA path, kernel_ms and candidates_found.
- requested="cuda-only" is a strict mode: if CUDA cannot execute,
  construction raises RuntimeError naming the reason. Default
  "auto" and "cuda" (prefer) behavior is preserved.
- The existing ComputeEngine interface (batch_search, search_first,
  search_first_counted, benchmark, describe) is unchanged for
  mining/engine.py, mining/mainnet_live.py, and the tests.

### Build and diagnostics (gpu/cuda/build.py, gpu/diagnostics.py)

- Separated states: host_compiler, host_build, cuda_compiler,
  cuda_build, cuda_library, runtime (device_available, no_device,
  runtime_error_<code>, library_not_built, library_load_failed),
  device_count, execution_verified (always False from the build;
  only a live self-test in gpu.engine can set it).
- Exit status: the full build exits 1 when the host build fails,
  the CUDA build fails, or no CUDA compiler exists; --host-only
  exits 0 on host success. Compiler stderr is preserved in the
  result on failure. The host build now also builds host_checks.
- diagnostics.py uses the same state vocabulary and computes its
  verdict from actual facts (it no longer claims a toolkit exists
  when none does). No serials, UUIDs, or device names anywhere.

### Benchmark harness (gpu/benchmark.py)

Warmup batch, repeated measured batches, median/min/max rates,
end-to-end time on a monotonic host clock, kernel time from CUDA
events only when a batch really ran on CUDA, fallback events, and
an explicit label. On this machine it reports: backend c, median
about 1.45M H/s over the sampled runs (range 0.95M to 1.96M on a
shared, capped, contended VM), "NOT a GPU measurement", and the
CPU-versus-GPU comparison as "not comparable yet".

## Correctness evidence (host-exact, for the exact shared source)

gpu/cuda/host_checks.cpp compiles kernels/sha256.h for the host and
tests the new logic; tests/test_gpu_correction.py cross-checks its
output independently:

- Genesis hash via the midstate path and via the circular path:
  000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f.
- Fixed pseudo-random header sample at nonce 12345 matches hashlib
  exactly (Python-recomputed).
- 300 randomized headers x 5 nonces (0, 1, 12345, 0xFFFFFFFE,
  0xFFFFFFFF): full path vs midstate vs circular, 0 mismatches.
- Candidate recording over genesis nonces 0..1999 at the regtest
  target: total 1021 (matches a Python recount), recorded capped
  at 3, overflow 1.
- Concurrent recording: 8 host threads, 40,000 synthetic candidates
  into capacity 100: counter 40,000, recorded exactly 100, overflow
  1, no duplicates possible by construction (atomic index claim).
- Original host_sha256 vectors still pass after the refactor:
  sha256("abc"), genesis, 49,907 regtest-target hits in 100,000
  nonces, FIPS million-byte vector.
- Target boundaries through the live engine: digest below target
  hits, digest exactly equal to target meets, target minus one
  misses.
- Nonce boundaries through the live engine: start 0xFFFFFFFF with
  count 1 works; 0xFFFFFFFE with count 2 works; wrapping, empty,
  and out-of-space ranges are rejected with ValueError.

## Compile-time kernel data (nvcc 12.9.86, sm_80, ptxas -v)

Compile-time resource data only, NOT measured throughput:

- Full-header kernel (old approach): 52 registers, 496 B stack.
- Midstate kernel, 64-word schedule: 48 registers, 416 B stack.
- Midstate kernel, circular schedule: 32 registers, 64 B stack.
- Production bal_search_kernel as shipped: 48 registers, 416 B
  stack (64-word schedule; the circular variant is proven exact
  and available, and switching the production kernel to it is a
  one-line change to make after device benchmarks can confirm the
  register saving converts to throughput on real hardware).

## Sanitizer status

cuda-sanitizer-12-9 was installed. Running compute-sanitizer
(memcheck) against a minimal CUDA program on this machine reports
that the target terminated before the first instrumented API call:
there is no device or driver for the runtime to initialize
against. Device-side memcheck, racecheck, and synccheck runs are
therefore UNVERIFIED here and must be run on the first GPU
machine. The candidate primitive's memory safety is meanwhile
covered by the host concurrency tests above, which exercise the
identical source logic.

## Test results

- tests/test_gpu_correction.py: PASSED (both with the toolkit
  absent, in its honest-states branch, and after restoration).
- tests/test_gpu_compute.py: PASSED.
- Full suite: 16 of 17 Makefile targets pass. The single failure
  is test-rtl, which fails because iverilog is absent after the VM
  replacement (environment, unrelated to the GPU subsystem, not
  hidden and not weakened). test-gpu passes now that the toolkit
  is restored.
- Regtest integration through the existing mining workflow
  (tests/test_mining_engine.py): PASSED. Templates flowed through
  ComputeEngine and blocks were accepted (tip 504 to 507 during
  the runs). The executing backend was "c" (CPU), reported as CPU
  execution everywhere. This is not Gate 7 evidence.

## The seven gates

- Gate 1, mathematical correctness: PASS at the level this machine
  can prove. The optimized implementation's exact source (midstate
  and circular variants) is digest-exact against hashlib, the host
  reference, and the genesis block, over randomized and boundary
  inputs. Device execution of that source is Gate 6's question.
- Gate 2, target correctness: PASS at the same level. GPU-side
  filtering uses the shared bal_meets_target; its logic is proven
  against independent Python recounts and boundary cases, and the
  Python production path CPU-verifies every candidate regardless.
- Gate 3, memory safety: PASS for the candidate primitive and
  context design as host-proven (bounded writes, atomic claims,
  overflow always surfaced, concurrent stress exact). Device
  sanitizer confirmation is pending hardware (see Sanitizer
  status) and is not claimed.
- Gate 4, performance: UNVERIFIED on device. No GPU exists, so no
  device benchmark of old versus new is possible and none is
  fabricated. Compile-time evidence (register and stack reductions
  above) indicates the direction; measured device proof awaits
  hardware. Host-path benchmark numbers in this report are
  labelled NOT GPU measurements.
- Gate 5, runtime reliability: PASS for everything exercisable
  here: build states and exit codes, honest fallback with
  structured events, strict CUDA-only failure, repeated engine
  init, self-test gating before trust. Context creation on a real
  device is part of Gate 6.
- Gate 6, actual device verification: UNVERIFIED. No physical
  NVIDIA GPU exists on this VM. Compilation and host validation
  were performed and are explicitly not substitutes.
- Gate 7, mining integration with a GPU candidate: UNVERIFIED.
  The wiring is complete and exercised end-to-end on regtest with
  the honest CPU fallback; no GPU-generated candidate has ever
  existed here, so no GPU block acceptance is claimed.

To close Gates 4, 6, and 7: any machine with a supported NVIDIA
GPU and driver running this repo. On it, ComputeEngine will build
the context, pass the diagnostic self-test, select the cuda
backend, and the same test files plus compute-sanitizer runs and
a regtest mining cycle will produce the missing evidence. No code
change is expected to be needed; if the diagnostic self-test fails
there, the engine will say so and stay on CPU.

## Files changed

New: gpu/cuda/host_checks.cpp, gpu/benchmark.py,
tests/test_gpu_correction.py, results/TASK002_GPU_CORRECTION.md,
evidence/regtest/task002-gpu-correction.json.
Modified: gpu/cuda/kernels/sha256.h, gpu/cuda/engine.cu,
gpu/cuda/build.py, gpu/engine.py, gpu/diagnostics.py,
gpu/README.md, docs/CUDA.md, tests/test_gpu_compute.py, Makefile
(new test-gpu-correction target, wired into test-all).

Environment change (not repo): CUDA toolkit 12.9 packages restored
via apt from NVIDIA's official repository, listed above.

## Remaining limitations

- No device: Gates 4 (device side), 6, 7 unverified, sanitizer
  device runs pending, streams benefit unmeasured, pinned memory
  decision unmeasured.
- The production kernel still uses the 64-word schedule; the
  proven circular variant awaits a device benchmark before being
  made the default, per the rule that optimizations need measured
  benefit, not just lower register counts.
- Legacy bal_cuda_batch retains its per-batch allocation behavior
  for compatibility; it is documented as legacy and unused by the
  production path.
- The toolkit lives in system paths, so a future VM replacement
  will remove it again; build.py now reports that state honestly
  instead of failing obscurely.

## Task 003 addendum (2026-11-14)

Task 003 hardened three GPU items from this report; see
results/TASK003_CORRECTIONS.md for the full evidence. Gates 4, 6
and 7 remain UNVERIFIED: this VM still has no NVIDIA GPU.

- Candidate overflow (was: reported and refused, search lost):
  CudaContext.search still raises on overflow, now as the typed
  CandidateOverflowError, and the new guaranteed-coverage driver
  collect_candidates_complete (used by CudaContext.
  search_complete and by ComputeEngine.batch_search) partitions
  the range into target-sized sub-batches and splits only an
  overflowing sub-range until it resolves. No candidate is
  discarded, re-searched work is accounted separately from unique
  coverage, and the returned set is deduplicated by nonce.
  Exercised end-to-end through a Python stub with device-identical
  bounded semantics, since no device exists here.
- Startup validation (was: legacy batch plus a diagnostic-path
  context check could leave CUDA selected): CUDA is now selected
  only when cuda_production_selftest passes on the persistent
  context. It exercises the production candidate path itself
  (work setup and midstate, candidate search, counter, capacity
  overflow probe, overflow recovery) and compares the candidate
  set against a CPU recount. Diagnostic success alone can no
  longer authorize CUDA.
- C ABI range validation (was: start + count comparisons):
  bal_cuda_ctx_search, bal_cuda_ctx_batch_diag and the legacy
  bal_cuda_batch now call the shared subtraction-based
  bal_nonce_range_valid from kernels/sha256.h, and context
  creation bounds its allocation sizes. The validator is proven
  12 of 12 on the host build (gpu/cuda/host_checks.cpp line 7).
