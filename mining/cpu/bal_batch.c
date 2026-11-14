/* Batch SHA256d nonce search as a shared library, midstate optimized.
 *
 * Per header, the first SHA-256 compression (bytes 0..63) is computed
 * once. Each nonce then costs exactly two compressions: the second
 * header block (bytes 64..79 with the nonce patched in, plus
 * padding) and the outer hash block. Uses OpenSSL's low-level
 * SHA256_Transform, which dispatches to SHA-NI on this CPU.
 *
 * Exported for gpu/engine.py (ComputeEngine) through ctypes. Output
 * layout matches the CUDA library: hashes is count*32 bytes, flags
 * is count bytes (1 when the digest meets the little-endian target).
 *
 * Concurrency, nonce-range and winner-publication rules live in
 * bal_search.h and are shared with bal_sha_intrin.c: per-search
 * context, C11 atomics, mutex-published winner, per-span thread
 * tracking, 64-bit half-open nonce intervals. There is no shared
 * mutable search state in this file, so independent searches may
 * run concurrently and the entry points are reentrant.
 *
 * Extended entry points (the originals are kept as wrappers):
 *   bal_c_search2 / bal_c_batch2 accept a 64-bit count and report
 *   the ACTUAL number of hash attempts through out_attempted.
 *   bal_c_batch always hashes the whole range, so its attempt
 *   count equals the range size; bal_c_search stops early on a
 *   hit, so its attempt count is the sum of the per-worker counts
 *   at the moment every worker stopped, which is at most the
 *   range size and usually far less.
 * Return values: 1 found (search only), 0 range exhausted,
 * -1 bad arguments, -2 nonce range exceeds the 32-bit space,
 * -3 winner publication failed (mutex error), -4 search context
 * initialization failed (no worker was started).
 */
#include <openssl/sha.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdint.h>
#include <string.h>

#include "bal_search.h"

_Atomic int bal_create_fail_after = -1;
_Atomic int bal_create_fail_calls = 0;
_Atomic int bal_mutex_fail_mask = 0;

/* Test hook: fail pthread_create after n successes (-1 disables). */
void bal_c_test_set_create_fail_after(int n) {
  atomic_store(&bal_create_fail_calls, 0);
  atomic_store(&bal_create_fail_after, n);
}

/* Test hook (Task 003.1): bit 0 fails mutex initialization,
 * bit 1 fails mutex locking, 0 disables. */
void bal_c_test_set_mutex_fail_mask(int mask) {
  atomic_store(&bal_mutex_fail_mask, mask);
}

static int meets(const uint8_t *digest, const uint8_t *target) {
  for (int i = 31; i >= 0; i--) {
    if (digest[i] < target[i]) return 1;
    if (digest[i] > target[i]) return 0;
  }
  return 1; /* exactly equal to the target also meets it */
}

static void store_be32(uint8_t *out, uint32_t v) {
  out[0] = (uint8_t)(v >> 24); out[1] = (uint8_t)(v >> 16);
  out[2] = (uint8_t)(v >> 8);  out[3] = (uint8_t)v;
}

static const uint32_t BAL_H0[8] = {0x6a09e667, 0xbb67ae85, 0x3c6ef372,
    0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};

/* One double hash for (header tail, midstate, nonce). Writes the
 * 32-byte digest in big-endian word order (the byte string whose
 * little-endian integer interpretation Bitcoin compares). */
static void hash_nonce(const uint8_t *header, const uint32_t midstate[8],
                       uint32_t nonce, uint8_t digest[32]) {
  uint8_t block[64];
  memset(block, 0, sizeof(block));
  memcpy(block, header + 64, 12);            /* bytes 64..75 */
  block[12] = (uint8_t)(nonce & 0xff);       /* nonce, LE in header */
  block[13] = (uint8_t)((nonce >> 8) & 0xff);
  block[14] = (uint8_t)((nonce >> 16) & 0xff);
  block[15] = (uint8_t)((nonce >> 24) & 0xff);
  block[16] = 0x80;
  store_be32(block + 60, 640);               /* 80 bytes * 8 */
  SHA256_CTX ictx;
  memset(&ictx, 0, sizeof(ictx));
  for (int w = 0; w < 8; w++) ictx.h[w] = midstate[w];
  SHA256_Transform(&ictx, block);
  uint8_t inner[32];
  for (int w = 0; w < 8; w++) store_be32(inner + 4 * w, ictx.h[w]);
  uint8_t oblock[64];
  memset(oblock, 0, sizeof(oblock));
  memcpy(oblock, inner, 32);
  oblock[32] = 0x80;
  store_be32(oblock + 60, 256);
  SHA256_CTX octx;
  memset(&octx, 0, sizeof(octx));
  for (int w = 0; w < 8; w++) octx.h[w] = BAL_H0[w];
  SHA256_Transform(&octx, oblock);
  for (int w = 0; w < 8; w++) store_be32(digest + 4 * w, octx.h[w]);
}

static void compute_midstate(const uint8_t *header, uint32_t midstate[8]) {
  SHA256_CTX ctx;
  SHA256_Init(&ctx);
  SHA256_Update(&ctx, header, 64);
  for (int w = 0; w < 8; w++) midstate[w] = ctx.h[w];
}

/* ---- batch: hash every nonce in the range ---- */

typedef struct {
  const uint8_t *header;
  uint32_t midstate[8];
  uint64_t start;
  uint64_t begin, end; /* offsets into the range, 64-bit */
  const uint8_t *target;
  uint8_t *hashes;
  uint8_t *flags;
  uint64_t attempted;
} Job;

static void *worker(void *arg) {
  Job *job = (Job *)arg;
  uint64_t done = 0;
  for (uint64_t i = job->begin; i < job->end; i++) {
    uint32_t nonce = (uint32_t)(job->start + i);
    uint8_t digest[32];
    hash_nonce(job->header, job->midstate, nonce, digest);
    memcpy(job->hashes + (size_t)i * 32, digest, 32);
    job->flags[i] = (uint8_t)meets(digest, job->target);
    done++;
  }
  job->attempted = done;
  return NULL;
}

int bal_c_batch2(const uint8_t *header, uint64_t start, uint64_t count,
                 unsigned threads, const uint8_t *target, uint8_t *hashes,
                 uint8_t *flags, uint64_t *out_attempted) {
  if (!header || !target || !hashes || !flags) return -1;
  if (!threads || threads > 16) return -1;
  int v = bal_validate_range(start, count);
  if (v != 0) return v;
  uint32_t midstate[8];
  compute_midstate(header, midstate);
  uint64_t begins[16], ends[16];
  unsigned spans = bal_partition(count, threads, begins, ends);
  pthread_t tids[16];
  int created[16] = {0};
  Job jobs[16];
  for (unsigned s = 0; s < spans; s++) {
    jobs[s] = (Job){header, {0}, start, begins[s], ends[s], target,
                    hashes, flags, 0};
    memcpy(jobs[s].midstate, midstate, sizeof(midstate));
    if (bal_pthread_create(&tids[s], NULL, worker, &jobs[s]) != 0) {
      worker(&jobs[s]); /* synchronous fallback, disjoint outputs */
    } else {
      created[s] = 1;
    }
  }
  for (unsigned s = 0; s < spans; s++)
    if (created[s]) pthread_join(tids[s], NULL);
  if (out_attempted) {
    uint64_t total = 0;
    for (unsigned s = 0; s < spans; s++) total += jobs[s].attempted;
    *out_attempted = total;
  }
  return 0;
}

int bal_c_batch(const uint8_t *header, uint64_t start, uint32_t count,
                unsigned threads, const uint8_t *target, uint8_t *hashes,
                uint8_t *flags) {
  return bal_c_batch2(header, start, count, threads, target, hashes,
                      flags, NULL);
}

/* ---- early-exit search: stop at the first qualifying nonce ---- */

typedef struct {
  const uint8_t *header;
  uint32_t midstate[8];
  uint64_t start;
  uint64_t begin, end;
  const uint8_t *target;
  BalSearchCtx *ctx;
  uint64_t attempted;
} SearchJob;

static void *search_worker(void *arg) {
  SearchJob *job = (SearchJob *)arg;
  uint64_t done = 0;
  for (uint64_t i = job->begin; i < job->end; i++) {
    if (bal_ctx_stopped(job->ctx)) break;
    uint32_t nonce = (uint32_t)(job->start + i);
    uint8_t digest[32];
    hash_nonce(job->header, job->midstate, nonce, digest);
    done++;
    if (meets(digest, job->target)) {
      bal_ctx_publish(job->ctx, nonce, digest);
      break;
    }
  }
  job->attempted = done;
  return NULL;
}

int bal_c_search2(const uint8_t *header, uint64_t start, uint64_t count,
                  unsigned threads, const uint8_t *target,
                  uint32_t *out_nonce, uint8_t *out_digest,
                  uint64_t *out_attempted) {
  if (!header || !target || !out_nonce || !out_digest) return -1;
  if (!threads || threads > 16) return -1;
  int v = bal_validate_range(start, count);
  if (v != 0) return v;
  uint32_t midstate[8];
  compute_midstate(header, midstate);
  BalSearchCtx ctx;
  if (bal_ctx_init(&ctx) != 0) return -4; /* no worker is started */
  uint64_t begins[16], ends[16];
  unsigned spans = bal_partition(count, threads, begins, ends);
  pthread_t tids[16];
  int created[16] = {0};
  SearchJob jobs[16];
  for (unsigned s = 0; s < spans; s++) {
    jobs[s] = (SearchJob){header, {0}, start, begins[s], ends[s],
                          target, &ctx, 0};
    memcpy(jobs[s].midstate, midstate, sizeof(midstate));
    if (bal_pthread_create(&tids[s], NULL, search_worker, &jobs[s]) != 0) {
      search_worker(&jobs[s]);
    } else {
      created[s] = 1;
    }
  }
  for (unsigned s = 0; s < spans; s++)
    if (created[s]) pthread_join(tids[s], NULL);
  if (out_attempted) {
    uint64_t total = 0;
    for (unsigned s = 0; s < spans; s++) total += jobs[s].attempted;
    *out_attempted = total;
  }
  if (bal_ctx_publish_failed(&ctx)) {
    bal_ctx_destroy(&ctx);
    return -3; /* winner publication failed: result is not trusted */
  }
  int found = ctx.found_valid;
  if (found) {
    *out_nonce = ctx.found_nonce;
    memcpy(out_digest, ctx.found_digest, 32);
  }
  bal_ctx_destroy(&ctx);
  return found ? 1 : 0;
}

int bal_c_search(const uint8_t *header, uint64_t start, uint32_t count,
                 unsigned threads, const uint8_t *target,
                 uint32_t *out_nonce, uint8_t *out_digest) {
  return bal_c_search2(header, start, count, threads, target, out_nonce,
                       out_digest, NULL);
}
