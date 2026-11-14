/* NOVA SHA-X EXP-008 (X-009): cross-nonce phase
 * pipelining on the H-02/H-01 SHA-NI core. See the
 * wave machinery section for the design and the
 * declared accounting semantics. ABI: bal_p_batch2 /
 * bal_p_search2, counted, no streams parameter (the
 * pipeline depth is fixed at two phases).
 */
#include <stdint.h>
#include <string.h>
#include <stdatomic.h>
#include <pthread.h>

#include "shani_core.h"
#include "../../../../mining/cpu/bal_search.h"

#define GEO_MAXS 6

_Atomic int bal_create_fail_after = -1;
_Atomic int bal_create_fail_calls = 0;
_Atomic int bal_mutex_fail_mask = 0;

typedef struct {
  HRS s;
  __m128i m0, m1, m2, m3;
} MStream;

/* ---- interleaved group sequence, instantiated per NS ---- */
#define S_G0_B2(NS) \
  for (int si = 0; si < NS; si++) { MStream *sp = &streams[si]; \
    __m128i t_ = _mm_add_epi32(sp->m0, KV[0]); \
    t_ = _mm_shuffle_epi32(t_, 0x0E); \
    sp->s = h_rp(sp->s, t_); }
#define S_G0_FULL(NS) \
  for (int si = 0; si < NS; si++) { MStream *sp = &streams[si]; \
    __m128i t_ = _mm_add_epi32(sp->m0, KV[0]); \
    sp->s = h_rp(sp->s, t_); \
    t_ = _mm_shuffle_epi32(t_, 0x0E); \
    sp->s = h_rp(sp->s, t_); }
#define S_GRP(NS, MF, GI) \
  for (int si = 0; si < NS; si++) { MStream *sp = &streams[si]; \
    __m128i t_ = _mm_add_epi32(sp->MF, KV[GI]); \
    sp->s = h_rp(sp->s, t_); \
    t_ = _mm_shuffle_epi32(t_, 0x0E); \
    sp->s = h_rp(sp->s, t_); }
#define S_GENA(NS, FA, FB) \
  for (int si = 0; si < NS; si++) { MStream *sp = &streams[si]; \
    sp->FA = _mm_sha256msg1_epu32(sp->FA, sp->FB); }
#define S_GENB(NS, FY, FA, FB) \
  for (int si = 0; si < NS; si++) { MStream *sp = &streams[si]; \
    sp->FY = _mm_sha256msg2_epu32( \
      _mm_add_epi32(sp->FY, _mm_alignr_epi8(sp->FA, sp->FB, 4)), \
      sp->FA); }
#define S_TAIL(NS) \
  S_GENA(NS, m0, m1); \
  S_GRP(NS, m1, 1);  S_GENA(NS, m1, m2); S_GENB(NS, m0, m3, m2); \
  S_GRP(NS, m2, 2);  S_GENA(NS, m2, m3); S_GENB(NS, m1, m0, m3); \
  S_GRP(NS, m3, 3);  S_GENA(NS, m3, m0); S_GENB(NS, m2, m1, m0); \
  S_GRP(NS, m0, 4);  S_GENA(NS, m0, m1); S_GENB(NS, m3, m2, m1); \
  S_GRP(NS, m1, 5);  S_GENA(NS, m1, m2); S_GENB(NS, m0, m3, m2); \
  S_GRP(NS, m2, 6);  S_GENA(NS, m2, m3); S_GENB(NS, m1, m0, m3); \
  S_GRP(NS, m3, 7);  S_GENA(NS, m3, m0); S_GENB(NS, m2, m1, m0); \
  S_GRP(NS, m0, 8);  S_GENA(NS, m0, m1); S_GENB(NS, m3, m2, m1); \
  S_GRP(NS, m1, 9);  S_GENA(NS, m1, m2); S_GENB(NS, m0, m3, m2); \
  S_GRP(NS, m2, 10); S_GENA(NS, m2, m3); S_GENB(NS, m1, m0, m3); \
  S_GRP(NS, m3, 11); S_GENA(NS, m3, m0); S_GENB(NS, m2, m1, m0); \
  S_GRP(NS, m0, 12); S_GENB(NS, m3, m2, m1); \
  S_GRP(NS, m1, 13); S_GRP(NS, m2, 14); S_GRP(NS, m3, 15);
#define DEF_RUN(NS) \
  static void m_run_b2_##NS(MStream *streams, const __m128i *KV) { \
    S_G0_B2(NS); S_TAIL(NS); } \
  static void m_run_full_##NS(MStream *streams, const __m128i *KV) { \
    S_G0_FULL(NS); S_TAIL(NS); }
DEF_RUN(1)
DEF_RUN(2)
DEF_RUN(3)
DEF_RUN(4)
DEF_RUN(6)

static void run_b2(MStream *arr, int a, const __m128i *KV) {
  while (a >= 6) { m_run_b2_6(arr, KV); arr += 6; a -= 6; }
  if (a >= 4) { m_run_b2_4(arr, KV); arr += 4; a -= 4; }
  if (a >= 3) { m_run_b2_3(arr, KV); arr += 3; a -= 3; }
  if (a >= 2) { m_run_b2_2(arr, KV); arr += 2; a -= 2; }
  if (a == 1) m_run_b2_1(arr, KV);
}

static void run_full(MStream *arr, int a, const __m128i *KV) {
  while (a >= 6) { m_run_full_6(arr, KV); arr += 6; a -= 6; }
  if (a >= 4) { m_run_full_4(arr, KV); arr += 4; a -= 4; }
  if (a >= 3) { m_run_full_3(arr, KV); arr += 3; a -= 3; }
  if (a >= 2) { m_run_full_2(arr, KV); arr += 2; a -= 2; }
  if (a == 1) m_run_full_1(arr, KV);
}

/* ---- EXP-008 cross-nonce phase pipelining ----
 * One worker runs a two-stage software pipeline over the
 * span's nonces in order. Stage B2 computes block 2 of
 * nonce n+1 while stage OUT computes the outer compression
 * of nonce n, the two advanced in lockstep by the fused
 * mixed run below: at every step of the group sequence the
 * step is applied to both streams, so the two independent
 * RNDS2 latency chains (different phases, different data)
 * overlap exactly as two same-phase streams would.
 *
 * Accounting: attempted counts completed digests. In batch
 * mode every nonce's block 2 and outer run exactly once, so
 * attempted == backend work in hashes == count. In search
 * mode, when the outer stage publishes a winner, the block
 * 2 of the next nonce computed alongside it is real work
 * that produced no digest; it is NOT counted in attempted
 * (attempted counts digests examined), and this is the
 * declared semantics: attempted == winner_offset + 1 for a
 * single-threaded span walk.
 */

typedef struct {
  const HTemplate *tp;
  uint64_t start;
  const uint8_t *target;
  BalSearchCtx *ctx;
  uint8_t *hashes;
  uint8_t *flags;
  uint64_t attempted;
} PWave;

#define M_G0 \
  do { \
    __m128i t_ = _mm_add_epi32(X->m0, KV[0]); \
    t_ = _mm_shuffle_epi32(t_, 0x0E); \
    X->s = h_rp(X->s, t_); \
    t_ = _mm_add_epi32(Y->m0, KV[0]); \
    Y->s = h_rp(Y->s, t_); \
    t_ = _mm_shuffle_epi32(t_, 0x0E); \
    Y->s = h_rp(Y->s, t_); \
  } while (0)
#define M_GRP(MF, GI) \
  do { \
    __m128i t_ = _mm_add_epi32(X->MF, KV[GI]); \
    X->s = h_rp(X->s, t_); \
    t_ = _mm_shuffle_epi32(t_, 0x0E); \
    X->s = h_rp(X->s, t_); \
    t_ = _mm_add_epi32(Y->MF, KV[GI]); \
    Y->s = h_rp(Y->s, t_); \
    t_ = _mm_shuffle_epi32(t_, 0x0E); \
    Y->s = h_rp(Y->s, t_); \
  } while (0)
#define M_GENA(FA, FB) \
  do { \
    X->FA = _mm_sha256msg1_epu32(X->FA, X->FB); \
    Y->FA = _mm_sha256msg1_epu32(Y->FA, Y->FB); \
  } while (0)
#define M_GENB(FY, FA, FB) \
  do { \
    X->FY = _mm_sha256msg2_epu32( \
      _mm_add_epi32(X->FY, _mm_alignr_epi8(X->FA, X->FB, 4)), \
      X->FA); \
    Y->FY = _mm_sha256msg2_epu32( \
      _mm_add_epi32(Y->FY, _mm_alignr_epi8(Y->FA, Y->FB, 4)), \
      Y->FA); \
  } while (0)

static void run_mixed(MStream *X, MStream *Y, const __m128i *KV) {
  M_G0;
  M_GENA(m0, m1);
  M_GRP(m1, 1);  M_GENA(m1, m2); M_GENB(m0, m3, m2);
  M_GRP(m2, 2);  M_GENA(m2, m3); M_GENB(m1, m0, m3);
  M_GRP(m3, 3);  M_GENA(m3, m0); M_GENB(m2, m1, m0);
  M_GRP(m0, 4);  M_GENA(m0, m1); M_GENB(m3, m2, m1);
  M_GRP(m1, 5);  M_GENA(m1, m2); M_GENB(m0, m3, m2);
  M_GRP(m2, 6);  M_GENA(m2, m3); M_GENB(m1, m0, m3);
  M_GRP(m3, 7);  M_GENA(m3, m0); M_GENB(m2, m1, m0);
  M_GRP(m0, 8);  M_GENA(m0, m1); M_GENB(m3, m2, m1);
  M_GRP(m1, 9);  M_GENA(m1, m2); M_GENB(m0, m3, m2);
  M_GRP(m2, 10); M_GENA(m2, m3); M_GENB(m1, m0, m3);
  M_GRP(m3, 11); M_GENA(m3, m0); M_GENB(m2, m1, m0);
  M_GRP(m0, 12); M_GENB(m3, m2, m1);
  M_GRP(m1, 13); M_GRP(m2, 14); M_GRP(m3, 15);
}

static void p_setup_b2(MStream *X, const HTemplate *tp,
                       uint32_t nonce) {
  X->s = tp->snap1;
  X->m0 = _mm_set_epi32((int)h_bswap32(nonce), (int)tp->w2,
                        (int)tp->w1, (int)tp->w0);
  X->m1 = _mm_set_epi32(0, 0, 0, (int)0x80000000);
  X->m2 = _mm_setzero_si128();
  X->m3 = _mm_set_epi32(640, 0, 0, 0);
}

static void p_setup_out(MStream *Y, const uint32_t inner[8]) {
  Y->s = h_load_state(H02_H0);
  Y->m0 = _mm_set_epi32((int)inner[3], (int)inner[2],
                        (int)inner[1], (int)inner[0]);
  Y->m1 = _mm_set_epi32((int)inner[7], (int)inner[6],
                        (int)inner[5], (int)inner[4]);
  Y->m2 = _mm_set_epi32(0, 0, 0, (int)0x80000000);
  Y->m3 = _mm_set_epi32(256, 0, 0, 0);
}

static void p_inner(const PWave *w, const MStream *X,
                    uint32_t inner[8]) {
  uint32_t fin[8];
  h_store_state(X->s, fin);
  for (int j = 0; j < 8; j++) inner[j] = w->tp->mid[j] + fin[j];
}

static void p_digest(const MStream *Y, uint8_t dig[32]) {
  uint32_t fin[8];
  h_store_state(Y->s, fin);
  for (int j = 0; j < 8; j++) {
    uint32_t v = H02_H0[j] + fin[j];
    dig[4 * j] = (uint8_t)(v >> 24);
    dig[4 * j + 1] = (uint8_t)(v >> 16);
    dig[4 * j + 2] = (uint8_t)(v >> 8);
    dig[4 * j + 3] = (uint8_t)v;
  }
}

/* Walk one span [0, span) through the pipeline. */
static void walk_span_pipe(PWave *w, uint64_t span) {
  __m128i KV[16];
  h_kv(KV);
  if (!span) return;
  MStream X, Y;
  uint32_t inner[8];
  p_setup_b2(&X, w->tp, (uint32_t)w->start);
  {
    MStream one[1];
    one[0] = X;
    run_b2(one, 1, KV);
    X = one[0];
  }
  p_inner(w, &X, inner);
  p_setup_out(&Y, inner);
  for (uint64_t i = 0; i < span; i++) {
    if (w->ctx && bal_ctx_stopped(w->ctx)) break;
    int have_next = (i + 1 < span);
    if (have_next) {
      p_setup_b2(&X, w->tp, (uint32_t)(w->start + i + 1));
      run_mixed(&X, &Y, KV);
    } else {
      MStream one[1];
      one[0] = Y;
      run_full(one, 1, KV);
      Y = one[0];
    }
    uint8_t dig[32];
    p_digest(&Y, dig);
    w->attempted += 1;
    if (w->ctx) {
      if (h_meets(dig, w->target))
        bal_ctx_publish(w->ctx, (uint32_t)(w->start + i), dig);
    } else {
      memcpy(w->hashes + 32 * (size_t)i, dig, 32);
      w->flags[i] = h_meets(dig, w->target) ? 1 : 0;
    }
    if (have_next) {
      p_inner(w, &X, inner);
      p_setup_out(&Y, inner);
    }
  }
}

/* ---- batch ---- */

typedef struct {
  PWave w;
  uint64_t begin, end;
} PJob;

static void *p_worker(void *arg) {
  PJob *job = (PJob *)arg;
  PWave w = job->w;
  w.start += job->begin;
  w.hashes = job->w.hashes + 32 * (size_t)job->begin;
  w.flags = job->w.flags + job->begin;
  w.attempted = 0;
  walk_span_pipe(&w, job->end - job->begin);
  job->w.attempted = w.attempted;
  return NULL;
}

int bal_p_batch2(const uint8_t *header, uint64_t start, uint64_t count,
                 unsigned threads, const uint8_t *target,
                 uint8_t *hashes, uint8_t *flags,
                 uint64_t *out_attempted) {
  if (!header || !target || !hashes || !flags) return -1;
  if (!threads || threads > 16) return -1;
  int v = bal_validate_range(start, count);
  if (v != 0) return v;
  HTemplate tp;
  h_template_init(&tp, header);
  uint64_t begins[16], ends[16];
  unsigned spans = bal_partition(count, threads, begins, ends);
  pthread_t tids[16];
  int created[16] = {0};
  PJob jobs[16];
  for (unsigned sp = 0; sp < spans; sp++) {
    jobs[sp].w = (PWave){&tp, start, target, NULL, hashes, flags, 0};
    jobs[sp].begin = begins[sp];
    jobs[sp].end = ends[sp];
    if (bal_pthread_create(&tids[sp], NULL, p_worker, &jobs[sp]) != 0) {
      p_worker(&jobs[sp]);
    } else {
      created[sp] = 1;
    }
  }
  for (unsigned sp = 0; sp < spans; sp++)
    if (created[sp]) pthread_join(tids[sp], NULL);
  if (out_attempted) {
    uint64_t total = 0;
    for (unsigned sp = 0; sp < spans; sp++) total += jobs[sp].w.attempted;
    *out_attempted = total;
  }
  return 0;
}

/* ---- search ---- */

typedef struct {
  PWave w;
  uint64_t begin, end;
} PSJob;

static void *p_sworker(void *arg) {
  PSJob *job = (PSJob *)arg;
  PWave w = job->w;
  w.start += job->begin;
  w.attempted = 0;
  walk_span_pipe(&w, job->end - job->begin);
  job->w.attempted = w.attempted;
  return NULL;
}

int bal_p_search2(const uint8_t *header, uint64_t start, uint64_t count,
                  unsigned threads, const uint8_t *target,
                  uint32_t *out_nonce, uint8_t *out_digest,
                  uint64_t *out_attempted) {
  if (!header || !target || !out_nonce || !out_digest) return -1;
  if (!threads || threads > 16) return -1;
  int v = bal_validate_range(start, count);
  if (v != 0) return v;
  HTemplate tp;
  h_template_init(&tp, header);
  BalSearchCtx ctx;
  if (bal_ctx_init(&ctx) != 0) return -4;
  uint64_t begins[16], ends[16];
  unsigned spans = bal_partition(count, threads, begins, ends);
  pthread_t tids[16];
  int created[16] = {0};
  PSJob jobs[16];
  for (unsigned sp = 0; sp < spans; sp++) {
    jobs[sp].w = (PWave){&tp, start, target, &ctx, NULL, NULL, 0};
    jobs[sp].begin = begins[sp];
    jobs[sp].end = ends[sp];
    if (bal_pthread_create(&tids[sp], NULL, p_sworker, &jobs[sp]) != 0) {
      p_sworker(&jobs[sp]);
    } else {
      created[sp] = 1;
    }
  }
  for (unsigned sp = 0; sp < spans; sp++)
    if (created[sp]) pthread_join(tids[sp], NULL);
  if (out_attempted) {
    uint64_t total = 0;
    for (unsigned sp = 0; sp < spans; sp++) total += jobs[sp].w.attempted;
    *out_attempted = total;
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
