#!/usr/bin/env python3
"""EXP-036 independent audit tests.

Written by the post-integration auditor, not the integration
author. These tests re-derive every expectation independently:
SHA-256d via hashlib directly, compact target decoding via a
from-Core-spec implementation local to this file, and solo
server behaviour against an independently written fake Core.
Run: python3 EXP036_AUDIT_TESTS.py [--regtest]
"""

import hashlib
import os
import random
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__),
                                "..", "..", ".."))

from mining.candidate_verify import (classify_submit_result,
                                     meets_target,
                                     verify_candidate,
                                     verify_chain_acceptance)
from mining.pow import dsha256
from mining.pow_engine import POW_LIMIT_MAINNET, POW_LIMIT_REGTEST
from mining.solo_server import SoloServer

DIFF1 = 0x00000000FFFF0000000000000000000000000000000000000000000000000000
PAYOUT = "bc1q528egeqsvv8aa382j43edxskqw6x7zxc2xpcf3"
FAILURES = []


def check(cond, label, detail=""):
    if cond:
        print(f"ok: {label}")
    else:
        print(f"FAIL: {label} {detail}")
        FAILURES.append(label)


def ref_dsha(b):
    return hashlib.sha256(hashlib.sha256(b).digest()).digest()


def my_decode(nbits):
    """Core SetCompact, reimplemented here from the spec."""
    size = nbits >> 24
    word = nbits & 0x007FFFFF
    negative = bool(word and (nbits & 0x00800000))
    if size <= 3:
        value = word >> (8 * (3 - size))
    else:
        value = word << (8 * (size - 3))
    overflow = bool(word and (size > 34 or (word > 0xFF and size > 33)
                           or (word > 0xFFFF and size > 32)))
    return value, negative, overflow


def my_encode(value):
    size = (value.bit_length() + 7) // 8
    if size <= 3:
        compact = (value & 0xFFFFFF) << (8 * (3 - size))
    else:
        compact = value >> (8 * (size - 3))
    if compact & 0x00800000:
        compact >>= 8
        size += 1
    return (size << 24) | (compact & 0x007FFFFF)


SANE_FAIL = ("negative-target", "overflow-target", "zero-target",
             "target-above-limit")


def expected(header, pow_limit, share_target=None):
    digest = ref_dsha(header)
    value = int.from_bytes(digest, "little")
    nbits = struct.unpack("<I", header[72:76])[0]
    target, neg, over = my_decode(nbits)
    if neg:
        reason = "negative-target"
    elif over:
        reason = "overflow-target"
    elif target == 0:
        reason = "zero-target"
    elif target > pow_limit:
        reason = "target-above-limit"
    elif value > target:
        reason = "high-hash"
    else:
        reason = "ok"
    sane = reason not in SANE_FAIL
    meets_net = reason == "ok"
    meets_share = bool(sane and share_target is not None
                       and value <= share_target)
    if not sane:
        cls = "invalid"
    elif meets_net:
        cls = "block_candidate"
    elif meets_share:
        cls = "share"
    else:
        cls = "below_target"
    return {"classification": cls, "reason": reason, "digest": digest,
            "value": value, "target": target,
            "meets_network_target": meets_net,
            "meets_share_target": meets_share,
            "valid_header": sane}


# ------------------------------------------------------------ differentials

def test_differentials():
    rng = random.Random(36036)
    bits_pool = [0x207FFFFF, 0x1D00FFFF, 0x1F010000, 0x20100000,
                 0x21008000, 0x1D000000, 0x01800001, 0x2300FFFF,
                 0x2200FFFF, 0x01120000, 0x0300FFFF, 0x20700000]
    counts = {"block_candidate": 0, "share": 0, "below_target": 0,
              "invalid": 0}
    n = 0
    for i in range(300):
        header = bytearray(rng.getrandbits(8) for _ in range(80))
        nbits = rng.choice(bits_pool)
        header[72:76] = struct.pack("<I", nbits)
        header = bytes(header)
        limit = rng.choice([POW_LIMIT_MAINNET, POW_LIMIT_REGTEST])
        share_target = rng.choice([None, (1 << 250), (1 << 230)])
        exp = expected(header, limit, share_target)
        got = verify_candidate(header, limit, share_target=share_target)
        n += 1
        counts[exp["classification"]] += 1
        for key in ("classification", "reason", "digest", "value",
                    "target", "meets_network_target",
                    "meets_share_target", "valid_header"):
            if got[key] != exp[key]:
                check(False, f"differential case {i} field {key}",
                      f"nbits={nbits:08x} got={got[key]!r} "
                      f"exp={exp[key]!r}")
                return
        if got["digest"] != got["digest_independent"]:
            check(False, f"differential case {i} digest disagreement")
            return
    check(True, f"differentials: {n} random headers match the "
                f"independent model on every field; class mix "
                f"{counts}")
    # header length handling
    v = verify_candidate(b"\x00" * 79, POW_LIMIT_MAINNET)
    check(v["classification"] == "invalid"
          and v["reason"] == "header-length",
          "79-byte header is invalid (header-length)")
    v = verify_candidate(b"\x00" * 81, POW_LIMIT_MAINNET)
    check(v["classification"] == "invalid"
          and v["reason"] == "header-length",
          "81-byte header is invalid (header-length)")


def test_boundary():
    for target in (DIFF1, POW_LIMIT_REGTEST, (1 << 240)):
        check(meets_target(target, target),
              f"boundary: value == target meets (target bits "
              f"{target.bit_length()})")
        check(not meets_target(target + 1, target),
              "boundary: value == target + 1 does not meet")
        # The float judgement cannot see this boundary at all:
        # both values round to the same double and their float
        # difficulties are the same double.
        check(float(target) == float(target + 1),
              "boundary: float64 conflates target and target + 1")
        check(DIFF1 / target == DIFF1 / (target + 1),
              "boundary: float difficulty of target and target + 1 "
              "is identical, exact compare still decides")


def test_compact_straddle():
    """nBits ladder around a winning header. Note the honest
    constraint: nBits is part of the hashed header, so changing
    nBits changes the hash; no fixed-hash straddle exists. What
    can be pinned is that for every rung of the ladder the
    verdict equals the independent model applied to the
    modified header (its own hash, its own decoded target).
    The exact equality boundary itself is pinned arithmetically
    in test_boundary."""
    rng = random.Random(777)
    base = bytearray(rng.getrandbits(8) for _ in range(80))
    target = 1 << 240
    base[72:76] = struct.pack("<I", my_encode(target))
    winner = None
    for nonce in range(300000):
        base[76:80] = struct.pack("<I", nonce)
        if int.from_bytes(ref_dsha(bytes(base)), "little") <= target:
            winner = bytes(base)
            break
    check(winner is not None, "straddle: found a winning header "
                              "at target 2^240")
    if winner is None:
        return
    value = int.from_bytes(ref_dsha(winner), "little")
    ladder = [my_encode(value), my_encode(value + (1 << 232)),
              my_encode(1 << 240), my_encode(1 << 248),
              my_encode((1 << 256) - 1), 0x207FFFFF, 0x1D00FFFF]
    allok = True
    for nbits in ladder:
        h = winner[:72] + struct.pack("<I", nbits) + winner[76:]
        exp = expected(h, POW_LIMIT_REGTEST)
        got = verify_candidate(h, POW_LIMIT_REGTEST)
        if (got["classification"] != exp["classification"]
                or got["target"] != exp["target"]
                or got["value"] != exp["value"]
                or got["meets_network_target"]
                != exp["meets_network_target"]):
            allok = False
            check(False, f"straddle rung {nbits:08x}",
                  f"got={got['classification']} "
                  f"exp={exp['classification']}")
    check(allok, "straddle: every nBits rung matches the "
                 "independent model on the modified header")


def test_mutation():
    rng = random.Random(4242)
    header = bytearray(rng.getrandbits(8) for _ in range(80))
    header[72:76] = struct.pack("<I", 0x207FFFFF)
    winner = None
    for nonce in range(1000):
        header[76:80] = struct.pack("<I", nonce)
        v = verify_candidate(bytes(header), POW_LIMIT_REGTEST)
        if v["classification"] == "block_candidate":
            winner = (bytes(header), v)
            break
    check(winner is not None, "mutation: found a regtest winner")
    if winner is None:
        return
    header, v = winner
    claimed = v["digest"]
    # Flip one bit in the merkle-root region (byte 40).
    mut = bytearray(header)
    mut[40] ^= 0x01
    vm = verify_candidate(bytes(mut), POW_LIMIT_REGTEST)
    check(vm["digest"] != claimed,
          "mutation: one flipped merkle bit changes the digest")
    # This is the exact predicate mining/mainnet_live.py applies
    # (digest == v[digest] and v[digests_agree]): a backend
    # digest claimed for the unmutated header cannot confirm
    # the mutated one.
    hash_match = (claimed == vm["digest"] and vm["digests_agree"])
    check(not hash_match,
          "mutation: pool confirmation predicate rejects a digest "
          "claimed for a different header")
    # Mutate only the nonce: same conclusion.
    mut2 = bytearray(header)
    mut2[79] ^= 0x01
    vm2 = verify_candidate(bytes(mut2), POW_LIMIT_REGTEST)
    check(vm2["digest"] != claimed,
          "mutation: one flipped nonce bit changes the digest")


def test_classify_extra():
    check(classify_submit_result("bad-diffbits") == "rejected",
          "classify: unknown reject string is rejected")
    check(classify_submit_result(0) == "rejected",
          "classify: non-string non-None result is rejected")
    check(classify_submit_result("duplicate") == "duplicate",
          "classify: duplicate")


# ------------------------------------------------------------ fake Core

class AuditRPCError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class AuditFakeRPC:
    """Independent fake Core. submit behaviour and chain state
    are controlled separately so a submission response and the
    chain can disagree, which is the whole point of step 12."""

    def __init__(self, chain="regtest", bits="207fffff",
                 submit="land", best_raises=False):
        self.chain = chain
        self.bits = bits
        self.submit = submit
        self.best_raises = best_raises
        self.best = "ef" * 32
        self.conf = {}
        self.submit_calls = []

    def call(self, method, *params):
        if method == "getblockchaininfo":
            return {"chain": self.chain, "blocks": 50, "headers": 50,
                    "initialblockdownload": False,
                    "bestblockhash": self.best}
        if method == "getblocktemplate":
            return {"height": 51, "coinbasevalue": 5000000000,
                    "previousblockhash": self.best, "bits": self.bits,
                    "curtime": 1700000000, "mintime": 1600000000,
                    "version": 0x20000000, "transactions": []}
        if method == "validateaddress":
            return {"isvalid": True, "scriptPubKey": "0014" + "33" * 20}
        if method == "submitblock":
            self.submit_calls.append(params[0])
            block_hash = dsha256(bytes.fromhex(params[0])[:80])[::-1].hex()
            if self.submit == "raise":
                raise RuntimeError("audit injected submit failure")
            if self.submit in ("land", "duplicate-landed"):
                self.best = block_hash
                self.conf[block_hash] = 1
                return None if self.submit == "land" else "duplicate"
            if self.submit == "orphan":
                return None
            if self.submit.startswith("reject:"):
                return self.submit[len("reject:"):]
            raise AssertionError(self.submit)
        if method == "getbestblockhash":
            if self.best_raises:
                raise RuntimeError("audit injected chain read failure")
            return self.best
        if method == "getblockheader":
            block_hash = params[0]
            if block_hash in self.conf:
                return {"hash": block_hash,
                        "confirmations": self.conf[block_hash]}
            raise AuditRPCError(-5, "Block not found")
        raise AssertionError(f"unexpected RPC {method}")


EN1 = b"\x02\x00\x00\x00"
EN2 = "00000007"


def find_winning(solo, job, target):
    t = job["template"]
    ntime = f"{t['curtime']:08x}"
    for nonce in range(2000000):
        res, err = solo.validate_share(job, EN1, EN2, ntime,
                                       f"{nonce:08x}")
        assert err is None, err
        if res["value"] <= target:
            return nonce, ntime
    raise AssertionError("no winning nonce")


def make(submit="land", chain="regtest", bits="207fffff",
         share_difficulty=0.01, best_raises=False):
    rpc = AuditFakeRPC(chain=chain, bits=bits, submit=submit,
                       best_raises=best_raises)
    solo = SoloServer(rpc, PAYOUT, share_difficulty=share_difficulty,
                      expected_chain=chain)
    job = solo.refresh_job()
    return rpc, solo, job


def test_solo_land_and_duplicate():
    rpc, solo, job = make("land")
    nonce, ntime = find_winning(solo, job, job["target"])
    out = solo.submit_share(job["job_id"], EN1, EN2, ntime,
                            f"{nonce:08x}", worker="aud")
    rec = out["block"]
    check(out["accepted"] and rec["accepted"] is True
          and rec["chain_status"] == "tip"
          and rec["submit_classification"] == "accepted",
          "solo land: block accepted only with chain confirmation")
    check(solo.stats()["workers"]["aud"]["blocks"] == 1,
          "solo land: worker block count 1")

    rpc, solo, job = make("duplicate-landed")
    nonce, ntime = find_winning(solo, job, job["target"])
    out = solo.submit_share(job["job_id"], EN1, EN2, ntime,
                            f"{nonce:08x}", worker="aud")
    rec = out["block"]
    check(rec["accepted"] is True
          and rec["submit_classification"] == "duplicate"
          and rec["submit_result"] == "duplicate",
          "solo duplicate: already-known block confirmed in chain "
          "counts, verbatim kept")


def test_solo_none_without_chain():
    rpc, solo, job = make("orphan")
    nonce, ntime = find_winning(solo, job, job["target"])
    out = solo.submit_share(job["job_id"], EN1, EN2, ntime,
                            f"{nonce:08x}", worker="aud")
    rec = out["block"]
    check(rec["submit_result"] is None and rec["accepted"] is False
          and rec["chain_verified"] is False
          and rec["chain_status"] == "not-in-chain",
          "solo orphan: submitblock None without chain entry is "
          "NOT accepted")
    st = solo.stats()
    check(st["workers"]["aud"]["blocks"] == 0
          and st["blocks_found"] == 1,
          "solo orphan: no block counted, record kept")


def test_solo_rejections_and_rpc_failures():
    for s in ("inconclusive", "high-hash", "duplicate-invalid"):
        rpc, solo, job = make(f"reject:{s}")
        nonce, ntime = find_winning(solo, job, job["target"])
        out = solo.submit_share(job["job_id"], EN1, EN2, ntime,
                                f"{nonce:08x}", worker="aud")
        rec = out["block"]
        exp_cls = ("inconclusive" if s == "inconclusive"
                   else "duplicate-invalid" if s == "duplicate-invalid"
                   else "rejected")
        check(rec["accepted"] is False
              and rec["submit_result"] == s
              and rec["submit_classification"] == exp_cls,
              f"solo reject {s}: verbatim kept, not accepted")

    rpc, solo, job = make("raise")
    nonce, ntime = find_winning(solo, job, job["target"])
    out = solo.submit_share(job["job_id"], EN1, EN2, ntime,
                            f"{nonce:08x}", worker="aud")
    rec = out["block"]
    check(rec["accepted"] is False
          and rec["submit_classification"] == "rpc-error"
          and rec["chain_status"] == "unknown"
          and solo.blocks_found[-1]["hash"] == rec["hash"],
          "solo RPC raise on submit: record preserved, no block")

    # The block lands at submitblock, but the chain read itself
    # fails: acceptance must stay unproven, record preserved.
    rpc, solo, job = make("land", best_raises=True)
    nonce, ntime = find_winning(solo, job, job["target"])
    out = solo.submit_share(job["job_id"], EN1, EN2, ntime,
                            f"{nonce:08x}", worker="aud")
    rec = out["block"]
    check(rec["accepted"] is False
          and rec["chain_status"] == "unknown"
          and solo.blocks_found[-1]["hash"] == rec["hash"]
          and solo.stats()["workers"]["aud"]["blocks"] == 0,
          "solo RPC raise on chain read: landed block still not "
          "claimed, record preserved")


def test_solo_invalid_encodings_never_submitted():
    # overflow, a different encoding than the author's test used
    rpc, solo, job = make("land")
    job["template"] = dict(job["template"], bits="2200ffff")
    job["target"] = my_decode(0x2200FFFF)[0]
    nonce, ntime = find_winning(solo, job, job["target"])
    out = solo.submit_share(job["job_id"], EN1, EN2, ntime,
                            f"{nonce:08x}", worker="aud")
    check(not out["accepted"] and "overflow-target" in out["reason"]
          and rpc.submit_calls == []
          and solo.candidates_rejected[0]["reason"]
          == "overflow-target",
          "solo overflow 0x2200ffff: rejected, zero submitblock "
          "calls")

    # zero target
    rpc, solo, job = make("land", chain="main", bits="1d000000",
                          share_difficulty=1e-6)
    nonce, ntime = find_winning(solo, job, solo.share_target)
    out = solo.submit_share(job["job_id"], EN1, EN2, ntime,
                            f"{nonce:08x}", worker="aud")
    check(not out["accepted"] and "zero-target" in out["reason"]
          and rpc.submit_calls == [],
          "solo zero target: rejected, zero submitblock calls")

    # negative target
    rpc, solo, job = make("land", chain="main", bits="01800001",
                          share_difficulty=1e-6)
    nonce, ntime = find_winning(solo, job, solo.share_target)
    out = solo.submit_share(job["job_id"], EN1, EN2, ntime,
                            f"{nonce:08x}", worker="aud")
    check(not out["accepted"] and "negative-target" in out["reason"]
          and rpc.submit_calls == [],
          "solo negative target: rejected, zero submitblock calls")

    # inflated recorded job target cannot override the header's
    # own exact nBits (the recorded target is tampered, the
    # header is honest regtest)
    rpc, solo, job = make("land")
    real_target = job["target"]
    job["target"] = (1 << 256) - 1
    nonce, ntime = find_winning(solo, job, real_target)
    out = solo.submit_share(job["job_id"], EN1, EN2, ntime,
                            f"{nonce:08x}", worker="aud")
    check(not out["accepted"]
          and "header-target-mismatch" in out["reason"]
          and rpc.submit_calls == [],
          "solo inflated job target: exact header nBits decides, "
          "candidate rejected, zero submitblock calls")


def test_share_is_not_a_block():
    """A candidate meeting the server share target (derived
    through a float difficulty) but failing the exact nBits
    network check is accepted as a share only: no submission,
    no block record, no block count."""
    rpc, solo, job = make("land", chain="main", bits="1d00ffff",
                          share_difficulty=1e-6)
    # find a nonce above the network target, at or below the
    # share target
    t = job["template"]
    ntime = f"{t['curtime']:08x}"
    chosen = None
    for nonce in range(2000000):
        res, err = solo.validate_share(job, EN1, EN2, ntime,
                                       f"{nonce:08x}")
        assert err is None, err
        if job["target"] < res["value"] <= solo.share_target:
            chosen = nonce
            break
    check(chosen is not None, "share case: found a share-only "
                              "nonce")
    if chosen is None:
        return
    out = solo.submit_share(job["job_id"], EN1, EN2, ntime,
                            f"{chosen:08x}", worker="aud")
    st = solo.stats()
    check(out["accepted"] and out["block"] is None
          and rpc.submit_calls == [] and solo.blocks_found == []
          and st["workers"]["aud"]["blocks"] == 0
          and st["workers"]["aud"]["accepted"] == 1,
          "share case: share accepted, never submitted as a "
          "block, never counted as one")


class StubRPC:
    def __init__(self, best=None, conf=None, best_exc=None,
                 header_exc=None):
        self.best = best
        self.conf = conf
        self.best_exc = best_exc
        self.header_exc = header_exc

    def call(self, method, *params):
        if method == "getbestblockhash":
            if self.best_exc:
                raise self.best_exc
            return self.best
        if method == "getblockheader":
            if self.header_exc:
                raise self.header_exc
            return {"confirmations": self.conf}
        raise AssertionError(method)


def test_chain_acceptance_unit():
    h = "ab" * 32
    check(verify_chain_acceptance(StubRPC(best=h), h)
          == ("tip", True), "chain: tip")
    check(verify_chain_acceptance(StubRPC(best="cd" * 32, conf=5), h)
          == ("in-chain", True), "chain: in-chain with descendants")
    check(verify_chain_acceptance(StubRPC(best="cd" * 32, conf=-1), h)
          == ("not-in-chain", False), "chain: fork block rejected")
    check(verify_chain_acceptance(StubRPC(best="cd" * 32, conf=0), h)
          == ("not-in-chain", False),
          "chain: zero confirmations rejected")
    err = AuditRPCError(-5, "Block not found")
    check(verify_chain_acceptance(
        StubRPC(best="cd" * 32, header_exc=err), h)
        == ("not-in-chain", False), "chain: -5 is not-in-chain")
    err2 = AuditRPCError(-8, "something else")
    check(verify_chain_acceptance(
        StubRPC(best="cd" * 32, header_exc=err2), h)
        == ("unknown", False),
        "chain: non -5 header error is unknown, not accepted")
    check(verify_chain_acceptance(
        StubRPC(best_exc=RuntimeError("down")), h)
        == ("unknown", False),
        "chain: best-hash read failure is unknown, not accepted")


# ------------------------------------------------------------ regtest

def test_regtest():
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
    solo = SoloServer(rpc, payout, share_difficulty=0.01,
                      expected_chain="regtest")
    tip0 = rpc.get_block_count()
    best0 = rpc.get_best_block_hash()

    # Negative: overflow nBits job on the real node. Exact
    # verification must reject it before any submission and
    # the tip must not move.
    job = solo.refresh_job()
    job["template"] = dict(job["template"], bits="2300ffff")
    job["target"] = my_decode(0x2300FFFF)[0]
    nonce, ntime = find_winning(solo, job, job["target"])
    out = solo.submit_share(job["job_id"], EN1, EN2, ntime,
                            f"{nonce:08x}", worker="exp036-audit")
    check(not out["accepted"] and "overflow-target" in out["reason"]
          and solo.blocks_found == []
          and rpc.get_block_count() == tip0
          and rpc.get_best_block_hash() == best0,
          "regtest negative: overflow candidate rejected, no "
          "submission, tip unmoved")

    # Positive: a real block through the production solo path.
    job = solo.refresh_job()
    nonce, ntime = find_winning(solo, job, job["target"])
    out = solo.submit_share(job["job_id"], EN1, EN2, ntime,
                            f"{nonce:08x}", worker="exp036-audit")
    rec = out["block"]
    header = rpc.call("getblockheader", rec["hash"], True)
    check(out["accepted"] and rec["accepted"] is True
          and rec["chain_verified"] is True
          and rec["chain_status"] in ("tip", "in-chain")
          and rec["submit_result"] is None
          and header["confirmations"] >= 1
          and rpc.get_block_count() >= tip0 + 1,
          f"regtest positive: block chain-verified at height "
          f"{rec['height']}: {rec['hash']}")
    print(f"regtest evidence: height {rec['height']} hash "
          f"{rec['hash']} chain_status {rec['chain_status']} "
          f"confirmations {header['confirmations']}")


def main():
    test_differentials()
    test_boundary()
    test_compact_straddle()
    test_mutation()
    test_classify_extra()
    test_solo_land_and_duplicate()
    test_solo_none_without_chain()
    test_solo_rejections_and_rpc_failures()
    test_solo_invalid_encodings_never_submitted()
    test_share_is_not_a_block()
    test_chain_acceptance_unit()
    if "--regtest" in sys.argv:
        test_regtest()
    if FAILURES:
        print(f"AUDIT TESTS FAILED: {len(FAILURES)}: {FAILURES}")
        return 1
    print("ALL EXP-036 AUDIT TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
