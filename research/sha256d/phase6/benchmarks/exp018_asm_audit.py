#!/usr/bin/env python3
"""EXP-018 assembly audit (Y-023 primary metric).

Disassembles the hot compression functions of the
EXP-018 register-resident dual-batch library
(libbal_r512.so), the EXP-011 dual-batch library
(libbal_w512.so) and the single-batch library
(libbal_v512.so), and counts, per function:

  * static instruction count and stack frame size;
  * vmovdqa64 total, stack-relative, and
    register-to-register counts;
  * vmovdqa32 stack-relative loads and stores;
  * every instruction carrying a zmm register and a
    stack-relative operand, split by stack region.

Stack regions are taken from each function's own
prologue: the memcpy destination offsets give the two
schedule ring arrays (1,024 bytes each). Stack vector
traffic below the first ring in libbal_r512.so is the
compiler spill area; the audit lists those offsets
individually so a state spill slot is visible by
address. Output is benchmarks/exp018/asm_audit.json;
re-running overwrites only that audit file, never a
benchmark session.
"""
import json
import os
import re
import subprocess
from collections import Counter
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "..", "extreme_optimization", "src")
OUT = os.path.join(HERE, "exp018", "asm_audit.json")

TARGETS = [
    # (library, function, schedule ring regions, note)
    ("libbal_r512.so", "v_compress16x2_reg",
     [(0x100, 0x500), (0x500, 0x900)],
     "EXP-018 dual compress. Rings at 0x100 and 0x500 "
     "per the two prologue memcpy destinations. Stack "
     "offsets below 0x100 are the spill area."),
    ("libbal_w512.so", "v_compress16x2",
     [(0x0, 0x400), (0x400, 0x800)],
     "EXP-011 dual compress. Rings at 0x0 and 0x400 "
     "per the prologue (rsp copied to r13, second ring "
     "at rsp+0x400); some schedule accesses use the "
     "r13 and r8 base pointers instead of rsp-relative "
     "form and are not in the stack counts."),
    ("libbal_v512.so", "v_compress16",
     [(0x0, 0x400)],
     "Single-batch compress. One schedule ring."),
    ("libbal_w512.so", "v_compress16",
     [(0x0, 0x400)],
     "Single-batch compress as compiled inside the "
     "EXP-011 library (identical counts expected)."),
]


def parse_functions(path):
    text = subprocess.check_output(
        ["objdump", "-d", "--no-show-raw-insn", path], text=True)
    data = {}
    cur = None
    for line in text.splitlines():
        m = re.match(r"^([0-9a-f]+) <([^>]+)>:", line)
        if m:
            cur = m.group(2)
            data.setdefault(cur, [])
            continue
        m = re.match(r"^\s+([0-9a-f]+):\s+(\S+)\s*(.*)$", line)
        if cur and m:
            data[cur].append((m.group(2), m.group(3)))
    return data


def stack_offset(operand):
    m = re.search(r"(-?0x[0-9a-f]+|-?\d+)?\(%rsp", operand)
    if not m:
        return None
    s = m.group(1)
    if s is None:
        return 0
    return int(s, 16) if s.lstrip("-").startswith("0x") else int(s)


def is_store(operand):
    return re.search(r",\s*(-?0x[0-9a-f]+|-?\d+)?\(%rsp", operand) is not None


def audit(path, fn, regions, note):
    ins = parse_functions(path)[fn]
    frame = None
    for mn, op in ins:
        if mn == "sub" and "%rsp" in op:
            frame = int(op.split(",")[0].strip().lstrip("$"), 16)
            break

    def region_of(off):
        if off is None:
            return "none"
        for lo, hi in regions:
            if lo <= off < hi:
                return f"schedule_0x{lo:x}"
        return "spill_or_other"

    out = {"library": os.path.basename(path), "function": fn,
           "note": note, "instructions": len(ins),
           "frame_bytes": frame}
    for mn in ("vmovdqa64", "vmovdqa32"):
        tot = [op for m2, op in ins if m2 == mn]
        stack = [op for op in tot if "(%rsp" in op]
        out[mn] = {
            "total": len(tot),
            "stack": len(stack),
            "stack_loads": sum(1 for op in stack if not is_store(op)),
            "stack_stores": sum(1 for op in stack if is_store(op)),
            "register_to_register": sum(
                1 for op in tot
                if "(%rsp" not in op
                and op.split(",")[-1].strip().startswith("%zmm")),
        }
    zstack = [(mn, op) for mn, op in ins
              if "(%rsp" in op and "%zmm" in op]
    by_region = Counter()
    directions = Counter()
    offsets = Counter()
    for mn, op in zstack:
        off = stack_offset(op)
        reg = region_of(off)
        by_region[reg] += 1
        directions[(reg, "store" if is_store(op) else "load")] += 1
        if reg == "spill_or_other":
            offsets[f"0x{off:x}"] += 1
    out["zmm_stack_instructions"] = {
        "total": len(zstack),
        "by_region": dict(by_region),
        "directions": {f"{k[0]}:{k[1]}": v
                       for k, v in directions.items()},
        "spill_region_offsets": dict(offsets),
    }
    out["opcode_top"] = Counter(mn for mn, _op in ins).most_common(10)
    return out


def main():
    results = []
    for lib, fn, regions, note in TARGETS:
        results.append(audit(os.path.join(SRC, lib), fn, regions, note))
        r = results[-1]
        print(f"{lib} {fn}: insns={r['instructions']} "
              f"frame={r['frame_bytes']} "
              f"vmovdqa64={r['vmovdqa64']} "
              f"zmm_stack={r['zmm_stack_instructions']['by_region']}")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as fh:
        json.dump({"experiment": "EXP-018",
                   "audit_utc": datetime.now(timezone.utc).isoformat(),
                   "method": "objdump -d --no-show-raw-insn; "
                             "regions from prologue memcpy "
                             "destinations",
                   "functions": results}, fh, indent=2)
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
