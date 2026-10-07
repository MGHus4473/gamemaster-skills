"""Synthetic recovery and task-scope regressions; no live calls."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ptty-skill/scripts'))
import workflow_state as recovery
import task_contract


def snapshot(values, time='2030-01-01T10:00:00Z'):
    return {'binding': {'event': 'synthetic-event', 'scope': 'synthetic-project'},
            'complete': True, 'captured_at': time,
            'rows': [{'key': k, 'values': v} for k, v in values.items()]}


def case():
    before = snapshot({'A': {'start': '11:45', 'court': 1}, 'B': {'start': '11:45', 'court': 2}})
    desired = snapshot({'A': {'start': '11:30', 'court': 1}, 'B': {'start': '11:30', 'court': 2}})
    current = deepcopy(before); current['captured_at'] = '2030-01-01T10:02:00Z'
    return {'schema_version': 1, 'operation_id': 'schedule.move', 'input_version': 'synthetic-v1',
            'before': before, 'desired': desired, 'current': current, 'attempts': 1,
            'submitted_at': '2030-01-01T10:01:00Z',
            'policy': {'subset_retry_verified': True},
            'evidence': {'session_valid': True, 'contract_current': True, 'transport': 'timeout'}}


class RecoveryTests(unittest.TestCase):
    def test_timeout_but_committed_is_not_retried(self):
        r = case(); r['current']['rows'] = deepcopy(r['desired']['rows'])
        out = recovery.assess(r)
        self.assertEqual(out['status'], 'matched_desired'); self.assertEqual(out['retry_keys'], [])
        self.assertFalse(out['online_verified']); self.assertFalse(out['execution_authorized'])

    def test_partial_import_only_retries_missing_rows(self):
        r = case(); r['current']['rows'][0] = deepcopy(r['desired']['rows'][0])
        out = recovery.assess(r)
        self.assertEqual(out['completed_keys'], ['A']); self.assertEqual(out['retry_keys'], ['B'])

    def test_partially_changed_row_requires_review(self):
        r = case(); r['current']['rows'][0]['values']['court'] = 3
        self.assertEqual(recovery.assess(r)['status'], 'conflict_review_required')

    def test_unrequested_change_is_not_overwritten(self):
        r = case(); extra = {'key': 'protected', 'values': {'visible': False}}
        for key in ('before', 'desired', 'current'): r[key]['rows'].append(deepcopy(extra))
        r['current']['rows'][-1]['values']['visible'] = True
        self.assertIn('protected', recovery.assess(r)['conflicting_keys'])

    def test_incomplete_readback_cannot_prove_absence(self):
        r = case(); r['current']['complete'] = False; r['current']['rows'] = []
        self.assertEqual(recovery.assess(r)['status'], 'readback_required')

    def test_expired_login_cannot_be_treated_as_empty_state(self):
        r = case(); r['evidence']['session_valid'] = False
        self.assertEqual(recovery.assess(r)['status'], 'readback_required')

    def test_stale_readback_after_timeout_is_rejected(self):
        r = case(); r['current']['captured_at'] = r['before']['captured_at']
        self.assertEqual(recovery.assess(r)['status'], 'readback_required')

    def test_repeated_failure_without_new_evidence_stops(self):
        r = case(); r['attempts'] = 2
        self.assertEqual(recovery.assess(r)['status'], 'retry_limit_requires_new_evidence')

    def test_new_evidence_does_not_bypass_conflict(self):
        r = case(); r['attempts'] = 2; r['evidence']['new_evidence'] = True
        r['current']['rows'][0]['values']['court'] = 8
        self.assertEqual(recovery.assess(r)['status'], 'conflict_review_required')

    def test_payments_need_transaction_reconciliation(self):
        r = case(); r['operation_id'] = 'roster.lock'; r['policy']['irreversible'] = True
        self.assertEqual(recovery.assess(r)['status'], 'transaction_reconciliation_required')

    def test_full_replace_endpoint_cannot_receive_subset_retry(self):
        r = case(); r['policy']['subset_retry_verified'] = False
        self.assertEqual(recovery.assess(r)['status'], 'retry_contract_required')

    def test_score_write_needs_downstream_readback(self):
        r = case(); r['current']['rows'] = deepcopy(r['desired']['rows']); r['policy']['downstream_required'] = True
        self.assertEqual(recovery.assess(r)['status'], 'downstream_readback_required')
        r['evidence']['downstream_verified'] = True
        self.assertEqual(recovery.assess(r)['status'], 'matched_desired')

    def test_changed_client_contract_stops_retry(self):
        r = case(); r['evidence']['contract_current'] = False
        self.assertEqual(recovery.assess(r)['status'], 'contract_recheck_required')

    def test_success_message_with_wrong_created_sport_is_conflict(self):
        r = case(); r['before']['rows'] = []
        r['desired']['rows'] = [{'key': 'new-event', 'values': {'sport': 'requested-sport'}}]
        r['current']['rows'] = [{'key': 'new-event', 'values': {'sport': 'different-sport'}}]
        r['evidence']['transport'] = 'success'
        out = recovery.assess(r)
        self.assertEqual(out['status'], 'conflict_review_required')
        self.assertEqual(out['retry_keys'], [])

    def test_unchanged_after_success_is_pending_not_verified(self):
        r = case(); r['evidence']['transport'] = 'success'
        out = recovery.assess(r)
        self.assertEqual(out['pending_keys'], ['A', 'B'])
        self.assertNotEqual(out['status'], 'matched_desired')

    def test_wrong_event_or_duplicate_ids_fail(self):
        r = case(); r['current']['binding']['event'] = 'another-event'
        with self.assertRaises(ValueError): recovery.assess(r)
        r = case(); r['current']['rows'].append(deepcopy(r['current']['rows'][0]))
        with self.assertRaises(ValueError): recovery.assess(r)
        r = case(); del r['input_version']
        with self.assertRaises(ValueError): recovery.assess(r)

    def test_add_and_delete_rows_are_compared_exactly(self):
        r = case(); r['desired']['rows'] = [{'key': 'C', 'values': {'start': '11:30', 'court': 1}}]
        r['current']['rows'] = deepcopy(r['desired']['rows'])
        self.assertEqual(recovery.assess(r)['completed_keys'], ['A', 'B', 'C'])

    def test_hash_stable_across_row_order_but_sensitive_to_input(self):
        r = case(); a = recovery.assess(r)['operation_key']; r['before']['rows'].reverse()
        self.assertEqual(a, recovery.assess(r)['operation_key'])
        r['input_version'] = 'synthetic-v2'
        self.assertNotEqual(a, recovery.assess(r)['operation_key'])

    def test_prepared_operation_is_not_a_retry_or_authorization(self):
        r = case(); r['attempts'] = 0
        out = recovery.assess(r)
        self.assertEqual(out['status'], 'prepared'); self.assertFalse(out['execution_authorized'])

    def test_journal_chain_detects_modified_receipt(self):
        r = case(); out = recovery.assess(r)
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'receipts.jsonl'
            recovery.append_record(p, r, out); recovery.append_record(p, r, out)
            records = [json.loads(line) for line in p.read_text().splitlines()]
            records[0]['attempts'] = 99
            p.write_text('\n'.join(json.dumps(x) for x in records) + '\n')
            with self.assertRaises(ValueError): recovery.append_record(p, r, out)


class IntentScopeTests(unittest.TestCase):
    def test_publish_roster_only_rejects_draw_and_other_project(self):
        contract = {'event_id': 'synthetic-event', 'allowed_operations': ['publish.visibility'],
                    'required_operations': ['publish.visibility'], 'project_ids': ['P1'],
                    'allowed_fields': {'publish.visibility': ['ISGSMD']}}
        action = {'event_id': 'synthetic-event', 'operation_id': 'publish.visibility',
                  'project_ids': ['P1'], 'changed_fields': ['ISGSMD']}
        self.assertTrue(task_contract.validate(contract, [action])['valid'])
        for delta in ({'changed_fields': ['ISGSCQ']}, {'project_ids': ['P2']}, {'project_ids': []}):
            self.assertFalse(task_contract.validate(contract, [{**action, **delta}])['valid'])

    def test_do_not_move_started_match_or_regenerate(self):
        contract = {'event_id': 'synthetic-event', 'allowed_operations': ['schedule.move'],
                    'match_ids': ['M1', 'M2'], 'protected_match_ids': ['M1'], 'protect_existing_results': True,
                    'allowed_fields': {'schedule.move': ['date', 'time', 'court']}}
        a = {'event_id': 'synthetic-event', 'operation_id': 'schedule.move', 'match_ids': ['M2'], 'changed_fields': ['time']}
        self.assertTrue(task_contract.validate(contract, [a])['valid'])
        self.assertFalse(task_contract.validate(contract, [{**a, 'match_ids': ['M1']}])['valid'])
        self.assertFalse(task_contract.validate(contract, [{**a, 'operation_id': 'matches.generate'}])['valid'])

    def test_publish_does_not_authorize_notifications(self):
        c = {'event_id': 'synthetic-event', 'allowed_operations': ['publish.content']}
        a = {'event_id': 'synthetic-event', 'operation_id': 'control.notify_send'}
        self.assertFalse(task_contract.validate(c, [a])['valid'])

    def test_mobile_section_only_preserves_other_audiences(self):
        c = {'event_id': 'synthetic-event', 'allowed_operations': ['control.sections'], 'audiences': ['mobile'],
             'allowed_fields': {'control.sections': ['ISWAPQY']}}
        a = {'event_id': 'synthetic-event', 'operation_id': 'control.sections',
             'audiences': ['mobile'], 'changed_fields': ['ISWAPQY']}
        self.assertTrue(task_contract.validate(c, [a])['valid'])
        self.assertFalse(task_contract.validate(c, [{**a, 'audiences': ['referee']}])['valid'])
        self.assertFalse(task_contract.validate(c, [{**a, 'audiences': []}])['valid'])
        self.assertFalse(task_contract.validate(c, [{**a, 'changed_fields': ['ISQY']}])['valid'])

    def test_wrong_event_readonly_and_missing_work(self):
        c = {'event_id': 'synthetic-event', 'allowed_operations': ['reports.export'],
             'required_operations': ['reports.export'], 'readonly': True}
        self.assertFalse(task_contract.validate(c, [])['valid'])
        self.assertFalse(task_contract.validate(c, [{'event_id': 'other', 'operation_id': 'reports.export'}])['valid'])
        self.assertFalse(task_contract.validate(c, [{'event_id': 'synthetic-event', 'operation_id': 'roster.lock'}])['valid'])

    def test_wildcard_or_demo_not_accepted_as_confirmation(self):
        for allowed in (['*'], ['demo.check']):
            with self.assertRaises(ValueError): task_contract.validate({'event_id': 'synthetic-event', 'allowed_operations': allowed}, [])


if __name__ == '__main__':
    unittest.main()
