"""Watch-only address tracking.

Creates (or reuses) a descriptor wallet with no private keys,
imports an address as a watch-only descriptor, and answers balance,
UTXO and received-payment questions for it from the node's own data:
getbalances, listunspent and listtransactions on the watch wallet,
plus scantxoutset as an independent cross-check that needs no wallet
state at all.

Descriptors need a checksum: getdescriptorinfo supplies it. Import
uses timestamp 0 so the node rescans its (small, regtest) chain.
"""

import logging

from node.rpc_client import BitcoinRPC, RpcError

log = logging.getLogger("bal.blockchain.watch")

WATCH_WALLET = "bal-watchonly"


class WatchWallet:
    def __init__(self, rpc):
        self.node = rpc
        self.rpc = self._ensure_wallet(rpc)

    def _ensure_wallet(self, rpc):
        names = rpc.call("listwalletdir")["wallets"]
        loaded = rpc.call("listwallets")
        exists = any(w["name"] == WATCH_WALLET for w in names)
        if WATCH_WALLET not in loaded:
            if exists:
                rpc.call("loadwallet", WATCH_WALLET)
            else:
                # createwallet(name, disable_private_keys=True,
                # blank=True, passphrase, avoid_reuse,
                # descriptors=True): a true watch-only wallet.
                rpc.call("createwallet", WATCH_WALLET, True, True,
                         "", False, True)
        return BitcoinRPC(wallet=WATCH_WALLET)

    def watch(self, address):
        """Import an address for watching. Returns the descriptor."""
        desc_plain = f"addr({address})"
        desc = self.rpc.call("getdescriptorinfo", desc_plain)["descriptor"]
        results = self.rpc.call("importdescriptors", [{
            "desc": desc, "timestamp": 0, "active": False,
            "internal": False, "watchonly": True}])
        for item in results:
            if not item.get("success"):
                err = item.get("error", {}).get("message", "import failed")
                if "already" not in err.lower():
                    raise RpcError("importdescriptors", -1, err)
        return desc

    def balance(self, address=None):
        bal = self.rpc.call("getbalances")
        watch = bal.get("watchonly", {})
        return {
            "trusted_sats": int(round(watch.get("trusted", 0) * 100_000_000)),
            "untrusted_pending_sats": int(round(
                watch.get("untrusted_pending", 0) * 100_000_000)),
            "immature_sats": int(round(watch.get("immature", 0) * 100_000_000)),
        }

    def utxos(self, address):
        return self.rpc.call("listunspent", 0, 9999999, [address])

    def received(self, address, count=50):
        txs = self.rpc.call("listtransactions", "*", count, 0, True)
        return [t for t in txs
                if t.get("address") == address
                and t.get("category") in ("receive", "generate", "immature")]

    def scan_balance(self, address):
        """Wallet-independent cross-check via scantxoutset."""
        result = self.node.call("scantxoutset", "start",
                                [f"addr({address})"])
        return {"total_sats": int(round(result["total_amount"] * 100_000_000)),
                "utxos": len(result["unspents"]),
                "height": result["height"]}
