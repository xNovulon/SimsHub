"""speedkit.api (docs\\hub_contract.md) and the CLI (python -m speedkit) on a fake Sims 4 tree under
E:\\speedkit_test\\api: test_fastmode's world plus two saves with slot data (test_savepacks), a fake game folder
and a fake game exe (a .bat that only writes a marker file). The real game is never started and nothing
under the real Sims 4 folder is touched."""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
import test_fastmode as TF  # noqa: E402
import test_savepacks as TS  # noqa: E402
from speedkit import api, fastmode as F, savepacks as S, profiles as PR, journal as J, library as L  # noqa: E402
from speedkit import __main__ as CLI  # noqa: E402
from speedkit.game_index import GameIndex  # noqa: E402

BASE = r'E:\speedkit_test\api'
STATUS_KEYS = {'ok', 'game_running', 'profile', 'graphics', 'memory', 'library', 'fastpack', 'monitor', 'load_times',
               'journals', 'animator', 'disk', 'game', 'inbox', 'report'}
INSIDE_WORDS = ('package', 'quarantine', 'journal', 'profile', 'CASP')


def assert_plain(test, text):
    for w in INSIDE_WORDS:
        test.assertNotRegex(text, r'(?i)(?<![\w.])%s' % w, text)


class Tree(unittest.TestCase):
    """A fresh fake tree per test class; api configured to it."""

    @classmethod
    def setUpClass(cls):
        os.makedirs(BASE, exist_ok=True)
        cls.root = tempfile.mkdtemp(dir=BASE, prefix='t_')
        cls.sims, _ = TF.make_world(cls.root)
        TS.make_saves(cls.sims)
        cls.old_big = F.BIG_CAS_BYTES
        F.BIG_CAS_BYTES = 3000
        gi = GameIndex(os.path.join(cls.root, 'game.sqlite'), os.path.join(cls.root, 'game'))
        gi.scan()
        gi.close()
        cls.marker = os.path.join(cls.root, 'launched.txt')
        cls.exe = os.path.join(cls.root, 'fakegame', 'TS4_x64.bat')
        os.makedirs(os.path.dirname(cls.exe))
        with open(cls.exe, 'w') as f:
            f.write('@echo off\r\necho started>> "%s"\r\n' % cls.marker)
        cls.opened = []
        cls.animator = os.path.join(cls.root, 'Start Wicked Animator.bat')
        with open(cls.animator, 'w') as f:
            f.write('@echo off\r\n')
        cls.config = dict(
            sims=cls.sims, db_path=os.path.join(cls.root, 'library.sqlite'), refs_db=os.path.join(cls.root, 'refs.sqlite'),
            game_ids_db=os.path.join(cls.root, 'game_ids.sqlite'), game_db=os.path.join(cls.root, 'game.sqlite'),
            companions_cache=os.path.join(cls.root, 'companions.sqlite'), hash_cache=os.path.join(cls.root, 'hash.sqlite'),
            bc_cache=os.path.join(cls.root, 'bc.json.gz'),
            game={'exe': cls.exe, 'game_dir': os.path.join(cls.root, 'game'), 'store': 'unknown', 'source': 'test'},
            check_game=False, verdicts=TF.verdicts_for, build_monitor=False, processes=False, animator=cls.animator,
            opener=cls.opened.append, remember_game=False)

    @classmethod
    def tearDownClass(cls):
        api.reset()
        F.BIG_CAS_BYTES = cls.old_big
        shutil.rmtree(cls.root, ignore_errors=True)

    def setUp(self):
        api.reset()
        api.configure(**self.config)

    def tearDown(self):
        api.reset()

    def mods_packs(self):
        return sorted(n for n in os.listdir(os.path.join(self.sims, 'Mods')) if F.is_speedkit_pack(n))

    def journals(self):
        return J.list_journals(os.path.join(self.sims, 'SpeedKit'))


class Flow(Tree):
    """One ordered story: status, saves, prepare fast, the saves' numbers, a save, play, undo."""

    def test_1_status_before_anything(self):
        st = api.status()
        self.assertTrue(STATUS_KEYS <= set(st), STATUS_KEYS - set(st))
        self.assertTrue(st['ok'])
        self.assertEqual(st['game'], {'found': True, 'exe': self.exe, 'source': 'test', 'saved': False,
                                      'message': st['game']['message'], 'store': 'unknown',
                                      'game_dir': os.path.join(self.root, 'game'), 'lost_path': None})
        self.assertEqual(st['inbox'], {'path': os.path.join(self.sims, 'SpeedKit', 'Inbox'), 'waiting': 0})
        self.assertEqual(st['report'], {'path': None, 'when': None})
        # CAS parts loaded now: the packages in Mods (the fake world keeps some CC in Mods)
        self.assertGreater(st['library']['cas_now'], 0)          # read from the files (no index yet)
        assert_plain(self, st['fastpack']['why'])
        self.assertEqual(st['fastpack']['state'], 'missing')
        self.assertIn(st['profile']['name'], PR.PROFILES + ('custom',))
        self.assertEqual(st['animator'], {'installed': True, 'path': self.animator})
        for k in ('free_gb', 'total_gb', 'warnings', 'top'):
            self.assertIn(k, st['memory'])
        for k in ('packages', 'gb', 'cas_full', 'cas_fast'):
            self.assertIn(k, st['library'])
        self.assertIn('c_free_gb', st['disk'])

    def test_2_list_saves(self):
        r = api.list_saves()
        self.assertTrue(r['ok'])
        by = {s['slot']: s for s in r['saves']}
        self.assertEqual(sorted(by), ['Slot_00000001', 'Slot_00000002'])
        s1 = by['Slot_00000001']
        self.assertEqual((s1['name'], s1['household'], s1['world'], s1['sims'], s1['lots'], s1['cc_parts'],
                          s1['cc_missing']), ('Lee Story', 'Lee Family', 'Willow Creek', 1, 3, 1, 1))
        self.assertEqual(s1['pack'], {'state': 'missing', 'gb': None})
        self.assertIsNone(s1['cas_loaded'])                  # unknown until the b/c part has been planned once
        for k in ('slot', 'name', 'household', 'world', 'last_played', 'size_mb', 'sims', 'lots', 'cc_parts',
                  'cas_loaded', 'pack'):
            self.assertIn(k, s1)

    def test_3_prepare_fast(self):
        events = []
        r = api.prepare('fast', lambda step, frac, msg: events.append((step, msg)))
        self.assertTrue(r['ok'], r)
        self.assertFalse(r['launched'])
        steps = [s['step'] for s in r['steps']]
        for want in ('library', 'monitor', 'graphics', 'pack', 'mods', 'memory'):
            self.assertIn(want, steps)
        self.assertTrue(all(s['ok'] for s in r['steps']), r['steps'])
        self.assertTrue(all('warn' in s for s in r['steps']))
        self.assertTrue(all(s['warn'] for s in r['steps'] if s['step'] == 'memory' and 'fine' not in s['message']))
        for s in r['steps']:
            assert_plain(self, s['message'])
        self.assertTrue(events)
        self.assertEqual(self.mods_packs(), ['!!!!!SpeedKit_Fast_001.package'])
        self.assertTrue(os.path.exists(os.path.join(self.sims, 'Mods', 'SpeedKit_Monitor.ts4script')))
        st = api.status()
        self.assertEqual(st['profile']['name'], 'fast')
        self.assertEqual(st['fastpack']['state'], 'fresh')
        # in Fast mode the loaded CAS parts are the kept ones plus the pack's (read from the pack itself)
        man = F.read_manifest(os.path.join(self.sims, 'SpeedKit', 'fastpack'))
        self.assertEqual(st['library']['cas_now'], man['cas_parts']['fast'])
        js = st['journals']
        self.assertEqual(js[0]['title'], 'Switched to Fast mode')
        self.assertTrue(js[0]['undoable'] and js[0]['next_undo'])
        self.assertEqual(sum(1 for j in js if j['next_undo']), 1)
        self.assertIn('Made the fast pack', [j['title'] for j in js])
        for j in js:
            assert_plain(self, j['title'])
        self.assertTrue(st['monitor']['installed'])
        self.assertIsNotNone(st['library']['cas_fast'])
        self.assertTrue(os.path.exists(self.config['bc_cache']))
        # now the saves know how many CAS parts playing only them would load
        by = {s['slot']: s for s in api.list_saves()['saves']}
        self.assertTrue(all(isinstance(s['cas_loaded'], int) for s in by.values()))

    def test_4_prepare_a_save(self):
        r = api.prepare('save:Slot_00000002')
        self.assertTrue(r['ok'], r)
        self.assertEqual(self.mods_packs(), ['!!!!!SpeedKit_Save_00000002_001.package'])
        st = api.status()
        self.assertEqual((st['profile']['name'], st['profile']['save_slot']), ('save', 'Slot_00000002'))
        self.assertIn('Nu Legacy', st['profile']['label'])
        state = PR.read_state(self.sims)
        self.assertEqual((state['profile'], state['save_slot'], state['save_name']),
                         ('save', 'Slot_00000002', 'Nu Legacy'))
        self.assertTrue(state['pack_dir'].endswith(os.path.join('savepacks', 'Slot_00000002')))
        by = {s['slot']: s for s in api.list_saves()['saves']}
        self.assertEqual(by['Slot_00000002']['pack']['state'], 'fresh')
        self.assertEqual(by['Slot_00000001']['pack']['state'], 'missing')
        self.assertLess(by['Slot_00000002']['cas_loaded'], api.status()['library']['cas_full'])
        # the duplicate clean-up refuses while a pack is in Mods (it would take the pack's copies for keepers)
        r = api.cleanup_plan()
        self.assertFalse(r['ok'])
        self.assertIn('All CC', r['message'])
        self.assertFalse(api.cleanup_apply()['ok'])
        # while a Play runs, list_saves parses nothing and still answers
        api._run_lock.acquire()
        try:
            self.assertTrue(api.list_saves()['ok'])
        finally:
            api._run_lock.release()

    def test_5_play_launches_the_fake_exe(self):
        if os.path.exists(self.marker):
            os.remove(self.marker)
        r = api.play('save:Slot_00000001')
        self.assertTrue(r['ok'], r)
        self.assertTrue(r['launched'])
        self.assertEqual(r['steps'][-1]['step'], 'launch')
        for _ in range(50):
            if os.path.exists(self.marker):
                break
            time.sleep(0.1)
        self.assertTrue(os.path.exists(self.marker), 'the fake exe did not run')
        with open(os.path.join(self.sims, 'SpeedKit', 'launch_time.json'), encoding='utf-8') as f:
            lt = json.load(f)
        self.assertEqual((lt['profile'], lt['save_slot']), ('save', 'Slot_00000001'))
        self.assertEqual(self.mods_packs(), ['!!!!!SpeedKit_Save_00000001_001.package'])
        # the other save's pack went back to its folder
        self.assertEqual(S.pack_names(os.path.join(self.sims, 'SpeedKit'), 'Slot_00000002'),
                         ['!!!!!SpeedKit_Save_00000002_001.package'])

    def test_6_undo_last(self):
        before = [j for j in self.journals() if j[2] == 'committed']
        nxt = [j for j in api.status()['journals'] if j['next_undo']][0]
        r = api.undo_last()
        self.assertTrue(r['ok'], r)
        self.assertEqual(r['journal'], nxt['id'])                 # status says exactly what undo_last undoes
        self.assertIn('Switched to Play this save', r['message'])
        assert_plain(self, r['message'])
        undone = [j for j in self.journals() if j[0] == r['journal']][0]
        self.assertEqual(undone[2], 'undone')
        self.assertEqual(self.mods_packs(), ['!!!!!SpeedKit_Save_00000002_001.package'])   # back to save 2
        self.assertEqual(api.status()['profile']['save_slot'], 'Slot_00000002')
        self.assertTrue(before)

    def test_7_full_puts_every_pack_home(self):
        r = api.prepare('full')
        self.assertTrue(r['ok'], r)
        self.assertEqual(self.mods_packs(), [])
        self.assertEqual(api.status()['profile']['name'], 'full')
        self.assertTrue(PR.check_manifest(self.sims)['ok'])
        self.assertTrue(api.cleanup_plan()['ok'])

    def test_8_report_and_folders(self):
        r = api.report()
        self.assertTrue(r['ok'], r)
        rep = api.status()['report']
        self.assertEqual(rep['path'], r['path'])
        self.assertTrue(rep['when'])
        with open(r['path'], encoding='utf-8') as f:
            html = f.read()
        self.assertIn('Lee Story', html)
        self.assertIn('Nu Legacy', html)
        del self.opened[:]
        for which in api.FOLDERS:
            self.assertTrue(api.open_folder(which)['ok'], which)
        self.assertEqual(len(self.opened), len(api.FOLDERS))
        self.assertFalse(api.open_folder('windows')['ok'])
        self.assertTrue(api.open_folder('report_html')['ok'])
        self.assertEqual(self.opened[-1], r['path'])
        self.assertTrue(api.open_animator()['ok'])
        self.assertEqual(self.opened[-1], self.animator)
        api.configure(animator=os.path.join(self.root, 'nope.bat'))
        self.assertFalse(api.open_animator()['ok'])
        self.assertEqual(api.status()['animator'], {'installed': False, 'path': None})
        # the default: the Wicked Animator desktop app, or its .bat when the exe is missing (nothing is started here)
        api.configure(animator=None)
        a = api.status()['animator']
        self.assertIn(a['path'], (api.ANIMATOR_EXE, api.ANIMATOR_BAT, None))
        if a['installed']:
            del self.opened[:]
            self.assertTrue(api.open_animator()['ok'])
            self.assertIn(self.opened[-1], (api.ANIMATOR_EXE, api.ANIMATOR_BAT))


class Refusals(Tree):
    def test_game_running(self):
        api.configure(check_game=True)
        before = self.journals()
        with mock.patch.object(L, 'game_running', return_value=True):
            for target in ('fast', 'full', 'save:Slot_00000001'):
                r = api.play(target)
                self.assertFalse(r['ok'])
                self.assertFalse(r['launched'])
                self.assertIn('already running', r['message'])
            self.assertFalse(api.undo_last()['ok'])
            self.assertFalse(api.inbox(apply=True)['ok'])
            self.assertFalse(api.cleanup_apply()['ok'])
            self.assertFalse(api.graphics_tune(apply=True)['ok'])
            self.assertTrue(api.status()['game_running'])
        self.assertEqual(self.journals(), before)

    def test_bad_targets_and_missing_game(self):
        for bad in ('', 'turbo', 'save:', 'save:Slot_1'):
            r = api.prepare(bad)
            self.assertFalse(r['ok'])
            self.assertIn('Choose what to play' if bad in ('', 'turbo') else 'not a save slot', r['message'])
        r = api.prepare('save:Slot_00000009')
        self.assertFalse(r['ok'])
        self.assertIn('gone', r['message'])
        import test_gamepath as TG
        api.configure(game=None, game_clues=TG.no_clues(), home=os.path.join(self.root, 'nogame_home'))
        r = api.play('fast')
        self.assertFalse(r['ok'])
        self.assertIn("can't find The Sims 4", r['message'])
        self.assertFalse(api.status()['game']['found'])

    def test_graphics_without_rules_and_inbox_and_cleanup(self):
        r = api.graphics_tune()
        self.assertFalse(r['ok'])
        self.assertTrue(r['message'])
        self.assertFalse(api.graphics_restore()['ok'])
        r = api.inbox()
        self.assertTrue(r['ok'], r)
        self.assertIn('empty', r['message'])
        self.assertEqual(r['items'], [])
        self.assertTrue(r['inbox_path'].endswith('Inbox'))
        inbox = os.path.join(self.sims, 'SpeedKit', 'Inbox')
        os.makedirs(inbox, exist_ok=True)
        TF.pkg(os.path.join(inbox, 'NewHair.package'), TF.filler_cas(0x4E4E000000000000, 2))
        with open(os.path.join(inbox, 'desktop.ini'), 'w') as f:
            f.write('x')
        with open(os.path.join(inbox, 'Half.zip.crdownload'), 'w') as f:
            f.write('x')
        self.assertEqual(api.status()['inbox']['waiting'], 1)
        r = api.inbox()
        self.assertEqual([i['name'] for i in r['items'] if i['status'] != 'skipped'], ['NewHair.package'])
        self.assertIn('waiting', r['message'])
        self.assertTrue(os.path.exists(os.path.join(inbox, 'NewHair.package')))       # a dry run moves nothing
        r = api.cleanup_plan()
        self.assertTrue(r['ok'], r)
        for k in ('copies', 'gb', 'rewritten', 'removed', 'message'):
            self.assertIn(k, r)


class Steam(Tree):
    def test_steam_install_starts_through_steam(self):
        from speedkit import launch as LA
        api.configure(game=dict(self.config['game'], store='steam'))
        with mock.patch.object(LA, '_open_url') as opened, mock.patch.object(LA, '_start_detached') as started:
            r = api.play('full')
        self.assertTrue(r['ok'], r)
        opened.assert_called_once_with('steam://rungameid/1222670')
        started.assert_not_called()
        self.assertIn('through Steam', r['steps'][-1]['message'])
        with open(os.path.join(self.sims, 'SpeedKit', 'launch_time.json'), encoding='utf-8') as f:
            lt = json.load(f)
        self.assertEqual(lt['via'], 'steam://rungameid/1222670')
        self.assertIsNone(lt['pid'])


class Cli(Tree):
    def run_cli(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch.object(CLI.api, 'configure', lambda **kw: None):
            code = CLI.main(list(args))
        return code, out.getvalue()

    def test_cli(self):
        code, out = self.run_cli('status')
        self.assertEqual(code, 0, out)
        self.assertIn('Mods:', out)
        code, out = self.run_cli('saves')
        self.assertEqual(code, 0, out)
        self.assertIn('Lee Story', out)
        code, out = self.run_cli('prepare', 'fast')
        self.assertEqual(code, 0, out)
        self.assertIn('[ok]', out)
        code, out = self.run_cli('prepare')
        self.assertEqual(code, 2)
        code, out = self.run_cli('graphics')
        self.assertEqual(code, 1)
        code, out = self.run_cli('inbox')
        self.assertEqual(code, 0, out)
        code, out = self.run_cli('undo')
        self.assertEqual(code, 0, out)
        code, out = self.run_cli('nonsense')
        self.assertEqual(code, 2)
        code, out = self.run_cli('help')
        self.assertIn('python -m speedkit', out)


if __name__ == '__main__':
    unittest.main()
