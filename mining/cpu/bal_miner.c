// Bitcoin Autonomous Lab: CPU miner engine.
//
// Double SHA-256 over 80-byte Bitcoin block headers. Linked against
// OpenSSL, which on this host dispatches to the CPU SHA-NI accelerated
// implementation (the host CPU exposes the sha_ni flag). Multi-threaded
// nonce search with a caller supplied target.
//
// Modes:
//   bal-miner bench <seconds> <threads>
//   bal-miner search <header_hex> <target_be_hex> <start_nonce> <count> <threads>
//
// search prints exactly one of:
//   FOUND nonce=<n> hash=<display hex> ... winner_semantics=first-found
//   NONE hashes=<n> seconds=<s> hashrate_hs=<n>
// bench prints:
//   BENCH hashes=<n> seconds=<s> hashrate_hs=<n> threads=<n>
//         unique_nonce_space=<n> slice_wraps=<n> repeated=own-slice-only
//
// Task 001 corrections:
// - The shared stop flag is a C11 _Atomic int, not volatile.
// - Every pthread_create result is checked; created threads are
//   tracked per worker slot and exactly those are joined. A failed
//   creation runs that worker synchronously so no assigned nonce
//   range is lost.
// - calloc results are checked.
// - Each worker records its own actual completed hash count; the
//   totals printed are the sum of those counts.
// - All numeric arguments are parsed strictly (whole string, no
//   overflow) and validated. The nonce range is a 64-bit half-open
//   interval [start_nonce, start_nonce + count) that must fit the
//   32-bit nonce space; wrapping ranges are rejected, never
//   silently wrapped. The final nonce 0xFFFFFFFF is reachable when
//   the interval ends exactly at 2^32.
// - Winner semantics (corrected in Task 003.3): the search stops
//   at the FIRST candidate found by any worker (first-found
//   semantics). The reported nonce is the smallest among the
//   candidates that were actually found before the stop flag
//   propagated. That is NOT a proof that it is the lowest valid
//   nonce in the range: a worker may be stopped before reaching a
//   lower qualifying nonce in its own span. No output of this
//   program claims the globally lowest nonce.
// - Bench mode (corrected in Task 003.3): every worker owns a
//   disjoint contiguous slice of the 32-bit nonce space and wraps
//   inside its own slice only. The earlier scheme started workers
//   1,000,000 nonces apart but let each run unboundedly, so a
//   worker hashed straight into its neighbour's starting region
//   and nonces were computed twice (measured: about 300,000
//   duplicated nonces in a 10 second 2-thread bench). Wrap-arounds
//   inside a worker's own slice are repeated computations of
//   nonces that worker already covered; they count in hashes=
//   (actual attempts) but the output states the unique nonce
//   space covered separately so the two are never confused.

#include <openssl/sha.h>
#include <errno.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static int hexval(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

static int hex_decode(const char *hex, uint8_t *out, size_t out_len) {
    if (strlen(hex) != out_len * 2) return -1;
    for (size_t i = 0; i < out_len; i++) {
        int hi = hexval(hex[i * 2]), lo = hexval(hex[i * 2 + 1]);
        if (hi < 0 || lo < 0) return -1;
        out[i] = (uint8_t)((hi << 4) | lo);
    }
    return 0;
}

static int parse_u64(const char *s, uint64_t *out) {
    if (!s || !*s) return -1;
    for (const char *p = s; *p; p++)
        if (*p < '0' || *p > '9') return -1;
    errno = 0;
    char *end = NULL;
    unsigned long long v = strtoull(s, &end, 10);
    if (errno != 0 || !end || *end != '\0') return -1;
    *out = (uint64_t)v;
    return 0;
}

// Returns 1 when dsha256(header) as a 256-bit number <= target.
// hash number = digest interpreted little endian (Bitcoin display order
// reversed). target is supplied big endian (display order).
static int meets_target(const uint8_t digest[32], const uint8_t target_be[32]) {
    for (int k = 0; k < 32; k++) {
        uint8_t h = digest[31 - k];
        uint8_t t = target_be[k];
        if (h < t) return 1;
        if (h > t) return 0;
    }
    return 1; // exactly equal
}

static void dsha256(const uint8_t *data, size_t len, uint8_t out[32]) {
    uint8_t tmp[32];
    SHA256(data, len, tmp);
    SHA256(tmp, 32, out);
}

typedef struct {
    uint8_t header[80];
    uint8_t target_be[32];
    uint64_t start;      // offset of this worker's first nonce
    uint64_t count;      // number of nonces assigned to this worker
    uint32_t nonce_base; // start_nonce value
    int seconds;         // bench mode: run duration, count ignored
    _Atomic int *stop;
    uint64_t hashes;     // actual hashes completed by this worker
    uint64_t wraps;      // bench only: wraps inside the own slice
    int found;
    uint32_t found_nonce;
    uint8_t found_hash[32];
    uint8_t best_hash[32];
    uint32_t best_nonce;
} work_t;

static int hash_smaller(const uint8_t a[32], const uint8_t b[32]) {
    for (int k = 0; k < 32; k++) {
        uint8_t av = a[31 - k], bv = b[31 - k];
        if (av < bv) return 1;
        if (av > bv) return 0;
    }
    return 0;
}

static void *search_worker(void *arg) {
    work_t *w = (work_t *)arg;
    uint8_t header[80];
    memcpy(header, w->header, 80);
    uint64_t done = 0;
    for (uint64_t i = 0; i < w->count; i++) {
        if (atomic_load_explicit(w->stop, memory_order_acquire)) break;
        // Range was validated to fit the 32-bit nonce space.
        uint32_t nonce = (uint32_t)((uint64_t)w->nonce_base + w->start + i);
        header[76] = (uint8_t)(nonce & 0xff);
        header[77] = (uint8_t)((nonce >> 8) & 0xff);
        header[78] = (uint8_t)((nonce >> 16) & 0xff);
        header[79] = (uint8_t)((nonce >> 24) & 0xff);
        uint8_t digest[32];
        dsha256(header, 80, digest);
        done++;
        if (done == 1 || hash_smaller(digest, w->best_hash)) {
            memcpy(w->best_hash, digest, 32);
            w->best_nonce = nonce;
        }
        if (meets_target(digest, w->target_be)) {
            memcpy(w->found_hash, digest, 32);
            w->found_nonce = nonce;
            w->found = 1;
            atomic_store_explicit(w->stop, 1, memory_order_release);
            break;
        }
    }
    w->hashes = done;
    return NULL;
}

static void *bench_worker(void *arg) {
    work_t *w = (work_t *)arg;
    uint8_t header[80];
    memcpy(header, w->header, 80);
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    double start = ts.tv_sec + ts.tv_nsec / 1e9;
    uint64_t done = 0;
    // This worker owns exactly [begin, end) of the nonce space and
    // never leaves it: at the end it wraps to its own begin and
    // counts the wrap. Wraps are repeated computations, reported
    // separately from the unique space the worker covers.
    uint64_t begin = w->start;
    uint64_t end = w->start + w->count; // <= 2^32 by construction
    uint64_t nonce = begin;
    uint64_t wraps = 0;
    for (;;) {
        for (int burst = 0; burst < 100000; burst++) {
            if (nonce >= end) { nonce = begin; wraps++; }
            uint32_t n32 = (uint32_t)nonce;
            header[76] = (uint8_t)(n32 & 0xff);
            header[77] = (uint8_t)((n32 >> 8) & 0xff);
            header[78] = (uint8_t)((n32 >> 16) & 0xff);
            header[79] = (uint8_t)((n32 >> 24) & 0xff);
            nonce++;
            uint8_t digest[32];
            dsha256(header, 80, digest);
            done++;
            (void)digest;
        }
        clock_gettime(CLOCK_MONOTONIC, &ts);
        double now = ts.tv_sec + ts.tv_nsec / 1e9;
        if (now - start >= w->seconds) break;
    }
    w->hashes = done;
    w->wraps = wraps;
    return NULL;
}

static double now_sec(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec + ts.tv_nsec / 1e9;
}

// Launch one thread per worker, tracked per slot; a failed launch
// runs the worker synchronously. Joins exactly the created ones.
// Returns the total actual hashes reported by the workers.
static uint64_t run_workers(work_t *works, pthread_t *tids, int *created,
                            int threads, void *(*fn)(void *)) {
    for (int i = 0; i < threads; i++) {
        if (pthread_create(&tids[i], NULL, fn, &works[i]) != 0) {
            created[i] = 0;
            fn(&works[i]);
        } else {
            created[i] = 1;
        }
    }
    uint64_t total = 0;
    for (int i = 0; i < threads; i++) {
        if (created[i]) pthread_join(tids[i], NULL);
        total += works[i].hashes;
    }
    return total;
}

// Bench slice for worker i of `threads`: disjoint contiguous
// partition of the 32-bit nonce space (Task 003.3).
static void bench_slice(uint64_t threads, uint64_t i,
                        uint64_t *begin, uint64_t *count) {
    uint64_t slice = 0x100000000ULL / threads;
    *begin = i * slice;
    *count = (i == threads - 1) ? (0x100000000ULL - i * slice) : slice;
}

int main(int argc, char **argv) {
    if (argc >= 2 && strcmp(argv[1], "ranges") == 0) {
        // Diagnostic: print the bench nonce slices for a thread
        // count so tests can prove they are disjoint and complete.
        if (argc != 3) { fprintf(stderr, "usage: ranges <threads>\n"); return 2; }
        uint64_t threads;
        if (parse_u64(argv[2], &threads) != 0 || threads == 0 || threads > 64) {
            fprintf(stderr, "invalid threads\n");
            return 2;
        }
        uint64_t expect = 0;
        int disjoint = 1;
        for (uint64_t i = 0; i < threads; i++) {
            uint64_t begin, count;
            bench_slice(threads, i, &begin, &count);
            if (begin != expect) disjoint = 0;
            expect = begin + count;
            printf("RANGE worker=%llu begin=%llu end=%llu\n",
                   (unsigned long long)i, (unsigned long long)begin,
                   (unsigned long long)(begin + count));
        }
        printf("RANGES disjoint=%d covers=%llu\n", disjoint,
               (unsigned long long)expect);
        return (disjoint && expect == 0x100000000ULL) ? 0 : 1;
    }

    if (argc >= 2 && strcmp(argv[1], "bench") == 0) {
        if (argc != 4) { fprintf(stderr, "usage: bench <seconds> <threads>\n"); return 2; }
        uint64_t seconds, threads;
        if (parse_u64(argv[2], &seconds) != 0 || parse_u64(argv[3], &threads) != 0 ||
            seconds == 0 || seconds > 3600 || threads == 0 || threads > 64) {
            fprintf(stderr, "invalid bench arguments\n");
            return 2;
        }
        const char *genesis =
            "010000000000000000000000000000000000000000000000000000000000000000000000"
            "3ba3edfd7a7b12b27ac72c3e67768f617fc81bc3888a51323a9fb8aa4b1e5e4a"
            "29ab5f49ffff001d1dac2b7c";
        work_t *works = calloc((size_t)threads, sizeof(work_t));
        pthread_t *tids = calloc((size_t)threads, sizeof(pthread_t));
        int *created = calloc((size_t)threads, sizeof(int));
        if (!works || !tids || !created) {
            fprintf(stderr, "allocation failed\n");
            free(works); free(tids); free(created);
            return 2;
        }
        _Atomic int stop = 0;
        double t0 = now_sec();
        // Disjoint contiguous slices partition the whole 32-bit
        // nonce space (bench_slice; the ranges mode prints them).
        uint64_t unique_space = 0;
        for (uint64_t i = 0; i < threads; i++) {
            hex_decode(genesis, works[i].header, 80);
            works[i].seconds = (int)seconds;
            works[i].nonce_base = 0;
            bench_slice(threads, i, &works[i].start, &works[i].count);
            unique_space += works[i].count;
            works[i].stop = &stop;
        }
        uint64_t total = run_workers(works, tids, created, (int)threads, bench_worker);
        double dt = now_sec() - t0;
        uint64_t total_wraps = 0;
        for (uint64_t i = 0; i < threads; i++) total_wraps += works[i].wraps;
        printf("BENCH hashes=%llu seconds=%.3f hashrate_hs=%.0f threads=%llu "
               "unique_nonce_space=%llu slice_wraps=%llu repeated=own-slice-only\n",
               (unsigned long long)total, dt, total / dt,
               (unsigned long long)threads,
               (unsigned long long)unique_space,
               (unsigned long long)total_wraps);
        free(works); free(tids); free(created);
        return 0;
    }

    if (argc >= 2 && strcmp(argv[1], "search") == 0) {
        if (argc != 7) { fprintf(stderr, "usage: search <header_hex> <target_be_hex> <start_nonce> <count> <threads>\n"); return 2; }
        uint8_t header[80], target[32];
        if (hex_decode(argv[2], header, 80) != 0) { fprintf(stderr, "bad header hex\n"); return 2; }
        if (hex_decode(argv[3], target, 32) != 0) { fprintf(stderr, "bad target hex\n"); return 2; }
        uint64_t start_nonce, count, threads;
        if (parse_u64(argv[4], &start_nonce) != 0 ||
            parse_u64(argv[5], &count) != 0 ||
            parse_u64(argv[6], &threads) != 0) {
            fprintf(stderr, "invalid numeric arguments\n");
            return 2;
        }
        if (threads == 0 || threads > 64 || count == 0) {
            fprintf(stderr, "invalid threads or count\n");
            return 2;
        }
        // 64-bit half-open interval must fit the 32-bit nonce space.
        if (start_nonce > 0xFFFFFFFFULL || count > 0x100000000ULL ||
            start_nonce + count > 0x100000000ULL) {
            fprintf(stderr, "nonce range exceeds the 32-bit nonce space\n");
            return 2;
        }
        work_t *works = calloc((size_t)threads, sizeof(work_t));
        pthread_t *tids = calloc((size_t)threads, sizeof(pthread_t));
        int *created = calloc((size_t)threads, sizeof(int));
        if (!works || !tids || !created) {
            fprintf(stderr, "allocation failed\n");
            free(works); free(tids); free(created);
            return 2;
        }
        _Atomic int stop = 0;
        uint64_t per = count / threads;
        double t0 = now_sec();
        for (uint64_t i = 0; i < threads; i++) {
            memcpy(works[i].header, header, 80);
            memcpy(works[i].target_be, target, 32);
            works[i].start = per * i;
            works[i].count = (i == threads - 1) ? (count - per * (threads - 1)) : per;
            works[i].nonce_base = (uint32_t)start_nonce;
            works[i].stop = &stop;
        }
        uint64_t total = run_workers(works, tids, created, (int)threads, search_worker);
        double dt = now_sec() - t0;
        // Winner: smallest nonce among the candidates actually
        // found before the stop flag propagated (first-found
        // semantics, Task 003.3). Not claimed to be the lowest
        // valid nonce in the range.
        int found_idx = -1;
        for (uint64_t i = 0; i < threads; i++) {
            if (works[i].found &&
                (found_idx < 0 || works[i].found_nonce < works[found_idx].found_nonce))
                found_idx = (int)i;
        }
        int best_idx = -1;
        for (uint64_t i = 0; i < threads; i++) {
            if (works[i].hashes == 0) continue;
            if (best_idx < 0 || hash_smaller(works[i].best_hash, works[best_idx].best_hash))
                best_idx = (int)i;
        }
        char best_hex[65] = {0};
        if (best_idx >= 0)
            for (int i = 0; i < 32; i++) sprintf(best_hex + i * 2, "%02x", works[best_idx].best_hash[31 - i]);
        if (found_idx >= 0) {
            char hash_hex[65];
            for (int i = 0; i < 32; i++) sprintf(hash_hex + i * 2, "%02x", works[found_idx].found_hash[31 - i]);
            printf("FOUND nonce=%u hash=%s hashes=%llu seconds=%.3f best_hash=%s best_nonce=%u winner_semantics=first-found\n",
                   works[found_idx].found_nonce, hash_hex, (unsigned long long)total, dt,
                   best_hex, works[best_idx].best_nonce);
            free(works); free(tids); free(created);
            return 0;
        }
        printf("NONE hashes=%llu seconds=%.3f hashrate_hs=%.0f best_hash=%s best_nonce=%u\n",
               (unsigned long long)total, dt, total / (dt > 0 ? dt : 1),
               best_hex, best_idx >= 0 ? works[best_idx].best_nonce : 0);
        free(works); free(tids); free(created);
        return 1;
    }

    fprintf(stderr, "usage: bal-miner bench|search ...\n");
    return 2;
}
