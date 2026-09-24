"""End-to-end tests of speedkit.hashing and speedkit.dedup on a FAKE Sims 4 tree under E:\\speedkit_test\\dedup.

The fake tree (overlay load order: AAA < CC < REAL < REAL2 < SCRIPTS < SIM):
  Mods_parked/aaa/early.package        4 resources copied bit-exact from the real merged slider package
  Mods_parked/cc/B.package             I1-I3, IA, D1 (zlib), X1 (winner), the RefPack resource uncompressed
  Mods_parked/cc/C.package             I1-I3, D1 (stored uncompressed), Y1 (corrupt zlib), U3
  Mods_parked/cc/D_dups.package        I1 and K2 twice (two different contents) -> skipped
  Mods/cc/Z_active.package             IA, U4 (the active root's copy of IA is the one kept)
  Mods_parked/real/KW.package          real package with a RefPack resource and a NameMap
  Mods_parked/real/<slider>.package    real S4S-merged package (manifest, NameMap)
  Mods_parked/real2/<slider>.package   identical copy of it
  Mods/scripts/Fake.ts4script + Fake_Tuning.package   T1-T4 (protected: sits next to a script)
  Mods_parked/sim/m1.package           S4S merge: T1-T3 (identical), T4 (stale, differs), I1-I3, X1 (loser), Y1, U1, U2
  Mods_parked/sim/m2.package           S4S merge: IA, I1 -> fully redundant
Nothing under the real Sims 4 folder is written; the real packages are only read and copied.
"""
import hashlib
import os
import random
import shutil
import stat
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from speedkit.dbpf import Package, PackageWriter, Entry, ZLIB, NONE, REFPACK, key_of          # noqa: E402
from speedkit.library import Library, SIMS as REAL_SIMS                                       # noqa: E402
from speedkit import dedup                                                                    # noqa: E402
from speedkit.hashing import hash_copies, hash_duplicates, key_status, effective_map          # noqa: E402
from speedkit.dedup import plan, apply, report, PackagePlan, InvariantError, DedupError, default_protected  # noqa: E402
from speedkit.journal import undo, list_journals                                              # noqa: E402
from speedkit import manifest as s4s                                                          # noqa: E402

BASE = r'E:\speedkit_test\dedup'
REAL_ROOTS = [os.path.join(REAL_SIMS, 'Mods_parked'), os.path.join(REAL_SIMS, 'Mods')]
SLIDER = 'Sliders/pirumxsim_slider02_neck_Fixed.package'
KW = 'scripts/KW_LuckyBrats_anims.package'

CASP, TUN = 0x034AEECB, 0x0C772E27
T = [(TUN, 0, 0x1000 + n) for n in range(5)]            # T[1..4]
I1, I2, I3 = (CASP, 0, 0xA1), (CASP, 0, 0xA2), (CASP, 0, 0xA3)
IA, D1, X1, Y1, K2 = (CASP, 0, 0xAA), (CASP, 0, 0xD1), (CASP, 0, 0xE1), (CASP, 0, 0xF1), (CASP, 0, 0xB2)
U1, U2, U3, U4 = [(CASP, 0x80000000, 0xC0 + n) for n in range(1, 5)]


def blob(seed, n=3000):
    """Compressible pseudo-random bytes (zlib makes them smaller, so PackageWriter.add compresses)."""
    r = random.Random(seed)
    words = [b'<T n="%d">%d</T>' % (r.randrange(50), r.randrange(10 ** 6)) for _ in range(40)]
    return b''.join(r.choice(words) for _ in range(n // 16))[:n]


class DupWriter(PackageWriter):
    """PackageWriter that allows one key twice (to fake the S4S merges that hold a key twice)."""

    def _put(self, t, g, i, raw, msize, comp, committed=1):
        self.keys.discard((t, g, i))
        super()._put(t, g, i, raw, msize, comp, committed)


class SameOffsetWriter(PackageWriter):
    """PackageWriter whose second copy of a key is a second index entry pointing at the first copy's bytes."""

    def _put(self, t, g, i, raw, msize, comp, committed=1):
        first = next((x for x in self.index if x[:3] == (t, g, i)), None)
        if first is not None:
            self.index.append(first)
            return
        super()._put(t, g, i, raw, msize, comp, committed)


def rmtree(path):
    """Remove a test folder, including read-only files (copies of real packages keep their attributes)."""
    def retry(func, p, _):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    if os.path.exists(path):
        shutil.rmtree(path, onerror=retry)


def write(path, items, writer=PackageWriter):
    """items: (key, data, how) with how 'z' (zlib), 'u' (stored), 'bad' (invalid zlib), or ('raw', entry)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with writer(path) as w:
        for key, data, how in items:
            if how == 'z':
                w.add(key, data, compress=True)
            elif how == 'u':
                w.add(key, data, compress=False)
            elif how == 'bad':
                w.add_raw(Entry(key[0], key[1], key[2], 0, len(data), len(data) * 3, ZLIB, 1), data)
            else:
                e = how[1]
                w.add_raw(e, data)


def real_file(rel):
    for root in REAL_ROOTS:
        p = os.path.join(root, rel.replace('/', os.sep))
        if os.path.isfile(p):
            return p
    return None


def tree_digest(sims):
    out = {}
    for dp, dn, fn in os.walk(sims):
        if os.path.basename(dp) == 'SpeedKit' or os.sep + 'SpeedKit' in dp:
            continue
        for n in fn:
            p = os.path.join(dp, n)
            with open(p, 'rb') as f:
                out[os.path.relpath(p, sims)] = hashlib.blake2b(f.read(), digest_size=16).hexdigest()
    return out


class Fake:
    """Builds the fake tree and its library index."""

    def __init__(self):
        os.makedirs(BASE, exist_ok=True)
        self.dir = tempfile.mkdtemp(dir=BASE)
        self.sims = os.path.join(self.dir, 'sims')
        self.mods = os.path.join(self.sims, 'Mods')
        self.parked = os.path.join(self.sims, 'Mods_parked')
        self.home = os.path.join(self.sims, 'SpeedKit')
        self.cache = os.path.join(self.dir, 'hash.sqlite')
        self.slider = real_file(SLIDER)
        self.kw = real_file(KW)
        self.build()
        self.lib = Library(os.path.join(self.dir, 'library.sqlite'), {'Mods': self.mods, 'Mods_parked': self.parked})
        self.lib.scan()

    def P(self, *parts):
        return os.path.join(self.parked, *parts)

    def build(self):
        m = self.mods
        os.makedirs(os.path.join(m, 'scripts'))
        with open(os.path.join(m, 'scripts', 'Fake.ts4script'), 'wb') as f:
            f.write(b'PK\x05\x06' + b'\0' * 18)                      # an empty zip
        tun = {k: blob(k[2]) for k in T[1:]}
        write(os.path.join(m, 'scripts', 'Fake_Tuning.package'), [(k, tun[k], 'z') for k in T[1:]])
        cc = {k: blob(k[2] * 7) for k in (I1, I2, I3, IA, D1)}
        self.cc = cc
        self.refpack = None
        b_items = [(k, cc[k], 'z') for k in (I1, I2, I3, IA, D1)] + [(X1, blob(111), 'z')]
        if self.kw:
            with Package(self.kw) as p:
                e = next(e for e in p.entries if e.comp == REFPACK)
                self.refpack = (key_of(e), p.read(e))
            b_items.append((self.refpack[0], self.refpack[1], 'u'))
        write(self.P('cc', 'B.package'), b_items)
        write(self.P('cc', 'C.package'), [(k, cc[k], 'z') for k in (I1, I2, I3)] + [
            (D1, cc[D1], 'u'), (Y1, b'\x57' + random.Random(5).randbytes(700), 'bad'), (U3, blob(33), 'z')])
        write(self.P('cc', 'D_dups.package'), [(I1, cc[I1], 'z'), (K2, blob(21), 'z'), (K2, blob(22), 'z')], DupWriter)
        write(os.path.join(m, 'cc', 'Z_active.package'), [(IA, cc[IA], 'z'), (U4, blob(44), 'z')])
        m1_keys = [T[1], T[2], T[3], T[4], I1, I2, I3, X1, Y1, U1, U2]
        man1 = s4s.build_flat([('Fake_Tuning', [T[1], T[2], T[3], T[4]]), ('SomeCC', [I1, I2, I3, X1, Y1, U1, U2])])
        data = dict(tun)
        data.update(cc)
        data.update({T[4]: blob(999), X1: blob(112), Y1: blob(55), U1: blob(1), U2: blob(2)})
        write(self.P('sim', 'm1.package'), [(s4s.MANIFEST_KEY, man1, 'z')] + [(k, data[k], 'z') for k in m1_keys])
        man2 = s4s.build_flat([('Redundant', [IA, I1])])
        write(self.P('sim', 'm2.package'), [(s4s.MANIFEST_KEY, man2, 'z'), (IA, cc[IA], 'z'), (I1, cc[I1], 'z')])
        if self.slider:
            name = os.path.basename(self.slider)
            for folder in ('real', 'real2'):
                os.makedirs(self.P(folder), exist_ok=True)
                shutil.copy2(self.slider, self.P(folder, name))
            with Package(self.slider) as p:
                self.early = [e for e in p.entries if e.t in (0x8B18FF6E, 0xC5F6763E)]
                write(self.P('aaa', 'early.package'), [(key_of(e), p.raw(e), ('raw', e)) for e in self.early])
            self.slider_rel = 'real/' + name
        if self.kw:
            os.makedirs(self.P('real'), exist_ok=True)
            shutil.copy2(self.kw, self.P('real', 'KW.package'))

    def pkg(self, rel, root='Mods_parked'):
        return next(p for p in self.lib.packages(root) if p.rel == rel)

    def close(self):
        self.lib.close()
        rmtree(self.dir)


class HashingTests(unittest.TestCase):
    def setUp(self):
        self.f = Fake()

    def tearDown(self):
        self.f.close()

    def test_status_and_cache(self):
        f = self.f
        stats = {}
        groups = hash_copies(f.lib, cache_path=f.cache, stats=stats)
        self.assertGreater(stats['pass1']['bytes_read'], 0)
        st = {k: key_status(v) for k, v in groups.items()}
        for k in (T[1], T[2], T[3], I1, I2, I3, IA, D1):
            self.assertEqual(st[k], 'identical', k)
        for k in (T[4], X1, K2):
            self.assertEqual(st[k], 'conflict', k)
        self.assertEqual(st[Y1], 'undecidable')
        d1 = groups[D1]
        self.assertNotEqual(d1[0].raw, d1[1].raw)                  # zlib vs stored ...
        self.assertEqual(d1[0].data, d1[1].data)                   # ... same content
        self.assertEqual(d1[0].data, hashlib.blake2b(f.cc[D1], digest_size=16).digest())
        self.assertIn('cannot decompress', [c for c in groups[Y1] if c.err][0].err)
        if f.refpack:
            rp = groups[f.refpack[0]]
            self.assertEqual(st[f.refpack[0]], 'identical')
            self.assertEqual({c.comp for c in rp}, {NONE, REFPACK})
        # the 3-tuple API gives the same verdicts
        dups = hash_duplicates(f.lib, cache_path=f.cache)
        self.assertEqual({k: key_status(v) for k, v in dups.items()}, st)
        self.assertTrue(all(len(c) == 3 for v in dups.values() for c in v))
        # second run: everything from the cache
        stats2 = {}
        hash_copies(f.lib, cache_path=f.cache, stats=stats2)
        self.assertEqual(stats2['pass1']['bytes_read'] + stats2['pass2']['bytes_read'], 0)
        self.assertEqual(stats2['cache_hits'], stats2['copies'])

    def test_cache_survives_a_move_between_roots(self):
        f = self.f
        hash_copies(f.lib, cache_path=f.cache)
        src = f.P('cc', 'C.package')
        dst = os.path.join(f.mods, 'cc', 'C.package')
        os.replace(src, dst)                                      # what the other tool does (keeps the mtime)
        f.lib.scan()
        stats = {}
        hash_copies(f.lib, cache_path=f.cache, stats=stats)
        self.assertEqual(stats['pass1']['bytes_read'] + stats['pass2']['bytes_read'], 0)

    def test_effective_map(self):
        f = self.f
        em = effective_map(f.lib, ('Mods', 'Mods_parked'), [D1, X1, IA, (1, 2, 3)], cache_path=f.cache)
        self.assertEqual(em[D1], hashlib.blake2b(f.cc[D1], digest_size=16).hexdigest())
        self.assertEqual(em[X1], hashlib.blake2b(blob(111), digest_size=16).hexdigest())   # B's copy wins
        self.assertIsNone(em[(1, 2, 3)])
        act = effective_map(f.lib, ('Mods',), [IA, X1], cache_path=f.cache)
        self.assertEqual(act[IA], em[IA])
        self.assertIsNone(act[X1])

    def test_real_sample_packages_present(self):
        """The checks on real packages (S4S manifest, RefPack) are skipped silently if these files are gone."""
        self.assertTrue(self.f.slider, 'real sample missing: %s' % SLIDER)
        self.assertTrue(self.f.kw, 'real sample missing: %s' % KW)
        self.assertIsNotNone(self.f.refpack)

    def test_changed_file_is_not_read(self):
        f = self.f
        with open(f.P('cc', 'C.package'), 'ab') as fh:            # change it after the scan
            fh.write(b'x')
        groups = hash_copies(f.lib, cache_path=f.cache)
        c_id = f.pkg('cc/C.package').id
        errs = [c.err for cs in groups.values() for c in cs if c.pkg == c_id]
        self.assertTrue(errs and all('changed since the library scan' in e for e in errs))
        self.assertEqual(key_status(groups[I2]), 'undecidable')


class DedupTests(unittest.TestCase):
    def setUp(self):
        self.f = Fake()

    def tearDown(self):
        self.f.close()

    def plan(self, **kw):
        """plan() on the fake tree. The real research/merging/companions.json is not used here: it names real
        packages such as sim/m1.package, which the fake tree reuses as names."""
        kw.setdefault('protected', default_protected(self.f.lib, source=None))
        return plan(self.f.lib, cache_path=self.f.cache, **kw)

    def run_apply(self, p, **kw):
        return apply(p, self.f.lib, journal_home=self.f.home, sims=self.f.sims, dry_run=False, check_game=False,
                     cache_path=self.f.cache, min_free=kw.pop('min_free', 0), **kw)

    def test_plan_identical(self):
        f = self.f
        p = self.plan()
        act = {pp.rel: pp.action for pp in p.packages.values()}
        self.assertEqual(act['sim/m1.package'], 'rewrite')
        self.assertEqual(act['sim/m2.package'], 'quarantine')
        self.assertEqual(act['cc/C.package'], 'rewrite')
        self.assertEqual(act['cc/D_dups.package'], 'skip')
        self.assertEqual(act['cc/B.package'], 'rewrite')          # loses only IA: Z_active in Mods keeps it
        b = next(pp for pp in p.packages.values() if pp.rel == 'cc/B.package')
        self.assertEqual({d[:3] for d in b.drop}, {IA})
        for rel in ('aaa/early.package', 'scripts/Fake_Tuning.package', 'cc/Z_active.package'):
            self.assertNotIn(rel, act)                            # keeper, protected, active copy
        tun = f.pkg('scripts/Fake_Tuning.package', 'Mods').id
        self.assertIn(tun, p.protected)
        m1 = next(pp for pp in p.packages.values() if pp.rel == 'sim/m1.package')
        dropped = {d[:3] for d in m1.drop}
        self.assertEqual(dropped, {T[1], T[2], T[3], I1, I2, I3})   # T4 differs, X1 conflicts, Y1 undecidable
        c = next(pp for pp in p.packages.values() if pp.rel == 'cc/C.package')
        self.assertEqual({d[:3] for d in c.drop}, {I1, I2, I3, D1})
        s = p.summary()
        self.assertEqual(s['undecidable_keys'], 1)
        self.assertGreaterEqual(s['conflicting_keys'], 3)
        if f.slider:
            name = os.path.basename(f.slider)
            self.assertEqual(act['real/' + name], 'rewrite')          # loses the 4 early resources
            self.assertEqual(act['real2/' + name], 'rewrite')         # keeps only its NameMap (conflicts with KW's)
            r2 = next(pp for pp in p.packages.values() if pp.rel == 'real2/' + name)
            self.assertEqual(r2.only_metadata_left, ['NameMap', 'S4S merge manifest'])
            p2 = self.plan(ignore_namemap=True)
            self.assertEqual({pp.rel: pp.action for pp in p2.packages.values()}['real2/' + name], 'quarantine')
        rep = report(p, f.lib)
        ssc = rep['stale_script_copies_in_merges']
        stale = [e for e in ssc['same_file'] if e['merge'].endswith('sim/m1.package')]
        self.assertEqual(len(stale), 1)
        self.assertEqual((stale[0]['shared_keys'], stale[0]['identical'], stale[0]['differing']), (4, 3, 1))
        self.assertEqual(stale[0]['merge_sources'], {'Fake_Tuning': 4})
        self.assertEqual((ssc['same_file_pairs'], ssc['same_file_differing_keys']), (1, 1))
        self.assertIn('Mods_parked/sim/m2.package', [e['package'] for e in rep['packages_becoming_empty']])
        self.assertTrue(rep['free_space']['drives'])

    def test_apply_verify_undo(self):
        f = self.f
        original = tree_digest(f.sims)
        p = self.plan()
        dry = apply(p, f.lib, journal_home=f.home, sims=f.sims, cache_path=f.cache)
        self.assertTrue(dry['dry_run'])
        self.assertEqual(tree_digest(f.sims), original)           # a dry run changes nothing
        self.assertFalse(os.path.exists(f.home))
        before = {s: effective_map(f.lib, s, sorted(p.check_keys), cache_path=f.cache) for s in (('Mods', 'Mods_parked'), ('Mods',))}
        self.assertEqual(dedup.sims_folder(f.lib), f.sims)        # so the defaults below stay inside the fake tree
        r = apply(p, f.lib, dry_run=False, check_game=False, cache_path=f.cache, min_free=0)
        self.assertEqual(r['journal_home'], f.home)
        self.assertTrue(os.path.exists(os.path.join(f.home, 'journal', r['journal'] + '.json')))
        self.assertEqual(r['invariant']['changed'], [])
        self.assertEqual(r['invariant']['missing'], [])
        self.assertIn('Mods_parked/sim/m2.package', r['quarantined'])
        self.assertIn('Mods_parked/sim/m1.package', r['rewritten'])
        self.assertFalse(os.path.exists(f.P('sim', 'm2.package')))
        self.assertTrue(os.path.exists(f.P('cc', 'D_dups.package')))
        after = {s: effective_map(f.lib, s, sorted(p.check_keys), cache_path=f.cache) for s in before}
        self.assertEqual(before, after)
        # m1 lost exactly the dropped copies and its manifest no longer lists them
        with Package(f.P('sim', 'm1.package')) as m1:
            keys = [key_of(e) for e in m1.entries]
            self.assertEqual(keys, [s4s.MANIFEST_KEY, T[4], X1, Y1, U1, U2])
            srcs = s4s.sources_of(s4s.read_payload(m1))
            self.assertEqual(srcs, {'Fake_Tuning': {T[4]}, 'SomeCC': {X1, Y1, U1, U2}})
            self.assertEqual(m1.read(m1.find(*U1)[0]), blob(1))
        if f.slider:
            with Package(f.P('real', os.path.basename(f.slider))) as sl:
                have = {key_of(e) for e in sl.entries}
                early = {key_of(e) for e in f.early}
                self.assertFalse(have & early)
                listed = set().union(*s4s.sources_of(s4s.read_payload(sl)).values())
                self.assertFalse(listed & early)
                self.assertTrue(listed <= have)
        # nothing left behind, journal recorded, then undo restores every file bit for bit
        self.assertFalse([n for dp, dn, fn in os.walk(f.sims) for n in fn if dedup.TMP_SUFFIX in n])
        undo(r['journal'], home=f.home, check_game=False)
        self.assertEqual(tree_digest(f.sims), original)

    def test_winner_policy(self):
        f = self.f
        original = tree_digest(f.sims)
        p = self.plan(policy='winner')
        m1 = next(pp for pp in p.packages.values() if pp.rel == 'sim/m1.package')
        self.assertIn(T[4], {d[:3] for d in m1.drop})             # stale copy loses to the companion
        self.assertIn(X1, {d[:3] for d in m1.drop})               # B's X1 wins
        self.assertNotIn(Y1, {d[:3] for d in m1.drop})            # undecidable stays
        b = next(pp for pp in p.packages.values() if pp.rel == 'cc/B.package')
        self.assertEqual({d[:3] for d in b.drop}, {IA})           # B's winners (X1 ...) all stay
        if f.slider:
            act = {pp.rel: pp.action for pp in p.packages.values()}
            self.assertEqual(act['real2/' + os.path.basename(f.slider)], 'quarantine')
        r = self.run_apply(p)
        self.assertEqual(r['invariant']['changed'], [])
        with Package(f.P('sim', 'm1.package')) as m:
            self.assertEqual([key_of(e) for e in m.entries], [s4s.MANIFEST_KEY, Y1, U1, U2])
        undo(r['journal'], home=f.home, check_game=False)
        self.assertEqual(tree_digest(f.sims), original)

    def test_invariant_violation_undoes_everything(self):
        f = self.f
        original = tree_digest(f.sims)
        p = self.plan()
        b = f.pkg('cc/B.package')
        bad = PackagePlan(b)                                      # drop the copy of X1 the game uses
        with Package(b.path) as pk:
            e = pk.find(*X1)[0]
            bad.drop = {(e.t, e.g, e.i, e.off)}
            bad.new_size = b.size - e.fsize
        bad.action = 'rewrite'
        p.packages[b.id] = bad
        with self.assertRaises(InvariantError) as cm:
            self.run_apply(p)
        self.assertIn('undone', str(cm.exception))
        self.assertEqual(tree_digest(f.sims), original)

    def test_stale_plan_is_refused(self):
        f = self.f
        original = tree_digest(f.sims)
        p = self.plan()
        path = f.P('cc', 'B.package')                              # a keeper changes after planning
        os.utime(path, (1, 1))
        with self.assertRaises(DedupError):
            self.run_apply(p)
        os.utime(path, None)
        dig = tree_digest(f.sims)
        self.assertEqual(dig, original)
        self.assertFalse(os.path.exists(os.path.join(f.home, 'quarantine')))

    def test_free_space_guard(self):
        f = self.f
        original = tree_digest(f.sims)
        p = self.plan()
        r = self.run_apply(p, min_free=10 ** 18)                  # no rewrite fits; quarantines still happen
        self.assertEqual(r['rewritten'], [])
        self.assertIn('Mods_parked/sim/m2.package', r['quarantined'])
        self.assertTrue(any('free space' in why for _, why in r['skipped']))
        self.assertEqual(r['invariant']['changed'], [])
        undo(r['journal'], home=f.home, check_game=False)
        self.assertEqual(tree_digest(f.sims), original)

    def test_protected_and_active(self):
        f = self.f
        z = f.pkg('cc/Z_active.package', 'Mods').id
        p = self.plan(protected={z})        # protect only Z: Fake_Tuning may now lose T1-T3
        self.assertNotIn(z, p.packages)
        tun = next((pp for pp in p.packages.values() if pp.rel == 'scripts/Fake_Tuning.package'), None)
        self.assertIsNone(tun)                                    # it loads before m1, so its copies are kept
        m2 = next(pp for pp in p.packages.values() if pp.rel == 'sim/m2.package')
        self.assertEqual(m2.action, 'quarantine')
        # IA: B (parked) loads first, but Z (Mods) is what the game loads now: only Z's copy stays
        p2 = self.plan(protected=set())
        dropped_ia = {pp.rel for pp in p2.packages.values() if any(d[:3] == IA for d in pp.drop)}
        self.assertEqual(dropped_ia, {'cc/B.package', 'sim/m2.package'})
        # with only parked copies, the earliest-loaded one stays (I2: B, C, m1 -> B)
        dropped_i2 = {pp.rel for pp in p2.packages.values() if any(d[:3] == I2 for d in pp.drop)}
        self.assertEqual(dropped_i2, {'cc/C.package', 'sim/m1.package'})

    def test_game_started_midway(self):
        f = self.f
        original = tree_digest(f.sims)
        p = self.plan()
        calls = [0]

        def dedup_sees():                  # 1st call: before starting, 2nd: first package, then running
            calls[0] += 1
            return calls[0] > 2

        with mock.patch('speedkit.dedup.game_running', dedup_sees), \
                mock.patch('speedkit.journal.game_running', lambda: calls[0] > 2):
            with self.assertRaises(DedupError) as cm:
                apply(p, f.lib, journal_home=f.home, sims=f.sims, dry_run=False, check_game=True,
                      cache_path=f.cache, min_free=0)
        msg = str(cm.exception)
        self.assertIn('was started', msg)
        self.assertIn('could NOT be undone', msg)       # undo also refuses while the game runs
        (jid, kind, state, nsteps, note), = list_journals(f.home)
        self.assertTrue(state.startswith('failed'))
        self.assertEqual(nsteps, 1)                       # exactly one package was done
        self.assertNotEqual(tree_digest(f.sims), original)
        self.assertFalse([n for dp, dn, fn in os.walk(f.sims) for n in fn if dedup.TMP_SUFFIX in n])
        undo(jid, home=f.home, check_game=False)
        self.assertEqual(tree_digest(f.sims), original)

    def test_free_space_model(self):
        f = self.f
        p = self.plan()
        same = dedup.free_space(p, f.lib, min_free=0)
        self.assertEqual(same['quarantine_home'], f.home)
        self.assertTrue(same['quarantine_on_same_drive'])
        self.assertEqual(same['peak_growth_of_mods_drive'], same['new_files_bytes'])
        run = same['one_run_with_current_free_space']
        self.assertEqual((run['packages_done'], run['rewrites_done']), (run['of'], run['rewrites']))
        other_drive = 'D:' if os.path.splitdrive(BASE)[0].upper() == 'C:' else 'C:'
        other = dedup.free_space(p, f.lib, min_free=0, journal_home=other_drive + r'\speedkit_no_such_folder\SpeedKit')
        self.assertFalse(other['quarantine_on_same_drive'])        # only reads the drive's free space
        self.assertEqual(other['peak_growth_of_mods_drive'], other['largest_new_file'])
        full = dedup.free_space(p, f.lib, min_free=10 ** 18)['one_run_with_current_free_space']
        self.assertEqual(full['rewrites_done'], 0)
        self.assertEqual(full['packages_done'], len(p.actions('quarantine')))   # a same-drive move needs no space

    def test_same_offset_entries_are_skipped(self):
        f = self.f
        write(f.P('cc', 'E_same.package'), [(I3, f.cc[I3], 'z'), (I3, f.cc[I3], 'z'), (U4, blob(45), 'z')],
              SameOffsetWriter)
        with Package(f.P('cc', 'E_same.package')) as pk:
            self.assertEqual(len({e.off for e in pk.find(*I3)}), 1)
        f.lib.scan()
        p = self.plan()
        e = next(pp for pp in p.packages.values() if pp.rel == 'cc/E_same.package')
        self.assertEqual(e.action, 'skip')
        self.assertIn('cannot be told apart', e.reason)
        r = self.run_apply(p)
        self.assertEqual(r['invariant']['changed'], [])
        self.assertTrue(os.path.exists(f.P('cc', 'E_same.package')))
        undo(r['journal'], home=f.home, check_game=False)


if __name__ == '__main__':
    unittest.main(verbosity=2)
