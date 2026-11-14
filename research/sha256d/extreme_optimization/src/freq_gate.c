/* NOVA SHA-X X-041: sustained AVX-512 frequency behaviour.
 *
 * No perf counters exist in this guest, so clock behaviour
 * is inferred from wall-clock throughput on fixed-work
 * loops. Two loop types with matched structure: a scalar
 * throughput loop (8 independent 64-bit add chains) and an
 * AVX-512 throughput loop (8 independent zmm add chains).
 * Protocol: alternating blocks S A S A S A, each about 2 s,
 * rates printed per block. Drift within a type (first block
 * vs last block) and any cross-type drag (scalar rate in
 * blocks after AVX-512 blocks vs before) are the signals.
 * On Zen 4/5 no licence-based downclocking is expected; on
 * a shared virtualised host, neighbour effects can mimic
 * it, which is exactly why the alternation exists.
 */
#include <stdint.h>
#include <stdio.h>
#include <time.h>
#include <immintrin.h>

static double now_s(void) {
  struct timespec ts;
  clock_gettime(CLOCK_MONOTONIC, &ts);
  return ts.tv_sec + ts.tv_nsec * 1e-9;
}

static uint64_t sink_u = 0;
static __m512i sink_v;

__attribute__((noinline))
static double run_scalar(double seconds) {
  uint64_t a0 = sink_u + 1, a1 = 3, a2 = 5, a3 = 7,
           a4 = 11, a5 = 13, a6 = 17, a7 = 19;
  uint64_t iters = 0;
  double t0 = now_s(), dt = 0;
  while (dt < seconds) {
    for (int i = 0; i < 100000; i++) {
      a0 += a1; a1 += a2; a2 += a3; a3 += a4;
      a4 += a5; a5 += a6; a6 += a7; a7 += a0;
    }
    iters += 100000;
    dt = now_s() - t0;
  }
  sink_u = a0 + a1 + a2 + a3 + a4 + a5 + a6 + a7;
  /* 8 adds per iteration */
  return (double)iters * 8.0 / dt / 1e9;
}

__attribute__((noinline))
static double run_avx512(double seconds) {
  __m512i a0 = _mm512_add_epi32(sink_v, _mm512_set1_epi32(1));
  __m512i a1 = _mm512_set1_epi32(3), a2 = _mm512_set1_epi32(5),
          a3 = _mm512_set1_epi32(7), a4 = _mm512_set1_epi32(11),
          a5 = _mm512_set1_epi32(13), a6 = _mm512_set1_epi32(17),
          a7 = _mm512_set1_epi32(19);
  uint64_t iters = 0;
  double t0 = now_s(), dt = 0;
  while (dt < seconds) {
    for (int i = 0; i < 100000; i++) {
      a0 = _mm512_add_epi32(a0, a1);
      a1 = _mm512_add_epi32(a1, a2);
      a2 = _mm512_add_epi32(a2, a3);
      a3 = _mm512_add_epi32(a3, a4);
      a4 = _mm512_add_epi32(a4, a5);
      a5 = _mm512_add_epi32(a5, a6);
      a6 = _mm512_add_epi32(a6, a7);
      a7 = _mm512_add_epi32(a7, a0);
    }
    iters += 100000;
    dt = now_s() - t0;
  }
  sink_v = _mm512_add_epi32(
    _mm512_add_epi32(_mm512_add_epi32(a0, a1),
                     _mm512_add_epi32(a2, a3)),
    _mm512_add_epi32(_mm512_add_epi32(a4, a5),
                     _mm512_add_epi32(a6, a7)));
  /* 8 vector adds (128 lane-adds) per iteration */
  return (double)iters * 8.0 / dt / 1e9;
}

int main(void) {
  double s[3], a[3];
  for (int blk = 0; blk < 3; blk++) {
    s[blk] = run_scalar(2.0);
    printf("scalar block %d: %.3f Gops/s\n", blk, s[blk]);
    fflush(stdout);
    a[blk] = run_avx512(2.0);
    printf("avx512 block %d: %.3f Gvecops/s\n", blk, a[blk]);
    fflush(stdout);
  }
  printf("scalar drift first->last: %+.2f%%\n",
         100.0 * (s[2] - s[0]) / s[0]);
  printf("avx512 drift first->last: %+.2f%%\n",
         100.0 * (a[2] - a[0]) / a[0]);
  printf("avx512/scalar block-rate ratio: %.2f %.2f %.2f\n",
         a[0] / s[0], a[1] / s[1], a[2] / s[2]);
  return 0;
}
