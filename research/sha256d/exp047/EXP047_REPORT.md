# EXP-047: Cross-backend differential fuzzing at scale

Experiment identity: EXP-047 (portfolio NOVA-ER-0007, register
X-096), Directive 5 Stage 9, first item.
Host: AMD EPYC 9D25 126-Core Processor (guest, 4 vCPUs visible),
recorded from /proc/cpuinfo at campaign time.
Production seam under test: gpu/engine.py (sha256 prefix
bfe605cbb155b59f at campaign start), through ComputeEngine
exactly as production constructs it.
Predeclared: 2026-11-16T15:42:30Z, before any campaign code ran.
Campaign seed: 47047 (all random headers and starts derive from
this seed in a fixed generation order; the campaign is
reproducible byte for byte from the seed alone).

## 1. Question

Do all production backends agree digest-for-digest and
hit-for-hit with the hashlib reference at fuzzing scale, across
random headers, boundary nonces, unaligned spans and target
densities, including densities near the solo share difficulty?

Prior single-integration gates topped out at 648,000 digests
across variants (EXP-041) and 491,520 digests (EXP-022). No
prior campaign compared every backend against every other
backend, through the production seam, at multi-million scale,
as one standing campaign. That is the gap this experiment
closes. Hypothesis (from the portfolio): no mismatches exist;
the campaign's value is the scale and the cross-backend shape.

## 2. Backends enumerated on this host

Constructed through ComputeEngine(requested=...) exactly as
production does, one engine per tier, reused for the whole
campaign:

- v512dual (AVX-512 DualMask), also what requested="auto"
  selects on this host
- v512 (AVX-512 MB)
- shani (SHA-NI streams)
- avx2 (AVX2 MB)
- c (C batch)
- cpu (pure Python hashlib fallback)

CUDA is absent: there is no GPU on this host (no /dev/nvidia*
nodes; ComputeEngine(requested="cuda") reports "CUDA runtime
error 35 (no usable NVIDIA device/driver)" and falls back to
cpu). No CUDA comparison is possible here and none is claimed.

## 3. Predeclared design

### 3.1 Batch digest campaign (Gate 2)

Surfaces per case, per native backend: the backend's own
materialised batch through the seam's internal batch method
(_c_batch, _a_batch, _m_batch, _v_batch, _vd_batch, the same
methods the seam's batch path is built on), compared digest by
digest against the hashlib reference (gpu.engine.cpu_digest)
and pairwise against every other backend's digest list for the
same case (15 backend pairs). The reference digests for a case
are computed once and shared across backends. The cpu engine
has no separate batch ABI: its production batch path enumerates
cpu_digest itself, so its batch digests are the reference by
construction; it is exercised on every search surface below
instead. This identity is stated, not hidden.

Case set (identical for every backend; counts are nonces per
case):

- B1: 24 cases x 65,536, aligned starts (start a multiple of
  65,536), random headers. 1,572,864 digests.
- B2: 8 cases x 65,536, unaligned starts (start not divisible
  by 16), random headers. 524,288 digests.
- B3: 2 cases x 1,048,576 (MAX_BATCH, the production batch
  cap): B3a start 0, B3b start 999,983. 2,097,152 digests.
- B4 boundary spans, 262,177 digests total:
  B4a genesis header, start 0, count 65,536;
  B4b start 2^32 - 65,536, count 65,536 (ends exactly at 2^32);
  B4c start 2^32 - 1, count 1 (the final nonce);
  B4d genesis header, start 2^32 - 16, count 16;
  B4e start 2^32 - 17, count 17;
  B4f start 1, count 65,535;
  B4g genesis header, start 2,083,236,893 - 32,768, count
  65,536 (the span contains the genesis nonce 2083236893).
- B5 partial batches: counts 1, 2, 3, 15, 16, 17, 31, 32, 33,
  63, 64, 65, 100, 1000, 4095, 4096, 4097, 65,535 at start 0
  and at start 12,345, one random header per start. 158,530
  digests.

Predeclared batch total: 4,615,011 digests per native backend
(5 native backends), 4,615,011 reference digests computed once,
69,225,165 pairwise digest comparisons (15 pairs over the same
total). This exceeds the 2,000,000 per-backend floor and every
prior single gate.

### 3.2 Search campaign (hit sets)

Surfaces per case, per backend:

- S-A: ComputeEngine.batch_search candidate nonce set (the
  seam's verified hit set). On every call the stats must show
  the pinned backend, verification_failures 0 and no rescan;
  a rescan would mean the seam stopped trusting the backend
  mid-case and is recorded as a surface failure.
- S-B: the backend's raw flagged pairs through its own
  _x_batch_flagged (nonce set only, no verification layer),
  plus, on the v512 and v512dual engines, the EXP-022 flags
  library pairs through _vf_batch_flagged (the batch path
  batch_search actually routes through on those engines).
- S-C: ComputeEngine.search_first_counted on a declared subset
  (below): the (found, nonce) pair must be identical across
  all backends and equal to the minimum reference hit in the
  span; the reported digest must verify against cpu_digest.

Reference hit set per case: every nonce in the span whose
cpu_digest, read little-endian, is <= target (equality meets).

Density ladder (target, density (target + 1) / 2^256):

- T_FULL = 2^256 - 1, density 1 (every nonce hits)
- T_D8 = 2^248 - 1, density about 2^-8
- T_D16 = 2^240 - 1, density about 2^-16
- T_D24 = 2^232 - 1, density about 2^-24
- T_SOLO = 50 x (0xffff x 2^208), the exact share target for
  solo share difficulty 0.02 (the operative solo difficulty,
  mining/endpoint_config.py SOLO_SHARE_DIFFICULTY). Its density
  is about 1.164e-8, about 2^-26.36: one expected hit per
  about 85.9 million hashes. This is the density the solo
  server judges shares at, so the ladder reaches it exactly,
  with T_D24 as the nearest denser rung.
- T_ZERO = 1, density about 2^-256 (no hits expected)

Cases per density (random headers and starts from the seed,
mixed aligned and unaligned starts as in the batch campaign):

- S_FULL: 4 spans x 65,536 (one is the genesis span containing
  nonce 2083236893, one ends exactly at 2^32). S-C on 2 spans.
- S_D8: 8 spans x 65,536. S-C on all 8.
- S_D16: 4 spans x 1,048,576. S-C on all 4.
- S_D24: 4 spans x 1,048,576. Expected hits about 0.25 total.
- S_SOLO: 8 spans x 1,048,576. Expected hits about 0.098
  total; empty-set agreement at the exact solo density is the
  expected outcome and is reported as such, not dressed up.
- S_ZERO: 2 spans x 65,536; every surface must return the
  empty set and S-C must return no hit on every backend.
- S_FIRST_BOUNDARY: S-C only: T_FULL over start 2^32 - 1,
  count 1 must hit nonce 2^32 - 1 on every backend; the
  genesis header at target DIFF1 (0xffff x 2^208) over start
  2083236893 - 3, count 1000 must hit nonce 2083236893 on
  every backend.

Predeclared search totals per backend: 30 batch_search calls,
17,694,720 nonces covered per surface, 16 search_first_counted
calls plus the 2 boundary calls.

### 3.3 Malformed inputs (Gate 3, input dimension)

Per engine (all six), through batch_search unless noted;
every case must raise ValueError, uniformly across engines:

- G1 header 79 bytes; G2 header 81 bytes; G3 target 0;
  G4 target 2^256; G5 target -1; G6 start -1; G7 count 0;
  G8 count -5; G9 count 1,048,577 (MAX_BATCH + 1);
  G10 crossing span start 2^32 - 100, count 200;
  G11 start 2^32, count 1.
- G12 search_first_counted crossing span; G13
  search_first_counted target 0; G14 search_first_counted
  header 79 bytes.

Per native backend (five), at the library ABI the seam wraps:
G15 _x_batch_flagged over start 2^32 - 8, count 16 (crossing)
must refuse (return None, no pairs); G16 _x_batch over the
same span must refuse (return None). Spans ending exactly at
2^32 are valid and are covered in B4, not here.

### 3.4 Failure rule

Any mismatch anywhere is a FAILURE of the campaign: the
driver stops at the first mismatch, records the full case
(backend, case id, header, start, count, target, nonce,
expected and actual digest), shrinks it to a minimal
reproducing case, and this report records it as a critical
defect. Production code is not modified by this experiment
under any outcome.

## 4. Gates

Gate 2 (differential verification) is the entry gate and the
substance of sections 3.1 and 3.2. Gate 3 (adversarial testing)
applies in its input dimension only, section 3.3. Gates 1, 4,
5 and 6 do not apply: no new mathematics, no performance claim
(this campaign times nothing and reports no hash rate as a
result), no operational or regtest component. Production code
is read-only throughout; the live mining stack is never
touched, signalled or reconfigured.

## 5. Results

Campaign run 2026-11-16T15:44:12Z onward, seed 47047, driver
exp047_fuzz.py, raw records under RAW_RESULTS/ (manifest,
batch_results.json, progress.jsonl, mismatch.json).

### 5.1 Batch campaign: executed in full, zero mismatches

All 77 predeclared cases completed. Per native backend
(v512dual, v512, shani, avx2, c): 4,615,011 digests, every one
byte-identical to the hashlib reference; 4,615,011 reference
digests computed once and shared. Direct pairwise comparisons
among the five native backends: 46,150,110 (10 pairs). The
predeclared 69,225,165 total counted all 15 pairs over six
backends; the five pairs involving the cpu backend are the
reference comparisons themselves (5 x 4,615,011 = 23,075,055),
since the cpu backend's digests are the reference by
construction, so the executed pairwise total is the
predeclared total with the decomposition stated here. No
backend refused a valid span, no length error occurred, and
the boundary set (spans ending exactly at 2^32, the final
nonce, partial batches down to count 1) matched everywhere.

### 5.2 Search campaign: stopped at the first mismatch

Executed: case S_FULL-00 only (genesis header, T_FULL, start
2083204125, count 65,536; the reference hit set is all 65,536
nonces).

- v512dual: batch_search set exact, own flagged pairs exact,
  flags-library pairs exact, search_first_counted returned
  the span minimum (S-C passed).
- v512: batch_search set exact, own flagged pairs exact,
  flags-library pairs exact, then search_first_counted
  returned nonce 2083236893, not the span minimum 2083204125.
  MISMATCH. The driver stopped the campaign at once, per
  section 3.4. Record: RAW_RESULTS/mismatch.json.

Not executed: S_FULL-01 to 03, S_D8, S_D16, S_D24, S_SOLO,
S_ZERO, S_FIRST_BOUNDARY, and the whole of Gate 3 (section
3.3). The predeclared search totals (30 cases, 17,694,720
nonces per backend per surface) were not reached; executed
search coverage is the 65,536-nonce case above on the
surfaces listed.

Pre-campaign smoke probes (driver validation, not campaign
results): the library-level crossing-span refusal (the G15
and G16 shape) held on all five native backends; a 37-nonce
batch probe matched the reference on all five; genesis
search_first returned nonce 2083236893 on all six engines.

### 5.3 Critical finding: the search winner is first-publisher-wins

Defect statement. The predeclared cross-backend invariant
"search_first_counted returns the minimum hit of the span,
identically on every backend" is false for every
multithreaded native backend. The mechanism is in the
production source: mining/cpu/bal_search.h partitions the
span into per-thread contiguous spans (bal_partition) and
bal_ctx_publish is explicitly first-publisher-wins (its own
comment: "Only the first publisher wins"); every native
search ABI publishes through it (bal_avx512_mb.c,
bal_avx512_dual.c, bal_avx2_mb.c, bal_batch.c,
bal_shani_streams.c). When several thread spans hold hits,
which genuine hit is returned depends on thread scheduling.

Evidence. The campaign observation: v512 (2 threads tuned
that run, spans of 32,768) returned start + 32,768, the first
nonce of the second span. Characterization after the stop
(exp047_characterize.py, RAW_RESULTS/characterization.json;
characterization, not campaign): the failing case repeated
200 times per native backend at density 1 produced
non-minimum genuine returns of 22/200 (v512dual), 108/200
(v512), 27/200 (shani), 59/200 (avx2), 130/200 (c); every
non-minimum return was exactly the first nonce of another
thread span (offsets at the bal_partition boundaries for
each engine's thread count); zero no-hit returns and zero
wrong digests in those 1,000 calls. v512 at threads=1
returned the minimum 50/50. At T_D8 (24 random spans, all
six backends) and T_D16 (8 random spans of 262,144, all six
backends) the found flag agreed with the reference on every
span for every backend, with zero false hits, zero false
misses and zero bad digests, while non-minimum genuine
returns occurred on every native backend (7 to 19 of 24 at
T_D8; 4 to 7 of 8 at T_D16); the cpu backend, an in-order
Python scan, returned the minimum every time. The minimal
repro (RAW_RESULTS/minimal_repro.py) reproduced the exact
campaign nonce 2083236893, offset +32,768, on call 0.

What the defect is not. No digest produced by any backend
was wrong anywhere in this experiment: 23,075,055 backend
digests in the batch campaign, every flagged-pair digest in
the executed search surfaces, and every returned search
digest in 1,242 characterization calls verified against
hashlib. No search call invented a hit or missed a span's
hits anywhere. batch_search hit sets were exact on every
executed surface.

Production impact, stated plainly. None on mining
correctness, consensus or accounting: production search
consumers receive a candidate that is independently verified
before any submission (the seam verifies candidates inside
search_first_counted; the solo path verifies through
EXP-036), and any genuine hit is a valid share or block
candidate; nothing in production requires the returned
candidate to be the span minimum. What fails is determinism
of which genuine candidate a multithreaded native search
returns when a span holds several hits. A caller that needs
the minimum hit must use batch_search enumeration (exact
here at 4.6M scale) or a single-threaded search. The finding
is recorded as a critical defect in the experiment's terms
because a plausible cross-backend invariant is false in
production code as designed; whether to accept and document
the semantics or pay for a minimum reduction in the search
context is a later integration decision. Production code was
not modified by this experiment.

### 5.4 Suites

Run one at a time after the campaign, all passing:
make test-gpu (ALL GPU COMPUTE TESTS PASSED),
make test-avx512 (PASSED; the suite mined regtest block 1907
through the production path), make test-avx512dual (PASSED;
regtest block 1908). Full test-all was not run, per the
experiment brief.

### 5.5 Live stack

Share census from evidence/mainnet-live.jsonl: 586 accepted
/ 8 rejected before the campaign; 587 / 8 after (the +1 is
the live miner's own pool share at 2026-11-16T15:48:34Z,
during the suite window). The live stack was never touched,
signalled, restarted or reconfigured by this work.

## 6. Verdict

Campaign verdict: FAILED under its own predeclared failure
rule (section 3.4). The search campaign stopped at its first
mismatch, in its first case; the batch campaign had already
completed at full predeclared scale with zero mismatches.

Three-tier classification:

- VERIFIED (a correctness result, not a performance
  improvement; this campaign reports no hash rate as a
  result): digest-for-digest and hit-for-hit agreement of
  all five native backends with the hashlib reference, and
  pairwise, at 4,615,011 digests per backend, across random
  headers, boundary nonces, unaligned spans, partial batches
  and spans ending exactly at 2^32. This is the largest
  single differential campaign in the programme (prior
  maxima 648,000 across variants and 491,520) and it is
  clean.
- ESTABLISHED NEGATIVE: the hypothesis that
  search_first_counted returns the minimum hit of a span,
  identically across backends. Refuted by the campaign
  observation, by reproduction, by characterization across
  all five native backends, and by the production source.
  The cpu backend, and any native backend at one thread, do
  return the minimum.
- NOT EXECUTED, therefore UNVERIFIED by this experiment:
  the remaining predeclared search cases (S_FULL-01 onward,
  including the T_D24, T_SOLO and T_ZERO ladders and the
  boundary first-hit calls) and the Gate 3 malformed-input
  set G1 to G16 as campaign items. Hit-set agreement at the
  exact solo share density (T_SOLO) in particular remains
  unverified; what exists is the smoke-probe and
  characterization evidence at densities 1, 2^-8 and 2^-16.
  A follow-up campaign with a corrected S-C criterion
  (found-flag agreement plus hit genuineness, not minimum
  identity) is the natural completion; it is a parent
  programme decision, not assumed here.

## 7. Limitations and unverified register

- CUDA: absent on this host, untested by this campaign.
- The cpu backend's batch digests are the hashlib reference by
  construction (section 3.1); its independent surface is the
  search campaign.
- Single host (AMD EPYC 9D25). The SHA-less Intel host would
  exercise the same libraries' refusal paths, not different
  digest code; digest agreement there remains covered by the
  per-integration gates, not by this campaign.
- The S-C criterion as predeclared exceeded the production
  search's designed semantics (first-publisher-wins is a
  deliberate early-exit design, documented in the source).
  The failure is recorded against the criterion and the
  design fact is recorded with it; both halves matter, since
  an invariant a future caller might assume is false.
- Thread counts are auto-tuned per engine construction and
  vary with contention (v512 tuned 2 threads for the
  campaign run and 4 in one characterization run), so the
  characterization's divergence rates are host-and-load
  specific; the existence of the divergence is not.
