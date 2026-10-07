#!/usr/bin/env python3
"""Prepare a singles/doubles member edit and audit complete roster readback; offline."""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path

PERSON_FIELDS = ('RYID', 'RYXM', 'XB', 'SFZH', 'AGE', 'TEL', 'DWID', 'DWQC', 'DWJC')
FORM_FIELDS = ('DWQC', 'DWJC', 'RYXM', 'XB', 'SFZH', 'AGE', 'TEL')


def suffixes(event_type):
    if event_type in ('MS', 'WS', 'SS'):
        return ('',)
    if event_type in ('MD', 'WD', 'XD', 'SD'):
        return ('1', '2')
    raise ValueError('unsupported roster type; verify its own member contract')


def member_suffix(event_type, member_index):
    slots = suffixes(event_type)
    if type(member_index) is not int or not 1 <= member_index <= len(slots):
        raise ValueError('invalid member_index for roster type')
    return slots[member_index - 1]


def prepare(form, candidate, member_index=1):
    """Clone the live UPT form; candidate ID is for readback, not an invented field."""
    if form.get('TYPE') != 'UPT' or not form.get('XMID') or not form.get('XMNM'):
        raise ValueError('current entry UPT form required')
    member_suffix(form.get('SSLX'), member_index)
    if any(k not in candidate for k in PERSON_FIELDS) or not candidate['RYID']:
        raise ValueError('complete candidate identity required')
    if any(k + str(i) not in form for i in range(1, len(suffixes(form['SSLX'])) + 1)
           for k in FORM_FIELDS):
        raise ValueError('incomplete current form')
    if any(not candidate[k] for k in ('DWQC', 'DWJC', 'RYXM', 'XB')):
        raise ValueError('unit, name and gender required by current form')
    result = deepcopy(form)
    for key in FORM_FIELDS:
        result[key + str(member_index)] = candidate[key]
    return result


def audit(before, after, project_id, entry_id, candidate, member_index=1):
    """Audit ALL project roster rows; target is one member of singles or doubles.

    The caller supplies complete, freshly paginated getRmdData rows. This checks
    identity rebinding and non-target changes, not draw, scores or scheduling.
    """
    def index(rows):
        result = {}
        for row in rows:
            key = (row.get('XMID'), row.get('XMNM'))
            if not all(key) or key in result:
                raise ValueError('missing or duplicate project/entry identity')
            result[key] = row
        return result

    if any(k not in candidate for k in PERSON_FIELDS) or not candidate['RYID']:
        raise ValueError('complete candidate identity required')
    old, new = index(before), index(after)
    target = (project_id, entry_id)
    if target not in old:
        raise ValueError('target must be an existing entry')
    suffix = member_suffix(old[target].get('SSLX'), member_index)
    editable = {k + suffix for k in PERSON_FIELDS}
    if old[target].get('RYID' + suffix) == candidate['RYID']:
        raise ValueError('replacement must be a different person')
    errors = []
    if old.keys() != new.keys():
        errors.append('entry_set_changed')
    if target in new:
        row = new[target]
        if any(row.get(k + suffix) != candidate[k] for k in PERSON_FIELDS):
            errors.append('replacement_identity_mismatch')
        stable = lambda r: {k: v for k, v in r.items() if k not in editable}
        if stable(old[target]) != stable(row):
            errors.append('target_non_person_fields_changed')
        # Count both member slots, including the retained partner of the target.
        if any(r.get('RYID' + s) == candidate['RYID']
               and (k != target or s != suffix)
               for k, r in new.items() if k[0] == project_id
               for s in suffixes(r.get('SSLX'))):
            errors.append('duplicate_person_in_project')
    else:
        errors.append('target_entry_missing')
    protected = old.keys() - {target}
    if any(k not in new or old[k] != new[k] for k in protected):
        errors.append('other_entry_changed')
    return {'valid': not errors, 'errors': errors, 'protected_entries': len(protected),
            'scope': 'complete_roster_only', 'execution_authorized': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('packet', type=Path,
                        help='JSON: before/after rows, project_id, entry_id, candidate; optional member_index (1/2)')
    args = parser.parse_args()
    packet = json.loads(args.packet.read_text(encoding='utf-8'))
    report = audit(**packet)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report['valid'] else 1)


if __name__ == '__main__':
    main()
