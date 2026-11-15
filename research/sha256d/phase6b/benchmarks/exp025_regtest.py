#!/usr/bin/env python3
"""EXP-025 fresh regtest gate.

Binds the REPAIRED cache (exp025_repaired.py) into the
production block-building flow: a research subclass of
mining.engine.MiningEngine overrides ONLY
build_candidate, routing candidate construction through
the identity-keyed repaired cache (RepairedFamily,
TemplateCache, RepairedTemplate). Everything else is
production code, unmodified: getblocktemplate handling,
the nonce search (production ComputeEngine), block
assembly, submitblock, and best-chain confirmation all
run through MiningEngine.mine_cycle.

Exactly which parts ran where:
  * Template fetch, search, assembly, submission,
    acceptance check: production (mining/engine.py,
    gpu/engine.py), unmodified.
  * Candidate construction (transaction pass, witness
    commitment, Merkle root, coinbase, header, body):
    the EXP-025 repaired cache in this research tree,
    through the subclass below. The production
    build_candidate is NOT used for construction in
    this harness; that is the honest limit of binding a
    research cache without editing production code, and
    it is labelled as such.
  * Every build_candidate call re-derives the
    template's full layered identity (identity_of)
    before serving, so the regtest path exercises the
    same fail-closed identity check the gates verify.

The regtest node is the lab's own regtest datadir
(.local/regtest, RPC 18443) managed by
node.node_manager. The mainnet node, autopilot and
miner are not touched.
"""
import json
import os
import sys
from datetime import datetime, timezone

ROOT = "/home/hatch/workspace/bitcoin-autonomous-lab"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "exp025")
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

from exp025_repaired import (RepairedFamily,  # noqa: E402
                             TemplateCache)
from gpu.engine import cpu_digest  # noqa: E402
from mining.engine import MiningEngine  # noqa: E402
from node import node_manager  # noqa: E402
from node.rpc_client import BitcoinRPC  # noqa: E402


class RepairedCacheEngine(MiningEngine):
    """Production MiningEngine with candidate
    construction served by the EXP-025 repaired cache."""

    def __init__(self, rpc, payout_address, **kw):
        super().__init__(rpc, payout_address, **kw)
        self.family = RepairedFamily(rpc, payout_address)
        self.cache = TemplateCache()
        self.backend = self.compute.backend

    def build_candidate(self, template, extranonce_int=0):
        prep, _was_hit = self.cache.get(self.family, template)
        return prep.build(extranonce_int, template=template)


def main():
    node_manager.start()
    rpc = BitcoinRPC()
    if "bal-regtest" not in rpc.call("listwallets"):
        try:
            rpc.call("loadwallet", "bal-regtest")
        except Exception:
            rpc.call("createwallet", "bal-regtest")
    wallet = BitcoinRPC(wallet="bal-regtest")
    payout = wallet.call("getnewaddress", "", "bech32")
    eng = RepairedCacheEngine(rpc, payout, batch_size=100_000)
    tip0 = rpc.get_block_count()
    out = eng.mine_cycle(max_batches=1000, deadline_seconds=600)
    assert out["accepted"], out
    assert rpc.get_best_block_hash() == out["hash"], out
    assert rpc.get_block_count() == tip0 + 1, out
    blk = rpc.call("getblock", out["hash"], 0)
    raw = bytes.fromhex(blk)
    header = raw[:80]
    nonce = int.from_bytes(header[76:80], "little")
    assert nonce == out["nonce"], (nonce, out["nonce"])
    d = cpu_digest(header, nonce)
    assert d[::-1].hex() == out["hash"]
    print(f"ok regtest (repaired cache): block accepted, "
          f"height {out['height']} hash {out['hash']} nonce "
          f"{out['nonce']} hashes {out['hashes']} "
          f"cache prepares={eng.cache.prepares} "
          f"hits={eng.cache.hits} "
          f"identity_checks={eng.cache.identity_checks}",
          flush=True)
    record = {
        "experiment": "EXP-025",
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "node": "regtest (.local/regtest, RPC 18443)",
        "construction_path": "EXP-025 repaired cache "
                             "(exp025_repaired.py) via "
                             "RepairedCacheEngine.build_candidate",
        "search_and_submission": "production MiningEngine."
                                 "mine_cycle + ComputeEngine",
        "height": out["height"], "hash": out["hash"],
        "nonce": out["nonce"], "hashes": out["hashes"],
        "extranonce_rounds": out["extranonce_rounds"],
        "submit_result": out["submit_result"],
        "cache_stats": {"prepares": eng.cache.prepares,
                        "hits": eng.cache.hits,
                        "identity_checks":
                            eng.cache.identity_checks},
        "accepted": True,
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(OUT_DIR, f"regtest_{stamp}.json")
    suffix = 2
    while os.path.exists(path):
        path = os.path.join(OUT_DIR, f"regtest_{stamp}_r{suffix}.json")
        suffix += 1
    with open(path, "x") as fh:
        json.dump(record, fh, indent=2)
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
