#!/usr/bin/env python3
"""Compare scoped before/desired/readback snapshots. No network or automatic retry."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def timestamp(value):
    require(isinstance(value, str), "observation timestamp required")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(parsed.tzinfo is not None, "timestamp must include timezone")
    return parsed


def rows(snapshot):
    require(isinstance(snapshot, dict) and type(snapshot.get("complete")) is bool,
            "snapshot requires an explicit completeness flag")
    require(isinstance(snapshot.get("binding"), dict) and snapshot["binding"], "scope binding required")
    items = snapshot.get("rows")
    require(isinstance(items, list), "snapshot rows required")
    out = {}
    for row in items:
        require(isinstance(row, dict) and set(row) == {"key", "values"}, "invalid row shape")
        key = row["key"]
        require(isinstance(key, str) and key and key not in out, "missing or duplicate stable row key")
        require(isinstance(row["values"], dict), "row values must be a projected field object")
        out[key] = row["values"]
    return out


def fingerprint(snapshot):
    return digest({"binding": snapshot["binding"], "complete": snapshot["complete"], "rows": rows(snapshot)})


def assess(request):
    require(isinstance(request, dict), "request must be an object")
    require(request.get("schema_version") == 1, "unsupported schema version")
    require(isinstance(request.get("operation_id"), str) and request["operation_id"].strip(),
            "explicit operation ID required")
    require(isinstance(request.get("input_version"), str) and request["input_version"].strip(),
            "explicit input version required")
    before, desired, current = (request[k] for k in ("before", "desired", "current"))
    b, d, c = rows(before), rows(desired), rows(current)
    require(before["binding"] == desired["binding"] == current["binding"], "snapshot scope mismatch")
    require(before["complete"] and desired["complete"], "baseline and desired scope must be complete")
    policy = request.get("policy", {})
    require(set(policy) <= {"subset_retry_verified", "irreversible", "downstream_required"}, "unknown recovery policy")
    require(all(type(v) is bool for v in policy.values()), "policy must use explicit booleans")
    evidence = request.get("evidence", {})
    require(set(evidence) <= {"session_valid", "transport", "contract_current", "downstream_verified", "new_evidence"}, "unknown evidence field")
    require(all(v is None or type(v) is bool for k, v in evidence.items() if k != "transport"), "invalid evidence flag")
    require(evidence.get("transport", "unknown") in {"not_sent", "success", "timeout", "error", "unknown"}, "invalid transport result")
    attempts = request.get("attempts", 0)
    require(type(attempts) is int and attempts >= 0, "invalid attempt count")
    baseline_time, current_time = timestamp(before.get("captured_at")), timestamp(current.get("captured_at"))
    require(current_time >= baseline_time, "readback predates baseline")
    fresh = attempts == 0 or current_time > timestamp(request.get("submitted_at"))
    operation_key = digest({"operation": request["operation_id"], "binding": before["binding"],
                            "before": b, "desired": d, "input_version": request.get("input_version", "")})
    missing = object()
    changed, pending, complete, conflicts = [], [], [], []
    for key in sorted(set(b) | set(d) | set(c)):
        bv, dv, cv = b.get(key, missing), d.get(key, missing), c.get(key, missing)
        if bv != dv:
            changed.append(key)
            if cv == dv:
                complete.append(key)
            elif cv == bv:
                pending.append(key)
            else:
                # A partially updated row is not known to be safe to resend.
                conflicts.append(key)
        elif cv != bv:
            conflicts.append(key)
    result = {
        "operation_key": operation_key, "before_sha256": fingerprint(before),
        "desired_sha256": fingerprint(desired), "current_sha256": fingerprint(current),
        "changed_keys": changed, "completed_keys": complete, "pending_keys": pending,
        "conflicting_keys": conflicts, "retry_keys": [], "execution_authorized": False,
        "online_verified": False,
    }
    if not fresh or not current["complete"] or evidence.get("session_valid") is not True:
        status = "readback_required"
    elif evidence.get("contract_current") is not True:
        status = "contract_recheck_required"
    elif conflicts:
        status = "conflict_review_required"
    elif not pending:
        if policy.get("downstream_required") and evidence.get("downstream_verified") is not True:
            status = "downstream_readback_required"
        else:
            status = "matched_desired"
    elif attempts == 0 and not complete:
        status = "prepared"
    elif policy.get("irreversible"):
        status = "transaction_reconciliation_required"
    elif attempts >= 2 and evidence.get("new_evidence") is not True:
        status = "retry_limit_requires_new_evidence"
    elif policy.get("subset_retry_verified") is not True:
        status = "retry_contract_required"
    else:
        status = "subset_retry_candidate"
        result["retry_keys"] = pending
    result["status"] = status
    # A caller-provided snapshot is comparison evidence, not proof it was read online.
    result["note"] = "Comparison only. Re-read immediately before submitting; use current user authorization and verified endpoint semantics."
    return result


def append_record(path, request, result):
    """Append a hash-linked receipt, with no raw payloads or credentials."""
    previous = None
    if path.exists():
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        for record in records:
            signature = record.pop("record_sha256")
            require(record.get("previous_sha256") == previous and digest(record) == signature,
                    "journal chain changed; inspect before appending")
            previous = signature
    record = {"previous_sha256": previous, "operation_id": request["operation_id"],
              "input_version": request.get("input_version", ""), "attempts": request.get("attempts", 0),
              "result": result}
    record["record_sha256"] = digest(record)
    with path.open("x" if not path.exists() else "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return record["record_sha256"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--journal", type=Path)
    args = parser.parse_args()
    try:
        require(not args.out.exists(), "use a new output path")
        require(not args.journal or args.journal.resolve() not in {args.out.resolve(), args.request.resolve()},
                "journal, request and output paths must be distinct")
        request = json.loads(args.request.read_text(encoding="utf-8"))
        result = assess(request)
        if args.journal:
            result["journal_record_sha256"] = append_record(args.journal, request, result)
        with args.out.open("x", encoding="utf-8") as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2)
    except (ValueError, KeyError, TypeError, OSError):
        parser.exit(2, "Invalid snapshot, journal or path. No platform operation executed.\n")
    print(json.dumps({"status": result["status"], "retry_count": len(result["retry_keys"]),
                      "execution_authorized": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
