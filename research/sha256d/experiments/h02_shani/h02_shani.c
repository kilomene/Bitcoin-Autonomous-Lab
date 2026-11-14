/* NOVA SHA-X EXP-002 (H-02): direct SHA-NI mining library.
 *
 * Exports the same counted ABI shape as the production and
 * intrinsics libraries (bal_h_batch2 / bal_h_search2 mirror
 * bal_c_batch2 / bal_i_batch2 semantics exactly: return 0 on a
 * completed batch, 1 on a found candidate, 0 on a miss,
 * negatives on errors; attempted counts are actuals summed
 * from per-worker slots). Two measurement variants ride along:
 * bal_h_batch2_full (no block-2 prefix) and bal_h_batch2_p2
 * (H-03 mode-2 prefix), so the prefix effect is measurable
 * through the identical accounting path.
 *
 * bal_h_compress exposes the raw one-block compression for
 * FIPS vector testing of the SHA-256 core itself.
 *
 * Concurrency and range semantics reuse the lab's shared
 * header mining/cpu/bal_search.h (per-search context, C11
 * atomic stop, mutex-published first winner, exact partition),
 * so this library is directly comparable to the incumbents.
 */
#include <stdint.h>
#include <string.h>
#include <stdatomic.h>
#include <pthread.h>

#include "shani_core.h"
#include "../../../../mining/cpu/bal_search.h"

_Atomic int bal_create_fail_after = -1;
_Atomic int bal_create_fail_calls = 0;
_Atomic int bal_mutex_fail_mask = 0;

void bal_h_compress(const uint32_t in[8], const uint8_t *block,
                    uint32_t out[8]) {
  h_compress_block(in, block, out);
}

/* ---- batch ---- */

typedef void (*hash_fn)(const HTemplate *, uint32_t, uint8_t *);

static void hash_p1(const HTemplate *tp, uint32_t n, uint8_t *d) {
  h_hash_nonce(tp, n, d);
}
static void hash_full(const HTemplate *tp, uint32_t n, uint8_t *d) {
  h_hash_nonce_full(tp, n, d);
}
static void hash_p2(const HTemplate *tp, uint32_t n, uint8_t *d) {
  h_hash_nonce_p2(tp, n, d);
}

typedef struct {
  const HTemplate *tp;
  hash_fn fn;
  uint64_t start;
  uint64_t begin, end;
  const uint8_t *target;
  uint8_t *hashes, *flags;
  uint64_t attempted;
} HJob;

static void *h_worker(void *arg) {
  HJob *job = (HJob *)arg;
  uint64_t done = 0;
  for (uint64_t i = job->begin; i < job->end; i++) {
    uint8_t d[32];
    job->fn(job->tp, (uint32_t)(job->start + i), d);
    memcpy(job->hashes + 32 * (size_t)i, d, 32);
    job->flags[i] = h_meets(d, job->target) ? 1 : 0;
    done++;
  }
  job->attempted = done;
  return NULL;
}

static int batch_impl(hash_fn fn, const uint8_t *header, uint64_t start,
                      uint64_t count, unsigned threads,
                      const uint8_t *target, uint8_t *hashes,
                      uint8_t *flags, uint64_t *out_attempted) {
  if (!header || !target || !hashes || !flags) return -1;
  if (!threads || threads > 16) return -1;
  int v = bal_validate_range(start, count);
  if (v != 0) return v;
  HTemplate tp;
  h_template_init(&tp, header);
  uint64_t begins[16], ends[16];
  unsigned spans = bal_partition(count, threads, begins, ends);
  pthread_t tids[16];
  int created[16] = {0};
  HJob jobs[16];
  for (unsigned sp = 0; sp < spans; sp++) {
    jobs[sp] = (HJob){&tp, fn, start, begins[sp], ends[sp], target,
                      hashes, flags, 0};
    if (bal_pthread_create(&tids[sp], NULL, h_worker, &jobs[sp]) != 0) {
      h_worker(&jobs[sp]);
    } else {
      created[sp] = 1;
    }
  }
  for (unsigned sp = 0; sp < spans; sp++)
    if (created[sp]) pthread_join(tids[sp], NULL);
  if (out_attempted) {
    uint64_t total = 0;
    for (unsigned sp = 0; sp < spans; sp++) total += jobs[sp].attempted;
    *out_attempted = total;
  }
  return 0;
}

int bal_h_batch2(const uint8_t *header, uint64_t start, uint64_t count,
                 unsigned threads, const uint8_t *target, uint8_t *hashes,
                 uint8_t *flags, uint64_t *out_attempted) {
  return batch_impl(hash_p1, header, start, count, threads, target,
                    hashes, flags, out_attempted);
}

int bal_h_batch2_full(const uint8_t *header, uint64_t start,
                      uint64_t count, unsigned threads,
                      const uint8_t *target, uint8_t *hashes,
                      uint8_t *flags, uint64_t *out_attempted) {
  return batch_impl(hash_full, header, start, count, threads, target,
                    hashes, flags, out_attempted);
}

int bal_h_batch2_p2(const uint8_t *header, uint64_t start, uint64_t count,
                    unsigned threads, const uint8_t *target,
                    uint8_t *hashes, uint8_t *flags,
                    uint64_t *out_attempted) {
  return batch_impl(hash_p2, header, start, count, threads, target,
                    hashes, flags, out_attempted);
}

/* ---- counted early-exit search (mode 1 prefix) ---- */

typedef struct {
  const HTemplate *tp;
  uint64_t start;
  uint64_t begin, end;
  const uint8_t *target;
  BalSearchCtx *ctx;
  uint64_t attempted;
} HSJob;

static void *h_sworker(void *arg) {
  HSJob *job = (HSJob *)arg;
  uint64_t done = 0;
  for (uint64_t i = job->begin; i < job->end; i++) {
    if (bal_ctx_stopped(job->ctx)) break;
    uint8_t d[32];
    uint32_t nonce = (uint32_t)(job->start + i);
    h_hash_nonce(job->tp, nonce, d);
    done++;
    if (h_meets(d, job->target)) {
      bal_ctx_publish(job->ctx, nonce, d);
      break;
    }
  }
  job->attempted = done;
  return NULL;
}

int bal_h_search2(const uint8_t *header, uint64_t start, uint64_t count,
                  unsigned threads, const uint8_t *target,
                  uint32_t *out_nonce, uint8_t *out_digest,
                  uint64_t *out_attempted) {
  if (!header || !target || !out_nonce || !out_digest) return -1;
  if (!threads || threads > 16) return -1;
  int v = bal_validate_range(start, count);
  if (v != 0) return v;
  HTemplate tp;
  h_template_init(&tp, header);
  BalSearchCtx ctx;
  if (bal_ctx_init(&ctx) != 0) return -4;
  uint64_t begins[16], ends[16];
  unsigned spans = bal_partition(count, threads, begins, ends);
  pthread_t tids[16];
  int created[16] = {0};
  HSJob jobs[16];
  for (unsigned sp = 0; sp < spans; sp++) {
    jobs[sp] = (HSJob){&tp, start, begins[sp], ends[sp], target, &ctx, 0};
    if (bal_pthread_create(&tids[sp], NULL, h_sworker, &jobs[sp]) != 0) {
      h_sworker(&jobs[sp]);
    } else {
      created[sp] = 1;
    }
  }
  for (unsigned sp = 0; sp < spans; sp++)
    if (created[sp]) pthread_join(tids[sp], NULL);
  if (out_attempted) {
    uint64_t total = 0;
    for (unsigned sp = 0; sp < spans; sp++) total += jobs[sp].attempted;
    *out_attempted = total;
  }
  if (bal_ctx_publish_failed(&ctx)) {
    bal_ctx_destroy(&ctx);
    return -3;
  }
  int found = ctx.found_valid;
  if (found) {
    *out_nonce = ctx.found_nonce;
    memcpy(out_digest, ctx.found_digest, 32);
  }
  bal_ctx_destroy(&ctx);
  return found ? 1 : 0;
}
