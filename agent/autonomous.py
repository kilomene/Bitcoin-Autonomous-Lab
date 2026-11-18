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
import os
import time

from blockchain.store import BlockStore
from gpu.engine import ComputeEngine
from mining.engine import MiningEngine

log = logging.getLogger("bal.agent.autonomous")

# EXP-038: the GBT path's work-state checkpoint. The engine
# records its completed search frontier per template identity
# here, so an agent restarted mid-template resumes instead of
# rescanning from nonce 0 and extranonce 0, and its cycle
# results carry the checkpoint decision. See
# mining/work_checkpoint.py for the honesty rules.
WORK_CHECKPOINT_PATH = os.path.join(
    os.path.dirname(__file__), "..", ".local",
    "work-checkpoint.json")

MIN_BATCH = 4096
MAX_BATCH = 1 << 20
TARGET_BATCH_SECONDS = 0.25


class AutonomousMiner:
    def __init__(self, rpc, payout_address, store=None, compute=None,
                 allow_mainnet=False, use_prefetch=True):
        self.rpc = rpc
        self.store = store or BlockStore()
        self.compute = compute or ComputeEngine()
        # EXP-051 live enablement (Stage 9 enablements,
        # 2026-11-18, owner decision "enable all five"): the
        # agent path now constructs its MiningEngine with the
        # prepared-work prefetch queue enabled. The mechanism
        # was VERIFIED at regtest difficulty in EXP-051 (the
        # queue removed 57.1 percent of the median non-search
        # overhead per loaded block, zero stale serves in 84
        # campaign runs and the adversarial suite); the
        # engine's own default stays use_prefetch=False, so
        # every other MiningEngine caller is byte-for-byte
        # historical. Rollback is this one value:
        # use_prefetch=False restores the historical agent
        # path exactly (no queue is constructed, no feed
        # thread exists). At mainnet difficulty the EXP-051
        # record claims the effect is nil and measures
        # nothing there; this agent refuses mainnet without
        # allow_mainnet=True regardless.
        # Known semantic consequence, accepted with the
        # mechanism's design: a queue-served template is a
        # prepared snapshot. Its tip and identity are
        # re-verified at serve time, but its transaction set
        # is the set the feed prepared, so a transaction
        # that reaches the mempool after that preparation
        # enters the NEXT cycle's work, not the served
        # block. Blocks stay valid and fully verified
        # (EXP-036); only inclusion timing shifts by at
        # most one cycle. tests/test_mining_engine.py
        # encodes this explicitly.
        self.engine = MiningEngine(
            rpc, payout_address, self.compute,
            checkpoint_path=WORK_CHECKPOINT_PATH,
            use_prefetch=use_prefetch)
        self.use_prefetch = use_prefetch
        self.allow_mainnet = allow_mainnet
        self.decisions = []

    def close(self):
        """Stop the engine's prefetch feed thread, if any
        (EXP-051 enablement). Safe when prefetch is disabled
        or was never started; the queue and its counters
        remain inspectable afterwards."""
        self.engine.close_prefetch()

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
