/* NOVA SHA-X EXP-015: bitsliced 32-lane SHA-256d.
 *
 * Extends X-029 (bitslicing, previously an analytic bound
 * only) with an actual implementation. Thirty-two hashes
 * advance together, transposed the other way from the
 * multi-buffer kernels: each 32-bit word is stored as 32
 * uint32_t planes, plane i holding bit i of that word for
 * all 32 lanes. Boolean functions become one scalar op
 * per plane; rotations become plane reindexing (free at
 * the index level); shifts become reindexing with zero
 * fill; addition becomes a 32-step ripple-carry over
 * planes, which is the known cost centre.
 *
 * Mining shape mirrors avx512_mb.c: block 1 is identical
 * across lanes, so the midstate is computed once, scalar,
 * and broadcast into planes. Block 2 differs only in the
 * nonce word planes. The outer block consumes the inner
 * state planes directly.
 *
 * Accounting (Task 003.9 definitions): out_attempted
 * counts real nonces completed; out_backend counts actual
 * lane computations, padded to whole 32-lane groups.
 * Groups are atomic for search: when a lane hits,
 * attempted counts every real nonce in that group.
 *
 * Exports follow the counted ABI of avx512_mb.c:
 *   bal_z_batch2 / bal_z_search2
 */
#include <stdint.h>
#include <string.h>
#include <stdatomic.h>
#include <pthread.h>

#include "../../../../mining/cpu/bal_search.h"

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

/* ---- bitsliced core ---- */
typedef uint32_t bs_word[32];

static void bs_broadcast(bs_word r, uint32_t v) {
  for (int i = 0; i < 32; i++)
    r[i] = ((v >> i) & 1) ? 0xFFFFFFFFu : 0;
}

static void bs_copy(bs_word r, const bs_word a) {
  memcpy(r, a, sizeof(bs_word));
}

static void bs_add(bs_word r, const bs_word a, const bs_word b) {
  uint32_t carry = 0;
  for (int i = 0; i < 32; i++) {
    uint32_t ai = a[i], bi = b[i];
    uint32_t x = ai ^ bi;
    r[i] = x ^ carry;
    carry = (ai & bi) | (carry & x);
  }
}

static void bs_add_const(bs_word r, const bs_word a, uint32_t c) {
  uint32_t carry = 0;
  for (int i = 0; i < 32; i++) {
    uint32_t ai = a[i];
    if ((c >> i) & 1) {
      r[i] = ~(ai ^ carry);
      carry = ai | carry;
    } else {
      r[i] = ai ^ carry;
      carry = ai & carry;
    }
  }
}

static void bs_BS0(bs_word r, const bs_word x) {
  for (int i = 0; i < 32; i++)
    r[i] = x[(i + 2) & 31] ^ x[(i + 13) & 31] ^ x[(i + 22) & 31];
}

static void bs_BS1(bs_word r, const bs_word x) {
  for (int i = 0; i < 32; i++)
    r[i] = x[(i + 6) & 31] ^ x[(i + 11) & 31] ^ x[(i + 25) & 31];
}

static void bs_ss0(bs_word r, const bs_word x) {
  for (int i = 0; i < 32; i++)
    r[i] = x[(i + 7) & 31] ^ x[(i + 18) & 31] ^
           (i + 3 < 32 ? x[i + 3] : 0);
}

static void bs_ss1(bs_word r, const bs_word x) {
  for (int i = 0; i < 32; i++)
    r[i] = x[(i + 17) & 31] ^ x[(i + 19) & 31] ^
           (i + 10 < 32 ? x[i + 10] : 0);
}

static void bs_ch(bs_word r, const bs_word e, const bs_word f,
                  const bs_word g) {
  for (int i = 0; i < 32; i++)
    r[i] = (e[i] & f[i]) ^ (~e[i] & g[i]);
}

static void bs_maj(bs_word r, const bs_word a, const bs_word b,
                   const bs_word c) {
  for (int i = 0; i < 32; i++)
    r[i] = (a[i] & b[i]) ^ (a[i] & c[i]) ^ (b[i] & c[i]);
}

static void bs_compress(bs_word S[8], const bs_word W0[16]) {
  bs_word W[64];
  bs_word t1, t2, u1, u2;
  for (int i = 0; i < 16; i++) bs_copy(W[i], W0[i]);
  for (int t = 16; t < 64; t++) {
    bs_ss0(t1, W[t - 15]);
    bs_ss1(t2, W[t - 2]);
    bs_add(W[t], W[t - 16], t1);
    bs_add(W[t], W[t], W[t - 7]);
    bs_add(W[t], W[t], t2);
  }
  int o = 0;
  for (int t = 0; t < 64; t++) {
    int ia = o, ib = (o + 1) & 7, ic = (o + 2) & 7,
        id = (o + 3) & 7, ie = (o + 4) & 7, jf = (o + 5) & 7,
        jg = (o + 6) & 7, ih = (o + 7) & 7;
    bs_BS1(u1, S[ie]);
    bs_ch(u2, S[ie], S[jf], S[jg]);
    bs_add(t1, S[ih], u1);
    bs_add(t1, t1, u2);
    bs_add_const(t1, t1, V_K[t]);
    bs_add(t1, t1, W[t]);
    bs_BS0(u1, S[ia]);
    bs_maj(u2, S[ia], S[ib], S[ic]);
    bs_add(t2, u1, u2);
    bs_add(S[id], S[id], t1);
    bs_add(S[ih], t1, t2);
    o = (o + 7) & 7;
  }
}

/* ---- template and group ---- */
typedef struct {
  uint32_t mid[8];
  uint32_t w0, w1, w2;
} BsTemplate;

static void bs_template_init(BsTemplate *tp, const uint8_t *header) {
  v_compress_scalar(V_H0, header, tp->mid);
  tp->w0 = ((uint32_t)header[64] << 24) | ((uint32_t)header[65] << 16) |
           ((uint32_t)header[66] << 8) | header[67];
  tp->w1 = ((uint32_t)header[68] << 24) | ((uint32_t)header[69] << 16) |
           ((uint32_t)header[70] << 8) | header[71];
  tp->w2 = ((uint32_t)header[72] << 24) | ((uint32_t)header[73] << 16) |
           ((uint32_t)header[74] << 8) | header[75];
}

static inline uint32_t bs_bswap32(uint32_t x) {
  return ((x & 0xff) << 24) | ((x & 0xff00) << 8) |
         ((x >> 8) & 0xff00) | ((x >> 24) & 0xff);
}

static void bs_group(const BsTemplate *tp, uint32_t first_nonce,
                     int valid, uint8_t dig[][32]) {
  bs_word W0[16];
  bs_broadcast(W0[0], tp->w0);
  bs_broadcast(W0[1], tp->w1);
  bs_broadcast(W0[2], tp->w2);
  for (int i = 0; i < 32; i++) W0[3][i] = 0;
  for (int l = 0; l < 32; l++) {
    uint32_t word = bs_bswap32(first_nonce + (uint32_t)l);
    for (int i = 0; i < 32; i++)
      W0[3][i] |= ((word >> i) & 1) << l;
  }
  bs_broadcast(W0[4], 0x80000000u);
  for (int i = 5; i < 15; i++)
    for (int b = 0; b < 32; b++) W0[i][b] = 0;
  bs_broadcast(W0[15], 640);
  bs_word S[8];
  for (int j = 0; j < 8; j++) bs_broadcast(S[j], tp->mid[j]);
  bs_compress(S, (const bs_word *)W0);
  bs_word init;
  for (int j = 0; j < 8; j++) {
    bs_broadcast(init, tp->mid[j]);
    bs_add(S[j], S[j], init);
  }
  bs_word W1[16];
  for (int j = 0; j < 8; j++) bs_copy(W1[j], S[j]);
  bs_broadcast(W1[8], 0x80000000u);
  for (int i = 9; i < 15; i++)
    for (int b = 0; b < 32; b++) W1[i][b] = 0;
  bs_broadcast(W1[15], 256);
  bs_word SO[8];
  for (int j = 0; j < 8; j++) bs_broadcast(SO[j], V_H0[j]);
  bs_compress(SO, (const bs_word *)W1);
  for (int j = 0; j < 8; j++) {
    bs_broadcast(init, V_H0[j]);
    bs_add(SO[j], SO[j], init);
  }
  for (int l = 0; l < valid; l++) {
    for (int j = 0; j < 8; j++) {
      uint32_t v = 0;
      for (int i = 0; i < 32; i++)
        v |= ((SO[j][i] >> l) & 1) << i;
      dig[l][4 * j] = (uint8_t)(v >> 24);
      dig[l][4 * j + 1] = (uint8_t)(v >> 16);
      dig[l][4 * j + 2] = (uint8_t)(v >> 8);
      dig[l][4 * j + 3] = (uint8_t)v;
    }
  }
}

static int bs_meets(const uint8_t *digest, const uint8_t *target_le) {
  for (int i = 31; i >= 0; i--) {
    if (digest[i] != target_le[i]) return digest[i] < target_le[i];
  }
  return 1;
}

/* ---- span walkers ---- */
typedef struct {
  const BsTemplate *tp;
  uint64_t start;
  uint64_t span;
  const uint8_t *target;
  BalSearchCtx *ctx;
  uint8_t *hashes;
  uint8_t *flags;
  uint64_t attempted;
  uint64_t backend;
} BsJob;

static void bs_walk(BsJob *job) {
  uint64_t off = 0;
  while (off < job->span) {
    if (job->ctx && bal_ctx_stopped(job->ctx)) break;
    uint64_t rem = job->span - off;
    int valid = rem >= 32 ? 32 : (int)rem;
    uint8_t dig[32][32];
    bs_group(job->tp, (uint32_t)(job->start + off), valid, dig);
    job->backend += 32;
    job->attempted += (uint64_t)valid;
    for (int l = 0; l < valid; l++) {
      if (job->ctx) {
        if (bs_meets(dig[l], job->target))
          bal_ctx_publish(job->ctx,
                          (uint32_t)(job->start + off + (uint64_t)l),
                          dig[l]);
      } else {
        memcpy(job->hashes + 32 * (size_t)(off + (uint64_t)l),
               dig[l], 32);
        job->flags[off + (uint64_t)l] =
          bs_meets(dig[l], job->target) ? 1 : 0;
      }
    }
    off += (uint64_t)valid;
  }
}

typedef struct {
  BsJob v;
  uint64_t begin, end;
} BsThreadJob;

static void *bs_worker(void *arg) {
  BsThreadJob *job = (BsThreadJob *)arg;
  BsJob v = job->v;
  v.start += job->begin;
  v.span = job->end - job->begin;
  if (v.hashes) v.hashes = job->v.hashes + 32 * (size_t)job->begin;
  if (v.flags) v.flags = job->v.flags + job->begin;
  v.attempted = 0;
  v.backend = 0;
  bs_walk(&v);
  job->v.attempted = v.attempted;
  job->v.backend = v.backend;
  return NULL;
}

static int bs_run(const uint8_t *header, uint64_t start, uint64_t count,
                  unsigned threads, const uint8_t *target,
                  BalSearchCtx *ctx, uint8_t *hashes, uint8_t *flags,
                  uint64_t *out_attempted, uint64_t *out_backend) {
  BsTemplate tp;
  bs_template_init(&tp, header);
  uint64_t begins[16], ends[16];
  unsigned spans = bal_partition(count, threads, begins, ends);
  pthread_t tids[16];
  int created[16] = {0};
  BsThreadJob jobs[16];
  for (unsigned sp = 0; sp < spans; sp++) {
    jobs[sp].v = (BsJob){&tp, start, 0, target, ctx, hashes, flags,
                         0, 0};
    jobs[sp].begin = begins[sp];
    jobs[sp].end = ends[sp];
    if (bal_pthread_create(&tids[sp], NULL, bs_worker, &jobs[sp]) != 0) {
      bs_worker(&jobs[sp]);
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

int bal_z_batch2(const uint8_t *header, uint64_t start, uint64_t count,
                 unsigned threads, const uint8_t *target,
                 uint8_t *hashes, uint8_t *flags,
                 uint64_t *out_attempted, uint64_t *out_backend) {
  if (!header || !target || !hashes || !flags) return -1;
  if (!threads || threads > 16) return -1;
  int v = bal_validate_range(start, count);
  if (v != 0) return v;
  return bs_run(header, start, count, threads, target, NULL, hashes,
                flags, out_attempted, out_backend);
}

int bal_z_search2(const uint8_t *header, uint64_t start, uint64_t count,
                  unsigned threads, const uint8_t *target,
                  uint32_t *out_nonce, uint8_t *out_digest,
                  uint64_t *out_attempted, uint64_t *out_backend) {
  if (!header || !target || !out_nonce || !out_digest) return -1;
  if (!threads || threads > 16) return -1;
  int v = bal_validate_range(start, count);
  if (v != 0) return v;
  BalSearchCtx ctx;
  if (bal_ctx_init(&ctx) != 0) return -4;
  int rc = bs_run(header, start, count, threads, target, &ctx, NULL,
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
