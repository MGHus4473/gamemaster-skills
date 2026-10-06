#!/usr/bin/env python3
"""Offline constrained draw. Standard library only; no platform calls."""
import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
import random

VERSION = '1.0'
# BWF 5.3.8, 19 February 2020, Tables 1–2. Values are draw positions.
BWF_BYES = {
  2: [], 3:[2], 4:[], 5:[2,4,7], 6:[2,7], 7:[2], 8:[],
  9:[2,4,6,8,11,13,15], 10:[2,4,6,11,13,15], 11:[2,4,6,11,15],
  12:[2,6,11,15], 13:[2,6,15], 14:[2,15], 15:[2], 16:[],
  17:[2,4,6,8,10,12,14,16,19,21,23,25,27,29,31],
  18:[2,4,6,8,10,12,14,19,21,23,25,27,29,31],
  19:[2,4,6,8,10,12,14,19,21,23,27,29,31],
  20:[2,4,6,10,12,14,19,21,23,27,29,31],
  21:[2,4,6,10,12,14,19,23,27,29,31],
  22:[2,4,6,10,14,19,23,27,29,31],
  23:[2,4,6,10,14,19,23,27,31], 24:[2,6,10,14,19,23,27,31],
  25:[2,6,10,14,23,27,31], 26:[2,6,10,23,27,31],
  27:[2,6,10,23,31], 28:[2,10,23,31], 29:[2,10,31],
  30:[2,31], 31:[2], 32:[],
}


class DrawError(ValueError):
    pass


class SearchLimit(DrawError):
    pass


def require(condition, message):
    if not condition:
        raise DrawError(message)


def digest(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(',', ':')).encode()).hexdigest()


def seed_domains(size, ranks):
    """BWF-style tiers: 1 at top, 2 at bottom; remaining unoccupied sections."""
    require(size >= 2 and size & (size - 1) == 0, '签位必须为不小于2的2次幂')
    domains = {1: [1], 2: [size]}
    occupied = {1, size}
    tier = 4
    while tier <= size:
        width = size // tier
        taken = {(p - 1) // width for p in occupied}
        positions = [i * width + 1 if i < tier // 2 else (i + 1) * width
                     for i in range(tier) if i not in taken]
        for rank in range(tier // 2 + 1, tier + 1):
            domains[rank] = positions
        occupied.update(positions)
        tier *= 2
    require(all(r in domains for r in ranks), '种子号超出签位范围')
    return {r: domains[r] for r in ranks}


def prepare(project):
    sport = project.get('sport')
    require(sport is None or sport in ('badminton', 'table_tennis', 'tennis', 'pickleball'),
            '未知运动类型；使用badminton/table_tennis/tennis/pickleball')
    entries = sorted(project['entries'], key=lambda e: str(e['id']))
    n = len(entries)
    require(n >= 2, '每个抽签项目至少需要两个报名项')
    require(len({str(e['id']) for e in entries}) == n, '报名项ID重复')
    for e in entries:
        require(isinstance(e['id'], str) and bool(e['id']), '报名项ID必须为非空字符串')
        require(isinstance(e.get('club', ''), str), 'club须为单一明确回避单位；跨单位双打请先明确政策')
        require(type(e.get('seed', 0)) is int and e.get('seed', 0) >= 0, '种子号必须为非负整数')
    ranks = sorted(e.get('seed', 0) for e in entries if e.get('seed', 0))
    require(ranks == list(range(1, len(ranks) + 1)), '种子号须唯一且从1连续编号')
    kind = project['format']
    if kind == 'knockout':
        if sport is not None and sport != 'badminton':
            require(isinstance(project.get('seed_profile'), str) and bool(project['seed_profile']),
                    '非羽毛球项目须显式指定seed_profile，并提供本场确认的种子/轮空配置')
            require(project['seed_profile'] != 'badminton_bwf',
                    '非羽毛球项目不能套用badminton_bwf；使用custom及本场确认的seed_positions/byes')
        size = project.get('bracket_size', 1 << (n - 1).bit_length())
        require(type(size) is int and size >= n and size >= 2 and size & (size - 1) == 0,
                '签位数量不合法')
        require(size == 1 << (n - 1).bit_length(),
                '当前离线对阵使用最小2次幂签表；更大特殊签表须另行适配')
        if 'byes' in project:
            byes = project['byes']
        elif n == size:
            byes = []
        else:
            require(project.get('seed_profile', 'badminton_bwf') == 'badminton_bwf'
                    and n in BWF_BYES and size == 1 << (n - 1).bit_length(),
                    '该人数/运动配置需明确提供轮空位置，不自动套用未核验规则')
            byes = BWF_BYES[n]
        require(all(type(p) is int and 1 <= p <= size for p in byes), '轮空位置越界')
        require(len(set(byes)) == len(byes) == size - n, '轮空数量不匹配或重复')
        require(all(not ({p, p + 1} <= set(byes)) for p in range(1, size, 2)),
                '首轮双方均为空，须明确更小签位或特殊轮空规则')
        slots = [p for p in range(1, size + 1) if p not in byes]
        labels = {p: {'group': 1, 'position': p} for p in slots}
        tiers = project.get('seed_positions')
        if tiers is None:
            require(project.get('seed_profile', 'badminton_bwf') == 'badminton_bwf',
                    '该种子规则需提供seed_positions；不跨运动默认套用')
            tiers = seed_domains(size, ranks)
        else:
            tiers = {int(r): positions for r, positions in tiers.items()}
        levels = project.get('balance_levels')
        if levels is None:
            levels = []
            g = 2
            while g <= size // 2:
                levels.append(g)
                g *= 2
        require(len(levels) == len(set(levels)), '分区层级重复')
        require(all(type(g) is int and g >= 2 and g <= size // 2 and g & (g - 1) == 0
                    for g in levels), '淘汰分区层级必须为2次幂且不超过签位数的一半')
        regions = {g: {p: (p - 1) // (size // g) for p in slots} for g in levels}
        num_regions = {g: g for g in levels}
        domains = []
        for e in entries:
            seed = e.get('seed', 0)
            require(not seed or seed in tiers, f'缺少{seed}号种子规则')
            allowed = set(tiers[seed]) if seed else set(slots)
            if 'position' in e:
                allowed &= {e['position']}
            domains.append(allowed & set(slots))
        meta = {'bracket_size': size, 'byes': sorted(byes), 'seed_domains': tiers}
    elif kind == 'groups':
        sizes = project['group_sizes']
        require(sizes and all(type(s) is int and s > 0 for s in sizes) and sum(sizes) == n,
                '小组容量之和必须等于人数，且每组容量为正整数')
        require(project.get('seed_policy', 'snake') == 'snake', '当前分组种子支持snake；其它规则需配置实现')
        labels = {}
        for g, count in enumerate(sizes, 1):
            for p in range(1, count + 1):
                labels[len(labels) + 1] = {'group': g, 'position': p}
        slots = list(labels)
        group_count = len(sizes)
        regions = {'groups': {p: labels[p]['group'] - 1 for p in slots}}
        num_regions = {'groups': group_count}
        domains = []
        for e in entries:
            allowed = set(slots)
            if e.get('seed', 0):
                wave, offset = divmod(e['seed'] - 1, group_count)
                group = offset + 1 if wave % 2 == 0 else group_count - offset
                allowed &= {s for s, loc in labels.items()
                            if loc == {'group': group, 'position': wave + 1}}
            if 'group' in e:
                allowed &= {s for s, loc in labels.items() if loc['group'] == e['group']}
            if 'position' in e:
                allowed &= {s for s, loc in labels.items() if loc['position'] == e['position']}
            domains.append(allowed)
        meta = {'group_sizes': sizes, 'seed_policy': 'snake'}
    else:
        raise DrawError('当前支持knockout及groups；晋级交叉需先显式给定席位约束')
    require(all(domains), '种子/固定签位与轮空、容量或位置范围冲突')
    return entries, slots, labels, regions, num_regions, domains, meta


def solve_project(project, random_seed, node_limit=200000):
    entries, slots, labels, regions, num_regions, domains, meta = prepare(project)
    rng = random.Random(digest([VERSION, random_seed, project['id'], project]))
    clubs = [e.get('club', '').strip() for e in entries]
    totals = Counter(c for c in clubs if c)
    counts = {c: {g: [0] * num_regions[g] for g in regions} for c in totals}
    bounds = {c: {g: (totals[c] // num_regions[g], (totals[c] + num_regions[g] - 1) // num_regions[g])
                  for g in regions} for c in totals}
    assigned = {}
    free = set(slots)
    nodes = 0
    entry_priority = list(range(len(entries)))
    rng.shuffle(entry_priority)
    priority = {e: i for i, e in enumerate(entry_priority)}
    candidate_order = {}
    for i in range(len(entries)):
        order = sorted(domains[i]); rng.shuffle(order)
        candidate_order[i] = {slot: k for k, slot in enumerate(order)}

    def candidates(i):
        club = clubs[i]
        return [s for s in domains[i] & free if not club or
                all(counts[club][g][regions[g][s]] < bounds[club][g][1] for g in regions)]

    def feasible(ds):
        # Lower bounds must remain achievable; capacity checks detect seed/club conflicts early.
        for club in totals:
            remaining = [i for i in ds if clubs[i] == club]
            for g in regions:
                low, high = bounds[club][g]
                needs = [max(0, low - k) for k in counts[club][g]]
                if sum(needs) > len(remaining):
                    return False
                for region, need in enumerate(needs):
                    if need and sum(any(regions[g][s] == region for s in ds[i]) for i in remaining) < need:
                        return False
        return True

    def search():
        nonlocal nodes
        nodes += 1
        if nodes > node_limit:
            raise SearchLimit(f'搜索达到{node_limit}节点上限；尚未找到解，不代表已证明无解')
        if len(assigned) == len(entries):
            return all(all(low <= k <= high for k in counts[c][g])
                       for c in totals for g, (low, high) in bounds[c].items())
        ds = {i: candidates(i) for i in range(len(entries)) if i not in assigned}
        if any(not d for d in ds.values()) or not feasible(ds):
            return False
        i = min(ds, key=lambda x: (len(ds[x]), -totals.get(clubs[x], 0), priority[x]))
        club = clubs[i]
        def key(s):
            return tuple(counts[club][g][regions[g][s]] for g in regions) + (candidate_order[i][s],) if club else (candidate_order[i][s],)
        for slot in sorted(ds[i], key=key):
            assigned[i] = slot; free.remove(slot)
            if club:
                for g in regions:
                    counts[club][g][regions[g][slot]] += 1
            if search():
                return True
            if club:
                for g in regions:
                    counts[club][g][regions[g][slot]] -= 1
            free.add(slot); del assigned[i]
        return False

    require(search(), '种子/固定签位/容量与单位均匀分布约束无可行解；未自动放宽')
    assignments = [{'entry_id': e['id'], 'name': e.get('name', ''), 'club': e.get('club', ''),
                    'seed': e.get('seed', 0), **labels[assigned[i]]}
                   for i, e in enumerate(entries)]
    assignments.sort(key=lambda a: (a['group'], a['position']))
    result = {'project_id': project['id'], 'name': project.get('name', project['id']),
              'format': project['format'], **meta, 'assignments': assignments,
              'search_nodes': nodes, 'balance_policy': 'hard_floor_ceil_each_region',
              'unit_definition': 'exact_club_string; empty club has no separation constraint'}
    if 'sport' in project:
        result['sport'] = project['sport']
    result['validation'] = validate_project(project, result)
    return result


def validate_project(project, result):
    entries, slots, labels, regions, nums, domains, meta = prepare(project)
    require(result['project_id'] == project['id'] and result['format'] == project['format'], '结果项目或赛制不符')
    for key in ('byes', 'bracket_size', 'group_sizes'):
        if key in meta:
            require(result.get(key) == meta[key], f'结果{key}与输入规则不一致')
    rows = result['assignments']
    require(len(rows) == len(entries), '输出报名项数量不符')
    by_id = {r['entry_id']: r for r in rows}
    require(set(by_id) == {e['id'] for e in entries}, '输出重复或遗漏报名项')
    loc_to_slot = {(v['group'], v['position']): s for s, v in labels.items()}
    taken = []
    unit_positions = defaultdict(list)
    for i, e in enumerate(entries):
        a = by_id[e['id']]
        require(a['seed'] == e.get('seed', 0) and a['club'] == e.get('club', '')
                and a['name'] == e.get('name', ''), '姓名/种子/单位属性改变')
        loc = (a['group'], a['position'])
        require(loc in loc_to_slot, '输出位置越界或占用轮空')
        s = loc_to_slot[loc]
        require(s in domains[i], f"报名项{e['id']}违反种子或固定位置约束")
        taken.append(s)
        if e.get('club', '').strip():
            unit_positions[e['club'].strip()].append(s)
    require(len(set(taken)) == len(taken) and set(taken) == set(slots), '签位重复或遗漏')
    report = {}
    for club, positions in sorted(unit_positions.items()):
        report[club] = {}
        for g in regions:
            values = [sum(regions[g][s] == r for s in positions) for r in range(nums[g])]
            require(max(values) - min(values) <= 1, f'{club}在{g}分区未均匀分布')
            report[club][str(g)] = values
    return {'passed': True, 'entrants': len(entries), 'seeds': sum(bool(e.get('seed')) for e in entries),
            'unique_slots': True, 'seed_positions_valid': True, 'all_units_balanced': True,
            'unit_distribution': report}


def generate(config):
    require('random_seed' in config and str(config['random_seed']), '须先记录random_seed，禁止隐式反复重抽')
    require(len({p['id'] for p in config['projects']}) == len(config['projects']), '项目ID重复')
    return {'schema': 'gamemaster.draw.v1', 'engine_version': VERSION,
            'event_id': config.get('event_id', ''), 'input_sha256': digest(config),
            'random_seed': config['random_seed'], 'test_seeds': config.get('test_seeds', False),
            'projects': [solve_project(p, config['random_seed'], config.get('node_limit', 200000)) for p in config['projects']]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    config = json.loads(args.input.read_text(encoding='utf-8'))
    result = generate(config)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'projects': len(result['projects']), 'entrants': sum(len(p['assignments']) for p in result['projects']), 'passed': True}, ensure_ascii=False))


if __name__ == '__main__':
    main()
