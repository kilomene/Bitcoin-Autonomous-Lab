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

Verdict on the lab VM: CUDA Toolkit 12.9 is installed and the kernel
compiles and validates, but the machine has no NVIDIA GPU (runtime
error 35), so no GPU computation is claimed. Full record in
docs/CUDA.md.
