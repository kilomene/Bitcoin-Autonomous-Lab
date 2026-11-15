#!/usr/bin/env python3
"""AVX-512 flags batch production integration gates.

The EXP-022 (Y-084) flags-only batch was integrated for
the production engine's batch consumers on 2026-11-15,
under the owner's explicit decision (option B), after
EXP-022 returned a VERIFIED IMPROVEMENT in batch scope
under the EXP-017 rule (pooled 1.82x vs the production
batch at density about 0, every session significant)
and EXP-024 reproduced the batch comparison at pooled
1.649x. This suite is the standing gate for that
integration. It proves, through the PRODUCTION engine
path (never the research harness):

- Selection discipline: the flags batch library
  (libbal_v512flags.so) is selected only when the
  flag-free CPUID probe confirms AVX-512F and AVX-512BW,
  the library is complete (bal_v_batchf2 present,
  checked before any call), and a hashlib self-test
  passes in extract and pure modes. Selection never
  changes the search backend: the auto engine still
  selects v512dual for search, requested="v512" still
  selects the single-batch v512 backend, and the pins
  requested="c" and requested="cpu" select no flags
  path at all.
- Digest and candidate exactness: well over 150,000
  randomized batch differentials, flags path against
  hashlib AND against the preserved production batch,
  byte-exact on the digests of flagged lanes and on
  candidate sets; candidate-set equivalence at
  densities 0, about 2^-16, about 2^-8 and 1; the
  wave-boundary sizes 15/16/17/31/32/33/63/64/65 and
  spans ending exactly at 2^32.
- Accounting parity: the flags counted ABI reports
  exactly the attempted and backend counts the
  preserved v512 and v512dual batch ABIs report on
  identical inputs.
- Forced fallback: a probe-failure flags library, a
  symbol-incomplete flags library, a corrupted-source
  build failure, an absent flags library, and a
  runtime flags failure each leave batch_search on
  the preserved digest-materialising batch, producing
  exact candidate sets with batch_path "materialised".
- A fresh regtest block mined through the production
  ComputeEngine and accepted by Core, whose header the
  flags-routed batch_search then re-enumerates,
  returning the block nonce as a candidate.
- An objdump census of the built flags library: zero
  unambiguous AVX-512DQ, VBMI or IFMA mnemonics.

Scope honesty: every ratio attached to this feature
is a BATCH-scope ratio. The search path is not touched
by the integration and no search rate is asserted
anywhere in this suite.

On a machine without AVX-512 the kernel-specific
gates are skipped with a printed reason and the
fallback gates still run: the suite must pass on
every machine the lab supports.

Run: python3 tests/test_avx512_flags_integration.py
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
from mining.cpu.build import (build as build_c, build_v512,
                              build_v512dual, build_v512flags)

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


def predict_batch_backend(count, threads):
    """Independent simulation of the counted batch
    accounting shared by bal_v_batch2, bal_vd_batch2
    and bal_v_batchf2: bal_partition splits the range
    into contiguous spans of ceil(count/threads); each
    span's backend count is its length rounded up to
    whole 16-lane groups."""
    if threads > count:
        threads = count
    chunk = (count + threads - 1) // threads
    total = 0
    pos = 0
    while pos < count:
        span = min(chunk, count - pos)
        total += ((span + 15) // 16) * 16
        pos += span
    return total


def test_selection(supported):
    eng = ComputeEngine()
    if supported:
        assert eng.backend == "v512dual", eng.describe()
        assert eng._vf_lib is not None, eng.v512flags_reason
        assert eng.describe()["v512flags_batch"] is True
        eng_v = ComputeEngine(requested="v512")
        assert eng_v.backend == "v512", eng_v.describe()
        assert eng_v._vf_lib is not None, eng_v.v512flags_reason
        print("ok selection: auto engine keeps v512dual "
              "for search and selects the flags batch; "
              "requested='v512' keeps v512 search and "
              "selects the flags batch")
    else:
        assert eng._vf_lib is None
        assert eng.v512flags_reason and \
            "CPUID" in eng.v512flags_reason, eng.v512flags_reason
        print("ok selection: CPU lacks AVX-512F/BW; flags "
              "batch unselected with the reason recorded, "
              f"search backend is {eng.backend}")
    for req, want_backend in (("c", "c"), ("cpu", "cpu")):
        e = ComputeEngine(requested=req)
        assert e.backend == want_backend, (req, e.describe())
        assert e._vf_lib is None, (req, e.v512flags_reason)
    print("ok pins: requested='c' and requested='cpu' "
          "select no flags path")
    return eng


PROBE_STUB_C = (
    "int bal_v512_supported(void) { return 1; }\n"
    "unsigned bal_v512_feature_bits(void) { return 3u; }\n")
PROBE_FAIL_C = (
    "int bal_v512_supported(void) { return 0; }\n"
    "unsigned bal_v512_feature_bits(void) { return 0u; }\n")
BATCHF_STUB_C = "int bal_v_batchf2(void) { return 0; }\n"


def _build_fake_flags(tmp, name, sources):
    out = os.path.join(tmp, name)
    cc = shutil.which("gcc") or shutil.which("cc")
    proc = subprocess.run(
        [cc, "-shared", "-fPIC", "-O2", "-o", out] + sources,
        capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return out


def _assert_batch_falls_back(vf_path, reason_parts):
    eng = ComputeEngine(vf_lib_path=vf_path)
    assert eng._vf_lib is None, (vf_path, eng.describe())
    assert eng.v512flags_reason, (vf_path, eng.describe())
    for part in reason_parts:
        assert part in eng.v512flags_reason, \
            (vf_path, part, eng.v512flags_reason)
    # The preserved batch still produces the exact
    # candidate set, labelled materialised.
    cands, st = eng.batch_search(GENESIS, DIFF1,
                                 GENESIS_NONCE - 3, 1000)
    assert [c["nonce"] for c in cands] == [GENESIS_NONCE], st
    assert st["batch_path"] == "materialised", st
    return eng


def test_forced_fallbacks(supported):
    """Gate: forced fallback for the flags path. (1)
    Probe failure: a flags library whose CPUID probe
    reports unsupported is never entered. (2) Incomplete
    library: probe only, no bal_v_batchf2; rejected as a
    whole with the missing entry point named (audit D-1
    mirror), and the build smoke test returns its
    designed error instead of raising. (3) Build
    failure: a scratch copy of the build tree with a
    corrupted flags kernel source fails loudly and
    produces no library. (4) Absent library. (5) Runtime
    failure after selection: a flags entry that starts
    returning errors mid-flight makes batch_search fall
    through to the preserved batch for that call."""
    cc = shutil.which("gcc") or shutil.which("cc")
    if not cc:
        print("ok forced fallbacks: skipped, no C compiler "
              "available to build the fake libraries")
        return
    tmp = tempfile.mkdtemp(prefix="bal-flags-fb-")

    def write(name, text):
        p = os.path.join(tmp, name)
        with open(p, "w") as fh:
            fh.write(text)
        return p

    probe_fail = _build_fake_flags(
        tmp, "libfake_flags_probe_fail.so",
        [write("probe_fail.c", PROBE_FAIL_C),
         write("batchf_stub.c", BATCHF_STUB_C)])
    _assert_batch_falls_back(probe_fail, ("CPUID",))

    probe_only = _build_fake_flags(
        tmp, "libfake_flags_probe_only.so",
        [write("probe_stub.c", PROBE_STUB_C)])
    _assert_batch_falls_back(probe_only, ("bal_v_batchf2",))
    err, _supported = cpu_build._smoke_v512flags(probe_only)
    assert err is not None and "bal_v_batchf2" in err, err

    # Build failure in a scratch copy of the build tree.
    scratch = os.path.join(tmp, "tree")
    cpu_dir = os.path.join(scratch, "mining", "cpu")
    os.makedirs(cpu_dir)
    src_dir = os.path.join(os.path.dirname(__file__), "..",
                           "mining", "cpu")
    for name in ("build.py", "bal_avx512_probe.c", "bal_search.h"):
        shutil.copy(os.path.join(src_dir, name),
                    os.path.join(cpu_dir, name))
    with open(os.path.join(cpu_dir, "bal_avx512_flags.c"),
              "w") as fh:
        fh.write("this is not C source; the build must fail\n")
    spec = importlib.util.spec_from_file_location(
        "scratch_build_flags", os.path.join(cpu_dir, "build.py"))
    scratch_build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scratch_build)
    res = scratch_build.build_v512flags(log=lambda *a: None)
    assert res["ok"] is False and res["lib"] is None, res
    absent = os.path.join(scratch, ".local", "cpu",
                          "libbal_v512flags.so")
    assert not os.path.isfile(absent)
    _assert_batch_falls_back(absent, ("not built",))

    # Library absent outright.
    _assert_batch_falls_back(
        os.path.join(tmp, "no_such_libbal_v512flags.so"),
        ("not built",))

    # Runtime failure after a successful selection.
    if supported:
        eng = ComputeEngine()
        assert eng._vf_lib is not None

        class DeadFlags:
            def bal_v_batchf2(self, *args):
                return -1

        eng._vf_lib = DeadFlags()
        cands, st = eng.batch_search(GENESIS, DIFF1,
                                     GENESIS_NONCE - 3, 1000)
        assert [c["nonce"] for c in cands] == [GENESIS_NONCE], st
        assert st["batch_path"] == "materialised", st
    print("ok forced fallbacks: probe failure, incomplete "
          "library (missing entry point named, D-1 mirror), "
          "corrupted-source build failure, absent library "
          "and runtime flags failure each leave batch_search "
          "on the preserved materialised batch with exact "
          "candidate sets")


def test_differentials(eng, eng_v):
    """Randomized differentials through the production
    batch paths. At density 1 every digest is flagged,
    so the flags path's extracted digests are compared
    byte for byte against hashlib AND against the
    preserved production batch's full digest array. At
    about 2^-8 the candidate sets and the flagged
    digests are compared the same three ways."""
    rng = random.Random(0xF022)
    total = 0
    for trial in range(20):
        header = bytes(rng.randrange(256) for _ in range(80))
        count = 8192
        start = rng.randrange(0, NONCE_SPACE - count)
        fpairs = eng._vf_batch_flagged(eng._vf_lib, header, ALL,
                                       start, count)
        assert fpairs is not None and len(fpairs) == count
        vpairs = eng_v._v_batch_flagged(eng_v._v_lib, header, ALL,
                                        start, count, want_all=True)
        assert vpairs is not None and len(vpairs) == count
        fmap = dict(fpairs)
        vmap = dict(vpairs)
        for nonce in range(start, start + count):
            want = cpu_digest(header, nonce)
            assert fmap[nonce] == want, (trial, nonce)
            assert vmap[nonce] == want, (trial, nonce)
        total += count
    assert total >= 150_000, total
    # Sparse density: candidate sets three ways.
    for target, count in ((1 << 248, 65536), (1 << 240, 1 << 18)):
        header = bytes(rng.randrange(256) for _ in range(80))
        start = rng.randrange(0, NONCE_SPACE - count)
        fpairs = eng._vf_batch_flagged(eng._vf_lib, header,
                                       target, start, count)
        vpairs = eng_v._v_batch_flagged(eng_v._v_lib, header,
                                        target, start, count)
        want = recount(header, target, start, count)
        assert dict(fpairs) == want, (target, count)
        assert dict(vpairs) == want, (target, count)
        total += count
    print(f"ok differentials: {total:,} batch differentials "
          "through the production flags path match hashlib "
          "and the preserved production batch byte for byte "
          "on flagged digests and candidate sets (density 1 "
          "full-array comparison plus sparse densities)")


def test_candidate_sets_and_boundaries(eng, eng_v):
    threads = engine_mod.C_THREADS
    # batch_search end to end at four densities, with
    # accounting parity against the independent
    # prediction and the preserved ABIs.
    for target, count in ((1, 65536), (1 << 240, 1 << 18),
                          (1 << 248, 65536), (ALL, 4096)):
        rng = random.Random(0xBEEF + count)
        header = bytes(rng.randrange(256) for _ in range(80))
        start = rng.randrange(0, 1 << 24)
        want = recount(header, target, start, count)
        cands, st = eng.batch_search(header, target, start, count)
        got = {c["nonce"]: bytes.fromhex(c["hash"])[::-1]
               for c in cands}
        assert got == want, (target, count)
        assert st["batch_path"] == "flags", st
        assert st["backend"] == "v512dual", st
        assert st["unique_coverage"] == count, st
        assert st["device_hashes"] == 0, st
        assert st["candidate_count"] == len(want), st
        assert st["verification_hashes"] == len(want), st
        assert st["backend_hashes"] == predict_batch_backend(
            count, threads), st
    # Accounting parity across all three batch ABIs on
    # identical inputs, hit and miss cases alike.
    for target, count in ((1, 30000), (DIFF1, 100000),
                          (ALL, 12345), (1 << 248, 65536)):
        header = bytes(random.Random(count).randrange(256)
                       for _ in range(80))
        start = 777
        eng._vf_batch_flagged(eng._vf_lib, header, target,
                              start, count)
        vf = eng._vf_last_counts
        eng_v._v_batch_flagged(eng_v._v_lib, header, target,
                               start, count)
        v = eng_v._v_last_counts
        eng._vd_batch_flagged(eng._vd_lib, header, target,
                              start, count)
        vd = eng._vd_last_counts
        assert vf == v == vd, (target, count, vf, v, vd)
        assert vf[0] == count, (target, count, vf)
        assert vf[1] == predict_batch_backend(count, threads), \
            (target, count, vf)
    # Wave-boundary sizes, including spans ending exactly
    # at 2^32, digests byte-exact at density 1 and
    # candidate sets exact at about 2^-8.
    total = 0
    for count in (15, 16, 17, 31, 32, 33, 63, 64, 65):
        for start in (0, 12345, NONCE_SPACE - count):
            fpairs = eng._vf_batch_flagged(
                eng._vf_lib, GENESIS, ALL, start, count)
            assert fpairs is not None and len(fpairs) == count
            for nonce, digest in fpairs:
                assert digest == cpu_digest(GENESIS, nonce), \
                    (count, start, nonce)
            fpairs = eng._vf_batch_flagged(
                eng._vf_lib, GENESIS, 1 << 248, start, count)
            assert dict(fpairs) == recount(
                GENESIS, 1 << 248, start, count)
            total += count
    # Target equality meets; target minus one misses,
    # through batch_search on the flags path.
    g = cpu_digest(GENESIS, GENESIS_NONCE)
    gv = int.from_bytes(g, "little")
    cands, st = eng.batch_search(GENESIS, gv, GENESIS_NONCE, 1)
    assert len(cands) == 1 and cands[0]["nonce"] == GENESIS_NONCE
    assert st["batch_path"] == "flags", st
    cands, _st = eng.batch_search(GENESIS, gv - 1, GENESIS_NONCE, 1)
    assert cands == []
    print("ok candidate sets and boundaries: batch_search "
          "candidate sets equal the hashlib recount at "
          "densities 0, 2^-16, 2^-8 and 1 with batch_path "
          "'flags'; attempted/backend accounting identical "
          "across the flags, v512 and v512dual batch ABIs "
          "and equal to the independent prediction; sizes "
          "15/16/17/31/32/33/63/64/65 and spans ending at "
          "2^32 exact; target equality meets, minus one "
          "misses")


def test_objdump_census():
    lib = os.path.join(os.path.dirname(__file__), "..",
                       ".local", "cpu", "libbal_v512flags.so")
    if not shutil.which("objdump"):
        print("ok objdump census: skipped, objdump absent")
        return
    out = subprocess.run(["objdump", "-d", lib],
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    bad = re.findall(
        r"\b(vpmullq|vpermi2[a-z]*|vpermt2[a-z]*|"
        r"vpmultishiftqb|vpmadd52[a-z]*|vcvt[a-z0-9]*qq)\b",
        out.stdout)
    assert bad == [], bad[:5]
    print("ok objdump census: zero unambiguous AVX-512DQ, "
          "VBMI or IFMA mnemonics in the built flags "
          "library (no vpmullq, vpermi2/vpermt2 families, "
          "vpmultishiftqb, vpmadd52 forms or vcvt*qq forms)")


def test_regtest_block(eng):
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
    compute = ComputeEngine()
    assert compute.backend == "v512dual", compute.describe()
    assert compute._vf_lib is not None
    meng = MiningEngine(rpc, payout, compute=compute,
                        batch_size=100_000)
    tip0 = rpc.get_block_count()
    out = meng.mine_cycle(max_batches=1000, deadline_seconds=600)
    assert out["accepted"], out
    assert rpc.get_best_block_hash() == out["hash"]
    assert rpc.get_block_count() == tip0 + 1
    # Re-enumerate the accepted block's header through
    # the flags-routed batch_search: the block nonce
    # must come back as a verified candidate.
    blk = rpc.call("getblock", out["hash"])
    bits = int(blk["bits"], 16)
    exp = bits >> 24
    mant = bits & 0xFFFFFF
    target = mant << (8 * (exp - 3)) if exp > 3 else \
        mant >> (8 * (3 - exp))
    header = (
        blk["version"].to_bytes(4, "little")
        + bytes.fromhex(blk["previousblockhash"])[::-1]
        + bytes.fromhex(blk["merkleroot"])[::-1]
        + blk["time"].to_bytes(4, "little")
        + bits.to_bytes(4, "little")
        + blk["nonce"].to_bytes(4, "little"))
    assert len(header) == 80
    nonce = blk["nonce"]
    start = max(0, nonce - 50000)
    count = nonce - start + 50001
    cands, st = compute.batch_search(header, target, start, count)
    assert st["batch_path"] == "flags", st
    got = {c["nonce"] for c in cands}
    assert nonce in got, (nonce, len(got))
    for c in cands:
        assert verify_candidate(
            header, target, c["nonce"],
            bytes.fromhex(c["hash"])[::-1])
    print(f"ok regtest: fresh block accepted through the "
          f"production ComputeEngine: height {out['height']} "
          f"hash {out['hash']}; its header re-enumerated "
          f"through the flags-routed batch_search returned "
          f"the block nonce among {len(got)} verified "
          f"candidates")
    return out


def main():
    built = build_c(log=lambda *a: None)
    assert built["lib"], built
    v = build_v512(log=lambda *a: None)
    assert v["ok"], v
    vd = build_v512dual(log=lambda *a: None)
    assert vd["ok"], vd
    vf = build_v512flags(log=lambda *a: None)
    assert vf["ok"], vf
    supported = bool(vf["supported"])
    eng = test_selection(supported)
    test_forced_fallbacks(supported)
    test_objdump_census()
    if supported:
        eng_v = ComputeEngine(requested="v512")
        assert eng_v.backend == "v512", eng_v.describe()
        test_differentials(eng, eng_v)
        test_candidate_sets_and_boundaries(eng, eng_v)
        test_regtest_block(eng)
    else:
        print("kernel gates skipped: this CPU cannot "
              "execute the AVX-512 flags batch kernel")
    print("ALL AVX512 FLAGS INTEGRATION TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
