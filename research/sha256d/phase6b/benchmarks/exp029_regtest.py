#!/usr/bin/env python3
"""EXP-029 end-to-end regtest gate.

The distributed path mines a fresh regtest block: the
production MiningEngine builds the candidate
(getblocktemplate, coinbase, Merkle root, assembly,
submission all production mining/engine.py), and the
nonce search is served by a DistributedCompute shim
that partitions every batch through the EXP-029
RangeAllocator into chunks leased to two worker
threads, each running its own production ComputeEngine
(C backend, requested="c" for per-worker isolation)
over its leased chunk. The allocator's accounting for
the winning batch is recorded: chunks are disjoint by
construction, every chunk runs to its own completion
or its own hit, and the shim returns the lowest-nonce
candidate across chunks.

Exactly which parts ran where:
  * Template, candidate build, assembly, submission:
    production code, unmodified.
  * Search: production C backend kernels, partitioned
    and scheduled by the research allocator prototype.
    This is a local in-process distribution (threads in
    one process on one host), NOT a multi-machine run.
  * Candidate verification: the production
    ComputeEngine re-verifies every candidate it
    returns (gpu/engine.py verify_candidate), and
    MiningEngine submits only verified candidates.
  * The mainnet node, autopilot and miner are not
    touched; the node here is the lab regtest datadir
    (.local/regtest, RPC 18443).
"""
import json
import os
import sys
import threading
from datetime import datetime, timezone

ROOT = "/home/hatch/workspace/bitcoin-autonomous-lab"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "exp029")
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from exp029_allocator import RangeAllocator  # noqa: E402
from gpu.engine import ComputeEngine, cpu_digest  # noqa: E402
from mining.engine import MiningEngine  # noqa: E402
from node import node_manager  # noqa: E402
from node.rpc_client import BitcoinRPC  # noqa: E402


class DistributedCompute:
    """ComputeEngine counted-search surface backed by
    the allocator plus per-worker production engines."""

    def __init__(self, workers=2, chunk=16384):
        self._workers = workers
        self._chunk = chunk
        self.backend = "exp029-distributed(c x%d)" % workers
        self.last_search_stats = {}
        self.batch_records = []

    def search_first_counted(self, header, target, start, count):
        alloc = RangeAllocator("regtest-batch", start, count,
                               self._chunk)
        engines = {f"w{i}": ComputeEngine(requested="c")
                   for i in range(self._workers)}
        hits = []
        stats = []
        lock = threading.Lock()

        def body(name):
            eng = engines[name]
            while True:
                got = alloc.lease(name)
                if got is None:
                    return
                lo, hi = got
                res, attempted, _dt = eng.search_first_counted(
                    header, target, lo, hi - lo)
                alloc.progress(name, lo, attempted)
                with lock:
                    stats.append(dict(eng.last_search_stats))
                    if res is not None:
                        hits.append(res)
                # A chunk is complete when its own search
                # returns: it either scanned the whole
                # chunk or stopped at its own hit.
                alloc.complete(name, lo)

        threads = [threading.Thread(target=body, args=(f"w{i}",))
                   for i in range(self._workers)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        acc = alloc.accounting()
        attempted = sum(s.get("attempted", 0) for s in stats)
        self.last_search_stats = {
            "backend": self.backend, "counted": True,
            "attempted": attempted,
            "backend_hashes": sum(
                s.get("backend_hashes", 0) for s in stats),
            "unique_coverage": acc["unique_coverage"],
            "candidate_count": len(hits),
            "verification_hashes": sum(
                s.get("verification_hashes", 0) for s in stats)}
        self.batch_records.append({
            "start": start, "count": count,
            "allocator": acc, "hits": len(hits)})
        if not hits:
            return None, attempted, 0.0
        hits.sort(key=lambda r: r[0])
        return hits[0], attempted, 0.0


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
    compute = DistributedCompute(workers=2, chunk=16384)
    eng = MiningEngine(rpc, payout, compute=compute,
                       batch_size=65536)
    tip0 = rpc.get_block_count()
    out = eng.mine_cycle(max_batches=1000, deadline_seconds=600)
    assert out["accepted"], out
    assert rpc.get_best_block_hash() == out["hash"], out
    assert rpc.get_block_count() == tip0 + 1, out
    raw = bytes.fromhex(rpc.call("getblock", out["hash"], 0))
    header = raw[:80]
    nonce = int.from_bytes(header[76:80], "little")
    assert nonce == out["nonce"], (nonce, out["nonce"])
    d = cpu_digest(header, nonce)
    assert d[::-1].hex() == out["hash"]
    record = {
        "experiment": "EXP-029",
        "kind": "distributed-path regtest block, local "
                "in-process distribution (2 worker threads, "
                "production C backend per worker)",
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "node": "regtest (.local/regtest, RPC 18443)",
        "height": out["height"], "hash": out["hash"],
        "nonce": out["nonce"], "hashes": out["hashes"],
        "batches": out["batches"],
        "batch_records": compute.batch_records,
        "all_accepted": True}
    os.makedirs(OUT_DIR, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(OUT_DIR, f"regtest_{stamp}.json")
    suffix = 2
    while os.path.exists(path):
        path = os.path.join(OUT_DIR, f"regtest_{stamp}_r{suffix}.json")
        suffix += 1
    with open(path, "x") as fh:
        json.dump(record, fh, indent=2)
    print(f"ok regtest: height {out['height']} hash "
          f"{out['hash']} nonce {out['nonce']}")
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
