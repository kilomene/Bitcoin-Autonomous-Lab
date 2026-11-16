#!/usr/bin/env python3
"""Independent Bitcoin block reconstruction and verification tool.

Stage 1 of the NOVA SHA-X Extreme Research mandate. This tool
reconstructs a block from its raw serialized bytes and verifies
every consensus-visible quantity independently of Bitcoin Core:

  1. Split the raw block into the 80-byte header and the
     transaction list (legacy and SegWit serializations).
  2. Decode all six header fields with byte order and width.
  3. Re-serialize the header from the decoded fields and check
     it is exactly 80 bytes and byte-identical to the raw slice.
  4. Compute SHA-256 and SHA-256d of the header with the pure
     Python reference implementation in this directory
     (sha256d_reference.py), cross-checked against hashlib.
  5. Confirm the block hash (reversed digest, hex) equals the
     hash Core reports.
  6. Decode the target from nBits with integer arithmetic only
     and verify hash <= target.
  7. Recompute every TXID (double SHA-256 of the non-witness
     serialization) and WTXID (double SHA-256 of the full
     serialization), rebuild the Merkle tree with odd-node
     duplication, and confirm the root equals the header field.
  8. If the block contains SegWit transactions, verify the
     witness commitment in the coinbase: SHA-256d of the witness
     Merkle root (coinbase leaf fixed at 0x00..00) concatenated
     with the coinbase witness reserved value must equal the
     32 bytes after the aa21a9ed header in the OP_RETURN output.

Sources of blocks:
  --genesis            construct the genesis block from the
                       Phase 001 constants and verify it.
  --file PATH          raw block hex read from a file.
  --mainnet-height H   fetch from the lab's pruned mainnet node
                       via bitcoin-cli (getblockhash, getblock 0).
  --regtest-height H   fetch from the lab's regtest datadir via
                       bitcoin-cli (the node must be running).

No RPC credential is read by this tool; bitcoin-cli reads its
own config file. Nothing here writes to any datadir.
"""

import hashlib
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sha256d_reference import sha256 as ref_sha256
from sha256d_reference import sha256d as ref_sha256d

BIN = "/home/hatch/workspace/bitcoin-core-dist/bitcoin-core-28.1/bin/bitcoin-cli"
MAINNET_DATADIR = ("/home/hatch/workspace/bitcoin-autonomous-lab"
                   "/.local/mainnet")
REGTEST_DATADIR = ("/home/hatch/workspace/bitcoin-autonomous-lab"
                   "/.local/regtest/data")


# ----------------------------------------------------------------
# Serialization primitives
# ----------------------------------------------------------------

class Reader:
    def __init__(self, data):
        self.d = data
        self.i = 0

    def read(self, n):
        out = self.d[self.i:self.i + n]
        if len(out) != n:
            raise ValueError("short read")
        self.i += n
        return out

    def u8(self):
        return self.read(1)[0]

    def u32(self):
        return struct.unpack("<I", self.read(4))[0]

    def u64(self):
        return struct.unpack("<Q", self.read(8))[0]

    def varint(self):
        b = self.u8()
        if b < 0xFD:
            return b
        if b == 0xFD:
            return struct.unpack("<H", self.read(2))[0]
        if b == 0xFE:
            return struct.unpack("<I", self.read(4))[0]
        return struct.unpack("<Q", self.read(8))[0]

    def varbytes(self):
        return self.read(self.varint())


def dsha(data):
    """Double SHA-256 via the reference implementation."""
    return ref_sha256d(data)


def display_hash(digest):
    """Internal byte order digest to display hex (reversed)."""
    return digest[::-1].hex()


# ----------------------------------------------------------------
# Transaction parsing
# ----------------------------------------------------------------

def parse_tx(raw, off):
    """Parse one transaction starting at offset off in raw.
    Returns (tx_dict, next_offset). The dict carries the stripped
    (non-witness) serialization, the full serialization, the
    TXID, the WTXID, output scripts and, for a SegWit coinbase,
    the witness reserved value."""
    start = off
    r = Reader(raw)
    r.i = off
    version = r.u32()
    segwit = False
    if raw[r.i] == 0x00 and raw[r.i + 1] != 0x00:
        segwit = True
        r.i += 2  # marker 0x00, flag 0x01
    n_in = r.varint()
    inputs = []
    for _ in range(n_in):
        prev = r.read(32)
        prev_idx = r.u32()
        script = r.varbytes()
        seq = r.u32()
        inputs.append((prev, prev_idx, script, seq))
    n_out = r.varint()
    outputs = []
    for _ in range(n_out):
        value = r.u64()
        script = r.varbytes()
        outputs.append((value, script))
    witnesses = []
    if segwit:
        for _ in range(n_in):
            n_stack = r.varint()
            stack = [r.varbytes() for _ in range(n_stack)]
            witnesses.append(stack)
    locktime = r.u32()
    end = r.i
    full = raw[start:end]
    if segwit:
        # Rebuild the stripped serialization: version, inputs,
        # outputs, locktime, with no marker, flag or witness.
        buf = bytearray()
        buf += struct.pack("<I", version)
        buf += _varint(n_in)
        for prev, prev_idx, script, seq in inputs:
            buf += prev
            buf += struct.pack("<I", prev_idx)
            buf += _varint(len(script)) + script
            buf += struct.pack("<I", seq)
        buf += _varint(n_out)
        for value, script in outputs:
            buf += struct.pack("<Q", value)
            buf += _varint(len(script)) + script
        buf += struct.pack("<I", locktime)
        stripped = bytes(buf)
    else:
        stripped = full
    is_coinbase = (n_in == 1 and inputs[0][0] == b"\x00" * 32
                   and inputs[0][1] == 0xFFFFFFFF)
    tx = {
        "version": version,
        "segwit": segwit,
        "inputs": inputs,
        "outputs": outputs,
        "witnesses": witnesses,
        "locktime": locktime,
        "stripped": stripped,
        "full": full,
        "txid": dsha(stripped),
        "wtxid": dsha(full),
        "is_coinbase": is_coinbase,
    }
    return tx, end


def _varint(n):
    if n < 0xFD:
        return bytes([n])
    if n <= 0xFFFF:
        return b"\xfd" + struct.pack("<H", n)
    if n <= 0xFFFFFFFF:
        return b"\xfe" + struct.pack("<I", n)
    return b"\xff" + struct.pack("<Q", n)


def merkle_root(leaves):
    """Merkle root over 32-byte internal-order leaf digests,
    with odd-node duplication (the last node is paired with
    itself)."""
    if not leaves:
        raise ValueError("no leaves")
    level = list(leaves)
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        level = [dsha(level[i] + level[i + 1])
                 for i in range(0, len(level), 2)]
    return level[0]


# ----------------------------------------------------------------
# Header decoding
# ----------------------------------------------------------------

def decode_header(header):
    if len(header) != 80:
        raise ValueError("header must be exactly 80 bytes")
    return {
        "version": struct.unpack("<i", header[0:4])[0],
        "version_u32": struct.unpack("<I", header[0:4])[0],
        "prev_hash": header[4:36],
        "merkle_root": header[36:68],
        "time": struct.unpack("<I", header[68:72])[0],
        "bits": struct.unpack("<I", header[72:76])[0],
        "nonce": struct.unpack("<I", header[76:80])[0],
    }


def serialize_header(f):
    out = struct.pack("<I", f["version_u32"])
    out += f["prev_hash"]
    out += f["merkle_root"]
    out += struct.pack("<I", f["time"])
    out += struct.pack("<I", f["bits"])
    out += struct.pack("<I", f["nonce"])
    return out


def target_from_bits(bits):
    """Core SetCompact semantics, integer arithmetic only.
    Returns the target as a non-negative integer. (For valid
    chain blocks the sign bit is never set; the nBits-equality
    gate in block acceptance is what enforces that, per the
    Phase 001 and EXP-036 records.)"""
    exponent = bits >> 24
    mantissa = bits & 0x007FFFFF
    if bits & 0x00800000:
        raise ValueError("negative target encoding")
    if exponent <= 3:
        return mantissa >> (8 * (3 - exponent))
    return mantissa << (8 * (exponent - 3))


# ----------------------------------------------------------------
# Block analysis
# ----------------------------------------------------------------

def analyze_block(raw, label, expect_hash=None):
    checks = []

    def check(name, ok, detail=""):
        checks.append((name, bool(ok), detail))
        return ok

    header = raw[:80]
    f = decode_header(header)
    r = Reader(raw)
    r.i = 80
    n_tx = r.varint()
    txs = []
    off = r.i
    for _ in range(n_tx):
        tx, off = parse_tx(raw, off)
        txs.append(tx)
    check("raw block fully consumed", off == len(raw),
          "%d of %d bytes" % (off, len(raw)))
    check("transaction count", len(txs) == n_tx, str(n_tx))

    reser = serialize_header(f)
    check("header re-serialized is exactly 80 bytes",
          len(reser) == 80)
    check("header re-serialization byte-identical", reser == header)

    single = ref_sha256(header)
    digest = ref_sha256d(header)
    check("reference SHA-256d agrees with hashlib",
          digest == hashlib.sha256(hashlib.sha256(header).digest()).digest())
    block_hash = display_hash(digest)
    if expect_hash is not None:
        check("block hash matches Core", block_hash == expect_hash,
              block_hash)
    hash_int = int.from_bytes(digest, "little")
    target = target_from_bits(f["bits"])
    check("hash <= target (integer comparison)", hash_int <= target,
          "hash %064x target %064x" % (hash_int, target))

    txids = [t["txid"] for t in txs]
    root = merkle_root(txids)
    check("recomputed Merkle root matches header field",
          root == f["merkle_root"], display_hash(root))

    segwit_txs = [t for t in txs if t["segwit"]]
    wit = {"present": False, "verified": None}
    if segwit_txs:
        wit["present"] = True
        cb = txs[0]
        commitment = None
        for _value, script in cb["outputs"]:
            if (len(script) == 38 and script[0] == 0x6A
                    and script[1] == 0x24
                    and script[2:6] == bytes.fromhex("aa21a9ed")):
                commitment = script[6:38]
        reserved = None
        if cb["witnesses"] and cb["witnesses"][0]:
            reserved = cb["witnesses"][0][0]
        if commitment is not None and reserved is not None:
            wleaves = [b"\x00" * 32] + [t["wtxid"] for t in txs[1:]]
            wroot = merkle_root(wleaves)
            expect = dsha(wroot + reserved)
            wit["verified"] = (expect == commitment)
            wit["witness_root"] = display_hash(wroot)
            wit["reserved_value"] = reserved.hex()
            wit["commitment"] = commitment.hex()
            check("witness commitment verified", wit["verified"])
        else:
            check("witness commitment located", False,
                  "commitment or reserved value missing")

    print("=== %s ===" % label)
    print("raw block bytes: %d" % len(raw))
    print("transactions: %d (segwit: %d)" % (n_tx, len(segwit_txs)))
    print("header hex: %s" % header.hex())
    print("  version: %d (u32 0x%08x, 4 bytes LE)"
          % (f["version"], f["version_u32"]))
    print("  prev_hash: %s (32 bytes, internal order; display reversed)"
          % display_hash(f["prev_hash"]))
    print("  merkle_root: %s (32 bytes, internal order; display reversed)"
          % display_hash(f["merkle_root"]))
    print("  time: %d (4 bytes LE)" % f["time"])
    print("  bits: 0x%08x (4 bytes LE)" % f["bits"])
    print("  nonce: %d (4 bytes LE)" % f["nonce"])
    print("sha256(header), reference: %s" % single.hex())
    print("sha256d(header), reference: %s" % digest.hex())
    print("block hash (display): %s" % block_hash)
    print("coinbase txid (display): %s" % display_hash(txs[0]["txid"]))
    if wit["present"]:
        print("witness commitment: %s" % wit.get("commitment"))
        print("witness merkle root (display): %s"
              % wit.get("witness_root"))
    failed = 0
    for name, ok, detail in checks:
        print("  [%s] %s %s" % ("PASS" if ok else "FAIL", name,
                                ("- " + detail) if detail else ""))
        failed += 0 if ok else 1
    print("RESULT: %s (%d checks, %d failed)"
          % ("ALL PASS" if failed == 0 else "FAILURES", len(checks),
             failed))
    print()
    return failed == 0


# ----------------------------------------------------------------
# Genesis block, from the Phase 001 record
# ----------------------------------------------------------------

GENESIS_TIME_TEXT = (b"The Times 03/Jan/2009 Chancellor on brink of "
                     b"second bailout for banks")
GENESIS_PUBKEY = bytes.fromhex(
    "04678afdb0fe5548271967f1a67130b7105cd6a828e03909a67962e0ea1f61deb"
    "649f6bc3f4cef38c4f35504e51ec112de5c384df7ba0b8d578a4c702b6bf11d5f")
GENESIS_HASH = ("000000000019d6689c085ae165831e934ff763ae46a2a6c172b3"
                "f1b60a8ce26f")


def genesis_block_raw():
    """Construct the genesis block exactly as Phase 001 recorded
    it (research/phase001/COINBASE_MERKLE_ANALYSIS.md section
    1.3): scriptSig = push(486604799 as 4-byte CBigNum) +
    push(CBigNum(4)) + push(69-byte headline); one output of
    50 * COIN to the genesis public key with OP_CHECKSIG."""
    scriptsig = (b"\x04" + bytes.fromhex("ffff001d")
                 + b"\x01\x04"
                 + bytes([len(GENESIS_TIME_TEXT)]) + GENESIS_TIME_TEXT)
    scriptpub = b"\x41" + GENESIS_PUBKEY + b"\xac"
    tx = bytearray()
    tx += struct.pack("<I", 1)                    # version
    tx += b"\x01"                                 # 1 input
    tx += b"\x00" * 32                            # null prevout hash
    tx += struct.pack("<I", 0xFFFFFFFF)           # prevout index
    tx += bytes([len(scriptsig)]) + scriptsig
    tx += struct.pack("<I", 0xFFFFFFFF)           # sequence
    tx += b"\x01"                                 # 1 output
    tx += struct.pack("<Q", 5000000000)           # 50 * COIN
    tx += bytes([len(scriptpub)]) + scriptpub
    tx += struct.pack("<I", 0)                    # locktime
    txid = dsha(bytes(tx))
    header = (struct.pack("<I", 1) + b"\x00" * 32 + txid
              + struct.pack("<I", 1231006505)
              + struct.pack("<I", 0x1D00FFFF)
              + struct.pack("<I", 2083236893))
    return header + b"\x01" + bytes(tx)


# ----------------------------------------------------------------
# Fetching from the lab nodes
# ----------------------------------------------------------------

def cli(datadir, *args):
    cmd = [BIN, "-datadir=" + datadir] + list(args)
    out = subprocess.run(cmd, capture_output=True, text=True,
                         timeout=120)
    if out.returncode != 0:
        raise RuntimeError("bitcoin-cli failed: " + out.stderr.strip())
    return out.stdout.strip()


def fetch_mainnet(height):
    h = cli(MAINNET_DATADIR, "getblockhash", str(height))
    raw = bytes.fromhex(cli(MAINNET_DATADIR, "getblock", h, "0"))
    return raw, h


def fetch_regtest(height):
    h = cli(REGTEST_DATADIR, "getblockhash", str(height))
    raw = bytes.fromhex(cli(REGTEST_DATADIR, "getblock", h, "0"))
    return raw, h


def main(argv):
    ok = True
    if "--genesis" in argv:
        raw = genesis_block_raw()
        ok = analyze_block(raw, "genesis block (Phase 001 constants)",
                           expect_hash=GENESIS_HASH) and ok
    if "--file" in argv:
        path = argv[argv.index("--file") + 1]
        with open(path) as fh:
            raw = bytes.fromhex(fh.read().strip())
        expect = None
        if "--expect-hash" in argv:
            expect = argv[argv.index("--expect-hash") + 1]
        ok = analyze_block(raw, "block from file " + path,
                           expect_hash=expect) and ok
    if "--mainnet-height" in argv:
        h = int(argv[argv.index("--mainnet-height") + 1])
        raw, bhash = fetch_mainnet(h)
        ok = analyze_block(raw, "mainnet height %d" % h,
                           expect_hash=bhash) and ok
    if "--regtest-height" in argv:
        h = int(argv[argv.index("--regtest-height") + 1])
        raw, bhash = fetch_regtest(h)
        ok = analyze_block(raw, "regtest height %d" % h,
                           expect_hash=bhash) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
