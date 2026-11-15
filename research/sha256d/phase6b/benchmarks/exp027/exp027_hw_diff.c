/* EXP-027 hardware differentials.
 * T1: VGF2P8AFFINEQB hardware vs the scalar per-byte affine
 *     model used in the EXP-027 proofs (1,000,000 bytes).
 * T2: VPSHUFB byte-rotate plus shift/or construction of
 *     ROTR13 vs scalar ROTR13 (1,000,000 dwords).
 * T3: carry-save identity in scalar C (1,000,000 triples).
 * Build: gcc -O3 -mavx512f -mavx512bw -mgfni.
 * The extra -mgfni flag is recorded in the experiment
 * record; nothing here is a production dispatch candidate.
 */
#include <immintrin.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static uint64_t rng_state = 0x9E3779B97F4A7C15ull;

static uint64_t rng(void) {
    uint64_t x = rng_state;
    x ^= x << 13; x ^= x >> 7; x ^= x << 17;
    rng_state = x;
    return x;
}

static uint32_t rotr32(uint32_t x, int n) {
    return (x >> n) | (x << (32 - n));
}

static uint8_t gfni_byte(uint8_t b, uint64_t mat, uint8_t imm) {
    /* Empirically established on this host (single-bit
     * probe, exp027_hw_diff development): output bit i is
     * the parity of byte (7 - i) of the matrix operand
     * ANDed with the input byte, XOR imm bit i. */
    uint8_t out = 0;
    for (int i = 0; i < 8; i++) {
        uint8_t row = (uint8_t)(mat >> (8 * (7 - i)));
        uint8_t v = row & b;
        v ^= v >> 4; v ^= v >> 2; v ^= v >> 1;
        out |= (uint8_t)(((v & 1) ^ ((imm >> i) & 1)) << i);
    }
    return out;
}

int main(void) {
    /* T1: GFNI model vs hardware */
    uint64_t mat = rng();
    const int imm = 0xA5;
    long mism1 = 0;
    long total1 = 0;
    for (int iter = 0; iter < 15625; iter++) {
        uint8_t buf[64];
        for (int i = 0; i < 64; i++) buf[i] = (uint8_t)rng();
        __m512i v = _mm512_loadu_si512(buf);
        __m512i A = _mm512_set1_epi64(mat);
        __m512i r = _mm512_gf2p8affine_epi64_epi8(v, A, imm);
        uint8_t out[64];
        _mm512_storeu_si512(out, r);
        for (int i = 0; i < 64; i++) {
            total1++;
            if (out[i] != gfni_byte(buf[i], mat, (uint8_t)imm))
                mism1++;
        }
    }
    printf("T1 gfni samples=%ld mismatches=%ld\n", total1, mism1);

    /* T2: shuffle construction of ROTR13 */
    uint8_t ctl[64];
    for (int i = 0; i < 64; i++) {
        int pos = i % 4;
        ctl[i] = (uint8_t)((i & ~3) + ((pos + 1) % 4));
    }
    __m512i vctl = _mm512_loadu_si512(ctl);
    long mism2 = 0;
    long total2 = 0;
    for (int iter = 0; iter < 62500; iter++) {
        uint32_t buf[16];
        for (int i = 0; i < 16; i++) buf[i] = (uint32_t)rng();
        __m512i v = _mm512_loadu_si512(buf);
        __m512i step = _mm512_shuffle_epi8(v, vctl);
        __m512i r = _mm512_or_si512(_mm512_srli_epi32(step, 5),
                                    _mm512_slli_epi32(step, 27));
        uint32_t out[16];
        _mm512_storeu_si512(out, r);
        for (int i = 0; i < 16; i++) {
            total2++;
            if (out[i] != rotr32(buf[i], 13)) mism2++;
        }
    }
    printf("T2 shuffle_rotr13 samples=%ld mismatches=%ld\n",
           total2, mism2);

    /* T3: carry-save identity */
    long mism3 = 0;
    for (long i = 0; i < 1000000; i++) {
        uint32_t a = (uint32_t)rng(), b = (uint32_t)rng(),
                 c = (uint32_t)rng();
        uint32_t s = a ^ b ^ c;
        uint32_t carry = ((a & b) | (a & c) | (b & c)) << 1;
        if ((uint32_t)(a + b + c) != (uint32_t)(s + carry))
            mism3++;
    }
    printf("T3 carrysave samples=1000000 mismatches=%ld\n", mism3);
    return (mism1 || mism2 || mism3) ? 1 : 0;
}
