#!/usr/bin/env python3
"""EXP-041 variant generator and builder.

Generates research copies of the production AVX-512 MB
kernel (mining/cpu/bal_avx512_mb.c) that differ ONLY in
the Maj expression inside v_compress16 (plus, for tfull,
the Ch expression), builds each with the production
restricted flag set (gcc -O3 -shared -fPIC -mavx512f
-mavx512bw, never -march=native), and records a build
manifest. Production files are never touched.

Variants:
  base  unchanged expressions (rebuild control)
  alta  Maj_alt_A: (a&b) ^ (c & (a^b))   [Phase 5 proven]
  altb  Maj_alt_B: (a & (b^c)) ^ (b&c)   [Phase 5 proven]
  altc  Maj OR form: (a&b) | (c & (a|b))
  tmaj  Maj only as _mm512_ternarylogic_epi32(a,b,c,0xE8)
  tfull Ch 0xCA and Maj 0xE8 intrinsics (P6C-007 replica
        on the current production source)

Flag census variants (base source, census only):
  base_o2     -O2 instead of -O3
  base_znver3 -O3 -mtune=znver3 (tuning only, no ISA change)
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
PROD = os.path.join(ROOT, "mining/cpu/bal_avx512_mb.c")
RESTRICTED = ["-mavx512f", "-mavx512bw"]

MAJ_CLASSIC = (
    "    __m512i mj = _mm512_xor_si512(\n"
    "      _mm512_xor_si512(_mm512_and_epi32(a, b),\n"
    "                       _mm512_and_epi32(a, c)),\n"
    "      _mm512_and_epi32(b, c));")
CH_CLASSIC = (
    "    __m512i ch = _mm512_xor_si512(_mm512_and_epi32(e, f),\n"
    "                                  _mm512_andnot_epi32(e, g));")

MAJ_ALTA = (
    "    __m512i mj = _mm512_xor_si512(\n"
    "      _mm512_and_epi32(a, b),\n"
    "      _mm512_and_epi32(c, _mm512_xor_si512(a, b)));")
MAJ_ALTB = (
    "    __m512i mj = _mm512_xor_si512(\n"
    "      _mm512_and_epi32(a, _mm512_xor_si512(b, c)),\n"
    "      _mm512_and_epi32(b, c));")
MAJ_ALTC = (
    "    __m512i mj = _mm512_or_si512(\n"
    "      _mm512_and_epi32(a, b),\n"
    "      _mm512_and_epi32(c, _mm512_or_si512(a, b)));")
MAJ_TERN = "    __m512i mj = _mm512_ternarylogic_epi32(a, b, c, 0xE8);"
CH_TERN = "    __m512i ch = _mm512_ternarylogic_epi32(e, f, g, 0xCA);"

VARIANTS = {
    "base": ("unchanged classic Maj and Ch expressions "
             "(rebuild control)", None, None),
    "alta": ("Maj_alt_A (a&b) ^ (c & (a^b))", MAJ_ALTA, None),
    "altb": ("Maj_alt_B (a & (b^c)) ^ (b&c)", MAJ_ALTB, None),
    "altc": ("Maj OR form (a&b) | (c & (a|b))", MAJ_ALTC, None),
    "tmaj": ("Maj as single VPTERNLOGD intrinsic 0xE8, "
             "Ch classic", MAJ_TERN, None),
    "tfull": ("Ch 0xCA and Maj 0xE8 VPTERNLOGD intrinsics "
              "(P6C-007 form)", MAJ_TERN, CH_TERN),
}

BANNER = ("/* EXP-041 variant {tag}: {desc}.\n"
          " * Research copy of mining/cpu/bal_avx512_mb.c with\n"
          " * ONLY the v_compress16 Boolean expression(s) named\n"
          " * above changed and the counted-ABI exports renamed\n"
          " * to bal_e41{tag}_batch2 / bal_e41{tag}_search2.\n"
          " * Production code is untouched by this experiment. */\n")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def gen_source(tag, desc, maj, ch):
    with open(PROD) as fh:
        text = fh.read()
    assert text.count(MAJ_CLASSIC) == 1, "classic Maj block not unique"
    assert text.count(CH_CLASSIC) == 1, "classic Ch block not unique"
    if maj is not None:
        text = text.replace(MAJ_CLASSIC, maj)
    if ch is not None:
        text = text.replace(CH_CLASSIC, ch)
    text = text.replace("bal_v_batch2", f"bal_e41{tag}_batch2")
    text = text.replace("bal_v_search2", f"bal_e41{tag}_search2")
    text = BANNER.format(tag=tag, desc=desc) + text
    out = os.path.join(SRC, f"bal_avx512_mb_exp041_{tag}.c")
    with open(out, "w") as fh:
        fh.write(text)
    return out


def build(src_path, out_path, extra_flags):
    cmd = (["gcc", "-O3", "-shared", "-fPIC", "-I",
            os.path.join(ROOT, "mining/cpu")] + RESTRICTED
           + extra_flags + [src_path, "-o", out_path])
    if "-O2" in extra_flags:
        cmd[1] = "-O2"
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(res.stdout)
        print(res.stderr, file=sys.stderr)
        raise SystemExit(f"build failed: {out_path}")
    return " ".join(cmd)


def main():
    os.makedirs(SRC, exist_ok=True)
    manifest = {
        "experiment": "EXP-041",
        "built_utc": datetime.now(timezone.utc).isoformat(),
        "production_source": "mining/cpu/bal_avx512_mb.c",
        "production_source_sha256": sha256_file(PROD),
        "production_binary": ".local/cpu/libbal_v512.so",
        "production_binary_sha256": sha256_file(
            os.path.join(ROOT, ".local/cpu/libbal_v512.so")),
        "variants": {},
    }
    for tag, (desc, maj, ch) in VARIANTS.items():
        src = gen_source(tag, desc, maj, ch)
        out = os.path.join(SRC, f"libbal_e41{tag}.so")
        cmd = build(src, out, [])
        manifest["variants"][tag] = {
            "description": desc,
            "source": os.path.relpath(src, ROOT),
            "source_sha256": sha256_file(src),
            "binary": os.path.relpath(out, ROOT),
            "binary_sha256": sha256_file(out),
            "build_command": cmd,
        }
        print(f"built {tag}: {out}")
    base_src = os.path.join(SRC, "bal_avx512_mb_exp041_base.c")
    for tag, extra in (("base_o2", ["-O2"]),
                       ("base_znver3", ["-mtune=znver3"])):
        out = os.path.join(SRC, f"libbal_e41{tag}.so")
        cmd = build(base_src, out, extra)
        manifest["variants"][tag] = {
            "description": f"base source, flag variant {extra} "
                           "(census only)",
            "source": os.path.relpath(base_src, ROOT),
            "binary": os.path.relpath(out, ROOT),
            "binary_sha256": sha256_file(out),
            "build_command": cmd,
        }
        print(f"built {tag}: {out}")
    mpath = os.path.join(HERE, "RAW_RESULTS", "build_manifest.json")
    os.makedirs(os.path.dirname(mpath), exist_ok=True)
    with open(mpath, "w") as fh:
        json.dump(manifest, fh, indent=1)
    print("manifest:", mpath)
    return 0


if __name__ == "__main__":
    sys.exit(main())
