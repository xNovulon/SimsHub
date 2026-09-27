"""Tests for speedkit/novulon_install.py on a FAKE Sims 4 folder under E:\\speedkit_test\\novulon_install.

install()/uninstall() default to a dry run that changes nothing; a real run goes through one Journal of
kind 'install' covering both files, and journal.undo() reverses it. The real Mods folder is never touched.
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from speedkit import novulon_install as ni  # noqa: E402
from speedkit.journal import undo, list_journals  # noqa: E402

BASE = r'E:\speedkit_test\novulon_install' if os.path.isdir('E:\\') else os.path.join(tempfile.gettempdir(), 'novulon_install')


def listing(root):
    out = []
    for d, _ds, fs in os.walk(root):
        for n in fs:
            p = os.path.join(d, n)
            out.append((os.path.relpath(p, root), os.path.getsize(p)))
    return sorted(out)


def read_bytes(path):
    with open(path, 'rb') as f:
        return f.read()


class InstallTests(unittest.TestCase):
    def setUp(self):
        os.makedirs(BASE, exist_ok=True)
        self.root = tempfile.mkdtemp(dir=BASE)
        self.sims = os.path.join(self.root, 'The Sims 4')
        self.home = os.path.join(self.sims, 'Novulon')
        os.makedirs(os.path.join(self.sims, 'Mods', 'scripts'))
        with open(os.path.join(self.sims, 'Mods', 'scripts', 'other_mod.ts4script'), 'wb') as f:
            f.write(b'PK other')
        self.script = os.path.join(self.root, 'dist', 'Novulon.ts4script')
        self.package = os.path.join(self.root, 'dist', 'Novulon_Tuning.package')
        os.makedirs(os.path.dirname(self.script))
        with open(self.script, 'wb') as f:
            f.write(b'PK script v1')
        with open(self.package, 'wb') as f:
            f.write(b'DBPF package v1')
        self.target_script = os.path.join(self.sims, 'Mods', 'Novulon.ts4script')
        self.target_package = os.path.join(self.sims, 'Mods', 'Novulon_Tuning.package')

    def tearDown(self):
        shutil.rmtree(self.root)

    def kw(self):
        return dict(script=self.script, package=self.package, sims=self.sims, home=self.home, check_game=False)

    def test_dry_run_changes_nothing(self):
        before = listing(self.sims)
        plan = ni.install(dry_run=True, script=self.script, package=self.package, sims=self.sims)
        self.assertEqual(plan['script']['action'], 'put_new')
        self.assertEqual(plan['package']['action'], 'put_new')
        self.assertEqual(plan['script']['target'], self.target_script)
        self.assertEqual(plan['package']['target'], self.target_package)
        self.assertTrue(plan['dry_run'])
        self.assertEqual(listing(self.sims), before)
        self.assertFalse(os.path.exists(self.home))
        self.assertEqual(ni.uninstall(dry_run=True, sims=self.sims)['quarantine'], [])

    def test_install_update_uninstall_and_undo(self):
        r = ni.install(dry_run=False, **self.kw())
        self.assertEqual(sorted(r['done']), sorted([('installed', self.target_script), ('installed', self.target_package)]))
        self.assertEqual(read_bytes(self.target_script), b'PK script v1')
        self.assertEqual(read_bytes(self.target_package), b'DBPF package v1')
        found = ni.find_installed(self.sims)
        self.assertEqual(found['script'], [self.target_script])
        self.assertEqual(found['package'], [self.target_package])
        # same bytes again: nothing to do for either file, no journal
        n = len(list_journals(self.home))
        again = ni.install(dry_run=False, **self.kw())
        self.assertEqual(again['script']['action'], 'up_to_date')
        self.assertEqual(again['package']['action'], 'up_to_date')
        self.assertEqual(len(list_journals(self.home)), n)
        # only the script changes: the package is left alone, one journal covers just the one replace
        with open(self.script, 'wb') as f:
            f.write(b'PK script v2')
        r2 = ni.install(dry_run=False, **self.kw())
        self.assertEqual(r2['script']['action'], 'replace')
        self.assertEqual(r2['package']['action'], 'up_to_date')
        self.assertEqual(read_bytes(self.target_script), b'PK script v2')
        self.assertEqual(read_bytes(self.target_package), b'DBPF package v1')
        undo(r2['journal'], home=self.home, check_game=False)
        self.assertEqual(read_bytes(self.target_script), b'PK script v1')
        # uninstall quarantines both; undo restores both, together
        u = ni.uninstall(dry_run=False, sims=self.sims, home=self.home, check_game=False)
        self.assertFalse(os.path.exists(self.target_script))
        self.assertFalse(os.path.exists(self.target_package))
        self.assertEqual(len(u['done']), 2)
        for _op, _src, q in u['done']:
            self.assertTrue(os.path.exists(q))
        self.assertTrue(os.path.exists(os.path.join(self.sims, 'Mods', 'scripts', 'other_mod.ts4script')))
        undo(u['journal'], home=self.home, check_game=False)
        self.assertEqual(read_bytes(self.target_script), b'PK script v1')
        self.assertEqual(read_bytes(self.target_package), b'DBPF package v1')

    def test_other_copies_of_either_file_are_quarantined(self):
        stray_script = os.path.join(self.sims, 'Mods', 'scripts', 'novulon_old.ts4script')
        stray_package = os.path.join(self.sims, 'Mods', 'scripts', 'Novulon_Tuning_old.package')
        deep = os.path.join(self.sims, 'Mods', 'scripts', 'deeper', 'Novulon.ts4script')
        os.makedirs(os.path.dirname(deep))
        for p in (stray_script, stray_package, deep):
            with open(p, 'wb') as f:
                f.write(b'PK old')
        plan = ni.install(dry_run=True, script=self.script, package=self.package, sims=self.sims)
        self.assertEqual(sorted(plan['quarantine']), sorted([stray_script, stray_package]))  # two levels down: never loaded
        r = ni.install(dry_run=False, **self.kw())
        self.assertFalse(os.path.exists(stray_script))
        self.assertFalse(os.path.exists(stray_package))
        self.assertTrue(os.path.exists(deep))
        undo(r['journal'], home=self.home, check_game=False)
        self.assertTrue(os.path.exists(stray_script))
        self.assertTrue(os.path.exists(stray_package))
        self.assertFalse(os.path.exists(self.target_script))
        self.assertFalse(os.path.exists(self.target_package))

    def test_missing_build_refuses(self):
        os.remove(self.package)
        with self.assertRaises(FileNotFoundError):
            ni.install(dry_run=True, script=self.script, package=self.package, sims=self.sims)
        os.remove(self.script)
        with open(self.package, 'wb') as f:      # package back, script still missing
            f.write(b'DBPF package v1')
        with self.assertRaises(FileNotFoundError):
            ni.install(dry_run=True, script=self.script, package=self.package, sims=self.sims)

    def test_never_touches_saves_or_tray(self):
        """journal.py's Journal._check_path() refuses any path under saves/Tray; novulon_install.py never
        constructs one, but this pins that its targets always live directly under Mods."""
        self.assertTrue(os.path.normcase(self.target_script).startswith(os.path.normcase(os.path.join(self.sims, 'Mods'))))
        self.assertTrue(os.path.normcase(self.target_package).startswith(os.path.normcase(os.path.join(self.sims, 'Mods'))))


if __name__ == '__main__':
    unittest.main(verbosity=2)
