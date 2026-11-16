"""Command line entry for the agent intelligence package.

    python3 -m agent.intelligence status

prints the live mining status summary (read-only), composed
from the autopilot heartbeat and the evidence census exactly
as inspect_status returns them. Also available: machine and
backends (read-only), gap <rate_hs> for the objective gap
report at a caller-supplied measured rate, and awareness
[window_s] for the Milestone 2 live awareness operational
report (read-only; never touches the miner).
"""

import json
import os
import sys
from dataclasses import asdict

sys.path.insert(0, os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..")))

from agent.intelligence import Agent


def main(argv):
    agent = Agent()
    cmd = argv[0] if argv else "status"
    if cmd == "status":
        print(json.dumps(asdict(agent.status()), indent=2,
                         default=str))
    elif cmd == "machine":
        print(json.dumps(asdict(agent.interface.inspect_machine()),
                         indent=2, default=str))
    elif cmd == "backends":
        print(json.dumps(asdict(agent.interface.inspect_backends()),
                         indent=2, default=str))
    elif cmd == "gap" and len(argv) > 1:
        print(json.dumps(agent.gap_report(float(argv[1])),
                         indent=2, default=str))
    elif cmd == "awareness":
        from agent.intelligence.awareness import Awareness
        window = float(argv[1]) if len(argv) > 1 else 30.0
        report = Awareness(agent).observe_cycle(window_s=window)
        print(json.dumps(report, indent=2, default=str))
    elif cmd == "mode":
        print(json.dumps(agent.mode(), indent=2, default=str))
    elif cmd == "control-status":
        from dataclasses import asdict as _asdict
        result = agent.interface.resolved_controller.status()
        print(json.dumps(_asdict(result), indent=2,
                         default=str))
    else:
        print("usage: python3 -m agent.intelligence "
              "[status|machine|backends|gap <rate_hs>|"
              "awareness [window_s]|mode|control-status]",
              file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
