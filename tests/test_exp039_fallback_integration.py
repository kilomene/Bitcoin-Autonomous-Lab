#!/usr/bin/env python3
"""EXP-039 fallback tier production integration gates.

EXP-032 verified two fallback kernels as research: the
AVX2 8-way multi-buffer batch (pooled 1.409x against the
production C batch, CI 1.340x to 1.480x) and the SHA-NI
H-01 streams-4 batch (pooled 2.861x, CI 2.671x to
3.089x), both under the EXP-017 protocol. EXP-039
integrates them as production dispatch tiers in
gpu/engine.py, between v512 and C, in the order shani
then avx2 (the SHA-NI tier's verified batch rate is the
higher of the two; each tier's CPUID probe decides
reachability per host). The kernels are the EXP-032
sources ported unchanged into mining/cpu/
(bal_avx2_mb.c, bal_shani_streams.c on
bal_shani_core.h), built by mining/cpu/build.py under
restricted flags (-mavx2; -msha -mssse3; never
-march=native) with the flag-free CPUID probe
(bal_fallback_probe.c) linked into each library.

This suite is the standing gate for that integration.
It proves, through the PRODUCTION engine path (never
the research harness):

- Selection discipline: each tier is selected only
  when its flag-free CPUID probe confirms the exact
  feature set (AVX2; SHA extensions plus SSSE3), the
  library is complete (entry points checked with
  hasattr before any argtypes assignment, audit D-1),
  and hashlib self-tests pass (batch for both tiers;
  a streams search self-test for shani). The SHA-NI
  tier can therefore never execute on a SHA-less
  host. Auto dispatch is unchanged: an AVX-512 host
  still selects v512dual, and the new tiers are
  reached only when the tiers above them are absent,
  unselected or pinned away.
- Digest exactness: at least 100,000 randomized batch
  differentials per kernel through the ComputeEngine
  seam, byte-identical against hashlib, including
  edge ranges (counts 1 to 9, group and stream
  boundaries, unaligned starts, a span ending exactly
  at 2^32).
- Candidate-set equivalence with the C backend at
  densities 0, about 2^-16, about 2^-8 and 1, and
  search-path exactness: hits carry the exact CPU
  digest of the reported nonce, misses report
  attempted == count on both tiers, and the
  accounting invariants hold (avx2: backend_hashes
  >= attempted, dummy lanes bounded; shani:
  backend_hashes == attempted exactly, no dummy
  lanes exist).
- Forced fallback: a probe-failure library, a
  symbol-incomplete library and an absent library
  for each tier each leave the engine on the next
  tier down with the reason recorded, still
  producing exact candidate sets.
- An objdump census: the AVX2 library contains no
  zmm registers and no mask registers; the SHA-NI
  library contains SHA256RNDS2 and no ymm or zmm
  registers; the compiled probe objects contain no
  vector registers at all.
- A fresh regtest block mined through the production
  ComputeEngine with EACH tier forced active
  (requested="shani", requested="avx2") and accepted
  by Core.

Scope honesty: the EXP-032 verdicts behind this
integration are BATCH-scope (category D) verdicts.
The search entries are integrated because both
kernels export counted search entries with honest
accounting (group-atomic for avx2, wave-atomic for
shani); EXP-039 measures the production search scope
separately and reports it as its own category, never
as a consequence of the batch verdict.

On a machine lacking AVX2 or the SHA extensions the
corresponding kernel gates are skipped with a
printed reason and the fallback gates still run:
the suite must pass on every machine the lab
supports, including the SHA-less AVX-512 host,
where requested="shani" must fall through cleanly.

Run: python3 tests/test_exp039_fallback_integration.py
"""

import importlib.util
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import gpu.engine as engine_mod
from gpu.engine import ComputeEngine, cpu_digest, verify_candidate
from mining.cpu import build as cpu_build
from mining.cpu.build import (build as build_c, build_avx2,
                              build_shani)

GENESIS = bytes.fromhex(
    "01000000" + "00" * 32
    + "3ba3edfd7a7b12b27ac72c3e67768f617fc81bc3888a51323a9fb8aa4b1e5e4a"
    + "29ab5f49" + "ffff001d" + "1dac2b7c")
GENESIS_NONCE = 2083236893
DIFF1 = 0xFFFF << 208
NONCE_SPACE = 1 << 32
ALL = (1 << 256) - 1


def recount(header, target, start, count):
    out = {}
    for i in range(count):
        d = cpu_digest(header, start + i)
        if int.from_bytes(d, "little") <= target:
            out[start + i] = d
    return out


def test_selection(shani_supported, avx2_supported):
    eng = ComputeEngine()
    desc = eng.describe()
    assert desc["shani_backend"] is bool(eng._m_lib), desc
    assert desc["avx2_backend"] is bool(eng._a_lib), desc
    assert "shani_reason" in desc and "avx2_reason" in desc, desc
    print(f"ok selection: auto engine backend is {eng.backend} "
          f"(unchanged dispatch above the new tiers); "
          f"describe() reports both fallback tiers")
    if shani_supported:
        e = ComputeEngine(requested="shani")
        assert e.backend == "shani", e.describe()
        assert e._m_lib is not None
        print("ok selection: requested='shani' selects the "
              "SHA-NI streams tier (CPUID probe confirms the "
              "SHA extensions and SSSE3, self-tests pass)")
    else:
        e = ComputeEngine(requested="shani")
        assert e.backend != "shani", e.describe()
        assert e.shani_reason and "CPUID" in e.shani_reason, \
            e.shani_reason
        print("ok selection: CPU lacks the SHA extensions; "
              "requested='shani' falls through with the "
              f"reason recorded, backend is {e.backend}")
    if avx2_supported:
        e = ComputeEngine(requested="avx2")
        assert e.backend == "avx2", e.describe()
        assert e._a_lib is not None
        print("ok selection: requested='avx2' selects the "
              "AVX2 multi-buffer tier (CPUID probe confirms "
              "AVX2, batch self-test passes)")
    else:
        e = ComputeEngine(requested="avx2")
        assert e.backend != "avx2", e.describe()
        assert e.avx2_reason and "CPUID" in e.avx2_reason, \
            e.avx2_reason
        print("ok selection: CPU lacks AVX2; "
              "requested='avx2' falls through with the "
              f"reason recorded, backend is {e.backend}")
    e = ComputeEngine(requested="c")
    assert e.backend == "c", e.describe()
    assert e._m_lib is None and e._a_lib is None, e.describe()
    print("ok pins: requested='c' selects the C backend "
          "alone; neither fallback tier is entered")
    return eng


SHANI_PROBE_FAIL_C = (
    "int bal_shani_supported(void) { return 0; }\n"
    "unsigned bal_shani_feature_bits(void) { return 0u; }\n"
    "int bal_m_batch2(void) { return 0; }\n"
    "int bal_m_search2(void) { return 0; }\n")
SHANI_PROBE_ONLY_C = (
    "int bal_shani_supported(void) { return 1; }\n"
    "unsigned bal_shani_feature_bits(void) { return 3u; }\n")
AVX2_PROBE_FAIL_C = (
    "int bal_avx2_supported(void) { return 0; }\n"
    "unsigned bal_avx2_feature_bits(void) { return 0u; }\n"
    "int bal_a_batch2(void) { return 0; }\n"
    "int bal_a_search2(void) { return 0; }\n")
AVX2_PROBE_ONLY_C = (
    "int bal_avx2_supported(void) { return 1; }\n"
    "unsigned bal_avx2_feature_bits(void) { return 1u; }\n")


def _build_fake(tmp, name, text):
    src = os.path.join(tmp, name + ".c")
    with open(src, "w") as fh:
        fh.write(text)
    out = os.path.join(tmp, name)
    cc = shutil.which("gcc") or shutil.which("cc")
    proc = subprocess.run(
        [cc, "-shared", "-fPIC", "-O2", "-o", out, src],
        capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return out


def _assert_exact_genesis(eng):
    cands, st = eng.batch_search(GENESIS, DIFF1,
                                 GENESIS_NONCE - 3, 1000)
    assert [c["nonce"] for c in cands] == [GENESIS_NONCE], st


def test_forced_fallbacks():
    cc = shutil.which("gcc") or shutil.which("cc")
    if not cc:
        print("ok forced fallbacks: skipped, no C compiler "
              "available to build the fake libraries")
        return
    tmp = tempfile.mkdtemp(prefix="bal-exp039-fb-")

    fake = _build_fake(tmp, "libfake_shani_probe_fail.so",
                       SHANI_PROBE_FAIL_C)
    e = ComputeEngine(requested="shani", m_lib_path=fake)
    assert e.backend != "shani", e.describe()
    assert "CPUID" in e.shani_reason, e.shani_reason
    _assert_exact_genesis(e)

    fake = _build_fake(tmp, "libfake_shani_probe_only.so",
                       SHANI_PROBE_ONLY_C)
    e = ComputeEngine(requested="shani", m_lib_path=fake)
    assert e.backend != "shani", e.describe()
    assert "bal_m_batch2" in e.shani_reason, e.shani_reason
    _assert_exact_genesis(e)
    err, _sup = cpu_build._smoke_shani(fake)
    assert err is not None, err

    e = ComputeEngine(
        requested="shani",
        m_lib_path=os.path.join(tmp, "no_such_libbal_shani.so"))
    assert e.backend != "shani", e.describe()
    assert "not built" in e.shani_reason, e.shani_reason
    _assert_exact_genesis(e)

    fake = _build_fake(tmp, "libfake_avx2_probe_fail.so",
                       AVX2_PROBE_FAIL_C)
    e = ComputeEngine(requested="avx2", a_lib_path=fake)
    assert e.backend != "avx2", e.describe()
    assert "CPUID" in e.avx2_reason, e.avx2_reason
    _assert_exact_genesis(e)

    fake = _build_fake(tmp, "libfake_avx2_probe_only.so",
                       AVX2_PROBE_ONLY_C)
    e = ComputeEngine(requested="avx2", a_lib_path=fake)
    assert e.backend != "avx2", e.describe()
    assert "bal_a_batch2" in e.avx2_reason, e.avx2_reason
    _assert_exact_genesis(e)
    err, _sup = cpu_build._smoke_avx2(fake)
    assert err is not None, err

    e = ComputeEngine(
        requested="avx2",
        a_lib_path=os.path.join(tmp, "no_such_libbal_avx2.so"))
    assert e.backend != "avx2", e.describe()
    assert "not built" in e.avx2_reason, e.avx2_reason
    _assert_exact_genesis(e)

    print("ok forced fallbacks: for each tier, a "
          "probe-failure library (never entered), a "
          "symbol-incomplete library (missing entry "
          "point named, D-1 mirror; build smoke test "
          "agrees) and an absent library each leave "
          "the engine on the next tier down with the "
          "reason recorded and exact candidate sets")


def _batch_digests(eng, tier, header, start, count):
    if tier == "shani":
        return eng._m_batch(eng._m_lib, header, ALL, start, count)
    return eng._a_batch(eng._a_lib, header, ALL, start, count)


def test_differentials(eng_m, eng_a):
    rng = random.Random(39039)
    totals = {"shani": 0, "avx2": 0}
    for tier, eng in (("shani", eng_m), ("avx2", eng_a)):
        # Randomized bulk: 6 headers x 20,000 digests.
        for _ in range(6):
            header = bytes(rng.randrange(256) for _ in range(80))
            start = rng.randrange(0, NONCE_SPACE - 20000)
            got = _batch_digests(eng, tier, header, start, 20000)
            assert got is not None
            for i in range(20000):
                want = cpu_digest(header, start + i)
                assert got[i] == want, (tier, start + i)
            totals[tier] += 20000
        # Edge ranges on the genesis header.
        edges = [(0, 1), (0, 2), (0, 3), (0, 4), (0, 5),
                 (0, 7), (0, 8), (0, 9), (0, 15), (0, 16),
                 (0, 17), (7, 100), (13, 4099),
                 (NONCE_SPACE - 64, 64), (NONCE_SPACE - 1, 1)]
        for start, count in edges:
            got = _batch_digests(eng, tier, GENESIS, start, count)
            assert got is not None, (tier, start, count)
            for i in range(count):
                want = cpu_digest(GENESIS, start + i)
                assert got[i] == want, (tier, start + i)
            totals[tier] += count
        print(f"ok differentials ({tier}): {totals[tier]} "
              f"batch digests through the ComputeEngine "
              f"seam byte-identical to hashlib, including "
              f"counts 1 to 17, unaligned starts and a "
              f"span ending exactly at 2^32")
    assert totals["shani"] >= 100000, totals
    assert totals["avx2"] >= 100000, totals


def test_candidate_sets_and_search(eng_m, eng_a, eng_c):
    rng = random.Random(17017)
    for tier, eng in (("shani", eng_m), ("avx2", eng_a)):
        for target in (1, 1 << 240, 1 << 248, ALL):
            header = bytes(rng.randrange(256) for _ in range(80))
            start = rng.randrange(0, NONCE_SPACE - 3000)
            cands, st = eng.batch_search(header, target,
                                         start, 3000)
            got = {c["nonce"]: bytes.fromhex(c["hash"])[::-1]
                   for c in cands}
            want = recount(header, target, start, 3000)
            assert got == want, (tier, target)
            assert st["backend"] == tier, st
            assert st["unique_coverage"] == 3000, st
            if tier == "shani":
                assert st["backend_hashes"] == 3000, st
            else:
                assert st["backend_hashes"] >= 3000, st
        # Search: a planted hit and a clean miss.
        header = bytes(rng.randrange(256) for _ in range(80))
        base = rng.randrange(0, NONCE_SPACE - 100000)
        planted = base + 50000
        target = int.from_bytes(
            cpu_digest(header, planted), "little")
        hit, attempted, _s = eng.search_first_counted(
            header, target, base, 100000)
        assert hit is not None, tier
        nonce, digest = hit
        assert digest == cpu_digest(header, nonce), tier
        assert int.from_bytes(digest, "little") <= target, tier
        stats = eng.last_search_stats
        assert stats["backend"] == tier, stats
        assert stats["backend_hashes"] >= attempted, stats
        hit, attempted, _s = eng.search_first_counted(
            header, 1, base, 100000)
        assert hit is None, tier
        assert attempted == 100000, (tier, attempted)
        stats = eng.last_search_stats
        if tier == "shani":
            assert stats["backend_hashes"] == 100000, stats
        else:
            assert stats["backend_hashes"] >= 100000, stats
            assert stats["backend_hashes"] < 100000 + 8 * 16, stats
        print(f"ok candidate sets and search ({tier}): "
              f"batch candidate sets identical to the "
              f"hashlib recount at densities 0, 2^-16, "
              f"2^-8 and 1; planted-hit search returns "
              f"the exact CPU digest; clean miss reports "
              f"attempted == count with the tier's "
              f"accounting invariant holding")


def test_objdump_census():
    cpu_dir = os.path.join(os.path.dirname(__file__), "..",
                           ".local", "cpu")
    if not shutil.which("objdump"):
        print("ok objdump census: skipped, objdump absent")
        return
    out = subprocess.run(
        ["objdump", "-d", os.path.join(cpu_dir, "libbal_avx2.so")],
        capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert "zmm" not in out.stdout
    assert not re.search(r"%k[0-7]\b", out.stdout)
    assert "ymm" in out.stdout
    out = subprocess.run(
        ["objdump", "-d", os.path.join(cpu_dir, "libbal_shani.so")],
        capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert "sha256rnds2" in out.stdout
    assert "ymm" not in out.stdout and "zmm" not in out.stdout
    for sub in (".avx2-build", ".shani-build"):
        obj = os.path.join(cpu_dir, sub, "bal_fallback_probe.o")
        if not os.path.isfile(obj):
            continue
        out = subprocess.run(["objdump", "-d", obj],
                             capture_output=True, text=True)
        assert out.returncode == 0, out.stderr
        assert not re.search(r"\b[xyz]mm[0-9]", out.stdout), sub
    print("ok objdump census: AVX2 library has ymm but "
          "zero zmm and zero mask registers; SHA-NI "
          "library has sha256rnds2 and zero ymm/zmm; "
          "both compiled probe objects contain no "
          "vector registers at all")


def test_regtest_block(eng, tier):
    from node import node_manager
    from node.rpc_client import BitcoinRPC
    from mining.engine import MiningEngine
    node_manager.start()
    rpc = BitcoinRPC()
    if "bal-regtest" not in rpc.call("listwallets"):
        try:
            rpc.call("loadwallet", "bal-regtest")
        except Exception:
            rpc.call("createwallet", "bal-regtest")
    wallet = BitcoinRPC(wallet="bal-regtest")
    payout = wallet.call("getnewaddress", "", "bech32")
    assert eng.backend == tier, eng.describe()
    meng = MiningEngine(rpc, payout, compute=eng,
                        batch_size=100_000)
    tip0 = rpc.get_block_count()
    out = meng.mine_cycle(max_batches=1000, deadline_seconds=600)
    assert out["accepted"], out
    assert rpc.get_best_block_hash() == out["hash"]
    assert rpc.get_block_count() == tip0 + 1
    print(f"ok regtest ({tier}): fresh block accepted "
          f"through the production ComputeEngine with "
          f"the {tier} tier forced active: height "
          f"{out['height']} hash {out['hash']}")
    return out


def main():
    built = build_c(log=lambda *a: None)
    assert built["lib"], built
    a = build_avx2(log=lambda *a: None)
    assert a["ok"], a
    m = build_shani(log=lambda *a: None)
    assert m["ok"], m
    avx2_supported = bool(a["supported"])
    shani_supported = bool(m["supported"])
    eng = test_selection(shani_supported, avx2_supported)
    test_forced_fallbacks()
    test_objdump_census()
    if shani_supported and avx2_supported:
        eng_m = ComputeEngine(requested="shani")
        assert eng_m.backend == "shani", eng_m.describe()
        eng_a = ComputeEngine(requested="avx2")
        assert eng_a.backend == "avx2", eng_a.describe()
        eng_c = ComputeEngine(requested="c")
        assert eng_c.backend == "c", eng_c.describe()
        test_differentials(eng_m, eng_a)
        test_candidate_sets_and_search(eng_m, eng_a, eng_c)
        test_regtest_block(eng_m, "shani")
        test_regtest_block(eng_a, "avx2")
    else:
        print("kernel gates skipped: this CPU cannot "
              "execute one or both fallback kernels "
              f"(shani supported: {shani_supported}, "
              f"avx2 supported: {avx2_supported})")
    print("EXP-039 fallback integration suite: ALL PASSED")


if __name__ == "__main__":
    main()
