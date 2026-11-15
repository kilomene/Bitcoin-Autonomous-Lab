# EXP-035: Proof Obligations and Their Discharge

The disjointness and honesty obligations of the design
(WORK_DISTRIBUTION_DESIGN.md section 10), and how the
controlled tests discharge each one. All evidence is
from the research prototype on this VM; the raw record
is RAW_RESULTS/campaign_20261115T101733Z.json, produced
by TESTS/test_exp035_campaign.py.

| Obligation | Statement | Discharged by |
|---|---|---|
| P1 exact union | Union of completed intervals equals the declared space exactly, per slice and in total | check_completed() in every campaign trial (60/60) and in the coordinator-restart targeted test |
| P2 pairwise disjoint | Completed intervals pairwise disjoint; per-slice chunks tile [0, nonce_count) at every assertion instant | assert_partition_invariant() at trial ends, every 500 campaign steps, and after every steal in the steal targeted test |
| P3 duplicates never credited | Duplicate, stale and not-holder reports counted separately, contributing zero unique coverage | Campaign: 2,088 duplicate deliveries, 3,190 stale reports, 739 not-holder attempts injected and counted, while unique coverage still equals the declared total exactly in all 60 trials |
| P4 accounting identity | unique + pending + leased == declared; actual >= unique; repeated visible separately | accounting() assertions in check_completed(); campaign aggregate repeated = 257,020 against unique = 609,280 |
| P5 restart honesty | No pre-restart, pre-death or pre-expiry completion claim is ever credited | Targeted tests restart_replay_never_credited, lease_expiry_reclaim, coordinator_restart_tokens_die; campaign zombie replays (3,190, all STALE) after 1,564 worker restarts and 801 coordinator restarts |
| P6 candidate integrity | Verifier invoked exactly once per unique candidate identity; duplicates and stale generations never reach it; journal recovery preserves this | Targeted tests candidate_queue and candidate_queue_journal_recovery; campaign queue assertions per trial (892 duplicate candidate submissions, all detected) |

Scope limit, stated once and binding: these are proofs
by exhaustive assertion over the simulated campaigns
above, in the EXP-029 style. They cover the prototype's
semantics on one VM. They say nothing about networked
behaviour, real clocks, or real fleet hosts; see the
UNVERIFIED register in WORK_DISTRIBUTION_DESIGN.md
section 12.
