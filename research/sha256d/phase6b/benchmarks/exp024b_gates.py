#!/usr/bin/env python3
"""EXP-024b compact confirmation gates for design C.

The full EXP-024 gate set (G1 to G9) passed for this
exact kernel and library build. This compact re-run,
required by the EXP-024b predeclared design, covers:
  K1 differentials vs hashlib on >= 50,000 nonces for
     design C (through the batch form bal_v_mbatch2,
     which exercises the same vm_group code C searches
     with), byte-identical to hashlib and production.
  K2 candidate-set equivalence for C vs a hashlib
     recount and vs production search at density 0
     and about 2^-12 (target_int 2^244).
  K3 genesis nonce 2083236893 re-found by C with the
     exact hashlib digest.
Host CPU is recorded in the gate record.
"""
import ctypes
import hashlib
import json
import os
import random
import sys
from datetime import datetime, timezone

ROOT = "/home/hatch/workspace/bitcoin-autonomous-lab"
EO_SRC = os.path.join(ROOT, "research/sha256d/extreme_optimization/src")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "exp024b")
sys.path.insert(0, os.path.join(ROOT, "research/sha256d/experiments"))
from bench_harness import GENESIS, GENESIS_NONCE, DIFF1_LE  # noqa: E402

SEARCH_SIG = [
    ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
    ctypes.c_uint, ctypes.c_char_p,
    ctypes.POINTER(ctypes.c_uint32), ctypes.c_char_p,
    ctypes.POINTER(ctypes.c_uint64),
    ctypes.POINTER(ctypes.c_uint64)]
BATCH_SIG = [
    ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
    ctypes.c_uint, ctypes.c_char_p, ctypes.c_char_p,
    ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint64),
    ctypes.POINTER(ctypes.c_uint64)]

base = ctypes.CDLL(os.path.join(EO_SRC, "libbal_v512_exp022base.so"))
prod_search = base.bal_v_search2
prod_search.restype = ctypes.c_int
prod_search.argtypes = SEARCH_SIG
prod_batch = base.bal_v_batch2
prod_batch.restype = ctypes.c_int
prod_batch.argtypes = BATCH_SIG
mlib = ctypes.CDLL(os.path.join(EO_SRC, "libbal_m512.so"))
search_c = mlib.bal_v_msearcha2
search_c.restype = ctypes.c_int
search_c.argtypes = SEARCH_SIG
mbatch = mlib.bal_v_mbatch2
mbatch.restype = ctypes.c_int
mbatch.argtypes = BATCH_SIG

MAX_TARGET = b"\xff" * 32


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def digest_of(header, nonce):
    return hashlib.sha256(hashlib.sha256(
        header[:76] + nonce.to_bytes(4, "little")).digest()).digest()


def run_search(fn, header, start, count, threads, target):
    nonce = ctypes.c_uint32(0)
    dig = ctypes.create_string_buffer(32)
    att = ctypes.c_uint64(0)
    back = ctypes.c_uint64(0)
    rc = fn(header, start, count, threads, target,
            ctypes.byref(nonce), dig, ctypes.byref(att),
            ctypes.byref(back))
    return rc, nonce.value, dig.raw, att.value, back.value


def run_batch(fn, header, start, count, threads, target):
    hashes = ctypes.create_string_buffer(32 * count)
    flags = ctypes.create_string_buffer(count)
    att = ctypes.c_uint64(0)
    back = ctypes.c_uint64(0)
    rc = fn(header, start, count, threads, target, hashes, flags,
            ctypes.byref(att), ctypes.byref(back))
    return rc, hashes.raw, flags.raw, att.value, back.value


def recount(header, target_int, start, count):
    out = {}
    for i in range(count):
        d = digest_of(header, start + i)
        if int.from_bytes(d, "little") <= target_int:
            out[start + i] = d
    return out


def cpu_info():
    model = "unknown"
    flags = []
    try:
        with open("/proc/cpuinfo") as fh:
            text = fh.read()
        for line in text.splitlines():
            if line.startswith("model name") and model == "unknown":
                model = line.split(":", 1)[1].strip()
            if line.startswith("flags") and not flags:
                flags = line.split(":", 1)[1].split()
    except OSError:
        pass
    wanted = ("sha_ni", "avx2", "avx512f", "avx512bw", "avx512dq",
              "avx512vl", "avx512vbmi", "avx512_vbmi2",
              "avx512ifma", "avx512_vnni", "gfni", "vaes")
    return model, {w: (w in flags) for w in wanted}


def main():
    rng = random.Random(20261124)
    model, flags = cpu_info()
    report = {"experiment": "EXP-024b", "gates": {},
              "started_utc": datetime.now(timezone.utc).isoformat(),
              "host": {"cpu_model": model, "relevant_flags": flags},
              "libraries": {
                  "production": "libbal_v512_exp022base.so",
                  "mask": "libbal_m512.so",
                  "mask_sha256": sha256_file(
                      os.path.join(EO_SRC, "libbal_m512.so")),
                  "mask_source_sha256": sha256_file(os.path.join(
                      EO_SRC, "avx512_mb_mask_search.c"))}}
    failures = []

    def gate(name, ok, detail):
        report["gates"][name] = {"pass": bool(ok), "detail": detail}
        print(f"{name}: {'PASS' if ok else 'FAIL'} {detail}",
              flush=True)
        if not ok:
            failures.append(name)

    headers = [GENESIS]
    for _ in range(3):
        h = bytearray(GENESIS)
        for i in range(0, 76, 4):
            h[i:i + 4] = rng.getrandbits(32).to_bytes(4, "little")
        headers.append(bytes(h))

    # K1: differentials for design C group code, >= 50k nonces
    total = 0
    ok = True
    detail = ""
    for hi, header in enumerate(headers):
        for threads in (1, 2):
            start = rng.randrange(0, 1 << 20)
            count = 16384
            rc, raw, fl, att, back = run_batch(
                mbatch, header, start, count, threads, MAX_TARGET)
            prc, praw, _pf, patt, pback = run_batch(
                prod_batch, header, start, count, threads,
                MAX_TARGET)
            if rc != 0 or prc != 0 or att != count or \
                    patt != count or back != pback or raw != praw:
                ok = False
                detail = f"batch mismatch h{hi} t{threads}"
                break
            for i in range(count):
                if raw[32 * i:32 * i + 32] != digest_of(
                        header, start + i):
                    ok = False
                    detail = f"hashlib mismatch h{hi} nonce {start+i}"
                    break
                if fl[i] != 1:
                    ok = False
                    detail = f"flag not set h{hi}"
                    break
            if not ok:
                break
            total += count
        if not ok:
            break
    gate("K1_differential_designC", ok and total >= 50_000,
         detail or f"{total} nonces byte-identical to hashlib "
                   f"and production batch")

    # K2: candidate-set equivalence for C at density 0 and 2^-12
    ok = True
    detail = ""
    trials = 0
    for dval, dname in ((0, "0"), (1 << 244, "2^-12")):
        target = dval.to_bytes(32, "little")
        for trial in range(12):
            header = headers[rng.randrange(len(headers))]
            start = rng.randrange(0, 1 << 24)
            count = rng.choice((1000, 4096, 8192))
            want = recount(header, dval, start, count)
            for fn, nm in ((search_c, "C"), (prod_search, "P")):
                rc, nonce, dig, att, back = run_search(
                    fn, header, start, count, 1, target)
                if want:
                    if rc != 1 or nonce != min(want) or \
                            dig != want[min(want)]:
                        ok = False
                        detail = (f"{nm} d{dname} t{trial}: rc {rc} "
                                  f"nonce {nonce} want {min(want)}")
                elif rc != 0 or att != count:
                    ok = False
                    detail = f"{nm} d{dname} t{trial}: miss rc {rc}"
                if not ok:
                    break
            if not ok:
                break
            trials += 1
        if not ok:
            break
    gate("K2_candidate_equivalence_designC", ok,
         detail or f"{trials} spans x densities 0 and 2^-12: C "
                   f"identical to recount minimum and production "
                   f"at 1 thread")

    # K3: genesis re-found by C
    gwant = digest_of(GENESIS, GENESIS_NONCE)
    rc, nonce, dig, att, back = run_search(
        search_c, GENESIS, GENESIS_NONCE - 1000, 2000, 2, DIFF1_LE)
    gate("K3_genesis_designC",
         rc == 1 and nonce == GENESIS_NONCE and dig == gwant,
         f"rc {rc} nonce {nonce} digest exact: "
         f"{dig == gwant}")

    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    report["all_pass"] = not failures
    report["failures"] = failures
    os.makedirs(OUT_DIR, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(OUT_DIR, f"gates_{stamp}.json")
    suffix = 2
    while os.path.exists(path):
        path = os.path.join(OUT_DIR, f"gates_{stamp}_r{suffix}.json")
        suffix += 1
    with open(path, "x") as fh:
        json.dump(report, fh, indent=2)
    print(f"wrote {path}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
