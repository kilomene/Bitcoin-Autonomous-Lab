# Research results: statistics, the solo stack, and CPU peak 2
# (2026-11-13)

All numbers below were produced by our own code on our own data
in this lab. Scripts: research/statistics.py,
research/probability.py, mining/solo_server.py. Tests:
tests/test_research.py, tests/test_solo_server.py.

## 1. Is there statistical structure to exploit? Measured answer

- 1,000,000 fresh double hashes from the C engine: worst byte
  position chi-square 306.3 at 255 degrees of freedom (p about
  0.015 before correcting for 32 positions tested; not
  significant). Bit-one fraction 0.49998. Lag-1 agreement between
  consecutive nonces' top bits 0.5005. Nothing.
- Our own chain (390 blocks): winning nonces follow the
  geometric law of sequential search: median scaled nonce 0.50
  against a theoretical 0.69. The raw nonce histogram is
  violently non-uniform (chi-square 5850) for a boring, proven
  reason: every miner scans from nonce 0 and the regtest target
  accepts about half of all hashes, so 99.5 percent of winners
  sit below nonce 10. Search order, not hash structure.
- Reduced-round bias curve (our parametrized SHA-256, one-bit
  differential, 3,000 trials per point, noise floor about 0.015):
  16 rounds: bias 0.492 (output nearly determined). 20 rounds:
  0.084 (strong bias). 24 rounds: 0.0077 (gone). 28 to 64
  rounds: flat at noise. Statistical structure is real in the
  small and dead long before the full 64 rounds Bitcoin uses.
  That curve is the honest map of where a formula could live
  and where it cannot.

## 2. The solo stack (built, proven end to end)

mining/solo_server.py is our own Stratum V1 solo pool:
getblocktemplate in, jobs out, shares validated with the lab's
PoW engine, winning shares assembled into full blocks and
submitted via submitblock. A worker running our ComputeEngine
mined through it and Bitcoin Core accepted the block at height
390. Two real bugs were found and fixed on the way: the Stratum
merkle branch must be computed on the layer that includes the
coinbase, and the coinbase served to workers must be the
stripped form (its hash is the txid the merkle root expects);
the server re-attaches the witness when assembling a block.

## 3. CPU peak 2: the intrinsics experiment (kept the winner)

We hand-wrote a SHA-256 compression on the Intel SHA intrinsics
(mining/cpu/bal_sha_intrin.c), including a template snapshot
after round 1 (the nonce enters at round 3). Deriving the
instruction's true operand organisation took a brute-force
search against the Python reference; the kernel then reproduced
the genesis double hash exactly and matched hashlib on 5,000
consecutive nonces. Measured A/B on this VM: intrinsics
1.14M H/s, OpenSSL transform library 2.97M H/s in the same run
(absolute rates move with VM throttling; the ratio is the
result). The scalar message schedule is a serial recurrence and
it costs more than the snapshot saves. Verdict by measurement:
the OpenSSL-backed kernel stays the production CPU path; the
intrinsics kernel stays in the repo as a verified artifact and
the starting point for a future SIMD-schedule attempt.

## 4. Solo odds, computed by research/probability.py

At the engine's measured rate (about 4.7M H/s in the reference
run):

| target | expected time | P(block in 1 year) |
| --- | --- | --- |
| testnet4 minimum difficulty (1) | about 15 minutes | about 1 |
| testnet4 at ASIC difficulty (245M) | about 7,093 years | 1.4e-4 |
| mainnet (about 110T) | about 3.2 billion years | 3.1e-10 |

Testnet4 periodically offers difficulty-1 blocks under its
20-minute rule; that window is the one real shot a CPU has at a
public-chain block, and the lab's testnet4 node (syncing,
10 peers) plus this solo stack are the apparatus to take it.

## 5. The Lite question, settled by measurement

Owner's question (2026-11-14): can a "lite" miner, the way
Facebook Lite does the same job as Facebook with less, confirm
a block faster than an ASIC by screening with formulas,
statistics or physics instead of full hashing?

Measured answer, from section 1's own data: no, and the
reason is structural. A block is confirmed by exactly one
thing, a full double SHA-256 of the header at or under the
target, accepted by the network. Every output bit of SHA-256
depends on all 64 rounds, so no partial or lite evaluation
can certify the result early; and the one place structure
could have lived dies measurably before full rounds (bias
0.49 at 16 rounds, 0.08 at 20, indistinguishable from noise
from 24 on, against 64 rounds applied twice). Statistics
cannot bend the search either: winning nonces follow the
geometric law of the protocol exactly (section 1). A lite
screen that skips the full hash can only produce candidates
that still need the full hash, so it saves nothing; a screen
that skips it and claims confirmation is not mining, it is
fiction, and this lab does not ship fiction.

What "lite" legitimately means here, and what the lab does:
do the full work, but waste none of it. The midstate of the
header's fixed half is computed once per job, not per nonce.
The search exits at the first hit instead of finishing the
range. Templates are judged before hashing and the freshest
always replaces stale work within about a second. Found
candidates are confirmed by an independent recomputation.
The supervisor never lets the miner rest. Those are the real
coefficients, and on this VM they are worth the difference
between the naive Python loop (about 0.16M H/s measured) and
the full-workforce engine (about 6.2M H/s measured): roughly
40 times, honestly earned. The remaining gap to an ASIC
(about 200T H/s, tens of millions of times this VM) is
silicon, not mathematics: the lab's own ASIC package is the
answer on that axis, and the team's combined machines are
the answer on the other. There is no third axis, and any
source claiming one should be asked for a pool-accepted
share as proof, the same evidence standard this lab holds
itself to.
