#!/usr/bin/env python3
"""EXP-042 catch-all: rerun the EXP-033 full-cone CEGIS
at L = 5 with the small seed the EXP-033 script now
uses (the EXP-033 run that timed out used an 82-example
seed at a 600 s timeout under heavier contention).

This driver imports the EXP-033 module unchanged and
only raises the per-query timeout and records wall
times. A synthesis UNSAT here refutes H-033-02 for the
chosen cone with no decomposition assumptions. A SAT
candidate is verified by the EXP-033 exact z3 check
inside its cegis loop; any program reported found is
additionally differentially tested in plain Python by
this driver before the result is read.

Usage: exp042_fullcone.py <a_cone|e_cone> <timeout_ms>

No em dash characters anywhere in this file.
"""

import json
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
EXP042 = os.path.dirname(HERE)
EXP033_SRC = os.path.join(
    os.path.dirname(os.path.dirname(HERE)), "exp033", "src")
sys.path.insert(0, EXP033_SRC)

import exp033_cone_synth as cs


def main():
    cone = sys.argv[1] if len(sys.argv) > 1 else "a_cone"
    timeout_ms = int(sys.argv[2]) if len(sys.argv) > 2 \
        else 1500000
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    rng = random.Random(20261118)

    orig_synth = cs.synth_query

    def synth_timed(c, L, examples):
        return orig_synth(c, L, examples,
                          timeout_ms=timeout_ms)

    cs.synth_query = synth_timed
    print(f"EXP-042 full-cone CEGIS {cone} L=5, per-query "
          f"timeout {timeout_ms} ms", flush=True)
    t0 = time.time()
    res = cs.cegis(cone, 5, rng)
    wall = time.time() - t0
    print(f"full-cone {cone} verdict:", res["verdict"],
          f"wall {wall:.1f}s", flush=True)
    out = {"experiment": "EXP-042 full-cone catch-all",
           "timestamp_utc": ts, "cone": cone, "L": 5,
           "host": "AMD EPYC 9D25",
           "per_query_timeout_ms": timeout_ms,
           "wall_s": wall,
           "result": {k: v for k, v in res.items()
                      if k != "examples"}}
    if res["verdict"] == "program_found_and_proven":
        # Independent plain-Python differential of the
        # found program against the cone target.
        prog = [tuple(p) for p in res["program"]]
        outputs = tuple(res["outputs"])
        target = cs.CONES[cone]["target"]
        bad = 0
        for _ in range(1000000):
            vals = tuple(rng.getrandbits(32)
                         for _ in range(4))
            if cs.run_program(prog, outputs, vals) \
                    != target(vals):
                bad += 1
        out["independent_python_differential_1e6_bad"] = bad
        print("independent differential 1e6: bad =", bad,
              flush=True)
    rp = os.path.join(EXP042, "RAW_RESULTS",
                      f"exp042_fullcone_{cone}_{ts}.json")
    with open(rp, "w") as fh:
        json.dump(out, fh, indent=2, default=str)
    print("wrote", rp, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
