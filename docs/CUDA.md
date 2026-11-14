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
