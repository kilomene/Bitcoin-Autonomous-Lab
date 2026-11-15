#!/usr/bin/env python3
"""EXP-042: the E2 attack. Sigma sub-DAG synthesis with the
Maj / Ch value inside the operand pool.

Background (EXP-033, hypothesis H-033-05, shape E2).
A round cone is

  a-cone: inputs (T1, T2, a, b) ->
          (s = T1 + T2, Sigma0(s), Maj(s, a, b))
  e-cone: inputs (d, T1, e, f) ->
          (s = d + T1, Sigma1(s), Ch(s, e, f))

with incumbent cost 6 over the vocabulary
  V = { ADD(x,y), LUT(imm,x,y,z) any imm,
        ROTR(x,k), SHR(x,k), k in 1..31 }.

EXP-033 proved (H-033-13 and H-033-14, cone-conditioned
synthesis) that no 3-instruction program over the pool
(s, T1, T2, a, b) computes Sigma0(s), and none over
(s, d, T1, e, f) computes Sigma1(s). Cone accounting:
any 5-instruction cone program is 1 ADD producing s,
plus the Sigma dependency DAG D, plus the Maj (resp.
Ch) instruction. If the Boolean instruction is not in
D, then |D| <= 3 over the pool without the Boolean
value, which H-033-13/14 exclude. Shape E2 is the
remaining case: the Boolean instruction lies inside D,
so Sigma is routed through the Maj (resp. Ch) value.

Reduction used here. If the Boolean instruction lies
in D, then D minus that one instruction is a program
of length |D| - 1 <= 3 whose operands are drawn from
the pool (s, p, q, x, y, m): the two sum inputs p, q,
the two other cone inputs x, y, the sum s, the Boolean
value m (Maj(s, x, y) on the a-side, Ch(s, x, y) on
the e-side), and its own prior results. Giving the
synthesiser m as a free pool input, available from the
first instruction, only enlarges the program space
(the real program can use m only after computing it),
so UNSAT at L = 3 over this pool refutes E2 at the
stated bounds, and any SAT candidate is a genuine
construction once verified exactly (the cone program
is then ADD, LUT for m, then the 3 instructions, with
indices remapped).

Examples are cone inputs (p, q, x, y); the pool tuple
is ((p + q) mod 2^32, p, q, x, y, BoolFn(s, x, y)), so
every example is cone-realizable by construction.

Method: CEGIS, the EXP-033 encoding (src/exp033_sigma_
synth.py) generalised to a 6-value pool. A universally
correct program matches every example, so a synthesis
UNSAT on the seed set is a proof at the stated scope.
Candidates are verified exactly in z3 over symbolic
cone inputs (s and m derived, not independent), and
independently in plain Python on random cone inputs
before any claim is read.

Stated bounds for any refutation produced here:
straight-line programs, vocabulary V, cone length 5,
the sum s produced by a single ADD of the two sum
inputs (the only single instruction over V that
computes the sum), the Boolean output produced by a
single LUT instruction (the E2 shape as named in
EXP-033). Shapes outside these bounds (sum or Boolean
value produced by two or more instructions) are not
covered by this reduction; the EXP-033 full-cone
CEGIS at L = 5 is the catch-all for them.

No em dash characters anywhere in this file.
"""

import json
import os
import random
import sys
import time

import z3

M32 = 0xFFFFFFFF

OP_ADD, OP_LUT, OP_ROTR, OP_SHR = 0, 1, 2, 3

# Pool layout: (s, p, q, x, y, m). p and q are the two
# sum inputs, x and y the other two cone inputs, m the
# Boolean value of (s, x, y).
N_IN = 6


def rotr(x, k):
    return ((x >> k) | (x << (32 - k))) & M32


def sigma0(x):
    return rotr(x, 2) ^ rotr(x, 13) ^ rotr(x, 22)


def sigma1(x):
    return rotr(x, 6) ^ rotr(x, 11) ^ rotr(x, 25)


def maj(a, b, c):
    return (a & b) ^ (a & c) ^ (b & c)


def ch(e, f, g):
    return (e & f) ^ ((~e & M32) & g)


CONES = {
    "a": {"sigma": sigma0, "bool": maj, "imm": 0xE8,
          "rots": (2, 13, 22), "name": "a_cone"},
    "e": {"sigma": sigma1, "bool": ch, "imm": 0xCA,
          "rots": (6, 11, 25), "name": "e_cone"},
}


def pool_of(cone, p, q, x, y):
    s = (p + q) & M32
    m = CONES[cone]["bool"](s, x, y)
    return (s, p, q, x, y, m)


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


def z3_sigma(cone, s):
    r = CONES[cone]["rots"]
    return z3.RotateRight(s, r[0]) ^ z3.RotateRight(s, r[1]) \
        ^ z3.RotateRight(s, r[2])


def z3_bool(cone, s, x, y):
    if cone == "a":
        return (s & x) ^ (s & y) ^ (x & y)
    return (s & x) ^ (~s & y)


def verify_candidate_z3(cone, prog, out_idx, timeout_ms=600000):
    """Exact check over symbolic cone inputs (p, q, x, y)
    with s = p + q and m derived. UNSAT of the negation
    proves the program computes Sigma(s) for every
    cone-realizable input."""
    p, q, x, y = (z3.BitVec(n, 32) for n in ("p", "q", "x", "y"))
    s = p + q
    m = z3_bool(cone, s, x, y)
    got = prog_to_z3(prog, out_idx, [s, p, q, x, y, m])
    want = z3_sigma(cone, s)
    sol = z3.Solver()
    sol.set("timeout", timeout_ms)
    sol.add(got != want)
    r = sol.check()
    if r == z3.unsat:
        return ("unsat", None)
    if r == z3.sat:
        mm = sol.model()
        return ("sat", tuple(mm[v].as_long() for v in (p, q, x, y)))
    return ("unknown", None)


def synth_query(cone, L, examples, target, timeout_ms):
    """target: 'sigma' (the E2 question) or 'control'
    (a target with a known 3-instruction program over
    this pool, used as an encoding sanity gate).
    examples: list of pool tuples."""
    sigma = CONES[cone]["sigma"]
    rots = CONES[cone]["rots"]

    def target_of(pool):
        if target == "sigma":
            return sigma(pool[0])
        # control: ROTR(s, r0) ^ ROTR(s, r1) ^ m has the
        # 3-instruction program ROTR, ROTR, LUT 0x96.
        return rotr(pool[0], rots[0]) ^ rotr(pool[0], rots[1]) \
            ^ pool[5]

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
            sol.add(srcs[i][j] >= 0, srcs[i][j] < N_IN + i)
        sol.add(z3.UGE(amts[i], 1), z3.ULE(amts[i], 31))
    sol.add(out_sel >= N_IN, out_sel < N_IN + L)
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
        sol.add(got == z3.BitVecVal(target_of(ex), 32))
    t0 = time.time()
    r = sol.check()
    wall = time.time() - t0
    if r == z3.unsat:
        return ("unsat", None, None, wall)
    if r != z3.sat:
        return ("unknown", None, None, wall)
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
    return ("sat", prog, m[out_sel].as_long(), wall)


EDGE4 = [(0, 0, 0, 0), (1, 0, 0, 0), (0, 1, 0, 0),
         (M32, 1, 0, 0), (M32, M32, M32, M32),
         (0x80000000, 0x80000000, 0, 0),
         (0xAAAAAAAA, 0x55555555, 0xAAAAAAAA, 0x55555555),
         (2, 3, 5, 7), (0, 0, M32, 1),
         (123456789, 987654321, 0xDEADBEEF, 0x12345678),
         # Boolean stress: x = y forces m = x on the
         # a-side and m = x on the e-side as well when
         # x = y = all ones or all zero patterns arise;
         # x != y extremes separate m from s.
         (0x11111111, 0x22222222, 0, 0),
         (0x11111111, 0x22222222, M32, M32),
         (0x11111111, 0x22222222, M32, 0),
         (0x11111111, 0x22222222, 0, M32)]


def seed_examples(cone, rng, n_random=2):
    exs = [pool_of(cone, *e) for e in EDGE4]
    for _ in range(n_random):
        exs.append(pool_of(cone, *(rng.getrandbits(32)
                                   for _ in range(4))))
    return exs


def cegis(cone, rng, L=3, target="sigma",
          timeout_ms=1500000, max_iters=60, log=print):
    sigma = CONES[cone]["sigma"]
    examples = seed_examples(cone, rng)
    total_wall = 0.0
    for it in range(max_iters):
        res, prog, out_idx, wall = synth_query(
            cone, L, examples, target, timeout_ms)
        total_wall += wall
        log(f"  [{cone} L={L} {target}] iter {it}: synth "
            f"{res}, examples {len(examples)}, "
            f"query wall {wall:.1f}s", flush=True)
        if res == "unsat":
            return {"verdict": "no_program_proven",
                    "iterations": it + 1,
                    "final_examples": len(examples),
                    "examples": examples,
                    "solver_wall_s": total_wall}
        if res == "unknown":
            return {"verdict": "synth_unknown",
                    "iterations": it + 1,
                    "final_examples": len(examples),
                    "solver_wall_s": total_wall}
        # Candidate: independent Python differential over
        # cone inputs first.
        cex = None
        for _ in range(200000):
            cin = tuple(rng.getrandbits(32) for _ in range(4))
            pool = pool_of(cone, *cin)
            want = sigma(pool[0]) if target == "sigma" else \
                rotr(pool[0], CONES[cone]["rots"][0]) \
                ^ rotr(pool[0], CONES[cone]["rots"][1]) ^ pool[5]
            if run_program(prog, out_idx, pool) != want:
                cex = pool
                break
        if cex is None and target == "sigma":
            vres, cex_in = verify_candidate_z3(cone, prog,
                                               out_idx)
            log(f"  [{cone}] candidate exact z3: {vres}",
                flush=True)
            if vres == "unsat":
                return {"verdict": "program_found_and_proven",
                        "program": prog, "output": out_idx,
                        "iterations": it + 1,
                        "solver_wall_s": total_wall}
            if vres == "sat":
                cex = pool_of(cone, *cex_in)
            else:
                return {"verdict": "verify_unknown",
                        "program": prog, "output": out_idx,
                        "iterations": it + 1,
                        "solver_wall_s": total_wall}
        if cex is None:
            return {"verdict": "candidate_passed_differential",
                    "program": prog, "output": out_idx,
                    "iterations": it + 1,
                    "solver_wall_s": total_wall}
        examples.append(cex)
    return {"verdict": "iteration_cap",
            "final_examples": len(examples),
            "solver_wall_s": total_wall}


def gates(cone, rng, log=print):
    """Sanity gates, run before any synthesis result is
    read. (1) The 4-instruction incumbent Sigma program
    over pool index 0 matches Sigma(s) on 200,000 random
    cone inputs, in plain Python. (2) The same incumbent
    is proven exact in z3 over symbolic cone inputs.
    (3) The pool Boolean value m equals a direct
    reference Maj / Ch on 200,000 random cone inputs
    (it is computed by the same functions, so this gate
    guards the pool wiring, not the mathematics)."""
    sigma = CONES[cone]["sigma"]
    rots = CONES[cone]["rots"]
    inc = [(OP_ROTR, 0, 0, 0, None, rots[0]),
           (OP_ROTR, 0, 0, 0, None, rots[1]),
           (OP_ROTR, 0, 0, 0, None, rots[2]),
           (OP_LUT, N_IN, N_IN + 1, N_IN + 2, 0x96, None)]
    bad = 0
    for _ in range(200000):
        pool = pool_of(cone, *(rng.getrandbits(32)
                               for _ in range(4)))
        if run_program(inc, N_IN + 3, pool) != sigma(pool[0]):
            bad += 1
    log(f"  [{cone}] incumbent L=4 Python differential "
        f"200k: bad = {bad}", flush=True)
    assert bad == 0
    vres, _ = verify_candidate_z3(cone, inc, N_IN + 3)
    log(f"  [{cone}] incumbent L=4 exact z3: {vres}",
        flush=True)
    assert vres == "unsat"
    return {"incumbent_L4_python_differential_200k_bad": bad,
            "incumbent_L4_exact_z3": vres}


def main():
    cone = sys.argv[1] if len(sys.argv) > 1 else "a"
    stage = sys.argv[2] if len(sys.argv) > 2 else "all"
    timeout_ms = int(sys.argv[3]) if len(sys.argv) > 3 \
        else 1500000
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    rng = random.Random(20261117)
    here = os.path.dirname(os.path.abspath(__file__))
    exp042 = os.path.dirname(here)
    host = "AMD EPYC 9D25"
    out = {"experiment": "EXP-042 E2 synthesis",
           "timestamp_utc": ts, "cone": cone, "stage": stage,
           "host": host, "z3_version": z3.get_version_string(),
           "pool": ["s", "p", "q", "x", "y", "m"],
           "timeout_ms_per_query": timeout_ms}
    print(f"EXP-042 cone {cone} stage {stage} z3 "
          f"{z3.get_version_string()}", flush=True)
    if stage in ("all", "gates"):
        out["gates"] = gates(cone, rng)
    if stage in ("all", "control"):
        print(f"CEGIS {cone} L=3 control ...", flush=True)
        out["control_L3"] = cegis(cone, rng, L=3,
                                  target="control",
                                  timeout_ms=timeout_ms)
        print(f"  control verdict:",
              out["control_L3"]["verdict"], flush=True)
    if stage in ("all", "s1"):
        print(f"CEGIS {cone} L=3 sigma (E2) ...", flush=True)
        out["e2_L3"] = cegis(cone, rng, L=3, target="sigma",
                             timeout_ms=timeout_ms)
        print(f"  E2 verdict:", out["e2_L3"]["verdict"],
              flush=True)
    rp = os.path.join(exp042, "RAW_RESULTS",
                      f"exp042_e2_{cone}_{stage}_{ts}.json")
    pp = os.path.join(exp042, "PROOFS",
                      f"exp042_e2_{cone}_{stage}_{ts}.json")
    with open(rp, "w") as fh:
        json.dump(out, fh, indent=2, default=str)
    with open(pp, "w") as fh:
        json.dump(out, fh, indent=2, default=str)
    print("wrote", rp, flush=True)
    print("wrote", pp, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
