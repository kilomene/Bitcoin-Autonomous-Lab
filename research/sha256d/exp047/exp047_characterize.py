#!/usr/bin/env python3
"""EXP-047 defect characterization (NOT the campaign).

The predeclared campaign stopped at its first mismatch:
search_first_counted on the v512 engine, case S_FULL-00
(genesis header, target 2^256 - 1, start 2083204125, count
65536), returned nonce 2083236893 where the predeclared
criterion expected the span minimum 2083204125. This script
characterizes that divergence: is the returned hit genuine, is
it deterministic, which backends can produce it, does the
found flag ever disagree with the reference, and does it
depend on thread count. Source mechanism: mining/cpu/
bal_search.h bal_ctx_publish is first-publisher-wins across
per-thread spans; every native search ABI uses it.

Writes RAW_RESULTS/characterization.json. Read-only against
production code, like the campaign.
"""

import json
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, REPO)

from gpu.engine import ComputeEngine, cpu_digest  # noqa: E402

GENESIS = bytes.fromhex(
    "01000000" + "00" * 32
    + "3ba3edfd7a7b12b27ac72c3e67768f617fc81bc3888a51323a9fb8aa4b1e5e4a"
    + "29ab5f49" + "ffff001d" + "1dac2b7c")
GENESIS_NONCE = 2083236893
T_FULL = (1 << 256) - 1
T_D8 = (1 << 248) - 1
T_D16 = (1 << 240) - 1
RESULTS = os.path.join(HERE, "RAW_RESULTS")

out = {"characterization_of": "EXP-047 S_FULL-00 v512 "
       "search_first divergence (mismatch.json)"}

# Part 1: the failing case, repeated, per native backend.
start = GENESIS_NONCE - 32768
count = 65536
part1 = {}
for name in ("v512dual", "v512", "shani", "avx2", "c"):
    eng = ComputeEngine(requested=name)
    tally = {"minimum": 0, "other_genuine": 0, "none": 0,
             "bad_digest": 0, "other_nonces": {}}
    for _ in range(200):
        hit, _a, _s = eng.search_first_counted(
            GENESIS, T_FULL, start, count)
        if hit is None:
            tally["none"] += 1
        elif hit[1] != cpu_digest(GENESIS, hit[0]):
            tally["bad_digest"] += 1
        elif hit[0] == start:
            tally["minimum"] += 1
        else:
            tally["other_genuine"] += 1
            k = str(hit[0] - start)
            tally["other_nonces"][k] = \
                tally["other_nonces"].get(k, 0) + 1
    tally["threads"] = eng.c_threads
    part1[name] = tally
    print("part1", name, json.dumps(tally), flush=True)
out["part1_failing_case_x200"] = part1

eng1 = ComputeEngine(requested="v512", threads=1)
tally = {"minimum": 0, "other_genuine": 0, "none": 0}
for _ in range(50):
    hit, _a, _s = eng1.search_first_counted(
        GENESIS, T_FULL, start, count)
    if hit is None:
        tally["none"] += 1
    elif hit[0] == start:
        tally["minimum"] += 1
    else:
        tally["other_genuine"] += 1
out["part1_v512_threads1_x50"] = tally
print("part1 v512 threads=1", json.dumps(tally), flush=True)

# Part 2 and 3: found-flag agreement and hit genuineness on
# random spans at production-like densities.
rng = random.Random(47048)


def probe(target, span_count, nspans, label):
    engines = {name: ComputeEngine(requested=name)
               for name in ("v512dual", "v512", "shani", "avx2",
                            "c", "cpu")}
    agg = {name: {"spans": 0, "found_agree": 0, "minimum": 0,
                  "other_genuine": 0, "false_hit": 0,
                  "false_miss": 0, "bad_digest": 0}
           for name in engines}
    for _ in range(nspans):
        hdr = rng.randbytes(80)
        st = rng.randrange(0, 1 << 24)
        want_min = None
        for i in range(span_count):
            d = cpu_digest(hdr, st + i)
            if int.from_bytes(d, "little") <= target:
                want_min = st + i
                break
        for name, eng in engines.items():
            rec = agg[name]
            rec["spans"] += 1
            hit, _a, _s = eng.search_first_counted(
                hdr, target, st, span_count)
            if want_min is None:
                if hit is None:
                    rec["found_agree"] += 1
                else:
                    rec["false_hit"] += 1
                continue
            if hit is None:
                rec["false_miss"] += 1
                continue
            rec["found_agree"] += 1
            if hit[1] != cpu_digest(hdr, hit[0]) \
                    or int.from_bytes(hit[1], "little") > target:
                rec["bad_digest"] += 1
            elif hit[0] == want_min:
                rec["minimum"] += 1
            else:
                rec["other_genuine"] += 1
    out[label] = agg
    print(label, json.dumps(agg), flush=True)


probe(T_D8, 65536, 24, "part2_T_D8_24_spans")
probe(T_D16, 262144, 8, "part3_T_D16_8_spans")

out["finished"] = time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                time.gmtime())
with open(os.path.join(RESULTS, "characterization.json"),
          "w") as f:
    json.dump(out, f, indent=1)
print("CHARACTERIZATION_COMPLETE", flush=True)
