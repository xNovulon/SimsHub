"""speedkit.profiles on FAKE Sims 4 folders under E:\\speedkit_test\\profiles (synthetic packages; a stub
fast-mode module stands in for speedkit.fastmode). Nothing under the real Sims 4 folder is written:
the only real files read are mods_switch.py (for its KEEP list) and, in one test, a read-only copy of
the companions cache.

Helpers here (make_tree, StubFast, make_verdicts, logical, snapshot) are shared with
test_profiles_compat.py."""
import contextlib
import hashlib
import io
import json
import os
import shutil
import sqlite3
import stat
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from speedkit import profiles as PR  # noqa: E402
from speedkit import journal as JR  # noqa: E402
from speedkit.companions import Verdict  # noqa: E402
from speedkit.dbpf import PackageWriter  # noqa: E402
from speedkit.library import Library, PROJECT  # noqa: E402

BASE = r'E:\speedkit_test\profiles'
CASP = 0x034AEECB
REAL_KEEP = ['Resource.cfg', 'desktop.ini', 'scripts/TURBODRIVER_WickedWhims_Scripts.ts4script',
             'scripts/TURBODRIVER_WickedWhims_Tuning.package', 'scripts/desktop.ini',
             'animation/WW_LAMABOY_Animation.package', 'animation/WW_LAMABOY_Animations.package',
             'animation/desktop.ini', 'FitStudio/']
WW = 'scripts/TURBODRIVER_WickedWhims_Scripts.ts4script'
MCCC = 'scripts/mc_cmd_center.ts4script'

# The full library, laid out like the user's (Mods paths). Kind decides how the file is made.
LAYOUT = [
    ('Resource.cfg', 'text'), ('desktop.ini', 'text'),
    (WW, 'script'), ('scripts/TURBODRIVER_WickedWhims_Tuning.package', 'pkg'), ('scripts/desktop.ini', 'text'),
    (MCCC, 'script'), ('scripts/mc_cmd_center.package', 'pkg'), ('scripts/mc_settings.cfg', 'text'),
    ('scripts/!!![NSW] Lighting DARK.package', 'pkg'), ('scripts/HRK_addon.package', 'pkg'),
    ('scripts/lonely_cc.package', 'pkg'),
    ('animation/WW_LAMABOY_Animation.package', 'pkg'), ('animation/WW_LAMABOY_Animations.package', 'pkg'),
    ('animation/desktop.ini', 'text'), ('animation/anim1.package', 'pkg'),
    ('FitStudio/FitStudio.ts4script', 'script'), ('FitStudio/FitStudio.log', 'text'),
    ('FitStudio/MyAnimations/FitStudio_test.package', 'pkg'),
    ('sim/1.package', 'pkg'), ('sim/2.package', 'pkg'), ('sim/m3.package', 'pkg'), ('sim/small_tuning.package', 'pkg'),
    ('sim/desktop.ini', 'text'),
    ('Sliders/slider1.package', 'pkg'), ('Sliders/desktop.ini', 'text'), ('Sliders/Sub/deep slider.package', 'pkg'),
    ('TMEX-Settings/BE-TESTER.log', 'text'), ('TMEX-Settings/DO NOT DELETE THIS FOLDER', 'text'),
    ('Scripts testing/TURBODRIVER_WickedWhims_InappropriateUnlock.package', 'pkg'),
    ('Srsly Pack/hair1.package', 'pkg'), ('Srsly Pack/hair2.package', 'pkg'),
    ('SpeedKit_Monitor.ts4script', 'script'),
]
PACK = '!!!!!SpeedKit_Fast_001.package'


def _write_pkg(path, rel):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    iid = int.from_bytes(hashlib.blake2b(rel.encode(), digest_size=8).digest(), 'little')
    with PackageWriter(path) as w:
        w.add((CASP, 0, iid), ('CASP ' + rel).encode() * 8)


def _write_file(path, rel, kind):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if kind == 'pkg':
        _write_pkg(path, rel)
    elif kind == 'script':
        with zipfile.ZipFile(path, 'w') as z:
            z.writestr('readme.txt', 'script ' + rel)
    else:
        with open(path, 'wb') as f:
            f.write(('text of ' + rel).encode())


def make_tree(root, layout=LAYOUT, with_pack=True, thumbcache=True):
    """A fake '<root>\\The Sims 4' with every LAYOUT file in Mods (the 'full' state), saves/Tray, a
    thumbnail cache and a fast pack in SpeedKit\\fastpack. Returns the Sims folder."""
    sims = os.path.join(root, 'The Sims 4')
    mods = os.path.join(sims, 'Mods')
    for rel, kind in layout:
        _write_file(os.path.join(mods, rel.replace('/', os.sep)), rel, kind)
    os.makedirs(os.path.join(sims, 'saves'))
    with open(os.path.join(sims, 'saves', 'Slot_00000001.save'), 'wb') as f:
        f.write(b'save data')
    os.makedirs(os.path.join(sims, 'Tray'))
    with open(os.path.join(sims, 'Tray', '0x1.trayitem'), 'wb') as f:
        f.write(b'tray data')
    if thumbcache:
        with open(os.path.join(sims, 'localthumbcache.package'), 'wb') as f:
            f.write(b'thumbs')
    if with_pack:
        fp = os.path.join(sims, 'SpeedKit', 'fastpack')
        _write_pkg(os.path.join(fp, PACK), 'pack v1')
        with open(os.path.join(fp, 'fastpack.json'), 'w') as f:
            json.dump({'packages': [PACK]}, f)
    return sims


def library(sims, tag='lib'):
    return Library(db_path=os.path.join(os.path.dirname(sims), tag + '.sqlite'),
                   roots={'Mods': os.path.join(sims, 'Mods'), 'Mods_parked': os.path.join(sims, 'Mods_parked')})


class StubFast:
    """Stands in for speedkit.fastmode: parks sim/ packages except small_tuning (+ extra rels)."""

    def __init__(self, fresh=True, extra=(), fail_update=False, write_on_update=True):
        self.fresh = fresh
        self.extra = {e.lower() for e in extra}
        self.fail_update = fail_update
        self.write_on_update = write_on_update
        self.updates = []
        self.status_calls = []

    def park_set(self, lib, roots=('Mods', 'Mods_parked')):
        out = []
        for p in lib.packages():
            low = p.rel.lower()
            if (low.startswith('sim/') and 'small_tuning' not in low) or low in self.extra:
                out.append((p.root, p.rel, 'CAS-heavy CC catalog'))
        return out

    def status(self, out_dir):
        self.status_calls.append(out_dir)
        return {'fresh': self.fresh, 'why': '' if self.fresh else 'saves changed since the build'}

    def update_pack(self, lib=None, out_dir=None, dry_run=True, check_game=False):
        self.updates.append({'out_dir': out_dir, 'dry_run': dry_run, 'lib': lib is not None})
        if self.fail_update:
            raise RuntimeError('disk full (stub)')
        self.fresh = True
        if not self.write_on_update:
            return {'written': []}
        os.makedirs(out_dir, exist_ok=True)
        _write_pkg(os.path.join(out_dir, '!!!!!SpeedKit_Fast_900.package'), 'pack delta')
        return {'written': ['!!!!!SpeedKit_Fast_900.package']}


# verdicts the way companions.classify would give them for LAYOUT
COMPANIONS = {
    'scripts/turbodriver_wickedwhims_tuning.package': ('core', WW),
    'scripts/mc_cmd_center.package': ('core', MCCC),
    'scripts/hrk_addon.package': ('addon', WW),
    'animation/ww_lamaboy_animation.package': ('addon', WW),
    'animation/ww_lamaboy_animations.package': ('addon', WW),
    'animation/anim1.package': ('addon', WW),
    'fitstudio/myanimations/fitstudio_test.package': ('addon', WW),
    'scripts testing/turbodriver_wickedwhims_inappropriateunlock.package': ('core', WW),
}


def make_verdicts(lib):
    out = {}
    for p in lib.packages():
        kind, script = COMPANIONS.get(p.rel.lower(), ('cc', None))
        out[p.id] = Verdict(kind, script, [])
    return out


def _digest(path):
    h = hashlib.blake2b(digest_size=16)
    with open(path, 'rb') as f:
        h.update(f.read())
    return h.hexdigest()


def logical(sims):
    """{Mods-relative path or 'PACK:name' or 'THUMB': digest} of every mod-folder file wherever it sits
    (Mods, Mods_parked, the fastpack folder), plus 'dups': paths found in more than one place."""
    out, dups = {}, []
    places = [(os.path.join(sims, 'Mods'), False), (os.path.join(sims, 'Mods_parked'), True)]
    for root, parked in places:
        if not os.path.isdir(root):
            continue
        for dp, dn, fn in os.walk(root):
            if parked and os.path.normcase(dp) == os.path.normcase(root):
                dn[:] = [d for d in dn if d != '_old_caches']
            for n in fn:
                rel = os.path.relpath(os.path.join(dp, n), root).replace(os.sep, '/')
                if parked and rel == '_manifest.json':
                    continue
                key = ('PACK:' + n) if ('/' not in rel and n.lower().startswith('!!!!!speedkit_fast_')) else rel
                if key in out:
                    dups.append(key)
                out[key] = _digest(os.path.join(dp, n))
    fp = os.path.join(sims, 'SpeedKit', 'fastpack')
    if os.path.isdir(fp):
        for n in os.listdir(fp):
            if n.lower().startswith('!!!!!speedkit_fast_'):
                if 'PACK:' + n in out:
                    dups.append('PACK:' + n)
                out['PACK:' + n] = _digest(os.path.join(fp, n))
    return out, dups


def snapshot(sims):
    """{path relative to sims: digest} of every file (SpeedKit's journal folder left out)."""
    out = {}
    for dp, dn, fn in os.walk(sims):
        rel_dir = os.path.relpath(dp, sims)
        if rel_dir == 'SpeedKit':
            dn[:] = [d for d in dn if d not in ('journal', 'quarantine', 'staging', 'profiles')]
        for n in fn:
            p = os.path.join(dp, n)
            out[os.path.relpath(p, sims).replace(os.sep, '/')] = _digest(p)
    return out


def dirs_of(root):
    out = set()
    for dp, dn, fn in os.walk(root):
        for d in dn:
            out.add(os.path.relpath(os.path.join(dp, d), root).replace(os.sep, '/'))
    return out


def rmtree(p):
    shutil.rmtree(p, onerror=lambda f, x, e: (os.chmod(x, stat.S_IWRITE), f(x)))


class Base(unittest.TestCase):
    def setUp(self):
        os.makedirs(BASE, exist_ok=True)
        self.root = tempfile.mkdtemp(dir=BASE)
        self.sims = make_tree(self.root)
        self.mods = os.path.join(self.sims, 'Mods')
        self.parked = os.path.join(self.sims, 'Mods_parked')
        self.home = os.path.join(self.sims, 'SpeedKit')
        self.lib = library(self.sims)
        self.fast = StubFast()
        self.start, dups = logical(self.sims)
        self.assertEqual(dups, [])

    def tearDown(self):
        self.lib.close()
        rmtree(self.root)

    def sw(self, profile, dry_run=False, **kw):
        kw.setdefault('check_game', False)
        kw.setdefault('fastmode', self.fast)
        kw.setdefault('verdicts', make_verdicts)
        kw.setdefault('keep', REAL_KEEP)
        return PR.switch(profile, dry_run=dry_run, lib=self.lib, sims=self.sims, **kw)

    def manifest(self):
        with open(os.path.join(self.parked, '_manifest.json'), encoding='utf-8') as f:
            return json.load(f)

    def assert_consistent(self, pack_where=None):
        """No file lost or duplicated, manifest consistent for mods_switch.py, no empty parked folders."""
        now, dups = logical(self.sims)
        self.assertEqual(dups, [], 'a file exists in two places')
        self.assertEqual(now, self.start, 'files changed, got lost or appeared')
        chk = PR.check_manifest(self.sims)
        self.assertTrue(chk['ok'], chk)
        if os.path.isdir(self.parked):
            for d in dirs_of(self.parked):
                if d.split('/')[0] == '_old_caches':
                    continue
                full = os.path.join(self.parked, d)
                self.assertTrue(any(fs for _, _, fs in os.walk(full)), 'empty folder left in Mods_parked: %s' % d)
        # scripts: every script in Mods is at depth <= 1, saves/Tray untouched
        for dp, dn, fn in os.walk(self.mods):
            for n in fn:
                if n.lower().endswith('.ts4script'):
                    rel = os.path.relpath(os.path.join(dp, n), self.mods)
                    self.assertLessEqual(rel.count(os.sep), 1, rel)
        with open(os.path.join(self.sims, 'saves', 'Slot_00000001.save'), 'rb') as f:
            self.assertEqual(f.read(), b'save data')
        if pack_where == 'mods':
            self.assertTrue(os.path.exists(os.path.join(self.mods, PACK)))
        elif pack_where == 'home':
            self.assertFalse(os.path.exists(os.path.join(self.mods, PACK)))
            self.assertTrue(os.path.exists(os.path.join(self.home, 'fastpack', PACK)))

    def in_mods(self, rel):
        return os.path.exists(os.path.join(self.mods, rel.replace('/', os.sep)))

    def in_parked(self, rel):
        return os.path.exists(os.path.join(self.parked, rel.replace('/', os.sep)))


class KeepAndManifest(unittest.TestCase):
    def test_keep_imported_from_mods_switch(self):
        keep, src = PR.load_keep()
        if not os.path.exists(PR.MODS_SWITCH):
            self.skipTest('mods_switch.py is not on this machine')
        self.assertEqual(os.path.normcase(src), os.path.normcase(PR.MODS_SWITCH))
        self.assertEqual(keep, REAL_KEEP)
        keep2, src2 = PR.load_keep(os.path.join(BASE, 'no_such_mods_switch.py'))
        self.assertEqual(keep2, PR.BUILTIN_KEEP)
        self.assertIn('built-in', src2)

    def test_keep_broken_file_falls_back(self):
        os.makedirs(BASE, exist_ok=True)
        d = tempfile.mkdtemp(dir=BASE)
        try:
            p = os.path.join(d, 'mods_switch.py')
            with open(p, 'w') as f:
                f.write('KEEP = 42\n')
            keep, src = PR.load_keep(p)
            self.assertEqual(keep, PR.BUILTIN_KEEP)
            self.assertIn('built-in', src)
            with open(p, 'w') as f:
                f.write('raise SystemExit("boom")\n')
            self.assertEqual(PR.load_keep(p)[0], PR.BUILTIN_KEEP)
        finally:
            rmtree(d)

    def test_keep_matcher_folder_and_case(self):
        kept = PR.keep_matcher(REAL_KEEP)
        self.assertTrue(kept('FitStudio/MyAnimations/x.package'))
        self.assertTrue(kept('fitstudio/x.log'))
        self.assertTrue(kept('SCRIPTS/turbodriver_wickedwhims_scripts.ts4script'))
        self.assertFalse(kept('FitStudioOther/x.package'))
        self.assertFalse(kept('scripts/mc_cmd_center.ts4script'))

    def test_rebuild_splits_folder_entry_when_mods_has_that_folder(self):
        p_files = {'sim/1.package': 'sim/1.package', 'sim/2.package': 'sim/2.package'}
        p_dirs = {'sim': 'sim'}
        out, info = PR.rebuild_manifest(['sim/', 'scripts/a.package'], p_files, p_dirs, m_keys={'sim', 'scripts',
                                                                                             'scripts/a.package'})
        self.assertEqual(out, ['sim/1.package', 'sim/2.package'])
        self.assertEqual(info['split'], ['sim/'])
        self.assertEqual(info['dropped_restored'], ['scripts/a.package'])

    def test_rebuild_keeps_valid_and_foreign_entries_and_drops_nested(self):
        p_files = {'sliders/a.package': 'Sliders/a.package', 'x/y.package': 'x/y.package'}
        p_dirs = {'sliders': 'Sliders', 'x': 'x'}
        entries = ['Sliders/', 'Sliders/a.package', 'Gone/thing.package', 'x/y.package', 'x/y.package']
        out, info = PR.rebuild_manifest(entries, p_files, p_dirs, m_keys=set())
        self.assertEqual(out, ['Sliders/', 'Gone/thing.package', 'x/y.package'])
        self.assertEqual(info['dropped_nested'], ['Sliders/a.package'])
        self.assertEqual(info['kept_stale'], ['Gone/thing.package'])
        self.assertEqual(info['duplicates'], ['x/y.package'])

    def test_rebuild_adds_coarsest_cover(self):
        p_files = {'a/b/c.package': 'A/b/c.package', 'a/d.package': 'A/d.package', 'e/f.package': 'E/f.package',
                   'e/g.package': 'E/g.package'}
        p_dirs = {'a': 'A', 'a/b': 'A/b', 'e': 'E'}
        out, _ = PR.rebuild_manifest([], p_files, p_dirs, m_keys={'e'})
        self.assertEqual(sorted(out), ['A/', 'E/f.package', 'E/g.package'])


class FastmodeInterface(unittest.TestCase):
    """The shapes speedkit.fastmode really returns, and a call that must not leak kwargs into **plan_kw."""

    def test_fresh_understands_fastmode_status(self):
        self.assertEqual(PR._fresh({'state': 'fresh', 'why': []})[0], True)
        f, why = PR._fresh({'state': 'stale', 'why': ['3 save/Tray files are new', 'pack files missing: x']})
        self.assertFalse(f)
        self.assertIn('save/Tray', why)
        self.assertFalse(PR._fresh({'state': 'missing', 'why': ['no fast pack has been built yet']})[0])
        self.assertTrue(PR._fresh('fresh')[0])
        self.assertFalse(PR._fresh(None)[0])
        self.assertTrue(PR._fresh((True, 'ok'))[0])

    def test_park_rels_accepts_every_shape(self):
        class ParkSet(list):
            reasons = {}
        ps = ParkSet([('Mods_parked', 'sim/1.package'), ('Mods', 'sim/2.package')])
        self.assertEqual(PR._park_rels(ps), ['sim/1.package', 'sim/2.package'])
        self.assertEqual(PR._park_rels({('Mods', 'a.package'): 'why'}), ['a.package'])
        self.assertEqual(PR._park_rels([('Mods', 'a.package', 'why')]), ['a.package'])
        self.assertEqual(PR._park_rels((['x\\y.package'], {})), ['x/y.package'])

    def test_call_passes_only_named_parameters(self):
        seen = {}

        def update_pack(lib, refs, out_dir=None, dry_run=True, **plan_kw):
            seen.update(lib=lib, refs=refs, out_dir=out_dir, dry_run=dry_run, plan_kw=plan_kw)
        PR._call(update_pack, None, lib='L', refs='R', out_dir='O', dry_run=False, progress=print, sims='S')
        self.assertEqual(seen, {'lib': 'L', 'refs': 'R', 'out_dir': 'O', 'dry_run': False, 'plan_kw': {}})

        def status(out):
            return out
        self.assertEqual(PR._call(status, 'first', out_dir='ignored'), 'first')

    def test_real_fastmode_status_on_a_fake_tree_is_read_only(self):
        try:
            from speedkit import fastmode
        except Exception as e:                       # built by another agent at the same time
            self.skipTest('speedkit.fastmode not importable: %s' % e)
        os.makedirs(BASE, exist_ok=True)
        root = tempfile.mkdtemp(dir=BASE)
        try:
            sims = make_tree(root)
            before = snapshot(sims)
            lib = library(sims)
            p = PR.switch('fast', dry_run=True, lib=lib, sims=sims, check_game=False, fastmode=fastmode,
                          verdicts=make_verdicts)
            lib.close()
            self.assertFalse(p['pack']['fresh'])       # our stub fastpack.json is not a real build
            self.assertEqual(p['pack']['action'], 'update')
            self.assertEqual(snapshot(sims), before)
        finally:
            rmtree(root)


class Switching(Base):
    def test_malformed_manifest_is_refused(self):
        os.makedirs(self.parked)
        before = snapshot(self.sims)
        for text in ('{not json', '[1, 2]', '{"moved": "sim/"}', '{"moved": ["../../Windows/x"]}',
                     '{"moved": ["C:/x.package"]}', '{"moved": [3]}'):
            with open(os.path.join(self.parked, '_manifest.json'), 'w') as f:
                f.write(text)
            before = snapshot(self.sims)
            for prof in ('studio', 'full', 'fast'):
                with self.assertRaises(PR.ProfileError) as cm:
                    self.sw(prof)
                self.assertIn('parking list', str(cm.exception))
            self.assertEqual(snapshot(self.sims), before)
            self.assertFalse(PR.check_manifest(self.sims)['ok'])

    def test_dry_run_changes_nothing(self):
        before = snapshot(self.sims)
        for prof in ('studio', 'fast', 'full'):
            plan = self.sw(prof, dry_run=True)
            self.assertTrue(plan['dry_run'])
            self.assertEqual(plan['done'], [])
        self.assertEqual(snapshot(self.sims), before)
        self.assertFalse(os.path.exists(os.path.join(self.home, 'journal')))
        self.assertFalse(os.path.exists(self.parked))
        plan = self.sw('studio', dry_run=True)
        self.assertEqual(plan['counts']['park_files'], len(LAYOUT) - 11 - 1)  # all but KEEP's 11 files and the monitor
        json.dumps(plan)                                                       # plain data for the CLI

    def test_full_studio_fast_full_cycle(self):
        # full -> studio: exactly the KEEP set (+ the monitor) stays
        p = self.sw('studio')
        self.assertTrue(p['verified'], p['warnings'])
        kept = PR.keep_matcher(REAL_KEEP)
        for rel, _ in LAYOUT:
            want_mods = kept(rel) or rel == 'SpeedKit_Monitor.ts4script'
            self.assertEqual(self.in_mods(rel), want_mods, rel)
            self.assertEqual(self.in_parked(rel), not want_mods, rel)
        m = self.manifest()['moved']
        for folder in ('sim/', 'Sliders/', 'TMEX-Settings/', 'Scripts testing/', 'Srsly Pack/'):
            self.assertIn(folder, m)                                     # whole folders, like mods_switch.py
        self.assertIn('scripts/mc_cmd_center.ts4script', m)              # scripts/ keeps things: file entries
        self.assertIn('animation/anim1.package', m)
        self.assertFalse(os.path.exists(os.path.join(self.sims, 'localthumbcache.package')))  # quarantined
        self.assertEqual(PR.read_state(self.sims)['profile'], 'studio')
        self.assertEqual(PR.current(sims=self.sims, keep=REAL_KEEP)['profile'], 'studio')
        self.assert_consistent(pack_where='home')
        self.assertEqual(p['counts']['folder_moves'], 5)

        # studio -> fast: only sim/ CAS packs stay parked, the pack goes to the Mods root
        with open(os.path.join(self.sims, 'localthumbcache.package'), 'wb') as f:
            f.write(b'thumbs again')
        p = self.sw('fast')
        self.assertTrue(p['verified'], p['warnings'])
        self.assertFalse(os.path.exists(os.path.join(self.sims, 'localthumbcache.package')))
        for rel in ('sim/1.package', 'sim/2.package', 'sim/m3.package'):
            self.assertTrue(self.in_parked(rel) and not self.in_mods(rel), rel)
        # sim/ keeps a package in fast mode, so its desktop.ini stays with it
        for rel in ('sim/small_tuning.package', 'sim/desktop.ini', MCCC, 'scripts/mc_settings.cfg', 'TMEX-Settings/BE-TESTER.log',
                    'Sliders/Sub/deep slider.package', 'animation/anim1.package', 'FitStudio/FitStudio.log'):
            self.assertTrue(self.in_mods(rel) and not self.in_parked(rel), rel)
        m = self.manifest()['moved']
        self.assertNotIn('sim/', m)                                       # Mods has a sim folder now: split
        self.assertEqual(sorted(m), ['sim/1.package', 'sim/2.package', 'sim/m3.package'])
        self.assertTrue(os.path.exists(os.path.join(self.mods, PACK)))
        # at the Mods root, first in the game's (upper-cased NTFS) order, so its copies win
        self.assertEqual(sorted(os.listdir(self.mods), key=str.upper)[0], PACK)
        self.assertEqual(PR.current(sims=self.sims, keep=REAL_KEEP)['profile'], 'fast')
        self.assertEqual(PR.read_state(self.sims)['profile'], 'fast')
        self.assertEqual(p['pack']['action'], 'none')
        self.assert_consistent(pack_where='mods')

        # fast -> full: everything back, pack home, manifest empty, no empty folders
        p = self.sw('full')
        self.assertTrue(p['verified'], p['warnings'])
        for rel, _ in LAYOUT:
            self.assertTrue(self.in_mods(rel) and not self.in_parked(rel), rel)
        self.assertEqual(self.manifest()['moved'], [])
        self.assertEqual(dirs_of(self.parked), set())
        self.assertEqual(PR.current(sims=self.sims, keep=REAL_KEEP)['profile'], 'full')
        self.assert_consistent(pack_where='home')
        kinds = {j[1] for j in JR.list_journals(self.home)}
        self.assertEqual(kinds, {'profile'})

    def test_same_profile_twice_is_a_no_op(self):
        self.sw('studio')
        n = len(JR.list_journals(self.home))
        p = self.sw('studio')
        self.assertTrue(p['nothing_to_do'])
        self.assertEqual(p['counts']['moves'], 0)
        self.assertEqual(len(JR.list_journals(self.home)), n)

    def test_undo_restores_exact_state(self):
        self.sw('studio')
        with open(os.path.join(self.sims, 'localthumbcache.package'), 'wb') as f:
            f.write(b'thumbs 2')
        before = snapshot(self.sims)
        before_dirs = dirs_of(self.mods), dirs_of(self.parked)
        p = self.sw('fast')
        self.assertTrue(self.in_mods('sim/small_tuning.package'))          # the switch created Mods\sim
        self.assertNotEqual(snapshot(self.sims), before)
        acts = PR.undo_switch(p['journal'], dry_run=True, sims=self.sims, check_game=False)
        self.assertTrue(acts)
        self.assertNotEqual(snapshot(self.sims), before)                  # dry run changed nothing
        PR.undo_switch(p['journal'], dry_run=False, sims=self.sims, check_game=False)
        # manifest, state, pack, mods exactly; the thumbnail cache has its own journal
        without_cache = {k: v for k, v in before.items() if k != 'localthumbcache.package'}
        self.assertEqual(snapshot(self.sims), without_cache)
        self.assertEqual((dirs_of(self.mods), dirs_of(self.parked)), before_dirs)   # no empty Mods\sim left
        self.assertTrue(PR.check_manifest(self.sims)['ok'])
        self.assertTrue(p['thumbcache_journal'])
        PR.undo_switch(p['thumbcache_journal'], dry_run=False, sims=self.sims, check_game=False)
        self.assertEqual(snapshot(self.sims), before)

    def test_undo_works_after_the_game_rebuilt_its_thumbnail_cache(self):
        """The normal flow: switch, play (the game writes a new localthumbcache.package), undo."""
        self.sw('studio')
        with open(os.path.join(self.sims, 'localthumbcache.package'), 'wb') as f:
            f.write(b'thumbs of the studio set')
        before = snapshot(self.sims)
        p = self.sw('fast')
        self.assertFalse(os.path.exists(os.path.join(self.sims, 'localthumbcache.package')))
        with open(os.path.join(self.sims, 'localthumbcache.package'), 'wb') as f:
            f.write(b'rebuilt by the game in fast mode')
        self.assertTrue(PR.undo_switch(p['journal'], dry_run=True, sims=self.sims, check_game=False))
        PR.undo_switch(p['journal'], dry_run=False, sims=self.sims, check_game=False)
        now = snapshot(self.sims)
        self.assertEqual({k: v for k, v in now.items() if k != 'localthumbcache.package'},
                         {k: v for k, v in before.items() if k != 'localthumbcache.package'})
        self.assertEqual(PR.current(sims=self.sims, keep=REAL_KEEP)['profile'], 'studio')
        # refusals are plain ProfileErrors: undone twice, or a journal of another kind
        with self.assertRaises(PR.ProfileError):
            PR.undo_switch(p['journal'], dry_run=False, sims=self.sims, check_game=False)
        j = JR.Journal('merge', 'not a profile switch', home=self.home, sims=self.sims, check_game=False)
        j.close()
        with self.assertRaises(PR.ProfileError) as cm:
            PR.undo_switch(j.id, dry_run=True, sims=self.sims, check_game=False)
        self.assertIn('not a profile switch', str(cm.exception))

    def test_refuses_while_the_game_runs(self):
        before = snapshot(self.sims)
        with mock.patch.object(PR, 'game_running', return_value=True), \
                mock.patch.object(JR, 'game_running', return_value=True):
            for prof in PROFILES_ALL:
                with self.assertRaises(PR.ProfileError) as cm:
                    PR.switch(prof, dry_run=False, lib=self.lib, sims=self.sims, fastmode=self.fast,
                              verdicts=make_verdicts, keep=REAL_KEEP)
                self.assertIn('running', str(cm.exception))
            plan = PR.switch('studio', dry_run=True, lib=self.lib, sims=self.sims, verdicts=False, keep=REAL_KEEP)
            self.assertTrue(plan['game_running'])
            self.assertIn('running', plan['warnings'][0])
            # a stale pack is not even brought home or updated: the refusal comes before anything
            self.fast.fresh = False
            with self.assertRaises(PR.ProfileError):
                PR.switch('fast', dry_run=False, lib=self.lib, sims=self.sims, fastmode=self.fast,
                          verdicts=make_verdicts, keep=REAL_KEEP)
            self.assertEqual(self.fast.updates, [])
            self.assertEqual(self.fast.status_calls, [])
        self.assertEqual(snapshot(self.sims), before)
        self.assertFalse(os.path.exists(os.path.join(self.home, 'journal')))

    def test_game_starting_half_way_stops_and_can_be_undone(self):
        self.sw('studio')
        before = snapshot(self.sims)
        before_dirs = dirs_of(self.mods), dirs_of(self.parked)
        calls = {'n': 0}

        def flaky():
            calls['n'] += 1
            return calls['n'] > 4                   # the game "starts" after a few steps
        with mock.patch.object(PR, 'game_running', return_value=False), \
                mock.patch.object(JR, 'game_running', side_effect=flaky):
            with self.assertRaises(PR.ProfileError) as cm:
                self.sw('fast', check_game=True)
        # the journal refuses mid-way; the rollback refuses too (the game runs): nothing is lost meanwhile
        msg = str(cm.exception)
        self.assertIn('stopped', msg)
        now, dups = logical(self.sims)
        self.assertEqual(dups, [])
        self.assertEqual(now, self.start)
        self.assertIn('undo journal', msg)
        jid = msg.split('undo journal ')[1].rstrip('.')
        PR.undo_switch(jid, dry_run=False, sims=self.sims, check_game=False)
        self.assertEqual(snapshot(self.sims), before)
        self.assertEqual((dirs_of(self.mods), dirs_of(self.parked)), before_dirs)

    def test_failure_half_way_is_undone(self):
        self.sw('studio')
        before = snapshot(self.sims)
        real_move = JR.Journal.move
        calls = {'n': 0}

        def failing_move(j, src, dst):
            calls['n'] += 1
            if calls['n'] == 7:
                raise PermissionError(32, 'file in use (simulated)', src)
            return real_move(j, src, dst)
        with mock.patch.object(JR.Journal, 'move', failing_move):
            with self.assertRaises(PR.ProfileError) as cm:
                self.sw('fast')
        self.assertIn('put back', str(cm.exception))
        self.assertEqual(snapshot(self.sims), before)
        self.assertEqual(PR.current(sims=self.sims, keep=REAL_KEEP)['profile'], 'studio')
        self.assertTrue(PR.check_manifest(self.sims)['ok'])

    def _crash_every_step(self, target, exc=PermissionError):
        """Fail every journal step of a switch to target in turn - before it starts and after its move
        happened - and check the rollback gives back exactly the files and folders there were."""
        before = snapshot(self.sims)
        before_dirs = dirs_of(self.mods), dirs_of(self.parked)
        real_step, real_done = JR.Journal._step, JR.Journal._done
        runs = 0
        for where in ('before', 'after'):
            n = 0
            while True:
                n += 1
                calls = {'n': 0}

                def step(j, op, **kw):
                    if where == 'before':
                        calls['n'] += 1
                        if calls['n'] == n:
                            raise exc('simulated failure before step %d' % n)
                    return real_step(j, op, **kw)

                def done(j, s):
                    if where == 'after':
                        calls['n'] += 1
                        if calls['n'] == n:
                            raise exc('simulated failure after step %d' % n)
                    return real_done(j, s)
                with mock.patch.object(JR.Journal, '_step', step), mock.patch.object(JR.Journal, '_done', done):
                    try:
                        p = self.sw(target)
                    except (PR.ProfileError, exc):
                        p = None
                if p is None:
                    runs += 1
                    self.assertEqual(snapshot(self.sims), before, '%s step %d' % (where, n))
                    self.assertEqual((dirs_of(self.mods), dirs_of(self.parked)), before_dirs, '%s step %d' % (where, n))
                    continue
                # n passed the last step: the switch went through; undo it for the next round
                self.assertGreater(n, 5)
                PR.undo_switch(p['journal'], dry_run=False, sims=self.sims, check_game=False)
                if p.get('thumbcache_journal'):
                    PR.undo_switch(p['thumbcache_journal'], dry_run=False, sims=self.sims, check_game=False)
                self.assertEqual(snapshot(self.sims), before)
                self.assertEqual((dirs_of(self.mods), dirs_of(self.parked)), before_dirs)
                break
        return runs

    def test_failure_at_every_step_is_rolled_back(self):
        self.sw('studio')
        os.makedirs(os.path.join(self.parked, 'Srsly Pack', 'Optional', 'empty'))   # empty folders of a download
        with open(os.path.join(self.sims, 'localthumbcache.package'), 'wb') as f:
            f.write(b'thumbs')
        self.assertGreater(self._crash_every_step('fast'), 20)

    def test_ctrl_c_half_way_is_rolled_back_and_re_raised(self):
        self.sw('fast')
        with open(os.path.join(self.sims, 'localthumbcache.package'), 'wb') as f:
            f.write(b'thumbs')
        self.assertGreater(self._crash_every_step('studio', exc=KeyboardInterrupt), 20)
        before = snapshot(self.sims)
        real_move = JR.Journal.move
        calls = {'n': 0}

        def interrupted(j, src, dst):
            calls['n'] += 1
            if calls['n'] == 3:
                raise KeyboardInterrupt()
            return real_move(j, src, dst)
        with mock.patch.object(JR.Journal, 'move', interrupted):
            with self.assertRaises(KeyboardInterrupt):
                self.sw('full')
        self.assertEqual(snapshot(self.sims), before)
        self.assertTrue(PR.check_manifest(self.sims)['ok'])

    def test_empty_folders(self):
        """Empty folders that were there stay (also through a rollback/undo); a parked empty folder comes
        back with 'full'; a folder a switch emptied goes, even if an old 'dir/' entry named it."""
        os.makedirs(os.path.join(self.mods, 'scripts', 'EmptySettings'))
        os.makedirs(os.path.join(self.mods, 'Sliders', 'Empty2'))
        os.makedirs(os.path.join(self.mods, 'EmptyTop'))
        before_dirs = dirs_of(self.mods)
        p = self.sw('studio')
        self.assertTrue(self.in_mods('scripts/EmptySettings'))        # scripts/ was emptied only partly
        self.assertTrue(self.in_parked('Sliders/Empty2'))             # went along with its folder
        PR.undo_switch(p['journal'], dry_run=False, sims=self.sims, check_game=False)
        self.assertEqual(dirs_of(self.mods), before_dirs)
        self.assertEqual(dirs_of(self.parked), set())
        # the other tool parks EmptyTop/ as a folder entry; SpeedKit's 'full' brings it back
        os.makedirs(self.parked, exist_ok=True)
        os.replace(os.path.join(self.mods, 'EmptyTop'), os.path.join(self.parked, 'EmptyTop'))
        with open(os.path.join(self.parked, '_manifest.json'), 'w') as f:
            json.dump({'moved': ['EmptyTop/']}, f)
        self.sw('full')
        self.assertTrue(self.in_mods('EmptyTop'))
        self.assertEqual(self.manifest()['moved'], [])
        self.assertEqual(dirs_of(self.parked), set())
        # 'sim/' parked whole, then new CC dropped into Mods\sim: 'full' brings sim back file by file and
        # removes the emptied Mods_parked\sim although the old list named it
        shutil.move(os.path.join(self.mods, 'sim'), os.path.join(self.parked, 'sim'))
        with open(os.path.join(self.parked, '_manifest.json'), 'w') as f:
            json.dump({'moved': ['sim/']}, f)
        _write_pkg(os.path.join(self.mods, 'sim', 'new.package'), 'new cc')
        self.start, _ = logical(self.sims)
        self.assertEqual(PR.check_manifest(self.sims)['blocked'], ['sim/'])
        self.sw('full')
        self.assertFalse(os.path.exists(os.path.join(self.parked, 'sim')))
        self.assert_consistent(pack_where='home')

    def test_pack_names_are_exact(self):
        """Only '!!!!!SpeedKit_Fast_###.package' at the Mods root is the pack (fastmode's own pattern)."""
        copy = '!!!!!SpeedKit_Fast_001 - Copy.package'
        _write_pkg(os.path.join(self.mods, copy), 'a user copy')
        self.start, _ = logical(self.sims)
        self.sw('fast')
        self.assertTrue(self.in_mods(copy))
        self.sw('studio')
        self.assertTrue(self.in_parked(copy) and not self.in_mods(copy))
        self.assertIn(copy, self.manifest()['moved'])
        self.assertEqual(sorted(os.listdir(os.path.join(self.home, 'fastpack'))), sorted(['fastpack.json', PACK]))
        self.sw('full')
        self.assert_consistent(pack_where='home')

    def test_script_and_companions_stay_together(self):
        keep = ['Resource.cfg', 'scripts/HRK_addon.package', MCCC]
        p = self.sw('studio', keep=keep, dry_run=True)
        parked = {r.lower() for r in p['target_parked']}
        self.assertNotIn(WW.lower(), parked)                               # the addon needs WickedWhims
        self.assertNotIn('scripts/turbodriver_wickedwhims_tuning.package', parked)   # same-folder core companion
        self.assertNotIn('scripts/mc_cmd_center.package', parked)          # MCCC's own package goes with it
        self.assertIn('scripts testing/turbodriver_wickedwhims_inappropriateunlock.package', parked)  # optional, other folder
        self.assertIn('scripts/lonely_cc.package', parked)
        self.assertTrue(any('kept script' in n for n in p['notes']))
        # a companion-less script parked while its core companion is kept would be flipped too
        keep = ['scripts/TURBODRIVER_WickedWhims_Tuning.package']
        p = self.sw('studio', keep=keep, dry_run=True)
        self.assertNotIn(WW.lower(), {r.lower() for r in p['target_parked']})

    def test_fast_never_parks_scripts_fitstudio_or_animation(self):
        self.fast.extra = {'fitstudio/myanimations/fitstudio_test.package', 'animation/anim1.package',
                           'scripts/lonely_cc.package'}
        p = self.sw('fast', dry_run=True)
        parked = {r.lower() for r in p['target_parked']}
        self.assertNotIn('fitstudio/myanimations/fitstudio_test.package', parked)
        self.assertNotIn('animation/anim1.package', parked)
        self.assertIn('scripts/lonely_cc.package', parked)
        self.assertFalse(any(r.endswith('.ts4script') for r in parked))

    def test_stale_pack_is_updated_before_switching(self):
        self.fast.fresh = False
        plan = self.sw('fast', dry_run=True)
        self.assertEqual(plan['pack']['action'], 'update')
        self.assertEqual(self.fast.updates, [])                             # dry run: no update
        p = self.sw('fast')
        self.assertEqual(len(self.fast.updates), 1)
        self.assertFalse(self.fast.updates[0]['dry_run'])
        self.assertTrue(os.path.exists(os.path.join(self.mods, PACK)))
        self.assertTrue(os.path.exists(os.path.join(self.mods, '!!!!!SpeedKit_Fast_900.package')))
        self.assertEqual(PR.current(sims=self.sims, keep=REAL_KEEP)['profile'], 'fast')
        # stale again while deployed: the pack comes home for the update, then goes back
        self.fast.fresh = False
        self.fast.write_on_update = False
        n = len(self.fast.updates)
        p2 = self.sw('fast')
        self.assertEqual(p2['pack']['action'], 'updated')
        self.assertTrue(p2['pack']['brought_home'])
        self.assertEqual(len(self.fast.updates), n + 1)
        self.assertTrue(os.path.exists(os.path.join(self.mods, PACK)))
        self.assertTrue(p2['cc_changed'])
        # a status that only looks in the fastpack folder: stale while deployed, fresh once home -> no update,
        # the same files go back, and the CC set did not change (the thumbnail cache is left alone)
        self.fast.status = lambda out_dir: {'fresh': os.path.exists(os.path.join(out_dir, PACK))}
        with open(os.path.join(self.sims, 'localthumbcache.package'), 'wb') as f:
            f.write(b'thumbs 3')
        p3 = self.sw('fast')
        self.assertEqual(p3['pack']['action'], 'checked at home')
        self.assertEqual(len(self.fast.updates), n + 1)
        self.assertFalse(p3['cc_changed'])
        self.assertTrue(os.path.exists(os.path.join(self.sims, 'localthumbcache.package')))
        self.assertTrue(os.path.exists(os.path.join(self.mods, PACK)))
        self.assertEqual(PR.current(sims=self.sims, keep=REAL_KEEP)['profile'], 'fast')

    def test_pack_update_failure_changes_nothing(self):
        self.sw('fast')
        before = snapshot(self.sims)
        self.fast.fresh = False
        self.fast.fail_update = True
        with self.assertRaises(PR.ProfileError) as cm:
            self.sw('fast')
        self.assertIn('not changed', str(cm.exception))
        self.assertEqual(snapshot(self.sims), before)                        # pack back in Mods

    def test_pack_goes_back_when_the_switch_after_its_update_fails(self):
        self.sw('fast')
        before = snapshot(self.sims)
        self.fast.fresh = False
        self.fast.write_on_update = False                   # the update only makes status say 'fresh'
        with mock.patch.object(PR, '_execute', side_effect=PR.ProfileError('Switching to fast stopped: boom.')):
            with self.assertRaises(PR.ProfileError) as cm:
                self.sw('fast')
        self.assertIn('put back', str(cm.exception))
        self.assertEqual(snapshot(self.sims), before)         # the pack is in Mods again
        self.assertEqual(PR.current(sims=self.sims, keep=REAL_KEEP)['profile'], 'fast')

    def test_fast_refuses_without_a_pack(self):
        os.remove(os.path.join(self.home, 'fastpack', PACK))
        self.start.pop('PACK:' + PACK)
        self.fast.fresh = False
        self.fast.write_on_update = False
        before = snapshot(self.sims)
        plan = self.sw('fast', dry_run=True)
        self.assertEqual(plan['pack']['action'], 'update')
        with self.assertRaises(PR.ProfileError):
            self.sw('fast')
        self.assertEqual(snapshot(self.sims), before)
        with self.assertRaises(PR.ProfileError):
            self.sw('fast', update_pack=False)
        self.assertEqual(snapshot(self.sims), before)

    def test_fast_needs_fastmode(self):
        with mock.patch.object(PR, '_load_fastmode', return_value=(None, 'not built yet')):
            with self.assertRaises(PR.ProfileError) as cm:
                PR.switch('fast', dry_run=True, lib=self.lib, sims=self.sims, check_game=False, verdicts=False)
        self.assertIn('not built yet', str(cm.exception))

    def test_parked_monitor_comes_back(self):
        os.makedirs(self.parked)
        os.replace(os.path.join(self.mods, 'SpeedKit_Monitor.ts4script'), os.path.join(self.parked, 'SpeedKit_Monitor.ts4script'))
        with open(os.path.join(self.parked, '_manifest.json'), 'w') as f:
            json.dump({'moved': ['SpeedKit_Monitor.ts4script']}, f)
        self.assertIn('Monitor', ' '.join(PR.current(sims=self.sims, keep=REAL_KEEP)['notes']))
        self.sw('studio')
        self.assertTrue(self.in_mods('SpeedKit_Monitor.ts4script'))
        self.assertNotIn('SpeedKit_Monitor.ts4script', self.manifest()['moved'])
        self.assert_consistent()

    def test_same_path_in_both_roots_is_never_overwritten(self):
        os.makedirs(os.path.join(self.parked, 'Sliders'))
        other = os.path.join(self.parked, 'Sliders', 'slider1.package')
        _write_pkg(other, 'a different copy')
        d_parked = _digest(other)
        d_mods = _digest(os.path.join(self.mods, 'Sliders', 'slider1.package'))
        p = self.sw('full')
        self.assertIn('Sliders/slider1.package', p['conflicts'])
        self.assertTrue(any('both' in w for w in p['warnings']))
        self.assertEqual(_digest(other), d_parked)
        self.assertEqual(_digest(os.path.join(self.mods, 'Sliders', 'slider1.package')), d_mods)
        self.assertIn('Sliders/slider1.package', self.manifest()['moved'])    # still listed, as mods_switch would
        self.assertEqual(PR.current(sims=self.sims, keep=REAL_KEEP)['profile'], 'full')

    def test_foreign_entries_and_keys_are_kept(self):
        self.sw('studio')
        m = self.manifest()
        m['note'] = 'written by someone else'
        m['moved'].append('Gone/thing.package')
        with open(os.path.join(self.parked, '_manifest.json'), 'w') as f:
            json.dump(m, f, indent=1)
        self.sw('fast')
        m2 = self.manifest()
        self.assertEqual(m2['note'], 'written by someone else')
        self.assertIn('Gone/thing.package', m2['moved'])
        self.assertTrue(PR.check_manifest(self.sims)['ok'])

    def test_unlisted_parked_file_is_listed_and_restored(self):
        self.sw('studio')
        m = self.manifest()
        m['moved'].remove('Sliders/')                                          # e.g. an interrupted run
        with open(os.path.join(self.parked, '_manifest.json'), 'w') as f:
            json.dump(m, f, indent=1)
        chk = PR.check_manifest(self.sims)
        self.assertFalse(chk['ok'])
        self.assertTrue(chk['unlisted'])
        self.sw('fast')                                                        # heals the list (Sliders come back)
        self.assertTrue(self.in_mods('Sliders/slider1.package'))
        self.sw('studio')
        self.assertIn('Sliders/', self.manifest()['moved'])
        self.assert_consistent()

    def test_speedkit_merged_and_loose_are_ordinary_mods(self):
        """Only Mods\\SpeedKit_Monitor.ts4script and root '!!!!!SpeedKit_Fast_*.package' are SpeedKit's own;
        merge.py's 'SpeedKit Merged\\' / 'SpeedKit Loose\\' hold user CC and move like any mod."""
        extra = ['SpeedKit Merged/CAS_001.package', 'SpeedKit Loose/conflicting.package', 'SpeedKit_Other.package',
                 'sub/SpeedKit_Monitor.ts4script', 'sub/!!!!!SpeedKit_Fast_001.package']
        for rel in extra:
            _write_file(os.path.join(self.mods, rel.replace('/', os.sep)), rel,
                        'script' if rel.endswith('.ts4script') else 'pkg')
        self.start, _ = logical(self.sims)
        self.sw('studio')
        for rel in extra:
            self.assertTrue(self.in_parked(rel) and not self.in_mods(rel), rel)
        self.assertIn('SpeedKit Merged/', self.manifest()['moved'])
        self.assertTrue(self.in_mods('SpeedKit_Monitor.ts4script'))
        self.sw('full')
        for rel in extra:
            self.assertTrue(self.in_mods(rel) and not self.in_parked(rel), rel)
        self.assert_consistent(pack_where='home')

    def test_current_reports_custom_with_differences(self):
        self.sw('studio')
        os.makedirs(os.path.join(self.mods, 'Srsly Pack'))
        os.replace(os.path.join(self.parked, 'Srsly Pack', 'hair1.package'), os.path.join(self.mods, 'Srsly Pack', 'hair1.package'))
        cur = PR.current(sims=self.sims, keep=REAL_KEEP)
        self.assertEqual(cur['profile'], 'custom')
        self.assertEqual(cur['closest'], 'studio')
        self.assertEqual(cur['differences']['to_park'], ['Srsly Pack/hair1.package'])
        st = PR.status(sims=self.sims, fastmode=self.fast)
        text = PR.format_status(st)
        self.assertIn('custom', text)
        self.assertFalse(st['state_matches'])

    def test_default_companion_check_runs_on_a_fake_tree(self):
        """verdicts=None uses companions.classify (cache seeded read-only from the project's cache)."""
        cache = os.path.join(self.root, 'companions.sqlite')
        src = os.path.join(PROJECT, 'data', 'companions.sqlite')
        if os.path.exists(src):
            s = sqlite3.connect('file:%s?mode=ro' % src.replace('\\', '/'), uri=True)
            d = sqlite3.connect(cache)
            s.backup(d)
            d.close()
            s.close()
        p = self.sw('studio', verdicts=None, companions_cache=cache, dry_run=True)
        self.assertFalse(any('skipped' in w for w in p['warnings']), p['warnings'])


PROFILES_ALL = PR.PROFILES


if __name__ == '__main__':
    unittest.main(verbosity=1)
