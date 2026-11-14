/* EXP-019 (Y-002, Y-001): microbenchmark for the four-operand
 * schedule sum W[t] = a + b + c + d (mod 2^32 per lane), where
 * the operand roles in the multi-buffer kernel are
 *   a = W[t-16], b = sigma0(W[t-15]),
 *   c = W[t-7],  d = sigma1(W[t-2]).
 *
 * Forms priced (all exact, all verified below):
 *   current_serial : the shape the production compiler emits
 *                    in the hot loop, ((a + b) + c) + d,
 *                    3 VPADDD in one dependency chain.
 *   balanced_tree  : (a + b) + (c + d), 3 VPADDD, depth 2.
 *                    Control only: it is a reassociation
 *                    (Y-003 territory), not a carry-save form.
 *   cs1_resolved   : one carry-save level on (a, b, c), then
 *                    resolve the pair and add d.
 *   csfull_resolved: two carry-save levels on all four
 *                    operands, then one carry-propagate add.
 *   sigma_led_cs1  : one carry-save level on (b, d, a), the
 *                    two sigma terms plus the oldest direct
 *                    word, then resolve and add c.
 *
 * A SIMD 3:2 compressor costs three vector instructions on
 * this instruction set, not two: VPTERNLOGD for the parity
 * (sum) output, VPTERNLOGD for the majority (carry) output,
 * and VPSLLD to align the carry vector to the bit positions
 * it carries into. The carry alignment shift is a real
 * instruction in software; only in wiring does it vanish.
 *
 * Bench model: a ring of `depth` independent vector chains.
 * Each iteration feeds one chain's previous output back as
 * operand a, with b, c, d streamed from L2-resident arrays.
 * depth = separation + 1, so separation 0 is immediate
 * feedback and separation s means s independent vector sums
 * issue between a word's production and its next dependent
 * use. The actual recurrence's separations are 0 (the fused
 * round's T1), 1 (sigma1 use at t+2), 6 (direct use at
 * t+7), 14 (sigma0 use at t+15) and 15 (direct use at
 * t+16).
 *
 * Output: one JSON object per timed block on stdout.
 * Modes: verify | bench <depth> <iterations> <repeats> <seed>
 */
#include <immintrin.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#ifndef DATA_VECTORS
#define DATA_VECTORS 1024
#endif
#define MAX_DEPTH 16
#define NFORMS 5

static uint64_t splitmix64(uint64_t *state) {
  uint64_t z = (*state += 0x9e3779b97f4a7c15ULL);
  z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9ULL;
  z = (z ^ (z >> 27)) * 0x94d049bb133111ebULL;
  return z ^ (z >> 31);
}

static inline __m512i csa_sum(__m512i a, __m512i b, __m512i c) {
  return _mm512_ternarylogic_epi32(a, b, c, 0x96);
}

static inline __m512i csa_carry(__m512i a, __m512i b, __m512i c) {
  return _mm512_slli_epi32(
      _mm512_ternarylogic_epi32(a, b, c, 0xE8), 1);
}

static inline __m512i sum_current_serial(__m512i a, __m512i b,
                                         __m512i c, __m512i d) {
  __m512i t = _mm512_add_epi32(a, b);
  t = _mm512_add_epi32(t, c);
  return _mm512_add_epi32(t, d);
}

static inline __m512i sum_balanced_tree(__m512i a, __m512i b,
                                        __m512i c, __m512i d) {
  return _mm512_add_epi32(_mm512_add_epi32(a, b),
                          _mm512_add_epi32(c, d));
}

static inline __m512i sum_cs1_resolved(__m512i a, __m512i b,
                                       __m512i c, __m512i d) {
  __m512i s = csa_sum(a, b, c);
  __m512i cy = csa_carry(a, b, c);
  return _mm512_add_epi32(_mm512_add_epi32(s, cy), d);
}

static inline __m512i sum_csfull_resolved(__m512i a, __m512i b,
                                          __m512i c, __m512i d) {
  __m512i s1 = csa_sum(a, b, c);
  __m512i c1 = csa_carry(a, b, c);
  __m512i s2 = csa_sum(s1, c1, d);
  __m512i c2 = csa_carry(s1, c1, d);
  return _mm512_add_epi32(s2, c2);
}

static inline __m512i sum_sigma_led_cs1(__m512i a, __m512i b,
                                        __m512i c, __m512i d) {
  __m512i s = csa_sum(b, d, a);
  __m512i cy = csa_carry(b, d, a);
  return _mm512_add_epi32(_mm512_add_epi32(s, cy), c);
}

#define DEFINE_RUNNER(NAME, SUMFN)                                     \
  __attribute__((noinline, noclone)) static void run_##NAME(           \
      const __m512i *B, const __m512i *C, const __m512i *D,            \
      __m512i *ring, int depth, size_t iterations) {                   \
    size_t idx = 0;                                                    \
    int slot = 0;                                                      \
    for (size_t i = 0; i < iterations; i++) {                          \
      __m512i a = ring[slot];                                          \
      __m512i out = SUMFN(a, B[idx], C[idx], D[idx]);                  \
      ring[slot] = out;                                                \
      idx++;                                                           \
      if (idx == DATA_VECTORS) idx = 0;                                \
      slot++;                                                          \
      if (slot == depth) slot = 0;                                     \
    }                                                                  \
  }

DEFINE_RUNNER(current_serial, sum_current_serial)
DEFINE_RUNNER(balanced_tree, sum_balanced_tree)
DEFINE_RUNNER(cs1_resolved, sum_cs1_resolved)
DEFINE_RUNNER(csfull_resolved, sum_csfull_resolved)
DEFINE_RUNNER(sigma_led_cs1, sum_sigma_led_cs1)

typedef void (*runner_fn)(const __m512i *, const __m512i *,
                          const __m512i *, __m512i *, int, size_t);

static const char *FORM_NAMES[NFORMS] = {
    "current_serial", "balanced_tree", "cs1_resolved",
    "csfull_resolved", "sigma_led_cs1"};

static runner_fn FORM_RUNNERS[NFORMS] = {
    run_current_serial, run_balanced_tree, run_cs1_resolved,
    run_csfull_resolved, run_sigma_led_cs1};

static uint64_t now_ns(void) {
  struct timespec ts;
  clock_gettime(CLOCK_MONOTONIC_RAW, &ts);
  return (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
}

static uint64_t ring_checksum(const __m512i *ring, int depth) {
  uint64_t acc = 0;
  for (int s = 0; s < depth; s++) {
    uint32_t lanes[16];
    _mm512_storeu_si512((void *)lanes, ring[s]);
    for (int j = 0; j < 16; j++) acc += lanes[j] + (uint64_t)s;
  }
  return acc;
}

static int verify(void) {
  const int trials = 100000;
  uint64_t state = 0xE9019ULL;
  long mismatches = 0;
  for (int t = 0; t < trials; t++) {
    uint32_t av[16], bv[16], cv[16], dv[16], out[16];
    for (int j = 0; j < 16; j++) {
      av[j] = (uint32_t)splitmix64(&state);
      bv[j] = (uint32_t)splitmix64(&state);
      cv[j] = (uint32_t)splitmix64(&state);
      dv[j] = (uint32_t)splitmix64(&state);
    }
    __m512i a = _mm512_loadu_si512((const void *)av);
    __m512i b = _mm512_loadu_si512((const void *)bv);
    __m512i c = _mm512_loadu_si512((const void *)cv);
    __m512i d = _mm512_loadu_si512((const void *)dv);
    __m512i results[NFORMS];
    results[0] = sum_current_serial(a, b, c, d);
    results[1] = sum_balanced_tree(a, b, c, d);
    results[2] = sum_cs1_resolved(a, b, c, d);
    results[3] = sum_csfull_resolved(a, b, c, d);
    results[4] = sum_sigma_led_cs1(a, b, c, d);
    /* Deferred identities, checked as integer equalities:
     * cs1: sum + carry + d == total (three-vector output);
     * csfull: the second level's pair sums to the total. */
    __m512i cs1_pair = _mm512_add_epi32(csa_sum(a, b, c),
                                        csa_carry(a, b, c));
    __m512i cs1_total = _mm512_add_epi32(cs1_pair, d);
    for (int f = 0; f < NFORMS; f++) {
      _mm512_storeu_si512((void *)out, results[f]);
      for (int j = 0; j < 16; j++) {
        uint32_t want = av[j] + bv[j] + cv[j] + dv[j];
        if (out[j] != want) mismatches++;
      }
    }
    _mm512_storeu_si512((void *)out, cs1_total);
    for (int j = 0; j < 16; j++) {
      uint32_t want = av[j] + bv[j] + cv[j] + dv[j];
      if (out[j] != want) mismatches++;
    }
  }
  printf("{\"mode\":\"verify\",\"trials\":%d,\"lanes\":%d,"
         "\"mismatches\":%ld}\n",
         trials, trials * 16, mismatches);
  return mismatches == 0 ? 0 : 2;
}

int main(int argc, char **argv) {
  if (argc >= 2 && strcmp(argv[1], "verify") == 0) return verify();
  if (argc != 6 || strcmp(argv[1], "bench") != 0) {
    fprintf(stderr,
            "usage: %s verify | bench <depth> <iterations> "
            "<repeats> <seed>\n",
            argv[0]);
    return 1;
  }
  int depth = atoi(argv[2]);
  size_t iterations = (size_t)atol(argv[3]);
  int repeats = atoi(argv[4]);
  uint64_t seed = strtoull(argv[5], NULL, 10);
  if (depth < 1 || depth > MAX_DEPTH || iterations == 0 ||
      repeats < 1) {
    fprintf(stderr, "bad bench arguments\n");
    return 1;
  }

  __m512i *B = aligned_alloc(64, DATA_VECTORS * sizeof(__m512i));
  __m512i *C = aligned_alloc(64, DATA_VECTORS * sizeof(__m512i));
  __m512i *D = aligned_alloc(64, DATA_VECTORS * sizeof(__m512i));
  __m512i *ring = aligned_alloc(64, MAX_DEPTH * sizeof(__m512i));
  __m512i *init_ring =
      aligned_alloc(64, MAX_DEPTH * sizeof(__m512i));
  if (!B || !C || !D || !ring || !init_ring) return 1;

  uint64_t state = seed ^ 0xB5297A4D3F84D5B5ULL;
  __m512i *arrays[3] = {B, C, D};
  for (int k = 0; k < 3; k++) {
    uint32_t *p = (uint32_t *)arrays[k];
    for (size_t i = 0; i < DATA_VECTORS * 16; i++)
      p[i] = (uint32_t)splitmix64(&state);
  }
  {
    uint32_t *p = (uint32_t *)init_ring;
    for (int i = 0; i < MAX_DEPTH * 16; i++)
      p[i] = (uint32_t)splitmix64(&state);
  }

  /* Warmup: every form once at this depth. */
  for (int f = 0; f < NFORMS; f++) {
    memcpy(ring, init_ring, MAX_DEPTH * sizeof(__m512i));
    FORM_RUNNERS[f](B, C, D, ring, depth, 2048);
  }

  uint64_t rng = seed * 2862933555777941757ULL + 3037000493ULL;
  for (int rep = 0; rep < repeats; rep++) {
    int order[NFORMS] = {0, 1, 2, 3, 4};
    for (int i = NFORMS - 1; i > 0; i--) {
      int j = (int)(splitmix64(&rng) % (uint64_t)(i + 1));
      int tmp = order[i];
      order[i] = order[j];
      order[j] = tmp;
    }
    uint64_t expected = 0;
    int have_expected = 0;
    for (int pos = 0; pos < NFORMS; pos++) {
      int f = order[pos];
      memcpy(ring, init_ring, MAX_DEPTH * sizeof(__m512i));
      uint64_t t0 = now_ns();
      FORM_RUNNERS[f](B, C, D, ring, depth, iterations);
      uint64_t elapsed = now_ns() - t0;
      uint64_t chk = ring_checksum(ring, depth);
      if (!have_expected) {
        expected = chk;
        have_expected = 1;
      } else if (chk != expected) {
        fprintf(stderr,
                "checksum mismatch: form %s rep %d "
                "(forms disagree; bench aborted)\n",
                FORM_NAMES[f], rep);
        return 3;
      }
      printf("{\"separation\":%d,\"depth\":%d,\"repeat\":%d,"
             "\"order_position\":%d,\"form\":\"%s\","
             "\"iterations\":%zu,\"elapsed_ns\":%llu,"
             "\"ns_per_vector_op\":%.6f,\"checksum\":%llu}\n",
             depth - 1, depth, rep, pos, FORM_NAMES[f],
             iterations, (unsigned long long)elapsed,
             (double)elapsed / (double)iterations,
             (unsigned long long)chk);
      fflush(stdout);
    }
  }
  return 0;
}
