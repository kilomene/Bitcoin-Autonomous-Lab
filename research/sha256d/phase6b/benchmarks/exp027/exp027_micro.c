/* EXP-027 rotation price micro (EXP-019 style), v2.
 * Register-resident form: eight independent accumulators,
 * no memory stream in the timed region, so the measurement
 * prices vector-op throughput rather than load bandwidth.
 * (v1 streamed a 256 KB buffer and measured the load path;
 * all forms read 1.05 ns/vec. That run is not used.)
 * Three exact forms of ROTR13 on zmm dword lanes:
 *   A: VPROLD            (1 op, incumbent)
 *   B: VPSHUFB byte rotate + VPSRLD + VPSLLD + VPOR (4 ops)
 *   C: VPSRLD + VPSLLD + VPOR                       (3 ops)
 * Build: gcc -O3 -mavx512f -mavx512bw.
 */
#include <immintrin.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define ITERS 20000
#define REPS 15

static double now_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec * 1e9 + ts.tv_nsec;
}

static int cmp_double(const void *a, const void *b) {
    double d = *(const double *)a - *(const double *)b;
    return (d > 0) - (d < 0);
}

#define LOAD8(p) \
    __m512i p##0 = seed, p##1 = seed, p##2 = seed, p##3 = seed, \
            p##4 = seed, p##5 = seed, p##6 = seed, p##7 = seed
#define SUM8(p) (_mm512_reduce_add_epi64( \
    _mm512_xor_si512(_mm512_xor_si512(p##0, p##1), \
                     _mm512_xor_si512(p##2, p##3))) + \
    _mm512_reduce_add_epi64( \
    _mm512_xor_si512(_mm512_xor_si512(p##4, p##5), \
                     _mm512_xor_si512(p##6, p##7))))

int main(void) {
    uint8_t ctl[64];
    for (int i = 0; i < 64; i++) {
        int pos = i % 4;
        ctl[i] = (uint8_t)((i & ~3) + ((pos + 1) % 4));
    }
    __m512i vctl = _mm512_loadu_si512(ctl);
    __m512i seed = _mm512_set_epi64(
        0x243F6A8885A308D3ull, 0x13198A2E03707344ull,
        0xA4093822299F31D0ull, 0x082EFA98EC4E6C89ull,
        0x452821E638D01377ull, 0xBE5466CF34E90C6Cull,
        0xC0AC29B7C97C50DDull, 0x3F84D5B5B5470917ull);
    /* verify the three forms agree on the seed */
    {
        __m512i a = _mm512_ror_epi32(seed, 13);
        __m512i st = _mm512_shuffle_epi8(seed, vctl);
        __m512i b = _mm512_or_si512(_mm512_srli_epi32(st, 5),
                                    _mm512_slli_epi32(st, 27));
        __m512i c = _mm512_or_si512(_mm512_srli_epi32(seed, 13),
                                    _mm512_slli_epi32(seed, 19));
        if (memcmp(&a, &b, 64) || memcmp(&a, &c, 64)) {
            printf("FORM MISMATCH\n");
            return 1;
        }
        printf("forms verified equal\n");
    }
    double tA[REPS], tB[REPS], tC[REPS];
    volatile uint64_t sink = 0;
    for (int r = 0; r < REPS; r++) {
        double t0 = now_ns();
        { LOAD8(a);
          for (int i = 0; i < ITERS; i++) {
              a0 = _mm512_ror_epi32(a0, 13);
              a1 = _mm512_ror_epi32(a1, 13);
              a2 = _mm512_ror_epi32(a2, 13);
              a3 = _mm512_ror_epi32(a3, 13);
              a4 = _mm512_ror_epi32(a4, 13);
              a5 = _mm512_ror_epi32(a5, 13);
              a6 = _mm512_ror_epi32(a6, 13);
              a7 = _mm512_ror_epi32(a7, 13);
          }
          sink += SUM8(a); }
        tA[r] = (now_ns() - t0) / (ITERS * 8);
        t0 = now_ns();
        { LOAD8(b);
          for (int i = 0; i < ITERS; i++) {
#define STEPB(v) do { __m512i st = _mm512_shuffle_epi8(v, vctl); \
    v = _mm512_or_si512(_mm512_srli_epi32(st, 5), \
                        _mm512_slli_epi32(st, 27)); } while (0)
              STEPB(b0); STEPB(b1); STEPB(b2); STEPB(b3);
              STEPB(b4); STEPB(b5); STEPB(b6); STEPB(b7);
          }
          sink += SUM8(b); }
        tB[r] = (now_ns() - t0) / (ITERS * 8);
        t0 = now_ns();
        { LOAD8(c);
          for (int i = 0; i < ITERS; i++) {
#define STEPC(v) v = _mm512_or_si512(_mm512_srli_epi32(v, 13), \
                                     _mm512_slli_epi32(v, 19))
              STEPC(c0); STEPC(c1); STEPC(c2); STEPC(c3);
              STEPC(c4); STEPC(c5); STEPC(c6); STEPC(c7);
          }
          sink += SUM8(c); }
        tC[r] = (now_ns() - t0) / (ITERS * 8);
    }
    qsort(tA, REPS, sizeof(double), cmp_double);
    qsort(tB, REPS, sizeof(double), cmp_double);
    qsort(tC, REPS, sizeof(double), cmp_double);
    printf("A vprold        median %.4f ns/vec\n", tA[REPS / 2]);
    printf("B shuffle form  median %.4f ns/vec\n", tB[REPS / 2]);
    printf("C shift/or form median %.4f ns/vec\n", tC[REPS / 2]);
    printf("ratios: B/A %.3f  C/A %.3f  sink=%llu\n",
           tB[REPS / 2] / tA[REPS / 2], tC[REPS / 2] / tA[REPS / 2],
           (unsigned long long)sink);
    return 0;
}
