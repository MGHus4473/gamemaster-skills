#!/usr/bin/env python3
"""Validate a model's explicit action plan against a scoped user task; offline."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from operation_catalog import load_catalog, resolve


def strings(value, label):
    if not isinstance(value, list) or any(not isinstance(x, str) or not x or x == "*" for x in value) or len(value) != len(set(value)):
        raise ValueError("invalid explicit scope: " + label)
    return set(value)


def validate(contract, actions, catalog=None):
    catalog = catalog or load_catalog()
    if not isinstance(contract, dict) or not isinstance(actions, list):
        raise ValueError("contract and action list required")
    if not isinstance(contract.get("event_id"), str) or not contract["event_id"]:
        raise ValueError("target event required")
    allowed = strings(contract.get("allowed_operations"), "operations")
    required = strings(contract.get("required_operations", []), "required operations")
    if not required <= allowed:
        raise ValueError("required operations must be allowed")
    for op in allowed:
        if resolve(catalog, op)["kind"] == "demo":
            raise ValueError("demonstrations cannot be task operations")
    scopes = {k: strings(contract.get(k, []), k) for k in ("project_ids", "match_ids", "protected_match_ids", "audiences")}
    fields = contract.get("allowed_fields", {})
    if not isinstance(fields, dict) or not set(fields) <= allowed:
        raise ValueError("field scope must refer to allowed operations")
    fields = {k: strings(v, "field paths") for k, v in fields.items()}
    for flag in ("readonly", "protect_existing_results"):
        if flag in contract and type(contract[flag]) is not bool:
            raise ValueError("task flags must be booleans")
    errors, seen = [], set()
    for index, action in enumerate(actions):
        reasons = []
        if not isinstance(action, dict):
            raise ValueError("invalid action")
        op = action.get("operation_id")
        try:
            item = resolve(catalog, op)
        except ValueError:
            errors.append({"action": index, "reasons": ["unknown_operation"]})
            continue
        seen.add(op)
        if op not in allowed:
            reasons.append("operation_outside_task")
        if action.get("event_id") != contract["event_id"]:
            reasons.append("wrong_event")
        if contract.get("readonly") and item["kind"] not in {"read", "local"}:
            reasons.append("outside_readonly_scope")
        if item["kind"] == "demo":
            reasons.append("demonstration_not_executable")
        for key in ("project_ids", "match_ids", "audiences"):
            values = strings(action.get(key, []), key)
            if not values <= scopes[key]:
                reasons.append(key + "_outside_scope")
            if key == "match_ids" and values & scopes["protected_match_ids"] and item["kind"] not in {"read", "local"}:
                reasons.append("protected_match")
        # Scope-bound writes must actually enumerate targets; omission is not all.
        if item["kind"] not in {"read", "local"}:
            for key in ("project_ids", "match_ids", "audiences"):
                if scopes[key] and not action.get(key):
                    reasons.append("missing_" + key)
            if contract.get("protect_existing_results") and "results" in item["impacts"]:
                reasons.append("existing_results_may_change")
        changed = strings(action.get("changed_fields", []), "changed fields")
        if not changed <= fields.get(op, set()):
            reasons.append("fields_outside_task")
        if op in fields and item["kind"] not in {"read", "local"} and not changed:
            reasons.append("changed_fields_missing")
        if reasons:
            errors.append({"action": index, "reasons": reasons})
    missing = sorted(required - seen)
    return {"valid": not errors and not missing, "errors": errors, "missing_operations": missing,
            "execution_authorized": False,
            "note": "Checks the structured interpretation only; compare it with the user's actual words and live state before execution."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path)
    args = parser.parse_args()
    try:
        data = json.loads(args.request.read_text(encoding="utf-8"))
        result = validate(data["contract"], data["actions"])
    except (ValueError, KeyError, TypeError, OSError):
        parser.exit(2, "Invalid task contract or action schema. No operations executed.\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
