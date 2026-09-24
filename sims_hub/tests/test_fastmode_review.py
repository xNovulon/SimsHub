"""Adversarial review tests for speedkit.fastmode, on a fake Sims tree under E:\\speedkit_test\\fastmode_review
(never the real one). The world is test_fastmode's plus a third S4S merge whose tuning names a CAS part with a
32-bit instance (a makeup chair's buff) and an _IMG icon by full key (WickedWhims' cas_part_display_icon).

Covered: 32-bit CC ids and full-key icons named by tuning reach the pack (and verify misses them when they do
not); a kept package that loads before the pack at the Mods root is reported; pack files doubled in Mods or
unlisted make the pack stale; a change of the park rules makes it stale; the kept list must cover every loaded
package; a build that fails half-way leaves the previous pack exactly as it was; a delta reports its real path.
"""
import hashlib, os, shutil, struct, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import test_fastmode as T
from speedkit.dbpf import Package
from speedkit.library import Library
from speedkit.game_index import GameIndex
from speedkit import usedpack as U
from speedkit import fastmode as F
import speedkit.journal as journal_mod

BASE = r'E:\speedkit_test\fastmode_review'

SMALL_CASP, SMALL_TEX = 0x00F9DE37, 0xA300000000000001        # a CC CAS part with a 32-bit instance
ICON = 0xA300000000000002                                       # an _IMG icon named by full key
BUFF_M3, SNIP_M3 = 0xB300000000000001, 0xB300000000000002
ORDER_KEY = 0xB300000000000003                                  # tuning in '!!!!!!!!A' (parked) and '!!!!!!!!B' (kept)


def add_review_packages(sims):
    parked = os.path.join(sims, 'Mods_parked')
    m3 = T.filler_cas(0xE3E3000000000000, 25) + [
        ((U.T_CASP, 0, SMALL_CASP), T.casp([(U.T_RLE2, 0, SMALL_TEX)])),
        ((U.T_RLE2, 0, SMALL_TEX), b'makeup texture' * 30),
        ((T.BUFF, 0, BUFF_M3), T.xml('makeup_chair_buff', '<V n="modifier" t="set_cas_part"><U n="set_cas_part">'
                                    '<T n="cas_part">%d</T><T n="count">70000</T></U></V>' % SMALL_CASP)),
        ((T.SNIPPET, 0, SNIP_M3), T.xml('ww_cas_part', '<T n="cas_part_display_icon">00B2D882:00000000:%016X</T>'
                                        % ICON)),
        ((U.T_IMG, 0, ICON), b'DDS icon' * 40),
    ]
    T.pkg(os.path.join(parked, 'sim', 'm3.package'), m3, merged=[('m3 sources', [k for k, _ in m3])])
    # a CAS catalog whose name loads before the pack; it holds tuning a kept package also has
    first = T.filler_cas(0xE4E4000000000000, 25) + [((T.BUFF, 0, ORDER_KEY), T.xml('parked winner'))]
    T.pkg(os.path.join(parked, '!!!!!!!!A_first.package'), first)


def files_of(folder):
    """{name: blake2b of the content} of the files in a folder (not recursive)."""
    out = {}
    for n in sorted(os.listdir(folder)):
        p = os.path.join(folder, n)
        if os.path.isfile(p):
            with open(p, 'rb') as f:
                out[n] = hashlib.blake2b(f.read(), digest_size=16).hexdigest()
    return out


class FastModeReviewTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.makedirs(BASE, exist_ok=True)
        cls.root = tempfile.mkdtemp(dir=BASE, prefix='t_')
        cls.sims, cls.has_script = T.make_world(cls.root)
        add_review_packages(cls.sims)
        cls.roots = {'Mods': os.path.join(cls.sims, 'Mods'), 'Mods_parked': os.path.join(cls.sims, 'Mods_parked')}
        cls.lib = Library(db_path=os.path.join(cls.root, 'library.sqlite'), roots=cls.roots)
        cls.lib.scan()
        cls.game = U.load_game_ids(os.path.join(cls.root, 'game'), os.path.join(cls.root, 'game_ids.sqlite'))
        gi = GameIndex(os.path.join(cls.root, 'game.sqlite'), os.path.join(cls.root, 'game'))
        gi.scan()
        cls.overrides = gi.override_keys(cls.lib)
        gi.close()
        cls.cache = os.path.join(cls.root, 'companions.sqlite')
        cls.refs_db = os.path.join(cls.root, 'refs.sqlite')
        cls.old_big = F.BIG_CAS_BYTES
        F.BIG_CAS_BYTES = 3000
        cls.kw = dict(game=cls.game, overrides=cls.overrides, cache_path=cls.cache)

    @classmethod
    def tearDownClass(cls):
        F.BIG_CAS_BYTES = cls.old_big
        cls.lib.close()
        shutil.rmtree(cls.root, ignore_errors=True)

    def refs(self):
        return U.scan_references(os.path.join(self.sims, 'saves'), os.path.join(self.sims, 'Tray'), self.refs_db,
                                 workers=1)

    def parked(self, lib=None):
        lib = lib or self.lib
        return F.park_set(lib, verdicts=T.verdicts_for(lib))

    def plan(self, lib=None, refs=None, **kw):
        lib = lib or self.lib
        return F.plan_pack(lib, refs or self.refs(), self.parked(lib), **dict(self.kw, **kw))

    def out(self, name):
        return os.path.join(self.sims, 'SpeedKit', name)

    # ------------------------------------------------------------------ what the tuning names
    def test_scanners(self):
        data = (b'<T>12345678901234567890</T><T>0x00A1000000000001</T><T>4294967295</T><T>99</T><T>70000</T>'
                b'<T n="icon">00b2d882:00000000:A300000000000002</T><T>2f7d0004-00000000-00000000000000AA</T>')
        self.assertNotIn(4294967295, F.xml_ids(data))                    # default: 64-bit ids only
        self.assertEqual(F.xml_ids(data, F.SMALL_ID_MIN) - F.xml_ids(data), {4294967295, 70000})
        self.assertEqual(F.xml_keys(data, F.ASSET_TYPES), {(U.T_IMG, 0, ICON)})
        self.assertEqual(F.xml_keys(data), {(U.T_IMG, 0, ICON), (0x2F7D0004, 0, 0xAA)})
        tarr = F.np.array([SMALL_CASP, 0xA100000000000003], dtype=F.np.uint64)
        blob = b'xy' + struct.pack('<Q', SMALL_CASP) + struct.pack('<Q', 0xA100000000000003)
        self.assertEqual(F.binary_ids(blob, tarr), {0xA100000000000003})
        self.assertEqual(F.binary_ids(blob, tarr, F.SMALL_ID_MIN), {SMALL_CASP, 0xA100000000000003})
        self.assertTrue(F.is_cc_id(U.T_CASP, SMALL_CASP, self.game))
        self.assertFalse(F.is_cc_id(U.T_CASP, 70, self.game))           # a small number, not an id
        self.assertFalse(F.is_cc_id(U.T_CASP, T.EA_PART, self.game))    # below the floor anyway
        self.assertTrue(F.is_cc_id(U.T_CASP, 1 << 40, self.game))

    def test_small_ids_and_named_keys_reach_the_pack(self):
        refs = self.refs()
        p = self.plan(refs=refs)
        k = lambda t, i: (t, 0, i)
        for key in (k(U.T_CASP, SMALL_CASP), k(U.T_RLE2, SMALL_TEX), k(U.T_IMG, ICON)):
            self.assertIn(key, p.items, F.key_text(key))
            self.assertEqual(p.items[key].part, 'c')
        self.assertTrue(p.items[k(U.T_IMG, ICON)].why.startswith('tuning key'))
        self.assertEqual(p.items[k(T.BUFF, BUFF_M3)].part, 'b')           # the buff itself: script content
        self.assertGreaterEqual(p.stats['c_scan']['tuning_small_ids'], 1)
        self.assertGreaterEqual(p.stats['c_scan']['tuning_keys'], 1)
        # verify: fine with the whole plan, and misses each of them when the pack lacks it
        full = self.out('fp_named')
        F.build_pack(p, full, dry_run=False)
        v = F.verify(self.lib, refs, full, **self.kw)
        self.assertTrue(v['ok'], v)
        self.assertGreaterEqual(v['checked']['tuning_keys'], 1)
        for drop, check in ((k(U.T_IMG, ICON), 'tuning_keys'), (k(U.T_CASP, SMALL_CASP), 'tuning')):
            p2 = self.plan(refs=refs)
            del p2.items[drop]
            out = self.out('fp_without_%s' % check)
            F.build_pack(p2, out, dry_run=False)
            v = F.verify(self.lib, refs, out, **self.kw)
            self.assertFalse(v['ok'])
            self.assertIn(check, {m[0] for m in v['missing']}, v['missing'])
            self.assertTrue(any('%016X' % drop[2] in m[1] for m in v['missing']), v['missing'])

    # ------------------------------------------------------------------ load order at the Mods root
    def test_loads_before(self):
        self.assertTrue(F.loads_before('!!!!!!!!B_early.package'))
        self.assertTrue(F.loads_before('!!!!!!x/deep/a.package'))
        self.assertTrue(F.loads_before('!!!!!A.package'))                # 'A' sorts before 'S'
        self.assertTrue(F.loads_before(' space first/x.package'))
        for rel in ('!!!Mods/x.package', '000/x.package', '!!!!!zzz.package', 'sim/m1.package', 'SpeedKit Merged/a.package',
                    '!!!!!SpeedKit_Fast_A.package'):
            self.assertFalse(F.loads_before(rel), rel)
        self.assertTrue(F.loads_before('!!!!!SpeedKit_Fast_500x.package', F.PACK_NAME % 900))

    def test_kept_package_loading_before_the_pack_is_reported(self):
        early = os.path.join(self.roots['Mods'], '!!!!!!!!B_early.package')
        T.pkg(early, [((T.BUFF, 0, ORDER_KEY), T.xml('kept copy that loads before the pack'))])
        lib2 = Library(db_path=os.path.join(self.root, 'lib_early.sqlite'), roots=self.roots)
        out = self.out('fp_early')
        try:
            lib2.scan()
            refs = self.refs()
            p = self.plan(lib=lib2, refs=refs)
            key = (T.BUFF, 0, ORDER_KEY)
            self.assertEqual(p.items[key].part, 'b')                      # the full library uses the parked copy
            first = os.path.join(self.roots['Mods_parked'], '!!!!!!!!A_first.package')
            self.assertEqual(T.winner_raw(lib2, key), T.read_raw(first, key))
            lb = p.stats['loads_before_pack']
            self.assertEqual((lb['packages'], lb['pack_keys_they_hold']), (1, 1))
            self.assertEqual(lb['examples'], ['!!!!!!!!B_early.package'])
            F.build_pack(p, out, dry_run=False)
            v = F.verify(lib2, refs, out, **self.kw)
            self.assertFalse(v['ok'])
            self.assertEqual([d[:2] for d in v['different']], [('order', F.key_text(key))])
        finally:
            lib2.close()
            os.remove(early)

    # ------------------------------------------------------------------ status: doubled, unlisted, rules
    def test_status_doubled_and_unlisted_pack_files(self):
        refs = self.refs()
        p = self.plan(refs=refs)
        out = self.out('fp_status')
        res = F.build_pack(p, out, dry_run=False, max_package_bytes=900)
        self.assertGreater(len(res), 1)
        names = [os.path.basename(r['path']) for r in res]
        mods = self.roots['Mods']
        self.assertEqual(F.status(out)['state'], 'fresh')
        # a copy of a pack file in Mods too (e.g. an older build the switcher left): stale, 'split'
        dup = os.path.join(mods, names[0])
        shutil.copy2(res[0]['path'], dup)
        try:
            st = F.status(out)
            self.assertEqual(st['state'], 'stale')
            self.assertEqual(st['pack']['duplicated'], [names[0]])
            self.assertEqual(st['pack']['where'], 'split')
            self.assertIn('both', ' '.join(st['why']))
            self.assertEqual(F.update_pack(self.lib, refs, out, parked=self.parked(), **self.kw)['action'], 'rebuild')
        finally:
            os.remove(dup)
        self.assertEqual(F.status(out)['state'], 'fresh')
        # an unlisted pack file in Mods would load first in every profile: stale; a real update refuses
        stray = os.path.join(mods, F.PACK_NAME % 7)
        shutil.copy2(res[0]['path'], stray)
        before = files_of(out)
        try:
            st = F.status(out)
            self.assertEqual(st['state'], 'stale')
            self.assertEqual(st['pack']['extra'], [stray])
            with self.assertRaises(F.FastPackError):
                F.update_pack(self.lib, refs, out, parked=self.parked(), dry_run=False, **self.kw)
            self.assertEqual(files_of(out), before)
        finally:
            os.remove(stray)
        # an unlisted pack file in the fastpack folder: the rebuild quarantines it
        stray = os.path.join(out, F.PACK_NAME % 950)
        shutil.copy2(res[0]['path'], stray)
        self.assertEqual(F.status(out)['state'], 'stale')
        u = F.update_pack(self.lib, refs, out, parked=self.parked(), dry_run=False, **self.kw)
        self.assertEqual(u['action'], 'rebuild')
        self.assertFalse(os.path.exists(stray))
        self.assertEqual(F.status(out)['state'], 'fresh', F.status(out)['why'])

    def test_rules_change_makes_the_pack_stale(self):
        refs = self.refs()
        out = self.out('fp_rules')
        F.build_pack(self.plan(refs=refs), out, dry_run=False)
        self.assertEqual(F.read_manifest(out)['rules'], F.rules_fingerprint())
        self.assertEqual(F.status(out)['state'], 'fresh')
        old = F.PARK_MIN_CASP
        F.PARK_MIN_CASP = old + 1
        try:
            st = F.status(out)
            self.assertEqual(st['state'], 'stale')
            self.assertIn('rules', ' '.join(st['why']))
            u = F.update_pack(self.lib, refs, out, parked=self.parked(), dry_run=False, **self.kw)
            self.assertEqual(u['action'], 'refresh')                     # same parked set here: nothing missing
            self.assertEqual(F.status(out)['state'], 'fresh')
        finally:
            F.PARK_MIN_CASP = old
        self.assertEqual(F.status(out)['state'], 'stale')                # built under the other rules now

    def test_kept_list_must_cover_every_loaded_package(self):
        refs = self.refs()
        ps = self.parked()
        p = F.plan_pack(self.lib, refs, ps, kept=list(ps.kept), **self.kw)
        self.assertEqual(set(p.items), set(self.plan(refs=refs).items))
        with self.assertRaises(ValueError):
            F.plan_pack(self.lib, refs, ps, kept=list(ps.kept)[1:], **self.kw)
        with self.assertRaises(ValueError):
            F.plan_pack(self.lib, refs, ps, kept=list(ps.kept) + [ps[0]], **self.kw)

    # ------------------------------------------------------------------ failure half-way, delta path
    def test_failed_rebuild_leaves_the_previous_pack(self):
        refs = self.refs()
        p = self.plan(refs=refs)
        out = self.out('fp_fail')
        self.assertGreater(len(F.build_pack(p, out, dry_run=False, max_package_bytes=900)), 1)
        before = files_of(out)
        real = journal_mod.Journal.put_new
        calls = []

        def flaky(j, tmp, final):
            calls.append(final)
            if len(calls) == 2:
                raise OSError('disk full (simulated)')
            return real(j, tmp, final)

        journal_mod.Journal.put_new = flaky
        try:
            with self.assertRaises(OSError):
                F.build_pack(p, out, dry_run=False, max_package_bytes=900)
        finally:
            journal_mod.Journal.put_new = real
        self.assertEqual(len(calls), 2)                                  # it failed after one new file was in
        self.assertEqual(files_of(out), before)                          # the previous pack, bit for bit
        self.assertEqual(F.status(out)['state'], 'fresh')
        staging = os.path.join(self.sims, 'SpeedKit', 'staging')
        self.assertFalse(os.path.isdir(staging) and os.listdir(staging))

    def test_delta_reports_where_it_is(self):
        refs = self.refs()
        out = self.out('fp_delta')
        F.build_pack(self.plan(refs=refs), out, dry_run=False)
        extra = os.path.join(self.sims, 'saves', 'Slot_00000009.save')
        T.write_save(extra, T.savegame([], [T.sim_data(0x5901, 0, b'De', b'Lta', [T.CC_NEW])]))
        try:
            refs2 = self.refs()
            d = F.update_pack(self.lib, refs2, out, parked=self.parked(), dry_run=False, **self.kw)
            self.assertEqual(d['action'], 'delta')
            self.assertEqual(os.path.dirname(d['result'][0]['path']), out)
            self.assertTrue(os.path.isfile(d['result'][0]['path']))
            with Package(d['result'][0]['path']) as pk:
                self.assertIn((U.T_CASP, 0, T.CC_NEW), {(e.t, e.g, e.i) for e in pk.entries})
        finally:
            os.remove(extra)
            self.refs()


if __name__ == '__main__':
    unittest.main(verbosity=1)
