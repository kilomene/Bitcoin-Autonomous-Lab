"""Agent interface: structured answers from real node data.

Task 001 scope: node status, chain info, height, latest block, block
lookup, and test block generation on Regtest. Every method returns a
plain dict (JSON serializable) built only from Bitcoin Core RPC data.
Task 002 extends the question set (mempool, analysis, search).

CLI examples:
    python3 -m agent.interface height
    python3 -m agent.interface latest
    python3 -m agent.interface generate 5
"""

import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from blockchain.monitor import ChainMonitor
from node.rpc_client import BitcoinRPC

log = logging.getLogger("bal.agent")


class AgentInterface:
    def __init__(self, rpc=None, store=None):
        self.rpc = rpc or BitcoinRPC()
        self.chain = ChainMonitor(self.rpc)
        self._store = store

    # Task 002: Blockchain Intelligence Engine questions.
    @property
    def _engine_store(self):
        if self._store is None:
            from blockchain.store import BlockStore
            self._store = BlockStore()
        return self._store

    def latest_block_hash(self):
        return {"bestblockhash": self.rpc.get_best_block_hash(),
                "height": self.chain.height()}

    def latest_blocks(self, count=10):
        blocks = self.chain.latest_blocks(count)
        return {"count": len(blocks), "blocks": [
            {"height": b["height"], "hash": b["hash"], "time": b["time"],
             "tx_count": len(b.get("tx", [])),
             "previousblockhash": b.get("previousblockhash")}
            for b in blocks]}

    def analyze_block(self, ref):
        from blockchain.analysis import BlockAnalyzer
        if isinstance(ref, str) and ref.isdigit():
            ref = int(ref)
        return BlockAnalyzer(self.rpc).analyze(ref)

    def block_tx_count(self, ref=None):
        if ref is None:
            b = self.chain.latest_block()
        elif isinstance(ref, str) and ref.isdigit():
            b = self.chain.block_by_height(int(ref))
        else:
            b = self.chain.block_by_hash(ref)
        return {"hash": b["hash"], "height": b["height"],
                "tx_count": len(b.get("tx", []))}

    def network_difficulty(self):
        info = self.chain.info()
        return {"difficulty": info["difficulty"], "chain": info["chain"],
                "blocks": info["blocks"]}

    def mempool_status(self):
        from blockchain.transactions import TxInspector
        return TxInspector(self.rpc).mempool_snapshot()

    def inspect_transaction(self, txid):
        from blockchain.transactions import TxInspector
        return TxInspector(self.rpc).inspect(txid)

    def has_new_block(self, since_height):
        from blockchain.service import MonitorService
        return MonitorService(self.rpc, self._engine_store).has_new_block(
            int(since_height))

    def sync_status(self):
        from blockchain.service import MonitorService
        return MonitorService(self.rpc, self._engine_store).status()

    def node_status(self):
        info = self.chain.info()
        return {
            "chain": info["chain"],
            "blocks": info["blocks"],
            "headers": info["headers"],
            "bestblockhash": info["bestblockhash"],
            "difficulty": info["difficulty"],
            "verificationprogress": info["verificationprogress"],
            "size_on_disk": info.get("size_on_disk"),
        }

    def current_height(self):
        return {"height": self.chain.height()}

    def latest_block(self):
        b = self.chain.latest_block()
        return {
            "hash": b["hash"],
            "height": b["height"],
            "time": b["time"],
            "tx_count": len(b.get("tx", [])),
            "previousblockhash": b.get("previousblockhash"),
            "difficulty": b["difficulty"],
            "nonce": b["nonce"],
            "merkleroot": b["merkleroot"],
        }

    def get_block(self, blockhash):
        b = self.chain.block_by_hash(blockhash, verbosity=2)
        return b

    def generate_blocks(self, count, address=None):
        """Regtest only: generate blocks to a wallet address."""
        info = self.chain.info()
        if info["chain"] != "regtest":
            raise RuntimeError("block generation is Regtest only")
        wallet_rpc = BitcoinRPC(wallet="bal-regtest")
        if address is None:
            address = wallet_rpc.call("getnewaddress", "", "bech32")
        hashes = self.rpc.call("generatetoaddress", count, address)
        return {"generated": len(hashes), "hashes": hashes, "address": address}


def main(argv):
    logging.basicConfig(level=logging.WARNING)
    agent = AgentInterface()
    if not argv:
        print(__doc__)
        return 2
    cmd = argv[0]
    if cmd == "status":
        print(json.dumps(agent.node_status(), indent=2))
    elif cmd == "height":
        print(json.dumps(agent.current_height(), indent=2))
    elif cmd == "latest":
        print(json.dumps(agent.latest_block(), indent=2))
    elif cmd == "block":
        print(json.dumps(agent.get_block(argv[1]), indent=2))
    elif cmd == "generate":
        print(json.dumps(agent.generate_blocks(int(argv[1])), indent=2))
    elif cmd == "latesthash":
        print(json.dumps(agent.latest_block_hash(), indent=2))
    elif cmd == "blocks":
        print(json.dumps(agent.latest_blocks(int(argv[1]) if len(argv) > 1 else 10), indent=2))
    elif cmd == "analyze":
        print(json.dumps(agent.analyze_block(argv[1]), indent=2))
    elif cmd == "txcount":
        print(json.dumps(agent.block_tx_count(argv[1] if len(argv) > 1 else None), indent=2))
    elif cmd == "difficulty":
        print(json.dumps(agent.network_difficulty(), indent=2))
    elif cmd == "mempool":
        print(json.dumps(agent.mempool_status(), indent=2))
    elif cmd == "tx":
        print(json.dumps(agent.inspect_transaction(argv[1]), indent=2))
    elif cmd == "newblock":
        print(json.dumps(agent.has_new_block(int(argv[1])), indent=2))
    elif cmd == "sync":
        print(json.dumps(agent.sync_status(), indent=2))
    else:
        print(f"unknown command: {cmd}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
