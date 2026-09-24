"""Round-trip real packages through PackageWriter and compare every resource; decode all RefPack resources.

Reads real packages from the library (read-only). Files are chosen when the test runs, not at import, and a
package that another tool has moved or removed meanwhile is skipped instead of failing the suite.
"""
import os, random, sqlite3, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from speedkit.dbpf import Package, PackageWriter, key_of, REFPACK  # noqa: E402

SIMS = os.path.join(os.path.expanduser('~'), 'Documents', 'Electronic Arts', 'The Sims 4')
DB = os.path.join(os.path.dirname(__file__), '..', 'data', 'library.sqlite')
OUT = r'E:\speedkit_test' if os.path.isdir('E:\\') else tempfile.gettempdir()


def _path(root, rel):
    return os.path.join(SIMS, root, rel.replace('/', os.sep))


def _existing(rows):
    """Resolve each (root, rel) to a file that exists now, trying the other root too (files get parked)."""
    out = []
    for root, rel in rows:
        for r in (root, 'Mods_parked' if root == 'Mods' else 'Mods'):
            p = _path(r, rel)
            if os.path.isfile(p):
                out.append(p)
                break
    return out


@unittest.skipUnless(os.path.isfile(DB) and os.path.isdir(SIMS), 'no real library on this machine')
class RoundTrip(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        uri = 'file:' + DB.replace('\\', '/') + '?mode=ro'
        cls.db = sqlite3.connect(uri, uri=True)

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def roundtrip(self, src):
        os.makedirs(OUT, exist_ok=True)
        dst = os.path.join(OUT, 'rt_%d_%s' % (os.getpid(), os.path.basename(src)))
        try:
            with Package(src) as p, PackageWriter(dst) as w:
                for e in p.entries:
                    w.add_raw(e, p.raw(e))
            with Package(src) as a, Package(dst) as b:
                self.assertEqual(len(a.entries), len(b.entries))
                bk = {key_of(e): e for e in b.entries}
                for e in a.entries:
                    f = bk[key_of(e)]
                    self.assertEqual((e.fsize, e.msize, e.comp), (f.fsize, f.msize, f.comp))
                    self.assertEqual(a.raw(e), b.raw(f), 'bytes differ %r' % (key_of(e),))
        finally:
            for p in (dst, dst + '.writing'):
                if os.path.exists(p):
                    os.remove(p)

    def test_small_packages(self):
        rows = self.db.execute('select root, rel from pkg where n > 0 and size < 30e6').fetchall()
        random.Random(4).shuffle(rows)
        files = _existing(rows[:40])[:12]
        if not files:
            self.skipTest('no small packages on disk right now')
        for src in files:
            with self.subTest(src=os.path.basename(src)):
                self.roundtrip(src)

    def test_largest_package(self):
        rows = self.db.execute('select root, rel from pkg order by size desc limit 5').fetchall()
        files = _existing(rows)[:1]
        if not files:
            self.skipTest('the largest packages are not on disk right now')
        self.roundtrip(files[0])

    def test_all_refpack_resources_decode(self):
        rows = self.db.execute('select distinct p.root, p.rel from res r join pkg p on p.id = r.pkg '
                               'where r.comp = ?', (REFPACK,)).fetchall()
        files = _existing(rows)
        if not files:
            self.skipTest('no RefPack packages on disk right now')
        ok = 0
        for src in files:
            with Package(src) as p:
                for e in p.entries:
                    if e.comp == REFPACK:
                        self.assertEqual(len(p.read(e)), e.msize)
                        ok += 1
        self.assertGreater(ok, 0)


if __name__ == '__main__':
    unittest.main(verbosity=1)
