#!/usr/bin/env python3
"""EXP-041 regtest soundness gate (gate d).

Mines a fresh regtest block through the production
path (ComputeEngine pinned to the v512 backend but
loading the EXP-041 gate library, then MiningEngine
mine_cycle against the regtest node) for each 28-op
candidate. The gate libraries carry the production
ABI names and the production CPUID probe, built with
the production recipe, differing from production only
in the Maj (and for tfull, Ch) expression.

This gate establishes production-path soundness only.
It is NOT a verification pass: the EXP-017 rate gate
(c) already failed for both candidates, so neither is
a verified improvement and no integration follows.
"""
import os
import sys

ROOT = "/home/hatch/workspace/bitcoin-autonomous-lab"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)


def mine_one(tag):
    from node import node_manager
    from node.rpc_client import BitcoinRPC
    from mining.engine import MiningEngine
    from gpu.engine import ComputeEngine
    node_manager.start()
    rpc = BitcoinRPC()
    if "bal-regtest" not in rpc.call("listwallets"):
        try:
            rpc.call("loadwallet", "bal-regtest")
        except Exception:
            rpc.call("createwallet", "bal-regtest")
    wallet = BitcoinRPC(wallet="bal-regtest")
    payout = wallet.call("getnewaddress", "", "bech32")
    gate_lib = os.path.join(HERE, "src", f"libbal_e41{tag}_gate.so")
    compute = ComputeEngine(requested="v512", v_lib_path=gate_lib)
    assert compute.backend == "v512", compute.describe()
    eng = MiningEngine(rpc, payout, compute=compute,
                       batch_size=100_000)
    tip0 = rpc.get_block_count()
    out = eng.mine_cycle(max_batches=1000, deadline_seconds=600)
    assert out["accepted"], out
    assert out["backend"] == "v512", out
    assert rpc.get_best_block_hash() == out["hash"]
    assert rpc.get_block_count() == tip0 + 1
    print(f"ok regtest {tag}: fresh block accepted through the "
          f"production path with the EXP-041 {tag} gate library: "
          f"height {out['height']} hash {out['hash']} "
          f"submitblock null, best-block match")
    return out


def main():
    results = {}
    for tag in ("tmaj", "tfull"):
        results[tag] = mine_one(tag)
    print("EXP-041 regtest soundness gate: PASS for tmaj and tfull "
          "(soundness only; rate gate failed, no integration)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
