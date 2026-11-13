// Host CPU validation of the shared CUDA SHA-256 source.
// Prints digests that the Python tests compare against hashlib:
//   line 1: sha256("abc")
//   line 2: sha256d of the Bitcoin genesis header (real nonce)
//   line 3: count of nonces in [0,100000) whose sha256d of the
//           genesis header meets the regtest pow-limit target
//   line 4: sha256 of 1,000,000 bytes of 0x61 (FIPS long-message vector)
#include <cstdio>
#include <cstring>
#include "kernels/sha256.h"

static void print_hex(const uint8_t* d) {
  for (int i = 0; i < 32; i++) printf("%02x", d[i]);
  printf("\n");
}

int main() {
  uint8_t out[32];
  bal_sha256((const uint8_t*)"abc", 3, out);
  print_hex(out);

  // Genesis header, internal order (prevhash zero, merkle reversed).
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
  uint8_t gen[32];
  bal_sha256d_header(header, 2083236893u, gen);
  // print in display order (reversed), matching the known block hash
  for (int i = 31; i >= 0; i--) printf("%02x", gen[i]);
  printf("\n");

  // Regtest pow limit target, little endian bytes of 0x7fffff * 2^232.
  uint8_t target[32];
  memset(target, 0, sizeof(target));
  target[29] = 0xff; target[30] = 0xff; target[31] = 0x7f;
  long count = 0;
  for (uint32_t n = 0; n < 100000; n++) {
    uint8_t d[32];
    bal_sha256d_header(header, n, d);
    if (bal_meets_target(d, target)) count++;
  }
  printf("%ld\n", count);

  static uint8_t big[1000000];
  memset(big, 0x61, sizeof(big));
  bal_sha256(big, sizeof(big), out);
  print_hex(out);
  return 0;
}
