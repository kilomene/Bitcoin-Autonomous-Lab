"""Mining probability engine (EXP-037): exact odds, no optimism.

Adopts the formulas of research/probability.py (where they were
orphaned: no production code imported that module) into a
production-reachable home. The mathematics is the directive's
section 10 statement, unchanged:

- A difficulty-D target accepts an expected one hash in
  D * 2^32, so expected_hashes(D) = D * 2^32.
- Blocks found by a constant-rate searcher form a Poisson
  process with rate R / (D * 2^32) per second, so the expected
  time to a block is (D * 2^32) / R seconds.
- P(at least one block within t seconds)
  = 1 - exp(-R * t / (D * 2^32)).

These are THEORETICAL results given the inputs: they are exact
for an ideal uniform hash function, and their inputs (network
difficulty D, measured hashrate R) must come from measurement.
This module never estimates either input. Expected time,
probability over a period, best share difficulty, network
difficulty and actual block discovery are separate quantities
and are never conflated here or by callers: a high-difficulty
share is not a block, and a probability is not a promise.
"""

import math

HASHES_PER_DIFFICULTY = 1 << 32


def _check_difficulty(difficulty):
    if difficulty <= 0:
        raise ValueError("difficulty must be positive")
    return float(difficulty)


def expected_hashes(difficulty):
    """Expected hash computations to find one block at the
    given difficulty: D * 2^32."""
    return _check_difficulty(difficulty) * HASHES_PER_DIFFICULTY


def expected_seconds(hashrate, difficulty):
    """Expected seconds to one block at a constant measured
    hashrate: (D * 2^32) / R. Infinite if the hashrate is 0."""
    d = _check_difficulty(difficulty)
    if hashrate <= 0:
        return math.inf
    return d * HASHES_PER_DIFFICULTY / hashrate


def prob_at_least_one(hashrate, difficulty, seconds):
    """P(at least one block within `seconds`) for a constant
    measured hashrate: 1 - exp(-R * t / (D * 2^32))."""
    d = _check_difficulty(difficulty)
    if hashrate <= 0 or seconds <= 0:
        return 0.0
    lam = hashrate * seconds / (d * HASHES_PER_DIFFICULTY)
    return 1.0 - math.exp(-lam)


# Aliases matching the research module's names, so existing
# research callers read the same either way.
prob_within = prob_at_least_one


def prob_within_days(hashrate, difficulty, days):
    return prob_at_least_one(hashrate, difficulty, days * 86400)
