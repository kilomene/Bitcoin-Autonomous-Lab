"""Basic blockchain monitoring built on the node RPC client.

Task 001 scope: height, latest block, block lookup by height or hash,
and a polling watcher that reports new blocks as they appear. Task 002
extends this module into the full Blockchain Intelligence Engine
(transaction intelligence, storage, reorganization handling).
"""

import logging
import time

log = logging.getLogger("bal.blockchain.monitor")


class ChainMonitor:
    def __init__(self, rpc):
        self.rpc = rpc

    def height(self):
        return self.rpc.get_block_count()

    def info(self):
        return self.rpc.get_blockchain_info()

    def block_by_height(self, height, verbosity=1):
        return self.rpc.get_block(self.rpc.get_block_hash(height), verbosity)

    def block_by_hash(self, blockhash, verbosity=1):
        return self.rpc.get_block(blockhash, verbosity)

    def latest_block(self, verbosity=1):
        return self.rpc.get_block(self.rpc.get_best_block_hash(), verbosity)

    def latest_blocks(self, count, verbosity=1):
        tip = self.height()
        out = []
        for h in range(max(0, tip - count + 1), tip + 1):
            out.append(self.block_by_height(h, verbosity))
        return out

    def watch(self, on_block, poll_seconds=2.0, stop_after=None):
        """Poll height and call on_block(block) for each new block.

        Returns the number of blocks delivered. Handles the node being
        briefly unreachable by logging and retrying rather than dying.
        """
        from node.rpc_client import RpcConnectionError
        delivered = 0
        last_seen = None
        while stop_after is None or delivered < stop_after:
            try:
                tip = self.height()
            except RpcConnectionError as exc:
                log.warning("watch: node unreachable, retrying: %s", exc)
                time.sleep(poll_seconds)
                continue
            if last_seen is None:
                last_seen = tip
            while last_seen < tip:
                last_seen += 1
                block = self.block_by_height(last_seen)
                on_block(block)
                delivered += 1
                if stop_after is not None and delivered >= stop_after:
                    break
            time.sleep(poll_seconds)
        return delivered
