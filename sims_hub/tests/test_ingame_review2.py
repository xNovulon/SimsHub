"""Second adversarial review of the SpeedKit Monitor (ingame/speedkit_monitor).

Defects these tests pin down (all reproduced before the fix):
  1. Owner map: a decorator built with functools.wraps returns a wrapper whose __module__ is copied from the
     mod's function but whose code lives where the decorator is defined. WickedWhims (in Mods now) has ten
     test classes with '@turbo_cached_test def __call__' (= EA's caches.cached_test), so EA's
     'T:\\InGame\\Gameplay\\Scripts\\Core\\caches.py' was mapped to WickedWhims and every EA cached test on
     the stack was charged to it. The same with a module-level '@exception_protected' (sims4/utils.py, which
     also wraps areaserver.c_api_server_tick) would have charged EVERY Python sample to that mod.
  2. Start-up: a launch_time.json holding a date before 1970 made datetime.timestamp() raise OSError (game
     3.7 on Windows), which aborted __init__ before the hooks and the cheats were installed.
  3. Lag meter: nothing ended a run when the lot was unloaded, so faulthandler kept dumping through a travel
     loading screen (no Zone.update there) and through the game's shutdown.

Everything runs on FAKE Sims folders under E:\\speedkit_test\\ingame_review\\r2; the game DLL part loads
E:\\The Sims 4\\Game\\Bin\\python37_x64.dll read-only in a child process. Nothing under the real Sims 4
folder or E:\\The Sims 4 is written and the game is never started.

    python tests/test_ingame_review2.py
"""
import functools
import json
import os
import shutil
import sys
import tempfile
import textwrap
import time
import types
import unittest
from unittest import mock

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT)
sys.path.insert(0, os.path.join(PROJECT, 'ingame'))
sys.path.insert(0, os.path.join(PROJECT, 'tests'))

import speedkit_monitor  # noqa: E402
from speedkit_monitor import common, commands, hooks, loadtimer, lagmeter, sampling  # noqa: E402
from tools import build_ingame, game_python  # noqa: E402

SCRATCH = r'E:\speedkit_test\ingame_review\r2'
EA_CACHES = 'T:\\InGame\\Gameplay\\Scripts\\Core\\caches.py'
EA_UTILS = 'T:\\InGame\\Gameplay\\Scripts\\Core\\sims4\\utils.py'
FRESH_STATE = {k: (dict(v) if isinstance(v, dict) else v) for k, v in loadtimer.state.items()}


def module_from(name, file, co_filename, src, extra=None):
    """A module named `name` with __file__ `file`, whose code was compiled as `co_filename`."""
    m = types.ModuleType(name)
    m.__file__ = file
    m.__dict__.update(extra or {})
    exec(compile(src, co_filename, 'exec'), m.__dict__)
    return m


def ea_module(name, co_filename, src, extra=None):
    return module_from(name, 'E:\\The Sims 4\\Data\\Simulation\\Gameplay\\core.zip\\%s.pyc' % name, co_filename,
                       src, extra)


WRAPS_DECORATOR = ('import functools\n'
                   'def %s(fn):\n'
                   '    @functools.wraps(fn)\n'
                   '    def wrapper(*args, **kwargs):\n'
                   '        return fn(*args, **kwargs)\n'
                   '    return wrapper\n')


# ====================================================================== 1. owner map vs. decorators
class OwnerMapDecoratorTests(unittest.TestCase):
    def setUp(self):
        self.caches = ea_module('caches', EA_CACHES, WRAPS_DECORATOR % 'cached_test')
        self.utils = ea_module('sims4.utils', EA_UTILS, WRAPS_DECORATOR % 'exception_protected')

    def mod(self, name, archive, co_filename, src, extra=None):
        return module_from(name, 'C:\\S\\Mods\\scripts\\%s\\%s.pyc' % (archive, name.replace('.', '\\')),
                           co_filename, src, dict(extra or {}, __name__=name))

    def test_ea_cached_test_on_a_mod_method_maps_the_mod_not_ea(self):
        """WickedWhims: class IsFaithfulTest: @turbo_cached_test def __call__(...)."""
        ww = self.mod('wickedwhims.faithful', 'TURBODRIVER_WickedWhims_Scripts.ts4script',
                      '.\\WickedWhims_v185k\\wickedwhims\\faithful.py',
                      'class IsFaithfulTest:\n    @turbo_cached_test\n    def __call__(self):\n        return True\n',
                      {'turbo_cached_test': self.caches.cached_test})
        fmap = sampling.build_owner_map([('caches', self.caches), ('wickedwhims.faithful', ww)])
        self.assertNotIn(EA_CACHES, fmap)
        self.assertEqual(fmap, {'.\\WickedWhims_v185k\\wickedwhims\\faithful.py': 'TURBODRIVER_WickedWhims_Scripts.ts4script'})
        # an EA test evaluated inside the tick, no mod code anywhere on the stack
        stack = [('T:\\InGame\\Gameplay\\Scripts\\Server\\event_testing\\statistic_tests.py', '812', '__call__'),
                 (EA_CACHES, '290', 'wrapper'),
                 ('T:\\InGame\\Gameplay\\Scripts\\Server\\autonomy\\autonomy_modes.py', '1200', '_run_gen'),
                 ('T:\\InGame\\Gameplay\\Scripts\\Server\\areaserver.py', '208', 'c_api_server_tick'),
                 (EA_UTILS, '179', 'wrapper')]
        self.assertEqual(sampling.attribute(stack, sampling.OwnerLookup(fmap))[0], sampling.GAME)

    def test_module_level_exception_protected_does_not_capture_every_tick(self):
        """areaserver.c_api_server_tick is itself @exception_protected, so sims4/utils.py is at the bottom of
        every simulation stack; a mod using the same decorator must not own that file."""
        kut = self.mod('kuttoe_mod', '[Kuttoe] BasementalAddons.ts4script', 'E:\\Kuttoe\\kuttoe_mod.py',
                       '@exception_protected\ndef on_load_complete():\n    return 1\n',
                       {'exception_protected': self.utils.exception_protected})
        fmap = sampling.build_owner_map([('sims4.utils', self.utils), ('kuttoe_mod', kut)])
        self.assertEqual(fmap, {'E:\\Kuttoe\\kuttoe_mod.py': '[Kuttoe] BasementalAddons.ts4script'})
        look = sampling.OwnerLookup(fmap)
        stack = [('T:\\InGame\\Gameplay\\Scripts\\Server\\zone.py', '500', 'update'),
                 ('T:\\InGame\\Gameplay\\Scripts\\Server\\areaserver.py', '208', 'c_api_server_tick'),
                 (EA_UTILS, '179', 'wrapper')]
        self.assertEqual(sampling.attribute(stack, look)[0], sampling.GAME)
        # the mod's own function (found through __wrapped__) is still charged to the mod
        self.assertEqual(sampling.attribute([('E:\\Kuttoe\\kuttoe_mod.py', '3', 'on_load_complete')] + stack,
                                            look)[0], '[Kuttoe] BasementalAddons.ts4script')

    def test_class_alias_of_an_ea_function_is_not_the_mods_code(self):
        m = self.mod('aliases', 'A.ts4script', 'E:\\A\\aliases.py',
                     'class K:\n    run = ea_fn\n    helper = staticmethod(ea_fn)\n    def own(self):\n        pass\n',
                     {'ea_fn': self.caches.cached_test})
        self.assertEqual(sampling.build_owner_map([('aliases', m)]), {'E:\\A\\aliases.py': 'A.ts4script'})

    def test_decorator_from_another_mod_stays_with_that_mod(self):
        """Mod A decorates its functions with mod B's injector (functools.wraps): B's file is B's only."""
        b = self.mod('b_lib.inject', 'B.ts4script', 'B/inject.py', WRAPS_DECORATOR % 'inject')
        a = self.mod('a_mod', 'A.ts4script', 'E:\\A\\a_mod.py',
                     '@inject\ndef hook():\n    pass\nclass T:\n    @inject\n    def m(self):\n        pass\n',
                     {'inject': b.inject})
        fmap = sampling.build_owner_map([('a_mod', a), ('b_lib.inject', b)])
        self.assertEqual(fmap, {'E:\\A\\a_mod.py': 'A.ts4script', 'B/inject.py': 'B.ts4script'})

    def test_wrapper_of_something_that_is_not_a_function_is_skipped(self):
        m = self.mod('wrapsbuiltin', 'W.ts4script', 'E:\\W\\w.py',
                     'import functools\nclass K:\n    pass\n', {})
        wrapper = self.utils.exception_protected(len)          # __wrapped__ = a builtin, code = EA's
        wrapper.__module__ = 'wrapsbuiltin'
        m.K.__module__ = 'wrapsbuiltin'
        m.f = wrapper
        m.K.g = wrapper
        self.assertEqual(sampling.build_owner_map([('wrapsbuiltin', m)]), {})

    def test_ea_code_is_never_mapped_to_a_mod(self):
        """Even a function that claims to belong to a mod module is not a mod's if its code is EA's."""
        m = self.mod('odd', 'O.ts4script', 'D:\\dev\\TS4\\_deploy\\Client\\Releasex64\\Python\\Generated\\x.py',
                     'def f():\n    pass\n')
        self.assertEqual(sampling.build_owner_map([('odd', m)]), {})

    def test_wrapped_cycle_does_not_hang(self):
        m = self.mod('cyc', 'C.ts4script', 'E:\\C\\c.py', 'def f():\n    pass\ndef g():\n    pass\n')
        m.f.__wrapped__ = m.g
        m.g.__wrapped__ = m.f
        self.assertEqual(sampling.build_owner_map([('cyc', m)]), {'E:\\C\\c.py': 'C.ts4script'})


# ====================================================================== fake Sims folder helpers
class FakeSims(unittest.TestCase):
    def setUp(self):
        os.makedirs(SCRATCH, exist_ok=True)
        self.root = tempfile.mkdtemp(dir=SCRATCH)
        self.sims = os.path.join(self.root, 'The Sims 4')
        os.makedirs(os.path.join(self.sims, 'Mods'))
        os.makedirs(os.path.join(self.sims, 'SpeedKit'))
        common.configure(self.sims)
        loadtimer.state.clear()
        loadtimer.state.update({k: (dict(v) if isinstance(v, dict) else v) for k, v in FRESH_STATE.items()})
        self.saved = {k: sys.modules.get(k) for k in ('zone', 'services', 'areaserver', 'sims4', 'sims4.commands')}
        self.notes = []
        p = mock.patch.object(common, 'notify', lambda title, text, urgent=False: self.notes.append((title, text)) or True)
        p.start()
        self.addCleanup(p.stop)
        lagmeter._pending = None

    def tearDown(self):
        if lagmeter.running():
            lagmeter.finish('test teardown', show=False)
        lagmeter._pending = None
        for k, v in self.saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
        common.configure(None)
        shutil.rmtree(self.root, ignore_errors=True)

    def log_text(self):
        p = os.path.join(self.sims, 'SpeedKit', 'reports', 'monitor.log')
        if not os.path.exists(p):
            return ''
        with open(p, encoding='utf-8') as f:
            return f.read()

    @staticmethod
    def fake_zone():
        z = types.ModuleType('zone')

        class Zone:
            def __init__(self, zone_id):
                self.id = zone_id
                self.torn_down = []

            def start_services(self, gameplay_zone_data, save_slot_data):
                return 'started'

            def update(self, absolute_ticks):
                return absolute_ticks

            def on_loading_screen_animation_finished(self):
                return 'loaded'

            def on_teardown(self, client):
                self.torn_down.append(client)
                return 'torn down'
        z.Zone = Zone
        return z

    @staticmethod
    def fake_services():
        s = types.ModuleType('services')
        s.on_enter_main_menu = lambda: None
        s.current_zone_id = lambda: 0x1234
        return s


# ====================================================================== 2. start-up survives bad files
class StartupTests(FakeSims):
    def fake_commands(self):
        pkg = types.ModuleType('sims4')
        pkg.__path__ = []
        cmd = types.ModuleType('sims4.commands')
        cmd.REGISTRY = {}

        class CommandType:
            Live = 5
        cmd.CommandType = CommandType

        def Command(*aliases, command_type=None):
            def named(func):
                for a in aliases:
                    cmd.REGISTRY[a] = command_type
                return func
            return named
        cmd.Command = Command
        cmd.CheatOutput = lambda conn: (lambda s: None)
        pkg.commands = cmd
        sys.modules['sims4'], sys.modules['sims4.commands'] = pkg, cmd
        return cmd

    def start(self):
        sys.modules['zone'] = self.fake_zone()
        sys.modules['services'] = self.fake_services()
        cmd = self.fake_commands()
        commands._registered = False
        self.addCleanup(setattr, commands, '_registered', False)
        speedkit_monitor._start()
        return cmd

    def test_parse_time_value_out_of_range_dates(self):
        for v in ('1969-12-31T23:00:00', '0001-01-01', '9999-12-31T23:59:59', 'garbage'):
            self.assertIsNone(loadtimer.parse_time_value(v), v)
        self.assertEqual(loadtimer.parse_time_value('1790200000.5'), 1790200000.5)

    def test_pre_1970_launch_time_does_not_disable_the_mod(self):
        with open(os.path.join(self.sims, 'SpeedKit', 'launch_time.json'), 'w') as f:
            json.dump({'launch_time': '1969-12-31T23:00:00'}, f)
        cmd = self.start()
        self.assertEqual(sorted(cmd.REGISTRY), ['speedkit.cc', 'speedkit.lag', 'speedkit.status'])
        self.assertTrue(hooks.is_wrapped(sys.modules['zone'].Zone, 'on_loading_screen_animation_finished'))
        self.assertTrue(hooks.is_wrapped(sys.modules['services'], 'on_enter_main_menu'))
        self.assertEqual(loadtimer.state['launch_source'], 'unknown')
        self.assertNotIn('ERROR', self.log_text())

    def test_each_start_up_step_is_independent(self):
        with mock.patch.object(loadtimer, 'on_import', side_effect=RuntimeError('boom')):
            cmd = self.start()
        self.assertEqual(len(cmd.REGISTRY), 3)
        self.assertTrue(hooks.is_wrapped(sys.modules['zone'].Zone, 'start_services'))
        self.assertIn('ERROR in SpeedKit Monitor start-up (load timer)', self.log_text())


# ====================================================================== 3. a lot unload ends the run
class LotUnloadTests(FakeSims):
    def test_teardown_ends_the_run_and_the_next_lot_shows_it(self):
        zmod = self.fake_zone()
        sys.modules['zone'], sys.modules['services'] = zmod, self.fake_services()
        with mock.patch.object(__import__('speedkit_monitor.ccguard').ccguard, 'run_after_load', lambda: None):
            self.assertIn('measuring', lagmeter.start(60, 25))
            z = zmod.Zone(0x11)
            for i in range(3):
                z.update(i)
            self.assertEqual(z.on_teardown('client-1'), 'torn down')      # the game's call is unchanged
            self.assertEqual(z.torn_down, ['client-1'])
            self.assertFalse(lagmeter.running())
            r = lagmeter.last_result
            with open(r['report'], encoding='utf-8') as f:
                self.assertIn('stopped by lot unloaded', f.read())
            self.assertEqual(r['ticks']['n'], 3)
            self.assertEqual(self.notes, [])                               # no lot UI any more
            z2 = zmod.Zone(0x22)
            loadtimer.on_zone_start(z2)
            loadtimer.on_lot_loaded(z2)
            self.assertEqual(len(self.notes), 1)
            self.assertEqual(self.notes[0][0], 'SpeedKit lag meter (previous lot)')
            loadtimer.on_zone_start(z2)
            loadtimer.on_lot_loaded(z2)
            self.assertEqual(len(self.notes), 1)                           # shown once
            self.assertEqual(z2.on_teardown(None), 'torn down')            # idle teardown: pass-through
        self.assertNotIn('ERROR', self.log_text())

    def test_zone_without_on_teardown_still_measures(self):
        zmod = self.fake_zone()
        del zmod.Zone.on_teardown
        sys.modules['zone'], sys.modules['services'] = zmod, self.fake_services()
        self.assertIn('measuring', lagmeter.start(5, 25))
        self.assertIsNotNone(lagmeter.finish('stop command', show=False))
        self.assertNotIn('ERROR', self.log_text())
        self.assertIn('has no on_teardown', self.log_text())


# ====================================================================== odd names in what we write
class LoneSurrogateTests(FakeSims):
    """A Windows file name may hold an unpaired surrogate (Python decodes it with surrogatepass); a strict
    UTF-8 write of it raised, which lost the whole lag result."""
    BAD = 'Bad\udc80Mod.ts4script'

    def test_lag_report_with_a_lone_surrogate_mod_name(self):
        zmod = self.fake_zone()
        sys.modules['zone'], sys.modules['services'] = zmod, self.fake_services()
        prof = sampling.Profile()
        look = sampling.OwnerLookup({'m.py': self.BAD})
        for _ in range(5):
            prof.add([('m.py', '1', 'f')], look)
        with mock.patch.object(sampling, 'analyse_file', lambda *a, **k: (prof, False)):
            lagmeter.start(5, 25)
            r = lagmeter.finish('stop command', show=False)
        self.assertIsNotNone(r)
        with open(r['report'], encoding='utf-8') as f:
            self.assertIn('Bad?Mod.ts4script', f.read())

    def test_log_and_csv_with_a_lone_surrogate(self):
        common.log('mod ' + self.BAD)
        self.assertIn('Bad?Mod', self.log_text())
        loadtimer.state['profile'] = 'lean\udc80'
        loadtimer.on_main_menu()
        with open(os.path.join(self.sims, 'SpeedKit', 'reports', 'loadtimes.csv'), encoding='utf-8') as f:
            self.assertIn('lean?', f.read())


# ====================================================================== install: partial failure + undo
class InstallPartialFailureTests(unittest.TestCase):
    def setUp(self):
        from speedkit import ingame_install, journal
        self.ii, self.journal = ingame_install, journal
        os.makedirs(SCRATCH, exist_ok=True)
        self.root = tempfile.mkdtemp(dir=SCRATCH)
        self.sims = os.path.join(self.root, 'The Sims 4 José ش')      # non-ASCII user folder
        self.home = os.path.join(self.sims, 'SpeedKit')
        os.makedirs(os.path.join(self.sims, 'Mods', 'scripts'))
        self.dist = os.path.join(self.root, 'SpeedKit_Monitor.ts4script')
        with open(self.dist, 'wb') as f:
            f.write(b'PK new build')
        self.target = os.path.join(self.sims, 'Mods', 'SpeedKit_Monitor.ts4script')
        self.stray = os.path.join(self.sims, 'Mods', 'scripts', 'SpeedKit_Monitor_old.ts4script')
        self.other = os.path.join(self.sims, 'Mods', 'scripts', 'WickedWhims.ts4script')
        for p, data in ((self.stray, b'PK old copy'), (self.other, b'PK someone else')):
            with open(p, 'wb') as f:
                f.write(data)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def read(self, p):
        with open(p, 'rb') as f:
            return f.read()

    def test_failure_after_quarantine_is_undoable(self):
        """The stray copy is quarantined first; then the target appears (the other chat) and put_new refuses.
        The journal must say 'failed', list the quarantine step, and undo must bring the stray copy back."""
        real_plan = self.ii.plan_install

        def stale_plan(dist, sims):
            plan = real_plan(dist, sims)
            with open(self.target, 'wb') as f:                  # appears between planning and applying
                f.write(b'PK somebody else')
            return plan
        with mock.patch.object(self.ii, 'plan_install', stale_plan):
            with self.assertRaises(self.journal.JournalError):
                self.ii.install(dry_run=False, dist=self.dist, sims=self.sims, home=self.home, check_game=False)
        self.assertFalse(os.path.exists(self.stray))
        self.assertEqual(self.read(self.target), b'PK somebody else')      # never overwritten
        (jid, kind, state, nsteps, _note), = self.journal.list_journals(self.home)
        self.assertEqual(kind, 'install')
        self.assertTrue(state.startswith('failed'), state)
        actions = self.journal.undo(jid, home=self.home, check_game=False)
        self.assertEqual(actions, [('restore', self.stray)])
        self.assertEqual(self.read(self.stray), b'PK old copy')
        self.assertEqual(self.read(self.target), b'PK somebody else')
        self.assertEqual(self.read(self.other), b'PK someone else')

    def test_non_ascii_sims_folder_install_and_undo(self):
        r = self.ii.install(dry_run=False, dist=self.dist, sims=self.sims, home=self.home, check_game=False)
        self.assertEqual(r['done'], [('quarantined', self.stray), ('installed', self.target)])
        self.assertEqual(self.read(self.target), b'PK new build')
        self.journal.undo(r['journal'], home=self.home, check_game=False)
        self.assertFalse(os.path.exists(self.target))
        self.assertEqual(self.read(self.stray), b'PK old copy')
        self.assertEqual(self.read(self.other), b'PK someone else')


# ====================================================================== the same inside the game's DLL
SCENARIO = r'''
import sys, os, json, time, zipfile, marshal, importlib.util, zipimport, types
A = json.loads(HOST_ARGS)
sys.path.insert(0, A['stubs'])
R = {'python': sys.version}
MODS = os.path.join(A['sims'], 'Mods')
BURN = 'import time\ndef burn(ms):\n    end = time.perf_counter() + ms / 1000.0\n    while time.perf_counter() < end:\n        pass\n'
WRAPS = 'import functools\ndef %s(fn):\n    @functools.wraps(fn)\n    def wrapper(*args, **kwargs):\n        return fn(*args, **kwargs)\n    return wrapper\n'

def ea_module(name, co_filename, src):
    m = types.ModuleType(name)
    m.__file__ = 'E:\\The Sims 4\\Data\\Simulation\\Gameplay\\simulation.zip\\' + name + '.pyc'
    sys.modules[name] = m
    exec(compile(src, co_filename, 'exec'), m.__dict__)
    return m
ea_module('caches', 'T:\\InGame\\Gameplay\\Scripts\\Core\\caches.py', WRAPS % 'cached_test')
ea_module('ea_utils', 'T:\\InGame\\Gameplay\\Scripts\\Core\\sims4\\utils.py', WRAPS % 'exception_protected')
ea_tests = ea_module('ea_tests', 'T:\\InGame\\Gameplay\\Scripts\\Server\\event_testing\\statistic_tests.py',
                     BURN + 'from caches import cached_test\nclass EATest:\n    @cached_test\n    def __call__(self):\n        burn(4)\n')
ea_area = ea_module('ea_area', 'T:\\InGame\\Gameplay\\Scripts\\Server\\areaserver.py',
                    'from ea_utils import exception_protected\n@exception_protected\ndef c_api_server_tick(zone, n):\n    zone.update(n)\n')

def build(name, entries):
    p = os.path.join(MODS, name)
    with zipfile.ZipFile(p, 'w', zipfile.ZIP_DEFLATED) as z:
        for arc, src, fake in entries:
            z.writestr(arc, importlib.util.MAGIC_NUMBER + b'\0' * 12 + marshal.dumps(compile(src, fake, 'exec')))
    sys.path.append(p)
build('fake_ww.ts4script', [('ww_tests.pyc', BURN + 'from caches import cached_test\nclass WWTest:\n    @cached_test\n    def __call__(self):\n        burn(1)\n',
                             '.\\WickedWhims_v185k\\ww_tests.py')])
build('fake_kuttoe.ts4script', [('kuttoe_mod.pyc', 'from ea_utils import exception_protected\n@exception_protected\ndef on_load_complete():\n    return 1\n',
                                 'E:\\Kuttoe\\kuttoe_mod.py')])
import ww_tests, kuttoe_mod, zone, services, sims4.commands
from ui import ui_dialog_notification as uidn
zone.ELEMENTS[:] = [ea_tests.EATest(), ww_tests.WWTest()]

code = zipimport.zipimporter(os.path.join(A['core_zip'], 'sims4', 'importer')).get_code('utils')
g = {'__name__': 'sims4.importer.utils_under_test'}
exec(code, g)
sys.path.append(A['archive'])
R['import_errors'] = g['import_modules_by_path'](A['archive'], True)
CMD = {k: v[0] for k, v in sims4.commands.REGISTRY.items()}
R['commands'] = sorted(CMD)
LM = sys.modules['speedkit_monitor.lagmeter']
LT = sys.modules['speedkit_monitor.loadtimer']
R['launch_source'] = LT.state['launch_source']
Z = zone.Zone(0x1234ABCD)
services._ZONE = Z
Z.start_services(None, None)
Z.on_loading_screen_animation_finished()
CMD['speedkit.lag']('60', '100', _connection=5)
S = {'n': 0}

def tick():
    S['n'] += 1
    if S['n'] <= 150:
        ea_area.c_api_server_tick(Z, S['n'])
    if S['n'] == 150:
        R['teardown_returned'] = Z.on_teardown('client')
        R['running_after_teardown'] = LM.running()
        r = LM.last_result or {}
        R['session'] = {k: r.get(k) for k in ('report', 'samples', 'ticks', 'shares', 'top')}
        R['lag_notes_before_next_lot'] = [n for n in uidn.SHOWN if 'lag meter' in n['title']]
        Z2 = zone.Zone(0x5678)
        services._ZONE = Z2
        Z2.start_services(None, None)
        Z2.on_loading_screen_animation_finished()
        R['lag_notes_after_next_lot'] = [n for n in uidn.SHOWN if 'lag meter' in n['title']]

def finish(host_s):
    with open(A['result'], 'w', encoding='utf-8') as f:
        json.dump(R, f, indent=1, default=str)
'''


@unittest.skipUnless(game_python.available(), 'game python37_x64.dll not found')
class GameDllReviewTests(unittest.TestCase):
    """The built archive in the game's own python37_x64.dll: EA-style decorators in a mod and in the tick
    path, a lot unload during a run, and a pre-1970 launch_time.json."""

    @classmethod
    def setUpClass(cls):
        from test_ingame import STUBS
        cls.base = os.path.join(SCRATCH, 'dll')
        shutil.rmtree(cls.base, ignore_errors=True)
        stubs = os.path.join(cls.base, 'stubs')
        files = dict(STUBS)
        # the game's Zone has on_teardown(self, client) (zone.pyc line 791); Zone is the stub's last class
        files['zone.py'] = STUBS['zone.py'] + ("    def on_teardown(self, client):\n"
                                               "        self.torn_down = client\n"
                                               "        return 'torn down'\n")
        for rel, text in files.items():
            p = os.path.join(stubs, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, 'w', encoding='utf-8') as f:
                f.write(text)
        cls.sims = os.path.join(cls.base, 'fake_sims', 'The Sims 4')
        mods = os.path.join(cls.sims, 'Mods')
        os.makedirs(os.path.join(cls.sims, 'SpeedKit'))
        os.makedirs(mods)
        with open(os.path.join(cls.sims, 'Config.log'), 'w') as f:
            f.write('Free memory:     559MB\n')
        with open(os.path.join(cls.sims, 'SpeedKit', 'launch_time.json'), 'w') as f:
            json.dump({'launch_time': '1969-12-31T23:00:00'}, f)
        dist = os.path.join(cls.base, 'SpeedKit_Monitor.ts4script')
        build_ingame.build(dist=dist)
        cls.archive = os.path.join(mods, 'SpeedKit_Monitor.ts4script')
        shutil.copy2(dist, cls.archive)
        script = os.path.join(cls.base, 'scenario_review37.py')
        with open(script, 'w', encoding='utf-8') as f:
            f.write(SCENARIO)
        result = os.path.join(cls.base, 'result.json')
        args = {'stubs': stubs, 'sims': cls.sims, 'archive': cls.archive, 'result': result,
                'core_zip': os.path.join(game_python.GAMEPLAY, 'core.zip')}
        cls.cp = game_python.run(script, args=json.dumps(args), ticks=155, gap_ms=20.0, timeout=600)
        cls.R = {}
        if os.path.exists(result):
            with open(result, encoding='utf-8') as f:
                cls.R = json.load(f)
        log = os.path.join(cls.sims, 'SpeedKit', 'reports', 'monitor.log')
        with open(log, encoding='utf-8') as f:
            cls.log = f.read()
        raw = os.path.join(cls.sims, 'SpeedKit', 'reports', 'lag_raw_last.txt')
        if os.path.exists(raw):
            os.remove(raw)                                       # scratch dump, not needed after the run

    def test_ran_cleanly_with_a_pre_1970_launch_time(self):
        self.assertEqual(self.cp.returncode, 0, self.cp.stdout[-3000:] + self.cp.stderr[-3000:])
        self.assertTrue(self.R['python'].startswith('3.7.0'))
        self.assertEqual(self.R['import_errors'], 0)
        self.assertEqual(self.R['commands'], ['speedkit.cc', 'speedkit.lag', 'speedkit.status'])
        self.assertEqual(self.R['launch_source'], 'config.log')
        self.assertNotIn('ERROR', self.log)

    def test_ea_decorators_are_not_charged_to_mods(self):
        """Per tick: EA cached test 4 ms, the WickedWhims-like test 1 ms, zone 3 ms, then 20 ms outside
        Python. Before the fix the EA test (4 ms) went to fake_ww and the zone's own 3 ms to fake_kuttoe."""
        sh = self.R['session']['shares']
        ww, kut, game = sh.get('fake_ww.ts4script', 0), sh.get('fake_kuttoe.ts4script', 0), sh.get('game', 0)
        self.assertEqual(kut, 0, sh)
        self.assertGreater(ww, 0, sh)
        self.assertLess(ww, 9, sh)                               # true 1/28 = 3.6 %; the old map gave ~18 %
        self.assertGreater(game, 15, sh)                         # true 7/28 = 25 %; the old map gave ~0 %
        self.assertGreater(game, 2 * ww, sh)

    def test_lot_unload_ends_the_run_and_the_next_lot_shows_it(self):
        self.assertEqual(self.R['teardown_returned'], 'torn down')
        self.assertFalse(self.R['running_after_teardown'])
        with open(self.R['session']['report'], encoding='utf-8') as f:
            self.assertIn('stopped by lot unloaded', f.read())
        self.assertEqual(self.R['session']['ticks']['n'], 150)   # tick 150 ran its update before teardown
        self.assertEqual(self.R['lag_notes_before_next_lot'], [])
        notes = self.R['lag_notes_after_next_lot']
        self.assertEqual(len(notes), 1)
        self.assertIn('(previous lot)', notes[0]['title'])
        self.assertIn('Top script mods', notes[0]['text'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
