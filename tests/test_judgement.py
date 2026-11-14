#!/usr/bin/env python3
"""Block judgement tests.

The miner must know which block to mine and confirm a good
block: templates are validated before work is spent, every
accepted template supersedes work in progress, malformed or
stale templates are rejected, and nbits decodes to the true
network target.
"""

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mining.stratum_client import (DIFF1_TARGET, Evidence,
                                   StratumClient, target_from_nbits,
                                   validate_job)


def good_job(**over):
    job = {
        "job_id": "job-1",
        "prevhash": "ab" * 32,
        "coinb1": "0100000001",
        "coinb2": "ffffffff",
        "merkle_branch": ["cd" * 32, "ef" * 32],
        "version": "20000000",
        "nbits": "170355ff",
        "ntime": "%08x" % int(time.time()),
        "clean_jobs": True,
    }
    job.update(over)
    return job


def main():
    # nbits decoding: the difficulty-1 nbits is DIFF1 itself,
    # and the genesis nbits decodes to the known genesis target.
    assert target_from_nbits("1d00ffff") == DIFF1_TARGET
    g = target_from_nbits("1d00ffff")
    assert DIFF1_TARGET / g == 1.0
    print("ok: nbits decodes to the network target")

    # A well formed, fresh job validates clean.
    assert validate_job(good_job()) == []
    print("ok: well formed fresh template accepted")

    # Broken templates are rejected with named problems.
    bad = validate_job(good_job(prevhash="zz"))
    assert any("prevhash" in p for p in bad), bad
    bad = validate_job(good_job(merkle_branch=["00"]))
    assert any("merkle" in p for p in bad), bad
    bad = validate_job(good_job(coinb1="not-hex"))
    assert any("coinbase" in p for p in bad), bad
    bad = validate_job(good_job(ntime="%08x" % (int(time.time()) - 8000)))
    assert any("stale" in p for p in bad), bad
    bad = validate_job(good_job(ntime="%08x" % (int(time.time()) + 8000)))
    assert any("future" in p for p in bad), bad
    print("ok: malformed and stale templates rejected with reasons")

    # Client behaviour: a valid notify is accepted, logged as
    # validated, and supersedes; an invalid one changes nothing.
    with tempfile.TemporaryDirectory() as td:
        ev = Evidence(os.path.join(td, "ev.jsonl"))
        c = StratumClient("pool.invalid", 1, "addr.worker", "x", ev)

        def notify(job):
            p = [job["job_id"], job["prevhash"], job["coinb1"],
                 job["coinb2"], job["merkle_branch"], job["version"],
                 job["nbits"], job["ntime"], job["clean_jobs"]]
            c._handle({"method": "mining.notify", "params": p})

        notify(good_job())
        assert c.current_job["job_id"] == "job-1"
        gen1 = c.job_generation
        assert gen1 >= 1
        # Non-clean update also supersedes: freshest template wins.
        notify(good_job(job_id="job-2", clean_jobs=False))
        assert c.current_job["job_id"] == "job-2"
        assert c.job_generation > gen1
        # A broken template never displaces the good one.
        notify(good_job(job_id="job-3", prevhash="00"))
        assert c.current_job["job_id"] == "job-2"
        ev.close()
        text = open(os.path.join(td, "ev.jsonl")).read()
        assert "template_validated" in text
        assert "template_rejected" in text
    print("ok: client accepts freshest valid template, rejects "
          "broken ones, and logs both judgements")
    print("ALL JUDGEMENT TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
