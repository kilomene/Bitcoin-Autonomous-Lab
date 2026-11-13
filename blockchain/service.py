"""Blockchain monitoring service.

One service object, three jobs:

1. Synchronization: walk from the last stored height to the node tip,
   fetching each block once and storing its metadata (and, optionally,
   indexing its transactions). No block is fetched twice: the walk
   starts at the stored tip.
2. Reorganization handling: before extending, the stored tip is
   compared with the node's chain at the same heights. On a mismatch
   the fork point is found by walking down, affected stored blocks
   are invalidated in the store, a reorg chain_event is recorded, and
   the new branch is processed.
3. Resilience: RPC failures never raise out of the run loop. The
   service records sync state "disconnected", backs off, and retries.
   sync_once() returns a status dict in every case.

Mempool watching: each sync also snapshots the mempool txid set;
newly seen txids are stored and reported as mempool_new events.
"""

import logging
import time

from node.rpc_client import RpcConnectionError, RpcError

log = logging.getLogger("bal.blockchain.service")


class MonitorService:
    def __init__(self, rpc, store, poll_seconds=2.0, index_transactions=True):
        self.rpc = rpc
        self.store = store
        self.poll_seconds = poll_seconds
        self.index_transactions = index_transactions
        self._known_mempool = set()
        self._stop = False

    # Internal helpers
    def _stored_tip(self):
        sync = self.store.get_sync()
        return sync["tip_height"], sync["tip_hash"]

    def _find_fork(self, node_tip_height):
        """Return the greatest height where stored and node agree."""
        stored_tip, _ = self._stored_tip()
        h = min(stored_tip, node_tip_height)
        while h >= 0:
            stored = self.store.block_at_height(h)
            if stored is None:
                return h - 1
            if stored["hash"] == self.rpc.get_block_hash(h):
                return h
            h -= 1
        return -1

    def _process_block(self, height):
        block = self.rpc.get_block(self.rpc.get_block_hash(height), 1)
        self.store.upsert_block(block)
        if self.index_transactions:
            full = self.rpc.get_block(block["hash"], 2)
            for tx in full["tx"]:
                self.store.upsert_transaction(
                    {"txid": tx["txid"], "confirmations": tx.get("confirmations", 1),
                     "size": tx.get("size"), "vsize": tx.get("vsize"),
                     "weight": tx.get("weight"), "fee_sats": None,
                     "vin": tx.get("vin", []), "vout": tx.get("vout", [])},
                    block_hash=block["hash"], block_height=height)
        self.store.record_event("new_block", {
            "height": height, "hash": block["hash"],
            "tx_count": len(block.get("tx", []))})
        return block

    def _sync_mempool(self):
        from blockchain.transactions import TxInspector
        insp = TxInspector(self.rpc)
        try:
            current = set(insp.mempool_txids())
        except RpcError as exc:
            log.warning("mempool read failed: %s", exc)
            return []
        new = current - self._known_mempool
        for txid in sorted(new):
            view = insp.inspect(txid)
            self.store.upsert_transaction(view, in_mempool=True)
            self.store.record_event("mempool_new", {"txid": txid})
        gone = self._known_mempool - current
        self._known_mempool = current
        return sorted(new)

    # Public API
    def sync_once(self):
        """Synchronize the store with the node. Never raises for
        connection problems; returns a status dict."""
        try:
            info = self.rpc.get_blockchain_info()
        except (RpcConnectionError, RpcError) as exc:
            self.store.set_sync(*self._stored_tip(), "disconnected")
            log.warning("sync: node unreachable: %s", exc)
            return {"status": "disconnected", "error": str(exc)}
        node_tip = info["blocks"]

        stored_tip, _ = self._stored_tip()
        new_blocks = []
        reorg = None
        try:
            if stored_tip >= 0:
                fork = self._find_fork(node_tip)
                if fork < stored_tip:
                    dropped = self.store.invalidate_from(fork + 1)
                    reorg = {"fork_height": fork, "dropped_blocks": dropped,
                             "previous_stored_tip": stored_tip}
                    self.store.record_event("reorg", reorg)
                    self.store.set_sync(fork,
                                        self.rpc.get_block_hash(fork) if fork >= 0 else None,
                                        "reorg")
                    stored_tip = fork
            for height in range(stored_tip + 1, node_tip + 1):
                block = self._process_block(height)
                new_blocks.append(block["hash"])
                self.store.set_sync(height, block["hash"], "synced")
            mempool_new = self._sync_mempool()
        except (RpcConnectionError, RpcError) as exc:
            self.store.set_sync(*self._stored_tip(), "error")
            log.warning("sync interrupted: %s", exc)
            return {"status": "error", "error": str(exc),
                    "new_blocks": new_blocks, "reorg": reorg}

        return {
            "status": "synced",
            "chain": info["chain"],
            "node_tip": node_tip,
            "stored_tip": node_tip,
            "new_blocks": new_blocks,
            "reorg": reorg,
            "mempool_new": mempool_new,
            "bestblockhash": info["bestblockhash"],
        }

    def has_new_block(self, since_height):
        """Structured answer for the agent: is there a newer block?"""
        try:
            tip = self.rpc.get_block_count()
        except (RpcConnectionError, RpcError) as exc:
            return {"status": "disconnected", "error": str(exc)}
        return {
            "current_height": tip,
            "since_height": since_height,
            "new_block": tip > since_height,
            "blocks_behind": max(0, tip - since_height),
            "bestblockhash": self.rpc.get_best_block_hash(),
        }

    def run(self, duration_seconds=None, max_cycles=None):
        """Poll loop. Returns after duration or max_cycles, or stop()."""
        self._stop = False
        started = time.time()
        cycles = 0
        while not self._stop:
            result = self.sync_once()
            cycles += 1
            if result["status"] == "disconnected":
                time.sleep(min(self.poll_seconds * 4, 30))
            else:
                time.sleep(self.poll_seconds)
            if max_cycles is not None and cycles >= max_cycles:
                break
            if duration_seconds is not None and time.time() - started >= duration_seconds:
                break
        return {"cycles": cycles}

    def stop(self):
        self._stop = True

    def status(self):
        sync = self.store.get_sync()
        return {
            "sync": sync,
            "stored_blocks": self.store.block_count(),
            "stored_transactions": self.store.transaction_count(),
            "known_mempool_txids": len(self._known_mempool),
        }
