"""Solo mining probability engine: exact odds, no optimism.

For hashrate H (hashes/second) and network difficulty D, the
expected hashes per block are D * 2^32, blocks arrive as a
Poisson process with rate H / (D * 2^32) per second, and the
probability of at least one block within time t is
1 - exp(-H * t / (D * 2^32)). Every number the lab quotes about
solo mining comes from here.
"""

import math

HASHES_PER_DIFFICULTY = 1 << 32


def expected_seconds(hashrate, difficulty):
    return difficulty * HASHES_PER_DIFFICULTY / hashrate


def prob_within(hashrate, difficulty, seconds):
    lam = hashrate * seconds / (difficulty * HASHES_PER_DIFFICULTY)
    return 1.0 - math.exp(-lam)


def prob_within_days(hashrate, difficulty, days):
    return prob_within(hashrate, difficulty, days * 86400)


def human_time(seconds):
    if seconds < 3600:
        return f"{seconds / 60:.1f} minutes"
    if seconds < 86400 * 2:
        return f"{seconds / 3600:.1f} hours"
    if seconds < 86400 * 730:
        return f"{seconds / 86400:.1f} days"
    return f"{seconds / (86400 * 365.25):,.0f} years"


def report(hashrate, label, difficulty):
    exp_s = expected_seconds(hashrate, difficulty)
    return {
        "label": label, "difficulty": difficulty,
        "expected": human_time(exp_s),
        "p_1_hour": prob_within(hashrate, difficulty, 3600),
        "p_1_day": prob_within_days(hashrate, difficulty, 1),
        "p_1_year": prob_within_days(hashrate, difficulty, 365.25),
    }
