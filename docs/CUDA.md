# CUDA: installation, build and runtime verdict on this machine

## What was installed

CUDA Toolkit 12.9 (nvcc 12.9.86) from NVIDIA's official Ubuntu
24.04 apt repository (cuda-keyring, packages cuda-nvcc-12-9,
cuda-cudart-12-9, cuda-cccl-12-9), at /usr/local/cuda. Cost: $0.

## What builds and validates

- gpu/cuda/engine.cu compiles cleanly with nvcc into
  .local/cuda/libbal_cuda.so (batch nonce search kernel over the
  shared gpu/cuda/kernels/sha256.h).
- The same sha256.h compiled for the host CPU (gpu/cuda/host_sha256.cpp)
  matches hashlib exactly: sha256 of "abc", the genesis block hash
  from its real nonce, the FIPS million-byte vector, and the count
  of regtest-target hits over 100,000 nonces (49,907, computed
  independently in the test).
- gpu/engine.py ComputeEngine loads the library, asks the runtime
  for devices, and would self-test a batch against the CPU before
  trusting CUDA results.

## The runtime verdict (honest)

This VM has no NVIDIA GPU: zero /dev/nvidia device nodes, and the
CUDA runtime returns error 35 (cudaErrorInsufficientDriver) when
asked for a device count. So no GPU computation has run here, and
none is claimed. The ComputeEngine selects the CPU backend and
records the fallback reason on every run; gpu/diagnostics.py
reproduces the whole picture on demand (make cuda-diag).

On any machine with a real NVIDIA device and driver, the same code
path selects CUDA only after the live self-test batch matches the
CPU digest for digest. Nothing about that claim is pre-baked.

## Task 003.8 ABI hardening (2026-11-14)

The legacy one-shot entry point bal_cuda_batch validates every
argument before any CUDA memory operation, through the shared
bal_cuda_batch_validate in gpu/cuda/kernels/sha256.h (the same
code the host validation build executes): header, target_le,
hashes and flags must be non-null; the thread count must be
within [1, 1024]; the nonce range must pass the subtraction-based
bal_nonce_range_valid; and the count-derived allocation sizes
(count times 32 digest bytes, count times 1 flag bytes) are
computed with checked multiplication. The documented maximum
legacy batch is BAL_CUDA_LEGACY_MAX_BATCH = 2^24 nonces (the
legacy path materializes every digest, so at most 512 MiB of
digest output); larger requests are rejected with -6 and belong
on the persistent candidate-filtering context or in chunks.

C ABI error codes (negative values are local validation errors,
positive values are CUDA runtime error codes): 0 success; -1
invalid argument (null pointer, zero count, bad thread count);
-2 host allocation failure; -3 invalid kernel configuration; -4
invalid nonce range; -5 allocation-size overflow or size limit;
-6 legacy batch too large.

bal_cuda_ctx_create validates out_ctx first and clears it
immediately, so every failure path leaves the caller's pointer
null. The persistent-context search validates its candidate
output buffers before launching anything.

## Task 003.9 accounting note (2026-11-14)

Mining statistics follow the definitions in gpu/engine.py's
module docstring. device_hashes counts CUDA device
computations only (exactly 0 when no device executed work),
and the identity device_hashes == unique_coverage +
researched_hashes belongs to the CUDA candidate-recovery
driver alone; it is not a property of CPU or C statistics.
backend_hashes is the selected backend's own computations;
independent verification and trusted rescans are reported
separately as verification_hashes. ComputeEngine.benchmark
accumulates actual per-batch backend computations (see
benchmark_report), never the requested batch size. Full
record: results/TASK0039_FINAL_ACCOUNTING_CORRECTION.md.

## Task 002 update (2026-11-14)

The toolkit is currently ABSENT on this VM (a VM replacement
removed /usr/local/cuda and the NVIDIA apt source); a restore was
attempted from NVIDIA's official Ubuntu 24.04 repository. An older
libbal_cuda.so build remains in .local/cuda and still answers the
device-count call with error 35. The engine was rewritten around a
persistent CUDA context: midstate kernel (first 64 header bytes
compressed once per header), GPU-side target filtering, bounded
candidate array with atomic counter and overflow flag, CUDA events
for kernel timing, and a diagnostic batch mode for self-tests.
Build and diagnostics now report separated states and the build
exits nonzero when the requested build fails. Gates 6 (device
execution) and 7 (GPU candidate accepted by regtest) are UNVERIFIED
here; the full record is results/TASK002_GPU_CORRECTION.md.
