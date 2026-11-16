"""EXP-051: prepared-work prefetch queue (register R-33).

A bounded queue between the template engine and the search,
plus the background longpoll feed that fills it. While the
search runs on the current template, the feed waits on the
node's GBT longpoll and prepares the next template ahead of
need (the full EXP-025 layered-identity construction, paid
off the critical path). At a template transition the engine
asks the queue for work; the queue serves its newest entry
only after two re-verifications, mirroring the EXP-025
serving rule (a serve recomputes the identity from scratch
and never silently serves):

  1. the entry's previousblockhash is still the node's best
     block hash (the entry is not built on a stale tip), and
  2. the entry template's layered identity, recomputed from
     scratch at serve time, equals the identity the entry
     was prepared under.

Any failure drops the entry (counted, by reason) and the
transition falls back to the synchronous fetch and prepare:
the queue can only ever remove work from the critical path,
never change what work is done. A candidate prepared under
identity A is therefore never searched under identity B.

Accounting is EXP-037 separated counters, recorded through
an injected recorder callable (category name only; the
engine passes its SafeRecorder): prefetch_enqueued,
prefetch_served, prefetch_starved (transitions where no
valid prepared work was ready, including a cold engine's
first cycle), prefetch_dropped_identity,
prefetch_dropped_stale, prefetch_dropped_superseded,
prefetch_dropped_overflow. No counter here is ever summed
with another.

The deliberate EXP-025 boundary applies unchanged: mintime
and curtime are not in the identity. A queued template's
curtime ages while it waits, so at serve time the entry's
curtime is refreshed to the current time, exactly the value
a fresh GBT response would carry; PreparedTemplate.build
then clamps it against mintime per build exactly as the
uncached path does.
"""

import threading
import time
from collections import deque

# mining.engine.template_identity is imported inside serve()
# (this module is imported by mining.engine, so a module-level
# import would be circular).


class PrefetchQueue:
    """Bounded identity-keyed queue of (template,
    PreparedTemplate) entries, newest at the right end.

    Thread-safe: the feed thread enqueues while the mining
    thread serves. max_entries bounds memory; overflow
    evicts the OLDEST entry (the one most likely superseded)
    and counts the eviction.
    """

    def __init__(self, max_entries=2, recorder=None):
        if max_entries < 1:
            raise ValueError("prefetch queue must hold at "
                             "least one entry")
        self.max_entries = max_entries
        self._recorder = recorder
        self._entries = deque()
        self._lock = threading.Lock()

    def _record(self, category):
        if self._recorder is not None:
            self._recorder(category)

    def __len__(self):
        with self._lock:
            return len(self._entries)

    def identities(self):
        """Identities of the queued entries, oldest first."""
        with self._lock:
            return [prep.identity for _tpl, prep
                    in self._entries]

    def enqueue(self, template, prepared):
        """Place a prepared template in the queue. Returns
        False (and queues nothing) when an entry with the
        same identity is already queued: a duplicate delivery
        of the same work is not a second entry. Evicts the
        oldest entry on overflow, counted."""
        with self._lock:
            for _tpl, prep in self._entries:
                if prep.identity == prepared.identity:
                    return False
            self._entries.append((template, prepared))
            while len(self._entries) > self.max_entries:
                self._entries.popleft()
                self._record("prefetch_dropped_overflow")
            self._record("prefetch_enqueued")
            return True

    def serve(self, family, best_hash):
        """Attempt to serve the next template at a
        transition. family is the engine's TemplateFamily;
        best_hash is a zero-argument callable returning the
        node's current best block hash (display-order hex).

        Returns (template, prepared) for the newest entry
        after both re-verifications pass, else None. Every
        queued entry that is not served is dropped and
        counted by reason: entries older than the newest are
        superseded by it; the newest is dropped as stale if
        its previousblockhash is not the node's best block
        (or the tip cannot be verified at all) and as an
        identity drop if its recomputed identity disagrees
        with the identity it was prepared under. Exactly one
        of prefetch_served / prefetch_starved is recorded per
        call.
        """
        with self._lock:
            entries = list(self._entries)
            self._entries.clear()
        if not entries:
            self._record("prefetch_starved")
            return None
        for _tpl, _prep in entries[:-1]:
            self._record("prefetch_dropped_superseded")
        template, prepared = entries[-1]
        try:
            tip = best_hash()
        except Exception:
            tip = None
        if tip is None or template["previousblockhash"] != tip:
            self._record("prefetch_dropped_stale")
            self._record("prefetch_starved")
            return None
        from mining.engine import template_identity
        try:
            identity_now = template_identity(family, template)[0]
        except Exception:
            identity_now = None
        if identity_now != prepared.identity:
            self._record("prefetch_dropped_identity")
            self._record("prefetch_starved")
            return None
        # Time is not in the identity (EXP-025 boundary); a
        # fresh GBT response would carry the current time, so
        # the served template carries it too. build() clamps
        # against mintime per build as the uncached path does.
        template["curtime"] = int(time.time())
        self._record("prefetch_served")
        return template, prepared


class PrefetchFeed(threading.Thread):
    """Background longpoll feed for one PrefetchQueue.

    The engine notes the template it is currently mining
    (note_current); the feed longpolls from that template's
    longpollid, prepares whatever the node serves next
    through the engine's own prepare path (the EXP-025
    cache, so a returning identity is a cache hit), and
    enqueues it unless it is the work already being mined
    or already queued. Errors never kill the feed: a failed
    longpoll or prepare backs off briefly and retries from
    the last noted longpollid, which Core answers with the
    current template if it has gone stale.

    fetch_template(longpollid) -> template dict and
    prepare_template(template) -> (PreparedTemplate, was_hit)
    are injected, so the feed is testable without a node and
    the category F harness can give the feed its own RPC
    connection (in production both are the engine's own
    wait_template and prepare_template).
    """

    def __init__(self, queue, fetch_template, prepare_template,
                 error_sleep=1.0, idle_sleep=0.05):
        super().__init__(daemon=True, name="bal-prefetch-feed")
        self.queue = queue
        self._fetch = fetch_template
        self._prepare = prepare_template
        self.error_sleep = error_sleep
        self.idle_sleep = idle_sleep
        self._stop_evt = threading.Event()
        self._cond = threading.Condition()
        self._longpollid = None
        self._current_identity = None
        # Observability for tests and reports: the feed's own
        # counters are plain attributes, deliberately NOT
        # mining statistics (the queue's EXP-037 counters are
        # the accounting of record).
        self.fetches = 0
        self.prepares = 0
        self.errors = 0
        self.last_error = None

    def note_current(self, template, identity):
        """Tell the feed which template the engine is mining
        now. Called at every mine_cycle template resolution,
        served or synchronous."""
        with self._cond:
            self._longpollid = template.get("longpollid")
            self._current_identity = identity
            self._cond.notify_all()

    def stop(self):
        self._stop_evt.set()
        with self._cond:
            self._cond.notify_all()

    def run(self):
        while not self._stop_evt.is_set():
            with self._cond:
                longpollid = self._longpollid
                current_identity = self._current_identity
                if longpollid is None:
                    self._cond.wait(timeout=1.0)
                    continue
            try:
                template = self._fetch(longpollid)
                self.fetches += 1
            except Exception as exc:  # node busy, timeout, ...
                self.errors += 1
                self.last_error = repr(exc)
                self._stop_evt.wait(self.error_sleep)
                continue
            # The longpoll answered. If the engine has since
            # moved to a different current template, this
            # answer belongs to an old longpoll chain; still
            # process it only if its chain is the live one.
            with self._cond:
                live = (longpollid == self._longpollid)
                if live:
                    self._longpollid = template.get("longpollid")
            if not live or self._stop_evt.is_set():
                continue
            try:
                prepared, _hit = self._prepare(template)
                self.prepares += 1
            except Exception as exc:  # invalid template, ...
                self.errors += 1
                self.last_error = repr(exc)
                self._stop_evt.wait(self.error_sleep)
                continue
            if prepared.identity == current_identity:
                continue
            if prepared.identity in self.queue.identities():
                continue
            self.queue.enqueue(template, prepared)
