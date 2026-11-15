#!/usr/bin/env python3
"""EXP-028 probe run on THIS host only.

Compiles exp028_probe.c with no architecture flags,
verifies at the object level that the probe object
contains no vector or extension instruction (objdump
census), runs it, cross-checks its bits against
/proc/cpuinfo flags, and exercises the dispatch
specification (exp028_dispatch.py) including the
forced-failure and incomplete-library fallbacks (the
D-1 regression pattern). Writes one append-only JSON
record under benchmarks/exp028/.

Scope honesty: this verifies the probe and the
dispatch logic on this one host (AMD EPYC 9D25 guest).
It verifies no kernel on any architecture; per-family
kernel status lives in EXP028_CPU_ARCHITECTURES.md.
"""
import ctypes
import json
import os
import platform
import re
import subprocess
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "exp028")
sys.path.insert(0, HERE)
from exp028_dispatch import BIT_NAMES, select_backend  # noqa: E402

VECTOR_MNEMONICS = re.compile(
    r"\b(v[a-z0-9]+|sha256[a-z0-9]*|aes[a-z]*|pclmulqdq|"
    r"vbroadcast[a-z0-9]*)\b")


def cpuinfo():
    model, flags = "", set()
    with open("/proc/cpuinfo") as fh:
        for line in fh:
            if line.startswith("model name") and not model:
                model = line.split(":", 1)[1].strip()
            if line.startswith("flags"):
                flags = set(line.split(":", 1)[1].split())
                break
    return model, flags


# cpuinfo flag name for each probe bit.
CPUINFO_FOR_BIT = {0: "avx512f", 1: "avx512bw", 2: "avx512dq",
                   3: "avx512vl", 4: "avx512vbmi",
                   5: "avx512_vbmi2", 6: "avx512ifma",
                   7: "avx512_vnni", 8: "avx2", 9: "sha_ni",
                   10: "sse4_1", 11: "sse4_2", 12: "bmi1",
                   13: "bmi2", 14: "adx", 15: "aes"}


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    so = os.path.join(OUT_DIR, "libbal_xarch_probe.so")
    obj = os.path.join(OUT_DIR, "exp028_probe.o")
    subprocess.run(["gcc", "-O2", "-fPIC", "-c",
                    os.path.join(HERE, "exp028_probe.c"),
                    "-o", obj], check=True)
    subprocess.run(["gcc", "-shared", obj, "-o", so],
                   check=True)
    dis = subprocess.run(["objdump", "-d", obj],
                         capture_output=True, text=True,
                         check=True).stdout
    mnemonics = set()
    for line in dis.splitlines():
        m = re.search(r":\t[0-9a-f ]+\t([a-z0-9.]+)", line)
        if m:
            mnemonics.add(m.group(1))
    vector_hits = sorted(m for m in mnemonics
                         if VECTOR_MNEMONICS.match(m)
                         and not m.startswith("vzeroupper")
                         and m not in ("vmovd",))
    # The probe must contain no vector/extension mnemonics
    # at all beyond scalar moves the compiler emits for
    # __builtin_cpu_supports bookkeeping; assert strictly:
    strict_hits = sorted(m for m in mnemonics
                         if m.startswith(("v", "sha256", "aes",
                                          "pclmul")))
    lib = ctypes.CDLL(so)
    lib.bal_xarch_feature_bits.restype = ctypes.c_uint64
    bits = lib.bal_xarch_feature_bits()
    lib.bal_xarch_v512_ok.restype = ctypes.c_int
    lib.bal_xarch_shani_ok.restype = ctypes.c_int
    model, flags = cpuinfo()
    bit_report, cross_ok = {}, True
    for idx, name in BIT_NAMES.items():
        probe_bit = bool((bits >> idx) & 1)
        cpu_bit = CPUINFO_FOR_BIT[idx] in flags
        # __builtin_cpu_supports also requires OS state for
        # AVX families; on this host both must agree.
        agree = probe_bit == cpu_bit
        cross_ok = cross_ok and agree
        bit_report[name] = {"probe": probe_bit,
                            "cpuinfo": cpu_bit, "agree": agree}
    full_libs = {
        "avx512-mb": {"bal_v512_supported", "bal_v_batch2",
                      "bal_v_search2"},
        "shani-streams": {"bal_m_batch2m", "bal_m_search2m"},
        "avx2-mb": {"bal_a_batch2", "bal_a_search2"},
        "c-openssl": {"bal_batch2", "bal_search2"}}
    all_pass = {k: True for k in full_libs}
    scenarios = {}
    scenarios["this_host_all_present"] = select_backend(
        bits, full_libs, all_pass)
    scenarios["forced_probe_failure"] = select_backend(
        0, full_libs, all_pass)
    incomplete = dict(full_libs)
    incomplete["avx512-mb"] = {"bal_v512_supported"}
    incomplete["shani-streams"] = {"bal_m_batch2m"}
    incomplete["avx2-mb"] = {"bal_a_batch2"}
    scenarios["incomplete_libraries_d1_pattern"] = \
        select_backend(bits, incomplete, all_pass)
    failed_test = dict(all_pass)
    failed_test["avx512-mb"] = False
    scenarios["v512_self_test_failure"] = select_backend(
        bits, full_libs, failed_test)
    scenarios["nothing_present"] = select_backend(
        bits, {}, {})
    record = {
        "experiment": "EXP-028",
        "kind": "probe and dispatch-spec verification, "
                "this host only",
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "host": {"model": model,
                 "machine": platform.machine(),
                 "vcpus": os.cpu_count(),
                 "kernel": platform.release()},
        "feature_bits_hex": hex(bits),
        "bits": bit_report,
        "cpuinfo_crosscheck_all_agree": cross_ok,
        "v512_predicate": bool(lib.bal_xarch_v512_ok()),
        "shani_predicate": bool(lib.bal_xarch_shani_ok()),
        "probe_object_mnemonics": sorted(mnemonics),
        "probe_object_vector_mnemonics_strict": strict_hits,
        "probe_safety": "PASS" if not strict_hits else "FAIL",
        "dispatch_scenarios": {
            k: {"selected": v[0], "reasons": v[1]}
            for k, v in scenarios.items()},
        "expectations": {
            "this_host_all_present": "avx512-mb",
            "forced_probe_failure": "c-openssl",
            "incomplete_libraries_d1_pattern": "c-openssl",
            "v512_self_test_failure": "shani-streams",
            "nothing_present": "hashlib"},
    }
    exp = record["expectations"]
    record["dispatch_expectations_met"] = all(
        record["dispatch_scenarios"][k]["selected"] == v
        for k, v in exp.items())
    record["verdict"] = (
        "PASS" if cross_ok and not strict_hits
        and record["dispatch_expectations_met"] else "FAIL")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(OUT_DIR, f"probe_{stamp}.json")
    suffix = 2
    while os.path.exists(path):
        path = os.path.join(OUT_DIR, f"probe_{stamp}_r{suffix}.json")
        suffix += 1
    with open(path, "x") as fh:
        json.dump(record, fh, indent=2)
    print(f"verdict {record['verdict']} bits {hex(bits)} "
          f"wrote {path}")
    return 0 if record["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
