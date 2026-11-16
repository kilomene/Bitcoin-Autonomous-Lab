"""Machine-readable integration registry (Stage 7, wave 1,
item A; closes Stage 0 discrepancy D6).

The narrative experiment registries record integration in
prose addenda, not in the verdict lines the research memory
parser reads, so the memory reported zero INTEGRATED entries
while the Stage 0 reconciliation registry
(research/EXTREME_RESEARCH/EXPERIMENT_REGISTRY.json, the
source of truth built by reading the production tree) records
the integrations verified in source.

This module is the bridge. integration_registry.json, beside
this file, is DERIVED from that Stage 0 registry: every entry
whose status there is INTEGRATED, with the production files
and mechanisms named in its evidence and measured result. The
derived file is the authoritative source the research memory
consults for integration status; the narrative parse remains
authoritative for everything else, and a REJECTED parse is
never overridden (see memory.py).

Regenerate after the Stage 0 registry changes:

    python3 -m agent.intelligence.integrations

The intelligence test suite pins the derived registry against
the Stage 0 source (counts computed live on both sides), so a
stale derivation fails the suite instead of drifting silently.
"""

import json
import os
import re
from dataclasses import dataclass, field

_REPO_ROOT = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", ".."))

DEFAULT_INTEGRATION_REGISTRY = os.path.join(
    os.path.dirname(__file__), "integration_registry.json")

STAGE0_REGISTRY = os.path.join(
    _REPO_ROOT, "research", "EXTREME_RESEARCH",
    "EXPERIMENT_REGISTRY.json")

_CODE_EXT_RE = re.compile(r"\.(py|c|h)\b")
_CODE_PATH_RE = re.compile(
    r"(?:gpu|mining|agent|tests|scripts)/[\w./-]+\.(?:py|c|h)\b")


@dataclass
class IntegrationRecord:
    entry_id: str
    title: str
    integrated_into: list = field(default_factory=list)
    evidence: list = field(default_factory=list)
    measured_result: str = ""


def _production_targets(entry):
    """Production files and mechanisms an entry integrated
    into, as stated by the source: evidence items that name
    code files outside the research tree (kept verbatim, so a
    parenthetical mechanism note survives), plus code paths
    named in the measured result."""
    targets = []
    for item in entry.get("evidence") or []:
        item = str(item)
        if item.startswith("research/"):
            continue
        if _CODE_EXT_RE.search(item) and item not in targets:
            targets.append(item)
    for path in _CODE_PATH_RE.findall(
            str(entry.get("measured_result") or "")):
        if path not in targets:
            targets.append(path)
    return targets


def derive_records(stage0_path=None):
    """IntegrationRecords for every Stage 0 entry whose status
    is INTEGRATED, in Stage 0 order."""
    path = stage0_path or STAGE0_REGISTRY
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    records = []
    for entry in data.get("entries") or []:
        if str(entry.get("status") or "").upper() != "INTEGRATED":
            continue
        records.append(IntegrationRecord(
            entry_id=str(entry.get("id")),
            title=str(entry.get("hypothesis") or ""),
            integrated_into=_production_targets(entry),
            evidence=[str(x) for x in entry.get("evidence") or []],
            measured_result=str(entry.get("measured_result") or "")))
    return records


def write_registry(path=None, stage0_path=None):
    """(Re)write the derived integration registry JSON from
    the Stage 0 source. Returns the record count."""
    path = path or DEFAULT_INTEGRATION_REGISTRY
    records = derive_records(stage0_path)
    payload = {
        "registry": "agent-integration-registry/1",
        "derived_from": os.path.relpath(
            stage0_path or STAGE0_REGISTRY, _REPO_ROOT),
        "rule": "Every Stage 0 entry with status INTEGRATED. "
                "Authoritative for integration status only; "
                "never overrides a REJECTED narrative parse.",
        "entries": [
            {"id": r.entry_id, "title": r.title,
             "status": "INTEGRATED",
             "integrated_into": r.integrated_into,
             "evidence": r.evidence,
             "measured_result": r.measured_result}
            for r in records],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1)
        f.write("\n")
    return len(records)


def load_integration_registry(path=None):
    """Load the derived registry as {entry_id: IntegrationRecord}.
    Raises OSError or ValueError on a missing or malformed file;
    callers that must tolerate absence check first."""
    path = path or DEFAULT_INTEGRATION_REGISTRY
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    records = {}
    for entry in data.get("entries") or []:
        if not isinstance(entry, dict) or not entry.get("id"):
            continue
        records[str(entry["id"])] = IntegrationRecord(
            entry_id=str(entry["id"]),
            title=str(entry.get("title") or ""),
            integrated_into=[str(x) for x in
                             entry.get("integrated_into") or []],
            evidence=[str(x) for x in entry.get("evidence") or []],
            measured_result=str(entry.get("measured_result") or ""))
    return records


if __name__ == "__main__":
    n = write_registry()
    print(f"integration registry written: {n} INTEGRATED entries")
