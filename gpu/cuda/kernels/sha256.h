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

// One SHA-256 compression of a 64-byte block into an explicit state.
// This is the single compression core; the streaming API, the circular
// schedule variant and the Bitcoin midstate path are all built on the
// same round function so a host proof of one covers the others.
BAL_HD static inline void bal_compress_state(uint32_t h[8], const uint8_t* p) {
  uint32_t w[64];
  for (int i=0;i<16;i++)
    w[i]=((uint32_t)p[4*i]<<24)|((uint32_t)p[4*i+1]<<16)|((uint32_t)p[4*i+2]<<8)|(uint32_t)p[4*i+3];
  for (int i=16;i<64;i++) {
    uint32_t s0=BAL_RR(w[i-15],7)^BAL_RR(w[i-15],18)^(w[i-15]>>3);
    uint32_t s1=BAL_RR(w[i-2],17)^BAL_RR(w[i-2],19)^(w[i-2]>>10);
    w[i]=w[i-16]+s0+w[i-7]+s1;
  }
  uint32_t a=h[0],b=h[1],c=h[2],d=h[3],e=h[4],f=h[5],g=h[6],hh=h[7];
  for (int i=0;i<64;i++) {
    uint32_t S1=BAL_RR(e,6)^BAL_RR(e,11)^BAL_RR(e,25);
    uint32_t ch=(e&f)^((~e)&g);
    uint32_t t1=hh+S1+ch+bal_k(i)+w[i];
    uint32_t S0=BAL_RR(a,2)^BAL_RR(a,13)^BAL_RR(a,22);
    uint32_t mj=(a&b)^(a&c)^(b&c);
    uint32_t t2=S0+mj;
    hh=g;g=f;f=e;e=d+t1;d=c;c=b;b=a;a=t1+t2;
  }
  h[0]+=a;h[1]+=b;h[2]+=c;h[3]+=d;h[4]+=e;h[5]+=f;h[6]+=g;h[7]+=hh;
}

// Circular 16-word schedule variant: mathematically identical, but the
// schedule lives in a 16-word ring instead of a 64-word array, which
// cuts local-memory/register pressure on GPU threads. Slot (i&15)
// holds w[i-16] at step i, exactly the word the recurrence replaces.
BAL_HD static inline void bal_compress_state_circ(uint32_t h[8], const uint8_t* p) {
  uint32_t w[16];
  for (int i=0;i<16;i++)
    w[i]=((uint32_t)p[4*i]<<24)|((uint32_t)p[4*i+1]<<16)|((uint32_t)p[4*i+2]<<8)|(uint32_t)p[4*i+3];
  uint32_t a=h[0],b=h[1],c=h[2],d=h[3],e=h[4],f=h[5],g=h[6],hh=h[7];
  for (int i=0;i<64;i++) {
    if (i>=16) {
      uint32_t x15=w[(i-15)&15], x2=w[(i-2)&15];
      uint32_t s0=BAL_RR(x15,7)^BAL_RR(x15,18)^(x15>>3);
      uint32_t s1=BAL_RR(x2,17)^BAL_RR(x2,19)^(x2>>10);
      w[i&15]=w[i&15]+s0+w[(i-7)&15]+s1;
    }
    uint32_t wi=w[i&15];
    uint32_t S1=BAL_RR(e,6)^BAL_RR(e,11)^BAL_RR(e,25);
    uint32_t ch=(e&f)^((~e)&g);
    uint32_t t1=hh+S1+ch+bal_k(i)+wi;
    uint32_t S0=BAL_RR(a,2)^BAL_RR(a,13)^BAL_RR(a,22);
    uint32_t mj=(a&b)^(a&c)^(b&c);
    uint32_t t2=S0+mj;
    hh=g;g=f;f=e;e=d+t1;d=c;c=b;b=a;a=t1+t2;
  }
  h[0]+=a;h[1]+=b;h[2]+=c;h[3]+=d;h[4]+=e;h[5]+=f;h[6]+=g;h[7]+=hh;
}

BAL_HD static inline void bal_sha256_block(BalSha256* s, const uint8_t* p) {
  bal_compress_state(s->h, p);
}

BAL_HD static inline void bal_sha256_block_circ(BalSha256* s, const uint8_t* p) {
  bal_compress_state_circ(s->h, p);
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

BAL_HD static inline void bal_sha256_init_words(uint32_t h[8]) {
  static const uint32_t H0[8] = {0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,
                                 0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19};
  for (int i=0;i<8;i++) h[i]=H0[i];
}

BAL_HD static inline void bal_state_to_bytes(const uint32_t h[8], uint8_t* out) {
  for (int i=0;i<8;i++) {
    out[4*i]=(uint8_t)(h[i]>>24); out[4*i+1]=(uint8_t)(h[i]>>16);
    out[4*i+2]=(uint8_t)(h[i]>>8); out[4*i+3]=(uint8_t)(h[i]);
  }
}

// Full SHA-256 using the circular schedule for every block.
BAL_HD static inline void bal_sha256_circ(const uint8_t* data, uint64_t n, uint8_t* out) {
  BalSha256 s; bal_sha256_init(&s);
  // Streaming with the circular compressor: process full blocks
  // directly and pad manually, mirroring bal_sha256_final semantics.
  uint32_t h[8]; bal_sha256_init_words(h);
  uint64_t full = n / 64;
  for (uint64_t b=0;b<full;b++) bal_compress_state_circ(h, data + 64*b);
  uint32_t rem = (uint32_t)(n % 64);
  uint8_t tail[128];
  for (uint32_t i=0;i<rem;i++) tail[i]=data[64*full+i];
  tail[rem]=0x80;
  uint32_t tailblocks = (rem < 56) ? 1 : 2;
  for (uint32_t i=rem+1;i<64*tailblocks;i++) tail[i]=0;
  uint64_t bits = n * 8;
  for (int i=0;i<8;i++) tail[64*tailblocks-8+i]=(uint8_t)(bits >> (56-8*i));
  for (uint32_t b=0;b<tailblocks;b++) bal_compress_state_circ(h, tail + 64*b);
  (void)s;
  bal_state_to_bytes(h, out);
}

// ------------------------------------------------------------------
// Bitcoin midstate path (Task 002, Phase 2).
//
// The 80-byte header is two SHA-256 blocks for the inner hash:
// block 1 is header bytes 0..63 (version, prevhash, and the first
// 28 bytes of the merkle root). It contains NO nonce, timestamp or
// nBits bytes, so its compression from the SHA-256 IV is a per-header
// constant: the midstate. Block 2 is header bytes 64..79 (last 4
// merkle bytes, timestamp, nBits, nonce at bytes 76..79) followed by
// SHA-256 padding for an 80-byte message (0x80, zeros, bit length
// 640 in the final 8 bytes). The midstate must be recomputed whenever
// any byte of header[0..63] changes; bytes 64..79 travel with the
// per-nonce work as the "tail". This splits exactly at the consensus
// block boundary; no round is approximated or skipped.
// ------------------------------------------------------------------
BAL_HD static inline void bal_sha256d_midstate(const uint8_t* header, uint32_t st[8]) {
  bal_sha256_init_words(st);
  bal_compress_state(st, header);
}

BAL_HD static inline void bal_sha256d_midstate_circ(const uint8_t* header, uint32_t st[8]) {
  bal_sha256_init_words(st);
  bal_compress_state_circ(st, header);
}

BAL_HD static inline void bal_sha256d_from_midstate(const uint32_t st0[8],
                                                    const uint8_t* tail16,
                                                    uint32_t nonce,
                                                    uint8_t* out) {
  uint8_t block[64];
  for (int i=0;i<16;i++) block[i]=tail16[i];
  // Nonce sits at header bytes 76..79, tail offsets 12..15, little endian.
  block[12]=(uint8_t)(nonce & 0xff); block[13]=(uint8_t)((nonce>>8)&0xff);
  block[14]=(uint8_t)((nonce>>16)&0xff); block[15]=(uint8_t)((nonce>>24)&0xff);
  block[16]=0x80;
  for (int i=17;i<56;i++) block[i]=0;
  for (int i=56;i<62;i++) block[i]=0;
  block[62]=0x02; block[63]=0x80; // 640 bits, big endian length field
  uint32_t st[8];
  for (int i=0;i<8;i++) st[i]=st0[i];
  bal_compress_state(st, block);
  uint8_t first[32];
  bal_state_to_bytes(st, first);
  bal_sha256(first, 32, out);
}

BAL_HD static inline void bal_sha256d_from_midstate_circ(const uint32_t st0[8],
                                                         const uint8_t* tail16,
                                                         uint32_t nonce,
                                                         uint8_t* out) {
  uint8_t block[64];
  for (int i=0;i<16;i++) block[i]=tail16[i];
  block[12]=(uint8_t)(nonce & 0xff); block[13]=(uint8_t)((nonce>>8)&0xff);
  block[14]=(uint8_t)((nonce>>16)&0xff); block[15]=(uint8_t)((nonce>>24)&0xff);
  block[16]=0x80;
  for (int i=17;i<56;i++) block[i]=0;
  for (int i=56;i<62;i++) block[i]=0;
  block[62]=0x02; block[63]=0x80;
  uint32_t st[8];
  for (int i=0;i<8;i++) st[i]=st0[i];
  bal_compress_state_circ(st, block);
  uint8_t first[32];
  bal_state_to_bytes(st, first);
  bal_sha256_circ(first, 32, out);
}

BAL_HD static inline void bal_sha256d_header_midstate(const uint8_t* header,
                                                      uint32_t nonce,
                                                      uint8_t* out) {
  uint32_t st[8];
  bal_sha256d_midstate(header, st);
  bal_sha256d_from_midstate(st, header + 64, nonce, out);
}

BAL_HD static inline void bal_sha256d_header_circ(const uint8_t* header,
                                                  uint32_t nonce,
                                                  uint8_t* out) {
  uint32_t st[8];
  bal_sha256d_midstate_circ(header, st);
  bal_sha256d_from_midstate_circ(st, header + 64, nonce, out);
}

// ------------------------------------------------------------------
// Candidate recording (Task 002, Phase 3). One primitive shared by the
// CUDA kernel and the host validation build, so the host concurrency
// tests exercise the exact logic the device runs. The counter counts
// EVERY candidate found (including ones that no longer fit), a slot
// is claimed atomically before any write, writes happen only when the
// claimed index is inside the allocated capacity, and an overflow
// flag is set when a candidate could not be stored. A caller that
// sees the overflow flag must treat the search as incomplete, never
// as a clean truncated list.
// ------------------------------------------------------------------
#if defined(__CUDA_ARCH__)
#define BAL_ATOMIC_ADD(p, v) atomicAdd((p), (v))
#define BAL_ATOMIC_SET1(p) atomicExch((p), 1u)
#else
#define BAL_ATOMIC_ADD(p, v) __sync_fetch_and_add((p), (v))
#define BAL_ATOMIC_SET1(p) (void)__sync_lock_test_and_set((p), 1u)
#endif

BAL_HD static inline void bal_record_candidate(uint32_t* counter, uint32_t cap,
                                               uint32_t* cand_nonces,
                                               uint8_t* cand_digests,
                                               uint32_t* overflow,
                                               uint32_t nonce,
                                               const uint8_t* digest) {
  uint32_t idx = BAL_ATOMIC_ADD(counter, 1u);
  if (idx < cap) {
    cand_nonces[idx] = nonce;
    for (int b=0;b<32;b++) cand_digests[32*(uint64_t)idx + b] = digest[b];
  } else {
    BAL_ATOMIC_SET1(overflow);
  }
}

// Nonce-range validation (Task 003.7), shared by the CUDA C ABI
// and the host validation build so the exact logic is testable
// without a device. Subtraction-based: count is validated FIRST,
// so 0x100000000 - count can never underflow, and start is compared
// against that remainder instead of computing start + count (which
// can wrap for start near 2^64). A valid range is a non-empty
// half-open interval [start, start+count) inside the 32-bit nonce
// space; the endpoint may be exactly 2^32.
BAL_HD static inline int bal_nonce_range_valid(uint64_t start, uint64_t count) {
  if (count == 0) return 0;
  if (count > 0x100000000ULL) return 0;
  if (start > 0x100000000ULL - count) return 0;
  return 1;
}

// ------------------------------------------------------------------
// CUDA C ABI validation (Task 003.8), shared by engine.cu and the
// host validation build so the exact checks the legacy entry point
// performs are executable without a device. Error codes crossing
// the C ABI (negative values are local validation errors; zero is
// success; positive values are CUDA runtime error codes):
//   0  success
//  -1  invalid argument (null pointer, zero count, bad thread count)
//  -2  host allocation failure
//  -3  invalid kernel configuration
//  -4  invalid nonce range (subtraction-based check failed)
//  -5  allocation-size overflow or size over the documented limit
//  -6  batch count over BAL_CUDA_LEGACY_MAX_BATCH
// The legacy one-shot entry point materializes every digest, so
// its documented maximum batch is 2^24 nonces: at most 512 MiB of
// digest output and 16 MiB of flags. Larger searches belong on the
// persistent candidate-filtering context or in caller-sized chunks.
// ------------------------------------------------------------------
#define BAL_CUDA_OK 0
#define BAL_CUDA_ERR_INVALID_ARGUMENT -1
#define BAL_CUDA_ERR_HOST_ALLOCATION -2
#define BAL_CUDA_ERR_INVALID_CONFIGURATION -3
#define BAL_CUDA_ERR_INVALID_RANGE -4
#define BAL_CUDA_ERR_SIZE_LIMIT -5
#define BAL_CUDA_ERR_BATCH_TOO_LARGE -6
#define BAL_CUDA_LEGACY_MAX_BATCH 16777216ULL

BAL_HD static inline int bal_checked_mul_size(size_t a, size_t b,
                                              size_t* out) {
  if (!out) return 0;
  if (a != 0 && b > ((size_t)-1) / a) return 0;
  *out = a * b;
  return 1;
}

// Validate every bal_cuda_batch argument BEFORE any pointer is
// dereferenced, copied, or passed to a CUDA memory operation, and
// compute the two count-derived allocation sizes with checked
// multiplication. out_hash_bytes and out_flag_bytes may be null
// when the caller only wants validation.
BAL_HD static inline int bal_cuda_batch_validate(
    const void* header, const void* target_le, const void* hashes,
    const void* flags, uint64_t start, uint64_t count,
    unsigned threads, size_t* out_hash_bytes, size_t* out_flag_bytes) {
  if (!header || !target_le || !hashes || !flags)
    return BAL_CUDA_ERR_INVALID_ARGUMENT;
  if (!count || !threads || threads > 1024)
    return BAL_CUDA_ERR_INVALID_ARGUMENT;
  if (count > BAL_CUDA_LEGACY_MAX_BATCH)
    return BAL_CUDA_ERR_BATCH_TOO_LARGE;
  if (!bal_nonce_range_valid(start, count))
    return BAL_CUDA_ERR_INVALID_RANGE;
  size_t hash_bytes = 0, flag_bytes = 0;
  if (!bal_checked_mul_size((size_t)count, (size_t)32, &hash_bytes) ||
      !bal_checked_mul_size((size_t)count, (size_t)1, &flag_bytes))
    return BAL_CUDA_ERR_SIZE_LIMIT;
  if (out_hash_bytes) *out_hash_bytes = hash_bytes;
  if (out_flag_bytes) *out_flag_bytes = flag_bytes;
  return BAL_CUDA_OK;
}

// Target check: digest and target are both 32-byte little-endian values.
BAL_HD static inline int bal_meets_target(const uint8_t* digest, const uint8_t* target_le) {
  for (int i=31;i>=0;i--) {
    if (digest[i] < target_le[i]) return 1;
    if (digest[i] > target_le[i]) return 0;
  }
  return 1; // equal meets the target
}
