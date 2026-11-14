/* Runtime CPUID dispatch probe for the AVX-512 multi-buffer
 * kernel (bal_avx512_mb.c).
 *
 * This translation unit is compiled WITHOUT any AVX-512 flags
 * and linked into libbal_v512.so alongside the kernel, so the
 * probe itself is safe to call on any x86-64 machine: it
 * contains no AVX-512 instructions. The engine calls
 * bal_v512_supported() before it calls any kernel entry point;
 * on a machine lacking a required feature the kernel is never
 * entered and the engine falls back to the OpenSSL C backend.
 *
 * Required feature set, determined from the kernel source and
 * confirmed against the compiled object's instruction audit
 * (see mining/cpu/build.py and the integration record):
 * - AVX-512F: the foundation. _mm512_ror_epi32 (vprold),
 *   _mm512_add_epi32, the bitwise ops and vpternlogd are all
 *   AVX-512F instructions.
 * - AVX-512BW: _mm512_shuffle_epi8 (vpshufb on a zmm register),
 *   used to byte-swap the nonce word into schedule word W3.
 * No other AVX-512 subset is required: the kernel uses no
 * AVX-512DQ, VL, VBMI, VBMI2 or IFMA intrinsics, and the
 * production build's restricted flag set (-mavx512f
 * -mavx512bw, never -march=native) keeps the compiler from
 * emitting any.
 *
 * __builtin_cpu_supports checks both the CPUID feature bits
 * and, for AVX-512F, that the OS exposes the zmm register
 * state (xgetbv), so a positive answer means the kernel can
 * actually execute, not merely that the silicon lists it.
 */

int bal_v512_supported(void) {
  return __builtin_cpu_supports("avx512f") &&
         __builtin_cpu_supports("avx512bw");
}

/* Bitmask of the individual checks, for diagnostics:
 * bit 0 = AVX-512F, bit 1 = AVX-512BW. */
unsigned bal_v512_feature_bits(void) {
  unsigned bits = 0;
  if (__builtin_cpu_supports("avx512f")) bits |= 1u;
  if (__builtin_cpu_supports("avx512bw")) bits |= 2u;
  return bits;
}
