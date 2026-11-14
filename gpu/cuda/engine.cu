// CUDA nonce search for Bitcoin Autonomous Lab (Task 002 rewrite).
//
// Two ABIs live here:
//   * Persistent context (production): bal_cuda_ctx_create /
//     bal_cuda_ctx_set_work / bal_cuda_ctx_search /
//     bal_cuda_ctx_batch_diag / bal_cuda_ctx_destroy. Buffers are
//     allocated once, reused across batches, and freed on destroy.
//     The production search kernel uses the SHA-256 midstate of the
//     header's first 64 bytes and GPU-side target filtering: only
//     candidate records (nonce + digest) cross back to the host,
//     through the bounded candidate array in kernels/sha256.h.
//   * Legacy one-shot: bal_cuda_device_count and bal_cuda_batch,
//     retained for older callers and hardened in Task 003.8. The
//     legacy batch still allocates per call and returns every
//     digest; new code must use the context ABI.
// Numeric error codes only cross the boundary: no device names,
// serials, or other identifiers. Local validation codes are
// defined with the shared validator in kernels/sha256.h (0
// success; -1 invalid argument; -2 host allocation failure; -3
// invalid kernel configuration; -4 invalid nonce range; -5
// allocation-size overflow or size limit; -6 legacy batch over
// BAL_CUDA_LEGACY_MAX_BATCH, 2^24 nonces). Positive return values
// are CUDA runtime error codes. Every CUDA call is checked,
// including frees in destroy (the first free error is returned).
#include <cuda_runtime.h>
#include <stdint.h>
#include <stdlib.h>
#include "kernels/sha256.h"

// ---------------- kernels ----------------

// Production search: midstate + tail per nonce, GPU target filter,
// bounded candidate output.
__global__ void bal_search_kernel(const uint32_t* __restrict__ midstate,
                                  const uint8_t* __restrict__ tail,
                                  const uint8_t* __restrict__ target_le,
                                  uint64_t start, uint32_t count,
                                  uint32_t cand_cap,
                                  uint32_t* __restrict__ counter,
                                  uint32_t* __restrict__ overflow,
                                  uint32_t* __restrict__ cand_nonces,
                                  uint8_t* __restrict__ cand_digests) {
  uint64_t i = (uint64_t)blockIdx.x * blockDim.x + threadIdx.x;
  if (i >= count) return;
  uint32_t nonce = (uint32_t)(start + i);
  uint32_t st[8];
  for (int w = 0; w < 8; w++) st[w] = midstate[w];
  uint8_t digest[32];
  bal_sha256d_from_midstate(st, tail, nonce, digest);
  if (bal_meets_target(digest, target_le)) {
    bal_record_candidate(counter, cand_cap, cand_nonces, cand_digests,
                         overflow, nonce, digest);
  }
}

// Diagnostic kernel: same midstate path, but returns every digest
// and flag. Used by self-tests and differential debugging only; it
// is NOT the production mining path.
__global__ void bal_diag_kernel(const uint32_t* __restrict__ midstate,
                                const uint8_t* __restrict__ tail,
                                const uint8_t* __restrict__ target_le,
                                uint64_t start, uint32_t count,
                                uint8_t* __restrict__ hashes,
                                uint8_t* __restrict__ flags) {
  uint64_t i = (uint64_t)blockIdx.x * blockDim.x + threadIdx.x;
  if (i >= count) return;
  uint32_t nonce = (uint32_t)(start + i);
  uint32_t st[8];
  for (int w = 0; w < 8; w++) st[w] = midstate[w];
  uint8_t digest[32];
  bal_sha256d_from_midstate(st, tail, nonce, digest);
  for (int b = 0; b < 32; b++) hashes[32 * i + b] = digest[b];
  flags[i] = (uint8_t)bal_meets_target(digest, target_le);
}

// Legacy kernel (full header per nonce), retained for bal_cuda_batch.
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

// ---------------- persistent context ----------------

extern "C" int bal_cuda_ctx_destroy(void* vctx);

struct BalCudaCtx {
  uint32_t max_count;
  uint32_t cand_cap;
  uint32_t* d_midstate;
  uint8_t* d_tail;
  uint8_t* d_target;
  uint32_t* d_counter;
  uint32_t* d_overflow;
  uint32_t* d_cand_nonces;
  uint8_t* d_cand_digests;
  uint8_t* d_diag_hashes;
  uint8_t* d_diag_flags;
  cudaStream_t stream;
  cudaEvent_t ev_begin;
  cudaEvent_t ev_end;
  int has_work;
};

extern "C" int bal_cuda_ctx_create(uint32_t max_count, uint32_t cand_cap,
                                   void** out_ctx) {
  // Task 003.8: out_ctx is validated first and cleared IMMEDIATELY,
  // before any other validation or allocation, so every failure
  // path below leaves the caller's pointer null, never
  // uninitialized, stale, or partially constructed.
  if (!out_ctx) return BAL_CUDA_ERR_INVALID_ARGUMENT;
  *out_ctx = nullptr;
  if (!max_count || !cand_cap) return BAL_CUDA_ERR_INVALID_ARGUMENT;
  // Task 003.7/003.8: allocation sizes are products (max_count * 32,
  // cand_cap * 32, cand_cap * 4). They are computed with checked
  // multiplication, and the caps below additionally bound them to
  // sane sizes (diagnostic buffer at most 512 MiB, candidate
  // digests at most 128 MiB), rejecting absurd requests with an
  // explicit error instead of relying on the allocator to fail.
  if (max_count > (1u << 24) || cand_cap > (1u << 22))
    return BAL_CUDA_ERR_SIZE_LIMIT;
  size_t cand_nonce_bytes = 0, cand_digest_bytes = 0,
         diag_hash_bytes = 0, diag_flag_bytes = 0;
  if (!bal_checked_mul_size((size_t)cand_cap, (size_t)4,
                            &cand_nonce_bytes) ||
      !bal_checked_mul_size((size_t)cand_cap, (size_t)32,
                            &cand_digest_bytes) ||
      !bal_checked_mul_size((size_t)max_count, (size_t)32,
                            &diag_hash_bytes) ||
      !bal_checked_mul_size((size_t)max_count, (size_t)1,
                            &diag_flag_bytes))
    return BAL_CUDA_ERR_SIZE_LIMIT;
  BalCudaCtx* ctx = (BalCudaCtx*)calloc(1, sizeof(BalCudaCtx));
  if (!ctx) return BAL_CUDA_ERR_HOST_ALLOCATION;
  ctx->max_count = max_count;
  ctx->cand_cap = cand_cap;
  cudaError_t e = cudaSuccess;
#define BAL_CTX_TRY(call) do { e = (call); if (e != cudaSuccess) { \
    bal_cuda_ctx_destroy(ctx); return (int)e; } } while (0)
  BAL_CTX_TRY(cudaMalloc((void**)&ctx->d_midstate, 32));
  BAL_CTX_TRY(cudaMalloc((void**)&ctx->d_tail, 16));
  BAL_CTX_TRY(cudaMalloc((void**)&ctx->d_target, 32));
  BAL_CTX_TRY(cudaMalloc((void**)&ctx->d_counter, 4));
  BAL_CTX_TRY(cudaMalloc((void**)&ctx->d_overflow, 4));
  BAL_CTX_TRY(cudaMalloc((void**)&ctx->d_cand_nonces, cand_nonce_bytes));
  BAL_CTX_TRY(cudaMalloc((void**)&ctx->d_cand_digests, cand_digest_bytes));
  BAL_CTX_TRY(cudaMalloc((void**)&ctx->d_diag_hashes, diag_hash_bytes));
  BAL_CTX_TRY(cudaMalloc((void**)&ctx->d_diag_flags, diag_flag_bytes));
  BAL_CTX_TRY(cudaStreamCreate(&ctx->stream));
  BAL_CTX_TRY(cudaEventCreate(&ctx->ev_begin));
  BAL_CTX_TRY(cudaEventCreate(&ctx->ev_end));
#undef BAL_CTX_TRY
  *out_ctx = ctx;
  return 0;
}

extern "C" int bal_cuda_ctx_destroy(void* vctx) {
  BalCudaCtx* ctx = (BalCudaCtx*)vctx;
  if (!ctx) return 0;
  cudaError_t first = cudaSuccess;
#define BAL_FREE(call) do { cudaError_t fe = (call); \
    if (first == cudaSuccess) first = fe; } while (0)
  if (ctx->ev_begin) BAL_FREE(cudaEventDestroy(ctx->ev_begin));
  if (ctx->ev_end) BAL_FREE(cudaEventDestroy(ctx->ev_end));
  if (ctx->stream) BAL_FREE(cudaStreamDestroy(ctx->stream));
  if (ctx->d_midstate) BAL_FREE(cudaFree(ctx->d_midstate));
  if (ctx->d_tail) BAL_FREE(cudaFree(ctx->d_tail));
  if (ctx->d_target) BAL_FREE(cudaFree(ctx->d_target));
  if (ctx->d_counter) BAL_FREE(cudaFree(ctx->d_counter));
  if (ctx->d_overflow) BAL_FREE(cudaFree(ctx->d_overflow));
  if (ctx->d_cand_nonces) BAL_FREE(cudaFree(ctx->d_cand_nonces));
  if (ctx->d_cand_digests) BAL_FREE(cudaFree(ctx->d_cand_digests));
  if (ctx->d_diag_hashes) BAL_FREE(cudaFree(ctx->d_diag_hashes));
  if (ctx->d_diag_flags) BAL_FREE(cudaFree(ctx->d_diag_flags));
#undef BAL_FREE
  free(ctx);
  return (int)first;
}

// Prepare work: compute the midstate on the host from header bytes
// 0..63 (exact prefix identity: any change there yields a different
// midstate and set_work must be called again), upload midstate, tail
// (bytes 64..79) and target once for any number of batches.
extern "C" int bal_cuda_ctx_set_work(void* vctx, const uint8_t* header,
                                     const uint8_t* target_le) {
  BalCudaCtx* ctx = (BalCudaCtx*)vctx;
  if (!ctx || !header || !target_le) return -1;
  uint32_t midstate[8];
  bal_sha256d_midstate(header, midstate);
  cudaError_t e = cudaSuccess;
#define BAL_SW_TRY(call) do { e = (call); if (e != cudaSuccess) return (int)e; } while (0)
  BAL_SW_TRY(cudaMemcpyAsync(ctx->d_midstate, midstate, 32,
                             cudaMemcpyHostToDevice, ctx->stream));
  BAL_SW_TRY(cudaMemcpyAsync(ctx->d_tail, header + 64, 16,
                             cudaMemcpyHostToDevice, ctx->stream));
  BAL_SW_TRY(cudaMemcpyAsync(ctx->d_target, target_le, 32,
                             cudaMemcpyHostToDevice, ctx->stream));
  BAL_SW_TRY(cudaStreamSynchronize(ctx->stream));
#undef BAL_SW_TRY
  ctx->has_work = 1;
  return 0;
}

static int bal_ctx_grid(uint32_t count, unsigned threads, dim3* grid) {
  if (!threads || threads > 1024) return -1;
  uint64_t blocks = ((uint64_t)count + threads - 1) / threads;
  if (blocks > 0x7fffffffULL) return -3;
  grid->x = (unsigned)blocks;
  return 0;
}

// Production search over [start, start+count). Returns candidate
// records only. out_count is the TOTAL candidates found (which may
// exceed out capacity when out_overflow is 1; the stored records are
// then incomplete and the caller must not treat them as a clean
// result). out_kernel_ms is CUDA-event kernel time.
extern "C" int bal_cuda_ctx_search(void* vctx, uint64_t start,
                                   uint32_t count, unsigned threads,
                                   uint32_t* out_count,
                                   uint32_t* out_overflow,
                                   uint32_t* cand_nonces,
                                   uint8_t* cand_digests,
                                   float* out_kernel_ms) {
  BalCudaCtx* ctx = (BalCudaCtx*)vctx;
  if (!ctx || !ctx->has_work || !count || count > ctx->max_count) return -1;
  // Task 003.8: every output pointer is validated BEFORE any CUDA
  // operation, including the candidate buffers (a candidate could
  // always be stored, so their validity cannot wait until after
  // the kernel has run). out_kernel_ms alone is optional.
  if (!out_count || !out_overflow || !cand_nonces || !cand_digests)
    return BAL_CUDA_ERR_INVALID_ARGUMENT;
  // Task 003.7: subtraction-based range validation (the shared
  // bal_nonce_range_valid); the old start + count form could wrap
  // for start near 2^64 and admit an invalid range.
  if (!bal_nonce_range_valid(start, count)) return -4;
  dim3 grid;
  int grc = bal_ctx_grid(count, threads, &grid);
  if (grc != 0) return grc;
  cudaError_t e = cudaSuccess;
#define BAL_S_TRY(call) do { e = (call); if (e != cudaSuccess) return (int)e; } while (0)
  BAL_S_TRY(cudaMemsetAsync(ctx->d_counter, 0, 4, ctx->stream));
  BAL_S_TRY(cudaMemsetAsync(ctx->d_overflow, 0, 4, ctx->stream));
  BAL_S_TRY(cudaEventRecord(ctx->ev_begin, ctx->stream));
  bal_search_kernel<<<grid, threads, 0, ctx->stream>>>(
      ctx->d_midstate, ctx->d_tail, ctx->d_target, start, count,
      ctx->cand_cap, ctx->d_counter, ctx->d_overflow,
      ctx->d_cand_nonces, ctx->d_cand_digests);
  BAL_S_TRY(cudaGetLastError());
  BAL_S_TRY(cudaEventRecord(ctx->ev_end, ctx->stream));
  uint32_t total = 0, ovf = 0;
  BAL_S_TRY(cudaMemcpyAsync(&total, ctx->d_counter, 4,
                            cudaMemcpyDeviceToHost, ctx->stream));
  BAL_S_TRY(cudaMemcpyAsync(&ovf, ctx->d_overflow, 4,
                            cudaMemcpyDeviceToHost, ctx->stream));
  BAL_S_TRY(cudaStreamSynchronize(ctx->stream));
  *out_count = total;
  *out_overflow = ovf;
  uint32_t stored = total < ctx->cand_cap ? total : ctx->cand_cap;
  if (stored) {
    if (!cand_nonces || !cand_digests) return -1;
    BAL_S_TRY(cudaMemcpy(cand_nonces, ctx->d_cand_nonces,
                         (size_t)stored * 4, cudaMemcpyDeviceToHost));
    BAL_S_TRY(cudaMemcpy(cand_digests, ctx->d_cand_digests,
                         (size_t)stored * 32, cudaMemcpyDeviceToHost));
  }
  if (out_kernel_ms) {
    float ms = 0.0f;
    BAL_S_TRY(cudaEventElapsedTime(&ms, ctx->ev_begin, ctx->ev_end));
    *out_kernel_ms = ms;
  }
#undef BAL_S_TRY
  return 0;
}

// Diagnostic batch: every digest and flag, persistent buffers.
extern "C" int bal_cuda_ctx_batch_diag(void* vctx, uint64_t start,
                                       uint32_t count, unsigned threads,
                                       const uint8_t* header,
                                       const uint8_t* target_le,
                                       uint8_t* hashes, uint8_t* flags) {
  BalCudaCtx* ctx = (BalCudaCtx*)vctx;
  if (!ctx || !count || count > ctx->max_count || !hashes || !flags ||
      !header || !target_le)
    return BAL_CUDA_ERR_INVALID_ARGUMENT;
  if (!bal_nonce_range_valid(start, count)) return -4;
  int rc = bal_cuda_ctx_set_work(ctx, header, target_le);
  if (rc != 0) return rc;
  dim3 grid;
  int grc = bal_ctx_grid(count, threads, &grid);
  if (grc != 0) return grc;
  cudaError_t e = cudaSuccess;
#define BAL_D_TRY(call) do { e = (call); if (e != cudaSuccess) return (int)e; } while (0)
  bal_diag_kernel<<<grid, threads, 0, ctx->stream>>>(
      ctx->d_midstate, ctx->d_tail, ctx->d_target, start, count,
      ctx->d_diag_hashes, ctx->d_diag_flags);
  BAL_D_TRY(cudaGetLastError());
  BAL_D_TRY(cudaMemcpyAsync(hashes, ctx->d_diag_hashes, (size_t)count * 32,
                            cudaMemcpyDeviceToHost, ctx->stream));
  BAL_D_TRY(cudaMemcpyAsync(flags, ctx->d_diag_flags, count,
                            cudaMemcpyDeviceToHost, ctx->stream));
  BAL_D_TRY(cudaStreamSynchronize(ctx->stream));
#undef BAL_D_TRY
  return 0;
}

// ---------------- legacy ABI (retained) ----------------

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
  // Task 003.8: validate ALL arguments, the nonce range, the
  // documented maximum batch (BAL_CUDA_LEGACY_MAX_BATCH) and the
  // count-derived allocation sizes (checked multiplication)
  // BEFORE any pointer is dereferenced or copied and before any
  // CUDA memory operation. Invalid input returns the documented
  // negative codes from kernels/sha256.h and allocates nothing.
  size_t hash_bytes = 0, flag_bytes = 0;
  int vrc = bal_cuda_batch_validate(header, target_le, hashes, flags,
                                    start, count, threads, &hash_bytes,
                                    &flag_bytes);
  if (vrc != BAL_CUDA_OK) return vrc;
  uint8_t *d_header = nullptr, *d_target = nullptr, *d_hashes = nullptr,
          *d_flags = nullptr;
  cudaError_t e = cudaSuccess;
#define BAL_TRY(call) do { e = (call); if (e != cudaSuccess) goto done; } while (0)
  BAL_TRY(cudaMalloc((void**)&d_header, 80));
  BAL_TRY(cudaMalloc((void**)&d_target, 32));
  BAL_TRY(cudaMalloc((void**)&d_hashes, hash_bytes));
  BAL_TRY(cudaMalloc((void**)&d_flags, flag_bytes));
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
  BAL_TRY(cudaMemcpy(hashes, d_hashes, hash_bytes, cudaMemcpyDeviceToHost));
  BAL_TRY(cudaMemcpy(flags, d_flags, flag_bytes, cudaMemcpyDeviceToHost));
done:
  // Every exit path after validation passes through here, and
  // every allocation that succeeded is freed (all frees are
  // attempted even if an earlier one reports an error). If the
  // batch itself succeeded but a free fails, the free error is
  // reported rather than hidden.
  {
    cudaError_t first_free = cudaSuccess;
    if (d_flags) { cudaError_t fe = cudaFree(d_flags);
                   if (first_free == cudaSuccess) first_free = fe; }
    if (d_hashes) { cudaError_t fe = cudaFree(d_hashes);
                    if (first_free == cudaSuccess) first_free = fe; }
    if (d_target) { cudaError_t fe = cudaFree(d_target);
                    if (first_free == cudaSuccess) first_free = fe; }
    if (d_header) { cudaError_t fe = cudaFree(d_header);
                    if (first_free == cudaSuccess) first_free = fe; }
    if (e == cudaSuccess) e = first_free;
  }
#undef BAL_TRY
  return (int)e;
}
