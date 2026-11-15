#!/usr/bin/env python3
"""EXP-033 foundation tests (fast subset).

Re-checks, from scratch, the load-bearing facts the
EXP-033 report rests on:

  1. The reference implementation equals hashlib
     (SHA-256 and SHA-256d on headers).
  2. The two-round DAG evaluates exactly like the
     reference rounds and costs exactly 56 ops
     (rounds + schedule pair) under the EXP-020 model.
  3. W18 / W19 nonce-delta identities hold on random
     templates (exact arithmetic).
  4. The incumbent boundary-cone programs (6 ops each)
     compute the a-cone and e-cone targets on random
     inputs.

The heavy evidence (e-graph saturation and soundness,
z3 CEGIS at L=5, z3 identity proofs, 1e6-sample
differentials) lives in ../src and its outputs in
../RAW_RESULTS and ../PROOFS; this file is the quick
gate. Run with the lab z3 venv python.
"""

import hashlib
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(
    os.path.abspath(__file__)), "..", "src"))
from exp033_common import (M32, build_two_rounds, compress,
                           dag_cost, dag_eval, rotr,
                           sha256_ref)
from exp033_cone_synth import CONES, run_program


def main():
    rng = random.Random(4242)

    for _ in range(50):
        msg = bytes(rng.getrandbits(8)
                    for _ in range(rng.randrange(200)))
        assert sha256_ref(msg) == hashlib.sha256(msg).digest()
        hdr = bytes(rng.getrandbits(8) for _ in range(80))
        inner = hashlib.sha256(hdr).digest()
        assert sha256_ref(inner) == hashlib.sha256(
            inner).digest()
    print("1. reference == hashlib: OK")

    dag, roots = build_two_rounds(20)
    cost, _ = dag_cost(dag, roots["state"])
    assert cost == 56, cost
    for _ in range(500):
        block = [rng.getrandbits(32) for _ in range(16)]
        state0 = [rng.getrandbits(32) for _ in range(8)]
        W, states, _ = compress(state0, block)
        t0 = roots["t0"]
        env = {}
        for n, v in zip(["a", "b", "c", "d", "e", "f", "g",
                         "h"], states[t0]):
            env[n] = v
        for t in range(t0 - 16, t0):
            env[f"W{t}"] = W[t]
        got = dag_eval(dag, roots["state"], env)
        assert tuple(got) == states[t0 + 2]
    print("2. two-round DAG exact, cost 56: OK")

    def sched_words(template16, n):
        words = list(template16)
        words[3] = n
        W = list(words)
        for t in range(16, 21):
            s0 = rotr(W[t - 15], 7) ^ rotr(W[t - 15], 18) ^ \
                (W[t - 15] >> 3)
            s1 = rotr(W[t - 2], 17) ^ rotr(W[t - 2], 19) ^ \
                (W[t - 2] >> 10)
            W.append((W[t - 16] + s0 + W[t - 7] + s1) & M32)
        return W

    def s0(x):
        return rotr(x, 7) ^ rotr(x, 18) ^ (x >> 3)

    for _ in range(20000):
        tpl = [rng.getrandbits(32) for _ in range(16)]
        n = rng.getrandbits(32)
        W0 = sched_words(tpl, 0)
        Wn = sched_words(tpl, n)
        assert (Wn[18] - W0[18]) & M32 == s0(n)
        assert (Wn[19] - W0[19]) & M32 == n
    print("3. W18/W19 delta identities (20k samples): OK")

    for name, cone in CONES.items():
        for _ in range(20000):
            vals = tuple(rng.getrandbits(32) for _ in range(4))
            got = run_program(cone["incumbent"],
                              cone["incumbent_outputs"], vals)
            assert got == cone["target"](vals), name
    print("4. incumbent cone programs exact (20k each): OK")
    print("ALL EXP-033 FOUNDATION TESTS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
