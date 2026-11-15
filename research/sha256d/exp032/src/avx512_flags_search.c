/* EXP-032 RESEARCH COPY (Phase D, 2026-11-15): this file
 * is a byte copy of the production translation unit
 * mining/cpu/bal_avx512_flags.c (sha256 of the production
 * source recorded in ../EXP032_REPORT.md) with ONE
 * addition at the end of the file: bal_v_searchf2, an
 * early-exit SEARCH entry built on the same vf_group
 * opmask-compare machinery, written to answer the EXP-032
 * question whether the EXP-022 flags approach can improve
 * the real production search path and not merely the
 * batch API. The production file is untouched. Everything
 * below this header, down to the EXP-032 addition marker,
 * is the production comment and code unchanged.
 *
 * NOVA SHA-X EXP-022 (Y-084): flags-only AVX-512
 * multi-buffer batch. PRODUCTION COPY (integrated
 * 2026-11-15 under the owner's explicit decision,
 * option B, after EXP-022 returned a VERIFIED
 * IMPROVEMENT in batch scope under the EXP-017 rule
 * and EXP-024 reproduced it): this file is the
 * production translation unit built by
 * mining/cpu/build.py into .local/cpu/libbal_v512flags.so.
 *
 * Provenance and divergence from the research original
 * at research/sha256d/extreme_optimization/src/
 * avx512_mb_flags.c, recorded in full:
 * - The header comment (this comment) and the
 *   bal_search.h include path differ.
 * - The export name bal_v_batchf2 is carried over
 *   unchanged.
 * - The research file's bal_v_batch2 and bal_v_search2
 *   sections (the digest-materialising batch and the
 *   search) are NOT copied: they stay in
 *   mining/cpu/bal_avx512_mb.c, untouched, as the
 *   preserved fallback. The scalar v_meets helper and
 *   the digest-writing v_group are likewise omitted;
 *   nothing in the flags path calls them.
 * - Every retained section (failure hooks, constant
 *   tables, the scalar midstate compression, the
 *   vector compression, the template init, and the
 *   whole vf_* flags path through bal_v_batchf2) is
 *   byte-identical to the research original.
 *
 * Mechanism (EXP-022): the target comparison is
 * computed in vector form over the transposed final
 * state, the per-group result is a single __mmask16
 * (one mask bit per hash, accumulated into a flag-bit
 * array), and digests are extracted only for flagged
 * lanes. With digests == NULL no digest is
 * materialised at all. The batch consumer therefore
 * reads one bit per hash instead of 32 digest bytes
 * plus a flag byte, and the kernel skips the full
 * transpose store, the per-lane scalar byte
 * extraction, the 32-byte per-hash output copy and
 * the scalar per-lane comparison for every unflagged
 * lane.
 *
 * The vector comparison reproduces the production
 * v_meets semantics exactly: v_meets scans digest
 * bytes from index 31 down to 0, so byte 31 is the
 * most significant. Grouping those bytes into words,
 * the comparison is a lexicographic unsigned compare
 * of the eight words bswap32(state[7-j]) against
 * bswap32(tword[7-j]), where tword[m] is the
 * big-endian word formed from target bytes 4m..4m+3.
 * The compare runs on AVX-512 opmask registers: per
 * word, undecided lanes take the cmplt/cmpgt result
 * until every lane is decided; a lane meets the
 * target iff it is never greater. Equality meets.
 *
 * Accounting matches bal_v_batch2 exactly:
 * out_attempted == count, out_backend == sum over
 * spans of ceil(span/16)*16. Dummy lanes in a partial
 * final group are masked out of the flag bits and
 * never extracted.
 *
 * Scope: this is a BATCH-scope entry point only. It
 * is not a search entry point and changes no search
 * rate. The kernel is only ever CALLED after the
 * runtime CPUID probe in bal_avx512_probe.c confirms
 * AVX-512F and AVX-512BW; see gpu/engine.py
 * (_try_v512flags).
 *
 * Exports:
 *   bal_v_batchf2(header, start, count, threads, target,
 *                 flagbits, digests, out_attempted,
 *                 out_backend)
 * Return codes follow the counted ABI (-1 bad args or
 * empty, -2 range crossing 2^32, -5 scratch allocation
 * failure, 0 ok).
 */
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdatomic.h>
#include <pthread.h>
#include <immintrin.h>

#include "bal_search.h"

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
      __m512i s0 = _mm512_xor_si512(
        _mm512_xor_si512(vr32(x, 7), vr32(x, 18)),
        _mm512_srli_epi32(x, 3));
      __m512i s1 = _mm512_xor_si512(
        _mm512_xor_si512(vr32(y, 17), vr32(y, 19)),
        _mm512_srli_epi32(y, 10));
      w = _mm512_add_epi32(
        _mm512_add_epi32(W[(t - 16) & 15], s0),
        _mm512_add_epi32(W[(t - 7) & 15], s1));
      W[t & 15] = w;
    }
    __m512i S1 = _mm512_xor_si512(
      _mm512_xor_si512(vr32(e, 6), vr32(e, 11)), vr32(e, 25));
    __m512i ch = _mm512_xor_si512(_mm512_and_epi32(e, f),
                                  _mm512_andnot_epi32(e, g));
    __m512i T1 = _mm512_add_epi32(
      _mm512_add_epi32(
        _mm512_add_epi32(h, S1),
        _mm512_add_epi32(ch, _mm512_set1_epi32((int)V_K[t]))), w);
    __m512i S0 = _mm512_xor_si512(
      _mm512_xor_si512(vr32(a, 2), vr32(a, 13)), vr32(a, 22));
    __m512i mj = _mm512_xor_si512(
      _mm512_xor_si512(_mm512_and_epi32(a, b),
                       _mm512_and_epi32(a, c)),
      _mm512_and_epi32(b, c));
    __m512i T2 = _mm512_add_epi32(S0, mj);
    h = g; g = f; f = e;
    e = _mm512_add_epi32(d, T1);
    d = c; c = b; b = a;
    a = _mm512_add_epi32(T1, T2);
  }
  S[0] = a; S[1] = b; S[2] = c; S[3] = d;
  S[4] = e; S[5] = f; S[6] = g; S[7] = h;
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

/* ---- EXP-022 flags-only group, walker and run ---- */

static inline __m512i vf_bswap_vec(__m512i x) {
  const __m512i swmask = _mm512_set_epi8(
    60, 61, 62, 63, 56, 57, 58, 59, 52, 53, 54, 55,
    48, 49, 50, 51, 44, 45, 46, 47, 40, 41, 42, 43,
    36, 37, 38, 39, 32, 33, 34, 35, 28, 29, 30, 31,
    24, 25, 26, 27, 20, 21, 22, 23, 16, 17, 18, 19,
    12, 13, 14, 15, 8, 9, 10, 11, 4, 5, 6, 7, 0, 1, 2, 3);
  return _mm512_shuffle_epi8(x, swmask);
}

/* One group of 16 lanes, flags form. sw[j] is the j-th most
 * significant comparison word of the target (see the file
 * header for the derivation). Returns the meets mask over
 * the valid lanes. When extract is nonzero and at least one
 * lane meets, the flagged lanes' digests are written into
 * dig[l] in the same byte layout as v_group; unflagged slots
 * of dig are not written. */
static __mmask16 vf_group(const VTemplate *tp, const uint32_t sw[8],
                          uint32_t first_nonce, int valid,
                          uint8_t dig[][32], int extract) {
  __m512i laneidx = _mm512_set_epi32(15, 14, 13, 12, 11, 10, 9, 8,
                                     7, 6, 5, 4, 3, 2, 1, 0);
  __m512i nonces = _mm512_add_epi32(
    _mm512_set1_epi32((int)first_nonce), laneidx);
  __m512i w3 = vf_bswap_vec(nonces);
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
  for (int j = 0; j < 8; j++)
    SO[j] = _mm512_add_epi32(
      SO[j], _mm512_set1_epi32((int)V_H0[j]));
  /* Vector lexicographic compare in v_meets significance
   * order, carried in opmask registers. */
  __mmask16 greater = 0, less = 0;
  for (int j = 0; j < 8; j++) {
    __m512i cw = vf_bswap_vec(SO[7 - j]);
    __m512i tw = _mm512_set1_epi32((int)sw[j]);
    __mmask16 undecided = (__mmask16)~(greater | less);
    less |= undecided & _mm512_cmplt_epu32_mask(cw, tw);
    greater |= undecided & _mm512_cmpgt_epu32_mask(cw, tw);
  }
  __mmask16 valid_mask = valid >= 16
    ? (__mmask16)0xFFFFu
    : (__mmask16)((1u << valid) - 1u);
  __mmask16 meets = (__mmask16)~greater & valid_mask;
  (void)less;
  if (extract && meets) {
    uint32_t dg[8][16];
    for (int j = 0; j < 8; j++)
      _mm512_storeu_si512((void *)dg[j], SO[j]);
    __mmask16 m = meets;
    while (m) {
      int l = __builtin_ctz((unsigned)m);
      m = (__mmask16)(m & (m - 1));
      for (int j = 0; j < 8; j++) {
        uint32_t v = dg[j][l];
        dig[l][4 * j] = (uint8_t)(v >> 24);
        dig[l][4 * j + 1] = (uint8_t)(v >> 16);
        dig[l][4 * j + 2] = (uint8_t)(v >> 8);
        dig[l][4 * j + 3] = (uint8_t)v;
      }
    }
  }
  return meets;
}

typedef struct {
  const VTemplate *tp;
  uint32_t sw[8];
  uint64_t start;      /* global nonce of span start */
  uint64_t span;
  uint8_t *localbits;  /* private per-span flag bits */
  uint8_t *digests;    /* global slots, pre-offset; may be NULL */
  uint64_t attempted;
  uint64_t backend;
} VFJob;

static void vf_walk(VFJob *job) {
  uint64_t off = 0;
  int extract = job->digests != NULL;
  while (off < job->span) {
    uint64_t rem = job->span - off;
    int valid = rem >= 16 ? 16 : (int)rem;
    uint8_t dig[16][32];
    __mmask16 meets = vf_group(job->tp, job->sw,
                               (uint32_t)(job->start + off), valid,
                               dig, extract);
    job->backend += 16;
    job->attempted += (uint64_t)valid;
    /* off is a multiple of 16 for every group, so the 16
     * mask bits land exactly on two local flag bytes. */
    job->localbits[off >> 3] = (uint8_t)(meets & 0xFFu);
    job->localbits[(off >> 3) + 1] = (uint8_t)(meets >> 8);
    if (extract && meets) {
      __mmask16 m = meets;
      while (m) {
        int l = __builtin_ctz((unsigned)m);
        m = (__mmask16)(m & (m - 1));
        memcpy(job->digests + 32 * (size_t)(off + (uint64_t)l),
               dig[l], 32);
      }
    }
    off += (uint64_t)valid;
  }
}

typedef struct {
  VFJob v;
  uint64_t begin, end;
} VFThreadJob;

static void *vf_worker(void *arg) {
  VFThreadJob *job = (VFThreadJob *)arg;
  VFJob v = job->v;
  v.start += job->begin;
  v.span = job->end - job->begin;
  if (v.digests) v.digests = job->v.digests + 32 * (size_t)job->begin;
  v.attempted = 0;
  v.backend = 0;
  vf_walk(&v);
  job->v.attempted = v.attempted;
  job->v.backend = v.backend;
  return NULL;
}

/* OR the span-local bit array into the global flag bits at
 * bit offset begin. Bits at or beyond begin+span in local
 * are zero by construction, so the spill byte write only
 * ever carries real bits; it is bounds-guarded regardless. */
static void vf_merge(uint8_t *flagbits, size_t flagbytes,
                     const uint8_t *local, uint64_t begin,
                     uint64_t span) {
  unsigned shift = (unsigned)(begin & 7u);
  size_t out = (size_t)(begin >> 3);
  size_t nbytes = (size_t)((span + 7u) / 8u);
  if (shift == 0) {
    for (size_t i = 0; i < nbytes; i++)
      flagbits[out + i] |= local[i];
    return;
  }
  uint8_t prev = 0;
  for (size_t i = 0; i < nbytes; i++) {
    uint8_t cur = local[i];
    flagbits[out + i] |=
      (uint8_t)((cur << shift) | (prev >> (8 - shift)));
    prev = cur;
  }
  if (out + nbytes < flagbytes)
    flagbits[out + nbytes] |= (uint8_t)(prev >> (8 - shift));
}

static int vf_run(const uint8_t *header, uint64_t start,
                  uint64_t count, unsigned threads,
                  const uint8_t *target, uint8_t *flagbits,
                  uint8_t *digests, uint64_t *out_attempted,
                  uint64_t *out_backend) {
  VTemplate tp;
  v_template_init(&tp, header);
  /* Comparison words in v_meets significance order: word j
   * (most significant first) is bswap32 of the big-endian
   * target word 7-j. */
  uint32_t sw[8];
  for (int j = 0; j < 8; j++) {
    int m = 7 - j;
    uint32_t tw = ((uint32_t)target[4 * m] << 24) |
                  ((uint32_t)target[4 * m + 1] << 16) |
                  ((uint32_t)target[4 * m + 2] << 8) |
                  (uint32_t)target[4 * m + 3];
    sw[j] = v_bswap32(tw);
  }
  size_t flagbytes = (size_t)((count + 7u) / 8u);
  memset(flagbits, 0, flagbytes);
  uint64_t begins[16], ends[16];
  unsigned spans = bal_partition(count, threads, begins, ends);
  pthread_t tids[16];
  int created[16] = {0};
  VFThreadJob jobs[16];
  uint8_t *locals[16] = {0};
  for (unsigned sp = 0; sp < spans; sp++) {
    uint64_t span = ends[sp] - begins[sp];
    locals[sp] = (uint8_t *)calloc((size_t)((span + 7u) / 8u) + 2, 1);
    if (!locals[sp]) {
      for (unsigned q = 0; q < sp; q++) free(locals[q]);
      return -5;
    }
    jobs[sp].v = (VFJob){&tp, {0}, start, 0, locals[sp], digests,
                         0, 0};
    memcpy(jobs[sp].v.sw, sw, sizeof(sw));
    jobs[sp].begin = begins[sp];
    jobs[sp].end = ends[sp];
    if (bal_pthread_create(&tids[sp], NULL, vf_worker,
                           &jobs[sp]) != 0) {
      vf_worker(&jobs[sp]);
    } else {
      created[sp] = 1;
    }
  }
  for (unsigned sp = 0; sp < spans; sp++)
    if (created[sp]) pthread_join(tids[sp], NULL);
  if (out_attempted) {
    uint64_t total = 0;
    for (unsigned sp = 0; sp < spans; sp++)
      total += jobs[sp].v.attempted;
    *out_attempted = total;
  }
  if (out_backend) {
    uint64_t total = 0;
    for (unsigned sp = 0; sp < spans; sp++)
      total += jobs[sp].v.backend;
    *out_backend = total;
  }
  for (unsigned sp = 0; sp < spans; sp++) {
    vf_merge(flagbits, flagbytes, locals[sp], begins[sp],
             ends[sp] - begins[sp]);
    free(locals[sp]);
  }
  return 0;
}

/* Flags-only batch (EXP-022, Y-084). flagbits receives
 * ceil(count/8) bytes; bit i (byte i/8, bit i%8, LSB first)
 * is set iff nonce start+i meets the target. digests may be
 * NULL (no digest is materialised) or a count*32 buffer in
 * which only flagged lanes' slots are written, in the same
 * layout as bal_v_batch2. Return codes mirror bal_v_batch2,
 * plus -5 for a scratch allocation failure. */
int bal_v_batchf2(const uint8_t *header, uint64_t start,
                  uint64_t count, unsigned threads,
                  const uint8_t *target, uint8_t *flagbits,
                  uint8_t *digests, uint64_t *out_attempted,
                  uint64_t *out_backend) {
  if (!header || !target || !flagbits) return -1;
  if (!threads || threads > 16) return -1;
  int v = bal_validate_range(start, count);
  if (v != 0) return v;
  return vf_run(header, start, count, threads, target, flagbits,
                digests, out_attempted, out_backend);
}

/* ==== EXP-032 ADDITION: flags-form early-exit search ====
 * bal_v_searchf2 walks the same 16-lane groups as the
 * flags batch, but per group it asks vf_group for the
 * meets mask with extraction enabled, and on the first
 * group whose mask is nonzero it publishes the lowest
 * flagged lane through the shared BalSearchCtx and stops.
 * No flag-bit array is materialised and no digest is
 * extracted for any unflagged lane or any group after the
 * hit group. Accounting mirrors bal_v_search2: attempted
 * counts the real nonces of every completed group
 * (group-atomic, including the hit group), backend counts
 * lane computations including dummy lanes of partial
 * groups. ABI and return codes mirror bal_v_search2. */

typedef struct {
  const VTemplate *tp;
  uint32_t sw[8];
  uint64_t start;
  uint64_t span;
  BalSearchCtx *ctx;
  uint64_t attempted;
  uint64_t backend;
} SFJob;

static void sf_walk(SFJob *job) {
  uint64_t off = 0;
  while (off < job->span) {
    if (bal_ctx_stopped(job->ctx)) break;
    uint64_t rem = job->span - off;
    int valid = rem >= 16 ? 16 : (int)rem;
    uint8_t dig[16][32];
    __mmask16 meets = vf_group(job->tp, job->sw,
                               (uint32_t)(job->start + off), valid,
                               dig, 1);
    job->backend += 16;
    job->attempted += (uint64_t)valid;
    if (meets) {
      int l = __builtin_ctz((unsigned)meets);
      bal_ctx_publish(job->ctx,
                      (uint32_t)(job->start + off + (uint64_t)l),
                      dig[l]);
      break;
    }
    off += (uint64_t)valid;
  }
}

typedef struct {
  SFJob v;
  uint64_t begin, end;
} SFThreadJob;

static void *sf_worker(void *arg) {
  SFThreadJob *job = (SFThreadJob *)arg;
  SFJob v = job->v;
  v.start += job->begin;
  v.span = job->end - job->begin;
  v.attempted = 0;
  v.backend = 0;
  sf_walk(&v);
  job->v.attempted = v.attempted;
  job->v.backend = v.backend;
  return NULL;
}

int bal_v_searchf2(const uint8_t *header, uint64_t start,
                   uint64_t count, unsigned threads,
                   const uint8_t *target, uint32_t *out_nonce,
                   uint8_t *out_digest, uint64_t *out_attempted,
                   uint64_t *out_backend) {
  if (!header || !target || !out_nonce || !out_digest) return -1;
  if (!threads || threads > 16) return -1;
  int v = bal_validate_range(start, count);
  if (v != 0) return v;
  VTemplate tp;
  v_template_init(&tp, header);
  uint32_t sw[8];
  for (int j = 0; j < 8; j++) {
    int m = 7 - j;
    uint32_t tw = ((uint32_t)target[4 * m] << 24) |
                  ((uint32_t)target[4 * m + 1] << 16) |
                  ((uint32_t)target[4 * m + 2] << 8) |
                  (uint32_t)target[4 * m + 3];
    sw[j] = v_bswap32(tw);
  }
  BalSearchCtx ctx;
  if (bal_ctx_init(&ctx) != 0) return -4;
  uint64_t begins[16], ends[16];
  unsigned spans = bal_partition(count, threads, begins, ends);
  pthread_t tids[16];
  int created[16] = {0};
  SFThreadJob jobs[16];
  for (unsigned sp = 0; sp < spans; sp++) {
    jobs[sp].v = (SFJob){&tp, {0}, start, 0, &ctx, 0, 0};
    memcpy(jobs[sp].v.sw, sw, sizeof(sw));
    jobs[sp].begin = begins[sp];
    jobs[sp].end = ends[sp];
    if (bal_pthread_create(&tids[sp], NULL, sf_worker,
                           &jobs[sp]) != 0) {
      sf_worker(&jobs[sp]);
    } else {
      created[sp] = 1;
    }
  }
  for (unsigned sp = 0; sp < spans; sp++)
    if (created[sp]) pthread_join(tids[sp], NULL);
  if (out_attempted) {
    uint64_t total = 0;
    for (unsigned sp = 0; sp < spans; sp++)
      total += jobs[sp].v.attempted;
    *out_attempted = total;
  }
  if (out_backend) {
    uint64_t total = 0;
    for (unsigned sp = 0; sp < spans; sp++)
      total += jobs[sp].v.backend;
    *out_backend = total;
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

