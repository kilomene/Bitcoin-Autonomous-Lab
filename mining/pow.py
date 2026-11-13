"""Proof-of-Work primitives: double SHA-256, targets, merkle roots.

Pure Python, standard library only. Every function here is verified
against real Bitcoin data in tests/test_known_blocks.py and, in the
Blockchain Intelligence Engine, against live Regtest blocks.
"""

import hashlib
import struct


def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def dsha256(data: bytes) -> bytes:
    return sha256(sha256(data))


def hash_display(digest: bytes) -> str:
    """Bitcoin displays hashes byte reversed."""
    return digest[::-1].hex()


def target_from_nbits(nbits: int) -> int:
    """Expand the compact nbits representation to the full target."""
    exponent = nbits >> 24
    mantissa = nbits & 0x007FFFFF
    if exponent <= 3:
        return mantissa >> (8 * (3 - exponent))
    return mantissa << (8 * (exponent - 3))


def difficulty_from_nbits(nbits: int) -> float:
    diff1 = target_from_nbits(0x1D00FFFF)
    return diff1 / target_from_nbits(nbits)


def block_work_ok(header: bytes) -> bool:
    """True if dsha256(header) meets the target in the header itself."""
    if len(header) != 80:
        raise ValueError("header must be 80 bytes")
    nbits = struct.unpack("<I", header[72:76])[0]
    target = target_from_nbits(nbits)
    value = int.from_bytes(dsha256(header), "little")
    return value <= target


def merkle_root(txids_internal) -> bytes:
    """Compute a merkle root from txids in internal byte order.

    Duplicates the last element on odd levels, as Bitcoin does.
    """
    if not txids_internal:
        raise ValueError("no transactions")
    level = list(txids_internal)
    while len(level) > 1:
        nxt = []
        for i in range(0, len(level), 2):
            a = level[i]
            b = level[i + 1] if i + 1 < len(level) else a
            nxt.append(dsha256(a + b))
        level = nxt
    return level[0]


def coinbase_subsidy(height: int) -> int:
    """Block subsidy in satoshis for a height (era halvings)."""
    halvings = height // 210000
    if halvings >= 64:
        return 0
    return 5_000_000_000 >> halvings
