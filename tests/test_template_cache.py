#!/usr/bin/env python3
"""EXP-025 repaired template cache: production integration gates.

Gates the cache integrated into mining/engine.py (owner decision
2026-11-14, option A; design record:
research/sha256d/phase6b/EXP025_CACHE_CORRECTNESS.md):

G-A  Adversarial invalidation, 19 cases (including the EXP-025
     defect cases D1 to D7 that broke the EXP-023 prototype),
     each checked at the prepared-entry level (a sibling serve
     under a changed identity raises TemplateError, never
     silently serves) and at the engine level (the cached
     build_candidate is byte-identical to the uncached path for
     valid mutations, and raises exactly where it raises for
     invalid ones; a changed identity prepares a new cache
     entry, an unchanged one does not).
G-B  Positive controls: identical inputs reuse the cache
     (counters prove it), a prepared entry stays byte-identical
     across boundary and random extranonces, the mining-loop
     steps shape prepares once for 64 steps, and the uncached
     fallback (use_template_cache=False) is byte-identical with
     zero cache activity.
G-C  Randomised differential campaign: 1,320 (template,
     extranonce) cases over 11 configurations (0 to 500
     transactions, segwit mixes, flags, witness commitments),
     cached vs uncached byte-identical on header, body and
     every scalar field.
G-D  Validation parity: every invalid input shape raises
     TemplateError on the cached path exactly as on the
     uncached path, on first serve and on sibling serves.
G-E  Regtest: a fresh block mined through the production
     MiningEngine with the cache active (mine_cycle steps fast
     path), accepted by Core as the best block.

Synthetic templates use curtime 1700000000 and mintime 1, so
both paths clamp the header time to the same value
deterministically (the EXP-023/EXP-025 gate pattern).
"""

import copy
import os
import random
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mining.engine import (MiningEngine, TemplateError,  # noqa: E402
                           txid_of, wtxid_of)
from mining.pow import coinbase_subsidy, dsha256, merkle_root  # noqa: E402

PAYOUT = "bc1q528egeqsvv8aa382j43edxskqw6x7zxc2xpcf3"
SPK = "0014" + "11" * 20
NOW = 2_000_000_000
ZERO32 = b"\x00" * 32


class StubRPC:
    """Zero-latency counting RPC (the EXP-023 fixture shape)."""

    def __init__(self, template=None):
        self.template = template
        self.counts = {}

    def call(self, method, *args):
        self.counts[method] = self.counts.get(method, 0) + 1
        if method == "getblocktemplate":
            return self.template
        if method == "validateaddress":
            return {"isvalid": True, "scriptPubKey": SPK}
        if method == "getblockchaininfo":
            return {"chain": "regtest"}
        if method == "submitblock":
            return None
        raise ValueError(method)

    def get_blockchain_info(self):
        return self.call("getblockchaininfo")

    def get_best_block_hash(self):
        return "00" * 32

    def with_timeout(self, _t):
        return self


def synth_tx(rng, segwit=False):
    prev = rng.randbytes(32)
    value = rng.randrange(1, 10 ** 8)
    script = b"\x76\xa9\x14" + rng.randbytes(20) + b"\x88\xac"
    vin = (prev + struct.pack("<I", rng.randrange(4))
           + b"\x00" + struct.pack("<I", 0xFFFFFFFE))
    vout = struct.pack("<Q", value) + bytes([len(script)]) + script
    if not segwit:
        return (struct.pack("<i", 1) + b"\x01" + vin + b"\x01" + vout
                + struct.pack("<I", 0))
    wit = rng.randbytes(20)
    return (struct.pack("<i", 2) + b"\x00\x01" + b"\x01" + vin
            + b"\x01" + vout
            + b"\x01" + bytes([len(wit)]) + wit
            + struct.pack("<I", 0))


def synth_template(rng, ntx, segwit_fraction=0.0, flags="",
                   with_commitment=False, height=1000,
                   curtime=1700000000):
    txs = []
    total_fees = 0
    for _ in range(ntx):
        raw = synth_tx(rng, segwit=rng.random() < segwit_fraction)
        fee = rng.randrange(500, 5000)
        total_fees += fee
        txs.append({"txid": txid_of(raw)[::-1].hex(),
                    "data": raw.hex(), "fee": fee})
    template = {
        "version": 0x20000000,
        "previousblockhash": rng.randbytes(32).hex(),
        "transactions": txs,
        "coinbaseaux": {"flags": flags},
        "coinbasevalue": coinbase_subsidy(height, 150) + total_fees,
        "target": "7fffff0000000000000000000000000000000000000000"
                  "000000000000000000",
        "mintime": 1, "curtime": curtime,
        "bits": "207fffff", "height": height,
    }
    if with_commitment:
        template["default_witness_commitment"] = commitment_hex(
            template)
    return template


def commitment_hex(template):
    wtxids = [wtxid_of(bytes.fromhex(tx["data"]))
              for tx in template["transactions"]]
    wroot = merkle_root([ZERO32] + wtxids)
    return "6a24aa21a9ed" + dsha256(wroot + ZERO32).hex()


def same_output(a, b):
    if a["header"] != b["header"] or a["body"] != b["body"]:
        return False
    return all(a[k] == b[k] for k in
               ("target", "height", "fees", "tx_count",
                "witness_count"))


def make_engines():
    stub = StubRPC()
    cached = MiningEngine(stub, PAYOUT, compute=object())
    uncached = MiningEngine(stub, PAYOUT, compute=object(),
                            use_template_cache=False)
    return stub, cached, uncached


def adversarial_case(name, base, mut, cached, uncached,
                     expect="new_identity"):
    """expect: 'new_identity' (valid, different identity),
    'invalid' (both paths raise), 'same_identity' (per-build
    input only)."""
    base_prep, _ = cached.prepare_template(base)
    sibling_raised = False
    try:
        base_prep.build(0, template=mut, now=NOW)
    except TemplateError:
        sibling_raised = True
    unc_error = None
    try:
        want = uncached.build_candidate_uncached(mut, 0)
    except TemplateError as exc:
        unc_error = str(exc)
    got = None
    got_error = None
    prepares_before = cached.template_cache.prepares
    try:
        got = cached.build_candidate(mut, 0)
    except TemplateError as exc:
        got_error = str(exc)
    if expect == "invalid":
        ok = (sibling_raised and unc_error is not None
              and got_error is not None
              and cached.template_cache.prepares == prepares_before)
        assert ok, (name, sibling_raised, unc_error, got_error)
        print(f"ok G-A {name}: sibling refused, both paths raise, "
              f"no new prepare")
        return
    if expect == "same_identity":
        ok = (not sibling_raised and unc_error is None
              and got is not None and same_output(got, want)
              and cached.template_cache.prepares == prepares_before)
        assert ok, name
        print(f"ok G-A {name}: served under same identity, "
              f"byte-identical, no new prepare")
        return
    ok = (sibling_raised and unc_error is None
          and got_error is None and got is not None
          and same_output(got, want)
          and cached.template_cache.prepares == prepares_before + 1)
    assert ok, (name, sibling_raised, unc_error, got_error,
                cached.template_cache.prepares, prepares_before)
    print(f"ok G-A {name}: sibling refused, new entry prepared, "
          f"byte-identical to uncached")


def gate_a(rng):
    stub, cached, uncached = make_engines()
    base = synth_template(rng, 10, segwit_fraction=0.5,
                          with_commitment=True)
    stub.template = base

    def fresh_tx(segwit=False):
        return synth_tx(rng, segwit=segwit)

    # D1: middle transaction replaced.
    mut = copy.deepcopy(base)
    raw = fresh_tx()
    mut["transactions"][4] = {
        "txid": txid_of(raw)[::-1].hex(), "data": raw.hex(),
        "fee": mut["transactions"][4]["fee"]}
    mut["default_witness_commitment"] = commitment_hex(mut)
    adversarial_case("D1 middle_tx_changed", base, mut, cached,
                     uncached)

    mut = copy.deepcopy(base)
    raw = fresh_tx()
    mut["transactions"][0] = {
        "txid": txid_of(raw)[::-1].hex(), "data": raw.hex(),
        "fee": mut["transactions"][0]["fee"]}
    mut["default_witness_commitment"] = commitment_hex(mut)
    adversarial_case("first_tx_changed", base, mut, cached,
                     uncached)

    mut = copy.deepcopy(base)
    raw = fresh_tx()
    mut["transactions"][-1] = {
        "txid": txid_of(raw)[::-1].hex(), "data": raw.hex(),
        "fee": mut["transactions"][-1]["fee"]}
    mut["default_witness_commitment"] = commitment_hex(mut)
    adversarial_case("last_tx_changed", base, mut, cached,
                     uncached)

    # D3: two middle transactions reordered.
    mut = copy.deepcopy(base)
    mut["transactions"][2], mut["transactions"][3] = \
        mut["transactions"][3], mut["transactions"][2]
    mut["default_witness_commitment"] = commitment_hex(mut)
    adversarial_case("D3 tx_reordered", base, mut, cached,
                     uncached)

    # D2: witness bytes changed, txid held fixed.
    mut = copy.deepcopy(base)
    idx = next(i for i, tx in enumerate(mut["transactions"])
               if bytes.fromhex(tx["data"])[4:6] == b"\x00\x01")
    raw0 = bytearray(bytes.fromhex(mut["transactions"][idx]["data"]))
    raw0[-24] ^= 0xFF
    mut["transactions"][idx]["data"] = bytes(raw0).hex()
    assert txid_of(bytes(raw0)) == txid_of(
        bytes.fromhex(base["transactions"][idx]["data"]))
    mut["default_witness_commitment"] = commitment_hex(mut)
    adversarial_case("D2 witness_only_change_txid_fixed", base,
                     mut, cached, uncached)

    mut = copy.deepcopy(base)
    mut["transactions"][1]["fee"] += 777
    mut["coinbasevalue"] += 777
    adversarial_case("coinbase_value_changed_valid", base, mut,
                     cached, uncached)

    mut = copy.deepcopy(base)
    mut["coinbasevalue"] += 1
    adversarial_case("coinbase_value_changed_invalid", base, mut,
                     cached, uncached, expect="invalid")

    mut = copy.deepcopy(base)
    mut["previousblockhash"] = rng.randbytes(32).hex()
    adversarial_case("prevhash_changed", base, mut, cached,
                     uncached)

    mut = copy.deepcopy(base)
    mut["version"] = 0x20000002
    adversarial_case("version_changed", base, mut, cached,
                     uncached)

    mut = copy.deepcopy(base)
    mut["bits"] = "207fff00"
    adversarial_case("bits_changed", base, mut, cached, uncached)

    # D5: target changed.
    mut = copy.deepcopy(base)
    mut["target"] = "0" * 8 + "f" * 56
    adversarial_case("D5 target_changed", base, mut, cached,
                     uncached)

    # D4: coinbaseaux flags changed.
    mut = copy.deepcopy(base)
    mut["coinbaseaux"] = {"flags": "abcd"}
    adversarial_case("D4 flags_changed", base, mut, cached,
                     uncached)

    mut = copy.deepcopy(base)
    mut["curtime"] = base["curtime"] + 600
    adversarial_case("curtime_changed_per_build_input", base, mut,
                     cached, uncached, expect="same_identity")

    mut = copy.deepcopy(base)
    raw = fresh_tx(segwit=True)
    fee = rng.randrange(500, 5000)
    mut["transactions"].append({
        "txid": txid_of(raw)[::-1].hex(), "data": raw.hex(),
        "fee": fee})
    mut["coinbasevalue"] += fee
    mut["default_witness_commitment"] = commitment_hex(mut)
    adversarial_case("tx_added", base, mut, cached, uncached)

    mut = copy.deepcopy(base)
    removed = mut["transactions"].pop(5)
    mut["coinbasevalue"] -= removed["fee"]
    mut["default_witness_commitment"] = commitment_hex(mut)
    adversarial_case("tx_removed", base, mut, cached, uncached)

    mut = copy.deepcopy(base)
    mut.pop("default_witness_commitment", None)
    adversarial_case("commitment_field_removed", base, mut,
                     cached, uncached)

    # D7: witness commitment field wrong.
    mut = copy.deepcopy(base)
    mut["default_witness_commitment"] = "6a24aa21a9ed" + "00" * 32
    adversarial_case("D7 commitment_field_wrong", base, mut,
                     cached, uncached, expect="invalid")

    # D6: fee raised with coinbasevalue not adjusted.
    mut = copy.deepcopy(base)
    mut["transactions"][3]["fee"] += 100
    adversarial_case("D6 fee_up_value_fixed", base, mut, cached,
                     uncached, expect="invalid")

    mut = copy.deepcopy(base)
    mut["transactions"][1]["fee"] += 250
    mut["transactions"][2]["fee"] -= 250
    adversarial_case("fee_moved_total_fixed", base, mut, cached,
                     uncached)
    print("ok G-A: 19 adversarial cases pass (D1 to D7 included)")


def gate_b(rng):
    stub, cached, uncached = make_engines()
    template = synth_template(rng, 50, segwit_fraction=0.5,
                              with_commitment=True)
    stub.template = template
    out1 = cached.build_candidate(template, 0)
    stats1 = (cached.template_cache.prepares,
              cached.template_cache.hits)
    out2 = cached.build_candidate(copy.deepcopy(template), 0)
    assert stats1 == (1, 0), stats1
    assert cached.template_cache.prepares == 1
    assert cached.template_cache.hits == 1
    assert same_output(out1, out2)
    print("ok G-B1 identical inputs reuse cache: prepares=1 "
          "hits=1, byte-identical")

    prep, _ = cached.prepare_template(template)
    ok = True
    for en in (0, 1, 2, 3, 2 ** 32 - 1):
        want = uncached.build_candidate_uncached(template, en)
        got = prep.build(en, now=NOW)
        ok = ok and same_output(got, want)
    assert ok
    print("ok G-B2 reused entry byte-identical over boundary "
          "extranonces")
    ok = True
    for en in [rng.randrange(2 ** 32) for _ in range(20)]:
        ok = ok and same_output(
            prep.build(en, now=NOW),
            uncached.build_candidate_uncached(template, en))
    assert ok
    print("ok G-B3 extranonce variation byte-identical (20)")

    # Steps shape: one prepare, 64 steps, no further prepares,
    # every step byte-identical to the uncached path.
    stub2, cached2, uncached2 = make_engines()
    prep2, hit = cached2.prepare_template(template)
    assert not hit and cached2.template_cache.prepares == 1
    for en in range(64):
        got = prep2.build(en, now=NOW)
        want = uncached2.build_candidate_uncached(template, en)
        assert same_output(got, want), en
    assert cached2.template_cache.prepares == 1
    print("ok G-B4 steps shape: 1 prepare for 64 extranonce "
          "steps, all byte-identical")

    # Uncached fallback: byte-identical, zero cache activity.
    out3 = uncached.build_candidate(template, 7)
    want3 = uncached.build_candidate_uncached(template, 7)
    assert same_output(out3, want3)
    assert uncached.template_cache.prepares == 0
    assert uncached.template_cache.identity_checks == 0
    print("ok G-B5 uncached fallback byte-identical, cache "
          "untouched")


def gate_c(rng):
    stub, cached, uncached = make_engines()
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
        ens = [0, 1, 2, 3, 2 ** 32 - 1] + [
            rng.randrange(2 ** 32) for _ in range(115)]
        for en in ens:
            want = uncached.build_candidate_uncached(template, en)
            got = cached.build_candidate(template, en)
            assert same_output(got, want), (cfg, en)
            cases += 1
    assert cases == 1320, cases
    print(f"ok G-C randomised differential campaign: {cases} "
          f"(template, extranonce) cases byte-identical, cache "
          f"prepares={cached.template_cache.prepares}")


def gate_d(rng):
    stub, cached, uncached = make_engines()
    base = synth_template(rng, 10, segwit_fraction=0.5,
                          with_commitment=True)
    stub.template = base
    base_prep, _ = cached.prepare_template(base)

    def invalid_mutations():
        mut = copy.deepcopy(base)
        mut["transactions"][2]["txid"] = "00" * 32
        yield "txid_field_wrong", mut
        mut = copy.deepcopy(base)
        del mut["transactions"][2]["data"]
        yield "tx_data_missing", mut
        mut = copy.deepcopy(base)
        del mut["transactions"][2]["txid"]
        yield "tx_txid_missing", mut
        mut = copy.deepcopy(base)
        mut["coinbasevalue"] += 1
        yield "coinbasevalue_mismatch", mut
        mut = copy.deepcopy(base)
        mut["transactions"][3]["fee"] += 100
        yield "fee_up_value_fixed", mut
        mut = copy.deepcopy(base)
        mut["default_witness_commitment"] = (
            "6a24aa21a9ed" + "00" * 32)
        yield "commitment_wrong", mut

    for name, mut in invalid_mutations():
        for label, fn in (
                ("uncached", lambda: uncached
                 .build_candidate_uncached(mut, 0)),
                ("cached first serve", lambda: cached
                 .build_candidate(mut, 0)),
                ("cached sibling serve", lambda: base_prep
                 .build(0, template=mut, now=NOW)),
                ("cached prepare", lambda: cached
                 .prepare_template(mut))):
            try:
                fn()
            except TemplateError:
                continue
            raise AssertionError(f"{name}: {label} did not raise")
        print(f"ok G-D {name}: TemplateError on uncached, "
              f"cached first serve, sibling serve and prepare")


def gate_e():
    from node import node_manager
    from node.rpc_client import BitcoinRPC
    node_manager.start()
    rpc = BitcoinRPC()
    if "bal-regtest" not in rpc.call("listwallets"):
        try:
            rpc.call("loadwallet", "bal-regtest")
        except Exception:
            rpc.call("createwallet", "bal-regtest")
    wallet = BitcoinRPC(wallet="bal-regtest")
    payout = wallet.call("getnewaddress", "", "bech32")
    eng = MiningEngine(rpc, payout, batch_size=100_000)
    assert eng.use_template_cache
    tip0 = rpc.get_block_count()
    out = eng.mine_cycle(max_batches=1000, deadline_seconds=600)
    assert out["accepted"], out
    assert rpc.get_best_block_hash() == out["hash"]
    assert rpc.get_block_count() == tip0 + 1
    stats = eng.template_cache
    assert stats.prepares >= 1 and stats.identity_checks >= 1, (
        stats.prepares, stats.identity_checks)
    print(f"ok G-E regtest: block accepted through the "
          f"production MiningEngine with the template cache "
          f"active (mine_cycle steps fast path): cache "
          f"prepares={stats.prepares} hits={stats.hits} "
          f"identity_checks={stats.identity_checks}")
    print(f"REGTEST height={out['height']} hash={out['hash']}")
    return out


def main():
    rng = random.Random(25025)
    gate_a(rng)
    gate_b(rng)
    gate_c(rng)
    gate_d(rng)
    gate_e()
    print("ALL TEMPLATE CACHE TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
