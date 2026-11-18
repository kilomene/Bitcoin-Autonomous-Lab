#!/usr/bin/env python3
"""Stage 9.5 LAUNCHER (disclosed): starts the lab's own agent
stack against the isolated Stage 9.5 regtest node and lets the
agent discover blocks.

What this launcher does, and nothing more:
  1. Points the agent's work checkpoint at the isolated
     .local/stage95 directory (the agent module's default is
     the shared .local/work-checkpoint.json) by setting the
     module constant before the agent is constructed.
  2. Creates a wallet on the ISOLATED node and takes a fresh
     bech32 address from it as the payout address.
  3. Constructs agent.autonomous.AutonomousMiner with an
     isolated BlockStore database and a default-constructed
     gpu.engine.ComputeEngine (the production backend
     dispatch), through the VerifyingRPC shim below.
  4. Enables the Stage 9.4 StatusPublisher opt-in on the
     constructed engine (status_publish=True, interval 0.25 s;
     AutonomousMiner's constructor does not expose the flag,
     and MiningEngine.mine_cycle reads it at call time).
  5. Calls agent.run_cycles(5) exactly once and writes the
     returned record (cycles, agent decisions, engine status
     events, RPC trace, shim verifications) to
     .local/stage95/run_output.json.

All per-block sequencing (template acquisition, candidate
construction, search, submission, best-chain confirmation,
batch adaptation) is performed by the agent's and engine's
own code. This launcher contains no template handling, no
search and no submission logic of its own.

SHIM (disclosed): VerifyingRPC, a BitcoinRPC subclass that
overrides call(). It (a) traces every RPC call with a
timestamp, and (b) on submitblock, runs the production
EXP-036 verifier (mining.candidate_verify.verify_candidate)
over the candidate's 80-byte header under the regtest pow
limit BEFORE forwarding, and refuses to forward (raises) a
candidate that does not meet the network target. Reason for
the shim: the GBT agent path's own in-loop verification is
Core's submitblock and best-chain verdict (see the comment
in mining/engine.py _mine_cycle); verify_candidate is wired
on the pool, solo-server and aggregation paths only. The
shim adds the production verifier at the submission boundary
for this run without modifying any agent or engine code.
"""

import json
import logging
import os
import sys
import time

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                    "..", ".."))
sys.path.insert(0, REPO)
STAGE = os.path.join(REPO, ".local", "stage95")

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(os.path.join(STAGE, "agent.log")),
              logging.StreamHandler(sys.stdout)])
log = logging.getLogger("bal.stage95.launcher")

import agent.autonomous as autonomous_mod

# Launcher configuration 1: isolated work checkpoint.
autonomous_mod.WORK_CHECKPOINT_PATH = os.path.join(
    STAGE, "work-checkpoint.json")

from agent.autonomous import AutonomousMiner
from blockchain.store import BlockStore
from gpu.engine import ComputeEngine
from mining.candidate_verify import (pow_limit_for_chain,
                                     verify_candidate)
from node.rpc_client import BitcoinRPC

RPC_HOST = "127.0.0.1"
RPC_PORT = 18643
RPC_USER = "balstage95"
with open(os.path.join(STAGE, "rpc_password.txt")) as f:
    RPC_PASSWORD = f.read().strip()


class VerifyingRPC(BitcoinRPC):
    """The disclosed shim described in the module docstring."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.trace = []
        self.verifications = []

    def call(self, method, *params):
        entry = {"ts": time.time(), "method": method}
        if method == "submitblock":
            header = bytes.fromhex(params[0])[:80]
            verdict = verify_candidate(
                header, pow_limit_for_chain("regtest"))
            v = {"ts": entry["ts"], "header_hex": header.hex(),
                 "classification": verdict["classification"],
                 "reason": verdict["reason"],
                 "meets_network_target":
                     verdict["meets_network_target"],
                 "digests_agree": verdict["digests_agree"],
                 "value": verdict["value"],
                 "target": verdict["target"],
                 "nbits": verdict["nbits"]}
            self.verifications.append(v)
            entry["verify"] = v
            if not verdict["meets_network_target"]:
                entry["refused"] = True
                self.trace.append(entry)
                raise RuntimeError(
                    "SHIM REFUSAL: candidate failed production "
                    f"verification: {verdict['classification']}/"
                    f"{verdict['reason']}")
        result = super().call(method, *params)
        if method == "getblocktemplate" and isinstance(result, dict):
            entry["template_height"] = result.get("height")
            entry["template_bits"] = result.get("bits")
            entry["template_prevhash"] = result.get(
                "previousblockhash")
        if method == "submitblock":
            entry["submit_result"] = result
        self.trace.append(entry)
        return result


def main():
    base = BitcoinRPC(host=RPC_HOST, port=RPC_PORT, user=RPC_USER,
                      password=RPC_PASSWORD)
    wallets = base.call("listwallets")
    if "stage95" not in wallets:
        base.call("createwallet", "stage95")
    wallet = BitcoinRPC(host=RPC_HOST, port=RPC_PORT, user=RPC_USER,
                        password=RPC_PASSWORD, wallet="stage95")
    payout = wallet.call("getnewaddress", "", "bech32")
    log.info("payout address (isolated node wallet): %s", payout)

    rpc = VerifyingRPC(host=RPC_HOST, port=RPC_PORT, user=RPC_USER,
                       password=RPC_PASSWORD)
    store = BlockStore(os.path.join(STAGE, "agent-store.db"))
    compute = ComputeEngine()
    agent = AutonomousMiner(rpc, payout, store=store,
                            compute=compute)
    # Launcher configuration 4: Stage 9.4 status publisher.
    agent.engine.status_publish = True
    agent.engine.status_interval_s = 0.25

    t0 = time.time()
    out = agent.run_cycles(5)
    t1 = time.time()

    record = {
        "launcher": "run_stage95.py",
        "started_ts": t0, "ended_ts": t1,
        "payout_address": payout,
        "chain": out["chain"],
        "backend": out["backend"],
        "fallback_reason": out["fallback_reason"],
        "benchmark_hs": out["benchmark_hs"],
        "cycles": out["cycles"],
        "decisions": out["decisions"],
        "summary": out["summary"],
        "engine_statistics": agent.engine.statistics.snapshot(),
        "status_events": list(agent.engine.status_events),
        "rpc_trace": rpc.trace,
        "verifications": rpc.verifications,
    }
    with open(os.path.join(STAGE, "run_output.json"), "w") as f:
        json.dump(record, f, indent=2)
    for c in out["cycles"]:
        print({k: c.get(k) for k in
               ("accepted", "height", "hash", "nonce", "hashes",
                "batches", "backend", "reason")})
    print(f"accepted: "
          f"{sum(1 for c in out['cycles'] if c.get('accepted'))}"
          f"/{len(out['cycles'])}")
    print("run_output.json written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
