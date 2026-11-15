# EXP-038: Final Report

Date: 2026-11-15. Design and as-built operations record:
AUTONOMOUS_OPERATIONS.md in this directory.

Implemented and tested:

1. mining/work_checkpoint.py: a work-state checkpoint for
   the GBT path. It records an exact (extranonce, nonce)
   frontier of completed search per template, keyed by the
   template's EXP-025 layered identity plus the extranonce
   space and the template's curtime basis, written
   atomically. Only completed batches advance the frontier;
   a hit batch never does.
2. MiningEngine integration (opt-in checkpoint_path, default
   off and behaviour-identical when off): a cycle resumes at
   a matching checkpoint's frontier, refuses to rescan a
   space recorded complete, starts fresh with a recorded
   reason on any mismatch, and carries the decision in its
   result dicts so repeated work across restarts is visible
   instead of silent.
3. agent/autonomous.py, the GBT path's production driver,
   enables the checkpoint at .local/work-checkpoint.json.

Proven by tests/test_exp038_checkpoint.py: disjoint and
jointly complete coverage across a restart, mid-round
resume at the exact nonce, no rescan of a completed space,
fresh starts with reasons on identity, space and time-basis
changes and on corrupt files, and unchanged behaviour with
no checkpoint configured.

Not done, and not claimed: candidate recovery across a
crash (the EXP-035 persist-before-acknowledge queue is
designed, not built); checkpointing for the Stratum pool
path (out of scope by design: its separation is the pool's
extranonce1 and its job state is session state; see the
operations document's scope boundary); M18 and M21 are
design notes on unmeasured ground; M15 lives in the EXP-035
design; no end-to-end startup self-test on the live pool
path; no disk or memory watch for the growing evidence log.
Nothing live was restarted for this phase.
