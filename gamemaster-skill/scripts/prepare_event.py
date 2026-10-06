#!/usr/bin/env python3
"""Connect a reviewed roster to offline draw and bracket engines without guessing identities."""
import argparse
from copy import deepcopy
import json
from pathlib import Path

from participant_roster import validate as validate_roster
from draw_engine import digest, prepare as check_draw_project, validate_project


def require(condition, message):
    if not condition:
        raise ValueError(message)


def prepare(roster, settings):
    active, counts = validate_roster(roster)
    require(settings.get('confirmed') is True, 'Confirm project and draw settings')
    event_id = settings.get('event_id')
    require(isinstance(event_id, str) and event_id, 'Explicit local event_id required')
    require(isinstance(settings.get('event_name'), str) and settings['event_name'], 'Event name required')
    require('random_seed' in settings and str(settings['random_seed']), 'Record random_seed before draw')
    overrides = settings.get('projects', [])
    source_projects = {p['key']: p for p in roster['projects']}
    require(len({p['id'] for p in overrides}) == len(overrides) and {p['id'] for p in overrides} == set(source_projects),
            'Settings must cover each final roster project exactly once')
    athletes = {}
    entries = []
    draw_projects, bracket_projects = [], []
    allowed = {'id', 'sport', 'format', 'entry_size', 'unit_policy', 'club_by_entry', 'fixed_entries',
               'seed_profile', 'seed_positions', 'byes', 'bracket_size', 'balance_levels',
               'group_sizes', 'seed_policy', 'third_place', 'classification_places', 'advance_per_group', 'knockout_slots',
               'legs', 'ranking', 'scoring', 'scoring_by_stage', 'duration_minutes', 'enforce_round_order', 'group_name'}
    for original in overrides:
        p = deepcopy(original)
        require(set(p) <= allowed, 'Unknown project setting: ' + ','.join(sorted(set(p) - allowed)))
        pid = p['id']
        source = source_projects[pid]
        selected = [e for e in active if e['project'] == pid]
        require(counts[pid] >= 2, 'Resolve project cancellation/merger before preparation')
        expected_size = 1 if source['type'].endswith('S') else 2
        require(type(p.get('entry_size')) is int and p['entry_size'] == expected_size, 'entry_size disagrees with reviewed roster type')
        require(p.get('sport') in ('badminton', 'table_tennis', 'tennis', 'pickleball'), 'Explicit supported sport required')
        require(p.get('format') in ('knockout', 'round_robin', 'groups_knockout'), 'Explicit supported format required')
        policy = p.get('unit_policy')
        require(policy in ('full_unit', 'entry_map'), 'Confirm unit_policy: full_unit or entry_map')
        real_ids = {e['id'] for e in selected if e.get('kind') != 'placeholder'}
        mapping = p.get('club_by_entry', {})
        if policy == 'entry_map':
            require(isinstance(mapping, dict) and set(mapping) == real_ids,
                    'Explicit club_by_entry must cover every real entry exactly once')
            require(all(isinstance(v, str) and (v == '' or v.strip()) for v in mapping.values()),
                    'Explicit club labels must be text; empty means confirmed no separation constraint')
        else:
            require(not mapping, 'club_by_entry supplied with full_unit policy')
        fixed = p.get('fixed_entries', {})
        require(isinstance(fixed, dict) and set(fixed) <= {e['id'] for e in selected}, 'Fixed position references unknown entry')
        draw_entries = []
        for e in selected:
            placeholder = e.get('kind') == 'placeholder'
            units = {m['unit'] for m in e['members']}
            if placeholder:
                club, label, seed = '', e['label'], 0
            else:
                if policy == 'full_unit':
                    require(len(units) == 1, 'Cross-unit doubles require an explicit entry_map; do not choose one partner silently')
                    club = next(iter(units))
                else:
                    club = mapping[e['id']]
                label = '／'.join(m['name'] for m in e['members'])
                raw_seed = e.get('seed')
                require(raw_seed in (None, '') or (type(raw_seed) is int and raw_seed >= 0) or
                        (isinstance(raw_seed, str) and raw_seed.isascii() and raw_seed.isdecimal()),
                        'Seed must be a nonnegative integer; do not infer from serial/technical numbers')
                seed = int(raw_seed) if raw_seed not in (None, '') else 0
            members = []
            for person in e['members']:
                mid = person['id']
                require(mid not in athletes or athletes[mid] == person, 'Conflicting athlete identity')
                athletes[mid] = deepcopy(person)
                members.append(mid)
            normalized = {k: deepcopy(v) for k, v in e.items() if k not in ('members', 'project')}
            normalized.update(project_id=pid, member_ids=members, label=label, club=club, seed=seed)
            entries.append(normalized)
            de = {'id': e['id'], 'name': label, 'club': club, 'seed': seed, 'source': e['source']}
            if e['id'] in fixed:
                value = fixed[e['id']]
                require(isinstance(value, dict) and value and set(value) <= {'group', 'position'}, 'Fixed entry uses group/position only')
                require(all(type(v) is int and v > 0 for v in value.values()), 'Fixed group/position must be positive integers')
                require(p['format'] != 'knockout' or value.get('group', 1) == 1,
                        'Knockout fixed entries use group 1')
                de.update(value)
            draw_entries.append(de)
        dp = {'id': pid, 'name': source['name'], 'type': source['type'], 'sport': p['sport'],
              'format': 'knockout' if p['format'] == 'knockout' else 'groups', 'entries': draw_entries}
        if p['format'] == 'knockout':
            require(not set(p) & {'group_sizes', 'seed_policy', 'advance_per_group', 'knockout_slots', 'legs', 'enforce_round_order'},
                    'Round-robin settings supplied for a knockout project')
            require(isinstance(p.get('seed_profile'), str) and p['seed_profile'], 'Explicit seed_profile required for new workflows')
            require(type(p.get('third_place')) is bool, 'Confirm third_place')
            for k in ('seed_profile', 'seed_positions', 'byes', 'bracket_size', 'balance_levels'):
                if k in p:
                    dp[k] = p[k]
        else:
            require(not set(p) & {'seed_profile', 'seed_positions', 'byes', 'bracket_size', 'balance_levels'},
                    'Knockout draw settings supplied for a round-robin first stage')
            require(p.get('seed_policy') == 'snake', 'Confirm supported group seed_policy: snake')
            require(isinstance(p.get('group_sizes'), list) and p['group_sizes'] and
                    all(type(n) is int and n >= 2 for n in p['group_sizes']) and sum(p['group_sizes']) == len(selected),
                    'Group sizes must cover reviewed slots, at least two per group')
            require(p['format'] != 'round_robin' or len(p['group_sizes']) == 1, 'Round robin requires exactly one group')
            require(p['format'] != 'round_robin' or not set(p) & {'third_place', 'classification_places', 'advance_per_group', 'knockout_slots'},
                    'Qualifying knockout settings supplied for a standalone round robin')
            dp.update(group_sizes=p['group_sizes'], seed_policy=p['seed_policy'])
            if p['format'] == 'groups_knockout':
                require(type(p.get('third_place')) is bool and type(p.get('advance_per_group')) is int and p['advance_per_group'] >= 1,
                        'Confirm qualifying count and third_place')
                require(all(p['advance_per_group'] <= size for size in p['group_sizes']), 'Advancing count exceeds a group')
                crossover = p.get('knockout_slots')
                require(isinstance(crossover, list), 'Explicit qualifying crossover required')
                expected = {(g, r) for g in range(1, len(p['group_sizes']) + 1) for r in range(1, p['advance_per_group'] + 1)}
                refs = [(s.get('group'), s.get('rank')) for s in crossover if isinstance(s, dict)]
                require(all(s is None or isinstance(s, dict) for s in crossover) and len(refs) == len(expected) and set(refs) == expected,
                        'Qualifying crossover duplicates or omits a group rank')
        check_draw_project(dp)
        draw_projects.append(dp)
        bp = {k: deepcopy(v) for k, v in p.items() if k not in ('unit_policy', 'club_by_entry', 'fixed_entries',
              'seed_profile', 'seed_positions', 'byes', 'bracket_size', 'balance_levels', 'group_sizes', 'seed_policy')}
        bp.update(name=source['name'], type=source['type'])
        bracket_projects.append(bp)
    draw_config = {'event_id': event_id, 'random_seed': settings['random_seed'],
                   'test_seeds': settings.get('test_seeds', False), 'projects': draw_projects}
    bracket_base = {'event_id': event_id, 'event_name': settings['event_name'], 'reviewed': True,
                    'athletes': list(athletes.values()), 'entries': entries, 'projects': bracket_projects,
                    'draw_config_sha256': digest(draw_config)}
    provenance = {'schema': 'gamemaster.prepared.v1', 'roster_sha256': digest(roster),
                  'settings_sha256': digest(settings), 'draw_config_sha256': digest(draw_config),
                  'roster_version': roster.get('version'), 'event_id': event_id,
                  'excluded_withdrawn_entries': [{'id': e['id'], 'project': e['project'], 'source': e['source']}
                                                 for e in roster['entries'] if e['status'] == 'withdrawn'],
                  'unknown_identity_entries': [e['id'] for e in entries if e.get('kind') == 'placeholder'],
                  'unit_policies': {p['id']: {'policy': p['unit_policy'], 'club_by_entry': p.get('club_by_entry', {})}
                                    for p in overrides}}
    bracket_base['provenance'] = provenance
    return {'draw_config': draw_config, 'bracket_base': bracket_base, 'provenance': provenance}


def attach_draw(draw_config, bracket_base, draw_result):
    fingerprint = digest(draw_config)
    require(bracket_base.get('draw_config_sha256') == fingerprint and draw_result.get('input_sha256') == fingerprint,
            'Draw input version mismatch')
    require(bracket_base['event_id'] == draw_config['event_id'] == draw_result.get('event_id'), 'Draw event mismatch')
    require(draw_result.get('random_seed') == draw_config['random_seed'], 'Recorded random seed mismatch')
    by_project = {p['id']: p for p in draw_config['projects']}
    results = draw_result.get('projects', [])
    require(len(results) == len(by_project) and {r['project_id'] for r in results} == set(by_project), 'Draw project coverage mismatch')
    for result in results:
        validate_project(by_project[result['project_id']], result)
    result = deepcopy(bracket_base)
    result['draw'] = deepcopy(draw_result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('prepare')
    p.add_argument('roster'); p.add_argument('settings'); p.add_argument('directory')
    p = sub.add_parser('attach')
    p.add_argument('draw_config'); p.add_argument('bracket_base'); p.add_argument('draw_result'); p.add_argument('output')
    a = parser.parse_args()
    read = lambda p: json.loads(Path(p).read_text(encoding='utf-8'))
    write = lambda p, d: p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    try:
        if a.command == 'prepare':
            out = Path(a.directory)
            require(not out.exists(), 'Choose a new output directory')
            data = prepare(read(a.roster), read(a.settings))
            out.mkdir(parents=True)
            for key, name in [('draw_config', 'draw-input.json'), ('bracket_base', 'bracket-base.json'), ('provenance', 'provenance.json')]:
                write(out / name, data[key])
            print(out)
        else:
            out = Path(a.output)
            require(not out.exists(), 'Choose a new output filename')
            data = attach_draw(read(a.draw_config), read(a.bracket_base), read(a.draw_result))
            out.parent.mkdir(parents=True, exist_ok=True)
            write(out, data)
            print(out)
    except (ValueError, KeyError, OSError, TypeError) as exc:
        parser.exit(2, str(exc) + '\n')


if __name__ == '__main__':
    main()
