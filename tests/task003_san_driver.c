/* Task 003 sanitizer driver: exercises batch, counted search,
 * boundary ranges, pthread_create failure injection, mutex failure
 * injection (Task 003.1) and 8 simultaneous independent searches
 * for one CPU library at a time. Built with ASan/UBSan and with
 * TSan by tests/test_task003_corrections.py.
 *
 * Default: bal_batch.c entry points. Define INTRIN for
 * bal_sha_intrin.c.
 */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <pthread.h>
#include <assert.h>

extern int bal_c_batch2(const uint8_t*, uint64_t, uint64_t, unsigned, const uint8_t*, uint8_t*, uint8_t*, uint64_t*);
extern int bal_c_search2(const uint8_t*, uint64_t, uint64_t, unsigned, const uint8_t*, uint32_t*, uint8_t*, uint64_t*);
extern void bal_c_test_set_create_fail_after(int);
extern void bal_c_test_set_mutex_fail_mask(int);
#define BATCH2 bal_c_batch2
#define SEARCH2 bal_c_search2
#define SETFAIL bal_c_test_set_create_fail_after
#define SETMUTEX bal_c_test_set_mutex_fail_mask
#ifdef INTRIN
#undef BATCH2
#undef SEARCH2
#undef SETFAIL
#undef SETMUTEX
extern int bal_i_batch2(const uint8_t*, uint64_t, uint64_t, unsigned, const uint8_t*, uint8_t*, uint8_t*, uint64_t*);
extern int bal_i_search2(const uint8_t*, uint64_t, uint64_t, unsigned, const uint8_t*, uint32_t*, uint8_t*, uint64_t*);
extern void bal_i_test_set_create_fail_after(int);
extern void bal_i_test_set_mutex_fail_mask(int);
#define BATCH2 bal_i_batch2
#define SEARCH2 bal_i_search2
#define SETFAIL bal_i_test_set_create_fail_after
#define SETMUTEX bal_i_test_set_mutex_fail_mask
#endif

static const uint8_t GEN[80] = {
 0x01,0,0,0, 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
 0x3b,0xa3,0xed,0xfd,0x7a,0x7b,0x12,0xb2,0x7a,0xc7,0x2c,0x3e,0x67,0x76,0x8f,0x61,
 0x7f,0xc8,0x1b,0xc3,0x88,0x8a,0x51,0x32,0x3a,0x9f,0xb8,0xaa,0x4b,0x1e,0x5e,0x4a,
 0x29,0xab,0x5f,0x49, 0xff,0xff,0x00,0x1d, 0x1d,0xac,0x2b,0x7c};

static void *concurrent(void *arg) {
  (void)arg;
  uint8_t target[32] = {0};
  target[26] = 0xFF; target[27] = 0xFF; /* DIFF1, little endian */
  for (int r = 0; r < 10; r++) {
    uint32_t nonce; uint8_t dig[32]; uint64_t att;
    int rc = SEARCH2(GEN, 2083236890ULL, 5000, 4, target, &nonce, dig, &att);
    assert(rc == 1 && nonce == 2083236893U);
  }
  return NULL;
}

int main(void) {
  uint8_t ones[32]; memset(ones, 0xFF, 32);
  uint8_t hashes[32 * 1000]; uint8_t flags[1000]; uint64_t att = 0;
  assert(BATCH2(GEN, 0, 1000, 4, ones, hashes, flags, &att) == 0 && att == 1000);
  uint8_t one_target[32] = {0}; one_target[0] = 1;
  uint32_t nonce; uint8_t dig[32];
  assert(SEARCH2(GEN, 0xFFFFFFFEULL, 2, 2, one_target, &nonce, dig, &att) == 0 && att == 2);
  assert(SEARCH2(GEN, 0xFFFFFFFFULL, 2, 1, one_target, &nonce, dig, &att) == -2);
  /* pthread_create failure injection: no work lost. */
  SETFAIL(0);
  uint8_t dt[32] = {0}; dt[26] = 0xFF; dt[27] = 0xFF;
  assert(SEARCH2(GEN, 2083236890ULL, 2000, 4, dt, &nonce, dig, &att) == 1 && nonce == 2083236893U);
  SETFAIL(-1);
  /* Task 003.1: mutex init failure -> -4, no worker started. */
  SETMUTEX(1);
  assert(SEARCH2(GEN, 2083236890ULL, 2000, 4, dt, &nonce, dig, &att) == -4);
  SETMUTEX(0);
  /* Task 003.1: mutex lock failure on publish -> -3, no winner. */
  SETMUTEX(2);
  assert(SEARCH2(GEN, 2083236893ULL, 1, 1, dt, &nonce, dig, &att) == -3);
  SETMUTEX(0);
  /* Recovery: the library works again after injection is off. */
  assert(SEARCH2(GEN, 2083236890ULL, 2000, 4, dt, &nonce, dig, &att) == 1 && nonce == 2083236893U);
  pthread_t th[8];
  for (int i = 0; i < 8; i++) assert(pthread_create(&th[i], NULL, concurrent, NULL) == 0);
  for (int i = 0; i < 8; i++) pthread_join(th[i], NULL);
  printf("SAN DRIVER OK\n");
  return 0;
}
