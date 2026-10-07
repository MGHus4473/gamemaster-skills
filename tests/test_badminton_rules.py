"""Synthetic rule lookup, version boundaries and evidence provenance regressions."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'gamemaster-skill/scripts/badminton_rules.py'
spec = importlib.util.spec_from_file_location('badminton_rules', SCRIPT)
rules = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rules)


class BadmintonKnowledgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = rules.load_knowledge()

    def find(self, query, on='2026-10-07', authority='BWF', **kwargs):
        return rules.search(self.data, query, on, authority, **kwargs)

    def card(self, query, card_id, **kwargs):
        return next(c for c in self.find(query, **kwargs)['matches'] if c['id'] == card_id)

    def test_2026_uses_21_not_published_future_15(self):
        found = self.find('计分')['matches']
        self.assertEqual([c['parameters']['target'] for c in found], [21])
        self.assertEqual(found[0]['parameters']['cap'], 30)

    def test_day_before_change(self):
        self.assertEqual(self.card('计分', 'scoring-21', on='2027-01-03')['parameters']['target'], 21)

    def test_effective_day_changes_all_scoring_fields(self):
        card = self.card('计分', 'scoring-15', on='2027-01-04')
        self.assertEqual(card['parameters'], dict(mode='points', best_of=3, target=15, win_by=2, cap=21))
        self.assertNotIn('scoring-21', [c['id'] for c in self.find('计分', on='2027-01-04')['matches']])

    def test_interval_change_is_not_left_at_11(self):
        p = self.card('换边', 'intervals-15', on='2027-01-04')['parameters']
        self.assertEqual((p['interval_at'], p['deciding_change_at']), (8, 8))
        self.assertEqual((p['interval_seconds'], p['between_games_seconds']), (60, 120))

    def test_old_interval_remains_11(self):
        self.assertEqual(self.card('换边', 'intervals-21')['parameters']['interval_at'], 11)

    def test_future_comparison_explicitly_labelled(self):
        card = self.card('计分', 'scoring-15', include_inactive=True)
        self.assertEqual(card['status'], 'future')
        self.assertFalse(card['rule_evidence'])

    def test_post_check_date_warns_even_when_plan_effective(self):
        result = self.find('计分', on='2027-01-04')
        self.assertTrue(any('晚于' in w for w in result['warnings']))
        self.assertEqual(result['checked_on'], '2026-10-07')

    def test_date_before_available_rules_does_not_backport(self):
        result = self.find('计分', on='2024-01-01')
        self.assertEqual(result['matches'], [])
        self.assertTrue(result['needs_primary_source'])

    def test_citations_selected_for_date(self):
        for on, source in [('2026-10-07', 'bwf-laws-2025'), ('2027-01-04', 'bwf-laws-2027')]:
            with self.subTest(on=on):
                card = self.card('发球高度', 'serve-height-spin', on=on)
                self.assertEqual([c['source'] for c in card['citations']], [source])

    def test_cba_is_not_silently_replaced_with_bwf(self):
        result = self.find('发球', authority='CBA')
        self.assertFalse(result['needs_primary_source'])
        self.assertTrue(result['needs_applicability_check'])
        self.assertTrue(result['matches'])
        self.assertTrue(all(c['organization'] == 'CBA' for m in result['matches'] for c in m['citations']))

    def test_reviewed_old_book_is_not_automatically_current(self):
        card = self.card('计分', 'cba-2023-score', authority='CBA')
        self.assertTrue(card['reviewed_edition_evidence'])
        self.assertFalse(card['rule_evidence'])
        self.assertEqual(card['status'], 'historical_reference')
        self.assertEqual(card['parameters']['target'], 21)
        citation = card['citations'][0]
        self.assertEqual((citation['pages'], citation['printed_pages']), ([14], [7]))
        self.assertIsNone(citation['url'])
        self.assertEqual(citation['cache_file'], 'cba-book-2023.pdf')

    def test_2023_reference_does_not_erase_2027_bwf_change(self):
        card = self.card('计分', 'cba-2023-score', authority='CBA', on='2027-01-04')
        self.assertFalse(card['rule_evidence'])
        self.assertEqual(self.card('计分', 'scoring-15', on='2027-01-04')['parameters']['target'], 15)

    def test_book_not_backdated_before_publication_month(self):
        result = self.find('2023', authority='CBA', on='2023-07-31')
        self.assertEqual(result['matches'], [])
        result = self.find('2023', authority='CBA', on='2023-07-31', include_inactive=True)
        self.assertTrue(result['matches'])
        self.assertFalse(any(m['reviewed_edition_evidence'] for m in result['matches']))

    def test_scan_map_accounts_for_missing_pages(self):
        source = next(s for s in self.data['sources'] if s['id'] == 'cba-book-2023')
        self.assertEqual([rules.printed_page(source, p) for p in [290, 291, 305, 306, 334]],
                         [286, 288, 302, 304, 332])
        self.assertEqual(source['confirmed_content_missing'], [287, 303])
        self.assertEqual(source['verification'], 'partial_scan_reviewed')

    def test_scan_rejects_unreviewed_or_mislabelled_citation(self):
        for bad in ('unreviewed_page', 'wrong_printed_page', 'unreviewed_card', 'overlapping_map'):
            data = copy.deepcopy(self.data)
            card = next(c for c in data['cards'] if c['id'] == 'cba-2023-score')
            source = next(s for s in data['sources'] if s['id'] == 'cba-book-2023')
            if bad == 'unreviewed_page':
                card['citations'][0]['pages'] = [200]
            elif bad == 'wrong_printed_page':
                card['citations'][0]['printed_pages'] = [8]
            elif bad == 'unreviewed_card':
                card['review_status'] = 'unreviewed_ocr'
            else:
                source['page_segments'].append(source['page_segments'][0])
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / 'knowledge.json'
                path.write_text(json.dumps(data), encoding='utf-8')
                with self.assertRaises(ValueError):
                    rules.load_knowledge(path)

    def test_cba_2025_notice_not_full_rulebook(self):
        card = self.card('2025规则书', 'cba-edition', authority='CBA')
        self.assertEqual(card['status'], 'reference_only')
        self.assertFalse(card['rule_evidence'])
        status = rules.status(self.data, '2026-10-07', 'CBA')
        source = next(s for s in status['sources'] if s['id'] == 'cba-book-2025')
        self.assertEqual(source['status'], 'unavailable')
        self.assertIsNone(source['effective_from'])

    def test_old_cba_summary_not_current_law(self):
        card = self.card('计分', 'cba-historical-score', authority='CBA')
        self.assertEqual(card['status'], 'historical_reference')
        self.assertFalse(card['rule_evidence'])

    def test_old_cba_article_not_available_before_publication(self):
        result = self.find('简易版', on='2021-01-01', authority='CBA')
        self.assertEqual(result['matches'], [])

    def test_unknown_question_requires_source(self):
        result = self.find('U7出生日期能否跨年龄报名')
        self.assertTrue(result['needs_primary_source'])
        self.assertFalse(result['matches'])

    def test_no_fake_cba_clause_ids_from_bwf(self):
        card = self.card('发球', 'cba-historical-service', authority='CBA')
        self.assertEqual(card['citations'][0]['clause'], '五；八至十一')

    def test_rest_uses_2026_gcr_number_not_old_cross_reference(self):
        card = self.card('场间休息', 'between-matches')
        gcr = next(c for c in card['citations'] if c['source'] == 'bwf-gcr-2026')
        self.assertEqual(gcr['clause'], '1；11.4')
        self.assertIn(26, gcr['pages'])

    def test_mixed_source_card_not_backported_to_old_date(self):
        result = self.find('场间休息', on='2026-01-01')
        self.assertNotIn('between-matches', [c['id'] for c in result['matches']])

    def test_precise_ruling_topics_have_distinct_evidence(self):
        cases = [
            ('发球旋转', 'serve-height-spin', '9.1.5–9.1.6'),
            ('发球擦网', 'service-net', '9.1；13.2.1–13.2.2'),
            ('触网', 'net-touch', '13.4.1；15'),
            ('过网击球', 'over-net', '13.4.2–13.4.5'),
            ('连击', 'double-hit', '13.3.6–13.3.8'),
            ('发球区错误', 'service-error', '12.1–12.2；13.2.3'),
            ('同分', 'group-ranking', '16.2.1–16.2.4.2'),
            ('受伤', 'injury', '5.14.1–5.14.3'),
        ]
        for query, card_id, clause in cases:
            with self.subTest(query=query):
                card = self.card(query, card_id)
                self.assertTrue(card['rule_evidence'])
                self.assertIn(clause, [c['clause'] for c in card['citations']])

    def test_reviewed_sources_have_real_hosts_and_locators(self):
        result = self.find('计分')
        citation = result['matches'][0]['citations'][0]
        self.assertEqual(citation['version'], '5.0(2)')
        self.assertIn('extranet.bwf.sport/', citation['url'])
        self.assertEqual(citation['pages'], [5])

    def test_date_and_empty_query_errors(self):
        for when in ['2026-2-3', '2026-02-30', 'yesterday']:
            with self.subTest(when=when), self.assertRaises(ValueError):
                self.find('计分', on=when)
        with self.assertRaises(ValueError):
            self.find('   ')
        with self.assertRaises(ValueError):
            self.find('计分', limit=0)

    def test_fullwidth_service_height_query(self):
        self.assertEqual(self.card('１．１５米', 'serve-height-spin')['id'], 'serve-height-spin')

    def test_15_point_question_does_not_silently_apply_future_rules(self):
        result = self.find('2026年是不是已经改15分了')
        self.assertEqual(result['matches'][0]['id'], 'scoring-21')
        self.assertEqual(result['matches'][0]['parameters']['target'], 21)

    def test_cache_change_and_missing_fail_without_modification(self):
        raw = b'synthetic rule snapshot'
        manifest = {'sources': [{'id': 'synthetic', 'cache_file': 'rules.txt',
                                'sha256': hashlib.sha256(raw).hexdigest()}]}
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            self.assertFalse(rules.verify_cache(manifest, directory)['ok'])
            file = directory / 'rules.txt'
            file.write_bytes(raw)
            self.assertTrue(rules.verify_cache(manifest, directory)['ok'])
            file.write_bytes(b'changed rules')
            result = rules.verify_cache(manifest, directory)
            self.assertFalse(result['ok'])
            self.assertEqual(result['artifacts'][0]['status'], 'changed_review_required')
            self.assertEqual(file.read_bytes(), b'changed rules')

    def test_source_validation_rejects_missing_evidence_and_wrong_pages(self):
        for bad in ('unknown_source', 'wrong_page', 'duplicate_source'):
            data = copy.deepcopy(self.data)
            if bad == 'unknown_source':
                data['cards'][0]['citations'][0]['source'] = 'missing'
            elif bad == 'wrong_page':
                data['cards'][0]['citations'][0]['pages'] = [500]
            else:
                data['sources'].append(data['sources'][0])
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as temp:
                p = Path(temp) / 'knowledge.json'
                p.write_text(json.dumps(data), encoding='utf-8')
                with self.assertRaises((KeyError, ValueError)):
                    rules.load_knowledge(p)

    def test_cli_operates_outside_skill_directory(self):
        proc = subprocess.run([sys.executable, str(SCRIPT), 'search', '计分', '--on',
                               '2027-01-04', '--authority', 'BWF'], cwd=tempfile.gettempdir(),
                              capture_output=True, text=True, check=True)
        result = json.loads(proc.stdout)
        self.assertEqual(result['matches'][0]['parameters']['target'], 15)


if __name__ == '__main__':
    unittest.main()
