#!/usr/bin/env python3
"""Offline, deterministic court/time scheduling. No platform or network calls.

Input: sessions, courts, matches with confirmed athlete IDs and predecessor IDs.
All matches occupy one slot (duration + turnover <= slot_minutes).
Multiple seeded list-scheduling attempts; a failed search is not an infeasibility proof.
"""
import argparse
import hashlib
import json
import random
from copy import deepcopy
from collections import defaultdict
from datetime import datetime, timedelta
from itertools import combinations
from pathlib import Path


def dt(value):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is not None or parsed.second or parsed.microsecond:
        raise ValueError('Use local event time with whole-minute precision; keep timezone in metadata')
    return parsed


def slots_for(data):
    size = data['slot_minutes']
    if type(size) is not int or size <= 0:
        raise ValueError('slot_minutes must be a positive integer')
    result = []
    last_end = None
    for session in data['sessions']:
        start, end = dt(session['start']), dt(session['end'])
        if end <= start or (last_end is not None and start < last_end):
            raise ValueError('Sessions must be ordered, positive and non-overlapping')
        if not isinstance(session['section'], int) or session['section'] < 1:
            raise ValueError('Section must be a positive integer')
        last_end = end
        while start + timedelta(minutes=size) <= end:
            result.append({'index': len(result), 'scene': len(result) + 1,
                           'start': start.isoformat(timespec='minutes'),
                           'end': (start + timedelta(minutes=size)).isoformat(timespec='minutes'),
                           'section': session['section'],
                           'courts': session.get('courts', data['courts'])})
            start += timedelta(minutes=size)
    return result


def prepare(data):
    if not data['sessions']:
        raise ValueError('At least one confirmed session is required')
    slots = slots_for(data)
    matches = data['matches']
    by_id = {m['id']: m for m in matches}
    if len(by_id) != len(matches) or not matches:
        raise ValueError('Match IDs must be unique; matches cannot be empty')
    objective_order(data)
    for relation in data.get('strict_finish_order', []):
        projects = {m['project_id'] for m in matches}
        if (relation.get('before') not in projects or relation.get('after') not in projects
                or relation['before'] == relation['after']
                or relation.get('source', {}).get('kind') != 'user'
                or not isinstance(relation['source'].get('reference'), str)
                or not relation['source']['reference'].strip()):
            raise ValueError('Strict finish order needs distinct projects and an explicit user source')
    if data.get('conflict_scope') not in ('known', 'possible'):
        raise ValueError('Confirm conflict_scope: known or possible')
    if data.get('rest_basis') not in ('elapsed', 'active_scenes'):
        raise ValueError('Confirm rest_basis: elapsed or active_scenes')
    for key in ('rest_minutes', 'rest_scenes', 'turnover_minutes'):
        value = data.get(key, 0)
        if type(value) is not int or value < 0:
            raise ValueError(key + ' must be a non-negative integer')
    required_rest = 'rest_minutes' if data['rest_basis'] == 'elapsed' else 'rest_scenes'
    if required_rest not in data:
        raise ValueError('Missing confirmed rest parameter: ' + required_rest)
    courts = data['courts']
    if not courts or len(set(courts)) != len(courts):
        raise ValueError('Courts must be distinct and non-empty')
    for s in slots:
        if not s['courts'] or len(set(s['courts'])) != len(s['courts']) or not set(s['courts']) <= set(courts):
            raise ValueError('Session courts must be distinct members of courts')
    for m in matches:
        duration = m.get('duration_minutes', data['slot_minutes'])
        if type(duration) is not int or duration <= 0 or duration + data.get('turnover_minutes', 0) > data['slot_minutes']:
            raise ValueError('One-slot engine requires duration + turnover <= slot_minutes')
        if len(m['athletes']) != len(set(m['athletes'])):
            raise ValueError('Duplicate athlete inside match ' + m['id'])
        if data['conflict_scope'] == 'possible' and 'possible_athletes' not in m:
            raise ValueError('possible_athletes required for every match in possible mode')
        if 'possible_athletes' in m and not set(m['athletes']) <= set(m['possible_athletes']):
            raise ValueError('possible_athletes must include confirmed athletes: ' + m['id'])
        if m.get('allowed_courts') is not None and not set(m['allowed_courts']) <= set(courts):
            raise ValueError('Unknown allowed court')
        for parent in m.get('predecessors', []):
            if parent not in by_id or parent == m['id']:
                raise ValueError('Invalid predecessor: ' + parent)
        if len(set(m.get('predecessors', []))) != len(m.get('predecessors', [])):
            raise ValueError('Duplicate predecessor: ' + m['id'])
        # If an adapter supplies structured sides, reconcile them with the DAG.
        for side in m.get('sides', []):
            if side.get('kind') in ('winner', 'loser'):
                if side.get('match_id') not in m.get('predecessors', []):
                    raise ValueError('Side source missing from predecessors: ' + m['id'])
            if side.get('kind') == 'group_rank':
                sources = side.get('match_ids', [])
                if not isinstance(sources, list) or not sources or len(sources) != len(set(sources)):
                    raise ValueError('Group ranking needs distinct source matches: ' + m['id'])
                if not set(sources) <= set(m.get('predecessors', [])):
                    raise ValueError('Group ranking source missing from predecessors: ' + m['id'])
                for source_id in sources:
                    source = by_id[source_id]
                    if source['project_id'] != m['project_id']:
                        raise ValueError('Group ranking source crosses projects: ' + m['id'])
                    if 'stage' in source and 'stage' in m and source['stage'] >= m['stage']:
                        raise ValueError('Group ranking source is not an earlier stage: ' + m['id'])
            if not set(side.get('athletes', [])) <= set(m['athletes']):
                raise ValueError('Side athlete missing from confirmed athletes: ' + m['id'])
            if data['conflict_scope'] == 'possible' and not set(side.get('possible_athletes', [])) <= set(m['possible_athletes']):
                raise ValueError('Side candidates missing from possible athletes: ' + m['id'])
        if data['conflict_scope'] == 'possible':
            for parent in m.get('predecessors', []):
                source = by_id[parent]
                if not set(source.get('possible_athletes', source['athletes'])) <= set(m['possible_athletes']):
                    raise ValueError('Predecessor candidates missing from possible athletes: ' + m['id'])
    depth, visiting = {}, set()
    children = {mid: [] for mid in by_id}
    for m in matches:
        for parent in m.get('predecessors', []):
            children[parent].append(m['id'])

    def visit(mid):
        if mid in visiting:
            raise ValueError('Cyclic match dependencies')
        if mid not in depth:
            visiting.add(mid)
            depth[mid] = 1 + max((visit(c) for c in children[mid]), default=0)
            visiting.remove(mid)
        return depth[mid]

    for mid in by_id:
        visit(mid)
    field = 'athletes' if data['conflict_scope'] == 'known' else 'possible_athletes'
    participants = {m['id']: set(m[field]) for m in matches}
    # Explicitly proved disjoint outcome paths, e.g. final and bronze match.
    disjoint = {frozenset(p) for p in data.get('outcome_disjoint_pairs', [])}
    for pair in disjoint:
        if len(pair) != 2 or not pair <= by_id.keys():
            raise ValueError('Invalid outcome-disjoint pair')
    for a, b in combinations(matches, 2):
        if frozenset((a['id'], b['id'])) in disjoint:
            if set(a['athletes']) & set(b['athletes']):
                raise ValueError('Confirmed athletes contradict outcome-disjoint claim')
            if not prove_opposite_outcomes(a, b, by_id):
                raise ValueError('Outcome-disjoint claim lacks opposite winner/loser source proof')
    conflicts = {mid: set() for mid in by_id}
    for a, b in combinations(by_id, 2):
        if participants[a] & participants[b] and frozenset((a, b)) not in disjoint:
            conflicts[a].add(b)
            conflicts[b].add(a)
    return slots, by_id, depth, conflicts


def prove_opposite_outcomes(a, b, matches):
    """Narrow proof for opposite winner/loser paths from the same disjoint feeders.

    Unproved exemptions are rejected; other classification brackets need their own proof.
    """
    sources = []
    for match in (a, b):
        sides = match.get('sides', [])
        if not sides or any(s.get('kind') not in ('winner', 'loser') for s in sides):
            return False
        outcomes = {s.get('match_id'): s['kind'] for s in sides}
        if len(outcomes) != len(sides) or not outcomes.keys() <= matches.keys():
            return False
        sources.append(outcomes)
    if sources[0].keys() != sources[1].keys():
        return False
    if any(sources[0][mid] == sources[1][mid] for mid in sources[0]):
        return False
    pools = []
    for mid in sources[0]:
        parent = matches[mid]
        pool = set(parent.get('possible_athletes', parent['athletes']))
        if not pool or any(pool & other for other in pools):
            return False
        pools.append(pool)
    return True


def rest_ok(data, earlier, later):
    if dt(earlier['end']) > dt(later['start']):
        return False
    if data['rest_basis'] == 'active_scenes':
        return later['slot_index'] - earlier['slot_index'] >= data['rest_scenes'] + 1
    return (dt(later['start']) - dt(earlier['end'])).total_seconds() >= 60 * data['rest_minutes']


def record_for(data, match, slot, court):
    end = dt(slot['start']) + timedelta(minutes=match.get('duration_minutes', data['slot_minutes']))
    return {'match_id': match['id'], 'project_id': match['project_id'],
            'slot_index': slot['index'], 'scene': slot['scene'], 'section': slot['section'],
            'start': slot['start'], 'end': end.isoformat(timespec='minutes'), 'court': court}


def allowed(data, match, rec):
    if rec['court'] not in match.get('allowed_courts', data['courts']):
        return False
    if match.get('not_before') and dt(rec['start']) < dt(match['not_before']):
        return False
    if match.get('finish_by') and dt(rec['end']) > dt(match['finish_by']):
        return False
    fixed = match.get('fixed', {})
    if any(rec.get(k) != v for k, v in fixed.items()):
        return False
    return True


def validate(data, result):
    """Recompute all hard constraints from the serialized result, not scheduler state."""
    slots, matches, _, conflicts = prepare(data)
    errors, rows = [], result['assignments']
    assigned = {r['match_id']: r for r in rows}
    if len(assigned) != len(rows):
        errors.append('Duplicate match assignments')
    if set(assigned) - matches.keys():
        errors.append('Unknown match assignments')
    occupied = set()
    for rec in rows:
        mid, idx = rec['match_id'], rec['slot_index']
        if mid not in matches or not 0 <= idx < len(slots):
            errors.append('Invalid match/slot: ' + mid)
            continue
        m, s = matches[mid], slots[idx]
        expected = record_for(data, m, s, rec['court'])
        if rec != expected or rec['court'] not in s['courts'] or not allowed(data, m, rec):
            errors.append('Time/court/window mismatch: ' + mid)
        key = (idx, rec['court'])
        if key in occupied:
            errors.append('Court overlap: ' + str(key))
        occupied.add(key)
        for parent in m.get('predecessors', []):
            if parent not in assigned or not rest_ok(data, assigned[parent], rec):
                errors.append('Predecessor/rest violation: ' + parent + ' -> ' + mid)
    for a, b in combinations(assigned, 2):
        if a in conflicts and b in conflicts[a]:
            ra, rb = sorted((assigned[a], assigned[b]), key=lambda r: r['start'])
            if not rest_ok(data, ra, rb):
                errors.append('Athlete conflict/rest: ' + a + ', ' + b)
    missing = sorted(matches.keys() - assigned.keys())
    if not missing and not errors:
        for relation in data.get('strict_finish_order', []):
            ends = {p: max(r['end'] for r in rows if r['project_id'] == p)
                    for p in (relation['before'], relation['after'])}
            if ends[relation['before']] >= ends[relation['after']]:
                errors.append('Explicit strict finish order violation: ' + relation['before'] + ' -> ' + relation['after'])
    if sorted(result.get('unscheduled', [])) != missing:
        errors.append('Unscheduled list mismatch')
    return {'valid': not errors, 'complete': not missing and not errors, 'errors': errors,
            'scheduled': len(assigned), 'unscheduled': missing,
            'conflict_scope': data['conflict_scope'], 'rest_basis': data['rest_basis']}


DEFAULT_OBJECTIVES = ('makespan', 'priority_completion', 'project_completion_sum',
                      'round_splits', 'round_span_minutes', 'total_wait_minutes', 'start_times')


def objective_order(data):
    objective = data.get('objective', 'makespan')
    if objective not in ('makespan', 'project_first'):
        raise ValueError('objective must be makespan or project_first')
    priority = data.get('priority_projects', [])
    projects = {m['project_id'] for m in data['matches']}
    if len(set(priority)) != len(priority) or not set(priority) <= projects:
        raise ValueError('Invalid priority projects')
    if objective == 'project_first' and not priority:
        raise ValueError('project_first requires an explicitly selected priority project')
    default = list(DEFAULT_OBJECTIVES)
    if objective == 'project_first':
        default[:2] = default[1::-1]
    order = data.get('objective_order', default)
    if not isinstance(order, list) or len(order) != len(default) or set(order) != set(default):
        raise ValueError('objective_order must be a permutation of all seven supported objectives')
    return order


def constraint_catalog(data):
    """Keep unknown provenance visible; never turn inferred preferences into hard rules."""
    supplied = data.get('constraint_sources', {})
    if not isinstance(supplied, dict):
        raise ValueError('constraint_sources must be a mapping')
    for source in supplied.values():
        if (not isinstance(source, dict) or source.get('kind') not in ('user', 'regulation', 'structure')
                or not isinstance(source.get('reference'), str) or not source['reference'].strip()):
            raise ValueError('Each constraint source needs kind and reference')
    rows = []

    def add(key, value, structural=False, source=None):
        origin = source or ({'kind': 'structure', 'reference': key} if structural else
                            supplied.get(key, supplied.get(key.split('.')[-1], supplied.get('*'))))
        rows.append({'id': key, 'value': value, 'hard': True,
                     'source': origin or {'kind': 'unverified_input', 'reference': 'input:' + key},
                     'source_verified': origin is not None})

    for key in ('courts', 'sessions', 'slot_minutes', 'conflict_scope', 'rest_basis'):
        add(key, data[key])
    add('rest_minutes' if data['rest_basis'] == 'elapsed' else 'rest_scenes',
        data['rest_minutes'] if data['rest_basis'] == 'elapsed' else data['rest_scenes'])
    if data.get('turnover_minutes'):
        add('turnover_minutes', data['turnover_minutes'])
    add('match_completeness', 'every actual match exactly once', True)
    add('court_exclusion', 'one match per court and slot', True)
    add('athlete_exclusion', 'stable athlete IDs, across projects within confirmed scope', True)
    if data.get('outcome_disjoint_pairs'):
        add('outcome_disjoint_pairs', data['outcome_disjoint_pairs'], True)
    for m in data['matches']:
        if m.get('predecessors'):
            add('matches.' + m['id'] + '.predecessors', m['predecessors'], True)
        for key in ('duration_minutes', 'allowed_courts', 'not_before', 'finish_by', 'fixed'):
            if key in m:
                add('matches.' + m['id'] + '.' + key, m[key])
    for i, relation in enumerate(data.get('strict_finish_order', [])):
        add('strict_finish_order.' + str(i), [relation['before'], relation['after']], source=relation['source'])
    return rows


def round_groups(matches):
    groups = defaultdict(list)
    for mid, m in matches.items():
        # Missing round metadata must not invent one giant synchronous round.
        if m.get('round') is not None:
            groups[(m['project_id'], str(m.get('stage', 1)), str(m['round']))].append(mid)
    return [sorted(ids) for _, ids in sorted(groups.items())]


def release_time(data, earlier, slots):
    if data['rest_basis'] == 'elapsed':
        return dt(earlier['end']) + timedelta(minutes=data['rest_minutes'])
    idx = earlier['slot_index'] + data['rest_scenes'] + 1
    return dt(slots[idx]['start']) if idx < len(slots) else datetime.max


def metrics(data, result, context=None):
    slots, matches, _, conflicts = context or prepare(data)
    placed = {r['match_id']: r for r in result['assignments']}
    origin = dt(data['sessions'][0]['start'])
    minutes = lambda value: int((dt(value) - origin).total_seconds() // 60)
    projects = sorted({m['project_id'] for m in matches.values()})
    ends = {p: max((r['end'] for r in placed.values() if r['project_id'] == p), default=None) for p in projects}
    complete = {p: all(mid in placed for mid, m in matches.items() if m['project_id'] == p) for p in projects}
    sentinel = 10**12
    finish = {p: minutes(ends[p]) if complete[p] else sentinel for p in projects}
    splits = span = waiting = 0
    for group in round_groups(matches):
        starts = {placed[mid]['start'] for mid in group if mid in placed}
        splits += max(0, len(starts) - 1)
        if starts:
            span += minutes(max(starts)) - minutes(min(starts))
    for mid, rec in placed.items():
        m = matches[mid]
        lower = max(origin, dt(m.get('not_before', data['sessions'][0]['start'])))
        related = set(m.get('predecessors', [])) | conflicts[mid]
        for other in related & placed.keys():
            if placed[other]['start'] < rec['start']:
                lower = max(lower, release_time(data, placed[other], slots))
        # Calendar waiting, not claimed to be every athlete's on-site waiting.
        waiting += max(0, int((dt(rec['start']) - lower).total_seconds() // 60))
    indexes = {r['slot_index'] for r in placed.values()}
    return {'makespan': max(finish.values()),
            'priority_completion': [finish[p] for p in data.get('priority_projects', [])],
            'project_completion_sum': sum(finish.values()), 'round_splits': splits,
            'round_span_minutes': span, 'total_wait_minutes': waiting,
            'start_times': [minutes(placed[mid]['start']) if mid in placed else sentinel for mid in sorted(matches)],
            'start_time_match_order': sorted(matches), 'project_end_times': ends,
            'expected_end': max((r['end'] for r in placed.values()), default=None),
            'total_matches': len(matches), 'scheduled_matches': len(placed),
            'occupied_scenes': len(indexes),
            'scene_span': max(indexes) - min(indexes) + 1 if indexes else 0,
            'time_origin': origin.isoformat(timespec='minutes')}


def score(data, values):
    return tuple(tuple(values[k]) if isinstance(values[k], list) else values[k] for k in objective_order(data))


def first_changed_objective(data, before, after):
    return next((k for k in objective_order(data) if before[k] != after[k]), None)


def placement_violations(data, context, placed, mid, rec):
    """Check both directions, including all unchanged/fixed successors and cross-project athletes."""
    slots, matches, _, conflicts = context
    m = matches[mid]; failures = []

    def fail(code, constraint, other=None):
        failures.append({'category': 'hard_constraint', 'code': code, 'constraint': constraint,
                         'related_match': other,
                         'rest_constraint': ('rest_minutes' if data['rest_basis'] == 'elapsed' else 'rest_scenes')
                         if 'rest' in code else None})

    idx = rec['slot_index']
    if rec['court'] not in slots[idx]['courts']:
        fail('court_unavailable', 'sessions')
    if not allowed(data, m, rec):
        for key in ('allowed_courts', 'not_before', 'finish_by', 'fixed'):
            if key in m and not allowed(data, {key: m[key]}, rec):
                fail('window_or_fixed', 'matches.' + mid + '.' + key)
    for other, row in placed.items():
        if other == mid:
            continue
        if idx == row['slot_index'] and rec['court'] == row['court']:
            fail('court_occupied', 'court_exclusion', other)
        if other in conflicts[mid]:
            a, b = sorted((row, rec), key=lambda r: r['start'])
            if not rest_ok(data, a, b):
                fail('athlete_overlap_or_rest', 'athlete_exclusion', other)
        if mid in matches[other].get('predecessors', []) and not rest_ok(data, rec, row):
            fail('successor_dependency_or_rest', 'matches.' + other + '.predecessors', other)
    for parent in m.get('predecessors', []):
        if parent not in placed or not rest_ok(data, placed[parent], rec):
            fail('predecessor_dependency_or_rest', 'matches.' + mid + '.predecessors', parent)
    trial = dict(placed); trial[mid] = rec
    for i, relation in enumerate(data.get('strict_finish_order', [])):
        a, b = relation['before'], relation['after']
        ends = {p: max((r['end'] for r in trial.values() if r['project_id'] == p), default='') for p in (a, b)}
        if ends[a] >= ends[b]:
            fail('explicit_strict_finish_order', 'strict_finish_order.' + str(i))
    return failures


def moved_records(data, context, placed, targets):
    """Exact court matching for a proposed set of slot changes, then whole-neighborhood legality."""
    slots, matches, _, _ = context
    trial = {mid: r for mid, r in placed.items() if mid not in targets}
    groups = defaultdict(list)
    for mid, idx in targets.items():
        if not 0 <= idx < len(slots):
            return None
        groups[idx].append(mid)
    for idx, mids in sorted(groups.items()):
        occupied = {r['court'] for r in trial.values() if r['slot_index'] == idx}
        options = {mid: [c for c in slots[idx]['courts'] if c not in occupied
                         and allowed(data, matches[mid], record_for(data, matches[mid], slots[idx], c))] for mid in mids}
        owners = {}

        def augment(mid, seen):
            for court in options[mid]:
                if court in seen:
                    continue
                seen.add(court)
                if court not in owners or augment(owners[court], seen):
                    owners[court] = mid
                    return True
            return False

        if any(not augment(mid, set()) for mid in sorted(mids, key=lambda x: (len(options[x]), x))):
            return None
        for court, mid in owners.items():
            trial[mid] = record_for(data, matches[mid], slots[idx], court)
    if any(placement_violations(data, context, trial, mid, trial[mid]) for mid in targets):
        return None
    return trial


def search_settings(data):
    settings = {'max_evaluations': 100000, 'max_chain_matches': 6, 'swaps': True}
    supplied = data.get('local_search', {})
    if set(supplied) - settings.keys():
        raise ValueError('Unknown local_search setting')
    settings.update(supplied)
    for k in ('max_evaluations', 'max_chain_matches'):
        if type(settings[k]) is not int or settings[k] < 1:
            raise ValueError(k + ' must be a positive integer')
    if type(settings['swaps']) is not bool:
        raise ValueError('local_search.swaps must be boolean')
    return settings


def proposals(context, placed, settings):
    _, matches, _, _ = context
    ids = sorted(placed)
    yield 'single', ({mid: idx} for mid in ids for idx in range(placed[mid]['slot_index']))
    groups = set()
    for group in round_groups(matches):
        if len(group) > 1:
            groups.add(tuple(group))
        # Also move the same-round cohort sharing a start; a fixed earlier
        # cohort must not prevent this subset from advancing together.
        cohorts = defaultdict(list)
        for mid in group:
            cohorts[placed[mid]['slot_index']].append(mid)
        groups.update(tuple(ids) for ids in cohorts.values() if len(ids) > 1)
    yield 'round_group', ({mid: placed[mid]['slot_index'] - shift for mid in group}
                          for group in sorted(groups) for shift in range(1, min(placed[m]['slot_index'] for m in group) + 1))
    chains = set()
    for mid in ids:
        ancestors, todo = {mid}, [mid]
        while todo:
            for parent in matches[todo.pop()].get('predecessors', []):
                if parent not in ancestors:
                    ancestors.add(parent); todo.append(parent)
        if 1 < len(ancestors) <= settings['max_chain_matches']:
            chains.add(tuple(sorted(ancestors)))
    yield 'ancestor_chain', ({mid: placed[mid]['slot_index'] - shift for mid in chain}
                            for chain in sorted(chains) for shift in range(1, min(placed[m]['slot_index'] for m in chain) + 1))
    if settings['swaps']:
        yield 'pair_swap', ({a: placed[b]['slot_index'], b: placed[a]['slot_index']}
                            for a, b in combinations(ids, 2) if placed[a]['slot_index'] != placed[b]['slot_index'])


def find_improvement(data, result, context=None, limit=None):
    context = context or prepare(data)
    placed = {r['match_id']: r for r in result['assignments']}
    settings = search_settings(data)
    maximum = settings['max_evaluations'] if limit is None else limit
    before = metrics(data, result, context); baseline = score(data, before)
    counts, exhausted, count = {}, [], 0
    for kind, changes in proposals(context, placed, settings):
        counts[kind] = 0
        for targets in changes:
            if count >= maximum:
                return None, {'status': 'search_limit', 'evaluations': count, 'counts': counts, 'exhausted': exhausted}
            count += 1; counts[kind] += 1
            trial = moved_records(data, context, placed, targets)
            if trial is None:
                continue
            after = metrics(data, {'assignments': list(trial.values())}, context)
            if score(data, after) < baseline:
                return trial, {'status': 'improvement_found', 'kind': kind, 'evaluations': count,
                               'counts': counts, 'exhausted': exhausted,
                               'objective': first_changed_objective(data, before, after),
                               'changes': [{'match_id': mid, 'before': placed[mid], 'after': trial[mid]}
                                           for mid in sorted(targets)], 'before': before, 'after': after}
        exhausted.append(kind)
    return None, {'status': 'no_improvement_in_checked_neighborhood', 'evaluations': count,
                  'counts': counts, 'exhausted': exhausted, 'global_optimality_proven': False,
                  'swap_status': 'bounded_search_no_improvement' if settings['swaps'] else 'not_requested',
                  'infeasibility_proven': False}


def explain_waits(data, result, context=None):
    context = context or prepare(data)
    slots, matches, _, _ = context
    placed = {r['match_id']: r for r in result['assignments']}
    before = metrics(data, result, context); old_score = score(data, before)
    focus = data.get('focus_matches', [mid for mid, r in placed.items()
                                      if r['end'] == before['project_end_times'][r['project_id']]])
    if not set(focus) <= matches.keys():
        raise ValueError('Unknown focus match')
    reports = []
    for mid in focus:
        rec = placed[mid]; details = []; earliest = None
        for slot in slots[:rec['slot_index'] + 1]:
            alternatives = []; legal = False
            for court in slot['courts']:
                candidate = record_for(data, matches[mid], slot, court)
                failures = placement_violations(data, context, placed, mid, candidate)
                if not failures:
                    legal = True
                    trial = dict(placed); trial[mid] = candidate
                    after = metrics(data, {'assignments': list(trial.values())}, context)
                    new_score = score(data, after)
                    failures = [{'category': 'optimization_tradeoff' if new_score > old_score else
                                             'avoidable_wait' if new_score < old_score else 'objective_tie',
                                 'objective': first_changed_objective(data, before, after)}]
                alternatives.append({'court': court, 'reasons': failures})
            if legal and earliest is None:
                earliest = slot['start']
            if slot['index'] < rec['slot_index']:
                free = [c for c in slot['courts'] if not any(r['slot_index'] == slot['index'] and r['court'] == c
                        for other, r in placed.items() if other != mid)]
                details.append({'scene': slot['scene'], 'start': slot['start'], 'free_courts': free,
                                'alternatives': alternatives})
        parents = [{'match_id': p, 'end': placed[p]['end'],
                    'rest_release': release_time(data, placed[p], slots).isoformat(timespec='minutes')}
                   for p in matches[mid].get('predecessors', [])]
        reports.append({'match_id': mid, 'scheduled_start': rec['start'], 'predecessors': parents,
                        'earliest_legal_start_with_other_matches_fixed': earliest,
                        'earlier_scenes': details, 'infeasibility_proven': False,
                        'scope': 'single-match relocation on supplied grid; all other matches fixed'})
    return reports


def acceptance(data, result, explain=True):
    context = prepare(data)
    hard = validate(data, result)
    digest = hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    if (result.get('event_id') != data['event_id'] or result.get('input_sha256') != digest
            or result.get('slots') != context[0]):
        hard['errors'].append('Event/input/grid version mismatch')
        hard.update(valid=False, complete=False)
    sources = constraint_catalog(data)
    if not hard['complete']:
        return {'hard_constraints': hard, 'ready_for_export': False, 'quality_checked': False,
                'constraint_sources': sources, 'global_optimality_proven': False}
    _, audit = find_improvement(data, result, context)
    clean = audit['status'] == 'no_improvement_in_checked_neighborhood'
    known_sources = all(c['source_verified'] for c in sources)
    return {'hard_constraints': hard, 'objective_order': objective_order(data),
            'metrics': metrics(data, result, context), 'constraint_sources': sources,
            'sources_complete': known_sources, 'quality_checked': clean,
            'ready_for_export': clean and known_sources,
            'local_search': audit, 'global_optimality_proven': False,
            'waiting_explanations': explain_waits(data, result, context) if explain else []}


def improve(data, result):
    """Improve a complete candidate without changing inputs, identities or hard rules."""
    context = prepare(data)
    digest = hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    if (result.get('event_id') != data['event_id'] or result.get('input_sha256') != digest
            or result.get('slots') != context[0]):
        raise ValueError('Candidate does not match event/input/grid version')
    if not validate(data, result)['complete']:
        raise ValueError('Local improvement requires a complete hard-valid candidate')
    output = deepcopy(result)
    before = metrics(data, output, context)
    moves, count = [], 0
    maximum = search_settings(data)['max_evaluations']
    while True:
        trial, audit = find_improvement(data, output, context, max(0, maximum - count))
        count += audit['evaluations']
        if trial is None:
            break
        moves.append({k: audit[k] for k in ('kind', 'objective', 'changes', 'before', 'after')})
        output['assignments'] = sorted(trial.values(), key=lambda r: (r['slot_index'], str(r['court']), r['match_id']))
    output.update(status='complete', objective_order=objective_order(data), optimality_proven=False,
                  metrics=metrics(data, output, context), constraint_sources=constraint_catalog(data))
    output['optimization'] = {'before': before, 'after': output['metrics'], 'moves': moves,
                              'evaluations': count, 'termination': audit,
                              'model': 'one-slot local-time grid; supplied athletes, DAG, windows and fixed arrangements',
                              'neighborhood': search_settings(data), 'global_optimality_proven': False}
    output['validation'] = validate(data, output)
    output['acceptance'] = acceptance(data, output)
    return output


def audit_tables(data, result, report):
    """Small, untruncated rows shared by offline and platform-file exporters."""
    encode = lambda value: json.dumps(value, ensure_ascii=False)
    tables = {}
    values = report['metrics']
    before = result.get('optimization', {}).get('before', {})
    tables['优化指标'] = [['指标', '优化前（生成记录）', '当前（独立重算）']]
    for key in report['objective_order'] + ['total_matches', 'occupied_scenes', 'scene_span', 'expected_end', 'time_origin', 'project_end_times']:
        # Per-match start vectors can exceed the Excel cell length limit.
        if key == 'start_times':
            tables['优化指标'].append([key, '见逐场开始指标', '见逐场开始指标'])
            continue
        tables['优化指标'].append([key, encode(before.get(key)), encode(values[key])])
    tables['逐场开始指标'] = [['场次', '优化前分钟数（生成记录）', '当前分钟数（独立重算）']]
    old_starts = dict(zip(before.get('start_time_match_order', []), before.get('start_times', [])))
    tables['逐场开始指标'] += [[mid, old_starts.get(mid), start]
                              for mid, start in zip(values['start_time_match_order'], values['start_times'])]
    tables['约束来源'] = [['约束', '取值', '来源类型', '依据', '来源已记录']]
    tables['约束来源'] += [[r['id'], encode(r['value']), r['source']['kind'],
                           r['source']['reference'], r['source_verified']] for r in report['constraint_sources']]
    tables['前移记录'] = [['调整序号', '搜索类型', '首个改善目标', '场次', '原开始', '新开始', '原场地', '新场地']]
    for i, move in enumerate(result.get('optimization', {}).get('moves', []), 1):
        tables['前移记录'] += [[i, move['kind'], move['objective'], c['match_id'], c['before']['start'],
                              c['after']['start'], c['before']['court'], c['after']['court']] for c in move['changes']]
    tables['等待解释'] = [['场次', '当前开始', '其他比赛固定时最早合法开始', '前置场次', '前置结束', '休息释放']]
    tables['早场阻塞'] = [['场次', '更早场序', '开始', '场地', '场地空闲', '类别', '原因', '约束/目标', '关联场次', '休息依据']]
    for item in report['waiting_explanations']:
        for parent in item['predecessors'] or [{}]:
            tables['等待解释'].append([item['match_id'], item['scheduled_start'],
                item['earliest_legal_start_with_other_matches_fixed'], parent.get('match_id'), parent.get('end'), parent.get('rest_release')])
        for slot in item['earlier_scenes']:
            for alternative in slot['alternatives']:
                for reason in alternative['reasons']:
                    tables['早场阻塞'].append([item['match_id'], slot['scene'], slot['start'], alternative['court'],
                        alternative['court'] in slot['free_courts'], reason['category'], reason.get('code'),
                        reason.get('constraint', reason.get('objective')), reason.get('related_match'), reason.get('rest_constraint')])
    tables['优化验收'] = [['事项', '内容'], ['目标顺序', encode(report['objective_order'])],
        ['搜索范围', encode(search_settings(data))], ['验收搜索证据', encode(report['local_search'])],
        ['正式导出条件合格', report['ready_for_export']], ['全局最优已证明', False],
        ['模型范围', '单场占一格；当前输入的人员口径、依赖、窗口、休息和固定安排'],
        ['结论', '仅在已检查的单场、同轮整体平移、有限上游链及换位范围内未找到改进；不证明全局最优或不可行'],
        ['优化前与调整记录', '来自候选生成记录；当前指标及验收在导出时独立重算']]
    return tables


def schedule(data):
    slots, matches, depth, conflicts = prepare(data)
    # Compute static windows once; repeated attempts only vary the match order.
    court_options, mandatory = {}, {}
    for mid, match in matches.items():
        feasible = []
        for slot in slots:
            courts = [c for c in slot['courts'] if allowed(data, match, record_for(data, match, slot, c))]
            court_options[(mid, slot['index'])] = courts
            if courts:
                feasible.append(slot['index'])
        if len(feasible) == 1:
            idx = feasible[0]
            mandatory[mid] = record_for(data, match, slots[idx], court_options[(mid, idx)][0])
    project_counts = {}
    for m in matches.values():
        project_counts[m['project_id']] = project_counts.get(m['project_id'], 0) + 1
    objective = data.get('objective', 'makespan')
    if objective not in ('makespan', 'project_first'):
        raise ValueError('objective must be makespan or project_first')
    priority = data.get('priority_projects', [])
    if objective == 'project_first' and not priority:
        raise ValueError('project_first requires an explicitly selected priority project')
    if len(set(priority)) != len(priority) or not set(priority) <= project_counts.keys():
        raise ValueError('Invalid priority projects')
    order = priority + sorted(project_counts.keys() - set(priority), key=lambda p: (project_counts[p], p))
    rank = {p: i for i, p in enumerate(order)}
    attempts = data.get('attempts', 80)
    if not isinstance(attempts, int) or attempts < 1:
        raise ValueError('attempts must be positive')
    best, best_key = None, None
    for attempt in range(attempts):
        rng = random.Random(str(data.get('random_seed', 0)) + ':' + str(attempt))
        jitter = {mid: rng.random() for mid in matches}
        placed = {}
        for s in slots:
            available_courts = list(s['courts'])
            remaining = [m for mid, m in matches.items() if mid not in placed]
            # Fixed slots first, then explicit project priority and downstream path.
            mode = attempt % 4
            def order_key(m):
                # Explore across projects, instead of always starving the longer project.
                if mode == 0:
                    key = (rank[m['project_id']], -depth[m['id']], jitter[m['id']])
                elif mode == 1:
                    key = (-depth[m['id']], rank[m['project_id']], jitter[m['id']])
                elif mode == 2:
                    key = (-depth[m['id']], jitter[m['id']], rank[m['project_id']])
                else:
                    key = (-depth[m['id']] + 2 * jitter[m['id']], rank[m['project_id']], jitter[m['id']])
                forced_here = mandatory.get(m['id'], {}).get('slot_index') == s['index']
                return (0 if forced_here else 1,
                        len(court_options[(m['id'], s['index'])]) if forced_here else 0,
                        *key, m['id'])
            remaining.sort(key=order_key)
            # Prefer courts with fewer alternative users; preserve a sole court
            # for a constrained match when a flexible match has another option.
            court_demand = {c: sum(1 / len(options) for m in remaining
                                  if (options := court_options[(m['id'], s['index'])]) and c in options)
                            for c in available_courts}
            for m in remaining:
                if not available_courts:
                    break
                eligible_courts = [c for c in available_courts if c in court_options[(m['id'], s['index'])]]
                if not eligible_courts:
                    continue
                court = min(eligible_courts, key=lambda c: court_demand[c])
                rec = record_for(data, m, s, court)
                parents = m.get('predecessors', [])
                if any(p not in placed or not rest_ok(data, placed[p], rec) for p in parents):
                    continue
                if any(not rest_ok(data, placed[p], rec) for p in conflicts[m['id']] & placed.keys()):
                    continue
                # A future fixed/window-forced match cannot move. Playing an
                # optional match now must leave its athlete/dependency rest intact.
                if any(future not in placed and fixed['slot_index'] > s['index']
                       and (future in conflicts[m['id']] or m['id'] in matches[future].get('predecessors', []))
                       and not rest_ok(data, rec, fixed) for future, fixed in mandatory.items()):
                    continue
                # A strict ending order is enforced only when explicitly supplied.
                strict_block = False
                for relation in data.get('strict_finish_order', []):
                    if m['project_id'] != relation['after']:
                        continue
                    after_left = [x for x in matches if matches[x]['project_id'] == relation['after'] and x not in placed]
                    if after_left != [m['id']]:
                        continue
                    before_ids = [x for x in matches if matches[x]['project_id'] == relation['before']]
                    if (any(x not in placed for x in before_ids)
                            or max(placed[x]['end'] for x in before_ids) >= rec['end']):
                        strict_block = True
                if strict_block:
                    continue
                placed[m['id']] = rec
                available_courts.remove(rec['court'])
        candidate = {'schema': 'gamemaster.schedule.v1', 'event_id': data['event_id'],
                    'input_sha256': hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
                    'algorithm': 'seeded-list-scheduling+bounded-local-search', 'objective': objective,
                    'attempt': attempt, 'attempts': attempts,
                    'optimality_proven': False, 'priority_order': order, 'slots': slots,
                    'assignments': sorted(placed.values(), key=lambda r: (r['slot_index'], r['court'])),
                    'unscheduled': sorted(matches.keys() - placed.keys())}
        # Only hard-valid candidates participate in objective comparisons.
        if not validate(data, candidate)['valid']:
            continue
        candidate_key = (len(matches) - len(placed), *score(data, metrics(data, candidate,
                         (slots, matches, depth, conflicts))))
        if best_key is None or candidate_key < best_key:
            best_key, best = candidate_key, candidate
    if best is None:
        best = dict(candidate, assignments=[], unscheduled=sorted(matches))
    best['validation'] = validate(data, best)
    best['status'] = 'complete' if best['validation']['complete'] else 'search_incomplete'
    if best['validation']['complete']:
        return improve(data, best)
    best['acceptance'] = acceptance(data, best)
    return best


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--improve-existing', type=Path, help='Improve a complete candidate JSON locally')
    parser.add_argument('--check', type=Path, help='Independently audit a candidate; output is an audit JSON')
    args = parser.parse_args()
    if args.check and args.improve_existing:
        parser.error('--check and --improve-existing are mutually exclusive')
    data = json.loads(args.input.read_text())
    if args.check:
        report = acceptance(data, json.loads(args.check.read_text()))
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        raise SystemExit(0 if report['ready_for_export'] else 2)
    result = (improve(data, json.loads(args.improve_existing.read_text())) if args.improve_existing
              else schedule(data))
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({'status': result['status'], **result['validation']}, ensure_ascii=False))
    raise SystemExit(0 if result['validation']['complete'] else 2)


if __name__ == '__main__':
    main()
