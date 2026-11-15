#!/usr/bin/env python3
"""EXP-027 extension of the Phase 6 discovery harness.

New file, per the Phase 6B rule that the harness of record
(phase6/src/discovery_harness.py) is extended, never
silently replaced. Three automated searches over
vocabularies outside the one EXP-020 closed:

  S1  Exhaustive single-instruction byte-shuffle search:
      every per-dword VPSHUFB pattern (each output byte is
      one of the 4 input bytes or zero; 5^4 = 625 patterns)
      tested against ROTR13 and against Sigma0 on a
      discriminating input set. A pattern survives only if
      it matches on every test input.
  S2  Byte-locality check for single-instruction GFNI:
      computes the input-byte dependency set of every
      Sigma0 output byte. A per-byte affine instruction
      (any matrix, any constant, any preceding shuffle)
      makes each output byte a function of exactly one
      input byte, so a non-local target refutes the whole
      single-instruction class without enumerating the
      2^64 matrices.
  S3  Extended-vocabulary extraction table: for each cone,
      the best construction cost under the EXP-020
      vocabulary and under each extension (GFNI, VPSHUFB,
      carry-save at the EXP-019 corrected price of 3,
      VPMADD52 accumulation), from the constructive forms
      and floors established in EXP-027. Costs are op
      counts under the phase cost model; the vocabulary
      of every number is stated in the record.

Output: phase6b/proofs/exp027_vocab_search_<stamp>.json.
Run with the lab z3 venv python (for the harness import's
proof gate spot-check).
"""

import itertools
import json
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
PHASE6 = os.path.dirname(HERE)
REPO = os.path.abspath(os.path.join(
    HERE, "..", "..", "..", ".."))
PHASE6B = os.path.join(REPO, "research", "sha256d", "phase6b")
sys.path.insert(0, HERE)

M32 = 0xFFFFFFFF


def rotr(x, n):
    return ((x >> n) | (x << (32 - n))) & M32


def S0(x):
    return rotr(x, 2) ^ rotr(x, 13) ^ rotr(x, 22)


def discriminating_set():
    vals = [0, 1, M32, 0x12345678, 0x9E3779B9, 1359758873]
    vals += [1 << j for j in range(32)]
    st = 0x2545F491
    for _ in range(10000):
        st ^= (st << 13) & M32
        st ^= st >> 17
        st ^= (st << 5) & M32
        vals.append(st & M32)
    return vals


def apply_pattern(x, pat):
    out = 0
    for p in range(4):
        src = pat[p]
        if src < 4:
            out |= ((x >> (8 * src)) & 0xFF) << (8 * p)
    return out


def search_shuffle(target, name):
    vals = discriminating_set()
    survivors = 0
    for pat in itertools.product(range(5), repeat=4):
        ok = True
        for v in vals:
            if apply_pattern(v, pat) != target(v):
                ok = False
                break
        if ok:
            survivors += 1
    return {"target": name, "patterns_tested": 625,
            "test_inputs": len(vals), "survivors": survivors}


def byte_locality():
    dep = {ob: set() for ob in range(4)}
    for j in range(32):
        y = S0(1 << j)
        for ob in range(4):
            if (y >> (8 * ob)) & 0xFF:
                dep[ob].add(j // 8)
    return {"Sigma0_output_byte_input_bytes":
            {str(k): sorted(v) for k, v in dep.items()},
            "byte_local": all(len(v) == 1 for v in dep.values())}


# Extraction table. V0 = the EXP-020 vocabulary
# {VPADDD, VPTERNLOGD, classic bitwise, VPROLD, VPSRLD}.
# Extensions add one instruction class each. Numbers are
# op counts of the best construction found by EXP-027
# (constructive) or the proven floor where stated.
EXTRACTION = [
    {"cone": "Sigma0 / Sigma1 (per round)",
     "V0_exp020_vocab": 4,
     "plus_GFNI": {"floor": 11, "constructive": 35,
                   "note": "floor: every output byte depends "
                           "on all 4 input bytes (S2), so at "
                           "least 4 partial vectors, each at "
                           "least a shuffle plus a GFNI, plus "
                           "3 XOR combines. Constructive: 4 "
                           "byte slices x (1 broadcast + 4 "
                           "GFNI + 3 byte blends) + 3 XOR."},
     "plus_VPSHUFB": {"best": 10,
                      "note": "3 rotations in shuffle form "
                              "at 4 ops each would be 12; the "
                              "best mixed form keeps VPROLD. "
                              "Pure shuffle rotation measured "
                              "at 2.00x the VPROLD price."},
     "plus_carrysave": "not applicable (no addition)",
     "plus_VPMADD52": "not applicable (no addition)"},
    {"cone": "sigma0 / sigma1 (per schedule word)",
     "V0_exp020_vocab": 4,
     "plus_GFNI": {"floor": 11, "constructive": 35,
                   "note": "same linearity and dependency "
                           "shape as Sigma0 (L1, L2 method)"},
     "plus_VPSHUFB": {"best": 10, "note": "as Sigma0"},
     "plus_carrysave": "not applicable (no addition)",
     "plus_VPMADD52": "not applicable (no addition)"},
    {"cone": "ROTR by a non-byte-multiple amount",
     "V0_exp020_vocab": 1,
     "plus_GFNI": "refuted (single affine is per-byte; a "
                  "rotation is not byte-local)",
     "plus_VPSHUFB": {"best": 4,
                      "note": "shuffle + 2 shifts + OR; "
                              "measured 2.00x the VPROLD "
                              "price (exp027 micro)"},
     "plus_carrysave": "not applicable",
     "plus_VPMADD52": "not applicable"},
    {"cone": "Ch / Maj",
     "V0_exp020_vocab": 1,
     "plus_GFNI": "refuted for every affine form "
                  "(non-affinity counterexamples, L1)",
     "plus_VPSHUFB": "no form (bitwise cone, bytes are "
                     "not permuted by Ch or Maj)",
     "plus_carrysave": "not applicable",
     "plus_VPMADD52": "not applicable"},
    {"cone": "T1 five-operand sum",
     "V0_exp020_vocab": 4,
     "plus_GFNI": "not applicable (arithmetic cone)",
     "plus_VPSHUFB": "not applicable",
     "plus_carrysave": {"best": 6,
                        "note": "one carry-save level at "
                                "the corrected compressor "
                                "price 3, then 3 VPADDD "
                                "(EXP-020 pricing table); "
                                "two levels cost 8"},
     "plus_VPMADD52": {"best": 5,
                       "note": "4 VPMADD52LUQ accumulations "
                               "into a 52-bit accumulator "
                               "plus 1 mask to 32 bits; "
                               "exactness proven (L6) and "
                               "differential-tested at "
                               "1,000,000 samples"}},
    {"cone": "schedule four-operand sum",
     "V0_exp020_vocab": 3,
     "plus_GFNI": "not applicable (arithmetic cone)",
     "plus_VPSHUFB": "not applicable",
     "plus_carrysave": {"best": 5,
                        "note": "EXP-019/EXP-020 pricing; "
                                "measured loser at every "
                                "forced-resolution separation"},
     "plus_VPMADD52": {"best": 4,
                       "note": "3 accumulations + 1 mask; "
                               "same exactness argument as "
                               "T1, one fewer operand"}},
    {"cone": "full round + schedule (joint census)",
     "V0_exp020_vocab": 28,
     "extensions_combined": "no extension lowers any cone "
                            "in the table, so no combined "
                            "extraction below 28 exists "
                            "within the searched forms; "
                            "this is a statement about the "
                            "stated vocabularies and "
                            "constructions, not a global "
                            "lower bound"},
]


def main():
    rec = {"experiment": "EXP-027",
           "kind": "extended-vocabulary automated search",
           "generated_utc": datetime.now(timezone.utc).strftime(
               "%Y-%m-%dT%H:%M:%SZ"),
           "harness_extended": "discovery_harness.py "
                               "(unmodified) + this file"}
    with open("/proc/cpuinfo") as fh:
        for line in fh:
            if line.startswith("model name"):
                rec["cpu"] = line.split(":", 1)[1].strip()
                break
    rec["S1_shuffle_search"] = [
        search_shuffle(lambda x: rotr(x, 13), "ROTR13"),
        search_shuffle(S0, "Sigma0"),
    ]
    print("S1 done", flush=True)
    rec["S2_byte_locality"] = byte_locality()
    print("S2 done", flush=True)
    # Spot-check: the unmodified harness still proves the
    # EXP-012 ternlog forms (the extension did not disturb
    # the base tooling).
    import discovery_harness as dh
    x, y, z = dh.V("x"), dh.V("y"), dh.V("z")
    imm_ch = dh.ternlog_imm(
        lambda env: (env["x"] & env["y"])
        ^ ((1 - env["x"]) & env["z"]), ("x", "y", "z"))
    rec["S3_harness_spotcheck"] = {
        "Ch_ternlog_imm": imm_ch,
        "Ch_proof": "z3 UNSAT" if dh.prove_equiv(
            dh.ch_ref(), ("ternlog", imm_ch, x, y, z),
            ["x", "y", "z"]) else "FAILED",
    }
    rec["S3_extraction_table"] = EXTRACTION
    os.makedirs(os.path.join(PHASE6B, "proofs"), exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(PHASE6B, "proofs",
                        "exp027_vocab_search_%s.json" % stamp)
    with open(path, "w") as fh:
        json.dump(rec, fh, indent=2)
    print("wrote", path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
