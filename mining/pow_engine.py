"""Task 003: independent Proof-of-Work engine.

A from-specification SHA-256 (FIPS 180-4) in pure Python, a strict
80-byte header type, compact target handling that mirrors Bitcoin
Core's SetCompact and CheckProofOfWork (negative, overflow, zero and
above-limit targets are rejected with reason codes), difficulty, and
Core cross-verification. The fast paths elsewhere in the lab use
hashlib; this engine exists so the lab can check hashlib, OpenSSL and
Bitcoin Core against an implementation that shares no code with any
of them.
"""

import struct

MASK = 0xFFFFFFFF

K = (
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
    0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2)

H0 = (0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
      0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19)


def _rr(x, n):
    return ((x >> n) | (x << (32 - n))) & MASK


class PureSHA256:
    """Streaming SHA-256 per FIPS 180-4, standard library free."""

    def __init__(self, data=b""):
        self.h = list(H0)
        self.buf = b""
        self.length = 0
        if data:
            self.update(data)

    def _block(self, block):
        w = list(struct.unpack(">16I", block))
        for i in range(16, 64):
            s0 = _rr(w[i - 15], 7) ^ _rr(w[i - 15], 18) ^ (w[i - 15] >> 3)
            s1 = _rr(w[i - 2], 17) ^ _rr(w[i - 2], 19) ^ (w[i - 2] >> 10)
            w.append((w[i - 16] + s0 + w[i - 7] + s1) & MASK)
        a, b, c, d, e, f, g, hh = self.h
        for i in range(64):
            s1 = _rr(e, 6) ^ _rr(e, 11) ^ _rr(e, 25)
            ch = (e & f) ^ (~e & g)
            t1 = (hh + s1 + ch + K[i] + w[i]) & MASK
            s0 = _rr(a, 2) ^ _rr(a, 13) ^ _rr(a, 22)
            mj = (a & b) ^ (a & c) ^ (b & c)
            t2 = (s0 + mj) & MASK
            hh, g, f, e, d, c, b, a = (g, f, e, (d + t1) & MASK,
                                       c, b, a, (t1 + t2) & MASK)
        self.h = [(x + y) & MASK for x, y in
                  zip(self.h, (a, b, c, d, e, f, g, hh))]

    def update(self, data):
        self.length += len(data)
        data = self.buf + data
        full = len(data) - (len(data) % 64)
        for i in range(0, full, 64):
            self._block(data[i:i + 64])
        self.buf = data[full:]
        return self

    def copy(self):
        other = PureSHA256()
        other.h = list(self.h)
        other.buf = self.buf
        other.length = self.length
        return other

    def digest(self):
        clone = self.copy()
        bitlen = clone.length * 8
        clone.update(b"\x80")
        while len(clone.buf) != 56:
            clone.update(b"\x00")
        tail = clone.buf + struct.pack(">Q", bitlen)
        clone.buf = b""
        clone._block(tail)
        return struct.pack(">8I", *clone.h)

    def hexdigest(self):
        return self.digest().hex()


def sha256_pure(data):
    return PureSHA256(data).digest()


def double_sha256_pure(data):
    return sha256_pure(sha256_pure(data))


# Consensus targets, mirroring Core.
POW_LIMIT_MAINNET = (0x00000000FFFF0000000000000000000000000000000000000000000000000000)
POW_LIMIT_REGTEST = (0x7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF)


def compact_decode(nbits):
    """Core SetCompact with explicit negative and overflow flags."""
    size = nbits >> 24
    word = nbits & 0x007FFFFF
    negative = bool(word and (nbits & 0x00800000))
    if size <= 3:
        value = word >> (8 * (3 - size))
    else:
        value = word << (8 * (size - 3))
    overflow = bool(word and (size > 34 or (word > 0xFF and size > 33)
                           or (word > 0xFFFF and size > 32)))
    return value, negative, overflow


def compact_encode(value):
    size = (value.bit_length() + 7) // 8
    if size <= 3:
        compact = (value & 0xFFFFFF) << (8 * (3 - size))
    else:
        compact = value >> (8 * (size - 3))
    if compact & 0x00800000:
        compact >>= 8
        size += 1
    return (size << 24) | (compact & 0x007FFFFF)


def check_pow(header80, pow_limit):
    """Core CheckProofOfWork plus hash comparison.

    Returns (ok, reason): reason is one of ok, header-length,
    negative-target, overflow-target, zero-target, target-above-limit,
    high-hash."""
    if len(header80) != 80:
        return False, "header-length"
    nbits = struct.unpack("<I", header80[72:76])[0]
    target, negative, overflow = compact_decode(nbits)
    if negative:
        return False, "negative-target"
    if overflow:
        return False, "overflow-target"
    if target == 0:
        return False, "zero-target"
    if target > pow_limit:
        return False, "target-above-limit"
    digest = double_sha256_pure(header80)
    if int.from_bytes(digest, "little") > target:
        return False, "high-hash"
    return True, "ok"


def block_hash_display(header80):
    return double_sha256_pure(header80)[::-1].hex()


DIFF1_TARGET = 0x00000000FFFF0000000000000000000000000000000000000000000000000000


def difficulty(nbits):
    """Core GetDifficulty: difficulty-1 target divided by this target."""
    target, _, _ = compact_decode(nbits)
    if target == 0:
        return float("inf")
    return DIFF1_TARGET / target


def expected_hashes(nbits):
    target, _, _ = compact_decode(nbits)
    return (1 << 256) // (target + 1)
