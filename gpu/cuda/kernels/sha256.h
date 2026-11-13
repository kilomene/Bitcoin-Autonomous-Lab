// SHA-256 (FIPS 180-4) written to compile in three contexts:
//   * CUDA device code (nvcc, __CUDACC__ defined)
//   * CUDA host code
//   * plain C++ host code (g++), for CPU validation of the exact same
//     source the GPU kernel uses. If the host build of this file
//     disagrees with hashlib, the GPU path is never trusted.
#pragma once
#include <stdint.h>
#include <string.h>

#if defined(__CUDACC__)
#define BAL_HD __host__ __device__
#else
#define BAL_HD
#endif

static const uint32_t BAL_K[64] = {
  0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
  0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
  0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
  0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
  0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
  0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
  0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
  0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};

#if defined(__CUDACC__)
// Device code cannot read the host static array; nvcc copies this
// table into device constant storage instead.
__device__ static const uint32_t BAL_K_DEV[64] = {
  0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
  0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
  0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
  0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
  0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
  0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
  0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
  0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};
#endif

BAL_HD static inline uint32_t bal_k(int i) {
#if defined(__CUDA_ARCH__)
  return BAL_K_DEV[i];
#else
  return BAL_K[i];
#endif
}

#define BAL_RR(x,n) (((x)>>(n))|((x)<<(32-(n))))

struct BalSha256 {
  uint32_t h[8];
  uint64_t len;
  uint8_t buf[64];
  uint32_t buflen;
};

BAL_HD static inline void bal_sha256_init(BalSha256* s) {
  static const uint32_t H0[8] = {0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,
                                 0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19};
  for (int i=0;i<8;i++) s->h[i]=H0[i];
  s->len=0; s->buflen=0;
}

BAL_HD static inline void bal_sha256_block(BalSha256* s, const uint8_t* p) {
  uint32_t w[64];
  for (int i=0;i<16;i++)
    w[i]=((uint32_t)p[4*i]<<24)|((uint32_t)p[4*i+1]<<16)|((uint32_t)p[4*i+2]<<8)|(uint32_t)p[4*i+3];
  for (int i=16;i<64;i++) {
    uint32_t s0=BAL_RR(w[i-15],7)^BAL_RR(w[i-15],18)^(w[i-15]>>3);
    uint32_t s1=BAL_RR(w[i-2],17)^BAL_RR(w[i-2],19)^(w[i-2]>>10);
    w[i]=w[i-16]+s0+w[i-7]+s1;
  }
  uint32_t a=s->h[0],b=s->h[1],c=s->h[2],d=s->h[3],e=s->h[4],f=s->h[5],g=s->h[6],hh=s->h[7];
  for (int i=0;i<64;i++) {
    uint32_t S1=BAL_RR(e,6)^BAL_RR(e,11)^BAL_RR(e,25);
    uint32_t ch=(e&f)^((~e)&g);
    uint32_t t1=hh+S1+ch+bal_k(i)+w[i];
    uint32_t S0=BAL_RR(a,2)^BAL_RR(a,13)^BAL_RR(a,22);
    uint32_t mj=(a&b)^(a&c)^(b&c);
    uint32_t t2=S0+mj;
    hh=g;g=f;f=e;e=d+t1;d=c;c=b;b=a;a=t1+t2;
  }
  s->h[0]+=a;s->h[1]+=b;s->h[2]+=c;s->h[3]+=d;s->h[4]+=e;s->h[5]+=f;s->h[6]+=g;s->h[7]+=hh;
}

BAL_HD static inline void bal_sha256_update(BalSha256* s, const uint8_t* data, uint64_t n) {
  s->len += n;
  while (n) {
    uint32_t take = 64 - s->buflen;
    if (take > n) take = (uint32_t)n;
    for (uint32_t i=0;i<take;i++) s->buf[s->buflen+i]=data[i];
    s->buflen += take; data += take; n -= take;
    if (s->buflen==64) { bal_sha256_block(s, s->buf); s->buflen=0; }
  }
}

BAL_HD static inline void bal_sha256_final(BalSha256* s, uint8_t* out) {
  uint64_t bits = s->len * 8;
  uint8_t pad = 0x80;
  bal_sha256_update(s, &pad, 1);
  uint8_t zero = 0;
  while (s->buflen != 56) bal_sha256_update(s, &zero, 1);
  uint8_t lenbuf[8];
  for (int i=0;i<8;i++) lenbuf[i]=(uint8_t)(bits >> (56-8*i));
  // Write length directly as the final 8 bytes of the block.
  for (int i=0;i<8;i++) s->buf[56+i]=lenbuf[i];
  bal_sha256_block(s, s->buf);
  for (int i=0;i<8;i++) {
    out[4*i]=(uint8_t)(s->h[i]>>24); out[4*i+1]=(uint8_t)(s->h[i]>>16);
    out[4*i+2]=(uint8_t)(s->h[i]>>8); out[4*i+3]=(uint8_t)(s->h[i]);
  }
}

BAL_HD static inline void bal_sha256(const uint8_t* data, uint64_t n, uint8_t* out) {
  BalSha256 s; bal_sha256_init(&s); bal_sha256_update(&s, data, n); bal_sha256_final(&s, out);
}

// Double SHA-256 of an 80-byte header with the nonce (little endian)
// patched at offset 76. Output is the raw 32-byte digest (internal order).
BAL_HD static inline void bal_sha256d_header(const uint8_t* header, uint32_t nonce, uint8_t* out) {
  uint8_t h[80];
  for (int i=0;i<80;i++) h[i]=header[i];
  h[76]=(uint8_t)(nonce & 0xff); h[77]=(uint8_t)((nonce>>8)&0xff);
  h[78]=(uint8_t)((nonce>>16)&0xff); h[79]=(uint8_t)((nonce>>24)&0xff);
  uint8_t first[32];
  bal_sha256(h, 80, first);
  bal_sha256(first, 32, out);
}

// Target check: digest and target are both 32-byte little-endian values.
BAL_HD static inline int bal_meets_target(const uint8_t* digest, const uint8_t* target_le) {
  for (int i=31;i>=0;i--) {
    if (digest[i] < target_le[i]) return 1;
    if (digest[i] > target_le[i]) return 0;
  }
  return 1; // equal meets the target
}
