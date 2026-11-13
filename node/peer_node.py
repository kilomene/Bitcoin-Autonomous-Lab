"""A second regtest node, peered with the lab node.

Runs its own bitcoind with its own datadir and ports (RPC 18543,
P2P 18544), connects to the primary node (P2P 18444) with addnode,
and exposes its own RPC client sharing the primary node's
credentials. Used to prove block propagation, cross-node monitoring
and multi-node resilience: work mined on node 1 must arrive,
validate and become visible on node 2 with no shared state at all
except the peer connection.
"""

import json
import os
import subprocess
import time

from node.node_manager import _read_config, find_bitcoind
from node.rpc_client import BitcoinRPC

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL = os.path.join(ROOT, ".local", "regtest2")
DATADIR = os.path.join(LOCAL, "data")
CONFIG = os.path.join(LOCAL, "node-config.json")
RPC_PORT = 18543
P2P_PORT = 18544
PRIMARY_P2P = "127.0.0.1:18444"


def setup():
    os.makedirs(DATADIR, exist_ok=True)
    primary = _read_config()
    user = primary["rpcuser"]
    password = primary["rpcpassword"]
    conf = os.path.join(DATADIR, "bitcoin.conf")
    if not os.path.exists(conf):
        with open(conf, "w") as f:
            f.write(
                "regtest=1\n"
                "server=1\n"
                "daemon=1\n"
                "txindex=1\n"
                "fallbackfee=0.0002\n"
                f"rpcuser={user}\n"
                f"rpcpassword={password}\n"
                "rpcallowip=127.0.0.1\n"
                "[regtest]\n"
                "listen=1\n"
                "bind=127.0.0.1\n"
                "rpcbind=127.0.0.1\n"
                f"rpcport={RPC_PORT}\n"
                f"port={P2P_PORT}\n")
        os.chmod(conf, 0o600)
    if not os.path.exists(CONFIG):
        with open(CONFIG, "w") as f:
            json.dump({"host": "127.0.0.1", "port": RPC_PORT,
                       "rpcuser": user, "rpcpassword": password}, f)
        os.chmod(CONFIG, 0o600)
    return CONFIG


def client():
    setup()
    cfg = json.load(open(CONFIG))
    return BitcoinRPC(host=cfg["host"], port=cfg["port"],
                      user=cfg["rpcuser"], password=cfg["rpcpassword"])


def is_running():
    try:
        client().get_block_count()
        return True
    except Exception:
        return False


def start(wait_seconds=60):
    setup()
    if is_running():
        return True
    bitcoind = find_bitcoind()
    subprocess.Popen(
        [bitcoind, f"-datadir={DATADIR}",
         f"-conf={os.path.join(DATADIR, 'bitcoin.conf')}", "-daemon"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        if is_running():
            return True
        time.sleep(0.5)
    return False


def connect_to_primary():
    """Peer the two nodes. The primary node runs with listen=0, so
    the connection is established outbound from the primary to this
    node (which listens): addnode is issued on the primary."""
    from node.rpc_client import BitcoinRPC as PrimaryRPC
    primary = PrimaryRPC()
    try:
        primary.call("addnode", f"127.0.0.1:{P2P_PORT}", "add")
    except Exception:
        pass  # already added
    rpc = client()
    deadline = time.time() + 20
    peers = rpc.call("getpeerinfo")
    while not peers and time.time() < deadline:
        time.sleep(0.5)
        peers = rpc.call("getpeerinfo")
    return peers


def stop():
    try:
        client().call("stop")
    except Exception:
        pass
