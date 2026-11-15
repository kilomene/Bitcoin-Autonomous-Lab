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
from fractions import Fraction

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


# Percentile, exact-target and period outputs (BR-011 closure).
# Specified by research/probability/
# BITCOIN_MINING_PROBABILITY_MODEL.md section 8, which pins the
# signatures, definitions and error behaviour implemented here
# and the acceptance anchors the tests must hold. The waiting
# time to a block is exponentially distributed with mean
# expected_seconds, so its quantiles are exact multiples of the
# mean: median = ln 2, p90 = ln 10, p95 = ln 20, p99 = ln 100.
# The exact-target forms take the consensus target itself, not
# a difficulty: p = (target + 1) / 2^256 exactly, so the
# difficulty form's relative error (1.5259e-5 at the genesis
# target, model section 4) never enters. The two 63.2 percent
# anchors differ in the fifth decimal for exactly that reason
# and are pinned separately in the tests: merging them is a
# defect.


def quantile_seconds(hashrate, difficulty, q):
    """Seconds by which P(at least one block) reaches q:
    -ln(1 - q) * (D * 2^32) / R. Infinite if the hashrate is
    0. q must satisfy 0 < q < 1."""
    d = _check_difficulty(difficulty)
    if not 0 < q < 1:
        raise ValueError("q must satisfy 0 < q < 1")
    if hashrate <= 0:
        return math.inf
    return -math.log(1.0 - q) * d * HASHES_PER_DIFFICULTY / hashrate


def median_seconds(hashrate, difficulty):
    """Median seconds to one block: the q = 0.5 quantile,
    ln 2 * (D * 2^32) / R. Infinite if the hashrate is 0."""
    return quantile_seconds(hashrate, difficulty, 0.5)


def percentile_seconds(hashrate, difficulty, p):
    """Seconds by which P(at least one block) reaches p
    percent: quantile_seconds at q = p / 100. p must satisfy
    0 < p < 100."""
    if not 0 < p < 100:
        raise ValueError("p must satisfy 0 < p < 100")
    return quantile_seconds(hashrate, difficulty, p / 100)


def _check_n_hashes(n_hashes):
    if not isinstance(n_hashes, int) or n_hashes < 0:
        raise ValueError("n_hashes must be a non-negative int")
    return n_hashes


def prob_at_least_one_hashes(difficulty, n_hashes):
    """P(at least one block in exactly n_hashes hashes) in the
    difficulty form: 1 - (1 - p_D)^N with p_D = 1 / (D * 2^32),
    evaluated stably as -expm1(N * log1p(-p_D)). N = 0 is 0.0."""
    d = _check_difficulty(difficulty)
    n = _check_n_hashes(n_hashes)
    if n == 0:
        return 0.0
    p_d = 1.0 / (d * HASHES_PER_DIFFICULTY)
    if p_d >= 1.0:
        return 1.0
    return -math.expm1(n * math.log1p(-p_d))


def _check_target(target):
    if not isinstance(target, int) \
            or not 0 <= target < (1 << 256):
        raise ValueError(
            "target must be an int with 0 <= target < 2^256")
    return target


def expected_hashes_exact(target):
    """Exact expected hashes to one block at the given
    consensus target: 2^256 / (target + 1), returned as an
    exact Fraction. No floating point is involved, so the
    genesis-target value keeps its exact fractional part
    (4295032833.000015...)."""
    t = _check_target(target)
    return Fraction(1 << 256, t + 1)


def prob_at_least_one_exact(target, n_hashes):
    """P(at least one block in exactly n_hashes hashes) at the
    given consensus target: 1 - (1 - (target + 1) / 2^256)^N.
    The per-hash probability is formed as the exact Fraction
    (target + 1) / 2^256 first and only then evaluated in
    floating point through log1p/expm1, so no difficulty
    rounding enters. N = 0 is 0.0."""
    t = _check_target(target)
    n = _check_n_hashes(n_hashes)
    if n == 0:
        return 0.0
    p = float(Fraction(t + 1, 1 << 256))
    if p >= 1.0:
        return 1.0
    return -math.expm1(n * math.log1p(-p))


PERIOD_SECONDS = {
    "day": 86400,
    "week": 604800,
    "month": 2629800,
    "year": 31557600,
    "ten_years": 315576000,
}


def prob_within_period(hashrate, difficulty, period):
    """P(at least one block within a named period): prob_at_
    least_one over the period lengths of the probability
    model section 6 (month and year are the mean Gregorian
    lengths, 2629800 and 31557600 seconds). An unknown period
    name raises ValueError."""
    try:
        seconds = PERIOD_SECONDS[period]
    except (KeyError, TypeError):
        raise ValueError(
            f"unknown period {period!r}; expected one of "
            f"{sorted(PERIOD_SECONDS)}") from None
    return prob_at_least_one(hashrate, difficulty, seconds)
