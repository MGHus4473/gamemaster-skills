"""Synthetic adversarial examples; no real account or athlete data is used."""
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import release_check as gate


class PublicationGateTests(unittest.TestCase):
    def test_sensitive_assignment_detected_without_value_disclosure(self):
        secret = "made-up-" + "credential-71"
        text = json.dumps({"password": secret})
        result = gate.scan_text(text, "ptty-skill/example.json")
        self.assertEqual(result[0]["rule"], "literal_credential_or_session")
        self.assertNotIn(secret, json.dumps(result))

    def test_generic_variables_and_public_endpoint_are_allowed(self):
        text = '\n'.join([
            'const token = tokens.shift();',
            'https://www.ptty.com.cn/',
            'http://wap.ptty.com.cn/trialWapApi',
            'password: "<password supplied interactively>"',
            'username: "example_user"',
            'MD5(inner + "public-protocol-marker")',
        ])
        self.assertEqual(gate.scan_text(text, "ptty-skill/references/site.md"), [])

    def test_concrete_public_event_identifier_is_not_release_sample(self):
        text = "https://example.test/?ssid=" + "ab" * 20
        self.assertEqual(gate.scan_text(text, "ptty-skill/example.md")[0]["rule"], "concrete_event_url")

    def test_platform_record_identifier_is_detected(self):
        text = "SS" + "250101" + "XX" + "000001"
        self.assertEqual(gate.scan_text(text, "ptty-skill/example.md")[0]["rule"], "platform_record_id")

    def test_signed_query_detected(self):
        text = "https://example.test/export?" + "uisStr" + chr(61) + "synthetic-signature"
        self.assertEqual(gate.scan_text(text, "ptty-skill/example.md")[0]["rule"], "signed_url")

    def test_personal_workspace_paths_detected(self):
        text = "/home/" + "sample-person/work/roster.xlsx"
        self.assertEqual(gate.scan_text(text, "README.md")[0]["rule"], "personal_absolute_path")

    def test_private_denylist_catches_names_without_disclosure(self):
        name = "虚构运动员" + "甲"
        result = gate.scan_text("报名人: " + name, "gamemaster-skill/example.md", (name,))
        self.assertEqual(result[0]["rule"], "private_denylist_match")
        self.assertNotIn(name, json.dumps(result, ensure_ascii=False))

    def test_archive_scans_inner_text_and_metadata(self):
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as archive:
            archive.writestr("xl/sharedStrings.xml", '<t>' + json.dumps({"password": str(71) + "-synthetic"}) + '</t>')
            archive.writestr("docProps/core.xml", '<core><creator>Fictional Person</creator></core>')
            archive.writestr("docProps/custom.xml", '<custom/>')
        rules = {i["rule"] for i in gate.scan_archive(data.getvalue(), "template.xlsx", ())}
        self.assertEqual(rules, {"literal_credential_or_session", "personal_document_author", "unreviewed_custom_document_metadata"})

    def test_clean_blank_workbook_relationships_are_allowed(self):
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as archive:
            archive.writestr("_rels/.rels", '<Relationships/>')
            archive.writestr("docProps/core.xml", '<core><creator>gamemaster</creator></core>')
            archive.writestr("xl/worksheets/sheet1.xml", '<worksheet><t>姓名*</t></worksheet>')
        self.assertEqual(gate.scan_archive(data.getvalue(), "blank.xlsx", ()), [])

    def test_archive_paths_are_never_extracted(self):
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as archive:
            archive.writestr("../outside.txt", 'harmless')
            archive.writestr("embedded.bin", b'\x00\xff')
        rules = {i["rule"] for i in gate.scan_archive(data.getvalue(), "sample.zip", ())}
        self.assertEqual(rules, {"unsafe_archive_path", "unreviewed_binary_member"})

    def test_large_archive_refused(self):
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("data.txt", '0' * (gate.MAX_MEMBER_BYTES + 1))
        self.assertEqual(gate.scan_archive(data.getvalue(), "sample.zip", ())[0]["rule"], "uninspectable_archive_member")

    def test_default_scope_excludes_private_docs_but_strict_scope_flags_them(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'README.md').write_text('Public skills')
            (root / 'docs').mkdir()
            (root / 'docs' / 'private.md').write_text('local only')
            self.assertTrue(gate.scan_tree(root)["passed"])
            self.assertFalse(gate.scan_tree(root, strict=True)["passed"])

    def test_public_directory_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'private').mkdir()
            (root / 'gamemaster-skill').symlink_to(root / 'private', target_is_directory=True)
            self.assertFalse(gate.scan_tree(root)["passed"])

    def test_session_filename_is_rejected_in_allowed_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'ptty-skill').mkdir()
            (root / 'ptty-skill' / ('browser-' + 'session.json')).write_text('{}')
            self.assertIn('private_path', [i['rule'] for i in gate.scan_tree(root)['findings']])

    def test_ignored_but_tracked_private_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            (root / 'docs').mkdir()
            (root / 'docs' / 'private.md').write_text('synthetic fixture')
            (root / '.gitignore').write_text('/docs/\n')
            subprocess.run(['git', '-C', str(root), 'add', '-f', 'docs/private.md'], check=True)
            result = gate.scan_tree(root, tracked=True)
            self.assertFalse(result['passed'])
            self.assertIn('outside_public_allowlist', [i['rule'] for i in result['findings']])

    def test_staged_secret_is_detected_even_when_worktree_was_cleaned(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            source = root / 'README.md'
            source.write_text(json.dumps({"password": str(7) + "-staged-secret"}))
            subprocess.run(['git', '-C', str(root), 'add', 'README.md'], check=True)
            source.write_text('Cleaned working tree')
            self.assertTrue(gate.scan_tree(root, tracked=True)['passed'])
            self.assertFalse(gate.scan_tree(root, staged=True)['passed'])

    def test_staged_symlink_rejected_even_if_worktree_replaced_it(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            source = root / 'README.md'
            source.symlink_to('unpublished.txt')
            subprocess.run(['git', '-C', str(root), 'add', 'README.md'], check=True)
            source.unlink()
            source.write_text('Regular working tree file')
            result = gate.scan_tree(root, staged=True)
            self.assertFalse(result['passed'])
            self.assertEqual(result['findings'][0]['rule'], 'nonregular_or_unmerged_git_entry')

    def test_parent_repository_does_not_count_as_release_repository(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            (root / 'child').mkdir()
            with self.assertRaises(ValueError):
                gate.git_tracked(root / 'child')


if __name__ == '__main__':
    unittest.main()
