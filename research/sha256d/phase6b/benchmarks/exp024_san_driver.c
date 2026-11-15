/* EXP-024 sanitizer driver (gate G9).
 *
 * Built together with avx512_mb_mask_search.c under
 * -fsanitize=address,undefined. Exercises the three
 * EXP-024 search forms and the batch form over boundary
 * spans, invalid arguments and randomised spans, checking
 * return codes and accounting invariants. Digest
 * correctness against hashlib is the Python gate suite's
 * job; this driver's job is memory and UB safety plus
 * structural invariants on the sanitised build itself.
 * Prints SAN_DRIVER_OK and returns 0 on success. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int bal_v_msearch2(const uint8_t *, uint64_t, uint64_t,
                   unsigned, const uint8_t *, uint32_t *,
                   uint8_t *, uint64_t *, uint64_t *);
int bal_v_msearcha2(const uint8_t *, uint64_t, uint64_t,
                    unsigned, const uint8_t *, uint32_t *,
                    uint8_t *, uint64_t *, uint64_t *);
int bal_v_msearchs2(const uint8_t *, uint64_t, uint64_t,
                    unsigned, const uint8_t *, uint32_t *,
                    uint8_t *, uint64_t *, uint64_t *);
int bal_v_mbatch2(const uint8_t *, uint64_t, uint64_t,
                  unsigned, const uint8_t *, uint8_t *,
                  uint8_t *, uint64_t *, uint64_t *);

typedef int (*SearchFn)(const uint8_t *, uint64_t, uint64_t,
                        unsigned, const uint8_t *, uint32_t *,
                        uint8_t *, uint64_t *, uint64_t *);

static const uint8_t GENESIS[80] = {
  0x01, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x3b, 0xa3, 0xed, 0xfd, 0x7a, 0x7b, 0x12, 0xb2,
  0x7a, 0xc7, 0x2c, 0x3e, 0x67, 0x76, 0x8f, 0x61,
  0x7f, 0xc8, 0x1b, 0xc3, 0x88, 0x8a, 0x51, 0x32,
  0x3a, 0x9f, 0xb8, 0xaa, 0x4b, 0x1e, 0x5e, 0x4a,
  0x29, 0xab, 0x5f, 0x49, 0xff, 0xff, 0x00, 0x1d,
  0x1d, 0xac, 0x2b, 0x7c};
static const uint32_t GENESIS_NONCE = 2083236893u;

static int failures = 0;

#define CHECK(cond, msg) do { \
    if (!(cond)) { \
      printf("SAN FAIL: %s (line %d)\n", msg, __LINE__); \
      failures++; \
    } \
  } while (0)

static uint64_t rng_state = 0x9E3779B97F4A7C15ull;

static uint64_t rng_next(void) {
  uint64_t x = rng_state;
  x ^= x << 13;
  x ^= x >> 7;
  x ^= x << 17;
  rng_state = x;
  return x;
}

int main(void) {
  SearchFn arms[3] = {bal_v_msearch2, bal_v_msearcha2,
                      bal_v_msearchs2};
  const char *names[3] = {"B", "C", "S"};
  uint8_t max_target[32];
  uint8_t diff1[32];
  uint8_t d248[32];
  memset(max_target, 0xFF, 32);
  memset(diff1, 0, 32);
  diff1[26] = 0xFF;
  diff1[27] = 0xFF;
  memset(d248, 0, 32);
  d248[31] = 0x01; /* target_int 2^248, little-endian arg */

  for (int a = 0; a < 3; a++) {
    uint32_t nonce = 0;
    uint8_t dig[32];
    uint64_t att = 0, back = 0;
    /* genesis window, 1 and 2 threads */
    for (unsigned t = 1; t <= 2; t++) {
      int rc = arms[a](GENESIS, GENESIS_NONCE - 3, 100000, t,
                       diff1, &nonce, dig, &att, &back);
      CHECK(rc == 1 && nonce == GENESIS_NONCE, names[a]);
      if (a == 2) {
        CHECK(att == 100000, "scan attempted == count");
      } else if (t == 1) {
        CHECK(att == 16 && back == 16, "genesis wave accounting");
      }
    }
    /* boundary spans at the maximum target */
    static const uint64_t starts[5] = {
      0, 15, 100000, 0xFFFFFFC0ull, 0xFFFFFFFFull};
    static const uint64_t counts[5] = {1, 5, 16, 17, 33};
    for (int i = 0; i < 5; i++) {
      uint64_t start = starts[i];
      uint64_t count = counts[i];
      if (start + count > 0x100000000ull) count = 0x100000000ull - start;
      int rc = arms[a](GENESIS, start, count, 1, max_target,
                       &nonce, dig, &att, &back);
      CHECK(rc == 1 && nonce == (uint32_t)start, "boundary hit");
      CHECK(back % 16 == 0 && back >= att, "accounting shape");
    }
    /* invalid arguments */
    CHECK(arms[a](NULL, 0, 16, 1, max_target, &nonce, dig,
                  &att, &back) == -1, "null header");
    CHECK(arms[a](GENESIS, 0, 0, 1, max_target, &nonce, dig,
                  &att, &back) == -1, "zero count");
    CHECK(arms[a](GENESIS, 0, 16, 0, max_target, &nonce, dig,
                  &att, &back) == -1, "zero threads");
    CHECK(arms[a](GENESIS, 0xFFFFFFF8ull, 16, 1, max_target,
                  &nonce, dig, &att, &back) == -2, "range cross");
    /* randomised spans at density about 2^-8 */
    for (int trial = 0; trial < 200; trial++) {
      uint64_t start = rng_next() % (1ull << 28);
      uint64_t count = 1 + rng_next() % 5000;
      unsigned threads = 1 + (unsigned)(rng_next() % 4);
      int rc = arms[a](GENESIS, start, count, threads, d248,
                       &nonce, dig, &att, &back);
      CHECK(rc == 0 || rc == 1, "random rc");
      if (rc == 0) CHECK(att == count, "miss attempted");
      if (rc == 1) {
        CHECK(nonce >= start && nonce < start + count,
              "hit in range");
        CHECK(att <= count && back >= att, "hit accounting");
      }
      if (a == 2) CHECK(att == count, "scan always full");
    }
  }

  /* batch form at density 1 */
  {
    uint8_t hashes[32 * 1000];
    uint8_t flags[1000];
    uint64_t att = 0, back = 0;
    int rc = bal_v_mbatch2(GENESIS, 12345, 1000, 2, max_target,
                           hashes, flags, &att, &back);
    CHECK(rc == 0 && att == 1000, "mbatch accounting");
    int all = 1;
    for (int i = 0; i < 1000; i++) if (flags[i] != 1) all = 0;
    CHECK(all, "mbatch flags at density 1");
  }

  if (failures) {
    printf("SAN_DRIVER_FAILED failures=%d\n", failures);
    return 1;
  }
  printf("SAN_DRIVER_OK\n");
  return 0;
}
