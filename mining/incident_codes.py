"""Incident code registry access (NOVA-ER-0006, register R-30).

Every detected fault, recovery action and backend
refusal in the mining stack carries a stable numeric
code from the append-only registry in
mining/incident_registry.json, so agent reasoning and
post-incident audit key on codes instead of free text.
The taxonomy is coarse by design (20 codes at first
ship, grouped 1xxx miner lifecycle, 2xxx supervisor
lifecycle, 3xxx self-update, 4xxx work and report
integrity, 5xxx upstream and verification) and is
modelled on the MicroBT Whatsminer public error-code
documentation, the studied precedent in register R-30.

Discipline, enforced here and pinned by
tests/test_incident_codes.py:

- Codes are integers, unique, and strictly increasing
  in registry file order (file order is assignment
  order).
- An entry's code, name and meaning are immutable once
  shipped; codes are never reused. New fault classes
  are only ever appended. check_append_only(old, new)
  returns the list of violations of that rule between
  two entry lists, so an audit can prove a registry
  edit was a pure append.
- Unknown codes are refused at validation time:
  resolve(), annotate() and prefix() raise
  UnknownIncidentCode (a ValueError). There is no
  silent fallback and no default code.

This module is deliberately dependency-free (json and
os only) and is loaded by hot paths defensively: the
autopilot degrades to uncoded log lines if the
registry cannot be read, and the statistics keying
path uses constants pinned to this registry by the
test suite, so a registry problem can never stop
mining or supervision. Refusal is a validation-layer
contract; availability of the supervisor is the
hot-path contract. Both are stated in the design note,
research/EXTREME_RESEARCH/NOVA_ER_0006_DESIGN.md.
"""

import json
import os

REGISTRY_PATH = os.path.join(os.path.dirname(
    os.path.abspath(__file__)), "incident_registry.json")

_ENTRY_FIELDS = ("code", "name", "class", "description",
                 "emission")


class UnknownIncidentCode(ValueError):
    """Raised when a code is not in the registry."""


def validate_entries(entries):
    """Validate a registry entry list against the
    discipline: a list of complete entries whose codes
    are unique integers in strictly increasing order.
    Returns the entries unchanged; raises ValueError
    describing the first violation."""
    if not isinstance(entries, list) or not entries:
        raise ValueError("incident registry entries must "
                         "be a non-empty list")
    seen = set()
    prev = None
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"incident entry {i} is not "
                             f"an object")
        for field in _ENTRY_FIELDS:
            if field not in entry:
                raise ValueError(f"incident entry {i} is "
                                 f"missing field {field!r}")
        code = entry["code"]
        if not isinstance(code, int) or isinstance(
                code, bool):
            raise ValueError(f"incident entry {i} code "
                             f"{code!r} is not an integer")
        if code in seen:
            raise ValueError(f"incident code {code} is "
                             f"assigned twice")
        if prev is not None and code <= prev:
            raise ValueError(f"incident code {code} is "
                             f"out of order after {prev}; "
                             f"file order is assignment "
                             f"order")
        if not isinstance(entry["name"], str) or \
                not entry["name"]:
            raise ValueError(f"incident entry {i} has no "
                             f"name")
        seen.add(code)
        prev = code
    return entries


def load_registry(path=None):
    """Load and validate the registry file. Returns the
    entry list. Raises OSError for an unreadable file
    and ValueError for a discipline violation."""
    with open(path or REGISTRY_PATH) as f:
        doc = json.load(f)
    if not isinstance(doc, dict) or \
            doc.get("registry") != "bal-incident-codes/1":
        raise ValueError("not a bal-incident-codes/1 "
                         "registry document")
    return validate_entries(doc.get("entries"))


_cache = {}


def entries(path=None):
    """The validated entry list, cached per path."""
    key = path or REGISTRY_PATH
    if key not in _cache:
        _cache[key] = load_registry(key)
    return _cache[key]


def registry_map(path=None):
    """{code: entry} for the registry."""
    return {e["code"]: e for e in entries(path)}


def is_known(code, path=None):
    """True iff code is an integer assigned in the
    registry. Never raises for a malformed code."""
    if not isinstance(code, int) or isinstance(code,
                                                bool):
        return False
    return code in registry_map(path)


def resolve(code, path=None):
    """The registry entry for code. Raises
    UnknownIncidentCode for any code not assigned in
    the registry, including non-integer codes."""
    if isinstance(code, int) and not isinstance(code,
                                                bool):
        entry = registry_map(path).get(code)
        if entry is not None:
            return entry
    raise UnknownIncidentCode(
        f"incident code {code!r} is not in the "
        f"registry; codes are append-only and unknown "
        f"codes are refused, never defaulted")


def annotate(record, code, path=None):
    """Return the dict record with its "incident_code"
    field set to code, after resolving the code against
    the registry. Raises UnknownIncidentCode for an
    unassigned code and TypeError for a non-dict record.
    The record is mutated in place and also returned,
    for call-site convenience."""
    if not isinstance(record, dict):
        raise TypeError("incident annotation applies to "
                        "dict records")
    resolve(code, path)
    record["incident_code"] = code
    return record


def prefix(code, path=None):
    """The "[code] " log-line prefix token for code,
    after resolving it against the registry. Raises
    UnknownIncidentCode for an unassigned code."""
    resolve(code, path)
    return f"[{code}] "


def check_append_only(old_entries, new_entries):
    """Append-only discipline check between two entry
    lists (as returned by load_registry or parsed from
    a registry document). Returns a list of violation
    strings; an empty list means new_entries is
    old_entries with zero or more entries appended and
    every old entry identical in code, name, class,
    description and emission. Both lists are validated
    first, so a malformed list is itself a violation."""
    violations = []
    try:
        validate_entries(old_entries)
    except ValueError as exc:
        violations.append(f"old entries invalid: {exc}")
    try:
        validate_entries(new_entries)
    except ValueError as exc:
        violations.append(f"new entries invalid: {exc}")
    if violations:
        return violations
    if len(new_entries) < len(old_entries):
        violations.append(
            f"registry shrank from {len(old_entries)} to "
            f"{len(new_entries)} entries; entries are "
            f"never removed")
        return violations
    for i, old in enumerate(old_entries):
        new = new_entries[i]
        if new != old:
            if new.get("code") != old.get("code"):
                violations.append(
                    f"entry {i} changed code "
                    f"{old.get('code')} -> "
                    f"{new.get('code')}; codes are never "
                    f"reused or renumbered")
            else:
                changed = [f for f in _ENTRY_FIELDS
                           if new.get(f) != old.get(f)]
                violations.append(
                    f"entry {i} (code {old.get('code')}) "
                    f"was edited in place, fields "
                    f"{changed}; shipped entries are "
                    f"immutable")
    return violations
