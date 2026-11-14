#!/usr/bin/env python3
"""BAL network self-configuration.

Run at install time (scripts/install.sh) or standalone. The lab
has a small, fixed network shape, and this script makes the
machine it runs on suit that shape:

  * Mining is OUTBOUND ONLY: one TCP connection to the pool's
    Stratum endpoint (public-pool.io:21496). No inbound port is
    ever opened, forwarded or required.
  * Self-update and cloning need HTTPS to github.com and
    api.github.com. On VMs whose egress goes through a proxy,
    the proxy from the machine's own environment is detected
    and written into this repo's git config, so git (and the
    autopilot's self-update) uses the same door the machine
    itself uses.
  * The optional Bitcoin node needs outbound TCP 8333 to its
    pinned peers only (scripts/pin-peers.py); its RPC stays on
    localhost.

What it does: probes each endpoint, detects the proxy,
applies the git adaptation when a proxy exists, and writes a
report to .local/network.json (proxy credentials are never
recorded, only scheme, host and port). Exit code 0 means the
pool endpoint is reachable and mining can work here; exit 2
means it is not, and activation must not claim otherwise.

Usage: python3 scripts/network_setup.py [--check-only]
"""

import json
import os
import socket
import subprocess
import sys
import time
from urllib.parse import urlparse

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REPORT = os.path.join(ROOT, ".local", "network.json")

ENDPOINTS = [
    ("public-pool.io", 21496, "stratum pool (mining)", True),
    ("github.com", 443, "clone and self-update", False),
    ("api.github.com", 443, "update checks", False),
    ("seed.bitcoin.sipa.be", 8333, "node peers (optional)", False),
]


def tcp_probe(host, port, timeout=5.0):
    t0 = time.time()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, None, (time.time() - t0) * 1000
    except OSError as exc:
        return False, f"{exc.__class__.__name__}: {exc}", None


def proxy_from_env():
    for key in ("https_proxy", "HTTPS_PROXY", "http_proxy",
                "HTTP_PROXY"):
        val = os.environ.get(key)
        if val:
            p = urlparse(val if "//" in val else "//" + val)
            hostport = p.hostname or ""
            if p.port:
                hostport += f":{p.port}"
            return {"present": True, "env": key,
                    "endpoint": f"{p.scheme or 'http'}://{hostport}"}
    return {"present": False, "env": None, "endpoint": None}


def git_proxy_adapt(proxy_url):
    """Point this repo's git at the machine's proxy (idempotent)."""
    changes = []
    try:
        for key in ("http.proxy", "https.proxy"):
            cur = subprocess.run(
                ["git", "config", "--local", "--get", key],
                cwd=ROOT, capture_output=True, text=True)
            if cur.stdout.strip() != proxy_url:
                subprocess.run(["git", "config", "--local", key,
                                proxy_url], cwd=ROOT, check=True)
                changes.append(f"git {key} set from machine proxy")
    except (OSError, subprocess.CalledProcessError) as exc:
        changes.append(f"git proxy adaptation skipped: {exc}")
    return changes


def main():
    check_only = "--check-only" in sys.argv
    proxy = proxy_from_env()
    results = []
    pool_ok = False
    for host, port, purpose, required in ENDPOINTS:
        ok, err, ms = tcp_probe(host, port)
        results.append({"host": host, "port": port,
                        "purpose": purpose, "required": required,
                        "tcp_ok": ok, "error": err,
                        "rtt_ms": round(ms, 1) if ms else None})
        if required:
            pool_ok = ok
        print(f"{'ok  ' if ok else 'FAIL'} {host}:{port} "
              f"({purpose})" + ("" if ok else f"  {err}"))
    adaptations = []
    raw_proxy = None
    if proxy["present"]:
        for key in ("https_proxy", "HTTPS_PROXY", "http_proxy",
                    "HTTP_PROXY"):
            if os.environ.get(key):
                raw_proxy = os.environ[key]
                break
        print(f"proxy detected via {proxy['env']}: "
              f"{proxy['endpoint']}")
        if not check_only and raw_proxy:
            adaptations = git_proxy_adapt(raw_proxy)
            for a in adaptations:
                print(f"adapt: {a}")
    else:
        print("no proxy in environment; direct egress assumed")
    report = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "hostname": socket.gethostname(),
        "proxy": proxy,
        "endpoints": results,
        "adaptations": adaptations,
        "pool_reachable": pool_ok,
        "inbound_required": False,
    }
    if check_only:
        print(json.dumps(report, indent=2))
    else:
        os.makedirs(os.path.dirname(REPORT), exist_ok=True)
        with open(REPORT, "w") as f:
            json.dump(report, f, indent=2)
        print(f"report written to .local/network.json")
    if not pool_ok:
        print("POOL ENDPOINT UNREACHABLE: this machine cannot "
              "mine until outbound TCP to the pool is possible.",
              file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
