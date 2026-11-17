#!/usr/bin/env python3
"""EXP-053 variant generator and builder.

Generates the EXP-053 research translation unit from the
production dual-batch kernel (mining/cpu/bal_avx512_dual.c)
by mechanical transformation only:

  1. an EXP-053 banner is prepended;
  2. one new function, v_compress16x2_prefix, plus its two
     macros (VPREFIX3, DUAL5_TAIL) is inserted immediately
     before v_make_w0. It is the stock dual compress with
     chunk-2 rounds 0 to 2 executed once instead of twice
     (the H-6 prefix share: both batches enter chunk 2
     from the same midstate broadcast and differ only in
     schedule word W[3], the nonce word, so rounds 0 to 2,
     which consume only W[0], W[1], W[2], produce identical
     state for both batches; Stage 1 dependency graph,
     Phase 001 H-6);
  3. vp_group2 and vp_group2m are extracted verbatim from
     v_group2 and rm_group2m with the first (chunk-2)
     compress call retargeted to v_compress16x2_prefix and
     the function renamed; the outer-chunk call stays the
     stock v_compress16x2_reg;
  4. the span-walker spans (VJob/v_walk through
     bal_vd_batch2, RMJob/rm_walk through bal_vd_search2)
     are extracted verbatim and renamed to the vp exports
     bal_vp_batch2 and bal_vp_search2, with their dual
     steps retargeted to the vp group functions. The
     single-group remainder path (v_group) is shared
     unchanged.

Everything else in the generated file is byte-identical
to the production source. The stock bal_vd_* exports
remain in the unit as an in-library rebuild control.

Build: the production restricted recipe for the kernel
translation unit (gcc -O3 -shared -fPIC -I mining/cpu
-mavx512f -mavx512bw, never -march=native), linked with
-lpthread. The CPUID probe translation unit is not
linked: this library is research-only and is loaded only
on a host already known to run the production dual
kernel. Production files are never touched.

Writes RAW_RESULTS/build_manifest.json with the host CPU
model and the sha256 of the production source, the
generated source, the binary, and this generator.
"""
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

ROOT = "/home/hatch/workspace/bitcoin-autonomous-lab"
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "src")
PROD = os.path.join(ROOT, "mining/cpu/bal_avx512_dual.c")
GEN = os.path.join(SRC, "avx512_dual_exp053_prefix.c")
LIB = os.path.join(SRC, "libbal_e53prefix.so")
RAW = os.path.join(HERE, "RAW_RESULTS")

BANNER = """/* ============================================================
 * EXP-053 RESEARCH COPY (NOVA-ER-0013, register Y-098,
 * Phase 001 H-6): chunk-2 prefix sharing inside the
 * production dual-batch walker.
 *
 * Generated mechanically from mining/cpu/bal_avx512_dual.c
 * by research/sha256d/exp053/build_variant.py; do not edit
 * by hand, regenerate. The stock code is byte-identical to
 * production. The only additions are v_compress16x2_prefix
 * (chunk-2 rounds 0 to 2 executed once for both batches
 * instead of twice) and the vp walkers/exports
 * (bal_vp_batch2, bal_vp_search2) that call it for the
 * chunk-2 compression of each dual group. The outer chunk
 * and the single-group remainder path are unchanged.
 * Production is untouched by this experiment.
 * ============================================================ */
"""

PREFIX_BLOCK = """
/* ---- EXP-053: prefix-shared dual compress ----
 * Precondition (guaranteed by both call sites, which
 * build W0a and W0b from the same template through
 * v_make_w0 and seed both states from the same midstate
 * broadcast): Sa[j] == Sb[j] for all j at entry, and
 * W0a[i] == W0b[i] for i in 0..2. The batches differ
 * only in W[3], the nonce word. Rounds 0 to 2 consume
 * only W[0], W[1], W[2], so the state after round 2 is
 * identical for both batches (Stage 1 dependency
 * graph: state after rounds 0..2 carries no nonce
 * dependence). This function runs those three rounds
 * once on batch A's physical variables, copies the
 * eight physical state vectors to batch B, and runs
 * rounds 3 to 63 as the stock interleaved dual ring.
 * The schedule rings are not written by rounds 0 to 2
 * (the t < 16 branch of VSTEP_RING reads Wr[t] and
 * never stores), so Wa and Wb keep their own W[3] for
 * round 3 onward, exactly as in the stock compress.
 * The arithmetic is the stock arithmetic: same ops,
 * same order, one copy of the first three chunk-2
 * rounds instead of two. The saving is bounded by
 * 3 of the 256 round steps of a dual group (both
 * chunks, both batches), about 1.17 percent of round
 * work, before second-order effects. */
#define VPREFIX3(A, Wa) do { \\
  VSTEP_RING(A##0, A##1, A##2, A##3, A##4, A##5, A##6, A##7, Wa, 0); \\
  VSTEP_RING(A##7, A##0, A##1, A##2, A##3, A##4, A##5, A##6, Wa, 1); \\
  VSTEP_RING(A##6, A##7, A##0, A##1, A##2, A##3, A##4, A##5, Wa, 2); \\
} while (0)

#define DUAL5_TAIL(A, B, Wa, Wb) do { \\
  VSTEP_RING(A##5, A##6, A##7, A##0, A##1, A##2, A##3, A##4, Wa, 3); \\
  VSTEP_RING(B##5, B##6, B##7, B##0, B##1, B##2, B##3, B##4, Wb, 3); \\
  VSTEP_RING(A##4, A##5, A##6, A##7, A##0, A##1, A##2, A##3, Wa, 4); \\
  VSTEP_RING(B##4, B##5, B##6, B##7, B##0, B##1, B##2, B##3, Wb, 4); \\
  VSTEP_RING(A##3, A##4, A##5, A##6, A##7, A##0, A##1, A##2, Wa, 5); \\
  VSTEP_RING(B##3, B##4, B##5, B##6, B##7, B##0, B##1, B##2, Wb, 5); \\
  VSTEP_RING(A##2, A##3, A##4, A##5, A##6, A##7, A##0, A##1, Wa, 6); \\
  VSTEP_RING(B##2, B##3, B##4, B##5, B##6, B##7, B##0, B##1, Wb, 6); \\
  VSTEP_RING(A##1, A##2, A##3, A##4, A##5, A##6, A##7, A##0, Wa, 7); \\
  VSTEP_RING(B##1, B##2, B##3, B##4, B##5, B##6, B##7, B##0, Wb, 7); \\
} while (0)

static void v_compress16x2_prefix(__m512i Sa[8],
                                  const __m512i W0a[16],
                                  __m512i Sb[8],
                                  const __m512i W0b[16]) {
  __m512i Wa[16], Wb[16];
  for (int i = 0; i < 16; i++) { Wa[i] = W0a[i]; Wb[i] = W0b[i]; }
  __m512i a0 = Sa[0], a1 = Sa[1], a2 = Sa[2], a3 = Sa[3],
          a4 = Sa[4], a5 = Sa[5], a6 = Sa[6], a7 = Sa[7];
  /* Shared prefix: rounds 0 to 2 once (see the block
   * comment above). Sb at entry equals Sa by the
   * precondition and is not read. */
  VPREFIX3(a, Wa);
  __m512i b0 = a0, b1 = a1, b2 = a2, b3 = a3,
          b4 = a4, b5 = a5, b6 = a6, b7 = a7;
  /* Rounds 3 to 7 complete the first eight-round unit;
   * the ring orientation returns after round 7, so the
   * remaining seven units are the stock DUAL8. */
  DUAL5_TAIL(a, b, Wa, Wb);
  for (int rep = 1; rep < 8; rep++) {
    int base = rep * 8;
    DUAL8(base, a, b, Wa, Wb);
  }
  Sa[0] = a0; Sa[1] = a1; Sa[2] = a2; Sa[3] = a3;
  Sa[4] = a4; Sa[5] = a5; Sa[6] = a6; Sa[7] = a7;
  Sb[0] = b0; Sb[1] = b1; Sb[2] = b2; Sb[3] = b3;
  Sb[4] = b4; Sb[5] = b5; Sb[6] = b6; Sb[7] = b7;
}

"""

VP_HEADER = """
/* ============================================================
 * EXP-053 vp walkers and exports. The two group
 * functions below are verbatim extractions of v_group2
 * and rm_group2m with the chunk-2 compress call
 * retargeted to v_compress16x2_prefix; the walker spans
 * are verbatim extractions of the stock spans with the
 * renames listed in build_variant.py. Accounting is the
 * stock accounting, unchanged: search is dual-atomic
 * over 32 lanes, batch covers the full range, dummy
 * lanes are computed but never stored or counted.
 * ============================================================ */

"""


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def extract(text, start_anchor, end_anchor=None):
    i = text.index(start_anchor)
    if end_anchor is None:
        j = text.index("\n}\n", i) + 3
    else:
        j = text.index(end_anchor, i) + len(end_anchor)
    return text[i:j]


def generate(prod):
    out = BANNER + prod
    anchor = "static void v_make_w0("
    i = out.index(anchor)
    out = out[:i] + PREFIX_BLOCK.lstrip("\n") + out[i:]

    g2 = extract(prod, "static void v_group2(")
    assert g2.count("v_compress16x2_reg(") == 2
    g2 = g2.replace("v_group2(", "vp_group2(", 1)
    g2 = g2.replace("v_compress16x2_reg(", "v_compress16x2_prefix(", 1)

    g2m = extract(prod, "static uint32_t rm_group2m(")
    assert g2m.count("v_compress16x2_reg(") == 2
    g2m = g2m.replace("rm_group2m(", "vp_group2m(", 1)
    g2m = g2m.replace("v_compress16x2_reg(", "v_compress16x2_prefix(", 1)

    # The batch span runs from the span-walkers banner
    # through the end of bal_vd_batch2; take it manually
    # because extract() stops at the first closing brace.
    s = prod.index("/* ---- span walkers ---- */")
    e = prod.index("\n}\n", prod.index("int bal_vd_batch2(")) + 3
    batch = prod[s:e]
    for old, new in (("VThreadJob", "VPThreadJob"),
                     ("VJob", "VPJob"),
                     ("v_walk", "vp_walk"),
                     ("v_group2(", "vp_group2("),
                     ("v_worker", "vp_worker"),
                     ("v_run(", "vp_run("),
                     ("bal_vd_batch2", "bal_vp_batch2")):
        batch = batch.replace(old, new)
    assert "bal_vp_batch2" in batch and "vp_group2(" in batch

    s = prod.index("typedef struct {\n  const VTemplate *tp;\n"
                   "  uint32_t sw[8];")
    rm = prod[s:]
    for old, new in (("RMThreadJob", "VPRMThreadJob"),
                     ("RMJob", "VPRMJob"),
                     ("rm_walk", "vp_rm_walk"),
                     ("rm_group2m(", "vp_group2m("),
                     ("rm_worker", "vp_rm_worker"),
                     ("bal_vd_search2", "bal_vp_search2")):
        rm = rm.replace(old, new)
    assert "bal_vp_search2" in rm and "vp_group2m(" in rm

    out = out + VP_HEADER + g2 + "\n" + g2m + "\n" + batch + "\n" + rm
    if not out.endswith("\n"):
        out += "\n"
    return out


def cpu_model():
    with open("/proc/cpuinfo") as fh:
        for line in fh:
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    return "unknown"


def main():
    with open(PROD) as fh:
        prod = fh.read()
    gen = generate(prod)
    os.makedirs(SRC, exist_ok=True)
    with open(GEN, "w") as fh:
        fh.write(gen)
    cc = "gcc"
    cmd = [cc, "-O3", "-shared", "-fPIC",
           "-I", os.path.join(ROOT, "mining/cpu"),
           "-mavx512f", "-mavx512bw",
           GEN, "-o", LIB, "-lpthread"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        return 1
    if proc.stderr.strip():
        print("compiler warnings:")
        print(proc.stderr)
    os.makedirs(RAW, exist_ok=True)
    manifest = {
        "experiment": "EXP-053",
        "built_utc": datetime.now(timezone.utc).isoformat(),
        "host_cpu_model": cpu_model(),
        "os_cpu_count": os.cpu_count(),
        "production_source": {
            "path": "mining/cpu/bal_avx512_dual.c",
            "sha256": sha256_file(PROD)},
        "generated_source": {
            "path": "research/sha256d/exp053/src/"
                    "avx512_dual_exp053_prefix.c",
            "sha256": sha256_file(GEN)},
        "variant_binary": {
            "path": "research/sha256d/exp053/src/libbal_e53prefix.so",
            "sha256": sha256_file(LIB)},
        "production_binary": {
            "path": ".local/cpu/libbal_v512dual.so",
            "sha256": sha256_file(
                os.path.join(ROOT, ".local/cpu/libbal_v512dual.so"))},
        "generator": {
            "path": "research/sha256d/exp053/build_variant.py",
            "sha256": sha256_file(os.path.abspath(__file__))},
        "build_command": " ".join(cmd),
        "flags_note": "production restricted set for the "
                      "kernel TU (-mavx512f -mavx512bw, "
                      "never -march=native); probe TU not "
                      "linked (research-only library)",
    }
    with open(os.path.join(RAW, "build_manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2)
    print(f"generated {GEN}")
    print(f"built {LIB}")
    print(f"manifest {os.path.join(RAW, 'build_manifest.json')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
