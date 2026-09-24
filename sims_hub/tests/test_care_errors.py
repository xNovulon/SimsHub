"""Which mod caused this error? (speedkit/errorlogs.py through speedkit/api.py): the game's lastException /
lastUIException reports, MC Command Center's and Better Exceptions' reports, mapped to the mod files installed,
grouped, with odd files handled gracefully. Cross-platform: a fake Sims 4 folder in a temp folder."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from speedkit import api, errorlogs as EL  # noqa: E402
from tests import care_fakes as F  # noqa: E402


class Errors(unittest.TestCase):
    def setUp(self):
        self.root, self.sims = F.make_sims()
        self.mods = os.path.join(self.sims, 'Mods')
        api.configure(sims=self.sims, db_path=os.path.join(self.root, 'library.sqlite'), check_game=False,
                      game={'exe': None, 'game_dir': None, 'store': 'ea', 'source': 'test'})
        F.make_script(os.path.join(self.mods, 'MCCC', 'mc_cmd_center.ts4script'),
                      ['mc_cmd_center/__init__.pyc', 'mc_cmd_center/mc_utils/__init__.pyc',
                       'mc_cmd_center/mc_utils/mc_zone.pyc'])
        F.make_script(os.path.join(self.mods, 'Kuttoe', 'kuttoe_tweaks.ts4script'), ['kuttoe/tweaks.pyc'])
        F.make_script(os.path.join(self.mods, 'UI Cheats', 'weerbesu_ui_cheats.ts4script'), ['ui_cheats/main.pyc'])
        F.make_script(os.path.join(self.mods, 'WickedWhims', 'TURBODRIVER_WickedWhims_Scripts.ts4script'),
                      ['wickedwhims/main.pyc'])
        # set aside by another tool: it can be named, not set aside again
        F.make_script(os.path.join(self.sims, 'Mods_parked', 'LMS', 'lms_firstlove.ts4script'),
                      ['firstlove/__init__.pyc', 'firstlove/save_hook.pyc'])
        F.write_last_exception(self.sims)
        F.write_last_ui_exception(self.sims)
        F.write_mccc_html(os.path.join(self.mods, 'MCCC'))
        F.write_be_report(self.sims)
        with open(os.path.join(self.sims, 'lastException_2.txt'), 'wb') as f:
            f.write(b'\x00\x01garbage that is no report at all \xff\xfe')

    def tearDown(self):
        api.reset()
        F.cleanup(self.root)

    def group(self, rep, pred):
        found = [g for g in rep['errors'] if pred(g)]
        self.assertEqual(len(found), 1, [(g['error'], g['mod']) for g in rep['errors']])
        return found[0]

    def test_report_files_are_found(self):
        kinds = sorted((os.path.basename(p), k) for p, k in EL.report_files(self.sims))
        self.assertEqual(kinds, [('BetterExceptions_Report_2026-06-14_11-20-00.html', 'be'),
                                 ('lastException.txt', 'script'), ('lastException_2.txt', 'script'),
                                 ('lastUIException.txt', 'ui'), ('mc_lastexception.html', 'mccc')])

    def test_parse_the_game_xml(self):
        reps = EL.parse_file(os.path.join(self.sims, 'lastException.txt'), 'script')
        self.assertEqual(len(reps), 4)
        self.assertEqual(reps[0]['when'], '2026-06-12T20:31:45')
        self.assertEqual(reps[0]['category'], 'mc_cmd_center\\mc_utils\\mc_zone.py:188')
        self.assertIn('Traceback (most recent call last):\n  File "T:\\InGame', reps[0]['text'])
        self.assertTrue(reps[0]['build'].startswith('Local.Unknown'))

    def test_mods_are_named_and_repeats_grouped(self):
        rep = EL.scan(self.sims)
        # MCCC: the module path of its own traceback lines (compiled on the author's PC), twice in lastException
        # and once more in MCCC's own HTML copy - one group
        g = self.group(rep, lambda g: g['mod'] and g['mod']['file'] == 'mc_cmd_center.ts4script')
        self.assertEqual(g['count'], 3)
        self.assertEqual(g['how'], 'named')
        self.assertEqual(g['mod']['name'], 'MCCC')
        self.assertEqual(g['mod']['rel'], 'MCCC/mc_cmd_center.ts4script')
        self.assertTrue(g['mod']['can_set_aside'])
        self.assertEqual(g['error'], "AttributeError: 'NoneType' object has no attribute 'household_id'")
        self.assertEqual(g['first'], '2026-06-12T20:31:45')
        self.assertEqual(sorted(g['files']), ['lastException.txt', 'mc_lastexception.html'])
        self.assertIn('mc_zone.py', g['details'])
        # the path runs through the .ts4script: named although EA's code is innermost
        g = self.group(rep, lambda g: g['mod'] and g['mod']['file'] == 'kuttoe_tweaks.ts4script')
        self.assertEqual(g['error'], 'KeyError: 4231')
        self.assertEqual(g['where'], 'tweaks.py:wrapped')
        # only the game's own code: no mod is blamed
        g = self.group(rep, lambda g: g['error'].startswith('TypeError'))
        self.assertIsNone(g['mod'])
        # a menu error: no traceback, the mod file name written in it
        g = self.group(rep, lambda g: g['kind'] == 'ui')
        self.assertEqual(g['how'], 'mentioned')
        self.assertEqual(g['mod']['file'], 'weerbesu_ui_cheats.ts4script')
        self.assertIn('Error #1009', g['error'])
        # Better Exceptions' report: the mod is found, but it is already set aside (in Mods_parked)
        g = self.group(rep, lambda g: g['source'] == 'be')
        self.assertEqual(g['mod']['file'], 'lms_firstlove.ts4script')
        self.assertFalse(g['mod']['can_set_aside'])
        # the garbage file is listed, not a crash
        g = self.group(rep, lambda g: g['files'] == ['lastException_2.txt'])
        self.assertEqual(g['kind'], 'other')
        self.assertIsNone(g['mod'])
        self.assertEqual(rep['unreadable'], [])
        self.assertEqual(rep['errors'][0]['last'], max(x['last'] for x in rep['errors']))

    def test_api_and_seen(self):
        r = api.game_errors()
        self.assertTrue(r['ok'], r)
        self.assertTrue(all(g['new'] for g in r['errors']))
        self.assertIn('pointing at a mod', r['message'])
        self.assertTrue(api.errors_seen()['ok'])
        r = api.game_errors()
        self.assertFalse(any(g['new'] for g in r['errors']))
        self.assertEqual(r['message'], 'No new errors since the last review.')
        # set the mod aside from its error, then the error says so
        api.set_aside(['MCCC/mc_cmd_center.ts4script'], why='error')
        r = api.game_errors()
        g = next(g for g in r['errors'] if g['mod'] and g['mod']['file'] == 'mc_cmd_center.ts4script')
        self.assertTrue(g['set_aside'])
        self.assertFalse(g['mod']['can_set_aside'])

    def test_no_reports(self):
        for n in os.listdir(self.sims):
            if n.startswith('last'):
                os.remove(os.path.join(self.sims, n))
        os.remove(os.path.join(self.mods, 'MCCC', 'mc_lastexception.html'))
        import shutil
        shutil.rmtree(os.path.join(self.sims, 'BetterExceptions'))
        r = api.game_errors()
        self.assertEqual(r['errors'], [])
        self.assertEqual(r['message'], 'No error reports found.')

    def test_frame_paths(self):
        idx = EL.ModIndex({'Mods': self.mods})
        f, how = EL._frame_file(r'C:\Users\x\Documents\Electronic Arts\The Sims 4\Mods\WickedWhims\TURBODRIVER_WickedWhims_Scripts.ts4script\wickedwhims\main.py', idx)
        self.assertEqual((f['name'], how), ('TURBODRIVER_WickedWhims_Scripts.ts4script', 'script path'))
        f, how = EL._frame_file('/home/modder/build/wickedwhims/main.py', idx)
        self.assertEqual(how, 'module')
        self.assertEqual(EL._frame_file(r'T:\InGame\Gameplay\Scripts\Server\wickedwhims\main.py', idx), (None, None))
        self.assertEqual(EL._frame_file(r'D:\somewhere\unknown\thing.py', idx), (None, None))


if __name__ == '__main__':
    unittest.main()
