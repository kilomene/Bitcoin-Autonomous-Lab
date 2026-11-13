"""Lifecycle management for the Lab's Bitcoin Core Regtest node.

Design decisions:

- The node runs ONLY in Regtest mode for Task 001 and Task 002.
- Data lives in .local/regtest/ inside the repository working tree.
  That directory is gitignored: chain data, the bitcoin.conf with its
  RPC password, and the node-config.json used by rpc_client all stay
  local and are never committed.
- RPC credentials are generated per machine with `secrets` on first
  setup. Nothing secret is hardcoded or printed to logs.
- Bitcoin Core binaries are resolved from BAL_BITCOIND env var, then
  from the local distribution directory recorded at setup time in
  .local/regtest/node-config.json ("bitcoind" key), then from PATH.

CLI:
    python3 -m node.node_manager setup|start|stop|status
"""

import json
import logging
import os
import secrets
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

log = logging.getLogger("bal.node.manager")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_DIR = os.path.join(REPO, ".local", "regtest")
CONFIG_JSON = os.path.join(LOCAL_DIR, "node-config.json")
DATADIR = os.path.join(LOCAL_DIR, "data")
RPC_PORT = 18443
P2P_PORT = 18444


def find_bitcoind():
    env = os.environ.get("BAL_BITCOIND")
    if env and os.path.exists(env):
        return env
    cfg = _read_config()
    if cfg and cfg.get("bitcoind") and os.path.exists(cfg["bitcoind"]):
        return cfg["bitcoind"]
    # Common local distribution location used by scripts/setup-bitcoin-core.sh
    dist = os.path.expanduser("~/workspace/bitcoin-core-dist")
    if os.path.isdir(dist):
        for name in sorted(os.listdir(dist)):
            cand = os.path.join(dist, name, "bin", "bitcoind")
            if os.path.exists(cand):
                return cand
    from shutil import which
    return which("bitcoind")


def _read_config():
    if os.path.exists(CONFIG_JSON):
        with open(CONFIG_JSON) as f:
            return json.load(f)
    return None


def setup(bitcoind=None):
    """Create local dirs and config on first run. Idempotent."""
    os.makedirs(DATADIR, exist_ok=True)
    cfg = _read_config()
    if cfg is None:
        cfg = {
            "host": "127.0.0.1",
            "port": RPC_PORT,
            "rpcuser": "balrpc",
            "rpcpassword": secrets.token_hex(24),
            "bitcoind": bitcoind or find_bitcoind(),
            "network": "regtest",
        }
        fd = os.open(CONFIG_JSON, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(cfg, f, indent=2)
        log.info("wrote local node config at %s (credentials not shown)",
                 CONFIG_JSON)
    conf = os.path.join(DATADIR, "bitcoin.conf")
    if not os.path.exists(conf):
        with open(conf, "w") as f:
            f.write(
                "regtest=1\n"
                "server=1\n"
                "daemon=1\n"
                "txindex=1\n"
                "fallbackfee=0.0002\n"
                f"rpcport={RPC_PORT}\n"
                f"port={P2P_PORT}\n"
                f"rpcuser={cfg['rpcuser']}\n"
                f"rpcpassword={cfg['rpcpassword']}\n"
                "rpcallowip=127.0.0.1\n"
                "listen=0\n"
                "[regtest]\n"
                f"rpcport={RPC_PORT}\n"
                f"port={P2P_PORT}\n"
            )
        os.chmod(conf, 0o600)
        log.info("wrote bitcoin.conf for regtest at %s", conf)
    return cfg


def is_running():
    from node.rpc_client import BitcoinRPC, RpcConnectionError, RpcError
    try:
        BitcoinRPC(timeout=3, retries=1).get_block_count()
        return True
    except (RpcConnectionError, RpcError, Exception):
        return False


def start(wait_seconds=60):
    cfg = setup()
    if is_running():
        log.info("node already running")
        return cfg
    bitcoind = cfg.get("bitcoind") or find_bitcoind()
    if not bitcoind:
        raise RuntimeError(
            "bitcoind not found. Run scripts/setup-bitcoin-core.sh first "
            "or set BAL_BITCOIND.")
    cmd = [bitcoind, f"-datadir={DATADIR}",
           f"-conf={os.path.join(DATADIR, 'bitcoin.conf')}"]
    log.info("starting bitcoind: %s", " ".join(cmd))
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        if is_running():
            log.info("node is up")
            return cfg
        time.sleep(0.5)
    raise RuntimeError("bitcoind started but RPC did not answer in time")


def stop():
    from node.rpc_client import BitcoinRPC, RpcConnectionError
    try:
        BitcoinRPC(timeout=5, retries=1).call("stop")
        log.info("stop requested")
    except RpcConnectionError:
        log.info("node was not reachable, nothing to stop")
    for _ in range(40):
        if not is_running():
            return True
        time.sleep(0.5)
    return False


def status():
    from node.rpc_client import BitcoinRPC
    if not is_running():
        return {"running": False}
    rpc = BitcoinRPC()
    info = rpc.get_blockchain_info()
    return {
        "running": True,
        "chain": info["chain"],
        "blocks": info["blocks"],
        "headers": info["headers"],
        "bestblockhash": info["bestblockhash"],
        "difficulty": info["difficulty"],
        "verificationprogress": info["verificationprogress"],
    }


def main(argv):
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    if not argv:
        print(__doc__)
        return 2
    action = argv[0]
    if action == "setup":
        cfg = setup()
        print(json.dumps({"configured": True, "bitcoind": cfg.get("bitcoind"),
                          "network": "regtest", "rpc_port": RPC_PORT}, indent=2))
    elif action == "start":
        start()
        print(json.dumps(status(), indent=2))
    elif action == "stop":
        print(json.dumps({"stopped": stop()}, indent=2))
    elif action == "status":
        print(json.dumps(status(), indent=2))
    else:
        print(f"unknown action: {action}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
