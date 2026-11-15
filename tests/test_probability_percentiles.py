#!/usr/bin/env python3
"""Acceptance tests for the BR-011 probability outputs.

research/probability/BITCOIN_MINING_PROBABILITY_MODEL.md
section 8 specified seven functions for mining/probability.py
(quantile_seconds, median_seconds, percentile_seconds,
prob_at_least_one_hashes, expected_hashes_exact,
prob_at_least_one_exact, prob_within_period) and the anchors
their implementation must hold. This suite pins exactly those
anchors:

- the quantile multiples of the mean: median = ln 2,
  p90 = ln 10, p95 = ln 20, p99 = ln 100, to float precision;
- the CDF round trip prob_at_least_one(R, D,
  quantile_seconds(R, D, q)) == q for q in
  {0.5, 0.9, 0.95, 0.99};
- expected_hashes_exact(T1) == Fraction(2^256, T1 + 1) with
  float value 4295032833.000015, T1 = 0xffff * 2^208 the
  genesis (difficulty-1) target;
- the two 63.2 percent anchors KEPT SEPARATE:
  prob_at_least_one_hashes(1, 2^32) == 0.6321205589 (the
  difficulty form, p_D at D = 1 is exactly 2^-32) and
  prob_at_least_one_exact(T1, 2^32) == 0.6321149454 (the
  exact-target form), each to 1e-9. They differ in the fifth
  decimal because p(T1) is smaller than 2^-32 by the model
  section 4 factor; each function must also FAIL the other
  anchor's tolerance, so a test or implementation that
  conflates them is caught here;
- the specified error behaviour: q outside (0, 1), p outside
  (0, 100), a negative or non-int hash count, a target
  outside [0, 2^256), and an unknown period name all raise
  ValueError; a zero hashrate yields infinite times and the
  period probabilities still evaluate.

Run: python3 tests/test_probability_percentiles.py
"""

import math
import os
import sys
from fractions import Fraction

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mining.probability import (PERIOD_SECONDS, expected_hashes,
                                expected_hashes_exact,
                                expected_seconds, median_seconds,
                                percentile_seconds,
                                prob_at_least_one,
                                prob_at_least_one_exact,
                                prob_at_least_one_hashes,
                                prob_within_days, prob_within_period,
                                quantile_seconds)

T1 = 0xFFFF << 208  # genesis (difficulty-1) target
ANCHOR_DIFFICULTY = 0.6321205589
ANCHOR_EXACT = 0.6321149454

CHECKS = 0


def check(cond, label):
    global CHECKS
    CHECKS += 1
    assert cond, label
    print(f"ok {CHECKS}: {label}")


def raises_value_error(fn, label):
    try:
        fn()
    except ValueError:
        check(True, label)
        return
    raise AssertionError(f"{label}: no ValueError raised")


def test_quantile_multiples():
    for r, d in ((20.6e6, 8.0e13), (1 << 32, 1.0), (5.0e5, 1234.5)):
        mean = expected_seconds(r, d)
        check(abs(median_seconds(r, d) - math.log(2) * mean)
              <= 1e-12 * mean,
              f"median == ln2 * mean at R={r} D={d}")
        check(abs(percentile_seconds(r, d, 90)
                  - math.log(10) * mean) <= 1e-12 * mean,
              f"p90 == ln10 * mean at R={r} D={d}")
        check(abs(percentile_seconds(r, d, 95)
                  - math.log(20) * mean) <= 1e-12 * mean,
              f"p95 == ln20 * mean at R={r} D={d}")
        check(abs(percentile_seconds(r, d, 99)
                  - math.log(100) * mean) <= 1e-12 * mean,
              f"p99 == ln100 * mean at R={r} D={d}")
        check(median_seconds(r, d)
              == quantile_seconds(r, d, 0.5),
              f"median is the 0.5 quantile at R={r} D={d}")


def test_cdf_round_trip():
    for r, d in ((20.6e6, 8.0e13), (1 << 32, 1.0), (12345.0, 7.25)):
        for q in (0.5, 0.9, 0.95, 0.99):
            t = quantile_seconds(r, d, q)
            back = prob_at_least_one(r, d, t)
            check(abs(back - q) < 1e-12,
                  f"CDF round trip q={q} at R={r} D={d}: {back}")


def test_quantile_error_behaviour():
    raises_value_error(lambda: quantile_seconds(1e6, 1.0, 0.0),
                       "q = 0 refused")
    raises_value_error(lambda: quantile_seconds(1e6, 1.0, 1.0),
                       "q = 1 refused")
    raises_value_error(lambda: quantile_seconds(1e6, 1.0, -0.5),
                       "negative q refused")
    raises_value_error(lambda: quantile_seconds(1e6, 1.0, 1.5),
                       "q above 1 refused")
    raises_value_error(lambda: percentile_seconds(1e6, 1.0, 0),
                       "p = 0 refused")
    raises_value_error(lambda: percentile_seconds(1e6, 1.0, 100),
                       "p = 100 refused")
    raises_value_error(lambda: percentile_seconds(1e6, 1.0, 140),
                       "p above 100 refused")
    check(quantile_seconds(0, 1.0, 0.5) == math.inf,
          "zero hashrate quantile is infinite")
    check(median_seconds(0, 1.0) == math.inf,
          "zero hashrate median is infinite")
    check(percentile_seconds(0, 1.0, 99) == math.inf,
          "zero hashrate p99 is infinite")
    raises_value_error(lambda: quantile_seconds(1e6, 0.0, 0.5),
                       "zero difficulty still refused in quantiles")


def test_exact_target_form():
    exact = expected_hashes_exact(T1)
    check(isinstance(exact, Fraction),
          "expected_hashes_exact returns an exact Fraction")
    check(exact == Fraction(1 << 256, T1 + 1),
          "expected_hashes_exact(T1) == 2^256 / (T1 + 1) exactly")
    check(abs(float(exact) - 4295032833.000015) < 1e-5,
          f"float(expected_hashes_exact(T1)) == 4295032833.000015 "
          f"(got {float(exact)})")
    check(expected_hashes_exact(0) == Fraction(1 << 256, 1),
          "target 0 expects exactly 2^256 hashes")
    check(expected_hashes_exact((1 << 256) - 1) == 1,
          "maximum target expects exactly 1 hash")
    check(expected_hashes_exact((1 << 224) - 1)
          == Fraction(1 << 32, 1),
          "the 2^32 identity is exact at the proof-of-work limit "
          "target 2^224 - 1, not at T1")
    raises_value_error(lambda: expected_hashes_exact(-1),
                       "negative target refused")
    raises_value_error(lambda: expected_hashes_exact(1 << 256),
                       "target 2^256 refused")
    raises_value_error(lambda: expected_hashes_exact(1.5),
                       "non-int target refused")
    # The exact form and the difficulty form differ at T1 by the
    # model section 4 factor; neither may stand in for the other.
    check(abs(float(exact) / expected_hashes(1) - 1.0000152590218967)
          < 1e-15,
          "exact / difficulty at T1 == 1.0000152590218967")


def test_two_anchors_kept_separate():
    p_diff = prob_at_least_one_hashes(1, 1 << 32)
    p_exact = prob_at_least_one_exact(T1, 1 << 32)
    check(abs(p_diff - ANCHOR_DIFFICULTY) < 1e-9,
          f"difficulty-form anchor: {p_diff} == 0.6321205589 "
          f"to 1e-9")
    check(abs(p_exact - ANCHOR_EXACT) < 1e-9,
          f"exact-target anchor: {p_exact} == 0.6321149454 "
          f"to 1e-9")
    check(abs(p_diff - ANCHOR_EXACT) > 1e-9,
          "difficulty form FAILS the exact anchor tolerance "
          "(the two anchors are not interchangeable)")
    check(abs(p_exact - ANCHOR_DIFFICULTY) > 1e-9,
          "exact form FAILS the difficulty anchor tolerance "
          "(the two anchors are not interchangeable)")
    check(0 < p_exact < p_diff,
          "exact-target probability is the smaller of the two, "
          "as the section 4 factor requires")


def test_n_hashes_forms():
    check(prob_at_least_one_hashes(1, 0) == 0.0,
          "zero hashes give zero probability (difficulty form)")
    check(prob_at_least_one_exact(T1, 0) == 0.0,
          "zero hashes give zero probability (exact form)")
    raises_value_error(lambda: prob_at_least_one_hashes(1, -1),
                       "negative hash count refused (difficulty)")
    raises_value_error(lambda: prob_at_least_one_exact(T1, -5),
                       "negative hash count refused (exact)")
    raises_value_error(lambda: prob_at_least_one_hashes(1, 2.5),
                       "non-int hash count refused (difficulty)")
    raises_value_error(lambda: prob_at_least_one_exact(1 << 256, 10),
                       "out-of-range target refused (exact prob)")
    check(prob_at_least_one_exact((1 << 256) - 1, 3) == 1.0,
          "maximum target: every hash succeeds, probability 1")
    check(prob_at_least_one_exact(0, 1) == 2.0 ** -256,
          "target 0, one hash: probability exactly 2^-256")
    a = prob_at_least_one_hashes(2.0, 1 << 20)
    b = prob_at_least_one_hashes(2.0, 1 << 21)
    check(0.0 < a < b < 1.0,
          "difficulty-form probability grows with N and stays "
          "below 1")
    # The N-trial difficulty form at one expected period sits
    # next to the time form at lambda == 1 (prob_at_least_one
    # at R = 2^32, D = 1, t = 1): the Bernoulli form
    # 1 - (1 - p)^N and the Poisson form 1 - exp(-N p) are
    # distinct models and differ by about N p^2 / 2 = 2^-33
    # here (observed 4.3e-11), so agreement is to 1e-9, not to
    # float precision. The Bernoulli value itself is the one
    # pinned exactly by the difficulty anchor above.
    check(abs(prob_at_least_one_hashes(1, 1 << 32)
              - prob_at_least_one(1 << 32, 1, 1)) < 1e-9,
          "N-trial and Poisson time forms agree to 1e-9 at one "
          "expected period (distinct models, 2^-33 apart)")


def test_periods():
    check(PERIOD_SECONDS == {"day": 86400, "week": 604800,
                             "month": 2629800, "year": 31557600,
                             "ten_years": 315576000},
          "period lengths are the model section 6 values")
    r, d = 20.6e6, 8.0e13
    for name, seconds in PERIOD_SECONDS.items():
        check(prob_within_period(r, d, name)
              == prob_at_least_one(r, d, seconds),
              f"period {name} is prob_at_least_one over "
              f"{seconds} seconds")
    check(prob_within_period(r, d, "day") == prob_within_days(r, d, 1),
          "period day agrees with the pre-existing days helper")
    check(prob_within_period(0, d, "year") == 0.0,
          "zero hashrate gives zero probability over a year")
    raises_value_error(lambda: prob_within_period(r, d, "fortnight"),
                       "unknown period name refused")
    raises_value_error(lambda: prob_within_period(r, d, "Day"),
                       "period names are exact (Day refused)")


def main():
    test_quantile_multiples()
    test_cdf_round_trip()
    test_quantile_error_behaviour()
    test_exact_target_form()
    test_two_anchors_kept_separate()
    test_n_hashes_forms()
    test_periods()
    print(f"ALL PROBABILITY PERCENTILE TESTS PASSED "
          f"({CHECKS} checks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
