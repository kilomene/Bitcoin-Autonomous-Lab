"""Transaction intelligence on top of Bitcoin Core RPC.

Data sources: getrawtransaction (verbose), decoderawtransaction,
getmempoolinfo, getrawmempool, getmempoolentry.

Honest data handling: a transaction that the node cannot provide is
reported as unavailable with the node's reason, never guessed. Fees
are computed exactly from input values minus output values when every
input's previous output can be fetched; otherwise fee_sats is None
and fee_note explains why (for example, a coinbase transaction has no
fee, or a previous output is unavailable without txindex).
"""

import logging

from node.rpc_client import RpcError

log = logging.getLogger("bal.blockchain.tx")

SATS = 100_000_000


class TxUnavailable(Exception):
    """The node cannot provide this transaction, with its reason."""


def btc_to_sats(value_btc):
    if value_btc is None:
        return None
    return int(round(value_btc * SATS))


class TxInspector:
    def __init__(self, rpc):
        self.rpc = rpc

    def get_raw(self, txid, blockhash=None):
        try:
            if blockhash:
                return self.rpc.call("getrawtransaction", txid, True, blockhash)
            return self.rpc.call("getrawtransaction", txid, True)
        except RpcError as exc:
            raise TxUnavailable(
                f"transaction {txid} unavailable from this node: "
                f"[{exc.code}] {exc.rpc_message}. This usually means the "
                f"transaction is not in a block this node has, not in its "
                f"mempool, and (if it is an old spent transaction) txindex "
                f"coverage does not include it.") from exc

    def decode_raw(self, raw_hex):
        return self.rpc.call("decoderawtransaction", raw_hex)

    def inspect(self, txid, blockhash=None):
        """Full normalized view of one transaction."""
        tx = self.get_raw(txid, blockhash)
        return self.normalize(tx)

    def normalize(self, tx):
        vin = []
        is_coinbase = False
        for item in tx.get("vin", []):
            if "coinbase" in item:
                is_coinbase = True
                vin.append({"coinbase": item["coinbase"],
                            "sequence": item.get("sequence")})
            else:
                vin.append({"txid": item.get("txid"),
                            "vout": item.get("vout"),
                            "sequence": item.get("sequence")})
        vout = []
        for item in tx.get("vout", []):
            spk = item.get("scriptPubKey", {})
            vout.append({
                "n": item.get("n"),
                "value_sats": btc_to_sats(item.get("value")),
                "type": spk.get("type"),
                "address": spk.get("address"),
            })
        fee_sats, fee_note = self._fee(tx, is_coinbase)
        return {
            "txid": tx["txid"],
            "size": tx.get("size"),
            "vsize": tx.get("vsize"),
            "weight": tx.get("weight"),
            "version": tx.get("version"),
            "locktime": tx.get("locktime"),
            "confirmations": tx.get("confirmations", 0),
            "blockhash": tx.get("blockhash"),
            "time": tx.get("time"),
            "is_coinbase": is_coinbase,
            "vin": vin,
            "vout": vout,
            "total_output_sats": sum(v["value_sats"] or 0 for v in vout),
            "fee_sats": fee_sats,
            "fee_note": fee_note,
        }

    def _fee(self, tx, is_coinbase):
        if is_coinbase:
            return None, "coinbase transaction: no fee, it creates the subsidy plus block fees"
        in_total = 0
        for item in tx.get("vin", []):
            prev_txid = item.get("txid")
            prev_n = item.get("vout")
            if prev_txid is None:
                return None, "input without a previous output reference"
            try:
                prev = self.get_raw(prev_txid)
            except TxUnavailable as exc:
                return None, f"input value unavailable: {exc}"
            prev_outs = prev.get("vout", [])
            if prev_n is None or prev_n >= len(prev_outs):
                return None, "previous output index out of range"
            in_total += btc_to_sats(prev_outs[prev_n].get("value")) or 0
        out_total = sum(btc_to_sats(o.get("value")) or 0
                        for o in tx.get("vout", []))
        return in_total - out_total, "computed from input values minus output values"

    # Mempool
    def mempool_info(self):
        return self.rpc.call("getmempoolinfo")

    def mempool_txids(self):
        return self.rpc.call("getrawmempool", False)

    def mempool_entry(self, txid):
        try:
            entry = self.rpc.call("getmempoolentry", txid)
        except RpcError as exc:
            raise TxUnavailable(
                f"no mempool entry for {txid}: [{exc.code}] "
                f"{exc.rpc_message}") from exc
        fees = entry.get("fees", {})
        return {
            "txid": txid,
            "vsize": entry.get("vsize"),
            "weight": entry.get("weight"),
            "fee_sats": btc_to_sats(fees.get("base")),
            "fees": fees,
            "time": entry.get("time"),
            "height": entry.get("height"),
            "descendantcount": entry.get("descendantcount"),
            "ancestorcount": entry.get("ancestorcount"),
        }

    def mempool_snapshot(self):
        info = self.mempool_info()
        txids = self.mempool_txids()
        return {
            "size": info["size"],
            "bytes": info["bytes"],
            "usage": info["usage"],
            "total_fee_sats": btc_to_sats(info.get("total_fee")),
            "txids": txids,
        }
