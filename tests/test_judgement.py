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

        base = int(time.time())
        job1 = good_job(ntime="%08x" % base)
        job2 = good_job(job_id="job-2", clean_jobs=False,
                        ntime="%08x" % (base + 10))
        notify(job1)
        assert c.current_job["job_id"] == "job-1"
        gen1 = c.job_generation
        assert gen1 >= 1
        # Non-clean update also supersedes: freshest template wins.
        notify(job2)
        assert c.current_job["job_id"] == "job-2"
        assert c.job_generation > gen1
        gen2 = c.job_generation
        # A broken template never displaces the good one.
        notify(good_job(job_id="job-3", prevhash="00"))
        assert c.current_job["job_id"] == "job-2"
        # A stale echo for the same tip (older ntime) is rejected.
        notify(good_job(job_id="job-4", ntime="%08x" % (base + 5)))
        assert c.current_job["job_id"] == "job-2"
        assert c.job_generation == gen2
        # An exact duplicate changes nothing and restarts no work.
        notify(dict(job2))
        assert c.job_generation == gen2
        ev.close()
        text = open(os.path.join(td, "ev.jsonl")).read()
        assert "template_validated" in text
        assert "template_rejected" in text
        assert "template_duplicate" in text
        assert "stale template echo" in text
    print("ok: client accepts freshest valid template, rejects "
          "broken and stale ones, ignores duplicates, logs all")

    # Exact difficulty: a digest equal to the difficulty-1
    # target scores exactly 1.0; half the target scores 2.0.
    from mining.mainnet_live import difficulty_of
    d1 = DIFF1_TARGET.to_bytes(32, "little")
    assert difficulty_of(d1) == 1.0
    half = (DIFF1_TARGET // 2).to_bytes(32, "little")
    assert difficulty_of(half) == 2.0
    print("ok: difficulty is the exact DIFF1 / value ratio")

    # Reconnect: a dropped pool connection is re-established by
    # the reader loop and work resumes on the new session's job.
    import json as _json
    import socket as _socket
    import threading as _threading

    def stub_pool(jobs):
        srv = _socket.socket()
        srv.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", 0))
        srv.listen(2)
        srv.settimeout(30)
        port = srv.getsockname()[1]
        state = {"conns": 0}

        def send(f, obj):
            f.write((_json.dumps(obj) + "\n").encode())

        def serve():
            try:
                while state["conns"] < len(jobs):
                    conn, _ = srv.accept()
                    conn.settimeout(15)
                    state["conns"] += 1
                    job = jobs[state["conns"] - 1]
                    f = conn.makefile("rwb", buffering=0)
                    ids = {}
                    while len(ids) < 2:
                        line = f.readline()
                        if not line:
                            break
                        m = _json.loads(line)
                        if m.get("method") in (
                                "mining.subscribe",
                                "mining.authorize"):
                            ids[m["method"]] = m["id"]
                    send(f, {"id": ids["mining.subscribe"],
                             "result": [[["mining.notify", "n1"]],
                                        "aabbccdd", 4],
                             "error": None})
                    send(f, {"id": ids["mining.authorize"],
                             "result": True, "error": None})
                    send(f, {"id": None,
                             "method": "mining.set_difficulty",
                             "params": [1]})
                    send(f, {"id": None, "method": "mining.notify",
                             "params": [
                                 job["job_id"], job["prevhash"],
                                 job["coinb1"], job["coinb2"],
                                 job["merkle_branch"], job["version"],
                                 job["nbits"], job["ntime"], True]})
                    if state["conns"] == 1:
                        # Hard drop of session one: shutdown sends
                        # FIN even while the file wrapper is open.
                        try:
                            conn.shutdown(_socket.SHUT_RDWR)
                        except OSError:
                            pass
                        f.close()
                        conn.close()
                    else:
                        try:
                            while f.readline():
                                pass
                        except OSError:
                            pass
                        conn.close()
            except OSError:
                pass
            finally:
                srv.close()

        _threading.Thread(target=serve, daemon=True).start()
        return port

    with tempfile.TemporaryDirectory() as td:
        ev = Evidence(os.path.join(td, "ev2.jsonl"))
        base = int(time.time())
        j1 = good_job(job_id="job-a", ntime="%08x" % base)
        j2 = good_job(job_id="job-b", ntime="%08x" % (base + 20))
        port = stub_pool([j1, j2])
        c = StratumClient("127.0.0.1", port, "addr.worker", "x", ev)
        c.connect()
        t = _threading.Thread(target=c.reader_loop, daemon=True)
        t.start()
        deadline = time.time() + 20
        while time.time() < deadline:
            with c.lock:
                cur = c.current_job
            if cur and cur["job_id"] == "job-b":
                break
            time.sleep(0.1)
        with c.lock:
            cur = c.current_job
        assert cur and cur["job_id"] == "job-b", cur
        assert c.authorized.is_set()
        c.stop_flag = True
        try:
            c.sock.close()
        except OSError:
            pass
        ev.close()
        text = open(os.path.join(td, "ev2.jsonl")).read()
        assert "reconnected" in text
    print("ok: dropped pool connection reconnects and work "
          "resumes on the new session's template")
    print("ALL JUDGEMENT TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
