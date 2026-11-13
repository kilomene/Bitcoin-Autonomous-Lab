"""JSON-RPC client for Bitcoin Core.

Credentials are never hardcoded and never logged. They are resolved in
this order:

1. Environment variables BAL_RPC_USER, BAL_RPC_PASSWORD, BAL_RPC_HOST,
   BAL_RPC_PORT.
2. The local node configuration written by node_manager into
   .local/regtest/node-config.json (file permissions 0600, inside the
   gitignored .local directory).

All calls go through one method so timeouts, retries and error handling
stay consistent. RPC errors raise RpcError with the Core error message.
Transport failures raise RpcConnectionError after retries.
"""

import base64
import json
import logging
import os
import time
import urllib.error
import urllib.request

log = logging.getLogger("bal.node.rpc")

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18443  # Bitcoin Core regtest RPC port


class RpcError(Exception):
    """Bitcoin Core returned a JSON-RPC error object."""

    def __init__(self, method, code, message):
        super().__init__(f"RPC {method} failed: [{code}] {message}")
        self.method = method
        self.code = code
        self.rpc_message = message


class RpcConnectionError(Exception):
    """The node could not be reached after retries."""


class RpcConfigError(Exception):
    """RPC credentials are not configured."""


def _load_local_config():
    path = os.environ.get("BAL_NODE_CONFIG")
    if not path:
        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(repo, ".local", "regtest", "node-config.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None


class BitcoinRPC:
    def __init__(self, host=None, port=None, user=None, password=None,
                 timeout=30, retries=3, wallet=None):
        cfg = _load_local_config() or {}
        self.host = host or os.environ.get("BAL_RPC_HOST") or cfg.get("host") or DEFAULT_HOST
        self.port = int(port or os.environ.get("BAL_RPC_PORT") or cfg.get("port") or DEFAULT_PORT)
        self.user = user or os.environ.get("BAL_RPC_USER") or cfg.get("rpcuser")
        self.password = password or os.environ.get("BAL_RPC_PASSWORD") or cfg.get("rpcpassword")
        if not self.user or not self.password:
            raise RpcConfigError(
                "RPC credentials not configured. Start the node with "
                "node.node_manager first (it generates a local config), "
                "or set BAL_RPC_USER and BAL_RPC_PASSWORD.")
        self.timeout = timeout
        self.retries = retries
        self.wallet = wallet
        self._id = 0

    @property
    def url(self):
        base = f"http://{self.host}:{self.port}"
        if self.wallet:
            return f"{base}/wallet/{self.wallet}"
        return base

    def call(self, method, *params):
        """Call one RPC method. Returns the result value."""
        self._id += 1
        payload = json.dumps({
            "jsonrpc": "1.0",
            "id": f"bal-{self._id}",
            "method": method,
            "params": list(params),
        }).encode()
        auth = base64.b64encode(
            f"{self.user}:{self.password}".encode()).decode()
        last_exc = None
        for attempt in range(1, self.retries + 1):
            req = urllib.request.Request(self.url, data=payload, method="POST")
            req.add_header("Content-Type", "application/json")
            req.add_header("Authorization", f"Basic {auth}")
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    body = json.loads(resp.read().decode())
                break
            except urllib.error.HTTPError as exc:
                raw = exc.read().decode(errors="replace")
                try:
                    body = json.loads(raw)
                except json.JSONDecodeError:
                    raise RpcError(method, exc.code, raw[:200]) from exc
                break
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_exc = exc
                log.warning("RPC %s attempt %d/%d failed: %s",
                            method, attempt, self.retries, exc)
                if attempt < self.retries:
                    time.sleep(min(2 ** attempt, 8))
                continue
        else:
            raise RpcConnectionError(
                f"Could not reach Bitcoin Core at {self.host}:{self.port} "
                f"after {self.retries} attempts: {last_exc}")

        if body.get("error"):
            err = body["error"]
            raise RpcError(method, err.get("code"), err.get("message"))
        log.debug("RPC %s ok", method)
        return body.get("result")

    # Typed convenience wrappers used across the Lab.
    def get_blockchain_info(self):
        return self.call("getblockchaininfo")

    def get_block_count(self):
        return self.call("getblockcount")

    def get_best_block_hash(self):
        return self.call("getbestblockhash")

    def get_block_hash(self, height):
        return self.call("getblockhash", height)

    def get_block(self, blockhash, verbosity=1):
        return self.call("getblock", blockhash, verbosity)

    def get_block_header(self, blockhash, verbose=True):
        return self.call("getblockheader", blockhash, verbose)

    def get_chain_tips(self):
        return self.call("getchaintips")
