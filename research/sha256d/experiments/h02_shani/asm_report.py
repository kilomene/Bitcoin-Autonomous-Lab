#!/usr/bin/env python3
"""Assembly gate measurements for the H-02/H-01 libraries.

Parses objdump output per function: instruction totals, SHA-NI
instruction counts, stack frame size, spill-like stack traffic
(stores/loads to rsp-relative slots inside the function), calls,
and code size. The per-nonce hot functions are the static
hash_* / h_worker bodies where the compiler inlined the core.
"""
import re
import subprocess
import sys

def functions(path):
    out = subprocess.run(["objdump", "-d", path], capture_output=True,
                         text=True).stdout
    funcs = {}
    cur = None
    for line in out.splitlines():
        m = re.match(r"^[0-9a-f]+ <([^>]+)>:", line)
        if m:
            cur = m.group(1)
            funcs[cur] = []
            continue
        if cur and "\t" in line:
            funcs[cur].append(line)
    return funcs

def report(path, names):
    funcs = functions(path)
    print(f"== {path} ==")
    for name in names:
        lines = funcs.get(name)
        if lines is None:
            print(f"{name}: NOT FOUND")
            continue
        insns = []
        for ln in lines:
            parts = ln.split("\t")
            if len(parts) >= 3 and parts[1].strip():
                insns.append(parts[2].strip())
        text = "\n".join(insns)
        def count(op):
            return sum(1 for i in insns if i.startswith(op))
        frame = 0
        for i in insns:
            m = re.match(r"sub\s+\$0x([0-9a-f]+),%rsp", i)
            if m:
                frame = max(frame, int(m.group(1), 16))
        spills = sum(1 for i in insns
                     if re.search(r"%xmm\d+,-?0x?[0-9a-f]*\(%rsp\)", i)
                     or re.search(r"\(%rsp\),%xmm", i)
                     or "movaps" in i and "%rsp" in i
                     or "movups" in i and "%rsp" in i)
        stack_refs = sum(1 for i in insns if "(%rsp)" in i)
        calls = sum(1 for i in insns if i.startswith("call"))
        memops = sum(1 for i in insns if "(%r" in i or "(%rsp)" in i)
        addrs = [ln.split(":")[0].strip() for ln in lines if ":" in ln]
        size = (int(addrs[-1], 16) - int(addrs[0], 16)) if addrs else 0
        print(f"{name}: insns={len(insns)} size~{size}B "
              f"rnds2={count('sha256rnds2')} msg1={count('sha256msg1')} "
              f"msg2={count('sha256msg2')} frame={frame}B "
              f"xmm_stack_ops={spills} stack_refs={stack_refs} "
              f"calls={calls} mem_refs={memops}")

if __name__ == "__main__":
    report("libbal_h02.so", ["hash_p1", "hash_full", "hash_p2",
                             "h_worker", "h_sworker", "bal_h_compress"])
    report("libbal_h02_scalar.so", ["hash_p1", "h_worker"])
