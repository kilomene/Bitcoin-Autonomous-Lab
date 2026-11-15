/* NOVA SHA-X: AVX2 8-way multi-buffer software SHA-256d.
 * PRODUCTION kernel (EXP-039 integration, 2026-11-15) of the
 * kernel verified as research in EXP-032, where the batch
 * entry measured a pooled 1.409x [1.340, 1.480] against the
 * production C batch under the EXP-017 protocol. The kernel
 * body below the header is the EXP-032 source unchanged.
 *
 * Eight independent SHA-256d computations advance in
 * lockstep, one per 32-bit lane of a ymm register; the state
 * is transposed (vector j holds word j of all eight hashes);
 * block 1 is identical across lanes so the midstate is
 * computed once, scalar, and broadcast; block 2 differs only
 * in the nonce word; the outer block's first eight words are
 * the inner state vectors, so only the final digest store
 * transposes out.
 *
 * AVX2 differences from the AVX-512 original
 * (bal_avx512_mb.c), all forced by the instruction set:
 * - 8 lanes per group instead of 16.
 * - No VPROLD: each 32-bit rotation costs a shift pair plus
 *   an OR (3 vector ops where AVX-512 spends 1).
 * - The nonce byte swap uses VPSHUFB, which operates within
 *   each 128-bit half; every 32-bit lane lies entirely
 *   inside one half, so the per-word reversal is exact.
 *
 * Accounting mirrors bal_avx512_mb.c exactly (Task 003.9
 * definitions): out_attempted counts real nonces completed
 * (== count for batch); out_backend counts lane computations
 * including dummy lanes of a partial final group
 * (backend == sum over spans of ceil(span/8)*8). Dummy lanes
 * repeat the last real nonce; their outputs are never stored
 * and never counted as coverage. Search is group-atomic: on
 * a hit, attempted counts every real nonce of the completed
 * group.
 *
 * Exports (counted ABI, identical shape to bal_v_batch2 /
 * bal_v_search2 with the prefix bal_a):
 *   bal_a_batch2(header, start, count, threads, target,
 *                hashes, flags, out_attempted, out_backend)
 *   bal_a_search2(header, start, count, threads, target,
 *                 out_nonce, out_digest, out_attempted,
 *                 out_backend)
 * Return codes follow the counted ABI (-1 bad args or empty,
 * -2 range crossing 2^32, -3 winner publication failed,
 * -4 context init failed, 0 ok / miss, 1 found).
 *
 * Build (mining/cpu/build.py): gcc -O3 -mavx2, restricted
 * flag set, never -march=native, so the binary is portable
 * across AVX2 hosts. The kernel must only be CALLED after
 * the flag-free CPUID probe (bal_fallback_probe.c, linked
 * into the same library) confirms AVX2; gpu/engine.py
 * enforces that order.
 */
#include <stdint.h>
#include <string.h>
#include <stdatomic.h>
#include <pthread.h>
#include <immintrin.h>

#include "bal_search.h"

/* Failure-injection hooks declared by bal_search.h; the
 * definitions live in each translation unit that uses it. */
_Atomic int bal_create_fail_after = -1;
_Atomic int bal_create_fail_calls = 0;
_Atomic int bal_mutex_fail_mask = 0;

static const uint32_t A_K[64] = {
  0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,
  0x923f82a4,0xab1c5ed5,0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,
  0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,0xe49b69c1,0xefbe4786,
  0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
  0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,
  0x06ca6351,0x14292967,0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,
  0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,0xa2bfe8a1,0xa81a664b,
  0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
  0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,
  0x5b9cca4f,0x682e6ff3,0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,
  0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};

static const uint32_t A_H0[8] = {0x6a09e667,0xbb67ae85,0x3c6ef372,
  0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19};

/* ---- scalar one-block compression (midstate only) ---- */
static uint32_t arotr(uint32_t x, int n) {
  return (x >> n) | (x << (32 - n));
}

static void a_compress_scalar(const uint32_t in[8],
                              const uint8_t *block,
                              uint32_t out[8]) {
  uint32_t W[64];
  for (int i = 0; i < 16; i++)
    W[i] = ((uint32_t)block[4 * i] << 24) |
           ((uint32_t)block[4 * i + 1] << 16) |
           ((uint32_t)block[4 * i + 2] << 8) | block[4 * i + 3];
  for (int i = 16; i < 64; i++) {
    uint32_t s0 = arotr(W[i - 15], 7) ^ arotr(W[i - 15], 18) ^
                  (W[i - 15] >> 3);
    uint32_t s1 = arotr(W[i - 2], 17) ^ arotr(W[i - 2], 19) ^
                  (W[i - 2] >> 10);
    W[i] = W[i - 16] + s0 + W[i - 7] + s1;
  }
  uint32_t s[8];
  memcpy(s, in, 32);
  for (int t = 0; t < 64; t++) {
    uint32_t S1 = arotr(s[4], 6) ^ arotr(s[4], 11) ^ arotr(s[4], 25);
    uint32_t ch = (s[4] & s[5]) ^ (~s[4] & s[6]);
    uint32_t T1 = s[7] + S1 + ch + A_K[t] + W[t];
    uint32_t S0 = arotr(s[0], 2) ^ arotr(s[0], 13) ^ arotr(s[0], 22);
    uint32_t mj = (s[0] & s[1]) ^ (s[0] & s[2]) ^ (s[1] & s[2]);
    uint32_t T2 = S0 + mj;
    s[7] = s[6]; s[6] = s[5]; s[5] = s[4]; s[4] = s[3] + T1;
    s[3] = s[2]; s[2] = s[1]; s[1] = s[0]; s[0] = T1 + T2;
  }
  for (int i = 0; i < 8; i++) out[i] = in[i] + s[i];
}

/* ---- vector compression over 8 lanes ----
 * W0[16] are the block's first 16 schedule words as lane
 * vectors; S holds the input state as lane vectors; the
 * feed-forward is the caller's job. Identical round and
 * schedule structure to v_compress16 in the AVX-512
 * original, with AVX2 rotations expanded to shift pairs. */
static inline __m256i ar32(__m256i x, int n) {
  return _mm256_or_si256(_mm256_srli_epi32(x, n),
                         _mm256_slli_epi32(x, 32 - n));
}

static void a_compress8(__m256i S[8], const __m256i W0[16]) {
  __m256i W[16];
  for (int i = 0; i < 16; i++) W[i] = W0[i];
  __m256i a = S[0], b = S[1], c = S[2], d = S[3],
          e = S[4], f = S[5], g = S[6], h = S[7];
  for (int t = 0; t < 64; t++) {
    __m256i w;
    if (t < 16) {
      w = W[t];
    } else {
      __m256i x = W[(t - 15) & 15];
      __m256i y = W[(t - 2) & 15];
      __m256i s0 = _mm256_xor_si256(
        _mm256_xor_si256(ar32(x, 7), ar32(x, 18)),
        _mm256_srli_epi32(x, 3));
      __m256i s1 = _mm256_xor_si256(
        _mm256_xor_si256(ar32(y, 17), ar32(y, 19)),
        _mm256_srli_epi32(y, 10));
      w = _mm256_add_epi32(
        _mm256_add_epi32(W[(t - 16) & 15], s0),
        _mm256_add_epi32(W[(t - 7) & 15], s1));
      W[t & 15] = w;
    }
    __m256i S1 = _mm256_xor_si256(
      _mm256_xor_si256(ar32(e, 6), ar32(e, 11)), ar32(e, 25));
    __m256i ch = _mm256_xor_si256(_mm256_and_si256(e, f),
                                  _mm256_andnot_si256(e, g));
    __m256i T1 = _mm256_add_epi32(
      _mm256_add_epi32(
        _mm256_add_epi32(h, S1),
        _mm256_add_epi32(ch, _mm256_set1_epi32((int)A_K[t]))), w);
    __m256i S0 = _mm256_xor_si256(
      _mm256_xor_si256(ar32(a, 2), ar32(a, 13)), ar32(a, 22));
    __m256i mj = _mm256_xor_si256(
      _mm256_xor_si256(_mm256_and_si256(a, b),
                       _mm256_and_si256(a, c)),
      _mm256_and_si256(b, c));
    __m256i T2 = _mm256_add_epi32(S0, mj);
    h = g; g = f; f = e;
    e = _mm256_add_epi32(d, T1);
    d = c; c = b; b = a;
    a = _mm256_add_epi32(T1, T2);
  }
  S[0] = a; S[1] = b; S[2] = c; S[3] = d;
  S[4] = e; S[5] = f; S[6] = g; S[7] = h;
}

static int a_meets(const uint8_t *digest, const uint8_t *target_le) {
  for (int i = 31; i >= 0; i--) {
    if (digest[i] != target_le[i]) return digest[i] < target_le[i];
  }
  return 1;
}

typedef struct {
  uint32_t mid[8];
  uint32_t w0, w1, w2;
} ATemplate;

static void a_template_init(ATemplate *tp, const uint8_t *header) {
  a_compress_scalar(A_H0, header, tp->mid);
  tp->w0 = ((uint32_t)header[64] << 24) | ((uint32_t)header[65] << 16) |
           ((uint32_t)header[66] << 8) | header[67];
  tp->w1 = ((uint32_t)header[68] << 24) | ((uint32_t)header[69] << 16) |
           ((uint32_t)header[70] << 8) | header[71];
  tp->w2 = ((uint32_t)header[72] << 24) | ((uint32_t)header[73] << 16) |
           ((uint32_t)header[74] << 8) | header[75];
}

/* One group of 8 lanes: nonces first_nonce + lane. Writes
 * digests for the first `valid` lanes into dig[][32]. */
static void a_group(const ATemplate *tp, uint32_t first_nonce,
                    int valid, uint8_t dig[][32]) {
  __m256i laneidx = _mm256_set_epi32(7, 6, 5, 4, 3, 2, 1, 0);
  __m256i nonces = _mm256_add_epi32(
    _mm256_set1_epi32((int)first_nonce), laneidx);
  /* Byte-swap each lane's nonce: it is schedule word W3.
   * VPSHUFB works within 128-bit halves; each 32-bit lane
   * lies entirely inside one half, so reversing the bytes
   * of every 4-byte word in each half is exact. */
  const __m256i swmask = _mm256_set_epi8(
    12, 13, 14, 15, 8, 9, 10, 11, 4, 5, 6, 7, 0, 1, 2, 3,
    12, 13, 14, 15, 8, 9, 10, 11, 4, 5, 6, 7, 0, 1, 2, 3);
  __m256i w3 = _mm256_shuffle_epi8(nonces, swmask);
  __m256i W0[16];
  W0[0] = _mm256_set1_epi32((int)tp->w0);
  W0[1] = _mm256_set1_epi32((int)tp->w1);
  W0[2] = _mm256_set1_epi32((int)tp->w2);
  W0[3] = w3;
  W0[4] = _mm256_set1_epi32((int)0x80000000);
  for (int i = 5; i < 15; i++) W0[i] = _mm256_setzero_si256();
  W0[15] = _mm256_set1_epi32(640);
  __m256i S[8];
  for (int j = 0; j < 8; j++)
    S[j] = _mm256_set1_epi32((int)tp->mid[j]);
  a_compress8(S, W0);
  uint32_t inn[8][8];
  for (int j = 0; j < 8; j++) {
    S[j] = _mm256_add_epi32(
      S[j], _mm256_set1_epi32((int)tp->mid[j]));
    _mm256_storeu_si256((void *)inn[j], S[j]);
  }
  __m256i W1[16];
  for (int j = 0; j < 8; j++)
    W1[j] = _mm256_loadu_si256((const void *)inn[j]);
  W1[8] = _mm256_set1_epi32((int)0x80000000);
  for (int i = 9; i < 15; i++) W1[i] = _mm256_setzero_si256();
  W1[15] = _mm256_set1_epi32(256);
  __m256i SO[8];
  for (int j = 0; j < 8; j++)
    SO[j] = _mm256_set1_epi32((int)A_H0[j]);
  a_compress8(SO, W1);
  uint32_t dg[8][8];
  for (int j = 0; j < 8; j++) {
    SO[j] = _mm256_add_epi32(
      SO[j], _mm256_set1_epi32((int)A_H0[j]));
    _mm256_storeu_si256((void *)dg[j], SO[j]);
  }
  for (int l = 0; l < valid; l++) {
    for (int j = 0; j < 8; j++) {
      uint32_t v = dg[j][l];
      dig[l][4 * j] = (uint8_t)(v >> 24);
      dig[l][4 * j + 1] = (uint8_t)(v >> 16);
      dig[l][4 * j + 2] = (uint8_t)(v >> 8);
      dig[l][4 * j + 3] = (uint8_t)v;
    }
  }
}

/* ---- span walkers (mirroring bal_avx512_mb.c) ---- */

typedef struct {
  const ATemplate *tp;
  uint64_t start;
  uint64_t span;
  const uint8_t *target;
  BalSearchCtx *ctx;
  uint8_t *hashes;
  uint8_t *flags;
  uint64_t attempted;
  uint64_t backend;
} AJob;

static void a_walk(AJob *job) {
  uint64_t off = 0;
  while (off < job->span) {
    if (job->ctx && bal_ctx_stopped(job->ctx)) break;
    uint64_t rem = job->span - off;
    int valid = rem >= 8 ? 8 : (int)rem;
    uint8_t dig[8][32];
    a_group(job->tp, (uint32_t)(job->start + off), valid, dig);
    job->backend += 8;
    job->attempted += (uint64_t)valid;
    for (int l = 0; l < valid; l++) {
      if (job->ctx) {
        if (a_meets(dig[l], job->target))
          bal_ctx_publish(job->ctx,
                          (uint32_t)(job->start + off + (uint64_t)l),
                          dig[l]);
      } else {
        memcpy(job->hashes + 32 * (size_t)(off + (uint64_t)l),
               dig[l], 32);
        job->flags[off + (uint64_t)l] =
          a_meets(dig[l], job->target) ? 1 : 0;
      }
    }
    off += (uint64_t)valid;
  }
}

typedef struct {
  AJob v;
  uint64_t begin, end;
} AThreadJob;

static void *a_worker(void *arg) {
  AThreadJob *job = (AThreadJob *)arg;
  AJob v = job->v;
  v.start += job->begin;
  v.span = job->end - job->begin;
  if (v.hashes) v.hashes = job->v.hashes + 32 * (size_t)job->begin;
  if (v.flags) v.flags = job->v.flags + job->begin;
  v.attempted = 0;
  v.backend = 0;
  a_walk(&v);
  job->v.attempted = v.attempted;
  job->v.backend = v.backend;
  return NULL;
}

static int a_run(const uint8_t *header, uint64_t start, uint64_t count,
                 unsigned threads, const uint8_t *target,
                 BalSearchCtx *ctx, uint8_t *hashes, uint8_t *flags,
                 uint64_t *out_attempted, uint64_t *out_backend) {
  ATemplate tp;
  a_template_init(&tp, header);
  uint64_t begins[16], ends[16];
  unsigned spans = bal_partition(count, threads, begins, ends);
  pthread_t tids[16];
  int created[16] = {0};
  AThreadJob jobs[16];
  for (unsigned sp = 0; sp < spans; sp++) {
    jobs[sp].v = (AJob){&tp, start, 0, target, ctx, hashes, flags,
                        0, 0};
    jobs[sp].begin = begins[sp];
    jobs[sp].end = ends[sp];
    if (bal_pthread_create(&tids[sp], NULL, a_worker, &jobs[sp]) != 0) {
      a_worker(&jobs[sp]);
    } else {
      created[sp] = 1;
    }
  }
  for (unsigned sp = 0; sp < spans; sp++)
    if (created[sp]) pthread_join(tids[sp], NULL);
  if (out_attempted) {
    uint64_t total = 0;
    for (unsigned sp = 0; sp < spans; sp++) total += jobs[sp].v.attempted;
    *out_attempted = total;
  }
  if (out_backend) {
    uint64_t total = 0;
    for (unsigned sp = 0; sp < spans; sp++) total += jobs[sp].v.backend;
    *out_backend = total;
  }
  return 0;
}

int bal_a_batch2(const uint8_t *header, uint64_t start, uint64_t count,
                 unsigned threads, const uint8_t *target,
                 uint8_t *hashes, uint8_t *flags,
                 uint64_t *out_attempted, uint64_t *out_backend) {
  if (!header || !target || !hashes || !flags) return -1;
  if (!threads || threads > 16) return -1;
  int v = bal_validate_range(start, count);
  if (v != 0) return v;
  return a_run(header, start, count, threads, target, NULL, hashes,
               flags, out_attempted, out_backend);
}

int bal_a_search2(const uint8_t *header, uint64_t start, uint64_t count,
                  unsigned threads, const uint8_t *target,
                  uint32_t *out_nonce, uint8_t *out_digest,
                  uint64_t *out_attempted, uint64_t *out_backend) {
  if (!header || !target || !out_nonce || !out_digest) return -1;
  if (!threads || threads > 16) return -1;
  int v = bal_validate_range(start, count);
  if (v != 0) return v;
  BalSearchCtx ctx;
  if (bal_ctx_init(&ctx) != 0) return -4;
  int rc = a_run(header, start, count, threads, target, &ctx, NULL,
                 NULL, out_attempted, out_backend);
  if (rc != 0) {
    bal_ctx_destroy(&ctx);
    return rc;
  }
  if (bal_ctx_publish_failed(&ctx)) {
    bal_ctx_destroy(&ctx);
    return -3;
  }
  int found = ctx.found_valid;
  if (found) {
    *out_nonce = ctx.found_nonce;
    memcpy(out_digest, ctx.found_digest, 32);
  }
  bal_ctx_destroy(&ctx);
  return found ? 1 : 0;
}
