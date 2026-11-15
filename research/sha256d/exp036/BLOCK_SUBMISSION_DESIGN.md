# EXP-036: Exact Candidate Verification and Block Submission, as built

Date: 2026-11-15. Status: implemented in production, tested,
including a regtest end-to-end block through the fixed solo
path. This document describes the pipeline as it now exists in
the code, maps it onto the directive's twelve steps, records
what was wrong before, and states the remaining gaps without
softening them.

## The one-sentence design

Every candidate from every search path is re-verified exactly
(independent SHA-256d plus Core's target rules, integer
comparisons only) before anything is submitted, and a block
counts as accepted only when the node's chain state confirms
it, never because a submission call merely returned no error.

## New component: mining/candidate_verify.py

The Exact Candidate Verifier (directive component 12), the
single stage the production candidate paths now route
through. It exposes four functions:

- `verify_candidate(header, pow_limit, share_target=None)`:
  pipeline steps 4 to 7 for one reconstructed 80-byte header.
  It hashes the header twice, with hashlib
  (mining.pow.dsha256) and with the from-specification
  pure-Python SHA-256 (mining.pow_engine.double_sha256_pure,
  an implementation sharing no code with OpenSSL), and
  requires byte agreement. It decodes nBits via
  mining.pow_engine.check_pow, the strict verifier with
  Core-style reason codes (negative-target, overflow-target,
  zero-target, target-above-limit, high-hash) that before
  EXP-036 was called only by tests and a milestone script.
  It classifies the candidate as "block_candidate", "share",
  "below_target" or "invalid". Block candidacy is exactly
  `check_pow ok AND digests agree`. No floating-point value
  participates in any comparison in the module.
- `meets_target(value, target)`: the one authoritative
  comparison form, exact integer `value <= target`, matching
  Core's boundary semantics (a digest equal to the target
  meets it). Matrix row M02 (Bitaxe's uint256_lte against
  pool target and nBits target separately) is the adopted
  pattern; row M03 (the Qaxe fork's floating-point difficulty
  judgement in test_nonce_value and checkForFoundBlock,
  weakness W1) is rejected, as the directive requires.
- `classify_submit_result(result)`: classifies a submitblock
  return value as accepted (None), duplicate,
  duplicate-invalid, inconclusive, rejected, or (at the call
  site) rpc-error. The verbatim value is always recorded
  alongside the classification; the classification never
  replaces it.
- `verify_chain_acceptance(rpc, block_hash)`: pipeline step
  12. Returns "tip" (the block is getbestblockhash),
  "in-chain" (getblockheader reports confirmations >= 1, so
  a descendant already sits on it), "not-in-chain" (unknown
  to the block index, or a fork block with no confirmations),
  or "unknown" (chain state unreadable, reported as not
  accepted). Accepted means tip or in-chain.
- `pow_limit_for_chain(chain)`: per-chain proof-of-work
  limits (regtest has its own; mainnet, testnet, testnet4
  and signet share mainnet's), with unknown chains falling
  back to the mainnet limit, the strictest, so an unreadable
  chain never widens the target.

Cost discipline: verify_candidate runs a pure-Python double
hash, so it is invoked only on candidate hits (a submission
meeting the share target, or a claimed block candidate),
never inside a search loop. This is by construction, and it
is checkable: the only production callers are
SoloServer.submit_share (after its fast integer gate) and
the confirmation block in mining/mainnet_live.py (after
engine.search_first returns a hit).

## The twelve steps, as implemented

1. Recover immutable job. Solo path: SoloServer.jobs holds
   the job built from the getblocktemplate response, retained
   in full server-side; submit_share looks it up by job_id
   and rejects unknown jobs. Pool path: the Stratum client's
   current job dict plus its generation counter.
2. Recover exact header fields. Solo: validate_share
   rebuilds the coinbase from the job's stored coinb1,
   coinb2, the connection's extranonce1 and the submitted
   extranonce2, and the header from the template's version,
   previousblockhash and bits with the submitted ntime and
   nonce. Pool: stratum_client.build_header from the job,
   extranonce pair and winning nonce. As a consistency
   check, submit_share additionally requires the target
   decoded from the reconstructed header's own nBits to
   equal the job's recorded target; a mismatch classifies
   the candidate invalid (reason header-target-mismatch)
   and it is never submitted.
3. Reconstruct the 80-byte header. As in step 2; the exact
   bytes that are verified are the exact bytes whose hash
   the miner claimed, and on the solo path the exact header
   bytes that enter the assembled block.
4. Compute SHA-256d independently. verify_candidate, two
   implementations, byte agreement required (see above).
5. Decode nBits to the exact 256-bit target. check_pow's
   compact_decode, Core SetCompact semantics with negative
   and overflow flags.
6. Compare full digest vs target with exact integer
   semantics. meets_target; block candidacy is check_pow's
   verdict. No float anywhere in the decision.
7. Reject invalid candidates. Solo: classification
   "invalid" (target-sanity failure, digest disagreement,
   header-target mismatch) records the candidate in
   SoloServer.candidates_rejected (exposed in stats()),
   counts it rejected for the worker, and returns
   "exact verification failed: <reason>". submitblock is
   never called for it; tests/test_exp036_verification.py
   proves the zero-call property against a fake Core.
   Pool: an unconfirmed candidate is logged
   candidate_rejected with the verify reason and is never
   submitted to the pool.
8. Construct the complete block from the original
   transaction set and candidate coinbase. Solo: the header,
   the transaction count, the coinbase (witness re-attached
   by attach_witness when the template carried a witness
   commitment) and the template's transactions verbatim,
   exactly as before EXP-036; the header in the block is the
   header that passed exact verification. Pool path: not
   applicable, see Gaps.
9. Validate locally. The solo path's local validation is
   the exact verification of step 4 to 7 over the precise
   header being submitted, plus the node gating SoloServer
   already applies before serving work (chain match, no
   initial block download). There is no separate
   validateblock-style pass; Core performs full validation
   on submission, and step 12 confirms the outcome.
10. Submit through the correct interface. Solo: Bitcoin Core
    submitblock via the RPC adapter the server already uses
    (node/rpc_client.py BitcoinRPC in production). Pool:
    Stratum mining.submit via stratum_client.
11. Record the response. Solo block records in
    SoloServer.blocks_found (and therefore in stats() and
    .local/solo-status.json) now carry: height, hash,
    submit_result (verbatim), submit_classification,
    chain_status, chain_verified, verify_reason, and the
    final accepted boolean. An RPC exception during
    submission is still captured into the record (classified
    rpc-error) instead of killing the connection handler or
    losing the candidate, as before.
12. Verify acceptance through node chain state.
    verify_chain_acceptance, as above. The record's
    accepted flag, and the per-worker block count, are set
    from chain state, not from the submission response.

## What was wrong, and what changed

Defect 1 (solo acceptance standard). Before: submit_share
set ok = (submitblock returned None) and never looked at
chain state, so a block the node took but never landed (or
silently dropped) was recorded as found. After: accepted
requires chain confirmation (tip or in-chain) and a
submission classification of accepted or duplicate. The
standard is the one mining.engine.mine_cycle has always
applied on regtest (submitblock None AND getbestblockhash
equals the block hash), extended with the in-chain case for
a block that already has a descendant. Tests pin the old
failure mode directly: a fake Core whose submitblock
returns None but never lands the block now yields
accepted False, chain_status not-in-chain, and a worker
block count of 0.

Defect 2 (strict verifier not in production). Before:
pow_engine.check_pow was called only by tests and
scripts/milestone_003_006.py; the solo server validated
shares with inline hashlib code (its docstring's claim of
using "the lab's own PoW engine" was false), and the pool
path's network-target check was a plain integer compare
against a target decoded without the negative, overflow or
above-limit rules. After: both production candidate paths
route through candidate_verify.verify_candidate, which is
check_pow plus the second independent hash. MiningEngine
.mine_cycle was deliberately not modified: it already
applied the strict acceptance rule and its candidate target
comes from its own template handling; it is the reference
the solo path was brought up to, and the design decision is
recorded here rather than silently expanding the change.

Defect 3 (floating-point difficulty as a test). Before:
the pool path derived its target from the pool's floating
difficulty (target_for_difficulty) and used the same
compare for submission and, in the is_block_candidate log
field's neighbourhood, for judging the hit; difficulty
floats also decided nothing less than whether a candidate
was confirmed (the confirmation compare ran against the
float-derived target). After: target_for_difficulty remains
only as the pool's share criterion (the pool defines its
share target through a float difficulty, so a float-derived
integer is unavoidable for deciding what to submit as a
share; the function now says so in its docstring), while
confirmation additionally requires the exact verifier's
valid_header and meets_share_target under the same gate,
and block candidacy (the is_block_candidate field in the
share_submitted evidence event) is check_pow's
meets_network_target alone. Difficulty floats in
mainnet_live (difficulty_of, best-difficulty tracking) are
display and statistics only. The boundary case is pinned
by test: at the difficulty-1 target, float64 cannot
distinguish target from target + 1 and their float
difficulties are identical, while the integer compare
decides them differently; a float judgement (W1) is blind
exactly where consensus is sharpest.

## Evidence from the test runs (2026-11-15)

- tests/test_exp036_verification.py (new, make target
  test-exp036, wired into test-all): unit classifications
  (genesis block candidate; mutated header below target;
  negative, overflow, above-limit invalid; per-chain pow
  limits), fake-Core solo tests (chain-verified acceptance;
  overflow-target candidate rejected with zero submitblock
  calls; header-target mismatch rejected with zero calls;
  submitblock None without chain confirmation recorded as
  not accepted; rejection string classified verbatim; RPC
  failure keeps the candidate record), and a regtest
  end-to-end: block at height 1028, hash
  4a19aeb33bde2e2c9473dd32d374141ca9d95fc303278fd2ef6f36f5fe7fe241,
  chain_status tip, getbestblockhash equal to the record
  hash; a low-difficulty share on the same node rejected
  with no submission and the tip unmoved.
- tests/test_solo_server.py (pre-existing TCP end-to-end)
  passes against the fixed server: block at height 1029,
  hash 000000175fe4e004234ee85ac0d537cca0d5d25f0e0d5c183f08b1a843f4c79f,
  accepted by Core, per-worker accounting intact.
- Full suite (make test-all, 27 targets): every target
  passed except test-rtl, which fails on this VM with
  "iverilog: not found" before any test code runs, the
  pre-existing environment failure (the RTL simulator is
  not installed here) that predates EXP-036 and is
  unrelated to it. Because make stops at that target, the
  15 targets after test-rtl were then run in one
  continuation invocation and all passed, so every target
  except the environment-blocked RTL one has a fresh pass
  with the EXP-036 code in place.

## Gaps, stated honestly

- No candidate queue (directive component 11 remains
  MISSING). Candidates are still handled synchronously on
  both paths. The pool path logs candidate_confirmed before
  submitting, so a crash between confirmation and submission
  leaves evidence but no automatic recovery or replay;
  candidate recovery across restarts belongs to EXP-038.
  On the solo path a candidate exists as a record only once
  submit_share has processed it.
- The pool path cannot construct a block. It holds no
  transaction set, so a network-target hit there is
  submitted as a Stratum share flagged is_block_candidate
  (now by exact verdict), and the pool constructs and
  submits the block. That is inherent to pooled mining; the
  lab's own block construction exists on the solo and GBT
  engine paths only. A share acceptance by a pool is never
  recorded as a block found, and the solo path's records
  keep the two categories separate (accepted share vs
  chain-verified block).
- Solo "in-chain" acceptance trusts getblockheader
  confirmations at the instant of the check. A block in the
  active chain at that instant can in principle be reorged
  out later; no path in the lab re-checks found blocks after
  the fact. On the solo mainnet path this is a record-keeping
  caveat, not a payout risk (the coinbase matures after 100
  confirmations regardless), but it is a real limitation of
  step 12 as built.
- Stratum V2 remains absent entirely (EXP-034 territory);
  the Stratum adapter here is V1 only, and the solo server's
  share validation beyond the exact gate (ntime bounds,
  extranonce2 size) is unchanged from before.
- verify_chain_acceptance treats a getblockheader error
  other than Core's -5 (block not found) as "unknown", which
  records a genuinely accepted block as not accepted when
  the node's RPC is merely flaky at that moment. The bias is
  deliberate (never claim an unverified block), and the
  verbatim submit_result plus chain_status unknown in the
  record keep the evidence needed to reconcile by hand.
- The MiningEngine GBT path (mining/engine.py) was left as
  the reference implementation (see Defect 2); unifying it
  onto candidate_verify as well is a small follow-up that
  EXP-034's job-model work is the natural home for, since
  its chain context for pow-limit selection is not carried
  in its templates today.
