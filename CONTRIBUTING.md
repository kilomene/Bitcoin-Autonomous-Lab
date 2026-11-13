# Contributing

Bitcoin Autonomous Lab is developed task by task, with evidence.

## Rules that do not bend

- Never commit secrets: no RPC passwords, no private keys, no wallet
  files. Local node data lives in .local/ and is gitignored.
- Never present simulated data as real Bitcoin data. Every functional
  claim needs a test run or an evidence file in evidence/.
- Test on Regtest for chain work. Mainnet experiments require an
  explicit owner instruction naming them.
- Keep dependencies minimal. The Python code uses the standard library
  unless a change records why in docs/ARCHITECTURE.md.
- Run the tests before pushing:

  make test
  python3 tests/test_regtest_integration.py

- Do not use the long dash character in project documents. Use commas,
  colons, or brackets.

## Workflow

1. Work in small, verified steps. A component is not done until its
   test passes on this machine.
2. Record results in evidence/ or in the task document under docs/.
3. Update docs/ARCHITECTURE.md when a decision changes.
