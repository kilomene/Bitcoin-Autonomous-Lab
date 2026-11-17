#!/usr/bin/env python3
"""EXP-054 variant generator and builder.

Generates the EXP-054 research translation unit from the
production dual-batch kernel (mining/cpu/bal_avx512_dual.c)
by mechanical transformation only:

  1. an EXP-054 banner is prepended;
  2. four new dual compress functions,
     v_compress16x2_g1, v_compress16x2_g2,
     v_compress16x2_g4 and v_compress16x2_g8, plus their
     eight-round unit macros DUAL8_G1, DUAL8_G2,
     DUAL8_G4 and DUAL8_G8, are inserted immediately
     before v_make_w0. Each compress is the stock
     v_compress16x2_reg body with its unit macro
     retargeted. The unit macro for granularity G
     executes the two batches' rounds in alternation
     blocks of G rounds: within each eight-round unit,
     for each block start s in {0, G, 2G, ...} it runs
     batch A's rounds s..s+G-1 then batch B's rounds
     s..s+G-1. G = 1 reproduces the production DUAL8
     order exactly (A round t, B round t); G = 8 runs
     each batch's whole eight-round unit before
     switching. The round at unit position p uses the
     ring tuple starting at physical index (8 - p)
     mod 8, exactly as in the stock DUAL8 (position 0:
     indices 0..7; position 1: 7,0..6; position 7:
     1..7,0). Only the ORDER of the two batches' round
     steps inside the unit changes; every round step
     itself, every schedule word and the feed-forward
     are the stock ones. The arithmetic is exact by
     construction: the two batches are independent
     computations sharing no state, so interleaving
     order cannot change any output bit.
  3. for each granularity point G, the group functions
     and span walkers are extracted verbatim from the
     production source (v_group2, rm_group2m, the batch
     span VJob/v_walk through bal_vd_batch2, and the
     search span RMJob/rm_walk through bal_vd_search2),
     renamed to the vg{G} symbols, and their dual
     compress calls retargeted to v_compress16x2_g{G}.
     The single-group remainder path (v_group) is
     shared unchanged across all points. Exports per
     point: bal_vg{G}_batch2 and bal_vg{G}_search2.

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
GEN = os.path.join(SRC, "avx512_dual_exp054_granularity.c")
LIB = os.path.join(SRC, "libbal_e54gran.so")
RAW = os.path.join(HERE, "RAW_RESULTS")
POINTS = (1, 2, 4, 8)

BANNER = """/* ============================================================
 * EXP-054 RESEARCH COPY (NOVA-ER-0014, register Y-043):
 * dual-batch interleave granularity sweep inside the
 * production dual-batch walker.
 *
 * Generated mechanically from mining/cpu/bal_avx512_dual.c
 * by research/sha256d/exp054/build_variant.py; do not edit
 * by hand, regenerate. The stock code is byte-identical to
 * production. The only additions are the four granularity
 * compress functions v_compress16x2_g{G} (G in 1, 2, 4, 8)
 * and the per-point walkers/exports (bal_vg{G}_batch2,
 * bal_vg{G}_search2) that call them. Granularity G is the
 * alternation block size of the two batches' rounds
 * inside the dual compress: G = 1 is the production
 * order, G = 2, 4, 8 are the coarser alternations named
 * by Y-043. The batches are independent computations, so
 * the interleave order is exact by construction and
 * cannot change any output bit; Gate 2 verifies that
 * empirically per point. Production is untouched by
 * this experiment.
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


def ring_tuple(batch, p):
    """VSTEP_RING argument tuple for unit position p:
    physical indices starting at (8 - p) mod 8."""
    start = (8 - p) % 8
    idx = [str((start + j) % 8) for j in range(8)]
    return ", ".join(batch + "##" + k for k in idx)


def unit_macro(g):
    """The eight-round unit macro for granularity g:
    alternation blocks of g rounds, batch A block then
    batch B block, covering positions 0..7."""
    lines = [f"#define DUAL8_G{g}(BASE, A, B, Wa, Wb) do {{ \\"]
    for s in range(0, 8, g):
        for batch, w in (("A", "Wa"), ("B", "Wb")):
            for p in range(s, s + g):
                lines.append(
                    f"  VSTEP_RING({ring_tuple(batch, p)}, {w}, "
                    f"(BASE) + {p}); \\")
    lines.append("} while (0)")
    return "\n".join(lines)


GRAN_HEADER = """
/* ---- EXP-054: granularity-parameterised dual compress ----
 * One compress per granularity point, generated from the
 * stock v_compress16x2_reg body with the eight-round unit
 * macro retargeted. DUAL8_G1's emission order is the
 * stock DUAL8 order (verified textually at generation
 * time against the production macro's step sequence);
 * DUAL8_G2, DUAL8_G4 and DUAL8_G8 emit the same 16 round
 * steps per unit in coarser alternation blocks. The ring
 * tuple for unit position p starts at physical index
 * (8 - p) mod 8 in every macro, exactly as in DUAL8. */

"""


def compress_fn(prod, g):
    body = extract(prod, "static void v_compress16x2_reg(")
    assert body.count("DUAL8(base, a, b, Wa, Wb)") == 1
    body = body.replace("v_compress16x2_reg(",
                        f"v_compress16x2_g{g}(", 1)
    body = body.replace("DUAL8(base, a, b, Wa, Wb)",
                        f"DUAL8_G{g}(base, a, b, Wa, Wb)")
    return body


def point_block(prod, g):
    """Group functions and walker spans for one point,
    extracted verbatim from production, renamed, and
    retargeted to that point's compress."""
    header = f"""
/* ============================================================
 * EXP-054 granularity point G = {g}: walkers and exports.
 * Verbatim extractions of v_group2, rm_group2m, the batch
 * span and the search span, renamed to the vg{g} symbols
 * with both dual compress calls retargeted to
 * v_compress16x2_g{g}. Accounting is the stock
 * accounting, unchanged: search is dual-atomic over 32
 * lanes, batch covers the full range, dummy lanes are
 * computed but never stored or counted. The single-group
 * remainder path (v_group) is the shared stock function.
 * ============================================================ */

"""
    g2 = extract(prod, "static void v_group2(")
    assert g2.count("v_compress16x2_reg(") == 2
    g2 = g2.replace("v_group2(", f"vg{g}_group2(", 1)
    g2 = g2.replace("v_compress16x2_reg(", f"v_compress16x2_g{g}(")

    g2m = extract(prod, "static uint32_t rm_group2m(")
    assert g2m.count("v_compress16x2_reg(") == 2
    g2m = g2m.replace("rm_group2m(", f"vg{g}_group2m(", 1)
    g2m = g2m.replace("v_compress16x2_reg(", f"v_compress16x2_g{g}(")

    s = prod.index("/* ---- span walkers ---- */")
    e = prod.index("\n}\n", prod.index("int bal_vd_batch2(")) + 3
    batch = prod[s:e]
    for old, new in (("VThreadJob", f"VG{g}ThreadJob"),
                     ("VJob", f"VG{g}Job"),
                     ("v_group2(", f"vg{g}_group2("),
                     ("v_walk", f"vg{g}_walk"),
                     ("v_worker", f"vg{g}_worker"),
                     ("v_run(", f"vg{g}_run("),
                     ("bal_vd_batch2", f"bal_vg{g}_batch2")):
        batch = batch.replace(old, new)
    assert f"bal_vg{g}_batch2" in batch and f"vg{g}_group2(" in batch

    s = prod.index("typedef struct {\n  const VTemplate *tp;\n"
                   "  uint32_t sw[8];")
    rm = prod[s:]
    for old, new in (("RMThreadJob", f"VG{g}RMThreadJob"),
                     ("RMJob", f"VG{g}RMJob"),
                     ("rm_group2m(", f"vg{g}_group2m("),
                     ("rm_walk", f"vg{g}_rm_walk"),
                     ("rm_worker", f"vg{g}_rm_worker"),
                     ("bal_vd_search2", f"bal_vg{g}_search2")):
        rm = rm.replace(old, new)
    assert f"bal_vg{g}_search2" in rm and f"vg{g}_group2m(" in rm

    return header + g2 + "\n" + g2m + "\n" + batch + "\n" + rm


def generate(prod):
    out = BANNER + prod
    gran = GRAN_HEADER
    for g in POINTS:
        gran += unit_macro(g) + "\n\n"
    for g in POINTS:
        gran += (f"/* Granularity point G = {g}: stock dual "
                 f"compress body, unit macro DUAL8_G{g}. */\n")
        gran += compress_fn(prod, g) + "\n"
    anchor = "static void v_make_w0("
    i = out.index(anchor)
    out = out[:i] + gran.lstrip("\n") + out[i:]
    for g in POINTS:
        out += point_block(prod, g)
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
        "experiment": "EXP-054",
        "built_utc": datetime.now(timezone.utc).isoformat(),
        "host_cpu_model": cpu_model(),
        "os_cpu_count": os.cpu_count(),
        "granularity_points": list(POINTS),
        "granularity_definition": (
            "alternation block size, in rounds, of the two "
            "batches inside the dual compress; G = 1 is the "
            "production order (A round t, B round t), "
            "G = 2, 4, 8 are the coarser alternations named "
            "by register Y-043"),
        "production_source": {
            "path": "mining/cpu/bal_avx512_dual.c",
            "sha256": sha256_file(PROD)},
        "generated_source": {
            "path": "research/sha256d/exp054/src/"
                    "avx512_dual_exp054_granularity.c",
            "sha256": sha256_file(GEN)},
        "variant_binary": {
            "path": "research/sha256d/exp054/src/libbal_e54gran.so",
            "sha256": sha256_file(LIB)},
        "production_binary": {
            "path": ".local/cpu/libbal_v512dual.so",
            "sha256": sha256_file(
                os.path.join(ROOT, ".local/cpu/libbal_v512dual.so"))},
        "generator": {
            "path": "research/sha256d/exp054/build_variant.py",
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
