# Statistical Mining Analysis

All figures are estimates computed from measured inputs;
the inputs and their dates are stated so the arithmetic can
be redone when they move. Nothing here promises a block.

## Inputs (2026-11-14)

- Network difficulty: 134,823,837,323,272.66, decoded from
  nBits by the live miner's template validation and recorded
  in evidence/mainnet-live.jsonl (template_validated events,
  most recently 2026-11-14T10:41Z). Consistent with the value
  decoded the previous night.
- Expected hashes per block at this difficulty:
  difficulty x 2^32 = about 5.79 x 10^23.
- Measured rates: production C backend at 2 threads, median
  1,627,792 H/s (EXP-000 baseline, contended VM); the live
  miner's own status events reported about 3,013,312 H/s at
  the same period (its spans run at its tuned settings on
  real templates).

## Expected time and probabilities (geometric law)

Block discovery is a memoryless geometric process: each hash
is an independent trial with success probability
target / 2^256. Expected attempts equal expected hashes per
block; the probability of at least one block in T seconds at
rate R is 1 - exp(-R x T / 5.79e23), indistinguishable from
the linear approximation at these magnitudes.

| Rate basis | Expected time to one block | P(block in 24 h) | P(block in 30 days) |
|---|---|---|---|
| 1.63 MH/s (baseline, 2T) | about 1.13 x 10^10 years | 2.4 x 10^-13 | 7.3 x 10^-12 |
| 2.51 MH/s (baseline, 4T median, unstable) | about 7.3 x 10^9 years | 3.7 x 10^-13 | 1.1 x 10^-11 |
| 3.01 MH/s (live miner status rate) | about 6.1 x 10^9 years | 4.5 x 10^-13 | 1.3 x 10^-11 |

These are the honest numbers for a CPU on a capped shared
VM against the 2026 mainnet. They agree in order of
magnitude with the lab's earlier estimate (results/RESEARCH.md:
about 3.2 billion years at the then-difficulty of about 110T
and about 5.18 MH/s).

## What the statistics do and do not say

- Doubling the hash rate exactly doubles the discovery
  probability per unit time and halves the expected time.
  That linearity is the entire business case for this
  research programme: a proven 2x kernel is a proven 2x
  probability, no more and no less.
- Variance dominates any human timescale: the standard
  deviation of the waiting time equals its mean. "Expected
  in 10 billion years" and "could happen tonight" are both
  true statements about the same process; planning uses the
  mean, hope is not a metric.
- Effective useful work is the nominal rate discounted by
  stale-work fraction (about 0.17% at 1 s spans, see
  mining_pipeline_optimization.md), verification overhead
  (negligible at mainnet targets), and uptime (the keeper
  and autopilot exist precisely because VM restarts, not
  hash rate, were the largest observed source of lost work
  in this lab's history: multiple full stops per day before
  supervision, zero unrecovered stops since).
- Pool shares at difficulty 1 and above (32 accepted at the
  last count before this pass, since risen) are the lab's
  running proof that the work is real and correctly formed;
  per the charter they are not, and are never reported as,
  block discoveries.

## Decision use

At these probabilities, the rational engineering objective
is exactly the charter's: maximize correctly evaluated
candidates per unit time on the hardware that exists, keep
the miner running without gaps, and treat any block as the
tail event it is. Research effort is justified by the
linearity above and by the transferable engineering, not by
an expectation of imminent discovery.
