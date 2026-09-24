"""Adversarial review tests for the SpeedKit Monitor (ingame/speedkit_monitor) and speedkit/ingame_install.py.

Everything runs under Python 3.12 on a FAKE Sims 4 folder under E:\\speedkit_test\\ingame_review, with tiny
stand-in modules for the game-only imports (zone, services). The real Sims 4 folder and E:\\The Sims 4 are
never written; the game is never started.

    python tests/test_ingame_review.py
"""
import ctypes
import csv
import os
import shutil
import sys
import tempfile
import time
import types
import unittest
from ctypes import wintypes
from unittest import mock

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT)
sys.path.insert(0, os.path.join(PROJECT, 'ingame'))

from speedkit_monitor import common, hooks, loadtimer, lagmeter, ccguard, sampling  # noqa: E402
from speedkit import ingame_install as ii  # noqa: E402
from speedkit import journal as journal_mod  # noqa: E402

SCRATCH = r'E:\speedkit_test\ingame_review'
FRESH_STATE = dict(loadtimer.state)


def read_rows(path):
    with open(path, encoding='utf-8', newline='') as f:
        rows = list(csv.reader(f))
    return [dict(zip(rows[0], r)) for r in rows[1:]]


def lock_exclusively(path):
    """Open path with share mode 0, the way Excel holds a CSV it has open. Returns the handle."""
    k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    h = k32.CreateFileW(path, 0x80000000, 0, None, 3, 0x80, None)
    if h in (None, wintypes.HANDLE(-1).value):
        raise OSError('could not lock %s' % path)
    return h


def unlock(h):
    ctypes.WinDLL('kernel32').CloseHandle(wintypes.HANDLE(h))


def fake_zone_module(update=None):
    """A stand-in for the game's zone module: Zone with the three methods the monitor hooks."""
    z = types.ModuleType('zone')

    class Zone:
        def __init__(self, zone_id):
            self.id = zone_id
            self.updates = 0

        def start_services(self, gameplay_zone_data, save_slot_data):
            return 'started'

        def update(self, absolute_ticks):
            self.updates += 1
            return absolute_ticks

        def on_loading_screen_animation_finished(self):
            return 'loaded'
    if update is not None:
        Zone.update = update
    z.Zone = Zone
    return z


def fake_services_module():
    s = types.ModuleType('services')
    s.menu_calls = []
    s.on_enter_main_menu = lambda: s.menu_calls.append(1)
    s.current_zone_id = lambda: 0x1234
    return s


class FakeSimsCase(unittest.TestCase):
    """A fresh fake Sims 4 folder per test; the monitor pointed at it; stand-in game modules removed after."""

    def setUp(self):
        os.makedirs(SCRATCH, exist_ok=True)
        self.root = tempfile.mkdtemp(dir=SCRATCH)
        self.sims = os.path.join(self.root, 'The Sims 4')
        os.makedirs(os.path.join(self.sims, 'Mods'))
        common.configure(self.sims)
        loadtimer.state.clear()
        loadtimer.state.update({k: (dict(v) if isinstance(v, dict) else v) for k, v in FRESH_STATE.items()})
        self.saved_modules = {k: sys.modules.get(k) for k in ('zone', 'services', 'areaserver')}
        self.cc_calls = []
        p = mock.patch.object(ccguard, 'run_after_load', lambda: self.cc_calls.append(1))
        p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        if lagmeter.running():
            lagmeter.finish('test teardown', show=False)
        for k, v in self.saved_modules.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
        common.configure(None)
        shutil.rmtree(self.root, ignore_errors=True)

    def csv_path(self):
        return os.path.join(self.sims, 'SpeedKit', 'reports', 'loadtimes.csv')


# ====================================================================== where the Sims folder is
class SimsDirTests(unittest.TestCase):
    def test_nested_mods_folder_does_not_put_reports_inside_mods(self):
        """A zip extracted as Mods\\Mods\\SpeedKit_Monitor.ts4script is loaded by the game (one folder down);
        the Sims folder is still the parent of the OUTER Mods, so nothing is written into Mods."""
        base = r'C:\U\Documents\Electronic Arts\The Sims 4'
        inner = r'\SpeedKit_Monitor.ts4script\speedkit_monitor\common.pyc'
        self.assertEqual(common.find_sims_dir(base + r'\Mods' + inner), base)
        self.assertEqual(common.find_sims_dir(base + r'\Mods\Sub' + inner), base)
        self.assertEqual(common.find_sims_dir(base + r'\Mods\Mods' + inner), base)
        self.assertIsNone(common.find_sims_dir(base + r'\Mods\A\B' + inner))    # never loaded by the game
        self.assertIsNone(common.find_sims_dir(r'C:\tools\speedkit_monitor\common.py'))


# ====================================================================== load timer
class LoadTimerReviewTests(FakeSimsCase):
    def test_cc_guard_still_runs_when_the_csv_is_locked(self):
        """loadtimes.csv open in Excel (exclusive lock) must not stop the CC guard, and nothing may raise."""
        z = fake_zone_module().Zone(0xABC)
        loadtimer.on_zone_start(z)
        loadtimer.on_lot_loaded(z)                       # creates the CSV
        self.assertEqual(len(self.cc_calls), 1)
        h = lock_exclusively(self.csv_path())
        try:
            z2 = fake_zone_module().Zone(0xDEF)
            loadtimer.on_zone_start(z2)
            loadtimer.on_lot_loaded(z2)                  # must not raise
            loadtimer.on_main_menu()                     # must not raise either
        finally:
            unlock(h)
        self.assertEqual(len(self.cc_calls), 2)
        self.assertEqual(len(read_rows(self.csv_path())), 1)
        with open(os.path.join(self.sims, 'SpeedKit', 'reports', 'monitor.log'), encoding='utf-8') as f:
            self.assertIn('loadtimes.csv', f.read())

    def test_one_lot_loaded_row_per_zone_start(self):
        """The game has two Live commands that call Zone.on_loading_screen_animation_finished
        (zone.loading_screen_animation_finished and clock.restore_saved_clock_speed); one lot load must
        give one row and one CC check."""
        Z = fake_zone_module().Zone
        z = Z(0x1)
        loadtimer.on_zone_start(z)
        loadtimer.on_lot_loaded(z)
        loadtimer.on_lot_loaded(z)
        self.assertEqual([r['lot_index'] for r in read_rows(self.csv_path())], ['1'])
        self.assertEqual(len(self.cc_calls), 1)
        z2 = Z(0x1)                                      # the same lot loaded again later: a new zone start
        loadtimer.on_zone_start(z2)
        loadtimer.on_lot_loaded(z2)
        self.assertEqual([r['lot_index'] for r in read_rows(self.csv_path())], ['1', '2'])
        self.assertEqual(len(self.cc_calls), 2)

    def test_missed_first_menu_is_not_reported_as_launch_to_menu(self):
        """If the first main-menu event came before our import, the first one we see is a RETURN to the
        menu after playing; it must not be written as launch -> first menu."""
        loadtimer.state.update({'import_time': time.time() - 30, 'launch': time.time() - 90,
                                'launch_source': 'config.log'})
        z = fake_zone_module().Zone(0x7)
        loadtimer.on_zone_start(z)
        loadtimer.on_lot_loaded(z)
        loadtimer.on_main_menu()
        z2 = fake_zone_module().Zone(0x8)
        loadtimer.on_zone_start(z2)
        loadtimer.on_lot_loaded(z2)
        rows = read_rows(self.csv_path())
        self.assertEqual([r['event'] for r in rows], ['lot_loaded', 'main_menu', 'lot_loaded'])
        self.assertEqual([r['launch_to_menu_s'] for r in rows], ['', '', ''])
        self.assertEqual(rows[2]['lot_index'], '1')      # the menu still starts a new series

    def test_normal_sequence_keeps_launch_to_menu(self):
        loadtimer.state.update({'import_time': time.time() - 30, 'launch': time.time() - 90,
                                'launch_source': 'config.log'})
        loadtimer.on_main_menu()
        z = fake_zone_module().Zone(0x7)
        loadtimer.on_zone_start(z)
        loadtimer.on_lot_loaded(z)
        rows = read_rows(self.csv_path())
        self.assertNotEqual(rows[0]['launch_to_menu_s'], '')
        self.assertEqual(rows[0]['launch_to_menu_s'], rows[1]['launch_to_menu_s'])

    def write_json(self, name, obj):
        import json
        os.makedirs(os.path.join(self.sims, 'SpeedKit'), exist_ok=True)
        with open(os.path.join(self.sims, 'SpeedKit', name), 'w', encoding='utf-8') as f:
            json.dump(obj, f)

    def config_log(self, age_s):
        p = os.path.join(self.sims, 'Config.log')
        with open(p, 'w') as f:
            f.write('Free memory:     600MB\n')
        t = time.time() - age_s
        os.utime(p, (t, t))

    def test_profile_is_what_the_game_loaded_not_a_later_switch(self):
        """A profile tool may switch Mods (and profile_state.json) while the game runs; the game still
        runs with what it loaded, so rows keep the profile read at our import."""
        self.write_json('profile_state.json', {'profile': 'lean'})
        loadtimer.on_import(time.time())
        self.write_json('profile_state.json', {'profile': 'full'})
        loadtimer.on_main_menu()
        self.assertEqual(read_rows(self.csv_path())[0]['profile'], 'lean')

    def test_profile_falls_back_to_this_launchs_launch_time_json(self):
        """speedkit/launch.py writes {'epoch', 'profile', ...}; without profile_state.json its profile is used,
        but only when that launch_time.json belongs to this launch."""
        now = time.time()
        self.config_log(40)
        self.write_json('launch_time.json', {'epoch': now - 60, 'iso': 'x', 'profile': 'lean', 'pid': 1})
        loadtimer.on_import(now)
        self.assertEqual((loadtimer.state['launch_source'], loadtimer.state['profile']), ('speedkit', 'lean'))
        self.write_json('launch_time.json', {'epoch': now - 3000, 'profile': 'lean'})     # an earlier launch
        loadtimer.on_import(now)
        self.assertEqual((loadtimer.state['launch_source'], loadtimer.state['profile']), ('config.log', None))

    def test_lot_loaded_is_recorded_even_if_the_game_method_raises(self):
        """A mod that breaks inside on_loading_screen_animation_finished must not switch off the CC guard;
        the game's exception still reaches the game unchanged."""
        zmod = fake_zone_module()

        def broken(self):
            raise KeyError('a broken mod inside the loading-screen handler')
        zmod.Zone.on_loading_screen_animation_finished = broken
        sys.modules['zone'] = zmod
        sys.modules['services'] = fake_services_module()
        done = loadtimer.install()
        self.assertTrue(all(done.values()), done)
        z = zmod.Zone(0x55)
        self.assertEqual(z.start_services(None, None), 'started')
        with self.assertRaises(KeyError):
            z.on_loading_screen_animation_finished()
        self.assertEqual(len(self.cc_calls), 1)
        self.assertEqual([r['event'] for r in read_rows(self.csv_path())], ['lot_loaded'])
        # the main-menu wrapper still returns what the game returned
        sys.modules['services'].on_enter_main_menu()
        self.assertEqual(sys.modules['services'].menu_calls, [1])


# ====================================================================== lag meter (real faulthandler, 3.12)
class LagMeterReviewTests(FakeSimsCase):
    def test_refuses_to_start_without_the_tick_wrapper(self):
        """Without the Zone.update wrapper nothing would ever stop the run: faulthandler would keep writing
        lag_raw_last.txt until the main menu. The meter must refuse instead."""
        sys.modules['zone'] = fake_zone_module(update=42)          # not callable -> cannot be wrapped
        sys.modules['services'] = fake_services_module()
        msg = lagmeter.start(5, 25)
        self.assertFalse(lagmeter.running(), msg)
        self.assertIn('could not start', msg)

    def test_double_wrapped_zone_update_counts_each_tick_once(self):
        """A mod that wraps Zone.update after us without functools.wraps hides our marker, so the next
        'speedkit.lag' wraps again; every tick must still be timed once."""
        zmod = fake_zone_module()
        sys.modules['zone'] = zmod
        sys.modules['services'] = fake_services_module()
        self.assertIn('measuring', lagmeter.start(5, 25))
        lagmeter.finish('first run', show=False)
        ours = zmod.Zone.update

        def foreign(self, absolute_ticks):                         # another mod's plain wrapper
            return ours(self, absolute_ticks)
        zmod.Zone.update = foreign
        self.assertIn('measuring', lagmeter.start(5, 25))
        z = zmod.Zone(1)
        for i in range(10):
            self.assertEqual(z.update(i), i)
        r = lagmeter.finish('second run', show=False)
        self.assertEqual(z.updates, 10)
        self.assertEqual(r['ticks']['n'], 10)

    def test_time_up_finishes_inside_the_tick_and_keeps_results(self):
        zmod = fake_zone_module()
        sys.modules['zone'] = zmod
        sys.modules['services'] = fake_services_module()
        lagmeter.start(5, 25)
        lagmeter._session.deadline = lagmeter._perf()               # already due
        z = zmod.Zone(1)
        self.assertEqual(z.update(7), 7)
        self.assertFalse(lagmeter.running())
        self.assertTrue(os.path.exists(lagmeter.last_result['report']))
        self.assertEqual(lagmeter.last_result['ticks']['n'], 1)


# ====================================================================== sampling
class SamplingReviewTests(unittest.TestCase):
    def test_hottest_functions_are_per_function_not_per_line(self):
        """A function whose samples are spread over many lines must outrank one hot line elsewhere."""
        look = sampling.OwnerLookup({'m.py': 'M.ts4script'})
        prof = sampling.Profile()
        for line in range(10):
            for _ in range(10):
                prof.add([('m.py', str(100 + line), 'spread')], look)
        for _ in range(15):
            prof.add([('m.py', '7', 'hot')], look)
        top = prof.top_functions('M.ts4script', 5)
        self.assertEqual(top[0][0][1], 'spread')
        self.assertEqual(top[0][1], 100)
        self.assertEqual(top[1][0][1], 'hot')
        self.assertEqual(top[1][1], 15)
        self.assertEqual(len(top), 2)

    def test_owner_lookup_with_non_ascii_mods_folder(self):
        """faulthandler escapes non-ASCII characters, so the loose-script fallback must compare escaped."""
        look = sampling.OwnerLookup({}, 'C:\\Users\\Jos\u00e9\\Documents\\The Sims 4\\Mods')
        self.assertEqual(look('C:\\Users\\Jos\\xe9\\Documents\\The Sims 4\\Mods\\Loose\\x.py'), 'Mods\\Loose')
        self.assertEqual(look('T:\\InGame\\x.py'), sampling.GAME)

    def test_analyse_file_streams_and_truncates_on_a_dump_boundary(self):
        os.makedirs(SCRATCH, exist_ok=True)
        path = os.path.join(SCRATCH, 'stream_dump.txt')
        block = ('Timeout (0:00:00.040000)!\nThread 0x0000beef (most recent call first):\n'
                 '  File "w.py", line 1 in run\n\nThread 0x00001234 (most recent call first):\n'
                 '  File "m.py", line 5 in f\n  File "T:\\InGame\\zone.py", line 9 in update\n')
        with open(path, 'w', newline='\n') as f:
            f.write(block * 50)
        look = sampling.OwnerLookup({'m.py': 'M.ts4script'})
        try:
            prof, trunc = sampling.analyse_file(path, 0x1234, look)
            self.assertFalse(trunc)
            self.assertEqual((prof.dumps, prof.samples, prof.charged['M.ts4script']), (50, 50, 50))
            prof, trunc = sampling.analyse_file(path, 0x1234, look, max_bytes=len(block) * 10 + 5)
            self.assertTrue(trunc)
            self.assertIn(prof.dumps, (10, 11))                   # whole dumps only
            self.assertEqual(prof.samples, prof.dumps)
            self.assertEqual(prof.charged['M.ts4script'], prof.dumps)
        finally:
            os.remove(path)


# ====================================================================== build tool
@unittest.skipUnless(os.path.isfile(r'E:\The Sims 4\Game\Bin\python37_x64.dll'), 'game python37_x64.dll not found')
class BuildReviewTests(unittest.TestCase):
    def test_failed_build_leaves_no_partial_archive(self):
        from tools import build_ingame
        os.makedirs(SCRATCH, exist_ok=True)
        dist = os.path.join(SCRATCH, 'build_fail', 'SpeedKit_Monitor.ts4script')
        shutil.rmtree(os.path.dirname(dist), ignore_errors=True)
        with mock.patch.object(build_ingame, 'magic_ok', lambda data: False):
            with self.assertRaises(RuntimeError):
                build_ingame.build(dist=dist)
        self.assertEqual(os.listdir(os.path.dirname(dist)), [])
        r = build_ingame.build(dist=dist)
        self.assertEqual(build_ingame.verify(r['dist']), [])
        shutil.rmtree(os.path.dirname(dist))


# ====================================================================== install helper
class InstallReviewTests(unittest.TestCase):
    def setUp(self):
        os.makedirs(SCRATCH, exist_ok=True)
        self.root = tempfile.mkdtemp(dir=SCRATCH)
        self.sims = os.path.join(self.root, 'The Sims 4')
        self.home = os.path.join(self.sims, 'SpeedKit')
        os.makedirs(os.path.join(self.sims, 'Mods'))
        self.dist = os.path.join(self.root, 'SpeedKit_Monitor.ts4script')
        with open(self.dist, 'wb') as f:
            f.write(b'PK new build')
        self.target = os.path.join(self.sims, 'Mods', 'SpeedKit_Monitor.ts4script')

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def listing(self):
        return sorted(os.path.relpath(os.path.join(d, n), self.sims) for d, _ds, fs in os.walk(self.sims) for n in fs)

    def test_apply_refused_while_the_game_runs(self):
        before = self.listing()
        with mock.patch.object(journal_mod, 'game_running', lambda: True):
            with self.assertRaises(journal_mod.JournalError):
                ii.install(dry_run=False, dist=self.dist, sims=self.sims, home=self.home, check_game=True)
        self.assertEqual(self.listing(), before)
        self.assertFalse(os.path.exists(os.path.join(self.home, 'staging')))
        self.assertFalse(os.path.exists(self.target))

    def test_file_that_appears_after_planning_is_never_overwritten(self):
        """The other chat can drop a file into Mods at any time; a stale plan must not overwrite it."""
        real_find = ii.find_installed
        with mock.patch.object(ii, 'find_installed', lambda sims: []):
            plan = ii.plan_install(self.dist, self.sims)
            self.assertEqual(plan['action'], 'put_new')
            with open(self.target, 'wb') as f:
                f.write(b'PK somebody else')
            with self.assertRaises(journal_mod.JournalError):
                ii.install(dry_run=False, dist=self.dist, sims=self.sims, home=self.home, check_game=False)
        with open(self.target, 'rb') as f:
            self.assertEqual(f.read(), b'PK somebody else')
        states = [j[2] for j in journal_mod.list_journals(self.home)]
        self.assertEqual(len(states), 1)
        self.assertTrue(states[0].startswith('failed'), states)
        self.assertEqual(real_find(self.sims), [self.target])

    def test_cli_reports_refusal_without_a_traceback(self):
        """install() itself is replaced here, so the CLI can never reach the real Sims folder."""
        def refused(*a, **k):
            raise journal_mod.JournalError('The Sims 4 is running - close it first.')
        with mock.patch.object(ii, 'install', refused), mock.patch.object(ii, 'uninstall', refused):
            self.assertEqual(ii.main(['install', '--apply']), 1)
            self.assertEqual(ii.main(['uninstall', '--apply']), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
