"""One-shot JSON status snapshot from the real node.

Usage: python3 -m dashboard.status
Prints node, chain and latest-block data as JSON. This is the data
source a web dashboard would poll; Task 001 keeps it as a tested CLI
snapshot rather than shipping an untested web server.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.interface import AgentInterface


def snapshot():
    agent = AgentInterface()
    return {
        "node": agent.node_status(),
        "latest_block": agent.latest_block(),
    }


if __name__ == "__main__":
    print(json.dumps(snapshot(), indent=2))
