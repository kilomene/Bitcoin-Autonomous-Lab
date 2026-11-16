#!/usr/bin/env python3
"""AVX-512 DualMask production integration gates.

The EXP-026 candidate C2 kernel (DualMask: the EXP-018
register-resident dual-batch kernel plus the EXP-024
opmask target compare) was integrated as a production
ComputeEngine backend ("v512dual") on 2026-11-14, under
the owner's explicit decision, after EXP-026 returned a
VERIFIED IMPROVEMENT under the EXP-017 rule (pooled
1.718x vs the production single-batch search, 1.444x vs
its strongest single ingredient). This suite is the
standing gate for that integration. It proves, through
the PRODUCTION engine path (never the research harness):

- Runtime CPUID dispatch: the auto engine selects
  "v512dual" only when the flag-free probe in
  libbal_v512dual.so confirms AVX-512F and AVX-512BW;
  requesting "v512" still selects the single-batch v512
  backend alone and requesting "c" still selects C.
- Digest exactness: well over 100,000 randomized
  differentials against hashlib through the production
  batch ABI, plus the wave-boundary batch sizes
  15/16/17/31/32/33/63/64/65 and spans ending exactly
  at 2^32.
- Candidate sets equal to an independent hashlib
  recount at mainnet-like density and at about 2^-12.
- Accounting parity with the dual-atomic contract:
  on a miss, attempted is exactly the range size and
  backend_hashes is exactly the lane count predicted
  by an independent simulation of the dual walker
  (32 lane computations per dual group, 16 per
  single-group tail); on a hit, backend_hashes is a
  whole number of 16-lane groups and never below
  attempted.
- Forced fallback three ways, in scratch copies only:
  a probe-failure library, a dual build failure, and
  an absent dual library each land on v512 and keep
  mining correctly; symbol-incomplete dual libraries
  are rejected as a whole with the missing entry
  points named (audit defect D-1 regression gate,
  mirrored for the dual backend).
- A fresh regtest block mined through the production
  engine with the DualMask backend selected and
  accepted by Core.

On a machine without AVX-512 the kernel-specific gates
are skipped with a printed reason and the fallback
gates still run: the suite must pass on every machine
the lab supports.

Run: python3 tests/test_avx512_dual_integration.py
"""

import importlib.util
import os
import random
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import gpu.engine as engine_mod
from gpu.engine import ComputeEngine, cpu_digest, verify_candidate
from mining.cpu import build as cpu_build
from mining.cpu.build import build as build_c, build_v512, build_v512dual

GENESIS = bytes.fromhex(
    "01000000" + "00" * 32
    + "3ba3edfd7a7b12b27ac72c3e67768f617fc81bc3888a51323a9fb8aa4b1e5e4a"
    + "29ab5f49" + "ffff001d" + "1dac2b7c")
GENESIS_NONCE = 2083236893
DIFF1 = 0xFFFF << 208
NONCE_SPACE = 1 << 32


def recount(header, target, start, count):
    out = {}
    for i in range(count):
        d = cpu_digest(header, start + i)
        if int.from_bytes(d, "little") <= target:
            out[start + i] = d
    return out


def predict_miss_backend(count, threads):
    """Independent simulation of the dual walker's lane
    accounting on a full miss: bal_partition splits the
    range into contiguous spans; each span advances in
    dual groups (backend += 32, attempted += up to 32)
    while at least 17 nonces remain, then finishes with
    one single group (backend += 16)."""
    if threads > count:
        threads = count
    chunk = (count + threads - 1) // threads
    backend = 0
    pos = 0
    while pos < count:
        span = min(chunk, count - pos)
        off = 0
        while off < span:
            rem = span - off
            if rem >= 17:
                backend += 32
                off += 32 if rem >= 32 else rem
            else:
                backend += 16
                off += rem
        pos += span
    return backend


def test_dispatch(supported):
    eng_c = ComputeEngine(requested="c")
    assert eng_c.backend == "c", eng_c.describe()
    eng_v = ComputeEngine(requested="v512")
    if supported:
        assert eng_v.backend == "v512", eng_v.describe()
    eng = ComputeEngine()
    if supported:
        assert eng.backend == "v512dual", eng.describe()
        assert eng.describe()["native_impl"] == "avx512-dual"
        assert eng.describe()["v512dual_backend"] is True
        print("ok dispatch: auto engine selects v512dual via "
              "the CPUID probe; requested='v512' still selects "
              "the single-batch v512 backend and requested='c' "
              "still selects C alone")
    else:
        assert eng.backend in ("v512", "c", "cpu"), eng.describe()
        assert eng.v512dual_reason and \
            "CPUID" in eng.v512dual_reason, eng.v512dual_reason
        print("ok dispatch: CPU lacks AVX-512F/BW; engine fell "
              f"back cleanly to {eng.backend} with the reason "
              "recorded")
    return eng


PROBE_STUB_C = (
    "int bal_v512_supported(void) { return 1; }\n"
    "unsigned bal_v512_feature_bits(void) { return 3u; }\n")
PROBE_FAIL_C = (
    "int bal_v512_supported(void) { return 0; }\n"
    "unsigned bal_v512_feature_bits(void) { return 0u; }\n")
BATCH_STUB_C = "int bal_vd_batch2(void) { return 0; }\n"
SEARCH_STUB_C = "int bal_vd_search2(void) { return 0; }\n"


def _build_fake_dual(tmp, name, sources):
    out = os.path.join(tmp, name)
    cc = shutil.which("gcc") or shutil.which("cc")
    proc = subprocess.run(
        [cc, "-shared", "-fPIC", "-O2", "-o", out] + sources,
        capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return out


def _assert_falls_back_to_v512(path, reason_parts, supported):
    eng = ComputeEngine(vd_lib_path=path)
    if supported:
        assert eng.backend == "v512", (path, eng.describe())
    else:
        assert eng.backend in ("c", "cpu"), (path, eng.describe())
    assert eng.v512dual_reason, (path, eng.describe())
    for part in reason_parts:
        assert part in eng.v512dual_reason, \
            (path, part, eng.v512dual_reason)
    hit, _attempted, _s = eng.search_first_counted(
        GENESIS, DIFF1, GENESIS_NONCE - 3, 1000)
    assert hit and hit[0] == GENESIS_NONCE, (path, hit)
    return eng


def test_forced_fallbacks(supported):
    """Gate: forced fallback three ways, in scratch copies
    only. (1) Probe failure: a dual library whose CPUID
    probe reports unsupported is never entered and the
    engine lands on v512. (2) Dual build failure: a
    scratch copy of the build tree with a corrupted dual
    kernel source fails its build loudly, produces no
    library, and an engine pointed at the absent library
    lands on v512. (3) Dual library absent: a path that
    does not exist lands on v512. Plus the D-1 mirror:
    symbol-incomplete dual libraries are rejected as a
    whole with the missing entry points named, and the
    build smoke test returns its designed error instead
    of raising."""
    cc = shutil.which("gcc") or shutil.which("cc")
    if not cc:
        print("ok forced fallbacks: skipped, no C compiler "
              "available to build the fake libraries")
        return
    tmp = tempfile.mkdtemp(prefix="bal-dual-fb-")

    def write(name, text):
        p = os.path.join(tmp, name)
        with open(p, "w") as fh:
            fh.write(text)
        return p

    probe_fail = _build_fake_dual(
        tmp, "libfake_probe_fail.so",
        [write("probe_fail.c", PROBE_FAIL_C),
         write("batch_stub.c", BATCH_STUB_C),
         write("search_stub.c", SEARCH_STUB_C)])
    _assert_falls_back_to_v512(probe_fail, ("CPUID",), supported)

    probe_only = _build_fake_dual(
        tmp, "libfake_dual_probe_only.so",
        [write("probe_stub.c", PROBE_STUB_C)])
    _assert_falls_back_to_v512(
        probe_only, ("bal_vd_batch2", "bal_vd_search2"), supported)
    no_search = _build_fake_dual(
        tmp, "libfake_dual_no_search.so",
        [write("probe_stub2.c", PROBE_STUB_C),
         write("batch_stub2.c", BATCH_STUB_C)])
    _assert_falls_back_to_v512(no_search, ("bal_vd_search2",),
                               supported)
    err, _supported = cpu_build._smoke_v512dual(probe_only)
    assert err is not None and "bal_vd_batch2" in err, err

    # Build failure in a scratch copy of the build tree.
    scratch = os.path.join(tmp, "tree")
    cpu_dir = os.path.join(scratch, "mining", "cpu")
    os.makedirs(cpu_dir)
    src_dir = os.path.join(os.path.dirname(__file__), "..",
                           "mining", "cpu")
    for name in ("build.py", "bal_avx512_probe.c", "bal_search.h"):
        shutil.copy(os.path.join(src_dir, name),
                    os.path.join(cpu_dir, name))
    with open(os.path.join(cpu_dir, "bal_avx512_dual.c"),
              "w") as fh:
        fh.write("this is not C source; the build must fail\n")
    spec = importlib.util.spec_from_file_location(
        "scratch_build", os.path.join(cpu_dir, "build.py"))
    scratch_build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scratch_build)
    res = scratch_build.build_v512dual(log=lambda *a: None)
    assert res["ok"] is False and res["lib"] is None, res
    absent = os.path.join(scratch, ".local", "cpu",
                          "libbal_v512dual.so")
    assert not os.path.isfile(absent)
    _assert_falls_back_to_v512(absent, ("not built",), supported)

    # Library absent outright.
    _assert_falls_back_to_v512(
        os.path.join(tmp, "no_such_libbal_v512dual.so"),
        ("not built",), supported)
    print("ok forced fallbacks: probe failure, dual build "
          "failure and absent dual library each land on "
          "v512 and keep mining genesis; incomplete dual "
          "libraries are rejected with the missing entry "
          "points named (D-1 mirror) and the build smoke "
          "test returns its error instead of raising")


def test_differentials(eng):
    """Randomized differentials through the production
    batch ABI: every digest of every batch compared to
    hashlib, plus the wave-boundary sizes and spans
    ending exactly at 2^32."""
    rng = random.Random(0xD026)
    total = 0
    for trial in range(24):
        header = bytes(rng.randrange(256) for _ in range(80))
        count = 8192
        start = rng.randrange(0, NONCE_SPACE - count)
        pairs = eng._vd_batch_flagged(eng._vd_lib, header,
                                      (1 << 256) - 1, start, count,
                                      want_all=True)
        assert pairs is not None and len(pairs) == count
        for nonce, digest in pairs:
            assert digest == cpu_digest(header, nonce), \
                (trial, nonce)
        total += count
        attempted, backend = eng._vd_last_counts
        assert attempted == count, (attempted, count)
        assert backend == predict_miss_backend(count, 2) or \
            backend >= count, (backend, count)
    assert total >= 100_000, total
    # Wave-boundary sizes, including spans that end
    # exactly at 2^32.
    for count in (15, 16, 17, 31, 32, 33, 63, 64, 65):
        for start in (0, 12345, NONCE_SPACE - count):
            pairs = eng._vd_batch_flagged(
                eng._vd_lib, GENESIS, (1 << 256) - 1, start, count,
                want_all=True)
            assert pairs is not None and len(pairs) == count
            for nonce, digest in pairs:
                assert digest == cpu_digest(GENESIS, nonce), \
                    (count, start, nonce)
            total += count
    print(f"ok differentials: {total:,} digests through the "
          "production DualMask batch ABI match hashlib "
          "exactly, including sizes 15/16/17/31/32/33/63/64/65 "
          "and spans ending at 2^32")


def test_candidate_sets(eng):
    rng = random.Random(0xD512)
    cases = ((1 << 232, 65536), (1 << 244, 16384))
    for target, count in cases:
        header = bytes(rng.randrange(256) for _ in range(80))
        start = rng.randrange(0, 1 << 24)
        want = recount(header, target, start, count)
        cands, st = eng.batch_search(header, target, start, count)
        got = {c["nonce"]: bytes.fromhex(c["hash"])[::-1]
               for c in cands}
        assert got == want, (target, count)
        assert st["backend"] == "v512dual", st
        assert st["unique_coverage"] == count, st
        assert st["device_hashes"] == 0, st
        assert st["candidate_count"] == len(want), st
        assert st["verification_hashes"] == len(want), st
        assert st["backend_hashes"] == predict_miss_backend(
            count, eng.c_threads), st
    print("ok candidate sets: batch_search candidate sets "
          "equal the independent hashlib recount at "
          "mainnet-like density and at about 2^-12; "
          "backend_hashes exactly the predicted dual-walker "
          "lane count")


def test_search_gates(eng):
    threads = eng.c_threads
    hit, attempted, _s = eng.search_first_counted(
        GENESIS, DIFF1, GENESIS_NONCE - 3, 100000)
    assert hit and hit[0] == GENESIS_NONCE
    st = eng.last_search_stats
    assert st["backend"] == "v512dual" and st["counted"], st
    assert st["candidate_count"] == 1, st
    assert st["verification_hashes"] == 1, st
    assert st["unique_coverage"] == attempted, st
    assert st["backend_hashes"] >= attempted, st
    assert st["backend_hashes"] % 16 == 0, st
    # Full misses: attempted and backend exact against the
    # independent dual-walker simulation, at ordinary and
    # wave-boundary sizes.
    for count in (15, 16, 17, 31, 32, 33, 63, 64, 65, 30000):
        hit, attempted, _s = eng.search_first_counted(
            GENESIS, 1, 5000, count)
        assert hit is None and attempted == count, (count, attempted)
        st = eng.last_search_stats
        assert st["backend_hashes"] == predict_miss_backend(
            count, threads), (count, st["backend_hashes"])
    # Independent verification of the found candidate.
    hit2, _a, _s = eng.search_first_counted(
        GENESIS, DIFF1, GENESIS_NONCE - 3, 100)
    assert hit2 and verify_candidate(GENESIS, DIFF1, hit2[0],
                                     hit2[1])
    # Boundary nonces, including the final nonce of the space.
    hit, attempted, _s = eng.search_first_counted(
        GENESIS, (1 << 256) - 1, NONCE_SPACE - 1, 1)
    assert hit and hit[0] == NONCE_SPACE - 1 and attempted == 1
    # Target equality meets; target minus one misses.
    g = cpu_digest(GENESIS, GENESIS_NONCE)
    gv = int.from_bytes(g, "little")
    cands, _st = eng.batch_search(GENESIS, gv, GENESIS_NONCE, 1)
    assert len(cands) == 1 and cands[0]["nonce"] == GENESIS_NONCE
    cands, _st = eng.batch_search(GENESIS, gv - 1, GENESIS_NONCE, 1)
    assert cands == []
    print("ok search gates: genesis exact, dual-atomic "
          "accounting exact on misses at boundary sizes, "
          "candidate verified independently, final-nonce "
          "boundary exact, target equality meets and "
          "minus-one misses")


def test_regtest_block():
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
    eng = MiningEngine(rpc, payout, compute=compute,
                       batch_size=100_000)
    tip0 = rpc.get_block_count()
    out = eng.mine_cycle(max_batches=1000, deadline_seconds=600)
    assert out["accepted"], out
    assert out["backend"] == "v512dual", out
    assert rpc.get_best_block_hash() == out["hash"]
    assert rpc.get_block_count() == tip0 + 1
    print(f"ok regtest: fresh block accepted through the "
          f"production AVX-512 DualMask backend: height "
          f"{out['height']} hash {out['hash']} submitblock "
          f"null, best-block match")
    return out


def main():
    built = build_c(log=lambda *a: None)
    assert built["lib"], built
    v = build_v512(log=lambda *a: None)
    assert v["ok"], v
    vd = build_v512dual(log=lambda *a: None)
    assert vd["ok"], vd
    supported = bool(vd["supported"])
    eng = test_dispatch(supported)
    test_forced_fallbacks(supported)
    if supported:
        test_differentials(eng)
        test_candidate_sets(eng)
        test_search_gates(eng)
        test_regtest_block()
    else:
        print("kernel gates skipped: this CPU cannot execute "
              "the AVX-512 DualMask kernel")
    print("ALL AVX512 DUAL INTEGRATION TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
