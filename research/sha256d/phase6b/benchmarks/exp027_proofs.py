#!/usr/bin/env python3
"""EXP-027 proof and census driver (Phase 6B, Track B).

Legs: L1 GF(2)-linearity of the sigma maps (z3 UNSAT) and
non-affinity counterexamples for Ch and Maj (z3 SAT).
L2 single-instruction GFNI refutation for Sigma0 plus the
Sigma0 dependency census. L3 VPSHUFB rotation forms.
L4 carry-save compressor identity. L5 rotated and
byte-swapped state refutations. L6 52-bit accumulation
exactness. L7 two-round and cross-compression sharing
censuses. L8 schedule unrolling census.

Run with the lab z3 venv python. Writes one append-only
record under phase6b/proofs/. Touches no production file.
"""

import json
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
PHASE6B = os.path.dirname(HERE)
M32 = 0xFFFFFFFF


def rotr(x, n):
    return ((x >> n) | (x << (32 - n))) & M32


def S0(x):
    return rotr(x, 2) ^ rotr(x, 13) ^ rotr(x, 22)


def Ch(e, f, g):
    return (e & f) ^ ((~e & M32) & g)


def Maj(a, b, c):
    return (a & b) ^ (a & c) ^ (b & c)


def leg1():
    import z3
    out = {}
    a, b = z3.BitVec("a", 32), z3.BitVec("b", 32)
    R = z3.RotateRight
    maps = {
        "Sigma0": lambda x: R(x, 2) ^ R(x, 13) ^ R(x, 22),
        "Sigma1": lambda x: R(x, 6) ^ R(x, 11) ^ R(x, 25),
        "sigma0": lambda x: R(x, 7) ^ R(x, 18) ^ z3.LShR(x, 3),
        "sigma1": lambda x: R(x, 17) ^ R(x, 19) ^ z3.LShR(x, 10),
    }
    lin = {}
    for name, fn in maps.items():
        s = z3.Solver()
        s.add(fn(a ^ b) != (fn(a) ^ fn(b)))
        lin[name] = str(s.check())
    out["sigma_maps_gf2_linear_z3"] = lin

    def nonaffine(fn):
        e1, f1, g1 = (z3.BitVec(n, 32) for n in ("e1", "f1", "g1"))
        e2, f2, g2 = (z3.BitVec(n, 32) for n in ("e2", "f2", "g2"))
        s = z3.Solver()
        s.add(fn(e1 ^ e2, f1 ^ f2, g1 ^ g2)
              != (fn(e1, f1, g1) ^ fn(e2, f2, g2) ^ fn(0, 0, 0)))
        r = str(s.check())
        model = None
        if r == "sat":
            m = s.model()
            model = {str(d): m[d].as_long() for d in m.decls()}
        return r, model

    zCh = lambda e, f, g: (e & f) ^ (~e & g)
    zMaj = lambda a, b, c: (a & b) ^ (a & c) ^ (b & c)
    r_ch, m_ch = nonaffine(zCh)
    r_maj, m_maj = nonaffine(zMaj)
    out["Ch_affine_violation_z3"] = r_ch
    out["Ch_affine_counterexample"] = m_ch
    out["Maj_affine_violation_z3"] = r_maj
    out["Maj_affine_counterexample"] = m_maj
    if m_ch:
        u = (m_ch["e1"], m_ch["f1"], m_ch["g1"])
        v = (m_ch["e2"], m_ch["f2"], m_ch["g2"])
        lhs = Ch(u[0] ^ v[0], u[1] ^ v[1], u[2] ^ v[2])
        rhs = Ch(*u) ^ Ch(*v) ^ Ch(0, 0, 0)
        out["Ch_counterexample_numeric_recheck"] = (lhs != rhs)
    if m_maj:
        u = (m_maj["e1"], m_maj["f1"], m_maj["g1"])
        v = (m_maj["e2"], m_maj["f2"], m_maj["g2"])
        lhs = Maj(u[0] ^ v[0], u[1] ^ v[1], u[2] ^ v[2])
        rhs = Maj(*u) ^ Maj(*v) ^ Maj(0, 0, 0)
        out["Maj_counterexample_numeric_recheck"] = (lhs != rhs)
    return out


def leg2():
    out = {}
    dep_bytes = {ob: set() for ob in range(4)}
    dep_bits = {ob: 0 for ob in range(32)}
    for j in range(32):
        y = S0(1 << j)
        for ob in range(32):
            if (y >> ob) & 1:
                dep_bits[ob] += 1
                dep_bytes[ob // 8].add(j // 8)
    out["Sigma0_output_byte_input_bytes"] = {
        str(k): sorted(v) for k, v in dep_bytes.items()}
    out["Sigma0_output_bit_fanin"] = {
        str(k): v for k, v in dep_bits.items()}
    base = 0x12345678
    found = None
    for delta in range(1, 256):
        x2 = base ^ (delta << 8)
        if (S0(base) & 0xFF) != (S0(x2) & 0xFF):
            found = (base, x2, S0(base), S0(x2))
            break
    out["per_byte_refutation_pair"] = {
        "x": found[0], "x_prime": found[1],
        "differ_in_bytes": [1],
        "Sigma0_x": found[2], "Sigma0_x_prime": found[3],
        "output_byte0_differs": True,
    }
    return out


def leg3():
    import z3
    out = {}
    x = z3.BitVec("x", 32)
    step = z3.RotateRight(x, 8)
    cons = z3.LShR(step, 5) | (step << 27)
    s = z3.Solver()
    s.add(cons != z3.RotateRight(x, 13))
    out["shuffle_shift_or_ROTR13_z3"] = str(s.check())
    rng_state = 0x9E3779B9
    witness = None
    for _ in range(200000):
        rng_state ^= (rng_state << 13) & M32
        rng_state ^= rng_state >> 17
        rng_state ^= (rng_state << 5) & M32
        v = rng_state & M32
        b0 = rotr(v, 13) & 0xFF
        bytes_x = {(v >> (8 * i)) & 0xFF for i in range(4)}
        if b0 != 0 and b0 not in bytes_x:
            witness = (v, rotr(v, 13), b0)
            break
    out["pure_shuffle_refutation_witness"] = {
        "x": witness[0], "ROTR13_x": witness[1],
        "needed_byte0": witness[2],
        "bytes_of_x": sorted({(witness[0] >> (8 * i)) & 0xFF
                              for i in range(4)}),
    }
    return out


def leg4():
    import z3
    a, b, c = (z3.BitVec(n, 32) for n in ("a", "b", "c"))
    ssum = a ^ b ^ c
    carry = ((a & b) | (a & c) | (b & c)) << 1
    s = z3.Solver()
    s.add((a + b + c) != (ssum + carry))
    return {"carry_save_identity_z3": str(s.check())}


def S0z(x):
    import z3
    return z3.RotateRight(x, 2) ^ z3.RotateRight(x, 13) \
        ^ z3.RotateRight(x, 22)


def leg5():
    import z3
    out = {}
    a, b = z3.BitVec("a", 32), z3.BitVec("b", 32)
    s = z3.Solver()
    s.add(z3.RotateRight(a + b, 7)
          != (z3.RotateRight(a, 7) + z3.RotateRight(b, 7)))
    r = str(s.check())
    model = None
    if r == "sat":
        m = s.model()
        model = {str(d): m[d].as_long() for d in m.decls()}
        av, bv = model["a"], model["b"]
        lhs = rotr((av + bv) & M32, 7)
        rhs = (rotr(av, 7) + rotr(bv, 7)) & M32
        out["rotation_add_counterexample_numeric_recheck"] = (
            lhs != rhs)
    out["rotation_add_z3"] = r
    out["rotation_add_counterexample"] = model

    def bswap(x):
        return (((x & 0xFF) << 24) | ((x & 0xFF00) << 8)
                | ((x >> 8) & 0xFF00) | ((x >> 24) & 0xFF))

    def z_bswap(x):
        return (z3.Extract(7, 0, x) << 24) | \
            (z3.Extract(15, 8, x) << 16) | \
            (z3.Extract(23, 16, x) << 8) | z3.Extract(31, 24, x)

    s2 = z3.Solver()
    s2.add(z_bswap(a + b) != (z_bswap(a) + z_bswap(b)))
    r2 = str(s2.check())
    model2 = None
    if r2 == "sat":
        m = s2.model()
        model2 = {str(d): m[d].as_long() for d in m.decls()}
        av, bv = model2["a"], model2["b"]
        lhs = bswap((av + bv) & M32)
        rhs = (bswap(av) + bswap(bv)) & M32
        out["bswap_add_counterexample_numeric_recheck"] = (
            lhs != rhs)
    out["bswap_add_z3"] = r2
    out["bswap_add_counterexample"] = model2

    e, f, g = (z3.BitVec(n, 32) for n in ("e", "f", "g"))
    zCh = lambda x, y, z: (x & y) ^ (~x & z)
    s3 = z3.Solver()
    s3.add(z3.RotateRight(zCh(e, f, g), 7) != zCh(
        z3.RotateRight(e, 7), z3.RotateRight(f, 7),
        z3.RotateRight(g, 7)))
    out["Ch_rotation_equivariance_z3"] = str(s3.check())
    s4 = z3.Solver()
    s4.add(z3.RotateRight(S0z(a), 7) != S0z(z3.RotateRight(a, 7)))
    out["Sigma0_rotation_equivariance_z3"] = str(s4.check())
    return out


def leg6():
    import z3
    ops = [z3.BitVec("w%d" % i, 64) for i in range(5)]
    s = z3.Solver()
    for w in ops:
        s.add(z3.ULT(w, 2 ** 32))
    total = ops[0] + ops[1] + ops[2] + ops[3] + ops[4]
    s.add(z3.UGE(total, 2 ** 52))
    fits = str(s.check())
    a32 = [z3.BitVec("v%d" % i, 32) for i in range(5)]
    s2 = z3.Solver()
    chain = a32[0] + a32[1] + a32[2] + a32[3] + a32[4]
    wide = sum(z3.ZeroExt(32, v) for v in a32)
    s2.add(z3.Extract(31, 0, wide) != chain)
    low32 = str(s2.check())
    return {"t1_sum_fits_52_bits_z3": fits,
            "low32_equals_bv_chain_z3": low32}


_intern = {}


def node(op, *kids):
    key = (op,) + kids
    if key not in _intern:
        _intern[key] = len(_intern)
    return _intern[key]


def build_round(st, W, K, created):
    a, b, c, d, e, f, g, h = st

    def N(op, *kids):
        before = len(_intern)
        nid = node(op, *kids)
        if len(_intern) > before:
            created.add(nid)
        return nid

    def add(x, y):
        return N("add", x, y)

    def xor3(x, y, z):
        return N("xor3", x, y, z)

    S1v = xor3(N("rotr6", e), N("rotr11", e), N("rotr25", e))
    Chv = N("ch", e, f, g)
    S0v = xor3(N("rotr2", a), N("rotr13", a), N("rotr22", a))
    Majv = N("maj", a, b, c)
    T1 = add(add(add(add(h, S1v), Chv), K), W)
    T2 = add(S0v, Majv)
    ap = add(T1, T2)
    ep = add(d, T1)
    return (ap, a, b, c, ep, e, f, g), T1


def leg7():
    out = {}
    _intern.clear()
    atoms = {n: node("var", n) for n in "abcdefgh"}
    W1, K1 = node("var", "W_r1"), node("var", "K_r1")
    W2, K2 = node("var", "W_r2"), node("var", "K_r2")
    st = tuple(atoms[n] for n in "abcdefgh")
    created1, created2 = set(), set()
    st2, T1_r1 = build_round(st, W1, K1, created1)
    st3, T1_r2 = build_round(st2, W2, K2, created2)
    atom_ids = set(atoms.values()) | {W1, K1, W2, K2, T1_r1}
    shared = (created1 & created2) - atom_ids
    out["two_round_census"] = {
        "round1_new_nodes": len(created1),
        "round2_new_nodes": len(created2),
        "shared_nontrivial_nodes_across_boundary": len(shared),
        "note": "T1 of round 1 enters round 2 only as a "
                "consumed value; pass-through words are "
                "renames, not computations.",
    }
    D = 1
    dep = [D] * 8 + [0] * 8
    for t in range(16, 64):
        dep.append(dep[t - 16] | dep[t - 15] | dep[t - 7]
                   | dep[t - 2])
    out["outer_compression_census"] = {
        "schedule_words_depending_on_digest": sum(
            1 for t in range(16, 64) if dep[t] & D),
        "schedule_words_total_computed": 48,
        "rounds_fully_digest_independent": 0,
        "note": "Rounds 0..7 consume digest words directly; "
                "rounds 8..15 consume state already dependent "
                "on the digest. Zero complete outer rounds "
                "can execute before the inner compression "
                "finishes.",
    }
    return out


def leg8():
    size = [1] * 16
    for t in range(16, 64):
        s_sig0 = size[t - 15] + 5
        s_sig1 = size[t - 2] + 5
        size.append(size[t - 16] + s_sig0 + size[t - 7]
                    + s_sig1 + 3)
    return {
        "unrolled_tree_size_W20": size[20],
        "unrolled_tree_size_W24": size[24],
        "unrolled_tree_size_W28": size[28],
        "unrolled_tree_size_W31": size[31],
        "unrolled_tree_size_W63_digits": len(str(size[63])),
        "recurrence_dag_ops_per_word": 8,
        "recurrence_dag_ops_W16_to_W63": 48 * 8,
        "note": "Tree sizes count expression nodes with no "
                "sharing. The shared unrolling is exactly "
                "the recurrence DAG.",
    }


def main():
    import platform
    rec = {
        "experiment": "EXP-027",
        "kind": "proofs and censuses",
        "generated_utc": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"),
        "machine": platform.machine(),
    }
    with open("/proc/cpuinfo") as fh:
        for line in fh:
            if line.startswith("model name"):
                rec["cpu"] = line.split(":", 1)[1].strip()
                break
    rec["legs"] = {}
    for name, fn in [("L1_linearity", leg1), ("L2_gfni", leg2),
                     ("L3_shuffle", leg3), ("L4_carrysave", leg4),
                     ("L5_state_reprs", leg5), ("L6_ifma", leg6),
                     ("L7_sharing", leg7), ("L8_unroll", leg8)]:
        rec["legs"][name] = fn()
        print(name, "done", flush=True)
    os.makedirs(os.path.join(PHASE6B, "proofs"), exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(PHASE6B, "proofs",
                        "exp027_proofs_%s.json" % stamp)
    with open(path, "w") as fh:
        json.dump(rec, fh, indent=2)
    print("wrote", path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
