"""Tests for tools/build_novulon_package.py. Pure 3.12, no game (Tier 1).

The package is written to a scratch copy in the temp folder, never to the real dist/ path or the Mods folder.
"""
import os
import re
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(PROJECT)
sys.path.insert(0, PROJECT)
# wicked_animator/backend/texfmt.py is a flat-style module - put its folder on sys.path directly.
sys.path.insert(0, os.path.join(REPO_ROOT, 'wicked_animator', 'backend'))

from tools import build_novulon_package as bnp  # noqa: E402
from tools import novulon_ids as ids  # noqa: E402
from tools import novulon_stbl, novulon_tuning  # noqa: E402
from tools.novulon_ids.bp13_package_build import icon_instance, stbl_id  # noqa: E402
from tools.novulon_glyphs import NAMES  # noqa: E402
from speedkit.dbpf import Package  # noqa: E402
import texfmt  # noqa: E402

SCRATCH = tempfile.gettempdir()


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.dist = os.path.join(SCRATCH, 'Novulon_Tuning_test_%d.package' % os.getpid())
        self.addCleanup(lambda: os.path.exists(self.dist) and os.remove(self.dist))

    def built(self):
        bnp.build(dist=self.dist)
        return Package(self.dist)

    def test_every_icon_picture_is_there_at_its_size(self):
        self.assertEqual(len(bnp.load_rgba(bnp.ICON_PNG_32, 32)), 32 * 32 * 4)
        for name in NAMES:
            path = os.path.join(bnp.ICON_DIR, name + '.png')
            self.assertEqual(len(bnp.load_rgba(path, bnp.ICON_SIZE)), bnp.ICON_SIZE ** 2 * 4, name)

    def test_build_writes_entries_strings_and_icons_and_verifies(self):
        r = bnp.build(dist=self.dist)
        self.assertEqual(len(r['entries']), 2 + len(ids.LOCALES) + 1 + len(NAMES))
        self.assertEqual(len(set(r['entries'])), len(r['entries']))          # no key twice
        self.assertEqual(bnp.verify(self.dist), [])

    def test_computer_entry_opens_the_menu_and_sim_entry_passes_the_sim(self):
        with self.built() as p:
            by = {(e.t, e.i): e for e in p.entries}
            for inst, command, target in ((ids.INTERACTION_OPEN_MENU, 'novulon.menu', False),
                                          (ids.INTERACTION_SIM_MENU, 'novulon.sim', True)):
                root = ET.fromstring(p.read(by[(bnp.T_INTERACTION, inst)]))
                self.assertEqual(novulon_tuning.command_of(root), command)
                self.assertEqual(novulon_tuning.passes_target(root), target)
                self.assertEqual(int(root.findtext("T[@n='display_name']"), 16), ids.STR_MENU_TITLE)
                self.assertTrue(novulon_tuning.icon_key_of(root).upper().endswith('%016X' % ids.ICON_PIE_MENU_32))

    def test_the_mod_registers_both_commands_the_entries_run(self):
        with open(os.path.join(PROJECT, 'ingame', 'novulon', 'entry.py'), encoding='utf-8') as f:
            src = f.read()
        for command in (bnp.MENU_COMMAND, bnp.SIM_COMMAND):
            self.assertRegex(src, r"Command\(\s*'%s'" % re.escape(command))

    def test_every_language_has_the_label(self):
        with self.built() as p:
            by = {(e.t, e.i): e for e in p.entries}
            for loc in ids.LOCALES:
                table = novulon_stbl.read_stbl(p.read(by[(bnp.T_STBL, stbl_id('Novulon_Strings', loc))]))
                self.assertEqual(table[ids.STR_MENU_TITLE], 'Novulon', hex(loc))

    def test_icons_are_raw_dds_at_their_sizes(self):
        with self.built() as p:
            by = {(e.t, e.i): e for e in p.entries}
            info = texfmt.dds_info(p.read(by[(bnp.T_DDS, ids.ICON_PIE_MENU_32)]))
            self.assertEqual((info['width'], info['height'], info['format']), (32, 32, 'RAW'))
            for name in ('logo', 'back', 'cheats'):
                info = texfmt.dds_info(p.read(by[(bnp.T_DDS, icon_instance(name))]))
                self.assertEqual((info['width'], info['height'], info['format']), (128, 128, 'RAW'), name)

    def test_verify_catches_a_wrong_label_key(self):
        bnp.build(dist=self.dist)
        real = ids.STR_MENU_TITLE
        try:
            ids.STR_MENU_TITLE = real ^ 0xFF
            self.assertTrue(any('wrong label key' in x for x in bnp.verify(self.dist)))
        finally:
            ids.STR_MENU_TITLE = real

    def test_rebuild_overwrites_cleanly(self):
        bnp.build(dist=self.dist)
        r2 = bnp.build(dist=self.dist)
        self.assertEqual(bnp.verify(r2['dist']), [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
