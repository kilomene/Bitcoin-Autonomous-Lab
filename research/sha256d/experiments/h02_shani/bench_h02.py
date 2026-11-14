#!/usr/bin/env python3
"""EXP-002 benchmark: production C vs H-02 SHA-NI vs intrinsics,
plus the H-03 prefix variants (full / mode-1 / mode-2) measured
through the identical counted batch path.

Uses the EXP-000 harness measure() (same workload: genesis
header, DIFF1 target, count per run, repeats; attempted ==
count is asserted inside run_batch by the caller pattern used
in measure()). Unique coverage equals actual backend
computations for every batch here: the batch path hashes each
nonce exactly once, no overflow machinery exists in these
libraries, so the two accounting quantities coincide and the
report says so rather than dressing them up as two numbers.
"""
import ctypes
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from bench_harness import load_lib, measure, verify_batch, \
    verify_genesis_search  # noqa: E402

ROOT = "/home/hatch/workspace/bitcoin-autonomous-lab"
COUNT = 1_000_000
REPEATS = 3


def bind(lib, name):
    fn = getattr(lib, name)
    fn.restype = ctypes.c_int
    fn.argtypes = [ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
                   ctypes.c_uint, ctypes.c_char_p, ctypes.c_char_p,
                   ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint64)]
    return fn


def main():
    loadavg = open("/proc/loadavg").read().split()[:3]
    out = {"experiment": "EXP-002 H-02 SHA-NI kernel",
           "load_average_at_run": loadavg,
           "contention": ("live mainnet pool miner and pruned node "
                          "running; shared VM capped near 1.5 CPUs"),
           "accounting": ("unique_coverage == backend computations "
                          "for all batch runs (each nonce hashed "
                          "exactly once; asserted attempted == count)"),
           "backends": {}}
    specs = [
        ("c_openssl_midstate", f"{ROOT}/.local/cpu/libbal_batch.so",
         "bal_c", None),
        ("intrinsics_scalar_schedule",
         f"{ROOT}/.local/cpu/libbal_intrin.so", "bal_i", None),
        ("h02_shani_msg", os.path.join(HERE, "libbal_h02.so"),
         "bal_h", None),
        ("h02_shani_scalar_twin", os.path.join(HERE,
         "libbal_h02_scalar.so"), "bal_h", None),
    ]
    for name, path, prefix, _x in specs:
        _lib, b2, s2 = load_lib(path, prefix)
        ok_b, msg_b = verify_batch(b2, 20_000)
        ok_s, msg_s = verify_genesis_search(s2)
        entry = {"verify_batch_20000": f"{ok_b}: {msg_b}",
                 "verify_genesis_search": f"{ok_s}: {msg_s}",
                 "threads": {}}
        for threads in (1, 2):
            entry["threads"][str(threads)] = measure(
                b2, COUNT, threads, REPEATS)
        out["backends"][name] = entry
        print(name, json.dumps(entry["threads"]))
    # H-03 prefix variants on the H-02 library itself.
    lib = ctypes.CDLL(os.path.join(HERE, "libbal_h02.so"))
    variants = {}
    for vname, fn_name in (("prefix_mode1_snapshot_after_r1",
                            "bal_h_batch2"),
                           ("no_prefix_full_rounds", "bal_h_batch2_full"),
                           ("prefix_mode2_snapshot_after_r2",
                            "bal_h_batch2_p2")):
        fn = bind(lib, fn_name)
        entry = {}
        for threads in (1, 2):
            entry[str(threads)] = measure(fn, COUNT, threads, REPEATS)
        variants[vname] = entry
        print(vname, json.dumps(entry))
    out["prefix_variants"] = variants
    with open(os.path.join(HERE, "exp002_benchmarks.json"), "w") as fh:
        json.dump(out, fh, indent=2)
    print("wrote exp002_benchmarks.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
