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
    def __init__(self, rpc=None):
        self.rpc = rpc or BitcoinRPC()
        self.chain = ChainMonitor(self.rpc)

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
    else:
        print(f"unknown command: {cmd}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
