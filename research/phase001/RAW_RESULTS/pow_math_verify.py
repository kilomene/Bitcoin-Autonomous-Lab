#!/usr/bin/env python3
"""Wave 3 verification 4: PoW / target mathematics for Bitcoin v0.1.3.

Emulates, in exact Python integers:
  A. The 0.1.3 CBigNum::SetCompact (src/bignum.h lines 257-268), which builds
     an OpenSSL MPI byte string and calls BN_mpi2bn. MPI format: 4-byte
     big-endian length, then the magnitude big-endian, with the TOP BIT of
     the first magnitude byte as the sign bit (magnitude = remaining bits).
  B. The 0.1.3 CBigNum::getuint256 (bignum.h lines 218-231): BN_bn2mpi,
     vch[4] &= 0x7f (sign bit cleared), then the low 32 bytes copied into a
     uint256 (truncation of anything above 256 bits).
  C. The modern arith_uint256::SetCompact (v28.1 src/arith_uint256.cpp
     175-193, per research/bitcoin_core/POW_DIFFICULTY_SOURCE.md), with its
     negative/overflow out-flags and 256-bit wrap.
Then compares the two on a vector set, checks the genesis facts, derives the
probability quantities as exact fractions, and checks bnProofOfWorkLimit.
"""
from fractions import Fraction


def setcompact_013(ncompact):
    """Returns (signed_value, getuint256_value) under 0.1.3 semantics."""
    nsize = ncompact >> 24
    vch = bytearray(4 + nsize)
    vch[3] = nsize
    if nsize >= 1:
        vch[4] = (ncompact >> 16) & 0xFF
    if nsize >= 2:
        vch[5] = (ncompact >> 8) & 0xFF
    if nsize >= 3:
        vch[6] = (ncompact >> 0) & 0xFF
    # BN_mpi2bn: length = first 4 bytes BE = nsize; magnitude = next nsize
    # bytes; sign = top bit of first magnitude byte.
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
    # getuint256: bn2mpi of the value, vch[4] &= 0x7f, low 32 bytes kept.
    if value == 0:
        u256 = 0
    else:
        mb = abs(value).to_bytes((abs(value).bit_length() + 7) // 8, "big")
        # MPI writes a leading 0x00 if the top bit would read as sign; the
        # 0x7f mask in the source then applies to that first byte. Either way
        # the magnitude bytes copied are the plain big-endian magnitude.
        u256 = int.from_bytes(mb[-32:], "big") if len(mb) > 32 else int.from_bytes(mb, "big")
        u256 &= (1 << 256) - 1
    return value, u256


def setcompact_modern(ncompact):
    """Returns (value mod 2^256, fNegative, fOverflow), v28.1 semantics."""
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


vectors = [0x1D00FFFF, 0x1B0404CB, 0x1E0FFFFF, 0x0300FFFF, 0x0200FFFF,
           0x0100FFFF, 0x01800000, 0x1E80FFFF, 0x1D80FFFF, 0x2200FFFF,
           0x2300FFFF, 0x2100FFFF, 0x00000000, 0x1D00FFFE]
print("%-10s | %-28s | %-28s | %-28s | %s" %
      ("nBits", "0.1.3 signed (CBigNum)", "0.1.3 getuint256", "modern value", "modern flags"))
for v in vectors:
    signed, u = setcompact_013(v)
    mv, fn, fo = setcompact_modern(v)
    def fmt(x):
        s = hex(x)
        return s if len(s) <= 28 else s[:18] + ".." + s[-6:]
    print("%08x | %-28s | %-28s | %-28s | neg=%s ovf=%s" %
          (v, fmt(signed), fmt(u), fmt(mv), fn, fo))

T1, u1 = setcompact_013(0x1D00FFFF)
print()
print("genesis nBits 0x1d00ffff target:", hex(T1))
print("== 0xffff * 2^208:", T1 == 0xFFFF * 2**208)
print("modern agrees:", setcompact_modern(0x1D00FFFF)[0] == T1)

limit = (1 << 224) - 1  # bnProofOfWorkLimit = ~uint256(0) >> 32 (main.h 22)
print("bnProofOfWorkLimit = 2^224 - 1 >= genesis target:", limit >= T1)
print("limit / target =", float(Fraction(limit, T1)))

genesis_hash = int("000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f", 16)
print("genesis hash <= target:", genesis_hash <= T1)

# Probability, exact fractions. Model: hash uniform on [0, 2^256).
# Success iff hash <= T: p = (T + 1) / 2^256.
p1 = Fraction(T1 + 1, 2**256)
E1 = 1 / p1
print()
print("difficulty-1 target T1 = 0xffff * 2^208 =", T1)
print("p(T1) = (T1+1)/2^256 =", float(p1))
print("E[hashes at T1] = 2^256/(T1+1) =", E1, "=", float(E1))
print("E / 2^32 =", float(E1 / 2**32),
      " (the textbook 2^32 is the approximation T1 -> 2^224;")
print("   exactly, E = 2^32 * 2^224/(2^224 - 2^208 + 1))")
# With the limit target 2^224 - 1 instead of T1:
pL = Fraction(limit + 1, 2**256)
print("E[hashes at bnProofOfWorkLimit] = 2^256/2^224 = 2^32 exactly:",
      1 / pL == 2**32)
# Geometric distribution facts (derived, standard mathematics):
print("geometric: P(first success at trial k) = (1-p)^(k-1) p;")
print("P(at least one in N) = 1 - (1-p)^N; median trials = ceil(ln(1/2)/ln(1-p))")
import math
med = math.ceil(math.log(0.5) / math.log(1 - float(p1)))
print("median trials at T1 ~", med, " (~ ln2 * E =", float(math.log(2) * E1), ")")
print("nonce space per template in 0.1.3 loop: 2^32 values, loop starts at 1")
print("P(success within one full nonce space at T1) = 1-(1-p)^(2^32) =",
      1 - (1 - float(p1)) ** (2**32))
