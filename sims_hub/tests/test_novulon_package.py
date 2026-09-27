"""Tests for tools/build_novulon_package.py. Pure 3.12, no game (Tier 1).

Nothing under E:\\The Sims 4 or the real Mods folder is touched; dist/Novulon_Tuning.package is written to
a scratch copy under E:\\speedkit_test (or the system temp dir), never to the real dist/ path a test run
might otherwise clobber.
"""
import os
import shutil
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(PROJECT)
sys.path.insert(0, PROJECT)
# wicked_animator/backend/texfmt.py has no intra-package imports, but is still a flat-style module, not a
# proper package member - put its folder on sys.path directly, same as the other novulon_* tests.
sys.path.insert(0, os.path.join(REPO_ROOT, 'wicked_animator', 'backend'))

from tools import build_novulon_package as bnp  # noqa: E402
from tools import novulon_ids as ids  # noqa: E402
from speedkit.dbpf import Package  # noqa: E402
import texfmt  # noqa: E402

SCRATCH = r'E:\speedkit_test\novulon_package' if os.path.isdir('E:\\') else tempfile.gettempdir()


class BuildTests(unittest.TestCase):
    def setUp(self):
        os.makedirs(SCRATCH, exist_ok=True)
        self.dist = os.path.join(SCRATCH, 'Novulon_Tuning_test_%d.package' % os.getpid())
        self.addCleanup(lambda: os.path.exists(self.dist) and os.remove(self.dist))

    def test_asset_exists_and_is_the_right_size(self):
        self.assertTrue(os.path.isfile(bnp.ICON_PNG_32), 'design-phase icon PNG missing from the repo')
        rgba = bnp.load_icon_rgba()
        self.assertEqual(len(rgba), 32 * 32 * 4)

    def test_build_writes_three_resources(self):
        r = bnp.build(dist=self.dist)
        self.assertEqual(r['dist'], self.dist)
        self.assertTrue(os.path.isfile(self.dist))
        self.assertEqual(len(r['entries']), 3)
        self.assertEqual(bnp.verify(self.dist), [])

    def test_resources_are_at_the_expected_keys(self):
        bnp.build(dist=self.dist)
        with Package(self.dist) as p:
            byi = {e.i: e for e in p.entries}
            self.assertEqual(byi[ids.INTERACTION_OPEN_MENU].t, bnp.T_INTERACTION)
            self.assertEqual(byi[ids.STBL_MAIN_EN].t, bnp.T_STBL)
            self.assertEqual(byi[ids.ICON_PIE_MENU_32].t, bnp.T_DDS)
            self.assertEqual(len(p.entries), 3)

    def test_interaction_xml_parses_and_points_at_the_right_ids(self):
        bnp.build(dist=self.dist)
        with Package(self.dist) as p:
            e = [x for x in p.entries if x.t == bnp.T_INTERACTION][0]
            root = ET.fromstring(p.read(e))
            self.assertEqual(root.get('c'), 'ImmediateSuperInteraction')
            self.assertEqual(root.get('m'), 'interactions.base.immediate_interaction')
            display = int(root.findtext("T[@n='display_name']"), 16)
            self.assertEqual(display, ids.STR_MENU_TITLE)
            # the shapes the game's tuning loader needs (as MC Command Center's working entry has them): a field
            # written flat is dropped, and a flat basic_extras made the game raise "'NoneType' has no 'factory'"
            icon_field = root.findtext("V[@n='pie_menu_icon']/V[@t='resource_key']/U[@n='resource_key']/T[@n='key']")
            self.assertTrue(icon_field and icon_field.lower().startswith('2f7d0004:80000000:'), icon_field)
            self.assertEqual(int(icon_field.split(':')[-1], 16), ids.ICON_PIE_MENU_32)
            self.assertIsNone(root.find("T[@n='pie_menu_icon']"))
            command = root.findtext("L[@n='basic_extras']/V[@t='do_command']/U[@n='do_command']/T[@n='command']")
            self.assertEqual(command, bnp.COMMAND)
            self.assertEqual(root.findtext("E[@n='target_type']"), 'OBJECT')
            self.assertIsNone(root.find("T[@n='target_type']"))
            self.assertEqual(bnp.verify(self.dist), [])

    def test_the_entry_runs_a_command_the_mod_registers(self):
        # the first build ran 'novulon.open_menu', which nothing registered: clicking Novulon did nothing
        import re
        src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'ingame', 'novulon', 'commands.py'), encoding='utf-8').read()
        registered = re.findall(r"@sims4\.commands\.Command\('([^']+)'", src)
        self.assertIn(bnp.COMMAND, registered)

    def test_stbl_has_the_two_menu_strings(self):
        from tools import novulon_stbl
        bnp.build(dist=self.dist)
        with Package(self.dist) as p:
            e = [x for x in p.entries if x.t == bnp.T_STBL][0]
            strings = novulon_stbl.read_stbl(p.read(e))
            self.assertEqual(strings[ids.STR_MENU_TITLE], bnp.MENU_TITLE)
            self.assertEqual(strings[ids.STR_MENU_HOVER], bnp.MENU_HOVER)

    def test_icon_resource_is_a_valid_32x32_raw_dds(self):
        bnp.build(dist=self.dist)
        with Package(self.dist) as p:
            e = [x for x in p.entries if x.t == bnp.T_DDS][0]
            data = p.read(e)
            info = texfmt.dds_info(data)
            self.assertEqual((info['width'], info['height'], info['format']), (32, 32, 'RAW'))

    def test_verify_catches_a_display_name_mismatch(self):
        bnp.build(dist=self.dist)
        # tamper with the STR_MENU_TITLE constant just for this one check, then restore it
        real = ids.STR_MENU_TITLE
        try:
            ids.STR_MENU_TITLE = real ^ 0xFF
            self.assertIn('display_name does not match STR_MENU_TITLE', bnp.verify(self.dist))
        finally:
            ids.STR_MENU_TITLE = real

    def test_rebuild_overwrites_cleanly(self):
        bnp.build(dist=self.dist)
        r2 = bnp.build(dist=self.dist)
        self.assertEqual(bnp.verify(r2['dist']), [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
