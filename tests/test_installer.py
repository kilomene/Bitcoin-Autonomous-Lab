#!/usr/bin/env python3
"""Installer and network self-configuration tests.

The dry run must describe the full setup and activation plan;
the network probe must produce a structured report naming the
pool endpoint and a boolean verdict, without recording proxy
credentials and without writing files in check-only mode.
"""

import json
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def main():
    out = subprocess.run(["bash", "scripts/install.sh", "--dry-run"],
                         cwd=ROOT, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    for needle in ("build", "network", "smoke", "service",
                   "activate", "hostname"):
        assert needle in out.stdout, (needle, out.stdout)
    print("ok: installer dry run describes build, network, "
          "smoke, service, activation")

    report_path = os.path.join(ROOT, ".local", "network.json")
    before = (os.path.getmtime(report_path)
              if os.path.exists(report_path) else None)
    out = subprocess.run(
        [sys.executable, "scripts/network_setup.py", "--check-only"],
        cwd=ROOT, capture_output=True, text=True, timeout=90)
    # Exit 2 is a legitimate verdict (pool unreachable); the
    # report must still be structured and complete.
    assert out.returncode in (0, 2), (out.returncode, out.stderr)
    start = out.stdout.index("{")
    report = json.loads(out.stdout[start:])
    assert report["inbound_required"] is False
    hosts = {e["host"]: e for e in report["endpoints"]}
    assert "public-pool.io" in hosts
    assert isinstance(hosts["public-pool.io"]["tcp_ok"], bool)
    assert report["pool_reachable"] == hosts["public-pool.io"]["tcp_ok"]
    if report["proxy"]["present"]:
        ep = report["proxy"]["endpoint"]
        assert "@" not in ep, ep  # credentials never recorded
    after = (os.path.getmtime(report_path)
             if os.path.exists(report_path) else None)
    assert before == after, "check-only mode must not write the report"
    print("ok: network probe reports structured verdicts, "
          "records no credentials, writes nothing when checking")
    print("ALL INSTALLER TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
