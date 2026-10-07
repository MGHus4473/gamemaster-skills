import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ptty-skill/scripts'))
from roster_replacement import audit, prepare
import operation_catalog
import task_contract


class RosterReplacementTests(unittest.TestCase):
    def setUp(self):
        self.old = dict(RYID='athlete-old', RYXM='Synthetic Old', XB='M', SFZH='',
                        AGE='0', TEL='', DWID='unit-a', DWQC='Unit A', DWJC='A')
        self.candidate = dict(self.old, RYID='athlete-new', RYXM='Synthetic New')
        self.before = [dict(self.old, XMID='project-s', XMNM='entry-s', SSLX='MS',
                            ZZH='1', DNJSH='7'),
                       dict(XMID='project-d', XMNM='entry-d', SSLX='MD',
                            RYID1='athlete-partner', RYID2='athlete-new',
                            RYXM1='Synthetic Partner', RYXM2='Synthetic New')]
        self.after = copy.deepcopy(self.before)
        self.after[0].update(self.candidate)
        self.form = {k + '1': self.old[k] for k in ('DWQC', 'DWJC', 'RYXM', 'XB', 'SFZH', 'AGE', 'TEL')}
        self.form.update(TYPE='UPT', SSLX='MS', XMID='project-s', XMNM='entry-s',
                         ZZH='1', DNJSH='7', visible=True)

    def check(self):
        return audit(self.before, self.after, 'project-s', 'entry-s', self.candidate)

    def test_prepare_preserves_live_form_and_does_not_invent_person_id(self):
        original = copy.deepcopy(self.form)
        request = prepare(self.form, self.candidate)
        self.assertEqual(self.form, original)
        self.assertNotIn('RYID', request)
        for field in ('XMID', 'XMNM', 'ZZH', 'DNJSH', 'TYPE'):
            self.assertEqual(request[field], original[field])
        self.assertEqual(request['RYXM1'], 'Synthetic New')

    def test_real_rebind_preserves_cross_entry(self):
        self.assertTrue(self.check()['valid'])
        self.assertEqual(self.check()['protected_entries'], 1)

    def test_rename_is_not_replacement(self):
        self.after[0]['RYID'] = self.old['RYID']
        self.assertIn('replacement_identity_mismatch', self.check()['errors'])

    def test_fresh_id_on_restore_is_not_original_identity(self):
        restored = copy.deepcopy(self.before)
        restored[0]['RYID'] = 'athlete-recreated'
        result = audit(self.after, restored, 'project-s', 'entry-s', self.old)
        self.assertFalse(result['valid'])

    def test_other_project_rename_is_rejected(self):
        self.after[1]['RYXM2'] = 'Unexpected Rename'
        self.assertIn('other_entry_changed', self.check()['errors'])

    def test_seed_and_entry_changes_are_rejected(self):
        self.after[0]['ZZH'] = '2'
        self.assertIn('target_non_person_fields_changed', self.check()['errors'])
        self.after[0]['XMNM'] = 'new-entry'
        self.assertIn('entry_set_changed', self.check()['errors'])

    def test_duplicate_same_project_person_is_rejected(self):
        row = dict(self.candidate, XMID='project-s', XMNM='another-entry', SSLX='MS')
        self.before.append(row.copy())
        self.after.append(row.copy())
        self.assertIn('duplicate_person_in_project', self.check()['errors'])

    def test_incomplete_readback_is_rejected(self):
        self.after.pop()
        self.assertIn('other_entry_changed', self.check()['errors'])

    def test_missing_identity_and_unsupported_forms(self):
        with self.assertRaises(ValueError):
            prepare(self.form, {'RYXM': 'Only Name'})
        with self.assertRaises(ValueError):
            prepare(dict(self.form, SSLX='MD'), self.candidate)
        with self.assertRaises(ValueError):
            audit(self.before + [self.before[0]], self.after, 'project-s', 'entry-s', self.candidate)

    def test_roster_edit_exposes_downstream_identity_and_lock_effects(self):
        result = operation_catalog.preflight(operation_catalog.load_catalog(), {
            'operations': ['roster.edit'], 'mode': 'requested_changes'})['steps'][0]
        self.assertIn('downstream_reviewed', result['facts_to_read'])
        self.assertTrue({'results', 'roster_lock', 'identity_mapping'} <= set(result['recheck_after_change']))

    def test_protected_results_task_cannot_silently_replace_people(self):
        contract = {'event_id': 'synthetic-event', 'allowed_operations': ['roster.edit'],
                    'protect_existing_results': True,
                    'allowed_fields': {'roster.edit': ['person']}}
        action = {'event_id': 'synthetic-event', 'operation_id': 'roster.edit',
                  'changed_fields': ['person']}
        result = task_contract.validate(contract, [action])
        self.assertFalse(result['valid'])
        self.assertIn('existing_results_may_change', result['errors'][0]['reasons'])


class DoublesReplacementTests(unittest.TestCase):
    def setUp(self):
        def person(identity):
            return dict(RYID=identity, RYXM='Synthetic ' + identity, XB='M',
                        SFZH='', AGE='0', TEL='', DWID='unit', DWQC='Unit', DWJC='U')
        self.partner, self.old, self.candidate = map(person, ('partner', 'old', 'new'))
        target = dict(XMID='doubles', XMNM='pair', SSLX='MD', ZZH='2', DNJSH='9')
        for index, member in enumerate((self.partner, self.old), 1):
            target.update({k + str(index): v for k, v in member.items()})
        self.before = [target, dict(self.partner, XMID='singles', XMNM='entry-a', SSLX='MS'),
                       dict(self.candidate, XMID='singles', XMNM='entry-b', SSLX='MS')]
        self.after = copy.deepcopy(self.before)
        self.after[0].update({k + '2': v for k, v in self.candidate.items()})
        self.form = {k: v for k, v in target.items() if not k.startswith(('RYID', 'DWID'))}
        self.form.update(TYPE='UPT', visible=True)

    def check(self):
        return audit(self.before, self.after, 'doubles', 'pair', self.candidate, member_index=2)

    def test_second_member_form_preserves_first_and_seed(self):
        request = prepare(self.form, self.candidate, member_index=2)
        for k, v in self.form.items():
            if k not in {f + '2' for f in ('DWQC', 'DWJC', 'RYXM', 'XB', 'SFZH', 'AGE', 'TEL')}:
                self.assertEqual(request[k], v)
        self.assertEqual(request['RYXM2'], self.candidate['RYXM'])
        self.assertTrue(self.check()['valid'])

    def test_first_member_can_be_explicitly_selected(self):
        after = copy.deepcopy(self.before)
        after[0].update({k + '1': v for k, v in self.candidate.items()})
        self.assertTrue(audit(self.before, after, 'doubles', 'pair', self.candidate, 1)['valid'])
        self.assertEqual(prepare(self.form, self.candidate, 1)['RYXM2'], self.old['RYXM'])

    def test_partner_changes_and_member_swaps_are_rejected(self):
        self.after[0]['RYID1'] = 'different-partner'
        self.assertIn('target_non_person_fields_changed', self.check()['errors'])
        self.after[0]['RYID1'], self.after[0]['RYID2'] = self.after[0]['RYID2'], self.after[0]['RYID1']
        self.assertIn('replacement_identity_mismatch', self.check()['errors'])

    def test_duplicate_person_cannot_fill_both_pair_slots(self):
        self.candidate = self.partner
        self.after[0].update({k + '2': v for k, v in self.partner.items()})
        self.assertIn('duplicate_person_in_project', self.check()['errors'])

    def test_candidate_already_in_another_pair_is_rejected(self):
        pair = copy.deepcopy(self.before[0]); pair['XMNM'] = 'other-pair'
        pair['RYID1'] = self.candidate['RYID']
        self.before.append(pair.copy()); self.after.append(pair.copy())
        self.assertIn('duplicate_person_in_project', self.check()['errors'])

    def test_other_project_identity_is_protected(self):
        self.after[2]['RYID'] = 'new-duplicate-identity'
        self.assertIn('other_entry_changed', self.check()['errors'])

    def test_restore_with_recreated_partner_id_requires_mapping_refresh(self):
        restored = copy.deepcopy(self.before)
        restored[0]['RYID2'] = 'recreated-old'
        report = audit(self.after, restored, 'doubles', 'pair', self.old, 2)
        self.assertIn('replacement_identity_mismatch', report['errors'])

    def test_member_index_and_special_multi_person_types_are_rejected(self):
        for index in (0, 3, True, '2'):
            with self.assertRaises(ValueError):
                prepare(self.form, self.candidate, index)
        with self.assertRaises(ValueError):
            prepare(dict(self.form, SSLX='LD'), self.candidate, 2)

    def test_unrelated_team_entry_is_preserved_without_parsing_its_members(self):
        team = dict(XMID='team-project', XMNM='team-entry', SSLX='MT', members=['synthetic'])
        self.before.append(team.copy()); self.after.append(team.copy())
        self.assertTrue(self.check()['valid'])


if __name__ == '__main__':
    unittest.main()
