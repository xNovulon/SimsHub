"""The CC guard knows the prepared save (ingame/speedkit_monitor/ccguard.py): pure logic under 3.12, and the built
mod inside the game's own python37_x64.dll with stand-in game modules (a 'save' profile, the wrong save loaded,
the right one, and missing CC). Scratch data under E:\\speedkit_test\\ingame_saveguard."""
import json
import os
import shutil
import sys
import textwrap
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(PROJECT, 'ingame'))
sys.path.insert(0, PROJECT)
sys.path.insert(0, HERE)
from speedkit_monitor import ccguard  # noqa: E402
from tools import game_python, build_ingame  # noqa: E402

SCRATCH = r'E:\speedkit_test\ingame_saveguard'
DOC = {'profile': 'save', 'save_slot': 'Slot_00000014', 'save_slot_id': 20, 'save_name': 'Neuworld Save File',
       'save_guid': 1560215555, 'pack_dir': r'X:\SpeedKit\savepacks\Slot_00000014',
       'installed_nowhere': ['DEADBEEF0000000A']}


class PureLogic(unittest.TestCase):
    def test_expected_save(self):
        e = ccguard.expected_save(DOC)
        self.assertEqual(e, {'slot': 'Slot_00000014', 'number': 0x14, 'slot_id': 20, 'name': 'Neuworld Save File',
                             'guid': 1560215555})
        self.assertIsNone(ccguard.expected_save({'profile': 'fast'}))
        self.assertIsNone(ccguard.expected_save({'profile': 'save'}))          # no slot named
        self.assertIsNone(ccguard.expected_save(None))
        self.assertEqual(ccguard.slot_number('Slot_ffffffff'), 0xFFFFFFFF)
        self.assertIsNone(ccguard.slot_number('Slot_xyz'))

    def test_same_save(self):
        e = ccguard.expected_save(DOC)
        same = ccguard.same_save
        self.assertTrue(same(e, {'slot_id': 20, 'name': 'Neuworld Save File', 'guid': 1560215555}))
        # the game wrote the file's own number after a save to this slot
        self.assertTrue(same(e, {'slot_id': 0x14, 'name': 'Neuworld Save File', 'guid': 1560215555}))
        # the recovered copy: same guid, other name and id
        self.assertFalse(same(e, {'slot_id': 21, 'name': 'Neuworld Save File [Recovered]', 'guid': 1560215555}))
        # a copy that kept the id (Slot_00000018 holds 23 like Slot_00000017): the name tells them apart
        e17 = ccguard.expected_save(dict(DOC, save_slot='Slot_00000017', save_slot_id=23,
                                         save_name='My Saved Game 21 [Recovered]'))
        self.assertFalse(same(e17, {'slot_id': 23, 'name': 'My Saved Game 21 [Re [Recovered]', 'guid': 1560215555}))
        self.assertFalse(same(e, {'slot_id': 20, 'name': 'Neuworld Save File', 'guid': 99}))       # other game
        self.assertIsNone(same(e, None))
        self.assertIsNone(same(e, {'slot_id': None, 'name': None, 'guid': None}))

    def test_installed_nowhere(self):
        self.assertEqual(ccguard.installed_nowhere(DOC), {0xDEADBEEF0000000A})
        self.assertEqual(ccguard.installed_nowhere({'installed_nowhere': ['zz', None, 7]}), {7})
        self.assertEqual(ccguard.installed_nowhere(None), set())

    def test_decide(self):
        self.assertEqual(ccguard.decide({'profile': 'full'}, False, 5), (False, []))       # old guard's job
        self.assertEqual(ccguard.decide({'profile': 'lean'}, None, 0), (False, []))
        warn, why = ccguard.decide(DOC, False, 0)
        self.assertTrue(warn)
        self.assertIn('another save', why[0])
        self.assertEqual(ccguard.decide(DOC, True, 0), (False, []))
        self.assertEqual(ccguard.decide(DOC, None, 0), (False, []))                        # cannot tell: no alarm
        self.assertTrue(ccguard.decide(DOC, True, 3)[0])                                  # missing CC in 'save'
        self.assertTrue(ccguard.decide({'profile': 'fast'}, None, 1)[0])                   # missing CC in 'fast'
        self.assertFalse(ccguard.decide({'profile': 'fast'}, None, 0)[0])
        self.assertEqual(ccguard.PREPARED_TEXT, "This save was not prepared for this mode - do not save. "
                                                "Restart the game from Novulon's Sims Hub.")


SERVICES = textwrap.dedent('''\
    _ZONE = None
    _HOUSEHOLD = None
    _SLOT = None
    _GUID = None
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
    class _Persistence:
        def get_save_slot_proto_buff(self):
            return _SLOT
        def get_save_slot_proto_guid(self):
            return _GUID
    def get_persistence_service():
        return _Persistence()
    ''')

SCENARIO = r'''
import sys, os, json, time, zipimport
A = json.loads(HOST_ARGS)
sys.path.insert(0, A['stubs'])
R = {'python': sys.version}
import zone, services, cas.cas
from ui import ui_dialog_notification as uidn
code = zipimport.zipimporter(os.path.join(A['core_zip'], 'sims4', 'importer')).get_code('utils')
g = {'__name__': 'sims4.importer.utils_under_test'}
exec(code, g)
sys.path.append(A['archive'])
R['import_errors'] = g['import_modules_by_path'](A['archive'], True)

class Slot:
    def __init__(self, slot_id, name):
        self.slot_id, self.slot_name = slot_id, name
class OutfitData:
    def __init__(self, ids):
        self.part_ids = ids
class SimInfo:
    def __init__(self, first, sid, ids):
        self.first_name, self.last_name, self.id, self._ids = first, 'Lara', sid, ids
    def get_outfits(self):
        return self
    def get_all_outfits(self):
        yield 0, [OutfitData(self._ids)]
class Household:
    name = 'Lara'
    def __init__(self, sims):
        self.sims = sims
    def sim_info_gen(self):
        for s in self.sims:
            yield s
cas.cas.KNOWN.update({1, 2, 3})
ok_household = Household([SimInfo('Bella', 11, (1, 2)), SimInfo('Ann', 12, (3,))])
missing_household = Household([SimInfo('Bella', 11, (1, 0xDEADBEEF12345678))])
nowhere_household = Household([SimInfo('Bella', 11, (1, 0xDEADBEEF0000000A))])

def load_lot(zid, slot, guid, household):
    services._SLOT, services._GUID, services._HOUSEHOLD = slot, guid, household
    z = zone.Zone(zid)
    services._ZONE = z
    z.start_services(None, slot)
    z.on_loading_screen_animation_finished()
    return len(uidn.SHOWN)

R['counts'] = []
services.on_enter_main_menu()
# 1. the recovered copy is loaded instead of the prepared save
R['counts'].append(load_lot(0x100, Slot(21, 'Neuworld Save File [Recovered]'), 1560215555, ok_household))
# 2. travel in the same session: still that save (the verdict of the first lot is kept)
R['counts'].append(load_lot(0x101, Slot(20, 'Neuworld Save File'), 1560215555, ok_household))
# 3. back to the menu, the prepared save: all CC loaded -> no notification
services.on_enter_main_menu()
R['counts'].append(load_lot(0x102, Slot(20, 'Neuworld Save File'), 1560215555, ok_household))
# 4. the prepared save, but a sim wears CC this mode does not load
R['counts'].append(load_lot(0x103, Slot(20, 'Neuworld Save File'), 1560215555, missing_household))
# 5. no persistence data at all (cannot tell which save): only the CC check counts
services.on_enter_main_menu()
R['counts'].append(load_lot(0x104, None, None, ok_household))
# 6. the right save, wearing only CC that is installed nowhere (missing in every mode): no notification
services.on_enter_main_menu()
R['counts'].append(load_lot(0x105, Slot(20, 'Neuworld Save File'), 1560215555, nowhere_household))
R['notifications'] = uidn.SHOWN
with open(A['result'], 'w', encoding='utf-8') as f:
    json.dump(R, f, indent=1, default=str)
'''


@unittest.skipUnless(game_python.available(), 'game python37_x64.dll not found')
class GameDllSaveGuard(unittest.TestCase):
    """The built monitor inside the game's DLL with profile_state.json of a 'save' profile."""

    @classmethod
    def setUpClass(cls):
        import test_ingame as TI
        if os.path.exists(SCRATCH):
            shutil.rmtree(SCRATCH)
        stubs = os.path.join(SCRATCH, 'stubs')
        files = dict(TI.STUBS)
        files['services.py'] = SERVICES
        for rel, text in files.items():
            p = os.path.join(stubs, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, 'w', encoding='utf-8') as f:
                f.write(text)
        cls.sims = os.path.join(SCRATCH, 'fake_sims', 'The Sims 4')
        mods = os.path.join(cls.sims, 'Mods')
        os.makedirs(os.path.join(cls.sims, 'SpeedKit'))
        os.makedirs(mods)
        with open(os.path.join(cls.sims, 'Config.log'), 'w') as f:
            f.write('Free memory:     559MB\n')
        with open(os.path.join(cls.sims, 'SpeedKit', 'profile_state.json'), 'w') as f:
            json.dump(DOC, f)
        build = build_ingame.build()
        archive = os.path.join(mods, 'SpeedKit_Monitor.ts4script')
        shutil.copy2(build['dist'], archive)
        script = os.path.join(SCRATCH, 'scenario37.py')
        with open(script, 'w', encoding='utf-8') as f:
            f.write(SCENARIO)
        result = os.path.join(SCRATCH, 'result.json')
        args = {'stubs': stubs, 'archive': archive, 'result': result,
                'core_zip': os.path.join(game_python.GAMEPLAY, 'core.zip')}
        cls.cp = game_python.run(script, args=json.dumps(args), timeout=300)
        cls.R = {}
        if os.path.exists(result):
            with open(result, encoding='utf-8') as f:
                cls.R = json.load(f)
        log = os.path.join(cls.sims, 'SpeedKit', 'reports', 'monitor.log')
        with open(log, encoding='utf-8', errors='replace') as f:
            cls.log = f.read()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(SCRATCH, ignore_errors=True)

    def test_notifications(self):
        self.assertEqual(self.cp.returncode, 0, self.cp.stdout[-2000:] + self.cp.stderr[-2000:])
        self.assertEqual(self.R['import_errors'], 0)
        # 1 wrong save -> 1; 2 same session -> 2; 3 right save -> 2; 4 missing CC -> 3; 5 unknown save, all CC -> 3
        self.assertEqual(self.R['counts'], [1, 2, 2, 3, 3, 3])
        for n in self.R['notifications']:
            self.assertEqual(n['title'], "RAW:Novulon's Sims Hub")
            self.assertEqual(n['text'], 'RAW:' + ccguard.PREPARED_TEXT)
            self.assertEqual(n['urgency'], 1)
        self.assertIn('ANOTHER SAVE', self.log)
        self.assertIn('same save', self.log)
        self.assertIn('cannot tell', self.log)
        self.assertIn('installed nowhere', self.log)
        self.assertNotIn('ERROR', self.log)


if __name__ == '__main__':
    unittest.main()
