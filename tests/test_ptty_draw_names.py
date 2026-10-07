"""Observed display separators must not weaken doubles identity checks."""
import importlib.util
from pathlib import Path
import sys
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'ptty-skill/scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('ptty_draw_names', SCRIPTS / 'export_draw.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DrawNames(unittest.TestCase):
    def test_doubles_preserve_members_across_display_separators(self):
        for kind in ('MD', 'WD', 'XD', 'SD'):
            self.assertTrue(module.same_entry_name('甲／乙', '甲 / 乙', kind))
        self.assertTrue(module.same_entry_name('Ann Lee／Bo Wu', 'Ann Lee / Bo Wu', 'WD'))

    def test_wrong_partner_or_reversed_order_rejected(self):
        for value in ('甲 / 丙', '乙 / 甲', '甲 / 乙 / 丙', '甲 /', '甲乙'):
            self.assertFalse(module.same_entry_name('甲／乙', value, 'MD'))

    def test_single_and_unknown_types_keep_exact_identity(self):
        for kind in ('MS', 'WS', 'SS', 'TEAM', ''):
            self.assertFalse(module.same_entry_name('甲／乙', '甲 / 乙', kind))
        self.assertFalse(module.same_entry_name('Ann Lee／Bo Wu', 'AnnLee / Bo Wu', 'MD'))
        self.assertTrue(module.same_entry_name('甲', '甲', 'MS'))


if __name__ == '__main__':
    unittest.main()
