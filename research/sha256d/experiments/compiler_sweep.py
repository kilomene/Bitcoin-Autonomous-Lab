#!/usr/bin/env python3
"""EXP-001: compiler and flag sweep on the production C source.

Builds mining/cpu/bal_batch.c under several compiler flag sets,
verifies every variant differentially against hashlib (100,000
digests) and the genesis search, inspects the generated code, and
benchmarks each variant with the shared harness (bench_harness.py)
under identical conditions (2 threads, the production tuned count;
1 thread also recorded). Production is never touched: variants are
built into .local/shax/ and only measured.

Decision rule: a variant is a candidate for integration only if
its median beats the production-flag median AND the min/max
spreads do not overlap. Otherwise the verdict is reject or
inconclusive on this VM, and production stays byte-identical.

Usage: python3 research/sha256d/experiments/compiler_sweep.py
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bench_harness as bh  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
SRC = os.path.join(ROOT, "mining", "cpu", "bal_batch.c")
INCDIR = os.path.join(ROOT, "mining", "cpu")
OUTDIR = os.path.join(ROOT, ".local", "shax")

VARIANTS = {
    "prod_o3_native": ["-O3", "-march=native"],
    "o2_native": ["-O2", "-march=native"],
    "o3_generic": ["-O3", "-march=x86-64"],
    "o3_native_lto": ["-O3", "-march=native", "-flto"],
    "o3_native_unroll": ["-O3", "-march=native", "-funroll-loops"],
}
COMMON = ["-shared", "-fPIC", "-Wno-deprecated-declarations"]


def build(name, flags):
    os.makedirs(OUTDIR, exist_ok=True)
    out = os.path.join(OUTDIR, f"bal_batch_{name}.so")
    cmd = (["gcc"] + flags + COMMON + ["-I", INCDIR, SRC, "-o", out,
                                      "-lcrypto", "-pthread"])
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return out, proc.returncode, proc.stderr.strip()[-400:]


def asm_notes(path):
    dis = subprocess.run(["objdump", "-d", path], capture_output=True,
                         text=True).stdout
    m = re.search(r"<hash_nonce>:(.*?)(?=\n\n|\Z)", dis, re.S)
    notes = {"sha256rnds2_in_this_library": dis.count("sha256rnds2"),
             "sha256_transform_calls": dis.count("SHA256_Transform")}
    if m:
        body = m.group(1)
        notes["hash_nonce_instructions"] = body.count("\n")
        spill = re.search(r"sub\s+\$0x([0-9a-f]+),%rsp", body)
        notes["hash_nonce_stack_frame_bytes"] = (
            int(spill.group(1), 16) if spill else 0)
    return notes


def main():
    results = {"experiment": "EXP-001 compiler sweep",
               "source": "mining/cpu/bal_batch.c",
               "conditions": ("2 threads (production tuned) and 1 "
                              "thread, 1,000,000 hashes per run, "
                              "3 repeats, live mainnet miner and "
                              "node contending"),
               "variants": {}}
    for name, flags in VARIANTS.items():
        path, rc, err = build(name, flags)
        entry = {"flags": " ".join(flags), "build_rc": rc}
        if rc != 0:
            entry["build_error"] = err
            results["variants"][name] = entry
            continue
        _lib, batch2, search2 = bh.load_lib(path, "bal_c")
        ok_b, msg_b = bh.verify_batch(batch2, 100_000, threads=2)
        ok_s, msg_s = bh.verify_genesis_search(search2)
        entry["verify_100k_vs_hashlib"] = f"{ok_b}: {msg_b}"
        entry["verify_genesis_search"] = f"{ok_s}: {msg_s}"
        entry["asm"] = asm_notes(path)
        entry["bench_threads_2"] = bh.measure(batch2, 1_000_000, 2, 3)
        entry["bench_threads_1"] = bh.measure(batch2, 1_000_000, 1, 3)
        results["variants"][name] = entry
        print(f"{name}: 2T median {entry['bench_threads_2']['median_hs']} "
              f"(spread {entry['bench_threads_2']['spread_pct']}%), "
              f"1T median {entry['bench_threads_1']['median_hs']}",
              flush=True)
    prod = results["variants"]["prod_o3_native"]["bench_threads_2"]
    verdicts = {}
    for name, e in results["variants"].items():
        if name == "prod_o3_native" or "bench_threads_2" not in e:
            continue
        b = e["bench_threads_2"]
        overlap = not (b["min_hs"] > prod["max_hs"]
                       or prod["min_hs"] > b["max_hs"])
        verdicts[name] = {
            "median_vs_prod_pct": round(
                100.0 * (b["median_hs"] - prod["median_hs"])
                / prod["median_hs"], 1),
            "spreads_overlap": overlap,
            "decision": ("reject" if b["median_hs"] <= prod["median_hs"]
                         else ("candidate" if not overlap
                               else "inconclusive_on_this_vm")),
        }
    results["verdicts"] = verdicts
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
