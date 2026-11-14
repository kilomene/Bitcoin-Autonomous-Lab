#!/usr/bin/env python3
"""Pin the mainnet node to the peers it is already connected to.

Why: a syncing Bitcoin Core keeps dialing brand new peer IPs.
On hosts where outbound connections need a human approval per
destination (some agent runtimes gate network access per IP),
every new peer is a fresh approval card, forever. Pinning the
node with connect= lines makes it talk only to a fixed peer
set, approved once. Run this once the node has peers, then
restart the node (systemctl restart bal-bitcoind, or stop it
and let your supervisor start it).

Usage: python3 scripts/pin-peers.py [--max 8]
Reads peers through bitcoin-cli getpeerinfo, prefers outbound
full-relay and manually pinned (connect=) peers that are
furthest synced, rewrites the connect= lines in
.local/mainnet/bitcoin.conf in place (everything else in the
file is preserved).
"""

import argparse
import json
import os
import subprocess
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
DEFAULT_DATADIR = os.path.join(ROOT, ".local", "mainnet")
DEFAULT_CLI = os.path.expanduser(
    "~/workspace/bitcoin-core-dist/bitcoin-core-28.1/bin/bitcoin-cli")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--datadir", default=DEFAULT_DATADIR)
    ap.add_argument("--cli", default=DEFAULT_CLI)
    ap.add_argument("--max", type=int, default=8)
    args = ap.parse_args()

    conf = os.path.join(args.datadir, "bitcoin.conf")
    if not os.path.exists(conf):
        print(f"no bitcoin.conf at {conf}", file=sys.stderr)
        return 1
    out = subprocess.run(
        [args.cli, f"-datadir={args.datadir}", "getpeerinfo"],
        capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        print("bitcoin-cli getpeerinfo failed (node running?):",
              out.stderr.strip(), file=sys.stderr)
        return 1
    peers = json.loads(out.stdout)
    cand = [p for p in peers
            if p.get("connection_type") in
            ("outbound-full-relay", "manual")]
    cand.sort(key=lambda p: -(p.get("synced_blocks") or 0))
    addrs = [p["addr"] for p in cand[:args.max]]
    if not addrs:
        print("no outbound peers yet; let the node connect first",
              file=sys.stderr)
        return 1
    lines = [l for l in open(conf).read().splitlines()
             if not l.startswith("connect=")]
    lines += [f"connect={a}" for a in addrs]
    with open(conf, "w") as f:
        f.write("\n".join(lines) + "\n")
    os.chmod(conf, 0o600)
    print(f"pinned {len(addrs)} peers in {conf}:")
    for a in addrs:
        print(f"  connect={a}")
    print("restart the node for this to take effect")
    return 0


if __name__ == "__main__":
    sys.exit(main())
