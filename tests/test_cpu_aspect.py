#!/usr/bin/env python3
"""CPU aspect tests: correctness of the C engine against hashlib,
measured benchmark advantage, and live end-to-end CPU mining with
blocks accepted by Bitcoin Core (no CUDA anywhere in the path).
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mining.cpu.build import build as build_c
from mining.cpu.miner import CpuMiner, benchmark, verify_c_library
from node import node_manager
from node.rpc_client import BitcoinRPC


def wallet_rpc(rpc):
    if "bal-regtest" not in rpc.call("listwallets"):
        try:
            rpc.call("loadwallet", "bal-regtest")
        except Exception:
            rpc.call("createwallet", "bal-regtest")
    return BitcoinRPC(wallet="bal-regtest")


def main():
    built = build_c(log=lambda *a: None)
    assert built["lib"], built

    v = verify_c_library(4000)
    assert v["ok"], v
    print(f"ok: C batch library digests match hashlib on {v['samples']} "
          f"consecutive nonces")

    bench = benchmark()
    print("benchmarks:", {k: (f"{v:,.0f}" if isinstance(v, float) else v)
                          for k, v in bench.items()})
    assert bench["c_midstate_engine"] > bench["python_hashlib_engine"], bench
    # Relative floor, not an absolute one: this VM's CPU allocation
    # is shared and shrinks under parallel load (a syncing node, a
    # test suite), so an absolute H/s floor flakes. The invariant
    # that matters is C beating the pure-Python loop decisively.
    assert bench["c_midstate_raw_1thr"] > 2 * bench["python_hashlib_loop"], bench
    print(f"ok: C midstate engine {bench['c_midstate_engine']:,.0f} H/s "
          f"beats Python engine {bench['python_hashlib_engine']:,.0f} H/s")

    node_manager.start()
    rpc = BitcoinRPC()
    wallet = wallet_rpc(rpc)
    payout = wallet.call("getnewaddress", "", "bech32")
    miner = CpuMiner(rpc, payout)
    assert miner.compute.backend in ("c", "v512"), miner.compute.describe()
    tip0 = rpc.get_block_count()
    out = miner.mine(2)
    assert out["accepted"] == 2, out
    assert rpc.get_block_count() == tip0 + 2
    assert out["cycles"][-1]["hash"] == rpc.get_best_block_hash()
    for c in out["cycles"]:
        assert c["backend"] == miner.compute.backend, c
    print(f"ok: CPU miner (backend c only) mined 2 blocks accepted by "
          f"Core, tip {tip0} -> {tip0 + 2}")
    print("ALL CPU ASPECT TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
