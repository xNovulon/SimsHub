"""SpeedKit profiles and the other chat's mods_switch.py (C:\\Users\\basim\\Tools\\sims4_fitstudio\\mods_switch.py)
on the same FAKE Sims 4 folder under E:\\speedkit_test\\profiles. The real module is imported and its
SIMS/MODS/PARKED/MANIFEST constants are pointed at the fake tree; its game check is never used.

Both directions are checked: SpeedKit fast -> mods_switch full, mods_switch lean -> SpeedKit full,
plus mixed sequences. After every step: no file lost, none in two places, the parking list consistent."""
import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from speedkit import profiles as PR  # noqa: E402
from test_profiles import (BASE, LAYOUT, PACK, REAL_KEEP, StubFast, make_tree, make_verdicts, library,  # noqa: E402
                           logical, snapshot, dirs_of, rmtree, _write_pkg as test_profiles_write_pkg)


def load_mods_switch(sims):
    """The real mods_switch.py as a fresh module whose constants point at the fake Sims folder."""
    if not os.path.exists(PR.MODS_SWITCH):
        raise unittest.SkipTest('mods_switch.py is not on this machine')
    spec = importlib.util.spec_from_file_location('mods_switch_under_test', PR.MODS_SWITCH)
    ms = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ms)
    ms.SIMS = sims
    ms.MODS = os.path.join(sims, 'Mods')
    ms.PARKED = os.path.join(sims, 'Mods_parked')
    ms.MANIFEST = os.path.join(ms.PARKED, '_manifest.json')
    ms.game_running = lambda: (_ for _ in ()).throw(AssertionError('mods_switch must not be asked about the game here'))
    return ms


def quiet(fn):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn()
    return buf.getvalue()


class Compat(unittest.TestCase):
    def setUp(self):
        os.makedirs(BASE, exist_ok=True)
        self.root = tempfile.mkdtemp(dir=BASE)
        self.sims = make_tree(self.root)
        self.mods = os.path.join(self.sims, 'Mods')
        self.parked = os.path.join(self.sims, 'Mods_parked')
        self.lib = library(self.sims)
        self.fast = StubFast()
        self.ms = load_mods_switch(self.sims)
        self.start, dups = logical(self.sims)
        self.assertEqual(dups, [])

    def tearDown(self):
        self.lib.close()
        rmtree(self.root)

    def sk(self, profile, **kw):
        kw.setdefault('keep', None)
        kw.setdefault('mods_switch_path', PR.MODS_SWITCH)
        return PR.switch(profile, dry_run=False, lib=self.lib, sims=self.sims, check_game=False, fastmode=self.fast,
                         verdicts=make_verdicts, **kw)

    def manifest(self):
        with open(os.path.join(self.parked, '_manifest.json'), encoding='utf-8') as f:
            return json.load(f)['moved']

    def parked_files(self):
        out = []
        if os.path.isdir(self.parked):
            for dp, dn, fn in os.walk(self.parked):
                if os.path.normcase(dp) == os.path.normcase(self.parked):
                    dn[:] = [d for d in dn if d != '_old_caches']
                for n in fn:
                    rel = os.path.relpath(os.path.join(dp, n), self.parked).replace(os.sep, '/')
                    if rel != '_manifest.json':
                        out.append(rel)
        return sorted(out)

    def check(self, expect_pack=None):
        now, dups = logical(self.sims)
        self.assertEqual(dups, [], 'a file sits in two places')
        self.assertEqual(now, self.start, 'a file was lost, changed or appeared')
        chk = PR.check_manifest(self.sims)
        self.assertTrue(chk['ok'], chk)
        self.assertEqual(chk['in_both'], [])
        if expect_pack == 'mods':
            self.assertTrue(os.path.exists(os.path.join(self.mods, PACK)))
        elif expect_pack == 'home':
            self.assertTrue(os.path.exists(os.path.join(self.sims, 'SpeedKit', 'fastpack', PACK)))

    def all_in_mods(self):
        for rel, _ in LAYOUT:
            self.assertTrue(os.path.exists(os.path.join(self.mods, rel.replace('/', os.sep))), rel)
        self.assertEqual(self.parked_files(), [])

    # ------------------------------------------------------------------ the two directions the spec names
    def test_speedkit_fast_then_mods_switch_full_restores_everything(self):
        self.sk('fast')
        self.check(expect_pack='mods')
        self.assertTrue(self.parked_files())
        quiet(self.ms.full)
        self.all_in_mods()
        self.assertEqual(self.manifest(), [])
        self.check(expect_pack='mods')                  # the other tool does not know the pack: it stays in Mods
        self.assertEqual(PR.current(sims=self.sims)['profile'], 'custom')   # full + a stray fast pack
        self.sk('full')                                 # SpeedKit takes the pack home
        self.all_in_mods()
        self.check(expect_pack='home')
        self.assertEqual(PR.current(sims=self.sims)['profile'], 'full')

    def test_mods_switch_lean_then_speedkit_full_restores_everything(self):
        out = quiet(self.ms.lean)
        self.assertIn('parked', out)
        self.check()
        self.assertTrue(os.path.exists(os.path.join(self.parked, 'SpeedKit_Monitor.ts4script')))   # lean parks it
        cur = PR.current(sims=self.sims)
        self.assertEqual(cur['profile'], 'studio')                          # recognised as the studio set
        self.assertTrue(any('Monitor' in n for n in cur['notes']))
        p = self.sk('full')
        self.assertTrue(p['verified'], p['warnings'])
        self.all_in_mods()
        self.assertTrue(os.path.exists(os.path.join(self.mods, 'SpeedKit_Monitor.ts4script')))
        self.assertEqual(self.manifest(), [])
        self.assertEqual(dirs_of(self.parked) - {'_old_caches'}, set())
        self.check(expect_pack='home')

    # ------------------------------------------------------------------ same result, mixed sequences
    def test_speedkit_studio_matches_mods_switch_lean(self):
        other = tempfile.mkdtemp(dir=BASE)
        try:
            sims2 = make_tree(other)
            ms2 = load_mods_switch(sims2)
            quiet(ms2.lean)
            self.sk('studio')
            files_a = sorted(r for r in self.parked_files())
            files_b = []
            for dp, dn, fn in os.walk(os.path.join(sims2, 'Mods_parked')):
                if os.path.normcase(dp) == os.path.normcase(os.path.join(sims2, 'Mods_parked')):
                    dn[:] = [d for d in dn if d != '_old_caches']
                for n in fn:
                    rel = os.path.relpath(os.path.join(dp, n), os.path.join(sims2, 'Mods_parked')).replace(os.sep, '/')
                    if rel != '_manifest.json':
                        files_b.append(rel)
            # identical, except that SpeedKit keeps its monitor in Mods in every profile
            self.assertEqual(files_a, sorted(r for r in files_b if r != 'SpeedKit_Monitor.ts4script'))
            with open(os.path.join(sims2, 'Mods_parked', '_manifest.json'), encoding='utf-8') as f:
                m_b = json.load(f)['moved']
            self.assertEqual(sorted(self.manifest()), sorted(e for e in m_b if e != 'SpeedKit_Monitor.ts4script'))
            self.check()
        finally:
            rmtree(other)

    def test_fast_then_lean_then_full_then_speedkit_full(self):
        self.sk('fast')                                  # sim/ split: Mods\sim holds small_tuning
        quiet(self.ms.lean)                              # lean cannot move Mods\sim whole (Mods_parked\sim exists),
        self.check(expect_pack=None)                     # so it parks the files inside it one by one
        self.assertTrue(os.path.exists(os.path.join(self.parked, PACK)))    # ... and the fast pack as well
        cur = PR.current(sims=self.sims)
        self.assertEqual(cur['profile'], 'studio')
        self.assertTrue(any('fast pack' in n for n in cur['notes']))
        quiet(self.ms.full)
        self.assertTrue(os.path.exists(os.path.join(self.mods, PACK)))       # full puts the pack back in Mods
        self.check()
        self.sk('full')
        self.all_in_mods()
        self.check(expect_pack='home')

    def test_speedkit_full_then_lean_works_as_before(self):
        self.sk('studio')
        self.sk('fast')
        self.sk('full')                                  # leaves no empty Mods_parked\sim behind
        quiet(self.ms.lean)                              # so lean parks whole folders again
        self.assertIn('sim/', self.manifest())
        self.assertIn('Sliders/', self.manifest())
        self.check()
        self.assertEqual(PR.current(sims=self.sims)['profile'], 'studio')
        quiet(self.ms.full)
        self.all_in_mods()
        self.check(expect_pack='home')

    def test_fast_then_lean_then_speedkit_fast_again(self):
        self.sk('fast')
        quiet(self.ms.lean)                              # parks the pack and the monitor too
        self.assertTrue(os.path.exists(os.path.join(self.parked, PACK)))
        p = self.sk('fast')
        self.assertTrue(p['verified'], p['warnings'])
        self.check(expect_pack='mods')
        self.assertTrue(os.path.exists(os.path.join(self.mods, 'SpeedKit_Monitor.ts4script')))
        self.assertEqual(PR.current(sims=self.sims)['profile'], 'fast')
        quiet(self.ms.full)
        self.all_in_mods()
        self.check(expect_pack='mods')

    def test_blocked_folder_entry_then_speedkit_full_then_lean_parks_whole_again(self):
        """lean parks sim/ whole; new CC lands in Mods\\sim (so 'full' would skip 'sim/'); SpeedKit's full
        brings sim back file by file and leaves no empty Mods_parked\\sim, so lean parks sim/ whole again."""
        quiet(self.ms.lean)
        test_profiles_write_pkg(os.path.join(self.mods, 'sim', 'new.package'), 'new cc')
        self.start, _ = logical(self.sims)
        self.assertEqual(PR.check_manifest(self.sims)['blocked'], ['sim/'])
        p = self.sk('full')
        self.assertTrue(p['verified'], p['warnings'])
        self.all_in_mods()
        self.assertEqual(dirs_of(self.parked) - {'_old_caches'}, set())
        out = quiet(self.ms.lean)
        self.assertNotIn('skip', out)
        self.assertIn('sim/', self.manifest())
        self.check()
        quiet(self.ms.full)
        self.all_in_mods()
        self.check(expect_pack='home')

    def test_lean_then_speedkit_fast_then_studio_then_full(self):
        quiet(self.ms.lean)
        self.sk('fast')
        self.check(expect_pack='mods')
        self.sk('studio')
        self.check(expect_pack='home')
        self.assertEqual(PR.current(sims=self.sims)['profile'], 'studio')
        quiet(self.ms.full)                              # the other tool restores SpeedKit's studio set too
        self.all_in_mods()
        self.check(expect_pack='home')


if __name__ == '__main__':
    unittest.main(verbosity=1)
