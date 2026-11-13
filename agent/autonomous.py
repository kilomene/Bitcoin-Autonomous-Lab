"""Tasks 005/006: the autonomous mining agent.

Coordinates the mining lifecycle without manual intervention:
diagnostics first (backend selection from a measured benchmark),
then repeated MiningEngine cycles with batch size management from
measured batch times, persistent statistics and a decision log in
the engine store. Every cycle result is recorded, including
failures; errors are events, never silence.

Chain guard: the agent refuses to run on mainnet unless the caller
explicitly passes allow_mainnet=True. Regtest is the default and the
only chain this phase is verified on. (The lab's earlier mainnet
work was pool mining over Stratum, a separate path in
mining/stratum_client.py.)
"""

import logging
import time

from blockchain.store import BlockStore
from gpu.engine import ComputeEngine
from mining.engine import MiningEngine

log = logging.getLogger("bal.agent.autonomous")

MIN_BATCH = 4096
MAX_BATCH = 1 << 20
TARGET_BATCH_SECONDS = 0.25


class AutonomousMiner:
    def __init__(self, rpc, payout_address, store=None, compute=None,
                 allow_mainnet=False):
        self.rpc = rpc
        self.store = store or BlockStore()
        self.compute = compute or ComputeEngine()
        self.engine = MiningEngine(rpc, payout_address, self.compute)
        self.allow_mainnet = allow_mainnet
        self.decisions = []

    def _decide(self, kind, detail):
        entry = {"kind": kind, "detail": detail, "ts": time.time()}
        self.decisions.append(entry)
        self.store.record_event("agent_decision", entry)
        log.info("decision %s: %s", kind, detail)

    def _guard_chain(self):
        chain = self.rpc.get_blockchain_info()["chain"]
        if chain == "main" and not self.allow_mainnet:
            raise RuntimeError(
                "autonomous miner refuses mainnet without "
                "allow_mainnet=True (regtest research phase)")
        return chain

    def _adjust_batch(self, stats):
        current = self.engine.batch_size
        secs = stats.get("seconds") or 0
        if secs <= 0:
            return
        if secs < TARGET_BATCH_SECONDS / 2 and current < MAX_BATCH:
            new = min(current * 2, MAX_BATCH)
        elif secs > TARGET_BATCH_SECONDS * 2 and current > MIN_BATCH:
            new = max(current // 2, MIN_BATCH)
        else:
            return
        if new != current:
            self._decide("batch-size-adjusted",
                         f"batch_size {current} -> {new} from measured "
                         f"batch time {secs:.3f}s")
            self.engine.batch_size = new

    def run_cycles(self, cycles=3, max_batches_per_cycle=400):
        chain = self._guard_chain()
        bench = self.compute.benchmark()
        self._decide("backend-selected",
                     f"backend={self.compute.backend} (requested auto); "
                     f"fallback_reason={self.compute.fallback_reason}; "
                     f"measured {bench:.0f} H/s")
        results = []
        for i in range(cycles):
            try:
                result = self.engine.mine_cycle(
                    max_batches=max_batches_per_cycle)
            except Exception as exc:
                result = {"accepted": False, "reason": f"error: {exc}",
                          "height": None, "hashes": 0, "batches": 0,
                          "backend": self.compute.backend, "seconds": 0}
                self.store.record_event("mining_error",
                                        {"cycle": i + 1, "error": str(exc)})
            self.store.record_mining_cycle(result)
            if result.get("accepted"):
                self._decide("cycle-accepted",
                             f"height={result['height']} "
                             f"hash={result['hash']} nonce={result['nonce']} "
                             f"hashes={result['hashes']} "
                             f"backend={result['backend']}")
            else:
                self._decide("cycle-failed",
                             f"height={result.get('height')} "
                             f"reason={result.get('reason')}")
            # adapt batch size from the cycle timing
            if result.get("hashes") and result.get("seconds"):
                self._adjust_batch({"seconds": result["seconds"]
                                    / max(result.get("batches", 1), 1)})
            results.append(result)
        return {
            "chain": chain,
            "backend": self.compute.backend,
            "fallback_reason": self.compute.fallback_reason,
            "benchmark_hs": bench,
            "cycles": results,
            "summary": self.store.mining_summary(),
            "decisions": self.decisions,
        }
