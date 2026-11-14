/* NOVA SHA-X EXP-012: explicit VPTERNLOGD Boolean cone in the AVX-512 multi-buffer.
 * software SHA-256d.
 *
 * Sixteen independent SHA-256d computations advance in
 * lockstep, one per 32-bit lane of a zmm register. The state
 * is transposed: eight __m512i vectors, vector j holding
 * word j of all sixteen hashes. The message schedule is
 * computed per lane with vector ops (vprold rotations for
 * the sigma functions), so each vector round step performs
 * the round work of sixteen hashes at once, at the cost of
 * roughly ten vector ops per sigma-heavy round.
 *
 * Mining shape: one template per call. Block 1 is identical
 * across lanes, so the midstate is computed once, scalar,
 * and broadcast. Block 2 differs only in the nonce word:
 * lane l takes nonce start+base+l. The outer block's first
 * eight words are exactly the inner state vectors, so no
 * transpose is needed between phases; only the final digest
 * store transposes out through a [8][16] staging array.
 *
 * Accounting (Task 003.9 definitions): out_attempted counts
 * real nonces completed (== count for batch). out_backend
 * counts actual lane computations, including dummy lanes in
 * a partial final group: backend == ceil(count/16)*16 per
 * span summed over spans. Dummy lanes repeat the last real
 * nonce; their outputs are never stored and never counted
 * as coverage. Search is group-atomic: when a lane hits,
 * attempted counts every real nonce in that group (all were
 * really computed), mirroring the H-01 wave semantics.
 *
 * Exports:
 *   bal_t_batch2(header, start, count, threads, target,
 *                hashes, flags, out_attempted, out_backend)
 *   bal_t_search2(header, start, count, threads, target,
 *                 out_nonce, out_digest, out_attempted,
 *                 out_backend)
 * Return codes follow the counted ABI (-1 bad args or empty,
 * -2 range crossing 2^32, 0 ok / miss, 1 found).
 */
#include <stdint.h>
#include <string.h>
#include <stdatomic.h>
#include <pthread.h>
#include <immintrin.h>

#include "../../../../mining/cpu/bal_search.h"

/* Failure-injection hooks declared by bal_search.h; the
 * definitions live in each library that uses the header. */
_Atomic int bal_create_fail_after = -1;
_Atomic int bal_create_fail_calls = 0;
_Atomic int bal_mutex_fail_mask = 0;

static const uint32_t V_K[64] = {
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

static const uint32_t V_H0[8] = {0x6a09e667,0xbb67ae85,0x3c6ef372,
  0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19};

/* ---- scalar one-block compression (midstate only) ---- */
static uint32_t vrotr(uint32_t x, int n) {
  return (x >> n) | (x << (32 - n));
}

static void v_compress_scalar(const uint32_t in[8],
                              const uint8_t *block,
                              uint32_t out[8]) {
  uint32_t W[64];
  for (int i = 0; i < 16; i++)
    W[i] = ((uint32_t)block[4 * i] << 24) |
           ((uint32_t)block[4 * i + 1] << 16) |
           ((uint32_t)block[4 * i + 2] << 8) | block[4 * i + 3];
  for (int i = 16; i < 64; i++) {
    uint32_t s0 = vrotr(W[i - 15], 7) ^ vrotr(W[i - 15], 18) ^
                  (W[i - 15] >> 3);
    uint32_t s1 = vrotr(W[i - 2], 17) ^ vrotr(W[i - 2], 19) ^
                  (W[i - 2] >> 10);
    W[i] = W[i - 16] + s0 + W[i - 7] + s1;
  }
  uint32_t s[8];
  memcpy(s, in, 32);
  for (int t = 0; t < 64; t++) {
    uint32_t S1 = vrotr(s[4], 6) ^ vrotr(s[4], 11) ^ vrotr(s[4], 25);
    uint32_t ch = (s[4] & s[5]) ^ (~s[4] & s[6]);
    uint32_t T1 = s[7] + S1 + ch + V_K[t] + W[t];
    uint32_t S0 = vrotr(s[0], 2) ^ vrotr(s[0], 13) ^ vrotr(s[0], 22);
    uint32_t mj = (s[0] & s[1]) ^ (s[0] & s[2]) ^ (s[1] & s[2]);
    uint32_t T2 = S0 + mj;
    s[7] = s[6]; s[6] = s[5]; s[5] = s[4]; s[4] = s[3] + T1;
    s[3] = s[2]; s[2] = s[1]; s[1] = s[0]; s[0] = T1 + T2;
  }
  for (int i = 0; i < 8; i++) out[i] = in[i] + s[i];
}

/* ---- vector compression over 16 lanes ----
 * W0[16] are the block's first 16 schedule words as lane
 * vectors; S holds the input state as lane vectors; the
 * feed-forward is the caller's job. */
static inline __m512i vr32(__m512i x, int n) {
  return _mm512_ror_epi32(x, n);
}

static void v_compress16(__m512i S[8], const __m512i W0[16]) {
  __m512i W[16];
  for (int i = 0; i < 16; i++) W[i] = W0[i];
  __m512i a = S[0], b = S[1], c = S[2], d = S[3],
          e = S[4], f = S[5], g = S[6], h = S[7];
  for (int t = 0; t < 64; t++) {
    __m512i w;
    if (t < 16) {
      w = W[t];
    } else {
      __m512i x = W[(t - 15) & 15];
      __m512i y = W[(t - 2) & 15];
      __m512i s0 = _mm512_ternarylogic_epi32(
        vr32(x, 7), vr32(x, 18), _mm512_srli_epi32(x, 3), 0x96);
      __m512i s1 = _mm512_ternarylogic_epi32(
        vr32(y, 17), vr32(y, 19), _mm512_srli_epi32(y, 10), 0x96);
      w = _mm512_add_epi32(
        _mm512_add_epi32(W[(t - 16) & 15], s0),
        _mm512_add_epi32(W[(t - 7) & 15], s1));
      W[t & 15] = w;
    }
    __m512i S1 = _mm512_ternarylogic_epi32(
      vr32(e, 6), vr32(e, 11), vr32(e, 25), 0x96);
    __m512i ch = _mm512_ternarylogic_epi32(e, f, g, 0xCA);
    __m512i T1 = _mm512_add_epi32(
      _mm512_add_epi32(
        _mm512_add_epi32(h, S1),
        _mm512_add_epi32(ch, _mm512_set1_epi32((int)V_K[t]))), w);
    __m512i S0 = _mm512_ternarylogic_epi32(
      vr32(a, 2), vr32(a, 13), vr32(a, 22), 0x96);
    __m512i mj = _mm512_ternarylogic_epi32(a, b, c, 0xE8);
    __m512i T2 = _mm512_add_epi32(S0, mj);
    h = g; g = f; f = e;
    e = _mm512_add_epi32(d, T1);
    d = c; c = b; b = a;
    a = _mm512_add_epi32(T1, T2);
  }
  S[0] = a; S[1] = b; S[2] = c; S[3] = d;
  S[4] = e; S[5] = f; S[6] = g; S[7] = h;
}

static int v_meets(const uint8_t *digest, const uint8_t *target_le) {
  for (int i = 31; i >= 0; i--) {
    if (digest[i] != target_le[i]) return digest[i] < target_le[i];
  }
  return 1;
}

typedef struct {
  uint32_t mid[8];
  uint32_t w0, w1, w2;
} VTemplate;

static void v_template_init(VTemplate *tp, const uint8_t *header) {
  v_compress_scalar(V_H0, header, tp->mid);
  tp->w0 = ((uint32_t)header[64] << 24) | ((uint32_t)header[65] << 16) |
           ((uint32_t)header[66] << 8) | header[67];
  tp->w1 = ((uint32_t)header[68] << 24) | ((uint32_t)header[69] << 16) |
           ((uint32_t)header[70] << 8) | header[71];
  tp->w2 = ((uint32_t)header[72] << 24) | ((uint32_t)header[73] << 16) |
           ((uint32_t)header[74] << 8) | header[75];
}

static inline uint32_t v_bswap32(uint32_t x) {
  return ((x & 0xff) << 24) | ((x & 0xff00) << 8) |
         ((x >> 8) & 0xff00) | ((x >> 24) & 0xff);
}

/* One group of 16 lanes: nonces first_nonce + lane. Writes
 * digests for the first `valid` lanes into dig[][32]. */
static void v_group(const VTemplate *tp, uint32_t first_nonce,
                    int valid, uint8_t dig[][32]) {
  __m512i laneidx = _mm512_set_epi32(15, 14, 13, 12, 11, 10, 9, 8,
                                     7, 6, 5, 4, 3, 2, 1, 0);
  __m512i nonces = _mm512_add_epi32(
    _mm512_set1_epi32((int)first_nonce), laneidx);
  /* byte-swap each lane's nonce: it is schedule word W3 */
  const __m512i swmask = _mm512_set_epi8(
    60, 61, 62, 63, 56, 57, 58, 59, 52, 53, 54, 55,
    48, 49, 50, 51, 44, 45, 46, 47, 40, 41, 42, 43,
    36, 37, 38, 39, 32, 33, 34, 35, 28, 29, 30, 31,
    24, 25, 26, 27, 20, 21, 22, 23, 16, 17, 18, 19,
    12, 13, 14, 15, 8, 9, 10, 11, 4, 5, 6, 7, 0, 1, 2, 3);
  __m512i w3 = _mm512_shuffle_epi8(nonces, swmask);
  __m512i W0[16];
  W0[0] = _mm512_set1_epi32((int)tp->w0);
  W0[1] = _mm512_set1_epi32((int)tp->w1);
  W0[2] = _mm512_set1_epi32((int)tp->w2);
  W0[3] = w3;
  W0[4] = _mm512_set1_epi32((int)0x80000000);
  for (int i = 5; i < 15; i++) W0[i] = _mm512_setzero_si512();
  W0[15] = _mm512_set1_epi32(640);
  __m512i S[8];
  for (int j = 0; j < 8; j++)
    S[j] = _mm512_set1_epi32((int)tp->mid[j]);
  v_compress16(S, W0);
  uint32_t inn[8][16];
  for (int j = 0; j < 8; j++) {
    S[j] = _mm512_add_epi32(
      S[j], _mm512_set1_epi32((int)tp->mid[j]));
    _mm512_storeu_si512((void *)inn[j], S[j]);
  }
  __m512i W1[16];
  for (int j = 0; j < 8; j++)
    W1[j] = _mm512_loadu_si512((const void *)inn[j]);
  W1[8] = _mm512_set1_epi32((int)0x80000000);
  for (int i = 9; i < 15; i++) W1[i] = _mm512_setzero_si512();
  W1[15] = _mm512_set1_epi32(256);
  __m512i SO[8];
  for (int j = 0; j < 8; j++)
    SO[j] = _mm512_set1_epi32((int)V_H0[j]);
  v_compress16(SO, W1);
  uint32_t dg[8][16];
  for (int j = 0; j < 8; j++) {
    SO[j] = _mm512_add_epi32(
      SO[j], _mm512_set1_epi32((int)V_H0[j]));
    _mm512_storeu_si512((void *)dg[j], SO[j]);
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

/* ---- span walkers ---- */

typedef struct {
  const VTemplate *tp;
  uint64_t start;
  uint64_t span;
  const uint8_t *target;
  BalSearchCtx *ctx;
  uint8_t *hashes;
  uint8_t *flags;
  uint64_t attempted;
  uint64_t backend;
} VJob;

static void v_walk(VJob *job) {
  uint64_t off = 0;
  while (off < job->span) {
    if (job->ctx && bal_ctx_stopped(job->ctx)) break;
    uint64_t rem = job->span - off;
    int valid = rem >= 16 ? 16 : (int)rem;
    uint8_t dig[16][32];
    v_group(job->tp, (uint32_t)(job->start + off), valid, dig);
    job->backend += 16;
    job->attempted += (uint64_t)valid;
    for (int l = 0; l < valid; l++) {
      if (job->ctx) {
        if (v_meets(dig[l], job->target))
          bal_ctx_publish(job->ctx,
                          (uint32_t)(job->start + off + (uint64_t)l),
                          dig[l]);
      } else {
        memcpy(job->hashes + 32 * (size_t)(off + (uint64_t)l),
               dig[l], 32);
        job->flags[off + (uint64_t)l] =
          v_meets(dig[l], job->target) ? 1 : 0;
      }
    }
    off += (uint64_t)valid;
  }
}

typedef struct {
  VJob v;
  uint64_t begin, end;
} VThreadJob;

static void *v_worker(void *arg) {
  VThreadJob *job = (VThreadJob *)arg;
  VJob v = job->v;
  v.start += job->begin;
  v.span = job->end - job->begin;
  if (v.hashes) v.hashes = job->v.hashes + 32 * (size_t)job->begin;
  if (v.flags) v.flags = job->v.flags + job->begin;
  v.attempted = 0;
  v.backend = 0;
  v_walk(&v);
  job->v.attempted = v.attempted;
  job->v.backend = v.backend;
  return NULL;
}

static int v_run(const uint8_t *header, uint64_t start, uint64_t count,
                 unsigned threads, const uint8_t *target,
                 BalSearchCtx *ctx, uint8_t *hashes, uint8_t *flags,
                 uint64_t *out_attempted, uint64_t *out_backend) {
  VTemplate tp;
  v_template_init(&tp, header);
  uint64_t begins[16], ends[16];
  unsigned spans = bal_partition(count, threads, begins, ends);
  pthread_t tids[16];
  int created[16] = {0};
  VThreadJob jobs[16];
  for (unsigned sp = 0; sp < spans; sp++) {
    jobs[sp].v = (VJob){&tp, start, 0, target, ctx, hashes, flags,
                        0, 0};
    jobs[sp].begin = begins[sp];
    jobs[sp].end = ends[sp];
    if (bal_pthread_create(&tids[sp], NULL, v_worker, &jobs[sp]) != 0) {
      v_worker(&jobs[sp]);
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

int bal_t_batch2(const uint8_t *header, uint64_t start, uint64_t count,
                 unsigned threads, const uint8_t *target,
                 uint8_t *hashes, uint8_t *flags,
                 uint64_t *out_attempted, uint64_t *out_backend) {
  if (!header || !target || !hashes || !flags) return -1;
  if (!threads || threads > 16) return -1;
  int v = bal_validate_range(start, count);
  if (v != 0) return v;
  return v_run(header, start, count, threads, target, NULL, hashes,
               flags, out_attempted, out_backend);
}

int bal_t_search2(const uint8_t *header, uint64_t start, uint64_t count,
                  unsigned threads, const uint8_t *target,
                  uint32_t *out_nonce, uint8_t *out_digest,
                  uint64_t *out_attempted, uint64_t *out_backend) {
  if (!header || !target || !out_nonce || !out_digest) return -1;
  if (!threads || threads > 16) return -1;
  int v = bal_validate_range(start, count);
  if (v != 0) return v;
  BalSearchCtx ctx;
  if (bal_ctx_init(&ctx) != 0) return -4;
  int rc = v_run(header, start, count, threads, target, &ctx, NULL,
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
