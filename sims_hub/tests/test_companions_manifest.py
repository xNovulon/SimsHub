"""speedkit.manifest: synthetic cases, plus a read-only byte-for-byte re-encode of every S4S manifest
in the real library (Mods + Mods_parked). Scratch files go to E:\\speedkit_test\\companions only."""
import os, shutil, sqlite3, sys, tempfile, time, unittest, zlib
from urllib.request import pathname2url
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from speedkit import manifest as M
from speedkit.dbpf import Package, PackageWriter, ZLIB
from speedkit.library import Library, DEFAULT_DB

SCRATCH = r'E:\speedkit_test\companions'


def library_copy(path):
    """A private, freshly scanned copy of the shared library index (the shared one is never scanned)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    src = sqlite3.connect('file:%s?mode=ro' % pathname2url(DEFAULT_DB), uri=True)
    dst = sqlite3.connect(path)
    src.backup(dst)
    src.close()
    dst.close()
    lib = Library(db_path=path)
    lib.scan()
    return lib


class Synthetic(unittest.TestCase):
    def setUp(self):
        os.makedirs(SCRATCH, exist_ok=True)
        self.dir = tempfile.mkdtemp(dir=SCRATCH)

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_type_is_fnv_of_class_name(self):
        self.assertEqual(M.fnv1_32('S4SMergedPackageManifest'), 0x7FB6AD8A)
        self.assertEqual(M.MANIFEST_KEY, (0x7FB6AD8A, 0, 0))

    def test_flat_layout_bytes(self):
        data = M.build_flat([('A', [(1, 2, 3)])])
        # version 1, root name '', 0 folders, 1 source 'A', 1 key (instance, type, group)
        expect = (b'\x01\x00\x00\x00' + b'\x00' * 4 + b'\x00' * 4 + b'\x01\x00\x00\x00' + b'\x01\x00\x00\x00A'
                  + b'\x01\x00\x00\x00' + (3).to_bytes(8, 'little') + (1).to_bytes(4, 'little') + (2).to_bytes(4, 'little'))
        self.assertEqual(data, expect)

    def test_build_decode_sources(self):
        big = 0xFEDCBA9876543210
        data = M.build_flat([('Hair One.package', [(0x034AEECB, 0, big), (0x034AEECB, 0, big), (M.MANIFEST_TYPE, 0, 0)]),
                             ('hair one', [(0x3453CF95, 0, 5)]),
                             ('../evil', [(1, 1, 1)]),
                             ('CON', [(2, 2, 2)]),
                             ('C:\\x:y', [(3, 3, 3)]),
                             ('trailing. . ', [(4, 4, 4)])])
        root = M.decode(data)
        names = [s.name for _, s in root.walk()]
        self.assertEqual(names, ['Hair One', 'hair one (2)', '._evil', '_CON', 'C__x_y', 'trailing'])
        self.assertEqual(root.sources[0].keys, [(0x034AEECB, 0, big)])      # duplicate and manifest key dropped
        self.assertEqual(M.check_names(root), [])
        self.assertEqual(M.encode(root), data)
        src = M.sources_of(data)
        self.assertEqual(src['hair one (2)'], {(0x3453CF95, 0, 5)})

    def test_sanitize(self):
        taken = set()
        self.assertEqual(M.sanitize_name('A/B\\C', taken), 'A_B_C')
        self.assertEqual(M.sanitize_name('a_b_c', taken), 'a_b_c (2)')
        self.assertEqual(M.sanitize_name('..'), '_')
        self.assertEqual(M.sanitize_name('   '), '_')
        self.assertEqual(M.sanitize_name('nul.txt'), '_nul.txt')
        self.assertEqual(M.sanitize_name('lpt9'), '_lpt9')
        self.assertEqual(M.sanitize_name('x' * 400), 'x' * M.MAX_NAME)
        self.assertEqual(M.sanitize_name('ok name'), 'ok name')

    def test_folders_roundtrip_and_rewrite(self):
        root = M.Folder('', folders=[M.Folder('Deep', folders=[M.Folder('Er', sources=[M.Source('Leaf', [(9, 9, 9)])])],
                                              sources=[M.Source('Mid', [(8, 8, 8), (7, 7, 7)])])],
                        sources=[M.Source('Top', [(1, 1, 1)]), M.Source('Empty', [])], version=7)
        data = M.encode(root)
        back = M.decode(data)
        self.assertEqual(back.version, 7)
        self.assertEqual(M.encode(back), data)
        self.assertEqual(sorted(M.sources_of(data)), ['Deep/Er/Leaf', 'Deep/Mid', 'Empty', 'Top'])
        out = M.decode(M.rewrite_without(data, [(9, 9, 9), (8, 8, 8), (1, 1, 1)]))
        self.assertEqual([(p, s.name, s.keys) for p, s in out.walk()],
                         [('', 'Empty', []), ('Deep', 'Mid', [(7, 7, 7)])])   # Top and Deep/Er dropped, Empty kept
        self.assertEqual(out.version, 7)

    def test_check_names_flags_unsafe_and_case_duplicates(self):
        root = M.Folder('', sources=[M.Source('a/b'), M.Source('X'), M.Source('x'), M.Source('ok ')])
        problems = [(n, why) for _, n, why in M.check_names(root)]
        self.assertIn(('a/b', 'unsafe name'), problems)
        self.assertIn(('ok ', 'unsafe name'), problems)
        self.assertTrue(any(n == 'x' and 'same name' in why for n, why in problems))

    def test_malformed_payloads_raise(self):
        good = M.build_flat([('A', [(1, 2, 3)])])
        for bad in (good[:-1], good + b'\0', b'\x01\x00', good[:12] + b'\xff\xff\xff\x7f'):
            with self.assertRaises(ValueError):
                M.decode(bad)

    def test_package_with_manifest(self):
        path = os.path.join(self.dir, 'merged.package')
        keys_a = [(0x034AEECB, 0, 0x1111222233334444), (0x3453CF95, 0, 0x1111222233334444)]
        keys_b = [(0x545AC67A, 0x80000000, 0x5555666677778888)]
        with PackageWriter(path) as w:
            w.add(M.MANIFEST_KEY, M.build_flat([('A', keys_a), ('B', keys_b + [(1, 1, 1)])]))
            for k in keys_a + keys_b:
                w.add(k, b'x' * 200)
            w.add((0x0000BEEF, 0, 1), b'unlisted resource')
        with Package(path) as p:
            self.assertEqual(p.entries[0].t, M.MANIFEST_TYPE)
            self.assertEqual(p.entries[0].off, 96)                    # first resource, like S4S
            self.assertEqual(p.entries[0].comp, ZLIB)
            root = M.read(p)
            rep = M.unmerge_report(root, p.entries)
        self.assertEqual(rep, {'sources': 2, 'listed': 4, 'missing': 1, 'unlisted': 1, 'name_problems': 0})
        self.assertIsNone(M.read(self._plain()))

    def test_truncated_zlib_is_read(self):
        data = M.build_flat([('S%d' % n, [(n, n, n)]) for n in range(50)])
        packed = zlib.compress(data, 9)[:-4]          # no adler32, like the two LittleMsSam packages
        self.assertEqual(M.payload(packed, ZLIB, len(data)), data)

    def _plain(self):
        path = os.path.join(self.dir, 'plain.package')
        with PackageWriter(path) as w:
            w.add((1, 2, 3), b'hello')
        return path


class RealLibrary(unittest.TestCase):
    """Read-only: every manifest in Mods + Mods_parked must re-encode byte for byte."""

    def setUp(self):
        if not os.path.exists(DEFAULT_DB):
            self.skipTest('no library index yet')
        self.path = os.path.join(SCRATCH, 'lib_manifest_test.sqlite')
        self.addCleanup(os.remove, self.path)     # ~200 MB copy: do not leave it behind
        self.lib = library_copy(self.path)
        self.addCleanup(self.lib.close)           # cleanups run last-in first-out

    def test_reencode_all_real_manifests(self):
        lib = self.lib
        rows = lib.db.execute('select distinct pkg from res where t=?', (M.MANIFEST_TYPE,)).fetchall()
        pkgs = {p.id: p for p in lib.packages()}
        t0 = time.time()
        ok = sources = keys = lossless = 0
        bad = []
        for (pid,) in rows:
            p = pkgs[pid]
            with Package(p.path) as pk:
                data = M.read_payload(pk)
                root = M.decode(data)
                rep = M.unmerge_report(root, pk.entries)
            if M.encode(root) == data and M.rewrite_without(data, []) == data:
                ok += 1
            else:
                bad.append(p.rel)
            sources += rep['sources']
            keys += sum(len(s.keys) for _, s in root.walk())
            lossless += rep['missing'] == 0 and rep['unlisted'] == 0
        print('\n  real manifests: %d/%d byte-exact, %d sources, %d keys, %d would unmerge losslessly, %.1fs'
              % (ok, len(rows), sources, keys, lossless, time.time() - t0))
        self.assertGreater(len(rows), 0)
        self.assertEqual(bad, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
