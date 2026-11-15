#!/usr/bin/env python3
"""EXP-040 tests: the category F end-to-end pipeline harness.

Functional gate (the benchmark campaign itself lives in
research/sha256d/exp040/): the harness must drive the
unmodified production MiningEngine.mine_cycle to accepted
regtest blocks in the empty and loaded scenarios, every
accepted block must pass the EXP-036 exact verifier gate,
and the stage partition must account for the whole cycle
wall time. Session files go to a temporary directory, not
the campaign RAW_RESULTS.
"""

import importlib.util
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from node import node_manager
from node.rpc_client import BitcoinRPC

HARNESS = os.path.join(os.path.dirname(__file__), "..",
                       "research", "sha256d", "exp040",
                       "category_f.py")


def load_harness():
    spec = importlib.util.spec_from_file_location(
        "exp040_category_f", HARNESS)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def check_session(cf, session, expect_tx_count):
    runs = session["runs"]
    assert runs, "no runs recorded"
    for r in runs:
        assert r["accepted"] and not r["failed"], r
        assert r["verify"]["ok"], r
        assert r["verify"]["classification"] == "block_candidate", r
        assert r["tx_count"] == expect_tx_count, r
        assert r["hashes_counted"] > 0, r
        partition = sum(r["stages_s"].values()) + r["residual_s"]
        assert abs(partition - r["cycle_wall_s"]) < 0.002, (
            partition, r["cycle_wall_s"])
        assert r["stages_s"].get("search", 0) > 0, r
        assert r["stages_s"].get("gbt", 0) > 0, r
        assert r["stages_s"].get("submit", 0) > 0, r
    print(f"ok: scenario {session['scenario']} session: "
          f"{len(runs)} runs accepted and EXP-036 verified, "
          f"stage partition closes, tx_count {expect_tx_count}")


def main():
    node_manager.start()
    cf = load_harness()
    cf.RAW_DIR = tempfile.mkdtemp(prefix="exp040-test-")

    s_a = cf.run_session("A", 0, 2)
    check_session(cf, s_a, 1)

    loader = cf.MempoolLoader(cf.wallet_rpc(), BitcoinRPC(),
                              n_tx=40)
    s_b = cf.run_session("B", 0, 2, loader=loader)
    check_session(cf, s_b, 41)

    print("ALL EXP-040 CATEGORY F TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
