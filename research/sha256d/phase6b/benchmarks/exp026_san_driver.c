/* EXP-026 sanitizer driver: builds the two candidate
 * kernels under ASan/UBSan and runs the boundary and
 * invalid-argument corpus plus randomised spans through
 * every new export. Prints SAN_DRIVER_OK on success. */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

int bal_v_e26t_search2(const uint8_t *, uint64_t, uint64_t,
                       unsigned, const uint8_t *, uint32_t *,
                       uint8_t *, uint64_t *, uint64_t *);
int bal_v_e26t_batch2(const uint8_t *, uint64_t, uint64_t,
                      unsigned, const uint8_t *, uint8_t *,
                      uint8_t *, uint64_t *, uint64_t *);
int bal_v_e26d_search2(const uint8_t *, uint64_t, uint64_t,
                       unsigned, const uint8_t *, uint32_t *,
                       uint8_t *, uint64_t *, uint64_t *);

static uint64_t rng_state = 0x260261114ULL;
static uint64_t rnd(void) {
  rng_state ^= rng_state << 13;
  rng_state ^= rng_state >> 7;
  rng_state ^= rng_state << 17;
  return rng_state;
}

int main(void) {
  uint8_t header[80];
  for (int i = 0; i < 80; i++) header[i] = (uint8_t)rnd();
  uint8_t target_max[32];
  memset(target_max, 0xff, 32);
  uint8_t target_zero[32] = {0};
  uint32_t nonce = 0;
  uint8_t dig[32];
  uint64_t att = 0, back = 0;
  /* invalid arguments */
  if (bal_v_e26t_search2(NULL, 0, 16, 1, target_max, &nonce,
                         dig, &att, &back) != -1) return 1;
  if (bal_v_e26d_search2(NULL, 0, 16, 1, target_max, &nonce,
                         dig, &att, &back) != -1) return 2;
  if (bal_v_e26t_search2(header, 0xFFFFFFF0u, 32, 1, target_max,
                         &nonce, dig, &att, &back) != -2) return 3;
  if (bal_v_e26d_search2(header, 0xFFFFFFF0u, 32, 1, target_max,
                         &nonce, dig, &att, &back) != -2) return 4;
  /* boundary spans */
  static const struct { uint64_t s, c; } spans[] = {
    {0, 1}, {0, 5}, {0, 15}, {0, 16}, {0, 17}, {0, 31},
    {0, 32}, {0, 33}, {0, 100}, {12345, 17},
    {0xFFFFFFC0ULL, 64}, {0xFFFFFFFFULL, 1},
    {0xFFFFFFF0ULL, 16}, {0xFFFFFFE0ULL, 32}};
  for (unsigned i = 0; i < sizeof(spans) / sizeof(spans[0]); i++) {
    int rc = bal_v_e26t_search2(header, spans[i].s, spans[i].c,
                                1, target_max, &nonce, dig,
                                &att, &back);
    if (rc != 1 || nonce != (uint32_t)spans[i].s) return 5;
    rc = bal_v_e26d_search2(header, spans[i].s, spans[i].c, 1,
                            target_max, &nonce, dig, &att, &back);
    if (rc != 1 || nonce != (uint32_t)spans[i].s) return 6;
    rc = bal_v_e26t_search2(header, spans[i].s, spans[i].c, 2,
                            target_zero, &nonce, dig, &att, &back);
    if (rc != 0) return 7;
    rc = bal_v_e26d_search2(header, spans[i].s, spans[i].c, 2,
                            target_zero, &nonce, dig, &att, &back);
    if (rc != 0) return 8;
  }
  /* randomised spans, both densities, batch form too */
  uint8_t hashes[32 * 4096];
  uint8_t flags[4096];
  for (int it = 0; it < 200; it++) {
    uint64_t start = rnd() % (1u << 24);
    uint64_t count = 1 + rnd() % 4096;
    unsigned th = 1 + (unsigned)(rnd() % 3);
    const uint8_t *tgt = (it & 1) ? target_max : target_zero;
    bal_v_e26t_search2(header, start, count, th, tgt, &nonce,
                       dig, &att, &back);
    bal_v_e26d_search2(header, start, count, th, tgt, &nonce,
                       dig, &att, &back);
    if (count <= 4096) {
      int rc = bal_v_e26t_batch2(header, start, count, th,
                                 target_max, hashes, flags,
                                 &att, &back);
      if (rc != 0 || att != count) return 9;
    }
  }
  printf("SAN_DRIVER_OK\n");
  return 0;
}
