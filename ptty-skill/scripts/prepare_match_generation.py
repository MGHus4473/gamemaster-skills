#!/usr/bin/env python3
"""Prepare an observed first-generation request offline; never submits or redraws."""
import argparse
from copy import deepcopy
import json
from pathlib import Path

from workflow_state import fingerprint, rows, timestamp


OPTIONS = {
    "ZHSHOWMS": {"SZ", "ZM"},
    "CCHGZ": {"0", "1", "2", "3", "5", "6"},
    "ISLKZZH": {"0", "1"},
    "FZFS": {"ZZZPT", "RSPT"},
}


def identifiers(value):
    if (not isinstance(value, list) or not value or
            any(not isinstance(x, str) or not x.strip() for x in value) or
            len(set(value)) != len(value)):
        raise ValueError("explicit distinct IDs required")
    return value


def prepare(request):
    """Input evidence is caller supplied, not proof of live state or permission."""
    if request.get("mode") != "platform":
        raise ValueError("platform generation requires the platform workflow, not independent generation")
    event = request["event_id"]
    route_id = request["route_ssid"]
    if not all(isinstance(x, str) and x.strip() for x in (event, route_id)):
        raise ValueError("plain event ID and current route ssid required")
    projects = identifiers(request["project_ids"])
    plan = request["plan"]
    if plan.get("event_id") != event or plan.get("complete") is not True:
        raise ValueError("complete plan for target event required")
    if not set(projects) <= set(identifiers(plan["project_ids"])):
        raise ValueError("selected project stages not in current plan")
    inventory = request["inventory"]
    if inventory.get("event_id") != event or inventory.get("complete") is not True:
        raise ValueError("complete event-wide inventory required; filtered empty is not zero")
    timestamp(inventory.get("captured_at"))
    for field in ("matches", "scheduled", "started", "results"):
        if type(inventory.get(field)) is not int or inventory[field] != 0:
            raise ValueError("first generation requires verified zero event-wide " + field)
    draw = request["draw_snapshot"]
    if draw.get("binding") != {"event_id": event} or draw.get("complete") is not True:
        raise ValueError("complete event draw snapshot required, including confirmed positions")
    if rows(draw):
        raise ValueError("draw positions with zero matches are contradictory; re-read complete match inventory before generation")
    timestamp(draw.get("captured_at"))
    model = request["sc_model_data"]
    if (not isinstance(model, dict) or set(model) != set(OPTIONS) or
            any(not isinstance(v, str) or v not in OPTIONS[k] for k, v in model.items())):
        raise ValueError("use explicit observed generation options from current form")
    return {
        "offline_only": True, "execution_authorized": False, "online_verified": False,
        "operation_id": "matches.generate", "event_id": event,
        "route": "/trialGhIndex", "component": "TrialGhIndex",
        "request": {"headerData": {"ssid": route_id, "op": "scGl", "methodName": "czSc"},
                    "busData": {"xmids": list(projects), "type": "create", "scModelData": deepcopy(model)}},
        "draw_before_sha256": fingerprint(draw),
        "note": "Recheck current page, event, options, zero inventory and task scope immediately before one submission. Compare all draw positions and match dependencies after it; never blindly retry.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = prepare(json.loads(args.input.read_text(encoding="utf-8")))
        # Exclusive creation protects a previous prepared request/receipt.
        with args.out.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    except (ValueError, KeyError, TypeError, AttributeError, OSError):
        parser.exit(2, "Invalid evidence/options or output already exists. No operations executed.\n")
    print("Prepared locally. No platform request sent.")


if __name__ == "__main__":
    main()
