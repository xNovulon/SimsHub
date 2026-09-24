"""Tests for speedkit/ingame_install.py on a FAKE Sims 4 folder under E:\\speedkit_test\\ingame\\install.

install()/uninstall() default to a dry run that changes nothing; a real run goes through a Journal of
kind 'install' and journal.undo() reverses it. The real Mods folder is never touched.
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from speedkit import ingame_install as ii  # noqa: E402
from speedkit.journal import undo, list_journals  # noqa: E402

BASE = r'E:\speedkit_test\ingame\install'


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
        self.home = os.path.join(self.sims, 'SpeedKit')
        os.makedirs(os.path.join(self.sims, 'Mods', 'scripts'))
        with open(os.path.join(self.sims, 'Mods', 'scripts', 'other_mod.ts4script'), 'wb') as f:
            f.write(b'PK other')
        self.dist = os.path.join(self.root, 'dist', 'SpeedKit_Monitor.ts4script')
        os.makedirs(os.path.dirname(self.dist))
        with open(self.dist, 'wb') as f:
            f.write(b'PK version 1')
        self.target = os.path.join(self.sims, 'Mods', 'SpeedKit_Monitor.ts4script')

    def tearDown(self):
        shutil.rmtree(self.root)

    def kw(self):
        return dict(dist=self.dist, sims=self.sims, home=self.home, check_game=False)

    def test_dry_run_changes_nothing(self):
        before = listing(self.sims)
        plan = ii.install(dry_run=True, dist=self.dist, sims=self.sims)
        self.assertEqual(plan['action'], 'put_new')
        self.assertEqual(plan['target'], self.target)
        self.assertTrue(plan['dry_run'])
        self.assertEqual(listing(self.sims), before)
        self.assertFalse(os.path.exists(self.home))
        self.assertEqual(ii.uninstall(dry_run=True, sims=self.sims)['quarantine'], [])

    def test_install_update_uninstall_and_undo(self):
        r = ii.install(dry_run=False, **self.kw())
        self.assertEqual(r['done'], [('installed', self.target)])
        self.assertEqual(read_bytes(self.target), b'PK version 1')
        self.assertEqual(ii.find_installed(self.sims), [self.target])
        # same bytes again: nothing to do, no journal
        n = len(list_journals(self.home))
        self.assertEqual(ii.install(dry_run=False, **self.kw())['action'], 'up_to_date')
        self.assertEqual(len(list_journals(self.home)), n)
        # a newer build replaces the old file; the old one is quarantined, not deleted
        with open(self.dist, 'wb') as f:
            f.write(b'PK version 2')
        r2 = ii.install(dry_run=False, **self.kw())
        self.assertEqual(r2['action'], 'replace')
        self.assertEqual(read_bytes(self.target), b'PK version 2')
        undo(r2['journal'], home=self.home, check_game=False)
        self.assertEqual(read_bytes(self.target), b'PK version 1')
        # uninstall quarantines; undo puts it back
        u = ii.uninstall(dry_run=False, sims=self.sims, home=self.home, check_game=False)
        self.assertFalse(os.path.exists(self.target))
        self.assertTrue(os.path.exists(u['done'][0][2]))
        self.assertTrue(os.path.exists(os.path.join(self.sims, 'Mods', 'scripts', 'other_mod.ts4script')))
        undo(u['journal'], home=self.home, check_game=False)
        self.assertEqual(read_bytes(self.target), b'PK version 1')
        self.assertEqual(len({j[0] for j in list_journals(self.home)}), len(list_journals(self.home)))

    def test_other_copies_are_quarantined(self):
        stray = os.path.join(self.sims, 'Mods', 'scripts', 'speedkit_monitor_old.ts4script')
        deep = os.path.join(self.sims, 'Mods', 'scripts', 'deeper', 'SpeedKit_Monitor.ts4script')
        os.makedirs(os.path.dirname(deep))
        for p in (stray, deep):
            with open(p, 'wb') as f:
                f.write(b'PK old')
        plan = ii.install(dry_run=True, dist=self.dist, sims=self.sims)
        self.assertEqual(plan['quarantine'], [stray])             # two levels down is never loaded by the game
        r = ii.install(dry_run=False, **self.kw())
        self.assertFalse(os.path.exists(stray))
        self.assertTrue(os.path.exists(deep))
        self.assertEqual(ii.find_installed(self.sims), [self.target])
        undo(r['journal'], home=self.home, check_game=False)
        self.assertTrue(os.path.exists(stray))
        self.assertFalse(os.path.exists(self.target))

    def test_missing_build(self):
        os.remove(self.dist)
        with self.assertRaises(FileNotFoundError):
            ii.install(dry_run=True, dist=self.dist, sims=self.sims)


if __name__ == '__main__':
    unittest.main(verbosity=2)
