#!/usr/bin/env python3
"""Wave 3 verification 1: SHA-256 constants in Bitcoin v0.1.3 src/sha.cpp.

Recomputes, with exact integer arithmetic (no floating point):
  H0[i] = floor(frac(sqrt(p_i)) * 2^32),  p_i = first 8 primes
  K[i]  = floor(frac(cbrt(p_i)) * 2^32),  p_i = first 64 primes
  SHA224 IV = floor(frac(sqrt(p_i)) * 2^32), p_i = primes 9..16
and compares against the literals parsed out of the 0.1.3 source:
  SHA256::InitState  src/sha.cpp lines 93-97
  SHA224::InitState  src/sha.cpp lines 87-91
  SHA256_K[64]       src/sha.cpp lines 99-116

Method: floor(sqrt(p) * 2^32) is the unique x with x^2 <= p * 2^64 < (x+1)^2;
floor(cbrt(p) * 2^32) is the unique x with x^3 <= p * 2^96 < (x+1)^3.
The constant is x mod 2^32 (the fractional part scaled by 2^32).
"""
import re
from math import isqrt

SRC = ("~/workspace/bitcoin-autonomous-lab/.local/refs-genesis/"
       "extracted/sni_rar/src/sha.cpp")
import os
text = open(os.path.expanduser(SRC)).read()


def primes(n):
    out, c = [], 2
    while len(out) < n:
        if all(c % p for p in out if p * p <= c):
            out.append(c)
        c += 1
    return out


def icbrt(n):
    # floor cube root, exact, via integer Newton + fixup
    x = round(n ** (1.0 / 3.0)) + 2
    while x ** 3 > n:
        x -= 1
    while (x + 1) ** 3 <= n:
        x += 1
    return x


def frac_sqrt_2_32(p):
    return isqrt(p << 64) % (1 << 32)


def frac_cbrt_2_32(p):
    return icbrt(p << 96) % (1 << 32)


P = primes(64)

# Parse source literals
init256 = re.search(r"void SHA256::InitState.*?\{([^}]*)\}", text, re.S).group(1)
src_h = [int(x, 16) for x in re.findall(r"0x[0-9a-fA-F]+", init256)]
init224 = re.search(r"void SHA224::InitState.*?\{([^}]*)\}", text, re.S).group(1)
src_h224 = [int(x, 16) for x in re.findall(r"0x[0-9a-fA-F]+", init224)]
kblock = re.search(r"SHA256_K\[64\] = \{(.*?)\};", text, re.S).group(1)
src_k = [int(x, 16) for x in re.findall(r"0x[0-9a-fA-F]+", kblock)]

calc_h = [frac_sqrt_2_32(p) for p in P[:8]]
calc_k = [frac_cbrt_2_32(p) for p in P]

# SHA-224 IV: FIPS 180 defines it from the square roots of the 9th..16th
# primes at 64-bit precision; the 32-bit words are the LOW halves of
# floor(frac(sqrt(p)) * 2^64), which are exactly the low halves of the
# SHA-384 IV words in the same file (src/sha.cpp lines 251-259).
def frac_sqrt_2_64(p):
    return isqrt(p << 128) % (1 << 64)

calc_h384 = [frac_sqrt_2_64(p) for p in P[8:16]]
calc_h224 = [x % (1 << 32) for x in calc_h384]
init384 = re.search(r"void SHA384::InitState.*?\{([^}]*)\}", text, re.S).group(1)
src_h384 = [int(x, 16) for x in re.findall(r"0x[0-9a-fA-F]+", init384)]
print("SHA384 InitState source :", [hex(x) for x in src_h384])
print("SHA384 recomputed (frac sqrt primes 9..16, 64-bit):",
      [hex(x) for x in calc_h384])
print("H384 match:", src_h384 == calc_h384)

print("first 8 primes:", P[:8])
print("SHA256 InitState source :", [hex(x) for x in src_h])
print("SHA256 InitState recomputed:", [hex(x) for x in calc_h])
print("H0 match:", src_h == calc_h)
print("SHA224 InitState source :", [hex(x) for x in src_h224])
print("SHA224 recomputed (primes 9..16 = %s):" % P[8:16],
      [hex(x) for x in calc_h224])
print("H224 match:", src_h224 == calc_h224)
print("K count parsed:", len(src_k), "recomputed:", len(calc_k))
mism = [(i, hex(a), hex(b)) for i, (a, b) in enumerate(zip(src_k, calc_k)) if a != b]
print("K mismatches:", mism)
print("K match:", src_k == calc_k)
for i in range(64):
    print("K[%2d] prime=%3d source=%08x recomputed=%08x %s"
          % (i, P[i], src_k[i], calc_k[i], "OK" if src_k[i] == calc_k[i] else "DIFF"))
