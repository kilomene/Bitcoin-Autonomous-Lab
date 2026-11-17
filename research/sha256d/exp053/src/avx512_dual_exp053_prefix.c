/* ============================================================
 * EXP-053 RESEARCH COPY (NOVA-ER-0013, register Y-098,
 * Phase 001 H-6): chunk-2 prefix sharing inside the
 * production dual-batch walker.
 *
 * Generated mechanically from mining/cpu/bal_avx512_dual.c
 * by research/sha256d/exp053/build_variant.py; do not edit
 * by hand, regenerate. The stock code is byte-identical to
 * production. The only additions are v_compress16x2_prefix
 * (chunk-2 rounds 0 to 2 executed once for both batches
 * instead of twice) and the vp walkers/exports
 * (bal_vp_batch2, bal_vp_search2) that call it for the
 * chunk-2 compression of each dual group. The outer chunk
 * and the single-group remainder path are unchanged.
 * Production is untouched by this experiment.
 * ============================================================ */
/* NOVA SHA-X EXP-026 candidate C2 (DualMask): register-resident
 * dual-batch AVX-512 multi-buffer SHA-256d with the EXP-024
 * opmask target compare.
 *
 * PRODUCTION COPY (integrated 2026-11-14 under the owner's
 * explicit decision, following the EXP-026 VERIFIED
 * IMPROVEMENT verdict: pooled 1.718x vs the production
 * single-batch search, CI entirely above 0 in every session,
 * and 1.444x vs its strongest single ingredient): this file
 * is the production translation unit built by
 * mining/cpu/build.py into .local/cpu/libbal_v512dual.so.
 * It is byte-identical to the research original at
 * research/sha256d/extreme_optimization/src/
 * avx512_mb_exp026_dual.c except for this comment, the
 * bal_search.h include path, and the production export
 * renames listed below. Any change here must be mirrored
 * there or the divergence recorded. The kernel is only
 * ever CALLED after the runtime CPUID probe in
 * bal_avx512_probe.c confirms AVX-512F and AVX-512BW; see
 * gpu/engine.py (_try_v512dual).
 *
 * Export mapping (production name <- research name):
 *   bal_vd_search2        <- bal_v_e26d_search2
 *     (the DualMask counted search; the engine's entry)
 *   bal_vd_batch2         <- bal_r_batch2
 *     (the dual-batch full enumeration from the same
 *     source; the engine's batch entry)
 *   bal_vd_search2_exp018 <- bal_r_search2
 *     (the EXP-018 plain dual search, retained for source
 *     parity; not called by the engine)
 *
 * Accounting (Task 003.9 definitions): search is
 * dual-atomic over 32 lanes. A started dual group always
 * completes, so on an early exit attempted counts the
 * real nonces of every completed dual group and
 * backend counts 32 lane computations per dual group,
 * dummy lanes included. A span remainder under 17
 * nonces uses the single-group path, whose backend
 * granularity is 16 lanes. Batch enumeration covers the
 * full range: attempted == count, and backend counts
 * actual lane computations including dummy lanes of
 * partial final groups.
 *
 * Return codes follow the counted ABI (-1 bad args or
 * empty, -2 range crossing 2^32, 0 ok / miss, 1 found).
 */
/* NOVA SHA-X EXP-018 (Y-023): register-resident
 * dual-batch AVX-512 multi-buffer SHA-256d.
 *
 * This is a new implementation, derived from the
 * EXP-011 dual-batch kernel but not a modification of
 * it. The dual compression keeps both batches' eight
 * state vectors in named vector variables throughout
 * each compression. A compile-time ring relabelling
 * implements the SHA-256 state rotation: a round
 * writes its new A into the physical variable that
 * held H and its new E into the physical variable
 * that held D, and the next macro invocation receives
 * the rotated argument tuple. After eight rounds the
 * physical orientation repeats, so an eight-round
 * repeating unit returns to the initial orientation
 * with no state rename moves, and eight repetitions
 * cover the 64 rounds. The two schedule rings remain
 * stack arrays
 * by design: 16 state vectors plus two full schedule
 * rings cannot fit in 32 zmm registers, so this
 * experiment isolates state residency and records
 * the schedule stack traffic separately in its
 * assembly audit.
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
 *   bal_vd_batch2(header, start, count, threads, target,
 *                hashes, flags, out_attempted, out_backend)
 *   bal_vd_search2_exp018(header, start, count, threads, target,
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

/* ---- register-resident dual-batch compress (EXP-018) ----
 * VSTEP_RING writes only two of its eight state
 * arguments: h receives the new A and d receives the
 * new E. The other six physical variables keep their
 * values and are reinterpreted as the next round's
 * b, c, d, f, g and h by the rotated argument tuple
 * in DUAL_BLOCK. This is an exact relabelling, not a
 * changed round: T1 and T2 are computed from the
 * pre-update roles before either write. The Boolean
 * cones use the VPTERNLOGD forms proven in EXP-012
 * (XOR3 0x96, Ch 0xCA, Maj 0xE8). */
#define VSTEP_RING(a, b, c, d, e, f, g, h, Wr, t) do { \
  __m512i w; \
  if ((t) < 16) { w = Wr[t]; } else { \
    __m512i x = Wr[((t) - 15) & 15]; \
    __m512i y = Wr[((t) - 2) & 15]; \
    __m512i ms0 = _mm512_ternarylogic_epi32( \
      vr32(x, 7), vr32(x, 18), _mm512_srli_epi32(x, 3), 0x96); \
    __m512i ms1 = _mm512_ternarylogic_epi32( \
      vr32(y, 17), vr32(y, 19), _mm512_srli_epi32(y, 10), 0x96); \
    w = _mm512_add_epi32( \
      _mm512_add_epi32(Wr[((t) - 16) & 15], ms0), \
      _mm512_add_epi32(Wr[((t) - 7) & 15], ms1)); \
    Wr[(t) & 15] = w; } \
  __m512i S1 = _mm512_ternarylogic_epi32( \
    vr32(e, 6), vr32(e, 11), vr32(e, 25), 0x96); \
  __m512i ch = _mm512_ternarylogic_epi32(e, f, g, 0xCA); \
  __m512i T1 = _mm512_add_epi32( \
    _mm512_add_epi32( \
      _mm512_add_epi32(h, S1), \
      _mm512_add_epi32(ch, _mm512_set1_epi32((int)V_K[t]))), w); \
  __m512i S0 = _mm512_ternarylogic_epi32( \
    vr32(a, 2), vr32(a, 13), vr32(a, 22), 0x96); \
  __m512i mj = _mm512_ternarylogic_epi32(a, b, c, 0xE8); \
  __m512i T2 = _mm512_add_epi32(S0, mj); \
  h = _mm512_add_epi32(T1, T2); \
  d = _mm512_add_epi32(d, T1); \
} while (0)

/* One eight-round unit for both batches. The
 * argument tuples rotate right by one physical
 * variable per round and return to the initial
 * orientation after round 8. A is the token
 * prefix of batch A's state variables (a0 to a7) and
 * B the prefix of batch B's (b0 to b7). */
#define DUAL8(BASE, A, B, Wa, Wb) do { \
  VSTEP_RING(A##0, A##1, A##2, A##3, A##4, A##5, A##6, A##7, Wa, (BASE) + 0); \
  VSTEP_RING(B##0, B##1, B##2, B##3, B##4, B##5, B##6, B##7, Wb, (BASE) + 0); \
  VSTEP_RING(A##7, A##0, A##1, A##2, A##3, A##4, A##5, A##6, Wa, (BASE) + 1); \
  VSTEP_RING(B##7, B##0, B##1, B##2, B##3, B##4, B##5, B##6, Wb, (BASE) + 1); \
  VSTEP_RING(A##6, A##7, A##0, A##1, A##2, A##3, A##4, A##5, Wa, (BASE) + 2); \
  VSTEP_RING(B##6, B##7, B##0, B##1, B##2, B##3, B##4, B##5, Wb, (BASE) + 2); \
  VSTEP_RING(A##5, A##6, A##7, A##0, A##1, A##2, A##3, A##4, Wa, (BASE) + 3); \
  VSTEP_RING(B##5, B##6, B##7, B##0, B##1, B##2, B##3, B##4, Wb, (BASE) + 3); \
  VSTEP_RING(A##4, A##5, A##6, A##7, A##0, A##1, A##2, A##3, Wa, (BASE) + 4); \
  VSTEP_RING(B##4, B##5, B##6, B##7, B##0, B##1, B##2, B##3, Wb, (BASE) + 4); \
  VSTEP_RING(A##3, A##4, A##5, A##6, A##7, A##0, A##1, A##2, Wa, (BASE) + 5); \
  VSTEP_RING(B##3, B##4, B##5, B##6, B##7, B##0, B##1, B##2, Wb, (BASE) + 5); \
  VSTEP_RING(A##2, A##3, A##4, A##5, A##6, A##7, A##0, A##1, Wa, (BASE) + 6); \
  VSTEP_RING(B##2, B##3, B##4, B##5, B##6, B##7, B##0, B##1, Wb, (BASE) + 6); \
  VSTEP_RING(A##1, A##2, A##3, A##4, A##5, A##6, A##7, A##0, Wa, (BASE) + 7); \
  VSTEP_RING(B##1, B##2, B##3, B##4, B##5, B##6, B##7, B##0, Wb, (BASE) + 7); \
} while (0)

static void v_compress16x2_reg(__m512i Sa[8],
                               const __m512i W0a[16],
                               __m512i Sb[8],
                               const __m512i W0b[16]) {
  __m512i Wa[16], Wb[16];
  for (int i = 0; i < 16; i++) { Wa[i] = W0a[i]; Wb[i] = W0b[i]; }
  __m512i a0 = Sa[0], a1 = Sa[1], a2 = Sa[2], a3 = Sa[3],
          a4 = Sa[4], a5 = Sa[5], a6 = Sa[6], a7 = Sa[7];
  __m512i b0 = Sb[0], b1 = Sb[1], b2 = Sb[2], b3 = Sb[3],
          b4 = Sb[4], b5 = Sb[5], b6 = Sb[6], b7 = Sb[7];
  /* Eight repetitions of an eight-round unit. The
   * ring orientation returns after eight rounds, so
   * every repetition starts from the same physical
   * argument tuple and the compiler only has to keep
   * sixteen rounds (eight per batch) of live range in
   * view at once. An earlier full 64-round unroll of
   * this same source structure compiled to a body
   * whose low stack region carried hundreds of vector
   * spill accesses; that audit is recorded in
   * EXP-018 and is why the repeating unit is the
   * shipped structure. */
  for (int rep = 0; rep < 8; rep++) {
    int base = rep * 8;
    DUAL8(base, a, b, Wa, Wb);
  }
  Sa[0] = a0; Sa[1] = a1; Sa[2] = a2; Sa[3] = a3;
  Sa[4] = a4; Sa[5] = a5; Sa[6] = a6; Sa[7] = a7;
  Sb[0] = b0; Sb[1] = b1; Sb[2] = b2; Sb[3] = b3;
  Sb[4] = b4; Sb[5] = b5; Sb[6] = b6; Sb[7] = b7;
}

/* ---- EXP-053: prefix-shared dual compress ----
 * Precondition (guaranteed by both call sites, which
 * build W0a and W0b from the same template through
 * v_make_w0 and seed both states from the same midstate
 * broadcast): Sa[j] == Sb[j] for all j at entry, and
 * W0a[i] == W0b[i] for i in 0..2. The batches differ
 * only in W[3], the nonce word. Rounds 0 to 2 consume
 * only W[0], W[1], W[2], so the state after round 2 is
 * identical for both batches (Stage 1 dependency
 * graph: state after rounds 0..2 carries no nonce
 * dependence). This function runs those three rounds
 * once on batch A's physical variables, copies the
 * eight physical state vectors to batch B, and runs
 * rounds 3 to 63 as the stock interleaved dual ring.
 * The schedule rings are not written by rounds 0 to 2
 * (the t < 16 branch of VSTEP_RING reads Wr[t] and
 * never stores), so Wa and Wb keep their own W[3] for
 * round 3 onward, exactly as in the stock compress.
 * The arithmetic is the stock arithmetic: same ops,
 * same order, one copy of the first three chunk-2
 * rounds instead of two. The saving is bounded by
 * 3 of the 256 round steps of a dual group (both
 * chunks, both batches), about 1.17 percent of round
 * work, before second-order effects. */
#define VPREFIX3(A, Wa) do { \
  VSTEP_RING(A##0, A##1, A##2, A##3, A##4, A##5, A##6, A##7, Wa, 0); \
  VSTEP_RING(A##7, A##0, A##1, A##2, A##3, A##4, A##5, A##6, Wa, 1); \
  VSTEP_RING(A##6, A##7, A##0, A##1, A##2, A##3, A##4, A##5, Wa, 2); \
} while (0)

#define DUAL5_TAIL(A, B, Wa, Wb) do { \
  VSTEP_RING(A##5, A##6, A##7, A##0, A##1, A##2, A##3, A##4, Wa, 3); \
  VSTEP_RING(B##5, B##6, B##7, B##0, B##1, B##2, B##3, B##4, Wb, 3); \
  VSTEP_RING(A##4, A##5, A##6, A##7, A##0, A##1, A##2, A##3, Wa, 4); \
  VSTEP_RING(B##4, B##5, B##6, B##7, B##0, B##1, B##2, B##3, Wb, 4); \
  VSTEP_RING(A##3, A##4, A##5, A##6, A##7, A##0, A##1, A##2, Wa, 5); \
  VSTEP_RING(B##3, B##4, B##5, B##6, B##7, B##0, B##1, B##2, Wb, 5); \
  VSTEP_RING(A##2, A##3, A##4, A##5, A##6, A##7, A##0, A##1, Wa, 6); \
  VSTEP_RING(B##2, B##3, B##4, B##5, B##6, B##7, B##0, B##1, Wb, 6); \
  VSTEP_RING(A##1, A##2, A##3, A##4, A##5, A##6, A##7, A##0, Wa, 7); \
  VSTEP_RING(B##1, B##2, B##3, B##4, B##5, B##6, B##7, B##0, Wb, 7); \
} while (0)

static void v_compress16x2_prefix(__m512i Sa[8],
                                  const __m512i W0a[16],
                                  __m512i Sb[8],
                                  const __m512i W0b[16]) {
  __m512i Wa[16], Wb[16];
  for (int i = 0; i < 16; i++) { Wa[i] = W0a[i]; Wb[i] = W0b[i]; }
  __m512i a0 = Sa[0], a1 = Sa[1], a2 = Sa[2], a3 = Sa[3],
          a4 = Sa[4], a5 = Sa[5], a6 = Sa[6], a7 = Sa[7];
  /* Shared prefix: rounds 0 to 2 once (see the block
   * comment above). Sb at entry equals Sa by the
   * precondition and is not read. */
  VPREFIX3(a, Wa);
  __m512i b0 = a0, b1 = a1, b2 = a2, b3 = a3,
          b4 = a4, b5 = a5, b6 = a6, b7 = a7;
  /* Rounds 3 to 7 complete the first eight-round unit;
   * the ring orientation returns after round 7, so the
   * remaining seven units are the stock DUAL8. */
  DUAL5_TAIL(a, b, Wa, Wb);
  for (int rep = 1; rep < 8; rep++) {
    int base = rep * 8;
    DUAL8(base, a, b, Wa, Wb);
  }
  Sa[0] = a0; Sa[1] = a1; Sa[2] = a2; Sa[3] = a3;
  Sa[4] = a4; Sa[5] = a5; Sa[6] = a6; Sa[7] = a7;
  Sb[0] = b0; Sb[1] = b1; Sb[2] = b2; Sb[3] = b3;
  Sb[4] = b4; Sb[5] = b5; Sb[6] = b6; Sb[7] = b7;
}

static void v_make_w0(const VTemplate *tp, uint32_t first_nonce,
                      __m512i W0[16]) {
  __m512i laneidx = _mm512_set_epi32(15, 14, 13, 12, 11, 10, 9, 8,
                                     7, 6, 5, 4, 3, 2, 1, 0);
  __m512i nonces = _mm512_add_epi32(
    _mm512_set1_epi32((int)first_nonce), laneidx);
  const __m512i swmask = _mm512_set_epi8(
    60, 61, 62, 63, 56, 57, 58, 59, 52, 53, 54, 55,
    48, 49, 50, 51, 44, 45, 46, 47, 40, 41, 42, 43,
    36, 37, 38, 39, 32, 33, 34, 35, 28, 29, 30, 31,
    24, 25, 26, 27, 20, 21, 22, 23, 16, 17, 18, 19,
    12, 13, 14, 15, 8, 9, 10, 11, 4, 5, 6, 7, 0, 1, 2, 3);
  W0[0] = _mm512_set1_epi32((int)tp->w0);
  W0[1] = _mm512_set1_epi32((int)tp->w1);
  W0[2] = _mm512_set1_epi32((int)tp->w2);
  W0[3] = _mm512_shuffle_epi8(nonces, swmask);
  W0[4] = _mm512_set1_epi32((int)0x80000000);
  for (int i = 5; i < 15; i++) W0[i] = _mm512_setzero_si512();
  W0[15] = _mm512_set1_epi32(640);
}

/* Two groups of 16 lanes as one interleaved dual batch.
 * valid_total is 17..32; lanes beyond valid_total are
 * computed but never stored and never counted. */
static void v_group2(const VTemplate *tp, uint32_t first_nonce,
                     int valid_total, uint8_t dig[][32]) {
  __m512i W0a[16], W0b[16];
  v_make_w0(tp, first_nonce, W0a);
  v_make_w0(tp, first_nonce + 16, W0b);
  __m512i Sa[8], Sb[8];
  for (int j = 0; j < 8; j++) {
    Sa[j] = _mm512_set1_epi32((int)tp->mid[j]);
    Sb[j] = _mm512_set1_epi32((int)tp->mid[j]);
  }
  v_compress16x2_reg(Sa, W0a, Sb, W0b);
  uint32_t inna[8][16], innb[8][16];
  for (int j = 0; j < 8; j++) {
    Sa[j] = _mm512_add_epi32(
      Sa[j], _mm512_set1_epi32((int)tp->mid[j]));
    Sb[j] = _mm512_add_epi32(
      Sb[j], _mm512_set1_epi32((int)tp->mid[j]));
    _mm512_storeu_si512((void *)inna[j], Sa[j]);
    _mm512_storeu_si512((void *)innb[j], Sb[j]);
  }
  __m512i W1a[16], W1b[16];
  for (int j = 0; j < 8; j++) {
    W1a[j] = _mm512_loadu_si512((const void *)inna[j]);
    W1b[j] = _mm512_loadu_si512((const void *)innb[j]);
  }
  W1a[8] = _mm512_set1_epi32((int)0x80000000);
  W1b[8] = _mm512_set1_epi32((int)0x80000000);
  for (int i = 9; i < 15; i++) {
    W1a[i] = _mm512_setzero_si512();
    W1b[i] = _mm512_setzero_si512();
  }
  W1a[15] = _mm512_set1_epi32(256);
  W1b[15] = _mm512_set1_epi32(256);
  __m512i SOa[8], SOb[8];
  for (int j = 0; j < 8; j++) {
    SOa[j] = _mm512_set1_epi32((int)V_H0[j]);
    SOb[j] = _mm512_set1_epi32((int)V_H0[j]);
  }
  v_compress16x2_reg(SOa, W1a, SOb, W1b);
  uint32_t dga[8][16], dgb[8][16];
  for (int j = 0; j < 8; j++) {
    SOa[j] = _mm512_add_epi32(
      SOa[j], _mm512_set1_epi32((int)V_H0[j]));
    SOb[j] = _mm512_add_epi32(
      SOb[j], _mm512_set1_epi32((int)V_H0[j]));
    _mm512_storeu_si512((void *)dga[j], SOa[j]);
    _mm512_storeu_si512((void *)dgb[j], SOb[j]);
  }
  for (int l = 0; l < valid_total; l++) {
    const uint32_t(*dg)[16] = l < 16 ? dga : dgb;
    int lane = l < 16 ? l : l - 16;
    for (int j = 0; j < 8; j++) {
      uint32_t v = dg[j][lane];
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
    if (rem >= 17) {
      /* Dual-batch step (EXP-011): 32 lanes, group-atomic
       * over the whole dual batch. */
      int valid = rem >= 32 ? 32 : (int)rem;
      uint8_t dig[32][32];
      v_group2(job->tp, (uint32_t)(job->start + off), valid, dig);
      job->backend += 32;
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
    } else {
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

int bal_vd_batch2(const uint8_t *header, uint64_t start, uint64_t count,
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

int bal_vd_search2_exp018(const uint8_t *header, uint64_t start, uint64_t count,
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

/* ============================================================
 * EXP-026 candidate C2 (DualMask): opmask compare on the
 * EXP-018 dual-batch register-resident kernel. New walker
 * only; the dual compress above is unchanged. Per dual
 * group, each batch's final state is compared in opmask
 * registers; digest staging happens only for a batch
 * whose mask is nonzero, and only its lowest flagged
 * lane is extracted. Remainder spans under 17 nonces use
 * the original single-group path (v_group plus v_meets),
 * which is at most the final 16 nonces of a span.
 * Accounting mirrors bal_vd_search2_exp018 except the dual step
 * is group-atomic over 32 lanes: attempted counts the
 * real nonces of completed dual groups, backend counts
 * 32 per dual group including dummy lanes.
 * ============================================================ */

static void rm_target_words(const uint8_t *target, uint32_t sw[8]) {
  for (int j = 0; j < 8; j++) {
    int m = 7 - j;
    uint32_t tw = ((uint32_t)target[4 * m] << 24) |
                  ((uint32_t)target[4 * m + 1] << 16) |
                  ((uint32_t)target[4 * m + 2] << 8) |
                  (uint32_t)target[4 * m + 3];
    sw[j] = v_bswap32(tw);
  }
}

static __m512i rm_bswap_vec(__m512i x) {
  __m512i shuf = _mm512_set_epi8(
    60, 61, 62, 63, 56, 57, 58, 59, 52, 53, 54, 55, 48, 49, 50, 51,
    44, 45, 46, 47, 40, 41, 42, 43, 36, 37, 38, 39, 32, 33, 34, 35,
    28, 29, 30, 31, 24, 25, 26, 27, 20, 21, 22, 23, 16, 17, 18, 19,
    12, 13, 14, 15, 8, 9, 10, 11, 4, 5, 6, 7, 0, 1, 2, 3);
  return _mm512_shuffle_epi8(x, shuf);
}

static __mmask16 rm_meets_mask(const __m512i SO[8],
                               const uint32_t sw[8], int valid) {
  __mmask16 greater = 0, less = 0;
  for (int j = 0; j < 8; j++) {
    __m512i cw = rm_bswap_vec(SO[7 - j]);
    __m512i tw = _mm512_set1_epi32((int)sw[j]);
    __mmask16 undecided = (__mmask16)~(greater | less);
    less |= undecided & _mm512_cmplt_epu32_mask(cw, tw);
    greater |= undecided & _mm512_cmpgt_epu32_mask(cw, tw);
  }
  __mmask16 valid_mask = valid >= 16
    ? (__mmask16)0xFFFFu
    : (__mmask16)((1u << valid) - 1u);
  return (__mmask16)~greater & valid_mask;
}

static void rm_extract(const __m512i SO[8], int lane,
                       uint8_t dig[32]) {
  uint32_t dg[8][16];
  for (int j = 0; j < 8; j++)
    _mm512_storeu_si512((void *)dg[j], SO[j]);
  for (int j = 0; j < 8; j++) {
    uint32_t v = dg[j][lane];
    dig[4 * j] = (uint8_t)(v >> 24);
    dig[4 * j + 1] = (uint8_t)(v >> 16);
    dig[4 * j + 2] = (uint8_t)(v >> 8);
    dig[4 * j + 3] = (uint8_t)v;
  }
}

/* Dual group, mask form. Returns combined mask: bits
 * 0..15 batch A, bits 16..31 batch B. On a hit batch,
 * dig for its lowest flagged lane is written at
 * dig[global lane]. */
static uint32_t rm_group2m(const VTemplate *tp, const uint32_t sw[8],
                           uint32_t first_nonce, int valid_total,
                           uint8_t dig[][32]) {
  __m512i W0a[16], W0b[16];
  v_make_w0(tp, first_nonce, W0a);
  v_make_w0(tp, first_nonce + 16, W0b);
  __m512i Sa[8], Sb[8];
  for (int j = 0; j < 8; j++) {
    Sa[j] = _mm512_set1_epi32((int)tp->mid[j]);
    Sb[j] = _mm512_set1_epi32((int)tp->mid[j]);
  }
  v_compress16x2_reg(Sa, W0a, Sb, W0b);
  uint32_t inna[8][16], innb[8][16];
  for (int j = 0; j < 8; j++) {
    Sa[j] = _mm512_add_epi32(
      Sa[j], _mm512_set1_epi32((int)tp->mid[j]));
    Sb[j] = _mm512_add_epi32(
      Sb[j], _mm512_set1_epi32((int)tp->mid[j]));
    _mm512_storeu_si512((void *)inna[j], Sa[j]);
    _mm512_storeu_si512((void *)innb[j], Sb[j]);
  }
  __m512i W1a[16], W1b[16];
  for (int j = 0; j < 8; j++) {
    W1a[j] = _mm512_loadu_si512((const void *)inna[j]);
    W1b[j] = _mm512_loadu_si512((const void *)innb[j]);
  }
  W1a[8] = _mm512_set1_epi32((int)0x80000000);
  W1b[8] = _mm512_set1_epi32((int)0x80000000);
  for (int i = 9; i < 15; i++) {
    W1a[i] = _mm512_setzero_si512();
    W1b[i] = _mm512_setzero_si512();
  }
  W1a[15] = _mm512_set1_epi32(256);
  W1b[15] = _mm512_set1_epi32(256);
  __m512i SOa[8], SOb[8];
  for (int j = 0; j < 8; j++) {
    SOa[j] = _mm512_set1_epi32((int)V_H0[j]);
    SOb[j] = _mm512_set1_epi32((int)V_H0[j]);
  }
  v_compress16x2_reg(SOa, W1a, SOb, W1b);
  for (int j = 0; j < 8; j++) {
    SOa[j] = _mm512_add_epi32(
      SOa[j], _mm512_set1_epi32((int)V_H0[j]));
    SOb[j] = _mm512_add_epi32(
      SOb[j], _mm512_set1_epi32((int)V_H0[j]));
  }
  int va = valid_total >= 16 ? 16 : valid_total;
  int vb = valid_total > 16 ? valid_total - 16 : 0;
  __mmask16 ma = rm_meets_mask(SOa, sw, va);
  __mmask16 mb = vb > 0 ? rm_meets_mask(SOb, sw, vb) : 0;
  if (ma) {
    int l = __builtin_ctz((unsigned)ma);
    rm_extract(SOa, l, dig[l]);
  }
  if (mb) {
    int l = __builtin_ctz((unsigned)mb);
    rm_extract(SOb, l, dig[16 + l]);
  }
  return (uint32_t)ma | ((uint32_t)mb << 16);
}

typedef struct {
  const VTemplate *tp;
  uint32_t sw[8];
  uint64_t start;
  uint64_t span;
  const uint8_t *target;
  BalSearchCtx *ctx;
  uint64_t attempted;
  uint64_t backend;
} RMJob;

static void rm_walk(RMJob *job) {
  uint64_t off = 0;
  while (off < job->span) {
    if (bal_ctx_stopped(job->ctx)) break;
    uint64_t rem = job->span - off;
    if (rem >= 17) {
      int valid = rem >= 32 ? 32 : (int)rem;
      uint8_t dig[32][32];
      uint32_t m = rm_group2m(job->tp, job->sw,
                              (uint32_t)(job->start + off),
                              valid, dig);
      job->backend += 32;
      job->attempted += (uint64_t)valid;
      if (m) {
        int l = __builtin_ctz(m);
        bal_ctx_publish(job->ctx,
                        (uint32_t)(job->start + off + (uint64_t)l),
                        dig[l]);
      }
      off += (uint64_t)valid;
    } else {
      int valid = rem >= 16 ? 16 : (int)rem;
      uint8_t dig[16][32];
      v_group(job->tp, (uint32_t)(job->start + off), valid, dig);
      job->backend += 16;
      job->attempted += (uint64_t)valid;
      for (int l = 0; l < valid; l++) {
        if (v_meets(dig[l], job->target))
          bal_ctx_publish(job->ctx,
                          (uint32_t)(job->start + off + (uint64_t)l),
                          dig[l]);
      }
      off += (uint64_t)valid;
    }
  }
}

typedef struct {
  RMJob v;
  uint64_t begin, end;
} RMThreadJob;

static void *rm_worker(void *arg) {
  RMThreadJob *job = (RMThreadJob *)arg;
  RMJob v = job->v;
  v.start += job->begin;
  v.span = job->end - job->begin;
  v.attempted = 0;
  v.backend = 0;
  rm_walk(&v);
  job->v.attempted = v.attempted;
  job->v.backend = v.backend;
  return NULL;
}

int bal_vd_search2(const uint8_t *header, uint64_t start,
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
  rm_target_words(target, sw);
  BalSearchCtx ctx;
  if (bal_ctx_init(&ctx) != 0) return -4;
  uint64_t begins[16], ends[16];
  unsigned spans = bal_partition(count, threads, begins, ends);
  pthread_t tids[16];
  int created[16] = {0};
  RMThreadJob jobs[16];
  for (unsigned sp = 0; sp < spans; sp++) {
    jobs[sp].v = (RMJob){&tp, {0}, start, 0, target, &ctx, 0, 0};
    memcpy(jobs[sp].v.sw, sw, sizeof(sw));
    jobs[sp].begin = begins[sp];
    jobs[sp].end = ends[sp];
    if (bal_pthread_create(&tids[sp], NULL, rm_worker,
                           &jobs[sp]) != 0) {
      rm_worker(&jobs[sp]);
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

/* ============================================================
 * EXP-053 vp walkers and exports. The two group
 * functions below are verbatim extractions of v_group2
 * and rm_group2m with the chunk-2 compress call
 * retargeted to v_compress16x2_prefix; the walker spans
 * are verbatim extractions of the stock spans with the
 * renames listed in build_variant.py. Accounting is the
 * stock accounting, unchanged: search is dual-atomic
 * over 32 lanes, batch covers the full range, dummy
 * lanes are computed but never stored or counted.
 * ============================================================ */

static void vp_group2(const VTemplate *tp, uint32_t first_nonce,
                     int valid_total, uint8_t dig[][32]) {
  __m512i W0a[16], W0b[16];
  v_make_w0(tp, first_nonce, W0a);
  v_make_w0(tp, first_nonce + 16, W0b);
  __m512i Sa[8], Sb[8];
  for (int j = 0; j < 8; j++) {
    Sa[j] = _mm512_set1_epi32((int)tp->mid[j]);
    Sb[j] = _mm512_set1_epi32((int)tp->mid[j]);
  }
  v_compress16x2_prefix(Sa, W0a, Sb, W0b);
  uint32_t inna[8][16], innb[8][16];
  for (int j = 0; j < 8; j++) {
    Sa[j] = _mm512_add_epi32(
      Sa[j], _mm512_set1_epi32((int)tp->mid[j]));
    Sb[j] = _mm512_add_epi32(
      Sb[j], _mm512_set1_epi32((int)tp->mid[j]));
    _mm512_storeu_si512((void *)inna[j], Sa[j]);
    _mm512_storeu_si512((void *)innb[j], Sb[j]);
  }
  __m512i W1a[16], W1b[16];
  for (int j = 0; j < 8; j++) {
    W1a[j] = _mm512_loadu_si512((const void *)inna[j]);
    W1b[j] = _mm512_loadu_si512((const void *)innb[j]);
  }
  W1a[8] = _mm512_set1_epi32((int)0x80000000);
  W1b[8] = _mm512_set1_epi32((int)0x80000000);
  for (int i = 9; i < 15; i++) {
    W1a[i] = _mm512_setzero_si512();
    W1b[i] = _mm512_setzero_si512();
  }
  W1a[15] = _mm512_set1_epi32(256);
  W1b[15] = _mm512_set1_epi32(256);
  __m512i SOa[8], SOb[8];
  for (int j = 0; j < 8; j++) {
    SOa[j] = _mm512_set1_epi32((int)V_H0[j]);
    SOb[j] = _mm512_set1_epi32((int)V_H0[j]);
  }
  v_compress16x2_reg(SOa, W1a, SOb, W1b);
  uint32_t dga[8][16], dgb[8][16];
  for (int j = 0; j < 8; j++) {
    SOa[j] = _mm512_add_epi32(
      SOa[j], _mm512_set1_epi32((int)V_H0[j]));
    SOb[j] = _mm512_add_epi32(
      SOb[j], _mm512_set1_epi32((int)V_H0[j]));
    _mm512_storeu_si512((void *)dga[j], SOa[j]);
    _mm512_storeu_si512((void *)dgb[j], SOb[j]);
  }
  for (int l = 0; l < valid_total; l++) {
    const uint32_t(*dg)[16] = l < 16 ? dga : dgb;
    int lane = l < 16 ? l : l - 16;
    for (int j = 0; j < 8; j++) {
      uint32_t v = dg[j][lane];
      dig[l][4 * j] = (uint8_t)(v >> 24);
      dig[l][4 * j + 1] = (uint8_t)(v >> 16);
      dig[l][4 * j + 2] = (uint8_t)(v >> 8);
      dig[l][4 * j + 3] = (uint8_t)v;
    }
  }
}

static uint32_t vp_group2m(const VTemplate *tp, const uint32_t sw[8],
                           uint32_t first_nonce, int valid_total,
                           uint8_t dig[][32]) {
  __m512i W0a[16], W0b[16];
  v_make_w0(tp, first_nonce, W0a);
  v_make_w0(tp, first_nonce + 16, W0b);
  __m512i Sa[8], Sb[8];
  for (int j = 0; j < 8; j++) {
    Sa[j] = _mm512_set1_epi32((int)tp->mid[j]);
    Sb[j] = _mm512_set1_epi32((int)tp->mid[j]);
  }
  v_compress16x2_prefix(Sa, W0a, Sb, W0b);
  uint32_t inna[8][16], innb[8][16];
  for (int j = 0; j < 8; j++) {
    Sa[j] = _mm512_add_epi32(
      Sa[j], _mm512_set1_epi32((int)tp->mid[j]));
    Sb[j] = _mm512_add_epi32(
      Sb[j], _mm512_set1_epi32((int)tp->mid[j]));
    _mm512_storeu_si512((void *)inna[j], Sa[j]);
    _mm512_storeu_si512((void *)innb[j], Sb[j]);
  }
  __m512i W1a[16], W1b[16];
  for (int j = 0; j < 8; j++) {
    W1a[j] = _mm512_loadu_si512((const void *)inna[j]);
    W1b[j] = _mm512_loadu_si512((const void *)innb[j]);
  }
  W1a[8] = _mm512_set1_epi32((int)0x80000000);
  W1b[8] = _mm512_set1_epi32((int)0x80000000);
  for (int i = 9; i < 15; i++) {
    W1a[i] = _mm512_setzero_si512();
    W1b[i] = _mm512_setzero_si512();
  }
  W1a[15] = _mm512_set1_epi32(256);
  W1b[15] = _mm512_set1_epi32(256);
  __m512i SOa[8], SOb[8];
  for (int j = 0; j < 8; j++) {
    SOa[j] = _mm512_set1_epi32((int)V_H0[j]);
    SOb[j] = _mm512_set1_epi32((int)V_H0[j]);
  }
  v_compress16x2_reg(SOa, W1a, SOb, W1b);
  for (int j = 0; j < 8; j++) {
    SOa[j] = _mm512_add_epi32(
      SOa[j], _mm512_set1_epi32((int)V_H0[j]));
    SOb[j] = _mm512_add_epi32(
      SOb[j], _mm512_set1_epi32((int)V_H0[j]));
  }
  int va = valid_total >= 16 ? 16 : valid_total;
  int vb = valid_total > 16 ? valid_total - 16 : 0;
  __mmask16 ma = rm_meets_mask(SOa, sw, va);
  __mmask16 mb = vb > 0 ? rm_meets_mask(SOb, sw, vb) : 0;
  if (ma) {
    int l = __builtin_ctz((unsigned)ma);
    rm_extract(SOa, l, dig[l]);
  }
  if (mb) {
    int l = __builtin_ctz((unsigned)mb);
    rm_extract(SOb, l, dig[16 + l]);
  }
  return (uint32_t)ma | ((uint32_t)mb << 16);
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
} VPJob;

static void vp_walk(VPJob *job) {
  uint64_t off = 0;
  while (off < job->span) {
    if (job->ctx && bal_ctx_stopped(job->ctx)) break;
    uint64_t rem = job->span - off;
    if (rem >= 17) {
      /* Dual-batch step (EXP-011): 32 lanes, group-atomic
       * over the whole dual batch. */
      int valid = rem >= 32 ? 32 : (int)rem;
      uint8_t dig[32][32];
      vp_group2(job->tp, (uint32_t)(job->start + off), valid, dig);
      job->backend += 32;
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
    } else {
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
}

typedef struct {
  VPJob v;
  uint64_t begin, end;
} VPThreadJob;

static void *vp_worker(void *arg) {
  VPThreadJob *job = (VPThreadJob *)arg;
  VPJob v = job->v;
  v.start += job->begin;
  v.span = job->end - job->begin;
  if (v.hashes) v.hashes = job->v.hashes + 32 * (size_t)job->begin;
  if (v.flags) v.flags = job->v.flags + job->begin;
  v.attempted = 0;
  v.backend = 0;
  vp_walk(&v);
  job->v.attempted = v.attempted;
  job->v.backend = v.backend;
  return NULL;
}

static int vp_run(const uint8_t *header, uint64_t start, uint64_t count,
                 unsigned threads, const uint8_t *target,
                 BalSearchCtx *ctx, uint8_t *hashes, uint8_t *flags,
                 uint64_t *out_attempted, uint64_t *out_backend) {
  VTemplate tp;
  v_template_init(&tp, header);
  uint64_t begins[16], ends[16];
  unsigned spans = bal_partition(count, threads, begins, ends);
  pthread_t tids[16];
  int created[16] = {0};
  VPThreadJob jobs[16];
  for (unsigned sp = 0; sp < spans; sp++) {
    jobs[sp].v = (VPJob){&tp, start, 0, target, ctx, hashes, flags,
                        0, 0};
    jobs[sp].begin = begins[sp];
    jobs[sp].end = ends[sp];
    if (bal_pthread_create(&tids[sp], NULL, vp_worker, &jobs[sp]) != 0) {
      vp_worker(&jobs[sp]);
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

int bal_vp_batch2(const uint8_t *header, uint64_t start, uint64_t count,
                 unsigned threads, const uint8_t *target,
                 uint8_t *hashes, uint8_t *flags,
                 uint64_t *out_attempted, uint64_t *out_backend) {
  if (!header || !target || !hashes || !flags) return -1;
  if (!threads || threads > 16) return -1;
  int v = bal_validate_range(start, count);
  if (v != 0) return v;
  return vp_run(header, start, count, threads, target, NULL, hashes,
               flags, out_attempted, out_backend);
}

typedef struct {
  const VTemplate *tp;
  uint32_t sw[8];
  uint64_t start;
  uint64_t span;
  const uint8_t *target;
  BalSearchCtx *ctx;
  uint64_t attempted;
  uint64_t backend;
} VPRMJob;

static void vp_rm_walk(VPRMJob *job) {
  uint64_t off = 0;
  while (off < job->span) {
    if (bal_ctx_stopped(job->ctx)) break;
    uint64_t rem = job->span - off;
    if (rem >= 17) {
      int valid = rem >= 32 ? 32 : (int)rem;
      uint8_t dig[32][32];
      uint32_t m = vp_group2m(job->tp, job->sw,
                              (uint32_t)(job->start + off),
                              valid, dig);
      job->backend += 32;
      job->attempted += (uint64_t)valid;
      if (m) {
        int l = __builtin_ctz(m);
        bal_ctx_publish(job->ctx,
                        (uint32_t)(job->start + off + (uint64_t)l),
                        dig[l]);
      }
      off += (uint64_t)valid;
    } else {
      int valid = rem >= 16 ? 16 : (int)rem;
      uint8_t dig[16][32];
      v_group(job->tp, (uint32_t)(job->start + off), valid, dig);
      job->backend += 16;
      job->attempted += (uint64_t)valid;
      for (int l = 0; l < valid; l++) {
        if (v_meets(dig[l], job->target))
          bal_ctx_publish(job->ctx,
                          (uint32_t)(job->start + off + (uint64_t)l),
                          dig[l]);
      }
      off += (uint64_t)valid;
    }
  }
}

typedef struct {
  VPRMJob v;
  uint64_t begin, end;
} VPRMThreadJob;

static void *vp_rm_worker(void *arg) {
  VPRMThreadJob *job = (VPRMThreadJob *)arg;
  VPRMJob v = job->v;
  v.start += job->begin;
  v.span = job->end - job->begin;
  v.attempted = 0;
  v.backend = 0;
  vp_rm_walk(&v);
  job->v.attempted = v.attempted;
  job->v.backend = v.backend;
  return NULL;
}

int bal_vp_search2(const uint8_t *header, uint64_t start,
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
  rm_target_words(target, sw);
  BalSearchCtx ctx;
  if (bal_ctx_init(&ctx) != 0) return -4;
  uint64_t begins[16], ends[16];
  unsigned spans = bal_partition(count, threads, begins, ends);
  pthread_t tids[16];
  int created[16] = {0};
  VPRMThreadJob jobs[16];
  for (unsigned sp = 0; sp < spans; sp++) {
    jobs[sp].v = (VPRMJob){&tp, {0}, start, 0, target, &ctx, 0, 0};
    memcpy(jobs[sp].v.sw, sw, sizeof(sw));
    jobs[sp].begin = begins[sp];
    jobs[sp].end = ends[sp];
    if (bal_pthread_create(&tids[sp], NULL, vp_rm_worker,
                           &jobs[sp]) != 0) {
      vp_rm_worker(&jobs[sp]);
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
