# Reverse Engineering: How Established Implementations Are Built, and Why

Method: for each established design, state its structure,
the assumption its designers made, and whether this lab's
measurements support or contradict that assumption on the
machine that exists here (EPYC 9D25 KVM guest, SHA-NI,
AVX-512, about 1.5 effective CPUs). Copying a design
without its assumption is how a lab inherits other
hardware's answers. Nothing in this document is a design
target by itself; the targets are in
ALTERNATIVE_IMPLEMENTATIONS.md.

## 1. OpenSSL libcrypto SHA-256 (the incumbent's engine)

Structure, as measured from this repo's binaries
(../assembly_analysis.md): libcrypto.so.3 carries 128
sha256rnds2 sites and dispatches to the SHA-NI
implementation at runtime by CPU capability. The lab's
production library contains zero SHA-NI instructions of
its own; it calls SHA256_Transform four times per nonce
class through a streaming context (SHA256_CTX), and its
wrapper hash_nonce is 408 instructions with a 416 B stack
frame (EXP-001).

Design assumptions: a general-purpose library must hash
arbitrary messages of arbitrary length, in pieces, for
arbitrary callers. Its unit of work is the whole 64-byte
block transformed from a caller-held state. It cannot
know that block 1 of every mining header is fixed per
template beyond the midstate trick the caller performs,
cannot split a block mid-rounds, and cannot overlap one
message's phases with another's.

Verdict from measurement: the assumption is correct for a
library and expensive for a miner. The compression is
optimal-class; everything this programme has gained or
stands to gain comes from the structure around it
(midstate reuse, MSG-schedule hand kernels, interleaving),
never from restyling its rounds. EXP-001 closed the
compiler-flag version of this question permanently.

## 2. The classic published SHA-NI miner structure (Intel whitepaper lineage)

Structure: state in the org-form two-register packing;
schedule by SHA256MSG1 and SHA256MSG2 in the GENA/GENB
construction; rounds as RNDS2 pairs fed by pre-added K+W
operands; one hash per instruction stream.

Design assumption: the schedule instructions exist
precisely so the schedule stops being scalar work, and a
single stream, well fed, is the natural unit.

Verdict from measurement: half right, and the halves are
now separated by evidence. The schedule half is fully
vindicated: the lab's H-02 kernel follows this structure
exactly and the MSG schedule alone is worth about 2.6x
over a scalar schedule at equal rounds (EXP-002, proven
by the scalar twin). The single-stream half is refuted on
this core: one chain leaves most of the core's issue
capacity idle behind round latency, and interleaving two
to four chains per worker multiplies throughput (EXP-003).
The whitepaper structure is the correct kernel anatomy
and an incomplete execution strategy.

## 3. cpuminer-style multi-algorithm dispatch

Structure: a table of algorithm implementations, CPU
feature detection at startup, a scanhash contract (hash a
range, report attempts, return on hit), per-algorithm
thread management, and work distribution from a stratum
or GBT source.

Design assumptions: hardware varies more than algorithms
do, so the miner's job is selection among verified
implementations; and the search contract must make
coverage auditable (the ancestor of this lab's Task 003.9
accounting).

Verdict: the assumptions match this lab's own evolution.
ComputeEngine (gpu/engine.py) already implements the
selection half (self-test, then measured fallback, reason
recorded) and tune_c_threads the per-machine tuning half.
What this programme adds is candidates worth selecting
among, and the sweep discipline (X-049, X-082) to keep
selection honest as the candidate count grows. The part
of the cpuminer lineage this lab deliberately does not
copy is permissive result reporting: coverage and actual
computations are separate fields here, by rule.

## 4. Multi-buffer vector SHA (library lineage, ISA-L style)

Structure: N independent messages processed in lockstep,
one per vector lane, with the full round function and
schedule evaluated in vector registers; a manager feeds
lanes from a queue of pending messages and drains finished
ones.

Design assumptions: the caller has many independent
messages (true for TLS record batches and storage
checksums, the design's origin), vector ALUs are wide and
cheap relative to their width, and per-message latency is
worth trading for aggregate throughput.

Verdict: mining satisfies the many-messages assumption
perfectly (nonces are independent by definition), which
the design's original callers only sometimes did. The
open part is the second assumption, and it is genuinely
open: SHA-NI changed the comparison since multi-buffer's
era, and nothing in this repo measures a vector
multi-buffer SHA-256 yet. This is the largest untested
implementation family on this CPU (X-031 to X-034), and
its historical arc matters: it was not refuted, it was
displaced, by hardware that postdated it and that this
programme has already measured to be latency-bound in
single chains. Wide vectors with native rotates
(AVX-512 vprold) are a condition its original designers
did not have.

## 5. ASIC mining architecture (contrast only, not a target)

Structure, from the lab's own pre-layout package (asic/,
../results/ASIC_RESULTS.md) and the general design of
shipping miners: the round function is unrolled in
silicon, pipelines one or more hashes per clock per core
at hundreds of MHz, with thousands of cores per unit.
results/RESEARCH.md cites about 200 TH/s for a current
ASIC unit.

Design assumptions: area is cheap, so the serial round
chain is defeated by depth (a pipeline holds a different
hash at every round stage) rather than by latency hiding;
and power per hash, not instruction elegance, is the
metric.

Verdict: the assumption is correct and unreachable from
software. The ASIC comparison exists in this programme
for exactly one purpose: to size the mandate's targets
honestly. 140 TH/s is approximately one modern ASIC unit;
PERFORMANCE_ROADMAP.md derives what that means in CPU
cores. The lab's FPGA and ASIC records (fpga/, asic/)
stand as design studies with their hardware gates
UNVERIFIED; this programme's CPU software work neither
borrows their claims nor lends them any.

## 6. Techniques set aside by history that modern CPUs reopen

1. Multi-buffer vector SHA (section 4): displaced by
   SHA-NI, reopened by AVX-512 width, native vector
   rotates, and 32 vector registers. Status: untested
   here, Phase 3 of the roadmap.
2. Deep SHA-NI interleaving beyond 2 streams: known in
   principle since the instructions shipped, but the
   16-register file made 4 streams a spill exercise, and
   most implementations stopped at 1 or 2. This lab's
   EXP-003 measurement (spills cost less than the latency
   they hide, on this core) reopens the question
   empirically rather than by preference, and locates the
   actual cliff as an experiment (X-002, X-003).
3. Carry-save and redundant-representation addition:
   standard in hardware SHA cores, largely absent from
   software because scalar adds are already fast; vector
   rounds, where the add tree is explicit in the
   instruction stream, give it somewhere to live again
   (X-021, X-022).
4. Schedule generation by dedicated instruction (MSG1/
   MSG2): present since SHA-NI shipped, yet the lab's own
   first intrinsics kernel shipped without it and paid
   2.6x for the omission; a reminder that "available in
   the ISA" and "used by the implementation" are different
   claims, which is why this programme counts instructions
   in compiled binaries instead of trusting source.

## 7. Assumptions ledger

| Design | Core assumption | Lab verdict |
|---|---|---|
| OpenSSL streaming Transform | Callers need arbitrary messages | True for a library; the miner pays for it (B1) |
| Whitepaper SHA-NI kernel | MSG schedule plus a fed single stream suffices | Schedule: proven. Single stream: refuted on this core |
| cpuminer dispatch | Selection among verified candidates beats one fixed path | Supported; already this lab's architecture |
| Multi-buffer vector SHA | Many independent messages; wide ALU economics | Messages: perfectly true in mining. Economics: untested here |
| ASIC pipelining | Defeat latency with depth; area is cheap | True in silicon; defines the target gap, not a software method |
