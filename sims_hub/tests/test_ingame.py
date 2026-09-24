"""Tests for the SpeedKit Monitor script mod (ingame/speedkit_monitor) and its build tool.

  * Pure logic (dump parsing, attribution, owner map, tick stats, launch-time choice, CSV, CC guard) runs
    under this Python 3.12.
  * Build: tools/build_ingame.py compiles with the game's own python37_x64.dll and packs
    dist/SpeedKit_Monitor.ts4script (magic 3394, speedkit_monitor/<name>.pyc).
  * Game DLL: the built archive is copied into a FAKE Sims 4 folder under E:\\speedkit_test\\ingame and
    imported by the game's own sims4.importer.utils.import_modules_by_path (from core.zip) inside the
    game's python37_x64.dll, with small stubs for the game-only modules (services, zone, sims4.commands,
    sims4.localization, ui, cas, areaserver). The scenario drives main menu -> lot load -> CC guard ->
    lag meter (auto stop and 'stop' command) and checks the files the mod writes.
Nothing under the real Sims 4 folder or E:\\The Sims 4 is written; the game is never started.
"""
import json
import os
import shutil
import sys
import tempfile
import textwrap
import time
import types
import unittest
import zipfile

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT)
sys.path.insert(0, os.path.join(PROJECT, 'ingame'))

from speedkit_monitor import sampling, loadtimer, ccguard, common  # noqa: E402
from tools import build_ingame, game_python  # noqa: E402

SCRATCH = r'E:\speedkit_test\ingame'
RESEARCH_DUMP = os.path.join(PROJECT, 'research', 'profiler', 'py37', 'ts4prof_raw_20260924_003208.txt')


def read_text(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


# ====================================================================== pure logic under 3.12
class SamplingTests(unittest.TestCase):
    def test_monitor_is_inert_outside_a_mods_folder(self):
        self.assertIsNone(common.sims_dir())
        self.assertIsNone(common.reports_dir())

    def test_fh_escape_matches_cpython_traceback_c(self):
        self.assertEqual(sampling.fh_escape('C:\\a b.py'), 'C:\\a b.py')
        self.assertEqual(sampling.fh_escape('H\u00e9avy'), 'H\\xe9avy')
        self.assertEqual(sampling.fh_escape('\u0634x'), '\\u0634x')
        self.assertEqual(sampling.fh_escape('\U0001F600'), '\\U0001f600')
        self.assertEqual(sampling.fh_escape('a\tb'), 'a\\x09b')
        long = 'x' * 600
        self.assertEqual(sampling.fh_escape(long), 'x' * 500 + '...')

    def test_parse_frame(self):
        self.assertEqual(sampling.parse_frame('  File "E:\\B\\m.py", line 12 in burn\n'), ('E:\\B\\m.py', '12', 'burn'))
        self.assertEqual(sampling.parse_frame('  File ???, line ??? in ???'), ('???', '???', '???'))
        self.assertIsNone(sampling.parse_frame('Thread 0x00001234 (most recent call first):'))

    def test_iter_samples_threads_and_formats(self):
        dump = textwrap.dedent('''\
            Timeout (0:00:00.040000)!
            Thread 0x0000beef (most recent call first):
              File "worker.py", line 1 in run
            Thread 0x00001234 (most recent call first):
              File "E:\\Builds\\m.py", line 5 in inner
              File "T:\\InGame\\zone.py", line 9 in update
            Timeout (0:00:00.040000)!
            Thread 0x0000beef (most recent call first):
              File "worker.py", line 1 in run
            Thread 0x00001234 (most recent call first):
            Timeout (0:00:00.040000)!
            Thread 0x00001234 (most recent call first):
              <no Python frame>
            ''')
        samples = list(sampling.iter_samples(dump.splitlines(), 0x1234))
        self.assertEqual(len(samples), 3)
        self.assertEqual([f[2] for f in samples[0]], ['inner', 'update'])
        self.assertEqual(samples[1], [])
        self.assertEqual(samples[2], [])
        # unknown main thread id: the last block (oldest thread) is used
        self.assertEqual([f[2] for f in list(sampling.iter_samples(dump.splitlines(), None))[0]], ['inner', 'update'])

    def test_attribution_rules(self):
        owners = {'mod.py': 'A.ts4script', 'self.py': sampling.SELF}
        look = sampling.OwnerLookup(owners)
        f = lambda fn, fu='f': (fn, '1', fu)  # noqa: E731
        # innermost mod frame wins, even when EA code is innermost (the mod called it)
        o, key, inner = sampling.attribute([f('T:\\InGame\\x.py', 'ea'), f('mod.py', 'modfn'), f('self.py')], look)
        self.assertEqual((o, key[1], inner), ('A.ts4script', 'modfn', 'game'))
        # our wrapper is transparent
        o, key, inner = sampling.attribute([f('self.py'), f('T:\\InGame\\zone.py', 'update')], look)
        self.assertEqual((o, key[1], inner), ('game', 'update', 'game'))
        self.assertEqual(sampling.attribute([], look)[0], sampling.OUTSIDE)
        self.assertEqual(sampling.attribute([f('self.py')], look)[0], sampling.OWN_LABEL)
        # path fallback: a .py compiled from inside an archive carries the archive path
        self.assertEqual(look('C:\\S\\Mods\\B.ts4script\\b.py'), 'B.ts4script')

    def test_owner_map_from_modules(self):
        def fake(name, file, co_filename):
            m = types.ModuleType(name)
            m.__file__ = file
            exec(compile('def f():\n    pass\nclass K:\n    def g(self):\n        pass\n    @property\n    def p(self):\n        return 1\n',
                         co_filename, 'exec'), m.__dict__)
            m.__dict__['__name__'] = name
            m.f.__module__ = name
            m.K.__module__ = name
            return m
        mods = [('mc_bills', fake('mc_bills', r'C:\S\Mods\mc_cmd_center.ts4script\mc_bills.pyc', r'E:\Builds\MCCC\mc_bills.py')),
                ('lms1', fake('lms1', r'C:\S\Mods\LMS_A.ts4script\lms1\__init__.pyc', '__init__.py')),
                ('lms2', fake('lms2', r'C:\S\Mods\LMS_B.ts4script\lms2\__init__.pyc', '__init__.py')),
                ('caf', fake('caf', r'C:\S\Mods\X.ts4script\caf.pyc', 'E:\\Caf\u00e9\\c.py')),
                ('speedkit_monitor.lagmeter', fake('speedkit_monitor.lagmeter', r'C:\S\Mods\SpeedKit_Monitor.ts4script\speedkit_monitor\lagmeter.pyc', 'SK/lagmeter.py')),
                ('zone', fake('zone', r'T:\InGame\zone.pyc', r'T:\InGame\Gameplay\Scripts\Server\zone.py')),
                ('scriptloose', fake('scriptloose', r'C:\S\Mods\Loose\Scripts\l.py', r'C:\S\Mods\Loose\Scripts\l.py'))]
        fmap = sampling.build_owner_map(mods, mods_dir=r'C:\S\Mods')
        self.assertEqual(fmap[r'E:\Builds\MCCC\mc_bills.py'], 'mc_cmd_center.ts4script')
        self.assertEqual(fmap['__init__.py'], 'LMS_A.ts4script | LMS_B.ts4script')
        self.assertEqual(fmap['E:\\Caf\\xe9\\c.py'], 'X.ts4script')
        self.assertEqual(fmap['SK/lagmeter.py'], sampling.SELF)
        self.assertEqual(fmap[r'C:\S\Mods\Loose\Scripts\l.py'], 'Mods\\Loose')
        self.assertNotIn(r'T:\InGame\Gameplay\Scripts\Server\zone.py', fmap)

    def test_tick_stats(self):
        t = sampling.tick_stats([x / 1000.0 for x in range(1, 101)], wall_s=10.0)
        self.assertEqual(t['n'], 100)
        self.assertAlmostEqual(t['min_ms'], 1.0)
        self.assertAlmostEqual(t['avg_ms'], 50.5)
        self.assertAlmostEqual(t['p95_ms'], 95.0)
        self.assertAlmostEqual(t['max_ms'], 100.0)
        self.assertEqual(t['over_50ms'], 50)
        self.assertAlmostEqual(t['busy_pct'], 50.5)
        self.assertEqual(sampling.tick_stats([])['n'], 0)

    @unittest.skipUnless(os.path.exists(RESEARCH_DUMP), 'research dump missing')
    def test_real_dump_from_game_dll_matches_research(self):
        """The raw faulthandler file the research prototype recorded under the game's DLL (true split
        heavy/light/game 50/12.5/37.5 of Python time); research counted 497 Python samples, 245/67."""
        look = sampling.OwnerLookup({r'E:\Builds\Heavy\heavy\__init__.py': 'fake_heavy.ts4script',
                                     '/Users/x/light.py': 'fake_light.ts4script',
                                     r'C:\dev\ts4prof\ts4prof.py': sampling.SELF})
        prof, truncated = sampling.analyse_file(RESEARCH_DUMP, 0x148a0, look)
        self.assertFalse(truncated)
        self.assertEqual(prof.dumps, 1411)
        self.assertEqual(prof.python_samples(), 497)
        self.assertEqual(prof.charged['fake_heavy.ts4script'], 245)
        self.assertEqual(prof.charged['fake_light.ts4script'], 67)
        text = sampling.render_report(prof, sampling.tick_stats([0.008] * 10, 23.0),
                                      {'seconds': 23.0, 'hz': 150, 'when': 'x'})
        self.assertIn('fake_heavy.ts4script', text)
        self.assertIn('burn', text)
        self.assertEqual([o for o, _p in sampling.top_mods(prof)], ['fake_heavy.ts4script', 'fake_light.ts4script'])


class LoadTimerTests(unittest.TestCase):
    def test_pick_launch_time(self):
        imp = 1_000_000.0
        self.assertEqual(loadtimer.pick_launch_time(imp, None, imp - 50), (imp - 50, 'config.log'))
        self.assertEqual(loadtimer.pick_launch_time(imp, imp - 55, imp - 50), (imp - 55, 'speedkit'))
        # stale launch_time.json from an earlier SpeedKit launch loses to this launch's Config.log
        self.assertEqual(loadtimer.pick_launch_time(imp, imp - 3000, imp - 50), (imp - 50, 'config.log'))
        self.assertEqual(loadtimer.pick_launch_time(imp, imp - 7200, None), (None, 'unknown'))
        self.assertEqual(loadtimer.pick_launch_time(imp, None, imp + 30), (None, 'unknown'))
        self.assertEqual(loadtimer.pick_launch_time(imp, imp - 60, None), (imp - 60, 'speedkit'))

    def test_json_readers(self):
        self.assertEqual(loadtimer.launch_time_from_json({'launch_time': 123.5}), 123.5)
        self.assertEqual(loadtimer.launch_time_from_json({'time': '1000'}), 1000.0)
        iso = loadtimer.launch_time_from_json({'launched_at': '2026-09-24T00:31:30+00:00'})
        self.assertAlmostEqual(iso, 1790209890.0)
        self.assertIsNone(loadtimer.launch_time_from_json({'other': 1}))
        self.assertEqual(loadtimer.profile_from_json({'profile': ' lean '}), 'lean')
        self.assertEqual(loadtimer.profile_from_json({'active': {'name': 'full'}}), 'full')
        self.assertIsNone(loadtimer.profile_from_json([1, 2]))

    def test_free_ram_from_real_config_log_format(self):
        text = 'Memory:          15676MB\nFree memory:     559MB\nVA space:        134217728MB\n'
        self.assertEqual(loadtimer.parse_free_ram(text), 559)
        self.assertIsNone(loadtimer.parse_free_ram('nothing'))

    def test_append_row_and_header_change(self):
        d = os.path.join(SCRATCH, 'unit')
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, 'loadtimes_test.csv')
        for p in [path] + [os.path.join(d, n) for n in os.listdir(d) if n.startswith('loadtimes_test_old_')]:
            if os.path.exists(p):
                os.remove(p)
        loadtimer.append_row(path, ['a', 1], header=['h1', 'h2'])
        loadtimer.append_row(path, ['b', 2], header=['h1', 'h2'])
        self.assertEqual(read_text(path).splitlines(), ['h1,h2', 'a,1', 'b,2'])
        loadtimer.append_row(path, ['c', 3, 'x'], header=['h1', 'h2', 'h3'])
        self.assertEqual(read_text(path).splitlines(), ['h1,h2,h3', 'c,3,x'])
        old = [n for n in os.listdir(d) if n.startswith('loadtimes_test_old_')]
        self.assertEqual(len(old), 1)
        shutil.rmtree(d)


class CCGuardTests(unittest.TestCase):
    def test_find_missing_parts(self):
        known = {1, 2, 3}

        def is_loaded(pid):
            if pid == 99:
                raise RuntimeError('lookup failed')
            return pid in known
        sims = [('Bella Goth', 11, [1, 2, 0xDEADBEEF12345678, 0]), ('Mortimer Goth', 12, {1, 3, 99}),
                ('Cassandra Goth', 13, [0xDEADBEEF12345678, 0xABC])]
        r = ccguard.find_missing_parts(sims, is_loaded)
        self.assertEqual([s[0] for s in r['sims']], ['Bella Goth', 'Cassandra Goth'])
        self.assertEqual(r['missing'], {0xDEADBEEF12345678, 0xABC})
        self.assertEqual(r['errors'], 1)
        self.assertEqual(r['checked'], 6)
        lines, text = ccguard.describe(r, 'Goth')
        self.assertIn('0xDEADBEEF12345678', lines[1])
        self.assertIn('Do not save', text)
        self.assertIsNone(ccguard.describe(ccguard.find_missing_parts([('A', 1, [1])], is_loaded))[1])

    def test_bodytype_convention(self):
        self.assertTrue(ccguard.bodytype_says_loaded(5))
        for v in (0, -1, None, 'x'):
            self.assertFalse(ccguard.bodytype_says_loaded(v))


# ====================================================================== build with the game's Python
@unittest.skipUnless(game_python.available(), 'game python37_x64.dll not found')
class BuildTests(unittest.TestCase):
    def test_build_and_verify(self):
        r = build_ingame.build()
        self.assertTrue(r['python'].startswith('3.7.0'))
        self.assertEqual(r['magic'], '420d0d0a')
        self.assertEqual(build_ingame.verify(r['dist']), [])
        expected = sorted('speedkit_monitor/%s.pyc' % os.path.splitext(os.path.basename(p))[0]
                          for p in build_ingame.sources())
        with zipfile.ZipFile(r['dist']) as z:
            self.assertEqual(sorted(z.namelist()), expected)
            for n in z.namelist():
                data = z.read(n)
                self.assertEqual(int.from_bytes(data[:2], 'little'), 3394)
                self.assertEqual(z.getinfo(n).compress_type, zipfile.ZIP_DEFLATED)


# ====================================================================== the mod inside the game's DLL
STUBS = {
    'sims4/__init__.py': '# test stub of the sims4 package (the real one needs the game\'s native modules)\n',
    'sims4/log.py': textwrap.dedent('''\
        class Logger:
            def __init__(self, *a, **k):
                pass
            def __getattr__(self, name):
                return lambda *a, **k: None
        '''),
    'sims4/commands.py': textwrap.dedent('''\
        class CommandType:
            DebugOnly = 1
            Automation = 3
            Cheat = 4
            Live = 5
        REGISTRY = {}
        OUTPUT = []
        def Command(*aliases, command_type=CommandType.DebugOnly, **kw):
            def named_command(func):
                if command_type == CommandType.DebugOnly:
                    return None
                for a in aliases:
                    REGISTRY[a] = (func, command_type)
                return func
            return named_command
        class CheatOutput:
            def __init__(self, connection):
                self.connection = connection
            def __call__(self, s):
                OUTPUT.append([self.connection, s])
        '''),
    'sims4/localization.py': textwrap.dedent('''\
        class LocalizationHelperTuning:
            @classmethod
            def get_raw_text(cls, text):
                return 'RAW:' + text
        '''),
    'paths.py': 'IS_ARCHIVE = True\n',
    'areaserver.py': 'server_init_load_time = 12.5\n',
    'services.py': textwrap.dedent('''\
        _ZONE = None
        _HOUSEHOLD = None
        MENU_CALLS = []
        def on_enter_main_menu():
            MENU_CALLS.append(1)
        def current_zone():
            return _ZONE
        def current_zone_id():
            return _ZONE.id if _ZONE is not None else None
        def active_household():
            return _HOUSEHOLD
        class _TimeService:
            def get_simulator_debt(self):
                return 0.25
        def time_service():
            return _TimeService()
        '''),
    'zone.py': textwrap.dedent('''\
        import time
        ELEMENTS = []
        GAME_MS = 3.0
        def _burn(ms):
            end = time.perf_counter() + ms / 1000.0
            while time.perf_counter() < end:
                pass
        class Zone:
            def __init__(self, zone_id):
                self.id = zone_id
                self.started = self.loaded = self.updates = 0
            def start_services(self, gameplay_zone_data, save_slot_data):
                self.started += 1
            def update(self, absolute_ticks):
                self.updates += 1
                for e in ELEMENTS:
                    e()
                _burn(GAME_MS)
            def on_loading_screen_animation_finished(self):
                self.loaded += 1
        '''),
    'ui/__init__.py': '',
    'ui/ui_dialog_notification.py': textwrap.dedent('''\
        SHOWN = []
        class _Urgency:
            DEFAULT = 0
            URGENT = 1
        class _Dialog:
            def __init__(self, owner, **kw):
                self.owner, self.kw = owner, kw
            def show_dialog(self):
                SHOWN.append({'title': self.kw['title'](), 'text': self.kw['text'](), 'urgency': self.kw.get('urgency', 0)})
        class _Factory:
            def default(self, owner, **kw):
                return _Dialog(owner, **kw)
        class UiDialogNotification:
            UiDialogNotificationUrgency = _Urgency
            @classmethod
            def TunableFactory(cls):
                return _Factory()
        '''),
    'cas/__init__.py': '',
    'cas/cas.py': textwrap.dedent('''\
        KNOWN = set()
        CALLS = []
        def get_caspart_bodytype(part_id):
            CALLS.append(part_id)
            return 5 if part_id in KNOWN else 0
        '''),
}

SCENARIO = r'''
import sys, os, json, time, zipfile, marshal, importlib.util, zipimport
A = json.loads(HOST_ARGS)
sys.path.insert(0, A['stubs'])
R = {'python': sys.version}
MODS = os.path.join(A['sims'], 'Mods')

# --- two fake script mods, compiled by this (the game's) Python with their authors' build paths
def build(name, entries):
    p = os.path.join(MODS, name)
    with zipfile.ZipFile(p, 'w', zipfile.ZIP_DEFLATED) as z:
        for arc, src, fake in entries:
            z.writestr(arc, importlib.util.MAGIC_NUMBER + b'\0' * 12 + marshal.dumps(compile(src, fake, 'exec')))
    sys.path.append(p)
BURN = 'import time\ndef burn(ms):\n    end = time.perf_counter() + ms / 1000.0\n    while time.perf_counter() < end:\n        pass\n'
build('fake_heavy.ts4script', [('heavy/__init__.pyc', BURN + 'def on_tick():\n    burn(4)\n', 'E:\\Builds\\H\u00e9avy\\heavy\\__init__.py')])
build('fake_light.ts4script', [('light.pyc', BURN + 'class Thing:\n    def cb(self):\n        burn(1)\n', '/Users/x/light.py')])
import heavy, light, zone, services, cas.cas, sims4.commands
from ui import ui_dialog_notification as uidn
zone.ELEMENTS[:] = [heavy.on_tick, light.Thing().cb]

# --- import the monitor the way the game does: its own sims4.importer.utils from core.zip
code = zipimport.zipimporter(os.path.join(A['core_zip'], 'sims4', 'importer')).get_code('utils')
g = {'__name__': 'sims4.importer.utils_under_test'}
exec(code, g)
sys.path.append(A['archive'])
R['module_names'] = [list(x) for x in g['module_names_gen'](A['archive'])]
t0 = time.perf_counter()
R['import_errors'] = g['import_modules_by_path'](A['archive'], True)
R['import_ms'] = (time.perf_counter() - t0) * 1000.0
R['imported'] = sorted(n for n in sys.modules if n.startswith('speedkit_monitor'))
R['module_files'] = {n: getattr(sys.modules[n], '__file__', None) for n in R['imported']}
CMD = {k: v[0] for k, v in sims4.commands.REGISTRY.items()}
R['commands'] = {k: v[1] for k, v in sims4.commands.REGISTRY.items()}
R['hooked'] = {
    'main_menu': hasattr(services.on_enter_main_menu, '__speedkit_orig__'),
    'start_services': '__speedkit_orig__' in dir(zone.Zone.__dict__['start_services']),
    'loading_screen': '__speedkit_orig__' in dir(zone.Zone.__dict__['on_loading_screen_animation_finished']),
    'update_before_lag': '__speedkit_orig__' in dir(zone.Zone.__dict__['update'])}

# --- a household: Bella wears a part the catalog does not have
class OutfitData:
    def __init__(self, ids):
        self.part_ids = ids
class SimInfo:
    def __init__(self, first, last, sid, outfits):
        self.first_name, self.last_name, self.id, self._outfits = first, last, sid, outfits
    def get_outfits(self):
        return self
    def get_all_outfits(self):
        for cat, lst in self._outfits:
            yield cat, lst
    def get_outfit(self, *a):
        raise AssertionError('get_outfit can generate outfits; the guard must not call it')
class Household:
    name = 'Goth'
    def __init__(self, sims):
        self.sims = sims
    def sim_info_gen(self):
        for s in self.sims:
            yield s
cas.cas.KNOWN.update({1, 2, 3})
services._HOUSEHOLD = Household([
    SimInfo('Bella', 'Goth', 11, [(0, [OutfitData((1, 2)), OutfitData((1, 0xDEADBEEF12345678))]), (1, [OutfitData((3,))])]),
    SimInfo('Mortimer', 'Goth', 12, [(0, [OutfitData((1, 3))])])])

# --- the load sequence
services.on_enter_main_menu()
Z = zone.Zone(0x1234ABCD)
services._ZONE = Z
Z.start_services(None, None)
time.sleep(0.2)
Z.on_loading_screen_animation_finished()
R['menu_calls'] = len(services.MENU_CALLS)
R['zone_calls'] = [Z.started, Z.loaded]
R['cas_lookups'] = sorted(set(cas.cas.CALLS))

# --- other commands (registered functions return None, like the game expects; read the console)
def run_cmd(name, conn, *args):
    R.setdefault('cmd_returns', []).append(CMD[name](*args, _connection=conn))
    return [s for c, s in sims4.commands.OUTPUT if c == conn]
R['out_cc'] = run_cmd('speedkit.cc', 31)
R['out_status'] = run_cmd('speedkit.status', 32)
R['out_stop_idle'] = run_cmd('speedkit.lag', 33, 'stop')
R['out_bad'] = run_cmd('speedkit.lag', 34, 'abc')
CMD['speedkit.lag']('5', '100', _connection=5)          # session 1: 5 s at 100 Hz, stops itself
R['update_after_lag'] = '__speedkit_orig__' in dir(zone.Zone.__dict__['update'])
LM = sys.modules['speedkit_monitor.lagmeter']
S = {'n': 0, 'phase': 1}

def summary(r):
    if not r:
        return None
    return {k: r[k] for k in ('report', 'samples', 'dumps', 'ticks', 'top', 'shares', 'analysis_ms', 'text')}

def tick():
    S['n'] += 1
    Z.update(S['n'])
    if S['phase'] == 1 and not LM.running():
        R['session1'] = summary(LM.last_result)
        R['session1_ticks_seen'] = S['n']
        S['phase'], S['p2'] = 2, S['n']
        CMD['speedkit.lag']('60', '50', _connection=6)
        R['out_again'] = run_cmd('speedkit.lag', 61, '60')
    elif S['phase'] == 2 and S['n'] - S['p2'] >= 40:
        CMD['speedkit.lag']('stop', _connection=6)
        R['session2'] = summary(LM.last_result)
        S['phase'] = 3

def bench():
    """Stop-time cost at the default rate: 60 s x 25 Hz = 1,500 dumps of a 100-frame main thread."""
    sampling = sys.modules['speedkit_monitor.sampling']
    path = os.path.join(A['scratch'], 'bench_dump.txt')
    ea = ['  File "T:\\InGame\\Gameplay\\Scripts\\Server\\mod%d.py", line %d in fn%d\n' % (i, i, i) for i in range(100)]
    with open(path, 'w') as f:
        for d in range(1500):
            f.write('Timeout (0:00:00.040000)!\nThread 0x0000beef (most recent call first):\n  File "w.py", line 1 in run\n')
            f.write('Thread 0x00001234 (most recent call first):\n')
            if d % 3:
                frames = list(ea)
                if d % 5 == 0:
                    frames[40] = '  File "/Users/x/light.py", line 5 in burn\n'
                f.writelines(frames)
                f.write('  ...\n')
    size = os.path.getsize(path)
    t0 = time.perf_counter()
    look = sampling.OwnerLookup(sampling.build_owner_map(list(sys.modules.items())))
    t1 = time.perf_counter()
    prof, trunc = sampling.analyse_file(path, 0x1234, look)
    t2 = time.perf_counter()
    os.remove(path)
    return {'dump_mb': size / 1e6, 'owner_map_ms': (t1 - t0) * 1000, 'parse_ms': (t2 - t1) * 1000,
            'samples': prof.samples, 'light': prof.charged['fake_light.ts4script'], 'modules': len(sys.modules)}

def finish(host_s):
    R['host_s'] = host_s
    R['ticks'] = S['n']
    R['phase'] = S['phase']
    R['bench'] = bench()
    CMD['speedkit.lag']('10', _connection=8)                # a session the main menu stops
    services.on_enter_main_menu()
    R['session3'] = summary(LM.last_result)
    R['notifications'] = uidn.SHOWN
    R['cheat_output'] = sims4.commands.OUTPUT
    R['hooks_final'] = {'update': '__speedkit_orig__' in dir(zone.Zone.__dict__['update'])}
    with open(A['result'], 'w', encoding='utf-8') as f:
        json.dump(R, f, indent=1, default=str)
'''


@unittest.skipUnless(game_python.available(), 'game python37_x64.dll not found')
class GameDllTests(unittest.TestCase):
    """The built mod inside the game's own python37_x64.dll, in a fake Sims 4 folder."""

    @classmethod
    def setUpClass(cls):
        cls.base = os.path.join(SCRATCH, 'dll')
        if os.path.exists(cls.base):
            shutil.rmtree(cls.base)
        stubs = os.path.join(cls.base, 'stubs')
        for rel, text in STUBS.items():
            p = os.path.join(stubs, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, 'w', encoding='utf-8') as f:
                f.write(text)
        cls.sims = os.path.join(cls.base, 'fake_sims', 'The Sims 4')
        mods = os.path.join(cls.sims, 'Mods')
        os.makedirs(os.path.join(cls.sims, 'SpeedKit'))
        os.makedirs(mods)
        cls.now = time.time()
        with open(os.path.join(cls.sims, 'Config.log'), 'w') as f:
            f.write('=== Application info ===\nVersion:         1.126.73.1030\nMemory:          15676MB\n'
                    'Free memory:     559MB\n=== Options ===\nNumBoots 43\n')
        os.utime(os.path.join(cls.sims, 'Config.log'), (cls.now - 42, cls.now - 42))
        with open(os.path.join(cls.sims, 'SpeedKit', 'launch_time.json'), 'w') as f:
            json.dump({'launch_time': cls.now - 5000}, f)            # stale: an earlier launch
        with open(os.path.join(cls.sims, 'SpeedKit', 'profile_state.json'), 'w') as f:
            json.dump({'profile': 'lean'}, f)
        build = build_ingame.build()
        cls.archive = os.path.join(mods, 'SpeedKit_Monitor.ts4script')
        shutil.copy2(build['dist'], cls.archive)
        script = os.path.join(cls.base, 'scenario37.py')
        with open(script, 'w', encoding='utf-8') as f:
            f.write(SCENARIO)
        result = os.path.join(cls.base, 'result.json')
        args = {'stubs': stubs, 'sims': cls.sims, 'archive': cls.archive, 'result': result, 'scratch': cls.base,
                'core_zip': os.path.join(game_python.GAMEPLAY, 'core.zip')}
        cls.cp = game_python.run(script, args=json.dumps(args), ticks=320, gap_ms=20.0, timeout=600)
        cls.R = {}
        if os.path.exists(result):
            with open(result, encoding='utf-8') as f:
                cls.R = json.load(f)
        cls.reports = os.path.join(cls.sims, 'SpeedKit', 'reports')
        log = os.path.join(cls.reports, 'monitor.log')
        cls.log = read_text(log) if os.path.exists(log) else ''
        if os.environ.get('SPEEDKIT_TEST_VERBOSE'):
            print(cls.cp.stdout[-4000:], cls.cp.stderr[-4000:])
            print(json.dumps({k: v for k, v in cls.R.items() if k not in ('notifications',)}, indent=1, default=str)[:12000])

    def test_00_ran_cleanly(self):
        self.assertEqual(self.cp.returncode, 0, self.cp.stdout[-3000:] + self.cp.stderr[-3000:])
        self.assertTrue(self.R.get('python', '').startswith('3.7.0'))
        self.assertNotIn('ERROR', self.log)

    def test_imported_by_the_games_importer(self):
        R = self.R
        self.assertEqual(R['import_errors'], 0)
        names = dict((fqn, n) for n, fqn in R['module_names'])
        self.assertIn('speedkit_monitor', names)                  # __init__ -> the package itself
        self.assertEqual(sorted(names), R['imported'])
        self.assertEqual(len(R['imported']), len(build_ingame.sources()))
        for f in R['module_files'].values():
            self.assertIn('SpeedKit_Monitor.ts4script', f)
        self.assertEqual(R['commands'], {'speedkit.lag': 5, 'speedkit.cc': 5, 'speedkit.status': 5})
        self.assertEqual(R['hooked'], {'main_menu': True, 'start_services': True, 'loading_screen': True,
                                       'update_before_lag': False})
        self.assertTrue(R['update_after_lag'])

    def test_load_timer_rows(self):
        self.assertEqual(self.R['menu_calls'], 1)                 # the original still ran
        self.assertEqual(self.R['zone_calls'], [1, 1])
        rows = read_text(os.path.join(self.reports, 'loadtimes.csv')).splitlines()
        import csv
        rows = list(csv.reader(rows))
        self.assertEqual(rows[0], loadtimer.HEADER)
        body = [dict(zip(rows[0], r)) for r in rows[1:]]
        self.assertEqual([r['event'] for r in body], ['main_menu', 'lot_loaded', 'main_menu'])
        menu, lot = body[0], body[1]
        self.assertEqual(menu['launch_source'], 'config.log')     # stale launch_time.json ignored
        self.assertTrue(40 <= float(menu['since_launch_s']) <= 120, menu)
        self.assertTrue(40 <= float(menu['launch_to_scripts_s']) <= 120, menu)
        self.assertEqual(menu['profile'], 'lean')
        self.assertEqual(menu['free_ram_mb_at_start'], '559')
        self.assertEqual(menu['script_mods'], '2')                # fake_heavy + fake_light, not ourselves
        self.assertEqual(lot['zone_id'], '0x1234abcd')
        self.assertTrue(0.1 <= float(lot['lot_load_s']) <= 2.0, lot)
        self.assertEqual(lot['game_zone_load_s'], '12.5')
        self.assertEqual(lot['lot_index'], '1')
        self.assertNotEqual(lot['launch_to_menu_s'], '')

    def test_cc_guard(self):
        self.assertEqual(self.R['cas_lookups'], [1, 2, 3, 0xDEADBEEF12345678])
        cc = [n for n in self.R['notifications'] if 'missing CC' in n['title']]
        self.assertEqual(len(cc), 2)                              # after the lot load + speedkit.cc
        self.assertEqual(cc[0]['urgency'], 1)
        self.assertIn('Bella Goth', cc[0]['text'])
        self.assertNotIn('Mortimer', cc[0]['text'])
        self.assertIn('0xDEADBEEF12345678', self.log)
        self.assertIn('Bella Goth (sim id 11)', self.log)
        self.assertIn('not loaded', self.R['out_cc'][0])

    def test_lag_meter_auto_stop(self):
        s1 = self.R['session1']
        self.assertIsNotNone(s1)
        self.assertTrue(os.path.exists(s1['report']))
        shares = s1['shares']
        heavy, light = shares.get('fake_heavy.ts4script', 0), shares.get('fake_light.ts4script', 0)
        # per tick: heavy 4 ms, light 1 ms, game 3 ms in Python, then 20 ms outside Python (host)
        self.assertGreater(heavy, light)
        self.assertGreater(light, 0)
        self.assertTrue(6 <= heavy <= 25, shares)
        self.assertGreater(shares.get(sampling.OUTSIDE, 0), 50)
        self.assertGreater(shares.get(sampling.GAME, 0), 3)
        self.assertNotIn(sampling.SELF, shares)
        self.assertEqual([o for o, _p in s1['top']][:2], ['fake_heavy.ts4script', 'fake_light.ts4script'])
        t = s1['ticks']
        self.assertGreater(t['n'], 100)
        self.assertTrue(7.5 <= t['avg_ms'] <= 20, t)
        self.assertTrue(t['min_ms'] <= t['avg_ms'] <= t['p95_ms'] <= t['max_ms'])
        text = read_text(s1['report'])
        # the heavy mod's build path is non-ASCII: faulthandler writes it escaped, and the map still matches
        for needle in ('Zone.update', 'fake_heavy.ts4script', r'burn  (E:\Builds\H\xe9avy', 'Hottest functions per mod',
                       'simulator debt'):
            self.assertIn(needle, text)
        lag = [n for n in self.R['notifications'] if n['title'] == 'RAW:SpeedKit lag meter']
        self.assertEqual(len(lag), 2)                             # the main-menu stop shows none
        self.assertIn('1. fake_heavy', lag[0]['text'])
        self.assertIn('2. fake_light', lag[0]['text'])
        console = [s for c, s in self.R['cheat_output'] if c == 5]
        self.assertTrue(any('measuring for 5 s' in s for s in console))
        self.assertTrue(any(s.startswith('1. fake_heavy') for s in console))

    def test_lag_meter_stop_command_and_menu(self):
        s2 = self.R['session2']
        self.assertIsNotNone(s2)
        self.assertEqual(self.R['phase'], 3)
        self.assertIn('already running', self.R['out_again'][0])
        self.assertIn('not running', self.R['out_stop_idle'][0])
        self.assertIn('Usage', self.R['out_bad'][0])
        self.assertIn('stopped by stop command', read_text(s2['report']))
        self.assertGreater(s2['ticks']['n'], 30)
        s3 = self.R['session3']
        self.assertIn('stopped by main menu', read_text(s3['report']))
        self.assertTrue(self.R['hooks_final']['update'])          # wrapper stays, as a pass-through
        self.assertEqual(set(map(str, self.R['cmd_returns'])), {'None'})  # nothing handed back to C++

    def test_stop_time_cost(self):
        b = self.R['bench']
        self.assertEqual(b['samples'], 1500)
        self.assertEqual(b['light'], 200)
        self.assertLess(b['parse_ms'], 5000)
        print('\n  [game DLL] import %.0f ms; bench: %.1f MB dump (60 s @ 25 Hz, 100 frames) parsed in %.0f ms, '
              'owner map of %d modules in %.0f ms; session 1: %d samples, analysis %.0f ms'
              % (self.R['import_ms'], b['dump_mb'], b['parse_ms'], b['modules'], b['owner_map_ms'],
                 self.R['session1']['samples'], self.R['session1']['analysis_ms']))


if __name__ == '__main__':
    unittest.main(verbosity=2)
