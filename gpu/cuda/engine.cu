// CUDA batch nonce search for Bitcoin Autonomous Lab.
//
// Exports a small C ABI used by gpu/engine.py through ctypes:
//   bal_cuda_device_count() -> number of CUDA devices, or negative
//                              CUDA error code when the runtime fails.
//   bal_cuda_batch(...)     -> fills hashes and target flags for a
//                              nonce batch; returns 0 on success or a
//                              numeric CUDA error code. Numeric only:
//                              no device names or identifiers cross
//                              this boundary.
// The SHA-256 logic is the shared kernels/sha256.h, the same source
// validated on the host CPU by host_sha256.cpp.
#include <cuda_runtime.h>
#include <stdint.h>
#include "kernels/sha256.h"

__global__ void bal_nonce_kernel(const uint8_t* header, uint64_t start,
                                 uint32_t count, const uint8_t* target_le,
                                 uint8_t* hashes, uint8_t* flags) {
  uint64_t i = (uint64_t)blockIdx.x * blockDim.x + threadIdx.x;
  if (i >= count) return;
  uint8_t digest[32];
  bal_sha256d_header(header, (uint32_t)(start + i), digest);
  for (int b = 0; b < 32; b++) hashes[32 * i + b] = digest[b];
  flags[i] = (uint8_t)bal_meets_target(digest, target_le);
}

extern "C" int bal_cuda_device_count() {
  int n = 0;
  cudaError_t e = cudaGetDeviceCount(&n);
  if (e != cudaSuccess) return -(int)e;
  return n;
}

extern "C" int bal_cuda_batch(const uint8_t* header, uint64_t start,
                              uint32_t count, unsigned threads,
                              const uint8_t* target_le, uint8_t* hashes,
                              uint8_t* flags) {
  if (!count || !threads || threads > 1024) return -1;
  if (start + count > 0x100000000ULL) return -1;
  uint8_t *d_header = nullptr, *d_target = nullptr, *d_hashes = nullptr,
          *d_flags = nullptr;
  cudaError_t e = cudaSuccess;
#define BAL_TRY(call) do { e = (call); if (e != cudaSuccess) goto done; } while (0)
  BAL_TRY(cudaMalloc((void**)&d_header, 80));
  BAL_TRY(cudaMalloc((void**)&d_target, 32));
  BAL_TRY(cudaMalloc((void**)&d_hashes, (size_t)count * 32));
  BAL_TRY(cudaMalloc((void**)&d_flags, count));
  BAL_TRY(cudaMemcpy(d_header, header, 80, cudaMemcpyHostToDevice));
  BAL_TRY(cudaMemcpy(d_target, target_le, 32, cudaMemcpyHostToDevice));
  {
    uint64_t blocks = ((uint64_t)count + threads - 1) / threads;
    if (blocks > 0x7fffffffULL) { e = cudaErrorInvalidConfiguration; goto done; }
    bal_nonce_kernel<<<(unsigned)blocks, threads>>>(d_header, start, count,
                                                    d_target, d_hashes, d_flags);
  }
  BAL_TRY(cudaGetLastError());
  BAL_TRY(cudaDeviceSynchronize());
  BAL_TRY(cudaMemcpy(hashes, d_hashes, (size_t)count * 32, cudaMemcpyDeviceToHost));
  BAL_TRY(cudaMemcpy(flags, d_flags, count, cudaMemcpyDeviceToHost));
done:
  if (d_flags) cudaFree(d_flags);
  if (d_hashes) cudaFree(d_hashes);
  if (d_target) cudaFree(d_target);
  if (d_header) cudaFree(d_header);
#undef BAL_TRY
  return (int)e;
}
