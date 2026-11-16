#!/usr/bin/env python3
"""Stage 8 regtest miner: the miner child of the ISOLATED
autopilot instance used by the Stage 8 autonomous
demonstration (stage8_demonstration.py).

This is a production-path miner, not a stub: it drives
mining.engine.MiningEngine (GBT template fetch, EXP-025
template cache, candidate construction, counted ComputeEngine
search, submitblock, best-chain acceptance) against the lab's
regtest node, with a production MiningStatistics instance and
the EXP-038 work checkpoint enabled. It is the GBT-path
counterpart of mining/mainnet_live.py (which is the Stratum
pool path and is never touched by Stage 8).

Difficulty amplification (EXP-040 scenario C technique,
disclosed wherever its figures are used): the regtest target
gives p = (T + 1) / 2^256 of about 0.5 per hash, so an
unamplified search_first stops after a couple of hashes and
no hash-rate measurement is possible. The miner therefore
wraps the ComputeEngine in a delegating proxy that divides
the SEARCH target by 2**AMPLIFY_SHIFT before delegating, so
each block search examines on the order of 2**(AMPLIFY_SHIFT
+ 1) hashes. Blocks found against the divided target
necessarily meet the real regtest target and are submitted
and accepted by Core normally; the engine's own acceptance
test (submitblock result plus best-chain equality) is
unchanged and is what decides the accepted flag recorded
here. The shift is a harness parameter, set by the
BAL_STAGE8_AMPLIFY_SHIFT environment variable (default 24,
the EXP-040 value); it changes only how long each search
runs, never what counts as a block.

Outputs, all inside the isolated instance:

- an evidence JSONL in the mining/stratum_client.Evidence
  schema (the same event schema mining/mainnet_live.py
  writes, so the agent awareness layer reads it unmodified):
  miner_start, status (with the MiningStatistics totals),
  block (one per accepted block), miner_idle and miner_stop
  events. Path: BAL_STAGE8_EVIDENCE.
- the EXP-038 work checkpoint at BAL_STAGE8_CHECKPOINT (the
  path the demonstration's MiningController reads).

Behaviour bounds: after BAL_STAGE8_MAX_BLOCKS accepted
blocks (default 0, unlimited) or BAL_STAGE8_MAX_SECONDS of
searching (default 0, unlimited), the miner stops searching
and idles, still publishing a status event every 10 s so the
autopilot's evidence-staleness watchdog sees a live miner,
until the autopilot stops it. It never exits on its own
inside those bounds: an exit would be relaunched by the
autopilot watchdog and recorded as a restart, which the
demonstration wants to attribute only to its deliberate
fault step.

Status republication: a StatusPublisher thread republishes
the statistics totals every 10 s (the mainnet_live status
cadence), so the awareness layer's rate observation can
bracket its windows even while a single search cycle runs
for minutes under contention. Run 1 of the demonstration
published only on cycle completion and its awareness rate
windows observed nothing; the publisher is the fix, and
run 2 is the recorded demonstration.
"""

import json
import os
import sys
import threading
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
sys.path.insert(0, ROOT)

from gpu.engine import ComputeEngine                  # noqa: E402
from mining.engine import MiningEngine                # noqa: E402
from mining.mining_statistics import MiningStatistics  # noqa: E402
from mining.stratum_client import Evidence            # noqa: E402
from node.rpc_client import BitcoinRPC                # noqa: E402

WALLET = "bal-regtest"


class AmplifiedCompute:
    """Delegating ComputeEngine proxy: divides the search
    target by 2**shift before delegating the counted and
    uncounted search entries (the EXP-040 TimingCompute
    shape, without the timing). Every other attribute,
    including backend and the thread-tuning surface,
    delegates to the real engine."""

    def __init__(self, real, shift):
        object.__setattr__(self, "_real", real)
        object.__setattr__(self, "_shift", int(shift))

    def _target(self, target):
        shift = object.__getattribute__(self, "_shift")
        return target >> shift if shift else target

    def search_first_counted(self, header, target, start,
                             count):
        real = object.__getattribute__(self, "_real")
        return real.search_first_counted(
            header, self._target(target), start, count)

    def search_first(self, header, target, start, count):
        real = object.__getattribute__(self, "_real")
        return real.search_first(
            header, self._target(target), start, count)

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_real"),
                       name)


class StatusPublisher(threading.Thread):
    """Periodic status republication, the shape
    mining/mainnet_live.py uses on the pool path (a status
    event every 10 s from its main loop). The GBT search
    cycle can run for minutes under contention, and the
    awareness layer's rate observation needs two distinct
    status events bracketing its window; publishing only on
    cycle completion starves it (measured in Stage 8 run 1:
    two 20-25 s windows fell inside single cycles and no
    rate was observable). This thread republishes the
    shared MiningStatistics totals every interval_s seconds;
    Evidence.log is lock-guarded, and MiningStatistics
    snapshots are plain dict copies, so a republished
    snapshot can lag the search thread's counters but never
    corrupts them."""

    def __init__(self, ev, stats, t0, interval_s=10.0):
        super().__init__(daemon=True)
        self._ev = ev
        self._stats = stats
        self._t0 = t0
        self._interval = interval_s
        self._stop_event = threading.Event()

    def run(self):
        while not self._stop_event.wait(self._interval):
            totals = self._stats.snapshot()["totals"]
            self._ev.log(
                "status", hashes=totals["backend_hashes"],
                rate=(totals["backend_hashes"]
                      / max(time.time() - self._t0, 1e-9)),
                submitted=totals["blocks_submitted"],
                statistics=totals, statistics_errors=0)

    def stop(self):
        self._stop_event.set()


def ensure_wallet(rpc):
    """The tests/test_regtest_integration.py pattern: load the
    lab regtest wallet, creating it only if it does not exist
    at all, and return a wallet-scoped client."""
    wallets = rpc.call("listwallets")
    if WALLET not in wallets:
        try:
            rpc.call("loadwallet", WALLET)
        except Exception:
            rpc.call("createwallet", WALLET)
    return BitcoinRPC(wallet=WALLET)


def main():
    evidence_path = os.environ["BAL_STAGE8_EVIDENCE"]
    checkpoint_path = os.environ["BAL_STAGE8_CHECKPOINT"]
    shift = int(os.environ.get("BAL_STAGE8_AMPLIFY_SHIFT",
                               "24"))
    max_blocks = int(os.environ.get("BAL_STAGE8_MAX_BLOCKS",
                                    "0"))
    max_seconds = float(os.environ.get(
        "BAL_STAGE8_MAX_SECONDS", "0"))
    os.makedirs(os.path.dirname(evidence_path), exist_ok=True)
    os.makedirs(os.path.dirname(checkpoint_path), exist_ok=True)

    rpc = BitcoinRPC()
    info = rpc.get_blockchain_info()
    if info["chain"] != "regtest":
        print(f"refusing to mine: chain is {info['chain']}, "
              "not regtest", flush=True)
        return 2
    wallet = ensure_wallet(rpc)
    address = wallet.call("getnewaddress", "stage8-demo")

    real_compute = ComputeEngine()
    compute = AmplifiedCompute(real_compute, shift)
    stats = MiningStatistics()
    engine = MiningEngine(
        rpc, address, compute=compute, statistics=stats,
        checkpoint_path=checkpoint_path)
    ev = Evidence(evidence_path)
    ev.log("miner_start", backend=real_compute.backend,
           address=address, amplify_shift=shift,
           start_height=info["blocks"], chain=info["chain"])

    t0 = time.time()
    publisher = StatusPublisher(ev, stats, t0)
    publisher.start()
    blocks = 0
    idle_logged = False
    while True:
        over_blocks = max_blocks and blocks >= max_blocks
        over_time = max_seconds and \
            (time.time() - t0) >= max_seconds
        if over_blocks or over_time:
            if not idle_logged:
                idle_logged = True
                ev.log("miner_idle", blocks=blocks,
                       reason=("max_blocks" if over_blocks
                               else "max_seconds"))
            totals = stats.snapshot()["totals"]
            ev.log("status", hashes=totals["backend_hashes"],
                   rate=(totals["backend_hashes"]
                         / max(time.time() - t0, 1e-9)),
                   submitted=totals["blocks_submitted"],
                   statistics=totals, statistics_errors=0)
            time.sleep(10)
            continue
        result = engine.mine_cycle(max_batches=100000,
                                   deadline_seconds=300)
        totals = stats.snapshot()["totals"]
        elapsed = max(time.time() - t0, 1e-9)
        ev.log("status", hashes=totals["backend_hashes"],
               rate=totals["backend_hashes"] / elapsed,
               submitted=totals["blocks_submitted"],
               statistics=totals, statistics_errors=0)
        if result.get("accepted"):
            blocks += 1
            ev.log("block", height=result["height"],
                   hash=result["hash"], nonce=result["nonce"],
                   hashes=result["hashes"], accepted=True,
                   checkpoint=result.get("checkpoint"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
