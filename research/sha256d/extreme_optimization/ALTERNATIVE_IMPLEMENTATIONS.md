# Alternative Implementations, Ranked for This Hardware

Ranking basis: measured evidence first, then expected
mechanism of gain, then cost. "This hardware" means the
class of machine this lab actually runs and its agents
run: modern x86-64 with SHA-NI and AVX-512 exposed,
typically few cores visible, sometimes capped. Rates cited
are from this VM's records and are labelled by session;
they rank families, they do not promise rates elsewhere.

## Rank 1: H-01 multi-stream SHA-NI (2 and 4 streams)

- Structure: the H-02 kernel's MSG-schedule SHA-NI rounds,
  with 2 or 4 independent nonce chains interleaved inside
  one worker thread; blocked nonce chunks per stream, wave
  dispatch 4 then 2 then 1 so partial waves never hash
  dummy nonces; coverage exact and disjoint.
- Mechanism of gain: latency hiding. A single chain is
  latency-bound on this core (EXP-003); interleaved chains
  issue into each other's stalls.
- Evidence: MEASURED. Per-worker 1-thread medians:
  streams=2 2,515,315 H/s (2.36x its own streams=1),
  streams=4 3,298,604 H/s (EXP-003). Decision run at the
  tuned 2-thread configuration: streams=4 median
  3,084,485 H/s vs production 1,183,205 H/s, but range
  overlap with production's best sample blocked
  integration under the strict rule.
- Known cost: register spills at 4 streams (1,056 B
  frame, 365 xmm stack ops in the inlined hot function);
  wave-atomic early-exit semantics (attempted counts the
  whole final wave, which was genuinely computed).
- Status: best verified family. Awaiting the quiet-window
  decision re-run (X-067) and the geometry sweep (X-001
  to X-005).

## Rank 2: H-02 single-stream direct SHA-NI

- Structure: purpose-built kernel; whole schedule from
  SHA256MSG1/SHA256MSG2; midstate plus block-2 prefix
  snapshots in three modes; counted ABI mirroring
  production.
- Mechanism of gain: removes the streaming-API wrapper
  (B1) and the scalar schedule (B2) around the same
  rounds.
- Evidence: MEASURED. EXP-002 medians 1T 1,690,859 and
  2T 1,966,395 H/s against same-session production
  1,471,854 / 1,403,332; hot function 494 instructions,
  0 B stack frame, zero scalar schedule remnants.
- Known cost: single chain, so it keeps the latency
  ceiling that Rank 1 exists to break; it is Rank 1's
  substrate and permanent fallback form.
- Status: proven correct (120,000 differentials, scalar
  twin equivalence). Not integrated (same decision rule).

## Rank 3: AVX-512 multi-buffer (16-way and 8-way)

- Structure: 16 (or 8) independent hashes in lockstep in
  zmm lanes; vector rounds with vprold rotates; the
  proven alternative Ch and Maj forms; vector schedule
  per lane; mask registers for partial waves.
- Mechanism of gain: width. One instruction advances 16
  round-steps; independent lanes make the aggregate
  insensitive to per-round latency.
- Evidence: UNTESTED in this repo. Prior reasoning in
  CPU_EXECUTION_RESEARCH.md section 3 puts its per-hash
  instruction count in the same few-hundred range as
  Rank 2's measured 494, so the outcome is genuinely
  uncertain in both directions.
- Known cost: highest implementation and verification
  burden of the CPU families; sustained 512-bit frequency
  behaviour unobservable in this guest and must be
  measured by long-run drift (X-041); 32-register file
  helps the schedule but the state plus schedule for 16
  lanes is still a large live range.
- Status: largest untested family; Phase 3 (X-031,
  X-032). GFNI sigma forms (X-020) and carry-save adds
  (X-021) are its design options.

## Rank 4: Production OpenSSL midstate C (the incumbent)

- Structure: mining/cpu/bal_batch.c; per template, block
  1 compressed once into a midstate; per nonce, two
  OpenSSL SHA256_Transform calls through a streaming
  context; pthreads over partitioned spans; counted
  entry points.
- Mechanism: it is the baseline every candidate must
  beat, and its compression (libcrypto SHA-NI) is
  optimal-class.
- Evidence: MEASURED everywhere. EXP-000 medians 1T
  1,314,704; 2T 1,627,792 (the tuned configuration); 4T
  2,512,762 with 82.6 percent spread.
- Known cost: the wrapper (408 instructions, 416 B frame
  per nonce call path); whole-block API cannot express
  prefix snapshots or cross-phase overlap.
- Status: production, byte-identical, protected by the
  integration rule. It remains the correct choice until a
  candidate clears that rule, which is the rule working
  as intended, not a stalemate.

## Rank 5: AVX2 multi-buffer (8-way)

- Structure: as Rank 3 at ymm width, with shift-based
  rotates (3 ops per rotate instead of vprold's 1).
- Mechanism: width, at narrower width and higher
  per-round op count than Rank 3.
- Evidence: UNTESTED. Expected to be dominated by Rank 3
  on this CPU, which exposes AVX-512; retained because
  AVX2 exists on machines where AVX-512 does not, and the
  fleet is heterogeneous by design (H-08 in the H-series
  registry carries the same reasoning).
- Known cost: same verification burden class as Rank 3
  for a strictly smaller prize on this machine.
- Status: Phase 3, second (X-033). A 4-way 128-bit variant
  (X-034) is the low-register-pressure control in the same
  sweep.

## Rank 6: Hybrid dispatch over the above

- Structure: not a kernel but the selection layer:
  startup self-tests plus measured probes pick the
  fastest verified family per machine and span class,
  with structural fallback (gpu/engine.py is the existing
  pattern).
- Mechanism: the fleet's machines differ; the best family
  on this VM need not be the best on another agent's box.
- Evidence: the pattern is MEASURED in production for the
  CUDA / C / Python ladder and for thread tuning.
- Known cost: every selectable family multiplies the
  verification surface; a family earns a dispatch slot
  only with its full gate set green.
- Status: design in CPU_EXECUTION_RESEARCH.md section 5;
  experiments X-082 to X-084.

## Families considered and not ranked

- Scalar-schedule SHA intrinsics (mining/cpu/
  bal_sha_intrin.c): a verified artifact and the historical
  stepping stone, but its deficit is structural (R-05)
  and H-02 supersedes it as a candidate. Kept, not ranked.
- Pure Python and hashlib paths: reference and fallback
  roles (EXP-000: hashlib median 304,444 H/s). Correctness
  infrastructure, not performance candidates.
- CUDA (gpu/cuda/): host-proven, device UNVERIFIED; no
  GPU exists on this VM (H-20, BLOCKED on hardware). It
  joins this ranking the day a device is measured, at
  whatever position its measurements earn.
- FPGA and ASIC packages: design studies (H-21, H-22,
  BLOCKED on hardware). Out of scope for a software
  ranking.
- Bitsliced SHA-256: not ranked as an implementation
  family; registered as X-029 for an analytic bound that
  is expected to close it.
