"""Patch day (speedkit/patchday.py through speedkit/api.py): noticing a game update, listing script mods older
than it, setting mods aside through the shared parking store and putting them back - every change undoable, and
refused while the game runs. Cross-platform: a fake Sims 4 folder in a temp folder."""
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from speedkit import api, patchday as PD, profiles as PR, journal as J, library as L  # noqa: E402
from tests import care_fakes as F  # noqa: E402

DAY = F.DAY


class Base(unittest.TestCase):
    def setUp(self):
        self.root, self.sims = F.make_sims()
        self.mods = os.path.join(self.sims, 'Mods')
        self.parked = os.path.join(self.sims, 'Mods_parked')
        self.home = os.path.join(self.sims, 'SpeedKit')
        self.t_patch = F.now() - 3 * DAY
        self.game = F.make_game(self.root, self.t_patch)
        F.write_version(self.sims, '1.118.242.1030', self.t_patch - 20 * DAY)
        api.configure(sims=self.sims, db_path=os.path.join(self.root, 'library.sqlite'), check_game=False,
                      game={'exe': os.path.join(self.game, 'Game', 'Bin', 'TS4_x64.exe'), 'game_dir': self.game,
                            'store': 'ea', 'source': 'test'},
                      refs_db=os.path.join(self.root, 'refs.sqlite'), companions_cache=os.path.join(self.root, 'c.sqlite'))
        # MCCC: old script + its tuning companion (names the script's module) + an unrelated CC file in the folder
        old = self.t_patch - 40 * DAY
        F.make_script(os.path.join(self.mods, 'MCCC', 'mc_cmd_center.ts4script'),
                      ['mc_cmd_center/__init__.pyc', 'mc_cmd_center/mc_utils/mc_zone.pyc'], old)
        F.make_tuning_package(os.path.join(self.mods, 'MCCC', 'mc_cmd_center.package'), 'mc_cmd_center.mc_tuning', old)
        F.make_cc_package(os.path.join(self.mods, 'MCCC', 'some_hair.package'), old)
        # a root script with a same-name companion
        F.make_script(os.path.join(self.mods, 'ui_cheats_extension.ts4script'), ['ui_cheats/main.pyc'], old)
        F.make_tuning_package(os.path.join(self.mods, 'ui_cheats_extension.package'), 'ui_cheats.tuning', old)
        # updated after the patch
        F.make_script(os.path.join(self.mods, 'WickedWhims', 'TURBODRIVER_WickedWhims_Scripts.ts4script'),
                      ['wickedwhims/main.pyc', 'turbolib2/x.pyc'], self.t_patch + DAY)
        # too deep to load: never listed
        F.make_script(os.path.join(self.mods, 'a', 'b', 'deep.ts4script'), ['deep/x.pyc'], old)
        # SpeedKit's own monitor: never listed
        F.make_script(os.path.join(self.mods, 'SpeedKit_Monitor.ts4script'), ['speedkit_monitor/__init__.pyc'], old)

    def tearDown(self):
        api.reset()
        F.cleanup(self.root)

    def exists(self, *parts):
        return os.path.exists(os.path.join(self.sims, *parts))

    def manifest(self):
        with open(os.path.join(self.parked, '_manifest.json'), encoding='utf-8') as f:
            return json.load(f)


class Detection(Base):
    def test_version_file_with_header_bytes(self):
        self.assertEqual(PD.read_version_file(os.path.join(self.sims, 'GameVersion.txt')), '1.118.242.1030')
        self.assertIsNone(PD.read_version_file(os.path.join(self.sims, 'missing.txt')))

    def test_first_look_remembers_then_an_update_is_noticed(self):
        st = PD.check(self.sims, self.home, self.game)
        self.assertTrue(st['first_look'])
        self.assertFalse(st['updated'])
        self.assertEqual(st['version'], '1.118.242.1030')
        self.assertAlmostEqual(st['update_time'], self.t_patch, delta=2)
        self.assertFalse(PD.check(self.sims, self.home, self.game)['updated'])
        # the patch lands: a new exe (the game has not started yet, so GameVersion.txt is still the old one)
        t2 = F.now() - 3600
        F.make_game(self.root, t2, size=2000)
        st = PD.check(self.sims, self.home, self.game)
        self.assertTrue(st['updated'])
        self.assertAlmostEqual(st['update_time'], t2, delta=2)
        self.assertEqual(st['previous'], '1.118.242.1030')
        # first start after the patch writes the new version: no second notice, the version is updated
        F.write_version(self.sims, '1.119.109.1020')
        st = PD.check(self.sims, self.home, self.game)
        self.assertEqual(st['version'], '1.119.109.1020')
        self.assertTrue(st['updated'])
        self.assertTrue(PD.acknowledge(self.sims, self.home))
        self.assertFalse(PD.check(self.sims, self.home, self.game)['updated'])
        with open(os.path.join(self.home, PD.STATE), encoding='utf-8') as f:
            self.assertEqual(len(json.load(f)['history']), 1)

    def test_steam_manifest(self):
        common = os.path.join(self.root, 'SteamLibrary', 'steamapps', 'common')
        game = os.path.join(common, 'The Sims 4')
        os.makedirs(os.path.join(game, 'Game', 'Bin'))
        with open(os.path.join(common, '..', 'appmanifest_1222670.acf'), 'w') as f:
            f.write('"AppState"\n{\n\t"appid"\t\t"1222670"\n\t"buildid"\t\t"19283746"\n\t"LastUpdated"\t\t"%d"\n}\n'
                    % int(self.t_patch))
        v = PD.game_version(self.sims, game)
        self.assertEqual(v['build'], '19283746')
        self.assertEqual(v['update_time'], int(self.t_patch))
        self.assertTrue(v['fingerprint'].startswith('steam-19283746'))

    def test_older_scripts_and_their_companions(self):
        r = PD.older_scripts(self.sims, self.t_patch)
        rels = [o['rel'] for o in r['older']]
        self.assertEqual(sorted(rels), ['MCCC/mc_cmd_center.ts4script', 'ui_cheats_extension.ts4script'])
        self.assertEqual(r['newer'], 1)
        mccc = next(o for o in r['older'] if o['rel'].startswith('MCCC'))
        self.assertEqual(mccc['mod'], 'MCCC')
        self.assertEqual(mccc['goes_with'], ['MCCC/mc_cmd_center.package'])     # not the CC hair
        self.assertGreaterEqual(mccc['days_before'], 39)
        ui = next(o for o in r['older'] if o['rel'].startswith('ui_'))
        self.assertEqual(ui['goes_with'], ['ui_cheats_extension.package'])

    def test_api_patch_day(self):
        r = api.patch_day()
        self.assertTrue(r['ok'], r)
        self.assertFalse(r['game']['updated'])
        self.assertEqual(len(r['older']), 2)
        self.assertIn('older than the latest game update', r['message'])
        F.make_game(self.root, F.now() - 60, size=3000)
        r = api.patch_day()
        self.assertTrue(r['game']['updated'])
        # now every script is older than the brand-new build, WickedWhims too
        self.assertEqual(len(r['older']), 3)
        self.assertIn('WickedWhims/TURBODRIVER_WickedWhims_Scripts.ts4script', [o['rel'] for o in r['older']])
        self.assertIn('was updated', r['message'])
        self.assertIn('does not prove a mod is broken', r['message'])
        self.assertTrue(api.patch_seen()['ok'])
        self.assertFalse(api.patch_day()['game']['updated'])


class SetAside(Base):
    def test_set_aside_and_undo(self):
        doc = {'moved': ['OldStuff/'], 'note': 'written by mods_switch.py'}
        os.makedirs(os.path.join(self.parked, 'OldStuff'))
        F.make_cc_package(os.path.join(self.parked, 'OldStuff', 'x.package'))
        with open(os.path.join(self.parked, '_manifest.json'), 'w', encoding='utf-8') as f:
            json.dump(doc, f, indent=1)
        r = api.set_aside(['MCCC/mc_cmd_center.ts4script'], why='error')
        self.assertTrue(r['ok'], r)
        self.assertEqual(sorted(r['moved']), ['MCCC/mc_cmd_center.package', 'MCCC/mc_cmd_center.ts4script'])
        self.assertFalse(self.exists('Mods', 'MCCC', 'mc_cmd_center.ts4script'))
        self.assertTrue(self.exists('Mods_parked', 'MCCC', 'mc_cmd_center.ts4script'))
        self.assertTrue(self.exists('Mods_parked', 'MCCC', 'mc_cmd_center.package'))
        self.assertTrue(self.exists('Mods', 'MCCC', 'some_hair.package'))
        m = self.manifest()
        self.assertEqual(m['note'], 'written by mods_switch.py')           # other keys kept
        self.assertEqual(m['moved'][0], 'OldStuff/')                       # the other tool's entry kept, in order
        self.assertIn('MCCC/mc_cmd_center.ts4script', m['moved'])
        self.assertTrue(PR.check_manifest(self.sims)['ok'])
        held = PD.read_held(self.sims, self.home)['held']
        self.assertEqual({h['rel'] for h in held}, set(r['moved']))
        self.assertEqual(held[0]['why'], 'error')
        # the change is on the Tools page and it is the next to undo
        st = api.status()
        top = st['journals'][0]
        self.assertEqual(top['kind'], 'aside')
        self.assertEqual(top['title'], 'Set mods aside until they are updated')
        self.assertTrue(top['next_undo'], top)
        u = api.undo_last()
        self.assertTrue(u['ok'], u)
        self.assertTrue(self.exists('Mods', 'MCCC', 'mc_cmd_center.ts4script'))
        self.assertTrue(self.exists('Mods', 'MCCC', 'mc_cmd_center.package'))
        self.assertFalse(self.exists('Mods_parked', 'MCCC'))                 # no empty folder left behind
        self.assertEqual(self.manifest(), doc)
        self.assertFalse(os.path.exists(os.path.join(self.home, 'set_aside.json')))

    def test_patch_day_backs_up_the_saves_first(self):
        F.make_save(self.sims, 0x14, 5000)
        r = api.set_aside(['ui_cheats_extension.ts4script'], why='patch')
        self.assertTrue(r['ok'], r)
        self.assertIn('backed up first', r['steps'][0]['message'])
        self.assertEqual(len(api.save_health()['backups']), 1)
        self.assertTrue(self.exists('Mods_parked', 'ui_cheats_extension.package'))

    def test_put_back_and_undo_it(self):
        api.set_aside(['MCCC/mc_cmd_center.ts4script'], why='error')
        r = api.put_back(['MCCC/mc_cmd_center.ts4script', 'MCCC/mc_cmd_center.package'])
        self.assertTrue(r['ok'], r)
        self.assertTrue(self.exists('Mods', 'MCCC', 'mc_cmd_center.ts4script'))
        self.assertFalse(self.exists('Mods_parked', 'MCCC'))
        self.assertEqual(PD.read_held(self.sims, self.home)['held'], [])
        self.assertEqual(self.manifest()['moved'], [])
        self.assertEqual(api.status()['journals'][0]['title'], 'Put mods back')
        self.assertTrue(api.undo_last()['ok'])
        self.assertTrue(self.exists('Mods_parked', 'MCCC', 'mc_cmd_center.ts4script'))
        self.assertEqual(len(PD.read_held(self.sims, self.home)['held']), 2)
        self.assertTrue(PR.check_manifest(self.sims)['ok'])

    def test_put_back_keeps_the_old_copy_when_an_update_is_in_mods(self):
        api.set_aside(['ui_cheats_extension.ts4script'], why='error')
        F.make_script(os.path.join(self.mods, 'ui_cheats_extension.ts4script'), ['ui_cheats/main.pyc'])
        held = {h['rel']: h['state'] for h in PD.held_status(self.sims, self.home)}
        self.assertEqual(held['ui_cheats_extension.ts4script'], 'updated')
        r = api.put_back(['ui_cheats_extension.ts4script'])
        self.assertFalse(r['ok'])
        self.assertIn('newer copy', r['message'])

    def test_every_mode_keeps_held_files_parked(self):
        api.set_aside(['MCCC/mc_cmd_center.ts4script'], why='patch')
        P = PR.Paths(self.sims, self.home)
        inv = PR.inventory(P)
        target, notes = PR.compute_target('full', inv, held=PR.held_keys(P))
        self.assertEqual(target['mccc/mc_cmd_center.ts4script'], 'P')
        self.assertEqual(target['mccc/some_hair.package'], 'M')
        self.assertTrue(any('set aside until it is updated' in n for n in notes))
        # the folders are recognised as 'All CC' although two files are parked
        self.assertEqual(PR.current(sims=self.sims, home=self.home, keep=['x/'])['profile'], 'full')
        # a real switch to 'full' (another file was parked by the other tool) keeps the held ones parked
        F.make_cc_package(os.path.join(self.parked, 'Other', 'y.package'))
        with open(os.path.join(self.parked, '_manifest.json'), 'r+', encoding='utf-8') as f:
            doc = json.load(f)
            doc['moved'].append('Other/')
            f.seek(0)
            f.truncate()
            json.dump(doc, f, indent=1)
        plan = PR.switch('full', dry_run=False, sims=self.sims, home=self.home, check_game=False, scan=False)
        self.assertTrue(plan['verified'], plan['warnings'])
        self.assertTrue(self.exists('Mods', 'Other', 'y.package'))
        self.assertTrue(self.exists('Mods_parked', 'MCCC', 'mc_cmd_center.ts4script'))
        self.assertEqual(sorted(self.manifest()['moved']), ['MCCC/mc_cmd_center.package', 'MCCC/mc_cmd_center.ts4script'])

    def test_refused_while_the_game_runs(self):
        api.configure(check_game=True)
        with mock.patch.object(L, 'game_running', return_value=True), \
                mock.patch.object(J, 'game_running', return_value=True):
            r = api.set_aside(['MCCC/mc_cmd_center.ts4script'], why='error')
            self.assertFalse(r['ok'])
            self.assertIn('running', r['message'])
            with self.assertRaises(PD.PatchError):
                PD.set_aside(['MCCC/mc_cmd_center.ts4script'], sims=self.sims, home=self.home, check_game=True)
        self.assertTrue(self.exists('Mods', 'MCCC', 'mc_cmd_center.ts4script'))
        self.assertFalse(os.path.exists(os.path.join(self.home, 'journal')) and
                         any('aside' in n for n in os.listdir(os.path.join(self.home, 'journal'))))

    def test_the_game_starting_half_way_rolls_back(self):
        calls = {'n': 0}

        def running():
            calls['n'] += 1
            return calls['n'] == 3           # the journal opens, the first file moves, then the game "starts"
        with mock.patch.object(L, 'game_running', return_value=False), \
                mock.patch.object(J, 'game_running', side_effect=running):
            with self.assertRaises(PD.PatchError) as cm:
                PD.set_aside(['MCCC/mc_cmd_center.ts4script'], sims=self.sims, home=self.home, check_game=True)
        self.assertIn('running', str(cm.exception))
        self.assertIn('put back as it was', str(cm.exception))
        self.assertGreaterEqual(calls['n'], 4)
        for rel in ('mc_cmd_center.ts4script', 'mc_cmd_center.package'):
            self.assertTrue(self.exists('Mods', 'MCCC', rel), rel)
        self.assertFalse(self.exists('Mods_parked', 'MCCC'))
        self.assertFalse(os.path.exists(os.path.join(self.home, 'set_aside.json')))

    def test_damaged_parking_list_and_bad_paths_refuse(self):
        os.makedirs(self.parked)
        with open(os.path.join(self.parked, '_manifest.json'), 'w') as f:
            f.write('{not json')
        r = api.set_aside(['MCCC/mc_cmd_center.ts4script'], why='error')
        self.assertFalse(r['ok'])
        self.assertTrue(self.exists('Mods', 'MCCC', 'mc_cmd_center.ts4script'))
        os.remove(os.path.join(self.parked, '_manifest.json'))
        for bad in ('../saves/Slot_00000001.save', 'C:/Windows/x.ts4script', 'SpeedKit_Monitor.ts4script', 'nope.ts4script'):
            r = api.set_aside([bad], why='error')
            self.assertFalse(r['ok'], bad)
        self.assertTrue(self.exists('Mods', 'SpeedKit_Monitor.ts4script'))


if __name__ == '__main__':
    unittest.main()
