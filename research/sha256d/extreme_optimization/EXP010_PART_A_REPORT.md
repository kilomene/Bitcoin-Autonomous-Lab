# EXP-010: Part A Decision Closure (2026-11-14)

## Execution context, stated first

This experiment was ordered to run after the mainnet
node finished initial block download. The owner then
ordered immediate execution ("Finish it up now asap"),
overriding the wait-for-sync condition. It therefore
ran DURING initial block download, under the heaviest
sustained contention the programme has recorded, and
that contention is part of the result, not a footnote
to it:

- Node at session start: blocks 410,518, headers
  975,803, initialblockdownload true,
  verificationprogress 0.0828.
- Node at session end: blocks 410,520, headers
  975,803, initialblockdownload true.
- Load average (1 minute): 12.60 at start, 12.54 at
  end; per-round readings between 12.39 and 12.60 on a
  4 vCPU guest capped near 1.5 effective CPUs. The
  runnable queue was saturated for the whole session
  (live pool miner, syncing node, and other tenants).
- Session steal: 1.63 percent of total CPU jiffies.
- The hourly watcher armed for this experiment was
  pre-empted by this run; a stand-down marker records
  the verdict so it does not run again.

## Predeclared criterion (unchanged)

A candidate passes only if, at 2 worker threads in one
round-robin interleaved session, its MINIMUM round
rate exceeds production C's MAXIMUM round rate
(complete separation, beyond spread). This is the
EXP-004 rule, restated in the watcher protocol, and
it was not altered after the numbers were seen.

## Correctness (gate before benchmark)

All three contenders passed the full shared gate set
(tests/test_exp010_partA.py, tests/gates.py) before
any benchmark number was taken:

- 108,000 randomized SHA-256d differentials vs
  hashlib per contender, zero mismatches.
- Genesis digest exact; genesis search finds nonce
  2083236893.
- Boundary nonces and ranges, crossing range rejected
  (-2), empty range rejected (-1).
- Template variations (version, prevhash, merkle,
  timestamp, nBits) all track hashlib.
- Target exact equality accepted; target minus one
  rejected; regtest-easy candidate set identical to a
  Python recount (82 candidates over 20,000 nonces)
  for all three.
- Exact accounting: batch attempted equals count;
  search miss attempted equals range; early-exit
  attempted exact per kernel semantics (production
  50,001; streams=4 strided 50,004; multi-buffer
  50,016).

No contender was excluded. Production C therefore
faced both challengers at full strength.

## Results (2 threads, 15 rounds x 1M, interleaved)

Raw observations, including per-round load and steal,
are preserved in benchmarks/exp010_partA_decision.json
(bench_exp010_decision.py). Confidence intervals are
95 percent percentile-bootstrap intervals for the
median (10,000 resamples, seeded).

| Implementation | Median H/s | Median 95% CI | Min H/s | Max H/s | Spread |
|---|---|---|---|---|---|
| Production C | 1,209,879 | 1,078,769 to 1,714,289 | 886,493 | 2,288,008 | 115.8% |
| H-01 streams=4 strided | 3,342,449 | 3,065,806 to 3,895,558 | 1,440,195 | 5,128,658 | 110.4% |
| AVX-512 multi-buffer | 3,551,903 | 3,135,148 to 5,002,645 | 2,006,621 | 9,384,014 | 207.7% |

Median ratios to production: streams=4 strided 2.76x;
multi-buffer 2.94x. The candidates' median confidence
intervals sit entirely above production's, but the
predeclared criterion is not a median test.

## Criterion outcome

- Streams=4 strided: min 1,440,195 vs production max
  2,288,008. FAILS.
- AVX-512 multi-buffer: min 2,006,621 vs production
  max 2,288,008. FAILS (by about 12 percent).

Neither candidate passes. Per the protocol, no
integration was performed: gpu/engine.py and all
production sources are byte-identical, no regression
suite run was owed, and no regtest integration block
was mined. The decision is closed for this machine as
ordered: production C remains the mining backend.

## AVX-512 variance attribution

The multi-buffer kernel's spread (207.7 percent) is
the widest in the programme. The per-round covariates
answer the environmental question directly:

- Correlation of MB16 rate with per-round steal:
  +0.221 (the wrong sign for a steal explanation).
  Correlation with 1-minute load: -0.095 (load barely
  moved, 12.39 to 12.60, so it cannot explain
  round-to-round swings either).
- Calm rounds (steal at or below the 1.25 percent
  median) median 3,562,042 H/s; spiked rounds median
  3,515,186 H/s: 1.3 percent apart. Four of fifteen
  MB16 rounds fell below 80 percent of its median;
  they occur in both steal halves.
- Control: production C shows correlation -0.521 of
  rate against steal, the expected environmental
  signature, so the covariates were capable of
  registering environmental effects in this session.
  Streams=4 strided: correlation +0.067, calm and
  spiked medians within 1 percent.

Finding: steal and load spikes do not explain the
multi-buffer kernel's slow rounds. The environment
supplied a saturated runnable queue (a constant, not
a series of spikes), and under that constant pressure
the kernel's own behaviour produces the excess
variance: its wide vector state and memory-backed
transpose make its throughput far more sensitive to
neighbour scheduling and cache contention than
production's, round by round. Attribution: both, with
the differential variance (207.7 percent against
production's 115.8 percent under identical
conditions) assigned to implementation behaviour
under contention, not to steal events.

## Conclusions under the owner's three tiers

- VERIFIED IMPROVEMENT: none at the integration
  standard. The candidates' median superiority
  (2.76x and 2.94x, confidence intervals clear of
  production's) is a verified measurement under the
  stated IBD contention, and it is recorded as such;
  it is not an integration-grade improvement because
  the programme's own predeclared separation
  criterion is the standard, and it failed.
- PROMISING HYPOTHESIS: none newly created by this
  run. The result strengthens the standing Y-101 case
  (a steal and contention normalized decision
  statistic) and the Y-023 case (register-resident
  multi-buffer state, attacking the transpose
  sensitivity named above), both already registered.
- UNPROVEN BREAKTHROUGH: unchanged. Nothing in this
  run touches the ceiling arithmetic: the best
  median here (3.55 MH/s at 2 threads on a capped,
  saturated guest) leaves 500 GH/s about 140,000x
  away.

## Decision

Production C stands. The Part A decision is closed.
Reopening it requires either a materially quieter
measurement environment or a kernel whose minimum,
not median, clears production's maximum under the
same rule.
