"""'Find missing CC': save_cc's 'missing'/'found' also looks in the user's Downloads and Desktop, including
.package files inside .zip archives there (speedkit.api._cc_side_places, ccbrowser.CCIndex.side_update/side_find),
and the new cc_install_found task installs what turns up into Mods\\Found by Sims Hub as one undoable change.
Reuses tests/test_ccbrowser.py's fake-Sims-4-folder helpers (sim_data, savegame, write_save, pkg, casp); the real
Sims 4 folder is never touched - everything here lives in a temporary folder, and 'Downloads'/'Desktop' are fake
folders too (api.configure(find_places=...))."""
import os
import shutil
import sys
import tempfile
import unittest
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
import test_ccbrowser as TC  # noqa: E402
from speedkit import api, journal as J, usedpack as U  # noqa: E402

# three CAS parts a save wears that are installed nowhere: one turns up in a .zip in Downloads, one as a plain
# .package on Desktop, one in a .zip whose own entry name tries to escape with a '../../' path
ZIP_PART, DESK_PART, EVIL_PART = 0xF00D000000000001, 0xF00D000000000002, 0xF00D000000000003
SLOT = 'Slot_00000002'


def _package_bytes(resources):
    """The bytes of a .package holding `resources` (dbpf.PackageWriter only writes to a real path)."""
    d = tempfile.mkdtemp(prefix='sk_pkgstage_')
    try:
        p = os.path.join(d, 'stage.package')
        TC.pkg(p, resources)
        with open(p, 'rb') as f:
            return f.read()
    finally:
        shutil.rmtree(d, ignore_errors=True)


def make_world(root):
    """A small fake Sims 4 folder (Mods, saves, Tray) plus fake Downloads and Desktop folders: a save whose one
    sim wears three CC parts, none of them installed; Downloads holds a .zip with one of them, and another .zip
    whose one entry is named to try a path traversal; Desktop holds the third as a plain .package."""
    sims = os.path.join(root, 'The Sims 4')
    downloads = os.path.join(root, 'Downloads')
    desktop = os.path.join(root, 'Desktop')
    os.makedirs(os.path.join(sims, 'Mods'))
    os.makedirs(os.path.join(sims, 'saves'))
    os.makedirs(os.path.join(sims, 'Tray'))
    os.makedirs(downloads)
    os.makedirs(desktop)
    with zipfile.ZipFile(os.path.join(downloads, 'CoolHairPack.zip'), 'w') as zf:
        zf.writestr('Loose Hair.package',
                    _package_bytes([((U.T_CASP, 0, ZIP_PART), TC.casp('yfHair_Loose', 2))]))
    TC.pkg(os.path.join(desktop, 'DesktopHair.package'),
          [((U.T_CASP, 0, DESK_PART), TC.casp('yfHair_Desktop', 2))])
    with zipfile.ZipFile(os.path.join(downloads, 'EvilPack.zip'), 'w') as zf:
        zf.writestr('../../evil.package',
                    _package_bytes([((U.T_CASP, 0, EVIL_PART), TC.casp('yfHair_Evil', 2))]))
    zoe = TC.sim_data(0x6101, 0x8001, b'Zoe', b'Fox', [ZIP_PART, DESK_PART, EVIL_PART])
    TC.write_save(os.path.join(sims, 'saves', SLOT + '.save'),
                  TC.savegame('Fox Story', 0x8001, [(0x8001, b'Fox Family')], [zoe]))
    return sims, downloads, desktop


class FindMissingCC(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='sk_findmissing_')
        self.sims, self.downloads, self.desktop = make_world(self.root)
        self.data = os.path.join(self.root, 'data')
        api.configure(sims=self.sims, db_path=os.path.join(self.data, 'library.sqlite'),
                      refs_db=os.path.join(self.data, 'refs.sqlite'), game_ids_db=os.path.join(self.data, 'ids.sqlite'),
                      check_game=False, game_clues=TC.NO_GAME, remember_game=False, opener=lambda p: None,
                      companions_cache=os.path.join(self.data, 'comp.json'),
                      find_places=[('Downloads', self.downloads), ('Desktop', self.desktop)])

    def tearDown(self):
        api.reset()
        api._CC_PICS.clear()
        shutil.rmtree(self.root, ignore_errors=True)

    def found_dir(self):
        return os.path.join(self.sims, 'Mods', 'Found by Sims Hub')

    # ---------------------------------------------------------------- save_cc: found place, name and zip
    def test_save_cc_reports_found_place_and_zip(self):
        r = api.save_cc(SLOT)
        self.assertTrue(r['ok'], r)
        miss = {m['id']: m for m in r['missing']}
        self.assertEqual(set(miss), {'%016X' % ZIP_PART, '%016X' % DESK_PART, '%016X' % EVIL_PART})

        zf = miss['%016X' % ZIP_PART]['found']
        self.assertEqual(zf[0]['place'], 'Downloads')
        self.assertEqual(zf[0]['name'], 'Loose Hair.package')
        self.assertEqual(zf[0]['zip'], 'CoolHairPack.zip')
        self.assertTrue(zf[0]['path'].startswith(os.path.join(self.downloads, 'CoolHairPack.zip') + '|'))

        df = miss['%016X' % DESK_PART]['found']
        self.assertEqual(df[0]['place'], 'Desktop')
        self.assertEqual(df[0]['name'], 'DesktopHair.package')
        self.assertIsNone(df[0]['zip'])
        self.assertEqual(df[0]['path'], os.path.join(self.desktop, 'DesktopHair.package'))

        # the zip's own '../../evil.package' entry name never reaches the user: only its basename does
        ef = miss['%016X' % EVIL_PART]['found']
        self.assertEqual(ef[0]['place'], 'Downloads')
        self.assertEqual(ef[0]['name'], 'evil.package')
        self.assertEqual(ef[0]['zip'], 'EvilPack.zip')

        self.assertEqual(r['counts']['missing'], 3)
        self.assertEqual(r['counts']['found'], 3)

    def test_save_cc_unknown_slot_still_works(self):
        self.assertFalse(api.save_cc('Slot_000000FF')['ok'])

    # ---------------------------------------------------------------- cc_install_found
    def test_install_found_copies_into_mods_and_keeps_the_sources(self):
        before = sorted(os.listdir(self.downloads)) + sorted(os.listdir(self.desktop))
        r = api.cc_install_found(SLOT)
        self.assertTrue(r['ok'], r)
        self.assertEqual(r['left'], 0)
        self.assertEqual(set(r['installed']), {'Loose Hair.package', 'DesktopHair.package', 'evil.package'})
        found = self.found_dir()
        for n in r['installed']:
            self.assertTrue(os.path.isfile(os.path.join(found, n)), n)
        # copied, not moved: the sources are exactly as they were
        self.assertEqual(sorted(os.listdir(self.downloads)) + sorted(os.listdir(self.desktop)), before)
        # a change record names it plainly
        j = next(j for j in api.status()['journals'] if j['id'] == r['journal'])
        self.assertEqual(j['kind'], 'restore')
        self.assertEqual(j['title'], 'Installed missing CC found on this PC')
        # the save no longer counts these as missing once the library notices the new files
        r2 = api.save_cc(SLOT)
        self.assertEqual(r2['counts']['missing'], 0)

    def test_evil_zip_entry_cannot_write_outside_the_found_folder(self):
        r = api.cc_install_found(SLOT)
        self.assertTrue(r['ok'], r)
        self.assertTrue(os.path.isfile(os.path.join(self.found_dir(), 'evil.package')))
        # nowhere else did a file called evil.package (or anything from the traversal) appear
        for bad in (os.path.join(self.sims, 'Mods', 'evil.package'), os.path.join(self.sims, 'evil.package'),
                    os.path.join(self.root, 'evil.package'), os.path.join(self.root, 'The Sims 4', 'evil.package')):
            self.assertFalse(os.path.exists(bad), bad)
        # nothing besides the three expected files was written into Mods
        mods_top = set(os.listdir(os.path.join(self.sims, 'Mods')))
        self.assertEqual(mods_top, {'Found by Sims Hub'})

    def test_second_run_installs_nothing_new(self):
        r1 = api.cc_install_found(SLOT)
        self.assertTrue(r1['ok'], r1)
        self.assertEqual(len(os.listdir(self.found_dir())), 3)
        r2 = api.cc_install_found(SLOT)
        self.assertFalse(r2['ok'])
        self.assertEqual(r2['installed'], [])
        # no duplicate copies were made
        self.assertEqual(len(os.listdir(self.found_dir())), 3)

    def test_undo_removes_the_installed_files(self):
        r = api.cc_install_found(SLOT)
        self.assertTrue(r['ok'], r)
        found = self.found_dir()
        self.assertEqual(len(os.listdir(found)), 3)
        J.undo(r['journal'], home=os.path.join(self.sims, 'SpeedKit'), check_game=False)
        self.assertEqual(os.listdir(found), [])

    def test_refuses_while_the_game_runs(self):
        from unittest import mock
        with mock.patch.object(api, '_game_running', return_value=True):
            r = api.cc_install_found(SLOT)
        self.assertFalse(r['ok'])
        self.assertIn('running', r['message'])
        self.assertFalse(os.path.isdir(self.found_dir()))

    def test_nothing_to_install_when_nothing_is_found(self):
        # a save whose missing part has no copy anywhere stays that way
        os.remove(os.path.join(self.downloads, 'CoolHairPack.zip'))
        os.remove(os.path.join(self.downloads, 'EvilPack.zip'))
        os.remove(os.path.join(self.desktop, 'DesktopHair.package'))
        r = api.cc_install_found(SLOT)
        self.assertFalse(r['ok'])
        self.assertEqual(r['installed'], [])
        self.assertEqual(r['left'], 3)


if __name__ == '__main__':
    unittest.main()
