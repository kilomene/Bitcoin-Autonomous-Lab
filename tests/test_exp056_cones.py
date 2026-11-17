#!/usr/bin/env python3
"""EXP-056 regression suite: H-033-02 residual cone
closure attempt (NOVA-ER-0016).

Layers, in order:

  1. Predeclaration hash pinned and verified.
  2. Canonicalisation soundness: random concrete
     programs evaluate identically in the EXP-033
     representation and in the canonical 3-slot
     representation (C1 and C2 preserve values).
  3. Incumbent differentials: 100,000 random inputs
     per cone, 0 mismatches (the regression form of
     the campaign's 1,000,000-sample gates).
  4. Campaign record consistency: the checkpoint
     shows the gates passed, the SAT control passed,
     Stage A unknown at iteration 0 for both cones,
     Stage B closed exactly profiles 0, 1, 2, 3, 7,
     8, 9 per cone, no SAT candidate, and solver wall
     inside the predeclared 6,600 s box (plus the
     60 s slack). The campaign verdict is
     INCONCLUSIVE at the budget: H-033-02 stays open,
     narrowed by the closed profiles.
  5. The H-033-02 hypothesis registry entry carries
     the dated EXP-056 update note and its status is
     unchanged (UNPROVEN BREAKTHROUGH).

The solver campaign itself is NOT rerun here: it is
the campaign of record in research/sha256d/exp056/
(exp056_campaign.py), checkpointed in RAW_RESULTS.
This suite is the regression form. It must be run
with the lab venv python (.local/z3venv), which
provides z3, as the campaign was.

No em dash characters anywhere in this file.
"""

import json
import os
import random
import sys

ROOT = "/home/hatch/workspace/bitcoin-autonomous-lab"
EXP056 = os.path.join(ROOT, "research/sha256d/exp056")
sys.path.insert(0, os.path.join(EXP056, "src"))

import exp056_cone_synth as es  # noqa: E402
import exp033_cone_synth as cs  # noqa: E402

CHECKS = 0
CLOSED = [0, 1, 2, 3, 7, 8, 9]


def check(cond, label):
    global CHECKS
    CHECKS += 1
    if not cond:
        raise AssertionError("check failed: %s" % label)
    print("ok %d: %s" % (CHECKS, label), flush=True)


def main():
    es.check_predeclaration()
    check(True, "predeclaration hash pinned and verified")

    profs = es.all_profiles()
    check(len(profs) == 56 and profs[0] == (5, 0, 0, 0)
          and all(sum(p) == 5 for p in profs),
          "56 op-kind profiles in the predeclared order")

    rng = random.Random(20261122)
    bad = 0
    for _ in range(200):
        L = 5
        prog = []
        for i in range(L):
            op = rng.randrange(4)
            n_avail = 4 + i
            if op == cs.OP_ADD:
                prog.append((op, (rng.randrange(n_avail),
                                  rng.randrange(n_avail)),
                             None, None))
            elif op == cs.OP_LUT:
                prog.append((op, tuple(
                    rng.randrange(n_avail)
                    for _ in range(3)),
                    rng.randrange(256), None))
            else:
                prog.append((op, (rng.randrange(n_avail),),
                             None, rng.randrange(1, 32)))
        outs = tuple(rng.randrange(4, 4 + L)
                     for _ in range(3))
        cp, co = es.canonicalize_program(prog, outs)
        for _ in range(50):
            vals = tuple(rng.getrandbits(32)
                         for _ in range(4))
            if cs.run_program(prog, outs, vals) != \
                    es.run_program_canon(cp, co, vals):
                bad += 1
    check(bad == 0,
          "canonicalisation preserves values on 200 "
          "random programs x 50 inputs")

    for name, cone in cs.CONES.items():
        bad = 0
        for _ in range(100000):
            vals = tuple(rng.getrandbits(32)
                         for _ in range(4))
            if cs.run_program(cone["incumbent"],
                              cone["incumbent_outputs"],
                              vals) != cone["target"](vals):
                bad += 1
        check(bad == 0,
              "%s incumbent differential 100k clean"
              % name)

    with open(os.path.join(
            EXP056, "RAW_RESULTS",
            "exp056_checkpoint.json")) as fh:
        ck = json.load(fh)
    check(ck["gates"].get("done")
          and ck["gates"]["a_cone_differential_1e6_bad"]
          == 0
          and ck["gates"]["e_cone_differential_1e6_bad"]
          == 0
          and ck["gates"]["a_cone_incumbent_z3"]
          == "unsat"
          and ck["gates"]["e_cone_incumbent_z3"]
          == "unsat",
          "campaign gates passed (1e6 differentials, "
          "z3 exact incumbents)")
    check(ck["control"].get("passed") is True,
          "campaign SAT control passed (planted P5 "
          "found and proven equivalent)")
    for cone in ("a_cone", "e_cone"):
        iters = ck["cones"][cone]["stageA"]["iterations"]
        check(len(iters) == 1
              and iters[0]["verdict"] == "unknown",
              "%s stage A unknown at iteration 0" % cone)
        sb = ck["cones"][cone]["stageB"]
        check(sb.get("closed_profiles") == CLOSED
              and len(sb.get("profiles", {})) == 12,
              "%s stage B closed profiles %s of 12 "
              "queried" % (cone, CLOSED))
        check(not ck["cones"][cone].get("closed"),
              "%s not closed (H-033-02 stays open)"
              % cone)
    check(ck["sat_candidate"] is None,
          "no SAT candidate was produced")
    check(ck["solver_wall_s"] <= 6600.0 + 60.0,
          "solver wall %.1fs inside the predeclared "
          "box" % ck["solver_wall_s"])

    with open(os.path.join(
            ROOT, "research/sha256d/exp033",
            "HYPOTHESIS_REGISTRY.json")) as fh:
        reg = json.load(fh)
    h = [x for x in reg["hypotheses"]
         if x["id"] == "H-033-02"][0]
    check(h["status"] == "UNPROVEN BREAKTHROUGH"
          and "exp056_update_2026_11_17" in h,
          "H-033-02 registry note appended, status "
          "unchanged")
    print("EXP-056 suite: %d checks, ALL PASSED"
          % CHECKS, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
