# benchmarks/

Raw benchmark records (JSON) for X-series experiments, one
file per experiment, named after the experiment id. Every
record must state: machine probe reference, load average at
run time, contention conditions, backend and build flags,
hash count per run, repeats, per-run rates, median, minimum,
maximum, spread, and whether the figures are coverage or
actual backend computations (Task 003.9 accounting
definitions, gpu/engine.py module docstring).

The comparison harness is ../experiments/bench_harness.py
(EXP-000). A candidate is never compared against a stale
baseline from a different session without the session drift
being stated.
