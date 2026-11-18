# Stage 9.6: Mainnet Readiness Report

Stage: NOVA SHA-X Stage 9.6 (mainnet readiness gates and
live evidence). Basis: remote HEAD
5b4b27a1fb5f09172748be6cdcb34e1dd7dcda11 (the Stage 9.5
push; the local checkout carries no .git, so the remote
HEAD value itself is taken from the stage brief and is
UNVERIFIED from this host; every file-level claim below was
verified locally by content hash). Live observation window:
2026-11-18T07:06:35Z to 07:11:23Z. Raw evidence:
research/STAGE9/evidence_96/ (live_observation.json,
gap_computation.json, compute_gap.py).

Verdict in one paragraph: the lab is NOT mainnet-ready by
its own success criterion, and this report does not claim
otherwise. The production mining path is correct against
Bitcoin Core (Stage 9.3, audited), the test record at HEAD
is complete with every failure classified (Stage 9.3, as
corrected), CI is green on its clean-runner subset, and the
live stack demonstrably submits valid work: 1,082
pool-accepted shares observed live in this window. Against
that, the local node is still in initial block download
(471,150 of 976,395 headers), the solo cutover has
correctly not fired, the live stack has never produced a
network-target candidate, and no mainnet block has ever
been found: the balance is 0 BTC and the success criterion
(a real, independently verified, submitted, accepted
mainnet block) is NOT met. Five further gates are
BLOCKED-BY-OWNER: they wait on decisions only the owner
can make, and they are recorded as blocked, not passed.

Method note: this stage changed nothing. All live
observation was read-only (process listing, heartbeat and
status files, the evidence counter, the endpoint config
read for its hash, one read-only solo_cutover.py check, and
node RPC reads). The autopilot, miner, node, endpoint
config and cutover marker were not touched. Production
source hashes observed in this window match the audited
record exactly (mining/engine.py
866936fd6d41ebcc3a5ecbde886b0a5aa27eeae6ad5483025ddf0b3f1635f1ec,
the post Stage 9.4 value; mining/mainnet_live.py,
mining/autopilot.py and gpu/engine.py at their Stage 9.1
baseline values), so the Stage 9.3 and 9.4 findings stand
on the same source they audited.

## E1. Readiness gates

Fourteen gates. Verdicts: PASS 4, FAIL 5,
BLOCKED-BY-OWNER 5. A gate that depends on an owner
decision is marked BLOCKED-BY-OWNER, never passed.

| Gate | Requirement | Verdict | Evidence |
| --- | --- | --- | --- |
| G1 | Production mining path correct against Bitcoin Core | PASS | Stage 9.3 B2: production-constructed blocks accepted by Core 28.1 on isolated regtest (height 1 and the witness block at height 145), after the BIP34 coinbase-height defect (D-93-1) was found by that exercise and fixed in mining/engine.py script_num_push. Stage 9.5 re-proved the same path end to end (8 agent-mined blocks accepted). |
| G2 | Test suite state at HEAD known, failures classified | PASS, with two linked owner decisions at G12 | Stage 9.3 full run: 48 PASS, 3 FAIL of 51 targets. The three failures are classified, none is a production code defect: test-rtl (environment, iverilog not installed), test-exp052 (environment, host-fingerprint fail-closed fallback working as designed), test-task0039 (contention-sensitive promptness bound; its exact-accounting checks pass). test-all now has 52 prerequisites (Stage 9.4 added test-status-publisher, which passes locally). |
| G3 | CI runs on push and is green at HEAD | PASS | .github/workflows/test.yml runs the clean-runner subset (test-exp037, test-exp038, test-probability, test-exp049), verified in the workflow file this window. Final-HEAD CI run at the current HEAD: run 44255704573, completed, success (Stage 9.5 push record). The full suite record remains the local Makefile run at G2; the subset is what a clean runner can execute, per the Stage 9.3 corrections. |
| G4 | Live stack submits valid, pool-accepted work | PASS | Observed live this window: autopilot pid 2830, miner pid 2833, state running, restarts 0; shares_accepted_total 1,082 at 2026-11-18T07:11:11Z and rising (1,079 to 1,082 across the window); EXP-037 evidence counter agrees (accepted 1082, rejected 8, share_results 1090). Backend v512dual, selected by the production dispatch. |
| G5 | Local mainnet node fully synced | FAIL (in progress, not a defect) | getblockchaininfo this window: blocks 471,150, headers 976,395, initialblockdownload true, verificationprogress 0.1505, pruned (pruneheight 470730). The node is validating and advancing (471,126 to 471,150 during the window) but is roughly 505,000 blocks behind the header tip. Its RPC answered on the first attempt in this window and timed out on another call minutes apart, the standing IBD-load pattern. No ETA is promised. |
| G6 | Solo cutover executed: miner on the lab's own solo server | FAIL (correctly gated on G5) | solo_cutover.py check this window: NOT_READY, exit 3, "node in initial block download (471133 of 976392 headers)". The marker file .local/solo-cutover.json does not exist: the cutover has never fired. The endpoint config is still in pool mode (mode "pool", public-pool.io:21496; sha256 d741cde3c6224406f46f3bae138fb174eb1d780725bcb94baff4e14a8670c7d3, unchanged across Stages 9.3 to 9.6). The mechanism is armed and behaving as designed; it cannot pass until G5 passes. |
| G7 | Live stack has produced a network-target candidate | FAIL (none ever; statistical, see E2) | Census of every status event in .local/miner.out (3,639 snapshots, 2026-11-14 to 2026-11-18): network_target_candidates is 0 in all of them; sampled share_submitted events carry is_block_candidate false. The best share difficulty observed in this window is 51.2302 against a network difficulty of 134,823,837,323,272.66. |
| G8 | Success criterion: a real mainnet block, independently verified, submitted and accepted | FAIL (not met) | Zero blocks submitted, zero accepted, in the same census (blocks_submitted 0 and blocks_accepted 0 in all 3,639 snapshots). Wallet bc1q528egeqsvv8aa382j43edxskqw6x7zxc2xpcf3 balance 0 BTC. See E2 category (c). |
| G9 | Fleet activation (EXP-035 design, EXP-055 coordinator) | BLOCKED-BY-OWNER | Coordinator proven at protocol level on one host, including the Stage 9.4 cross-process B1 exercise; multi-machine behaviour UNVERIFIED. Stage 9.2 class: KEEP DISABLED / EXPERIMENTAL. Activation requires the owner's word and a genuine multi-machine test first (Stage 9.2 open item 4). |
| G10 | EXP-052 bake-off dispatch live enablement | BLOCKED-BY-OWNER | Campaign verdict STATIC by dominance on one AMD host; rotations outstanding (Intel Xeon 8321HC, second AMD), measured-winner Gate 5 not run, and any 5 percent certification campaign needs its own predeclaration. Resolver seam is live but default-off with no cache planted (Stage 9.2 F-3). DEF-9.2-1 (G12) must be fixed before any enablement. |
| G11 | EXP-057 aggregation deployment; EXP-058 PID live actuation | BLOCKED-BY-OWNER | EXP-057 proven for measured on-VM properties only; real upstream and multi-machine tests UNVERIFIED. EXP-058 ships disabled; its canary-probe observability design needs its own predeclaration and experiment before promotion (Stage 9.2 open item 6). |
| G12 | Code hardening and test-design decisions: DEF-9.2-1, DEF-9.2-2, registry repair, D-93-2, D-93-3, EXP-047 semantics | BLOCKED-BY-OWNER | DEF-9.2-1: unguarded host_fingerprint() call at the bakeoff seam (bakeoff_dispatch.py lines 566 to 567; caller in mainnet_live.py has no wrapper); documented, not fixed. DEF-9.2-2: unconditional prefetch import at mining/engine.py line 26; documented, not fixed. Registry repair (R-23, R-27, R-32, R-33, R-35 status updates plus D-02/D-03/D-04/D-06 text fixes): prepared in Stage 9.2 section 6, not applied. D-93-2: test-task0039 bound (quiet-host run or thread bound; must not be silently loosened). D-93-3: test-exp052 Gate 5a design (accepting the proven doubt fallback as a pass would be a test-design change). EXP-047: owner decision on search semantics (first-publisher-wins as documented production semantics, or pay for a minimum reduction). |
| G13 | EXP-050 endpoint health live enablement; EXP-051 prefetch live enablement | BLOCKED-BY-OWNER | EXP-050 defaults equal today's behaviour; live enablement needs a real second endpoint, which does not exist in this deployment, plus an owner decision. EXP-051 is opt-in and default-off; GBT-path live enablement is an owner decision and its mainnet difficulty effect is UNVERIFIED (Stage 9.2 F-1, F-2). |
| G14 | Autonomous mainnet operation by the agent stack | FAIL (explicitly not claimed) | Stage 9.4 classifications stand: C1 and C2 agent-assisted, C3 agent-controlled inside the package when driven but inactive in live production, C4 agent-controlled at protocol level on one host and deployed nowhere. Stage 9.5 proved autonomous discovery on regtest only; the agent's chain guard refuses mainnet without an explicit flag no one has passed. The live mainnet lifecycle belongs to the autopilot and the external keeper, not to the agent. |

Also outstanding, recorded so they are not lost: the
EXP-039 tier refusal check on the SHA-less Intel host and
an AVX2-only host (host-gated, Stage 9.2 open item 10);
the EXP-056 corrected-plant control re-run, owed if that
campaign resumes (open item 7); in-loop candidate
verification on the GBT agent path (Stage 9.5 gap 1: the
agent path verifies through Core's verdict by design, and
the production verifier had to be shimmed at the
submission boundary for the 9.5 run; whether to move it
inside the cycle is an owner decision); whether
test-status-publisher joins the CI subset (Stage 9.4 audit
recommendation: only after its own cleanroom run); and the
keeper rule's application during IBD (owner decided the
rule, keep restart on RPC silence; restarts have been held
since 2026-11-17 21:06 PST because the literal rule loops
during sync; awaiting the owner's word).

## E2. Live evidence, three separate categories

These categories are kept strictly separate. A share is
not a candidate; a candidate is not a block; only
category (c) counts toward the success criterion.

### (a) Pool-accepted shares: 1,082

Observed directly this window from the live stack's own
accounting: heartbeat shares_accepted_total 1,082 at
2026-11-18T07:11:11Z (autopilot pid 2830, miner pid 2833,
miner_state running, restarts 0), corroborated by the
EXP-037 evidence counter (.local/evidence-count.json:
accepted 1082, rejected 8, share_results 1090). The count
rose during the window (1,079 to 1,082), so this is a
live, working submission path to public-pool.io:21496
under worker htch-runtime, on the v512dual backend. What
shares prove: the stack constructs valid jobs, searches
them with exact SHA-256d, and submits work the pool
accepts at pool difficulty. What shares are not: blocks,
candidates, or earnings. The pool is solo-style: its
balance stays 0 unless a full block is found, so 1,082
accepted shares correspond to 0 BTC earned.

### (b) Network-target candidates: none

A network-target candidate is a searched header whose
SHA-256d meets the full current network target (the
EXP-036 verifier's block_candidate classification at
network difficulty). The live stack has never produced
one: network_target_candidates is 0 in every one of the
3,639 status snapshots in .local/miner.out (2026-11-14 to
2026-11-18), and blocks_submitted is 0 in all of them.
The best share difficulty seen this window is 51.2302;
the network difficulty is 134,823,837,323,272.66. This is
the expected state at the live hash rate (see the
waiting-time estimate below), not a malfunction: the
miner is running, submitting, and being accepted at pool
difficulty throughout.

### (c) Accepted mainnet blocks: zero. Balance: 0 BTC.

No block paying the lab wallet
bc1q528egeqsvv8aa382j43edxskqw6x7zxc2xpcf3 has ever been
accepted into the mainnet best chain by this stack:
blocks_accepted is 0 in every status snapshot, no
submission has ever been made (category (b) is empty, so
there has never been anything to submit), and the pool
balance is 0 BTC by the solo-style design. The success
criterion, a real, independently verified, submitted,
accepted mainnet Bitcoin block, is NOT met. Nothing in
categories (a) or (b) may be read as progress toward it in
any unit other than elapsed search time, which the next
section quantifies honestly.

## Expected waiting time (STATISTICAL ESTIMATE)

Inputs, both observed live this window:

- Current network difficulty: 134,823,837,323,272.66,
  reported by the live miner's template_validated events
  (2026-11-18T07:07Z, job nbits 17021673; the pool serves
  current mainnet templates). Cross-check: the difficulty
  computed from nbits 0x17021673 alone equals the reported
  value exactly (evidence_96/gap_computation.json). The
  local node cannot supply this figure yet: its own
  getblockchaininfo difficulty (678,760,110,082.99)
  describes its validated tip at height 471,126, a 2017-era
  value, because the node is still in IBD (G5).
- Sustained hash rate of the live stack: 21,357,487 H/s,
  the cumulative average over the current miner run at the
  final sample (85,259,089,184 hashes in 3,992 s;
  four samples over about 4.5 minutes, miner-printed rates
  21,172,085 to 21,355,505 H/s; full record in
  live_observation.json). The interval rate over the
  sampling window alone was higher (24,270,567 H/s); the
  cumulative figure is used because it is the conservative
  whole-run average. The rate was measured on this loaded
  host (live miner, syncing node, load average about 10 on
  the 5 minute figure at first observation), which is the
  honest operating condition of the live stack.

Arithmetic (reproducible: evidence_96/compute_gap.py):

- Expected hashes per block = difficulty x 2^32
  = 134,823,837,323,272.66 x 4,294,967,296
  = about 5.7906e23 hashes.
- Expected waiting time = expected hashes / rate
  = 5.7906e23 / 21,357,487
  = about 2.7113e16 seconds
  = about 859,000,000 years (859,156,780 years at the
  figures above).

This is a STATISTICAL ESTIMATE: the expected value of a
geometric waiting-time distribution at constant difficulty
and constant rate. The actual time is random (a block
could in principle arrive on the next hash, or far beyond
the expectation), and difficulty retargets every 2,016
blocks. The estimate's purpose is scale honesty: at the
live rate, a mainnet block is not a plausible outcome on
any human timescale, and no readiness claim may rest on
waiting for one. PERFORMANCE_GAP_REPORT.md quantifies the
distance to the programme's standing targets.

## What would have to change for a readiness claim

In order: G5 resolves only with time (the node finishes
IBD; nothing in this programme can hurry it, and its
progress is observable). G6 then becomes fireable by the
armed cutover mechanism, moving the miner to the lab's own
solo server; that changes where work is submitted, not the
probability of a block. G9 to G13 resolve only by owner
decision, several of them additionally needing evidence
that does not exist yet (multi-machine tests, a second
endpoint, host rotations). G7 and G8 resolve only by an
event whose expected waiting time is about 8.6e8 years at
the current rate: they are not schedule items. A
mainnet-readiness claim that means "the stack is correct,
tested, supervised and mining valid work" is supportable
today on G1 to G4. A claim that means "a block is a
realistic prospect" is not supportable at any current or
projected CPU-software rate in this programme, and the
standing targets (500 GH/s minimum, 140 TH/s larger
objective) remain at full height, unmet, and unlowered.

## Evidence index (research/STAGE9/evidence_96/)

- live_observation.json: every live value cited above,
  with timestamps and sources (processes, heartbeat,
  evidence counter, miner status samples, node RPC,
  endpoint config hash, production file hashes, solo
  cutover check output, miner statistics census).
- gap_computation.json: the output of compute_gap.py on
  the observed inputs (difficulty cross-check, rate
  samples, expected hashes, expected wait, systems to
  target).
- compute_gap.py: the arithmetic, reproducible.
