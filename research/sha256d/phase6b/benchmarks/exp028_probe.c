/* EXP-028 research probe: flag-free multi-family feature
 * detection, following the production pattern of
 * mining/cpu/bal_avx512_probe.c.
 *
 * This translation unit is compiled with NO architecture
 * flags (no -march, no -mavx*, no -msha). It contains no
 * vector or extension instruction: it only calls
 * __builtin_cpu_supports, which reads CPUID and, for the
 * AVX families, the OS xgetbv state. It is therefore safe
 * to call on any x86-64 machine, and on a non-x86 build
 * every x86 bit reads 0 (the ARM family is specified in
 * EXP028_CPU_ARCHITECTURES.md and detected there by the
 * OS capability interface of the target, never here).
 *
 * Bit assignments for bal_xarch_feature_bits():
 *   bit 0  AVX-512F        bit 8  AVX2
 *   bit 1  AVX-512BW       bit 9  SHA extensions (sha_ni)
 *   bit 2  AVX-512DQ       bit 10 SSE4.1
 *   bit 3  AVX-512VL       bit 11 SSE4.2
 *   bit 4  AVX-512VBMI     bit 12 BMI1
 *   bit 5  AVX-512VBMI2    bit 13 BMI2
 *   bit 6  AVX-512IFMA     bit 14 ADX
 *   bit 7  AVX-512VNNI     bit 15 AES-NI (context only)
 *
 * A bit means: the CPUID feature is present AND, where
 * the OS register state matters (AVX, AVX-512), the OS
 * exposes that state. A bit never means a kernel using
 * the feature is fast, correct, or present: selection
 * additionally requires the library completeness check
 * and the hashlib self-test (see exp028_dispatch.py).
 */

#include <stdint.h>

uint64_t bal_xarch_feature_bits(void) {
  uint64_t bits = 0;
#if defined(__x86_64__) || defined(__i386__)
  if (__builtin_cpu_supports("avx512f")) bits |= 1ull << 0;
  if (__builtin_cpu_supports("avx512bw")) bits |= 1ull << 1;
  if (__builtin_cpu_supports("avx512dq")) bits |= 1ull << 2;
  if (__builtin_cpu_supports("avx512vl")) bits |= 1ull << 3;
  if (__builtin_cpu_supports("avx512vbmi")) bits |= 1ull << 4;
  if (__builtin_cpu_supports("avx512vbmi2")) bits |= 1ull << 5;
  if (__builtin_cpu_supports("avx512ifma")) bits |= 1ull << 6;
  if (__builtin_cpu_supports("avx512vnni")) bits |= 1ull << 7;
  if (__builtin_cpu_supports("avx2")) bits |= 1ull << 8;
  if (__builtin_cpu_supports("sha")) bits |= 1ull << 9;
  if (__builtin_cpu_supports("sse4.1")) bits |= 1ull << 10;
  if (__builtin_cpu_supports("sse4.2")) bits |= 1ull << 11;
  if (__builtin_cpu_supports("bmi")) bits |= 1ull << 12;
  if (__builtin_cpu_supports("bmi2")) bits |= 1ull << 13;
  if (__builtin_cpu_supports("adx")) bits |= 1ull << 14;
  if (__builtin_cpu_supports("aes")) bits |= 1ull << 15;
#endif
  return bits;
}

/* The production v512 requirement, restated as the
 * probe-level predicate the dispatch spec consumes:
 * exactly AVX-512F plus AVX-512BW, nothing more. */
int bal_xarch_v512_ok(void) {
  uint64_t b = bal_xarch_feature_bits();
  return ((b & 1ull) != 0) && ((b & 2ull) != 0);
}

/* SHA-extension predicate for the H-01/H-02 family:
 * SHA instructions plus the SSE4 support the existing
 * kernels are built against. */
int bal_xarch_shani_ok(void) {
  uint64_t b = bal_xarch_feature_bits();
  return ((b >> 9) & 1ull) != 0 && ((b >> 10) & 1ull) != 0 &&
         ((b >> 11) & 1ull) != 0;
}
