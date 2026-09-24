"""speedkit.merge: plan_merge / apply_merge / undo on a FAKE Sims 4 tree under E:\\speedkit_test\\merge.

The fake tree (Mods holds a few loose CC files, Mods_parked the rest, with a mods_switch-style manifest):
  Mods/Resource.cfg                         the default one
  Mods/CC/hairA.package, hairB.package      CAS CC; they share the identical key SHARED (written once)
  Mods/CC/sub/topC.package                  CAS CC in a sub-folder of CC (same group: CC top folder)
  Mods/CC/!first.package                    load-order sensitive name
  Mods/CC/conflictX.package                 holds CONFLICT, which sim/m1 holds with other bytes
  Mods/CC/tweak.package                     tuning in a CC folder: never merged with CC (alone)
  Mods/!!!!!SpeedKit_Fast_001.package       SpeedKit's own file
  Mods/FitStudio/fs.package                 the other chat's mod
  Mods/scripts/Fake.ts4script + Fake_Tuning.package   script + companion
  Mods_parked/_manifest.json                {"moved": ["Sliders/", "sim/", "Tuning/", "odd/"]}
  Mods_parked/Sliders/s1.package, s2.package + two small REAL slider packages copied bit-exact
  Mods_parked/Sliders/d1/d2/d3/d4/d5/deep.package    more than 5 folders deep: never loaded
  Mods_parked/Tuning/ModA/a1.package + a real RefPack tuning package; Tuning/ModB/b1.package (alone)
  Mods_parked/sim/m1.package                S4S merge (manifest) with CONFLICT
  Mods_parked/odd/*.package                 deleted-flag entry, a key twice, unreadable, empty
Nothing under the real Sims 4 folder is written; real packages are only read and copied.
"""
import hashlib
import importlib.util
import io
import json
import os
import random
import shutil
import stat
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from speedkit.dbpf import Package, PackageWriter, Entry, DELETED, key_of                       # noqa: E402
from speedkit.library import Library, SIMS as REAL_SIMS, DEFAULT_RESOURCE_CFG                   # noqa: E402
from speedkit.companions import Verdict                                                         # noqa: E402
from speedkit import merge as M                                                                  # noqa: E402
from speedkit import manifest as S4S                                                             # noqa: E402

BASE = r'E:\speedkit_test\merge'
REAL_PARKED = os.path.join(REAL_SIMS, 'Mods_parked')
REAL_MODS = os.path.join(REAL_SIMS, 'Mods')
REAL_SLIDERS = ['Sliders/(marsosims)HeadSizeSlider.package', 'Sliders/LUUMIA_mod_NeckHeightSlider_UpdateJune2022.package']
REAL_TUNING = 'scripts/KW_LuckyBrats_anims.package'           # RefPack-compressed XML + NameMap
MODS_SWITCH = r'C:\Users\basim\Tools\sims4_fitstudio\mods_switch.py'

CASP, THUM, RLE2, GEOM, STBL, SIMDATA = 0x034AEECB, 0x3C1AF1F2, 0x3453CF95, 0x015A1849, 0x220557DA, 0x545AC67A
TUN, SMOD, BGEO, OBJD = 0x0C772E27, 0xC5F6763E, 0x067CAA11, 0xC0DB5AE7
SHARED = (CASP, 0, 0xAB00000000000001)
CONFLICT = (CASP, 0x80000000, 0xFFFFFFFFFFFFFF01)                # high-bit group and instance


def blob(seed, n=3000):
    r = random.Random(seed)
    words = [b'<T n="%d">%d</T>' % (r.randrange(50), r.randrange(10 ** 6)) for _ in range(40)]
    return b''.join(r.choice(words) for _ in range(n // 16))[:n]


class DupWriter(PackageWriter):
    def _put(self, t, g, i, raw, msize, comp, committed=1):
        self.keys.discard((t, g, i))
        super()._put(t, g, i, raw, msize, comp, committed)


def write(path, items, writer=PackageWriter, manifest=None):
    """items: (key, data, 'z'|'u'|'del')."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with writer(path) as w:
        if manifest is not None:
            w.add(S4S.MANIFEST_KEY, S4S.build_flat(manifest))
        for key, data, how in items:
            if how == 'del':
                w.add_raw(Entry(key[0], key[1], key[2], 0, len(data), len(data), DELETED, 1), data)
            else:
                w.add(key, data, compress=(how == 'z'))


def rmtree(path):
    def retry(func, p, _):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    if os.path.exists(path):
        shutil.rmtree(path, onerror=retry)


def real_file(rel):
    for root in (REAL_PARKED, REAL_MODS):
        p = os.path.join(root, rel.replace('/', os.sep))
        if os.path.isfile(p):
            return p
    return None


def tree_digest(sims, skip=('SpeedKit',)):
    """{relative path: blake2b} of every file under sims except SpeedKit's own journal/quarantine."""
    out = {}
    for dp, dn, fn in os.walk(sims):
        rel_dp = os.path.relpath(dp, sims)
        if rel_dp.split(os.sep)[0] in skip:
            continue
        for n in fn:
            p = os.path.join(dp, n)
            with open(p, 'rb') as f:
                out[os.path.relpath(p, sims)] = hashlib.blake2b(f.read(), digest_size=16).hexdigest()
    return out


def load_mods_switch(sims):
    spec = importlib.util.spec_from_file_location('mods_switch_under_test', MODS_SWITCH)
    ms = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ms)
    ms.SIMS = sims
    ms.MODS = os.path.join(sims, 'Mods')
    ms.PARKED = os.path.join(sims, 'Mods_parked')
    ms.MANIFEST = os.path.join(ms.PARKED, '_manifest.json')
    ms.game_running = lambda: False
    return ms


class Tree:
    """The fake tree, its library and the verdicts a classifier would give (by relative path)."""

    def __init__(self):
        os.makedirs(BASE, exist_ok=True)
        self.dir = tempfile.mkdtemp(dir=BASE)
        self.sims = os.path.join(self.dir, 'The Sims 4')
        self.mods = os.path.join(self.sims, 'Mods')
        self.parked = os.path.join(self.sims, 'Mods_parked')
        self.home = os.path.join(self.sims, 'SpeedKit')
        self.cache = os.path.join(self.dir, 'hash.sqlite')
        self.kinds = {}
        self.build()
        self.lib = Library(os.path.join(self.dir, 'library.sqlite'), {'Mods': self.mods, 'Mods_parked': self.parked})
        self.lib.scan()

    def m(self, *p):
        return os.path.join(self.mods, *p)

    def p(self, *p):
        return os.path.join(self.parked, *p)

    def cc(self, path, seed, extra=(), kind='cc', types=(CASP, THUM, RLE2, GEOM)):
        items = []
        for n, t in enumerate(types):
            items.append(((t, 1 if t == THUM else 0, 0x100000000 * seed + n), blob(seed * 10 + n, 4000 if t in (RLE2, GEOM) else 600),
                          'z' if n % 2 == 0 else 'u'))
        items.extend(extra)
        write(path, items)
        self.kinds[os.path.relpath(path, self.sims).split(os.sep, 1)[1].replace(os.sep, '/')] = kind

    def build(self):
        os.makedirs(self.mods)
        with open(self.m('Resource.cfg'), 'w') as f:
            f.write('\n'.join(DEFAULT_RESOURCE_CFG) + '\n')
        shared = (SHARED, blob(99, 800), 'z')
        self.cc(self.m('CC', 'hairA.package'), 1, [shared])
        self.cc(self.m('CC', 'hairB.package'), 2, [shared])
        self.cc(self.m('CC', 'sub', 'topC.package'), 3, types=(RLE2, OBJD, CASP, STBL, SIMDATA, THUM))
        self.cc(self.m('CC', '!first.package'), 4)
        self.cc(self.m('CC', 'conflictX.package'), 5, [(CONFLICT, blob(501, 700), 'z')])
        self.cc(self.m('CC', 'tweak.package'), 6, kind='tuning', types=(TUN,))
        self.cc(self.m('!!!!!SpeedKit_Fast_001.package'), 7)
        self.cc(self.m('FitStudio', 'fs.package'), 8)
        os.makedirs(self.m('scripts'))
        with open(self.m('scripts', 'Fake.ts4script'), 'wb') as f:
            f.write(b'PK\x05\x06' + b'\0' * 18)                 # an empty zip
        self.cc(self.m('scripts', 'Fake_Tuning.package'), 9, kind='core', types=(TUN,))
        # parked
        self.cc(self.p('Sliders', 's1.package'), 20, types=(SMOD, BGEO, THUM))
        self.cc(self.p('Sliders', 's2.package'), 21, types=(SMOD, BGEO))
        self.real = {}
        for rel in REAL_SLIDERS:
            src = real_file(rel)
            if src:
                shutil.copy2(src, self.p(*rel.split('/')))
                os.chmod(self.p(*rel.split('/')), stat.S_IWRITE | stat.S_IREAD)
                self.kinds[rel] = 'cc'
                self.real[rel] = src
        self.cc(self.p('Sliders', 'd1', 'd2', 'd3', 'd4', 'd5', 'deep.package'), 22, types=(SMOD,))
        self.cc(self.p('Tuning', 'ModA', 'a1.package'), 30, kind='tuning', types=(TUN, STBL))
        self.cc(self.p('Tuning', 'ModA', 'a2.package'), 31, kind='tuning', types=(TUN,))
        src = real_file(REAL_TUNING)
        if src:
            shutil.copy2(src, self.p('Tuning', 'ModA', 'KW.package'))
            os.chmod(self.p('Tuning', 'ModA', 'KW.package'), stat.S_IWRITE | stat.S_IREAD)
            self.kinds['Tuning/ModA/KW.package'] = 'tuning'
        self.cc(self.p('Tuning', 'ModB', 'b1.package'), 32, kind='tuning', types=(TUN,))
        write(self.p('sim', 'm1.package'), [((CASP, 0, 0x7700), blob(77), 'z'), (CONFLICT, blob(502, 700), 'z')],
              manifest=[('Some CC', [(CASP, 0, 0x7700), CONFLICT])])
        self.kinds['sim/m1.package'] = 'cc'
        write(self.p('odd', 'deleted.package'), [((CASP, 0, 0x8801), blob(81), 'z'), ((CASP, 0, 0x8802), b'gone', 'del')])
        write(self.p('odd', 'twice.package'), [((CASP, 0, 0x8901), blob(82), 'z'), ((CASP, 0, 0x8901), blob(83), 'z')],
              writer=DupWriter)
        with open(self.p('odd', 'broken.package'), 'wb') as f:
            f.write(b'NOT A PACKAGE' * 20)
        write(self.p('odd', 'empty.package'), [])
        for rel in ('odd/deleted.package', 'odd/twice.package', 'odd/broken.package'):
            self.kinds[rel] = 'cc'
        self.kinds['odd/broken.package'] = 'broken'
        self.kinds['odd/empty.package'] = 'empty'
        with open(os.path.join(self.parked, '_manifest.json'), 'w', encoding='utf-8') as f:
            json.dump({'moved': ['Sliders/', 'sim/', 'Tuning/', 'odd/'], 'note': 'kept'}, f, indent=1)

    def verdicts(self):
        return {p.id: Verdict(self.kinds.get(p.rel, 'cc'), 'scripts/Fake.ts4script' if self.kinds.get(p.rel) == 'core' else None, [])
                for p in self.lib.packages()}

    def plan(self, **kw):
        kw.setdefault('verdicts', self.verdicts())
        return M.plan_merge(self.lib, cache_path=self.cache, **kw)

    def apply(self, p, **kw):
        return M.apply_merge(p, self.lib, check_game=False, cache_path=self.cache, **kw)

    def pid(self, root, rel):
        return next(p.id for p in self.lib.packages() if p.root == root and p.rel == rel)

    def park_manifest(self):
        with open(os.path.join(self.parked, '_manifest.json'), encoding='utf-8') as f:
            return json.load(f)

    def close(self):
        self.lib.close()
        rmtree(self.dir)


class PlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.t = Tree()
        cls.p = cls.t.plan()

    @classmethod
    def tearDownClass(cls):
        cls.t.close()

    def reason(self, root, rel):
        return self.p.excluded.get(self.t.pid(root, rel), '')

    def test_groups(self):
        got = {(g.root, g.out_rel): sorted(s.rel for s in g.sources) for g in self.p.groups}
        self.assertEqual(got[('Mods', 'SpeedKit Merged/CAS_001.package')],
                         ['CC/hairA.package', 'CC/hairB.package', 'CC/sub/topC.package'])
        self.assertEqual(got[('Mods_parked', 'SpeedKit Merged/Sliders_001.package')], ['Sliders/s1.package', 'Sliders/s2.package'])
        self.assertEqual(got[('Mods_parked', 'SpeedKit Merged/Tuning_001.package')], ['Tuning/ModA/a1.package', 'Tuning/ModA/a2.package'])
        self.assertEqual(len(got), 3)
        g = next(g for g in self.p.groups if g.category == 'CAS')
        self.assertEqual(g.dup_copies, 1)                          # SHARED is written once
        self.assertEqual(len({s.root for g in self.p.groups for s in g.sources if g.root == 'Mods'}), 1)

    def test_exclusions(self):
        r = self.reason
        self.assertTrue(r('Mods', 'CC/!first.package').startswith('load-order name'))
        self.assertTrue(r('Mods', 'CC/conflictX.package').startswith('conflict'))
        self.assertTrue(r('Mods_parked', 'sim/m1.package').startswith('already merged'))
        self.assertTrue(r('Mods', '!!!!!SpeedKit_Fast_001.package').startswith('speedkit'))
        self.assertTrue(r('Mods', 'FitStudio/fs.package').startswith('fitstudio'))
        self.assertTrue(r('Mods', 'scripts/Fake_Tuning.package').startswith('script companion'))
        self.assertTrue(r('Mods_parked', 'Sliders/d1/d2/d3/d4/d5/deep.package').startswith('not loaded'))
        self.assertTrue(r('Mods_parked', 'odd/deleted.package').startswith('deleted entries'))
        self.assertTrue(r('Mods_parked', 'odd/twice.package').startswith('key twice'))
        self.assertTrue(r('Mods_parked', 'odd/broken.package').startswith(('unreadable', 'script companion')))
        self.assertTrue(r('Mods_parked', 'odd/empty.package').startswith('empty'))
        alone = {self.p.names[i] for i in self.p.alone}
        self.assertEqual(alone, {'Mods/CC/tweak.package', 'Mods_parked/Tuning/ModB/b1.package'})
        s = self.p.summary()
        self.assertEqual(s['groups'], 3)
        self.assertEqual(s['packages_seen'], len(self.t.lib.packages()))

    def test_namemap_is_content_by_default(self):
        # the real sliders and the real tuning all hold a NameMap at 0166038C:0:0 with different bytes
        real = list(self.t.real) + (['Tuning/ModA/KW.package'] if 'Tuning/ModA/KW.package' in self.t.kinds else [])
        if not real:
            self.skipTest('real sample packages are missing')
        for rel in real:
            self.assertTrue(self.reason('Mods_parked', rel).startswith('conflict'), rel)
        p = self.t.plan(ignore_namemap=True)
        got = {g.out_rel: sorted(s.rel for s in g.sources) for g in p.groups}
        self.assertEqual(got['SpeedKit Merged/Sliders_001.package'],
                         sorted(['Sliders/s1.package', 'Sliders/s2.package'] + list(self.t.real)))
        self.assertIn('Tuning/ModA/KW.package', got['SpeedKit Merged/Tuning_001.package'])
        self.assertFalse(any(k[0] == 0x0166038C for k in p.check_keys))
        self.assertTrue(p.summary()['ignore_namemap'])

    def test_next_to_script_protection_is_on_by_default(self):
        v = self.t.verdicts()
        v[self.t.pid('Mods', 'scripts/Fake_Tuning.package')] = Verdict('cc', None, [])
        p = self.t.plan(verdicts=v)
        self.assertTrue(p.excluded[self.t.pid('Mods', 'scripts/Fake_Tuning.package')].startswith('next to a script'))
        p2 = self.t.plan(verdicts=v, protect_script_folders=False)
        self.assertIn(self.t.pid('Mods', 'scripts/Fake_Tuning.package'), p2.alone)

    def test_target_size_splits_groups_and_min_group(self):
        cas_rels = {'Mods/CC/hairA.package', 'Mods/CC/hairB.package', 'Mods/CC/sub/topC.package'}
        p = self.t.plan(target_bytes=9000)
        cas = [g for g in p.groups if g.category == 'CAS']
        self.assertEqual(cas, [])                                  # every CAS package alone once split
        self.assertLessEqual(cas_rels, {p.names[i] for i in p.alone})
        p = self.t.plan(target_bytes=14000)
        cas = [g for g in p.groups if g.category == 'CAS']
        self.assertEqual([len(g.sources) for g in cas], [2])       # split: two fit, the third is alone
        self.assertIn('Mods/CC/sub/topC.package', {p.names[i] for i in p.alone})
        self.assertTrue(p.groups)
        for g in p.groups:
            self.assertLessEqual(g.est, 14000)
        p = self.t.plan(min_group=4, ignore_namemap=True)
        self.assertEqual([g.category for g in p.groups], ['Sliders'] if len(self.t.real) == 2 else [])
        p = self.t.plan(min_group=4)
        self.assertEqual(p.groups, [])

    def test_numbers_are_unique_across_roots(self):
        write(self.t.p('SpeedKit Merged', 'CAS_001.package'), [((CASP, 0, 0x5151), blob(5151), 'z')],
              manifest=[('x', [(CASP, 0, 0x5151)])])
        try:
            self.t.lib.scan()
            p = self.t.plan()
            self.assertIn('SpeedKit Merged/CAS_002.package', [g.out_rel for g in p.groups])
            self.assertTrue(p.excluded[self.t.pid('Mods_parked', 'SpeedKit Merged/CAS_001.package')].startswith('speedkit'))
        finally:
            os.remove(self.t.p('SpeedKit Merged', 'CAS_001.package'))
            os.rmdir(self.t.p('SpeedKit Merged'))
            self.t.lib.scan()

    def test_rank_and_category(self):
        self.assertEqual([M.rank(t) for t in (CASP, THUM, 0x0354796A, OBJD, 0x319E4F1D, SIMDATA, TUN, STBL, RLE2)],
                         [0, 1, 2, 3, 4, 5, 6, 7, 8])
        self.assertEqual(M.category_of({CASP, RLE2}, 'cc'), 'CAS')
        self.assertEqual(M.category_of({OBJD}, 'cc'), 'BuildBuy')
        self.assertEqual(M.category_of({SMOD}, 'cc'), 'Sliders')
        self.assertEqual(M.category_of({CASP}, 'tuning'), 'Tuning')
        self.assertEqual(M.category_of({0x12345678}, 'cc'), 'Other')

    def test_classifier_is_used_by_default(self):
        cache = os.path.join(self.t.dir, 'companions.sqlite')
        p = M.plan_merge(self.t.lib, cache_path=self.t.cache, companions_cache=cache)
        reasons = {self.t.lib.path(*p.names[i].split('/', 1)): r for i, r in p.excluded.items()}
        self.assertTrue(reasons[self.t.m('scripts', 'Fake_Tuning.package')].startswith(('next to a script', 'script companion')))
        self.assertIn('Mods/SpeedKit Merged/CAS_001.package', ['%s/%s' % (g.root, g.out_rel) for g in p.groups])


class ApplyTests(unittest.TestCase):
    def setUp(self):
        self.t = Tree()

    def tearDown(self):
        self.t.close()

    def originals(self, p):
        """{(t,g,i): (raw bytes, index fields)} of every resource of every source, read before the merge."""
        out = {}
        for g in p.groups:
            for s in g.sources:
                with Package(s.path) as k:
                    for e in k.entries:
                        out.setdefault(key_of(e), (k.raw(e), (e.fsize, e.msize, e.comp)))
        return out

    def test_dry_run_changes_nothing(self):
        before = tree_digest(self.t.sims, skip=())
        p = self.t.plan()
        r = self.t.apply(p)
        self.assertTrue(r['dry_run'])
        self.assertEqual(len(r['would_write']), 3)
        self.assertEqual(tree_digest(self.t.sims, skip=()), before)
        self.assertFalse(os.path.exists(self.t.home))

    def test_apply_verify_and_undo(self):
        before = tree_digest(self.t.sims)
        man_before = self.t.park_manifest()
        p = self.t.plan(ignore_namemap=True)                      # takes the real packages (NameMap) in too
        orig = self.originals(p)
        orig_keys = {}
        for g in p.groups:
            for s in g.sources:
                with Package(s.path) as k:
                    orig_keys[s.rel] = [key_of(e) for e in k.entries]
        r = self.t.apply(p, dry_run=False)
        self.assertEqual(len(r['written']), 3)
        self.assertFalse(r['invariant']['changed'])
        self.assertGreater(r['invariant']['keys_compared'], 20)
        self.assertTrue(r['journal'].endswith('-merge'))
        # sources gone (quarantined), merged files in place, no temp files
        for g in p.groups:
            for s in g.sources:
                self.assertFalse(os.path.exists(s.path))
        leftovers = [n for dp, dn, fn in os.walk(self.t.sims) for n in fn if M.TMP_SUFFIX in n or n.endswith('.writing')]
        self.assertEqual(leftovers, [])
        cas = self.t.m('SpeedKit Merged', 'CAS_001.package')
        with Package(cas) as k:
            es = k.entries
            self.assertEqual(key_of(es[0]), S4S.MANIFEST_KEY)
            ranks = [M.rank(e.t) for e in es[1:]]
            self.assertEqual(ranks, sorted(ranks))                 # catalog first
            keys = [key_of(e) for e in es[1:]]
            self.assertEqual(len(keys), len(set(keys)))
            self.assertEqual(keys.count(SHARED), 1)
            for e in es[1:]:
                raw, fields = orig[key_of(e)]
                self.assertEqual(k.raw(e), raw)                    # bit-exact
                self.assertEqual((e.fsize, e.msize, e.comp), fields)
            srcs = S4S.sources_of(S4S.read_payload(k))
        self.assertEqual(set(srcs), {'hairA', 'hairB', 'topC'})
        self.assertIn(SHARED, srcs['hairA'])
        self.assertIn(SHARED, srcs['hairB'])                       # listed under both, like S4S
        # every merged file lists EVERY resource of every source under that source (S4S unmerge rebuilds it)
        for g in p.groups:
            with Package(os.path.join(self.t.lib.roots[g.root], *g.out_rel.split('/'))) as k:
                listed = S4S.sources_of(S4S.read_payload(k))
            self.assertEqual(set(listed), {M._stem(s.rel) for s in g.sources})
            for s in g.sources:
                self.assertEqual(listed[M._stem(s.rel)], set(orig_keys[s.rel]), s.rel)
        # parked merged files are added to the other tool's manifest; its own entries are kept
        man = self.t.park_manifest()
        self.assertEqual(man['note'], 'kept')
        self.assertEqual(man['moved'][:4], man_before['moved'])
        self.assertEqual(set(man['moved'][4:]), {'SpeedKit Merged/Sliders_001.package', 'SpeedKit Merged/Tuning_001.package'})
        self.assertTrue(os.path.exists(self.t.p('SpeedKit Merged', 'Sliders_001.package')))
        # the real packages (RefPack tuning, uncompressed sliders) survived bit-exact
        for name in ('Sliders_001', 'Tuning_001'):
            with Package(self.t.p('SpeedKit Merged', name + '.package')) as k:
                for e in k.entries[1:]:
                    if key_of(e)[0] != 0x0166038C:
                        self.assertEqual(k.raw(e), orig[key_of(e)][0])
                if name == 'Tuning_001' and 'Tuning/ModA/KW.package' in self.t.kinds:
                    self.assertTrue(any(e.comp == 0xFFFF for e in k.entries))
                    self.assertIn('KW', S4S.sources_of(S4S.read_payload(k)))
        # undo restores every file and the manifest
        acts = M.undo(r['journal'], home=self.t.home, check_game=False)
        self.assertTrue(any(a[0].startswith('parking manifest') for a in acts))
        self.assertEqual(tree_digest(self.t.sims), before)
        self.assertEqual(self.t.park_manifest(), man_before)

    def test_mods_switch_full_restores_the_merged_files(self):
        p = self.t.plan()
        self.t.apply(p, dry_run=False)
        ms = load_mods_switch(self.t.sims)
        with redirect_stdout(io.StringIO()):
            ms.full()
        self.assertTrue(os.path.exists(self.t.m('SpeedKit Merged', 'Sliders_001.package')))
        self.assertTrue(os.path.exists(self.t.m('SpeedKit Merged', 'Tuning_001.package')))
        self.assertTrue(os.path.exists(self.t.m('SpeedKit Merged', 'CAS_001.package')))
        self.assertEqual(self.t.park_manifest()['moved'], [])
        left = [os.path.join(dp, n) for dp, dn, fn in os.walk(self.t.parked) for n in fn if n != '_manifest.json']
        self.assertEqual(left, [])
        self.t.lib.scan()
        # the other tool moved a merged file since: undo refuses instead of leaving duplicates
        jid = [n[:-5] for n in os.listdir(os.path.join(self.t.home, 'journal')) if n.endswith('-merge.json')][0]
        with self.assertRaises(M.MergeError):
            M.undo(jid, home=self.t.home, check_game=False)

    def test_invariant_violation_is_undone(self):
        before = tree_digest(self.t.sims)
        man_before = self.t.park_manifest()
        p = self.t.plan()
        real = M._effective
        calls = []

        def fake(lib, roots, keys, *a):
            out = real(lib, roots, keys, *a)
            calls.append(1)
            if len(calls) == 2:                                    # the check after the run
                scope = next(iter(out))
                k = next(iter(out[scope]))
                out[scope][k] = 'different'
            return out
        with mock.patch.object(M, '_effective', fake):
            with self.assertRaises(M.InvariantError):
                self.t.apply(p, dry_run=False)
        self.assertEqual(tree_digest(self.t.sims), before)
        self.assertEqual(self.t.park_manifest(), man_before)

    def test_failure_half_way_is_rolled_back(self):
        before = tree_digest(self.t.sims)
        man_before = self.t.park_manifest()
        p = self.t.plan()
        real = M.write_merged
        n = []

        def flaky(*a, **k):
            n.append(1)
            if len(n) == 3:
                raise OSError('disk full (simulated)')
            return real(*a, **k)
        with mock.patch.object(M, 'write_merged', flaky):
            with self.assertRaises(M.MergeError) as cm:
                self.t.apply(p, dry_run=False)
        self.assertIn('undone', str(cm.exception))
        self.assertEqual(tree_digest(self.t.sims), before)
        self.assertEqual(self.t.park_manifest(), man_before)

    def test_bad_bytes_are_caught_by_verification(self):
        before = tree_digest(self.t.sims)
        p = self.t.plan()
        real_raw = M._Reader.raw
        n = []

        def corrupt(self_, pi, e):
            b = real_raw(self_, pi, e)
            n.append(1)
            return b[:-1] + bytes([b[-1] ^ 1]) if len(n) == 5 else b
        with mock.patch.object(M._Reader, 'raw', corrupt):
            with self.assertRaises(M.MergeError):
                self.t.apply(p, dry_run=False)
        self.assertEqual(tree_digest(self.t.sims), before)

    def test_refusals_change_nothing(self):
        p = self.t.plan()
        before = tree_digest(self.t.sims, skip=())
        with mock.patch.object(M, 'game_running', lambda: True):
            with self.assertRaises(M.MergeError):
                M.apply_merge(p, self.t.lib, dry_run=False, cache_path=self.t.cache)
        with open(os.path.join(self.t.parked, '_manifest.json'), 'w') as f:
            f.write('{"moved": "oops"}')
        with self.assertRaises(M.MergeError):
            self.t.apply(p, dry_run=False)
        with open(os.path.join(self.t.parked, '_manifest.json'), 'w') as f:
            f.write('not json')
        with self.assertRaises(M.MergeError):
            self.t.apply(p, dry_run=False)
        after = tree_digest(self.t.sims, skip=())
        del before['Mods_parked' + os.sep + '_manifest.json'], after['Mods_parked' + os.sep + '_manifest.json']
        self.assertEqual(after, before)

    def test_stale_plan_is_refused(self):
        p = self.t.plan()
        before_q = os.path.exists(os.path.join(self.t.home, 'quarantine'))
        with open(self.t.m('CC', 'hairB.package'), 'ab') as f:
            f.write(b'\0')
        with self.assertRaises(M.MergeError):
            self.t.apply(p, dry_run=False)
        self.t.lib.scan()
        with self.assertRaises(M.MergeError):                       # rescanned: the plan itself is stale
            self.t.apply(p, dry_run=False)
        self.assertEqual(os.path.exists(os.path.join(self.t.home, 'quarantine')), before_q)
        self.assertTrue(os.path.exists(self.t.m('CC', 'hairA.package')))

    def test_non_default_resource_cfg_is_refused(self):
        with open(self.t.m('Resource.cfg'), 'w') as f:
            f.write('Priority 500\nPackedFile *.package\n')
        p = self.t.plan()
        self.assertTrue(any('Resource.cfg' in w for w in p.warnings))
        with self.assertRaises(M.MergeError):
            self.t.apply(p, dry_run=False)

    def test_unlisted_parked_sources_stay_unlisted(self):
        # parked files the other tool does not list are never restored by 'full': their merge must not be either
        self.t.cc(self.t.p('Unlisted', 'u1.package'), 40)
        self.t.cc(self.t.p('Unlisted', 'u2.package'), 41)
        self.t.lib.scan()
        man_before = self.t.park_manifest()
        p = self.t.plan()
        g = next(g for g in p.groups if g.folder == 'Unlisted')
        self.assertIs(g.park_listed, False)
        self.assertTrue(all(x.park_listed for x in p.groups if x.root == 'Mods_parked' and x is not g))
        r = self.t.apply(p, dry_run=False)
        self.assertTrue(os.path.exists(self.t.p(*g.out_rel.split('/'))))
        self.assertNotIn(g.out_rel, self.t.park_manifest()['moved'])
        self.assertEqual(len(self.t.park_manifest()['moved']), len(man_before['moved']) + 2)
        M.undo(r['journal'], home=self.t.home, check_game=False)
        self.assertEqual(self.t.park_manifest(), man_before)

    def test_manifest_changed_after_planning_is_refused(self):
        p = self.t.plan()
        man = self.t.park_manifest()
        man['moved'] = [e for e in man['moved'] if e != 'Sliders/']            # the other tool restored Sliders
        with open(os.path.join(self.t.parked, '_manifest.json'), 'w', encoding='utf-8') as f:
            json.dump(man, f)
        with self.assertRaises(M.MergeError) as cm:
            self.t.apply(p, dry_run=False)
        self.assertIn('plan again', str(cm.exception))
        self.assertTrue(os.path.exists(self.t.p('Sliders', 's1.package')))

    def test_quarantine_on_another_drive(self):
        q = tempfile.mkdtemp(prefix='speedkit_merge_q_')          # the system temp folder (C:), the tree is on E:
        if M._drive(q) == M._drive(self.t.sims):
            rmtree(q)
            self.skipTest('the temp folder is on the same drive as the fake tree')
        try:
            before = tree_digest(self.t.sims)
            p = self.t.plan()
            r = self.t.apply(p, dry_run=False, quarantine_home=q)
            self.assertTrue(any(os.path.isdir(os.path.join(q, x)) for x in os.listdir(q)))
            M.undo(r['journal'], home=self.t.home, check_game=False)
            self.assertEqual(tree_digest(self.t.sims), before)
        finally:
            rmtree(q)


class ParkManifestTests(unittest.TestCase):
    def setUp(self):
        os.makedirs(BASE, exist_ok=True)
        self.d = tempfile.mkdtemp(dir=BASE)

    def tearDown(self):
        rmtree(self.d)

    def test_add_remove_keep_others(self):
        self.assertIsNone(M.read_park_manifest(self.d))
        self.assertEqual(M.park_manifest_add(self.d, ['a/x.package']), ['a/x.package'])
        with open(os.path.join(self.d, '_manifest.json'), 'w', encoding='utf-8') as f:
            json.dump({'moved': ['sim/', 'other.package'], 'extra': 1}, f)
        self.assertEqual(M.park_manifest_add(self.d, ['sim/x.package', 'SIM/y.package', 'n/z.package']), ['n/z.package'])
        self.assertTrue(M.park_covered(['sim/'], 'Sim/deep/q.package'))
        self.assertFalse(M.park_covered(['sim'], 'sim/q.package'))
        self.assertEqual(M.park_manifest_remove(self.d, ['n/z.package', 'never.package']), ['n/z.package'])
        self.assertEqual(M.read_park_manifest(self.d), {'moved': ['sim/', 'other.package'], 'extra': 1})

    def test_malformed_is_refused(self):
        for text in ('[1, 2]', '{"moved": [1]}', '{"x": []}', '{broken'):
            with open(os.path.join(self.d, '_manifest.json'), 'w') as f:
                f.write(text)
            with self.assertRaises(M.MergeError):
                M.park_manifest_add(self.d, ['a.package'])
            with open(os.path.join(self.d, '_manifest.json')) as f:
                self.assertEqual(f.read(), text)                   # never rewritten


if __name__ == '__main__':
    unittest.main()
