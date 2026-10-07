"""Synthetic multi-event, bye and live-change scenarios; no platform credentials."""
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import sys
import json
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'gamemaster-skill/scripts'))
from test_workflow_pipeline import fixture
import prepare_event, draw_engine, bracket_engine, schedule_engine, results_engine


def complex_fixture():
    roster, settings, plan = fixture('groups_knockout')
    roster['exclusive'] = False
    for i,entry in enumerate(roster['entries']):
        entry['members'][0]['unit']=f'合成单位{i%3}'
    roster['projects'][0].update(name='合成分组男子单打')
    roster['projects'].append({'key': 'D', 'name': '合成男子双打', 'type': 'MD', 'expected_count': 5})
    for i in range(1, 6):
        person = deepcopy(roster['entries'][i-1]['members'][0])
        partner = {'id': f'A{i+8}', 'name': f'合成选手{i+8:02}', 'gender': 'M', 'unit': person['unit']}
        roster['entries'].append({'id': f'D{i}', 'status': 'active', 'project': 'D',
            'source': '合成兼项报名', 'seed': i if i<=2 else 0, 'members': [person, partner]})
    doubles=deepcopy(settings['projects'][0])
    for k in ('group_sizes','seed_policy','advance_per_group','knockout_slots'):
        doubles.pop(k,None)
    doubles.update(id='D',entry_size=2,format='knockout',seed_profile='badminton_bwf')
    settings['projects'].append(doubles)
    settings.update(event_id='SYNTHETIC-COMPLEX',event_name='合成复杂赛制与临场变更测试')
    plan['rows'][0].update(title='合成分组男子单打')
    plan['rows'][1].update(title='合成分组男子单打')
    plan['rows'].append(dict(plan['rows'][0],id='D',group='合成双打组',type='MD',
        title='合成男子双打',entrants=5,groups=0,advance=4,group_sizes=[],format='TT'))
    return roster,settings,plan


def build(roster=None,settings=None):
    if roster is None: roster,settings,_=complex_fixture()
    prepared=prepare_event.prepare(roster,settings)
    draw=draw_engine.generate(prepared['draw_config'])
    graph=bracket_engine.generate(prepare_event.attach_draw(prepared['draw_config'],prepared['bracket_base'],draw))
    data={'event_id':settings['event_id'],'courts':[1,2,3,4],'slot_minutes':15,
        'sessions':[{'start':'2030-01-01T09:00','end':'2030-01-01T12:00','section':1},
                    {'start':'2030-01-01T14:00','end':'2030-01-01T18:00','section':2}],
        'rest_basis':'elapsed','rest_minutes':15,'conflict_scope':'possible',
        'matches':deepcopy(graph['matches']),'outcome_disjoint_pairs':graph['outcome_disjoint_pairs'],
        'attempts':4,'random_seed':7,'priority_projects':['D'],
        'constraint_sources':{'*':{'kind':'user','reference':'Synthetic scenario parameters'}}}
    return prepared,draw,graph,data


def finish(graph):
    graph=deepcopy(graph);graph['synthetic']=True;graph.setdefault('results',[])
    while True:
        report=results_engine.evaluate(graph)
        if not report['pending_match_ids']: return graph,report
        ready=next((m for m in report['matches'] if m['status']=='pending' and all(m['entry_ids'])),None)
        if ready is None: raise AssertionError('Unresolved synthetic progression')
        winner=min(ready['entry_ids'])
        graph['results'].append({'match_id':ready['match_id'],'entry_ids':ready['entry_ids'],
            'status':'completed','winner_id':winner,'source':'Synthetic simulation',
            'score':{'games':[[21,10] if ready['entry_ids'][0]==winner else [10,21]]}})


class ComplexLifecycle(unittest.TestCase):
    def test_explicit_unit_constraints_report_infeasible_without_relaxing(self):
        roster,settings,_=complex_fixture()
        for entry in roster['entries']:
            for m in entry['members']:
                # Original two-club fixture conflicts with seeds and 5-entry bye regions.
                n=int(m['id'][1:]);n=n-8 if n>8 else n
                m['unit']=f'合成单位{(n-1)%2}'
        with self.assertRaisesRegex(draw_engine.DrawError,'无可行解'):
            build(roster,settings)

    def test_two_stage_doubles_byes_and_cross_event_rest(self):
        _,draw,graph,data=build()
        self.assertEqual(len(graph['matches']),21)
        self.assertEqual(len([m for m in graph['matches'] if m['project_id']=='D']),5)
        self.assertEqual(len(graph['automatic_advances']),3)
        schedule=schedule_engine.schedule(data)
        self.assertTrue(schedule_engine.acceptance(data,schedule)['ready_for_export'])
        final,report=finish(graph)
        self.assertFalse(report['unresolved_match_ids'])
        self.assertEqual(len(report['placements']),8)
        # Independently check actual resolved athletes and real elapsed rest.
        entries={e['id']:set(e['member_ids']) for e in graph['entries']}
        assignments={r['match_id']:r for r in schedule['assignments']}
        appearances={}
        for m in report['matches']:
            rec=assignments[m['match_id']]
            for aid in set.union(*(entries[eid] for eid in m['entry_ids'])):
                appearances.setdefault(aid,[]).append(rec)
        for records in appearances.values():
            records.sort(key=lambda r:r['start'])
            for a,b in zip(records,records[1:]):
                gap=(datetime.fromisoformat(b['start'])-datetime.fromisoformat(a['end'])).total_seconds()/60
                self.assertGreaterEqual(gap,15)
        for m in graph['matches']:
            for parent in m['predecessors']:
                self.assertLessEqual(assignments[parent]['end'],assignments[m['id']]['start'])

    def test_replacement_keeps_entry_draw_and_match_ids_but_updates_all_candidates(self):
        roster,settings,_=complex_fixture()
        _,draw,graph,_=build(roster,settings)
        target=next(e for e in roster['entries'] if e['id']=='D5')
        target['members'][1]={'id':'A99','name':'合成替补99','unit':target['members'][0]['unit'],'gender':'M'}
        for p in settings['projects']:
            dp=next(x for x in draw['projects'] if x['project_id']==p['id'])
            p['fixed_entries']={r['entry_id']:{'group':r['group'],'position':r['position']} for r in dp['assignments']}
        _,newdraw,newgraph,data=build(roster,settings)
        positions=lambda d:[(p['project_id'],r['entry_id'],r['group'],r['position']) for p in d['projects'] for r in p['assignments']]
        self.assertEqual(positions(draw),positions(newdraw))
        self.assertEqual([m['id'] for m in graph['matches']],[m['id'] for m in newgraph['matches']])
        self.assertTrue(any('A99' in m['possible_athletes'] for m in newgraph['matches']))
        self.assertFalse(any('A13' in m['possible_athletes'] for m in newgraph['matches']))
        self.assertTrue(schedule_engine.validate(data,schedule_engine.schedule(data))['complete'])

    def test_delayed_upstream_requires_new_schedule_and_preserves_finished_matches(self):
        _,_,_,data=build();result=schedule_engine.schedule(data)
        fixed=min(result['assignments'],key=lambda r:r['start'])
        pending=next(m for m in data['matches'] if m['project_id']=='D' and m['id']!=fixed['match_id'])
        old={r['match_id']:r for r in result['assignments']}[pending['id']]
        pending['not_before']='2030-01-01T14:00'
        frozen=next(m for m in data['matches'] if m['id']==fixed['match_id'])
        frozen['fixed']={'start':fixed['start'],'court':fixed['court']}
        self.assertFalse(schedule_engine.validate(data,result)['complete'])
        revised=schedule_engine.schedule(data)
        self.assertTrue(schedule_engine.validate(data,revised)['complete'])
        byid={r['match_id']:r for r in revised['assignments']}
        self.assertEqual(byid[fixed['match_id']],fixed)
        self.assertGreaterEqual(byid[pending['id']]['start'],pending['not_before'])

    def test_walkover_is_not_played_score_and_default_group_needs_ruling(self):
        _,_,graph,_=build();finished,report=finish(graph)
        target=next(m for m in report['matches'] if m['project_id']=='P' and m['stage']==1)
        # Keep only round-robin results so pending qualification remains observable.
        stage1={m['id'] for m in graph['matches'] if m['stage']==1}
        finished['results']=[r for r in finished['results'] if r['match_id'] in stage1]
        r=next(r for r in finished['results'] if r['match_id']==target['match_id'])
        r.update(status='walkover',reason='Synthetic single-match withdrawal');r.pop('score')
        after=results_engine.evaluate(finished)
        self.assertFalse(next(g for g in after['groups'] if g['id']==target['group_id'])['complete'])
        for g in finished['groups']:
            g['ranking'].update(abnormal_results='wins_only')
        after=results_engine.evaluate(finished)
        self.assertTrue(all(g['complete'] for g in after['groups']))
        r['score']={'games':[[21,0]]}
        with self.assertRaisesRegex(ValueError,'invent played'):results_engine.evaluate(finished)

    def test_score_bound_to_both_original_opponents(self):
        _,_,graph,_=build();finished,report=finish(graph)
        # A semifinal changes the final's losing player; the final winner still exists.
        final=next(m for m in graph['matches'] if m['project_id']=='D' and m.get('placement',{}).get('winner')==1)
        fr=next(m for m in report['matches'] if m['match_id']==final['id'])
        loser=fr['loser_id']
        parent=next(m for m in report['matches'] if m['match_id'] in final['predecessors'] and m['winner_id']==loser)
        r=next(r for r in finished['results'] if r['match_id']==parent['match_id'])
        r['winner_id']=parent['loser_id'];r['score']['games'][0].reverse()
        # Remove bronze to isolate the otherwise silently accepted final.
        bronze={m['id'] for m in graph['matches'] if m['project_id']=='D' and m.get('placement',{}).get('winner')==3}
        finished['results']=[r for r in finished['results'] if r['match_id'] not in bronze]
        with self.assertRaisesRegex(ValueError,'participant|opponent|entry binding'):
            results_engine.evaluate(finished)

    def test_binding_legacy_results_before_replacement_detects_changed_double_member(self):
        _,_,graph,_=build();finished,_=finish(graph)
        for r in finished['results']: r.pop('entry_ids',None)
        bound=results_engine.bind_result_participants(finished)
        self.assertNotIn('member_ids',finished['results'][0])
        self.assertTrue(all('entry_ids' in r and 'member_ids' in r for r in bound['results']))
        self.assertEqual(len(results_engine.evaluate(finished)['unbound_result_ids']),21)
        self.assertEqual(results_engine.evaluate(bound)['unbound_result_ids'],[])
        next(e for e in bound['entries'] if e['id']=='D5')['member_ids'][1]='A99'
        with self.assertRaisesRegex(ValueError,'member binding'):
            results_engine.evaluate(bound)

    def test_corrected_points_same_opponents_keep_valid_downstream_and_places(self):
        _,_,graph,_=build();finished,before=finish(graph)
        bound=results_engine.bind_result_participants(finished)
        r=bound['results'][0]
        r['score']['games'][0]=[21,12] if r['score']['games'][0][0]==21 else [12,21]
        after=results_engine.evaluate(bound)
        self.assertEqual(before['placements'],after['placements'])
        self.assertFalse(after['unresolved_match_ids'])

    def test_first_double_member_change_rejects_old_scores_even_with_same_entry_ids(self):
        _,_,graph,_=build();finished,_=finish(graph)
        bound=results_engine.bind_result_participants(finished)
        next(e for e in bound['entries'] if e['id']=='D2')['member_ids'][0]='A8'
        self.assertEqual(next(e for e in bound['entries'] if e['id']=='E2')['member_ids'], ['A2'])
        with self.assertRaisesRegex(ValueError,'member binding'):
            results_engine.evaluate(bound)

    def test_new_scores_after_first_member_replacement_propagate_champion(self):
        _,_,graph,_=build();finished,baseline=finish(graph)
        changed=results_engine.bind_result_participants(finished)
        entries={e['id']:e for e in changed['entries']}
        entries['D2']['member_ids'][0]='A8'
        doubles={m['id'] for m in changed['matches'] if m['project_id']=='D'}
        changed['results']=[r for r in changed['results'] if r['match_id'] not in doubles]
        for _ in range(len(doubles)):
            report=results_engine.evaluate(changed)
            ready=next(m for m in report['matches'] if m['status']=='pending' and all(m['entry_ids']))
            winner='D2' if 'D2' in ready['entry_ids'] else min(ready['entry_ids'])
            changed['results'].append({'match_id':ready['match_id'],'status':'completed',
                'entry_ids':ready['entry_ids'],
                'member_ids':[entries[e]['member_ids'][:] for e in ready['entry_ids']],
                'winner_id':winner,'source':'Fresh synthetic replacement score',
                'score':{'games':[[21,9] if ready['entry_ids'][0]==winner else [9,21]]}})
        final=results_engine.evaluate(changed)
        self.assertFalse(final['pending_match_ids'])
        self.assertFalse(final['unbound_result_ids'])
        self.assertEqual(next(p['entry_id'] for p in final['placements']
                              if p['project_id']=='D' and p['rank']==1),'D2')
        self.assertEqual([p for p in baseline['placements'] if p['project_id']=='P'],
                         [p for p in final['placements'] if p['project_id']=='P'])

    def test_duplicate_doubles_member_replacement_rejected(self):
        roster,settings,_=complex_fixture()
        target=next(e for e in roster['entries'] if e['id']=='D5')
        target['members'][1]=deepcopy(roster['entries'][0]['members'][0])
        with self.assertRaisesRegex(ValueError,'同项目重复'):
            build(roster,settings)

    def test_unfinished_group_does_not_allow_qualification_score(self):
        _,_,graph,_=build()
        match=next(m for m in graph['matches'] if m['project_id']=='P' and m['stage']==2)
        graph['results']=[{'match_id':match['id'],'status':'completed','winner_id':'E1','score':{'games':[[21,10]]}}]
        with self.assertRaisesRegex(ValueError,'unresolved'):
            results_engine.evaluate(graph)

    def test_cli_bound_snapshot_is_separate_and_refuses_overwrite(self):
        _,_,graph,_=build();finished,_=finish(graph)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'input.json';bound=root/'bound.json'
            source.write_text(json.dumps(finished),encoding='utf-8')
            cmd=[sys.executable,str(ROOT/'gamemaster-skill/scripts/results_engine.py'),str(source),
                 '--no-xlsx','--output',str(root/'export'),'--bind-participants-out',str(bound)]
            run=subprocess.run(cmd,capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)
            data=json.loads(bound.read_text());self.assertEqual(results_engine.evaluate(data)['unbound_result_ids'],[])
            previous=bound.read_bytes()
            cmd[cmd.index('--output')+1]=str(root/'another-export')
            self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0)
            self.assertEqual(bound.read_bytes(),previous)
            self.assertFalse((root/'another-export').exists())


if __name__=='__main__': unittest.main()
