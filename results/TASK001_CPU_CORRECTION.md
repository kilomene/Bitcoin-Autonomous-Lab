# TASK 001: Complete CPU Mining Engine Correction and Validation

Date: 2026-11-14. Scope: the existing CPU mining subsystem only.
No GPU, FPGA or ASIC work, no new algorithm, no mainnet mining or
mainnet submission in this task. All integration work ran on
Bitcoin Core regtest and in isolated unit tests. The live mainnet
autopilot, mainnet node and keeper cron (running under earlier
owner orders) were not stopped, restarted or altered; their load
on this shared VM is stated wherever it affects a measurement.

## The five gates

| Gate | Verdict | Evidence |
| --- | --- | --- |
| 1. Mathematical correctness | PASS | Genesis digest exact in both C libraries; 6,000 randomized digests per library match hashlib across 30 random headers; target equality tests pass; full suite green. |
| 2. Concurrency | PASS | TSan clean (see environment note), ASan/UBSan clean, 8-way concurrent independent search stress clean, pthread_create failure injection loses no work. |
| 3. Real native execution | PASS | ComputeEngine selects backend "c" from the compiled library, the library carries the new counted entry point, the build smoke-tests itself against hashlib, and the Python fallback reports itself as backend "cpu". |
| 4. Accurate performance | PASS | Early-exit searches report actual attempts (for example 3,291 counted attempts against 100,000 requested on the genesis window); misses report exactly the range size; mining/engine.py no longer adds requested batch sizes. |
| 5. Accepted regtest block | PASS | Corrected native engine blocks accepted by Core at heights 475, 476 and a hardened-search block at height 477 (details below); submitblock returned null and the node best block equals the submitted hash in every case. |

Machine readable evidence: evidence/regtest/task001-cpu-correction.json

## Part 1: Audit and execution-path inventory

Files inspected: mining/cpu/bal_batch.c, mining/cpu/bal_miner.c,
mining/cpu/bal_sha_intrin.c, mining/cpu/build.py,
mining/cpu/miner.py, mining/engine.py, mining/pow.py,
mining/pow_engine.py (target helpers), gpu/engine.py, gpu/cuda/
build.py (for contrast), node/node_manager.py, scripts/install.sh,
Makefile, and the test files test_cpu_aspect.py, test_deepening.py,
test_gpu_compute.py, test_known_blocks.py, test_mining_engine.py,
test_pow_engine.py. The whole tree was grepped for bal_c_batch,
bal_c_search, bal_i_batch, bal_i_search, SHA256_Transform,
midstate, C_THREADS and backend selection.

Execution paths found:

| Path | Compiled | Loaded | Selected | Actually used |
| --- | --- | --- | --- | --- |
| bal_batch.c as .local/cpu/libbal_batch.so (bal_c_batch, bal_c_search) | yes, mining/cpu/build.py | yes, gpu/engine.py _try_c with digest self-test | yes, backend "c" | yes: batch_search, search_first and all production mining |
| bal_sha_intrin.c as .local/cpu/libbal_intrin.so (bal_i_batch, bal_i_search) | yes, built manually and now by build_intrin() | no Python loader exists | never | only in tests and benchmarks. It was dead code at runtime before this task and remains experimental, by measurement (Part 7). |
| bal_miner.c as ./bal-miner | yes, Makefile | n/a (binary) | manual | standalone bench and search; used by `make test` |
| Python hashlib (gpu/engine.py cpu_digest) | n/a | yes | backend "cpu" when requested or when C is unavailable | fallback and the independent verifier of every candidate |
| CUDA library | compiles when nvcc exists | attempted first in auto mode | only with a real device passing self-test | never on this VM (no device; nvcc currently absent after a VM replacement) |

## Defects found and corrections applied

### D1. Volatile globals as synchronization (bal_batch.c, bal_sha_intrin.c)
Both libraries kept `volatile int g_stop`, `volatile uint32_t
g_found_nonce` and a shared `g_found_digest[32]`. Volatile is not
synchronization: the winner digest copy raced with readers and
with a second finder, and any two searches running in the same
process corrupted each other through the shared state.
Correction: a shared header, mining/cpu/bal_search.h, defines a
per-search context (BalSearchCtx) allocated on each call's stack:
a C11 _Atomic stop flag, and a winner (nonce plus digest)
published under a mutex by the first finder only, then read by
the caller after joining, which provides the happens-before edge.
No file-scope mutable search state remains in either library
(grep count for g_stop and g_found in the three C files: 0).
Searches are now reentrant and simultaneous independent searches
are safe, which the stress test proves.

### D2. First-N thread join bug (both libraries)
The old code counted successfully created threads in `launched`
but stored each new thread at `tids[spans]`, then joined
`tids[0..launched)`. A creation failure in the middle shifted
nothing: the join loop read an uninitialized slot and leaked a
still-running thread that kept writing into stack-owned job
arrays after return. Correction: a per-span `created[]` flag;
exactly the created threads are joined, and a failed span runs
synchronously in the calling thread (safe under the context
mutex, and it loses no work).

### D3. bal_miner.c concurrency and argument handling
The standalone miner shared a `volatile int` stop flag, never
checked pthread_create or calloc results, parsed numbers with
atoi/strtoul without validation (garbage silently became 0,
negative or overflowing values wrapped), computed nonces in a
way that could wrap the 32-bit space, and picked the winner as
the last worker in join order that had found anything.
Correction: C11 atomic stop shared by pointer; strict digit-only
overflow-checked parsing; the nonce range is validated as a
64-bit half-open interval that must fit the 32-bit space and
wrapping ranges are rejected with exit code 2; allocation
failures are reported; created threads are tracked per slot with
synchronous fallback; the reported winner is deterministically
the smallest found nonce; every worker's own actual hash count
is summed and printed.

### D4. Hash accounting inflated by requested batch size (mining/engine.py, gpu/engine.py)
MiningEngine.mine_cycle added `self.batch_size` to total_hashes
after every search_first call, including early-exit searches
that may have stopped after a few attempts. Reported hashrates
were therefore systematically too high, worst exactly when a
block was found quickly. Correction: the native libraries gained
counted entry points (bal_c_search2, bal_c_batch2, and the bal_i_
equivalents) that return the sum of per-worker actual attempts;
ComputeEngine.search_first_counted returns (hit, attempted,
seconds) and records last_search_stats (backend, threads,
requested range, attempted, counted flag); mine_cycle adds the
actual attempts only, and all elapsed timing in these paths now
uses a monotonic clock (time.perf_counter). search_first keeps
its old signature as a wrapper, so existing callers (including
the live mainnet runner, untouched by this task) keep working.
Measured proof: a genesis-window search over a requested range
of 100,000 reported 3,291 actual attempts; a miss over 30,000
reported exactly 30,000; in the regtest run below, a normal
regtest cycle that found nonce 0 now honestly reports hashes=1
instead of the old batch size of 1,048,576.

### D5. Build failure presented as success (mining/cpu/build.py)
build() returned a dict with lib=None on failure and the script
exited 0, so scripts/install.sh continued and presented the
install as a successful optimized CPU setup. Correction: build()
now checks for a compiler and for the OpenSSL development header
with plain-language messages, preserves compiler output in the
result and the log, smoke-tests the compiled library against
hashlib (256 genesis-header digests plus a genesis nonce search
through bal_c_search2 with a plausible attempt count) before
reporting it usable, returns ok=False on any failure, and the
script exits 1. Verified live with a fake gcc that exits 3: the
error text was preserved and the process exit code was 1.
build_intrin() builds the experimental intrinsics library and
reports it separately; its failure never fails the production
build and it is never a production selection.

### D6. SHA-intrinsics schedule is scalar, despite the file header (Part 7 audit)
The header comment claimed SHA256MSG1 and SHA256MSG2 advance the
message schedule. The code never calls them: schedule_impl() is
plain scalar C, recomputed per nonce for the inner hash and again
inside compress() for the outer hash. objdump of the built
library confirms it: sha256rnds2 is emitted (3 sites), sha256msg1
and sha256msg2 appear nowhere. This, plus recomputing the whole
inner schedule per nonce, is the measured reason the intrinsics
library loses to OpenSSL's SHA256_Transform, which uses the full
SHA-NI path including message scheduling. Correction applied:
the false header claim is fixed and the audit recorded here; the
implementation itself was not rewritten, because replacing the
scalar schedule with MSG-instruction scheduling is an
optimization project, not a correctness correction, and this
task's rule was correctness first. The intrinsics library stays
experimental and unselected.

### D7. Snapshot boundary comment was imprecise (bal_sha_intrin.c)
The comment said the state is snapshotted "after round 2" and
resumed "at round 3". The code snapshots after rounds 0 and 1
and resumes at round 2. The mathematics, verified word by word:
the nonce first enters the message schedule at W3 (the byte
swapped nonce word) and is first consumed by round 3; schedule
words from W18 onward also depend on it transitively. Rounds 0,
1 and 2 consume only W0, W1, W2 from the header tail and are
nonce independent. The snapshot still cannot advance past round
1, because SHA256RNDS2 computes rounds in pairs and the next
pair (rounds 2 and 3) needs W3. So no additional complete round
pair can be precomputed; the only theoretical extra is a single
scalar round 2, which would require extracting and repacking
the vector state per template and has no measured benefit. It
was not implemented. The comment now states this exactly.

### D8. Range validation relied on a wrapping-prone expression
All three C entry points validated with `start + count >
0x100000000` in mixed widths and trusted callers. Correction:
bal_validate_range() in bal_search.h validates in uint64_t:
count at least 1, start at most 0xFFFFFFFF, count at most 2^32,
and start + count at most 2^32, with distinct return codes
(-1 bad arguments, -2 range exceeds the nonce space). Worker
spans come from bal_partition(), which covers the interval
exactly once: disjoint, ordered, no gaps, final span ending
exactly at the interval end, so the maximum nonce 0xFFFFFFFF is
hashed exactly when the interval ends at 2^32.

## Part 4: Hashing and target validation

- Header serialization: version, previous hash and merkle root
  little-endian fields are passed through; the nonce is patched
  into header bytes 76..79 little-endian, as Bitcoin requires.
- The C batch path patches the nonce into the second compression
  block byte by byte little-endian, and the block itself is fed
  to SHA256_Transform as big-endian words, which is the correct
  dual view of the same bytes. Digest words are stored big
  endian; comparisons treat the digest as a little-endian
  integer, matching Bitcoin. The intrinsics path builds W3 by
  byte swapping the nonce into big-endian word form, which is
  the same statement from the other side, and its digests match
  hashlib exactly, which settles the question empirically.
- Target equality: a digest exactly equal to the target meets
  it (tested at the exact value, and at value minus one which
  must miss), in both libraries and in bal-miner.
- nBits: mining/pow.py target_from_nbits and the pow_engine
  compact decode/encode are covered by existing suites
  (test_known_blocks, test_pow_engine) including negative and
  overflow compact forms; the regtest cycles below run through
  Core's own template target end to end.
- Differential volume: 6,000 randomized digests per C library in
  the new suite, on top of the 4,000-nonce check in
  test_cpu_aspect.py, the six real mainnet header fixtures, and
  the live regtest chain cross-verification in test_pow_engine
  (every header on the regtest chain rehashed and PoW-checked).

## Parts 5 and 8: Benchmarks, before and after

Conditions, stated honestly: this VM is capped near 1.5 shared
CPUs and the live mainnet miner and mainnet node were running
throughout, under earlier owner orders. Run-to-run variance is
large (a 1-thread probe repeated 3 times gave 0.49M, 1.06M and
1.09M H/s). Numbers below are therefore evidence about which
path is fastest and about counting accuracy, not clean-machine
records, and no speedup is claimed for the correction: the
before and after ranges overlap, and the correction targeted
correctness, not speed.

Before (original code, load average 13.9, single runs):

| Path | H/s |
| --- | --- |
| C search (bal_c_search miss scan), 1 thread | 752,665 |
| C search, 2 threads | 813,706 |
| C search, 4 threads | 1,700,153 |
| C batch via batch_search, 1 / 2 / 4 threads | 630,622 / 851,722 / 964,691 |
| Intrinsics batch, 1 / 2 / 4 threads | 282,173 / 476,991 / 443,665 |
| bal-miner bench (full SHA256 OpenSSL, no midstate), 1 / 2 / 4 | 116,442 / 238,005 / 238,598 |

After (corrected code, load average about 5.2, medians of 3 runs
unless noted):

| Path | H/s |
| --- | --- |
| C search (bal_c_search2 miss scan, counted), 1 thread | 1,058,021 |
| C search, 2 threads | 1,325,791 |
| C search, 4 threads | 1,357,146 |
| C search, 8 threads | 1,512,787 |
| C batch via batch_search, 1 / 2 / 4 threads | 727,199 / 982,800 / 1,604,312 |
| Intrinsics batch (bal_i_batch2, counted), 1 / 2 / 4 threads | 301,036 / 410,102 / 828,165 |
| Python hashlib batch engine | 98,607 |
| Sustained C search, 2 threads, 23.5 s, 29,360,128 counted hashes | 1,249,566 |
| bal-miner bench, 1 / 2 / 4 threads | 248,571 / 217,393 / 260,560 |

A second in-suite run of the counted miss scan gave 1,155,378
(1 thread), 1,497,474 (2) and 1,497,521 (4), inside the same
variance band. Scaling conclusion: throughput rises from 1 to 2
threads and flattens after that on this capped VM; more threads
do not reliably help here, which is why the existing live tuner
keeps measuring per machine instead of hardcoding a count.

Hardware counters: the perf tool is not installed on this VM
and perf_event_paranoid is 4, so cycles per hash, instructions
per hash, IPC and cache misses could not be measured with
hardware counters; no numbers are claimed for them. Thread
pinning and affinity were not made mandatory and were not
benchmarked as a variant, per the task's portability rule.

## Part 10: Tests and sanitizers

New suite: tests/test_cpu_correction.py (wired into the Makefile
as test-cpu-correction and into test-all, now 16 targets). It
covers genesis and randomized differential correctness for both
libraries, target boundaries, every nonce boundary named in the
task, attempt-count exactness at 1, 2, 3, 4, 7 and 16 threads,
8-way concurrent independent search stress, pthread_create
failure injection at fail-after 0 and fail-after 1, bal-miner
argument and range rejection, engine backend identification, and
counted benchmarks at 1, 2 and 4 threads. No existing test was
weakened or deleted.

Suite tally (2026-11-14, this VM): 14 of 16 targets pass:
test, test-regtest, test-engine, test-pow, test-mining,
test-adversarial, test-deepening, test-cpu, test-cpu-correction,
test-solo, test-research, test-autopilot, test-judgement,
test-installer. Two fail for environment reasons unrelated to
the CPU subsystem: test-gpu asserts nvcc is installed and nvcc
is absent since the last VM replacement; test-rtl needs
iverilog, also absent. Both failures are tool absence, reported
here rather than hidden.

Sanitizers: dedicated C drivers exercising batch, counted
search, boundary ranges, failure injection and 8 simultaneous
independent searches were built three ways. ThreadSanitizer:
clean for bal_batch.c, bal_sha_intrin.c and bal_miner.c, with
one environment caveat: TSan aborts at startup on this VM with
"unexpected memory mapping" under the default ASLR layout, so
the runs were executed under `setarch -R`, after which all
drivers passed with no race reports. AddressSanitizer plus
UBSan: clean for all three, no reports.

## Part 9 and Gate 5: Regtest integration with the native backend

Run on the corrected build, backend explicitly "c", attempt
counting present, chain regtest only:

- Two standard CpuMiner cycles: height 475, hash
  2182317f2c33f2f3661e00cc0849c5b6c40c65690b106b704a426bf52d68602d,
  and height 476, hash
  5ed10ca7639f0fee647f0037b75e96dc26072ff14ff5f0c868fc972b28892bf5.
  submitblock returned null for both and each hash was the node
  best block. Both honestly report 1 actual hash attempt
  (regtest difficulty is minimal and nonce 0 qualified); under
  the old accounting each would have claimed 1,048,576.
- One hardened cycle at height 477: the template target was
  shifted right 20 bits (about 2^20 times harder than regtest
  requires) and searched with the native counted search: nonce
  135203252 found after 2,066,781 actual attempts in 0.782 s
  (2,643,910 H/s, 4 threads), digest re-verified with hashlib,
  full block reconstructed and submitted. submitblock returned
  null; block hash
  00000654b2869c8e4c44623d31a4953fef85eff5e8461f22a0cb39eeb05625ba
  equals the node's best block hash.
- The existing suites mined further accepted blocks with the
  corrected build in the same session (test_cpu_aspect tip 501
  to 503, plus mining engine and deepening cycles).

## Files modified

- mining/cpu/bal_search.h (new): shared per-search context,
  range validation and partitioning, failure-injection hook.
- mining/cpu/bal_batch.c: rewritten search and batch paths on
  the shared design; counted bal_c_batch2 and bal_c_search2
  entry points; original symbols kept as wrappers.
- mining/cpu/bal_sha_intrin.c: same concurrency and range
  corrections; counted bal_i_batch2 and bal_i_search2; snapshot
  comment corrected; schedule claim in the header corrected.
- mining/cpu/bal_miner.c: atomic stop, strict argument parsing
  and range validation, checked allocation and thread creation
  with per-slot tracking and synchronous fallback, deterministic
  smallest-nonce winner, actual per-worker hash counts.
- mining/cpu/build.py: failing builds fail (exit 1, clear
  missing compiler and missing header messages, preserved
  compiler output), post-build hashlib smoke test, separate
  build_intrin().
- gpu/engine.py: counted search (search_first_counted and
  last_search_stats), extended library signatures, monotonic
  timing in the batch paths, describe() reports attempt
  counting support.
- mining/engine.py: mine_cycle counts actual attempts from the
  backend and times on a monotonic clock.
- tests/test_cpu_correction.py (new) and Makefile wiring.
- evidence/regtest/task001-cpu-correction.json (new) and this
  report.

## Verdict: which CPU implementation is fastest, and why

The OpenSSL midstate C library (bal_batch.c, backend "c") is
the fastest CPU implementation in this lab at every thread
count measured, and it remains the production backend. It wins
for structural reasons: the first compression is paid once per
template (midstate), each nonce costs exactly two
SHA256_Transform calls, and OpenSSL's transform uses the full
SHA-NI implementation including the message schedule. The
SHA-intrinsics library does the rounds with SHA256RNDS2 but
recomputes its message schedule in scalar C per nonce, and
measures at roughly half the OpenSSL rate (301,036 vs 727,199
H/s at 1 thread; 828,165 vs 1,604,312 at 4 threads, medians
under the same load). The bal-miner binary path (full double
SHA-256 through the high-level OpenSSL API, no midstate) is the
slowest native path at about 0.22M to 0.26M H/s, and the Python
hashlib engine is the fallback at about 0.10M H/s under the same
conditions. No speedup from this correction is claimed: its
purpose was correctness, and the before and after bands overlap.

## Remaining limitations

- perf hardware counters were unavailable (tool absent,
  paranoid level 4); cycles and instructions per hash are
  unmeasured.
- TSan needs `setarch -R` on this VM to start at all; the runs
  under it are clean, but the plain-startup failure is an
  environment fact to remember on this host.
- The intrinsics message schedule remains scalar (defect D6);
  converting it to SHA256MSG1 and SHA256MSG2 scheduling is a
  future optimization task with its own benchmark burden, and
  until it beats OpenSSL under measurement it stays
  experimental and unselected.
- Benchmarks here are contention-limited by the shared VM and
  the live mainnet workload; clean-machine peaks will be higher
  and must be re-measured on the machine in question (the live
  tuner already does this per install).
- mining/mainnet_live.py still adds full span sizes to its own
  hash counter on early exit. It is part of the live mainnet
  runner, which this task was ordered not to alter; the same
  counted entry points it needs now exist, and switching it over
  is a small follow-up for a mainnet-scoped task.
- test-gpu and test-rtl cannot pass until nvcc and iverilog are
  present on this VM again; both are outside the CPU subsystem.

## Task 003 addendum (2026-11-14)

Task 003 hardened three items from this report; see
results/TASK003_CORRECTIONS.md for the full evidence.

- Mutex initialization (new): bal_ctx_init() now checks the
  pthread_mutex_init() result, propagates failure to the caller
  (the search entry points return -4 and start no worker), never
  destroys an uninitialized mutex, and bal_ctx_publish() checks
  lock and unlock results (a publication failure returns -3 from
  the search entry points instead of risking a corrupt winner).
  Verified by tests/task003_mutex_harness.c, ctypes failure
  injection against both libraries, and sanitizer runs in
  tests/test_task003_corrections.py.
- Hash accounting in mining/engine.py (extended): the cycle loop
  now also clamps the final nonce batch with
  count = min(batch_size, 2^32 - start) (Task 003.2). The Task 001
  accounting fix counted actual attempts but still submitted the
  raw configured batch size, which an awkward batch size turned
  into an out-of-range final batch at the end of the nonce space.
- Winner semantics (correction of wording): this report and
  bal_miner.c previously described the bal-miner search winner as
  "deterministically the smallest found nonce". The accurate
  statement is first-found semantics: workers stop at the first
  candidate found by any worker, and the reported nonce is the
  smallest among the candidates actually found before the stop
  propagated. That is not a proof of the lowest valid nonce in
  the range. bal_miner now prints winner_semantics=first-found.
  (The shared library search in bal_search.h is unaffected: its
  winner is the first candidate published under the mutex, which
  is what Task 001 Gate 2 tested.)
