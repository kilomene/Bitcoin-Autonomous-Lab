#!/usr/bin/env python3
"""EXP-056: canonicalised full-cone CEGIS synthesis at
L = 5, attacking the residual generality of H-033-02
(5-instruction round cones outside EXP-042's stated
bounds: sum or Boolean output produced by two or more
instructions).

The encoding is the EXP-033 full-cone encoding
(imported unchanged for semantics: cone targets,
incumbents, concrete evaluation, exact verification)
plus the canonicalisation constraints C1 to C5
predeclared in research/sha256d/exp056/
PREDECLARATION.md, whose sha256 is pinned below.
Encoding A: amounts as 32-bit bit-vectors in 1..31
(the EXP-033 form). Encoding B: amounts as integers
in 1..31 with rotation and shift by selection over
the 31 concrete rotations.

A synthesis UNSAT on the seed set is a proof at the
stated scope (vocabulary V, straight-line, length 5,
no decomposition assumptions), exactly as in EXP-033.
A SAT candidate is only believed after the exact z3
verification and a plain-Python differential run by
the campaign driver.

No em dash characters anywhere in this file.
"""

import hashlib
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
EXP056 = os.path.dirname(HERE)
LAB = os.path.dirname(os.path.dirname(os.path.dirname(EXP056)))
EXP033_SRC = os.path.join(LAB, "research", "sha256d",
                          "exp033", "src")
sys.path.insert(0, EXP033_SRC)

import exp033_cone_synth as cs  # noqa: E402

import z3  # noqa: E402

PREDECLARATION_SHA256 = \
    "95b39893c5e13fa7559c33dc3696ce05b6e17baadbd5c603f22b4165259b50a6"

OP_ADD, OP_LUT, OP_ROTR, OP_SHR = cs.OP_ADD, cs.OP_LUT, \
    cs.OP_ROTR, cs.OP_SHR
M32 = cs.M32
CONES = cs.CONES
run_program = cs.run_program

EDGE_VALUES = [0, 1, 2, 0xFFFFFFFF, 0xFFFFFFFE,
               0x80000000, 0x7FFFFFFF, 0xAAAAAAAA,
               0x55555555, 0x12345678]
STRESS = [(0, 0xFFFFFFFF, 0xAAAAAAAA, 0x55555555),
          (0xFFFFFFFF, 0, 0x55555555, 0xAAAAAAAA)]

# The planted control program P5, as predeclared.
# Representation: (op, srcs3, imm, amt) with srcs3 the
# full 3-slot selector tuple (unused slots 0).
P5_PROGRAM = [
    (OP_ROTR, (0, 0, 0), None, 7),
    (OP_ADD, (1, 4, 0), None, None),
    (OP_LUT, (5, 2, 3), 0x96, None),
    (OP_SHR, (6, 0, 0), None, 3),
    (OP_ADD, (6, 5, 0), None, None),
]
P5_OUTPUTS = (5, 6, 8)


def check_predeclaration():
    path = os.path.join(EXP056, "PREDECLARATION.md")
    with open(path, "rb") as fh:
        digest = hashlib.sha256(fh.read()).hexdigest()
    if digest != PREDECLARATION_SHA256:
        raise AssertionError(
            "predeclaration hash mismatch: %s" % digest)
    return digest


def seed_examples(rng, n_random=4):
    """The predeclared 16-example seed: 10 edge inputs,
    2 Boolean-stress inputs, n_random random inputs."""
    exs = [(v, v, v, v) for v in EDGE_VALUES]
    exs.extend(STRESS)
    for _ in range(n_random):
        exs.append(tuple(rng.getrandbits(32)
                         for _ in range(4)))
    seen = set()
    out = []
    for e in exs:
        if e not in seen:
            seen.add(e)
            out.append(e)
    return out


def targets_pairwise_distinguished(target, examples):
    """True iff for each pair of the 3 targets some
    example gives them different values (the C3
    soundness condition)."""
    for a in range(3):
        for b in range(a + 1, 3):
            if not any(target(e)[a] != target(e)[b]
                       for e in examples):
                return False
    return True


def planted_target(vals):
    return run_program_canon(P5_PROGRAM, P5_OUTPUTS, vals)


def run_program_canon(prog, outputs, vals):
    """Evaluate a program in the full 3-slot canonical
    representation (op, srcs3, imm, amt)."""
    vs = list(vals)
    for op, srcs, imm, amt in prog:
        if op == OP_ADD:
            vs.append((vs[srcs[0]] + vs[srcs[1]]) & M32)
        elif op == OP_LUT:
            vs.append(cs.lut_fast(imm, vs[srcs[0]],
                                  vs[srcs[1]], vs[srcs[2]]))
        elif op == OP_ROTR:
            vs.append(cs.rotr(vs[srcs[0]], amt))
        elif op == OP_SHR:
            vs.append(vs[srcs[0]] >> amt)
    return tuple(vs[o] for o in outputs)


def canonicalize_program(prog, outputs):
    """Map a concrete program in the EXP-033 variable
    length representation to the canonical 3-slot
    representation of this module (C1 and C2 applied).
    The computed function is unchanged."""
    out = []
    for op, srcs, imm, amt in prog:
        if op == OP_ADD:
            a, b = sorted((srcs[0], srcs[1]))
            out.append((op, (a, b, 0), 0, 1))
        elif op == OP_LUT:
            out.append((op, tuple(srcs), imm, 1))
        elif op in (OP_ROTR, OP_SHR):
            out.append((op, (srcs[0], 0, 0), 0, amt))
        else:
            raise ValueError(op)
    return out, tuple(outputs)


def all_profiles():
    """All 56 op-kind count profiles (nADD, nLUT,
    nROTR, nSHR) summing to 5, in the predeclared
    fixed order."""
    profs = []
    for a in range(6):
        for l in range(6 - a):
            for r in range(6 - a - l):
                s = 5 - a - l - r
                profs.append((a, l, r, s))
    profs.sort(key=lambda p: (-p[0], -p[1], -p[2], -p[3]))
    return profs


def _rot_sel(a, amt_int, rotate=True):
    """Rotation or shift of a by the integer amount
    amt_int in 1..31, by selection (encoding B)."""
    expr = None
    for k in range(31, 0, -1):
        v = z3.RotateRight(a, k) if rotate \
            else z3.LShR(a, k)
        expr = v if expr is None else z3.If(amt_int == k,
                                            v, expr)
    return expr


def synth_query(target, L, examples, timeout_ms,
                encoding="A", profile=None):
    """Canonicalised synthesis: ask z3 for a length-L
    program over V matching all examples of target
    (a callable from a 4-tuple of inputs to a 3-tuple
    of outputs). Returns (verdict, prog, outputs,
    wall_s) with verdict in sat, unsat, unknown. The
    program is returned in canonical 3-slot form."""
    n_in = 4
    ops = [z3.Int(f"op{i}") for i in range(L)]
    srcs = [[z3.Int(f"s{i}_{j}") for j in range(3)]
            for i in range(L)]
    imms = [z3.BitVec(f"imm{i}", 8) for i in range(L)]
    if encoding == "A":
        amts = [z3.BitVec(f"amt{i}", 32) for i in range(L)]
    else:
        amts = [z3.Int(f"amt{i}") for i in range(L)]
    out_sel = [z3.Int(f"out{k}") for k in range(3)]
    sol = z3.Solver()
    sol.set("timeout", timeout_ms)
    for i in range(L):
        sol.add(ops[i] >= 0, ops[i] <= 3)
        for j in range(3):
            sol.add(srcs[i][j] >= 0, srcs[i][j] < n_in + i)
        if encoding == "A":
            sol.add(z3.UGE(amts[i], 1), z3.ULE(amts[i], 31))
        else:
            sol.add(amts[i] >= 1, amts[i] <= 31)
        # C1: unused-slot fixing.
        sol.add(z3.Implies(ops[i] == OP_ADD,
                           z3.And(srcs[i][2] == 0,
                                  amts[i] == 1,
                                  imms[i] == 0)))
        sol.add(z3.Implies(ops[i] == OP_LUT, amts[i] == 1))
        sol.add(z3.Implies(
            z3.Or(ops[i] == OP_ROTR, ops[i] == OP_SHR),
            z3.And(srcs[i][1] == 0, srcs[i][2] == 0,
                   imms[i] == 0)))
        # C2: ADD commutativity.
        sol.add(z3.Implies(ops[i] == OP_ADD,
                           srcs[i][0] <= srcs[i][1]))
        # C4: every instruction used (output or read by
        # a later instruction's slots).
        uses = [out_sel[k] == n_in + i for k in range(3)]
        for j in range(i + 1, L):
            for t in range(3):
                uses.append(srcs[j][t] == n_in + i)
        sol.add(z3.Or(uses))
    # C3: output distinctness.
    for a in range(3):
        for b in range(a + 1, 3):
            sol.add(out_sel[a] != out_sel[b])
    for k in range(3):
        sol.add(out_sel[k] >= n_in, out_sel[k] < n_in + L)
    if profile is not None:
        for kind, count in zip(
                (OP_ADD, OP_LUT, OP_ROTR, OP_SHR), profile):
            sol.add(z3.Sum([z3.If(ops[i] == kind, 1, 0)
                            for i in range(L)]) == count)
    for ex in examples:
        vals = [z3.BitVecVal(v, 32) for v in ex]
        vs = list(vals)
        for i in range(L):
            a = cs.z3_select(srcs[i][0], vs)
            b = cs.z3_select(srcs[i][1], vs)
            c = cs.z3_select(srcs[i][2], vs)
            if encoding == "A":
                rot = z3.RotateRight(a, amts[i])
                shr = z3.LShR(a, amts[i])
            else:
                rot = _rot_sel(a, amts[i], rotate=True)
                shr = _rot_sel(a, amts[i], rotate=False)
            vi = z3.If(ops[i] == OP_ADD, a + b,
                       z3.If(ops[i] == OP_LUT,
                             cs.z3_lut(imms[i], a, b, c),
                             z3.If(ops[i] == OP_ROTR, rot,
                                   shr)))
            vs.append(vi)
        tgt = target(ex)
        for k in range(3):
            sol.add(cs.z3_select(out_sel[k], vs) ==
                    z3.BitVecVal(tgt[k], 32))
    t0 = time.time()
    res = sol.check()
    wall = time.time() - t0
    if str(res) == "unsat":
        return "unsat", None, None, wall
    if str(res) != "sat":
        return "unknown", None, None, wall
    m = sol.model()
    prog = []
    for i in range(L):
        op = m[ops[i]].as_long()
        s3 = tuple(m[srcs[i][j]].as_long() for j in range(3))
        imm = m[imms[i]].as_long() if op == OP_LUT else 0
        amt = m[amts[i]].as_long() if op in (OP_ROTR,
                                             OP_SHR) else 1
        prog.append((op, s3, imm, amt))
    outputs = tuple(m[o].as_long() for o in out_sel)
    return "sat", prog, outputs, wall


def verify_two_programs(prog_a, outs_a, prog_b, outs_b,
                        timeout_ms=600000):
    """Exact equivalence of two concrete canonical
    programs over symbolic inputs. Returns (verdict,
    wall_s): unsat means equivalent, sat means a
    counterexample exists, unknown on timeout."""
    ins = [z3.BitVec(f"in{i}", 32) for i in range(4)]

    def build(prog):
        vs = list(ins)
        for op, srcs, imm, amt in prog:
            if op == OP_ADD:
                vs.append(vs[srcs[0]] + vs[srcs[1]])
            elif op == OP_LUT:
                vs.append(cs.z3_lut(z3.BitVecVal(imm, 8),
                                    vs[srcs[0]], vs[srcs[1]],
                                    vs[srcs[2]]))
            elif op == OP_ROTR:
                vs.append(z3.RotateRight(vs[srcs[0]], amt))
            elif op == OP_SHR:
                vs.append(z3.LShR(vs[srcs[0]], amt))
        return vs

    va = build(prog_a)
    vb = build(prog_b)
    sol = z3.Solver()
    sol.set("timeout", timeout_ms)
    sol.add(z3.Or([va[outs_a[k]] != vb[outs_b[k]]
                   for k in range(3)]))
    t0 = time.time()
    res = sol.check()
    wall = time.time() - t0
    return str(res), wall


def verify_cone_candidate(cone, prog, outputs,
                          timeout_ms=600000):
    """Exact verification of a canonical candidate
    against a cone target, via the EXP-033 verify
    construction (the candidate is first mapped back
    to the EXP-033 variable-length representation).
    Returns (verdict, counterexample, wall_s)."""
    conv = []
    for op, srcs, imm, amt in prog:
        if op == OP_ADD:
            conv.append((op, (srcs[0], srcs[1]), None, None))
        elif op == OP_LUT:
            conv.append((op, tuple(srcs), imm, None))
        else:
            conv.append((op, (srcs[0],), None, amt))
    t0 = time.time()
    res, cex = cs.verify_program_z3(cone, conv, outputs,
                                    timeout_ms=timeout_ms)
    return res, cex, time.time() - t0
