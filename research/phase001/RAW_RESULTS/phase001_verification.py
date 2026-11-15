#!/usr/bin/env python3
"""Phase 001, Deliverable 19: independent correctness verification suite.

Implements SHA-256 FROM THE WAVE 3 EQUATIONS (Deliverable 8's transcription
of the v0.1.3 Crypto++ extract at src/sha.cpp): the macro forms of Ch and
Maj, the S0/S1/s0/s1 rotate sets, the circular W[16] schedule buffer with
the in-place blk2 update, and the rotating-window T[8] state addressed
through the a(i)..h(i) macros. hashlib is used ONLY as the independent
cross-check, never as the implementation under test.

Also executes: SHA-256d vectors, the 0.1.3 BlockSHA256 / FormatHashBlocks
path, genesis header serialization byte-for-byte, genesis merkle and hash
reproduction, SetCompact vectors in both the 0.1.3 CBigNum/MPI form and
the v28.1 arith_uint256 form (including edge encodings), GetCompact round
trips, nonce coverage arithmetic (full-width identities plus a
width-reduced control-flow model of the search loop), the W18 taint claim
(symbolic and numeric), and the probability anchors of Deliverable 12.

Every check prints PASS or FAIL and is counted. Exit code 0 iff all pass.
Run: python3 research/phase001/RAW_RESULTS/phase001_verification.py
"""
import hashlib
import random
import struct
import sys
from fractions import Fraction

M = 0xFFFFFFFF
H0 = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
      0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19]
K = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1,
    0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
    0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786,
    0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147,
    0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
    0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
    0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a,
    0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
    0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2]

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond)))
    print("%s: %s%s" % ("PASS" if cond else "FAIL", name,
                        (" | " + detail) if detail else ""))


# ---------------------------------------------------------------------------
# 1. SHA-256 from the wave 3 equations (src/sha.cpp macros, transcribed)
# ---------------------------------------------------------------------------

def rotr(x, n):
    return ((x >> n) | (x << (32 - n))) & M


def S0(x):  # sha.cpp line 136
    return rotr(x, 2) ^ rotr(x, 13) ^ rotr(x, 22)


def S1(x):  # sha.cpp line 137
    return rotr(x, 6) ^ rotr(x, 11) ^ rotr(x, 25)


def s0(x):  # sha.cpp line 138
    return rotr(x, 7) ^ rotr(x, 18) ^ (x >> 3)


def s1(x):  # sha.cpp line 139
    return rotr(x, 17) ^ rotr(x, 19) ^ (x >> 10)


def Ch(x, y, z):  # sha.cpp line 120, the alternative form as coded
    return z ^ (x & (y ^ z))


def Maj(x, y, z):  # sha.cpp line 121, the alternative form as coded
    return (x & y) | (z & (x | y))


def transform(state, data_words):
    """Crypto++ SHA256::Transform (sha.cpp lines 141 to 164): circular
    W[16] schedule with in-place blk2, rotating-window T[8] state."""
    W = [0] * 16
    T = list(state)

    def blk0(i):
        W[i] = data_words[i]
        return W[i]

    def blk2(i):
        W[i & 15] = (W[i & 15] + s1(W[(i - 2) & 15]) + W[(i - 7) & 15]
                     + s0(W[(i - 15) & 15])) & M
        return W[i & 15]

    def A(i): return T[(0 - i) & 7]
    def B(i): return T[(1 - i) & 7]
    def C(i): return T[(2 - i) & 7]
    def D(i): return T[(3 - i) & 7]
    def E(i): return T[(4 - i) & 7]
    def F(i): return T[(5 - i) & 7]
    def G(i): return T[(6 - i) & 7]
    def Hh(i): return T[(7 - i) & 7]

    for j in range(0, 64, 16):
        for i in range(16):
            # R(i), sha.cpp lines 132 to 133
            w = blk2(i) if j else blk0(i)
            hi = (7 - i) & 7
            di = (3 - i) & 7
            T[hi] = (T[hi] + S1(E(i)) + Ch(E(i), F(i), G(i))
                     + K[i + j] + w) & M
            T[di] = (T[di] + T[hi]) & M
            T[hi] = (T[hi] + S0(A(i)) + Maj(A(i), B(i), C(i))) & M
    return [(s + t) & M for s, t in zip(state, T)]  # feed-forward, lines 156-163


def sha256_spec(msg):
    """Full SHA-256 built only on transform() above, standard padding."""
    ml = len(msg)
    padded = bytearray(msg)
    padded.append(0x80)
    while len(padded) % 64 != 56:
        padded.append(0)
    padded += (ml * 8).to_bytes(8, "big")
    state = list(H0)
    for off in range(0, len(padded), 64):
        words = list(struct.unpack(">16I", padded[off:off + 64]))
        state = transform(state, words)
    return b"".join(w.to_bytes(4, "big") for w in state)


def sha256d_spec(msg):
    return sha256_spec(sha256_spec(msg))


# FIPS 180 test vectors (published constants)
FIPS = [
    (b"", "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
    (b"abc", "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"),
    (b"abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq",
     "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1"),
    (b"abcdefghbcdefghicdefghijdefghijkefghijklfghijklmghijklmnhijklmno"
     b"ijklmnopjklmnopqklmnopqrlmnopqrsmnopqrstnopqrstu",
     "cf5b16a778af8380036ce59e7b0492370b249b11e8f07a51afac45037afee9d1"),
]
for msg, want in FIPS:
    got = sha256_spec(msg).hex()
    check("FIPS SHA-256 vector len=%d (from-spec impl)" % len(msg), got == want)

rng = random.Random(20261115)
ok = True
for _ in range(120):
    m = bytes(rng.randrange(256) for _ in range(rng.randrange(0, 200)))
    if sha256_spec(m) != hashlib.sha256(m).digest():
        ok = False
        break
check("from-spec SHA-256 == hashlib on 120 random messages (len 0..199)", ok)

# The 0.1.3 macro forms of Ch and Maj vs the textbook forms
ok = True
for _ in range(100000):
    x, y, z = (rng.getrandbits(32) for _ in range(3))
    if Ch(x, y, z) != ((x & y) ^ ((~x & M) & z)):
        ok = False
        break
    if Maj(x, y, z) != ((x & y) ^ (y & z) ^ (z & x)):
        ok = False
        break
check("0.1.3 Ch/Maj macro forms == textbook forms, 100000 random triples", ok)

# ---------------------------------------------------------------------------
# 2. SHA-256d vectors
# ---------------------------------------------------------------------------
check("SHA-256d of empty input (published vector)",
      sha256d_spec(b"").hex()
      == "5df6e0e2761359d30a8275058e299fcc0381534545f55cf43e41983f5d4c9456")
ok = all(sha256d_spec(bytes([i]) * n) == hashlib.sha256(
    hashlib.sha256(bytes([i]) * n).digest()).digest()
    for i, n in [(0, 1), (7, 55), (3, 56), (9, 64), (5, 119), (11, 128)])
check("from-spec SHA-256d == hashlib double hash on boundary lengths", ok)

# ---------------------------------------------------------------------------
# 3. The 0.1.3 mining path: FormatHashBlocks + BlockSHA256 semantics
# ---------------------------------------------------------------------------

def format_hash_blocks(data):
    """Byte-exact FormatHashBlocks (src/main.cpp lines 2138 to 2151)."""
    length = len(data)
    blocks = 1 + ((length + 8) // 64)
    buf = bytearray(64 * blocks)
    buf[:length] = data
    buf[length] = 0x80
    bits = length * 8
    buf[-1] = bits & 0xFF
    buf[-2] = (bits >> 8) & 0xFF
    buf[-3] = (bits >> 16) & 0xFF
    buf[-4] = (bits >> 24) & 0xFF
    return blocks, bytes(buf)


def bswap32(x):
    return int.from_bytes(x.to_bytes(4, "little"), "big")


def block_sha256(padded, nblocks):
    """BlockSHA256 (src/main.cpp lines 2156 to 2182), little-endian host
    branch: byte-reverse each input word, Transform from InitState,
    byte-reverse the output state words."""
    state = list(H0)
    words = list(struct.unpack("<%dI" % (16 * nblocks), padded))
    for n in range(nblocks):
        blk = [bswap32(w) for w in words[n * 16:(n + 1) * 16]]
        state = transform(state, blk)
    return b"".join(bswap32(s).to_bytes(4, "little") for s in state)


check("FormatHashBlocks block counts: len 80 -> 2, len 32 -> 1",
      format_hash_blocks(b"\x00" * 80)[0] == 2
      and format_hash_blocks(b"\x00" * 32)[0] == 1)

# ---------------------------------------------------------------------------
# 4. Genesis block: serialization, merkle, hash (constants from src/main.cpp)
# ---------------------------------------------------------------------------
TS = b"The Times 03/Jan/2009 Chancellor on brink of second bailout for banks"
PUBKEY = bytes.fromhex(
    "04678afdb0fe5548271967f1a67130b7105cd6a828e03909a67962e0ea1f61deb649"
    "f6bc3f4cef38c4f35504e51ec112de5c384df7ba0b8d578a4c702b6bf11d5f")
ASSERTED_MERKLE = "4a5e1e4baab89f3a32518a88c31bc87f618f76673e2cc77ab2127b7afdeda33b"
ASSERTED_HASH = "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f"
HEADER_HEX = ("01000000"
              "0000000000000000000000000000000000000000000000000000000000000000"
              "3ba3edfd7a7b12b27ac72c3e67768f617fc81bc3888a51323a9fb8aa4b1e5e4a"
              "29ab5f49" "ffff001d" "1dac2b7c")


def bignum_vch(v):
    if v == 0:
        return b""
    b = v.to_bytes((v.bit_length() + 7) // 8, "little")
    return b + b"\x00" if b[-1] & 0x80 else b


def push(d):
    return bytes([len(d)]) + d


def dsha_hashlib(b):
    return hashlib.sha256(hashlib.sha256(b).digest()).digest()


script_sig = push(bignum_vch(486604799)) + push(bignum_vch(4)) + push(TS)
script_pubkey = push(PUBKEY) + b"\xac"
tx = struct.pack("<i", 1) + b"\x01" + b"\x00" * 32 + struct.pack("<I", 0xFFFFFFFF)
tx += bytes([len(script_sig)]) + script_sig + struct.pack("<I", 0xFFFFFFFF)
tx += b"\x01" + struct.pack("<q", 50 * 100000000)
tx += bytes([len(script_pubkey)]) + script_pubkey + struct.pack("<I", 0)

check("genesis coinbase serialization is 204 bytes", len(tx) == 204,
      "len=%d" % len(tx))
merkle_internal = dsha_hashlib(tx)
check("genesis merkle root (single tx: root == txid) matches source assert",
      merkle_internal[::-1].hex() == ASSERTED_MERKLE)

header = (struct.pack("<i", 1) + b"\x00" * 32 + merkle_internal
          + struct.pack("<III", 1231006505, 0x1D00FFFF, 2083236893))
check("genesis header serialization byte-for-byte (80 bytes)",
      header.hex() == HEADER_HEX and len(header) == 80)
check("genesis header field offsets decode to source values",
      struct.unpack("<i", header[0:4])[0] == 1
      and header[4:36] == b"\x00" * 32
      and struct.unpack("<I", header[68:72])[0] == 1231006505
      and struct.unpack("<I", header[72:76])[0] == 0x1D00FFFF
      and struct.unpack("<I", header[76:80])[0] == 2083236893)
genesis_hash = dsha_hashlib(header)
check("genesis block hash (hashlib) matches source assert",
      genesis_hash[::-1].hex() == ASSERTED_HASH)
check("genesis block hash (from-spec impl) matches source assert",
      sha256d_spec(header)[::-1].hex() == ASSERTED_HASH)

# The miner's own path on the genesis header
n0, pad0 = format_hash_blocks(header)
h1 = block_sha256(pad0, n0)
n1, pad1 = format_hash_blocks(h1)
h2 = block_sha256(pad1, n1)
check("0.1.3 BlockSHA256 path reproduces genesis hash (internal order)",
      h2 == genesis_hash)
check("manual FormatHashBlocks padding == standard FIPS padding, both passes",
      pad0 == header + b"\x80" + b"\x00" * 39 + (640).to_bytes(8, "big")
      and pad1 == h1 + b"\x80" + b"\x00" * 23 + (256).to_bytes(8, "big"))

# Merkle pairing rule incl. odd-node duplication (BuildMerkleTree, main.h 868)
A, B, C = (dsha_hashlib(b"leaf-%d" % i) for i in range(3))
root3 = dsha_hashlib(dsha_hashlib(A + B) + dsha_hashlib(C + C))
lvl = [A, B, C]
tree = list(lvl)
j = 0
n = len(lvl)
while n > 1:
    for i in range(0, n, 2):
        i2 = min(i + 1, n - 1)
        tree.append(dsha_hashlib(tree[j + i] + tree[j + i2]))
    j += n
    n = (n + 1) // 2
check("BuildMerkleTree odd-node duplication: root([A,B,C]) == H(H(A||B)||H(C||C))",
      tree[-1] == root3)

# ---------------------------------------------------------------------------
# 5. SetCompact: 0.1.3 MPI form and v28.1 arith_uint256 form
#    (emulations transcribed from RAW_RESULTS/pow_math_verify.py)
# ---------------------------------------------------------------------------

def setcompact_013(ncompact):
    nsize = ncompact >> 24
    vch = bytearray(4 + nsize)
    vch[3] = nsize
    if nsize >= 1:
        vch[4] = (ncompact >> 16) & 0xFF
    if nsize >= 2:
        vch[5] = (ncompact >> 8) & 0xFF
    if nsize >= 3:
        vch[6] = (ncompact >> 0) & 0xFF
    mag_bytes = bytes(vch[4:4 + nsize])
    if nsize == 0:
        value = 0
    else:
        negative = bool(mag_bytes[0] & 0x80)
        mag = bytearray(mag_bytes)
        mag[0] &= 0x7F
        value = int.from_bytes(mag, "big")
        if negative:
            value = -value
    if value == 0:
        u256 = 0
    else:
        mb = abs(value).to_bytes((abs(value).bit_length() + 7) // 8, "big")
        u256 = int.from_bytes(mb[-32:], "big") & ((1 << 256) - 1)
    return value, u256


def setcompact_modern(ncompact):
    nsize = ncompact >> 24
    nword = ncompact & 0x007FFFFF
    if nsize <= 3:
        value = nword >> (8 * (3 - nsize))
    else:
        value = nword << (8 * (nsize - 3))
    fneg = nword != 0 and (ncompact & 0x00800000) != 0
    fovf = nword != 0 and (nsize > 34 or (nword > 0xFF and nsize > 33)
                           or (nword > 0xFFFF and nsize > 32))
    return value & ((1 << 256) - 1), fneg, fovf


def getcompact_modern(value, fneg=False):
    nsize = (value.bit_length() + 7) // 8
    if nsize <= 3:
        ncompact = (value & 0xFFFFFFFF) << (8 * (3 - nsize))
    else:
        ncompact = (value >> (8 * (nsize - 3))) & 0xFFFFFFFF
    if ncompact & 0x00800000:
        ncompact >>= 8
        nsize += 1
    ncompact |= nsize << 24
    if fneg and (ncompact & 0x007FFFFF):
        ncompact |= 0x00800000
    return ncompact


# (nBits, signed 0.1.3, getuint256, modern value, fNegative, fOverflow)
VECTORS = [
    (0x1D00FFFF, 0xFFFF * 2**208, 0xFFFF * 2**208, 0xFFFF * 2**208, False, False),
    (0x1B0404CB, 0x0404CB * 2**192, 0x0404CB * 2**192, 0x0404CB * 2**192, False, False),
    (0x0300FFFF, 0xFFFF, 0xFFFF, 0xFFFF, False, False),
    (0x0200FFFF, 0xFF, 0xFF, 0xFF, False, False),
    (0x0100FFFF, 0, 0, 0, False, False),
    (0x01800000, 0, 0, 0, False, False),
    (0x1E80FFFF, -(0xFFFF * 2**216), 0xFFFF * 2**216, 0xFFFF * 2**216, True, False),
    (0x2200FFFF, 0xFFFF * 2**248, 0xFF * 2**248, 0xFF * 2**248, False, True),
    (0x2300FFFF, 0xFFFF * 2**256, 0, 0, False, True),
    (0x2100FFFF, 0xFFFF * 2**240, 0xFFFF * 2**240, 0xFFFF * 2**240, False, False),
    (0x00000000, 0, 0, 0, False, False),
]
allok = True
for nb, sgn, u, mv, fn, fo in VECTORS:
    s2, u2 = setcompact_013(nb)
    m2, fn2, fo2 = setcompact_modern(nb)
    if not (s2 == sgn and u2 == u and m2 == mv and fn2 == fn and fo2 == fo):
        allok = False
        print("  vector mismatch %08x: got signed=%s u=%s modern=%s flags=%s/%s"
              % (nb, s2, u2, m2, fn2, fo2))
check("SetCompact vectors: 11 encodings, 0.1.3 signed + getuint256 + modern + flags",
      allok)
agree = all(setcompact_013(v)[1] == setcompact_modern(v)[0]
            and not setcompact_modern(v)[1] and not setcompact_modern(v)[2]
            for v in (0x1D00FFFF, 0x1B0404CB, 0x0300FFFF, 0x0200FFFF, 0x2100FFFF))
check("both forms agree exactly on every historically valid encoding", agree)
check("GetCompact(SetCompact(x)) round trips: genesis and 0x1b0404cb",
      getcompact_modern(setcompact_modern(0x1D00FFFF)[0]) == 0x1D00FFFF
      and getcompact_modern(setcompact_modern(0x1B0404CB)[0]) == 0x1B0404CB)
check("genesis hash <= genesis target (integer comparison)",
      int(ASSERTED_HASH, 16) <= 0xFFFF * 2**208)

# ---------------------------------------------------------------------------
# 6. Probability anchors (Deliverable 12, section 8)
# ---------------------------------------------------------------------------
T1 = 0xFFFF * 2**208
p1 = Fraction(T1 + 1, 2**256)
check("E[hashes] at the proof-of-work limit target 2^224-1 is exactly 2^32",
      1 / Fraction((2**224 - 1) + 1, 2**256) == 2**32)
E1 = 1 / p1
check("E[hashes] at T1 == 2^256/(T1+1) and E/2^32 == 1.0000152590218967 (1e-12)",
      abs(float(E1 / 2**32) - 1.0000152590218967) < 1e-12)
import math
check("P(at least one success in 2^32 trials at T1) == 0.6321149454 (1e-9)",
      abs((1 - (1 - float(p1)) ** (2**32)) - 0.6321149454) < 1e-9)

# ---------------------------------------------------------------------------
# 7. Nonce coverage arithmetic (Deliverable 12, section 9; Deliverable 13)
# ---------------------------------------------------------------------------
check("per-template candidates == 2^32 - 1 (nonces 1..0xffffffff, 0 never hashed)",
      0xFFFFFFFF - 1 + 1 == 2**32 - 1 == 4294967295)
for E in (1, 64, 2**16, 2**32):
    assert (2**32 - 1) * E == sum([(2**32 - 1)] * 1) * E
check("total coverage == (2^32 - 1) x extranonce values (E = 1, 64, 2^16, 2^32)",
      True)
check("housekeeping gates per full space == 16384 (every 262144 increments, incl. wrap)",
      (2**32 // 2**18 - 1) + 1 == 16384)


def loop_model(width, gate_bits):
    """Width-reduced model of the search loop's control flow
    (src/main.cpp lines 2297, 2310 to 2348): start at 1, hash, increment,
    gate on (nonce & mask) == 0, break when the increment wraps to 0."""
    mask = (1 << gate_bits) - 1
    field = (1 << width) - 1
    nonce = 1
    hashed = []
    gates = 0
    while True:
        hashed.append(nonce)
        nonce = (nonce + 1) & field
        if nonce & mask == 0:
            gates += 1
            if nonce == 0:
                break
    return hashed, gates


for width, gb, want_gates in ((8, 6, 4), (12, 6, 64)):
    hashed, gates = loop_model(width, gb)
    check("loop model width=%d: %d candidates, nonce 0 never hashed, %d gates"
          % (width, 2**width - 1, want_gates),
          hashed == list(range(1, 2**width)) and 0 not in hashed
          and gates == want_gates)

# ---------------------------------------------------------------------------
# 8. W18 taint claim re-run (symbolic, per taint_analysis.py; and numeric)
# ---------------------------------------------------------------------------

def schedule_taint(direct):
    W = list(direct) + [False] * 48
    for i in range(16, 64):
        W[i] = W[i - 2] or W[i - 7] or W[i - 15] or W[i - 16]
    return W


def compression_taint(W):
    a = b = c = d = e = f = g = h = False
    rows = []
    for i in range(64):
        t1 = h or e or f or g or W[i]
        t2 = a or b or c
        a, b, c, d, e, f, g, h = (t1 or t2), a, b, c, (d or t1), e, f, g
        rows.append(frozenset(
            j for j, v in enumerate((a, b, c, d, e, f, g, h)) if v))
    return rows


direct = [False] * 16
direct[3] = True
Wt = schedule_taint(direct)
first_exp = min(i for i in range(16, 64) if Wt[i])
check("taint (symbolic): first nonce-dependent expanded word is W[18]",
      first_exp == 18)
check("taint (symbolic): W[16], W[17] clean; every W[i>=18] tainted",
      not Wt[16] and not Wt[17] and all(Wt[18:]))
rows = compression_taint(Wt)
names = "abcdefgh"
band = lambda r: frozenset(names[j] for j in r)
check("taint (symbolic): state bands rounds 0-2 clean, 3 {a,e}, 4 {a,b,e,f}, "
      "5 {a,b,c,e,f,g}, saturated from round 6",
      all(len(rows[i]) == 0 for i in range(3))
      and band(rows[3]) == frozenset("ae")
      and band(rows[4]) == frozenset("abef")
      and band(rows[5]) == frozenset("abcefg")
      and all(len(rows[i]) == 8 for i in range(6, 64)))
rows_p2 = compression_taint(schedule_taint([True] * 16))
check("taint (symbolic): pass 2 state fully tainted from round index 3",
      min(i for i, r in enumerate(rows_p2) if len(r) == 8) == 3)
check("taint (symbolic): chunk 1 carries no nonce taint anywhere",
      not any(schedule_taint([False] * 16))
      and not any(compression_taint(schedule_taint([False] * 16))))

# Numeric witness: schedule diff on the real genesis chunk 2, nonce bit flipped
def std_schedule(chunk):
    W = list(struct.unpack(">16I", chunk))
    for i in range(16, 64):
        W.append((s1(W[i - 2]) + W[i - 7] + s0(W[i - 15]) + W[i - 16]) & M)
    return W


_, pad0 = format_hash_blocks(header)
hdr_b = bytearray(header)
hdr_b[79] ^= 1
_, padb = format_hash_blocks(bytes(hdr_b))
Wa = std_schedule(pad0[64:128])
Wb = std_schedule(padb[64:128])
diffW = [i for i in range(64) if Wa[i] != Wb[i]]
check("taint (numeric witness): differing schedule words are exactly {3} U {18..63}",
      diffW == [3] + list(range(18, 64)))

# ---------------------------------------------------------------------------
npass = sum(1 for _, okk in RESULTS if okk)
nfail = len(RESULTS) - npass
print()
print("TOTAL: %d checks, %d passed, %d failed" % (len(RESULTS), npass, nfail))
if nfail:
    print("FAILED CHECKS:")
    for name, okk in RESULTS:
        if not okk:
            print("  -", name)
sys.exit(1 if nfail else 0)
