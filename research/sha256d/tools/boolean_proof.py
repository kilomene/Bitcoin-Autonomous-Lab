#!/usr/bin/env python3
"""NOVA SHA-X Boolean equivalence proofs for SHA-256 Ch and Maj.

Method 1 (proof): Ch and Maj are bitwise functions. A 32-bit word
identity built only from AND, OR, XOR, NOT holds for all 32-bit
inputs iff the corresponding 1-bit identity holds for all 8
combinations of the input bits. This script checks all 8 rows for
every candidate form, which is a complete proof, not a sample.

Method 2 (differential test): the same identities are checked on
random 32-bit words (default 1,000,000 samples, fixed seed) to
guard against a transcription error between the 1-bit forms and
the word-level code.

Method 3 (optional): if z3 is importable, each identity is also
handed to the bit-vector solver as an independent check. Its
absence is reported, never hidden.

Usage: python3 research/sha256d/tools/boolean_proof.py [samples]
Exit code 0 means every check passed.
"""
import random
import sys

M32 = 0xFFFFFFFF


def ch_ref(x, y, z):
    return (x & y) ^ ((~x & M32) & z)


def ch_alt(x, y, z):
    return z ^ (x & (y ^ z))


def maj_ref(x, y, z):
    return (x & y) ^ (x & z) ^ (y & z)


def maj_alt_a(x, y, z):
    return (x & y) ^ (z & (x ^ y))


def maj_alt_b(x, y, z):
    return (x & (y ^ z)) ^ (y & z)


CANDIDATES = [
    ("Ch_alt:  z ^ (x & (y ^ z))", ch_ref, ch_alt),
    ("Maj_alt_A: (x & y) ^ (z & (x ^ y))", maj_ref, maj_alt_a),
    ("Maj_alt_B: (x & (y ^ z)) ^ (y & z)", maj_ref, maj_alt_b),
]


def bit_proof(ref, alt):
    for x in (0, 1):
        for y in (0, 1):
            for z in (0, 1):
                if ref(x, y, z) != alt(x, y, z):
                    return False, (x, y, z)
    return True, None


def random_check(ref, alt, samples, rng):
    for _ in range(samples):
        x = rng.getrandbits(32)
        y = rng.getrandbits(32)
        z = rng.getrandbits(32)
        if ref(x, y, z) != alt(x, y, z):
            return False, (x, y, z)
    return True, None


def z3_check(name, ref, alt):
    try:
        import z3
    except ImportError:
        return "z3 not installed, skipped (methods 1 and 2 stand alone)"
    x, y, z = z3.BitVecs("x y z", 32)
    exprs = {
        "Ch_alt:  z ^ (x & (y ^ z))": z ^ (x & (y ^ z)),
        "Maj_alt_A: (x & y) ^ (z & (x ^ y))": (x & y) ^ (z & (x ^ y)),
        "Maj_alt_B: (x & (y ^ z)) ^ (y & z)": (x & (y ^ z)) ^ (y & z),
    }
    refs = {
        "Ch_alt:  z ^ (x & (y ^ z))": (x & y) ^ (~x & z),
        "Maj_alt_A: (x & y) ^ (z & (x ^ y))": (x & y) ^ (x & z) ^ (y & z),
        "Maj_alt_B: (x & (y ^ z)) ^ (y & z)": (x & y) ^ (x & z) ^ (y & z),
    }
    s = z3.Solver()
    s.add(refs[name] != exprs[name])
    return "UNSAT (equivalent)" if s.check() == z3.unsat else "SAT (NOT equivalent)"


def main():
    samples = int(sys.argv[1]) if len(sys.argv) > 1 else 1_000_000
    rng = random.Random(0x5EED)
    ok = True
    for name, ref, alt in CANDIDATES:
        p_ok, bad = bit_proof(ref, alt)
        r_ok, bad_r = random_check(ref, alt, samples, rng)
        z = z3_check(name, ref, alt)
        print(f"{name}")
        print(f"  exhaustive 1-bit proof (8/8 rows): "
              f"{'PASS' if p_ok else 'FAIL at ' + str(bad)}")
        print(f"  randomized 32-bit differential ({samples} samples): "
              f"{'PASS' if r_ok else 'FAIL at ' + str(bad_r)}")
        print(f"  z3 bit-vector check: {z}")
        ok = ok and p_ok and r_ok and not z.startswith("SAT")
    print("OVERALL:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
