# Task 001: Foundation and Bitcoin Regtest

Status: implemented and tested on the Lab VM. Evidence:
evidence/regtest/task001-evidence.json and the test output quoted in
the completion report.

## Setup instructions

1. Install Bitcoin Core (checksum verified, outside the repo):

   scripts/setup-bitcoin-core.sh 28.1

2. Configure and start the Regtest node (first run generates local
   RPC credentials under .local/regtest, gitignored):

   python3 -m node.node_manager setup
   python3 -m node.node_manager start
   python3 -m node.node_manager status

3. Use the agent interface:

   python3 -m agent.interface status
   python3 -m agent.interface height
   python3 -m agent.interface latest
   python3 -m agent.interface generate 5
   python3 -m dashboard.status

4. Run the tests:

   make test
   python3 tests/test_regtest_integration.py --evidence

5. Stop the node:

   python3 -m node.node_manager stop

## Milestone checklist

- Start a local Bitcoin Core node: done, via node_manager (daemon
  mode, Regtest, txindex on, listen off, RPC on 18443 localhost only).
- Connect through JSON-RPC: done, node/rpc_client.py.
- getblockchaininfo: done, asserted chain == regtest in tests.
- Current block count: done, getblockcount.
- generatetoaddress: done, 12 blocks per integration run, height
  increases verified exactly.
- getblock: done, tip block verified against its previous block.
- Node recognizes generated blocks: done, bestblockhash equals the
  last generated hash; getblockheader and getchaintips agree.

## Restrictions honored in this task

- No real Bitcoin mining started. The earlier mainnet long run was
  stopped when this task arrived; its partial log is preserved in
  evidence/ with the stop recorded in the summary.
- No mainnet connection for experiments. The Regtest node has
  listen=0 and its own datadir.
- No purchased infrastructure. Bitcoin Core is free software; the
  download is $0.
- No GPU mining. gpu/ holds only the research gate note.
