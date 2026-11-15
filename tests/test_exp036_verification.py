#!/usr/bin/env python3
"""EXP-036 tests: exact candidate verification and block submission.

What is pinned here:

- The authoritative comparison is exact integer semantics
  (matrix M02). At the target boundary, value == target meets
  and value == target + 1 does not, even where float64 cannot
  tell the two values apart: the Qaxe floating-point judgement
  (matrix M03, weakness W1) would call them the same.
- verify_candidate classifies the genesis header as a block
  candidate, a mutated header as below target, and headers
  with negative, overflow or above-limit nBits as invalid.
- Solo server, against a fake Core: a network-target share is
  verified exactly, submitted once, and counted as a block
  only when chain state confirms it as the tip.
- Solo server negative: a candidate whose nBits is an
  overflow target is rejected by exact verification and
  submitblock is NEVER called, even though the job's recorded
  target was tampered to a value the fast compare would have
  accepted. A header/job target mismatch is likewise rejected
  before submission.
- Solo server honesty: submitblock returning None is no
  longer success on its own. When the block does not land in
  the active chain, when Core answers with a rejection string,
  and when the submission RPC itself fails, the record says
  so and the block is not counted.
- Regtest end to end against a real node: a block mined
  through the fixed solo path is chain-verified as the tip,
  and a low-difficulty share is rejected without any
  submission.
"""

import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mining.candidate_verify import (classify_submit_result,
                                     meets_target,
                                     pow_limit_for_chain,
                                     verify_candidate,
                                     verify_chain_acceptance)
from mining.pow import dsha256, target_from_nbits
from mining.pow_engine import (POW_LIMIT_MAINNET, POW_LIMIT_REGTEST,
                               compact_decode)
from mining.solo_server import SoloServer
from node import node_manager
from node.rpc_client import BitcoinRPC

PAYOUT = "bc1q528egeqsvv8aa382j43edxskqw6x7zxc2xpcf3"
TIP = "ab" * 32

GENESIS_HEADER = bytes.fromhex(
    "01000000"
    + "00" * 32
    + "3ba3edfd7a7b12b27ac72c3e67768f617fc81bc3888a51323a9fb8aa4b1e5e4a"
    + "29ab5f49" + "ffff001d" + "1dac2b7c")


def with_bits(header, nbits):
    return header[:72] + struct.pack("<I", nbits) + header[76:]


# ---------------------------------------------------------------- unit: M02/M03

def test_boundary_integer_semantics():
    target = target_from_nbits(0x1D00FFFF)
    # float64 cannot distinguish target from target + 1 at
    # this magnitude, and the float difficulty of the two
    # values is identical: a float judgement (M03) cannot
    # decide this boundary at all.
    assert float(target) == float(target + 1)
    assert target / target == target / (target + 1)
    # The exact integer compare (M02) decides it.
    assert meets_target(target, target)
    assert not meets_target(target + 1, target)
    assert meets_target(target - 1, target)
    print("ok: boundary semantics are exact-integer; the float "
          "judgement cannot distinguish target from target + 1")


def test_verify_candidate_classifications():
    v = verify_candidate(GENESIS_HEADER, POW_LIMIT_MAINNET)
    assert v["classification"] == "block_candidate", v
    assert v["digests_agree"] and v["meets_network_target"]
    assert v["reason"] == "ok"
    # Same header, nonce zeroed: a well-formed header whose
    # hash simply does not meet the target.
    bad = GENESIS_HEADER[:76] + b"\x00\x00\x00\x00"
    v = verify_candidate(bad, POW_LIMIT_MAINNET)
    assert v["classification"] == "below_target", v
    assert v["reason"] == "high-hash" and v["digests_agree"]
    assert v["valid_header"] and not v["meets_network_target"]
    # Share classification against a share target the mutated
    # header does meet (the maximal target).
    v = verify_candidate(bad, POW_LIMIT_MAINNET,
                         share_target=(1 << 256) - 1)
    assert v["classification"] == "share", v
    assert v["meets_share_target"] and not v["meets_network_target"]
    print("ok: genesis is a block candidate; mutated header is "
          "below target; share classification is separate")


def test_verify_candidate_invalid_targets():
    v = verify_candidate(with_bits(GENESIS_HEADER, 0x01800001),
                         POW_LIMIT_MAINNET)
    assert v["classification"] == "invalid", v
    assert v["reason"] == "negative-target", v
    v = verify_candidate(with_bits(GENESIS_HEADER, 0x2300FFFF),
                         POW_LIMIT_MAINNET)
    assert v["classification"] == "invalid", v
    assert v["reason"] == "overflow-target", v
    # Regtest bits are legal on regtest and above the limit on
    # mainnet: the same header must flip verdicts with the
    # chain's pow limit.
    regtest_header = with_bits(GENESIS_HEADER, 0x207FFFFF)
    v = verify_candidate(regtest_header, POW_LIMIT_MAINNET)
    assert v["classification"] == "invalid", v
    assert v["reason"] == "target-above-limit", v
    v = verify_candidate(regtest_header, POW_LIMIT_REGTEST)
    assert v["reason"] != "target-above-limit", v
    assert pow_limit_for_chain("regtest") == POW_LIMIT_REGTEST
    assert pow_limit_for_chain("main") == POW_LIMIT_MAINNET
    assert pow_limit_for_chain("no-such-chain") == POW_LIMIT_MAINNET
    print("ok: negative, overflow and above-limit targets are "
          "invalid; pow limits are per chain with a strict "
          "fallback")


def test_submit_result_classification():
    assert classify_submit_result(None) == "accepted"
    assert classify_submit_result("duplicate") == "duplicate"
    assert classify_submit_result(
        "duplicate-invalid") == "duplicate-invalid"
    assert classify_submit_result("inconclusive") == "inconclusive"
    assert classify_submit_result("high-hash") == "rejected"
    print("ok: submitblock responses classified, verbatim kept "
          "by the caller")


# ---------------------------------------------------------------- fake Core

class FakeRPCError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class FakeRPC:
    """The slice of Core the solo server talks to, with a
    controllable submitblock outcome and chain state."""

    def __init__(self, submit_mode="accept"):
        self.submit_mode = submit_mode
        self.submit_calls = []
        self.best = TIP
        self.in_chain = {}  # block hash -> confirmations

    def call(self, method, *params):
        if method == "getblockchaininfo":
            return {"chain": "regtest", "blocks": 100,
                    "headers": 100, "initialblockdownload": False,
                    "bestblockhash": self.best}
        if method == "getblocktemplate":
            return {"height": 101, "coinbasevalue": 5000000000,
                    "previousblockhash": self.best,
                    "bits": "207fffff",
                    "curtime": 1700000000, "mintime": 1600000000,
                    "version": 0x20000000, "transactions": []}
        if method == "validateaddress":
            return {"isvalid": True,
                    "scriptPubKey": "0014" + "22" * 20}
        if method == "submitblock":
            self.submit_calls.append(params[0])
            header = bytes.fromhex(params[0])[:80]
            block_hash = dsha256(header)[::-1].hex()
            if self.submit_mode == "accept":
                self.best = block_hash
                self.in_chain[block_hash] = 1
                return None
            if self.submit_mode == "orphan":
                return None  # node took it; it never lands
            if self.submit_mode == "reject-string":
                return "duplicate-invalid"
            if self.submit_mode == "raise":
                raise RuntimeError("connection reset")
            raise AssertionError(self.submit_mode)
        if method == "getbestblockhash":
            return self.best
        if method == "getblockheader":
            block_hash = params[0]
            if block_hash in self.in_chain:
                return {"hash": block_hash,
                        "confirmations": self.in_chain[block_hash]}
            raise FakeRPCError(-5, "Block not found")
        raise AssertionError(f"unexpected RPC {method}")


EN1 = b"\x01\x00\x00\x00"
EN2 = "00000001"


def find_nonce(solo, job, want="block"):
    """First nonce (from 0) whose reconstructed header meets
    the wanted target, judged by the server's own validator.
    Regtest bits make the network target a coin flip, so this
    returns within a few tries."""
    t = job["template"]
    ntime = f"{t['curtime']:08x}"
    target = job["target"] if want == "block" else solo.share_target
    for nonce in range(100000):
        res, err = solo.validate_share(job, EN1, EN2, ntime,
                                       f"{nonce:08x}")
        assert err is None, err
        if res["value"] <= target:
            return nonce, ntime
    raise AssertionError("no winning nonce found")


def make_solo(submit_mode="accept"):
    rpc = FakeRPC(submit_mode)
    solo = SoloServer(rpc, PAYOUT, share_difficulty=0.01,
                      expected_chain="regtest")
    job = solo.refresh_job()
    return rpc, solo, job


def test_solo_block_chain_verified():
    rpc, solo, job = make_solo("accept")
    nonce, ntime = find_nonce(solo, job)
    out = solo.submit_share(job["job_id"], EN1, EN2, ntime,
                            f"{nonce:08x}", worker="w1")
    assert out["accepted"], out
    rec = out["block"]
    assert rec["accepted"] is True, rec
    assert rec["chain_verified"] is True, rec
    assert rec["chain_status"] == "tip", rec
    assert rec["submit_classification"] == "accepted", rec
    assert rec["submit_result"] is None, rec
    assert rec["verify_reason"] == "ok", rec
    assert len(rpc.submit_calls) == 1
    assert rpc.best == rec["hash"]
    st = solo.stats()
    assert st["workers"]["w1"]["blocks"] == 1, st["workers"]
    assert st["workers"]["w1"]["block_candidates"] == 1
    print("ok: solo block verified exactly, submitted once, "
          "counted only when chain state confirms it as tip")


def test_solo_negative_exact_verification():
    rpc, solo, job = make_solo("accept")
    # Tamper: the template now claims an overflow nBits, and
    # the job's recorded target is set to the value that
    # nBits decodes to, so the fast compare alone would call
    # any winning share a block and submit it.
    overflow_target, _neg, over = compact_decode(0x2300FFFF)
    assert over
    job["template"] = dict(job["template"], bits="2300ffff")
    job["target"] = overflow_target
    nonce, ntime = find_nonce(solo, job)
    out = solo.submit_share(job["job_id"], EN1, EN2, ntime,
                            f"{nonce:08x}", worker="w1")
    assert not out["accepted"], out
    assert "exact verification failed: overflow-target" \
        in out["reason"], out
    assert rpc.submit_calls == [], "an invalid candidate was submitted"
    assert len(solo.candidates_rejected) == 1
    assert solo.candidates_rejected[0]["reason"] == "overflow-target"
    st = solo.stats()
    assert st["workers"]["w1"]["rejected"] == 1, st["workers"]
    assert st["workers"]["w1"]["blocks"] == 0
    print("ok: overflow-target candidate rejected by exact "
          "verification; submitblock never called")


def test_solo_negative_target_mismatch():
    rpc, solo, job = make_solo("accept")
    # The header will carry mainnet bits while the job record
    # keeps the regtest target: the reconstructed header and
    # the job disagree, so the candidate is rejected before
    # any submission.
    job["template"] = dict(job["template"], bits="1d00ffff")
    nonce, ntime = find_nonce(solo, job)
    out = solo.submit_share(job["job_id"], EN1, EN2, ntime,
                            f"{nonce:08x}", worker="w1")
    assert not out["accepted"], out
    assert "header-target-mismatch" in out["reason"], out
    assert rpc.submit_calls == []
    assert solo.candidates_rejected[0]["reason"] \
        == "header-target-mismatch"
    print("ok: header/job target mismatch rejected before "
          "submission")


def test_solo_submit_none_is_not_success():
    rpc, solo, job = make_solo("orphan")
    nonce, ntime = find_nonce(solo, job)
    out = solo.submit_share(job["job_id"], EN1, EN2, ntime,
                            f"{nonce:08x}", worker="w1")
    # The share itself was a valid network-target candidate,
    # so it is accepted as a share; the BLOCK is not counted,
    # because submitblock's None was never confirmed by chain
    # state. This is defect 1, closed.
    assert out["accepted"], out
    rec = out["block"]
    assert rec["submit_result"] is None, rec
    assert rec["accepted"] is False, rec
    assert rec["chain_verified"] is False, rec
    assert rec["chain_status"] == "not-in-chain", rec
    st = solo.stats()
    assert st["workers"]["w1"]["blocks"] == 0, st["workers"]
    assert st["workers"]["w1"]["block_candidates"] == 1
    print("ok: submitblock None without chain confirmation is "
          "recorded as not accepted, not as a found block")


def test_solo_submit_rejection_and_rpc_failure():
    rpc, solo, job = make_solo("reject-string")
    nonce, ntime = find_nonce(solo, job)
    out = solo.submit_share(job["job_id"], EN1, EN2, ntime,
                            f"{nonce:08x}", worker="w1")
    rec = out["block"]
    assert rec["accepted"] is False, rec
    assert rec["submit_result"] == "duplicate-invalid", rec
    assert rec["submit_classification"] == "duplicate-invalid", rec

    rpc, solo, job = make_solo("raise")
    nonce, ntime = find_nonce(solo, job)
    out = solo.submit_share(job["job_id"], EN1, EN2, ntime,
                            f"{nonce:08x}", worker="w1")
    rec = out["block"]
    assert rec["accepted"] is False, rec
    assert rec["submit_classification"] == "rpc-error", rec
    assert rec["chain_status"] == "unknown", rec
    # The candidate record survives the failed submission.
    assert solo.blocks_found[-1]["hash"] == rec["hash"]
    print("ok: rejection strings classified verbatim; RPC "
          "failure keeps the candidate record and counts no "
          "block")


def test_chain_acceptance_unit():
    rpc = FakeRPC()
    status, ok = verify_chain_acceptance(rpc, TIP)
    assert (status, ok) == ("tip", True)
    status, ok = verify_chain_acceptance(rpc, "cd" * 32)
    assert (status, ok) == ("not-in-chain", False)
    rpc.in_chain["cd" * 32] = 3
    status, ok = verify_chain_acceptance(rpc, "cd" * 32)
    assert (status, ok) == ("in-chain", True)
    rpc.in_chain["cd" * 32] = -1  # fork block, not active
    status, ok = verify_chain_acceptance(rpc, "cd" * 32)
    assert (status, ok) == ("not-in-chain", False)
    print("ok: chain acceptance distinguishes tip, in-chain, "
          "fork and unknown blocks")


# ---------------------------------------------------------------- regtest e2e

def wallet_rpc(rpc):
    if "bal-regtest" not in rpc.call("listwallets"):
        try:
            rpc.call("loadwallet", "bal-regtest")
        except Exception:
            rpc.call("createwallet", "bal-regtest")
    return BitcoinRPC(wallet="bal-regtest")


def test_regtest_end_to_end():
    node_manager.start()
    rpc = BitcoinRPC()
    wallet = wallet_rpc(rpc)
    payout = wallet.call("getnewaddress", "", "bech32")
    solo = SoloServer(rpc, payout, share_difficulty=0.01,
                      expected_chain="regtest")
    tip0 = rpc.get_block_count()
    job = solo.refresh_job()
    nonce, ntime = find_nonce(solo, job)
    out = solo.submit_share(job["job_id"], EN1, EN2, ntime,
                            f"{nonce:08x}", worker="exp036-e2e")
    assert out["accepted"], out
    rec = out["block"]
    assert rec["accepted"] is True, rec
    assert rec["chain_verified"] is True, rec
    assert rec["chain_status"] == "tip", rec
    assert rpc.get_block_count() == tip0 + 1
    assert rpc.get_best_block_hash() == rec["hash"]
    print(f"ok: regtest block through the fixed solo path is "
          f"chain-verified at height {rec['height']}: "
          f"{rec['hash']}")

    # Negative on the real node: a share below the share
    # target is rejected and nothing is submitted.
    job = solo.refresh_job()
    t = job["template"]
    ntime = f"{t['curtime']:08x}"
    blocks_before = len(solo.blocks_found)
    tip_before = rpc.get_block_count()
    for nonce in range(100000):
        res, err = solo.validate_share(job, EN1, EN2, ntime,
                                       f"{nonce:08x}")
        assert err is None, err
        # Above the network target implies above the (smaller)
        # share target: a genuinely low-difficulty share.
        if res["value"] > job["target"]:
            break
    out = solo.submit_share(job["job_id"], EN1, EN2, ntime,
                            f"{nonce:08x}", worker="exp036-e2e")
    assert not out["accepted"], out
    assert out["reason"] == "low difficulty share", out
    assert len(solo.blocks_found) == blocks_before
    assert rpc.get_block_count() == tip_before
    print("ok: low-difficulty share rejected on the real node; "
          "no submission, tip unmoved")


def main():
    test_boundary_integer_semantics()
    test_verify_candidate_classifications()
    test_verify_candidate_invalid_targets()
    test_submit_result_classification()
    test_solo_block_chain_verified()
    test_solo_negative_exact_verification()
    test_solo_negative_target_mismatch()
    test_solo_submit_none_is_not_success()
    test_solo_submit_rejection_and_rpc_failure()
    test_chain_acceptance_unit()
    test_regtest_end_to_end()
    print("ALL EXP-036 VERIFICATION TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
