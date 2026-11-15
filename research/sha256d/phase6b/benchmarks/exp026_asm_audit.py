#!/usr/bin/env python3
"""EXP-026 assembly audit: objdump census of the two
candidate libraries and the production base library.
Per hot function: instruction count, frame size from
the prologue sub, stack-op census (zmm loads and stores
to stack slots), vpternlog and vpcmp presence.
"""
import json
import os
import re
import subprocess
from datetime import datetime, timezone

ROOT = "/home/hatch/workspace/bitcoin-autonomous-lab"
EO_SRC = os.path.join(ROOT, "research/sha256d/extreme_optimization/src")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "exp026")

LIBS = {
    "tern": ("libbal_e26t.so", ["vm_group", "v_compress16"]),
    "dual": ("libbal_e26d.so", ["rm_group2m", "v_compress16x2_reg"]),
    "mask": ("libbal_m512.so", ["vm_group", "v_compress16"]),
    "production": ("libbal_v512_exp022base.so", []),
}


def disasm(path):
    out = subprocess.run(["objdump", "-d", "--no-show-raw-insn", path],
                         capture_output=True, text=True, check=True)
    return out.stdout


def functions(text):
    fns = {}
    cur = None
    for line in text.splitlines():
        m = re.match(r"^[0-9a-f]+ <([^>]+)>:", line)
        if m:
            cur = m.group(1)
            fns[cur] = []
            continue
        if cur and "\t" in line:
            parts = line.split("\t")
            if len(parts) >= 2:
                fns[cur].append(parts[1].strip())
    return fns


def census(insns):
    stack_store = sum(1 for i in insns
                      if re.match(r"vmovdqa(32|64).*%rsp", i)
                      or re.match(r"vmovdqu.*%rsp", i))
    ternlog = sum(1 for i in insns if i.startswith("vpternlog"))
    vpcmp = sum(1 for i in insns if i.startswith("vpcmp"))
    frame = 0
    for i in insns[:40]:
        m = re.match(r"sub\s+\$0x([0-9a-f]+),%rsp", i)
        if m:
            frame = int(m.group(1), 16)
            break
    return {"instructions": len(insns),
            "zmm_stack_stores_approx": stack_store,
            "vpternlog": ternlog,
            "vpcmp": vpcmp,
            "frame_bytes_prologue": frame}


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    report = {"experiment": "EXP-026",
              "audited_utc": datetime.now(timezone.utc).isoformat(),
              "libraries": {}}
    for name, (lib, wanted) in LIBS.items():
        path = os.path.join(EO_SRC, lib)
        text = disasm(path)
        fns = functions(text)
        entry = {"library": lib,
                 "whole_library_vpternlog":
                     text.count("vpternlog"),
                 "whole_library_vpcmp": text.count("vpcmp"),
                 "functions": {}}
        targets = wanted or sorted(fns)[:0]
        for fn in targets:
            for key in fns:
                if key.startswith(fn):
                    entry["functions"][key] = census(fns[key])
        report["libraries"][name] = entry
        print(name, json.dumps(entry))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(OUT_DIR, f"asm_audit_{stamp}.json")
    with open(path, "w") as fh:
        json.dump(report, fh, indent=1)
    print("WROTE", path)


if __name__ == "__main__":
    main()
