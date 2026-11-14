# gpu/: GPU acceleration (Task 004)

Status: implemented. ComputeEngine (gpu/engine.py) dispatches batch
SHA256d nonce search to CUDA when a real device exists and passes a
CPU-verified self-test, and to the CPU otherwise, with the fallback
reason recorded.

- cuda/engine.cu: batch nonce search kernel (shared kernels/sha256.h).
- cuda/kernels/sha256.h: one SHA-256 source for device, CUDA host
  and plain C++ host builds.
- cuda/host_sha256.cpp: host validation binary for that source.
- cuda/build.py: builds .local/cuda/libbal_cuda.so and host_sha256.
- diagnostics.py: capability facts only (make cuda-diag).

Verdict on the lab VM: the machine has no NVIDIA GPU (runtime
error 35), so no GPU computation is claimed. Full record in
docs/CUDA.md.

Task 002 additions: persistent CUDA context ABI in cuda/engine.cu
(midstate kernel, GPU-side target filtering, bounded candidate
array with overflow flag, CUDA-event kernel timing, diagnostic
batch mode), the circular 16-word schedule variant and midstate
path in kernels/sha256.h, host_checks.cpp validating all of that
logic on the host, gpu/benchmark.py, and
tests/test_gpu_correction.py. Full report in
results/TASK002_GPU_CORRECTION.md. Gates 6 and 7 are UNVERIFIED:
no physical GPU exists on this machine.
