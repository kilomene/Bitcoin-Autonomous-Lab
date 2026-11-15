#!/usr/bin/env python3
"""EXP-041 emitted-code census.

Method: for each library, locate the compression
function body via its local symbol (nm address and
size), disassemble exactly that range with objdump,
and count vector instructions. The kernel compiles
v_compress16 as a loop over t = 0..63 whose body is
ONE round; the steady-state round (t >= 16) executes
every vector ALU instruction in the body exactly
once (the schedule-expansion instructions sit behind
the t >= 16 branch and the t < 16 path only skips
them), so the per-round emitted cost is the count of
vector ALU instructions in the body:

  offsets  = vprold + vprord + vpsrld + vpslld
  combines = vpternlogd + vpandd + vpandnd + vpxord
             + vpord (each counted, ternlog by imm)
  adds     = vpaddd
  total    = offsets + combines + adds

Vector moves (vmovdqa*) are counted separately: they
are outside the EXP-020 vocabulary census but are
recorded because they are part of the real cost.
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

ROOT = "/home/hatch/workspace/bitcoin-autonomous-lab"
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "src")

LIBS = {
    "production_v512": (
        os.path.join(ROOT, ".local/cpu/libbal_v512.so"),
        ["v_compress16"]),
    "production_v512dual": (
        os.path.join(ROOT, ".local/cpu/libbal_v512dual.so"),
        ["v_compress16", "v_compress16x2_reg"]),
}
for tag in ("base", "alta", "altb", "altc", "tmaj", "tfull",
            "base_o2", "base_znver3"):
    LIBS[f"e41{tag}"] = (
        os.path.join(SRC, f"libbal_e41{tag}.so"), ["v_compress16"])

OFFSETS = {"vprold", "vprord", "vpsrld", "vpslld"}
LOGIC = {"vpandd", "vpandnd", "vpxord", "vpord", "vpandq",
         "vpxorq", "vporq"}
MOVES = {"vmovdqa64", "vmovdqa32", "vmovdqu64", "vmovdqu32"}


def symbol_range(path, name):
    out = subprocess.run(["objdump", "-t", path],
                         capture_output=True, text=True).stdout
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 6 and parts[-1] == name:
            return int(parts[0], 16), int(parts[-2], 16)
    raise SystemExit(f"symbol {name} not found in {path}")


def census_body(path, name):
    addr, size = symbol_range(path, name)
    out = subprocess.run(
        ["objdump", "-d", path,
         f"--start-address={addr:#x}",
         f"--stop-address={addr + size:#x}"],
        capture_output=True, text=True).stdout
    counts = {"offsets": 0, "ternlog_total": 0, "ternlog_by_imm": {},
              "logic_other": 0, "adds": 0, "moves": 0,
              "total_instructions": 0, "body_bytes": size}
    for line in out.splitlines():
        m = re.match(r"\s*[0-9a-f]+:\s+(?:[0-9a-f]{2} )+\s*"
                     r"([a-z0-9.]+)\s*(.*)", line)
        if not m:
            continue
        mnem, rest = m.group(1), m.group(2)
        counts["total_instructions"] += 1
        if mnem in OFFSETS:
            counts["offsets"] += 1
        elif mnem == "vpternlogd":
            counts["ternlog_total"] += 1
            im = re.search(r"\$0x([0-9a-f]+)", rest)
            key = "0x" + im.group(1) if im else "?"
            counts["ternlog_by_imm"][key] = \
                counts["ternlog_by_imm"].get(key, 0) + 1
        elif mnem in LOGIC:
            counts["logic_other"] += 1
        elif mnem == "vpaddd":
            counts["adds"] += 1
        elif mnem in MOVES:
            counts["moves"] += 1
    counts["combines"] = counts["ternlog_total"] + counts["logic_other"]
    counts["vector_alu_total"] = (counts["offsets"]
                                  + counts["combines"]
                                  + counts["adds"])
    return counts


def main():
    result = {
        "experiment": "EXP-041",
        "census_utc": datetime.now(timezone.utc).isoformat(),
        "method": "objdump of the v_compress16 loop body "
                  "(one round per iteration); see census.py "
                  "docstring",
        "libraries": {},
    }
    for libname, (path, funcs) in LIBS.items():
        entry = {"path": os.path.relpath(path, ROOT), "functions": {}}
        for fn in funcs:
            c = census_body(path, fn)
            entry["functions"][fn] = c
            print(f"{libname:22s} {fn:20s} alu={c['vector_alu_total']:4d} "
                  f"off={c['offsets']:3d} tern={c['ternlog_total']:3d} "
                  f"{c['ternlog_by_imm']} logic={c['logic_other']} "
                  f"adds={c['adds']:3d} moves={c['moves']:3d} "
                  f"insns={c['total_instructions']}")
        result["libraries"][libname] = entry
    out = os.path.join(HERE, "RAW_RESULTS", "census.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as fh:
        json.dump(result, fh, indent=1)
    print("wrote", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
