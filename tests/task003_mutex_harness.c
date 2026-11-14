/* Task 003.1 harness: exercises mining/cpu/bal_search.h directly.
 *
 * Proves:
 * - normal context init, first-publisher-wins, destroy;
 * - simulated pthread_mutex_init failure: bal_ctx_init returns the
 *   error, the context is NOT marked initialized, and destroy is a
 *   safe no-op (an uninitialized mutex is never destroyed);
 * - simulated mutex lock failure: bal_ctx_publish returns -1,
 *   publishes nothing (found_valid stays 0), and records the
 *   publish error for the caller.
 *
 * Built and run by tests/test_task003_corrections.py, including
 * under AddressSanitizer/UBSan and ThreadSanitizer.
 */
#include <pthread.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

_Atomic int bal_create_fail_after = -1;
_Atomic int bal_create_fail_calls = 0;
_Atomic int bal_mutex_fail_mask = 0;

#include "../mining/cpu/bal_search.h"

static int failures = 0;
#define CHECK(cond, msg) do { \
  if (!(cond)) { printf("FAIL: %s\n", msg); failures++; } } while (0)

int main(void) {
  uint8_t dig[32];
  memset(dig, 7, sizeof(dig));

  /* Normal initialization, publish, destruction. */
  BalSearchCtx ctx;
  CHECK(bal_ctx_init(&ctx) == 0, "normal init succeeds");
  CHECK(ctx.mutex_ready == 1, "context marked initialized");
  CHECK(bal_ctx_publish(&ctx, 42, dig) == 0, "publish succeeds");
  CHECK(ctx.found_valid == 1 && ctx.found_nonce == 42,
        "winner recorded");
  CHECK(bal_ctx_publish(&ctx, 43, dig) == 0, "second publish ok");
  CHECK(ctx.found_nonce == 42, "first publisher still wins");
  CHECK(bal_ctx_publish_failed(&ctx) == 0, "no publish error");
  bal_ctx_destroy(&ctx);
  CHECK(ctx.mutex_ready == 0, "destroy clears readiness");

  /* Simulated mutex initialization failure. */
  atomic_store(&bal_mutex_fail_mask, 1);
  BalSearchCtx bad;
  int rc = bal_ctx_init(&bad);
  CHECK(rc != 0, "failed mutex init is propagated to the caller");
  CHECK(bad.mutex_ready == 0,
        "context not marked initialized after failed init");
  bal_ctx_destroy(&bad); /* must not destroy an uninitialized mutex */
  CHECK(bad.mutex_ready == 0, "destroy after failed init is a no-op");
  atomic_store(&bal_mutex_fail_mask, 0);

  /* After the failure, a fresh context works again. */
  BalSearchCtx again;
  CHECK(bal_ctx_init(&again) == 0, "init recovers after injection off");
  bal_ctx_destroy(&again);

  /* Simulated mutex lock failure during publish. */
  BalSearchCtx lk;
  CHECK(bal_ctx_init(&lk) == 0, "init for lock test");
  atomic_store(&bal_mutex_fail_mask, 2);
  CHECK(bal_ctx_publish(&lk, 99, dig) != 0,
        "publish reports the lock failure");
  atomic_store(&bal_mutex_fail_mask, 0);
  CHECK(lk.found_valid == 0,
        "nothing published when locking fails (no corrupt winner)");
  CHECK(bal_ctx_publish_failed(&lk) == 1,
        "publish error recorded for the caller");
  CHECK(bal_ctx_stopped(&lk) == 1,
        "stop raised so the search ends in an explicit error");
  bal_ctx_destroy(&lk);

  if (failures) {
    printf("MUTEX HARNESS FAILED (%d)\n", failures);
    return 1;
  }
  printf("MUTEX HARNESS OK (init failure rc=%d)\n", rc);
  return 0;
}
