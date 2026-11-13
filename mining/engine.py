"""Tasks 005/006: autonomous mining engine.

Obtains real mining work with getblocktemplate, constructs candidate
blocks (BIP34 coinbase, BIP141 witness commitment, merkle root, exact
fee accounting), searches nonces through the ComputeEngine (CUDA when
a real device exists, CPU otherwise, every candidate CPU verified),
submits with submitblock, and counts a block as mined only when the
node has it on the active chain as its best block.

generatetoaddress is never used here. Template transactions are
re-parsed and their txids (and wtxids) recomputed; a mismatch rejects
the template. The engine is chain-agnostic at this layer; the
autonomous agent enforces the regtest-only default.
"""

import logging
import struct
import time

from blockchain.transactions import btc_to_sats
from gpu.engine import ComputeEngine
from mining.pow import coinbase_subsidy, merkle_root, dsha256

log = logging.getLogger("bal.mining.engine")

WITNESS_COMMITMENT_HEADER = bytes.fromhex("aa21a9ed")
RESERVED_VALUE = b"\x00" * 32


def encode_varint(n):
    if n < 0xFD:
        return bytes([n])
    if n <= 0xFFFF:
        return b"\xfd" + struct.pack("<H", n)
    if n <= 0xFFFFFFFF:
        return b"\xfe" + struct.pack("<I", n)
    return b"\xff" + struct.pack("<Q", n)


def push_data(data):
    if len(data) < 0x4C:
        return bytes([len(data)]) + data
    if len(data) <= 0xFF:
        return b"\x4c" + bytes([len(data)]) + data
    raise ValueError("push too large")


def script_num_push(value):
    """CScript push of a small integer, as Core encodes block height."""
    if value == 0:
        return b"\x00"
    neg = value < 0
    absval = -value if neg else value
    out = bytearray()
    while absval:
        out.append(absval & 0xFF)
        absval >>= 8
    if out[-1] & 0x80:
        out.append(0x80 if neg else 0x00)
    elif neg:
        out[-1] |= 0x80
    return push_data(bytes(out))


def address_script_pubkey(rpc, address):
    info = rpc.call("validateaddress", address)
    if not info.get("isvalid"):
        raise ValueError(f"invalid payout address: {address}")
    return bytes.fromhex(info["scriptPubKey"])


def strip_witness(raw):
    """Return (stripped_bytes, has_witness) for a raw transaction."""
    if len(raw) >= 6 and raw[4] == 0 and raw[5] == 1:
        # marker 0x00, flag 0x01 after the 4-byte version
        pos = 6
        def read_varint(p):
            first = raw[p]
            if first < 0xFD:
                return first, p + 1
            if first == 0xFD:
                return struct.unpack("<H", raw[p + 1:p + 3])[0], p + 3
            if first == 0xFE:
                return struct.unpack("<I", raw[p + 1:p + 5])[0], p + 5
            return struct.unpack("<Q", raw[p + 1:p + 9])[0], p + 9
        vin_count, pos = read_varint(pos)
        vin_start = pos
        for _ in range(vin_count):
            pos += 36
            slen, pos = read_varint(pos)
            pos += slen + 4
        vin_end = pos
        vout_count, pos = read_varint(pos)
        for _ in range(vout_count):
            pos += 8
            slen, pos = read_varint(pos)
            pos += slen
        vout_end = pos
        # version + (vin and vout, which sit between the marker and
        # the witness data) + locktime; witness bytes live between
        # vout_end and the final 4 locktime bytes.
        stripped = raw[:4] + raw[6:vout_end] + raw[-4:]
        return stripped, True
    return raw, False


def txid_of(raw):
    stripped, _ = strip_witness(raw)
    return dsha256(stripped)


def wtxid_of(raw):
    return dsha256(raw)


def build_coinbase(height, value_sats, script_pubkey, extranonce=b"",
                   flags_hex="", witness_commitment=None):
    """Returns (full_bytes, txid_internal_order)."""
    script_sig = script_num_push(height) + b"/BAL/" + extranonce
    if flags_hex:
        script_sig += bytes.fromhex(flags_hex)
    if not (2 <= len(script_sig) <= 100):
        raise ValueError(f"coinbase scriptSig length {len(script_sig)}")
    vin = (b"\x00" * 32 + struct.pack("<I", 0xFFFFFFFF)
           + encode_varint(len(script_sig)) + script_sig
           + struct.pack("<I", 0xFFFFFFFF))
    outputs = [(value_sats, script_pubkey)]
    if witness_commitment is not None:
        commit_script = b"\x6a" + push_data(
            WITNESS_COMMITMENT_HEADER + witness_commitment)
        outputs.append((0, commit_script))
    vout = encode_varint(len(outputs))
    for value, script in outputs:
        vout += struct.pack("<Q", value) + encode_varint(len(script)) + script
    version = struct.pack("<i", 2)
    locktime = struct.pack("<I", 0)
    stripped = version + encode_varint(1) + vin + vout + locktime
    if witness_commitment is None:
        return stripped, dsha256(stripped)
    witness = encode_varint(1) + encode_varint(32) + RESERVED_VALUE
    full = version + b"\x00\x01" + encode_varint(1) + vin + vout \
        + witness + locktime
    return full, dsha256(stripped)


class TemplateError(Exception):
    pass


class MiningEngine:
    def __init__(self, rpc, payout_address, compute=None, batch_size=65536):
        self.rpc = rpc
        self.payout = payout_address
        self.compute = compute or ComputeEngine()
        self.batch_size = batch_size

    def get_template(self):
        return self.rpc.call("getblocktemplate", {"rules": ["segwit"]})

    def build_candidate(self, template, extranonce_int=0):
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
            wroot = merkle_root([b"\x00" * 32] + wtxids)
            commitment = dsha256(wroot + RESERVED_VALUE)
            expected = template.get("default_witness_commitment")
            if expected and commitment.hex() not in expected:
                raise TemplateError("witness commitment disagrees with Core")
        # Subsidy schedule is chain specific: regtest halves every
        # 150 blocks, mainnet and the public testnets every 210000.
        chain = self.rpc.get_blockchain_info()["chain"]
        interval = 150 if chain == "regtest" else 210000
        subsidy = coinbase_subsidy(template["height"], interval)
        value = template["coinbasevalue"]
        if value != subsidy + total_fees:
            raise TemplateError(
                f"coinbasevalue {value} != subsidy {subsidy} + fees "
                f"{total_fees}")
        script = address_script_pubkey(self.rpc, self.payout)
        coinbase, cb_txid = build_coinbase(
            template["height"], value, script,
            extranonce=struct.pack("<I", extranonce_int),
            flags_hex=template.get("coinbaseaux", {}).get("flags", ""),
            witness_commitment=commitment)
        root = merkle_root([cb_txid] + txids)
        now = int(time.time())
        curtime = max(template.get("mintime", 0) + 1,
                      min(now, template.get("curtime", now)))
        header = (
            struct.pack("<i", template["version"])
            + bytes.fromhex(template["previousblockhash"])[::-1]
            + root
            + struct.pack("<I", curtime)
            + bytes.fromhex(template["bits"])[::-1]
            + struct.pack("<I", 0))
        block_body = encode_varint(1 + len(txs_raw)) + coinbase \
            + b"".join(txs_raw)
        return {
            "header": header, "body": block_body,
            "target": int(template["target"], 16),
            "height": template["height"], "fees": total_fees,
            "tx_count": 1 + len(txs_raw), "witness_count": witness_count,
        }

    def mine_cycle(self, max_batches=200, deadline_seconds=120):
        """One full cycle. Returns a result dict; accepted means the
        block was submitted and is the node's best block."""
        template = self.get_template()
        started = time.time()
        total_hashes = 0
        batches = 0
        for extranonce in range(64):
            cand = self.build_candidate(template, extranonce)
            start = 0
            while start < (1 << 32):
                if time.time() - started > deadline_seconds or batches >= max_batches:
                    return {"accepted": False, "reason": "budget exhausted",
                            "height": cand["height"], "hashes": total_hashes,
                            "batches": batches,
                            "backend": self.compute.backend}
                found, stats = self.compute.batch_search(
                    cand["header"], cand["target"], start, self.batch_size)
                total_hashes += stats["hashes"]
                batches += 1
                if found:
                    sol = found[0]
                    header = cand["header"][:76] + struct.pack(
                        "<I", sol["nonce"])
                    block = header + cand["body"]
                    block_hash = dsha256(header)[::-1].hex()
                    submit = self.rpc.call("submitblock", block.hex())
                    best = self.rpc.get_best_block_hash()
                    accepted = (submit is None and best == block_hash)
                    return {
                        "accepted": accepted,
                        "submit_result": submit,
                        "height": cand["height"], "hash": block_hash,
                        "nonce": sol["nonce"], "hashes": total_hashes,
                        "batches": batches, "extranonce_rounds": extranonce + 1,
                        "backend": stats["backend"],
                        "seconds": time.time() - started,
                        "hashrate": total_hashes / max(time.time() - started, 1e-9),
                        "tx_count": cand["tx_count"], "fees": cand["fees"],
                    }
                start += self.batch_size
        return {"accepted": False, "reason": "nonce space exhausted",
                "height": template["height"], "hashes": total_hashes,
                "batches": batches, "backend": self.compute.backend}
