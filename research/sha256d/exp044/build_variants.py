#!/usr/bin/env python3
"""EXP-044 variant builder.

Builds research copies of the production v512 library from
the identical production sources, replicating
mining/cpu/build.py's build_v512 command lines exactly:

  kernel: gcc -O3 -shared -fPIC -I mining/cpu
          -mavx512f -mavx512bw -c bal_avx512_mb.c
  probe:  gcc -O3 -shared -fPIC -I mining/cpu
          -c bal_avx512_probe.c        (no vector flags)
  link:   gcc -shared kernel.o probe.o -o lib -lpthread

(the -shared in the compile steps is inert for -c but is
part of production's base list, so it is kept for exact
fidelity.)

Variants:
  replica  no extra flags. A build-fidelity control: if
           this host's gcc reproduces production's code,
           its v_compress16 / v_walk bodies must be
           instruction-identical to the production
           library's modulo addresses (the EXP-041
           rebuild-control test).
  znver3   kernel compile adds -mtune=znver3.
  znver4   kernel compile adds -mtune=znver4.

The -mtune flag goes on the kernel translation unit
only: it is the only TU with vector code to schedule,
and the probe TU is flag-free by production design.
-mtune changes scheduling only, never the ISA: the
-mavx512f -mavx512bw restricted set is unchanged and
-march=native is never used.

Output: src/libbal_v512_exp044_{replica,znver3,znver4}.so
plus RAW_RESULTS/build_manifest.json with exact commands
and source / binary hashes. Production files are never
written.
"""
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

ROOT = "/home/hatch/workspace/bitcoin-autonomous-lab"
HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(HERE, "src")
OUT_DIR = os.path.join(HERE, "RAW_RESULTS")
CPU_DIR = os.path.join(ROOT, "mining/cpu")
KERNEL_SRC = os.path.join(CPU_DIR, "bal_avx512_mb.c")
PROBE_SRC = os.path.join(CPU_DIR, "bal_avx512_probe.c")
PROD_LIB = os.path.join(ROOT, ".local/cpu/libbal_v512.so")

VARIANTS = {
    "replica": [],
    "znver3": ["-mtune=znver3"],
    "znver4": ["-mtune=znver4"],
}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run(cmd):
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print("FAILED: " + " ".join(cmd), file=sys.stderr)
        print(proc.stderr[-2000:], file=sys.stderr)
        sys.exit(1)
    return " ".join(cmd)


def build(tag, extra):
    tmp = os.path.join(SRC_DIR, f".build-{tag}")
    os.makedirs(tmp, exist_ok=True)
    kernel_obj = os.path.join(tmp, "bal_avx512_mb.o")
    probe_obj = os.path.join(tmp, "bal_avx512_probe.o")
    lib = os.path.join(SRC_DIR, f"libbal_v512_exp044_{tag}.so")
    base = ["gcc", "-O3", "-shared", "-fPIC", "-I", CPU_DIR]
    cmds = []
    cmds.append(run(base + ["-mavx512f", "-mavx512bw"] + extra +
                    ["-c", KERNEL_SRC, "-o", kernel_obj]))
    cmds.append(run(base + ["-c", PROBE_SRC, "-o", probe_obj]))
    cmds.append(run(["gcc", "-shared", kernel_obj, probe_obj,
                     "-o", lib, "-lpthread"]))
    return lib, cmds


def main():
    os.makedirs(SRC_DIR, exist_ok=True)
    os.makedirs(OUT_DIR, exist_ok=True)
    manifest = {
        "experiment": "EXP-044",
        "built_utc": datetime.now(timezone.utc).isoformat(),
        "host": {"hostname": os.uname().nodename},
        "gcc": subprocess.run(["gcc", "--version"],
                              capture_output=True,
                              text=True).stdout.splitlines()[0],
        "kernel_source": {"path": KERNEL_SRC,
                          "sha256": sha256_file(KERNEL_SRC)},
        "probe_source": {"path": PROBE_SRC,
                         "sha256": sha256_file(PROBE_SRC)},
        "production_library": {"path": PROD_LIB,
                               "sha256": sha256_file(PROD_LIB)},
        "production_build_py": {
            "path": os.path.join(CPU_DIR, "build.py"),
            "sha256": sha256_file(os.path.join(CPU_DIR,
                                               "build.py"))},
        "variants": {},
    }
    with open("/proc/cpuinfo") as fh:
        for line in fh:
            if line.startswith("model name"):
                manifest["host"]["cpu_model"] = \
                    line.split(":", 1)[1].strip()
                break
    for tag, extra in VARIANTS.items():
        lib, cmds = build(tag, extra)
        manifest["variants"][tag] = {
            "extra_kernel_flags": extra,
            "library": lib,
            "library_sha256": sha256_file(lib),
            "commands": cmds,
        }
        print(f"{tag}: {lib} sha256 "
              f"{manifest['variants'][tag]['library_sha256']}")
    path = os.path.join(OUT_DIR, "build_manifest.json")
    with open(path, "w") as fh:
        json.dump(manifest, fh, indent=2)
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
