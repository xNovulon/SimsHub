"""speedkit.companions: a fake Mods/Mods_parked tree under E:\\speedkit_test\\companions (two small real
.ts4script files copied from Mods_parked + synthetic packages), plus a read-only run over the real
library through a private copy of its index. Nothing under the Sims 4 folder is written."""
import hashlib, os, shutil, sqlite3, sys, tempfile, time, unittest, collections
from urllib.request import pathname2url
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from speedkit import companions as C
from speedkit import manifest as M
from speedkit.dbpf import PackageWriter
from speedkit.library import Library, MODS, PARKED, DEFAULT_DB

SCRATCH = r'E:\speedkit_test\companions'
CASP = 0x034AEECB
SNIPPET, BUFF = 0x7DF2169C, 0x6017E896
WALK = 'LittleMsSam_QuickGoForWalkwithDog'          # real script: top module of the same name, id B69951B3FF9E1C9B
FREERANGE = 'lot51_freerange'                         # real script: modules lot51_freerange.*
WALK_ID = 0xB69951B3FF9E1C9B


def tuning(m, c='Snippet', i='snippet', n='some_tuning_name', body=''):
    return ('<?xml version="1.0" encoding="utf-8"?>\n<I c="%s" i="%s" m="%s" n="%s" s="1">%s</I>'
            % (c, i, m, n, body)).encode()


def mfm(name, required=()):
    req = ''.join('<U><T n="name">%s</T></U>' % r for r in required)
    body = '<T n="name">%s</T><L n="required_mods">%s</L>' % (name, req)
    return tuning('llamalogic.snippets.modfilemanifest', 'ModFileManifest', 'snippet', 'mfm_' + name.replace(' ', '_'), body)


def pkg(path, resources, merged=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with PackageWriter(path) as w:
        if merged is not None:
            w.add(M.MANIFEST_KEY, M.build_flat(merged))
        for k, data in resources:
            w.add(k, data)


def tree_digest(root):
    h = hashlib.blake2b(digest_size=16)
    for dp, dn, fn in sorted(os.walk(root)):
        for n in sorted(fn):
            p = os.path.join(dp, n)
            with open(p, 'rb') as f:
                h.update(p.encode() + f.read())
    return h.hexdigest()


class FakeLibrary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.makedirs(SCRATCH, exist_ok=True)
        cls.dir = tempfile.mkdtemp(dir=SCRATCH)
        mods, parked = os.path.join(cls.dir, 'Mods'), os.path.join(cls.dir, 'Mods_parked')
        os.makedirs(os.path.join(mods, 'scripts'))
        for name in (WALK, FREERANGE):                # the other tool may have moved them: look in both roots
            src = [os.path.join(r, 'scripts', name + '.ts4script') for r in (PARKED, MODS)]
            shutil.copy2(next((p for p in src if os.path.exists(p)), src[0]), os.path.join(mods, 'scripts'))
        cas = lambda i: ((CASP, 0, i), b'CASP' * 40)
        pkg(os.path.join(mods, 'QuickWalk', WALK + '.package'), [cas(1), ((SNIPPET, 0, 0x100000001), mfm('Quick Walk (with the Dog)'))])
        pkg(os.path.join(mods, 'walk_addon.package'), [((SNIPPET, 0, 0x100000002), mfm('Walk Addon', ['Quick Walk (with the Dog)']))])
        pkg(os.path.join(mods, 'addon_pack.package'), [((SNIPPET, 0, 0x100000003), tuning(FREERANGE + '.injections'))])
        pkg(os.path.join(mods, 'needs_injector.package'), [((SNIPPET, 0, 0x100000004), tuning('xml_injector.snippet'))])
        pkg(os.path.join(mods, 'needs_missing_mod.package'), [((SNIPPET, 0, 0x100000005), mfm('Mine', ['Nonexistent Mod']))])
        pkg(os.path.join(mods, 'plain_tuning.package'), [((BUFF, 0, 0x100000006), tuning('buffs.buff', 'Buff', 'buff', 'my_plain_buff'))])
        pkg(os.path.join(mods, 'idref.package'), [((BUFF, 0, WALK_ID), b'<?xml version="1.0"?><X/>')])
        pkg(os.path.join(mods, 'hair.package'), [cas(2), cas(3)])
        pkg(os.path.join(mods, 'empty.package'), [])
        with open(os.path.join(mods, 'broken.package'), 'wb') as f:
            f.write(b'NOT A PACKAGE' * 10)
        pkg(os.path.join(mods, 'sim', '7.package'),
            [cas(4), ((SNIPPET, 0, 0x100000007), tuning(FREERANGE + '.commands'))],
            merged=[('Pretty Hair', [(CASP, 0, 4)]), ('FreeRange Tweak', [(SNIPPET, 0, 0x100000007)])])
        pkg(os.path.join(parked, 'more', WALK + '_Addon_Extra.package'), [cas(5)])
        cls.roots = {'Mods': mods, 'Mods_parked': parked}
        cls.lib = Library(db_path=os.path.join(cls.dir, 'lib.sqlite'), roots=cls.roots)
        cls.lib.scan()
        cls.cache = os.path.join(cls.dir, 'companions.sqlite')
        cls.before = tree_digest(mods) + tree_digest(parked)
        t0 = time.time()
        cls.v = C.classify(cls.lib, cache_path=cls.cache)
        cls.first = time.time() - t0
        cls.by = {p.rel.split('/')[-1]: cls.v[p.id] for p in cls.lib.packages()}

    @classmethod
    def tearDownClass(cls):
        cls.lib.close()
        shutil.rmtree(cls.dir)

    def test_kinds(self):
        by = self.by
        self.assertEqual(by[WALK + '.package'].kind, 'core')                       # same name as its script
        self.assertEqual(by[WALK + '.package'].script, 'scripts/%s.ts4script' % WALK)
        self.assertEqual(by['walk_addon.package'].kind, 'addon')                  # requires the core's manifest name
        self.assertEqual(by['walk_addon.package'].script, 'scripts/%s.ts4script' % WALK)
        self.assertEqual(by['addon_pack.package'], C.Verdict('addon', 'scripts/%s.ts4script' % FREERANGE,
                                                             by['addon_pack.package'].reasons))
        self.assertTrue(any('module %s.injections' % FREERANGE in r for r in by['addon_pack.package'].reasons))
        self.assertEqual(by['needs_injector.package'].kind, 'orphan')
        self.assertIn('missing script module xml_injector.snippet', by['needs_injector.package'].reasons)
        self.assertEqual(by['needs_missing_mod.package'].kind, 'orphan')
        self.assertEqual(by['plain_tuning.package'].kind, 'tuning')
        self.assertEqual(by['idref.package'].kind, 'addon')                       # instance id hard-coded in the script
        self.assertEqual(by['hair.package'], C.Verdict('cc', None, []))
        self.assertEqual(by['empty.package'].kind, 'empty')
        self.assertEqual(by['broken.package'].kind, 'broken')
        self.assertEqual(by['7.package'].kind, 'addon')
        self.assertEqual(by[WALK + '_Addon_Extra.package'].kind, 'weak')          # name only (parked root)

    def test_never_merge(self):
        never = {n for n, v in self.by.items() if C.never_merge(v)}
        self.assertEqual(never, {WALK + '.package', 'walk_addon.package', 'addon_pack.package', 'needs_injector.package',
                                 'needs_missing_mod.package', 'idref.package', 'broken.package', '7.package',
                                 WALK + '_Addon_Extra.package'})

    def test_script_modules(self):
        mods = C.script_modules(self.lib, cache_path=self.cache)
        self.assertEqual(mods[WALK], 'scripts/%s.ts4script' % WALK)
        self.assertEqual(mods[FREERANGE], 'scripts/%s.ts4script' % FREERANGE)

    def test_script_bearing_sources(self):
        sb = C.script_bearing_sources(self.lib, cache_path=self.cache)
        rel = {p.id: p.rel for p in self.lib.packages()}
        self.assertEqual({rel[k]: v for k, v in sb.items()}, {'sim/7.package': ['FreeRange Tweak']})

    def test_cache_and_read_only(self):
        t0 = time.time()
        again = C.classify(self.lib, cache_path=self.cache)
        self.assertEqual(again, self.v)
        print('\n  fake library: first classify %.2fs, cached %.3fs' % (self.first, time.time() - t0))
        self.assertEqual(tree_digest(self.roots['Mods']) + tree_digest(self.roots['Mods_parked']), self.before)

    def test_verdict_follows_file_changes(self):
        path = os.path.join(self.roots['Mods'], 'late.package')
        pkg(path, [((CASP, 0, 77), b'x' * 100)])
        self.lib.scan()
        v = C.classify(self.lib, cache_path=self.cache)
        late = [p.id for p in self.lib.packages() if p.rel == 'late.package'][0]
        self.assertEqual(v[late].kind, 'cc')
        time.sleep(0.05)
        pkg(path, [((SNIPPET, 0, 0x100000009), tuning('xml_injector.snippet'))])
        self.lib.scan()
        late = [p.id for p in self.lib.packages() if p.rel == 'late.package'][0]
        self.assertEqual(C.classify(self.lib, cache_path=self.cache)[late].kind, 'orphan')
        os.remove(path)
        self.lib.scan()


class LoadOrder(unittest.TestCase):
    def test_load_order_sensitive(self):
        yes = ['scripts/!!![NORTHERN SIBERIA WINDS] Better In-Game Lighting Mod v1.1 AVERAGE BASE DARK ROOMS.package',
               '![t]ChaseOverride.package', '000000 Zorak animations.package', '00s.package', 'zzz_last.package',
               '_Overrides/hair.package', '~late.package', '[Kuttoe] CareerReqs_Law.package', '01_first.package',
               '1 - Early/thing.package', 'NORTHERN SIBERIA WINDS lighting/x.package']
        no = ['sim/111.package', 'sim/m27.package', 'LittleMsSam_Roommates!_Addon_LotChallenge.package',
              'Srsly Pack/SCCO Expanded Recipes/EP05_Seasons/Coffee Maker/x.package', 'hair2020.package', '9.package']
        for rel in yes:
            self.assertTrue(C.load_order_sensitive(rel), rel)
        for rel in no:
            self.assertFalse(C.load_order_sensitive(rel), rel)


class RealLibrary(unittest.TestCase):
    """Read-only over the real Mods + Mods_parked, through a private scanned copy of library.sqlite."""

    def setUp(self):
        if not os.path.exists(DEFAULT_DB):
            self.skipTest('no library index yet')
        self.path = os.path.join(SCRATCH, 'lib_classify_test.sqlite')
        src = sqlite3.connect('file:%s?mode=ro' % pathname2url(DEFAULT_DB), uri=True)
        dst = sqlite3.connect(self.path)
        self.addCleanup(os.remove, self.path)     # ~200 MB copy: do not leave it behind
        src.backup(dst)
        src.close()
        dst.close()

    def test_real_library(self):
        lib = Library(db_path=self.path)
        self.addCleanup(lib.close)
        lib.scan()
        cache = os.path.join(SCRATCH, 'companions_real_test.sqlite')
        t0 = time.time()
        v = C.classify(lib, cache_path=cache)
        t1 = time.time() - t0
        sb = C.script_bearing_sources(lib, cache_path=cache)
        pk = {p.id: p for p in lib.packages()}
        by = {pk[i].rel: x for i, x in v.items()}
        counts = collections.Counter(x.kind for x in v.values())
        print('\n  real library: %d packages in %.1fs: %s; never-merge %d; load-order sensitive %d; '
              '%d merged packs (%.1f GB) carry %d script-bearing sources'
              % (len(v), t1, dict(counts.most_common()), sum(C.never_merge(x) for x in v.values()),
                 sum(C.load_order_sensitive(pk[i].rel) for i in v), len(sb), sum(pk[i].size for i in sb) / 1e9,
                 sum(len(s) for s in sb.values())))
        scripts = {s.rel for s in lib.scripts()}
        # Guarded by what is on disk (the other tool moves files), never by the classifier's own output:
        # a check guarded by "is it in script_bearing_sources" would pass when the classifier missed it.
        if 'scripts/UI_Cheats_Extension.package' in by and 'scripts/UI_Cheats_Extension_Scripts.ts4script' in scripts:
            self.assertEqual(by['scripts/UI_Cheats_Extension.package'].kind, 'core')   # research: a real core companion
        if 'scripts/TURBODRIVER_WickedWhims_Tuning.package' in by and \
                'scripts/TURBODRIVER_WickedWhims_Scripts.ts4script' in scripts:
            self.assertEqual(by['scripts/TURBODRIVER_WickedWhims_Tuning.package'].script,
                             'scripts/TURBODRIVER_WickedWhims_Scripts.ts4script')
        srcs = {pk[i].rel: s for i, s in sb.items()}
        # m27 / m9 carry script-module tuning: listed whether or not the script is installed (a missing
        # script's tuning counts too), so only the pack itself has to be present
        if 'sim/m27.package' in by:                                    # stale WickedWhims tuning inside a CC merge
            self.assertIn('TURBODRIVER_WickedWhims_Tuning', srcs.get('sim/m27.package', []))
        if 'sim/m9.package' in by:
            self.assertEqual(srcs.get('sim/m9.package'), ['lot51_plumbbros'])
        self.assertTrue(all(x.kind in C.KINDS for x in v.values()))
        self.assertEqual(len(v), len([p for p in lib.packages() if p.root in ('Mods', 'Mods_parked')]))
        self.assertEqual(C.NEVER_MERGE, {'core', 'addon', 'orphan', 'weak', 'broken'})   # research: weak/orphan too


if __name__ == '__main__':
    unittest.main(verbosity=2)
