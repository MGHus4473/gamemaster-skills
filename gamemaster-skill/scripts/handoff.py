#!/usr/bin/env python3
"""Build a hashed portable file manifest; no platform connection or ID allocation."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath


def build(spec, directory):
    directory = Path(directory).resolve()
    out = deepcopy(spec)
    out['schema_version'] = 1
    for field in ('local_id', 'name', 'sport'):
        if not isinstance(out.get('event', {}).get(field), str) or not out['event'][field].strip():
            raise ValueError('Missing event.' + field)
    for field in ('input_version', 'rules_version'):
        if not isinstance(out.get(field), str) or not out[field].strip():
            raise ValueError('Missing ' + field)
    mapping = out.setdefault('mapping', {'event_id': '', 'project_ids': {}, 'entry_ids': {}, 'match_ids': {}})
    if not isinstance(mapping.get('event_id'), str):
        raise ValueError('mapping.event_id must be a string; empty means unbound')
    for kind in ('project_ids', 'entry_ids', 'match_ids'):
        values = mapping.get(kind)
        if not isinstance(values, dict) or any(not isinstance(k, str) or not k or not isinstance(v, str) or not v for k, v in values.items()):
            raise ValueError('Invalid mapping.' + kind)
        if len(values) != len(set(values.values())):
            raise ValueError('Duplicate platform IDs in ' + kind)
    artifacts = out.get('artifacts')
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError('artifacts required')
    seen = set()
    for item in artifacts:
        name = item.get('path')
        if not isinstance(name, str) or not name or '\\' in name:
            raise ValueError('Use relative POSIX artifact paths')
        path, win = PurePosixPath(name), PureWindowsPath(name)
        if path.is_absolute() or win.drive or '..' in path.parts:
            raise ValueError('Artifact path escapes directory')
        resolved = (directory / name).resolve()
        if not resolved.is_relative_to(directory) or not resolved.is_file() or resolved in seen:
            raise ValueError('Missing, duplicate or out-of-directory artifact')
        if not isinstance(item.get('kind'), str) or not item['kind'].strip():
            raise ValueError('Artifact kind required')
        seen.add(resolved)
        item['sha256'] = hashlib.sha256(resolved.read_bytes()).hexdigest()
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('spec'); parser.add_argument('output')
    a = parser.parse_args()
    try:
        output = Path(a.output).resolve()
        if output.exists():
            raise ValueError('Choose a new output path')
        data = build(json.loads(Path(a.spec).read_text(encoding='utf-8')), output.parent)
        output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        print(output)
    except (ValueError, OSError, TypeError, KeyError) as exc:
        parser.exit(2, str(exc) + '\n')


if __name__ == '__main__':
    main()
