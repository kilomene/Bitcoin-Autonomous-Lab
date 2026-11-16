"""Persistent research memory (Master Build Mandate sections
4.1F and 17).

The lab's research record already exists and is authoritative:
the two experiment registries and the EXP-033 hypothesis
registry. This module does not copy or replace that record. It
builds a searchable in-memory index by parsing it, mapping each
entry's verdict onto the mandate's research decision statuses:

    NEW, UNDER_INVESTIGATION, EXPERIMENTAL, PROVEN,
    INTEGRATED, REJECTED, DEFERRED

Parsing is tolerant by design. A section that cannot be parsed
into an entry is counted in unparsed_count, never silently
dropped, and a registry file that is missing is reported in
missing_sources instead of raising.

The optimisation loop uses was_rejected() to refuse re-proposing
an idea the record has already rejected: a hypothesis whose
keywords all appear in a REJECTED entry's text is treated as
already decided.
"""

import json
import os
import re
from dataclasses import dataclass, field

STATUSES = ("NEW", "UNDER_INVESTIGATION", "EXPERIMENTAL",
            "PROVEN", "INTEGRATED", "REJECTED", "DEFERRED")

_REPO_ROOT = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", ".."))

DEFAULT_SOURCES = (
    os.path.join(_REPO_ROOT, "research", "sha256d",
                 "experiment_registry.md"),
    os.path.join(_REPO_ROOT, "research", "sha256d",
                 "extreme_optimization", "EXPERIMENT_REGISTRY.md"),
)
DEFAULT_JSON_SOURCE = os.path.join(
    _REPO_ROOT, "research", "sha256d", "exp033",
    "HYPOTHESIS_REGISTRY.json")

_HEADER_RE = re.compile(r"^(#{2,3})\s+(EXP-\d+[a-z]?(?:\b[^:\n]*)?)[:\s].*$|"
                        r"^(#{2,3})\s+(EXP-\d+[a-z]?)\b.*$", re.M)
_EXP_ID_RE = re.compile(r"EXP-(\d+)([a-z]?)\b")
_RANGE_RE = re.compile(r"EXP-(\d+)\s+to\s+EXP-(\d+)")
_BENEFIT_RE = re.compile(r"(\d+\.\d+)x\b")
_VERDICT_LINE_RE = re.compile(
    r"(decision|verdict|result|status)\b[^.\n]*", re.I)


@dataclass
class MemoryEntry:
    entry_id: str
    title: str
    status: str
    source: str
    text: str
    expected_benefit: float = None
    kind: str = "experiment"

    def matches_all(self, keywords):
        hay = (self.entry_id + " " + self.title + " " +
               self.text).lower()
        return all(str(k).lower() in hay for k in keywords)

    def match_count(self, keywords):
        hay = (self.entry_id + " " + self.title + " " +
               self.text).lower()
        return sum(1 for k in keywords if str(k).lower() in hay)


def _map_status(verdict_text, full_text):
    """Map registry wording onto a mandate status. Verdict
    lines (Decision / Verdict / Result) are weighed first; the
    full text is only a fallback, so a passing mention of a
    rejected sub-idea cannot relabel an accepted entry."""
    v = verdict_text.lower()
    if "reject" in v or "established negative" in v:
        return "REJECTED"
    if "integrated" in v and "not integrated" not in v:
        return "INTEGRATED"
    if "deferred" in v or "reserved" in v:
        return "DEFERRED"
    if "verified improvement" in v or "accepted" in v \
            or "verified" in v:
        return "PROVEN"
    if "not significant" in v or "inconclusive" in v \
            or "established null" in v:
        return "EXPERIMENTAL"
    f = full_text.lower()
    if "decision: reject" in f or "result: reject" in f \
            or "result: rejected" in f:
        return "REJECTED"
    if "integrated into production" in f:
        return "INTEGRATED"
    if "verified improvement" in f:
        return "PROVEN"
    return "EXPERIMENTAL"


def _ids_for_header(header_text):
    """All experiment ids a section header covers. A range
    header (EXP-004 to EXP-009) expands to every id in the
    range; a joint header (EXP-028 and EXP-029) yields both."""
    m = _RANGE_RE.search(header_text)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        if 0 <= hi - lo <= 64:
            return [f"EXP-{n:03d}" for n in range(lo, hi + 1)]
    ids = []
    for num, suffix in _EXP_ID_RE.findall(header_text):
        eid = f"EXP-{int(num):03d}{suffix}"
        if eid not in ids:
            ids.append(eid)
    return ids


def _parse_markdown(path):
    """Parse one registry markdown file into entries plus a
    count of sections that looked like experiment sections but
    produced no entry."""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    lines = content.splitlines()
    sections = []  # (header_line, [body lines])
    current = None
    header_re = re.compile(r"^#{2,3}\s+")
    for line in lines:
        if header_re.match(line):
            if current is not None:
                sections.append(current)
            current = (line, [])
        elif current is not None:
            current[1].append(line)
    if current is not None:
        sections.append(current)
    entries = []
    unparsed = 0
    for header, body_lines in sections:
        if "EXP-" not in header:
            continue
        ids = _ids_for_header(header)
        if not ids:
            unparsed += 1
            continue
        title = header.lstrip("# ").strip()
        body = "\n".join(body_lines).strip()
        verdict = "\n".join(
            ln for ln in body_lines
            if _VERDICT_LINE_RE.search(ln))
        status = _map_status(verdict, body)
        benefit = None
        bm = _BENEFIT_RE.search(body)
        if bm:
            try:
                benefit = float(bm.group(1))
            except ValueError:
                benefit = None
        for eid in ids:
            entries.append(MemoryEntry(
                entry_id=eid, title=title, status=status,
                source=path, text=(title + "\n" + body),
                expected_benefit=benefit, kind="experiment"))
    return entries, unparsed


def _map_json_status(raw):
    s = str(raw or "").upper()
    if "NEGATIVE" in s or "REJECT" in s or "REFUTED" in s:
        return "REJECTED"
    if "INTEGRATED" in s:
        return "INTEGRATED"
    if "UNPROVEN" in s or "OPEN" in s or "INCONCLUSIVE" in s:
        return "UNDER_INVESTIGATION"
    if "VERIFIED" in s or "PROVEN" in s:
        return "PROVEN"
    if "DEFER" in s:
        return "DEFERRED"
    return "EXPERIMENTAL"


def _parse_json_registry(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    entries = []
    unparsed = 0
    hyps = data.get("hypotheses") if isinstance(data, dict) else None
    if not isinstance(hyps, list):
        return [], 1
    for h in hyps:
        if not isinstance(h, dict) or not h.get("id"):
            unparsed += 1
            continue
        statement = str(h.get("statement", ""))
        evidence = str(h.get("evidence", ""))
        status_raw = str(h.get("status", ""))
        # EXP-042 later refuted H-033-05; the registry carries
        # the update as an appended note field on some records.
        note = str(h.get("exp042_note", "") or
                   h.get("update", "") or "")
        status = _map_json_status(status_raw)
        if status != "REJECTED" and "ESTABLISHED NEGATIVE" in \
                (note.upper()):
            status = "REJECTED"
        entries.append(MemoryEntry(
            entry_id=str(h["id"]), title=statement[:160],
            status=status, source=path,
            text=(statement + "\n" + evidence + "\n" + note),
            expected_benefit=None, kind="hypothesis"))
    return entries, unparsed


class ResearchMemory:
    """Searchable index over the lab's research record."""

    def __init__(self, md_sources=None, json_source=None):
        self.md_sources = list(md_sources) if md_sources is not None \
            else list(DEFAULT_SOURCES)
        self.json_source = json_source if json_source is not None \
            else DEFAULT_JSON_SOURCE
        self.entries = []
        self.unparsed_count = 0
        self.missing_sources = []
        self._by_id = {}
        self._load()

    def _load(self):
        for path in self.md_sources:
            if not os.path.isfile(path):
                self.missing_sources.append(path)
                continue
            try:
                entries, unparsed = _parse_markdown(path)
            except OSError:
                self.missing_sources.append(path)
                continue
            self.unparsed_count += unparsed
            self._add(entries)
        if self.json_source:
            if not os.path.isfile(self.json_source):
                self.missing_sources.append(self.json_source)
            else:
                try:
                    entries, unparsed = _parse_json_registry(
                        self.json_source)
                    self.unparsed_count += unparsed
                    self._add(entries)
                except (OSError, ValueError):
                    self.unparsed_count += 1

    def _add(self, entries):
        for e in entries:
            self.entries.append(e)
            # First record wins for an id: the primary registry
            # precedes the extreme registry in DEFAULT_SOURCES,
            # and duplicates across registries stay searchable
            # as separate entries.
            self._by_id.setdefault(e.entry_id, e)

    @property
    def indexed_count(self):
        return len(self.entries)

    def stats(self):
        by_status = {}
        for e in self.entries:
            by_status[e.status] = by_status.get(e.status, 0) + 1
        return {"indexed": len(self.entries),
                "unparsed": self.unparsed_count,
                "missing_sources": list(self.missing_sources),
                "by_status": by_status}

    def lookup(self, entry_id):
        """One entry by id (EXP-014, H-033-05), or None."""
        if entry_id is None:
            return None
        return self._by_id.get(str(entry_id).upper())

    def search(self, keywords, limit=20):
        """Entries matching the keywords, best first. A single
        string is treated as one keyword. Ranking: number of
        keywords matched, then id, for determinism."""
        if isinstance(keywords, str):
            keywords = [keywords]
        keywords = [str(k) for k in keywords if str(k).strip()]
        if not keywords:
            return []
        scored = []
        for e in self.entries:
            n = e.match_count(keywords)
            if n:
                scored.append((n, e))
        scored.sort(key=lambda t: (-t[0], t[1].entry_id,
                                   t[1].source))
        return [e for _n, e in scored[:limit]]

    def was_rejected(self, keywords):
        """The REJECTED entry whose text contains every keyword,
        or None. This is the guard the optimisation loop uses:
        a match means the idea is already decided and must not
        be re-proposed."""
        if isinstance(keywords, str):
            keywords = [keywords]
        keywords = [str(k) for k in keywords if str(k).strip()]
        if not keywords:
            return None
        for e in self.entries:
            if e.status == "REJECTED" and e.matches_all(keywords):
                return e
        return None

    def by_status(self, status):
        return [e for e in self.entries if e.status == status]
