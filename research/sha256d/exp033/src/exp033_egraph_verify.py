#!/usr/bin/env python3
"""EXP-033 scope 1a verification: independent soundness
check of the saturated e-graphs from exp033_egraph.py.

Method (inductive): fix one representative enode per
e-class. Define F(enode) by structural evaluation where
child classes are evaluated through their representatives.
For every root-reachable class, every enode in the class
must agree with the class representative on random inputs.
Separately, the root representatives must reproduce the
reference two-round map (exp033_common.compress). If both
hold, every enode in every reachable class computes the
incumbent function, so the saturation introduced no false
equivalence, and the extraction comparisons in the main
run are meaningful.

Writes RAW_RESULTS/exp033_egraph_verify_<ts>.json.
"""

import json
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from exp033_common import (M32, build_two_rounds, compress,
                           lut_eval, rotr)
from exp033_egraph import (EGraph, build_two_rounds_only,
                           enode_children, load_dag, saturate)

HERE = os.path.dirname(os.path.abspath(__file__))
EXP033 = os.path.dirname(HERE)


def eval_enode(eg, en, reps, env, memo):
    op = en[0]
    if op == "in":
        return env[en[1]]
    if op == "const":
        return en[1]

    def child(cls):
        cls = eg.find(cls)
        if cls not in memo:
            memo[cls] = eval_enode(eg, reps[cls], reps, env,
                                   memo)
        return memo[cls]

    if op == "add":
        return (child(en[1]) + child(en[2])) & M32
    if op == "rotr":
        return rotr(child(en[2]), en[1])
    if op == "shr":
        return child(en[2]) >> en[1]
    if op == "shl":
        return (child(en[2]) << en[1]) & M32
    if op == "lut":
        return lut_eval(en[1], child(en[2]), child(en[3]),
                        child(en[4]))
    raise ValueError(op)


def verify_case(label, dag, roots, rng, trials=300):
    eg = EGraph()
    ids = load_dag(eg, dag)
    eg.rebuild()
    saturate(eg, log=lambda *a: None)
    root_reps = [eg.find(ids[i]) for i in roots["state"]]
    reps = {}
    for rep, ens in eg.class_enodes.items():
        if eg.find(rep) == rep:
            reps[rep] = next(iter(ens))
    # reachable classes via representatives
    reach = set()
    stack = list(root_reps)
    while stack:
        r = eg.find(stack.pop())
        if r in reach:
            continue
        reach.add(r)
        for ch in enode_children(reps[r]):
            stack.append(ch)
    names = roots["inputs"]
    checked_enodes = 0
    mismatches = 0
    for trial in range(trials):
        env = {n: rng.getrandbits(32) for n in names}
        memo = {}
        base = {r: eval_enode(eg, reps[r], reps, env, {})
                for r in reach}
        for r in reach:
            for en in eg.class_enodes[r]:
                if en == reps[r]:
                    continue
                memo = {}
                v = eval_enode(eg, en, reps, env, memo)
                checked_enodes += 1
                if v != base[r]:
                    mismatches += 1
    return {
        "case": label,
        "classes_total": len(reps),
        "classes_reachable": len(reach),
        "enode_evaluations": checked_enodes,
        "mismatches": mismatches,
        "trials": trials,
    }


def anchor_check(label, dag, roots, rng, trials=200):
    """Root representatives of the saturated graph must
    reproduce the reference two-round map exactly."""
    eg = EGraph()
    ids = load_dag(eg, dag)
    eg.rebuild()
    saturate(eg, log=lambda *a: None)
    root_reps = [eg.find(ids[i]) for i in roots["state"]]
    reps = {}
    for rep, ens in eg.class_enodes.items():
        if eg.find(rep) == rep:
            reps[rep] = next(iter(ens))
    bad = 0
    for _ in range(trials):
        block = [rng.getrandbits(32) for _ in range(16)]
        state0 = [rng.getrandbits(32) for _ in range(8)]
        W, states, _ = compress(state0, block)
        t0 = roots["t0"]
        env = {}
        for n, v in zip(["a", "b", "c", "d", "e", "f", "g", "h"],
                        states[t0]):
            env[n] = v
        if "Wt" in roots.get("inputs", []):
            env["Wt"] = W[t0]
            env["Wt1"] = W[t0 + 1]
        else:
            for t in range(t0 - 16, t0):
                env[f"W{t}"] = W[t]
        got = [eval_enode(eg, reps[r], reps, env, {})
               for r in root_reps]
        if tuple(got) != states[t0 + 2]:
            bad += 1
    return {"case": label, "anchor_trials": trials,
            "anchor_mismatches": bad}


def main():
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    rng = random.Random(777)
    dag, roots = build_two_rounds(20)
    res1 = verify_case("two_rounds_plus_schedule_pair",
                       dag, roots, rng, trials=120)
    print(res1)
    anc1 = anchor_check("two_rounds_plus_schedule_pair",
                        dag, roots, rng)
    print(anc1)
    dag2, roots2 = build_two_rounds_only()
    roots2 = dict(roots2)
    roots2["inputs"] = ["a", "b", "c", "d", "e", "f", "g", "h",
                        "Wt", "Wt1"]
    roots2["t0"] = 20
    res2 = verify_case("two_rounds_only", dag2, roots2, rng,
                       trials=300)
    print(res2)
    anc2 = anchor_check("two_rounds_only", dag2, roots2, rng)
    print(anc2)
    out = {"experiment": "EXP-033 egraph soundness check",
           "timestamp_utc": ts, "cases": [res1, res2],
           "anchors": [anc1, anc2],
           "sound": res1["mismatches"] == 0 and
                    res2["mismatches"] == 0 and
                    anc1["anchor_mismatches"] == 0 and
                    anc2["anchor_mismatches"] == 0}
    rp = os.path.join(EXP033, "RAW_RESULTS",
                      f"exp033_egraph_verify_{ts}.json")
    with open(rp, "w") as fh:
        json.dump(out, fh, indent=2)
    print("wrote", rp)
    return 0 if out["sound"] else 1


if __name__ == "__main__":
    sys.exit(main())
