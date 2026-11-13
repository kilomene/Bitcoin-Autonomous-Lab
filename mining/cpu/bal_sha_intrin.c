/* Hand-written SHA-256 compression on the Intel SHA extensions
 * (sha_ni), following the instruction semantics in Intel's SHA
 * extensions whitepaper:
 *
 *   SHA256RNDS2 performs two rounds. Operands are organised as
 *   STATE0 = [A, B, E, F] and STATE1 = [C, D, G, H] in 32-bit
 *   lanes from most significant lane to least; the message
 *   operand supplies K+W for the two rounds in its low 64 bits.
 *   SHA256MSG1 / SHA256MSG2 advance the message schedule.
 *
 * On top of the raw rounds this kernel adds mining structure:
 * a snapshot of the inner state after round 2 (the nonce enters
 * the schedule only at W3, i.e. round 3), so per nonce the inner
 * compression resumes at round 3 with W0..W2 already folded in.
 *
 * Exported ABI mirrors bal_batch.c: bal_i_batch / bal_i_search
 * with identical semantics, so the A/B comparison is drop-in.
 * Correctness is never assumed: the host test and the Python
 * cross-checks decide whether this library is used at all.
 */

#include <stdint.h>
#include <string.h>
#include <stdalign.h>
#include <pthread.h>
#include <immintrin.h>

#if !defined(__SHA__)
#error "compile with -msha"
#endif

static const uint32_t K256[64] = {
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

static const uint32_t H0[8] = {0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,
                               0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19};

/* The Intel round organisation, established empirically in this
 * lab against the Python reference (see docs/CPU_PEAK2.md):
 * state lives in two vectors in "org form": ABEF holds lanes
 * (f, e, b, a) low to high, CDGH holds (h, g, d, c). One
 * SHA256RNDS2 call performs two rounds: RNDS2(cdgh_form,
 * abef_form, wk) returns the next abef_form, and the two vectors
 * then rotate: the old abef_form becomes the next call's
 * cdgh_form. We track (prev, cur): cur is the current abef_form,
 * prev is the vector that will serve as cdgh_form next. After
 * the final call, cur is the final abef_form and prev is the
 * final cdgh_form. */
typedef struct { __m128i prev, cur; } RoundState;

static inline RoundState run_rounds(RoundState st,
                                    const uint32_t *W, int r0, int r1) {
  for (int r = r0; r < r1; r += 2) {
    __m128i msg = _mm_set_epi32(0, 0,
                                (int)(W[r + 1] + K256[r + 1]),
                                (int)(W[r] + K256[r]));
    __m128i nxt = _mm_sha256rnds2_epu32(st.prev, st.cur, msg);
    st.prev = st.cur;
    st.cur = nxt;
  }
  return st;
}

static inline RoundState load_state(const uint32_t h[8]) {
  RoundState st;
  st.cur = _mm_set_epi32((int)h[0], (int)h[1], (int)h[4], (int)h[5]);
  st.prev = _mm_set_epi32((int)h[2], (int)h[3], (int)h[6], (int)h[7]);
  return st;
}

static inline void store_state(RoundState st, uint32_t h[8]) {
  alignas(16) uint32_t t0[4], t1[4];
  _mm_store_si128((__m128i *)t0, st.cur);   /* lanes f, e, b, a */
  _mm_store_si128((__m128i *)t1, st.prev);  /* lanes h, g, d, c */
  h[0] = t0[3]; h[1] = t0[2]; h[4] = t0[1]; h[5] = t0[0];
  h[2] = t1[3]; h[3] = t1[2]; h[6] = t1[1]; h[7] = t1[0];
}

static void schedule_impl(uint32_t *W);

/* Full compression: out = in + compress(in, block_words_be). */
static void compress(const uint32_t in[8], const uint32_t *words,
                     uint32_t out[8]) {
  uint32_t W[64];
  memcpy(W, words, 64);
  schedule_impl(W);
  RoundState st = load_state(in);
  st = run_rounds(st, W, 0, 64);
  uint32_t fin[8];
  store_state(st, fin);
  for (int i = 0; i < 8; i++) out[i] = in[i] + fin[i];
}

static uint32_t load_be32(const uint8_t *p) {
  return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) |
         ((uint32_t)p[2] << 8) | (uint32_t)p[3];
}

static void midstate_of(const uint8_t *header, uint32_t mid[8]) {
  uint32_t words[16];
  for (int i = 0; i < 16; i++) words[i] = load_be32(header + 4 * i);
  compress(H0, words, mid);
}

/* Per-template snapshot: inner block words W[0..2] come from the
 * header tail, W[3] is the nonce word, W[4] is the padding bit,
 * W[15] is 640. The nonce first enters at round 3 (as W[3]), so
 * rounds 0 and 1 are nonce-independent: the state after round 1
 * is snapshotted once per template and every nonce resumes at
 * round 2. The schedule is recomputed per nonce (it depends on
 * the nonce transitively from W[18] onward). */
typedef struct {
  uint32_t mid[8];
  RoundState snap; /* round state after round 1 */
  uint32_t w0, w1, w2;
} Template;

static void schedule_impl(uint32_t *W) {
  for (int i = 16; i < 64; i++) {
    uint32_t x = W[i - 15], y = W[i - 2];
    uint32_t s0 = ((x >> 7) | (x << 25)) ^ ((x >> 18) | (x << 14)) ^ (x >> 3);
    uint32_t s1 = ((y >> 17) | (y << 15)) ^ ((y >> 19) | (y << 13)) ^ (y >> 10);
    W[i] = W[i - 16] + s0 + W[i - 7] + s1;
  }
}

static void template_init(Template *tp, const uint8_t *header) {
  midstate_of(header, tp->mid);
  tp->w0 = load_be32(header + 64);
  tp->w1 = load_be32(header + 68);
  tp->w2 = load_be32(header + 72);
  uint32_t W[64] = {0};
  W[0] = tp->w0; W[1] = tp->w1; W[2] = tp->w2;
  W[4] = 0x80000000;
  W[15] = 640;
  schedule_impl(W);
  RoundState st = load_state(tp->mid);
  tp->snap = run_rounds(st, W, 0, 2);
}

/* One double hash using the template. Returns digest bytes. */
static void hash_nonce(const Template *tp, uint32_t nonce,
                       uint8_t digest[32]) {
  uint32_t W[64] = {0};
  W[0] = tp->w0; W[1] = tp->w1; W[2] = tp->w2;
  W[3] = ((nonce & 0xff) << 24) | ((nonce & 0xff00) << 8) |
         ((nonce >> 8) & 0xff00) | ((nonce >> 24) & 0xff);
  W[4] = 0x80000000;
  W[15] = 640;
  schedule_impl(W);
  RoundState st = run_rounds(tp->snap, W, 2, 64);
  uint32_t fin[8], inner[8];
  store_state(st, fin);
  for (int i = 0; i < 8; i++) inner[i] = tp->mid[i] + fin[i];
  /* outer block: inner digest words then padding, length 256 */
  uint32_t OW[64] = {0};
  memcpy(OW, inner, 32);
  OW[8] = 0x80000000;
  OW[15] = 256;
  compress(H0, OW, fin);
  for (int i = 0; i < 8; i++) {
    digest[4 * i] = (uint8_t)(fin[i] >> 24);
    digest[4 * i + 1] = (uint8_t)(fin[i] >> 16);
    digest[4 * i + 2] = (uint8_t)(fin[i] >> 8);
    digest[4 * i + 3] = (uint8_t)fin[i];
  }
}

static int meets(const uint8_t *digest, const uint8_t *target_le) {
  for (int i = 31; i >= 0; i--) {
    if (digest[i] != target_le[i]) return digest[i] < target_le[i];
  }
  return 1;
}

/* ---- batch ABI (identical semantics to bal_batch.c) ---- */

typedef struct {
  const Template *tp;
  uint64_t start;
  uint32_t begin, end;
  const uint8_t *target;
  uint8_t *hashes, *flags;
} Job;

static void *worker(void *arg) {
  Job *job = (Job *)arg;
  for (uint32_t i = job->begin; i < job->end; i++) {
    uint8_t d[32];
    hash_nonce(job->tp, (uint32_t)(job->start + i), d);
    memcpy(job->hashes + 32 * (size_t)i, d, 32);
    job->flags[i] = meets(d, job->target) ? 1 : 0;
  }
  return NULL;
}

int bal_i_batch(const uint8_t *header, uint64_t start, uint32_t count,
                unsigned threads, const uint8_t *target, uint8_t *hashes,
                uint8_t *flags) {
  if (!count || !threads || threads > 16) return -1;
  if (start + count > 0x100000000ULL) return -1;
  Template tp;
  template_init(&tp, header);
  if (threads > count) threads = count;
  pthread_t tids[16];
  Job jobs[16];
  uint32_t chunk = (count + threads - 1) / threads;
  unsigned launched = 0, spans = 0;
  for (unsigned t = 0; t < threads; t++) {
    uint32_t begin = t * chunk;
    if (begin >= count) break;
    uint32_t end = begin + chunk;
    if (end > count) end = count;
    jobs[spans] = (Job){&tp, start, begin, end, target, hashes, flags};
    if (pthread_create(&tids[spans], NULL, worker, &jobs[spans]) != 0) {
      worker(&jobs[spans]);
    } else {
      launched++;
    }
    spans++;
  }
  for (unsigned t = 0; t < launched; t++) pthread_join(tids[t], NULL);
  return 0;
}

/* ---- early-exit search ABI ---- */

static volatile int g_stop;
static volatile uint32_t g_found_nonce;
static uint8_t g_found_digest[32];

typedef struct {
  const Template *tp;
  uint64_t start;
  uint32_t begin, end;
  const uint8_t *target;
} SJob;

static void *sworker(void *arg) {
  SJob *job = (SJob *)arg;
  for (uint32_t i = job->begin; i < job->end && !g_stop; i++) {
    uint8_t d[32];
    uint32_t nonce = (uint32_t)(job->start + i);
    hash_nonce(job->tp, nonce, d);
    if (meets(d, job->target)) {
      if (!g_stop) {
        memcpy(g_found_digest, d, 32);
        g_found_nonce = nonce;
      }
      g_stop = 1;
      return NULL;
    }
  }
  return NULL;
}

int bal_i_search(const uint8_t *header, uint64_t start, uint32_t count,
                 unsigned threads, const uint8_t *target,
                 uint32_t *out_nonce, uint8_t *out_digest) {
  if (!count || !threads || threads > 16) return -1;
  if (start + count > 0x100000000ULL) return -1;
  Template tp;
  template_init(&tp, header);
  if (threads > count) threads = count;
  g_stop = 0;
  pthread_t tids[16];
  SJob jobs[16];
  uint32_t chunk = (count + threads - 1) / threads;
  unsigned launched = 0, spans = 0;
  for (unsigned t = 0; t < threads; t++) {
    uint32_t begin = t * chunk;
    if (begin >= count) break;
    uint32_t end = begin + chunk;
    if (end > count) end = count;
    jobs[spans] = (SJob){&tp, start, begin, end, target};
    if (pthread_create(&tids[spans], NULL, sworker, &jobs[spans]) != 0) {
      sworker(&jobs[spans]);
    } else {
      launched++;
    }
    spans++;
  }
  for (unsigned t = 0; t < launched; t++) pthread_join(tids[t], NULL);
  if (g_stop) {
    *out_nonce = g_found_nonce;
    memcpy(out_digest, g_found_digest, 32);
    return 1;
  }
  return 0;
}
