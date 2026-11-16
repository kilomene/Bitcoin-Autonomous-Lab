# SHA-256d Differential Verification

Stage 1 of the NOVA SHA-X Extreme Research mandate.
Correctness verification of the reference implementation
(tools/sha256d_reference.py) against hashlib and against the
production ComputeEngine batch path, plus target-decoding
and verdict agreement against the production proof-of-work
code. Correctness runs only; no timing is reported.

Environment: this VM (AMD EPYC 9D25 guest, about 2 effective
CPUs), Python 3.12.3, Bitcoin Core 28.1 binaries for block
fetching. Production backend selected by ComputeEngine auto
dispatch: v512dual. Runs executed 2026-11-16 (UTC).

## 1. Commands

```
python3 research/EXTREME_RESEARCH/tools/sha256d_reference.py
python3 research/EXTREME_RESEARCH/tools/header_reconstruction.py --genesis
python3 research/EXTREME_RESEARCH/tools/header_reconstruction.py --mainnet-height 450150
python3 research/EXTREME_RESEARCH/tools/header_reconstruction.py --mainnet-height 450160
python3 research/EXTREME_RESEARCH/tools/header_reconstruction.py --regtest-height 1491
python3 research/EXTREME_RESEARCH/tools/differential_check.py
```

(Height 450170 was verified in the tool's --file mode after
fetching its raw block by hash; see
BLOCK_HEADER_RECONSTRUCTION.md section 3.)

## 2. Block-level verification (header tool)

Each block was parsed, re-serialized, hashed with the
reference implementation, checked against Core's hash,
target-tested as integers, and its Merkle root recomputed
from the parsed transactions:

| Block | Transactions | Checks | Result |
|---|---|---|---|
| genesis (constructed) | 1 | 8 | ALL PASS |
| mainnet 450150 | 2,573 | 8 | ALL PASS |
| mainnet 450160 | 931 | 8 | ALL PASS |
| mainnet 450170 | 2,095 | 8 | ALL PASS |
| regtest 1491 (SegWit) | 41 | 9 | ALL PASS, witness commitment verified |

Full per-block records: BLOCK_HEADER_RECONSTRUCTION.md.

## 3. Differential run (differential_check.py)

The script pins its five header fixtures to the block
hashes Core reported before comparing anything, then runs
four parts. Recorded output:

```
fixtures: 5 headers pinned to Core block hashes
A reference vs hashlib: 234 comparisons, 0 mismatches
B production backend selected: v512dual
B reference+hashlib vs ComputeEngine batch (v512dual): 49288 digests, 0 mismatches
C target decoding and verdicts vs mining.pow_engine and candidate_verify: 237 comparisons, 0 mismatches
D midstate split vs full reference SHA-256: 15 comparisons, 0 mismatches
TOTAL: 49774 comparisons, 0 mismatches
```

Part A (reference vs hashlib): 24 message lengths including
every padding boundary (55, 56, 57, 63, 64, 65, 119, 120,
127, 128, 129) at 4 random messages each, both SHA-256 and
SHA-256d; plus the 5 headers at nonces 0, 1, 2, 2083236893
and 2^32 - 1. 234 comparisons.

Part B (production batch path): digests from the
ComputeEngine batch entry point for the auto-selected
backend (v512dual, entry bal_vd_batch2 via the same seam the
EXP-039 audit used), each compared against hashlib, with the
reference implementation compared on a stride sample and on
every boundary nonce. Composition: genesis header nonces 0
to 8,191 plus edge spans (0,1), (1,1), (0,17), (7,100),
(2^32-16,16), (2^32-1,1) = 8,328; the other four headers at
2,048 nonces from 0 and 2,048 ending at 2^32 = 16,384; six
random headers at 4,096 nonces from random starts = 24,576.
Total 49,288 digests. The boundary nonces 0, 1 and
2^32 - 1 are covered both as span starts and as span ends.

Part C (targets and verdicts): the header tool's
target_from_bits against production compact_decode over 211
encodings (11 named, including exponent <= 3 forms and a
zero mantissa, plus 200 random sign-masked encodings): all
equal. The sign-bit encoding 0x1d80ffff is flagged negative
by production and refused by the tool. For each of the 5
headers: the tool's integer verdict, check_pow, and
verify_candidate's meets_network_target all agree (accept).
Near-boundary: re-encoding each header's own digest as its
target (compact_encode truncates, giving the largest
representable target <= digest) makes both verdicts reject
with reason high-hash in all 5 cases. The exact-equality
point cannot be exercised with a crafted header without
inverting SHA-256; it is covered by the decode equality
above plus both verdicts using the same comparison
(rejection iff value > target, so equality accepts in both,
which is Core's CheckProofOfWork semantics as recorded in
the Core v28.1 audit). 237 comparisons.

Part D (midstate split): for the 5 headers and 10 random
80-byte strings, midstate over bytes 0 to 63 finished with
sha256_from_midstate equals the full reference SHA-256.
15 comparisons. This is the executable form of the pipeline
claim in SHA256D_PIPELINE_RECONSTRUCTION.md section 2.

## 4. An incident during this run, recorded

The first assembly of the differential script transcribed
one header fixture by hand and dropped characters in a
zero run (a 79-byte "header"). Parts A and B of that run
compared implementations against each other on the same
wrong bytes and passed vacuously for that fixture; part C
caught it, because check_pow reads the real field offsets.
The script now builds its fixtures from the decoded fields
and pins every fixture to its Core block hash before any
comparison runs, and the recorded results above are from
the corrected, complete run. The lesson is the lab's
standing one: a differential that cannot fail is not a
verification.

## 5. Verdict

The reference implementation, hashlib, and the production
v512dual batch path produce byte-identical SHA-256d digests
over the entire corpus, including all boundary nonces and
padding edges; the target decoding and verdicts agree with
the production proof-of-work code and the EXP-036 verifier
on every case, including the near-boundary rejects. The
Stage 1 reconstruction rests on verified implementations.
