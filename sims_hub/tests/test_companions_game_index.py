"""speedkit.game_index: a fake game folder under E:\\speedkit_test\\companions (cfg parsing, priorities,
incremental scan, queries, override_keys), plus read-only checks against the real E:\\The Sims 4."""
import os, shutil, sys, tempfile, time, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from speedkit import game_index as G
from speedkit.dbpf import PackageWriter, Entry, DELETED
from speedkit.library import Library

SCRATCH = r'E:\speedkit_test\companions'
CASP, TUNE = 0x034AEECB, 0x6017E896


def write_cfg(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write(text)


def write_pkg(path, keys, deleted=()):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with PackageWriter(path) as w:
        for k in keys:
            w.add(k, b'data %r' % (k,), compress=False)
        for t, g, i in deleted:
            w.add_raw(Entry(t, g, i, 0, 0, 0, DELETED, 1), b'')


class FakeGame(unittest.TestCase):
    def setUp(self):
        os.makedirs(SCRATCH, exist_ok=True)
        self.dir = tempfile.mkdtemp(dir=SCRATCH)
        g = self.game = os.path.join(self.dir, 'game')
        write_cfg(os.path.join(g, 'Data', 'Client', 'Resource.cfg'),
                  'Priority -20\nPackedFile ClientDeltaBuild0.package\nPriority -30\n'
                  'PackedFile ClientFullBuild*.package\nPackedFile Strings_*.package\n'
                  'Select CONSOLETRAY\n    PackedFile ConsoleTray.package\nEnd\n')
        write_cfg(os.path.join(g, 'Data', 'Client', 'Resource_LE.cfg'), 'Priority -30\nPackedFile Unlisted.package\n')
        write_pkg(os.path.join(g, 'Data', 'Client', 'ClientFullBuild0.package'), [(CASP, 0, 1), (CASP, 0, 2), (TUNE, 0, 10)])
        write_pkg(os.path.join(g, 'Data', 'Client', 'ClientDeltaBuild0.package'), [(CASP, 0, 3)], deleted=[(CASP, 0, 2)])
        write_pkg(os.path.join(g, 'Data', 'Client', 'Strings_ENG_US.package'), [(0x220557DA, 0, 0x0011223344556677)])
        write_pkg(os.path.join(g, 'Data', 'Client', 'ConsoleTray.package'), [(CASP, 0, 99)])     # console only
        write_pkg(os.path.join(g, 'Data', 'Client', 'Unlisted.package'), [(CASP, 0, 98)])        # no cfg line
        write_cfg(os.path.join(g, 'Data', 'Simulation', 'Resource.cfg'), 'Priority -30\nPackedFile SimulationFullBuild0.package\n')
        write_pkg(os.path.join(g, 'Data', 'Simulation', 'SimulationFullBuild0.package'), [(TUNE, 0, 11)])
        write_cfg(os.path.join(g, 'EP01', 'ResourceClient.cfg'), 'Priority -30\nPackedFile ClientFullBuild*.package\n')
        write_pkg(os.path.join(g, 'EP01', 'ClientFullBuild0.package'), [(CASP, 0, 1 << 63 | 5)])
        write_pkg(os.path.join(g, 'EP01', 'Worlds', 'ClientFullBuild9.package'), [(CASP, 0, 97)])  # sub-folder: not matched
        write_cfg(os.path.join(g, 'Delta', 'EP01', 'ResourceClient.cfg'), 'Priority -20\nPackedFile ClientDeltaBuild*.package\n')
        write_pkg(os.path.join(g, 'Delta', 'EP01', 'ClientDeltaBuild0.package'), [(CASP, 0, 1)])
        write_cfg(os.path.join(g, 'Mystery', 'ResourceClient.cfg'), 'PackedFile *.package\n')      # not a pack folder
        write_pkg(os.path.join(g, 'Mystery', 'x.package'), [(CASP, 0, 96)])
        self.db = os.path.join(self.dir, 'game.sqlite')

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_parse_cfg(self):
        lines = G.parse_cfg(os.path.join(self.game, 'Data', 'Client', 'Resource.cfg'))
        self.assertEqual([(p, pat) for _, p, pat in lines],
                         [(-20, 'ClientDeltaBuild0.package'), (-30, 'ClientFullBuild*.package'), (-30, 'Strings_*.package')])
        self.assertTrue(G._matches('ClientFullBuild*.package', 'clientfullbuild3.PACKAGE'))
        self.assertFalse(G._matches('ClientFullBuild*.package', 'Worlds/ClientFullBuild3.package'))
        self.assertTrue(G._matches('.../*.package', 'a/b/c.package'))
        self.assertTrue(G._matches('*/x?.package', 'dir/x1.package'))

    def test_loaded_packages(self):
        got = {rel: prio for rel, prio, cfg in G.loaded_packages(self.game)}
        self.assertEqual(got, {'Data/Client/ClientDeltaBuild0.package': -20,
                               'Data/Client/ClientFullBuild0.package': -30,
                               'Data/Client/Strings_ENG_US.package': -30,
                               'Data/Simulation/SimulationFullBuild0.package': -30,
                               'EP01/ClientFullBuild0.package': -30,
                               'Delta/EP01/ClientDeltaBuild0.package': -20})

    def test_scan_queries_and_incremental(self):
        gi = G.GameIndex(self.db, self.game)
        s = gi.scan()
        self.assertEqual((s['packages'], s['reread'], s['rows']), (6, 6, 9))
        self.assertTrue(gi.has(CASP, 0, 1))
        self.assertTrue(gi.has(CASP, 0, 1 << 63 | 5))                 # unsigned 64-bit instance round-trips
        self.assertFalse(gi.has(CASP, 0, 99))                         # ConsoleTray is console-only
        self.assertFalse(gi.has(CASP, 0, 98))                         # no PackedFile line
        self.assertFalse(gi.has(CASP, 0, 97))                         # sub-folder the pattern does not reach
        self.assertFalse(gi.has(CASP, 0, 96))                         # not a pack folder
        self.assertEqual(gi.ids_of_type(CASP), {1, 2, 3, 1 << 63 | 5})
        self.assertEqual(gi.where(CASP, 0, 1), [('Delta/EP01/ClientDeltaBuild0.package', -20),
                                                ('Data/Client/ClientFullBuild0.package', -30)])
        self.assertEqual(gi.stats()['string_packages'], 1)
        self.assertEqual(gi.scan()['reread'], 0)
        time.sleep(0.05)
        write_pkg(os.path.join(self.game, 'EP01', 'ClientFullBuild0.package'), [(CASP, 0, 7)])
        os.remove(os.path.join(self.game, 'Data', 'Client', 'Strings_ENG_US.package'))
        s = gi.scan()
        self.assertEqual((s['reread'], s['removed']), (1, 1))
        self.assertTrue(gi.has(CASP, 0, 7))
        self.assertFalse(gi.has(CASP, 0, 1 << 63 | 5))
        gi.close()

    def test_override_keys(self):
        gi = G.GameIndex(self.db, self.game)
        gi.scan()
        mods = os.path.join(self.dir, 'sims', 'Mods')
        write_pkg(os.path.join(mods, 'default_replacement.package'), [(CASP, 0, 1), (CASP, 0, 12345)])
        write_pkg(os.path.join(mods, 'sub', 'tuning_override.package'), [(TUNE, 0, 11)],
                  deleted=[(TUNE, 0, 10)])                            # a deleted marker is not an override
        lib = Library(db_path=os.path.join(self.dir, 'lib.sqlite'), roots={'Mods': mods})
        lib.scan()
        self.assertEqual(gi.override_keys(lib, roots=('Mods',)), {(CASP, 0, 1), (TUNE, 0, 11)})
        self.assertEqual(gi.override_keys(lib, roots=('Mods_parked',)), set())
        lib.close()
        gi.close()


class RealGame(unittest.TestCase):
    """Read-only on E:\\The Sims 4."""

    def test_every_game_package_is_loaded_by_some_cfg(self):
        if not os.path.isdir(G.GAME_DIR):
            self.skipTest('game not installed')
        on_disk = set()
        for dp, dn, fn in os.walk(G.GAME_DIR):
            for n in fn:
                if n.lower().endswith('.package'):
                    on_disk.add(os.path.relpath(os.path.join(dp, n), G.GAME_DIR).replace(os.sep, '/'))
        loaded = G.loaded_packages()
        self.assertEqual({rel for rel, _, _ in loaded}, on_disk)
        self.assertTrue(all(prio < 0 for _, prio, _ in loaded))
        print('\n  real game: %d packages loaded by %d cfg files' % (len(loaded), len(G.cfg_files())))

    def test_real_index_if_built(self):
        if not os.path.exists(G.DEFAULT_DB):
            self.skipTest('data/game.sqlite not built yet (python -m speedkit.game_index)')
        gi = G.GameIndex()
        st = gi.stats()
        print('\n  data/game.sqlite: %s' % st)
        self.assertEqual(st['packages'], len(G.loaded_packages()))
        self.assertEqual(st['unreadable'], 0)
        self.assertTrue(gi.has(0x034AEECB, 0, next(iter(gi.ids_of_type(0x034AEECB)))))
        gi.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
