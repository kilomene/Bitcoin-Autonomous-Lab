"""Work-state checkpoint for the GBT mining path (EXP-038).

Before this module the lab had no work-state checkpoints
anywhere (gap analysis components 19 and 20): a restarted
miner rescanned from nonce 0 and extranonce 0 for the current
template, repeated work across restarts was neither prevented
nor accounted, and nothing recorded where a dead process had
actually got to.

The checkpoint records a FRONTIER over the search positions
of one template: positions are (extranonce, nonce) pairs in
the lexicographic order MiningEngine.mine_cycle walks them
(extranonce rounds ascending, nonces ascending inside each
round). The frontier (fe, fn) means: every position with
extranonce < fe was examined to its full nonce range, and in
round fe every nonce < fn was examined. mine_cycle advances
in exactly this order, so one frontier describes completed
coverage exactly, not approximately.

Honesty rules, which are the point of the design:

- Only completed work is ever recorded. The frontier advances
  after a batch's search has returned, never before, and
  never across a batch that produced a hit (that batch was
  only partly examined; the cycle ends there anyway, and a
  later cycle on the same template rescans that one batch,
  which is repeated work and is visible as such).
- A checkpoint is valid only for the exact work it describes.
  Resume requires ALL of: the template's EXP-025 layered
  identity, the engine's extranonce space, and the template's
  curtime basis to match the record. (The layered identity
  deliberately excludes time fields, EXP-025's rule, while a
  header's time is a per-build input; the curtime basis is
  therefore matched separately so a resumed scan never claims
  coverage of positions under a different time basis than the
  one it recorded.) Any mismatch, a corrupt file, or a
  frontier outside the space: start fresh, and the returned
  note says why. Starting fresh is always safe; resuming
  wrongly is the failure this module exists to prevent.
- Writes are atomic (write to a sibling temp file, fsync,
  os.replace, best-effort directory fsync), so a crash
  mid-write leaves either the old checkpoint or the new one,
  never a torn file. A file that still fails to parse is
  treated as no checkpoint, with the reason kept in the note.

Scope boundary: this serves the GBT path, MiningEngine
(direct getblocktemplate solo mining, driven in production by
agent/autonomous.py). The Stratum pool path
(mining/mainnet_live.py) does not use MiningEngine and is
untouched: its work separation is the pool-assigned
extranonce1 per connection and its job state belongs to the
pool session, so there is no local position to checkpoint.
The lab's Stratum solo server holds no search position either
(its workers do); coordinator-level progress records are the
EXP-035 lease manager's progress positions, designed there
and not duplicated here.
"""

import json
import os
import time

SCHEMA_VERSION = 1


class WorkCheckpoint:
    """Frontier checkpoint bound to one checkpoint file."""

    def __init__(self, path):
        self.path = path
        self.last_note = "no checkpoint read yet"

    def _load(self):
        try:
            with open(self.path) as f:
                data = json.load(f)
        except OSError:
            self.last_note = "no checkpoint file; starting fresh"
            return None
        except ValueError:
            self.last_note = "checkpoint file corrupt; starting fresh"
            return None
        if not isinstance(data, dict) \
                or data.get("version") != SCHEMA_VERSION:
            self.last_note = "checkpoint schema not recognised; " \
                             "starting fresh"
            return None
        return data

    def resume(self, identity, extranonce_space, curtime_basis):
        """Decide where a cycle on this template may start.

        Returns (status, extranonce, nonce, note): status is
        "fresh" (start at the space's first position),
        "resume" (start at the returned frontier), or
        "exhausted" (a previous process completed this exact
        space under this exact identity and time basis; there
        is nothing left to scan). extranonce and nonce are
        None unless status is "resume".
        """
        data = self._load()
        if data is None:
            return "fresh", None, None, self.last_note
        if data.get("identity") != identity.hex():
            return "fresh", None, None, \
                "checkpoint is for a different template " \
                "identity; starting fresh"
        if list(extranonce_space) != data.get("extranonce_space"):
            return "fresh", None, None, \
                "checkpoint is for a different extranonce " \
                "space; starting fresh"
        if data.get("curtime_basis") != curtime_basis:
            return "fresh", None, None, \
                "checkpoint is for a different template time " \
                "basis; starting fresh"
        if data.get("complete"):
            return "exhausted", None, None, \
                "checkpoint records this template's space as " \
                "fully examined; not rescanning"
        fe = data.get("frontier_extranonce")
        fn = data.get("frontier_nonce")
        first, count = extranonce_space
        if not isinstance(fe, int) or not isinstance(fn, int) \
                or not (first <= fe <= first + count) \
                or not (0 <= fn < (1 << 32)):
            return "fresh", None, None, \
                "checkpoint frontier outside the search " \
                "space; starting fresh"
        return "resume", fe, fn, \
            f"resumed at extranonce {fe}, nonce {fn} from " \
            f"checkpoint written {data.get('updated_at', '?')}"

    def record(self, identity, height, previousblockhash,
               curtime_basis, extranonce_space,
               frontier_extranonce, frontier_nonce, complete=False):
        """Persist the frontier of work actually completed.
        Called only after the batches it covers have returned;
        see the module docstring's honesty rules."""
        data = {
            "version": SCHEMA_VERSION,
            "identity": identity.hex(),
            "height": height,
            "previousblockhash": previousblockhash,
            "curtime_basis": curtime_basis,
            "extranonce_space": list(extranonce_space),
            "frontier_extranonce": frontier_extranonce,
            "frontier_nonce": frontier_nonce,
            "complete": bool(complete),
            "updated_at": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        parent = os.path.dirname(self.path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)
        try:
            dfd = os.open(parent or ".", os.O_RDONLY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        except OSError:
            pass
        self.last_note = "checkpoint saved"
        return data
