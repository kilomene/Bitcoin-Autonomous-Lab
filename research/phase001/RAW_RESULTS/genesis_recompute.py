#!/usr/bin/env python3
"""Independent recomputation of the Bitcoin genesis block hash using ONLY the
constants found in the v0.1.3 source (src/main.cpp, LoadBlockIndex).
This is OUR recomputation (hashlib), not a build of the original code.
It parses pszTimestamp and the scriptPubKey CBigNum constant directly out of
main.cpp so the inputs are the source's own constants."""
import hashlib, re, struct, sys

SRC = "/home/hatch/workspace/bitcoin-autonomous-lab/.local/refs-genesis/extracted/sni_rar/src/main.cpp"
text = open(SRC, encoding="utf-8", errors="replace").read()

ts = re.search(r'pszTimestamp = "([^"]+)"', text).group(1)
bn_hex = re.search(r'scriptPubKey = CScript\(\) << CBigNum\("(0x[0-9A-F]+)"\)', text).group(1)[2:]
n_time = int(re.search(r'block\.nTime\s+= (\d+);', text).group(1))
n_bits = int(re.search(r'block\.nBits\s+= (0x[0-9a-f]+);', text).group(1), 16)
n_nonce = int(re.search(r'block\.nNonce\s+= (\d+);', text).group(1))
n_version = int(re.search(r'block\.nVersion = (\d+);', text).group(1))
asserted_merkle = re.search(r'assert\(block\.hashMerkleRoot == uint256\("0x([0-9a-f]+)"\)\)', text).group(1)
asserted_genesis = re.search(r'hashGenesisBlock\("0x([0-9a-f]+)"\)', text).group(1)

def dsha(b): return hashlib.sha256(hashlib.sha256(b).digest()).digest()

def bignum_push(v):
    # CBigNum byte vector: little-endian magnitude, extra 0x00 if top bit set
    if v == 0: return b""
    b = v.to_bytes((v.bit_length() + 7) // 8, "little")
    if b[-1] & 0x80: b += b"\x00"
    return b

def push(data): return bytes([len(data)]) + data

# scriptSig = CScript() << 486604799 << CBigNum(4) << timestamp bytes
script_sig = push(bignum_push(486604799)) + push(bignum_push(4)) + push(ts.encode())
# scriptPubKey = CScript() << CBigNum(0x...) << OP_CHECKSIG
# CBigNum hex string is parsed big-endian into the number; getvch() returns the
# little-endian byte vector, which is what CScript pushes.
pubkey = bytes.fromhex(bn_hex)[::-1]
script_pubkey = push(pubkey) + b"\xac"  # OP_CHECKSIG

def varint(n): return bytes([n]) if n < 0xfd else b"\xfd" + struct.pack("<H", n)

tx = struct.pack("<i", 1)                       # nVersion = 1
tx += varint(1)                                 # vin count
tx += b"\x00" * 32 + struct.pack("<I", 0xffffffff)  # null prevout
tx += varint(len(script_sig)) + script_sig
tx += struct.pack("<I", 0xffffffff)             # nSequence
tx += varint(1)                                 # vout count
tx += struct.pack("<q", 50 * 100000000)         # 50 * COIN
tx += varint(len(script_pubkey)) + script_pubkey
tx += struct.pack("<I", 0)                      # nLockTime

merkle_internal = dsha(tx)                      # single tx: root = tx hash
merkle_display = merkle_internal[::-1].hex()

header = struct.pack("<i", n_version) + b"\x00" * 32 + merkle_internal
header += struct.pack("<III", n_time, n_bits, n_nonce)
genesis_internal = dsha(header)
genesis_display = genesis_internal[::-1].hex()

print(f"pszTimestamp (main.cpp): {ts!r} ({len(ts)} chars)")
print(f"scriptSig ({len(script_sig)} bytes): {script_sig.hex()}")
print(f"pubkey ({len(pubkey)} bytes): {pubkey.hex()}")
print(f"tx ({len(tx)} bytes) sha256d display: {dsha(tx)[::-1].hex()}")
print(f"merkle recomputed : {merkle_display}")
print(f"merkle in source  : {asserted_merkle}  MATCH={merkle_display == asserted_merkle}")
print(f"header ({len(header)} bytes): {header.hex()}")
print(f"genesis recomputed: {genesis_display}")
print(f"genesis in source : {asserted_genesis}  MATCH={genesis_display == asserted_genesis}")
print(f"nTime={n_time} nBits=0x{n_bits:08x} nNonce={n_nonce} nVersion={n_version}")
sys.exit(0 if (merkle_display == asserted_merkle and genesis_display == asserted_genesis) else 1)
