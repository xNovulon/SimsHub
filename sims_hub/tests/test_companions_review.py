"""Adversarial review tests for the companions component (speedkit.manifest, speedkit.companions,
speedkit.game_index). Everything is built in a FAKE tree under E:\\speedkit_test\\companions_review and
removed afterwards; the only things read outside it are two small real .ts4script files (copied), the
game's Gameplay zips (read-only) and this project's source files."""
import io, os, re, shutil, struct, subprocess, sys, tempfile, time, unittest, zlib
from unittest import mock
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from speedkit import companions as C
from speedkit import manifest as M
from speedkit import game_index as G
from speedkit.dbpf import HEADER, DELETED, ZLIB, REFPACK, NONE, PackageWriter, Package, Entry, refpack_decompress
from speedkit.library import Library, MODS, PARKED, PROJECT

SCRATCH = r'E:\speedkit_test\companions_review'
CASP, SNIPPET, BUFF = 0x034AEECB, 0x7DF2169C, 0x6017E896
WALK = 'LittleMsSam_QuickGoForWalkwithDog'
FREERANGE = 'lot51_freerange'
UNICODE_REL = 'sim/\u6d4b\u8bd5\u5305 \u2713 \u00e9.package'          # CJK + check mark + e-acute


def tuning(m, c='Snippet', i='snippet', n='some_tuning_name', q='"', eq='='):
    a = lambda k, v: '%s%s%s%s%s' % (k, eq, q, v, q)
    return ('<?xml version="1.0" encoding="utf-8"?>\n<I %s %s %s %s s="1"></I>'
            % (a('c', c), a('i', i), a('m', m), a('n', n))).encode()


def refpack_literal(data):
    """RefPack stream made of literal blocks only (valid input for the game's decoder)."""
    n = len(data)
    out = bytearray([0x10, 0xFB]) + n.to_bytes(3, 'big')
    p = 0
    while n - p >= 4:
        chunk = min(112, (n - p) // 4 * 4)
        out.append(0xE0 + chunk // 4 - 1)
        out += data[p:p + chunk]
        p += chunk
    out.append(0xFC + (n - p))
    out += data[p:]
    return bytes(out)


def write_raw_dbpf(path, items, const_type=None):
    """A DBPF 2.1 file written by hand: items = [(t, g, i, stored_bytes, msize, comp)]. Allows what
    PackageWriter refuses (the same key twice) and the constant-type index flag."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    body = bytearray()
    index = bytearray(struct.pack('<I', 1 if const_type is not None else 0))
    if const_type is not None:
        index += struct.pack('<I', const_type)
    for t, g, i, raw, msize, comp in items:
        off = 96 + len(body)
        body += raw
        if const_type is None:
            index += struct.pack('<I', t)
        index += struct.pack('<IIIIIIHH', g, i >> 32, i & 0xFFFFFFFF, off, len(raw) | 0x80000000, msize, comp, 1)
    pos = 96 + len(body)
    with open(path, 'wb') as f:
        f.write(HEADER.pack(b'DBPF', 2, 1, 0, 0, 0, 0, 0, 0, len(items), 0, len(index), 0, 0, 0, 3, pos))
        f.write(body)
        f.write(index)


def pkg(path, resources, manifest_data=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with PackageWriter(path) as w:
        if manifest_data is not None:
            w.add(M.MANIFEST_KEY, manifest_data)
        for k, data in resources:
            w.add(k, data)


def tree_state(root):
    out = {}
    for dp, dn, fn in os.walk(root):
        for n in fn:
            p = os.path.join(dp, n)
            with open(p, 'rb') as f:
                out[p] = (os.path.getmtime(p), zlib.crc32(f.read()))
    return out


# ---------------------------------------------------------------------------------------------- manifest
class ManifestNames(unittest.TestCase):
    def test_length_is_capped_in_utf16_units(self):
        name = M.sanitize_name('\U0001F600' * 200)                   # emoji: 2 UTF-16 units each
        self.assertLessEqual(len(name.encode('utf-16-le')) // 2, M.MAX_NAME)
        self.assertLessEqual(len((name + '.package').encode('utf-16-le')) // 2, 255)   # NTFS name limit
        taken = {M.fold_name(name)}
        again = M.sanitize_name('\U0001F600' * 200, taken)
        self.assertTrue(again.endswith(' (2)'))
        self.assertLessEqual(len(again.encode('utf-16-le')) // 2, M.MAX_NAME)

    def test_lone_surrogate_and_extra_reserved_names(self):
        s = M.sanitize_name('bad\udc80name')
        s.encode('utf-8')                                          # must not raise
        self.assertEqual(s, 'bad_name')
        self.assertEqual(M.sanitize_name('COM\u00b9'), '_COM\u00b9')
        self.assertEqual(M.sanitize_name('conin$'), '_conin$')
        M.decode(M.build_flat([('x\ud800', [(1, 1, 1)])]))           # builds and reads back

    def test_names_equal_on_ntfs_are_made_unique(self):
        # NTFS upper-cases each character: long s / s, final sigma / sigma, dotless i / i clash there
        pairs = [('\u017fam', 'sam'), ('\u0131x', 'ix'), ('Hair', 'hair'),
                 ('\u03bb\u03cc\u03b3\u03bf\u03c2', '\u03bb\u03cc\u03b3\u03bf\u03c3')]
        for a, b in pairs:
            root = M.decode(M.build_flat([(a, [(1, 1, 1)]), (b, [(2, 2, 2)])]))
            names = [s.name for _, s in root.walk()]
            self.assertEqual(names[1], b + ' (2)', (a, b))
            clash = M.Folder('', sources=[M.Source(a, [(1, 1, 1)]), M.Source(b, [(2, 2, 2)])])
            self.assertTrue(any('same name' in why for _, _, why in M.check_names(clash)), (a, b))

    def test_huge_counts_fail_fast(self):
        t0 = time.time()
        for bad in (struct.pack('<III', 1, 0, 0xFFFFFFFF),                       # 4 billion folders, no data
                    struct.pack('<IIII', 1, 0, 0, 0xFFFFFFFF),                   # 4 billion sources
                    struct.pack('<IIIII', 1, 0, 0, 1, 0) + struct.pack('<i', 0x7FFFFFFF)):
            with self.assertRaises(ValueError):
                M.decode(bad)
        self.assertLess(time.time() - t0, 1.0)

    def test_unmerge_report_ignores_deleted_and_duplicate_rows(self):
        root = M.Folder('', sources=[M.Source('A', [(1, 0, 5), (2, 0, 6)])])
        entries = [Entry(1, 0, 5, 0, 1, 1, NONE, 1), Entry(1, 0, 5, 0, 1, 1, NONE, 1),     # same key twice
                   Entry(2, 0, 6, 0, 0, 0, DELETED, 1), Entry(3, 0, 7, 0, 1, 1, NONE, 1)]
        self.assertEqual(M.unmerge_report(root, entries),
                         {'sources': 1, 'listed': 2, 'missing': 1, 'unlisted': 1, 'name_problems': 0})


# ---------------------------------------------------------------------------------------------- companions
class FakeTree(unittest.TestCase):
    """Odd but legal packages in a fake Mods / Mods_parked tree."""

    @classmethod
    def setUpClass(cls):
        os.makedirs(SCRATCH, exist_ok=True)
        cls.dir = tempfile.mkdtemp(dir=SCRATCH)
        mods, parked = os.path.join(cls.dir, 'Mods'), os.path.join(cls.dir, 'Mods_parked')
        os.makedirs(os.path.join(mods, 'scripts'))
        for name in (WALK, FREERANGE):
            src = [os.path.join(r, 'scripts', name + '.ts4script') for r in (PARKED, MODS)]
            shutil.copy2(next((p for p in src if os.path.exists(p)), src[0]), os.path.join(mods, 'scripts'))
        cas = lambda i: ((CASP, 0, i), b'CASP' * 40)
        # XML attributes in single quotes and with spaces around '=' (legal XML)
        pkg(os.path.join(mods, 'single_quote.package'),
            [((SNIPPET, 0, 0x100000011), tuning('xml_injector.snippet', q="'", eq=' = '))])
        # tuning stored RefPack-compressed, and zlib without its final block / checksum
        xml = tuning('xml_injector.snippet')
        packed = refpack_literal(xml)
        assert refpack_decompress(packed) == xml
        write_raw_dbpf(os.path.join(mods, 'refpack_tuning.package'), [(SNIPPET, 0, 0x100000012, packed, len(xml), REFPACK)])
        xml2 = tuning(FREERANGE + '.injections', n='zlib_cut_tuning_name')
        write_raw_dbpf(os.path.join(mods, 'truncated_zlib.package'),
                       [(SNIPPET, 0, 0x100000013, zlib.compress(xml2, 9)[:-4], len(xml2), ZLIB)])
        # constant-type index flag + the same key twice inside one package
        xml3 = tuning(FREERANGE + '.commands')
        write_raw_dbpf(os.path.join(mods, 'const_type_dupes.package'),
                       [(SNIPPET, 0, 0x100000014, xml3, len(xml3), NONE), (SNIPPET, 0, 0x100000014, xml3, len(xml3), NONE)],
                       const_type=SNIPPET)
        # nothing live: only deleted records / only an S4S manifest
        write_raw_dbpf(os.path.join(mods, 'only_deleted.package'), [(CASP, 0, 9, b'', 0, DELETED)])
        pkg(os.path.join(mods, 'manifest_only.package'), [], M.build_flat([('Gone', [(CASP, 0, 1)])]))
        # Unicode names: a plain CC file, and a merged pack with a nested folder and a CJK source name
        pkg(os.path.join(parked, UNICODE_REL.replace('/', os.sep)), [cas(30)])
        cjk = '\u6e90 FreeRange'
        tree = M.Folder('', folders=[M.Folder('Deep', sources=[M.Source(cjk, [(SNIPPET, 0, 0x100000015)])])],
                        sources=[M.Source('Hair', [(CASP, 0, 31)]),
                                 M.Source('Custom Type', [(BUFF, 0, 0x100000016)])])
        pkg(os.path.join(mods, 'sim', 'merged_unicode.package'),
            [cas(31), ((SNIPPET, 0, 0x100000015), tuning(FREERANGE + '.commands')),
             ((BUFF, 0, 0x100000016), tuning('buffs.buff', 'Buff', 'zz_speedkit_custom_type', 'custom_type_buff'))],
            M.encode(tree))
        # the same relative path in both roots (the other tool may leave a copy in each)
        pkg(os.path.join(mods, 'dup', 'x.package'), [cas(40)])
        pkg(os.path.join(parked, 'dup', 'x.package'), [((SNIPPET, 0, 0x100000017), tuning('xml_injector.snippet'))])
        cls.roots = {'Mods': mods, 'Mods_parked': parked}
        cls.before = tree_state(cls.dir)
        cls.lib = Library(db_path=os.path.join(cls.dir, 'lib.sqlite'), roots=cls.roots)
        cls.lib.scan()
        cls.cache = os.path.join(cls.dir, 'companions.sqlite')
        cls.v = C.classify(cls.lib, cache_path=cls.cache)
        cls.pk = {p.id: p for p in cls.lib.packages()}
        cls.by = {(p.root, p.rel): cls.v[p.id] for p in cls.pk.values()}

    @classmethod
    def tearDownClass(cls):
        cls.lib.close()
        shutil.rmtree(cls.dir)

    def kind(self, rel, root='Mods'):
        return self.by[(root, rel)].kind

    def test_odd_encodings_are_sniffed(self):
        self.assertEqual(self.kind('single_quote.package'), 'orphan')      # was 'cc' (mergeable) before the fix
        self.assertIn('missing script module xml_injector.snippet', self.by[('Mods', 'single_quote.package')].reasons)
        self.assertEqual(self.kind('refpack_tuning.package'), 'orphan')
        self.assertEqual(self.kind('truncated_zlib.package'), 'addon')
        self.assertEqual(self.by[('Mods', 'truncated_zlib.package')].script, 'scripts/%s.ts4script' % FREERANGE)

    def test_const_type_index_and_duplicate_key(self):
        v = self.by[('Mods', 'const_type_dupes.package')]
        self.assertEqual((v.kind, v.script), ('addon', 'scripts/%s.ts4script' % FREERANGE))

    def test_nothing_live_is_empty(self):
        self.assertEqual(self.kind('only_deleted.package'), 'empty')
        self.assertEqual(self.kind('manifest_only.package'), 'empty')

    def test_unicode_and_both_roots(self):
        self.assertEqual(self.kind(UNICODE_REL, 'Mods_parked'), 'cc')
        self.assertEqual(self.kind('dup/x.package', 'Mods'), 'cc')
        self.assertEqual(self.kind('dup/x.package', 'Mods_parked'), 'orphan')
        self.assertEqual(len(self.v), len(self.pk))

    def test_script_bearing_sources_nested_unicode_and_missing_insttype(self):
        sb = C.script_bearing_sources(self.lib, cache_path=self.cache)
        rel = {pid: self.pk[pid].rel for pid in sb}
        got = {rel[pid]: sorted(names) for pid, names in sb.items()}
        # the CJK source in a sub-folder (script module), and the source whose tuning uses an instance
        # type no game or script defines (tuning of a missing script); not the CAS-only 'Hair'
        self.assertEqual(got, {'sim/merged_unicode.package': sorted(['Custom Type', 'Deep/\u6e90 FreeRange'])})
        data = M.read_payload(self.pk[next(iter(sb))].path)
        self.assertEqual(M.sources_of(data)['Deep/\u6e90 FreeRange'], {(SNIPPET, 0, 0x100000015)})

    def test_roots_given_as_one_string(self):
        one = C.classify(self.lib, roots='Mods_parked', cache_path=self.cache)
        self.assertEqual({self.pk[p].root for p in one}, {'Mods_parked'})
        self.assertEqual(one, C.classify(self.lib, roots=('Mods_parked',), cache_path=self.cache))

    def test_second_call_uses_the_cache(self):
        C.classify(self.lib, cache_path=self.cache)
        with mock.patch.object(C, '_analyse', side_effect=AssertionError('cache miss')):
            self.assertEqual(C.classify(self.lib, cache_path=self.cache), self.v)

    def test_read_only(self):
        C.classify(self.lib, cache_path=self.cache)
        C.script_bearing_sources(self.lib, cache_path=self.cache)
        now = tree_state(self.dir)
        for p, st in self.before.items():
            self.assertEqual(now.get(p), st, p)
        extra = set(now) - set(self.before)
        self.assertTrue(all(os.path.basename(p).startswith(('lib.sqlite', 'companions.sqlite', 'cli_cache.sqlite'))
                            for p in extra), extra)

    def test_cli_survives_unicode_on_a_cp1252_console(self):
        # --db of the fake index: the CLI resolves rels under the REAL roots (read-only stat/read), so the
        # fake packages come out 'broken' and their names get printed.
        env = dict(os.environ, PYTHONIOENCODING='cp1252')
        cache = os.path.join(self.dir, 'cli_cache.sqlite')
        r = subprocess.run([sys.executable, '-m', 'speedkit.companions', '--db', self.lib.db_path, '--cache', cache,
                            '--list', 'broken'], cwd=PROJECT, env=env, capture_output=True, timeout=600)
        self.assertEqual(r.returncode, 0, r.stderr.decode('cp1252', 'replace')[-500:])
        self.assertIn(b'\\u6d4b', r.stdout)
        merged = self.pk[[p for p in self.pk if self.pk[p].rel == 'sim/merged_unicode.package'][0]].path
        r = subprocess.run([sys.executable, '-m', 'speedkit.manifest', merged], cwd=PROJECT, env=env,
                           capture_output=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr.decode('cp1252', 'replace')[-500:])
        self.assertIn(b'Deep/\\u6e90 FreeRange', r.stdout)


class ReadOnlySource(unittest.TestCase):
    def test_modules_never_write_files_themselves(self):
        """The three modules only write their SQLite caches: no file writes, moves or deletes."""
        bad = re.compile(r"os\.(remove|unlink|rename|replace|rmdir|removedirs)\(|shutil\.|open\([^)]*['\"][wax]b?\+?['\"]"
                         r"|PackageWriter\(|Journal\(")
        for mod in ('manifest', 'companions', 'game_index'):
            with open(os.path.join(PROJECT, 'speedkit', mod + '.py'), encoding='utf-8') as f:
                hits = [l.strip() for l in f if bad.search(l)]
            self.assertEqual(hits, [], mod)


# ---------------------------------------------------------------------------------------------- game index
class GameIndexEdges(unittest.TestCase):
    def setUp(self):
        os.makedirs(SCRATCH, exist_ok=True)
        self.dir = tempfile.mkdtemp(dir=SCRATCH)
        self.game = os.path.join(self.dir, 'game')
        client = os.path.join(self.game, 'Data', 'Client')
        os.makedirs(client)
        with open(os.path.join(client, 'Resource.cfg'), 'wb') as f:              # UTF-8 BOM + CRLF
            f.write(b'\xef\xbb\xbfPriority -20\r\nPackedFile ClientDeltaBuild*.package\r\nPriority -30\r\n'
                    b'PackedFile ClientFullBuild*.package\r\n')
        pkg(os.path.join(client, 'ClientDeltaBuild0.package'), [((CASP, 0, 1), b'a'), ((CASP, 0, 1 << 63 | 2), b'b')])
        pkg(os.path.join(client, 'ClientFullBuild0.package'), [((CASP, 0, 1), b'c')])
        with open(os.path.join(client, 'ClientFullBuild1.package'), 'wb') as f:
            f.write(b'DBPF' + b'\0' * 20)                                        # truncated: unreadable

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_bom_crlf_cfg_and_unreadable_package(self):
        self.assertEqual([(p, pat) for _, p, pat in G.parse_cfg(os.path.join(self.game, 'Data', 'Client', 'Resource.cfg'))],
                         [(-20, 'ClientDeltaBuild*.package'), (-30, 'ClientFullBuild*.package')])
        gi = G.GameIndex(os.path.join(self.dir, 'g.sqlite'), self.game)
        try:
            s = gi.scan()
            self.assertEqual((s['packages'], s['reread']), (3, 3))
            self.assertEqual(gi.stats()['unreadable'], 1)
            self.assertEqual(gi.where(CASP, 0, 1), [('Data/Client/ClientDeltaBuild0.package', -20),
                                                    ('Data/Client/ClientFullBuild0.package', -30)])
            self.assertEqual(gi.ids_of_type(CASP), {1, 1 << 63 | 2})
        finally:
            gi.close()

    def test_unscanned_index_refuses_to_answer(self):
        gi = G.GameIndex(os.path.join(self.dir, 'never_scanned.sqlite'), self.game)
        lib = Library(db_path=os.path.join(self.dir, 'l.sqlite'), roots={'Mods': os.path.join(self.dir, 'none')})
        try:
            with self.assertRaises(RuntimeError):
                gi.override_keys(lib)              # an empty set would read as "nothing overrides the game"
            with self.assertRaises(RuntimeError):
                gi.ids_of_type(CASP)
        finally:
            lib.close()
            gi.close()

    def test_override_keys_odd_library_path_and_string_roots(self):
        gi = G.GameIndex(os.path.join(self.dir, 'g.sqlite'), self.game)
        try:
            gi.scan()
            odd = os.path.join(self.dir, 'lib dir #1 %20 \u00fc\u6d4b')
            mods = os.path.join(odd, 'Mods')
            pkg(os.path.join(mods, 'x.package'), [((CASP, 0, 1 << 63 | 2), b'x'), ((CASP, 0, 3), b'y')])
            lib = Library(db_path=os.path.join(odd, 'lib.sqlite'), roots={'Mods': mods})
            try:
                lib.scan()
                want = {(CASP, 0, 1 << 63 | 2)}
                self.assertEqual(gi.override_keys(lib, roots=('Mods',)), want)
                self.assertEqual(gi.override_keys(lib, roots='Mods'), want)       # one root, not 'M','o','d','s'
                self.assertEqual(gi.override_keys(lib), want)
            finally:
                lib.close()
        finally:
            gi.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
