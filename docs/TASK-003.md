# Task 003: Independent Proof-of-Work Engine

Status: implemented and tested. Code: mining/pow_engine.py.
Tests: tests/test_pow_engine.py. Evidence: the cross-verification
count is recorded in evidence/regtest/task003-006-evidence.json.

## What it is

An implementation of Bitcoin header hashing that shares no code
with hashlib, OpenSSL, or Bitcoin Core:

- PureSHA256: FIPS 180-4 SHA-256 in pure Python, streaming with
  update, copy and digest. Validated against hashlib on randomized
  inputs at every padding edge length (55, 56, 57, 63, 64, 65, 119,
  120) and on the FIPS million-byte vector.
- compact_decode and compact_encode: Core SetCompact and GetCompact
  semantics with explicit negative and overflow flags.
- check_pow: Core CheckProofOfWork with reason codes (ok,
  header-length, negative-target, overflow-target, zero-target,
  target-above-limit, high-hash).
- difficulty and expected_hashes from the compact target.

## Verification evidence

- Six real mainnet headers (heights 0, 100000, 200000, 400000,
  600000, 800000; fixtures in tests/fixtures_mainnet_headers.json,
  fetched from the mempool.space API and re-verified locally by
  rehashing) all pass check_pow under the mainnet pow limit, and a
  nonce-tampered copy of block 100000 is rejected as high-hash.
- Every header of the live regtest chain is cross-verified against
  Core: the pure engine's hash equals the node's block hash and its
  PoW check passes, for the whole chain (163 blocks at the
  Tasks 003 to 006 milestone run, zero mismatches).
