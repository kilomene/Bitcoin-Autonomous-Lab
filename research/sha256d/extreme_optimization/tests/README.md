# tests/

Correctness tests for X-series experiments. The minimum gate
set for any candidate implementation, inherited from the
EXP-002 and EXP-003 protocol:

- FIPS SHA-256 vectors through any raw compression entry
  point.
- Genesis header: exact digest, and the counted search
  re-finds nonce 2083236893.
- At least 100,000 randomized SHA-256d differentials against
  hashlib, zero mismatches.
- Boundary nonces and ranges (0, 1, 0xFFFFFFFE, 0xFFFFFFFF,
  range ending exactly at 2^32, crossing range rejected).
- Template variations (merkle root, prevhash, version,
  timestamp, nBits varied independently).
- Target equality accepted, target minus one rejected,
  candidate set equal to a Python recount at an easy target.
- Exact attempted-hash accounting on miss and early exit.

Existing gate implementations to reuse: ../experiments/
h02_shani/test_h02.py and test_h01.py.
