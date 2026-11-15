#!/usr/bin/env python3
"""EXP-033 Sigma sub-DAG synthesis bound.

Question: given the produced state word x (a' on the a-side,
e' on the e-side) plus up to four ARBITRARY side values
(fillers f1 to f4, universally quantified and independent
of x), can Sigma0(x) (resp. Sigma1(x)) be computed by a
straight-line program of L = 3 instructions over the
vocabulary V = {ADD, LUT(any imm), ROTR(any k), SHR(any k)}?

Why this is the right sub-question for the cone bound: in
any program computing the a-cone (a', Sigma0(a'),
Maj(a', a, b)), look at the set D of instructions whose
values the Sigma0(a') output transitively depends on,
excluding the instruction that produced a' itself.
Instructions in D that do not depend on a' contribute
values that are functions of the cone inputs other than
through a'; from the sub-DAG's perspective those are free
side values (fillers). The remaining instructions in D
depend on a' and number k. If k <= 3, the sub-DAG is an
L <= 3 program of the form synthesised here (operands
chosen from x, fillers, and prior values) computing
Sigma0(x) for ALL x and ALL independent fillers, because
the cone is correct for all inputs. So UNSAT here proves
k >= 4.

Cone accounting that follows (stated with its one caveat
in the report): cone ops >= 1 (the ADD producing a')
+ k (>= 4) + 1 (the Maj instruction), where the Maj
instruction is counted separately unless it itself lies
in D; if it lies in D it is one of the k a'-dependent
instructions and the bound reads >= 1 + 4 = 5 with the
Sigma output routed through the Maj value, a shape the
method does not exclude.

Method: CEGIS. Synthesis queries are over a finite
example set; a universally correct program matches every
example, so UNSAT on the final example set proves no
L = 3 program exists. Any candidate found is verified
exactly by z3 (UNSAT on the negation) before being
reported.

The 4-instruction incumbent (3 rotations + XOR3 LUT) is
verified exactly by z3 as a gate.

No em dash characters anywhere in this file.
"""
import json
import os
import random
import sys
import time

import z3

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from exp033_common import (M32, rotr)


def sigma0(x):
    return rotr(x, 2) ^ rotr(x, 13) ^ rotr(x, 22)


def sigma1(x):
    return rotr(x, 6) ^ rotr(x, 11) ^ rotr(x, 25)

EXP033 = os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))

OP_ADD, OP_LUT, OP_ROTR, OP_SHR = 0, 1, 2, 3

# Program inputs: (x, f1, f2, f3, f4). Four fillers, so
# the transfer to the round cone (whose x-independent
# values are exactly T1, T2 and the two other cone
# inputs) is airtight: any sub-DAG operand drawn from
# x-independent cone values is one of at most four
# values, all universally quantified here.
N_IN = 5


def run_program(prog, out_idx, vals):
    vs = list(vals)
    for (op, s0, s1, s2, imm, amt) in prog:
        a, b, c = vs[s0], vs[s1], vs[s2]
        if op == OP_ADD:
            v = (a + b) & M32
        elif op == OP_LUT:
            v = 0
            for bit in range(32):
                idx = (((a >> bit) & 1) << 2) \
                    | (((b >> bit) & 1) << 1) \
                    | ((c >> bit) & 1)
                v |= ((imm >> idx) & 1) << bit
        elif op == OP_ROTR:
            v = rotr(a, amt)
        else:
            v = a >> amt
        vs.append(v & M32)
    return vs[out_idx]


def z3_lut(imm, a, b, c):
    terms = []
    for idx in range(8):
        ba = (idx >> 2) & 1
        bb = (idx >> 1) & 1
        bc = idx & 1
        ta = a if ba else ~a
        tb = b if bb else ~b
        tc = c if bc else ~c
        terms.append(z3.If(z3.Extract(idx, idx, imm) == 1,
                           ta & tb & tc, 0))
    out = terms[0]
    for t in terms[1:]:
        out = out | t
    return out


def z3_select(sel, vals):
    out = vals[-1]
    for i in range(len(vals) - 2, -1, -1):
        out = z3.If(sel == i, vals[i], out)
    return out


def prog_to_z3(prog, out_idx, xs):
    vs = list(xs)
    for (op, s0, s1, s2, imm, amt) in prog:
        a, b, c = vs[s0], vs[s1], vs[s2]
        if op == OP_ADD:
            v = a + b
        elif op == OP_LUT:
            v = z3_lut(z3.BitVecVal(imm, 8), a, b, c)
        elif op == OP_ROTR:
            v = z3.RotateRight(a, amt)
        else:
            v = z3.LShR(a, amt)
        vs.append(v)
    return vs[out_idx]


def verify_z3(prog, out_idx, target_fn, n_in=N_IN):
    xs = [z3.BitVec(f"x{i}", 32) for i in range(n_in)]
    got = prog_to_z3(prog, out_idx, xs)
    if target_fn is sigma0:
        want = z3.RotateRight(xs[0], 2) \
            ^ z3.RotateRight(xs[0], 13) \
            ^ z3.RotateRight(xs[0], 22)
    else:
        want = z3.RotateRight(xs[0], 6) \
            ^ z3.RotateRight(xs[0], 11) \
            ^ z3.RotateRight(xs[0], 25)
    s = z3.Solver()
    s.set("timeout", 600000)
    s.add(got != want)
    r = s.check()
    return {"unsat": "unsat", "sat": "sat"}.get(
        str(r), "unknown")


def synth_query(L, examples, target_fn, timeout_ms=900000):
    n_in = N_IN
    ops = [z3.Int(f"op{i}") for i in range(L)]
    srcs = [[z3.Int(f"s{i}_{j}") for j in range(3)]
            for i in range(L)]
    imms = [z3.BitVec(f"imm{i}", 8) for i in range(L)]
    amts = [z3.BitVec(f"amt{i}", 32) for i in range(L)]
    out_sel = z3.Int("out")
    sol = z3.Solver()
    sol.set("timeout", timeout_ms)
    for i in range(L):
        sol.add(ops[i] >= 0, ops[i] <= 3)
        for j in range(3):
            sol.add(srcs[i][j] >= 0, srcs[i][j] < n_in + i)
        sol.add(z3.UGE(amts[i], 1), z3.ULE(amts[i], 31))
    sol.add(out_sel >= n_in, out_sel < n_in + L)
    for ex in examples:
        vals = [z3.BitVecVal(v, 32) for v in ex]
        vs = list(vals)
        for i in range(L):
            a = z3_select(srcs[i][0], vs)
            b = z3_select(srcs[i][1], vs)
            c = z3_select(srcs[i][2], vs)
            vi = z3.If(ops[i] == OP_ADD, a + b,
                       z3.If(ops[i] == OP_LUT,
                             z3_lut(imms[i], a, b, c),
                             z3.If(ops[i] == OP_ROTR,
                                   z3.RotateRight(a, amts[i]),
                                   z3.LShR(a, amts[i]))))
            vs.append(vi)
        got = z3_select(out_sel, vs)
        sol.add(got == target_fn(ex[0]))
    r = sol.check()
    if r == z3.unsat:
        return ("unsat", None, None)
    if r != z3.sat:
        return ("unknown", None, None)
    m = sol.model()
    prog = []
    for i in range(L):
        op = m[ops[i]].as_long()
        imm = m[imms[i]].as_long() if op == OP_LUT else None
        amt = m[amts[i]].as_long() \
            if op in (OP_ROTR, OP_SHR) else None
        if amt is not None and not (1 <= amt <= 31):
            amt = ((amt - 1) % 31) + 1
        prog.append((op,
                     m[srcs[i][0]].as_long(),
                     m[srcs[i][1]].as_long(),
                     m[srcs[i][2]].as_long(),
                     imm, amt))
    return ("sat", prog, m[out_sel].as_long())


def cegis(name, target_fn, rng, L=3, max_iters=300):
    edge = [0, 1, 2, M32, M32 - 1, 0x80000000, 0x7FFFFFFF,
            0xAAAAAAAA, 0x55555555]
    examples = []
    for v in edge:
        examples.append((v, 0, 0, 0, 0))
        examples.append((v, v, v, v, v))
    for _ in range(16):
        examples.append(tuple(rng.getrandbits(32)
                              for _ in range(N_IN)))
    for it in range(max_iters):
        res, prog, out_idx = synth_query(L, examples,
                                         target_fn)
        print(f"  [{name} L={L}] iter {it}: synth {res}, "
              f"examples {len(examples)}", flush=True)
        if res == "unsat":
            return {"verdict": "no_program_proven",
                    "iterations": it + 1,
                    "final_examples": len(examples),
                    "examples": examples}
        if res == "unknown":
            return {"verdict": "synth_unknown",
                    "iterations": it + 1,
                    "final_examples": len(examples)}
        cex = None
        for _ in range(200000):
            vals = tuple(rng.getrandbits(32)
                         for _ in range(N_IN))
            if run_program(prog, out_idx, vals) \
                    != target_fn(vals[0]):
                cex = vals
                break
        if cex is None:
            vres = verify_z3(prog, out_idx, target_fn)
            print(f"  [{name} L={L}] candidate exact z3: "
                  f"{vres}", flush=True)
            if vres == "unsat":
                return {"verdict": "program_found_and_proven",
                        "program": prog, "output": out_idx,
                        "iterations": it + 1}
            if vres == "sat":
                s = z3.Solver()
                xs = [z3.BitVec(f"y{i}", 32)
                      for i in range(N_IN)]
                got = prog_to_z3(prog, out_idx, xs)
                if target_fn is sigma0:
                    want = z3.RotateRight(xs[0], 2) \
                        ^ z3.RotateRight(xs[0], 13) \
                        ^ z3.RotateRight(xs[0], 22)
                else:
                    want = z3.RotateRight(xs[0], 6) \
                        ^ z3.RotateRight(xs[0], 11) \
                        ^ z3.RotateRight(xs[0], 25)
                s.add(got != want)
                s.check()
                mm = s.model()
                cex = tuple(mm[x].as_long() for x in xs)
            else:
                return {"verdict": "verify_unknown",
                        "program": prog, "output": out_idx,
                        "iterations": it + 1}
        examples.append(cex)
    return {"verdict": "iteration_cap",
            "final_examples": len(examples)}


def cegis_cone(name, target_fn, rng, L=3, max_iters=300):
    """Cone-conditioned variant: examples are cone inputs
    (T1, T2, a, b); the program's operand pool is
    (s, T1, T2, a, b) with s = T1 + T2 mod 2^32 computed
    per example. Every example is cone-realizable, so
    UNSAT here excludes exactly the sub-DAGs that could
    occur inside a correct cone program, including any
    that exploit the correlation s = T1 + T2."""
    edge4 = [(0, 0, 0, 0), (1, 0, 0, 0), (0, 1, 0, 0),
             (M32, 1, 0, 0), (M32, M32, M32, M32),
             (0x80000000, 0x80000000, 0, 0),
             (0xAAAAAAAA, 0x55555555, 0xAAAAAAAA,
              0x55555555),
             (2, 3, 5, 7), (0, 0, M32, 1),
             (123456789, 987654321, 0xDEADBEEF,
              0x12345678)]
    examples = []
    for (t1, t2, a, b) in edge4:
        examples.append(((t1 + t2) & M32, t1, t2, a, b))
    # Small seed: the 34-example cone-conditioned query
    # timed out at 900 s on this host; CEGIS grows the
    # set by counterexamples if a candidate appears.
    for _ in range(6):
        t1, t2, a, b = (rng.getrandbits(32)
                        for _ in range(4))
        examples.append(((t1 + t2) & M32, t1, t2, a, b))
    for it in range(max_iters):
        res, prog, out_idx = synth_query(L, examples,
                                         target_fn)
        print(f"  [{name} cone L={L}] iter {it}: synth "
              f"{res}, examples {len(examples)}",
              flush=True)
        if res == "unsat":
            return {"verdict": "no_program_proven",
                    "iterations": it + 1,
                    "final_examples": len(examples),
                    "examples": examples}
        if res == "unknown":
            return {"verdict": "synth_unknown",
                    "iterations": it + 1,
                    "final_examples": len(examples)}
        cex = None
        for _ in range(200000):
            t1, t2, a, b = (rng.getrandbits(32)
                            for _ in range(4))
            vals = ((t1 + t2) & M32, t1, t2, a, b)
            if run_program(prog, out_idx, vals) \
                    != target_fn(vals[0]):
                cex = vals
                break
        if cex is None:
            return {"verdict": "candidate_needs_exact_check",
                    "program": prog, "output": out_idx,
                    "iterations": it + 1}
        examples.append(cex)
    return {"verdict": "iteration_cap",
            "final_examples": len(examples)}


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "sigma0"
    cone_mode = which.endswith("c")
    if cone_mode:
        which = which[:-1]
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    rng = random.Random(20261116)
    target_fn = sigma0 if which == "sigma0" else sigma1
    # Gate: the 4-instruction incumbent for Sigma from x.
    if which == "sigma0":
        rots = (2, 13, 22)
    else:
        rots = (6, 11, 25)
    inc = [(OP_ROTR, 0, 0, 0, None, rots[0]),
           (OP_ROTR, 0, 0, 0, None, rots[1]),
           (OP_ROTR, 0, 0, 0, None, rots[2]),
           (OP_LUT, N_IN, N_IN + 1, N_IN + 2, 0x96, None)]
    bad = 0
    for _ in range(200000):
        vals = tuple(rng.getrandbits(32)
                     for _ in range(N_IN))
        if run_program(inc, N_IN + 3, vals) \
                != target_fn(vals[0]):
            bad += 1
    print(which, "incumbent L=4 differential 200k: bad =",
          bad, flush=True)
    assert bad == 0
    res = verify_z3(inc, N_IN + 3, target_fn)
    print(which, "incumbent L=4 z3:", res, flush=True)
    assert res == "unsat"
    tag = which + ("_cone" if cone_mode else "")
    print(f"CEGIS {tag} L=3 ...", flush=True)
    if cone_mode:
        out = cegis_cone(which, target_fn, rng, L=3)
    else:
        out = cegis(which, target_fn, rng, L=3)
    print(tag, "L=3 verdict:", out["verdict"], flush=True)
    raw = {"experiment": "EXP-033 Sigma sub-DAG synthesis",
           "timestamp_utc": ts, "target": tag,
           "host": "Intel(R) Xeon(R) Platinum 8321HC",
           "incumbent_L4_differential_200k_mismatches": bad,
           "incumbent_L4_z3": res,
           "L3_result": {k: v for k, v in out.items()
                         if k != "examples"}}
    rp = os.path.join(EXP033, "RAW_RESULTS",
                      f"exp033_sigma_synth_{tag}_{ts}.json")
    pp = os.path.join(EXP033, "PROOFS",
                      f"exp033_sigma_synth_{tag}_{ts}.json")
    with open(rp, "w") as fh:
        json.dump(raw, fh, indent=2, default=str)
    proofs = {"experiment": "EXP-033 Sigma proofs",
              "timestamp_utc": ts, "target": tag,
              "incumbent_L4_z3": res, "L3": out}
    with open(pp, "w") as fh:
        json.dump(proofs, fh, indent=2, default=str)
    print("wrote", rp, flush=True)
    print("wrote", pp, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
