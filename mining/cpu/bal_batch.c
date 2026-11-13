/* Batch SHA256d nonce search as a shared library, midstate optimized.
 *
 * Per header, the first SHA-256 compression (bytes 0..63) is computed
 * once. Each nonce then costs exactly two compressions: the second
 * header block (bytes 64..79 with the nonce patched in, plus
 * padding) and the outer hash block. Uses OpenSSL's low-level
 * SHA256_Transform, which dispatches to SHA-NI on this CPU.
 *
 * Exported for gpu/engine.py (ComputeEngine) through ctypes. Output
 * layout matches the CUDA library: hashes is count*32 bytes, flags
 * is count bytes (1 when the digest meets the little-endian target).
 */
#include <openssl/sha.h>
#include <pthread.h>
#include <stdint.h>
#include <string.h>

typedef struct {
  const uint8_t *header;
  uint32_t midstate[8];
  uint64_t start;
  uint32_t begin, end;
  const uint8_t *target;
  uint8_t *hashes;
  uint8_t *flags;
} Job;

static int meets(const uint8_t *digest, const uint8_t *target) {
  for (int i = 31; i >= 0; i--) {
    if (digest[i] < target[i]) return 1;
    if (digest[i] > target[i]) return 0;
  }
  return 1;
}

static void store_be32(uint8_t *out, uint32_t v) {
  out[0] = (uint8_t)(v >> 24); out[1] = (uint8_t)(v >> 16);
  out[2] = (uint8_t)(v >> 8);  out[3] = (uint8_t)v;
}

static void *worker(void *arg) {
  Job *job = (Job *)arg;
  for (uint32_t i = job->begin; i < job->end; i++) {
    uint32_t nonce = (uint32_t)(job->start + i);
    /* Second block of the inner hash: header bytes 64..79 + padding. */
    uint8_t block[64];
    memset(block, 0, sizeof(block));
    memcpy(block, job->header + 64, 12);            /* bytes 64..75 */
    block[12] = (uint8_t)(nonce & 0xff);            /* nonce, LE in header */
    block[13] = (uint8_t)((nonce >> 8) & 0xff);
    block[14] = (uint8_t)((nonce >> 16) & 0xff);
    block[15] = (uint8_t)((nonce >> 24) & 0xff);
    block[16] = 0x80;
    store_be32(block + 60, 640);                    /* 80 bytes * 8 */
    /* SHA256_Transform takes the block as big-endian words; the raw
       memory layout above is exactly that serialization. */
    SHA256_CTX ictx;
    memset(&ictx, 0, sizeof(ictx));
    for (int w = 0; w < 8; w++) ictx.h[w] = job->midstate[w];
    SHA256_Transform(&ictx, block);
    uint32_t state[8];
    for (int w = 0; w < 8; w++) state[w] = ictx.h[w];
    uint8_t inner[32];
    for (int w = 0; w < 8; w++) store_be32(inner + 4 * w, state[w]);
    /* Outer hash: one block, standard initial state. */
    uint8_t oblock[64];
    memset(oblock, 0, sizeof(oblock));
    memcpy(oblock, inner, 32);
    oblock[32] = 0x80;
    store_be32(oblock + 60, 256);
    static const uint32_t H0[8] = {0x6a09e667, 0xbb67ae85, 0x3c6ef372,
        0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};
    SHA256_CTX octx;
    memset(&octx, 0, sizeof(octx));
    for (int w = 0; w < 8; w++) octx.h[w] = H0[w];
    SHA256_Transform(&octx, oblock);
    uint32_t ostate[8];
    for (int w = 0; w < 8; w++) ostate[w] = octx.h[w];
    uint8_t digest[32];
    for (int w = 0; w < 8; w++) store_be32(digest + 4 * w, ostate[w]);
    memcpy(job->hashes + (size_t)i * 32, digest, 32);
    job->flags[i] = (uint8_t)meets(digest, job->target);
  }
  return NULL;
}

int bal_c_batch(const uint8_t *header, uint64_t start, uint32_t count,
                unsigned threads, const uint8_t *target, uint8_t *hashes,
                uint8_t *flags) {
  if (!count || !threads || threads > 16) return -1;
  if (start + count > 0x100000000ULL) return -1;
  /* Midstate: hash the constant first 64 header bytes. */
  SHA256_CTX ctx;
  SHA256_Init(&ctx);
  SHA256_Update(&ctx, header, 64);
  uint32_t midstate[8];
  for (int w = 0; w < 8; w++) midstate[w] = ctx.h[w];
  if (threads > count) threads = count;
  pthread_t tids[16];
  Job jobs[16];
  uint32_t chunk = (count + threads - 1) / threads;
  unsigned launched = 0, spans = 0;
  for (unsigned t = 0; t < threads; t++) {
    uint32_t begin = t * chunk;
    if (begin >= count) break;
    uint32_t end = begin + chunk;
    if (end > count) end = count;
    jobs[spans] = (Job){header, {0}, start, begin, end, target, hashes, flags};
    memcpy(jobs[spans].midstate, midstate, sizeof(midstate));
    if (pthread_create(&tids[spans], NULL, worker, &jobs[spans]) != 0) {
      worker(&jobs[spans]);
    } else {
      launched++;
    }
    spans++;
  }
  for (unsigned t = 0; t < launched; t++) pthread_join(tids[t], NULL);
  return 0;
}
