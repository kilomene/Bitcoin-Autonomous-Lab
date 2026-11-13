# CPU aspect: build, test and verification results (2026-11-13)

Subsystem: mining/cpu/ (bal_batch.c midstate SHA-NI library with an
early-exit search entry point, build.py, miner.py with CpuMiner,
the benchmark harness and live thread tuning).
Tests: tests/test_cpu_aspect.py, tests/test_mining_engine.py,
tests/test_deepening.py, all passing.

## Correctness (verified, not assumed)

- The C batch library's digests equal hashlib's on 4,000 consecutive
  nonces of a fixed header, checked in the test run.
- Every candidate returned in production paths is re-verified in
  Python before use (gpu/engine.py verify_candidate), including
  candidates from the early-exit search.

## The peak push (owner's order: highest peak, our own results)

Three bottlenecks were found by measurement and removed:

1. Python was rescanning every digest returned by C. The C flags
   array now locates candidates at C speed; Python only verifies
   the flagged few.
2. Mining dumped full digest arrays. bal_c_search is an early-exit
   scan: threads race ranges and stop at the first valid nonce,
   writing nothing per hash.
3. Thread count is tuned live per machine. On this VM the scan
   rates are: 1 thread 4.49M, 2 threads 6.77M (peak), 3 threads
   5.98M, 4 threads 5.14M, 8 threads 4.58M H/s. The VM gives about
   1.5 real cores, so 2 threads win and the tuner picks exactly
   that, from measurement, not from a guess.

## Measured hashrates (in-suite, sustained)

| path | H/s |
| --- | --- |
| C midstate engine, end to end (batch_search, flag path) | 6,617,558 |
| C midstate raw batch, 2 threads | 7,083,630 |
| C midstate raw batch, 4 threads | 7,774,869 |
| C early-exit scan (search_first), miss ranges | about 6,150,000 |
| Python hashlib engine | 634,435 |
| Python hashlib single loop | 761,270 |

The C engine is about 10x the Python engine end to end. A 1-in-16M
target nonce was found by search_first in 0.52 seconds.

## Live mining verification

CpuMiner (CPU backends only, CUDA excluded by construction, thread
tuner active) ran getblocktemplate cycles through the early-exit
search path: blocks submitted and accepted by Bitcoin Core (test
run: tip 331 to 333), cycle backend recorded as "c".
