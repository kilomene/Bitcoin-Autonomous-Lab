#!/usr/bin/env python3
"""EXP-025 repaired two-level candidate cache.

A research prototype that repairs the EXP-023 cache
identity (phase6/benchmarks/exp023_amortized.py, left
byte-identical as the historical record) after the
EXP-025 defect demonstration showed its 8-field
fingerprint silently serving stale candidates.

Design: a deterministic LAYERED identity. Every cached
object belongs to exactly one layer, and each layer's
key is a double SHA-256 over the COMPLETE dependency
set of that layer's objects (see
EXP025_CACHE_CORRECTNESS.md for the dependency matrix
this was derived from):

  family_key   payout address, payout scriptPubKey,
               chain, halving interval.
  tx_key       transaction count, and for every
               transaction IN ORDER: its txid (internal
               byte order), its wtxid, its fee; plus the
               template's default_witness_commitment
               string (a validation input: any change to
               it must force revalidation, so it is keyed
               even though it is not itself cached data).
  coinbase_key family_key, height, coinbasevalue,
               coinbaseaux flags, witness commitment
               (or an explicit none marker).
  header_key   version, previousblockhash, bits,
               target.

  identity = dsha256(tx_key || coinbase_key ||
             header_key)

Completeness argument: every byte of every cached
object is a deterministic function of the inputs
hashed into its layer key (raw transaction bytes enter
through their wtxid, which is dsha256 of the full
serialisation, and through the verified txid, which is
dsha256 of the stripped serialisation). The identity
is therefore exact up to SHA-256 collision resistance,
the same assumption Bitcoin itself places on txids.
Any input change changes the identity; build() with a
sibling template recomputes the sibling's identity
from scratch (full re-derivation, including the txid
re-verification and the coinbasevalue check the
production path performs) and raises TemplateError on
any mismatch. It never silently serves.

Deliberately NOT in any key: mintime and curtime.
Production build_candidate reads them fresh from the
passed template on every call; no cached object
depends on them; the header time is assembled per
build from the passed template exactly as production
does. The extranonce is likewise a per-build input,
never cached.

The identity recomputation is the honest cost of the
repair and is measured separately in
exp025_paired_bench.py: it re-derives every txid and
wtxid of the sibling template. What the cache still
saves per step is the Merkle tree construction, the
witness commitment tree, the body assembly, the value
and subsidy accounting, and the two RPC round trips.

Nothing here touches production code. Builds are
gated byte-identical to mining.engine
MiningEngine.build_candidate in exp025_gates.py.
"""
import struct
import sys
import time

ROOT = "/home/hatch/workspace/bitcoin-autonomous-lab"
sys.path.insert(0, ROOT)
sys.path.insert(0, ROOT + "/research/sha256d/phase6/benchmarks")

from exp023_amortized import PAYOUT, StubRPC, synth_template  # noqa: E402,F401
from mining.engine import (RESERVED_VALUE, TemplateError,  # noqa: E402
                           address_script_pubkey, build_coinbase,
                           encode_varint, txid_of, wtxid_of)
from mining.pow import coinbase_subsidy, dsha256, merkle_root  # noqa: E402

ZERO32 = b"\x00" * 32


def _lp(data):
    """Length-prefixed bytes, for unambiguous key material."""
    return struct.pack("<Q", len(data)) + data


class RepairedFamily:
    """Level 1: constants shared by every template a node
    serves to one payout address, keyed by everything
    they depend on."""

    def __init__(self, rpc, payout_address):
        self.rpc = rpc
        self.payout = payout_address
        self.script = address_script_pubkey(rpc, payout_address)
        self.chain = rpc.get_blockchain_info()["chain"]
        self.interval = 150 if self.chain == "regtest" else 210000
        self.family_key = dsha256(
            b"exp025/family/v1"
            + _lp(payout_address.encode())
            + _lp(self.script)
            + _lp(self.chain.encode())
            + struct.pack("<Q", self.interval))


def derive_tx_pass(template):
    """The full transaction pass, mirroring
    MiningEngine.build_candidate's checks exactly.
    Returns (txs_raw, txids, wtxids, total_fees,
    witness_count, commitment). Raises TemplateError on
    any inconsistency the production path would raise."""
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
            raise TemplateError(
                "witness commitment disagrees with Core")
    return (txs_raw, txids, wtxids, total_fees, witness_count,
            commitment)


def tx_layer_key(template, txids, wtxids, fees):
    parts = [b"exp025/tx/v1", encode_varint(len(txids))]
    for txid, wtxid, fee in zip(txids, wtxids, fees):
        parts.append(txid)
        parts.append(wtxid)
        parts.append(struct.pack("<q", fee))
    dwc = template.get("default_witness_commitment")
    parts.append(_lp(dwc.encode() if dwc else b""))
    return dsha256(b"".join(parts))


def coinbase_layer_key(family, template, commitment):
    flags = template.get("coinbaseaux", {}).get("flags", "")
    return dsha256(
        b"exp025/coinbase/v1"
        + family.family_key
        + struct.pack("<Q", template["height"])
        + struct.pack("<q", template["coinbasevalue"])
        + _lp(bytes.fromhex(flags) if flags else b"")
        + (commitment if commitment is not None else b"\x00" * 32)
        + (b"\x01" if commitment is not None else b"\x00"))


def header_layer_key(template):
    return dsha256(
        b"exp025/header/v1"
        + struct.pack("<i", template["version"])
        + bytes.fromhex(template["previousblockhash"])
        + bytes.fromhex(template["bits"])
        + template["target"].encode())


def identity_of(family, template):
    """Recompute a template's full layered identity from
    scratch, performing every validation the production
    construction performs on the identity inputs (txid
    re-verification, witness commitment cross-check,
    coinbasevalue equals subsidy plus fees). Returns
    (identity, tx_key, coinbase_key, header_key,
    derived) where derived is the derive_tx_pass tuple.
    Raises TemplateError exactly where production
    would."""
    derived = derive_tx_pass(template)
    txs_raw, txids, wtxids, total_fees, witness_count, \
        commitment = derived
    fees = [tx.get("fee", 0)
            for tx in template.get("transactions", [])]
    subsidy = coinbase_subsidy(template["height"], family.interval)
    if template["coinbasevalue"] != subsidy + total_fees:
        raise TemplateError(
            f"coinbasevalue {template['coinbasevalue']} != subsidy "
            f"{subsidy} + fees {total_fees}")
    tx_key = tx_layer_key(template, txids, wtxids, fees)
    cb_key = coinbase_layer_key(family, template, commitment)
    hd_key = header_layer_key(template)
    identity = dsha256(tx_key + cb_key + hd_key)
    return identity, tx_key, cb_key, hd_key, derived


class RepairedTemplate:
    """Level 2: one template's extranonce-independent
    work, paid once, served only under its full layered
    identity."""

    def __init__(self, family, template):
        self.family = family
        (identity, tx_key, cb_key, hd_key, derived) = \
            identity_of(family, template)
        (txs_raw, txids, wtxids, total_fees, witness_count,
         commitment) = derived
        self.identity = identity
        self.tx_key = tx_key
        self.coinbase_key = cb_key
        self.header_key = hd_key
        self.template = template
        self.txs_raw = txs_raw
        self.txids = txids
        self.total_fees = total_fees
        self.witness_count = witness_count
        self.commitment = commitment
        self.value = template["coinbasevalue"]
        self.flags_hex = template.get("coinbaseaux", {}).get(
            "flags", "")
        self.target = int(template["target"], 16)
        self.height = template["height"]
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

    def root_with_coinbase(self, cb_txid):
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
        """One extranonce step. A sibling template is
        served ONLY if its freshly recomputed full
        layered identity equals the prepared identity;
        any other sibling raises TemplateError. Time
        fields are read from the sibling per build,
        exactly as production reads them."""
        t = self.template if template is None else template
        if template is not None:
            sibling_identity = identity_of(self.family,
                                           template)[0]
            if sibling_identity != self.identity:
                raise TemplateError(
                    "template identity mismatch: refusing to "
                    "serve a sibling under a different layered "
                    "identity")
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


class TemplateCache:
    """Identity-keyed template store with reuse counters,
    so tests can assert that reuse actually happened (and
    only under an identical identity)."""

    def __init__(self):
        self.by_identity = {}
        self.prepares = 0
        self.hits = 0
        self.identity_checks = 0

    def get(self, family, template):
        identity = identity_of(family, template)[0]
        self.identity_checks += 1
        key = (family.family_key, identity)
        if key in self.by_identity:
            self.hits += 1
            return self.by_identity[key], True
        prep = RepairedTemplate(family, template)
        assert prep.identity == identity
        self.by_identity[key] = prep
        self.prepares += 1
        return prep, False
