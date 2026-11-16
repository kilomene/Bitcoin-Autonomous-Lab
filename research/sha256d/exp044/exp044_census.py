#!/usr/bin/env python3
"""EXP-044 emitted-code census.

Method follows EXP-041's census.py: for each library,
locate function bodies via the symbol table (objdump
-t), disassemble exactly those ranges (objdump -d), and
count instructions.

Two levels are recorded, because EXP-041's move claim
(64 vector moves in production, 33 under -mtune=znver3)
was made on a standalone-extracted compress body, and
EXP-044 must re-verify it on the full production
kernel:

  v_compress16 alone: total instructions, vector
    instructions, vector moves (EXP-041 MOVES set:
    vmovdqa64, vmovdqa32, vmovdqu64, vmovdqu32), all
    vmov* mnemonics, and the per-round ALU census
    (offsets = vprold + vprord + vpsrld + vpslld;
    combines = vpternlogd + vpandd + vpandnd + vpxord
    + vpord, ternlog by immediate; adds = vpaddd;
    total = offsets + combines + adds). The kernel
    compiles v_compress16 as a loop over t = 0..63
    whose body is one round, so the body count is the
    per-round emitted cost (EXP-041 method).

  full hot path: v_compress16 + v_walk combined total
    instructions and vector moves, so the scheduling
    change is measured on the whole kernel body that
    executes per batch wave, not only the compress
    function.

Libraries: production .local/cpu/libbal_v512.so, the
EXP-044 replica (byte-identical to production; the
build-fidelity control), znver3 and znver4 research
builds. Output: RAW_RESULTS/census.json plus a printed
table.
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

ROOT = "/home/hatch/workspace/bitcoin-autonomous-lab"
HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(HERE, "src")
OUT_DIR = os.path.join(HERE, "RAW_RESULTS")

LIBS = {
    "production": os.path.join(ROOT, ".local/cpu/libbal_v512.so"),
    "replica": os.path.join(
        SRC_DIR, "libbal_v512_exp044_replica.so"),
    "znver3": os.path.join(
        SRC_DIR, "libbal_v512_exp044_znver3.so"),
    "znver4": os.path.join(
        SRC_DIR, "libbal_v512_exp044_znver4.so"),
}

OFFSETS = {"vprold", "vprord", "vpsrld", "vpslld"}
COMBINES = {"vpternlogd", "vpandd", "vpandnd", "vpxord", "vpord"}
MOVES = {"vmovdqa64", "vmovdqa32", "vmovdqu64", "vmovdqu32"}
INSN_RE = re.compile(r"^\s*[0-9a-f]+:\s+(?:[0-9a-f]{2} )+\s*"
                     r"([a-z0-9.]+)\s*(.*)$")


def symbols(path):
    out = subprocess.run(["objdump", "-t", path],
                         capture_output=True, text=True).stdout
    found = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 6 and parts[-2] != "0000000000000000":
            try:
                addr = int(parts[0], 16)
                size = int(parts[-2], 16)
            except ValueError:
                continue
            name = parts[-1]
            if size > 0 and (name == "v_compress16"
                             or name.startswith("v_walk")):
                found[name] = (addr, size)
    return found


def disasm(path, addr, size):
    out = subprocess.run(
        ["objdump", "-d", f"--start-address={addr:#x}",
         f"--stop-address={addr + size:#x}", path],
        capture_output=True, text=True).stdout
    insns = []
    for line in out.splitlines():
        m = INSN_RE.match(line)
        if m:
            insns.append((m.group(1), m.group(2).strip()))
    return insns


def census_fn(insns):
    c = {"total_instructions": len(insns),
         "vector_instructions": 0,
         "moves_exp041_set": 0,
         "moves_all_vmov": 0,
         "offsets": 0, "combines": 0, "adds": 0,
         "ternlog_by_imm": {}}
    for mnem, operands in insns:
        if mnem.startswith("v"):
            c["vector_instructions"] += 1
        if mnem in MOVES:
            c["moves_exp041_set"] += 1
        if mnem.startswith("vmov"):
            c["moves_all_vmov"] += 1
        if mnem in OFFSETS:
            c["offsets"] += 1
        elif mnem in COMBINES:
            c["combines"] += 1
            if mnem == "vpternlogd":
                imm = operands.rsplit(",", 1)[-1].strip()
                c["ternlog_by_imm"][imm] = \
                    c["ternlog_by_imm"].get(imm, 0) + 1
        elif mnem == "vpaddd":
            c["adds"] += 1
    c["alu_total"] = c["offsets"] + c["combines"] + c["adds"]
    return c


def main():
    result = {
        "experiment": "EXP-044",
        "census_utc": datetime.now(timezone.utc).isoformat(),
        "method": "EXP-041 census method (objdump symbol "
                  "ranges); moves set = vmovdqa64/32 + "
                  "vmovdqu64/32",
        "libraries": {},
    }
    for tag, path in LIBS.items():
        syms = symbols(path)
        entry = {"path": path, "symbols": {}, "functions": {}}
        hot_total = 0
        hot_moves = 0
        for name, (addr, size) in sorted(syms.items()):
            entry["symbols"][name] = {"addr": addr, "size": size}
            c = census_fn(disasm(path, addr, size))
            entry["functions"][name] = c
            hot_total += c["total_instructions"]
            hot_moves += c["moves_exp041_set"]
        entry["hot_path_v_compress16_plus_v_walk"] = {
            "total_instructions": hot_total,
            "moves_exp041_set": hot_moves}
        result["libraries"][tag] = entry
        vc = entry["functions"].get("v_compress16", {})
        print(f"{tag:11s} v_compress16: total "
              f"{vc.get('total_instructions')} vector "
              f"{vc.get('vector_instructions')} moves "
              f"{vc.get('moves_exp041_set')} (all vmov "
              f"{vc.get('moves_all_vmov')}) ALU/round "
              f"{vc.get('alu_total')} | hot path: total "
              f"{hot_total} moves {hot_moves}")
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, "census.json")
    with open(path, "w") as fh:
        json.dump(result, fh, indent=2)
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
