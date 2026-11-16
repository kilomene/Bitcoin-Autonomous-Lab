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


def _desc(backend):
    """A ComputeEngine.describe() shaped dict with a distinct
    sentinel reason per backend, so a test can tell exactly
    which backend's probe record a line quoted."""
    return {
        "backend": backend,
        "native_impl": None,
        "v512_reason": "V512 PROBE REASON",
        "v512dual_reason": "DUAL PROBE REASON",
        "shani_reason": "SHANI PROBE REASON",
        "avx2_reason": "AVX2 PROBE REASON",
        "cuda_context_reason": "CUDA CONTEXT REASON",
        "fallback_reason": "FALLBACK REASON",
    }


def test_backend_reason_names_selected_backend():
    # D9 (Stage 0 reconciliation, fixed in Stage 6): the
    # session backend line must name the SELECTED backend and
    # quote its own probe record. The pre-fix code labelled
    # every non-dual backend "AVX-512 MB" and quoted the v512
    # probe's reason for shani, avx2 and C sessions.
    label, reason = mainnet_live.backend_reason(_desc("v512dual"))
    assert (label, reason) == ("AVX-512 DualMask",
                               "DUAL PROBE REASON"), (label, reason)
    label, reason = mainnet_live.backend_reason(_desc("v512"))
    assert (label, reason) == ("AVX-512 MB",
                               "V512 PROBE REASON"), (label, reason)
    label, reason = mainnet_live.backend_reason(_desc("shani"))
    assert (label, reason) == ("SHA-NI streams",
                               "SHANI PROBE REASON"), (label, reason)
    label, reason = mainnet_live.backend_reason(_desc("avx2"))
    assert (label, reason) == ("AVX2 MB",
                               "AVX2 PROBE REASON"), (label, reason)
    label, reason = mainnet_live.backend_reason(_desc("cuda"))
    assert (label, reason) == ("CUDA",
                               "CUDA CONTEXT REASON"), (label, reason)
    label, reason = mainnet_live.backend_reason(_desc("c"))
    assert label == "C batch", label
    assert "AVX-512" not in reason and "V512" not in reason, reason
    for backend in ("shani", "avx2", "c", "cpu"):
        label, reason = mainnet_live.backend_reason(_desc(backend))
        assert label != "AVX-512 MB", (backend, label)
        assert reason != "V512 PROBE REASON", (backend, reason)
    print("ok backend reason (D9): every backend's line names "
          "the selected backend and quotes its own probe record")


def test_backend_reason_matches_real_describe():
    own_field = {
        "v512dual": "v512dual_reason",
        "v512": "v512_reason",
        "shani": "shani_reason",
        "avx2": "avx2_reason",
        "cuda": "cuda_context_reason",
    }
    for requested in ("auto", "c"):
        desc = ComputeEngine(requested=requested).describe()
        label, reason = mainnet_live.backend_reason(desc)
        field = own_field.get(desc["backend"])
        if field is not None:
            assert reason == desc[field], (
                requested, desc["backend"], reason, desc[field])
        print(f"ok backend reason (real describe, {requested}): "
              f"backend {desc['backend']} labelled {label!r} "
              f"with its own probe record")


def main():
    auto = ComputeEngine()
    test_early_exit_counts_attempts_not_span(auto, "auto")
    test_full_miss_counts_span_equals_attempts(auto, "auto")
    eng_c = ComputeEngine(requested="c")
    test_early_exit_counts_attempts_not_span(eng_c, "c")
    test_full_miss_counts_span_equals_attempts(eng_c, "c")
    test_fallback_counts_only_what_result_proves()
    test_backend_reason_names_selected_backend()
    test_backend_reason_matches_real_describe()
    print("ALL MAINNET LIVE ACCOUNTING TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
