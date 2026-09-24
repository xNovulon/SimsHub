"""Save backups and save health (speedkit/savebackup.py through speedkit/api.py): backing up, keeping the last N,
one-click restore that the Hub's undo reverses, refusing while the game runs, and the size history with its
gentle warnings. The contents of a save are never changed. Cross-platform: a fake Sims 4 folder in a temp folder."""
import datetime
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from speedkit import api, savebackup as SB, library as L  # noqa: E402
from tests import care_fakes as F  # noqa: E402


def read(p):
    with open(p, 'rb') as f:
        return f.read()


class Saves(unittest.TestCase):
    def setUp(self):
        self.root, self.sims = F.make_sims()
        self.saves = os.path.join(self.sims, 'saves')
        self.home = os.path.join(self.sims, 'SpeedKit')
        api.configure(sims=self.sims, db_path=os.path.join(self.root, 'library.sqlite'), check_game=False,
                      game={'exe': None, 'game_dir': None, 'store': 'ea', 'source': 'test'})
        self.a = F.make_save(self.sims, 0x14, 6000, F.now() - 3600)
        self.b = F.make_save(self.sims, 0x09, 5000, F.now() - 7200)
        with open(os.path.join(self.saves, 'Slot_00000014.save.ver0'), 'wb') as f:
            f.write(b'old copy')
        os.makedirs(os.path.join(self.saves, 'FitStudio'))
        with open(os.path.join(self.saves, 'FitStudio', 'x.save'), 'wb') as f:
            f.write(b'not a slot')

    def tearDown(self):
        api.reset()
        F.cleanup(self.root)

    def backups(self):
        return SB.default_root(self.sims, self.home)

    def test_backup_copies_only_the_save_slots(self):
        r = api.backup_saves()
        self.assertTrue(r['ok'], r)
        folder = os.path.join(self.backups(), r['backup'])
        self.assertEqual(sorted(os.listdir(folder)), ['Slot_00000009.save', 'Slot_00000014.save', 'backup.json'])
        self.assertEqual(read(os.path.join(folder, 'Slot_00000014.save')), read(self.a))
        h = api.save_health()
        self.assertEqual(len(h['backups']), 1)
        b = h['backups'][0]
        self.assertTrue(b['complete'])
        self.assertEqual(b['files'], 2)
        self.assertEqual(b['bytes'], 11000)
        self.assertEqual(b['reason'], 'by hand')
        self.assertFalse(os.path.exists(folder + '.partial'))

    def test_unchanged_saves_share_space_and_only_the_last_ones_stay(self):
        ids = [SB.backup(self.saves, self.backups(), keep=3)['id'] for _ in range(5)]
        self.assertEqual(len(set(ids)), 5)
        left = [b['id'] for b in SB.list_backups(self.backups())]
        self.assertEqual(left, list(reversed(ids))[:3])          # newest first, the oldest two went
        a, b = (os.stat(os.path.join(self.backups(), i, 'Slot_00000014.save')) for i in left[:2])
        if hasattr(os, 'link'):
            self.assertEqual(a.st_ino, b.st_ino)                  # a hard link: no extra space for an unchanged save
        # a backup an undoable restore still needs is never pruned
        kept = SB.prune(self.backups(), keep=1, protect={left[2]})
        self.assertEqual(sorted(kept), [left[1]])
        self.assertTrue(os.path.isdir(os.path.join(self.backups(), left[2])))

    def test_restore_and_undo(self):
        first = api.backup_saves()['backup']
        before_a = read(self.a)
        # play on: the save changes, and a new save is made
        with open(self.a, 'ab') as f:
            f.write(b'more play')
        played_a = read(self.a)
        c = F.make_save(self.sims, 0x20, 4096)
        r = api.restore_saves(first)
        self.assertTrue(r['ok'], r)
        self.assertEqual(read(self.a), before_a)
        self.assertEqual(r['left'], ['Slot_00000020.save'])          # newer saves are left alone
        self.assertTrue(os.path.isfile(c))
        self.assertEqual(sorted(x for x in os.listdir(self.saves) if x.endswith('.hubrestore')), [])
        h = api.save_health()
        self.assertEqual(h['backups'][0]['reason'], 'before restore')
        st = api.status()
        top = st['journals'][0]
        self.assertEqual((top['kind'], top['title']), ('saves', 'Put back saves from a backup'))
        self.assertTrue(top['next_undo'])
        u = api.undo_last()
        self.assertTrue(u['ok'], u)
        self.assertEqual(read(self.a), played_a)
        self.assertTrue(os.path.isfile(c))
        self.assertFalse(api.status()['journals'][0]['next_undo'])

    def test_restore_brings_back_a_save_that_was_gone_and_undo_sets_it_aside(self):
        first = api.backup_saves()['backup']
        data_b = read(self.b)
        os.remove(self.b)
        r = api.restore_saves(first)
        self.assertTrue(r['ok'], r)
        self.assertEqual(read(self.b), data_b)
        self.assertTrue(api.undo_last()['ok'])
        self.assertFalse(os.path.exists(self.b))
        kept = [os.path.join(dp, n) for dp, dn, fn in os.walk(self.backups()) for n in fn
                if n == 'Slot_00000009.save' and dp.endswith('-set-aside')]
        self.assertEqual(len(kept), 1)                              # never deleted: moved to the backups folder

    def test_undo_refuses_after_playing_on(self):
        first = api.backup_saves()['backup']
        r = api.restore_saves(first)
        with open(self.a, 'ab') as f:
            f.write(b'played after the restore')
        top = api.status()['journals'][0]
        self.assertTrue(top['cannot_undo'] or not top['undoable'])
        u = api.undo_last()
        self.assertFalse(u['ok'])
        self.assertIn(r['journal'], [j['id'] for j in api.status()['journals']])

    def test_refused_while_the_game_runs(self):
        first = api.backup_saves()['backup']
        api.configure(check_game=True)
        with mock.patch.object(L, 'game_running', return_value=True):
            self.assertFalse(api.backup_saves()['ok'])
            r = api.restore_saves(first)
            self.assertFalse(r['ok'])
            self.assertIn('running', r['message'])
        self.assertEqual(len(SB.list_backups(self.backups())), 1)

    def test_bad_or_broken_backups(self):
        self.assertFalse(api.restore_saves('../../etc')['ok'])
        self.assertFalse(api.restore_saves('20990101-000000')['ok'])
        first = api.backup_saves()['backup']
        with open(os.path.join(self.backups(), first, 'Slot_00000014.save'), 'ab') as f:
            f.write(b'x')
        r = api.restore_saves(first)
        self.assertFalse(r['ok'])
        self.assertIn('incomplete', r['message'])
        self.assertFalse(SB.list_backups(self.backups())[0]['complete'])

    def test_no_saves(self):
        for n in os.listdir(self.saves):
            p = os.path.join(self.saves, n)
            if os.path.isfile(p):
                os.remove(p)
        r = api.backup_saves()
        self.assertFalse(r['ok'])
        self.assertIn('no saves', r['message'])

    def test_health_history_and_gentle_warnings(self):
        big = F.make_save(self.sims, 0x30, 260_000_000)
        grow = F.make_save(self.sims, 0x31, 60_000_000)
        hist_path = os.path.join(self.home, 'save_sizes.json')
        old = (datetime.date.today() - datetime.timedelta(days=20)).isoformat()
        with open(hist_path, 'w') as f:
            json.dump({'saves': {'Slot_00000031.save': [[old, 30_000_000]],
                                 'Slot_00000014.save': [[old, 6000]]}}, f)
        h = api.save_health()
        by = {s['file']: s for s in h['saves']}
        self.assertEqual(by['Slot_00000030.save']['level'], 'very_big')
        self.assertIn('very large', by['Slot_00000030.save']['note'])
        self.assertEqual(by['Slot_00000031.save']['level'], 'growing')
        self.assertEqual(by['Slot_00000031.save']['growth_mb'], 30.0)
        self.assertEqual(by['Slot_00000031.save']['growth_days'], 20)
        self.assertIn('grew 30 MB in the last 20 days', by['Slot_00000031.save']['note'])
        self.assertEqual(by['Slot_00000014.save']['level'], 'ok')
        self.assertIsNone(by['Slot_00000014.save']['note'])
        self.assertIn('2 saves are large or growing quickly', h['message'])
        # the history got today's sizes, once
        api.save_health()
        with open(hist_path) as f:
            pts = json.load(f)['saves']['Slot_00000031.save']
        self.assertEqual([p[1] for p in pts], [30_000_000, 60_000_000])
        self.assertEqual(os.path.getsize(big), 260_000_000)       # never changed


if __name__ == '__main__':
    unittest.main()
