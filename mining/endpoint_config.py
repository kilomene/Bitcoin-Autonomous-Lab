"""Stratum endpoint configuration for mainnet mining.

One small JSON file, .local/mining-endpoint.json, decides where
the miner points. It exists so the solo cutover (see
docs/SOLO_CUTOVER.md) is a config flip performed by a script,
never a code edit at fire time:

    mode "pool": public-pool.io:21496 (the behaviour since
                 2026-11-13, and the default when the file is
                 absent, unreadable, or names an unknown mode)
    mode "solo": the lab's own solo server (mining/solo_mainnet.py)
                 on 127.0.0.1:3333, fed by our own mainnet node

Resolution order for mainnet_live.py: explicit --pool-host /
--pool-port arguments, then BAL_POOL_HOST / BAL_POOL_PORT
environment variables, then this file, then the pool default.
The autopilot needs no endpoint logic of its own: the miner
reads this file at every (re)start, and the autopilot restarts
the miner, so a flip plus a miner restart is the whole switch.

The file lives in .local (gitignored, machine-local deployment
state). Code ships in the repo; the mode flag does not.
"""

import json
import os

ROOT = os.path.join(os.path.dirname(__file__), "..")
CONFIG_PATH = os.path.join(ROOT, ".local", "mining-endpoint.json")
MAINNET_NODE_CONFIG = os.path.join(ROOT, ".local", "mainnet",
                                   "node-config.json")
LAB_PAYOUT_ADDRESS = "bc1q528egeqsvv8aa382j43edxskqw6x7zxc2xpcf3"

POOL_HOST = "public-pool.io"
POOL_PORT = 21496
SOLO_HOST = "127.0.0.1"
SOLO_PORT = 3333
# Share difficulty for our own solo server. At the v512 session
# rate measured on this VM (about 12.5M H/s), difficulty d gives
# an expected share every d * 2^32 / rate seconds: 0.02 lands at
# about 7 seconds (about 14 seconds even at half that rate),
# frequent enough to show continuous worker activity, sparse
# enough that share handling is negligible load. The pool floor
# of difficulty 1 is about 5.7 minutes at the same rate, which
# is exactly the blink-off-the-dashboard gap this replaces.
SOLO_SHARE_DIFFICULTY = 0.02

# Solo vardiff parameters (Stage 6 integration of the decided
# R-12 design, research/vardiff/DESIGN.md section 4). These are
# the declared operating point of the control law; under
# vardiff, SOLO_SHARE_DIFFICULTY becomes the INITIAL difficulty
# each new connection starts at. Vardiff is disabled by default
# in the config below: the armed cutover keeps today's fixed-
# difficulty behaviour until the integration gates (DESIGN.md
# section 9 step 5, including the independent audit) have all
# passed and an operator enables it here.
SOLO_VARDIFF_TARGET_INTERVAL = 15.0
SOLO_VARDIFF_FLOOR = 0.002
SOLO_VARDIFF_CEILING = 1.0
SOLO_VARDIFF_EMA_ALPHA = 0.35
SOLO_VARDIFF_DEADBAND = 1.25
SOLO_VARDIFF_UP_HYSTERESIS_S = 30.0
SOLO_VARDIFF_UP_CONFIRMATIONS = 2
SOLO_VARDIFF_MAX_UP_FACTOR = 1.5
SOLO_VARDIFF_MAX_DOWN_FACTOR = 2.0
SOLO_VARDIFF_DECAY_AFTER_S = 60.0
SOLO_VARDIFF_DECAY_FACTOR = 2.0

SOLO_VARDIFF_DEFAULTS = {
    "enabled": False,
    "target_interval": SOLO_VARDIFF_TARGET_INTERVAL,
    "floor": SOLO_VARDIFF_FLOOR,
    "ceiling": SOLO_VARDIFF_CEILING,
    "ema_alpha": SOLO_VARDIFF_EMA_ALPHA,
    "deadband": SOLO_VARDIFF_DEADBAND,
    "up_hysteresis_s": SOLO_VARDIFF_UP_HYSTERESIS_S,
    "up_confirmations": SOLO_VARDIFF_UP_CONFIRMATIONS,
    "max_up_factor": SOLO_VARDIFF_MAX_UP_FACTOR,
    "max_down_factor": SOLO_VARDIFF_MAX_DOWN_FACTOR,
    "decay_after_s": SOLO_VARDIFF_DECAY_AFTER_S,
    "decay_factor": SOLO_VARDIFF_DECAY_FACTOR,
}

DEFAULT_CONFIG = {
    "mode": "pool",
    "pool": {"host": POOL_HOST, "port": POOL_PORT},
    "solo": {"host": SOLO_HOST, "port": SOLO_PORT,
             "share_difficulty": SOLO_SHARE_DIFFICULTY,
             "vardiff": dict(SOLO_VARDIFF_DEFAULTS)},
    "payout_address": LAB_PAYOUT_ADDRESS,
}


def solo_vardiff_config(cfg=None):
    """The merged vardiff settings from an endpoint config
    (defaults when cfg is None or carries no vardiff section).
    Pure data; mining/solo_mainnet.py turns it into a
    VarDiffController when "enabled" is true."""
    out = dict(SOLO_VARDIFF_DEFAULTS)
    if cfg is None:
        cfg = load_config()
    solo = cfg.get("solo") if isinstance(cfg, dict) else None
    vd = solo.get("vardiff") if isinstance(solo, dict) else None
    if isinstance(vd, dict):
        for key, val in vd.items():
            if key in out and val is not None:
                out[key] = val
    return out


def _merged(cfg):
    out = json.loads(json.dumps(DEFAULT_CONFIG))
    if isinstance(cfg, dict):
        for key, val in cfg.items():
            if isinstance(val, dict) and isinstance(out.get(key), dict):
                out[key].update(val)
            elif val is not None:
                out[key] = val
    if out.get("mode") not in ("pool", "solo"):
        out["mode"] = "pool"
    return out


def load_config(path=None):
    """Endpoint config merged over defaults. Never raises: a
    missing or corrupt file means the pool default, which is
    today's behaviour."""
    path = path or CONFIG_PATH
    try:
        with open(path) as f:
            return _merged(json.load(f))
    except (OSError, ValueError):
        return _merged(None)


def write_config(cfg, path=None):
    """Atomically write the endpoint config (0600, it sits next
    to other machine-local mining state)."""
    path = path or CONFIG_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def set_mode(mode, path=None):
    """Flip only the mode field, preserving everything else.
    This is the entire cutover switch, and the entire rollback."""
    if mode not in ("pool", "solo"):
        raise ValueError(f"unknown endpoint mode {mode!r}")
    cfg = load_config(path)
    cfg["mode"] = mode
    write_config(cfg, path)
    return cfg


def resolve_endpoint(cli_host=None, cli_port=None, env=None,
                     path=None):
    """(host, port, mode, config) for mainnet_live.py.

    Precedence: CLI arguments, environment, config file mode,
    pool default."""
    env = os.environ if env is None else env
    cfg = load_config(path)
    mode = cfg["mode"]
    host = cli_host or env.get("BAL_POOL_HOST")
    port = cli_port or env.get("BAL_POOL_PORT")
    if host or port:
        base = cfg["pool"] if mode == "pool" else cfg["solo"]
        host = host or base["host"]
        port = int(port or base["port"])
        return host, port, mode, cfg
    base = cfg["pool"] if mode == "pool" else cfg["solo"]
    return base["host"], int(base["port"]), mode, cfg


def load_mainnet_rpc(path=None):
    """BitcoinRPC for our pruned mainnet node, built from
    .local/mainnet/node-config.json. That file's schema
    (rpc_user / rpc_password / rpc_port / chain) predates the
    regtest schema rpc_client loads by itself, so the mapping
    is explicit here, following mining/testnet4_attempt.py.
    Credentials are read in-process only, never printed."""
    from node.rpc_client import BitcoinRPC
    path = path or MAINNET_NODE_CONFIG
    with open(path) as f:
        cfg = json.load(f)
    secret = cfg["rpc_password"]
    return BitcoinRPC(cfg.get("rpc_host", "127.0.0.1"),
                      int(cfg["rpc_port"]), cfg["rpc_user"], secret)
