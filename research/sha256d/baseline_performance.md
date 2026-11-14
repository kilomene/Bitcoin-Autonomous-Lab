# Baseline Performance Report (EXP-000, Stage 3)

Harness: experiments/bench_harness.py. Raw data:
experiments/exp000_baseline.json. Measured 2026-11-14 on the
lab VM with the live mainnet pool miner and pruned node
running (load average above 10 at probe time). All rates use
actual attempts returned by the counted entry points
(Task 003.9 accounting): batch calls hash their full range,
so attempted equals count and is verified per run, not
assumed. Batch work uses the genesis header and the
difficulty-1 target; target value does not change batch cost.

## Throughput (1,000,000 hashes per run, 3 repeats)

| Backend | Threads | Median H/s | Min | Max | Spread |
|---|---|---|---|---|---|
| C, OpenSSL midstate (production) | 1 | 1,314,704 | 1,120,875 | 1,474,549 | 26.9% |
| C, OpenSSL midstate (production) | 2 | 1,627,792 | 1,622,166 | 1,825,539 | 12.5% |
| C, OpenSSL midstate (production) | 4 | 2,512,762 | 2,381,340 | 4,457,165 | 82.6% |
| Intrinsics, scalar schedule | 1 | 699,926 | 659,312 | 766,740 | 15.3% |
| Intrinsics, scalar schedule | 2 | 848,348 | 675,173 | 923,166 | 29.2% |
| Intrinsics, scalar schedule | 4 | 1,135,344 | 1,114,731 | 1,608,268 | 43.5% |
| Python hashlib fallback | 1 | 304,444 | 197,609 | 517,731 | wide |

Reading: production at its tuned 2 threads is the reference
rate, about 1.63 MH/s on this contended VM. The 4-thread
median is higher but its spread (82.6%) makes it unusable as
a planning number; the cap, not the code, governs it. The
intrinsics path runs at about 0.52x production at 2 threads,
confirming the Task 001 finding with the shared harness.

## Latency

Single-candidate latency, measured as count=1 batch calls
through ctypes (3,000 calls): median 31.38 us production,
31.74 us intrinsics; p10 about 22 to 24 us; p90 above
1,100 us (contention spikes). This number is dominated by
the ctypes crossing and per-call thread setup. The amortized
cost of one hash inside a batch at 1 thread is about 0.76 us
(1 / 1.31 MH/s). Both figures are reported because the
programme charter asks for latency and throughput separately:
the honest summary is that isolated single hashes are cheap
to compute and expensive to request one at a time from
Python, which is why production callers use large spans.

## Correctness gates run inside the baseline

- Both native libraries: 20,000 batch digests match hashlib
  exactly; genesis nonce re-found by counted search.
- The harness asserts attempted == count on every batch run.

## Comparability contract

Later experiments must: use this harness (or extend it and
re-run the baseline), use the same batch size class, report
at least 3 repeats with median and spread, state contention,
and claim an improvement only when medians differ beyond
spread overlap. EXP-001 followed this contract; its negative
result is what a trustworthy baseline is for.
