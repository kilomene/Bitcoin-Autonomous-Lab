// Host validation for the Task 002 GPU changes: the midstate kernel
// path, the circular 16-word schedule variant, and the bounded
// candidate-recording primitive. This compiles the exact shared
// header the CUDA kernel uses (kernels/sha256.h) for the host CPU.
// It proves LOGIC only; it is not GPU execution evidence.
//
// Output lines (parsed by tests/test_gpu_correction.py):
//   1: genesis hash via the midstate path (display order)
//   2: genesis hash via the circular-schedule midstate path
//   3: "sample <hex>" sha256d (internal order) of a fixed pseudo
//      random header at nonce 12345 via the midstate path
//   4: "random_mismatches <n>" full vs midstate vs circular over
//      randomized headers and nonces, counted inside this program
//   5: "cand total <t> recorded <r> overflow <o>" bounded candidate
//      recording over a deterministic range with capacity 3
//   6: "concurrent counter <c> recorded <r> overflow <o>" 8 host
//      threads recording 40000 synthetic candidates into capacity 100
//   7: "range_valid <n>" Task 003.7 subtraction-based nonce-range
//      validation cases passed out of the total checked
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <thread>
#include <vector>
#include "kernels/sha256.h"

static void print_hex_rev(const uint8_t* d) {
  for (int i = 31; i >= 0; i--) printf("%02x", d[i]);
  printf("\n");
}

static uint32_t lcg_state = 42;
static uint8_t lcg_byte() {
  lcg_state = lcg_state * 1664525u + 1013904223u;
  return (uint8_t)(lcg_state >> 24);
}

int main() {
  static const char* GENESIS_HEX =
    "01000000"
    "0000000000000000000000000000000000000000000000000000000000000000"
    "3ba3edfd7a7b12b27ac72c3e67768f617fc81bc3888a51323a9fb8aa4b1e5e4a"
    "29ab5f49ffff001d1dac2b7c";
  uint8_t header[80];
  auto nib = [](char c) -> uint8_t {
    return (uint8_t)(c <= '9' ? c - '0' : (c <= 'F' ? c - 'A' + 10 : c - 'a' + 10));
  };
  for (int i = 0; i < 80; i++)
    header[i] = (uint8_t)((nib(GENESIS_HEX[2 * i]) << 4) | nib(GENESIS_HEX[2 * i + 1]));

  uint8_t d[32];
  bal_sha256d_header_midstate(header, 2083236893u, d);
  print_hex_rev(d);
  bal_sha256d_header_circ(header, 2083236893u, d);
  print_hex_rev(d);

  // Fixed pseudo random header sample (same LCG seed as the test).
  uint8_t sample_header[80];
  lcg_state = 42;
  for (int i = 0; i < 80; i++) sample_header[i] = lcg_byte();
  bal_sha256d_header_midstate(sample_header, 12345u, d);
  printf("sample ");
  for (int i = 0; i < 32; i++) printf("%02x", d[i]);
  printf("\n");

  // Randomized differential: full path vs midstate vs circular.
  long mismatches = 0;
  lcg_state = 1234567;
  for (int t = 0; t < 300; t++) {
    uint8_t h[80];
    for (int i = 0; i < 80; i++) h[i] = lcg_byte();
    for (uint32_t nonce : {0u, 1u, 12345u, 0xFFFFFFFEu, 0xFFFFFFFFu}) {
      uint8_t a[32], b[32], c[32];
      bal_sha256d_header(h, nonce, a);
      bal_sha256d_header_midstate(h, nonce, b);
      bal_sha256d_header_circ(h, nonce, c);
      if (memcmp(a, b, 32) || memcmp(a, c, 32)) mismatches++;
    }
  }
  printf("random_mismatches %ld\n", mismatches);

  // Bounded candidate recording, sequential and deterministic.
  uint8_t target[32];
  memset(target, 0, sizeof(target));
  target[29] = 0xff; target[30] = 0xff; target[31] = 0x7f; // regtest pow limit, LE
  uint32_t counter = 0, overflow = 0;
  const uint32_t cap = 3;
  uint32_t cand_nonces[3];
  uint8_t cand_digests[3 * 32];
  for (uint32_t n = 0; n < 2000; n++) {
    uint8_t dig[32];
    bal_sha256d_header_midstate(header, n, dig);
    if (bal_meets_target(dig, target))
      bal_record_candidate(&counter, cap, cand_nonces, cand_digests,
                           &overflow, n, dig);
  }
  printf("cand total %u recorded %u overflow %u\n", counter,
         counter < cap ? counter : cap, overflow);

  // Concurrent recording: the same primitive under 8 host threads.
  uint32_t counter2 = 0, overflow2 = 0;
  const uint32_t cap2 = 100;
  std::vector<uint32_t> nonces2(cap2, 0xFFFFFFFFu);
  std::vector<uint8_t> digests2(cap2 * 32, 0);
  {
    std::vector<std::thread> pool;
    for (uint32_t t = 0; t < 8; t++) {
      pool.emplace_back([&, t]() {
        uint8_t dig[32];
        memset(dig, (int)t, sizeof(dig));
        for (uint32_t i = 0; i < 5000; i++)
          bal_record_candidate(&counter2, cap2, nonces2.data(),
                               digests2.data(), &overflow2,
                               t * 5000 + i, dig);
      });
    }
    for (auto& th : pool) th.join();
  }
  uint32_t recorded2 = 0;
  for (uint32_t v : nonces2) if (v != 0xFFFFFFFFu) recorded2++;
  printf("concurrent counter %u recorded %u overflow %u\n", counter2,
         recorded2, overflow2);

  // Task 003.7: subtraction-based nonce-range validation, exactly
  // the logic the CUDA C ABI calls before any kernel launch.
  struct RangeCase { uint64_t start, count; int valid; };
  const RangeCase cases[] = {
    {0ULL, 1ULL, 1},                       // nonce zero
    {0xFFFFFFFFULL, 1ULL, 1},              // only the final nonce
    {0xFFFFFFFEULL, 2ULL, 1},              // ends exactly at 2^32
    {0ULL, 0x100000000ULL, 1},             // the whole space
    {0ULL, 0ULL, 0},                       // empty
    {0xFFFFFFFFULL, 2ULL, 0},              // crosses the boundary
    {0ULL, 0x100000001ULL, 0},             // count beyond the space
    {0x100000000ULL, 1ULL, 0},             // start beyond the space
    {0xFFFFFFFFFFFFFFFFULL, 1ULL, 0},      // start near 2^64 (wrap)
    {0xFFFFFFFFFFFFFFFEULL, 4ULL, 0},      // start + count would wrap
    {5ULL, 0xFFFFFFFFFFFFFFFBULL, 0},      // huge count
    {0x80000000ULL, 0x80000000ULL, 1},     // upper half exactly
  };
  int range_ok = 0, range_total = 0;
  for (const RangeCase& c : cases) {
    range_total++;
    if (bal_nonce_range_valid(c.start, c.count) == c.valid) range_ok++;
  }
  printf("range_valid %d of %d\n", range_ok, range_total);
  return 0;
}
