#!/usr/bin/env python3
"""Research tests: pin the qualitative findings of
research/statistics.py so a future change that alters them is
loud, not silent.

Findings pinned (measured 2026-11-13, see results/RESEARCH.md):
- Digest bytes from 1M fresh C-engine hashes show no deviation
  from uniform beyond multiple-comparison noise.
- Bit balance and lag-1 nonce adjacency sit at 0.5.
- On our own chain, winning nonces follow the geometric law of
  sequential search (median scaled nonce near ln 2).
- Reduced-round SHA-256 is heavily biased at 16 to 20 rounds
  and indistinguishable from noise at 24+ rounds: statistical
  structure exists in the small and dies long before 64.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from research.statistics import (bias_vs_rounds, chain_statistics,
                                 sample_statistics)


def main():
    from node import node_manager
    from node.rpc_client import BitcoinRPC
    node_manager.start()
    cs = chain_statistics(BitcoinRPC())
    assert cs["blocks"] >= 100, cs
    assert 0.2 < cs["median_scaled_nonce"] < 2.0, cs
    print(f"ok: chain winners follow the geometric law "
          f"(median scaled nonce {cs['median_scaled_nonce']:.2f}, "
          f"theory 0.69, blocks {cs['blocks']})")

    ss = sample_statistics(500_000)
    assert abs(ss["bit_one_fraction"] - 0.5) < 0.002, ss
    assert abs(ss["lag1_msb_agreement"] - 0.5) < 0.004, ss
    assert ss["byte_chi2_p"] > 0.0005, ss  # Bonferroni-ish floor for 32 tests
    print(f"ok: 500k fresh hashes uniform (bit fraction "
          f"{ss['bit_one_fraction']:.4f}, lag1 {ss['lag1_msb_agreement']:.4f}, "
          f"worst byte chi2 p {ss['byte_chi2_p']:.3f})")

    bv = bias_vs_rounds(2000)
    assert bv[16] > 0.3, bv
    assert bv[20] > 0.03, bv
    assert bv[24] < 0.02, bv
    assert bv[64] < 0.02, bv
    print(f"ok: reduced-round bias collapses between 20 and 24 "
          f"rounds (16r {bv[16]:.3f}, 20r {bv[20]:.3f}, "
          f"24r {bv[24]:.4f}, 64r {bv[64]:.4f})")
    print("ALL RESEARCH TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
