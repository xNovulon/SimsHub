"""A save's own shortcut (speedkit/hub/saveshortcut.py, the /api/shortcut routes, launcher.play_save and
python -m speedkit.hub --play). Everything is written into temp folders (SIMS_HUB_DATA and the shortcut folders);
the Desktop, the game and the Mods folder are never touched, and no app or game is started."""
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.request
from unittest import mock

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, ROOT)
from speedkit.hub import __main__ as hubmain, desktop, launcher, saveshortcut as SC, server, stub_api  # noqa: E402

SLOT = 'Slot_00000018'


def _fake_lnk(lnk, slot, save_name, icon):
    with open(lnk, 'w', encoding='utf-8') as f:
        f.write('%s|%s|%s' % (slot, save_name, icon))


class Temp(unittest.TestCase):
    def setUp(self):
        # a short path: Windows shortcuts don't take very long ones
        self.tmp = tempfile.mkdtemp(prefix='nvsc_')
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.desk = os.path.join(self.tmp, 'Desktop')
        self.docs = os.path.join(self.tmp, 'Documents')
        self.other = os.path.join(self.tmp, 'Games')
        for d in (self.desk, self.docs, self.other):
            os.makedirs(d)
        env = mock.patch.dict(os.environ, {'SIMS_HUB_DATA': os.path.join(self.tmp, 'data')})
        env.start()
        self.addCleanup(env.stop)
        places = mock.patch.dict(SC._places, {'desktop': self.desk, 'documents': self.docs}, clear=True)
        places.start()
        self.addCleanup(places.stop)
        icon = mock.patch.object(SC, 'icon_for', lambda slot, name, browser=None: desktop.ICO)
        icon.start()
        self.addCleanup(icon.stop)


class Names(unittest.TestCase):
    def test_file_names(self):
        self.assertEqual(SC.file_name('My Saved Game 24', SLOT), 'Play My Saved Game 24')
        self.assertEqual(SC.file_name('a/b:c*?"<>|', SLOT), 'Play a b c')
        self.assertEqual(SC.file_name('  ...  ', SLOT), 'Play ' + SLOT)
        self.assertEqual(SC.file_name(None, SLOT), 'Play ' + SLOT)
        self.assertLessEqual(len(SC.file_name('x' * 300, SLOT)), 75)

    def test_slots(self):
        self.assertEqual(SC.check_slot(SLOT), SLOT)
        for bad in ('', 'Slot_1', '../Slot_00000018', 'Slot_0000001g', None, 7):
            with self.assertRaises(SC.ShortcutError):
                SC.check_slot(bad)


class MakeMove(Temp):
    def setUp(self):
        super().setUp()
        w = mock.patch.object(SC, '_write_lnk', _fake_lnk)
        w.start()
        self.addCleanup(w.stop)

    def test_made_on_the_desktop_by_default(self):
        r = SC.make(SLOT, 'My Saved Game 24')
        self.assertTrue(r['ok'])
        self.assertEqual(r['path'], os.path.join(self.desk, 'Play My Saved Game 24.lnk'))
        self.assertTrue(os.path.isfile(r['path']))
        self.assertEqual((r['place'], r['exists'], r['declined']), ('Desktop', True, False))
        self.assertEqual(r['message'], 'Your shortcut is on your Desktop.')

    def test_moved_where_the_user_picks(self):
        first = SC.make(SLOT, 'My Saved Game 24')['path']
        r = SC.make(SLOT, 'My Saved Game 24', self.other)
        self.assertFalse(os.path.exists(first))
        self.assertEqual(r['path'], os.path.join(self.other, 'Play My Saved Game 24.lnk'))
        self.assertEqual(r['message'], 'Your shortcut is in Games now.')
        self.assertEqual(SC.make(SLOT, 'My Saved Game 24', self.other)['message'], 'Your shortcut is already in Games.')
        self.assertEqual(SC.make(SLOT, 'x', self.docs)['message'], 'Your shortcut is in your Documents now.')

    def test_never_replaces_someone_elses_file(self):
        mine = os.path.join(self.desk, 'Play Wicked Nights.lnk')
        with open(mine, 'w') as f:
            f.write('not ours')
        r = SC.make(SLOT, 'Wicked Nights')
        self.assertEqual(os.path.basename(r['path']), 'Play Wicked Nights (2).lnk')
        with open(mine) as f:
            self.assertEqual(f.read(), 'not ours')

    def test_a_deleted_shortcut_counts_as_gone(self):
        path = SC.make(SLOT, 'A')['path']
        os.remove(path)
        info = SC.info(SLOT)
        self.assertEqual((info['exists'], info['path'], info['declined']), (False, None, False))
        self.assertTrue(SC.make(SLOT, 'A')['ok'])                  # made again

    def test_not_now_is_remembered_until_one_is_made(self):
        SC.decline(SLOT)
        self.assertTrue(SC.info(SLOT)['declined'])
        self.assertTrue(SC.all_info()['shortcuts'][SLOT]['declined'])
        SC.make(SLOT, 'A')
        self.assertFalse(SC.info(SLOT)['declined'])
        SC.decline(SLOT)                                          # a shortcut that exists stays
        self.assertTrue(SC.info(SLOT)['exists'])

    def test_bad_folders(self):
        for bad in (os.path.join(self.tmp, 'nope'), 'x' * 2000, 'C:\\a\x00b'):
            with self.assertRaises(SC.ShortcutError):
                SC.make(SLOT, 'A', bad)


@unittest.skipUnless(os.name == 'nt', 'Windows shortcuts')
class RealShortcut(Temp):
    def test_the_lnk_runs_the_hub_for_that_save(self):
        import subprocess
        r = SC.make(SLOT, 'My Saved Game 24', self.other)
        ps = ('$s=(New-Object -ComObject WScript.Shell).CreateShortcut("%s"); $s.TargetPath; $s.Arguments; '
              '$s.WorkingDirectory' % r['path'])
        out = subprocess.run(['powershell', '-NoProfile', '-Command', ps], capture_output=True, text=True,
                             timeout=60).stdout.splitlines()
        self.assertTrue(out[0].lower().endswith('pythonw.exe'), out)
        self.assertEqual(out[1], '-m speedkit.hub --play save:' + SLOT)
        self.assertEqual(os.path.normcase(out[2]), os.path.normcase(desktop.ROOT))


class Routes(Temp):
    def setUp(self):
        super().setUp()
        w = mock.patch.object(SC, '_write_lnk', _fake_lnk)
        w.start()
        self.addCleanup(w.stop)

    def serve(self, mode):
        httpd = server.make_server(0, api=stub_api, mode=mode, log_path=os.path.join(self.tmp, 'hub.log'))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        return 'http://127.0.0.1:%d/api/' % httpd.port

    def call(self, url, body=None):
        req = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(),
                                     headers={'Content-Type': 'application/json'} if body is not None else {})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as ex:
            return ex.code, json.loads(ex.read())

    def test_engine_mode_makes_moves_and_skips(self):
        base = self.serve('engine')
        code, r = self.call(base + 'shortcuts')
        self.assertEqual((code, r['shortcuts']), (200, {}))
        self.assertEqual([p['label'] for p in r['places']], ['Desktop', 'Documents'])
        code, r = self.call(base + 'shortcut', {'slot': SLOT, 'name': 'Wicked Nights'})
        self.assertEqual((code, r['ok'], r['place']), (200, True, 'Desktop'))
        code, r = self.call(base + 'shortcut', {'slot': SLOT, 'name': 'Wicked Nights', 'folder': self.other})
        self.assertTrue(r['ok'])
        self.assertEqual(os.path.dirname(r['path']), self.other)
        code, r = self.call(base + 'shortcut', {'slot': SLOT, 'name': 'Wicked Nights', 'folder': os.path.join(self.tmp, 'no')})
        self.assertEqual((code, r['ok']), (200, False))
        self.assertEqual(r['message'], "That folder doesn't exist.")
        code, r = self.call(base + 'shortcut/skip', {'slot': 'Slot_00000009'})
        self.assertTrue(r['ok'])
        code, r = self.call(base + 'shortcuts')
        self.assertTrue(r['shortcuts']['Slot_00000009']['declined'])
        self.assertTrue(r['shortcuts'][SLOT]['exists'])
        code, r = self.call(base + 'shortcut', {'slot': '../x'})
        self.assertEqual(code, 400)

    def test_example_data_writes_nothing(self):
        base = self.serve('stub')
        code, r = self.call(base + 'shortcut', {'slot': SLOT, 'name': 'Wicked Nights'})
        self.assertTrue(r['ok'])
        self.assertTrue(r['path'].endswith('\\Play Wicked Nights.lnk'))
        self.assertEqual(os.listdir(self.desk), [])
        self.assertFalse(os.path.exists(os.path.join(self.tmp, 'data')))
        code, r = self.call(base + 'shortcuts')
        self.assertTrue(r['shortcuts'][SLOT]['exists'])


class Launcher(unittest.TestCase):
    def test_play_flag_runs_play_save(self):
        with mock.patch.object(launcher, 'play_save', return_value=0) as ps:
            self.assertEqual(hubmain.main(['--play', 'save:' + SLOT]), 0)
        ps.assert_called_once_with(8766 if not os.environ.get('SIMS_HUB_PORT') else int(os.environ['SIMS_HUB_PORT']),
                                   'save:' + SLOT)

    def test_a_bad_target_is_refused_before_anything_starts(self):
        said = []
        with mock.patch.object(launcher, 'message', lambda t, error=True: said.append(t)), \
                mock.patch.object(launcher.subprocess, 'Popen') as popen:
            self.assertEqual(launcher.play_save(1, 'fast'), 2)
            self.assertEqual(launcher.play_save(1, 'save:../x'), 2)
        popen.assert_not_called()
        self.assertEqual(len(said), 2)

    def test_without_the_app_it_starts_the_task_on_the_running_hub(self):
        httpd = server.make_server(0, api=stub_api, mode='stub', log_path=os.path.join(tempfile.mkdtemp(), 'h.log'))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        said = []
        with mock.patch.dict(os.environ, {'SIMS_HUB_NO_APP': '1'}), \
                mock.patch.object(launcher, 'update_first', lambda port: None), \
                mock.patch.object(launcher, 'hub_windows', lambda: []), \
                mock.patch.object(launcher, 'open_window', lambda url, *a, **k: said.append(url)), \
                mock.patch.object(launcher, 'message', lambda t, error=True: said.append('MSG ' + t)):
            self.assertEqual(launcher.play_save(httpd.port, 'save:' + SLOT), 0)
        self.assertEqual(said, ['http://127.0.0.1:%d/#saves' % httpd.port])
        task = httpd.hub.task_view('current')
        self.assertEqual((task['action'], task['args']), ('play', {'target': 'save:' + SLOT}))


if __name__ == '__main__':
    unittest.main(verbosity=2)
