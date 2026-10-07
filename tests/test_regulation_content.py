"""Synthetic content cases; never include actual events, entrants or accounts."""
from copy import deepcopy
from datetime import date,timedelta
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'gamemaster-skill/scripts'))
import regulation_content as content
import render_regulations as render


def fixture():
    return {'kind':'regulations','status':'final','event':{
        'name':'合成青少年公开赛','sport':'badminton','organizer':'合成赛事组织单位','issuer':'合成赛事组委会',
        'version':'合成验收v1','published':'2030-06-01','start':'2030-07-01','end':'2030-07-02',
        'venue':'合成体育馆','address':'合成测试区域一号场馆','contact':'合成报名服务台',
        'registration_open':'2030-06-02T09:00','registration_close':'2030-06-20T18:00',
        'registration_channel':'合成报名表交服务台，收到书面审核及缴费确认后报名成功'},
        'max_entries_per_person':2,'policies':{
        'eligibility':'参赛者按项目出生区间报名，服务台于报名截止前核验出生证明；不公开证件资料。',
        'entry_limits':'每人单打、双打各最多一项；不得跨年龄组重复报名。',
        'refunds':'报名截止前可向服务台申请全额退款；因取消或并组选择退出的，于通知后两日内申请，确认后七日内退还。',
        'draw_schedule':'6月25日由组委会随机抽签，不设种子；签表及日程同日在服务台公告。',
        'check_in':'提前20分钟检录；迟到从公布或延后调整的实际开赛时间起算，超过10分钟由裁判长按已确认办法处理。',
        'withdrawal':'伤退保留已得分，未赛场次状态单列；循环退出后的排序按合成排序附件执行。',
        'appeals':'资格异议于开赛前向服务台书面提出；竞赛异议在下一次发球前向当值裁判提出，并由裁判长处理。',
        'safety':'现场服务台负责紧急联系和中止比赛，必要时联系当地急救；不承诺未落实的医疗人员。',
        'changes':'重大调整由组委会书面公告并通知报名联系人，受影响人员在通知载明窗口内确认或退出。',
        'equipment':'场馆提供合成测试用球，选手自备球拍和适用室内鞋。',
        'rule_basis':'本合成验收采用已确认的测试规则附件v1，仅用于测试，不声称为协会官方规则。',
        'guardian':'未成年参赛者须由监护人书面同意并提供紧急联系渠道，比赛期间由监护人或指定成年人陪同。'},
        'groups':[{'id':'G1','name':'U10男子单打','discipline':'singles','sex':'male',
          'age':{'mode':'birth_year_age','year':2030,'min_age':8,'max_age':10,'u_policy':'cohort',
                 'label_note':'本届U10为8至10出生年份年龄组，按表列出生日期确定资格。','source':'合成参数指定'},
          'eligibility':'符合年龄的男性参赛者；不设单位限制。','min_entries':8,
          'insufficient_policy':'不足8人先征询并组；不同意并组的可按确认窗口退出退费。',
          'fee':{'amount':100,'unit':'人'},
          'stages':[{'name':'第一阶段','format':'round_robin','entrants':8,'group_sizes':[4,4],
            'advance_per_group':2,'progression':'各组前两名进入淘汰赛，组间交叉对阵，不重新抽签。',
            'ranking':'按胜次排序；两人同分先看相互胜负，多人同分按相互净胜局、净胜分，再按合成附件同分程序处理。',
            'rules':{'mode':'points','best_of':1,'target':21,'win_by':1,'cap':21}},
            {'name':'第二阶段','format':'knockout','entrants':4,'progression':'半决赛胜者争夺冠亚军，负者进行季军赛。',
             'rules':{'mode':'points','best_of':3,'target':21,'win_by':2,'cap':30}}],
          'awards':{'places':3,'bronze':'playoff','unit':'人','description':'前3名各颁证书一份；不设现金奖励。'}}],
        'age_partitions':[],'extra_clauses':[]}


def supplement():
    return {'kind':'supplement','status':'final','event':{'name':'合成青少年公开赛','issuer':'合成赛事组委会',
            'published':'2030-06-22','version':'补充通知v1'},
            'base_document':{'title':'合成青少年公开赛竞赛规程','version':'合成验收v1','published':'2030-06-01'},
            'effective_at':'2030-06-22T12:00','scope':'两个合成单打报名项目','reason':'实际报名不足最低规模',
            'changes':[{'section':'第三部分项目表','before':'两个原项目分别比赛','after':'两个项目合并比赛，原年龄和性别资格保留用于让分识别'}],
            'impacts':{'eligibility':'仅合并既有合格报名项，不扩大原报名资格；兼项上限不变。',
             'fees_refunds':'不同意并组者在确认窗口内退出，核实后七日内全额退费。',
             'schedule':'日期场馆维持原规程；新赛程于6月25日服务台公告。',
             'scoring':'一局21分，先到21分者胜，不加分；按本通知表列起始比分执行。',
             'awards':'合并项目决出前3名，各颁证书一份。',
             'draw':'重新抽签；尚未开赛，无既有成绩需迁移。'},
            'response_window':'6月24日18:00前向服务台书面确认或申请退出，未确认者由服务台逐一联系，不默认接受。',
            'contact':'合成报名服务台','affected_source_ids':['A','B'],
            'mapping':[{'source_id':'A','source_name':'原甲组男子单打','source_discipline':'singles','action':'merge',
                        'target_id':'C','target_name':'合成混合单打','target_discipline':'singles'},
                       {'source_id':'B','source_name':'原乙组女子单打','source_discipline':'singles','action':'merge',
                        'target_id':'C','target_name':'合成混合单打','target_discipline':'singles'}],
            'handicap':{'mode':'matrix','basis':'仅按本合成赛双方确认的起始比分表执行。',
             'application':'每局适用，不叠加；仍以21分封顶，换边按本合成附件计入起始分。',
             'pairs':[{'a':'A','b':'B','initial':[0,3],'rules':{'mode':'points','best_of':1,'target':21,'win_by':1,'cap':21}}]}}


class ContentTests(unittest.TestCase):
    def check_error(self,spec,substring):
        report=content.inspect(spec)
        self.assertFalse(report['valid'])
        self.assertIn(substring,json.dumps(report,ensure_ascii=False))
        with self.assertRaises(ValueError):content.compile_document(spec)

    def test_complete_regulation_renders_exact_birth_dates(self):
        spec=fixture(); doc,audit=content.compile_document(spec);render.validate(doc)
        self.assertTrue(audit['valid']);body=render.markdown(doc,False)
        self.assertIn('2020年1月1日至2022年12月31日',body)
        self.assertIn('每名运动员最多报名2个项目',body)
        self.assertIn('合成赛事组委会',body)

    def test_u_label_alone_is_not_a_birth_rule(self):
        spec=fixture();spec['groups'][0]['age']={'source':'合成输入仅给U10'}
        self.check_error(spec,'不能由U名称推算')

    def test_under7_differs_from_through7(self):
        rule={'mode':'age_on_date','reference_date':'2030-07-01','min_age':0,'max_age':6,'source':'合成确认'}
        a,b=content.age_bounds(rule)
        self.assertEqual(a,date(2023,7,2));self.assertEqual(b,date(2030,7,1))
        rule['max_age']=7;self.assertEqual(content.age_bounds(rule)[0],date(2022,7,2))

    def test_u_policy_wrong_upper_bound_fails(self):
        s=fixture();s['groups'][0]['age']['u_policy']='under';self.check_error(s,'不相符')

    def test_u7_and_u10_explicit_adjacent_cohorts(self):
        s=fixture();a=s['groups'][0];b=deepcopy(a);b.update(id='G2',name='U7男子单打')
        b['age'].update(min_age=7,max_age=7,label_note='本届U7仅指2030减出生年等于7的年份组')
        s['groups'].append(b);s['age_partitions']=[{'groups':['G1','G2']}]
        report=content.inspect(s);self.assertTrue(report['valid'],report)
        self.assertEqual(report['age_groups']['G2']['start'],'2023-01-01')

    def test_calendar_year_is_not_birthday_age(self):
        r={'mode':'birth_year_age','year':2030,'min_age':7,'max_age':7,'source':'合成确认'}
        self.assertEqual(content.age_bounds(r),(date(2023,1,1),date(2023,12,31)))
        self.assertIn('不按比赛日周岁',content.age_text(r))

    def test_leap_day_boundary_requires_choice_and_changes_result(self):
        r={'mode':'age_on_date','reference_date':'2025-02-28','min_age':0,'max_age':0,'source':'合成确认'}
        with self.assertRaises(ValueError):content.age_bounds(r)
        r['leap_day_rule']='march1';self.assertEqual(content.age_bounds(r)[0],date(2024,2,29))
        r['leap_day_rule']='feb28';self.assertEqual(content.age_bounds(r)[0],date(2024,3,1))

    def test_date_boundary_one_day_outside(self):
        r={'mode':'age_on_date','reference_date':'2030-07-01','min_age':8,'max_age':10,'source':'合成确认'}
        a,b=content.age_bounds(r);ref=date(2030,7,1)
        self.assertEqual(content.age_on(a,ref),10);self.assertEqual(content.age_on(a-timedelta(days=1),ref),11)
        self.assertEqual(content.age_on(b,ref),8);self.assertEqual(content.age_on(b+timedelta(days=1),ref),7)

    def test_birth_dates_cannot_contradict_age_calculation(self):
        s=fixture();s['groups'][0]['age'].update(start='2021-01-01',end='2022-12-31');self.check_error(s,'不一致')

    def test_reversed_birth_range(self):
        with self.assertRaisesRegex(ValueError,'倒置'):
            content.age_bounds({'mode':'birth_range','source':'合成','start':'2025-01-01','end':'2024-12-31'})

    def test_partitions_detect_gap_and_overlap(self):
        s=fixture();a=deepcopy(s['groups'][0]);a.update(id='G2',name='U7男子单打');a['age'].update(min_age=7,max_age=7)
        s['groups'].append(a);s['age_partitions']=[{'groups':['G1','G2']}]
        a['age'].update(min_age=6,max_age=6);self.check_error(s,'缺口')
        a['age'].update(min_age=7,max_age=8);self.check_error(s,'重叠')
        s['age_partitions'][0]['overlap_policy']='合成确认允许符合两组者择一报名';self.assertTrue(content.inspect(s)['valid'])

    def test_doubles_units_and_composition(self):
        s=fixture();g=s['groups'][0];g.update(discipline='doubles',sex='mixed',name='U10混合双打',combination_rule='两名成员均须符合本组出生区间，搭档固定。')
        self.check_error(s,'费用须')
        g['fee']['unit']='对';g['awards']['unit']='对'
        doc,_=content.compile_document(s);self.assertIn('一名男运动员和一名女运动员',render.markdown(doc,False))

    def test_open_singles_not_mixed_doubles(self):
        s=fixture();s['groups'][0]['sex']='mixed';self.check_error(s,'合并单打')

    def test_guardian_required_for_youth(self):
        s=fixture();del s['policies']['guardian'];self.check_error(s,'未成年人')

    def test_count_seven_gap_and_eight_overlap(self):
        s=fixture();s['groups'][0]['count_rules']=[{'min':1,'max':6,'action':'取消'},{'min':8,'max':None,'action':'开赛'}]
        self.check_error(s,'遗漏')
        s['groups'][0]['count_rules'][0]['max']=8;self.check_error(s,'重叠')

    def test_promotion_capacity(self):
        s=fixture();s['groups'][0]['stages'][1]['entrants']=8;self.check_error(s,'晋级席位')

    def test_cap_and_majority(self):
        s=fixture();s['groups'][0]['stages'][0]['rules']['cap']=15;self.check_error(s,'cap below')
        s=fixture();s['groups'][0]['stages'][0]['rules']['best_of']=2;self.check_error(s,'odd')

    def test_bronze_not_both_joint_and_fourth(self):
        s=fixture();s['groups'][0]['awards'].update(places=4,bronze='joint');self.check_error(s,'另决第4名')

    def test_ambiguous_version_blocks_final(self):
        s=fixture();s['policies']['rule_basis']='执行最新审定的《羽毛球竞赛规则》'
        self.assertTrue(content.inspect(s)['warnings'])
        with self.assertRaises(ValueError):content.compile_document(s)

    def test_draft_retains_pending_without_fabricating_values(self):
        s=fixture();s['status']='draft';s['groups'][0]['age']={'source':'仅给名称'}
        doc,audit=content.compile_document(s);render.validate(doc)
        self.assertEqual(doc['status'],'draft');self.assertTrue(doc['pending']);self.assertFalse(audit['valid'])
        self.assertIn('待确认：出生日期',render.markdown(doc,False))

    def test_blank_starter_is_real_draft(self):
        for name in ['regulation-content-template.json','supplement-content-template.json']:
            s=json.loads((ROOT/'gamemaster-skill/assets'/name).read_text());doc,audit=content.compile_document(s)
            render.validate(doc);self.assertTrue(doc['pending']);self.assertFalse(audit['valid'])

    def test_supplement_uses_original_categories_and_direction(self):
        s=supplement();doc,audit=content.compile_document(s);render.validate(doc)
        body=render.markdown(doc,False);self.assertTrue(audit['valid']);self.assertIn('0:3',body)
        self.assertIn('原甲组男子单打',body);self.assertIn('2030年6月22日12:00',body)

    def test_supplement_cannot_omit_baseline_or_response(self):
        s=supplement();del s['base_document']['version'];self.check_error(s,'base_document.version')
        s=supplement();s['response_window']=None;self.check_error(s,'response_window')

    def test_supplement_mapping_must_cover_affected_groups(self):
        s=supplement();s['affected_source_ids'].append('C');self.check_error(s,'原项目清单')

    def test_handicap_matrix_complete_and_not_already_won(self):
        s=supplement();s['handicap']['pairs']=[];self.check_error(s,'未覆盖')
        s=supplement();s['handicap']['pairs'][0]['initial']=[0,21];self.check_error(s,'cap')

    def test_handicap_reverse_duplicate_rejected(self):
        s=supplement();r=deepcopy(s['handicap']['pairs'][0]);r.update(a='B',b='A',initial=[3,0]);s['handicap']['pairs'].append(r)
        self.check_error(s,'重复')

    def test_old_ambiguous_clause_can_be_quoted_when_corrected(self):
        s=supplement();s['changes'][0].update(before='每人限兼报1项',after='每名运动员最多报名2个项目')
        self.assertTrue(content.compile_document(s)[1]['valid'])

    def test_tennis_and_pickleball_preserve_specific_fields(self):
        s=fixture();s['event']['sport']='pickleball';self.check_error(s,'侧出得分')
        for stage in s['groups'][0]['stages']:stage['scoring_system']='side_out'
        doc,_=content.compile_document(s);self.assertIn('侧出得分',render.markdown(doc,False))
        rule={'mode':'tennis','best_of':3,'games_to_win':6,'set_win_by':2,'tiebreak_at':6,
              'tiebreak_target':7,'match_tiebreak_target':10,'no_ad':True}
        s['event']['sport']='tennis'
        for stage in s['groups'][0]['stages']:stage['rules']=rule;stage.pop('scoring_system',None)
        doc,_=content.compile_document(s);body=render.markdown(doc,False)
        self.assertIn('3盘2胜',body);self.assertIn('抢10',body);self.assertIn('无占先',body)

    def test_cli_build_and_render_semantics(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp);source=p/'source.json';source.write_text(json.dumps(fixture(),ensure_ascii=False))
            run=subprocess.run([sys.executable,str(ROOT/'gamemaster-skill/scripts/regulation_content.py'),'build',str(source),str(p/'out')],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)
            result=json.loads((p/'out/document.json').read_text());self.assertEqual(result['status'],'final')
            self.assertTrue((p/'out/content-review.json').exists())

    def test_unknown_fields_and_malformed_containers_fail_explicitly(self):
        for key,value in [('extra_clauses',[None]),('changes',{}),('handicap',None),('unexpected','cannot drop me')]:
            s=fixture();s[key]=value
            with self.assertRaises(ValueError):content.compile_document(s)

    def test_partial_age_null_can_still_produce_draft(self):
        s=fixture();s['status']='draft';s['groups'][0]['age']=None
        doc,audit=content.compile_document(s);render.validate(doc)
        self.assertFalse(audit['ready_for_final']);self.assertTrue(doc['pending'])

    def test_known_entrants_need_progression_capacity_or_explicit_policy(self):
        s=fixture();del s['groups'][0]['stages'][0]['group_sizes']
        self.check_error(s,'晋级分组未定')

    def test_joint_bronze_requires_four_final_stage_places(self):
        s=fixture();g=s['groups'][0];g['stages'][0]['advance_per_group']=1
        g['stages'][1]['entrants']=2;g['awards']['bronze']='joint'
        self.check_error(s,'超过最终阶段')

    def test_notice_without_merge_has_continuous_headings_and_recipient(self):
        s=supplement();s['mapping']=[];s['affected_source_ids']=[];s.pop('handicap')
        s.update(subject='比赛时间调整',recipients='各参赛单位')
        doc,audit=content.compile_document(s);render.validate(doc)
        self.assertEqual([x['heading'].split('、')[0]for x in doc['sections']],['一','二','三','四'])
        self.assertIn('比赛时间调整的补充通知',doc['title']);self.assertIn('各参赛单位：',render.markdown(doc,False))
        self.assertTrue(audit['ready_for_final'])

    def test_warning_prevents_ready_for_final_even_if_structurally_valid(self):
        s=fixture();s['policies']['rule_basis']='采用最新发布的规则'
        report=content.inspect(s);self.assertTrue(report['valid']);self.assertFalse(report['ready_for_final'])

    def test_declared_sources_survive_and_no_facts_are_rewritten(self):
        s=fixture();before=deepcopy(s);doc,report=content.compile_document(s)
        self.assertEqual(s,before);body=render.markdown(doc,False)
        self.assertIn('100元/人',body);self.assertIn('2020年1月1日',body)
        self.assertEqual(report['age_groups']['G1']['end'],'2022-12-31')

    def test_nested_age_intervals_do_not_invent_union_gap(self):
        s=fixture();s['groups']=[]
        for i,(lo,hi)in enumerate([(5,15),(6,7),(10,11)]):
            g=deepcopy(fixture()['groups'][0]);g.update(id=f'G{i}',name=f'合成第{i}年龄组男子单打')
            g['age'].update(min_age=lo,max_age=hi);s['groups'].append(g)
        s['age_partitions']=[{'groups':['G0','G1','G2'],'overlap_policy':'合成方案允许符合两组者择一报名'}]
        self.assertTrue(content.inspect(s)['valid'])

    def test_orphan_handicap_is_not_silently_dropped(self):
        s=supplement();s['mapping']=[];self.check_error(s,'不能丢弃')

    def test_initial_scores_and_team_rubber_count_are_not_lost(self):
        text=content.scoring_text({'mode':'points','best_of':1,'target':21,'win_by':1,'cap':21,'initial_points':[0,3]})
        self.assertIn('0:3',text)
        self.assertIn('全部5个子场',content.scoring_text({'mode':'team','win_target':3,'play_all':True,'rubber_count':5}))


if __name__=='__main__':unittest.main(verbosity=2)
