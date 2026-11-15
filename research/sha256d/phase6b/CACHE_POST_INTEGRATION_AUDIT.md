# EXP-025 Repaired Template Cache: Post-Integration Audit

Auditor: independent agent (not the integration author),
2026-11-15. Scope: the cache integrated into
mining/engine.py per PRODUCTION_INTEGRATION_LOG.md
Entry 2, audited as it stands in production code.
The auditor restarted nothing and changed no
production code.

## Verdict: PASS WITH NOTES

Zero defects. Every author claim that this audit
re-tested independently held up, with the auditor's
own numbers below. Notes N-1 to N-6 are
documentation precision, inherited design boundaries,
and pre-existing semantics, not defects.

## 1. Design fidelity (production vs research)

Field-by-field diff of mining/engine.py against
research/sha256d/phase6b/benchmarks/exp025_repaired.py:
the construction is identical except (a) the key
domain tags (bal/template-cache/v1 in production,
exp025/v1 in research, documented in the log) and
(b) the production TemplateCache adds the
128-entry bound. Layered identity confirmed:

- family_key: payout address, scriptPubKey, chain,
  halving interval.
- tx_key: transaction count, then per transaction
  IN ORDER txid (internal order), wtxid, fee, plus
  the default_witness_commitment string as a
  validation input.
- coinbase_key: family_key, height, coinbasevalue,
  coinbaseaux flags, witness commitment or an
  explicit none marker.
- header_key: version, previousblockhash, bits,
  target.
- identity = dsha256(tx_key || coinbase_key ||
  header_key).

Full transaction serialisations enter through the
wtxid (dsha256 of the full serialisation) and the
re-verified txid (dsha256 of the stripped
serialisation), exactly the research completeness
argument. mintime, curtime and the extranonce are
in no key and are read per build. The EXP-023
prototype's 8-field fingerprint shape is nowhere
in the production code.

Behavioural confirmation (auditor harness): a
field-sensitivity matrix of 10 mutations computed
the production identity and the research identity
side by side. They agreed on every field: version,
previousblockhash, bits, target, height, flags and
per-tx fee move both identities; curtime and
mintime move neither; a changed
default_witness_commitment string moves both.

## 2. Stale-serve impossibility (auditor's own tests)

Auditor harness (fresh seed 987654321, own fixture
builders), 15 adversarial mutations against a
prepared entry and at engine level. Every valid
mutation was refused as a sibling serve, prepared
a new identity entry, and produced output
byte-identical to build_candidate_uncached. Every
invalid mutation raised TemplateError on both
paths with no new prepare. No stale serve occurred.

Required cases, all correct: D1 middle tx replaced;
D2 witness-only change with txid held fixed; D3
middle reorder; D4 coinbaseaux flags change; D5
target change; D6 fee raised with coinbasevalue
fixed (invalid); D7 wrong
default_witness_commitment (invalid).

Auditor inventions, all correct: M8 height +1 in
the same subsidy interval; M9 a non-witness tx's
locktime byte changed with its txid field updated;
M10 two transactions swapped in position AND in
fees simultaneously; M11 a fee field deleted
(defaults to 0 on both paths) with coinbasevalue
adjusted; M12 previousblockhash uppercased (same
bytes: same identity, byte-identical serve, because
the header key hashes the decoded bytes); M13
coinbaseaux removed entirely (flags default: same
identity, byte-identical); M14
default_witness_commitment carrying garbage around
the correct commitment (new identity, byte-identical
output; see N-6); M15 the prepared template object
mutated IN PLACE after prepare: the
explicit-template serve detected it and raised,
and the engine serve matched the uncached output
on the mutated object.

## 3. Auditor differential campaign

520 fresh randomised (template, extranonce) cases
(configurations of 0, 1, 2, 5, 17, 64, 200 and 500
transactions, segwit fractions 0, 0.5 and 1.0,
flags and witness commitment variants), cached
build_candidate vs build_candidate_uncached:
byte-identical on header, body and every scalar
field in all 520. Steps shape: 1 prepare, 100
extranonce steps, all byte-identical.
mine_cycle with a stub compute: the fast path
prepared exactly once; a subclass overriding
build_candidate was called per round with zero
cache prepares, exactly the documented behaviour.

## 4. Validation parity, fallback, cache bound

Six invalid shapes (missing data, missing txid,
wrong txid, coinbasevalue off by one, fee raised
with value fixed, wrong witness commitment) each
raised TemplateError identically on the uncached
path, the cached first serve, the cached sibling
serve and the cached prepare. Fallback:
use_template_cache=False produced byte-identical
output with zero prepares, zero hits and zero
identity checks. Bound: 200 distinct templates
prepared into the cache left exactly 128 entries;
serves of an evicted early template and of a
retained late template were both byte-identical
to the uncached path afterwards.

## 5. Auditor regtest block

Fresh block mined by the auditor through the
production MiningEngine with the cache active
(mine_cycle steps fast path, cache prepares 1,
identity checks 1), accepted by Core as best
block: height 984, hash
0f7469bd0fb9138d9c638bb57bf041335d92dd1b3a976e3014a872b7243c6e76.

## 6. Test suite (exactly what the auditor ran)

- make test-template-cache: PASSED in full,
  including the author's G-A to G-D gates (their
  1,320-case campaign reproduced byte-identical)
  and their G-E regtest block at height 979.
- make test-task0039: PASSED standalone, no flake
  reproduced (its regtest section mined height
  980). See N-1 on the author's flake wording.
- make test-engine and make test-mainnet-live:
  PASSED.
- The full 25-target test-all was NOT re-run by
  the auditor; the targets above are the ones this
  integration touches.

## 7. Live state from the outside

Unchanged by the integration and by this audit.
At audit start and close: autopilot pid 3190,
miner pid 30455, restarts 2, miner uptime
continuous (4,641 s rising to 4,830 s), backend
v512dual, endpoint config still mode pool, solo
cutover marker still absent (the armed default).
Verified from source that mining/mainnet_live.py
imports gpu.engine only and never mining/engine.py,
so the live miner does not load this code and was
correctly not restarted.

## 8. Hygiene

Long dash character (U+2014) count: zero in
mining/engine.py, tests/test_template_cache.py,
the Makefile and the integration log. Secrets
scan by value (values held in memory only, never
printed): the node RPC password, the wallet
private key hex and the wallet private key WIF
are all absent from the tree outside .local. The
public wallet address appears in the tree by
design.

## Notes (no defects)

- N-1 (documentation precision): the log says the
  flaked test-task0039 "does not touch
  mining/engine.py". The flaked assertion itself
  is in gpu/engine.py ComputeEngine accounting,
  which this integration did not change, and it
  passed standalone for the author and for this
  auditor. At file level the statement is
  imprecise: test_task0039_accounting.py imports
  MiningEngine for its regtest section, and that
  section now exercises the cache steps path (and
  passed). No verdict impact.
- N-2 (inherited design boundary): PreparedTemplate
  holds the template object by reference, and
  build(template=None) reads time and header fields
  from that held object without re-verification.
  That is the accepted EXP-025 steps design:
  mine_cycle holds the template itself and never
  hands it out between steps, and every
  explicit-template serve re-verifies the full
  identity (auditor case M15). Recorded so the
  trust boundary is explicit.
- N-3 (cosmetic): cache eviction is FIFO, not LRU;
  a hit does not refresh an entry's position. The
  128 bound holds and correctness is unaffected.
- N-4 (design, faithful to research): the family
  constants (scriptPubKey, chain, halving interval)
  are resolved once per engine, lazily, where the
  uncached path resolves them per call. Payout and
  chain are engine-lifetime constants in every
  production consumer, and the research
  RepairedFamily does the same.
- N-5 (claim precision, in the author's favour):
  mining/solo_server.py imports three helper
  functions from mining.engine (address_script_pubkey,
  build_coinbase, strip_witness) but does not use
  MiningEngine or the cache; the author's claim is
  exact, and those helpers are unchanged.
- N-6 (pre-existing semantics, parity confirmed):
  the witness commitment cross-check is a substring
  check on both paths, so a
  default_witness_commitment string merely
  containing the correct commitment is accepted by
  both (auditor case M14). The cache preserves the
  uncached path's semantics exactly; changing the
  check itself is outside this integration.
