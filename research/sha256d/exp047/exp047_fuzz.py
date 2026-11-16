#!/usr/bin/env python3
"""EXP-047: cross-backend differential fuzzing at scale.

Drives every production backend through the ComputeEngine seam
(gpu/engine.py) exactly as production constructs it, and compares
batch digests and search hit sets against the hashlib reference
(gpu.engine.cpu_digest) and pairwise against every other backend.

The campaign design is predeclared in EXP047_REPORT.md section 3.
All random headers and starts derive from SEED in a fixed
generation order, so the campaign is reproducible from the seed
alone. Any mismatch stops the campaign at once, writes
RAW_RESULTS/mismatch.json plus a minimal reproducing script, and
exits 3. No production code is modified; nothing here times
anything for a result (no hash rate is a campaign output).

Usage: python3 exp047_fuzz.py [results_dir]
"""

import json
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, REPO)

from gpu.engine import ComputeEngine, cpu_digest  # noqa: E402

SEED = 47047
MAX_BATCH = 1 << 20
NONCE_SPACE = 1 << 32
DIFF1 = 0xFFFF << 208
GENESIS = bytes.fromhex(
    "01000000" + "00" * 32
    + "3ba3edfd7a7b12b27ac72c3e67768f617fc81bc3888a51323a9fb8aa4b1e5e4a"
    + "29ab5f49" + "ffff001d" + "1dac2b7c")
GENESIS_NONCE = 2083236893

BATCH_TARGET = (1 << 248) - 1  # arbitrary; digests ignore target

T_FULL = (1 << 256) - 1
T_D8 = (1 << 248) - 1
T_D16 = (1 << 240) - 1
T_D24 = (1 << 232) - 1
T_SOLO = DIFF1 * 50  # exact share target at solo difficulty 0.02
T_ZERO = 1

RESULTS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    HERE, "RAW_RESULTS")
os.makedirs(RESULTS, exist_ok=True)
PROGRESS = os.path.join(RESULTS, "progress.jsonl")


def log(obj):
    obj = dict(obj)
    obj["t"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with open(PROGRESS, "a") as f:
        f.write(json.dumps(obj) + "\n")
    print(json.dumps(obj), flush=True)


def fail(kind, detail):
    """Record a mismatch, write a minimal repro, stop."""
    rec = {"kind": kind, "detail": detail}
    with open(os.path.join(RESULTS, "mismatch.json"), "w") as f:
        json.dump(rec, f, indent=1)
    log({"phase": "MISMATCH", **rec})
    if detail.get("header_hex") and detail.get("nonce") is not None \
            and detail.get("backend"):
        repro = (
            "#!/usr/bin/env python3\n"
            "\"\"\"Minimal repro for the EXP-047 mismatch in "
            "mismatch.json.\n"
            "Run from the repo root. Prints expected vs actual "
            "digest for the\nsingle failing nonce through the "
            "production seam.\"\"\"\n"
            "import os, sys\n"
            "sys.path.insert(0, os.path.abspath(os.path.join(\n"
            "    os.path.dirname(__file__), '..', '..', '..')))\n"
            "from gpu.engine import ComputeEngine, cpu_digest\n"
            f"HEADER = bytes.fromhex({detail['header_hex']!r})\n"
            f"NONCE = {detail['nonce']}\n"
            f"BACKEND = {detail['backend']!r}\n"
            "eng = ComputeEngine(requested=BACKEND)\n"
            "fn = {'c': (eng._c_lib, eng._c_batch),\n"
            "      'avx2': (eng._a_lib, eng._a_batch),\n"
            "      'shani': (eng._m_lib, eng._m_batch),\n"
            "      'v512': (eng._v_lib, eng._v_batch),\n"
            "      'v512dual': (eng._vd_lib, eng._vd_batch)}[BACKEND]\n"
            "got = fn[1](fn[0], HEADER, (1 << 248) - 1, NONCE, 1)\n"
            "print('expected', cpu_digest(HEADER, NONCE).hex())\n"
            "print('actual  ', None if got is None else "
            "got[0].hex())\n")
        with open(os.path.join(RESULTS, "minimal_repro.py"),
                  "w") as f:
            f.write(repro)
    sys.exit(3)


# ----------------------------------------------------------------
# Case generation (fixed order from the seed; see report 3.1/3.2)
# ----------------------------------------------------------------

def gen_cases():
    rng = random.Random(SEED)

    def header():
        return rng.randbytes(80)

    def aligned_start():
        return rng.randrange(0, 1 << 16) * 65536

    def unaligned_start(limit=1 << 24):
        s = rng.randrange(0, limit) | 1
        if s % 16 == 0:
            s += 1
        return s

    batch = []
    for i in range(24):
        batch.append((f"B1-{i:02d}", header(), aligned_start(),
                      65536))
    for i in range(8):
        batch.append((f"B2-{i:02d}", header(), unaligned_start(),
                      65536))
    batch.append(("B3a", header(), 0, MAX_BATCH))
    batch.append(("B3b", header(), 999983, MAX_BATCH))
    batch.append(("B4a", GENESIS, 0, 65536))
    batch.append(("B4b", header(), NONCE_SPACE - 65536, 65536))
    batch.append(("B4c", header(), NONCE_SPACE - 1, 1))
    batch.append(("B4d", GENESIS, NONCE_SPACE - 16, 16))
    batch.append(("B4e", header(), NONCE_SPACE - 17, 17))
    batch.append(("B4f", header(), 1, 65535))
    batch.append(("B4g", GENESIS, GENESIS_NONCE - 32768, 65536))
    ladder = [1, 2, 3, 15, 16, 17, 31, 32, 33, 63, 64, 65, 100,
              1000, 4095, 4096, 4097, 65535]
    h0 = header()
    h1 = header()
    for j, c in enumerate(ladder):
        batch.append((f"B5a-{j:02d}", h0, 0, c))
    for j, c in enumerate(ladder):
        batch.append((f"B5b-{j:02d}", h1, 12345, c))

    search = []  # (case_id, target_name, target, header, start, count, s_c)
    for i in range(4):
        if i == 0:
            search.append(("S_FULL-00", "T_FULL", T_FULL, GENESIS,
                           GENESIS_NONCE - 32768, 65536, True))
        elif i == 1:
            search.append(("S_FULL-01", "T_FULL", T_FULL, header(),
                           NONCE_SPACE - 65536, 65536, True))
        elif i == 2:
            search.append(("S_FULL-02", "T_FULL", T_FULL, header(),
                           aligned_start(), 65536, False))
        else:
            search.append(("S_FULL-03", "T_FULL", T_FULL, header(),
                           unaligned_start(), 65536, False))
    for i in range(8):
        st = aligned_start() if i % 2 == 0 else unaligned_start()
        search.append((f"S_D8-{i:02d}", "T_D8", T_D8, header(), st,
                       65536, True))
    for i in range(4):
        st = (rng.randrange(0, 1 << 11) * MAX_BATCH if i % 2 == 0
              else unaligned_start(1 << 21))
        search.append((f"S_D16-{i:02d}", "T_D16", T_D16, header(),
                       st, MAX_BATCH, True))
    for i in range(4):
        st = (rng.randrange(0, 1 << 11) * MAX_BATCH if i % 2 == 0
              else unaligned_start(1 << 21))
        search.append((f"S_D24-{i:02d}", "T_D24", T_D24, header(),
                       st, MAX_BATCH, False))
    for i in range(8):
        st = (rng.randrange(0, 1 << 11) * MAX_BATCH if i % 2 == 0
              else unaligned_start(1 << 21))
        search.append((f"S_SOLO-{i:02d}", "T_SOLO", T_SOLO,
                       header(), st, MAX_BATCH, False))
    for i in range(2):
        st = aligned_start() if i == 0 else unaligned_start()
        search.append((f"S_ZERO-{i:02d}", "T_ZERO", T_ZERO,
                       header(), st, 65536, True))
    return batch, search


# ----------------------------------------------------------------
# Engines
# ----------------------------------------------------------------

def build_engines():
    specs = {}
    for name in ("v512dual", "v512", "shani", "avx2", "c", "cpu"):
        eng = ComputeEngine(requested=name)
        if eng.backend != name:
            fail("engine_selection", {
                "backend": name, "selected": eng.backend,
                "reason": "pinned request did not select the tier"})
        specs[name] = eng
    native = {
        "c": lambda e: (e._c_lib, e._c_batch, e._c_batch_flagged),
        "avx2": lambda e: (e._a_lib, e._a_batch, e._a_batch_flagged),
        "shani": lambda e: (e._m_lib, e._m_batch, e._m_batch_flagged),
        "v512": lambda e: (e._v_lib, e._v_batch, e._v_batch_flagged),
        "v512dual": lambda e: (e._vd_lib, e._vd_batch,
                               e._vd_batch_flagged),
    }
    return specs, native


# ----------------------------------------------------------------
# Phases
# ----------------------------------------------------------------

def phase_batch(engines, native, cases):
    totals = {name: 0 for name in native}
    ref_total = 0
    pairwise = 0
    per_case = []
    for cid, hdr, start, count in cases:
        ref = [cpu_digest(hdr, start + i) for i in range(count)]
        ref_blob = b"".join(ref)
        ref_total += count
        blobs = {}
        for name, eng in engines.items():
            if name not in native:
                continue
            lib, batch_fn, _flag_fn = native[name](eng)
            got = batch_fn(lib, hdr, BATCH_TARGET, start, count)
            if got is None:
                fail("batch_refusal", {
                    "backend": name, "case": cid,
                    "header_hex": hdr.hex(), "start": start,
                    "count": count,
                    "reason": "batch returned None on a valid span"})
            if len(got) != count:
                fail("batch_length", {
                    "backend": name, "case": cid,
                    "header_hex": hdr.hex(), "start": start,
                    "count": count, "got": len(got)})
            blob = b"".join(got)
            blobs[name] = blob
            totals[name] += count
            if blob != ref_blob:
                for i in range(count):
                    if got[i] != ref[i]:
                        fail("batch_digest", {
                            "backend": name, "case": cid,
                            "header_hex": hdr.hex(), "start": start,
                            "count": count, "nonce": start + i,
                            "expected": ref[i].hex(),
                            "actual": got[i].hex()})
        names = sorted(blobs)
        for a in range(len(names)):
            for b in range(a + 1, len(names)):
                pairwise += count
                if blobs[names[a]] != blobs[names[b]]:
                    fail("batch_pairwise", {
                        "backend": names[a], "other": names[b],
                        "case": cid, "header_hex": hdr.hex(),
                        "start": start, "count": count})
        per_case.append({"case": cid, "start": start,
                         "count": count})
        log({"phase": "batch", "case": cid, "count": count,
             "ref_total": ref_total})
    return {"per_backend": totals, "reference_digests": ref_total,
            "pairwise_digest_comparisons": pairwise,
            "cases": per_case}


def ref_hits(hdr, target, start, count):
    hits = set()
    for i in range(count):
        d = cpu_digest(hdr, start + i)
        if int.from_bytes(d, "little") <= target:
            hits.add(start + i)
    return hits


def phase_search(engines, native, cases):
    per_backend = {}
    surface_checks = 0
    first_calls = 0
    observed_hits = {}
    for (cid, tname, target, hdr, start, count, s_c) in cases:
        want = ref_hits(hdr, target, start, count)
        observed_hits[cid] = len(want)
        for name, eng in engines.items():
            rec = per_backend.setdefault(
                name, {"batch_search_calls": 0, "nonces": 0,
                       "flagged_calls": 0, "flags_calls": 0,
                       "first_calls": 0})
            cands, st = eng.batch_search(hdr, target, start, count)
            rec["batch_search_calls"] += 1
            rec["nonces"] += count
            got_set = {c["nonce"] for c in cands}
            if st.get("verification_failures") != 0 \
                    or st.get("rescanned"):
                fail("search_surface", {
                    "backend": name, "case": cid,
                    "header_hex": hdr.hex(), "start": start,
                    "count": count, "target": target,
                    "reason": "batch_search reported verification "
                              "failures or a rescan",
                    "stats_backend": st.get("backend"),
                    "verification_failures":
                        st.get("verification_failures")})
            if got_set != want:
                extra = sorted(got_set - want)
                missing = sorted(want - got_set)
                fail("search_hitset_batch_search", {
                    "backend": name, "case": cid,
                    "header_hex": hdr.hex(), "start": start,
                    "count": count, "target": target,
                    "nonce": (extra or missing)[0],
                    "extra": extra[:8], "missing": missing[:8]})
            surface_checks += 1
            if name in native:
                lib, _b, flag_fn = native[name](eng)
                pairs = flag_fn(lib, hdr, target, start, count)
                if pairs is None:
                    fail("search_refusal", {
                        "backend": name, "case": cid,
                        "header_hex": hdr.hex(), "start": start,
                        "count": count, "target": target,
                        "reason": "flagged batch returned None"})
                rec["flagged_calls"] += 1
                fset = {n for n, _d in pairs}
                if fset != want:
                    extra = sorted(fset - want)
                    missing = sorted(want - fset)
                    fail("search_hitset_flagged", {
                        "backend": name, "case": cid,
                        "header_hex": hdr.hex(), "start": start,
                        "count": count, "target": target,
                        "nonce": (extra or missing)[0],
                        "extra": extra[:8], "missing": missing[:8]})
                for n, d in pairs:
                    if d != cpu_digest(hdr, n):
                        fail("search_flagged_digest", {
                            "backend": name, "case": cid,
                            "header_hex": hdr.hex(), "nonce": n,
                            "expected": cpu_digest(hdr, n).hex(),
                            "actual": d.hex()})
                surface_checks += 1
                if name in ("v512", "v512dual") \
                        and eng._vf_lib is not None:
                    vpairs = eng._vf_batch_flagged(
                        eng._vf_lib, hdr, target, start, count)
                    if vpairs is None:
                        fail("search_refusal", {
                            "backend": name + "/flags", "case": cid,
                            "header_hex": hdr.hex(), "start": start,
                            "count": count, "target": target,
                            "reason": "flags batch returned None"})
                    rec["flags_calls"] += 1
                    vset = {n for n, _d in vpairs}
                    if vset != want:
                        extra = sorted(vset - want)
                        missing = sorted(want - vset)
                        fail("search_hitset_flags", {
                            "backend": name + "/flags", "case": cid,
                            "header_hex": hdr.hex(), "start": start,
                            "count": count, "target": target,
                            "nonce": (extra or missing)[0],
                            "extra": extra[:8],
                            "missing": missing[:8]})
                    for n, d in vpairs:
                        if d != cpu_digest(hdr, n):
                            fail("search_flags_digest", {
                                "backend": name + "/flags",
                                "case": cid, "header_hex": hdr.hex(),
                                "nonce": n,
                                "expected": cpu_digest(hdr, n).hex(),
                                "actual": d.hex()})
                    surface_checks += 1
            if s_c:
                hit, _att, _sec = eng.search_first_counted(
                    hdr, target, start, count)
                rec["first_calls"] += 1
                first_calls += 1
                if want:
                    if hit is None or hit[0] != min(want):
                        fail("search_first", {
                            "backend": name, "case": cid,
                            "header_hex": hdr.hex(), "start": start,
                            "count": count, "target": target,
                            "nonce": min(want),
                            "reason": "first hit disagrees with "
                                      "the reference minimum",
                            "got": None if hit is None else hit[0]})
                    if hit[1] != cpu_digest(hdr, hit[0]):
                        fail("search_first_digest", {
                            "backend": name, "case": cid,
                            "header_hex": hdr.hex(), "nonce": hit[0],
                            "expected": cpu_digest(
                                hdr, hit[0]).hex(),
                            "actual": hit[1].hex()})
                elif hit is not None:
                    fail("search_first", {
                        "backend": name, "case": cid,
                        "header_hex": hdr.hex(), "start": start,
                        "count": count, "target": target,
                        "nonce": hit[0],
                        "reason": "reported a hit where the "
                                  "reference set is empty"})
        log({"phase": "search", "case": cid, "target": tname,
             "count": count, "ref_hits": len(want)})
    # Boundary first-hit calls (S_FIRST_BOUNDARY).
    for name, eng in engines.items():
        hit, _a, _s = eng.search_first_counted(
            GENESIS, T_FULL, NONCE_SPACE - 1, 1)
        first_calls += 1
        if hit is None or hit[0] != NONCE_SPACE - 1:
            fail("search_first_boundary", {
                "backend": name, "case": "S_FIRST_BOUNDARY-1",
                "header_hex": GENESIS.hex(), "nonce": NONCE_SPACE - 1,
                "reason": "final-nonce first hit wrong",
                "got": None if hit is None else hit[0]})
        hit, _a, _s = eng.search_first_counted(
            GENESIS, DIFF1, GENESIS_NONCE - 3, 1000)
        first_calls += 1
        if hit is None or hit[0] != GENESIS_NONCE:
            fail("search_first_boundary", {
                "backend": name, "case": "S_FIRST_BOUNDARY-2",
                "header_hex": GENESIS.hex(), "nonce": GENESIS_NONCE,
                "reason": "genesis first hit wrong",
                "got": None if hit is None else hit[0]})
    log({"phase": "search_boundary", "first_calls_total": first_calls})
    return {"per_backend": per_backend,
            "surface_checks": surface_checks,
            "search_first_calls_per_backend_in_boundary": 2,
            "observed_reference_hits": observed_hits}


def phase_gate3(engines, native):
    hdr = GENESIS
    results = {}
    cases = [
        ("G1", lambda e: e.batch_search(hdr[:79], T_D8, 0, 16)),
        ("G2", lambda e: e.batch_search(hdr + b"x", T_D8, 0, 16)),
        ("G3", lambda e: e.batch_search(hdr, 0, 0, 16)),
        ("G4", lambda e: e.batch_search(hdr, 1 << 256, 0, 16)),
        ("G5", lambda e: e.batch_search(hdr, -1, 0, 16)),
        ("G6", lambda e: e.batch_search(hdr, T_D8, -1, 16)),
        ("G7", lambda e: e.batch_search(hdr, T_D8, 0, 0)),
        ("G8", lambda e: e.batch_search(hdr, T_D8, 0, -5)),
        ("G9", lambda e: e.batch_search(hdr, T_D8, 0,
                                        MAX_BATCH + 1)),
        ("G10", lambda e: e.batch_search(hdr, T_D8,
                                         NONCE_SPACE - 100, 200)),
        ("G11", lambda e: e.batch_search(hdr, T_D8,
                                         NONCE_SPACE, 1)),
        ("G12", lambda e: e.search_first_counted(
            hdr, T_D8, NONCE_SPACE - 100, 200)),
        ("G13", lambda e: e.search_first_counted(hdr, 0, 0, 16)),
        ("G14", lambda e: e.search_first_counted(hdr[:79], T_D8,
                                                 0, 16)),
    ]
    for name, eng in engines.items():
        rec = {}
        for cid, fn in cases:
            try:
                fn(eng)
                rec[cid] = "NO_RAISE"
            except Exception as exc:  # noqa: BLE001
                rec[cid] = type(exc).__name__
        results[name] = rec
        log({"phase": "gate3", "engine": name, "results": rec})
    for name, rec in results.items():
        for cid, outcome in rec.items():
            if outcome != "ValueError":
                fail("gate3_uniformity", {
                    "backend": name, "case": cid,
                    "reason": f"expected ValueError, got {outcome}"})
    lib_results = {}
    for name, eng in engines.items():
        if name not in native:
            continue
        lib, batch_fn, flag_fn = native[name](eng)
        pairs = flag_fn(lib, hdr, T_D8, NONCE_SPACE - 8, 16)
        digs = batch_fn(lib, hdr, T_D8, NONCE_SPACE - 8, 16)
        lib_results[name] = {
            "G15_flagged_crossing": "refused" if pairs is None
            else f"NOT_REFUSED ({len(pairs)} pairs)",
            "G16_batch_crossing": "refused" if digs is None
            else "NOT_REFUSED",
        }
        if pairs is not None or digs is not None:
            fail("gate3_library_refusal", {
                "backend": name, "case": "G15/G16",
                "reason": "library produced output for a span "
                          "crossing 2^32 instead of refusing"})
        log({"phase": "gate3_lib", "engine": name,
             "results": lib_results[name]})
    return {"seam": results, "library": lib_results}


def main():
    cpu_model = "unknown"
    with open("/proc/cpuinfo") as f:
        for line in f:
            if line.startswith("model name"):
                cpu_model = line.split(":", 1)[1].strip()
                break
    batch_cases, search_cases = gen_cases()
    predeclared = {
        "batch_digests_per_backend":
            sum(c for _i, _h, _s, c in batch_cases),
        "batch_cases": len(batch_cases),
        "search_nonces_per_backend":
            sum(c for _i, _t, _tg, _h, _s, c, _f in search_cases),
        "search_cases": len(search_cases),
    }
    engines, native = build_engines()
    manifest = {
        "experiment": "EXP-047",
        "seed": SEED,
        "host_cpu": cpu_model,
        "started": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                 time.gmtime()),
        "predeclared": predeclared,
        "engines": {name: eng.describe()
                    for name, eng in engines.items()},
        "flags_lib_loaded": {
            name: (eng._vf_lib is not None)
            for name, eng in engines.items()},
        "targets": {"T_FULL": T_FULL, "T_D8": T_D8, "T_D16": T_D16,
                    "T_D24": T_D24, "T_SOLO": T_SOLO,
                    "T_ZERO": T_ZERO},
    }
    with open(os.path.join(RESULTS, "campaign_manifest.json"),
              "w") as f:
        json.dump(manifest, f, indent=1)
    log({"phase": "start", "predeclared": predeclared})

    out = {"manifest": "campaign_manifest.json"}
    out["batch"] = phase_batch(engines, native, batch_cases)
    with open(os.path.join(RESULTS, "batch_results.json"),
              "w") as f:
        json.dump(out["batch"], f, indent=1)
    log({"phase": "batch_done", **{
        k: v for k, v in out["batch"].items() if k != "cases"}})

    out["search"] = phase_search(engines, native, search_cases)
    with open(os.path.join(RESULTS, "search_results.json"),
              "w") as f:
        json.dump(out["search"], f, indent=1)
    log({"phase": "search_done"})

    out["gate3"] = phase_gate3(engines, native)
    with open(os.path.join(RESULTS, "gate3_results.json"),
              "w") as f:
        json.dump(out["gate3"], f, indent=1)
    out["mismatches"] = 0
    out["finished"] = time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                    time.gmtime())
    with open(os.path.join(RESULTS, "summary.json"), "w") as f:
        json.dump(out, f, indent=1)
    log({"phase": "COMPLETE", "mismatches": 0})


if __name__ == "__main__":
    main()
