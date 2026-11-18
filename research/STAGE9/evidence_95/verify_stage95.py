#!/usr/bin/env python3
"""Stage 9.5 builder-side INDEPENDENT verification (not part of
the agent run). For every block the agent found (heights 1 to
8 on the isolated regtest node):

  - fetch the raw block hex and the decoded block from Core,
  - recompute the block hash from the raw 80-byte header with
    hashlib SHA-256d and compare with the node's hash,
  - confirm height and best-chain membership from the node,
  - run the production acceptance checker
    (mining.candidate_verify.verify_chain_acceptance),
  - check the coinbase pays the payout address of the run
    that produced the block, at the full regtest subsidy.

Writes per-block evidence and verification.json into
research/STAGE9/evidence_95/, plus the combined decision log
and the submit-response extract.
"""

import hashlib
import json
import os
import sys
from datetime import datetime, timezone

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                    "..", ".."))
sys.path.insert(0, REPO)
STAGE = os.path.join(REPO, ".local", "stage95")
EVID = os.path.join(REPO, "research", "STAGE9", "evidence_95")
os.makedirs(EVID, exist_ok=True)

from mining.candidate_verify import verify_chain_acceptance
from node.rpc_client import BitcoinRPC

with open(os.path.join(STAGE, "rpc_password.txt")) as f:
    pw = f.read().strip()
rpc = BitcoinRPC(host="127.0.0.1", port=18643, user="balstage95",
                 password=pw)

run1 = json.load(open(os.path.join(STAGE, "run_output.json")))
run2 = json.load(open(os.path.join(STAGE,
                                   "run_output_publisher.json")))
payout_by_height = {}
for c in run1["cycles"]:
    payout_by_height[c["height"]] = run1["payout_address"]
for c in run2["cycles"]:
    payout_by_height[c["height"]] = run2["payout_address"]
agent_hash = {}
for c in run1["cycles"] + run2["cycles"]:
    agent_hash[c["height"]] = c["hash"]

info_after = rpc.get_blockchain_info()
with open(os.path.join(EVID, "getblockchaininfo_after.json"),
          "w") as f:
    json.dump(info_after, f, indent=2)
tip = info_after["blocks"]

results = []
for height in range(1, tip + 1):
    bhash = rpc.call("getblockhash", height)
    raw = rpc.call("getblock", bhash, 0)
    decoded = rpc.call("getblock", bhash, 2)
    header = bytes.fromhex(raw)[:80]
    digest = hashlib.sha256(hashlib.sha256(header).digest()).digest()
    recomputed = digest[::-1].hex()
    status, accepted = verify_chain_acceptance(rpc, bhash)
    coinbase = decoded["tx"][0]
    vout0 = coinbase["vout"][0]
    spk = vout0["scriptPubKey"]
    cb_address = spk.get("address")
    entry = {
        "height": height,
        "node_hash": bhash,
        "agent_reported_hash": agent_hash.get(height),
        "recomputed_hash_from_raw_hex": recomputed,
        "hash_matches_node": recomputed == bhash,
        "hash_matches_agent": recomputed == agent_hash.get(height),
        "confirmations": decoded["confirmations"],
        "in_best_chain": decoded["confirmations"] >= 1
        and bhash == rpc.call("getblockhash", height),
        "verify_chain_acceptance": {"status": status,
                                    "accepted": accepted},
        "nonce": decoded["nonce"],
        "bits": decoded["bits"],
        "block_time": decoded["time"],
        "tx_count": len(decoded["tx"]),
        "coinbase_txid": coinbase["txid"],
        "coinbase_address": cb_address,
        "expected_payout_address": payout_by_height.get(height),
        "coinbase_pays_intended_address":
            cb_address == payout_by_height.get(height),
        "coinbase_value_btc": vout0["value"],
    }
    results.append(entry)
    with open(os.path.join(EVID, f"block_{height}_hex.txt"),
              "w") as f:
        f.write(raw + "\n")
    with open(os.path.join(EVID, f"header_{height}_hex.txt"),
              "w") as f:
        f.write(header.hex() + "\n")
    with open(os.path.join(EVID, f"block_{height}.json"), "w") as f:
        json.dump(decoded, f, indent=2)
    print(height, bhash[:16], "hash_ok", entry["hash_matches_node"],
          "accept", status, accepted, "coinbase_ok",
          entry["coinbase_pays_intended_address"])

with open(os.path.join(EVID, "verification.json"), "w") as f:
    json.dump({"tip": tip, "blocks": results}, f, indent=2)

# Combined decision log (agent-recorded decisions, both runs)
def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()

decisions = []
for label, run in (("run1", run1), ("run2_publisher", run2)):
    for d in run["decisions"]:
        decisions.append({"run": label, "ts": d["ts"],
                          "ts_iso": iso(d["ts"]),
                          "kind": d["kind"],
                          "detail": d["detail"]})
decisions.sort(key=lambda d: d["ts"])
with open(os.path.join(EVID, "decision_log.json"), "w") as f:
    json.dump(decisions, f, indent=2)

# Submit responses and shim verifications, extracted per block
submits = []
for label, run in (("run1", run1), ("run2_publisher", run2)):
    vers = {v["header_hex"]: v for v in run["verifications"]}
    for t in run["rpc_trace"]:
        if t["method"] == "submitblock":
            submits.append({
                "run": label, "ts": t["ts"],
                "ts_iso": iso(t["ts"]),
                "submit_result": t.get("submit_result"),
                "verify": t.get("verify")})
with open(os.path.join(EVID, "submit_responses.json"), "w") as f:
    json.dump(submits, f, indent=2)

ok = all(r["hash_matches_node"] and r["hash_matches_agent"]
         and r["in_best_chain"] and r["verify_chain_acceptance"]["accepted"]
         and r["coinbase_pays_intended_address"] for r in results)
print("ALL BLOCKS VERIFIED:", ok, "| tip:", tip)
