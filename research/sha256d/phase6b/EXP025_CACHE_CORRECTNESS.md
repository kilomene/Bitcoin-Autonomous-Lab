# EXP-025: EXP-023 Cache Correctness and Identity Repair

Experiment ID: EXP-025 (reserved 2026-11-14, Phase 6B).
Status: COMPLETE 2026-11-15. Verdict: ACCEPTED as a
correctness repair (all six predeclared success
elements pass, section 8). No integration performed;
the EXP-023 integration question may be re-put to the
owner with this record and its honest performance
picture attached (section 7). Production code
byte-identical throughout.
Track: A (near-term engineering). This is a
correctness gate, not a performance experiment.
Host for all EXP-025 execution: AMD EPYC 9D25
126-Core Processor (AVX2, AVX-512F/BW, SHA-NI exposed;
4 vCPUs). EXP-023's measurements ran on an Intel Xeon
Platinum 8321HC host; cross-experiment rate
comparisons must carry that host difference.

## Predeclared hypothesis

The EXP-023 prototype's cache identity (the
PreparedTemplate fingerprint) does not cover every
input that can change the cached objects, so there
exist template changes that alter the correct output
while leaving the fingerprint unchanged (a silent
stale-cache serve). The adversarial suite below will
demonstrate at least one such case against the
prototype as written, and a layered identity built
from the complete dependency analysis (section: work
plan) will invalidate correctly on every case while
preserving byte-identical output on identical inputs.

The second half is falsifiable in the useful
direction: if the adversarial suite finds no stale
serve, that result is recorded with the suite as
evidence and the identity is stronger than this
hypothesis assumed.

## Predeclared success criterion

Not a performance criterion; the EXP-017 rule does
not apply. Success is all of:

1. Every cached object's dependency set is
   documented (work plan step 1) and the document is
   checked field by field against
   mining/engine.py build_candidate and
   mining/pow.py as the ground truth of what the
   uncached construction reads.
2. The repaired cache identity is complete against
   that dependency analysis: for every field in the
   dependency sets, a mutation test exists.
3. The adversarial invalidation suite passes in
   full: every mutation either invalidates the
   dependent layers or is proven (by byte-identical
   comparison against a complete uncached rebuild)
   to be output-irrelevant.
4. Cached and uncached block construction are
   byte-identical across the randomised corpus
   (the EXP-023 gate corpus of 1,320 cases, extended
   with the adversarial mutations).
5. Regtest blocks built through the repaired cache
   are accepted by Bitcoin Core.
6. No stale transaction body, witness commitment or
   Merkle root can be served: this is the summary
   claim and it must follow from items 2 to 4, not
   from inspection alone.

Only after all six: the EXP-023 integration question
may be put to the owner again, with this experiment's
record attached. Performance re-measurement of the
repaired cache (its identity cost may differ from
the prototype's) is a separate, later measurement
under the EXP-017 protocol; EXP-025 claims no rate.

(The performance re-check was nevertheless run under
the EXP-017 protocol at the parent directive's
request and is recorded in section 7 with its own
predeclared criterion; it does not change the six
correctness elements above.)

## 1. Initial inventory: cached objects and claimed identity (UNAUDITED)

Source: research/sha256d/phase6/benchmarks/
exp023_amortized.py, read in Assignment A. This list
is the prototype as written, flagged UNAUDITED: it is
the input to the dependency analysis, not its result.

FamilyContext (level 1, per node and payout):

- rpc handle; payout address.
- script: the payout scriptPubKey, from one
  validateaddress RPC (address_script_pubkey).
- chain: from one getblockchaininfo RPC.
- interval: halving interval derived from chain
  (150 regtest, else 210000).
- Identity as written: NONE. The context is keyed by
  construction (one object per (rpc, payout) pair as
  built by the caller); no fingerprint or equality
  check exists at this level. A changed payout
  address or a changed node behind the same rpc
  object is not detected by the prototype itself.

PreparedTemplate (level 2, per template):

- txs_raw: every transaction's raw serialisation
  (from template transactions[].data).
- txids: per-transaction txids, recomputed from the
  raw serialisation (stripped form) and checked
  against Core's txid field.
- wtxids: per-transaction witness txids, recomputed
  (full serialisation). Used only through the
  witness commitment and witness_count.
- total_fees: sum of transactions[].fee.
- witness_count: count of transactions whose txid
  differs from wtxid.
- commitment: the witness commitment, computed from
  the wtxid Merkle root and RESERVED_VALUE when
  witness_count is nonzero, and cross-checked
  against template default_witness_commitment when
  present.
- value: template coinbasevalue, verified equal to
  subsidy(height, interval) plus total_fees.
- flags_hex: template coinbaseaux.flags.
- target: int(template target, 16).
- height: template height.
- levels: Merkle tree levels over a placeholder
  coinbase leaf (ZERO32) plus the txids, with
  odd-level duplication as in mining.pow.merkle_root.
- body_head: varint of 1 plus transaction count.
- body_tail: concatenation of txs_raw (the full
  transaction body after the coinbase).
- fingerprint: the ONLY identity check in the
  prototype, computed by _fingerprint(template) and
  re-checked in build() when a sibling template is
  passed. Its fields, exactly as written:
  version, previousblockhash, bits, height,
  coinbasevalue, transaction count, first
  transaction's txid, last transaction's txid.

Known omissions in the fingerprint, visible on
inspection (to be confirmed or refuted by the
dependency analysis; listed here because the
directive names them): any middle transaction; any
transaction's raw data or wtxid (witness data can
change without changing the txid); transaction
ordering beyond first and last; per-transaction
fees (a fee change that keeps coinbasevalue fixed
is invisible, and one that changes coinbasevalue is
caught only at that field); the witness commitment
and default_witness_commitment; coinbaseaux flags
(flags_hex is cached but not fingerprinted, while
build() takes version, previousblockhash and bits
from the passed sibling template and flags from the
CACHED template, an asymmetry the analysis must
resolve); mintime and curtime (build() reads them
from the passed template, so time is not cached, but
the interaction with the cached height and value
must be stated); the FamilyContext contents
(script, chain, interval) behind the prepared
template.

Per-step computation (not cached): build_coinbase
per extranonce step (height, value, family script,
extranonce, cached flags, cached commitment), the
coinbase spine walk root_with_coinbase over the
cached levels, header assembly from the passed
template's version, previousblockhash, bits and
time fields plus the computed root.

## Work plan

1. Full cache-dependency analysis: for every cached
   object above, enumerate every source field that
   can affect it, from the uncached code path
   (mining/engine.py build_candidate, build_coinbase,
   mining/pow.py txid_of, wtxid_of, merkle_root,
   coinbase_subsidy). The directive's minimum list:
   block version; previous block hash; height; bits
   and target; timestamp fields; coinbase value;
   coinbase flags and auxiliary data; extranonce;
   transaction count; every txid; every wtxid;
   transaction ordering; transaction serialisation;
   witness data; witness commitment; Merkle
   branches; coinbase serialisation; all intermediate
   hashes and cached SHA states.
2. Layered identity design: deterministic keys per
   layer (family, template transactions, coinbase
   inputs, header inputs), so a change invalidates
   only dependent layers, with correctness taking
   priority over reuse wherever the two conflict.
   Where the safest design requires rebuilding an
   intermediate object, rebuild it.
3. Adversarial invalidation suite: deliberate
   mutations, each checked for correct invalidation
   AND byte-identical output vs a full uncached
   rebuild: a middle transaction changed; first
   transaction changed; last transaction changed;
   transaction order permuted; witness data changed
   with txid held fixed; coinbase value changed;
   extranonce changed; previous block hash changed;
   version changed; bits and target changed;
   timestamp fields changed; transaction count
   changed; witness commitment changed; fee changed
   with coinbasevalue held fixed and with it varied;
   coinbaseaux flags changed. Plus the positive leg:
   identical inputs reuse the cache and produce
   byte-identical output.
4. Regtest acceptance through the repaired builder.
5. Record: dependency tables, identity design,
   suite results, and the verdict on each of the
   six success elements.

## Gates

The success criterion above is the gate list. No
benchmark gate exists in this experiment. Historical
EXP-023 benchmark results are preserved untouched
and are not re-claimed here.

## 2. Dependency matrix (work plan step 1, EXECUTED)

Ground truth: mining/engine.py build_candidate,
build_coinbase, address_script_pubkey, strip_witness,
txid_of, wtxid_of, and mining/pow.py merkle_root,
coinbase_subsidy, dsha256, read field by field. Every
cached object of the prototype, and every object the
repaired design caches, with the complete set of
source fields that can change its bytes. A field
marked (validation) changes no output byte directly
but decides whether construction raises; a cache
that skips it serves candidates the uncached path
would refuse.

Family layer (per node and payout):
- script (payout scriptPubKey): payout address, the
  node's validateaddress answer.
- chain: the node's getblockchaininfo answer.
- interval: chain (150 if regtest else 210000).
- (No other field reaches this layer.)

Template transaction layer (per template):
- txs_raw and body_tail: every transaction's data
  (full serialisation, witness bytes included), in
  template order.
- txids: every transaction's stripped serialisation
  (hence its full serialisation and witness layout),
  in order.
- wtxids: every transaction's full serialisation,
  in order.
- total_fees: every transaction's fee.
- witness_count: every (txid, wtxid) pair.
- commitment: every wtxid in order, transaction
  count, RESERVED_VALUE (a protocol constant),
  and default_witness_commitment (validation).
- levels (Merkle tree over placeholder coinbase
  plus txids): every txid in order, transaction
  count.
- body_head: transaction count.
- value check (validation): coinbasevalue, height,
  interval, every fee.

Coinbase layer:
- The coinbase built per step depends on: height,
  coinbasevalue, family script, extranonce
  (per-build input), coinbaseaux.flags, commitment.
  Of these, height, coinbasevalue, flags and the
  commitment are cached or cache-derived; the
  extranonce is supplied per build and never cached.

Header layer (assembled per build, not cached, but
its inputs decide what a sibling may change):
- version, previousblockhash, bits: read from the
  passed template per build in both production and
  the prototype.
- Merkle root: the coinbase spine over cached
  levels plus the per-step coinbase txid.
- curtime: mintime and curtime of the passed
  template and the caller's clock. Read fresh per
  build by production; NOT a cached quantity.
- target, height, fees, tx_count, witness_count
  (returned fields): template target; height; the
  fee sum; the count; the pair count above.

Field coverage summary: the complete input set of
the construction is {payout address, chain, version,
previousblockhash, height, bits, target, mintime,
curtime, coinbasevalue, coinbaseaux.flags,
extranonce, transaction count, and per transaction
in order: data, txid field, fee; plus
default_witness_commitment}. The prototype
fingerprint covers exactly 8 of these (version,
previousblockhash, bits, height, coinbasevalue,
count, first txid, last txid). Uncovered: every
middle transaction's data, txid and fee; every
wtxid and all witness data; ordering beyond the
endpoints; flags; target; the commitment field;
the family layer entirely. Time fields are
uncovered by design in both implementations
because they are read fresh per build; the
extranonce likewise.

Snapshot note (EXP-023 Y-079 findings): this
builder caches no SHA-256 compression state at all,
so the R8, MID and SCH17 rungs do not arise inside
it. The only cross-step reuse is data-level (family
constants, transaction pass, Merkle levels, body
parts). Under the repaired identity, any change
that could move a Merkle root changes the
transaction layer key, so no data is ever served
across such a change; time-only changes, which the
Y-079 table shows leave even the midstate valid,
are applied per build after identity validation,
matching production exactly.

## 3. Demonstrated defect (work plan step 2, EXECUTED)

Driver: benchmarks/exp025_defect_demo.py, run
against the UNMODIFIED EXP-023 prototype. Record:
benchmarks/exp025/defect_demo_20261115T051355Z.json
(an earlier record, defect_demo_20261115T051348Z.json,
is the same suite before the D3 case was given the
reordered set's correct commitment field; both are
preserved). Base: 10 transactions, segwit fraction
0.5, witness commitment present. In every D case the
prototype fingerprint is UNCHANGED.

STALE SERVES (prototype accepts the sibling and its
output differs from the full uncached
reconstruction):
- D1 middle transaction replaced (same fee):
  header, body and witness_count differ.
- D2 witness bytes of a segwit transaction changed,
  txid held fixed, commitment field updated to the
  correct new value: header and body differ (stale
  body_tail and stale witness commitment served).
- D3 two middle transactions reordered (commitment
  field updated correctly): header and body differ.
- D4 coinbaseaux flags changed: header and body
  differ (the prototype builds the coinbase from
  the CACHED flags, resolving the audit's asymmetry
  in the worst direction).
- D5 target changed: the returned target field is
  the stale cached value.

VALIDATION BYPASSES (prototype accepts a sibling
the uncached path rejects with TemplateError):
- D6 one fee raised with coinbasevalue not
  adjusted.
- D7 default_witness_commitment replaced by a
  wrong value.

OUTPUT-IRRELEVANT gaps (fingerprint unchanged,
outputs byte-identical, with reason):
- D8 fee moved between two transactions with the
  total and coinbasevalue fixed: fees reach the
  output only through their sum and the value
  check, so no byte can change. The repaired
  identity keys per-transaction fees anyway
  (stricter than the output requires), because the
  value validation is part of the construction's
  contract.
- C1 curtime advanced only: time is read fresh per
  build by both paths; not a defect.

Control: C2 height changed (inside the fingerprint)
correctly raises in the prototype.

Conclusion: the hypothesis is CONFIRMED by
construction, in five distinct stale-serve shapes
and two validation-bypass shapes. The repair is
sized to the full dependency matrix of section 2,
not only to these cases.

## 4. Repaired identity design (work plan step 3)

Implementation: benchmarks/exp025_repaired.py (new
module; the EXP-023 prototype files are untouched).
A deterministic layered identity; each layer key is
dsha256 over that layer's complete dependency set,
with length prefixes where ambiguity could arise:

- family_key: payout address, scriptPubKey, chain,
  halving interval.
- tx_key: transaction count, then per transaction
  IN ORDER its txid (internal order), its wtxid and
  its fee, then the default_witness_commitment
  string (a validation input: any change forces
  revalidation even though the string is not itself
  cached data).
- coinbase_key: family_key, height, coinbasevalue,
  flags bytes, witness commitment (with an explicit
  none marker).
- header_key: version, previousblockhash, bits,
  target.
- identity = dsha256(tx_key || coinbase_key ||
  header_key).

Completeness: every byte of every cached object is
a deterministic function of the inputs hashed into
its layer key; raw serialisations enter through
their wtxid (dsha256 of the full serialisation)
and their verified txid (dsha256 of the stripped
serialisation). The identity is exact up to SHA-256
collision resistance, the same assumption Bitcoin
places on txids. mintime and curtime are
deliberately excluded: no cached object depends on
them, and the header time is assembled per build
from the passed template exactly as production
does. The extranonce is a per-build input.

Serving rule: build() with a sibling template
recomputes the sibling's identity FROM SCRATCH
(identity_of: full transaction pass with txid
re-verification, witness commitment cross-check,
and the coinbasevalue equals subsidy plus fees
check, identical to production's validations) and
raises TemplateError on any mismatch. It never
silently serves. A TemplateCache keyed by
(family_key, identity) provides reuse with counters
(prepares, hits, identity_checks) so tests can
prove reuse actually happened, and only under an
identical identity.

## 5. Adversarial suite and differential campaign (EXECUTED)

Driver: benchmarks/exp025_gates.py. Record:
benchmarks/exp025/gates_20261115T051501Z.json.
ALL PASS.

G-A adversarial invalidation, 19 cases, each
checked three ways (base entry refuses the sibling;
a fresh identity lookup prepares a new entry whose
output is byte-identical to a complete uncached
reconstruction; invalid templates raise on the
identity path exactly as the uncached path does):
middle tx changed; first tx changed; last tx
changed; reordered; witness-only change with txid
fixed; coinbase value changed (valid form);
coinbase value changed (invalid form); prevhash;
version; bits; target; flags; transaction added;
transaction removed; commitment field removed;
commitment field wrong (invalid); fee raised with
value fixed (invalid); fee moved with total fixed
(new identity, byte-identical output); curtime
changed (same identity, served, byte-identical).

G-B positive controls: identical inputs hit the
cache (prepares 1, hits 1, same object) with
byte-identical output; a reused entry stays
byte-identical across boundary extranonces (0, 1,
2, 3, 2^32-1) and 20 random extranonces.

G-C randomised differential campaign: 1,320
(template, extranonce) cases over 11 configurations
(0, 1, 2, 3, 10, 100 and 500 transactions; segwit
fractions 0, 0.5 and 1.0; flags; witness
commitments), cached vs uncached byte-identical on
header, body and every scalar field. Cache prepares
during the campaign: 11 (one per configuration).

## 6. Regtest gate (EXECUTED)

Driver: benchmarks/exp025_regtest.py. Record:
benchmarks/exp025/regtest_20261115T051520Z.json.
A research subclass of production MiningEngine
overrides ONLY build_candidate, routing construction
through the repaired cache; template fetch, the
production ComputeEngine search, block assembly,
submitblock and best-chain confirmation are
production code unmodified. The candidate
construction ran through the repaired cache path
(identity computed and checked on the serving call).

Result: block ACCEPTED on the lab regtest node,
height 826, hash
4d43835d08290e3db41d3953c47e3e39d213f4b2166299c16be38cd57a3e8734,
nonce 0, found on the first extranonce round (cache
prepares 1, identity checks 1; multi-step reuse is
proven by gates G-B and G-C rather than by this
run). The mainnet node, autopilot and miner were
not touched.

## 7. Performance re-check (EXP-017 protocol, EXECUTED)

Predeclared criterion (declared in the bench driver
before timing): VERIFIED only if the
covariate-adjusted 95 percent CI is entirely above
0 in every session and pooled. Arms: A production
build_candidate; B repaired cache with family and
template preparation inside the timed region, and in
the family shape the full identity recomputation
inside the timed region per sibling job, exactly as
an integration would pay it. Paired units of 16
builds, 60 pairs per session, 3 sessions per
comparison, randomised order, EXP-017 analyser
imported unchanged. Raw sessions and analyses under
benchmarks/exp025/.

Identity cost decomposition (medians, 500
transactions, this host; record
identity_cost_20261115T051600Z.json):
- build_candidate: 4.499 ms.
- EXP-023 prototype prepare: 4.214 ms.
- Repaired prepare: 6.414 ms.
- identity_of (one sibling identity recomputation):
  3.573 ms, about 79 percent of a full uncached
  build. This is the honest price of completeness:
  the identity re-derives every txid and wtxid.
- Repaired per-step build after preparation:
  0.023 ms.

Results:
- steps500 (16 extranonce steps on one 500-tx
  template): pooled 23.02x, CI [20.22, 25.93],
  significant in every session and pooled, pairs
  won 1.000. VERIFIED under the predeclared
  criterion. (EXP-023 prototype on the Intel host:
  18.49x; the host differs, so the figures are not
  directly comparable, but the steps shape pays the
  identity once per template and keeps essentially
  all of the gain.)
- family500 (16 sibling jobs of one family, one
  step each): pooled 1.083x, CI [1.022, 1.151],
  significant pooled and in session 1 only;
  sessions 2 and 3 CIs cross zero ([-0.009, +0.219]
  and [-0.101, +0.118] in log units). NOT VERIFIED
  under the predeclared criterion. The identity
  recomputation consumes nearly all of the
  family-shape gain the prototype's 8-field
  fingerprint appeared to buy (EXP-023 measured
  22.06x for this shape on the Intel host with the
  unsafe identity). The remaining family-shape
  savings are the Merkle trees, the body assembly
  and the RPC round trips, worth about 1.08x
  pooled on this host, not proven session by
  session.

Honest summary: the repaired cache keeps a large,
verified gain exactly where the identity is paid
once per template (the extranonce-steps shape,
which is the shape the live GBT mining loop
actually exercises: one template, many extranonce
rounds). Where a fresh identity must be proven per
job, the safe identity costs most of the gain.
That trade is the correct one: the prototype's
family figure was partly bought with correctness.

## 8. Acceptance verdict, item by item

Against the predeclared success criterion:
1. Dependency sets documented and checked against
   the uncached code: PASS (section 2).
2. Identity complete against the analysis, with a
   mutation test for every dependency field: PASS
   (sections 4 and 5; the field list of section 2
   maps one to one onto G-A cases, with time fields
   and the extranonce covered as per-build inputs).
3. Adversarial suite passes in full: PASS (19 of
   19, G-A).
4. Cached and uncached construction byte-identical
   across the randomised corpus: PASS (1,320 cases,
   G-C, plus every G-A new-identity case).
5. Regtest blocks built through the repaired cache
   accepted: PASS (height 826, section 6).
6. No stale body, commitment or Merkle root can be
   served: PASS as a consequence of items 2 to 4;
   the five stale-serve shapes demonstrated against
   the prototype in section 3 all raise or rebuild
   under the repaired identity, and no stale serve
   was constructible against the repaired cache in
   the suite.

Directive acceptance list, additionally: cache
identity complete (yes); adversarial tests pass
(yes); cached and uncached identical (yes); regtest
accepted (yes); no stale reuse path remaining that
could be constructed (none found).

VERDICT: EXP-025 ACCEPTED. The EXP-023 caching
design, AS REPAIRED HERE, is correctness-complete.
The EXP-023 prototype as originally written remains
unsafe and must never be integrated in its original
form. Integration of the repaired design is NOT
performed by this experiment; it is a recorded
recommendation for the owner's decision, with the
section 7 performance picture attached (steps shape
verified 23.02x on this host; family shape 1.083x
pooled, not verified per session).

## Files

- benchmarks/exp025_repaired.py: the repaired cache.
- benchmarks/exp025_defect_demo.py and
  benchmarks/exp025/defect_demo_*.json: the defect
  demonstration against the prototype.
- benchmarks/exp025_gates.py and
  benchmarks/exp025/gates_*.json: adversarial suite,
  positive controls, differential campaign.
- benchmarks/exp025_regtest.py and
  benchmarks/exp025/regtest_*.json: regtest gate.
- benchmarks/exp025_paired_bench.py,
  exp025_analyze_incremental.py, session_*.json,
  analysis_inc_*.json: the EXP-017 re-check.
- benchmarks/exp025_identity_cost.py and
  benchmarks/exp025/identity_cost_*.json: the cost
  decomposition.

Production files (mining/, gpu/) are byte-identical
to their pre-experiment hashes; the EXP-023
prototype files are byte-identical too. The 500 GH/s
minimum objective and the 140 TH/s larger objective
stand unchanged; this experiment is a correctness
gate and claims no throughput toward them.
