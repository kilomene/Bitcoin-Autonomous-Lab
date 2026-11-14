/* Shared, corrected concurrency and nonce-range design for the CPU
 * search engines (bal_batch.c and bal_sha_intrin.c).
 *
 * This header replaces the old pattern of file-scope volatile
 * globals (g_stop, g_found_nonce, g_found_digest), which were data
 * races under the C11 memory model and made simultaneous
 * independent searches corrupt each other. The design here:
 *
 * - Every search call allocates its own BalSearchCtx on its own
 *   stack. There is no shared mutable search state, so independent
 *   searches may run concurrently in the same process and the code
 *   is reentrant.
 * - The stop flag is a C11 _Atomic int, never volatile.
 * - The winner result (nonce plus digest) is published under a
 *   mutex: the first worker to find a qualifying digest locks the
 *   context, and only if no winner exists yet does it copy its
 *   nonce and digest and mark the result valid. It then sets the
 *   atomic stop flag. Losers never overwrite the winner. The
 *   caller reads the winner only after joining every worker, and
 *   pthread_join provides the happens-before edge that makes the
 *   published bytes safe to read.
 * - Each worker counts its own attempted hashes into its own job
 *   slot; the caller sums the slots after joining. Counts are
 *   therefore actual attempts, never requested batch sizes.
 * - Thread creation is tracked per span: each span has its own
 *   created flag, and exactly the threads that were created are
 *   joined. The old code joined tids[0..launched), which assumed
 *   created threads occupy the first positions of the array; a
 *   failure in the middle silently joined an uninitialized slot
 *   and leaked a running thread.
 * - If pthread_create fails for a span, that span runs
 *   synchronously in the calling thread. The context mutex makes
 *   that safe even when a winner is being published concurrently.
 *
 * Nonce ranges are 64-bit half-open intervals [start, start+count)
 * over the 32-bit nonce space. A range is valid only when
 * count >= 1, start <= 0xFFFFFFFF, and start + count <= 2^32,
 * checked in 64-bit arithmetic so nothing can wrap. The final
 * nonce 0xFFFFFFFF is included exactly when the interval ends at
 * 2^32. Workers receive disjoint contiguous sub-intervals that
 * partition the requested interval with no gaps and no overlap.
 *
 * Test support: bal_create_fail_after / bal_create_fail_calls form
 * a controlled pthread_create failure-injection hook. A test sets
 * bal_create_fail_after to N (and the call counter to 0) through
 * the library's exported setter; the N+1-th and later creation
 * attempts in that process then fail with EAGAIN, exercising the
 * synchronous fallback under test control. Production code never
 * sets it (it stays -1, disabled).
 */
#ifndef BAL_SEARCH_H
#define BAL_SEARCH_H

#include <errno.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdint.h>
#include <string.h>

/* Defined once in each translation unit that includes this header. */
extern _Atomic int bal_create_fail_after;
extern _Atomic int bal_create_fail_calls;

static inline int bal_pthread_create(pthread_t *tid, const pthread_attr_t *attr,
                                     void *(*start_fn)(void *), void *arg) {
  int limit = atomic_load_explicit(&bal_create_fail_after,
                                   memory_order_relaxed);
  if (limit >= 0) {
    int call = atomic_fetch_add_explicit(&bal_create_fail_calls, 1,
                                         memory_order_relaxed);
    if (call >= limit) return EAGAIN;
  }
  return pthread_create(tid, attr, start_fn, arg);
}

typedef struct {
  _Atomic int stop;
  pthread_mutex_t winner_lock;
  int found_valid;
  uint32_t found_nonce;
  uint8_t found_digest[32];
} BalSearchCtx;

static inline void bal_ctx_init(BalSearchCtx *ctx) {
  atomic_init(&ctx->stop, 0);
  pthread_mutex_init(&ctx->winner_lock, NULL);
  ctx->found_valid = 0;
  ctx->found_nonce = 0;
  memset(ctx->found_digest, 0, sizeof(ctx->found_digest));
}

static inline void bal_ctx_destroy(BalSearchCtx *ctx) {
  pthread_mutex_destroy(&ctx->winner_lock);
}

static inline int bal_ctx_stopped(const BalSearchCtx *ctx) {
  return atomic_load_explicit(&ctx->stop, memory_order_acquire);
}

/* Publish a candidate winner. Only the first publisher wins; the
 * digest and nonce are copied while holding the lock, then the
 * stop flag is raised with release semantics. */
static inline void bal_ctx_publish(BalSearchCtx *ctx, uint32_t nonce,
                                   const uint8_t digest[32]) {
  pthread_mutex_lock(&ctx->winner_lock);
  if (!ctx->found_valid) {
    memcpy(ctx->found_digest, digest, 32);
    ctx->found_nonce = nonce;
    ctx->found_valid = 1;
  }
  pthread_mutex_unlock(&ctx->winner_lock);
  atomic_store_explicit(&ctx->stop, 1, memory_order_release);
}

/* Validate a 64-bit half-open nonce interval against the 32-bit
 * nonce space. Returns 0 when valid, -1 for a null or empty range,
 * -2 when the interval exceeds the nonce space. All comparisons
 * are done in uint64_t and cannot overflow: start and count are
 * each required to be at most 2^32 before they are added. */
static inline int bal_validate_range(uint64_t start, uint64_t count) {
  if (count == 0) return -1;
  if (start > 0xFFFFFFFFULL) return -2;
  if (count > 0x100000000ULL) return -2;
  if (start + count > 0x100000000ULL) return -2;
  return 0;
}

/* Partition [0, count) into at most `threads` contiguous disjoint
 * spans. Span t is written to begin_out[t] / end_out[t]; the number
 * of spans is returned. Spans cover the interval exactly: no nonce
 * is duplicated and none is skipped, including when count is not
 * divisible by the thread count, and the final span ends exactly
 * at count. */
static inline unsigned bal_partition(uint64_t count, unsigned threads,
                                     uint64_t *begin_out, uint64_t *end_out) {
  if (threads == 0) return 0;
  if ((uint64_t)threads > count) threads = (unsigned)count;
  uint64_t chunk = (count + threads - 1) / threads;
  unsigned spans = 0;
  for (unsigned t = 0; t < threads; t++) {
    uint64_t begin = (uint64_t)t * chunk;
    if (begin >= count) break;
    uint64_t end = begin + chunk;
    if (end > count) end = count;
    begin_out[spans] = begin;
    end_out[spans] = end;
    spans++;
  }
  return spans;
}

#endif /* BAL_SEARCH_H */
