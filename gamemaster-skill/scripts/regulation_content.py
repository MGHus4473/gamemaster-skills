#!/usr/bin/env python3
"""Offline regulation/supplement content compiler. No inferred U-age or sporting rules.

Check structured facts before rendering; see references/regulation-content.md.
This verifies declared facts, not the truth of their sources or arbitrary prose.
"""
import argparse
import calendar
from copy import deepcopy
from datetime import date, datetime, timedelta
from hashlib import sha256
from itertools import combinations
import json
import math
from pathlib import Path
import re

from results_engine import validate_rule

UNITS = {'singles': '人', 'doubles': '对', 'team': '队'}
SPORTS = {'badminton': '羽毛球', 'table_tennis': '乒乓球', 'tennis': '网球', 'pickleball': '匹克球'}
POLICIES = {
    'eligibility': '参赛资格及资格核验', 'entry_limits': '跨组、兼项及搭档限制',
    'refunds': '退赛及退费办法', 'draw_schedule': '抽签及赛程公布',
    'check_in': '报到、检录及迟到起算', 'withdrawal': '弃权、退赛及成绩处理',
    'appeals': '异议提出及处理程序', 'safety': '安全、救助及联系安排',
    'changes': '变更通知及确认办法', 'equipment': '器材、用球及服装',
    'rule_basis': '适用竞赛规则的名称、版本及本届特殊办法',
}
IMPACTS = {'eligibility': '资格与兼项', 'fees_refunds': '费用与退费', 'schedule': '日期场地与赛程',
           'scoring': '计分与晋级', 'awards': '录取与奖励', 'draw': '名单、抽签与已赛成绩'}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def nonempty(value):
    return isinstance(value, str) and bool(value.strip()) and not re.search(r'【待确认|待定|TODO|XXX|\{\{', value, re.I)


def integer(value, minimum=0):
    return type(value) is int and value >= minimum


def day(value):
    require(isinstance(value, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', value), '须为YYYY-MM-DD完整日期')
    return date.fromisoformat(value)


def moment(value):
    require(isinstance(value, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}', value), '须为赛事当地时间YYYY-MM-DDTHH:MM')
    return datetime.fromisoformat(value)


def age_on(birth, reference, leap_day='march1'):
    birthday = (birth.month, birth.day)
    if birthday == (2, 29) and not calendar.isleap(reference.year) and leap_day == 'feb28':
        birthday = (2, 28)
    return reference.year - birth.year - ((reference.month, reference.day) < birthday)


def age_bounds(rule):
    require(isinstance(rule, dict), '须明确年龄口径或明确不限年龄')
    require(nonempty(rule.get('source')), '年龄条件须记录本届依据')
    mode = rule.get('mode')
    if mode == 'open':
        return None
    if mode == 'birth_range':
        start, end = day(rule.get('start')), day(rule.get('end'))
    elif mode in ('age_on_date', 'birth_year_age'):
        low, high = rule.get('min_age'), rule.get('max_age')
        require(integer(low) and integer(high) and low <= high <= 120, '年龄下限/上限须为0至120的整数闭区间')
        if mode == 'birth_year_age':
            year = rule.get('year')
            require(integer(year, 1900) and year <= 2200, '须明确计算出生年份年龄的年份')
            start, end = date(year-high, 1, 1), date(year-low, 12, 31)
        else:
            reference = day(rule.get('reference_date'))
            leap = rule.get('leap_day_rule')
            if (reference.month, reference.day) == (2, 28) and not calendar.isleap(reference.year):
                require(leap in ('feb28', 'march1'), '该基准日涉及闰日生日边界，须确认feb28或march1口径')
            require(leap in (None, 'feb28', 'march1'), '未知闰日生日口径')
            # Binary search monotone completed age, including February 29 boundaries.
            first, last = date(reference.year-high-1, 1, 1).toordinal(), reference.toordinal()+1
            def boundary(predicate):
                left, right = first, last
                while left < right:
                    mid = (left+right)//2
                    if predicate(age_on(date.fromordinal(mid), reference, leap or 'march1')):
                        right = mid
                    else:
                        left = mid+1
                return left
            start, end = date.fromordinal(boundary(lambda a: a <= high)), date.fromordinal(boundary(lambda a: a < low)-1)
    else:
        raise ValueError('年龄口径须为birth_range、age_on_date、birth_year_age或open；不能由U名称推算')
    require(start <= end, '出生日期区间倒置')
    if mode != 'birth_range' and ('start' in rule or 'end' in rule):
        require(day(rule.get('start')) == start and day(rule.get('end')) == end, '所填出生日期与声明年龄计算结果不一致')
    return start, end


def age_text(rule):
    bounds = age_bounds(rule)
    if bounds is None:
        return '不限年龄（按本届已确认资格条件执行）'
    start, end = bounds
    text = f'{cn_date(start.isoformat())}至{cn_date(end.isoformat())}出生，含首尾两日'
    if rule['mode'] == 'age_on_date':
        text += f"；截至{cn_date(rule['reference_date'])}已满{rule['min_age']}周岁、未满{rule['max_age']+1}周岁"
        if rule.get('leap_day_rule'):
            text += '；2月29日出生者非闰年生日按' + ('2月28日' if rule['leap_day_rule']=='feb28' else '3月1日') + '计算'
    if rule['mode'] == 'birth_year_age':
        text += f"；按{rule['year']}减出生年份计算为{rule['min_age']}至{rule['max_age']}岁，不按比赛日周岁计算"
    return text


def cn_date(value):
    d = day(value)
    return f'{d.year}年{d.month}月{d.day}日'


def cn_time(value):
    d = moment(value)
    return f'{cn_date(d.date().isoformat())}{d:%H:%M}'


def scoring_text(rule):
    validate_rule(rule)
    if rule['mode'] == 'team':
        return f"团体对抗先胜{rule['win_target']}场为胜；" + (f"全部{rule['rubber_count']}个子场须打满" if rule['play_all'] else '决出胜方即停止未开始子场')
    if rule['mode'] == 'points':
        prefix = '一局定胜负' if rule['best_of']==1 else f"{rule['best_of']}局{rule['best_of']//2+1}胜制"
        text = f"{prefix}，每局达到{rule['target']}分且至少领先{rule['win_by']}分者胜"
        text += (f"；{rule['cap']}分封顶，先到封顶分者即胜，不再要求领先分差" if rule.get('cap') is not None else '；不设封顶')
        if rule.get('initial_points'):
            text+='；每局起始比分（甲:乙）'+':'.join(map(str,rule['initial_points']))
        return text
    text = f"{rule['best_of']}盘{rule['best_of']//2+1}胜制，每盘先得{rule['games_to_win']}局且领先{rule['set_win_by']}局"
    text += '；无占先' if rule.get('no_ad') else '；有占先'
    text += f"；常规盘{rule['tiebreak_at']}平抢{rule['tiebreak_target']}，抢七至少领先2分" if rule.get('tiebreak_at') else '；常规盘不设抢七'
    if rule.get('match_tiebreak_target'):
        text += f"；决胜盘以抢{rule['match_tiebreak_target']}替代，至少领先2分"
    else:
        at = rule.get('final_tiebreak_at', rule.get('tiebreak_at'))
        text += f"；决胜盘{at}平抢{rule.get('final_tiebreak_target',rule['tiebreak_target'])}，至少领先2分" if at else '；决胜盘长盘'
    return text


def validate_shape(spec):
    """Reject unsupported fields and malformed containers before business checks.

    Missing business values remain reportable/draftable; invalid structures fail
    explicitly rather than being discarded during rendering.
    """
    def obj(value, keys, path):
        require(isinstance(value,dict), path+'须为对象')
        require(not set(value)-set(keys.split()), path+'含未知字段：'+','.join(sorted(set(value)-set(keys.split()))))
    def rows(parent,key,keys,path):
        value=parent.get(key,[])
        require(isinstance(value,list),path+'.'+key+'须为数组')
        for i,row in enumerate(value):obj(row,keys,f'{path}.{key}.{i}')
        return value
    obj(spec,'kind status event max_entries_per_person policies groups age_partitions extra_clauses base_document effective_at scope reason changes impacts response_window contact mapping affected_source_ids handicap subject recipients','root')
    obj(spec.get('event',{}),'name sport organizer issuer version published start end venue address contact registration_open registration_close registration_channel','event')
    obj(spec.get('policies',{}),' '.join(POLICIES)+' guardian','policies')
    obj(spec.get('base_document',{}),'title version published','base_document')
    obj(spec.get('impacts',{}),' '.join(IMPACTS),'impacts')
    for g in rows(spec,'groups','id name discipline sex age eligibility combination_rule min_entries insufficient_policy fee stages awards count_rules team','root'):
        require(isinstance(g.get('id',''),str),'group.id须为字符串')
        if g.get('age') is not None:obj(g['age'],'mode source start end reference_date year min_age max_age leap_day_rule u_policy label_note','age')
        for key,keys in [('fee','amount unit'),('awards','places bronze unit description placement_policy'),('team','roster lineup within_tie_limits subevents')]:
            obj(g.get(key,{}),keys,key)
        rows(g,'stages','name format entrants progression rules ranking group_sizes advance_per_group capacity_policy scoring_system','group')
        rows(g,'count_rules','min max action','group')
    for part in rows(spec,'age_partitions','groups overlap_policy','root'):
        require(isinstance(part.get('groups',[]),list) and all(isinstance(v,str)for v in part.get('groups',[])),'age_partitions.groups须为ID字符串数组')
    rows(spec,'extra_clauses','heading text','root')
    rows(spec,'changes','section before after','root')
    for row in rows(spec,'mapping','source_id source_name source_discipline action target_id target_name target_discipline','root'):
        require(all(isinstance(v,str)for v in row.values()),'mapping值须为字符串')
    ids=spec.get('affected_source_ids',[])
    require(isinstance(ids,list) and all(isinstance(v,str)for v in ids),'affected_source_ids须为ID字符串数组')
    hp=spec.get('handicap',{})
    obj(hp,'mode basis application pairs','handicap')
    for row in rows(hp,'pairs','a b initial rules','handicap'):
        require(isinstance(row.get('a',''),str) and isinstance(row.get('b',''),str),'handicap类别须为字符串')


def inspect(spec):
    validate_shape(spec)
    errors, warnings, normalized = [], [], {}
    def error(path, message): errors.append({'path':path,'message':message})
    def text(obj, key, path):
        if not nonempty(obj.get(key)): error(path+'.'+key, '缺少已确认的具体内容')
    def attempt(path, fn):
        try: return fn()
        except (ValueError, TypeError, KeyError, OverflowError) as exc: error(path,str(exc)); return None
    require(isinstance(spec,dict), '内容输入须为对象')
    kind=spec.get('kind'); event=spec.get('event',{}); policies=spec.get('policies',{})
    require(isinstance(event,dict) and isinstance(policies,dict), 'event/policies须为对象')
    if kind not in ('regulations','supplement'): error('kind','选择regulations或supplement')
    if spec.get('status') not in ('draft','final'): error('status','选择draft或final')
    for key in ('name','issuer','version'): text(event,key,'event')
    issued=attempt('event.published',lambda:day(event.get('published')))
    if kind=='regulations':
        for key in ('organizer','venue','address','contact','registration_channel'): text(event,key,'event')
        if event.get('sport') not in SPORTS: error('event.sport','须明确运动项目')
        start=attempt('event.start',lambda:day(event.get('start'))); end=attempt('event.end',lambda:day(event.get('end')))
        opened=attempt('event.registration_open',lambda:moment(event.get('registration_open')))
        closed=attempt('event.registration_close',lambda:moment(event.get('registration_close')))
        if start and end and end<start: error('event.end','结束日期早于开始日期')
        if opened and closed and closed<=opened: error('event.registration_close','报名截止须晚于开始')
        if closed and start and closed.date()>start: error('event.registration_close','报名晚于开赛；滚动报名需专项流程，不能默认为普通赛')
        if issued and end and issued>end: error('event.published','正式规程发布日期晚于比赛结束，须核实文种/日期')
        if not integer(spec.get('max_entries_per_person'),1): error('max_entries_per_person','须用每人最多报名几项，不能仅写可兼一项')
        for key in POLICIES: text(policies,key,'policies')
        groups=spec.get('groups',[])
        if not isinstance(groups,list) or not groups: error('groups','须列明每个项目及组别'); groups=[]
        ids=set()
        for g in groups:
            if not isinstance(g,dict): error('groups','组别须为对象'); continue
            gid=g.get('id'); path='groups.'+str(gid)
            if not nonempty(gid) or gid in ids: error(path,'组别ID缺失或重复')
            ids.add(gid); text(g,'name',path); text(g,'eligibility',path)
            discipline=g.get('discipline'); unit=UNITS.get(discipline)
            if not unit: error(path+'.discipline','选择singles/doubles/team')
            if g.get('sex') not in ('male','female','mixed','open'): error(path+'.sex','明确male/female/mixed/open')
            if discipline=='singles' and g.get('sex')=='mixed': error(path+'.sex','男女合并单打应为open；mixed表示混合组合')
            bounds=attempt(path+'.age',lambda:age_bounds(g.get('age')))
            if bounds: normalized[gid]={'start':bounds[0].isoformat(),'end':bounds[1].isoformat(),'text':age_text(g['age'])}
            labels=re.findall(r'(?i)U\s*0*(\d+)',str(g.get('name','')))
            if labels:
                age=g.get('age') or {}; policy=age.get('u_policy')
                if age.get('mode')=='open' or bounds is None: error(path+'.age','U组必须明确出生日期条件')
                if policy not in ('under','through','cohort'): error(path+'.age.u_policy','确认U表示未满、含该年龄上限或本届自定义年份组')
                if policy in ('under','through'):
                    expected=int(labels[0])-(policy=='under')
                    if len(labels)!=1 or age.get('mode') not in ('age_on_date','birth_year_age') or age.get('max_age')!=expected:
                        error(path+'.age.u_policy','U标签含义与年龄上限/计算口径不相符；复合自定义组使用cohort并解释')
                if policy=='cohort' and not nonempty(age.get('label_note')): error(path+'.age.label_note','自定义U组须说明名称与本届出生区间的关系')
            if bounds and start and age_on(bounds[1],start)<18 and not nonempty(policies.get('guardian')):
                error('policies.guardian','涉及未成年人：补充监护人同意、联系及到场安排')
            if discipline in ('doubles','team'): text(g,'combination_rule',path)
            if not integer(g.get('min_entries'),1): error(path+'.min_entries','明确最低开赛人/对/队数')
            text(g,'insufficient_policy',path)
            fee=g.get('fee',{})
            if not isinstance(fee,dict) or type(fee.get('amount')) not in (int,float) or not math.isfinite(fee['amount']) or fee['amount']<0 or fee.get('unit')!=unit:
                error(path+'.fee','费用须非负并按单打人、双打对、团体队明确计价；特殊计价另行说明并换算')
            stages=g.get('stages',[])
            if not isinstance(stages,list) or not stages: error(path+'.stages','明确赛制阶段'); stages=[]
            previous=None
            for i,stage in enumerate(stages):
                sp=path+f'.stages.{i}'
                if not isinstance(stage,dict): error(sp,'阶段须为对象');continue
                text(stage,'name',sp);text(stage,'progression',sp)
                if stage.get('format') not in ('round_robin','knockout'): error(sp+'.format','当前编译器支持循环/淘汰；其他赛制须扩展并核验')
                if stage.get('format')=='round_robin':text(stage,'ranking',sp)
                rule=stage.get('rules')
                attempt(sp+'.rules',lambda:validate_rule(rule))
                if isinstance(rule,dict):
                    expected='team' if discipline=='team' else 'tennis' if event.get('sport')=='tennis' else 'points'
                    if rule.get('mode')!=expected:error(sp+'.rules','计分层级与运动或团体类型不符')
                    if expected=='points' and 'cap' not in rule:error(sp+'.rules.cap','明确封顶分或null（不封顶）')
                    if expected=='tennis' and type(rule.get('no_ad')) is not bool:error(sp+'.rules.no_ad','明确有占先或无占先')
                    if event.get('sport')=='pickleball' and stage.get('scoring_system') not in ('side_out','rally'):
                        error(sp+'.scoring_system','匹克球须明确侧出得分或每球得分')
                size=stage.get('entrants'); sizes=stage.get('group_sizes'); advance=stage.get('advance_per_group')
                if size is not None and not integer(size,2):error(sp+'.entrants','阶段人数/对数/队数须至少2')
                if previous is not None and size!=previous:error(sp+'.entrants','下一阶段人数与上阶段晋级席位不一致')
                previous=None
                if sizes is not None:
                    if not isinstance(sizes,list) or not sizes or not all(integer(n,2) for n in sizes):error(sp+'.group_sizes','各循环小组人数至少2')
                    elif stage.get('format')!='round_robin':error(sp+'.group_sizes','淘汰阶段不使用循环小组容量')
                    else:
                        if size!=sum(sizes):error(sp+'.entrants','小组容量之和与阶段人数不符')
                        if i<len(stages)-1:
                            if not integer(advance,1) or advance>min(sizes):error(sp+'.advance_per_group','晋级数必须为每小组可提供的正整数')
                            else:previous=len(sizes)*advance
                elif (size is None or (stage.get('format')=='round_robin' and i<len(stages)-1)) and not nonempty(stage.get('capacity_policy')):
                    error(sp+'.capacity_policy','人数或晋级分组未定时须给人数触发方案、公布时点及渠道')
            awards=g.get('awards',{})
            if not isinstance(awards,dict): awards={}
            if not integer(awards.get('places')):error(path+'.awards.places','明确奖励名次范围，0表示不设奖励')
            if awards.get('bronze') not in ('playoff','joint','ranking','none'):error(path+'.awards.bronze','明确季军赛、并列第三、循环最终排名或不录取第三')
            if awards.get('bronze')=='joint' and awards.get('places',0) not in (3,):error(path+'.awards','并列第三不等于另决第4名；须明确排名体系')
            last_format=stages[-1].get('format') if stages and isinstance(stages[-1],dict) else None
            if awards.get('bronze') in ('playoff','joint') and last_format!='knockout':error(path+'.awards','季军赛/并列第三须与最终淘汰阶段对应')
            if awards.get('bronze')=='ranking' and last_format!='round_robin':error(path+'.awards','按循环排名须与最终循环阶段对应')
            if integer(awards.get('places'),3) and awards.get('bronze')=='none':error(path+'.awards','录取第三名及以上须明确第三名如何决出')
            text(awards,'description',path+'.awards')
            if awards.get('unit')!=unit:error(path+'.awards.unit','奖励计量单位与人/对/队不一致')
            final_size=stages[-1].get('entrants') if stages else None
            required_places=4 if awards.get('bronze')=='joint' else awards.get('places')
            if integer(final_size) and integer(required_places) and required_places>final_size and not nonempty(awards.get('placement_policy')):
                error(path+'.awards','录取范围超过最终阶段人数，须说明额外排名赛或其他名次来源')
            if integer(awards.get('places')) and awards['places']>4:text(awards,'placement_policy',path+'.awards')
            rules=g.get('count_rules',[]); next_min=1
            for i,row in enumerate(rules):
                if not isinstance(row,dict):error(path+'.count_rules','人数分支须为对象');continue
                lo,hi=row.get('min'),row.get('max')
                if lo!=next_min or not integer(lo,1) or (hi is not None and (not integer(hi,lo))):error(path+'.count_rules','人数区间有遗漏、重叠或倒置，须从1连续覆盖')
                if hi is None and i!=len(rules)-1:error(path+'.count_rules','无上限分支必须最后列出')
                next_min=hi+1 if integer(hi) else None;text(row,'action',path+'.count_rules')
            if rules and rules[-1].get('max') is not None:error(path+'.count_rules','须覆盖超过最后阈值的情况或明确无上限分支')
            if discipline=='team':
                team=g.get('team',{})
                if not isinstance(team,dict):team={}
                for key in ('roster','lineup','within_tie_limits','subevents'):text(team,key,path+'.team')
        for part in spec.get('age_partitions',[]):
            pids=part.get('groups',[])
            if not pids or len(pids)!=len(set(pids)) or not set(pids)<=normalized.keys():error('age_partitions','年龄分区须引用有效且不重复的有限年龄组');continue
            spans=sorted((day(normalized[g]['start']),day(normalized[g]['end']),g)for g in pids)
            covered_end=spans[0][1]
            for b in spans[1:]:
                if b[0]<=covered_end and not nonempty(part.get('overlap_policy')):error('age_partitions','声明同一分区的年龄组重叠，须明确跨组/择一等处理')
                if b[0]>covered_end+timedelta(days=1):error('age_partitions','声明连续覆盖的年龄分区有出生日期缺口')
                covered_end=max(covered_end,b[1])
    elif kind=='supplement':
        if 'subject' in spec:text(spec,'subject','supplement')
        if spec.get('recipients') is not None:text(spec,'recipients','supplement')
        base=spec.get('base_document',{})
        for key in ('title','version'):text(base,key,'base_document')
        original=attempt('base_document.published',lambda:day(base.get('published')))
        effective=attempt('effective_at',lambda:moment(spec.get('effective_at')))
        if issued and original and issued<original:error('base_document.published','补充通知不能早于所引用原规程的发布日')
        if issued and effective and effective.date()<issued:error('effective_at','生效日在发布日期之前，须单独核实追溯适用依据')
        for key in ('scope','reason','response_window','contact'):text(spec,key,'supplement')
        changes=spec.get('changes',[])
        if not isinstance(changes,list) or not changes:error('changes','补充通知须逐条说明原条款和新办法');changes=[]
        for i,c in enumerate(changes):
            for key in ('section','before','after'):text(c,key,f'changes.{i}')
        impacts=spec.get('impacts',{})
        for key in IMPACTS:text(impacts,key,'impacts')
        mapping=spec.get('mapping',[]);sources=set();targets={};target_names={}
        for i,row in enumerate(mapping):
            p=f'mapping.{i}'
            for key in ('source_id','source_name','source_discipline','action'):text(row,key,p)
            if row.get('source_id') in sources:error(p,'原组别重复映射')
            sources.add(row.get('source_id'))
            if row.get('action') not in ('merge','retain','cancel'):error(p+'.action','选择merge/retain/cancel')
            if row.get('source_discipline') not in UNITS:error(p+'.source_discipline','原项目类型须为singles/doubles/team')
            if row.get('action')!='cancel':
                for key in ('target_id','target_name','target_discipline'):text(row,key,p)
                if row.get('source_discipline')!=row.get('target_discipline'):error(p,'并组不能直接把单打名额变成双打组合；需另走名单转换')
                tid=row.get('target_id');targets.setdefault(tid,[]).append(row.get('source_id'))
                identity=(row.get('target_name'),row.get('target_discipline'))
                if tid in target_names and target_names[tid]!=identity:error(p,'同一目标项目ID的名称/类型不一致')
                target_names[tid]=identity
        if mapping:
            affected=spec.get('affected_source_ids',[])
            if len(affected)!=len(set(affected)) or set(affected)!=sources:error('affected_source_ids','受影响原项目清单与映射/取消项目不一致')
            hp=spec.get('handicap',{})
            if hp.get('mode') not in ('none','matrix'):error('handicap.mode','并组须明确不让分或完整让分对照，不能继承历史数值')
            text(hp,'basis','handicap');text(hp,'application','handicap')
            required={frozenset(pair) for members in targets.values() for pair in combinations(members,2)}; covered=set()
            for row in hp.get('pairs',[]):
                pair=frozenset((row.get('a'),row.get('b')))
                if pair not in required or pair in covered:error('handicap.pairs','让分对照有重复、未知或跨比赛项目的类别')
                covered.add(pair)
                rule=row.get('rules',{})
                if not isinstance(rule,dict) or rule.get('mode')!='points':error('handicap.pairs','当前让分检查只支持局分；其他玩法单独建模')
                else:attempt('handicap.pairs.initial',lambda:validate_rule(dict(rule,initial_points=row.get('initial'))))
            if hp.get('mode')=='matrix' and covered!=required:error('handicap.pairs','未覆盖合并项目内所有原资格类别的相遇情况（不让分也写0:0）')
            if hp.get('mode')=='none' and hp.get('pairs'):error('handicap','不让分模式不能同时给让分对照')
        elif spec.get('affected_source_ids') or spec.get('handicap',{}).get('pairs'):
            error('mapping','受影响项目或让分对照缺少原项目映射，不能丢弃这些信息')
    # Quoting an old defective clause in a correction notice is legitimate.
    review=deepcopy(spec)
    for change in review.get('changes',[]):change.pop('before',None)
    for value in all_strings(review):
        if re.search(r'最新(?:审定|颁布|发布)?(?:的)?[《规则]|最终解释权|一切后果自负|中午\s*22|每人限兼报',value):
            warnings.append('含模糊规则版本、解释/责任或时间/兼项表述，须人工核实：'+value[:70])
    for extra in spec.get('extra_clauses',[]):
        text(extra,'heading','extra_clauses');text(extra,'text','extra_clauses')
    return {'valid':not errors,'ready_for_final':not errors and not warnings,'errors':errors,'warnings':list(dict.fromkeys(warnings)),
            'age_groups':normalized,'source_sha256':sha256(json.dumps(spec,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),
            'scope':'结构字段、年龄边界、单位、计分、阶段容量及变更矩阵；不证明自由文本、来源真实性或官方规则适用性'}


def all_strings(value):
    if isinstance(value,str):yield value
    elif isinstance(value,dict):
        for item in value.values():yield from all_strings(item)
    elif isinstance(value,list):
        for item in value:yield from all_strings(item)


def show(value, label):
    return str(value) if value is not None and str(value).strip() else '【待确认：'+label+'】'


def compile_document(spec):
    audit=inspect(spec)
    if spec.get('status')=='final' and (audit['errors'] or audit['warnings']):
        raise ValueError('正式稿未通过内容审查：'+json.dumps(audit['errors']+audit['warnings'],ensure_ascii=False))
    e=spec.get('event',{});sections=[]
    def para(text):return {'type':'paragraph','text':text}
    def section(title, blocks):sections.append({'heading':title,'blocks':blocks})
    def safe_age(g):
        try:return age_text(g.get('age'))
        except (ValueError,TypeError,KeyError):return '【待确认：出生日期区间及计算口径】'
    def safe_rule(rule):
        try:return scoring_text(rule)
        except (ValueError,TypeError,KeyError):return '【待确认：局/盘/团体计分办法】'
    def formatted(obj,key,fn):
        try:return fn(obj.get(key))
        except (ValueError,TypeError,KeyError):return show(None,key)
    def table(headers,rows):return {'type':'table','headers':headers,'rows':rows or [['【待确认】']*len(headers)]}
    name=show(e.get('name'),'赛事名称'); supplement=spec.get('kind')=='supplement'
    if supplement:
        base=spec.get('base_document',{})
        section('一、制发依据与适用范围',[para(f"根据《{show(base.get('title'),'原规程名称')}》（{show(base.get('version'),'原版本')}，{formatted(base,'published',cn_date)}发布），因{show(spec.get('reason'),'调整原因')}，现就{show(spec.get('scope'),'适用项目及对象')}有关事项通知如下。")])
        section('二、调整事项',[table(['原条款','原办法','调整后办法'],[[show(c.get(k),k)for k in ('section','before','after')]for c in spec.get('changes',[])])])
        if spec.get('mapping'):
            section('三、项目调整及资格类别',[table(['原报名项目','处理方式','最终竞赛项目'],[[show(r.get('source_name'),'原项目'),{'merge':'并组','retain':'保留','cancel':'取消'}.get(r.get('action'),'【待确认】'),show(r.get('target_name'),'目标项目') if r.get('action')!='cancel' else '取消，后续处理见费用与退费条款']for r in spec['mapping']]),para('让分和资格识别保留原报名类别；最终项目名称不作为扩大原报名资格的依据。')])
            hp=spec.get('handicap',{})
            blocks=[para(show(hp.get('basis'),'让分或不让分的本届依据')),para(show(hp.get('application'),'适用局次、叠加、封顶及换边办法'))]
            if hp.get('mode')=='none':blocks.append(para('上述并组项目不实行让分。'))
            if hp.get('pairs'):
                labels={r['source_id']:r['source_name']for r in spec['mapping']}
                blocks.append(table(['甲方原类别','乙方原类别','每局起始比分（甲:乙）','计分办法'],[[labels.get(r.get('a'),'?'),labels.get(r.get('b'),'?'),':'.join(map(str,r.get('initial',[]))),safe_rule(r.get('rules'))]for r in hp['pairs']]))
            section('四、差异化计分办法',blocks)
        section('五、配套安排与办理要求',[table(['事项','本次执行办法'],[[title,show(spec.get('impacts',{}).get(key),title)]for key,title in IMPACTS.items()]),para('确认、退出及办理窗口：'+show(spec.get('response_window'),'处理时限、渠道及默认处理')),para('联系渠道：'+show(spec.get('contact'),'有效联系方式'))])
        section('六、生效与原规程关系',[para('本通知自'+formatted(spec,'effective_at',cn_time)+'起执行。仅调整本通知明确列明的事项，其余按所引用原规程执行。')])
        if spec.get('recipients'):
            sections[0]['blocks'].insert(0,para(str(spec['recipients']).rstrip('：:')+'：'))
        for i,part in enumerate(sections):
            part['heading']='一二三四五六'[i]+'、'+part['heading'].split('、',1)[1]
    else:
        p=spec.get('policies',{})
        section('一、组织单位',[para('主办或负责组织单位：'+show(e.get('organizer'),'组织单位'))])
        section('二、比赛时间与地点',[para('比赛时间：'+formatted(e,'start',cn_date)+'至'+formatted(e,'end',cn_date)+'。'),para('比赛地点：'+show(e.get('venue'),'场馆')+'；地址：'+show(e.get('address'),'可定位地址')+'。')])
        groups=[g for g in spec.get('groups',[]) if isinstance(g,dict)]
        section('三、竞赛项目与组别',[table(['组别/项目','类型与性别组成','出生日期及年龄口径','其他资格'],[[show(g.get('name'),'项目名称'),{'singles':'单打','doubles':'双打','team':'团体'}.get(g.get('discipline'),'【待确认】')+'；'+{'male':'男子','female':'女子','mixed':'混合组合','open':'不限性别'}.get(g.get('sex'),'【待确认】'),safe_age(g),show(g.get('eligibility'),'其他资格')]for g in groups])])
        eligibility=[para(show(p.get('eligibility'),'资格核验')),para(f"每名运动员最多报名{show(spec.get('max_entries_per_person'),'总项目数')}个项目。"),para(show(p.get('entry_limits'),'跨组兼项及搭档限制'))]
        for g in groups:
            if (g.get('age')or{}).get('label_note'):eligibility.append(para(show(g.get('name'),'项目')+'：'+g['age']['label_note']))
            if g.get('combination_rule'):
                composition={'male':'两名男运动员','female':'两名女运动员','mixed':'一名男运动员和一名女运动员','open':'两名运动员，性别组合不限'}.get(g.get('sex'),'【待确认：成员性别】')+'组成一对。' if g.get('discipline')=='doubles' else ''
                eligibility.append(para(show(g.get('name'),'项目')+'组合要求：'+composition+g['combination_rule']))
            if g.get('team'):
                eligibility.extend(para(show(g.get('name'),'项目')+'：'+show(g['team'].get(k),k))for k in ('roster','lineup','within_tie_limits','subevents'))
        if p.get('guardian'):eligibility.append(para(p['guardian']))
        section('四、参赛资格及参赛办法',eligibility)
        section('五、报名办法与费用',[para('报名时间：'+formatted(e,'registration_open',cn_time)+'至'+formatted(e,'registration_close',cn_time)+'。'),para('报名渠道及成功确认方式：'+show(e.get('registration_channel'),'报名渠道及确认')),para('联系人及有效联系渠道：'+show(e.get('contact'),'联系渠道')),table(['项目','报名费','最低开赛规模','不足规模处理'],[[show(g.get('name'),'项目'),show(g.get('fee',{}).get('amount'),'金额')+'元/'+show(g.get('fee',{}).get('unit'),'计价单位'),show(g.get('min_entries'),'开赛门槛')+UNITS.get(g.get('discipline'),'名额'),show(g.get('insufficient_policy'),'不足规模的确认方案')]for g in groups]),para(show(p.get('refunds'),'退费办法'))])
        stages=[]
        for g in groups:
            for s in g.get('stages',[]):
                info=show(s.get('progression'),'晋级或完赛办法')
                if s.get('entrants') is not None:info+=f"；本阶段{s['entrants']}{UNITS.get(g.get('discipline'),'名额')}"
                if s.get('group_sizes') is not None:info+='；各小组规模'+str(s['group_sizes'])
                if s.get('advance_per_group') is not None:info+=f"；每小组前{s['advance_per_group']}名晋级"
                if s.get('capacity_policy'):info+='；'+s['capacity_policy']
                if s.get('ranking'):info+='；排序：'+s['ranking']
                scoring=safe_rule(s.get('rules'))
                if s.get('scoring_system'):scoring+='；'+{'side_out':'侧出得分','rally':'每球得分'}.get(s['scoring_system'],'【待确认】')
                stages.append([show(g.get('name'),'项目'),show(s.get('name'),'阶段'),{'round_robin':'循环赛','knockout':'淘汰赛'}.get(s.get('format'),'【待确认】'),scoring,info])
        section('六、竞赛办法',[para(show(p.get('rule_basis'),'规则名称及版本')),table(['项目','阶段','赛制','计分','晋级与排名'],stages)])
        for g in groups:
            if g.get('count_rules'):sections[-1]['blocks'].append(table(['项目','规模（'+UNITS.get(g.get('discipline'),'名额')+'）','执行方案'],[[show(g.get('name'),'项目'),str(r.get('min'))+'至'+(str(r['max'])if r.get('max')is not None else '无上限'),show(r.get('action'),'人数触发办法')]for r in g['count_rules']]))
        section('七、抽签、赛程及检录',[para(show(p.get('draw_schedule'),'抽签和赛程公布')),para(show(p.get('check_in'),'检录与迟到起算')),para(show(p.get('withdrawal'),'异常参赛及成绩处理'))])
        section('八、录取名次与奖励',[table(['项目','录取范围','第三名处理','奖励及计量单位'],[[show(g.get('name'),'项目'),show(g.get('awards',{}).get('places'),'名次范围'),{'playoff':'设季军赛','joint':'并列第三','ranking':'按循环最终排名','none':'不录取第三名'}.get(g.get('awards',{}).get('bronze'),'【待确认】'),show(g.get('awards',{}).get('description'),'具体奖励')+'；按'+show(g.get('awards',{}).get('unit'),'单位')+'计'+('；'+g['awards']['placement_policy']if g.get('awards',{}).get('placement_policy')else '')]for g in groups])])
        section('九、器材、安全与异议处理',[para(show(p.get(k),POLICIES[k]))for k in ('equipment','safety','appeals')])
        section('十、变更与通知',[para(show(p.get('changes'),'变更通知办法'))])
    for extra in spec.get('extra_clauses',[]):section(show(extra.get('heading'),'附加条款标题'),[para(show(extra.get('text'),'附加条款内容'))])
    sections[-1]['blocks'] += [{'type':'paragraph','style':'issuer','text':show(e.get('issuer'),'发布单位')},{'type':'paragraph','style':'date','text':formatted(e,'published',cn_date)}]
    return {'title':('关于'+name+show(spec.get('subject','有关事项'),'通知事项')+'的补充通知') if supplement else name+'竞赛规程',
            'document_label':'补充通知' if supplement else '竞赛规程','subtitle':show(e.get('version'),'版本'),
            'status':spec.get('status','draft'),'pending':[x['path']+'：'+x['message']for x in audit['errors']]+audit['warnings'],
            'sections':sections},audit


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['check','build']);parser.add_argument('input',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();spec=json.loads(args.input.read_text(encoding='utf-8'))
    require(not args.output.exists(),'使用不存在的新输出路径')
    if args.action=='check':
        report=inspect(spec);args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2));return 0 if report['valid'] and not report['warnings'] else 2
    doc,report=compile_document(spec)
    from render_regulations import validate,markdown
    validate(doc);args.output.mkdir(parents=True)
    for name,value in [('document.json',doc),('content-review.json',report),('content-source.json',spec)]:
        (args.output/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    (args.output/'preview.md').write_text(markdown(doc,False),encoding='utf-8')
    print(json.dumps({'status':doc['status'],'content_valid':report['valid'],'output':str(args.output)},ensure_ascii=False));return 0


if __name__=='__main__':
    raise SystemExit(main())
