# EXP-035: Integration Decisions

Decision of record for this phase: **no production
integration**. EXP-035 delivers a design and a tested
research prototype only, per the directive (section 8:
design only at first; do not activate the 25 agents).

## Adopted into the design (from the reference matrix)

| Row | Idea | Form in this design |
|---|---|---|
| M06 | Qaxe extranonce2 partitioning, (slave_id << 25) + counter25 | Adopted as the coinbase dimension of the search space: (slot << 25) + counter, slot bound per worker per job, disjoint by construction |
| M14 | Qaxe CAN master worker registry, telemetry timeout, foreign-fleet rejection | Adopted: persistent registry, 10 second class heartbeat timeout, fleet identity check on registration |
| M15 | Starved slave re-registers | Adopted: starvation window; a leaseless worker past the window must re-register before leasing; re-registration restarts its clock |
| M13 | Master verifies centrally, slaves never submit | Adapted: workers report candidates to the coordinator; the EXP-036 verifier judges; only the coordinator submits. CAN transport and the dumb-worker model rejected (NOVA workers keep local state) |
| M04 | Job slot registries in both firmwares | Adapted: job identity is (job_id, generation); the generation tag removes the slot-recycling ambiguity (W3) both references accept |
| M05 | Clone-on-read job access | Adopted as a rule for the job record consumers (EXP-034 contract) |
| M12 | Qaxe duplicate nonce ring | Adapted: intent kept, mechanism replaced; dedup key is the full header identity over the whole queue history, not a 32-entry (nonce, version) ring (W2) |
| M31 | Qaxe CAN multiframe transfer | Adapted: length-prefixed frames kept as the wire discipline, with the total length and payload checksum the reference lacks (W7) added |
| M26 | Failure isolation (as a design rule) | Adopted: per-worker and per-VM failure domains; one worker's fault reclaims only its own leases |
| M27 | Scale sensing and capacity with device count | Adapted as a budgeting rule: verifier throughput bounds fleet size; queue backpressure pauses leases, never drops candidates. No capacity number is claimed |
| M34 | Newer silicon rolls more than the nonce | Adapted: version rolling (BIP320 mask), extranonce and ntime are one combined declared space with exact disjoint accounting |

## Rejected

| Idea | Reason |
|---|---|
| Dividing the 32-bit nonce range as the distribution model | Directive section 8 forbids the assumption; the space is multi-dimensional (section 2 of the design) |
| Workers submitting results directly to a pool or node | One verified submission path (M13 as adapted); direct submission would bypass EXP-036 exact verification |
| Float difficulty anywhere in work accounting | Coverage and candidacy are exact integer matters; difficulty is a display statistic (EXP-036 rule, matrix M02/M03) |
| Leases surviving a coordinator restart | A surviving lease would let a stale token claim work the new coordinator epoch cannot vouch for; reclaim-and-re-register is the honest semantics (EXP-029 rule, kept) |
| Activating the fleet agents for this phase | Forbidden by the directive and by the task; all testing was local simulation |

## Deferred to the production integration phase

- The coordinator service itself (journal, snapshots,
  wire frames of design section 9).
- Wiring EXP-034 declarations and the EXP-036 verifier
  into the manager and queue interfaces prototyped here.
- The single-VM multi-process regtest acceptance run
  and the coordination overhead study at increasing
  worker counts (design section 13). No fleet activation
  decision exists until those measurements do.
