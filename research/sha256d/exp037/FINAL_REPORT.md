# EXP-037: Final Report

Date: 2026-11-15. Design and model: STATISTICAL_MODEL.md in
this directory.

Implemented and tested:

1. The evidence census defect is fixed. EvidenceCounter in
   mining/autopilot.py counts share_result events over the
   whole evidence log incrementally, with a persisted byte
   offset, head fingerprint rotation detection, partial-line
   safety and corrupt-state fallback. On the production log
   it returns 247 accepted shares where the old tail-window
   code returned 222; a test asserts equality with an
   independent brute-force count of the same file. The fix
   reaches the live heartbeat at the autopilot's next natural
   restart; nothing was restarted for this phase.
2. mining/mining_statistics.py: the statistics engine.
   Directive section 10 plus EXP-035 section 7 categories as
   separated counters with per-worker and per-backend
   breakdowns, refusal of unknown categories, and a snapshot
   with deliberately no combined total. WindowedRate derives
   windowed rates from cumulative counter samples only
   (counter-first, M11).
3. mining/probability.py: the research probability formulas
   (expected hashes D * 2^32, expected time (D * 2^32) / R,
   P = 1 - exp(-R t / (D * 2^32))) adopted into production
   reach, pinned to known values and cross-checked identical
   to research/probability.py.

Not done, and not claimed: live record() wiring into
mainnet_live, the autopilot heartbeat and the solo server
(they still emit their own counters); windowed rate series
on the live path; the directive's latency series; M10
adaptive solo difficulty (design note in the EXP-038
document). Lease categories await a production producer
(EXP-035 is design and prototype).

Tests: tests/test_exp037_statistics.py, target test-exp037,
in test-all. All pass, including the brute-force check
against the real production evidence log.
