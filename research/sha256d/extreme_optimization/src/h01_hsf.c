/* NOVA SHA-X EXP-006: hand-scheduled schedule-first variant of the
 * EXP-005 geometry kernel (same ABI, same geometry).
 *
 * Built on the H-02 core (shani_core.h): the same MSG1/MSG2
 * schedule machinery and org-form state rotation, but NS
 * independent nonce streams are advanced in lockstep inside
 * one worker: at every step of the unrolled group sequence,
 * the step is applied to each stream in turn, so the
 * SHA256RNDS2 latency chains of the streams overlap instead
 * of serializing. Streams are NOT threads: one OS thread runs
 * all NS streams of its span.
 *
 * EXP-005 changes versus EXP-003:
 * - Stream counts 3 and 6 added (instantiations DEF_RUN(3),
 *   DEF_RUN(6)); wave dispatch is greedy 6, 4, 3, 2, 1.
 * - A mode parameter selects the nonce assignment geometry:
 *   mode 0 = blocked (each stream owns one contiguous chunk
 *   of the span, the EXP-003 geometry); mode 1 = strided
 *   (stream si takes span offsets si, si+NS, si+2NS, ...).
 *   Coverage is exact and disjoint under both modes.
 *
 * Waves run the currently active streams compacted together;
 * a partial final wave dispatches to the smaller
 * instantiations, so no dummy nonce is ever hashed or
 * counted. Attempted counts are exact for batch (== count on
 * completion). For search, a wave is the atomic unit: when
 * one stream publishes a winner, the other streams' hashes
 * in that same wave were really computed and are counted in
 * attempted. Winner semantics are the lab standard: first
 * published under the shared mutex, not the lowest nonce.
 *
 * Exports mirror the counted ABI plus streams and mode:
 *   bal_m_batch2 / bal_m_search2: blocked assignment (mode 0),
 *     the EXP-003 ABI, streams in {1, 2, 3, 4, 6}.
 *   bal_m_batch2m / bal_m_search2m: same plus a mode argument
 *     (0 blocked, 1 strided) before the target pointer.
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
/* ---- EXP-006 schedule-first run functions ----
 * Technique (a): the full MSG1/MSG2 schedule of every stream
 * in the wave is expanded FIRST, into a stack-resident W
 * array (the GENA/GENB sequence transcribed from
 * h_run_groups with the round calls removed), and only then
 * do the rounds run. During the rounds phase the live set
 * per stream is just the two state vectors plus one wk
 * temporary, and the K vector for a group is loaded once
 * and shared by all streams (technique (b): fused K reuse).
 * The expansion phase itself keeps at most the four rotating
 * message vectors per stream, one stream at a time. */

static inline void sf_expand(const MStream *sp, __m128i W[16]) {
  __m128i m0 = sp->m0, m1 = sp->m1, m2 = sp->m2, m3 = sp->m3;
#define SF_GENA(Ma, Mb) do { (Ma) = _mm_sha256msg1_epu32((Ma), (Mb)); } while (0)
#define SF_GENB(My, Ma, Mb) do { \
    (My) = _mm_sha256msg2_epu32( \
      _mm_add_epi32((My), _mm_alignr_epi8((Ma), (Mb), 4)), (Ma)); } while (0)
  W[0] = m0;                 SF_GENA(m0, m1);
  W[1] = m1;                 SF_GENA(m1, m2); SF_GENB(m0, m3, m2);
  W[2] = m2;                 SF_GENA(m2, m3); SF_GENB(m1, m0, m3);
  W[3] = m3;                 SF_GENA(m3, m0); SF_GENB(m2, m1, m0);
  W[4] = m0;                 SF_GENA(m0, m1); SF_GENB(m3, m2, m1);
  W[5] = m1;                 SF_GENA(m1, m2); SF_GENB(m0, m3, m2);
  W[6] = m2;                 SF_GENA(m2, m3); SF_GENB(m1, m0, m3);
  W[7] = m3;                 SF_GENA(m3, m0); SF_GENB(m2, m1, m0);
  W[8] = m0;                 SF_GENA(m0, m1); SF_GENB(m3, m2, m1);
  W[9] = m1;                 SF_GENA(m1, m2); SF_GENB(m0, m3, m2);
  W[10] = m2;                SF_GENA(m2, m3); SF_GENB(m1, m0, m3);
  W[11] = m3;                SF_GENA(m3, m0); SF_GENB(m2, m1, m0);
  W[12] = m0;                SF_GENB(m3, m2, m1);
  W[13] = m1; W[14] = m2; W[15] = m3;
#undef SF_GENA
#undef SF_GENB
}

static void sf_run(MStream *streams, int ns, const __m128i *KV,
                   int full) {
  __m128i W[GEO_MAXS][16];
  for (int si = 0; si < ns; si++) sf_expand(&streams[si], W[si]);
  for (int g = 0; g < 16; g++) {
    for (int si = 0; si < ns; si++) {
      MStream *sp = &streams[si];
      __m128i t_ = _mm_add_epi32(W[si][g], KV[g]);
      if (full || g > 0) sp->s = h_rp(sp->s, t_);
      t_ = _mm_shuffle_epi32(t_, 0x0E);
      sp->s = h_rp(sp->s, t_);
    }
  }
}

static void run_b2(MStream *arr, int a, const __m128i *KV) {
  sf_run(arr, a, KV, 0);
}

static void run_full(MStream *arr, int a, const __m128i *KV) {
  sf_run(arr, a, KV, 1);
}

/* ---- wave machinery shared by batch and search ---- */

typedef struct {
  const HTemplate *tp;
  uint64_t start;      /* absolute nonce of span offset 0 */
  const uint8_t *target;
  int streams;
  int mode;            /* 0 blocked, 1 strided */
  BalSearchCtx *ctx;   /* search only; NULL for batch */
  uint8_t *hashes;     /* batch only */
  uint8_t *flags;      /* batch only */
  uint64_t attempted;
} MWave;

/* Hash one wave of up to `a` nonces (given as span-relative
 * indices in rel[]) through block 2 and the outer hash,
 * interleaved. Digests land in dig[][32]. */
static void wave_hash(MWave *w, MStream *arr, const uint64_t *rel,
                      int a, const __m128i *KV,
                      uint8_t dig[][32]) {
  const HTemplate *tp = w->tp;
  for (int i = 0; i < a; i++) {
    uint32_t nonce = (uint32_t)(w->start + rel[i]);
    arr[i].s = tp->snap1;
    arr[i].m0 = _mm_set_epi32((int)h_bswap32(nonce), (int)tp->w2,
                              (int)tp->w1, (int)tp->w0);
    arr[i].m1 = _mm_set_epi32(0, 0, 0, (int)0x80000000);
    arr[i].m2 = _mm_setzero_si128();
    arr[i].m3 = _mm_set_epi32(640, 0, 0, 0);
  }
  run_b2(arr, a, KV);
  uint32_t inner[GEO_MAXS][8];
  for (int i = 0; i < a; i++) {
    uint32_t fin[8];
    h_store_state(arr[i].s, fin);
    for (int j = 0; j < 8; j++) inner[i][j] = tp->mid[j] + fin[j];
    arr[i].s = h_load_state(H02_H0);
    arr[i].m0 = _mm_set_epi32((int)inner[i][3], (int)inner[i][2],
                              (int)inner[i][1], (int)inner[i][0]);
    arr[i].m1 = _mm_set_epi32((int)inner[i][7], (int)inner[i][6],
                              (int)inner[i][5], (int)inner[i][4]);
    arr[i].m2 = _mm_set_epi32(0, 0, 0, (int)0x80000000);
    arr[i].m3 = _mm_set_epi32(256, 0, 0, 0);
  }
  run_full(arr, a, KV);
  for (int i = 0; i < a; i++) {
    uint32_t fin[8];
    h_store_state(arr[i].s, fin);
    for (int j = 0; j < 8; j++) {
      uint32_t v = H02_H0[j] + fin[j];
      dig[i][4 * j] = (uint8_t)(v >> 24);
      dig[i][4 * j + 1] = (uint8_t)(v >> 16);
      dig[i][4 * j + 2] = (uint8_t)(v >> 8);
      dig[i][4 * j + 3] = (uint8_t)v;
    }
  }
}

/* Walk one span [0, span) in waves. Returns via w->attempted.
 * Blocked mode: bal_partition splits the span into per-stream
 * contiguous chunks. Strided mode: stream si owns offsets
 * si, si+NS, si+2NS, ...; chunk bounds sb/se are unused and
 * the per-stream element count is ceil((span - si) / NS). */
static void walk_span(MWave *w, uint64_t span) {
  __m128i KV[16];
  h_kv(KV);
  uint64_t sb[GEO_MAXS], se[GEO_MAXS];
  unsigned nsp = bal_partition(span, (unsigned)w->streams, sb, se);
  uint64_t pos[GEO_MAXS] = {0};
  MStream arr[GEO_MAXS];
  for (;;) {
    if (w->ctx && bal_ctx_stopped(w->ctx)) break;
    uint64_t rel[GEO_MAXS];
    int a = 0;
    for (unsigned si = 0; si < nsp; si++) {
      if (w->mode == 1) {
        uint64_t idx = (uint64_t)si + pos[si] * (uint64_t)w->streams;
        if (idx >= span) continue;
        rel[a++] = idx;
      } else {
        if (sb[si] + pos[si] >= se[si]) continue;
        rel[a++] = sb[si] + pos[si];
      }
      pos[si]++;
    }
    if (!a) break;
    uint8_t dig[GEO_MAXS][32];
    wave_hash(w, arr, rel, a, KV, dig);
    w->attempted += (uint64_t)a;
    for (int i = 0; i < a; i++) {
      if (w->ctx) {
        if (h_meets(dig[i], w->target)) {
          bal_ctx_publish(w->ctx, (uint32_t)(w->start + rel[i]),
                          dig[i]);
        }
      } else {
        memcpy(w->hashes + 32 * (size_t)rel[i], dig[i], 32);
        w->flags[rel[i]] = h_meets(dig[i], w->target) ? 1 : 0;
      }
    }
  }
}

/* ---- batch ---- */

typedef struct {
  MWave w;
  uint64_t begin, end;
} MJob;

static void *m_worker(void *arg) {
  MJob *job = (MJob *)arg;
  MWave w = job->w;
  w.start += job->begin;
  w.hashes = job->w.hashes + 32 * (size_t)job->begin;
  w.flags = job->w.flags + job->begin;
  w.attempted = 0;
  walk_span(&w, job->end - job->begin);
  job->w.attempted = w.attempted;
  return NULL;
}

static int valid_streams(int streams) {
  return streams == 1 || streams == 2 || streams == 3 ||
         streams == 4 || streams == 6;
}

static int batch_impl(const uint8_t *header, uint64_t start,
                      uint64_t count, unsigned threads, int streams,
                      int mode, const uint8_t *target,
                      uint8_t *hashes, uint8_t *flags,
                      uint64_t *out_attempted) {
  if (!header || !target || !hashes || !flags) return -1;
  if (!threads || threads > 16) return -1;
  if (!valid_streams(streams)) return -1;
  if (mode != 0 && mode != 1) return -1;
  int v = bal_validate_range(start, count);
  if (v != 0) return v;
  HTemplate tp;
  h_template_init(&tp, header);
  uint64_t begins[16], ends[16];
  unsigned spans = bal_partition(count, threads, begins, ends);
  pthread_t tids[16];
  int created[16] = {0};
  MJob jobs[16];
  for (unsigned sp = 0; sp < spans; sp++) {
    jobs[sp].w = (MWave){&tp, start, target, streams, mode, NULL,
                         hashes, flags, 0};
    jobs[sp].begin = begins[sp];
    jobs[sp].end = ends[sp];
    if (bal_pthread_create(&tids[sp], NULL, m_worker, &jobs[sp]) != 0) {
      m_worker(&jobs[sp]);
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
  MWave w;
  uint64_t begin, end;
} MSJob;

static void *m_sworker(void *arg) {
  MSJob *job = (MSJob *)arg;
  MWave w = job->w;
  w.start += job->begin;
  w.attempted = 0;
  walk_span(&w, job->end - job->begin);
  job->w.attempted = w.attempted;
  return NULL;
}

static int search_impl(const uint8_t *header, uint64_t start,
                       uint64_t count, unsigned threads, int streams,
                       int mode, const uint8_t *target,
                       uint32_t *out_nonce, uint8_t *out_digest,
                       uint64_t *out_attempted) {
  if (!header || !target || !out_nonce || !out_digest) return -1;
  if (!threads || threads > 16) return -1;
  if (!valid_streams(streams)) return -1;
  if (mode != 0 && mode != 1) return -1;
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
  MSJob jobs[16];
  for (unsigned sp = 0; sp < spans; sp++) {
    jobs[sp].w = (MWave){&tp, start, target, streams, mode, &ctx,
                         NULL, NULL, 0};
    jobs[sp].begin = begins[sp];
    jobs[sp].end = ends[sp];
    if (bal_pthread_create(&tids[sp], NULL, m_sworker, &jobs[sp]) != 0) {
      m_sworker(&jobs[sp]);
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

/* ---- public ABI ---- */

int bal_m_batch2(const uint8_t *header, uint64_t start, uint64_t count,
                 unsigned threads, int streams, const uint8_t *target,
                 uint8_t *hashes, uint8_t *flags,
                 uint64_t *out_attempted) {
  return batch_impl(header, start, count, threads, streams, 0,
                    target, hashes, flags, out_attempted);
}

int bal_m_batch2m(const uint8_t *header, uint64_t start, uint64_t count,
                  unsigned threads, int streams, int mode,
                  const uint8_t *target, uint8_t *hashes,
                  uint8_t *flags, uint64_t *out_attempted) {
  return batch_impl(header, start, count, threads, streams, mode,
                    target, hashes, flags, out_attempted);
}

int bal_m_search2(const uint8_t *header, uint64_t start, uint64_t count,
                  unsigned threads, int streams, const uint8_t *target,
                  uint32_t *out_nonce, uint8_t *out_digest,
                  uint64_t *out_attempted) {
  return search_impl(header, start, count, threads, streams, 0,
                     target, out_nonce, out_digest, out_attempted);
}

int bal_m_search2m(const uint8_t *header, uint64_t start, uint64_t count,
                   unsigned threads, int streams, int mode,
                   const uint8_t *target, uint32_t *out_nonce,
                   uint8_t *out_digest, uint64_t *out_attempted) {
  return search_impl(header, start, count, threads, streams, mode,
                     target, out_nonce, out_digest, out_attempted);
}
