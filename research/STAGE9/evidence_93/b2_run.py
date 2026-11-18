#!/usr/bin/env python3
"""Stage 9.3 Part 2 (B2): candidate and block correctness on an
isolated regtest node, using Bitcoin Core 28.1 as the independent
consensus reference and the production code path
(mining/engine.py MiningEngine + gpu/engine.py ComputeEngine +
mining/candidate_verify.py) for construction, search and
verification.

Isolation: fresh datadir .local/stage9/data, RPC 18543, P2P 18544.
The live mainnet stack, .local/regtest and .local/stage8 are never
touched. All raw evidence is written to
research/STAGE9/evidence_93/ and a machine-readable summary to
summary.json in the same directory. The script exits non-zero if
any core consensus check fails; every check outcome is recorded
in the summary regardless.
"""
import json
import os
import secrets
import struct
import subprocess
import sys
import time

REPO = os.path.expanduser("~/workspace/bitcoin-autonomous-lab")
sys.path.insert(0, REPO)
EVID = os.path.join(REPO, "research", "STAGE9", "evidence_93")
DATADIR = os.path.join(REPO, ".local", "stage9", "data")
BITCOIND = os.path.expanduser(
    "~/workspace/bitcoin-core-dist/bitcoin-core-28.1/bin/bitcoind")
RPC_PORT = 18543
P2P_PORT = 18544
RPC_USER = "stage9rpc"
RPC_PASS = secrets.token_hex(24)

summary = {"checks": {}, "facts": {}}


def record(name, ok, detail=""):
    summary["checks"][name] = {"ok": bool(ok), "detail": str(detail)}
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}", flush=True)
    return ok


def save(name, text):
    with open(os.path.join(EVID, name), "w") as f:
        f.write(text)


def main():
    os.makedirs(EVID, exist_ok=True)
    os.makedirs(DATADIR, exist_ok=True)
    conf = os.path.join(DATADIR, "bitcoin.conf")
    with open(conf, "w") as f:
        f.write(
            "regtest=1\nserver=1\ntxindex=1\nfallbackfee=0.0002\n"
            f"rpcport={RPC_PORT}\nport={P2P_PORT}\n"
            f"rpcuser={RPC_USER}\nrpcpassword={RPC_PASS}\n"
            "rpcallowip=127.0.0.1\nlisten=0\n"
            f"[regtest]\nrpcport={RPC_PORT}\nport={P2P_PORT}\n")
    os.chmod(conf, 0o600)

    from node.rpc_client import BitcoinRPC
    rpc = BitcoinRPC(host="127.0.0.1", port=RPC_PORT, user=RPC_USER,
                     password=RPC_PASS, timeout=30, retries=1)

    proc = subprocess.Popen(
        [BITCOIND, f"-datadir={DATADIR}", f"-conf={conf}"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    summary["facts"]["bitcoind_pid"] = proc.pid
    try:
        deadline = time.time() + 120
        up = False
        info0 = None
        while time.time() < deadline:
            try:
                info0 = rpc.get_blockchain_info()
                up = True
                break
            except Exception:
                if proc.poll() is not None:
                    break
                time.sleep(0.5)
        if not record("node_started", up, "isolated regtest RPC answered"):
            return 1
        save("getblockchaininfo_initial.json",
             json.dumps(info0, indent=2) + "\n")
        summary["facts"]["initial_chain"] = {
            "chain": info0["chain"], "blocks": info0["blocks"],
            "headers": info0["headers"],
            "difficulty": info0["difficulty"]}
        ver = rpc.call("getnetworkinfo")["version"]
        summary["facts"]["core_version"] = ver
        record("core_chain_is_regtest", info0["chain"] == "regtest",
               f"chain={info0['chain']} core_version={ver}")

        rpc.call("createwallet", "stage9")
        wrpc = BitcoinRPC(host="127.0.0.1", port=RPC_PORT, user=RPC_USER,
                          password=RPC_PASS, timeout=30, retries=1,
                          wallet="stage9")
        payout = wrpc.call("getnewaddress", "stage9-payout", "bech32")
        summary["facts"]["payout_address"] = payout

        from gpu.engine import ComputeEngine, validate_nonce_range
        from mining.candidate_verify import (classify_submit_result,
                                             verify_candidate,
                                             verify_chain_acceptance)
        from mining.engine import MiningEngine, txid_of
        from mining.pow import dsha256, merkle_root
        from mining.pow_engine import (POW_LIMIT_REGTEST, check_pow,
                                       compact_decode,
                                       double_sha256_pure)

        compute = ComputeEngine()
        summary["facts"]["backend"] = compute.describe()
        print("backend:", json.dumps(compute.describe()), flush=True)
        engine = MiningEngine(rpc, payout, compute=compute)

        # ---- Template and candidate construction (production path)
        template = engine.get_template()
        save("template_block1.json", json.dumps(template, indent=2) + "\n")
        height = template["height"]
        summary["facts"]["block_height"] = height
        cand = engine.build_candidate(template, 0)
        cand_uncached = engine.build_candidate_uncached(template, 0)
        record("cached_vs_uncached_construction_identical",
               cand["header"] == cand_uncached["header"]
               and cand["body"] == cand_uncached["body"],
               "EXP-025 cached path and uncached reference agree byte for byte")
        header0 = cand["header"]
        record("header_is_80_bytes", len(header0) == 80,
               f"len={len(header0)}")

        # Header field dissection and byte order.
        version = struct.unpack("<i", header0[0:4])[0]
        prevhash_internal = header0[4:36]
        merkle_internal = header0[36:68]
        ntime = struct.unpack("<I", header0[68:72])[0]
        nbits = struct.unpack("<I", header0[72:76])[0]
        record("header_prevhash_matches_template_display_reversed",
               prevhash_internal == bytes.fromhex(
                   template["previousblockhash"])[::-1],
               "header stores prevhash in internal (reversed) byte order")
        record("header_bits_match_template",
               header0[72:76] == bytes.fromhex(template["bits"])[::-1],
               f"bits={template['bits']}")
        record("header_version_matches_template",
               version == template["version"], f"version={version}")

        # Independent merkle recomputation from the raw block body:
        # body = varint(txcount) || coinbase || txs. Empty mempool:
        # txcount 1 and the merkle root must equal the coinbase txid.
        body = cand["body"]
        first = body[0]
        assert first < 0xFD
        txcount = first
        coinbase_raw = body[1:]
        cb_txid_internal = txid_of(coinbase_raw)
        record("merkle_root_single_tx_equals_coinbase_txid",
               txcount == 1 and merkle_internal == cb_txid_internal,
               f"txcount={txcount}")
        record("merkle_root_function_agrees",
               merkle_root([cb_txid_internal]) == merkle_internal,
               "mining.pow.merkle_root over the body-derived txid matches header")
        summary["facts"]["template_tx_count"] = len(
            template.get("transactions", []))
        summary["facts"]["witness_count_block1"] = cand["witness_count"]
        summary["facts"]["template_default_witness_commitment"] = \
            template.get("default_witness_commitment")
        record("witness_commitment_empty_template_recorded",
               cand["witness_count"] == 0,
               "empty template: no witness txs, so the engine adds "
               "no witness commitment output; Core still serves a "
               "default_witness_commitment for the empty witness "
               "set on regtest (segwit active from genesis). A "
               "commitment is only required when a block carries "
               "witness data; Core acceptance of this block below "
               "is the deciding evidence. The witness-carrying "
               "case is proven separately at the end of this run.")

        # Compact target decoding and integer comparison basis.
        target_decoded, negative, overflow = compact_decode(nbits)
        target_template = int(template["target"], 16)
        save("decoded_target.txt",
             f"nbits_hex: {nbits:08x}\n"
             f"decoded_target_int: {target_decoded}\n"
             f"decoded_target_hex: {target_decoded:064x}\n"
             f"template_target_int: {target_template}\n"
             f"negative: {negative}\noverflow: {overflow}\n"
             f"pow_limit_regtest: {POW_LIMIT_REGTEST:064x}\n")
        record("compact_decode_matches_template_target",
               target_decoded == target_template
               and not negative and not overflow,
               f"nbits=0x{nbits:08x}")
        record("target_within_regtest_pow_limit",
               0 < target_decoded <= POW_LIMIT_REGTEST, "")
        expected_hashes = (1 << 256) // (target_decoded + 1)
        summary["facts"]["regtest_expected_hashes_per_block"] = \
            expected_hashes
        summary["facts"]["regtest_p_single_hash"] = \
            (target_decoded + 1) / float(1 << 256)

        # ---- Search with the production ComputeEngine
        hit, attempted, secs = compute.search_first_counted(
            header0, cand["target"], 0, 65536)
        en = 0
        while hit is None and en < 64:
            en += 1
            cand = engine.build_candidate(template, en)
            header0 = cand["header"]
            hit, attempted, secs = compute.search_first_counted(
                header0, cand["target"], 0, 65536)
        if not record("search_found_candidate", hit is not None,
                      f"extranonce={en} attempted={attempted}"):
            save("summary.json", json.dumps(summary, indent=2) + "\n")
            return 1
        nonce, digest_from_search = hit
        summary["facts"]["nonce"] = nonce
        summary["facts"]["search_attempted"] = attempted
        summary["facts"]["search_seconds"] = secs
        summary["facts"]["extranonce"] = en
        final_header = header0[:76] + struct.pack("<I", nonce)
        save("header_hex.txt", final_header.hex() + "\n")
        record("search_digest_matches_recomputed",
               digest_from_search == dsha256(final_header),
               "ComputeEngine-reported digest equals hashlib SHA-256d "
               "of the reconstructed header")

        # Candidate reconstruction from submitted fields alone.
        rebuilt = (struct.pack("<i", version) + prevhash_internal
                   + merkle_internal + struct.pack("<I", ntime)
                   + header0[72:76] + struct.pack("<I", nonce))
        record("candidate_reconstruction_from_fields",
               rebuilt == final_header,
               "version, prevhash, merkle root, time, bits and nonce "
               "rebuild the exact 80-byte header")

        # Digest agreement: hashlib vs pure-Python vs production verifier.
        digest_hashlib = dsha256(final_header)
        digest_pure = double_sha256_pure(final_header)
        record("digest_agreement_hashlib_vs_pure",
               digest_hashlib == digest_pure,
               "OpenSSL-backed hashlib and the from-specification "
               "pure-Python SHA-256d agree byte for byte")
        value = int.from_bytes(digest_hashlib, "little")
        record("integer_target_comparison",
               value <= target_decoded,
               f"value <= target as exact integers "
               f"(value={value:064x})")
        ok_pow, reason_pow = check_pow(final_header, POW_LIMIT_REGTEST)
        record("check_pow_ok", ok_pow and reason_pow == "ok",
               f"reason={reason_pow}")
        verdict = verify_candidate(final_header, POW_LIMIT_REGTEST)
        save("verify_candidate.json", json.dumps({
            "classification": verdict["classification"],
            "reason": verdict["reason"],
            "digests_agree": verdict["digests_agree"],
            "valid_header": verdict["valid_header"],
            "value": verdict["value"], "target": verdict["target"],
            "nbits": verdict["nbits"],
            "meets_network_target": verdict["meets_network_target"],
            "digest_display": verdict["digest"][::-1].hex(),
        }, indent=2) + "\n")
        record("production_verifier_block_candidate",
               verdict["classification"] == "block_candidate"
               and verdict["meets_network_target"]
               and verdict["digests_agree"],
               f"classification={verdict['classification']}")
        block_hash = digest_hashlib[::-1].hex()
        summary["facts"]["block_hash"] = block_hash
        save("computed_digest.txt",
             f"digest_internal_hex: {digest_hashlib.hex()}\n"
             f"block_hash_display: {block_hash}\n"
             f"value_int: {value}\nvalue_hex: {value:064x}\n")

        # ---- Submission and chain acceptance (Core is the judge)
        block = final_header + cand["body"]
        save("block_hex.txt", block.hex() + "\n")
        submit = rpc.call("submitblock", block.hex())
        save("submitblock_response.txt",
             f"submitblock returned: {submit!r}\n"
             f"classification: {classify_submit_result(submit)}\n")
        record("submitblock_accepted_response", submit is None,
               f"Core submitblock returned {submit!r} (None means "
               "accepted for processing)")
        status, accepted = verify_chain_acceptance(rpc, block_hash)
        record("chain_acceptance_tip", accepted and status == "tip",
               f"verify_chain_acceptance status={status}")
        info_after = rpc.get_blockchain_info()
        save("getblockchaininfo_after.json",
             json.dumps(info_after, indent=2) + "\n")
        record("best_chain_membership",
               info_after["blocks"] == height
               and info_after["bestblockhash"] == block_hash,
               f"blocks={info_after['blocks']} best={info_after['bestblockhash']}")
        try:
            blk = rpc.call("getblock", block_hash, 2)
            save("getblock.json", json.dumps(blk, indent=2) + "\n")
            record("getblock_confirms_block",
                   blk["hash"] == block_hash and blk["height"] == height
                   and blk["confirmations"] >= 1,
                   f"confirmations={blk['confirmations']} txs={len(blk['tx'])}")
        except Exception as exc:
            record("getblock_confirms_block", False,
                   f"getblock raised: {exc}")

        # ---- Boundary behaviour, exercised in code
        bounds = {}
        from mining.engine import MiningEngine as ME
        bounds["batch_count_start0"] = ME.batch_count(65536, 0)
        bounds["batch_count_last_nonce"] = ME.batch_count(65536, (1 << 32) - 1)
        bounds["batch_count_full_space"] = ME.batch_count(1 << 32, 0)
        try:
            ME.batch_count(65536, 1 << 32)
            bounds["batch_count_start_2pow32"] = "no error (UNEXPECTED)"
        except ValueError as exc:
            bounds["batch_count_start_2pow32"] = f"ValueError: {exc}"
        try:
            validate_nonce_range((1 << 32) - 1, 2)
            bounds["validate_range_overflow"] = "no error (UNEXPECTED)"
        except Exception as exc:
            bounds["validate_range_overflow"] = \
                f"{type(exc).__name__}: {exc}"
        try:
            validate_nonce_range(0, 1 << 32)
            bounds["validate_range_full"] = "accepted"
        except Exception as exc:
            bounds["validate_range_full"] = f"{type(exc).__name__}: {exc}"
        # Nonce 0 and nonce 2^32-1 are each searched and reachable:
        # with the maximum target every nonce meets it, so a
        # one-nonce search at each edge must hit exactly that nonce.
        max_target = (1 << 256) - 1
        hit0, att0, _ = compute.search_first_counted(
            header0, max_target, 0, 1)
        bounds["nonce0_hit"] = hit0[0] if hit0 else None
        bounds["nonce0_attempted"] = att0
        hitL, attL, _ = compute.search_first_counted(
            header0, max_target, (1 << 32) - 1, 1)
        bounds["nonce_last_hit"] = hitL[0] if hitL else None
        bounds["nonce_last_attempted"] = attL
        record("nonce_zero_searched_and_reachable",
               hit0 is not None and hit0[0] == 0,
               f"hit={bounds['nonce0_hit']}")
        record("nonce_max_searched_and_reachable",
               hitL is not None and hitL[0] == (1 << 32) - 1,
               f"hit={bounds['nonce_last_hit']}")
        # Extranonce space refusal out of range (constructor gate).
        for space in ((0, (1 << 32) + 1), ((1 << 32) - 1, 2), (-1, 4)):
            try:
                MiningEngine(rpc, payout, compute=compute,
                             extranonce_space=space)
                bounds[f"extranonce_space_{space}"] = \
                    "no error (UNEXPECTED)"
            except ValueError as exc:
                bounds[f"extranonce_space_{space}"] = f"ValueError: {exc}"
        try:
            engine.build_candidate(template, 1 << 32)
            bounds["extranonce_2pow32_build"] = "no error (UNEXPECTED)"
        except Exception as exc:
            bounds["extranonce_2pow32_build"] = \
                f"{type(exc).__name__}: {exc}"
        ok_en_max = True
        try:
            engine.build_candidate(template, (1 << 32) - 1)
        except Exception as exc:
            ok_en_max = False
            bounds["extranonce_max_build"] = f"{type(exc).__name__}: {exc}"
        if ok_en_max:
            bounds["extranonce_max_build"] = "accepted"
        save("boundaries.json", json.dumps(bounds, indent=2) + "\n")
        record("batch_count_boundaries",
               bounds["batch_count_start0"] == 65536
               and bounds["batch_count_last_nonce"] == 1
               and bounds["batch_count_full_space"] == (1 << 32)
               and str(bounds["batch_count_start_2pow32"]).startswith(
                   "ValueError"),
               json.dumps(bounds)[:200])
        record("extranonce_refusals",
               all(str(v).startswith("ValueError")
                   for k, v in bounds.items()
                   if k.startswith("extranonce_space_"))
               and ok_en_max,
               "out-of-range spaces refused at construction; "
               "2^32-1 accepted")

        # ---- Witness commitment, proven on a block with a real
        # segwit transaction. Funding uses the production
        # mine_cycle loop itself (GBT, ComputeEngine, submitblock,
        # best-chain check inside mining/engine.py).
        witness = {"funded_blocks": 0}
        try:
            need = 101 - height
            mined = 0
            for _ in range(need):
                res = engine.mine_cycle(max_batches=200,
                                        deadline_seconds=120)
                if not res.get("accepted"):
                    break
                mined += 1
            witness["funded_blocks"] = mined
            bal = wrpc.call("getbalance")
            witness["wallet_balance_btc"] = bal
            segwit_addr = wrpc.call("getnewaddress", "stage9-segwit",
                                    "bech32")
            txid = wrpc.call("sendtoaddress", segwit_addr, 0.5)
            witness["segwit_txid"] = txid
            tmpl2 = engine.get_template()
            witness["template2_tx_count"] = len(
                tmpl2.get("transactions", []))
            witness["core_default_witness_commitment"] = \
                tmpl2.get("default_witness_commitment")
            cand2 = engine.build_candidate(tmpl2, 0)
            witness["witness_count"] = cand2["witness_count"]
            # Independent commitment recomputation from raw data.
            from mining.engine import wtxid_of
            wtxids = [b"\x00" * 32] + [
                wtxid_of(bytes.fromhex(tx["data"]))
                for tx in tmpl2["transactions"]]
            wroot = merkle_root(wtxids)
            commitment = dsha256(wroot + b"\x00" * 32)
            witness["recomputed_commitment"] = commitment.hex()
            witness["commitment_matches_core"] = bool(
                tmpl2.get("default_witness_commitment")
                and commitment.hex()
                in tmpl2["default_witness_commitment"])
            # The commitment must sit in the coinbase of the built
            # candidate as an OP_RETURN aa21a9ed output.
            witness["commitment_in_coinbase"] = bool(
                bytes.fromhex("aa21a9ed") + commitment in cand2["body"])
            res2 = engine.mine_cycle(max_batches=400,
                                     deadline_seconds=300)
            witness["witness_block_result"] = {
                k: res2.get(k) for k in
                ("accepted", "hash", "height", "nonce", "submit_result")}
            if res2.get("accepted"):
                blk2 = rpc.call("getblock", res2["hash"], 2)
                save("getblock_witness.json",
                     json.dumps(blk2, indent=2) + "\n")
                witness["witness_block_confirmations"] = \
                    blk2["confirmations"]
            save("witness.json", json.dumps(witness, indent=2) + "\n")
            record("witness_commitment_matches_core",
                   witness["witness_count"] >= 1
                   and witness["commitment_matches_core"]
                   and witness["commitment_in_coinbase"],
                   f"witness_count={witness['witness_count']}")
            record("witness_block_accepted",
                   bool(witness["witness_block_result"].get("accepted")),
                   json.dumps(witness["witness_block_result"])[:200])
        except Exception as exc:
            witness["error"] = f"{type(exc).__name__}: {exc}"
            save("witness.json", json.dumps(witness, indent=2) + "\n")
            record("witness_commitment_matches_core", False,
                   witness["error"])
            record("witness_block_accepted", False, witness["error"])

        save("summary.json", json.dumps(summary, indent=2) + "\n")
        failed = [k for k, v in summary["checks"].items() if not v["ok"]]
        print("FAILED CHECKS:", failed, flush=True)
        return 1 if failed else 0
    finally:
        try:
            rpc.call("stop")
        except Exception:
            pass
        try:
            proc.wait(timeout=60)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
