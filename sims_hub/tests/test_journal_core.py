"""Journal behaviours the wave-1 reviewers found broken: dry-run undo of replace, unique ids,
cross-drive quarantine with read-only files, resumable undo, steps interrupted mid-way."""
import json, os, stat, sys, shutil, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from speedkit.journal import Journal, undo, JournalError

BASE_C = os.path.join(os.path.dirname(__file__), '..', 'data', '_jtest')   # a C: location
os.makedirs(BASE_C, exist_ok=True)


class T(unittest.TestCase):
    def setUp(self):
        self.sims = tempfile.mkdtemp(dir=BASE_C)
        self.home = os.path.join(self.sims, 'SpeedKit')
        os.makedirs(os.path.join(self.sims, 'Mods', 'sub'))
        self.a = os.path.join(self.sims, 'Mods', 'sub', 'a.package')
        self.b = os.path.join(self.sims, 'Mods', 'sub', 'b.package')
        open(self.a, 'wb').write(b'old-a'); open(self.b, 'wb').write(b'old-b')
        self.qE = tempfile.mkdtemp(dir=r'E:\speedkit_test')

    def tearDown(self):
        for d in (self.sims, self.qE):
            shutil.rmtree(d, onerror=lambda f, p, e: (os.chmod(p, stat.S_IWRITE), f(p)))

    def J(self, kind='dedup', **kw):
        return Journal(kind, home=self.home, sims=self.sims, check_game=False, **kw)

    def new(self, path, data):
        tmp = path + '.new'; open(tmp, 'wb').write(data); return tmp

    def test_dry_run_undo_of_replace(self):
        with self.J() as j:
            j.replace(self.new(self.a, b'new'), self.a)
        acts = undo(j.id, home=self.home, check_game=False, dry_run=True)
        self.assertEqual([a for a, _ in acts], ['remove new file (kept in quarantine)', 'restore'])
        self.assertEqual(open(self.a, 'rb').read(), b'new')          # dry run changed nothing
        undo(j.id, home=self.home, check_game=False)
        self.assertEqual(open(self.a, 'rb').read(), b'old-a')

    def test_unique_ids_same_second(self):
        ids = {self.J().id for _ in range(5)}
        self.assertEqual(len(ids), 5)

    def test_cross_drive_quarantine_readonly(self):
        os.chmod(self.a, stat.S_IREAD)
        with self.J(quarantine_home=self.qE) as j:
            q = j.quarantine(self.a)
        self.assertTrue(q.lower().startswith('e:'))
        self.assertFalse(os.path.exists(self.a))
        undo(j.id, home=self.home, check_game=False)
        self.assertEqual(open(self.a, 'rb').read(), b'old-a')

    def test_conflict_detected_before_anything_moves(self):
        with self.J() as j:
            j.quarantine(self.a)
            j.quarantine(self.b)
        open(self.a, 'wb').write(b'intruder')                       # blocks the LAST reversal (a)
        with self.assertRaises(JournalError):
            undo(j.id, home=self.home, check_game=False)
        self.assertFalse(os.path.exists(self.b))                    # b was NOT restored half-way

    def test_resume_after_partial_undo(self):
        with self.J() as j:
            j.quarantine(self.a)
            j.quarantine(self.b)
        # simulate an undo that restored b, then died
        data = json.load(open(j.path, encoding='utf-8'))
        shutil.move(data['steps'][1]['q'], self.b)
        data['steps'][1]['undone'] = True
        json.dump(data, open(j.path, 'w', encoding='utf-8'))
        undo(j.id, home=self.home, check_game=False)
        self.assertTrue(os.path.exists(self.a) and os.path.exists(self.b))

    def test_step_interrupted_after_move(self):
        with self.J() as j:
            j.quarantine(self.a)
        data = json.load(open(j.path, encoding='utf-8'))
        data['steps'][0]['done'] = False                            # crash between move and bookkeeping
        json.dump(data, open(j.path, 'w', encoding='utf-8'))
        undo(j.id, home=self.home, check_game=False)
        self.assertEqual(open(self.a, 'rb').read(), b'old-a')

    def test_home_inside_mods_refused(self):
        with self.assertRaises(JournalError):
            Journal('dedup', home=os.path.join(self.sims, 'Mods', 'SpeedKit'), sims=self.sims, check_game=False)

    def test_undo_refuses_when_new_file_was_moved_to_other_root(self):
        """dedup/merge wrote a new file in Mods, then a mod switch parked it: undo must not restore the
        original beside it (two copies) - it refuses until the file is back."""
        with self.J() as j:
            j.replace(self.new(self.a, b'new'), self.a)
        parked = os.path.join(self.sims, 'Mods_parked', 'sub', 'a.package')
        os.makedirs(os.path.dirname(parked))
        shutil.move(self.a, parked)
        with self.assertRaises(JournalError):
            undo(j.id, home=self.home, check_game=False)
        self.assertFalse(os.path.exists(self.a))           # nothing restored beside the moved copy
        shutil.move(parked, self.a)                         # switched back
        undo(j.id, home=self.home, check_game=False)
        self.assertEqual(open(self.a, 'rb').read(), b'old-a')

    def test_undo_still_restores_when_new_file_was_deleted(self):
        with self.J() as j:
            j.replace(self.new(self.a, b'new'), self.a)
        os.remove(self.a)                                   # deleted, not moved: restoring is safe
        undo(j.id, home=self.home, check_game=False)
        self.assertEqual(open(self.a, 'rb').read(), b'old-a')


if __name__ == '__main__':
    unittest.main(verbosity=1)
