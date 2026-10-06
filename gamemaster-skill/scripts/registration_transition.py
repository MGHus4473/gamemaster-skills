"""报名与竞赛分离：应用确认方案、测算预留成本、替换名额、输出补充通知。"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from participant_roster import need, text, validate, summarize


def positive(value, label, minimum=1):
    need(type(value) is int and value >= minimum, label + '须为整数且不小于' + str(minimum))
    return value


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


def cost(count, config):
    """Count actual matches when every planned entry is filled; byes are not matches."""
    positive(count, '参赛单位数', 2)
    mode = config['format']
    classification = config.get('classification_places', 0)
    need(type(classification) is int and classification in (0, 8), '名次赛测算仅支持classification_places:8或0')
    if mode == 'round_robin':
        need(not classification, '单循环不附加淘汰名次赛')
        return {'matches': count * (count - 1) // 2, 'groups': [count]}
    if mode == 'knockout':
        bronze = config.get('bronze', False)
        need(type(bronze) is bool, 'bronze须为布尔值')
        need(not bronze or count >= 4, '三四名赛至少需要4个报名项')
        need(not classification or (count >= 8 and bronze), '决前8名须至少8个淘汰报名项且bronze:true')
        size = 1 << (count - 1).bit_length()
        return {'matches': count - 1 + int(bronze) + (4 if classification else 0), 'bracket_size': size,
                'byes': size - count, 'rounds': size.bit_length() - 1}
    if mode == 'groups_knockout':
        groups = positive(config['groups'], '组数')
        advance = positive(config['advance'], '每组晋级数')
        low, larger = divmod(count, groups)
        need(low >= 2 and low >= advance, '各组至少2项且人数不得少于晋级数')
        sizes = [low + 1] * larger + [low] * (groups - larger)
        playoffs = cost(groups * advance, {'format': 'knockout', 'bronze': config.get('bronze', False),
                                           'classification_places': classification})
        rr = sum(n * (n - 1) // 2 for n in sizes)
        return {'matches': rr + playoffs['matches'], 'groups': sizes,
                'group_matches': rr, 'playoff_matches': playoffs['matches'],
                'playoff_entries': groups * advance}
    raise ValueError('仅测算单循环、单淘汰及三四/前8名附加赛、均衡固定分组循环接淘汰')


def scenarios(real_count, config, maximum=3):
    positive(maximum, '最多预留数', 0)
    base = cost(real_count, config)
    return [{'real_entries': real_count, 'reserved_entries': k, 'planned_entries': real_count + k,
             **cost(real_count + k, config),
             'extra_matches': cost(real_count + k, config)['matches'] - base['matches']}
            for k in range(maximum + 1)]


def check_handicap(rule, entries):
    """matrix[A][B] > 0 means A receives these starting points against B."""
    need(rule.get('confirmed') is True, '让分方案须确认')
    for key in ('source', 'combination_policy', 'ends', 'serving', 'ranking'):
        need(text(rule.get(key)), '让分方案缺少' + key)
    need(rule.get('application') == 'each_game_initial_score', '脚本仅校验每局起始让分')
    need(isinstance(rule.get('stages'), list) and bool(rule['stages'])
         and all(text(s) for s in rule['stages']), '须明确让分适用阶段')
    target = positive(rule.get('target_points'), '目标分', 2)
    positive(rule.get('cap_points'), '封顶分', target)
    classes = rule.get('classes', [])
    need(bool(classes) and all(text(c) for c in classes) and len(set(classes)) == len(classes), '让分类别缺失或重复')
    assigned = rule.get('entry_classes', {})
    need(set(assigned) == {e['id'] for e in entries}, '让分类别须恰好覆盖该项目全部真实报名项')
    need(all(c in classes for c in assigned.values()), '报名项的让分类别未定义')
    matrix = rule.get('matrix', {})
    need(set(matrix) == set(classes) and all(set(matrix[c]) == set(classes) for c in classes),
         '让分矩阵须覆盖所有类别对，包括不让分的0')
    for a in classes:
        for b in classes:
            value = matrix[a][b]
            need(type(value) is int and abs(value) < target, '让分须为整数且绝对值小于目标分')
            need(value == -matrix[b][a] and (a != b or value == 0), '让分方向不互逆或同类不是0')
    # Pairwise handicaps are deliberately not required to be transitive/additive.


def apply_plan(registration, plan):
    validate(registration)
    need(plan.get('reviewed') is True and plan.get('unresolved') == [], '先确认本次并组、取消、资格及让分参数')
    need(text(plan.get('id')), '调整方案ID缺失')
    need(plan.get('source_version') == registration.get('version', 1), '来源报名版本已变化，须重新核对方案')
    need(plan.get('source_event_id') == registration.get('event_id'), '来源赛事不一致')
    need(plan.get('seed_policy') in ('clear', 'retain'), '须确认保留或清除原种子')
    source_projects = {p['key']: p for p in registration['projects']}
    targets = deepcopy(plan.get('projects', []))
    need(bool(targets), '没有最终竞赛项目')
    target_index = {p['key']: p for p in targets}
    need(len(target_index) == len(targets), '最终项目编号重复')
    routes, cancellations = {}, {}
    for p in targets:
        need(bool(p.get('source_keys')), '最终项目须注明来源组别')
        positive(p.get('min_actual'), '开赛真实报名项下限', 2)
        positive(p.get('reserve_count'), '预留名额数', 0)
        need(p['reserve_count'] <= 3 or p.get('extra_reserves_confirmed') is True,
             '通常预留1至3项，更多须明确确认')
        need(text(p.get('qualification_policy')), '须明确并组后的资格与年龄计算口径')
        need(p.get('handicap_mode') in ('none', 'matrix'), '须确认本项目让分方式（可明确不让分）')
        need(p['handicap_mode'] != 'none' or text(p.get('no_handicap_reason')), '不让分须记录确认依据')
        for key in p['source_keys']:
            need(key in source_projects and key not in routes, '来源组别不存在或被重复映射')
            routes[key] = p['key']
    for item in plan.get('cancelled', []):
        key = item['source_key']
        need(key in source_projects and key not in routes, '取消组别不存在或已映射')
        need(text(item.get('reason')) and text(item.get('handling')), '取消须记录原因及退费/转项等处理')
        routes[key] = None
        cancellations[key] = item
    need(set(routes) == set(source_projects), '每个原报名组别须明确保留、合并或取消，空组也不能遗漏')
    overrides = plan.get('entry_decisions', {})
    source_entries = {e['id']: e for e in registration['entries']}
    need(set(overrides).issubset(source_entries), '逐项调整引用了不存在的报名项')
    rows, ledger = [], []
    for original in registration['entries']:
        need(original.get('kind', 'real') == 'real', '来源须为真实报名；预留名额在调整方案中新增')
        source_key = original['project']
        destination = routes[source_key]
        decision = overrides.get(original['id'])
        reason = '按确认的组别映射'
        handling = ''
        if decision is not None:
            need(original['status'] == 'active', '已退赛项须先确认恢复，不能通过转项隐式恢复')
            need('target' in decision and text(decision.get('reason')), '逐项调整须有目标及原因')
            destination, reason = decision['target'], decision['reason']
            need(destination is None or destination in target_index, '逐项调整目标项目不存在')
            handling = decision.get('handling', '')
            need(destination is not None or text(handling), '取消报名项须明确处理办法')
        elif destination is None:
            reason, handling = cancellations[source_key]['reason'], cancellations[source_key]['handling']
        if original['status'] == 'withdrawn':
            action, destination = 'previously_withdrawn', None
        elif destination is None:
            action = 'cancelled'
        else:
            action = 'assigned'
            entry = deepcopy(original)
            entry['project'] = destination
            entry['origin'] = {'event_id': registration.get('event_id'),
                               'version': registration.get('version', 1), 'entry_id': original['id'],
                               'project': source_key, 'project_name': source_projects[source_key]['name'],
                               'project_type': source_projects[source_key]['type']}
            entry['source'] = original['source'] + '；调整方案：' + plan['id']
            if plan['seed_policy'] == 'clear':
                entry.pop('seed', None)
            rows.append(entry)
        ledger.append({'entry_id': original['id'], 'source_project': source_key,
                       'target_project': destination, 'action': action, 'reason': reason, 'handling': handling})
    handicaps = plan.get('handicaps', {})
    need(set(handicaps) == {p['key'] for p in targets if p['handicap_mode'] == 'matrix'}, '让分方案与项目设置不一致')
    for p in targets:
        real = [e for e in rows if e['project'] == p['key']]
        need(len(real) >= 2, p['name'] + '不足2个真实报名项，不能作为可开赛项目输出')
        need(len(real) >= p['min_actual'] or text(p.get('below_min_reason')),
             p['name'] + '未达真实开赛人数，预留名额不能凑足门槛；需调整或确认例外')
        if p['handicap_mode'] == 'matrix':
            check_handicap(handicaps[p['key']], real)
            for e in real:
                e['handicap_class'] = handicaps[p['key']]['entry_classes'][e['id']]
        p['expected_real_count'] = len(real)
        p['expected_count'] = len(real) + p['reserve_count']
        for number in range(1, p['reserve_count'] + 1):
            slot_id = f"reserve:{plan['id']}:{p['key']}:{number:02}"
            need(slot_id not in source_entries, '预留名额ID与来源记录冲突')
            rows.append({'id': slot_id, 'kind': 'placeholder', 'project': p['key'], 'status': 'active',
                         'label': f"预留名额-{p['name']}-{number:02}", 'members': [],
                         'source': '用户确认的调整方案：' + plan['id'],
                         'reservation': deepcopy(p.get('reserve_policy', {}))})
    roster = {'version': 1, 'event_id': plan.get('event_id'), 'reviewed': True, 'unresolved': [],
              'exclusive': registration['exclusive'], 'projects': targets, 'entries': rows,
              'handicaps': deepcopy(handicaps),
              'registration_origin': {'event_id': registration.get('event_id'),
                                      'version': registration.get('version', 1),
                                      'sha256': fingerprint(registration)},
              'transition_plan_id': plan['id'], 'transition_plan_sha256': fingerprint(plan)}
    validate(roster)  # Includes cross-group duplicate athletes created by a merger.
    return {'roster': roster, 'ledger': ledger, 'summary': summarize(roster),
            'plan': deepcopy(plan), 'source_projects': deepcopy(registration['projects'])}


def replace_reservation(roster, slot_id, replacement):
    validate(roster)
    out = deepcopy(roster)
    entry = next((e for e in out['entries'] if e['id'] == slot_id), None)
    need(entry is not None and entry.get('kind') == 'placeholder' and entry['status'] == 'active', '目标不是有效预留名额')
    need(text(replacement.get('source')) and text(replacement.get('registration_entry_id')), '须有真实报名ID和来源')
    need(replacement.get('eligibility_confirmed') is True, '先确认替换者资格及截止时间')
    # This helper does not decide whether an already drawn/started event may be changed.
    need(replacement.get('downstream_reviewed') is True, '先核对开赛状态、签位、单位回避及跨项编排影响')
    need(all(e.get('replacement_registration_id') != replacement['registration_entry_id'] and
             e.get('origin', {}).get('entry_id') != replacement['registration_entry_id']
             for e in out['entries']), '真实报名项已用于本竞赛，不能重复填充预留')
    before = deepcopy(entry)
    entry.update({'kind': 'real', 'members': deepcopy(replacement['members']), 'source': replacement['source'],
                  'replacement_registration_id': replacement['registration_entry_id']})
    entry.pop('label')
    entry['reservation']['filled'] = True
    p = next(p for p in out['projects'] if p['key'] == entry['project'])
    p['expected_real_count'] += 1
    if p['handicap_mode'] == 'matrix':
        rule = out['handicaps'][p['key']]
        category = replacement.get('handicap_class')
        need(category in rule['classes'], '须确认真实选手属于已定义的让分类别')
        entry['handicap_class'] = category
        rule['entry_classes'][slot_id] = category
        check_handicap(rule, [e for e in out['entries'] if e['project'] == p['key'] and e['status'] == 'active'
                             and e.get('kind', 'real') == 'real'])
    op = {'id': 'fill:' + slot_id, 'action': 'fill_reservation', 'source': replacement['source']}
    out.setdefault('history', []).append({'operation': op, 'before': before, 'after': deepcopy(entry)})
    validate(out)
    out['version'] = out.get('version', 1) + 1
    out['reviewed'] = False  # Re-export only after final roster / draw / schedule review.
    return out


def render_notice(result):
    plan = result['plan']
    validate(result['roster'])
    need(fingerprint(plan) == result['roster']['transition_plan_sha256'], '调整方案已改变，须重新生成对应名单与通知')
    need(result['summary'] == summarize(result['roster']), '通知人数汇总与名单不一致')
    notice = plan.get('notice', {})
    for key in ('title', 'base_version', 'version', 'effective_at', 'issuer', 'participation_deadline',
                'participation_handling', 'publication_channel'):
        need(text(notice.get(key)), '补充通知缺少' + key)
    names = {p['key']: p['name'] for p in result['source_projects']}
    projects = result['roster']['projects']
    for section in ('awards', 'format_changes', 'score_changes'):
        need(set(notice.get(section, {})) == {p['key'] for p in projects}
             and all(text(v) for v in notice[section].values()), '逐项目明确' + section)
    lines = ['# ' + notice['title'], '', '版本：' + notice['version'], '生效时间：' + notice['effective_at'], '',
             f"本通知调整《{notice['base_version']}》的以下事项，其余条款继续执行。", '', '## 组别与名额', '',
             '| 原报名组别 | 最终竞赛组别 | 真实报名项 | 预留名额 | 合计编排名额 |',
             '|---|---|---:|---:|---:|']
    for p in projects:
        stats = result['summary'][p['key']]
        unit = '人' if p['type'].endswith('S') else '对'
        lines.append(f"| {'、'.join(names[k] for k in p['source_keys'])} | {p['name']} | {stats['real_entries']}{unit} | {stats['reserved_entries']} | {stats['planned_entries']} |")
    for c in plan.get('cancelled', []):
        lines += ['', f"取消{names[c['source_key']]}：{c['reason']}。处理办法：{c['handling']}。"]
    if plan.get('entry_decisions'):
        lines += ['', '个别转项、退出按已确认的逐项变更清单执行；涉及个人信息的清单单独发送相关参赛者。']
    for p in projects:
        key = p['key']
        lines += ['', '## ' + p['name'], '', '资格：' + p['qualification_policy'],
                  '赛制与晋级：' + notice['format_changes'][key], '计分：' + notice['score_changes'][key],
                  '录取与奖励：' + notice['awards'][key]]
        if p.get('below_min_reason'):
            lines += ['低于常用开赛门槛的安排：' + p['below_min_reason']]
        if p['handicap_mode'] == 'none':
            lines += ['让分：不让分。依据：' + p['no_handicap_reason']]
        else:
            rule = result['roster']['handicaps'][key]
            lines += [f"让分适用于{'、'.join(rule['stages'])}，每局按下表比分开始；目标{rule['target_points']}分、封顶{rule['cap_points']}分。",
                      '', '| 类别甲 | 类别乙 | 每局起始比分（甲:乙） |', '|---|---|---|']
            for i, a in enumerate(rule['classes']):
                for b in rule['classes'][i:]:
                    amount = rule['matrix'][a][b]
                    lines.append(f'| {a} | {b} | {max(amount, 0)}:{max(-amount, 0)} |')
            lines += ['', '性别/年龄等规则组合：' + rule['combination_policy'], '间歇与换边：' + rule['ends'],
                      '发接发：' + rule['serving'], '排名与比分统计：' + rule['ranking']]
        if p['reserve_count']:
            policy = p['reserve_policy']
            lines += [f"预留{p['reserve_count']}个报名项，不计入真实开赛人数。替换截止：{policy['replacement_deadline']}。",
                      '预留资格：' + policy['eligibility'], '分配办法：' + policy['allocation'],
                      '逾期未填：' + policy['unfilled']]
    lines += ['', '## 参赛确认与发布', '', '确认/退出截止：' + notice['participation_deadline'],
              '接受变更、退出及费用处理：' + notice['participation_handling'],
              '公布渠道：' + notice['publication_channel'], '', notice['issuer'], '',
              '文件由确认的调整方案生成；发布状态单独记录。', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    a = sub.add_parser('apply'); a.add_argument('registration'); a.add_argument('plan'); a.add_argument('output')
    s = sub.add_parser('scenarios'); s.add_argument('input'); s.add_argument('output')
    r = sub.add_parser('replace'); r.add_argument('roster'); r.add_argument('slot_id'); r.add_argument('replacement'); r.add_argument('output')
    n = sub.add_parser('notice'); n.add_argument('result'); n.add_argument('output')
    args = parser.parse_args()
    read = lambda p: json.loads(Path(p).read_text(encoding='utf-8'))
    try:
        target = Path(args.output)
        need(not target.exists(), '输出已存在，请使用新版本路径')
        if args.command == 'apply':
            value = apply_plan(read(args.registration), read(args.plan))
        elif args.command == 'scenarios':
            data = read(args.input)
            value = scenarios(data['real_count'], data['config'], data.get('max_reserve', 3))
        elif args.command == 'replace':
            value = replace_reservation(read(args.roster), args.slot_id, read(args.replacement))
        else:
            value = render_notice(read(args.result))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
        print(str(target))
    except (ValueError, KeyError, TypeError) as exc:
        parser.exit(2, str(exc) + '\n')


if __name__ == '__main__':
    main()
