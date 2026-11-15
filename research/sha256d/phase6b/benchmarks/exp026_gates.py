#!/usr/bin/env python3
"""EXP-026 correctness gates for candidates C1 (TernMask,
bal_v_e26t_search2 / bal_v_e26t_batch2 in libbal_e26t.so)
and C2 (DualMask, bal_v_e26d_search2 in libbal_e26d.so;
its batch form is the unchanged EXP-018 bal_r_batch2 in
the same library). All gates pass before any timing.
Ground truth: hashlib SHA256d and production
bal_v_search2 / bal_v_batch2. Restricted build flags:
-O3 -mavx512f -mavx512bw.

Gates: G1 batch differentials vs hashlib and production
(over 100k nonces per candidate); G2 candidate-set
equivalence at densities 0, about 2^-16, 2^-8, 1 (at
1 thread the exact recount minimum; at 2 and 3 threads
a true recount member with exact digest); G3 target
boundaries; G4 nonce boundaries; G5 exact accounting
(C1: production wave rule; C2: dual-atomic rule,
dual step 32 while the remaining span is at least 17,
single step 16 for the tail, simulated independently);
G6 genesis re-found; G7 invalid arguments; G8 lowest
lane of a multi-candidate group. The sanitizer gate is
a separate C driver, exp026_san_driver.c.
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
OUT_DIR = os.path.join(HERE, "exp026")
sys.path.insert(0, os.path.join(ROOT, "research/sha256d/experiments"))
from bench_harness import GENESIS, GENESIS_NONCE  # noqa: E402

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


def load(lib, sym, sig):
    fn = getattr(lib, sym)
    fn.restype = ctypes.c_int
    fn.argtypes = sig
    return fn


base = ctypes.CDLL(os.path.join(EO_SRC, "libbal_v512_exp022base.so"))
prod_search = load(base, "bal_v_search2", SEARCH_SIG)
prod_batch = load(base, "bal_v_batch2", BATCH_SIG)
tlib = ctypes.CDLL(os.path.join(EO_SRC, "libbal_e26t.so"))
dlib = ctypes.CDLL(os.path.join(EO_SRC, "libbal_e26d.so"))
mlib = ctypes.CDLL(os.path.join(EO_SRC, "libbal_m512.so"))
ARMS = {
    "T": load(tlib, "bal_v_e26t_search2", SEARCH_SIG),
    "D": load(dlib, "bal_v_e26d_search2", SEARCH_SIG),
    "C": load(mlib, "bal_v_msearcha2", SEARCH_SIG),
    "prod": prod_search,
}
BATCHES = {
    "T": load(tlib, "bal_v_e26t_batch2", BATCH_SIG),
    "D": load(dlib, "bal_r_batch2", BATCH_SIG),
}
MAX_TARGET = b"\xff" * 32


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


def dual_expected(count, hit_off):
    """Simulate the C2 walker at 1 thread. hit_off is the
    offset of the first hit or None. Returns
    (attempted, backend)."""
    att = 0
    back = 0
    off = 0
    while off < count:
        rem = count - off
        if rem >= 17:
            step = min(32, rem)
            gran = 32
        else:
            step = rem
            gran = 16
        att += step
        back += gran
        if hit_off is not None and off <= hit_off < off + step:
            break
        off += step
    return att, back


def main():
    rng = random.Random(20261126)
    os.makedirs(OUT_DIR, exist_ok=True)
    report = {"experiment": "EXP-026",
              "started_utc": datetime.now(timezone.utc).isoformat(),
              "gates": {}}
    failures = []

    def gate(name, ok, detail):
        report["gates"][name] = {"pass": bool(ok), "detail": detail}
        print(f"{name}: {'PASS' if ok else 'FAIL'} {detail}", flush=True)
        if not ok:
            failures.append(name)

    headers = [GENESIS]
    for _ in range(3):
        h = bytearray(GENESIS)
        for i in range(0, 76, 4):
            h[i:i + 4] = rng.getrandbits(32).to_bytes(4, "little")
        headers.append(bytes(h))

    # G1: batch differentials
    for cand in ("T", "D"):
        total = 0
        ok = True
        detail = ""
        for hi, header in enumerate(headers):
            for threads in (1, 2):
                start = rng.randrange(0, 1 << 20)
                count = 16384 + rng.randrange(0, 5000)
                rc, raw, flags, att, back = run_batch(
                    BATCHES[cand], header, start, count, threads,
                    MAX_TARGET)
                prc, praw, _pf, patt, pback = run_batch(
                    prod_batch, header, start, count, threads,
                    MAX_TARGET)
                if rc != 0 or prc != 0 or att != count or \
                        patt != count or back != pback:
                    ok = False
                    detail = f"accounting h{hi} t{threads}"
                    break
                for i in range(count):
                    want = digest_of(header, start + i)
                    if raw[32 * i:32 * i + 32] != want or \
                            praw[32 * i:32 * i + 32] != want:
                        ok = False
                        detail = f"digest h{hi} t{threads} i{i}"
                        break
                total += count
                if not ok:
                    break
            if not ok:
                break
        gate(f"G1_{cand}", ok and total >= 100000,
             detail or f"{total} nonces byte-identical to hashlib and production")

    # G2: candidate-set equivalence
    densities = [("0", 0), ("2^-16", (1 << 240)),
                 ("2^-8", (1 << 248)), ("1", (1 << 256) - 1)]
    for cand in ("T", "D"):
        ok = True
        detail = ""
        trials = 0
        for dname, tint in densities:
            target = tint.to_bytes(32, "little")
            for _ in range(10):
                header = headers[rng.randrange(len(headers))]
                start = rng.randrange(0, 1 << 24)
                count = rng.choice([100, 1000, 4096])
                want = recount(header, tint, start, count)
                trials += 1
                rc, nonce, dig, att, back = run_search(
                    ARMS[cand], header, start, count, 1, target)
                if want:
                    mn = min(want)
                    if rc != 1 or nonce != mn or dig != want[mn]:
                        ok = False
                        detail = f"{dname} 1t start{start} count{count}"
                else:
                    if rc != 0:
                        ok = False
                        detail = f"{dname} 1t phantom start{start}"
                for threads in (2, 3):
                    rc, nonce, dig, att, back = run_search(
                        ARMS[cand], header, start, count, threads,
                        target)
                    if want:
                        if rc != 1 or nonce not in want or \
                                dig != want[nonce]:
                            ok = False
                            detail = f"{dname} {threads}t member"
                    elif rc != 0:
                        ok = False
                        detail = f"{dname} {threads}t phantom"
                if not ok:
                    break
            if not ok:
                break
        gate(f"G2_{cand}", ok, detail or f"{trials} spans x 4 densities")

    # G3: target boundaries
    for cand in ("T", "D"):
        ok = True
        for _ in range(24):
            header = headers[rng.randrange(len(headers))]
            n = rng.randrange(0, 1 << 24)
            d = digest_of(header, n)
            di = int.from_bytes(d, "little")
            for tint, wantrc in ((di, 1), (di - 1, 0), (di + 1, 1)):
                if tint < 0:
                    continue
                rc, nonce, dig, att, back = run_search(
                    ARMS[cand], header, n, 1, 1,
                    tint.to_bytes(32, "little"))
                if rc != wantrc or (wantrc and (nonce != n or dig != d)):
                    ok = False
        gate(f"G3_{cand}", ok, "equal meets, minus 1 misses, plus 1 meets")

    # G4: nonce boundaries
    spans = [(0, 1), (0, 5), (0, 15), (0, 16), (0, 17), (0, 31),
             (0, 33), (0, 100), (12345, 17), (999, 31),
             (0xFFFFFFC0, 64), (0xFFFFFFFF, 1), (0xFFFFFFF0, 16),
             (0xFFFFFFE0, 32)]
    for cand in ("T", "D"):
        ok = True
        detail = ""
        for start, count in spans:
            rc, nonce, dig, att, back = run_search(
                ARMS[cand], GENESIS, start, count, 1, MAX_TARGET)
            if rc != 1 or nonce != start or \
                    dig != digest_of(GENESIS, start):
                ok = False
                detail = f"span {start}+{count}"
        gate(f"G4_{cand}", ok, detail or "14 boundary spans exact")

    # G5: exact accounting at 1 thread
    ok = True
    detail = ""
    for count in (1, 5, 15, 16, 17, 31, 32, 33, 100, 1000, 65537):
        rc, nonce, dig, att, back = run_search(
            ARMS["T"], GENESIS, 0, count, 1, (0).to_bytes(32, "little"))
        want_back = 16 * ((count + 15) // 16)
        if rc != 0 or att != count or back != want_back:
            ok = False
            detail = f"T miss count {count}: att {att} back {back}"
        rc, nonce, dig, att, back = run_search(
            ARMS["D"], GENESIS, 0, count, 1, (0).to_bytes(32, "little"))
        watt, wback = dual_expected(count, None)
        if rc != 0 or att != watt or back != wback:
            ok = False
            detail = f"D miss count {count}: att {att} back {back}"
    # hit accounting from recounts
    for cand in ("T", "D"):
        tint = 1 << 248
        target = tint.to_bytes(32, "little")
        for _ in range(12):
            start = rng.randrange(0, 1 << 20)
            count = 4096
            want = recount(GENESIS, tint, start, count)
            if not want:
                continue
            hit_off = min(want) - start
            rc, nonce, dig, att, back = run_search(
                ARMS[cand], GENESIS, start, count, 1, target)
            if cand == "T":
                grp = hit_off // 16
                watt = min(16 * (grp + 1), count)
                wback = 16 * (grp + 1)
            else:
                watt, wback = dual_expected(count, hit_off)
            if rc != 1 or att != watt or back != wback:
                ok = False
                detail = f"{cand} hit att {att} want {watt} back {back} want {wback}"
    gate("G5", ok, detail or "miss and hit accounting exact for both candidates")

    # G6: genesis. Target is the genesis digest itself,
    # span starts at the genesis nonce, so the genesis
    # nonce is the first qualifying lane by equality.
    for cand in ("T", "D"):
        want = digest_of(GENESIS, GENESIS_NONCE)
        gt = int.from_bytes(want, "little").to_bytes(32, "little")
        rc, nonce, dig, att, back = run_search(
            ARMS[cand], GENESIS, GENESIS_NONCE, 2000, 2, gt)
        gate(f"G6_{cand}", rc == 1 and nonce == GENESIS_NONCE and dig == want,
             f"nonce {nonce}")

    # G7: invalid args
    for cand in ("T", "D"):
        fn = ARMS[cand]
        nonce = ctypes.c_uint32(0)
        dig = ctypes.create_string_buffer(32)
        att = ctypes.c_uint64(0)
        back = ctypes.c_uint64(0)
        codes = []
        codes.append(fn(None, 0, 16, 1, MAX_TARGET, ctypes.byref(nonce),
                        dig, ctypes.byref(att), ctypes.byref(back)))
        codes.append(fn(GENESIS, 0, 0, 1, MAX_TARGET, ctypes.byref(nonce),
                        dig, ctypes.byref(att), ctypes.byref(back)))
        codes.append(fn(GENESIS, 0, 16, 0, MAX_TARGET, ctypes.byref(nonce),
                        dig, ctypes.byref(att), ctypes.byref(back)))
        codes.append(fn(GENESIS, 0, 16, 17, MAX_TARGET, ctypes.byref(nonce),
                        dig, ctypes.byref(att), ctypes.byref(back)))
        codes.append(fn(GENESIS, 0xFFFFFFF0, 32, 1, MAX_TARGET,
                        ctypes.byref(nonce), dig, ctypes.byref(att),
                        ctypes.byref(back)))
        gate(f"G7_{cand}", codes == [-1, -1, -1, -1, -2],
             f"codes {codes}")

    # G8: lowest lane of a full group / dual group
    rc, nonce, dig, att, back = run_search(
        ARMS["T"], GENESIS, 50000, 16, 1, MAX_TARGET)
    t_ok = rc == 1 and nonce == 50000
    rc, nonce, dig, att, back = run_search(
        ARMS["D"], GENESIS, 50000, 32, 1, MAX_TARGET)
    d_ok = rc == 1 and nonce == 50000
    gate("G8", t_ok and d_ok, f"T16 {t_ok}, D32 {d_ok}")

    report["failures"] = failures
    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(OUT_DIR, f"gates_{stamp}.json")
    with open(path, "w") as fh:
        json.dump(report, fh, indent=1)
    print("WROTE", path)
    print("FAILURES:", failures)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
