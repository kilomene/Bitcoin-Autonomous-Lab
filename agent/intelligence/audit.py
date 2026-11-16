"""Append-only audit log for the agent intelligence package
(Master Build Mandate sections 11 and 13).

Every consequential action the package takes records one JSON
line: timestamp, operation, authority level, a summary of the
inputs, and the outcome. The log is append-only: records are
never edited or removed by this module.

Writes follow the SafeRecorder precedent of
mining/mining_statistics.py: a write failure must never break
the operation being audited. Each record is emitted with a
single os.write call on an O_APPEND descriptor, so concurrent
writers cannot interleave a record, and any OSError is counted
in self.failures instead of raised.
"""

import json
import os
import time

SCHEMA_VERSION = 1


def _default_path():
    root = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", ".."))
    return os.path.join(root, ".local", "agent-audit.jsonl")


class AuditLog:
    """Append-only JSONL audit log with failure tolerance."""

    def __init__(self, path=None):
        self.path = path or _default_path()
        self.failures = 0
        self.written = 0

    def record(self, operation, level, inputs_summary, outcome,
               detail=None):
        """Append one record. Returns True when the record was
        written, False when the write failed (counted, never
        raised). inputs_summary must be JSON serializable; it is
        stringified defensively if it is not."""
        entry = {
            "version": SCHEMA_VERSION,
            "ts": time.time(),
            "ts_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                    time.gmtime()),
            "operation": str(operation),
            "level": int(level) if level is not None else None,
            "inputs": inputs_summary,
            "outcome": str(outcome),
        }
        if detail is not None:
            entry["detail"] = detail
        try:
            line = json.dumps(entry, default=str,
                              sort_keys=True) + "\n"
        except (TypeError, ValueError):
            self.failures += 1
            return False
        try:
            parent = os.path.dirname(os.path.abspath(self.path))
            if parent:
                os.makedirs(parent, exist_ok=True)
            fd = os.open(self.path,
                         os.O_WRONLY | os.O_CREAT | os.O_APPEND,
                         0o600)
            try:
                os.write(fd, line.encode("utf-8"))
            finally:
                os.close(fd)
        except OSError:
            self.failures += 1
            return False
        self.written += 1
        return True

    def read(self, limit=None):
        """Parse the log back into a list of dicts. A missing
        log reads as empty; unparseable lines are skipped and
        counted in the returned list's companion attribute via
        read_with_stats."""
        records, _skipped = self.read_with_stats(limit=limit)
        return records

    def read_with_stats(self, limit=None):
        records = []
        skipped = 0
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except OSError:
            return [], 0
        if limit is not None:
            lines = lines[-limit:] if limit > 0 else []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except ValueError:
                skipped += 1
        return records, skipped
