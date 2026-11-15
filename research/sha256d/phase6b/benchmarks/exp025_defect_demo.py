#!/usr/bin/env python3
"""EXP-025 step 2: demonstrate the EXP-023 prototype's
fingerprint defect BEFORE repairing it.

Method: prepare the EXP-023 prototype
(phase6/benchmarks/exp023_amortized.py, unmodified) on a
base template, then present sibling templates whose
fingerprint (version, previousblockhash, bits, height,
coinbasevalue, tx count, first txid, last txid) is
UNCHANGED while a fingerprinted-out input changes. For
each case, compare the prototype's build() output
against a complete uncached reconstruction
(mining.engine.MiningEngine.build_candidate) on the
mutated template, with identical `now` injected into
both paths so the header time field is held equal.

A case is a DEMONSTRATED STALE SERVE when the prototype
accepts the sibling (no TemplateError) and its output
differs from the uncached reconstruction. A case is a
DEMONSTRATED VALIDATION BYPASS when the prototype
accepts a sibling that the uncached path rejects with
TemplateError. A case is OUTPUT-IRRELEVANT when the
prototype accepts and the outputs are byte-identical
(the gap is real in the fingerprint but cannot change
any output byte, with the reason recorded).

Cases:
  D1 middle transaction replaced (same fee, first and
     last untouched).
  D2 witness data of the FIRST transaction changed,
     txid held fixed (segwit), default witness
     commitment updated to the correct new value.
  D3 two middle transactions reordered.
  D4 coinbaseaux flags changed.
  D5 target changed (returned metadata field).
  D6 one fee raised, coinbasevalue NOT adjusted
     (uncached path must reject; prototype serves).
  D7 default_witness_commitment replaced by a wrong
     value, everything else fixed (uncached rejects;
     prototype serves).
  D8 fee moved between two transactions, total and
     coinbasevalue fixed (expected output-irrelevant:
     fees enter the output only through their sum).

Controls (must NOT demonstrate a defect):
  C1 curtime advanced only: read fresh per build by
     both paths, outputs identical by construction
     when `now` is held equal.
  C2 height changed: inside the fingerprint, the
     prototype must raise.

Output: append-only JSON record under benchmarks/exp025/.
"""
import copy
import json
import os
import random
import struct
import sys
from datetime import datetime, timezone

ROOT = "/home/hatch/workspace/bitcoin-autonomous-lab"
HERE = os.path.dirname(os.path.abspath(__file__))
P6 = os.path.join(ROOT, "research/sha256d/phase6/benchmarks")
OUT_DIR = os.path.join(HERE, "exp025")
sys.path.insert(0, P6)
sys.path.insert(0, ROOT)

from exp023_amortized import (FamilyContext, PAYOUT,  # noqa: E402
                              PreparedTemplate, StubRPC,
                              synth_template, synth_tx)
from mining.engine import (MiningEngine, TemplateError,  # noqa: E402
                           txid_of, wtxid_of)
from mining.pow import dsha256, merkle_root  # noqa: E402

NOW = 2_000_000_000
ZERO32 = b"\x00" * 32
RESERVED = b"\x00" * 32


def commitment_hex(template):
    wtxids = [wtxid_of(bytes.fromhex(tx["data"]))
              for tx in template["transactions"]]
    wroot = merkle_root([ZERO32] + wtxids)
    return "6a24aa21a9ed" + dsha256(wroot + RESERVED).hex()


def outputs_differ(a, b):
    diffs = []
    for k in ("header", "body"):
        if a[k] != b[k]:
            diffs.append(k)
    for k in ("target", "height", "fees", "tx_count",
              "witness_count"):
        if a[k] != b[k]:
            diffs.append(k)
    return diffs


def run_case(name, base, mutated, eng, fam):
    prep = PreparedTemplate(fam, base)
    fp_same = prep._fingerprint(mutated) == prep.fingerprint
    uncached = None
    uncached_error = None
    try:
        uncached = eng.build_candidate(mutated, 0)
    except TemplateError as exc:
        uncached_error = str(exc)
    proto = None
    proto_error = None
    import time as _time
    real_time = _time.time
    _time.time = lambda: NOW
    try:
        proto = prep.build(0, template=mutated, now=NOW)
    except TemplateError as exc:
        proto_error = str(exc)
    finally:
        _time.time = real_time
    # build_candidate reads time.time() internally; rerun
    # it under the same frozen clock for an exact compare.
    if uncached_error is None:
        _time.time = lambda: NOW
        try:
            uncached = eng.build_candidate(mutated, 0)
        finally:
            _time.time = real_time
    rec = {"case": name, "fingerprint_unchanged": fp_same,
           "prototype_error": proto_error,
           "uncached_error": uncached_error}
    if proto is not None and uncached is not None:
        diffs = outputs_differ(proto, uncached)
        rec["differing_fields"] = diffs
        rec["verdict"] = ("STALE_SERVE" if diffs
                           else "OUTPUT_IRRELEVANT")
    elif proto is not None and uncached_error is not None:
        rec["verdict"] = "VALIDATION_BYPASS"
    elif proto_error is not None:
        rec["verdict"] = "PROTOTYPE_RAISES"
    else:
        rec["verdict"] = "BOTH_RAISE"
    print(f"{name}: fingerprint_unchanged={fp_same} "
          f"verdict={rec['verdict']} "
          f"diffs={rec.get('differing_fields')}", flush=True)
    return rec


def main():
    rng = random.Random(25025)
    stub = StubRPC()
    eng = MiningEngine(stub, PAYOUT)
    fam = FamilyContext(stub, PAYOUT)
    base = synth_template(rng, 10, segwit_fraction=0.5,
                          with_commitment=True)
    stub.template = base
    results = []

    # D1: middle tx replaced, same fee.
    mut = copy.deepcopy(base)
    raw = synth_tx(rng, segwit=False)
    fee = mut["transactions"][4]["fee"]
    mut["transactions"][4] = {"txid": txid_of(raw)[::-1].hex(),
                              "data": raw.hex(), "fee": fee}
    mut["default_witness_commitment"] = commitment_hex(mut)
    results.append(run_case("D1_middle_tx_replaced", base, mut,
                            eng, fam))

    # D2: witness bytes of a segwit tx mutated, txid fixed.
    # The mutated transaction is whichever segwit tx comes
    # first in the base template; its txid (a fingerprint
    # field when it sits first or last) does not move.
    mut = copy.deepcopy(base)
    idx = next(i for i, tx in enumerate(mut["transactions"])
               if bytes.fromhex(tx["data"])[4:6] == b"\x00\x01")
    first = mut["transactions"][idx]
    raw0 = bytes.fromhex(first["data"])
    # synth segwit tail: [count=1][len=20][wit 20][locktime 4]
    mut_raw = bytearray(raw0)
    mut_raw[-24] ^= 0xFF
    mut_raw = bytes(mut_raw)
    assert txid_of(mut_raw) == txid_of(raw0), "txid must not move"
    assert wtxid_of(mut_raw) != wtxid_of(raw0)
    first["data"] = mut_raw.hex()
    mut["default_witness_commitment"] = commitment_hex(mut)
    results.append(run_case(f"D2_witness_only_tx_index_{idx}",
                            base, mut, eng, fam))

    # D3: reorder two middle transactions (commitment
    # field updated to the reordered set's correct value,
    # as a real GBT response for that set would carry).
    mut = copy.deepcopy(base)
    txs = mut["transactions"]
    txs[2], txs[3] = txs[3], txs[2]
    mut["default_witness_commitment"] = commitment_hex(mut)
    results.append(run_case("D3_reorder_middle", base, mut,
                            eng, fam))

    # D4: coinbaseaux flags changed.
    mut = copy.deepcopy(base)
    mut["coinbaseaux"] = {"flags": "abcd"}
    results.append(run_case("D4_flags_changed", base, mut,
                            eng, fam))

    # D5: target changed.
    mut = copy.deepcopy(base)
    mut["target"] = "0" * 8 + "f" * 56
    results.append(run_case("D5_target_changed", base, mut,
                            eng, fam))

    # D6: fee raised, coinbasevalue not adjusted.
    mut = copy.deepcopy(base)
    mut["transactions"][3]["fee"] += 100
    results.append(run_case("D6_fee_up_value_fixed", base, mut,
                            eng, fam))

    # D7: wrong default witness commitment.
    mut = copy.deepcopy(base)
    mut["default_witness_commitment"] = "6a24aa21a9ed" + "00" * 32
    results.append(run_case("D7_wrong_commitment_field", base,
                            mut, eng, fam))

    # D8: fee moved between txs, total fixed.
    mut = copy.deepcopy(base)
    mut["transactions"][1]["fee"] += 250
    mut["transactions"][2]["fee"] -= 250
    results.append(run_case("D8_fee_moved_total_fixed", base, mut,
                            eng, fam))

    # C1: curtime advanced only.
    mut = copy.deepcopy(base)
    mut["curtime"] = base["curtime"] + 600
    results.append(run_case("C1_curtime_only", base, mut, eng, fam))

    # C2: height changed (inside fingerprint).
    mut = copy.deepcopy(base)
    mut["height"] = base["height"] + 1
    from mining.pow import coinbase_subsidy
    fees = sum(tx["fee"] for tx in mut["transactions"])
    mut["coinbasevalue"] = coinbase_subsidy(mut["height"], 150) + fees
    results.append(run_case("C2_height_changed", base, mut, eng, fam))

    stale = [r for r in results if r["verdict"] == "STALE_SERVE"]
    bypass = [r for r in results
              if r["verdict"] == "VALIDATION_BYPASS"]
    record = {
        "experiment": "EXP-025",
        "step": "defect demonstration against the EXP-023 "
                "prototype (unmodified)",
        "recorded_utc": datetime.now(timezone.utc).isoformat(),
        "host_cpu": open("/proc/cpuinfo").read().split(
            "model name")[1].split(":")[1].split("\n")[0].strip(),
        "prototype": "research/sha256d/phase6/benchmarks/"
                     "exp023_amortized.py",
        "cases": results,
        "stale_serve_cases": [r["case"] for r in stale],
        "validation_bypass_cases": [r["case"] for r in bypass],
        "defect_demonstrated": bool(stale or bypass),
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(OUT_DIR, f"defect_demo_{stamp}.json")
    suffix = 2
    while os.path.exists(path):
        path = os.path.join(OUT_DIR, f"defect_demo_{stamp}_r{suffix}.json")
        suffix += 1
    with open(path, "x") as fh:
        json.dump(record, fh, indent=2)
    print(f"stale={len(stale)} bypass={len(bypass)}")
    print(f"wrote {path}")
    return 0 if record["defect_demonstrated"] else 1


if __name__ == "__main__":
    sys.exit(main())
