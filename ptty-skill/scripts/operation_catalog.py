#!/usr/bin/env python3
"""Offline operation lookup and preflight. Never connects to or changes PTTY."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

CATALOG = Path(__file__).resolve().parents[1] / "references" / "operations.json"
KINDS = {"read", "write", "financial", "account", "notify", "compute", "local", "demo"}


def load_catalog(path=CATALOG):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("unsupported catalog version")
    groups = {g["id"]: g for g in data["groups"]}
    if len(groups) != len(data["groups"]):
        raise ValueError("duplicate group")
    seen = set()
    for item in data["operations"]:
        if item["id"] in seen or item["id"].split(".")[0] not in groups:
            raise ValueError("duplicate operation or missing group")
        seen.add(item["id"])
        if item["kind"] not in KINDS or not item.get("acceptance"):
            raise ValueError("missing kind or acceptance")
        for field in ("requires", "impacts", "methods"):
            if not isinstance(item[field], list) or any(not isinstance(x, str) for x in item[field]):
                raise ValueError("invalid operation field")
        if item["evidence"] not in {"static", "readonly", "write_readback"}:
            raise ValueError("unknown evidence class")
        route = item.get("route", groups[item["id"].split(".")[0]]["route"])
        if not route.startswith("/") or "?" in route:
            raise ValueError("route must omit event and session parameters")
    return data


def resolve(data, operation_id):
    operation = next((x for x in data["operations"] if x["id"] == operation_id), None)
    if operation is None:
        raise ValueError("unknown operation; use search first")
    group = next(g for g in data["groups"] if g["id"] == operation_id.split(".")[0])
    return {**group, **operation, "group_title": group["title"]}


def search(data, query):
    tokens = query.casefold().split()
    found = []
    for raw in data["operations"]:
        item = resolve(data, raw["id"])
        text = " ".join([item["id"], item["title"], item["group_title"], *item["methods"]]).casefold()
        score = sum(token in text for token in tokens)
        if not tokens or score:
            found.append((score, item))
    return [item for _, item in sorted(found, key=lambda x: (-x[0], x[1]["id"]))]


def preflight(data, request):
    """Facts come from current evidence; booleans are not authorization tokens."""
    if set(request) - {"operations", "mode", "facts"}:
        raise ValueError("unknown request fields; keep identities and credentials outside this file")
    mode = request.get("mode", "readonly")
    if mode not in {"readonly", "requested_changes"}:
        raise ValueError("invalid mode")
    ids, facts = request.get("operations"), request.get("facts", {})
    if not isinstance(ids, list) or not ids or any(not isinstance(i, str) for i in ids) or len(set(ids)) != len(ids):
        raise ValueError("provide distinct explicit operation IDs")
    known_facts = {x for op in data["operations"] for x in op["requires"]}
    if not isinstance(facts, dict) or any(k not in known_facts or (v is not None and type(v) is not bool) for k, v in facts.items()):
        raise ValueError("facts must be known names with true, false or null")
    steps = []
    for operation_id in ids:
        item = resolve(data, operation_id)
        missing = [name for name in item["requires"] if facts.get(name) is None]
        failed = [name for name in item["requires"] if facts.get(name) is False]
        blocked = []
        if item["kind"] == "demo":
            blocked.append("demonstration_or_unimplemented")
        if mode == "readonly" and item["kind"] not in {"read", "local", "demo"}:
            blocked.append("outside_readonly_scope")
        if failed:
            blocked.append("precondition_unsatisfied")
        # Never infer missing steps or mark execution authorized. In particular,
        # a generation request must not silently add lock/pay/delete operations.
        steps.append({
            "operation": item["id"], "route": item["route"], "component": item["component"],
            "kind": item["kind"], "evidence": item["evidence"],
            "blocked_by": blocked, "facts_to_read": missing, "failed_facts": failed,
            "recheck_after_change": item["impacts"], "acceptance": item["acceptance"],
            "next_step": "resolve_block" if blocked else "read_missing_facts" if missing else "verify_current_form_and_task_scope",
        })
    return {"offline_only": True, "execution_authorized": False,
            "note": "No operations executed. Existing user instructions determine authorization; verify current page contracts before submission.",
            "steps": steps}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate")
    s = sub.add_parser("search")
    s.add_argument("query", nargs="?", default="")
    s = sub.add_parser("show")
    s.add_argument("operation")
    s = sub.add_parser("preflight")
    s.add_argument("request", type=Path)
    args = parser.parse_args()
    try:
        data = load_catalog()
        if args.command == "validate":
            result = {"valid": True, "groups": len(data["groups"]), "operations": len(data["operations"])}
        elif args.command == "search":
            result = search(data, args.query)
        elif args.command == "show":
            result = resolve(data, args.operation)
        else:
            result = preflight(data, json.loads(args.request.read_text(encoding="utf-8")))
    except (ValueError, KeyError, TypeError, OSError):
        parser.exit(2, "Invalid catalog or request; inspect schema and operation IDs. No operations executed.\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
