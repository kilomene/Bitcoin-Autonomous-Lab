#!/usr/bin/env python3
"""EXP-023 correctness gates. All must pass before timing.

G-A  Snapshot stepper soundness: the round-stepper's full
     compression equals mining.pow_engine.PureSHA256's
     block result on randomised blocks, and header inner
     digests completed from the MID, B2R2 and SCH17
     snapshots equal hashlib.sha256(header) exactly
     (the midstate itself is checked against PureSHA256,
     the lab's from-spec implementation, and by
     completion against hashlib, since hashlib exposes
     no raw chaining state).
G-B  Amortised builder byte-identity: candidates from
     PreparedTemplate.build are byte-identical to
     MiningEngine.build_candidate (header, body, and
     every scalar field) over at least 1,000 randomised
     (template, extranonce) cases, including segwit
     mixes, coinbaseaux flags, witness commitments,
     and a fingerprint-mismatch rejection.
G-C  Merkle spine: root_with_coinbase equals
     mining.pow.merkle_root over randomised leaf counts.
G-D  Y-076 dependency gates: an extranonce-driven merkle
     change alters header bytes 36.. onward, alters the
     midstate, and leaves the R8 state untouched; the
     deepest extranonce-independent snapshot is R8,
     not the half block.
G-E  Y-077 alignment gates: within a job family (fixed
     version and prevhash) R8 is shared; R11 is shared
     iff the merkle head (bytes 36..47) aligns, by
     construction both ways.
G-F  Y-079 table gates: for every subset of the five
     fields {version, prevhash head, merkle tail, time,
     nbits} allowed to vary (nonce always varies), the
     deepest valid snapshot rung, found by construction
     over randomised header pairs, equals the derived
     table; plus supplementary rows S1 (merkle tail word
     only: MID survives) and S2 (merkle bytes 12..27
     only: R11 is deepest).
"""
import hashlib
import json
import os
import random
import struct
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = "/home/hatch/workspace/bitcoin-autonomous-lab"
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import exp023_snapshots as S  # noqa: E402
from exp023_amortized import (FamilyContext, PAYOUT,  # noqa: E402
                              PreparedTemplate, StubRPC,
                              synth_template)
from mining.engine import MiningEngine, TemplateError  # noqa: E402
from mining.pow import merkle_root  # noqa: E402
from mining.pow_engine import H0, PureSHA256  # noqa: E402

OUT_DIR = os.path.join(HERE, "exp023")
os.makedirs(OUT_DIR, exist_ok=True)
RESULTS = {}


def check(name, cond, detail=""):
    RESULTS[name] = {"pass": bool(cond), "detail": detail}
    print(f"{'PASS' if cond else 'FAIL'}  {name}  {detail}",
          flush=True)
    if not cond:
        raise SystemExit(f"gate failed: {name}")


def gate_a(rng):
    ok = True
    for _ in range(200):
        block = rng.randbytes(64)
        pure = PureSHA256()
        pure._block(block)
        if tuple(pure.h) != S.chaining_after(H0, block):
            ok = False
    check("G-A1 stepper vs PureSHA256 (200 blocks)", ok)
    ok = True
    for _ in range(200):
        header = rng.randbytes(80)
        lad = S.ladder(header)
        want = hashlib.sha256(header).digest()
        for fn in (S.inner_from_mid,):
            if S.words_to_bytes(fn(lad["MID"], header)) != want:
                ok = False
        if S.words_to_bytes(S.inner_from_b2r2(
                lad["MID"], header, lad["B2R2"])) != want:
            ok = False
        if S.words_to_bytes(S.inner_from_sch17(
                lad["MID"], header, lad["SCH17"])) != want:
            ok = False
        # the midstate against PureSHA256 directly
        pure = PureSHA256()
        pure._block(header[:64])
        if tuple(pure.h) != lad["MID"]:
            ok = False
    check("G-A2 snapshot completions vs hashlib (200 headers)", ok)


def gate_b(rng):
    stub = StubRPC()
    eng = MiningEngine(stub, PAYOUT)
    fam = FamilyContext(stub, PAYOUT)
    cases = 0
    configs = [
        dict(ntx=0), dict(ntx=1), dict(ntx=2), dict(ntx=3),
        dict(ntx=10), dict(ntx=100),
        dict(ntx=100, segwit_fraction=0.5),
        dict(ntx=500),
        dict(ntx=500, segwit_fraction=0.5, with_commitment=True),
        dict(ntx=50, flags="abcd"),
        dict(ntx=25, segwit_fraction=1.0, with_commitment=True),
    ]
    for cfg in configs:
        template = synth_template(rng, **cfg)
        stub.template = template
        prep = PreparedTemplate(fam, template)
        ens = [0, 1, 2, 3, 2 ** 32 - 1] + [
            rng.randrange(2 ** 32) for _ in range(115)]
        for en in ens:
            want = eng.build_candidate(template, en)
            got = prep.build(en, now=2_000_000_000)
            assert want["header"] == got["header"], (cfg, en)
            assert want["body"] == got["body"], (cfg, en)
            for k in ("target", "height", "fees", "tx_count",
                      "witness_count"):
                assert want[k] == got[k], (cfg, en, k)
            cases += 1
    check("G-B1 byte-identity build_candidate vs amortised",
          cases >= 1000, f"{cases} cases")
    # fingerprint mismatch must raise, never silently serve
    t1 = synth_template(rng, ntx=10)
    t2 = synth_template(rng, ntx=10)
    prep = PreparedTemplate(fam, t1)
    try:
        prep.build(0, template=t2, now=2_000_000_000)
        raised = False
    except TemplateError:
        raised = True
    check("G-B2 fingerprint mismatch raises", raised)


def gate_c(rng):
    stub = StubRPC()
    fam = FamilyContext(stub, PAYOUT)
    ok = True
    for n in list(range(0, 40)) + [63, 64, 65, 100, 255, 500, 501]:
        txids = [rng.randbytes(32) for _ in range(n)]
        template = {"version": 0x20000000,
                    "previousblockhash": "00" * 32,
                    "transactions": [], "coinbaseaux": {"flags": ""},
                    "coinbasevalue": 0, "target": "1" + "0" * 63,
                    "mintime": 1, "curtime": 2, "bits": "207fffff",
                    "height": 0}
        prep = PreparedTemplate.__new__(PreparedTemplate)
        prep.levels = [[b"\x00" * 32] + list(txids)]
        while len(prep.levels[-1]) > 1:
            lvl = prep.levels[-1]
            from mining.pow import dsha256
            prep.levels.append([
                dsha256(lvl[i] + (lvl[i + 1] if i + 1 < len(lvl)
                                  else lvl[i]))
                for i in range(0, len(lvl), 2)])
        for _ in range(3):
            cb = rng.randbytes(32)
            if prep.root_with_coinbase(cb) != \
                    merkle_root([cb] + txids):
                ok = False
    check("G-C merkle spine vs merkle_root (47 sizes x 3)", ok)


def rand_header(rng):
    return bytearray(rng.randbytes(80))


def with_fields(rng, base, vary):
    """Copy of base with the named fields re-randomised.
    Field byte ranges: version 0..3, prevhash head 4..35,
    merkle tail 36..67 (the whole root; a root change
    avalanches over all its words), time 68..71,
    nbits 72..75. The nonce (76..79) always varies."""
    h = bytearray(base)
    ranges = {"version": (0, 4), "prevhash": (4, 36),
              "merkle": (36, 68), "time": (68, 72),
              "nbits": (72, 76)}
    for f in vary:
        a, b = ranges[f]
        h[a:b] = rng.randbytes(b - a)
    h[76:80] = rng.randbytes(4)
    return bytes(h)


def deepest_rung(h1, h2):
    l1, l2 = S.ladder(h1), S.ladder(h2)
    deepest = None
    for rung in S.RUNGS:
        if l1[rung] == l2[rung]:
            deepest = rung
        else:
            break
    return deepest


def expected_rung(vary):
    if "version" in vary:
        return None
    if "prevhash" in vary:
        return "R0"
    if "merkle" in vary:
        return "R8"
    if "time" in vary:
        return "B2R0"
    if "nbits" in vary:
        return "B2R1"
    return "SCH17"


def gate_def(rng):
    # G-D: extranonce-driven root change (merkle axis only)
    for _ in range(20):
        base = rand_header(rng)
        other = with_fields(rng, base, {"merkle"})
        assert base[:36] == other[:36] and base[36:68] != other[36:68]
        got = deepest_rung(bytes(base), other)
        assert got == "R8", got
    check("G-D Y-076: root change kills MID, spares R8 (20 pairs)",
          True)
    # G-E: family sharing and the R11 alignment boundary
    ok = True
    for _ in range(20):
        base = rand_header(rng)
        diff_head = with_fields(rng, base, {"merkle"})
        if S.ladder(bytes(base))["R11"] == S.ladder(diff_head)["R11"]:
            ok = False
        aligned = bytearray(base)
        aligned[48:68] = rng.randbytes(20)  # root bytes 12..31 vary
        aligned[76:80] = rng.randbytes(4)
        if S.ladder(bytes(base))["R11"] != S.ladder(bytes(aligned))["R11"]:
            ok = False
        if S.ladder(bytes(base))["MID"] == S.ladder(bytes(aligned))["MID"]:
            ok = False
    check("G-E Y-077: R11 shared iff merkle head aligns (20 pairs)", ok)


def gate_f(rng):
    fields = ["version", "prevhash", "merkle", "time", "nbits"]
    rows = 0
    for mask in range(32):
        vary = {fields[i] for i in range(5) if mask & (1 << i)}
        want = expected_rung(vary)
        for _ in range(3):
            base = rand_header(rng)
            other = with_fields(rng, base, vary)
            got = deepest_rung(bytes(base), other)
            assert got == want, (vary, want, got)
            rows += 1
    check("G-F1 Y-079 table: 32 subsets x 3 instances", rows == 96)
    # S1: merkle tail word only (bytes 64..67) varies
    for _ in range(10):
        base = rand_header(rng)
        other = bytearray(base)
        other[64:68] = rng.randbytes(4)
        other[76:80] = rng.randbytes(4)
        assert deepest_rung(bytes(base), bytes(other)) == "MID"
    check("G-F2 S1 tail-word-only change: MID survives (10 pairs)",
          True)
    # S2: merkle bytes 12..27 only (block-1 words W12..W15)
    for _ in range(10):
        base = rand_header(rng)
        other = bytearray(base)
        other[48:64] = rng.randbytes(16)
        other[76:80] = rng.randbytes(4)
        assert deepest_rung(bytes(base), bytes(other)) == "R11"
    check("G-F3 S2 head-aligned root change: R11 deepest (10 pairs)",
          True)


def main():
    rng = random.Random(23023)
    gate_a(rng)
    gate_b(rng)
    gate_c(rng)
    gate_def(rng)
    gate_f(rng)
    record = {
        "experiment": "EXP-023",
        "recorded_utc": datetime.now(timezone.utc).isoformat(),
        "host": os.uname().nodename,
        "gates": RESULTS,
        "all_pass": all(v["pass"] for v in RESULTS.values()),
    }
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(OUT_DIR, f"gates_{stamp}.json")
    with open(path, "x") as fh:
        json.dump(record, fh, indent=2)
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
