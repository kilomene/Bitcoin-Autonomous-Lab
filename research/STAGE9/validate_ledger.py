#!/usr/bin/env python3
"""Validate EXPERIMENT_CLOSURE_LEDGER.json against its schema.
Uses the jsonschema package when available; otherwise falls back
to a structural check of the same constraints (required fields,
enums, 109 unique ids). Prints VALID or the first errors."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
led = json.load(open(os.path.join(HERE,
                     "EXPERIMENT_CLOSURE_LEDGER.json")))
sch = json.load(open(os.path.join(HERE,
                     "EXPERIMENT_CLOSURE_LEDGER.schema.json")))
try:
    import jsonschema
    jsonschema.validate(led, sch)
    print("VALID (jsonschema, draft 2020-12):",
          len(led["entries"]), "entries")
except ImportError:
    disps = set(sch["properties"]["entries"]["items"]
                ["properties"]["disposition"]["enum"])
    req = sch["properties"]["entries"]["items"]["required"]
    ids = [e["id"] for e in led["entries"]]
    assert len(ids) == 109 and len(set(ids)) == 109, "id count"
    for e in led["entries"]:
        for k in req:
            assert k in e, (e["id"], k)
        assert e["disposition"] in disps, e["id"]
    print("VALID (structural fallback; jsonschema not "
          "installed):", len(ids), "entries")
except Exception as exc:
    print("INVALID:", exc)
    sys.exit(1)
