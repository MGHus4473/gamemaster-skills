#!/usr/bin/env python3
"""Validate the portable gamemaster/ptty handoff without changing it."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath


def validate(path):
    path = Path(path).resolve()
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("unsupported schema_version")
    event = data.get("event", {})
    for field in ("local_id", "name", "sport"):
        if not isinstance(event.get(field), str) or not event[field].strip():
            raise ValueError(f"event.{field} is required")
    for field in ("input_version", "rules_version"):
        if not isinstance(data.get(field), str) or not data[field].strip():
            raise ValueError(f"{field} is required")
    mapping = data.get("mapping")
    if not isinstance(mapping, dict) or not isinstance(mapping.get("event_id"), str):
        raise ValueError("mapping.event_id must be a string")
    for field in ("project_ids", "entry_ids", "match_ids"):
        values = mapping.get(field)
        if not isinstance(values, dict) or any(not isinstance(k, str) or not isinstance(v, str) or not k or not v for k, v in values.items()):
            raise ValueError(f"mapping.{field} must map nonempty strings")
        if len(set(values.values())) != len(values):
            raise ValueError(f"mapping.{field} has duplicate platform IDs")
    artifacts = data.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("artifacts must be nonempty")
    seen, verified = set(), []
    for item in artifacts:
        name = item.get("path", "")
        if not isinstance(name, str) or not name or "\\" in name:
            raise ValueError("artifact path must use relative POSIX syntax")
        posix, windows = PurePosixPath(name), PureWindowsPath(name)
        if posix.is_absolute() or windows.is_absolute() or windows.drive or ".." in posix.parts:
            raise ValueError("artifact path escapes package")
        target = (path.parent / name).resolve()
        if not target.is_relative_to(path.parent) or not target.is_file():
            raise ValueError("missing or out-of-package artifact")
        if target in seen:
            raise ValueError("duplicate artifact path")
        seen.add(target)
        if not isinstance(item.get("kind"), str) or not item["kind"].strip():
            raise ValueError("artifact.kind is required")
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        if item.get("sha256") != digest:
            raise ValueError(f"artifact hash mismatch: {name}")
        verified.append({"kind": item["kind"], "path": name, "sha256": digest})
    return {"valid": True, "event": event, "artifacts": verified, "platform_event_id": mapping["event_id"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("handoff")
    args = parser.parse_args()
    try:
        print(json.dumps(validate(args.handoff), ensure_ascii=False, indent=2))
    except (ValueError, OSError, TypeError, KeyError) as exc:
        parser.exit(2, f"Invalid handoff: {exc}\n")
