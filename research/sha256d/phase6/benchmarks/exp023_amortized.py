#!/usr/bin/env python3
"""EXP-023 amortised candidate builder (Y-076/Y-077 prototype).

A research prototype of the two-level cache the midstate
amortisation family describes, applied to the lab's own
GBT path (mining/engine.py MiningEngine.build_candidate):

  Level 1, FamilyContext: per (node, payout) constants.
    build_candidate re-derives them on EVERY call: one
    validateaddress RPC for the payout script and one
    getblockchaininfo RPC for the halving interval. The
    family context pays both once.

  Level 2, PreparedTemplate: per template (tx set).
    build_candidate re-runs the full transaction pass on
    every extranonce call: strip-and-rehash every tx for
    its txid, rehash every tx for its wtxid, rebuild the
    witness commitment, and rebuild the whole merkle tree
    over [coinbase] + txids. None of that depends on the
    extranonce. The prepared template pays it once, caches
    the merkle tree levels over a placeholder coinbase
    leaf, and per extranonce step walks only the coinbase
    spine of the tree (ceil(log2(n+1)) double hashes,
    X-060's incremental spine) plus the coinbase build
    itself, which is genuinely extranonce-dependent.

The prototype lives outside production files and changes
no production behaviour. Its builds are gated
byte-identical to build_candidate (exp023_gates.py).
"""
import struct
import sys
import time

ROOT = "/home/hatch/workspace/bitcoin-autonomous-lab"
sys.path.insert(0, ROOT)

from mining.engine import (RESERVED_VALUE, TemplateError,  # noqa: E402
                           address_script_pubkey, build_coinbase,
                           encode_varint, txid_of, wtxid_of)
from mining.pow import coinbase_subsidy, dsha256, merkle_root  # noqa: E402

ZERO32 = b"\x00" * 32


class FamilyContext:
    """Level 1: constants shared by every template a node
    serves to one payout address."""

    def __init__(self, rpc, payout_address):
        self.rpc = rpc
        self.payout = payout_address
        self.script = address_script_pubkey(rpc, payout_address)
        self.chain = rpc.get_blockchain_info()["chain"]
        self.interval = 150 if self.chain == "regtest" else 210000


class PreparedTemplate:
    """Level 2: one template's extranonce-independent work,
    paid once; build() then prices a single extranonce step.
    """

    def __init__(self, family, template):
        self.family = family
        txs_raw = []
        txids = []
        wtxids = []
        total_fees = 0
        for tx in template.get("transactions", []):
            for field in ("txid", "data"):
                if field not in tx:
                    raise TemplateError(f"template tx missing {field}")
            raw = bytes.fromhex(tx["data"])
            computed_txid = txid_of(raw)[::-1].hex()
            if computed_txid != tx["txid"]:
                raise TemplateError(
                    f"template txid mismatch: core {tx['txid']} vs "
                    f"computed {computed_txid}")
            txs_raw.append(raw)
            txids.append(bytes.fromhex(tx["txid"])[::-1])
            wtxids.append(wtxid_of(raw))
            total_fees += tx.get("fee", 0)
        witness_count = sum(1 for a, b in zip(txids, wtxids) if a != b)
        commitment = None
        if witness_count:
            wroot = merkle_root([ZERO32] + wtxids)
            commitment = dsha256(wroot + RESERVED_VALUE)
            expected = template.get("default_witness_commitment")
            if expected and commitment.hex() not in expected:
                raise TemplateError("witness commitment disagrees with Core")
        subsidy = coinbase_subsidy(template["height"], family.interval)
        value = template["coinbasevalue"]
        if value != subsidy + total_fees:
            raise TemplateError(
                f"coinbasevalue {value} != subsidy {subsidy} + fees "
                f"{total_fees}")
        self.template = template
        self.txs_raw = txs_raw
        self.txids = txids
        self.total_fees = total_fees
        self.witness_count = witness_count
        self.commitment = commitment
        self.value = value
        self.flags_hex = template.get("coinbaseaux", {}).get("flags", "")
        self.target = int(template["target"], 16)
        self.height = template["height"]
        # Merkle tree levels over [placeholder coinbase] +
        # txids, built with the same odd-level duplication
        # as mining.pow.merkle_root. Level 0 is the leaf row;
        # the last level holds the root of the placeholder
        # tree and is never read by the spine walk.
        levels = [[ZERO32] + list(txids)]
        while len(levels[-1]) > 1:
            lvl = levels[-1]
            levels.append([
                dsha256(lvl[i] + (lvl[i + 1] if i + 1 < len(lvl)
                                  else lvl[i]))
                for i in range(0, len(lvl), 2)])
        self.levels = levels
        self.body_head = encode_varint(1 + len(txs_raw))
        self.body_tail = b"".join(txs_raw)
        self.fingerprint = self._fingerprint(template)

    def _fingerprint(self, template):
        txs = template.get("transactions", [])
        return (template["version"], template["previousblockhash"],
                template["bits"], template["height"],
                template["coinbasevalue"], len(txs),
                txs[0]["txid"] if txs else None,
                txs[-1]["txid"] if txs else None)

    def root_with_coinbase(self, cb_txid):
        """Merkle root over [cb_txid] + txids by walking
        only the coinbase spine of the cached tree."""
        if len(self.levels) == 1:
            return cb_txid
        cur = cb_txid
        idx = 0
        for level in self.levels[:-1]:
            sib = idx ^ 1
            sib_hash = level[sib] if sib < len(level) else level[idx]
            cur = (dsha256(cur + sib_hash) if idx % 2 == 0
                   else dsha256(sib_hash + cur))
            idx //= 2
        return cur

    def build(self, extranonce_int, template=None, now=None):
        """One extranonce step. `template` may be a sibling
        job of the same family (same tx set and static
        fields, fresh time fields); its fingerprint must
        match the prepared one or TemplateError is raised,
        exactly as a stale cache must never silently serve
        a different template."""
        t = self.template if template is None else template
        if template is not None and \
                self._fingerprint(template) != self.fingerprint:
            raise TemplateError(
                "template does not match the prepared fingerprint")
        coinbase, cb_txid = build_coinbase(
            self.height, self.value, self.family.script,
            extranonce=struct.pack("<I", extranonce_int),
            flags_hex=self.flags_hex,
            witness_commitment=self.commitment)
        root = self.root_with_coinbase(cb_txid)
        if now is None:
            now = int(time.time())
        curtime = max(t.get("mintime", 0) + 1,
                      min(now, t.get("curtime", now)))
        header = (
            struct.pack("<i", t["version"])
            + bytes.fromhex(t["previousblockhash"])[::-1]
            + root
            + struct.pack("<I", curtime)
            + bytes.fromhex(t["bits"])[::-1]
            + struct.pack("<I", 0))
        body = self.body_head + coinbase + self.body_tail
        return {
            "header": header, "body": body,
            "target": self.target,
            "height": self.height, "fees": self.total_fees,
            "tx_count": 1 + len(self.txs_raw),
            "witness_count": self.witness_count,
        }


# ---------------------------------------------------------------------
# Shared test fixtures: a zero-latency counting stub RPC and
# synthetic GBT-shaped templates whose tx entries pass
# build_candidate's own re-verification (the EXP-009 pattern,
# with distinct transactions instead of one repeated tx).
# ---------------------------------------------------------------------

PAYOUT = "bc1q528egeqsvv8aa382j43edxskqw6x7zxc2xpcf3"
SPK = "0014" + "11" * 20  # stub scriptPubKey (form only)


class StubRPC:
    """Zero-latency counting RPC for construction timing."""

    def __init__(self, template=None):
        self.template = template
        self.counts = {}

    def call(self, method, *args):
        self.counts[method] = self.counts.get(method, 0) + 1
        if method == "getblocktemplate":
            return self.template
        if method == "validateaddress":
            return {"isvalid": True, "scriptPubKey": SPK}
        if method == "getblockchaininfo":
            return {"chain": "regtest"}
        if method == "submitblock":
            return None
        raise ValueError(method)

    def get_blockchain_info(self):
        return self.call("getblockchaininfo")

    def get_best_block_hash(self):
        return "00" * 32

    def with_timeout(self, _t):
        return self


def synth_tx(rng, segwit=False):
    """A minimal structurally valid transaction (one input,
    one output) that mining.engine.strip_witness parses."""
    prev = rng.randbytes(32)
    value = rng.randrange(1, 10 ** 8)
    script = b"\x76\xa9\x14" + rng.randbytes(20) + b"\x88\xac"
    vin = (prev + struct.pack("<I", rng.randrange(4))
           + b"\x00" + struct.pack("<I", 0xFFFFFFFE))
    vout = struct.pack("<Q", value) + bytes([len(script)]) + script
    if not segwit:
        return (struct.pack("<i", 1) + b"\x01" + vin + b"\x01" + vout
                + struct.pack("<I", 0))
    wit = rng.randbytes(20)
    return (struct.pack("<i", 2) + b"\x00\x01" + b"\x01" + vin
            + b"\x01" + vout
            + b"\x01" + bytes([len(wit)]) + wit
            + struct.pack("<I", 0))


def synth_template(rng, ntx, segwit_fraction=0.0, flags="",
                   with_commitment=False, height=1000,
                   curtime=1700000000):
    """A GBT-shaped template with distinct transactions.
    coinbasevalue is subsidy + fees for the stub regtest
    chain, as build_candidate requires."""
    txs = []
    total_fees = 0
    for _ in range(ntx):
        raw = synth_tx(rng, segwit=rng.random() < segwit_fraction)
        fee = rng.randrange(500, 5000)
        total_fees += fee
        txs.append({"txid": txid_of(raw)[::-1].hex(),
                    "data": raw.hex(), "fee": fee})
    template = {
        "version": 0x20000000,
        "previousblockhash": rng.randbytes(32).hex(),
        "transactions": txs,
        "coinbaseaux": {"flags": flags},
        "coinbasevalue": coinbase_subsidy(height, 150) + total_fees,
        "target": "7fffff0000000000000000000000000000000000000000"
                  "000000000000000000",
        "mintime": 1, "curtime": curtime,
        "bits": "207fffff", "height": height,
    }
    if with_commitment:
        wtxids = [wtxid_of(bytes.fromhex(tx["data"])) for tx in txs]
        wroot = merkle_root([ZERO32] + wtxids)
        commitment = dsha256(wroot + RESERVED_VALUE)
        template["default_witness_commitment"] = (
            "6a24aa21a9ed" + commitment.hex())
    return template
