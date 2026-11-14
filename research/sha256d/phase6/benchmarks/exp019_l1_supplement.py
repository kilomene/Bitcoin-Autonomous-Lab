#!/usr/bin/env python3
"""EXP-019 supplementary check: L1-resident operand streams.

The main price list streams b, c, d from 192 KB of arrays
(L2-resident). The production kernel's schedule operands
come from a 1 KB stack ring (L1-resident). This supplement
recompiles the same microbenchmark with DATA_VECTORS=128
(24 KB total, L1-resident) and re-prices separations
0, 1, 6, 10, 13, 15 under the same paired protocol
(3 sessions, 21 repeats), to test whether the wide
separation carry-save advantage seen in the main list is
a property of the forms or of the L2 streaming pattern.
Output: one append-only JSON under benchmarks/exp019/.
"""
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

import numpy as np

ROOT = "/home/hatch/workspace/bitcoin-autonomous-lab"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "exp019")
SRC = os.path.join(ROOT, "research/sha256d/phase6/src/"
                          "exp019_price_micro.c")
BINARY = "/tmp/exp019_price_micro_l1"
CC_CMD = ["gcc", "-O3", "-mavx512f", "-mavx512bw",
          "-DDATA_VECTORS=128", "-Wall", "-Wextra",
          "-o", BINARY, SRC]
ITERATIONS = 8192
REPEATS = 21
SEPARATIONS = [0, 1, 6, 10, 13, 15]
FORMS = ["current_serial", "balanced_tree", "cs1_resolved",
         "csfull_resolved", "sigma_led_cs1"]
BOOT = 10_000


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    subprocess.run(CC_CMD, check=True)
    verify = json.loads(subprocess.run(
        [BINARY, "verify"], capture_output=True, text=True,
        check=True).stdout.strip())
    assert verify["mismatches"] == 0, verify
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    blocks = []
    for s in range(1, 4):
        session_id = f"{stamp}_exp019_l1_s{s}"
        seed_base = int.from_bytes(
            hashlib.sha256(session_id.encode()).digest()[:8],
            "little")
        for separation in SEPARATIONS:
            out = subprocess.run(
                [BINARY, "bench", str(separation + 1),
                 str(ITERATIONS), str(REPEATS),
                 str(seed_base + separation)],
                capture_output=True, text=True,
                check=True).stdout
            for line in out.splitlines():
                block = json.loads(line)
                block["session_id"] = session_id
                blocks.append(block)
        print("l1 session done:", session_id, flush=True)
    ref = {}
    vals = {}
    med = {}
    for block in blocks:
        key = (block["session_id"], block["separation"],
               block["repeat"])
        med.setdefault((block["separation"], block["form"]),
                       []).append(block["ns_per_vector_op"])
        if block["form"] == "current_serial":
            ref[key] = block["ns_per_vector_op"]
        else:
            vals.setdefault((block["separation"],
                             block["form"]), []).append(
                (key, block["ns_per_vector_op"]))
    rng = np.random.default_rng(19020)
    table = []
    for separation in SEPARATIONS:
        row = {"separation": separation,
               "median_ns_per_vector_op": {
                   form: float(np.median(
                       med[(separation, form)]))
                   for form in FORMS},
               "relative_to_current_serial": {}}
        for form in FORMS[1:]:
            logs = np.array([np.log(v / ref[key])
                             for key, v in vals[(separation,
                                                 form)]])
            idx = rng.integers(0, len(logs),
                               size=(BOOT, len(logs)))
            means = logs[idx].mean(axis=1)
            lo, hi = np.percentile(means, [2.5, 97.5])
            row["relative_to_current_serial"][form] = {
                "pairs": int(len(logs)),
                "ratio_mean_log": float(np.exp(logs.mean())),
                "ci95": [float(np.exp(lo)), float(np.exp(hi))],
                "fraction_pairs_faster_than_current":
                    float(np.mean(logs < 0))}
        table.append(row)
        print(separation,
              {f: round(row["relative_to_current_serial"]
                        [f]["ratio_mean_log"], 3)
               for f in row["relative_to_current_serial"]})
    record = {"experiment": "EXP-019",
              "kind": "l1_resident_supplement",
              "generated_utc":
                  datetime.now(timezone.utc).isoformat(),
              "data_vectors": 128,
              "verification": verify,
              "price_list_l1": table,
              "blocks": blocks}
    path = os.path.join(OUT_DIR, f"supplement_l1_{stamp}.json")
    with open(path, "w") as fh:
        json.dump(record, fh, indent=1)
    print("supplement written:", path)


if __name__ == "__main__":
    sys.exit(main())
