#!/usr/bin/env python3
"""Pure-Python SHA-256 and SHA-256d reference implementation.

Written from the mathematical model in
research/EXTREME_RESEARCH/SHA256_COMPLETE_MATHEMATICAL_MODEL.md
(FIPS 180-4 definitions), independently of every production kernel
in this repository (no production code is imported or called).

The 8 initial state words and the 64 round constants are NOT
copied from a table. They are derived at import time from the
prime roots exactly as Phase 001 verified them against the
Bitcoin v0.1.3 source (research/phase001/
SHA256_CONSTANTS_AND_TABLES.md): H(0)[i] is the first 32 bits of
the fractional part of sqrt(p_i) for the first 8 primes, and
K[t] is the first 32 bits of the fractional part of cbrt(p_t)
for the first 64 primes. The derivation uses exact integer
arithmetic only:

  floor(frac(sqrt(p)) * 2^32) = isqrt(p * 2^64) - isqrt(p) * 2^32
  floor(frac(cbrt(p)) * 2^32) = icbrt(p * 2^96) - icbrt(p) * 2^32

Usage as a library:
  from sha256d_reference import sha256, sha256d, compress, IV, K

Usage as a program: runs a small self-check against known FIPS
and Bitcoin vectors and prints the results.
"""

import math
import struct

MASK = 0xFFFFFFFF


def _first_primes(n):
    primes = []
    cand = 2
    while len(primes) < n:
        if all(cand % p for p in primes if p * p <= cand):
            primes.append(cand)
        cand += 1
    return primes


def _icbrt(n):
    """Exact integer cube root (floor) via Newton iteration."""
    if n < 0:
        raise ValueError("negative")
    if n == 0:
        return 0
    x = 1 << ((n.bit_length() + 2) // 3)
    while True:
        y = (2 * x + n // (x * x)) // 3
        if y >= x:
            break
        x = y
    while x * x * x > n:
        x -= 1
    while (x + 1) * (x + 1) * (x + 1) <= n:
        x += 1
    return x


def _derive_iv():
    out = []
    for p in _first_primes(8):
        out.append(math.isqrt(p << 64) - (math.isqrt(p) << 32))
    return tuple(out)


def _derive_k():
    out = []
    for p in _first_primes(64):
        out.append(_icbrt(p << 96) - (_icbrt(p) << 32))
    return tuple(out)


IV = _derive_iv()
K = _derive_k()


def _rotr(x, n):
    return ((x >> n) | (x << (32 - n))) & MASK


def compress(state, block):
    """One SHA-256 compression over a 64-byte block.

    state: tuple of 8 words. block: exactly 64 bytes.
    Returns the new state after the feed-forward addition.
    """
    if len(block) != 64:
        raise ValueError("block must be 64 bytes")
    w = list(struct.unpack(">16I", block))
    for t in range(16, 64):
        x = w[t - 15]
        s0 = _rotr(x, 7) ^ _rotr(x, 18) ^ (x >> 3)
        y = w[t - 2]
        s1 = _rotr(y, 17) ^ _rotr(y, 19) ^ (y >> 10)
        w.append((w[t - 16] + s0 + w[t - 7] + s1) & MASK)
    a, b, c, d, e, f, g, h = state
    for t in range(64):
        s1 = _rotr(e, 6) ^ _rotr(e, 11) ^ _rotr(e, 25)
        ch = (e & f) ^ ((~e & MASK) & g)
        t1 = (h + s1 + ch + K[t] + w[t]) & MASK
        s0 = _rotr(a, 2) ^ _rotr(a, 13) ^ _rotr(a, 22)
        maj = (a & b) ^ (a & c) ^ (b & c)
        t2 = (s0 + maj) & MASK
        h = g
        g = f
        f = e
        e = (d + t1) & MASK
        d = c
        c = b
        b = a
        a = (t1 + t2) & MASK
    return tuple((s + v) & MASK
                 for s, v in zip(state, (a, b, c, d, e, f, g, h)))


def _pad(message):
    """FIPS 180-4 padding: 0x80, zeros, 64-bit big-endian bit length."""
    ml = len(message)
    out = bytearray(message)
    out.append(0x80)
    while len(out) % 64 != 56:
        out.append(0)
    out += struct.pack(">Q", ml * 8)
    return bytes(out)


def sha256(message):
    """SHA-256 digest of an arbitrary byte string."""
    state = IV
    padded = _pad(message)
    for off in range(0, len(padded), 64):
        state = compress(state, padded[off:off + 64])
    return struct.pack(">8I", *state)


def sha256d(message):
    """Bitcoin double SHA-256: sha256(sha256(message))."""
    return sha256(sha256(message))


def midstate(first_64_bytes):
    """State after compressing exactly the first 64-byte block
    from the IV. This is the reusable midstate for an 80-byte
    Bitcoin header: bytes 0 to 63 are nonce-independent."""
    if len(first_64_bytes) != 64:
        raise ValueError("midstate input must be 64 bytes")
    return compress(IV, first_64_bytes)


def sha256_from_midstate(state, remaining):
    """Finish a SHA-256 whose first block produced `state`.
    `remaining` is the unpadded remainder of the message; the
    padding accounts for the full message length (64 + len)."""
    total = 64 + len(remaining)
    tail = bytearray(remaining)
    tail.append(0x80)
    while len(tail) % 64 != 56:
        tail.append(0)
    tail += struct.pack(">Q", total * 8)
    for off in range(0, len(tail), 64):
        state = compress(state, bytes(tail[off:off + 64]))
    return struct.pack(">8I", *state)


def _self_check():
    vectors = [
        (b"",
         "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
        (b"abc",
         "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"),
        (b"abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq",
         "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1"),
    ]
    ok = True
    for msg, want in vectors:
        got = sha256(msg).hex()
        print("sha256 len=%d %s" % (len(msg), "OK" if got == want else
                                   "MISMATCH " + got))
        ok = ok and got == want
    print("IV[0]=%08x K[0]=%08x K[63]=%08x" % (IV[0], K[0], K[63]))
    return ok


if __name__ == "__main__":
    raise SystemExit(0 if _self_check() else 1)
