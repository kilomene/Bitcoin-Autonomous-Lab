#!/usr/bin/env python3
"""EXP-033 scope 1b: bounded program synthesis (CEGIS) over
the two fused round-boundary cones.

The cones are the exact points where round t+1 consumes
round t's addition outputs bitwise:

  a-cone: inputs (T1, T2, a, b) ->
          (a' = T1 + T2, Sigma0(a'), Maj(a', a, b))
  e-cone: inputs (d, T1, e, f) ->
          (e' = d + T1, Sigma1(e'), Ch(e', e, f))

Incumbent cost of each cone is 6 instructions
(1 ADD + 3 ROTR + 1 LUT for the Sigma, 1 LUT for
Maj/Ch). The question: does any straight-line program
of 5 instructions over the vocabulary
  V = { ADD(x,y), LUT(imm,x,y,z) any imm,
        ROTR(x,k) any k in 1..31, SHR(x,k) any k in 1..31 }
compute either cone exactly, for all 32-bit inputs?

Method: CEGIS. A synthesis query asks z3 for a program
matching a finite example set (program shape symbolic:
op kinds, operand selectors, LUT immediates, rotation
and shift amounts; values per example concrete). A
candidate is verified against symbolic inputs (UNSAT of
the inequality = exact equivalence for all inputs). A
counterexample input joins the example set. If the
synthesis query itself goes UNSAT on the example set,
no program of that length over V matches the examples,
hence none is universally correct: a proof at the
stated scope (vocabulary V, straight-line, length).

Sanity gates run first: the known 6-instruction
incumbent programs are verified exactly in z3, and a
1,000,000-sample Python differential of the cone targets
against the reference round equations must pass before
any synthesis result is read.

Writes PROOFS/exp033_cone_synth_<ts>.json and
RAW_RESULTS/exp033_cone_synth_<ts>.json.
"""

import json
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from exp033_common import M32, rotr

HERE = os.path.dirname(os.path.abspath(__file__))
EXP033 = os.path.dirname(HERE)

import z3

OP_ADD, OP_LUT, OP_ROTR, OP_SHR = 0, 1, 2, 3


def sigma0(x):
    return rotr(x, 2) ^ rotr(x, 13) ^ rotr(x, 22)


def sigma1(x):
    return rotr(x, 6) ^ rotr(x, 11) ^ rotr(x, 25)


def maj(a, b, c):
    return (a & b) ^ (a & c) ^ (b & c)


def ch(e, f, g):
    return (e & f) ^ ((~e & M32) & g)


def lut_fast(imm, a, b, c):
    out = 0
    for p in range(8):
        if (imm >> p) & 1:
            m = (a if (p >> 2) & 1 else (~a & M32)) & \
                (b if (p >> 1) & 1 else (~b & M32)) & \
                (c if p & 1 else (~c & M32))
            out |= m
    return out & M32


CONES = {
    "a_cone": {
        "inputs": ["T1", "T2", "a", "b"],
        "target": lambda v: (
            (v[0] + v[1]) & M32,
            sigma0((v[0] + v[1]) & M32),
            maj((v[0] + v[1]) & M32, v[2], v[3])),
        # incumbent: add; rotr2; rotr13; rotr22; lut XOR3;
        # lut MAJ  (operands reference values list:
        # inputs 0..3, then instruction results 4..)
        "incumbent": [
            (OP_ADD, (0, 1), None, None),
            (OP_ROTR, (4,), None, 2),
            (OP_ROTR, (4,), None, 13),
            (OP_ROTR, (4,), None, 22),
            (OP_LUT, (5, 6, 7), 0x96, None),
            (OP_LUT, (4, 2, 3), 0xE8, None),
        ],
        "incumbent_outputs": (4, 8, 9),
    },
    "e_cone": {
        "inputs": ["d", "T1", "e", "f"],
        "target": lambda v: (
            (v[0] + v[1]) & M32,
            sigma1((v[0] + v[1]) & M32),
            ch((v[0] + v[1]) & M32, v[2], v[3])),
        "incumbent": [
            (OP_ADD, (0, 1), None, None),
            (OP_ROTR, (4,), None, 6),
            (OP_ROTR, (4,), None, 11),
            (OP_ROTR, (4,), None, 25),
            (OP_LUT, (5, 6, 7), 0x96, None),
            (OP_LUT, (4, 2, 3), 0xCA, None),
        ],
        "incumbent_outputs": (4, 8, 9),
    },
}


def run_program(prog, outputs, vals):
    """Execute a concrete program (list of
    (op, srcs, imm, amt)) on input values vals (list).
    Values list: inputs first, then instruction results."""
    vs = list(vals)
    for op, srcs, imm, amt in prog:
        if op == OP_ADD:
            vs.append((vs[srcs[0]] + vs[srcs[1]]) & M32)
        elif op == OP_LUT:
            vs.append(lut_fast(imm, vs[srcs[0]], vs[srcs[1]],
                               vs[srcs[2]]))
        elif op == OP_ROTR:
            vs.append(rotr(vs[srcs[0]], amt))
        elif op == OP_SHR:
            vs.append(vs[srcs[0]] >> amt)
    return tuple(vs[o] for o in outputs)


def z3_lut(imm_bv, a, b, c):
    out = z3.BitVecVal(0, 32)
    for p in range(8):
        m = (a if (p >> 2) & 1 else ~a) & \
            (b if (p >> 1) & 1 else ~b) & \
            (c if p & 1 else ~c)
        bit = z3.Extract(p, p, imm_bv)
        out = out | z3.If(bit == 1, m, z3.BitVecVal(0, 32))
    return out


def z3_select(idx_var, values):
    """values: list of BV expressions. idx_var: Int."""
    expr = values[-1]
    for i in range(len(values) - 2, -1, -1):
        expr = z3.If(idx_var == i, values[i], expr)
    return expr


def verify_program_z3(cone, prog, outputs, timeout_ms=600000):
    """Exact equivalence of a concrete program against the
    cone targets over symbolic inputs. Returns
    ('unsat', None) if equivalent, ('sat', counterexample
    input tuple) if not, ('unknown', None) on timeout."""
    ins = [z3.BitVec(f"in{i}", 32) for i in range(4)]
    vs = list(ins)
    for op, srcs, imm, amt in prog:
        if op == OP_ADD:
            vs.append(vs[srcs[0]] + vs[srcs[1]])
        elif op == OP_LUT:
            vs.append(z3_lut(z3.BitVecVal(imm, 8), vs[srcs[0]],
                             vs[srcs[1]], vs[srcs[2]]))
        elif op == OP_ROTR:
            vs.append(z3.RotateRight(vs[srcs[0]], amt))
        elif op == OP_SHR:
            vs.append(z3.LShR(vs[srcs[0]], amt))
    # targets as z3 expressions over the same inputs
    s = (ins[0] + ins[1])
    if cone == "a_cone":
        t = (s,
             z3.RotateRight(s, 2) ^ z3.RotateRight(s, 13) ^
             z3.RotateRight(s, 22),
             (s & ins[2]) ^ (s & ins[3]) ^ (ins[2] & ins[3]))
    else:
        t = (s,
             z3.RotateRight(s, 6) ^ z3.RotateRight(s, 11) ^
             z3.RotateRight(s, 25),
             (s & ins[2]) ^ (~s & ins[3]))
    outs = [vs[o] for o in outputs]
    sol = z3.Solver()
    sol.set("timeout", timeout_ms)
    sol.add(z3.Or([outs[i] != t[i] for i in range(3)]))
    res = sol.check()
    if str(res) == "unsat":
        return "unsat", None
    if str(res) == "sat":
        m = sol.model()
        return "sat", tuple(m[v].as_long() for v in ins)
    return "unknown", None


def synth_query(cone, L, examples, timeout_ms=900000):
    """Ask z3 for a length-L program over V matching all
    examples. Returns ('sat', prog, outputs) or
    ('unsat', None, None) or ('unknown', None, None)."""
    n_in = 4
    target = CONES[cone]["target"]
    ops = [z3.Int(f"op{i}") for i in range(L)]
    srcs = [[z3.Int(f"s{i}_{j}") for j in range(3)]
            for i in range(L)]
    imms = [z3.BitVec(f"imm{i}", 8) for i in range(L)]
    amts = [z3.BitVec(f"amt{i}", 32) for i in range(L)]
    out_sel = [z3.Int(f"out{k}") for k in range(3)]
    sol = z3.Solver()
    sol.set("timeout", timeout_ms)
    for i in range(L):
        sol.add(ops[i] >= 0, ops[i] <= 3)
        for j in range(3):
            sol.add(srcs[i][j] >= 0, srcs[i][j] < n_in + i)
        sol.add(z3.UGE(amts[i], 1), z3.ULE(amts[i], 31))
    for k in range(3):
        # targets are not inputs; outputs must be produced
        sol.add(out_sel[k] >= n_in, out_sel[k] < n_in + L)
    for ex in examples:
        vals = [z3.BitVecVal(v, 32) for v in ex]
        vs = list(vals)
        for i in range(L):
            a = z3_select(srcs[i][0], vs)
            b = z3_select(srcs[i][1], vs)
            c = z3_select(srcs[i][2], vs)
            rot = z3.RotateRight(a, amts[i])
            shr = z3.LShR(a, amts[i])
            vi = z3.If(ops[i] == OP_ADD, a + b,
                       z3.If(ops[i] == OP_LUT,
                             z3_lut(imms[i], a, b, c),
                             z3.If(ops[i] == OP_ROTR, rot,
                                   shr)))
            vs.append(vi)
        tgt = target(ex)
        for k in range(3):
            sol.add(z3_select(out_sel[k], vs) ==
                    z3.BitVecVal(tgt[k], 32))
    res = sol.check()
    if str(res) == "unsat":
        return "unsat", None, None
    if str(res) != "sat":
        return "unknown", None, None
    m = sol.model()
    prog = []
    for i in range(L):
        op = m[ops[i]].as_long()
        imm = m[imms[i]].as_long() if op == OP_LUT else None
        amt = m[amts[i]].as_long() if op in (OP_ROTR, OP_SHR) \
            else None
        if amt is not None and not (1 <= amt <= 31):
            amt = ((amt - 1) % 31) + 1
        nsrc = {OP_ADD: 2, OP_LUT: 3, OP_ROTR: 1, OP_SHR: 1}[op]
        prog.append((op, tuple(m[srcs[i][j]].as_long()
                               for j in range(nsrc)), imm, amt))
    outputs = tuple(m[o].as_long() for o in out_sel)
    return "sat", prog, outputs


def initial_examples(rng, n_random=12):
    """Small seed set: CEGIS grows it by counterexamples.
    A large seed makes the first synthesis query needlessly
    hard (learned on the first run: 82 examples timed out
    at 600 s under this host's contention)."""
    exs = []
    edge = [0, 1, 2, M32, M32 - 1, 0x80000000, 0x7FFFFFFF,
            0xAAAAAAAA, 0x55555555, 0x12345678]
    for v in edge:
        exs.append((v, v, v, v))
    for _ in range(n_random):
        exs.append(tuple(rng.getrandbits(32) for _ in range(4)))
    # dedupe, keep order
    seen = set()
    out = []
    for e in exs:
        if e not in seen:
            seen.add(e)
            out.append(e)
    return out


def cegis(cone, L, rng, max_iters=200, log=print):
    examples = initial_examples(rng)
    target = CONES[cone]["target"]
    for it in range(max_iters):
        res, prog, outputs = synth_query(cone, L, examples)
        log(f"  [{cone} L={L}] iter {it}: synth {res}, "
            f"examples {len(examples)}")
        if res == "unsat":
            return {"verdict": "unsat_no_program",
                    "iterations": it + 1,
                    "final_example_count": len(examples),
                    "examples": [list(e) for e in examples]}
        if res == "unknown":
            return {"verdict": "synth_unknown",
                    "iterations": it + 1,
                    "final_example_count": len(examples)}
        vres, cex = verify_program_z3(cone, prog, outputs)
        log(f"  [{cone} L={L}] iter {it}: verify {vres}")
        if vres == "unsat":
            return {"verdict": "program_found_and_proven",
                    "iterations": it + 1,
                    "program": prog, "outputs": outputs,
                    "final_example_count": len(examples)}
        if vres == "sat":
            if target(cex) == run_program(prog, outputs, cex):
                return {"verdict": "verify_inconsistent",
                        "iterations": it + 1}
            examples.append(cex)
            continue
        return {"verdict": "verify_unknown",
                "iterations": it + 1, "program": prog,
                "outputs": outputs}
    return {"verdict": "iteration_cap", "iterations": max_iters,
            "final_example_count": len(examples)}


def main():
    stage = sys.argv[1] if len(sys.argv) > 1 else "all"
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    rng = random.Random(20261115)
    proofs = {"experiment": "EXP-033 cone synthesis proofs",
              "timestamp_utc": ts, "stage": stage,
              "host": "Intel(R) Xeon(R) Platinum 8321HC"}
    raw = {"experiment": "EXP-033 cone synthesis",
           "timestamp_utc": ts, "stage": stage}

    if stage in ("all", "gates"):
        # Gate 1: cone targets vs Python program
        # differential on the incumbent programs
        # (1,000,000 samples each cone).
        for name, cone in CONES.items():
            bad = 0
            for _ in range(1000000):
                vals = tuple(rng.getrandbits(32)
                             for _ in range(4))
                got = run_program(cone["incumbent"],
                                  cone["incumbent_outputs"],
                                  vals)
                if got != cone["target"](vals):
                    bad += 1
            raw[f"{name}_incumbent_differential_1e6"] = \
                {"mismatches": bad}
            print(name, "incumbent differential 1e6: bad =",
                  bad, flush=True)
            assert bad == 0
        # Gate 2: z3 exact verification of the incumbent
        # programs (validates targets and encoding).
        for name, cone in CONES.items():
            res, _ = verify_program_z3(
                name, cone["incumbent"],
                cone["incumbent_outputs"])
            proofs[f"{name}_incumbent_L6_z3"] = res
            print(name, "incumbent z3 verification:", res,
                  flush=True)
            assert res == "unsat"

    results = {}
    todo = [stage] if stage in CONES else \
        (list(CONES) if stage == "all" else [])
    for name in todo:
        print(f"CEGIS {name} L=5 ...", flush=True)
        results[name] = cegis(name, 5, rng)
        print(f"CEGIS {name} L=5 verdict:",
              results[name]["verdict"], flush=True)
    if results:
        raw["L5_results"] = {
            k: {kk: vv for kk, vv in v.items()
                if kk != "examples"}
            for k, v in results.items()}
        for k, v in results.items():
            if "examples" in v:
                proofs[f"{k}_L5_final_examples"] = \
                    v["examples"]
            if v["verdict"] == "program_found_and_proven":
                proofs[f"{k}_L5_program"] = {
                    "program": v["program"],
                    "outputs": v["outputs"]}
    rp = os.path.join(EXP033, "RAW_RESULTS",
                      f"exp033_cone_synth_{stage}_{ts}.json")
    pp = os.path.join(EXP033, "PROOFS",
                      f"exp033_cone_synth_{stage}_{ts}.json")
    with open(rp, "w") as fh:
        json.dump(raw, fh, indent=2)
    with open(pp, "w") as fh:
        json.dump(proofs, fh, indent=2, default=str)
    print("wrote", rp, flush=True)
    print("wrote", pp, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
