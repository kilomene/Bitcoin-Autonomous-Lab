#!/usr/bin/env python3
"""EXP-012 automated Boolean-cone search and proof.

Question: what is the cheapest exact realization of the
SHA-256 Boolean cone functions Ch and Maj (and the
three-way XOR used by every sigma function) on this CPU?

Method:
1. Exhaustive search over all 256 VPTERNLOGD immediates:
   a bitwise instruction's behaviour is fully determined
   by its 8-row table, so matching the table of the
   1-bit reference function over all 8 input rows is a
   complete proof that the instruction computes the
   function at any word width.
2. Lower-bound search over classic two-input ops
   (AND, OR, XOR, ANDNOT, plus NOT on leaves): breadth
   first by expression size over the set of realizable
   8-bit function tables. If Ch and Maj are absent from
   the size <= 2 closure, no classic expression with
   fewer than 3 ops computes them.
3. z3 bit-vector proof (32-bit words, UNSAT of the
   negation) that the closed forms read off the winning
   ternlog tables equal the reference Ch and Maj.
4. A 1,000,000-sample word-level differential of the
   closed forms as a transcription guard, following
   tools/boolean_proof.py.

Run with the z3 venv python:
  .local/z3venv/bin/python proofs/boolean_cone_search.py
Writes proofs/boolean_cone_results.json. Exit 0 on pass.
"""
import itertools
import json
import os
import random
import sys

M32 = 0xFFFFFFFF
HERE = os.path.dirname(os.path.abspath(__file__))

# Function tables: bit r of the table is the output for
# input row r, where r = (x<<2)|(y<<1)|z.
ROWS = [(x, y, z) for x in (0, 1) for y in (0, 1) for z in (0, 1)]


def table(fn):
    t = 0
    for r, (x, y, z) in enumerate(ROWS):
        t |= (fn(x, y, z) & 1) << r
    return t


CH = table(lambda x, y, z: (x & y) ^ ((x ^ 1) & z))
MAJ = table(lambda x, y, z: (x & y) ^ (x & z) ^ (y & z))
XOR3 = table(lambda x, y, z: x ^ y ^ z)


def ternlog_table(imm):
    return imm & 0xFF


def search_ternlog(target):
    return [imm for imm in range(256) if ternlog_table(imm) == target]


OPS = {
    "and": lambda a, b: a & b,
    "or": lambda a, b: a | b,
    "xor": lambda a, b: a ^ b,
    "andnot": lambda a, b: a & (b ^ 0xFF),
}


def classic_exact(max_ops):
    """exact[n] = set of function tables realizable with
    exactly n binary ops (AND, OR, XOR, ANDNOT); leaves
    are x, y, z, their negations and the constants, with
    NOT on a leaf free in this model. Trees are counted
    by total op count: a tree with root op and subtrees
    of i and j ops has i + j + 1 ops."""
    xt = table(lambda x, y, z: x)
    yt = table(lambda x, y, z: y)
    zt = table(lambda x, y, z: z)
    leaves = {xt, yt, zt, xt ^ 0xFF, yt ^ 0xFF, zt ^ 0xFF, 0, 0xFF}
    exact = [set(leaves)]
    for n in range(1, max_ops + 1):
        new = set()
        for i in range(n):
            j = n - 1 - i
            for a, b in itertools.product(exact[i], exact[j]):
                for op in OPS.values():
                    new.add(op(a, b) & 0xFF)
        exact.append(new)
    return exact


def main():
    results = {}
    ok = True

    # 1. ternlog search
    for name, tgt in (("Ch", CH), ("Maj", MAJ), ("XOR3", XOR3)):
        hits = search_ternlog(tgt)
        results[f"{name}_ternlog_immediates"] = hits
        print(f"{name}: table={tgt:#04x} ternlog immediates={hits}")
        ok = ok and len(hits) >= 1

    # 2. classic lower bound by exact op count
    exact = classic_exact(4)
    results["classic_exact_sizes"] = [len(s) for s in exact]
    for name, tgt, expect in (("Ch", CH, 3), ("Maj", MAJ, 4),
                              ("XOR3", XOR3, 2)):
        minops = next((n for n in range(5) if tgt in exact[n]),
                      None)
        results[f"{name}_classic_min_ops"] = minops
        print(f"{name}: minimum classic op count = {minops} "
              f"(expected {expect}); exact level sizes "
              f"{[len(s) for s in exact]}")
        ok = ok and minops == expect

    # 3. z3 proof of the closed forms read off the tables
    # Ch table 0xCA == (x & y) | (~x & z); the two terms
    # are disjoint, so | and ^ agree. Maj table 0xE8 ==
    # (x & y) | (x & z) | (y & z).
    try:
        import z3
        x, y, z = z3.BitVecs("x y z", 32)
        ch_ref = (x & y) ^ (~x & z)
        ch_closed = (x & y) | (~x & z)
        maj_ref = (x & y) ^ (x & z) ^ (y & z)
        maj_closed = (x & y) | (x & z) | (y & z)
        for name, a, b in (("Ch", ch_ref, ch_closed),
                           ("Maj", maj_ref, maj_closed)):
            s = z3.Solver()
            s.add(a != b)
            res = s.check()
            results[f"z3_{name}"] = str(res)
            print(f"z3 {name}: ref != closed is {res} "
                  f"(unsat means proven equal)")
            ok = ok and str(res) == "unsat"
    except ImportError:
        results["z3"] = "unavailable"
        print("z3 unavailable; table proof in step 1 stands "
              "on its own (bitwise completeness)")
        ok = False

    # 4. word-level differential of the closed forms
    rng = random.Random(12031)
    bad = 0
    for _ in range(1_000_000):
        a, b, c = (rng.getrandbits(32) for _ in range(3))
        if ((a & b) ^ (~a & c)) & M32 != ((a & b) | (~a & c)) & M32:
            bad += 1
        if ((a & b) ^ (a & c) ^ (b & c)) != \
                ((a & b) | (a & c) | (b & c)):
            bad += 1
    results["differential_bad"] = bad
    print(f"word differential: 1,000,000 samples, bad={bad}")
    ok = ok and bad == 0

    results["verdict"] = "PASS" if ok else "FAIL"
    with open(os.path.join(HERE, "boolean_cone_results.json"),
              "w") as fh:
        json.dump(results, fh, indent=2)
    print("verdict:", results["verdict"])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
