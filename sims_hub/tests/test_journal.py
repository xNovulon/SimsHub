import os, sys, tempfile, unittest, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from speedkit.journal import Journal, undo, JournalError

class T(unittest.TestCase):
    def setUp(self):
        self.sims = tempfile.mkdtemp(dir=r'E:\speedkit_test')
        self.home = os.path.join(self.sims, 'SpeedKit')
        os.makedirs(os.path.join(self.sims, 'Mods', 'sub'))
        self.a = os.path.join(self.sims, 'Mods', 'sub', 'a.package')
        open(self.a, 'wb').write(b'old')
    def tearDown(self):
        shutil.rmtree(self.sims)
    def J(self, kind='dedup'):
        return Journal(kind, home=self.home, sims=self.sims, check_game=False)
    def test_replace_and_undo(self):
        tmp = self.a + '.new'; open(tmp, 'wb').write(b'new')
        with self.J() as j:
            j.replace(tmp, self.a)
        self.assertEqual(open(self.a, 'rb').read(), b'new')
        undo(j.id, home=self.home, check_game=False)
        self.assertEqual(open(self.a, 'rb').read(), b'old')
        with self.assertRaises(JournalError):
            undo(j.id, home=self.home, check_game=False)
    def test_refuses_outside_and_scripts_and_saves(self):
        with self.J() as j:
            with self.assertRaises(JournalError): j.quarantine(r'C:\Windows\win.ini')
            s = os.path.join(self.sims, 'Mods', 'x.ts4script'); open(s, 'wb').close()
            with self.assertRaises(JournalError): j.quarantine(s)
            os.makedirs(os.path.join(self.sims, 'saves'))
            sv = os.path.join(self.sims, 'saves', 'Slot.save'); open(sv, 'wb').close()
            with self.assertRaises(JournalError): j.quarantine(sv)
    def test_undo_refuses_changed_file(self):
        tmp = self.a + '.new'; open(tmp, 'wb').write(b'new')
        with self.J() as j:
            j.replace(tmp, self.a)
        os.utime(self.a, (1, 1))
        with self.assertRaises(JournalError):
            undo(j.id, home=self.home, check_game=False)
    def test_move_and_undo(self):
        dst = os.path.join(self.sims, 'Store', 'sub', 'a.package')
        with self.J('profile') as j:
            j.move(self.a, dst)
        self.assertFalse(os.path.exists(self.a))
        undo(j.id, home=self.home, check_game=False)
        self.assertTrue(os.path.exists(self.a))

if __name__ == '__main__':
    unittest.main(verbosity=1)
