/* Runtime CPUID dispatch probes for the EXP-039 fallback
 * kernels: the AVX2 multi-buffer kernel (bal_avx2_mb.c) and
 * the multi-stream SHA-NI kernel (bal_shani_streams.c).
 *
 * This translation unit is compiled WITHOUT any vector or
 * SHA flags and linked into both fallback libraries, so the
 * probes themselves are safe to call on any x86-64 machine:
 * they contain no AVX2 or SHA instructions. The engine calls
 * the matching probe before it calls any kernel entry point;
 * on a machine lacking a required feature the kernel is
 * never entered and the engine falls back to the next tier.
 *
 * Required feature sets, determined from the kernel sources
 * and the restricted production build flags
 * (mining/cpu/build.py):
 * - AVX2 tier: AVX2 only. The build is -mavx2; the kernel's
 *   256-bit integer ops including the in-lane VPSHUFB byte
 *   swap are all AVX2 instructions.
 * - SHA-NI tier: the SHA extensions plus SSSE3. The build
 *   is -msha -mssse3; the H-02 core uses the SHA256RNDS2 /
 *   SHA256MSG1 / SHA256MSG2 instruction family and SSSE3
 *   shuffles and aligns.
 *
 * __builtin_cpu_supports checks both the CPUID feature bits
 * and, for AVX2, that the OS exposes the ymm register state
 * (xgetbv), so a positive answer means the kernel can
 * actually execute, not merely that the silicon lists it.
 */

int bal_avx2_supported(void) {
  return __builtin_cpu_supports("avx2");
}

/* Bitmask of the individual AVX2 tier checks, for
 * diagnostics: bit 0 = AVX2. */
unsigned bal_avx2_feature_bits(void) {
  unsigned bits = 0;
  if (__builtin_cpu_supports("avx2")) bits |= 1u;
  return bits;
}

int bal_shani_supported(void) {
  return __builtin_cpu_supports("sha") &&
         __builtin_cpu_supports("ssse3");
}

/* Bitmask of the individual SHA-NI tier checks, for
 * diagnostics: bit 0 = SHA extensions, bit 1 = SSSE3. */
unsigned bal_shani_feature_bits(void) {
  unsigned bits = 0;
  if (__builtin_cpu_supports("sha")) bits |= 1u;
  if (__builtin_cpu_supports("ssse3")) bits |= 2u;
  return bits;
}
