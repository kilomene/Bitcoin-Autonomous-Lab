#!/usr/bin/env python3
"""Status-counter accounting gate for mining/mainnet_live.py.

Audit note N-1 (post-integration audit, 2026-11-14): the
live runner's status "hashes" counter added the full
requested span per search_first call, so it reported
requested nonces rather than exact attempts: on an
early-exit span it counted nonces never attempted, and
the displayed session rate inherited the inflation. The
fix accumulates the engine's exact attempted count
(last_search_stats["attempted"], the field the audit
verified as exact) through mainnet_live.call_attempts.

This suite proves, through the production engine:

- Early exit: a search whose winner sits near the start
  of a large span advances the counter by exactly the
  engine's attempted count, strictly below the span size.
- Full miss: a span with no hit advances the counter by
  exactly the span size, which equals the attempted
  count (a miss scans everything by construction).
- Fallback: with no stats present, call_attempts counts
  only what the result proves (span start through the
  winner for a hit, 0 for a miss), never the span size.

Run: python3 tests/test_mainnet_live_accounting.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gpu.engine import ComputeEngine
from mining import mainnet_live

GENESIS = bytes.fromhex(
    "01000000" + "00" * 32
    + "3ba3edfd7a7b12b27ac72c3e67768f617fc81bc3888a51323a9fb8aa4b1e5e4a"
    + "29ab5f49" + "ffff001d" + "1dac2b7c")
GENESIS_NONCE = 2083236893
DIFF1 = 0xFFFF << 208


def test_early_exit_counts_attempts_not_span(engine, label):
    start = GENESIS_NONCE - 3
    span = 100000
    counter = 0
    hit = engine.search_first(GENESIS, DIFF1, start, span)
    counter += mainnet_live.call_attempts(engine, hit, start)
    assert hit is not None and hit[0] == GENESIS_NONCE, (label, hit)
    attempted = engine.last_search_stats["attempted"]
    assert counter == attempted, (label, counter, attempted)
    assert 0 < counter < span, (label, counter, span)
    print(f"ok early exit ({label}): counter advanced by "
          f"{counter}, exactly the engine attempted count, "
          f"not the {span} nonce span")


def test_full_miss_counts_span_equals_attempts(engine, label):
    start, span = 5000, 30000
    counter = 0
    hit = engine.search_first(GENESIS, 1, start, span)
    counter += mainnet_live.call_attempts(engine, hit, start)
    assert hit is None, (label, hit)
    attempted = engine.last_search_stats["attempted"]
    assert attempted == span, (label, attempted, span)
    assert counter == span == attempted, (label, counter, span,
                                          attempted)
    print(f"ok full miss ({label}): counter advanced by "
          f"{counter} = span = attempted")


class _NoStats:
    """Engine stand-in with no counted stats at all."""

    last_search_stats = None


def test_fallback_counts_only_what_result_proves():
    eng = _NoStats()
    hit = (1050, b"\x00" * 32)
    assert mainnet_live.call_attempts(eng, hit, 1000) == 51
    assert mainnet_live.call_attempts(eng, None, 1000) == 0
    print("ok fallback: no stats, hit counts start..winner "
          "(51), miss counts 0, span size never used")


def main():
    auto = ComputeEngine()
    test_early_exit_counts_attempts_not_span(auto, "auto")
    test_full_miss_counts_span_equals_attempts(auto, "auto")
    eng_c = ComputeEngine(requested="c")
    test_early_exit_counts_attempts_not_span(eng_c, "c")
    test_full_miss_counts_span_equals_attempts(eng_c, "c")
    test_fallback_counts_only_what_result_proves()
    print("ALL MAINNET LIVE ACCOUNTING TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
