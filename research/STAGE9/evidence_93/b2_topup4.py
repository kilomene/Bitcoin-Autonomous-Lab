#!/usr/bin/env python3
"""Stage 9.3 B2 witness completion, Core-funded design.

Four production-mined funding attempts on this isolated chain
each mined 80+ blocks through MiningEngine.mine_cycle and then
hit a reproducible multi-minute node stall while connecting a
block in the height 80s (submitblock responses timed out; one
block connected only after a 900 s poll, the next not at all).
Funding is therefore done with Core's own generatetoaddress
(disclosed here and in witness.json: Core-mined funding blocks,
not production-mined). Everything being PROVEN is production:
the segwit transaction enters the template, the production
MiningEngine builds the candidate and its witness commitment,
the commitment is recomputed independently and compared with
Core's default_witness_commitment, the block is searched with
the production ComputeEngine, verified with the EXP-036
verifier, submitted with submitblock, and acceptance is read
from Core chain state, with tip polling to tolerate the node's
slow block connection. Single node instance throughout."""
import json, os, struct, subprocess, sys, time
REPO = os.path.expanduser("~/workspace/bitcoin-autonomous-lab")
sys.path.insert(0, REPO)
EVID = os.path.join(REPO, "research", "STAGE9", "evidence_93")
DATADIR = os.path.join(REPO, ".local", "stage9", "data")
BITCOIND = os.path.expanduser("~/workspace/bitcoin-core-dist/bitcoin-core-28.1/bin/bitcoind")
conf = os.path.join(DATADIR, "bitcoin.conf")
user = pw = None
for line in open(conf):
    if line.startswith("rpcuser="): user = line.strip().split("=", 1)[1]
    if line.startswith("rpcpassword="): pw = line.strip().split("=", 1)[1]
from node.rpc_client import BitcoinRPC
rpc = BitcoinRPC(host="127.0.0.1", port=18543, user=user, password=pw, timeout=180, retries=3)
short = BitcoinRPC(host="127.0.0.1", port=18543, user=user, password=pw, timeout=30, retries=1)
proc = subprocess.Popen([BITCOIND, f"-datadir={DATADIR}", f"-conf={conf}"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
witness = {"funding_method": "Bitcoin Core generatetoaddress (Core-mined funding blocks, used only to mature a coinbase so a segwit transaction can enter the template; four earlier production-mined funding attempts on this chain stalled in the height 80s on node block-connection stalls)", "proof_path": "production MiningEngine construction, ComputeEngine search, EXP-036 verification, submitblock, Core chain-state acceptance"}
try:
    info = None
    for _ in range(240):
        try:
            info = rpc.get_blockchain_info(); break
        except Exception: time.sleep(0.5)
    witness["start_height"] = info["blocks"]
    print("start height:", info["blocks"], flush=True)
    try: rpc.call("loadwallet", "stage9")
    except Exception as e: print("loadwallet:", e, flush=True)
    wrpc = BitcoinRPC(host="127.0.0.1", port=18543, user=user, password=pw, timeout=180, retries=3, wallet="stage9")
    witness["funding_blocks_core"] = 0
    witness["funding_note"] = "funding already complete on this chain (height above 101 reached by the earlier Core generatetoaddress call in the previous attempt); no new funding blocks mined by this run"
    witness["height_after_funding"] = rpc.get_blockchain_info()["blocks"]
    witness["balance_btc"] = wrpc.call("getbalance")
    print("funded to", witness["height_after_funding"], "balance", witness["balance_btc"], flush=True)
    payout = wrpc.call("getnewaddress", "stage9-payout-w", "bech32")
    from gpu.engine import ComputeEngine
    from mining.candidate_verify import verify_candidate
    from mining.engine import MiningEngine, wtxid_of
    from mining.pow import dsha256, merkle_root
    from mining.pow_engine import POW_LIMIT_REGTEST
    compute = ComputeEngine(requested="hashlib")
    witness["backend"] = compute.describe().get("backend")
    engine = MiningEngine(rpc, payout, compute=compute)
    segwit_addr = wrpc.call("getnewaddress", "stage9-segwit", "bech32")
    witness["segwit_txid"] = wrpc.call("sendtoaddress", segwit_addr, 0.5)
    tmpl2 = engine.get_template()
    witness["template2_height"] = tmpl2["height"]
    witness["template2_tx_count"] = len(tmpl2.get("transactions", []))
    witness["core_default_witness_commitment"] = tmpl2.get("default_witness_commitment")
    cand2 = engine.build_candidate(tmpl2, 0)
    witness["witness_count"] = cand2["witness_count"]
    wtxids = [b"\x00" * 32] + [wtxid_of(bytes.fromhex(tx["data"])) for tx in tmpl2["transactions"]]
    commitment = dsha256(merkle_root(wtxids) + b"\x00" * 32)
    witness["recomputed_commitment"] = commitment.hex()
    witness["commitment_matches_core"] = bool(tmpl2.get("default_witness_commitment") and commitment.hex() in tmpl2["default_witness_commitment"])
    witness["commitment_in_coinbase"] = bool(bytes.fromhex("aa21a9ed") + commitment in cand2["body"])
    print("commitment checks:", witness["commitment_matches_core"], witness["commitment_in_coinbase"], "witness_count", witness["witness_count"], flush=True)
    # Search and submit the witness block through the production path.
    en = 0
    hit = None
    cand = cand2
    while hit is None and en <= 512:
        hit, attempted, _s = compute.search_first_counted(cand["header"], cand["target"], 0, 65536)
        if hit is None:
            en += 1
            cand = engine.build_candidate(tmpl2, en)
    witness["search_extranonce"] = en
    nonce = hit[0]
    header = cand["header"][:76] + struct.pack("<I", nonce)
    verdict = verify_candidate(header, POW_LIMIT_REGTEST)
    witness["verifier_classification"] = verdict["classification"]
    block = header + cand["body"]
    block_hash = dsha256(header)[::-1].hex()
    witness["witness_block_hash"] = block_hash
    try:
        resp = short.call("submitblock", block.hex())
        witness["submitblock_response"] = resp
    except Exception as e:
        witness["submitblock_response"] = f"not received ({type(e).__name__}); polling tip"
    deadline = time.time() + 1200
    accepted = False
    while time.time() < deadline:
        try:
            cur = rpc.get_blockchain_info()
            if cur["bestblockhash"] == block_hash:
                accepted = True
                break
        except Exception:
            pass
        time.sleep(5)
    witness["witness_block_accepted"] = accepted
    if accepted:
        blk2 = rpc.call("getblock", block_hash, 2)
        with open(os.path.join(EVID, "getblock_witness.json"), "w") as f: f.write(json.dumps(blk2, indent=2) + "\n")
        witness["witness_block_height"] = blk2["height"]
        witness["witness_block_confirmations"] = blk2["confirmations"]
        witness["witness_block_tx_count"] = len(blk2["tx"])
    ok = witness["witness_count"] >= 1 and witness["commitment_matches_core"] and witness["commitment_in_coinbase"] and verdict["classification"] == "block_candidate" and accepted
    witness["verdict"] = "PASS" if ok else "FAIL"
    print(json.dumps(witness, indent=2), flush=True)
    with open(os.path.join(EVID, "witness.json"), "w") as f: f.write(json.dumps(witness, indent=2) + "\n")
    sys.exit(0 if ok else 1)
finally:
    try: rpc.call("stop")
    except Exception: pass
    try: proc.wait(timeout=60)
    except Exception: proc.kill()
