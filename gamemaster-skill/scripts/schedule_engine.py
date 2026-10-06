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
    slots = slots_for(data)
    matches = data['matches']
    by_id = {m['id']: m for m in matches}
    if len(by_id) != len(matches) or not matches:
        raise ValueError('Match IDs must be unique; matches cannot be empty')
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
    if sorted(result.get('unscheduled', [])) != missing:
        errors.append('Unscheduled list mismatch')
    return {'valid': not errors, 'complete': not missing and not errors, 'errors': errors,
            'scheduled': len(assigned), 'unscheduled': missing,
            'conflict_scope': data['conflict_scope'], 'rest_basis': data['rest_basis']}


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
                placed[m['id']] = rec
                available_courts.remove(rec['court'])
        finish = {p: max((r['slot_index'] for r in placed.values() if r['project_id'] == p), default=-1)
                  if sum(r['project_id'] == p for r in placed.values()) == project_counts[p]
                  else len(slots) + len(matches) for p in order}
        # Actual finish time matters too when durations differ within a slot.
        end_times = {p: max((dt(r['end']) for r in placed.values() if r['project_id'] == p),
                            default=datetime.max)
                     if sum(r['project_id'] == p for r in placed.values()) == project_counts[p]
                     else datetime.max for p in order}
        finish_objectives = ((*(end_times[p] for p in priority), max(end_times.values()))
                             if objective == 'project_first' else
                             (max(end_times.values()), *(end_times[p] for p in priority)))
        score = (len(matches) - len(placed), *finish_objectives,
                 len({r['slot_index'] for r in placed.values()}), sum(finish.values()),
                 *(finish[p] for p in order))
        if best_key is None or score < best_key:
            best_key = score
            best = {'schema': 'gamemaster.schedule.v1', 'event_id': data['event_id'],
                    'input_sha256': hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
                    'algorithm': 'seeded-list-scheduling', 'objective': objective,
                    'attempt': attempt, 'attempts': attempts,
                    'optimality_proven': False, 'priority_order': order, 'slots': slots,
                    'assignments': sorted(placed.values(), key=lambda r: (r['slot_index'], r['court'])),
                    'unscheduled': sorted(matches.keys() - placed.keys())}
    best['validation'] = validate(data, best)
    best['status'] = 'complete' if best['validation']['complete'] else 'search_incomplete'
    return best


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    result = schedule(json.loads(args.input.read_text()))
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({'status': result['status'], **result['validation']}, ensure_ascii=False))
    raise SystemExit(0 if result['validation']['complete'] else 2)


if __name__ == '__main__':
    main()
