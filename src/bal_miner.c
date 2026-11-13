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
//   FOUND nonce=<n> hash=<display hex>
//   NONE hashes=<n> seconds=<s> hashrate_hs=<n>
// bench prints:
//   BENCH hashes=<n> seconds=<s> hashrate_hs=<n> threads=<n>

#include <openssl/sha.h>
#include <pthread.h>
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
    uint64_t start;      // first nonce index assigned to this thread
    uint64_t count;      // number of nonces for this thread
    uint32_t nonce_base; // start_nonce value
    int seconds;         // bench mode: run duration, count ignored
    volatile int *stop;
    uint64_t hashes;
    int found;
    uint32_t found_nonce;
    uint8_t found_hash[32];
    uint8_t best_hash[32];
    uint32_t best_nonce;
} work_t;

// Returns 1 when hash a (digest byte order) is numerically smaller
// than hash b, comparing in Bitcoin display order.
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
        if (*w->stop) break;
        uint32_t nonce = w->nonce_base + (uint32_t)(w->start + i);
        // nonce sits in the header little endian
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
            *w->stop = 1;
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
    uint32_t nonce = w->nonce_base + (uint32_t)w->start;
    for (;;) {
        for (int burst = 0; burst < 100000; burst++) {
            header[76] = (uint8_t)(nonce & 0xff);
            header[77] = (uint8_t)((nonce >> 8) & 0xff);
            header[78] = (uint8_t)((nonce >> 16) & 0xff);
            header[79] = (uint8_t)((nonce >> 24) & 0xff);
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
    return NULL;
}

static double now_sec(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec + ts.tv_nsec / 1e9;
}

int main(int argc, char **argv) {
    if (argc >= 2 && strcmp(argv[1], "bench") == 0) {
        if (argc != 4) { fprintf(stderr, "usage: bench <seconds> <threads>\n"); return 2; }
        int seconds = atoi(argv[2]);
        int threads = atoi(argv[3]);
        if (seconds <= 0 || threads <= 0 || threads > 64) return 2;
        // Genesis header as a fixed, real workload.
        const char *genesis =
            "010000000000000000000000000000000000000000000000000000000000000000000000"
            "3ba3edfd7a7b12b27ac72c3e67768f617fc81bc3888a51323a9fb8aa4b1e5e4a"
            "29ab5f49ffff001d1dac2b7c";
        work_t *works = calloc((size_t)threads, sizeof(work_t));
        pthread_t *tids = calloc((size_t)threads, sizeof(pthread_t));
        volatile int stop = 0;
        double t0 = now_sec();
        for (int i = 0; i < threads; i++) {
            hex_decode(genesis, works[i].header, 80);
            works[i].seconds = seconds;
            works[i].nonce_base = (uint32_t)(i * 1000000u);
            works[i].start = 0;
            works[i].stop = &stop;
            pthread_create(&tids[i], NULL, bench_worker, &works[i]);
        }
        uint64_t total = 0;
        for (int i = 0; i < threads; i++) { pthread_join(tids[i], NULL); total += works[i].hashes; }
        double dt = now_sec() - t0;
        printf("BENCH hashes=%llu seconds=%.3f hashrate_hs=%.0f threads=%d\n",
               (unsigned long long)total, dt, total / dt, threads);
        return 0;
    }

    if (argc >= 2 && strcmp(argv[1], "search") == 0) {
        if (argc != 7) { fprintf(stderr, "usage: search <header_hex> <target_be_hex> <start_nonce> <count> <threads>\n"); return 2; }
        uint8_t header[80], target[32];
        if (hex_decode(argv[2], header, 80) != 0) { fprintf(stderr, "bad header hex\n"); return 2; }
        if (hex_decode(argv[3], target, 32) != 0) { fprintf(stderr, "bad target hex\n"); return 2; }
        uint32_t start_nonce = (uint32_t)strtoul(argv[4], NULL, 10);
        uint64_t count = strtoull(argv[5], NULL, 10);
        int threads = atoi(argv[6]);
        if (threads <= 0 || threads > 64 || count == 0) return 2;
        work_t *works = calloc((size_t)threads, sizeof(work_t));
        pthread_t *tids = calloc((size_t)threads, sizeof(pthread_t));
        volatile int stop = 0;
        uint64_t per = count / (uint64_t)threads;
        double t0 = now_sec();
        for (int i = 0; i < threads; i++) {
            memcpy(works[i].header, header, 80);
            memcpy(works[i].target_be, target, 32);
            works[i].start = per * (uint64_t)i;
            works[i].count = (i == threads - 1) ? (count - per * (uint64_t)(threads - 1)) : per;
            works[i].nonce_base = start_nonce;
            works[i].stop = &stop;
            pthread_create(&tids[i], NULL, search_worker, &works[i]);
        }
        uint64_t total = 0;
        int found_idx = -1;
        for (int i = 0; i < threads; i++) {
            pthread_join(tids[i], NULL);
            total += works[i].hashes;
            if (works[i].found) found_idx = i;
        }
        double dt = now_sec() - t0;
        int best_idx = 0;
        for (int i = 1; i < threads; i++) {
            if (works[i].hashes > 0 && hash_smaller(works[i].best_hash, works[best_idx].best_hash))
                best_idx = i;
        }
        char best_hex[65];
        for (int i = 0; i < 32; i++) sprintf(best_hex + i * 2, "%02x", works[best_idx].best_hash[31 - i]);
        if (found_idx >= 0) {
            char hash_hex[65];
            for (int i = 0; i < 32; i++) sprintf(hash_hex + i * 2, "%02x", works[found_idx].found_hash[31 - i]);
            printf("FOUND nonce=%u hash=%s hashes=%llu seconds=%.3f best_hash=%s best_nonce=%u\n",
                   works[found_idx].found_nonce, hash_hex, (unsigned long long)total, dt,
                   best_hex, works[best_idx].best_nonce);
            return 0;
        }
        printf("NONE hashes=%llu seconds=%.3f hashrate_hs=%.0f best_hash=%s best_nonce=%u\n",
               (unsigned long long)total, dt, total / (dt > 0 ? dt : 1),
               best_hex, works[best_idx].best_nonce);
        return 1;
    }

    fprintf(stderr, "usage: bal-miner bench|search ...\n");
    return 2;
}
