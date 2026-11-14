#!/usr/bin/env python3
"""EXP-021 (Y-097) correctness gates: the mixed worker
pool (phase6/benchmarks/exp021_pool.py) over the SHA-NI
streams kernel (libbal_geo.so, streams=4 strided) and
the AVX-512 multi-buffer kernel (libbal_v512.so).

Gates, all before any benchmark:
  * mixed-pool candidate sets at the regtest-easy
    target equal the independent Python recount, and
    are identical across at least three different
    splits of the same range;
  * every digest a pool worker emits equals the
    hashlib reference at its nonce (full check on
    the gate ranges);
  * the genesis nonce is found by whichever family
    owns its partition (MB owner and SHA-NI owner,
    first and second partition positions);
  * boundary partitions: a range ending exactly at
    2^32, a start that is not a wave multiple;
  * empty partitions (more workers than waves) and
    single-worker pools keep exact union accounting;
  * per-worker attempted equals its partition size
    and the union sums exactly to the range size,
    for every split tested.
"""
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gates import FAILS, check, ref  # noqa: E402

ROOT = "/home/hatch/workspace/bitcoin-autonomous-lab"
sys.path.insert(0, os.path.join(
    ROOT, "research/sha256d/phase6/benchmarks"))
sys.path.insert(0, os.path.join(ROOT, "research/sha256d/experiments"))
from bench_harness import GENESIS, DIFF1_LE  # noqa: E402
from exp021_pool import MB, SHANI, partition, run_pool  # noqa: E402

GN = 2083236893
EASY = (1 << 248).to_bytes(32, "little")
EASY_INT = 1 << 248


def recount_flags(header, start, count, target_int):
    return bytes(
        1 if int.from_bytes(ref(header, start + i), "little")
        <= target_int else 0 for i in range(count))


def union_flags(pool):
    out = bytearray()
    for w in pool["workers"]:
        out += w["flags"]
    return bytes(out)


def check_pool(specs, header, start, total, target,
               target_int, label, full_digests=True):
    pool = run_pool(specs, header, start, total, target,
                    materialize=True)
    ok_rc = all(w["rc"] == 0 for w in pool["workers"])
    ok_att = all(w["attempted"] == w["part_count"]
                 for w in pool["workers"])
    ok_sum = pool["attempted_total"] == total
    check(f"{label}: rc and exact union accounting",
          ok_rc and ok_att and ok_sum,
          f"att_total={pool['attempted_total']} total={total}")
    if full_digests:
        ok_dig = True
        for w in pool["workers"]:
            for i in range(w["part_count"]):
                got = w["hashes"][32 * i:32 * i + 32]
                if got != ref(header, w["part_start"] + i):
                    ok_dig = False
                    break
            if not ok_dig:
                break
        check(f"{label}: all digests match hashlib", ok_dig)
    want = recount_flags(header, start, total, target_int)
    check(f"{label}: candidate set equals recount",
          union_flags(pool) == want,
          f"candidates={sum(want)}")
    return pool


def main():
    rng = random.Random(21021)

    # Main splits over one regtest-easy range: candidate
    # sets must be identical across splits and equal to
    # the recount; every digest verified.
    splits = [
        [MB, MB], [SHANI, SHANI], [MB, SHANI], [SHANI, MB],
        [MB, SHANI, MB], [SHANI, MB, SHANI, SHANI],
    ]
    seen = []
    for specs in splits:
        label = "split " + "+".join(s[0] for s in specs)
        pool = check_pool(specs, GENESIS, 0, 20000, EASY,
                          EASY_INT, label)
        seen.append(union_flags(pool))
    check("candidate sets identical across six splits",
          all(s == seen[0] for s in seen))

    # Genesis ownership: the winner must be flagged by
    # the family owning its partition, in either slot.
    cases = [
        ([MB, SHANI], GN - 9000, 10000, 1, "shani, slot 2"),
        ([SHANI, MB], GN - 9000, 10000, 1, "mb, slot 2"),
        ([MB, SHANI], GN - 5000, 10000, 0, "mb, slot 1"),
        ([SHANI, MB], GN - 5000, 10000, 0, "shani, slot 1"),
    ]
    for specs, start, total, owner, label in cases:
        pool = run_pool(specs, GENESIS, start, total,
                        DIFF1_LE, materialize=True)
        parts = partition(start, total, len(specs))
        ok_att = pool["attempted_total"] == total and all(
            w["attempted"] == w["part_count"]
            for w in pool["workers"])
        w = pool["workers"][owner]
        off = GN - w["part_start"]
        ok_flag = 0 <= off < w["part_count"] \
            and w["flags"][off] == 1 \
            and w["hashes"][32 * off:32 * off + 32] \
            == ref(GENESIS, GN)
        others = sum(sum(x["flags"]) for j, x in
                     enumerate(pool["workers"]) if j != owner)
        check(f"genesis owned by {label}",
              ok_att and ok_flag and others == 0
              and parts[owner][0] <= GN
              < parts[owner][0] + parts[owner][1],
              f"owner_att={w['attempted']} others={others}")

    # Boundary partitions: range ending exactly at 2^32;
    # start not a wave multiple.
    check_pool([MB, SHANI], GENESIS, 0xFFFFF000, 0x1000,
               EASY, EASY_INT, "range ending at 2^32")
    check_pool([SHANI, MB, MB], GENESIS, 12345, 20000,
               EASY, EASY_INT, "unaligned start 12345")

    # Empty partition: three workers, two waves.
    pool = run_pool([MB, SHANI, MB], GENESIS, 0, 32, EASY,
                    materialize=True)
    check("empty partition accounting",
          pool["attempted_total"] == 32
          and pool["workers"][2]["attempted"] == 0
          and pool["workers"][2]["part_count"] == 0
          and union_flags(pool)
          == recount_flags(GENESIS, 0, 32, EASY_INT),
          f"parts={[w['part_count'] for w in pool['workers']]}")

    # Single-worker pools, both families, full digests.
    check_pool([MB], GENESIS, 777, 4096, EASY, EASY_INT,
               "single mb worker")
    check_pool([SHANI], GENESIS, 777, 4096, EASY, EASY_INT,
               "single shani worker")

    # Randomised pool differentials on a random template:
    # three random splits of one range, full digest check.
    hdr = bytes(rng.randbytes(80))
    start = rng.randrange(0, 2**31)
    for specs in ([MB, SHANI], [SHANI, SHANI, MB],
                  [MB, MB, SHANI, MB]):
        label = "random " + "+".join(s[0] for s in specs)
        check_pool(specs, hdr, start, 12000, EASY, EASY_INT,
                   label)

    # Four-worker deployment shapes at easy target.
    check_pool([MB, MB, SHANI, SHANI], GENESIS, 0, 20000,
               EASY, EASY_INT, "2 mb + 2 shani")
    check_pool([MB, MB, MB, MB], GENESIS, 0, 20000,
               EASY, EASY_INT, "4 mb")
    check_pool([SHANI, SHANI, SHANI, SHANI], GENESIS, 0,
               20000, EASY, EASY_INT, "4 shani")

    print()
    if FAILS:
        print(f"EXP-021 gates: {len(FAILS)} FAILURES")
        return 1
    print("EXP-021 gates: ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
