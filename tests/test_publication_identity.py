"""Synthetic, offline tests: no credentials, actual event IDs or network calls."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'ptty-skill/scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


publication = load('publication_packet')
qr = load('qr_export')


def source():
    return {
        'schema_version': 1,
        'event': {'id': 'SYNTHETIC-EVENT', 'name': '合成测试赛', 'sport': 'badminton'},
        'source_version': 'synthetic-v1',
        'baseline': {'event_id': 'SYNTHETIC-EVENT', 'captured_at': '2026-01-01T00:00:00Z',
                     'event': {'SSID': 'SYNTHETIC-EVENT', 'QSLXID': 'SPORT-A', 'QSLXMC': '羽毛球'},
                     'client': {}},
        'operations': [{'kind': 'materials_all', 'scope': 'all_projects', 'types': ['ISZXC'], 'visible': True}],
        'sport_identity': {'source': 'current_page', 'captured_at': '2026-01-01T00:00:00Z',
                           'page_url': 'https://www.ptty.com.cn/#/index',
                           'module_sport': 'badminton', 'selected_id': 'SPORT-A',
                           'options': [{'id': 'SPORT-A', 'label': '羽毛球', 'sport': 'badminton'}]},
    }


class PublicationIdentityTests(unittest.TestCase):
    def packet(self, spec):
        with tempfile.TemporaryDirectory() as root:
            return publication.compile_packet(spec, root)[0]

    def test_missing_evidence_is_a_write_blocked_offline_draft(self):
        spec = source(); del spec['sport_identity']
        packet = self.packet(spec)
        self.assertEqual(packet['sport_identity']['status'], 'unverified')
        self.assertTrue(packet['sport_identity']['write_blocked'])
        self.assertTrue(all(action['requires_sport_identity_check'] and action['pending_bindings']
                            for action in packet['actions']))
        self.assertEqual(packet['business_writes'], 0)

    def test_consistent_current_page_mapping_keeps_live_recheck(self):
        spec = source(); original = deepcopy(spec)
        packet = self.packet(spec)
        self.assertEqual(packet['sport_identity']['status'], 'observed_consistent')
        self.assertFalse(packet['sport_identity']['write_blocked'])
        self.assertTrue(packet['sport_identity']['requires_live_recheck'])
        self.assertEqual(spec, original)
        self.assertFalse(packet['live_execution_verified'])

    def test_conflicting_readback_label_blocks_even_without_mapping(self):
        spec = source(); del spec['sport_identity']
        spec['baseline']['event']['QSLXMC'] = '乒乓球'
        with self.assertRaisesRegex(ValueError, 'Sport identity conflict'):
            self.packet(spec)

    def test_numeric_code_has_no_hardcoded_sport_meaning(self):
        for arbitrary_id in ('0', '1', '7', 'SPORT-A'):
            spec = source()
            spec['baseline']['event']['QSLXID'] = arbitrary_id
            spec['sport_identity']['selected_id'] = arbitrary_id
            spec['sport_identity']['options'][0]['id'] = arbitrary_id
            self.assertFalse(self.packet(spec)['sport_identity']['write_blocked'])

    def test_module_and_selected_option_conflicts_block(self):
        for field, value in [('module_sport', 'pickleball'), ('selected_id', 'SPORT-B')]:
            spec = source(); spec['sport_identity'][field] = value
            with self.assertRaisesRegex(ValueError, 'Sport identity conflict'):
                self.packet(spec)
        spec = source(); spec['sport_identity']['options'][0]['label'] = '网球'
        with self.assertRaisesRegex(ValueError, 'Sport identity conflict'):
            self.packet(spec)

    def test_wrong_event_or_numeric_target_blocks(self):
        spec = source(); spec['baseline']['event']['SSID'] = 'SYNTHETIC-OTHER'
        with self.assertRaisesRegex(ValueError, 'different event'):
            self.packet(spec)
        spec = source(); spec['baseline']['event']['QSLXID'] = 'OTHER'
        with self.assertRaisesRegex(ValueError, 'QSLXID'):
            self.packet(spec)

    def test_sport_evidence_requires_current_page_without_query(self):
        for page in ('http://www.ptty.com.cn/#/index', 'https://wap.ptty.com.cn/wap/',
                     'https://www.ptty.com.cn:444/', 'https://www.ptty.com.cn/?session=synthetic',
                     'https://www.ptty.com.cn/#/index?ssid=synthetic',
                     ''.join(('https://', 'synthetic', ':', 'synthetic', '@', 'www.ptty.com.cn/'))):
            spec = source(); spec['sport_identity']['page_url'] = page
            with self.assertRaises(ValueError): self.packet(spec)
        spec = source(); spec['sport_identity']['source'] = 'remembered_default'
        with self.assertRaisesRegex(ValueError, 'current page'): self.packet(spec)

    def test_duplicate_options_are_not_accepted(self):
        spec = source(); spec['sport_identity']['options'] *= 2
        with self.assertRaisesRegex(ValueError, 'Duplicate'): self.packet(spec)

    def test_creation_id_is_checked_before_request_generation(self):
        spec = source(); spec['event']['id'] = ''; spec['baseline'] = {}
        spec['operations'] = [{'kind': 'create_event', 'fields': {'QSLXID': 'OTHER'}}]
        with self.assertRaisesRegex(ValueError, 'QSLXID'): self.packet(spec)

    def test_packet_validation_exposes_the_blocker(self):
        spec = source(); del spec['sport_identity']
        with tempfile.TemporaryDirectory() as root:
            packet, _ = publication.compile_packet(spec, root)
            path = Path(root) / 'packet.json'; path.write_text(json.dumps(packet), encoding='utf-8')
            result = publication.validate_packet(path)
        self.assertTrue(result['valid'])
        self.assertTrue(result['sport_write_blocked'])

    def test_editor_rejects_encoded_and_fragment_private_urls_without_echoing_values(self):
        for url in ('https://example.invalid/?%74oken=synthetic-private-value',
                    'https://example.invalid/#/x?SESSIONID=synthetic-private-value',
                    'https://example.invalid/#password=synthetic-private-value',
                    'https://example.invalid/?%75isStr=synthetic-private-value'):
            with self.assertRaises(ValueError) as caught:
                publication.EditorFragment({}).feed('<a href="' + url + '">文件</a>')
            self.assertNotIn('synthetic-private-value', str(caught.exception))

    def test_qr_retains_public_protocol_and_rejects_private_parameters(self):
        url = 'http://wap.ptty.com.cn/wap/#/xmIndex?ssid=SYNTHETIC'
        self.assertEqual(qr.validate_event_url(url), url)
        # Runtime synthetic counterexamples preserve the strict release scan.
        for tail in ('&' + key + chr(61) + 'synthetic' for key in ('token', '%70assword', 'UISSTR')):
            with self.assertRaises(ValueError): qr.validate_event_url(url + tail)


if __name__ == '__main__':
    unittest.main(verbosity=2)
