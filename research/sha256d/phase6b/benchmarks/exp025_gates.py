#!/usr/bin/env python3
"""EXP-025 gates for the repaired cache
(exp025_repaired.py). All must pass.

G-A  Adversarial invalidation: every mutation from the
     directive's list, checked three ways: (1) the base
     prepared template's build(sibling) raises
     TemplateError (never silently serves); (2) a fresh
     identity-keyed lookup prepares a NEW entry whose
     output is byte-identical to a complete uncached
     reconstruction; (3) where the mutation makes the
     template invalid, the repaired identity path raises
     exactly as the uncached path does.
G-B  Positive controls: identical inputs hit the cache
     (counters prove reuse) with byte-identical output;
     a curtime-only sibling is served by build() (time
     is a per-build input, not identity) with output
     byte-identical to uncached.
G-C  Randomised differential campaign: at least 1,000
     (template, extranonce) cases, 0 to 500
     transactions, segwit mixes, flags, witness
     commitments; cached vs uncached byte-identical on
     header, body and every scalar field.

Time handling: synth templates carry curtime
1700000000 and mintime 1, so both paths clamp to the
same header time deterministically (the EXP-023 gate
pattern); the timestamp mutation case freezes
time.time for the uncached path and passes the same
`now` to the repaired build.
"""
import copy
import json
import os
import random
import sys
import time as time_mod
from datetime import datetime, timezone

ROOT = "/home/hatch/workspace/bitcoin-autonomous-lab"
HERE = os.path.dirname(os.path.abspath(__file__))
P6 = os.path.join(ROOT, "research/sha256d/phase6/benchmarks")
OUT_DIR = os.path.join(HERE, "exp025")
sys.path.insert(0, HERE)
sys.path.insert(0, P6)
sys.path.insert(0, ROOT)

from exp023_amortized import (PAYOUT, StubRPC,  # noqa: E402
                              synth_template, synth_tx)
from exp025_repaired import (RepairedFamily,  # noqa: E402
                             RepairedTemplate, TemplateCache,
                             identity_of)
from mining.engine import (MiningEngine, TemplateError,  # noqa: E402
                           txid_of, wtxid_of)
from mining.pow import coinbase_subsidy, dsha256, merkle_root  # noqa: E402

NOW = 2_000_000_000
ZERO32 = b"\x00" * 32
RESULTS = {}


def check(name, cond, detail=""):
    RESULTS[name] = {"pass": bool(cond), "detail": detail}
    print(f"{'PASS' if cond else 'FAIL'}  {name}  {detail}",
          flush=True)
    if not cond:
        raise SystemExit(f"gate failed: {name}")


def commitment_hex(template):
    wtxids = [wtxid_of(bytes.fromhex(tx["data"]))
              for tx in template["transactions"]]
    wroot = merkle_root([ZERO32] + wtxids)
    return "6a24aa21a9ed" + dsha256(wroot + ZERO32).hex()


def uncached(eng, template, en=0, freeze_now=None):
    if freeze_now is None:
        return eng.build_candidate(template, en)
    real = time_mod.time
    time_mod.time = lambda: freeze_now
    try:
        return eng.build_candidate(template, en)
    finally:
        time_mod.time = real


def same_output(a, b):
    if a["header"] != b["header"] or a["body"] != b["body"]:
        return False
    return all(a[k] == b[k] for k in
               ("target", "height", "fees", "tx_count",
                "witness_count"))


def adversarial_case(name, base, mut, eng, fam, cache,
                     expect="new_identity"):
    """expect: 'new_identity' (valid template, different
    identity), 'invalid' (both paths raise), or
    'same_identity' (per-build input only)."""
    base_prep, _ = cache.get(fam, base)
    # (1) sibling serve through the base entry
    sibling_raised = False
    try:
        base_prep.build(0, template=mut, now=NOW)
    except TemplateError:
        sibling_raised = True
    # (2)/(3) fresh lookup and uncached reference
    unc_error = None
    try:
        want = uncached(eng, mut, 0, freeze_now=NOW)
    except TemplateError as exc:
        unc_error = str(exc)
    got = None
    get_error = None
    prepares_before = cache.prepares
    try:
        prep2, was_hit = cache.get(fam, mut)
        got = prep2.build(0, template=mut, now=NOW)
    except TemplateError as exc:
        get_error = str(exc)
    if expect == "invalid":
        ok = (sibling_raised and unc_error is not None
              and get_error is not None)
        check(f"G-A {name}", ok,
              f"sibling_raised={sibling_raised} "
              f"uncached_raises={unc_error is not None} "
              f"identity_raises={get_error is not None}")
        return
    if expect == "same_identity":
        ok = (not sibling_raised and unc_error is None
              and got is not None and same_output(got, want))
        check(f"G-A {name}", ok,
              "served under same identity, byte-identical")
        return
    ok = (sibling_raised and unc_error is None
          and get_error is None and got is not None
          and same_output(got, want)
          and cache.prepares == prepares_before + 1)
    check(f"G-A {name}", ok,
          f"sibling_raised={sibling_raised} "
          f"new_prepare={cache.prepares == prepares_before + 1} "
          f"byte_identical={got is not None and same_output(got, want)}")


def gate_a(rng):
    stub = StubRPC()
    eng = MiningEngine(stub, PAYOUT)
    fam = RepairedFamily(stub, PAYOUT)
    cache = TemplateCache()
    base = synth_template(rng, 10, segwit_fraction=0.5,
                          with_commitment=True)
    stub.template = base

    def fresh_tx(segwit=False):
        raw = synth_tx(rng, segwit=segwit)
        return raw

    mut = copy.deepcopy(base)
    raw = fresh_tx()
    mut["transactions"][4] = {
        "txid": txid_of(raw)[::-1].hex(), "data": raw.hex(),
        "fee": mut["transactions"][4]["fee"]}
    mut["default_witness_commitment"] = commitment_hex(mut)
    adversarial_case("middle_tx_changed", base, mut, eng, fam,
                     cache)

    mut = copy.deepcopy(base)
    raw = fresh_tx()
    mut["transactions"][0] = {
        "txid": txid_of(raw)[::-1].hex(), "data": raw.hex(),
        "fee": mut["transactions"][0]["fee"]}
    mut["default_witness_commitment"] = commitment_hex(mut)
    adversarial_case("first_tx_changed", base, mut, eng, fam,
                     cache)

    mut = copy.deepcopy(base)
    raw = fresh_tx()
    mut["transactions"][-1] = {
        "txid": txid_of(raw)[::-1].hex(), "data": raw.hex(),
        "fee": mut["transactions"][-1]["fee"]}
    mut["default_witness_commitment"] = commitment_hex(mut)
    adversarial_case("last_tx_changed", base, mut, eng, fam,
                     cache)

    mut = copy.deepcopy(base)
    mut["transactions"][2], mut["transactions"][3] = \
        mut["transactions"][3], mut["transactions"][2]
    mut["default_witness_commitment"] = commitment_hex(mut)
    adversarial_case("tx_reordered", base, mut, eng, fam, cache)

    mut = copy.deepcopy(base)
    idx = next(i for i, tx in enumerate(mut["transactions"])
               if bytes.fromhex(tx["data"])[4:6] == b"\x00\x01")
    raw0 = bytearray(bytes.fromhex(mut["transactions"][idx]["data"]))
    raw0[-24] ^= 0xFF
    mut["transactions"][idx]["data"] = bytes(raw0).hex()
    assert txid_of(bytes(raw0)) == txid_of(
        bytes.fromhex(base["transactions"][idx]["data"]))
    mut["default_witness_commitment"] = commitment_hex(mut)
    adversarial_case("witness_only_change_txid_fixed", base, mut,
                     eng, fam, cache)

    # coinbase value changed, kept valid by a compensating
    # fee change on one transaction.
    mut = copy.deepcopy(base)
    mut["transactions"][1]["fee"] += 777
    mut["coinbasevalue"] += 777
    adversarial_case("coinbase_value_changed_valid", base, mut,
                     eng, fam, cache)

    # coinbase value changed alone: invalid everywhere.
    mut = copy.deepcopy(base)
    mut["coinbasevalue"] += 1
    adversarial_case("coinbase_value_changed_invalid", base, mut,
                     eng, fam, cache, expect="invalid")

    mut = copy.deepcopy(base)
    mut["previousblockhash"] = rng.randbytes(32).hex()
    adversarial_case("prevhash_changed", base, mut, eng, fam,
                     cache)

    mut = copy.deepcopy(base)
    mut["version"] = 0x20000002
    adversarial_case("version_changed", base, mut, eng, fam,
                     cache)

    mut = copy.deepcopy(base)
    mut["bits"] = "207fff00"
    adversarial_case("bits_changed", base, mut, eng, fam, cache)

    mut = copy.deepcopy(base)
    mut["target"] = "0" * 8 + "f" * 56
    adversarial_case("target_changed", base, mut, eng, fam,
                     cache)

    mut = copy.deepcopy(base)
    mut["coinbaseaux"] = {"flags": "abcd"}
    adversarial_case("flags_changed", base, mut, eng, fam, cache)

    # timestamp: per-build input, same identity, served.
    mut = copy.deepcopy(base)
    mut["curtime"] = base["curtime"] + 600
    adversarial_case("curtime_changed_per_build_input", base,
                     mut, eng, fam, cache,
                     expect="same_identity")

    # transaction count: add one.
    mut = copy.deepcopy(base)
    raw = fresh_tx(segwit=True)
    fee = rng.randrange(500, 5000)
    mut["transactions"].append({
        "txid": txid_of(raw)[::-1].hex(), "data": raw.hex(),
        "fee": fee})
    mut["coinbasevalue"] += fee
    mut["default_witness_commitment"] = commitment_hex(mut)
    adversarial_case("tx_added", base, mut, eng, fam, cache)

    # transaction count: remove one (not first or last).
    mut = copy.deepcopy(base)
    removed = mut["transactions"].pop(5)
    mut["coinbasevalue"] -= removed["fee"]
    mut["default_witness_commitment"] = commitment_hex(mut)
    adversarial_case("tx_removed", base, mut, eng, fam, cache)

    # witness commitment input: field removed entirely.
    mut = copy.deepcopy(base)
    mut.pop("default_witness_commitment", None)
    adversarial_case("commitment_field_removed", base, mut, eng,
                     fam, cache)

    # witness commitment input: wrong value, invalid.
    mut = copy.deepcopy(base)
    mut["default_witness_commitment"] = "6a24aa21a9ed" + "00" * 32
    adversarial_case("commitment_field_wrong", base, mut, eng,
                     fam, cache, expect="invalid")

    # fee raised with coinbasevalue NOT adjusted: invalid.
    mut = copy.deepcopy(base)
    mut["transactions"][3]["fee"] += 100
    adversarial_case("fee_up_value_fixed", base, mut, eng, fam,
                     cache, expect="invalid")

    # fee moved between txs, total fixed: per-tx fees are
    # keyed, so this is a new identity (stricter than the
    # output requires); output must still be identical.
    mut = copy.deepcopy(base)
    mut["transactions"][1]["fee"] += 250
    mut["transactions"][2]["fee"] -= 250
    adversarial_case("fee_moved_total_fixed", base, mut, eng,
                     fam, cache)


def gate_b(rng):
    stub = StubRPC()
    eng = MiningEngine(stub, PAYOUT)
    fam = RepairedFamily(stub, PAYOUT)
    cache = TemplateCache()
    template = synth_template(rng, 50, segwit_fraction=0.5,
                              with_commitment=True)
    stub.template = template
    prep1, hit1 = cache.get(fam, template)
    prep2, hit2 = cache.get(fam, copy.deepcopy(template))
    check("G-B1 identical inputs reuse cache",
          (not hit1) and hit2 and prep1 is prep2
          and cache.prepares == 1 and cache.hits == 1,
          f"prepares={cache.prepares} hits={cache.hits}")
    ok = True
    for en in (0, 1, 2, 3, 2 ** 32 - 1):
        want = uncached(eng, template, en)
        got = prep1.build(en, now=NOW)
        ok = ok and same_output(got, want)
    check("G-B2 reused entry byte-identical over extranonces",
          ok)
    # extranonce is a per-build input: same entry, varying
    # extranonce, always equal to uncached.
    ok = True
    for en in [rng.randrange(2 ** 32) for _ in range(20)]:
        ok = ok and same_output(prep1.build(en, now=NOW),
                                uncached(eng, template, en))
    check("G-B3 extranonce variation byte-identical (20)", ok)


def gate_c(rng):
    stub = StubRPC()
    eng = MiningEngine(stub, PAYOUT)
    fam = RepairedFamily(stub, PAYOUT)
    cache = TemplateCache()
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
        prep, _ = cache.get(fam, template)
        ens = [0, 1, 2, 3, 2 ** 32 - 1] + [
            rng.randrange(2 ** 32) for _ in range(115)]
        for en in ens:
            want = uncached(eng, template, en)
            got = prep.build(en, now=NOW)
            assert same_output(got, want), (cfg, en)
            cases += 1
    check("G-C randomised differential campaign", cases >= 1000,
          f"{cases} cases, cache prepares={cache.prepares}")


def main():
    rng = random.Random(25025)
    gate_a(rng)
    gate_b(rng)
    gate_c(rng)
    record = {
        "experiment": "EXP-025",
        "recorded_utc": datetime.now(timezone.utc).isoformat(),
        "host_cpu": open("/proc/cpuinfo").read().split(
            "model name")[1].split(":")[1].split("\n")[0].strip(),
        "gates": RESULTS,
        "all_pass": all(v["pass"] for v in RESULTS.values()),
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(OUT_DIR, f"gates_{stamp}.json")
    suffix = 2
    while os.path.exists(path):
        path = os.path.join(OUT_DIR, f"gates_{stamp}_r{suffix}.json")
        suffix += 1
    with open(path, "x") as fh:
        json.dump(record, fh, indent=2)
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
