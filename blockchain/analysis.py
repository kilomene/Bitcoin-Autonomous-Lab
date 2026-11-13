"""Block structure analysis, verified against the node's own data.

Covers: header fields, previous hash linkage, merkle root
verification (recomputed from the block's transaction list), Proof of
Work target check (header rehashed and compared to its target),
difficulty, size and weight, transaction count, block subsidy from
the halving schedule, and total transaction fees (coinbase output
total minus subsidy, cross-checked against per-transaction fees).
"""

import logging
import struct

from blockchain.transactions import TxInspector
from mining.pow import (coinbase_subsidy, dsha256, merkle_root,
                        target_from_nbits)

log = logging.getLogger("bal.blockchain.analysis")


def build_header(block):
    prev = (bytes.fromhex(block["previousblockhash"])[::-1]
            if "previousblockhash" in block else b"\x00" * 32)
    return (
        struct.pack("<I", block["version"])
        + prev
        + bytes.fromhex(block["merkleroot"])[::-1]
        + struct.pack("<I", block["time"])
        + bytes.fromhex(block["bits"])[::-1]
        + struct.pack("<I", block["nonce"])
    )


class BlockAnalyzer:
    def __init__(self, rpc):
        self.rpc = rpc
        self.tx = TxInspector(rpc)

    def analyze(self, ref):
        """ref is a block hash (str, 64 hex) or a height (int)."""
        if isinstance(ref, int):
            blockhash = self.rpc.get_block_hash(ref)
        else:
            blockhash = ref
        block = self.rpc.get_block(blockhash, 2)
        header = self.rpc.get_block_header(blockhash, True)

        merkle_ok, merkle_computed = self.verify_merkle(block)
        pow_ok = self.verify_pow(block)

        chain = self.rpc.get_blockchain_info()["chain"]
        subsidy = coinbase_subsidy(
            block["height"], 150 if chain == "regtest" else 210000)
        coinbase = block["tx"][0]
        coinbase_out = sum(int(round(o["value"] * 100_000_000))
                           for o in coinbase["vout"])
        fees_from_coinbase = coinbase_out - subsidy

        fees_from_txs = 0
        fees_complete = True
        for tx in block["tx"][1:]:
            view = self.tx.normalize(tx)
            if view["fee_sats"] is None:
                fees_complete = False
            else:
                fees_from_txs += view["fee_sats"]

        return {
            "hash": block["hash"],
            "height": block["height"],
            "confirmations": block["confirmations"],
            "version": block["version"],
            "previousblockhash": block.get("previousblockhash"),
            "merkleroot": block["merkleroot"],
            "merkle_verified": merkle_ok,
            "merkle_computed": merkle_computed,
            "time": block["time"],
            "mediantime": block.get("mediantime"),
            "nonce": block["nonce"],
            "bits": block["bits"],
            "difficulty": block["difficulty"],
            "chainwork": block["chainwork"],
            "pow_verified": pow_ok,
            "size": block["size"],
            "strippedsize": block.get("strippedsize"),
            "weight": block["weight"],
            "tx_count": len(block["tx"]),
            "subsidy_sats": subsidy,
            "coinbase_output_sats": coinbase_out,
            "total_fees_sats_from_coinbase": fees_from_coinbase,
            "total_fees_sats_from_txs": fees_from_txs if fees_complete else None,
            "fees_agree": (fees_from_txs == fees_from_coinbase) if fees_complete else None,
            "header": {
                "version": header["version"],
                "previousblockhash": header.get("previousblockhash"),
                "merkleroot": header["merkleroot"],
                "time": header["time"],
                "bits": header["bits"],
                "nonce": header["nonce"],
                "difficulty": header["difficulty"],
                "target": "%064x" % target_from_nbits(int(header["bits"], 16)),
            },
        }

    def verify_merkle(self, block):
        """Recompute the merkle root from getblock verbosity-1 txids.

        Accepts either a verbosity-1 block (tx = list of txid strings)
        or verbosity-2 (tx = list of objects)."""
        txids = []
        for item in block["tx"]:
            txid = item if isinstance(item, str) else item["txid"]
            txids.append(bytes.fromhex(txid)[::-1])
        computed = merkle_root(txids)[::-1].hex()
        return computed == block["merkleroot"], computed

    def verify_pow(self, block):
        header = build_header(block)
        digest = dsha256(header)
        if digest[::-1].hex() != block["hash"]:
            return False
        target = target_from_nbits(int(block["bits"], 16))
        return int.from_bytes(digest, "little") <= target
