#!/usr/bin/env python3
"""EXP-034: autonomous job and template engine verification.

An INDEPENDENT adversarial campaign over the production job and
template machinery (mining/engine.py template cache and candidate
construction, mining/solo_server.py job construction and refresh,
mining/stratum_client.py freshness guards). It does not rerun
the EXP-025 integration gates in tests/test_template_cache.py;
every case here was designed for this audit. Where a case pins
behaviour that is a known design boundary rather than a defect,
the test says so in its name and the EXP-034 report explains.

Sections:
  A  Template cache adversarial cases beyond the EXP-025 set:
     height-only change, mintime as a per-build input, witness
     commitment over-keying, target string representation,
     unmodelled Core fields, missing coinbaseaux, cache bound
     and eviction, the held-object mutation boundary, extranonce
     stepping anatomy, equal-content sibling serves.
  B  Job construction against Bitcoin Core on regtest: engine
     merkle root, tx order, coinbase value and witness
     commitment checked against Core's own block record; solo
     server branch versus full-root agreement on a multi-tx
     template and a solo block accepted by Core.
  C  Extranonce space separation: the two-engine collision
     proven byte for byte, separation by payout, engine versus
     solo coinbase anatomy, and the EXP-034 extranonce_space
     fix (disjoint configured spaces, default unchanged).
  D  Template freshness: solo JobRefresher keyed on the node
     tip hash (not ntime), MiningEngine freshness granularity
     (cycle boundary, no in-cycle invalidation), Stratum client
     duplicate and stale-echo guards, and new-tip acceptance
     with a regressed ntime (the Phase A W4 comparison).

Synthetic templates follow the established gate pattern:
curtime 1700000000 and mintime 1 unless a case says otherwise,
so both construction paths clamp header time deterministically.
"""

import copy
import os
import struct
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mining.engine import (MiningEngine, TemplateCache,  # noqa: E402
                           TemplateError, build_coinbase, txid_of,
                           wtxid_of)
from mining.pow import coinbase_subsidy, dsha256, merkle_root  # noqa: E402

PAYOUT = "bc1q528egeqsvv8aa382j43edxskqw6x7zxc2xpcf3"
PAYOUT2 = "bc1q528egeqsvv8aa382j43edxskqw6x7zxc2xpcf4"
SPK = "0014" + "11" * 20
SPK2 = "0014" + "22" * 20
NOW = 2_000_000_000
ZERO32 = b"\x00" * 32
CURTIME = 1700000000


class StubRPC:
    """Counting stub RPC with a per-address script map."""

    def __init__(self, template=None):
        self.template = template
        self.counts = {}
        self.scripts = {PAYOUT: SPK, PAYOUT2: SPK2}

    def call(self, method, *args):
        self.counts[method] = self.counts.get(method, 0) + 1
        if method == "getblocktemplate":
            return self.template
        if method == "validateaddress":
            return {"isvalid": True,
                    "scriptPubKey": self.scripts[args[0]]}
        if method == "getblockchaininfo":
            return {"chain": "regtest", "blocks": 1000,
                    "headers": 1000, "initialblockdownload": False,
                    "bestblockhash":
                        (self.template or {}).get(
                            "previousblockhash", "00" * 32)}
        if method == "submitblock":
            return None
        raise ValueError(method)

    def get_blockchain_info(self):
        return self.call("getblockchaininfo")

    def get_best_block_hash(self):
        return "00" * 32

    def with_timeout(self, _t):
        return self


import random  # noqa: E402


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
                   curtime=CURTIME, mintime=1, prevhash=None):
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
        "previousblockhash": (prevhash or rng.randbytes(32).hex()),
        "transactions": txs,
        "coinbaseaux": {"flags": flags},
        "coinbasevalue": coinbase_subsidy(height, 150) + total_fees,
        "target": "7fffff0000000000000000000000000000000000000000"
                  "000000000000000000",
        "mintime": mintime, "curtime": curtime,
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


def serve_outcome(cached, base, mut):
    """Prepare base, then try a sibling serve of mut under the
    base entry. Returns (sibling_raised, prepares_delta)."""
    base_prep, _ = cached.prepare_template(base)
    before = cached.template_cache.prepares
    raised = False
    try:
        base_prep.build(0, template=mut, now=NOW)
    except TemplateError:
        raised = True
    return raised


# ---------------------------------------------------------------------
# Section A: cache adversarial cases beyond the EXP-025 set
# ---------------------------------------------------------------------

def section_a(rng):
    stub, cached, uncached = make_engines()
    base = synth_template(rng, 10, segwit_fraction=0.5,
                          with_commitment=True)
    stub.template = base
    base_prep, _ = cached.prepare_template(base)

    def check_new_identity(name, mut):
        raised = serve_outcome(cached, base, mut)
        assert raised, f"{name}: sibling serve did not raise"
        want = uncached.build_candidate_uncached(mut, 0)
        before = cached.template_cache.prepares
        got = cached.build_candidate(mut, 0)
        assert cached.template_cache.prepares == before + 1, name
        assert same_output(got, want), name
        print(f"ok A {name}: sibling refused, new entry, "
              f"byte-identical to uncached")

    def check_same_identity(name, mut, expect_same_bytes=True):
        raised = serve_outcome(cached, base, mut)
        assert not raised, f"{name}: sibling serve raised"
        before = cached.template_cache.prepares
        got = cached.build_candidate(mut, 0)
        assert cached.template_cache.prepares == before, name
        want = uncached.build_candidate_uncached(mut, 0)
        assert same_output(got, want), name
        if expect_same_bytes:
            base_out = uncached.build_candidate_uncached(base, 0)
            assert same_output(got, base_out), name
        print(f"ok A {name}: served under the same identity, "
              f"byte-identical to uncached")

    # A1: height changes alone (subsidy equal at 1000 and 1001
    # on the regtest interval, so coinbasevalue is untouched;
    # only the height in the coinbase layer key and the BIP34
    # push move). Not in the EXP-025 case list.
    mut = copy.deepcopy(base)
    mut["height"] = base["height"] + 1
    assert mut["coinbasevalue"] == base["coinbasevalue"]
    check_new_identity("height_only_change", mut)

    # A2: mintime is a per-build input, not keyed. Raising
    # mintime to curtime moves the header time to mintime + 1
    # under the SAME identity, and the cached serve tracks the
    # uncached path exactly.
    mut = copy.deepcopy(base)
    mut["mintime"] = base["curtime"]
    raised = serve_outcome(cached, base, mut)
    assert not raised
    before = cached.template_cache.prepares
    got = cached.build_candidate(mut, 0)
    assert cached.template_cache.prepares == before
    want = uncached.build_candidate_uncached(mut, 0)
    assert same_output(got, want)
    base_out = uncached.build_candidate_uncached(base, 0)
    assert got["header"][:68] == base_out["header"][:68]
    assert got["header"][72:] == base_out["header"][72:]
    assert struct.unpack("<I", got["header"][68:72])[0] == \
        base["curtime"] + 1
    assert struct.unpack("<I", base_out["header"][68:72])[0] == \
        base["curtime"]
    print("ok A mintime_per_build_input: same identity, header "
          "time follows mintime on both paths")

    # A3: a default_witness_commitment field appearing on a
    # template with NO witness transactions. Nothing cached
    # depends on it (no commitment is computed), yet the field
    # string is keyed, so the identity changes while every
    # output byte stays the same: over-keying, safe direction.
    stub3, cached3, uncached3 = make_engines()
    base3 = synth_template(rng, 5, segwit_fraction=0.0)
    stub3.template = base3
    prep3, _ = cached3.prepare_template(base3)
    mut3 = copy.deepcopy(base3)
    mut3["default_witness_commitment"] = "6a24aa21a9ed" + "ab" * 32
    raised = False
    try:
        prep3.build(0, template=mut3, now=NOW)
    except TemplateError:
        raised = True
    assert raised
    got3 = cached3.build_candidate(mut3, 0)
    want3 = uncached3.build_candidate_uncached(mut3, 0)
    base3_out = uncached3.build_candidate_uncached(base3, 0)
    assert same_output(got3, want3) and same_output(got3, base3_out)
    print("ok A dwc_field_on_witnessless_template: new identity, "
          "identical bytes (safe over-keying)")

    # A4: the witness commitment cross-check is a substring
    # check (mirrored exactly from the uncached path): a dwc
    # string that still CONTAINS the correct commitment passes
    # validation on both paths, and because the full string is
    # keyed it prepares a fresh entry rather than serving.
    mut = copy.deepcopy(base)
    mut["default_witness_commitment"] = \
        base["default_witness_commitment"] + "00"
    check_new_identity("dwc_string_padded_still_contains", mut)

    # A5: the header layer keys the target STRING, not the
    # decoded integer. A case-only change to the target hex
    # changes the identity but no output byte: over-keying,
    # safe direction.
    mut = copy.deepcopy(base)
    mut["target"] = base["target"].upper()
    assert int(mut["target"], 16) == int(base["target"], 16)
    raised = serve_outcome(cached, base, mut)
    assert raised
    got = cached.build_candidate(mut, 0)
    want = uncached.build_candidate_uncached(mut, 0)
    base_out = uncached.build_candidate_uncached(base, 0)
    assert same_output(got, want) and same_output(got, base_out)
    print("ok A target_string_case: new identity, identical "
          "bytes (representation keyed, safe over-keying)")

    # A6: fields Core returns that the construction never reads
    # (per-tx weight, template longpollid and friends) are not
    # keyed and not used: same identity, same bytes. This is
    # the real-world robustness case: Core may add fields.
    mut = copy.deepcopy(base)
    for tx in mut["transactions"]:
        tx["weight"] = 1234
        tx["vsize"] = 250
        tx["depends"] = []
    mut["longpollid"] = "deadbeef"
    mut["capabilities"] = ["proposal"]
    check_same_identity("unmodelled_core_fields_ignored", mut)

    # A7: coinbaseaux missing entirely behaves as flags "" on
    # both paths and under the same identity.
    mut = copy.deepcopy(base)
    del mut["coinbaseaux"]
    check_same_identity("coinbaseaux_missing", mut)

    # A8: cache bound. 130 distinct templates through a fresh
    # cache capped at 128: size never exceeds the cap, eviction
    # is oldest-first, an evicted identity re-prepares (miss),
    # a resident one hits, and a PreparedTemplate object held
    # by the caller survives eviction of its entry and still
    # builds byte-identical candidates (the mine_cycle steps
    # shape holds the object, not the dict entry).
    stub8 = StubRPC()
    eng8 = MiningEngine(stub8, PAYOUT, compute=object())
    fam = eng8.cache_family()
    cache = TemplateCache()
    assert cache.max_entries == 128
    templates = []
    for i in range(130):
        t = synth_template(rng, 2, prevhash=f"{i:064x}")
        templates.append(t)
        cache.get(fam, t)
    assert len(cache.by_identity) == 128, len(cache.by_identity)
    assert cache.prepares == 130
    _p, hit = cache.get(fam, templates[129])
    assert hit, "newest entry must be resident"
    _p, hit = cache.get(fam, templates[2])
    assert hit, "third-oldest entry must still be resident"
    _p, hit = cache.get(fam, templates[0])
    assert not hit, "oldest entry must have been evicted (miss)"
    _p, hit = cache.get(fam, templates[2])
    assert not hit, "reinserting the evicted oldest entry must " \
                    "evict the next-oldest in turn"
    held_prep, _ = cache.get(fam, templates[50])
    for i in range(200):
        t = synth_template(rng, 2, prevhash=f"{1000 + i:064x}")
        cache.get(fam, t)
    assert len(cache.by_identity) == 128
    want = eng8.build_candidate_uncached(templates[50], 9)
    got = held_prep.build(9, now=NOW)
    assert same_output(got, want)
    print("ok A cache_bound: cap 128 held over 330 prepares, "
          "oldest-first eviction, held entry survives eviction "
          "and stays byte-identical")

    # A9: the held-object mutation boundary, pinned with
    # evidence (the EXP-025 audit note N-2 boundary, verified
    # independently here). The steps path reads version,
    # previousblockhash, bits, mintime and curtime from the
    # held template object at build time, and everything else
    # (merkle levels, tx bytes, coinbase inputs, target) from
    # the verified prepare. Mutating the held dict in place
    # therefore moves exactly those five header inputs and
    # nothing else. No production caller mutates the object
    # (mine_cycle takes it fresh from the RPC and holds it
    # privately), so this is a documented trust boundary, not
    # a live defect; the report recommends snapshotting the
    # three identity-keyed header fields at prepare time.
    stub9, cached9, uncached9 = make_engines()
    held = synth_template(rng, 6, segwit_fraction=0.5,
                          with_commitment=True)
    stub9.template = held
    prep9, _ = cached9.prepare_template(held)
    ref = prep9.build(4, now=NOW)
    held["version"] = 0x20000002
    out = prep9.build(4, now=NOW)
    assert out["header"][:4] == struct.pack("<i", 0x20000002)
    assert out["header"][4:] == ref["header"][4:]
    assert out["body"] == ref["body"]
    held["version"] = 0x20000000
    orig_prev = held["previousblockhash"]
    new_prev = rng.randbytes(32).hex()
    held["previousblockhash"] = new_prev
    out = prep9.build(4, now=NOW)
    assert out["header"][4:36] == bytes.fromhex(new_prev)[::-1]
    assert out["header"][36:] == ref["header"][36:]
    held["previousblockhash"] = orig_prev
    held["bits"] = "207fff00"
    out = prep9.build(4, now=NOW)
    assert out["header"][72:76] == bytes.fromhex("207fff00")[::-1]
    held["bits"] = "207fffff"
    raw0 = bytearray(bytes.fromhex(held["transactions"][0]["data"]))
    raw0[10] ^= 0xFF
    held["transactions"][0]["data"] = bytes(raw0).hex()
    out = prep9.build(4, now=NOW)
    assert out["header"] == ref["header"] and out["body"] == ref["body"]
    print("ok A held_object_mutation_boundary: version, prevhash "
          "and bits follow an in-place mutation of the held "
          "template; tx mutation does not move root or body "
          "(documented trust boundary, see report)")

    # A10: extranonce stepping anatomy. Consecutive steps of a
    # prepared entry differ only through the coinbase: header
    # version, prevhash, time and bits are identical, the
    # merkle root moves, and the body tail (the template
    # transactions verbatim) is shared.
    stub10, cached10, _u = make_engines()
    t10 = synth_template(rng, 8, segwit_fraction=0.5,
                         with_commitment=True)
    stub10.template = t10
    prep10, _ = cached10.prepare_template(t10)
    b7 = prep10.build(7, now=NOW)
    b8 = prep10.build(8, now=NOW)
    assert b7["header"][:36] == b8["header"][:36]
    assert b7["header"][68:] == b8["header"][68:]
    assert b7["header"][36:68] != b8["header"][36:68]
    tail = prep10.body_tail
    assert b7["body"].endswith(tail) and b8["body"].endswith(tail)
    assert b7["body"] != b8["body"]
    print("ok A extranonce_stepping_anatomy: steps differ only "
          "via the coinbase and its merkle root")

    # A11: an equal-content sibling (a deep copy, a different
    # object) is served at the prepared level with no raise
    # and no new prepare.
    before = cached.template_cache.prepares
    out = base_prep.build(3, template=copy.deepcopy(base), now=NOW)
    want = uncached.build_candidate_uncached(base, 3)
    assert same_output(out, want)
    assert cached.template_cache.prepares == before
    print("ok A equal_content_sibling_served: deep-copy sibling "
          "serves under the prepared identity")


# ---------------------------------------------------------------------
# Section C: extranonce space separation
# ---------------------------------------------------------------------

def coinbase_scriptsig(body):
    """Extract the coinbase scriptSig from a built block body:
    varint tx count, then the coinbase (version, one input with
    a null prevout, scriptSig, sequence, outputs, locktime)."""
    pos = 0
    first = body[pos]
    pos += 1 if first < 0xFD else 3  # these bodies are small
    pos += 4  # coinbase version
    if body[pos:pos + 2] == b"\x00\x01":
        pos += 2  # segwit marker and flag on the full coinbase
    assert body[pos] == 1  # one input
    pos += 1 + 32 + 4  # prevout hash and index
    slen = body[pos]
    pos += 1
    return body[pos:pos + slen]


def height_push(height):
    from mining.engine import script_num_push
    return script_num_push(height)


class RecordingCompute:
    """Compute stub: records every header it is asked to scan
    and never finds a hit, so mine_cycle walks its full round
    structure deterministically."""

    backend = "recording-stub"

    def __init__(self):
        self.headers = []

    def search_first_counted(self, header, target, start, count):
        self.headers.append(header)
        return None, count, 0.0


def section_c(rng):
    stub, cached, uncached = make_engines()
    base = synth_template(rng, 10, segwit_fraction=0.5,
                          with_commitment=True)
    stub.template = base

    # C1: THE COLLISION, proven byte for byte. Two independent
    # MiningEngine instances (separate caches, separate
    # families) with the same payout address, fed the same
    # template, build byte-identical candidates at every one
    # of the 64 extranonce rounds mine_cycle steps. Same
    # coinbase, same header, same nonce scan order: two such
    # engines running at once duplicate each other's work
    # exactly, hash for hash.
    eng_a = MiningEngine(stub, PAYOUT, compute=object())
    eng_b = MiningEngine(stub, PAYOUT, compute=object())
    for en in range(64):
        out_a = eng_a.build_candidate(base, en)
        out_b = eng_b.build_candidate(base, en)
        assert same_output(out_a, out_b), en
    print("ok C1 two_engine_collision: two MiningEngine "
          "instances with the same payout build byte-identical "
          "candidates at all 64 extranonce rounds")

    # C2: the ONLY separation the GBT path has today is the
    # payout script. A different payout address changes the
    # coinbase, so the candidate spaces separate.
    eng_c = MiningEngine(stub, PAYOUT2, compute=object())
    out_a = eng_a.build_candidate(base, 0)
    out_c = eng_c.build_candidate(base, 0)
    assert out_a["body"] != out_c["body"]
    assert out_a["header"] != out_c["header"]
    print("ok C2 separation_by_payout_only: a different payout "
          "address separates the spaces; nothing else does")

    # C3: engine versus solo server coinbase anatomy. The
    # engine coinbase scriptSig is height push + "/BAL/" + the
    # 4-byte extranonce. The solo coinbase scriptSig is height
    # push + "/BAL/" + extranonce1 (4 bytes) + extranonce2
    # (4 bytes): with the template flags empty the lengths
    # differ by 4, so no solo coinbase can equal any engine
    # coinbase, for any extranonce values. (With a 4-byte
    # coinbaseaux flags string the lengths coincide; the
    # report records that theoretical edge.) Also pinned: the
    # solo server's configured tag (default b"/BAL-solo/") is
    # never written into the coinbase it builds; the coinbase
    # carries the engine builder's "/BAL/" marker.
    from mining.solo_server import SoloServer
    solo = SoloServer(stub, PAYOUT, share_difficulty=0.01)
    job = solo.refresh_job()
    en1 = b"\x01\x00\x00\x00"
    ntime_hex = f"{base['curtime']:08x}"
    res, err = solo.validate_share(job, en1, "00000007",
                                   ntime_hex, "00000000")
    assert err is None, err
    # validate_share returns the bare (stripped) coinbase;
    # parse its scriptSig directly:
    cb = res["coinbase"]
    pos = 4 + 1 + 32 + 4
    slen = cb[pos]
    solo_script = cb[pos + 1:pos + 1 + slen]
    expect_solo = height_push(base["height"]) + b"/BAL/" + \
        en1 + bytes.fromhex("00000007")
    assert solo_script == expect_solo, solo_script
    assert b"/BAL-solo/" not in cb
    eng_out = eng_a.build_candidate(base, 7)
    eng_script = coinbase_scriptsig(eng_out["body"])
    expect_eng = height_push(base["height"]) + b"/BAL/" + \
        struct.pack("<I", 7)
    assert eng_script == expect_eng, eng_script
    assert len(solo_script) - len(eng_script) == 4
    print("ok C3 engine_vs_solo_anatomy: engine scriptSig is "
          "height + /BAL/ + en4; solo scriptSig is height + "
          "/BAL/ + en1 + en2 (4 bytes longer, no collision "
          "with empty flags); the solo tag /BAL-solo/ never "
          "enters the coinbase")

    # C4: the EXP-034 fix. Engines constructed with disjoint
    # extranonce_space values build disjoint candidate sets,
    # their union is the default engine's set, the default is
    # unchanged, and mine_cycle actually steps the configured
    # rounds (observed through the headers a recording compute
    # backend is asked to scan).
    eng_lo = MiningEngine(stub, PAYOUT, compute=object(),
                          extranonce_space=(0, 32))
    eng_hi = MiningEngine(stub, PAYOUT, compute=object(),
                          extranonce_space=(32, 32))
    assert cached.extranonce_space == (0, 64)
    bodies_lo = {eng_lo.build_candidate(base, en)["body"]
                 for en in range(0, 32)}
    bodies_hi = {eng_hi.build_candidate(base, en)["body"]
                 for en in range(32, 64)}
    bodies_all = {cached.build_candidate(base, en)["body"]
                  for en in range(64)}
    assert not (bodies_lo & bodies_hi)
    assert bodies_lo | bodies_hi == bodies_all
    try:
        MiningEngine(stub, PAYOUT, compute=object(),
                     extranonce_space=(2 ** 32 - 1, 2))
        raise AssertionError("out-of-range space accepted")
    except ValueError:
        pass
    root_to_en = {}
    for en in range(128):
        out = uncached.build_candidate_uncached(base, en)
        root_to_en[out["header"][36:68]] = en
    for space, want_ens in (((32, 32), [32, 33, 34]),
                            ((0, 64), [0, 1])):
        rec = RecordingCompute()
        eng = MiningEngine(stub, PAYOUT, compute=rec,
                           batch_size=1 << 32,
                           extranonce_space=space)
        out = eng.mine_cycle(max_batches=len(want_ens),
                             deadline_seconds=120)
        assert out["reason"] == "budget exhausted", out
        got_ens = [root_to_en[h[36:68]] for h in rec.headers]
        assert got_ens == want_ens, (space, got_ens)
    print("ok C4 extranonce_space_fix: configured spaces are "
          "disjoint, union equals the default space, default "
          "is (0, 64), mine_cycle steps exactly the configured "
          "rounds, out-of-range spaces are refused")


# ---------------------------------------------------------------------
# Section D: template freshness
# ---------------------------------------------------------------------

class FakeNodeRPC:
    """Mutable fake node for the JobRefresher: the tip hash and
    the template it serves can be moved by the test."""

    def __init__(self, rng):
        self.rng = rng
        self.tip = rng.randbytes(32).hex()
        self.seq = 0

    def call(self, method, *args):
        if method == "getblockchaininfo":
            return {"chain": "regtest", "blocks": 500,
                    "headers": 500, "initialblockdownload": False,
                    "bestblockhash": self.tip}
        if method == "getblocktemplate":
            self.seq += 1
            return synth_template(self.rng, 3, height=501,
                                  prevhash=self.tip)
        if method == "validateaddress":
            return {"isvalid": True, "scriptPubKey": SPK}
        raise ValueError(method)

    def get_blockchain_info(self):
        return self.call("getblockchaininfo")


def wait_for(cond, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return True
        time.sleep(0.02)
    return cond()


def section_d(rng):
    from mining.solo_server import JobRefresher, SoloServer

    # D1: JobRefresher keys new-work detection on the node's
    # best block hash (the template's prevhash versus the tip),
    # NOT on ntime: the Phase A weakness W4 pattern (ntime-only
    # detection) is not present here. A tip move triggers a
    # refresh on the next poll; mere passage of time does not
    # (until the 120 s style age cap, exercised here with a
    # shortened cap); and a refresh REPLACES the job table
    # wholesale, so shares for a superseded job are rejected
    # as unknown (cancellation semantics).
    fake = FakeNodeRPC(rng)
    solo = SoloServer(fake, PAYOUT, share_difficulty=0.01)
    seen = []
    refr = JobRefresher(solo, seen.append, poll_s=0.05,
                        max_age_s=1000.0, log=lambda *a: None)
    refr.start()
    try:
        assert wait_for(lambda: len(seen) >= 1)
        first_job_id = seen[0]["job_id"]
        assert solo.current["template"]["previousblockhash"] \
            == fake.tip
        time.sleep(0.4)
        assert len(seen) == 1, "refresh with an unmoved tip " \
                               "and a young job"
        fake.tip = rng.randbytes(32).hex()
        assert wait_for(lambda: len(seen) >= 2)
        assert seen[1]["template"]["previousblockhash"] == fake.tip
        refr.max_age_s = 0.2
        assert wait_for(lambda: len(seen) >= 3), \
            "age cap must refresh even with an unmoved tip"
    finally:
        refr.stop()
    out = solo.submit_share(first_job_id, b"\x01\x00\x00\x00",
                            "00000000", "00000000", "00000000",
                            worker="exp034")
    assert out == {"accepted": False, "reason": "unknown job"}, out
    print("ok D1 job_refresher: tip-hash keyed refresh, no "
          "refresh on time alone, age cap refreshes, superseded "
          "job ids are cancelled (unknown job)")

    # D2: MiningEngine freshness granularity is the cycle.
    # get_template is fetched once per mine_cycle; a new block
    # arriving mid-cycle does NOT invalidate the work in
    # flight (the compute stub flips the stub template after
    # the first batch and every later header still carries the
    # old prevhash), the next cycle picks the new template up,
    # and the header version is never rolled inside a cycle.
    # The stale window is bounded by the cycle budget
    # (max_batches and deadline_seconds).
    stub2 = StubRPC()
    tmpl_a = synth_template(rng, 4, prevhash="aa" * 32)
    tmpl_b = synth_template(rng, 4, prevhash="bb" * 32)
    stub2.template = tmpl_a

    class FlippingCompute(RecordingCompute):
        def search_first_counted(self, header, target, start,
                                 count):
            self.headers.append(header)
            if len(self.headers) == 1:
                stub2.template = tmpl_b
            return None, count, 0.0

    flip = FlippingCompute()
    eng = MiningEngine(stub2, PAYOUT, compute=flip,
                       batch_size=1 << 32)
    out = eng.mine_cycle(max_batches=4, deadline_seconds=120)
    assert out["reason"] == "budget exhausted", out
    prev_a = bytes.fromhex("aa" * 32)[::-1]
    prev_b = bytes.fromhex("bb" * 32)[::-1]
    assert len(flip.headers) == 4
    assert all(h[4:36] == prev_a for h in flip.headers)
    versions = {h[:4] for h in flip.headers}
    assert versions == {struct.pack("<i", tmpl_a["version"])}
    flip2 = FlippingCompute()
    eng.compute = flip2
    out = eng.mine_cycle(max_batches=1, deadline_seconds=120)
    assert flip2.headers[0][4:36] == prev_b
    print("ok D2 engine_freshness: mid-cycle tip change does "
          "not invalidate in-flight work; the next cycle picks "
          "it up; version is never rolled inside a cycle")

    # D3: Stratum client freshness guards. New-tip detection
    # is prevhash-keyed, not ntime-keyed (the W4 comparison):
    # a notify for a NEW prevhash with an OLDER ntime is
    # accepted as new work, while a notify for the SAME
    # prevhash with an older ntime is rejected as a stale
    # echo, and an exact duplicate changes nothing.
    from mining.stratum_client import StratumClient

    class FakeEvidence:
        def __init__(self):
            self.events = []

        def log(self, event, **fields):
            self.events.append((event, fields))

    ev = FakeEvidence()
    client = StratumClient("127.0.0.1", 0, "u", "x", ev)
    now = int(time.time())

    def notify(job_id, prevhash, ntime):
        client._handle({"method": "mining.notify", "params": [
            job_id, prevhash, "00", "00", [], "20000000",
            "207fffff", f"{ntime:08x}", True]})

    p1, p2 = "aa" * 32, "bb" * 32
    notify("j1", p1, now - 10)
    assert client.job_generation == 1
    assert client.current_job["job_id"] == "j1"
    notify("j2", p1, now - 70)
    assert client.job_generation == 1
    assert client.current_job["job_id"] == "j1"
    assert any(e == "template_rejected" for e, _ in ev.events)
    notify("j3", p2, now - 130)
    assert client.job_generation == 2, client.job_generation
    assert client.current_job["job_id"] == "j3"
    notify("j3", p2, now - 130)
    assert client.job_generation == 2
    assert any(e == "template_duplicate" for e, _ in ev.events)
    print("ok D3 stratum_client_freshness: same-tip ntime "
          "regression rejected as stale echo; new prevhash "
          "with an older ntime accepted as new work; exact "
          "duplicate ignored")


# ---------------------------------------------------------------------
# Section B: job construction against Bitcoin Core (regtest)
# ---------------------------------------------------------------------

def wallet_rpc(rpc):
    if "bal-regtest" not in rpc.call("listwallets"):
        try:
            rpc.call("loadwallet", "bal-regtest")
        except Exception:
            rpc.call("createwallet", "bal-regtest")
    from node.rpc_client import BitcoinRPC
    return BitcoinRPC(wallet="bal-regtest")


def section_b():
    from mining.solo_server import SoloServer
    from mining.stratum_client import build_header
    from node import node_manager
    from node.rpc_client import BitcoinRPC

    node_manager.start()
    rpc = BitcoinRPC()
    wallet = wallet_rpc(rpc)
    payout = wallet.call("getnewaddress", "", "bech32")

    def fill_mempool(n, tag):
        dests = []
        for i in range(n):
            kind = "bech32" if i % 2 == 0 else "legacy"
            dests.append(wallet.call("getnewaddress", "", kind))
        for d in dests:
            wallet.call("sendtoaddress", d, 0.01)
        info = rpc.call("getmempoolinfo")
        assert info["size"] >= 3, info
        return dests

    # B1: solo server job construction on a multi-transaction
    # template. The merkle branch served to workers must
    # reproduce, through the worker-side header builder, the
    # exact merkle root the server computes from the full
    # transaction list; and a block found through the server
    # must be accepted by Core with that same root.
    fill_mempool(6, "solo")
    solo = SoloServer(rpc, payout, share_difficulty=0.01)
    job = solo.refresh_job()
    ntx = len(job["txids"])
    assert ntx >= 3, ntx
    assert len(job["branch"]) >= 2, len(job["branch"])
    t = job["template"]
    params = solo.notify_params(job)
    client_job = {"job_id": params[0], "prevhash": params[1],
                  "coinb1": params[2], "coinb2": params[3],
                  "merkle_branch": params[4],
                  "version": params[5], "nbits": params[6],
                  "ntime": params[7]}
    en1 = b"\x01\x00\x00\x00"
    en2_hex = "00000007"
    hdr_w, merkle_w, cb_w = build_header(
        client_job, en1.hex(), en2_hex, 0, "wordswap")
    res, err = solo.validate_share(job, en1, en2_hex,
                                   params[7], "00000000")
    assert err is None, err
    assert res["coinbase"] == cb_w
    assert res["header"] == hdr_w, "worker-built header and " \
                                   "server-built header disagree"
    assert res["header"][36:68] == merkle_w
    print(f"ok B1 solo_branch_vs_full_root: branch depth "
          f"{len(job['branch'])} over {ntx} template txs; "
          f"worker header byte-identical to server header")

    nonce = 0
    while True:
        res, err = solo.validate_share(
            job, en1, en2_hex, params[7], f"{nonce:08x}")
        assert err is None, err
        if res["value"] <= job["target"]:
            break
        nonce += 1
        assert nonce < 100000
    tip0 = rpc.get_block_count()
    out = solo.submit_share(job["job_id"], en1, en2_hex,
                            params[7], f"{nonce:08x}",
                            worker="exp034")
    assert out["accepted"] and out["block"]["accepted"], out
    assert out["block"]["chain_verified"], out["block"]
    assert rpc.get_block_count() == tip0 + 1
    assert rpc.get_best_block_hash() == out["block"]["hash"]
    blk = rpc.get_block(out["block"]["hash"], 1)
    assert blk["merkleroot"] == res["header"][36:68][::-1].hex()
    assert blk["tx"][1:] == [tx["txid"] for tx in t["transactions"]]
    print(f"ok B2 solo_block_vs_core: block at height "
          f"{out['block']['height']} accepted by Core; Core "
          f"merkleroot and tx order match the job construction")

    # B2: the GBT engine path on a fresh multi-transaction
    # template. Cached and uncached constructions agree on the
    # real template; the block the engine mines is checked
    # against Core's own record: merkle root, transaction
    # order, coinbase value, payout script and the witness
    # commitment output.
    fill_mempool(6, "engine")
    eng = MiningEngine(rpc, payout, batch_size=100_000)
    template = eng.get_template()
    assert len(template["transactions"]) >= 3
    got_c = eng.build_candidate(template, 3)
    got_u = eng.build_candidate_uncached(template, 3)
    assert same_output(got_c, got_u)
    tip0 = rpc.get_block_count()
    out = eng.mine_cycle(max_batches=2000, deadline_seconds=600)
    assert out["accepted"], out
    assert rpc.get_block_count() == tip0 + 1
    assert rpc.get_best_block_hash() == out["hash"]
    blk = rpc.get_block(out["hash"], 2)
    # Independent merkle check: rebuild the root from the
    # block's own coinbase txid plus the template txids and
    # compare with the root Core recorded for the block.
    cb_txid = bytes.fromhex(blk["tx"][0]["txid"])[::-1]
    tmpl_txids = [bytes.fromhex(tx["txid"])[::-1]
                  for tx in template["transactions"]]
    indep_root = merkle_root([cb_txid] + tmpl_txids)
    assert blk["merkleroot"] == indep_root[::-1].hex()
    assert [tx["txid"] for tx in blk["tx"][1:]] == \
        [tx["txid"] for tx in template["transactions"]]
    cb = blk["tx"][0]
    paid = round(cb["vout"][0]["value"] * 10 ** 8)
    assert paid == template["coinbasevalue"], (paid, template)
    spk = rpc.call("validateaddress", payout)["scriptPubKey"]
    assert cb["vout"][0]["scriptPubKey"]["hex"] == spk
    if template.get("default_witness_commitment"):
        scripts = [v["scriptPubKey"]["hex"] for v in cb["vout"]]
        assert template["default_witness_commitment"] in scripts
    print(f"ok B3 engine_block_vs_core: block at height "
          f"{out['height']} accepted; Core merkleroot, tx "
          f"order, coinbase value {paid} sats and payout "
          f"script all match the template construction "
          f"(cache prepares={eng.template_cache.prepares})")


def main():
    rng = random.Random(34034)
    section_a(rng)
    section_c(rng)
    section_d(rng)
    section_b()
    print("ALL EXP-034 JOB AND TEMPLATE TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
