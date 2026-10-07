"""Synthetic OCR index behavior; no real rulebook text is bundled in tests."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('rulebook_scan', Path(__file__).resolve().parents[1] /
                                             'gamemaster-skill/scripts/rulebook_scan.py')
scan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scan)


class ScanIndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'pages').mkdir()
        (self.root / 'manifest.json').write_text(json.dumps({
            'source_sha256': 'a' * 64, 'status': 'incomplete'}), encoding='utf-8')
        for n, text in [(1, '示例\n检索：１２.５'), (2, '示例 第二页')]:
            (self.root / 'pages' / f'{n:04}.json').write_text(json.dumps(
                {'pdf_page': n, 'text': text}), encoding='utf-8')

    def test_normalized_multiline_lookup_keeps_original_page(self):
        found = scan.search(self.root, '示例检索:12.5')
        self.assertEqual([p['pdf_page'] for p in found['matches']], [1])
        self.assertTrue(found['needs_visual_review'])
        self.assertEqual(found['index_status'], 'incomplete')
        self.assertEqual(found['matches'][0]['review_status'], 'unreviewed_ocr')

    def test_no_match_never_certifies_absence(self):
        found = scan.search(self.root, '缺失内容')
        self.assertEqual(found['matches'], [])
        self.assertTrue(found['needs_visual_review'])

    def test_limits_and_empty_query(self):
        self.assertEqual(len(scan.search(self.root, '示例', 1)['matches']), 1)
        for query, limit in [('', 1), ('示例', 0)]:
            with self.assertRaises(ValueError):
                scan.search(self.root, query, limit)


if __name__ == '__main__':
    unittest.main()
