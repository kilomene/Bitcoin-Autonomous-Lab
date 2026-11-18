#!/usr/bin/env python3
"""Stage 9.6 arithmetic, reproducible.

Inputs are the values observed live on 2026-11-18 (see
live_observation.json in this directory):

- Network difficulty 134823837323272.66, from the live miner's
  template_validated events (the pool serves current mainnet
  templates; job nbits 17021673). Cross-check in this script:
  the difficulty computed from nbits 0x17021673 alone equals
  the miner-reported value exactly.
- Sustained hash rate from the live miner's own status line
  (mining/mainnet-status.txt): cumulative hashes and elapsed
  seconds of the current miner run, sampled four times over
  about 4.5 minutes. The primary figure is the cumulative
  average over the whole current run at the final sample
  (conservative: it includes the run's slower start). The
  interval rate over the sampling window is also reported.

All waiting-time outputs are statistical estimates. No long
dash characters are used in this file.
"""
import json

DIFFICULTY_REPORTED = 134823837323272.66
NBITS = 0x17021673
SECONDS_PER_YEAR = 365.25 * 24 * 3600

# (elapsed_s, cumulative_hashes, miner_printed_rate_hs)
SAMPLES = [
    (3753, 79458423584, 21172085),
    (3813, 80810681216, 21192894),
    (3933, 83713139584, 21285572),
    (3992, 85259089184, 21355505),
]


def difficulty_from_bits(bits):
    exp = bits >> 24
    mant = bits & 0xFFFFFF
    target = mant * 256 ** (exp - 3)
    max_target = 0x00FFFF * 256 ** (0x1D - 3)
    return max_target / target


def main():
    diff_check = difficulty_from_bits(NBITS)
    t0, h0, _ = SAMPLES[0]
    t1, h1, printed = SAMPLES[-1]
    cumulative_rate = h1 / t1
    interval_rate = (h1 - h0) / (t1 - t0)
    expected_hashes = DIFFICULTY_REPORTED * 2**32
    wait_s = expected_hashes / cumulative_rate
    out = {
        "difficulty_reported_by_live_miner": DIFFICULTY_REPORTED,
        "difficulty_computed_from_nbits_17021673": diff_check,
        "difficulty_cross_check_equal": diff_check == DIFFICULTY_REPORTED,
        "samples": [
            {"elapsed_s": t, "cumulative_hashes": h,
             "miner_printed_rate_hs": r, "cumulative_avg_hs": h / t}
            for (t, h, r) in SAMPLES
        ],
        "sustained_rate_hs_used": cumulative_rate,
        "interval_rate_hs_over_sampling_window": interval_rate,
        "expected_hashes_per_block": expected_hashes,
        "expected_wait_seconds": wait_s,
        "expected_wait_years": wait_s / SECONDS_PER_YEAR,
        "systems_to_500_ghs": 500e9 / cumulative_rate,
        "systems_to_140_ths": 140e12 / cumulative_rate,
        "note": "STATISTICAL ESTIMATE: expected value of a geometric "
                "waiting-time distribution at constant difficulty and "
                "constant rate. Actual time is random; difficulty "
                "retargets every 2016 blocks.",
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
