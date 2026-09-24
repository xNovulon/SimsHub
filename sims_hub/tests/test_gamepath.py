"""speedkit.gamepath (where is the game?) and the Hub's folder browser (api.browse / api.set_game_path), on fake
folders under E:\\speedkit_test\\gamepath. Each clue is tested with fakes; the one real read is a .lnk the test
writes itself. Nothing is launched; the fake TS4_x64.exe files are empty."""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from speedkit import gamepath as G  # noqa: E402
from speedkit import api  # noqa: E402

BASE = r'E:\speedkit_test\gamepath'


def touch(path, data=b''):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data)
    return path


def fake_game(root, name='The Sims 4'):
    """<root>\\<name>\\Game\\Bin\\TS4_x64.exe (+ TS4.exe launcher at the top)."""
    gd = os.path.join(root, name)
    exe = touch(os.path.join(gd, 'Game', 'Bin', 'TS4_x64.exe'))
    touch(os.path.join(gd, 'TS4.exe'))
    return gd, exe


def no_clues(**kw):
    base = dict(processes=lambda: [], shortcuts=lambda: [], resolve=lambda paths: {}, registry=lambda: [],
                steam=lambda: None, drives=lambda: [])
    base.update(kw)
    return G.Clues(**base)


class Base(unittest.TestCase):
    def setUp(self):
        os.makedirs(BASE, exist_ok=True)
        self.root = tempfile.mkdtemp(dir=BASE)
        self.sims = os.path.join(self.root, 'sims')
        os.makedirs(self.sims)
        self.home = os.path.join(self.sims, 'SpeedKit')
        G._CACHE.clear()

    def tearDown(self):
        G._CACHE.clear()
        shutil.rmtree(self.root, onerror=lambda f, p, e: (os.chmod(p, stat.S_IWRITE), f(p)))


class Shapes(Base):
    def test_every_accepted_shape(self):
        gd, exe = fake_game(self.root)
        for shape in (gd, os.path.join(gd, 'Game'), os.path.join(gd, 'Game', 'Bin'), exe,
                      os.path.join(gd, 'TS4.exe'), '"%s"' % gd, gd + '\\'):
            self.assertEqual(os.path.normcase(G.normalise(shape)), os.path.normcase(exe), shape)
        loose = touch(os.path.join(self.root, 'loose', 'TS4_x64.exe'))
        self.assertEqual(G.normalise(os.path.dirname(loose)), loose)          # a folder holding the exe
        self.assertIsNone(G.normalise(self.root))
        self.assertIsNone(G.normalise(os.path.join(self.root, 'nope')))
        self.assertIsNone(G.normalise(''))
        self.assertEqual(os.path.normcase(G.game_dir_of(exe)), os.path.normcase(gd))
        self.assertTrue(G.is_game_folder(os.path.join(gd, 'Game')))

    def test_store(self):
        steam = touch(os.path.join(self.root, 'lib', 'steamapps', 'common', 'The Sims 4', 'Game', 'Bin', 'TS4_x64.exe'))
        self.assertEqual(G.store_of(steam), 'steam')
        gd, exe = fake_game(self.root, 'EA')
        self.assertEqual(G.store_of(exe), 'unknown')
        os.makedirs(os.path.join(gd, '__Installer'))
        self.assertEqual(G.store_of(exe), 'ea')
        self.assertEqual(G.store_of(exe, 'registry (Maxis)'), 'ea')


class Clues(Base):
    def test_order_and_each_step(self):
        gd1, exe1 = fake_game(self.root, 'proc')
        gd2, exe2 = fake_game(self.root, 'lnk')
        gd3, exe3 = fake_game(self.root, 'reg')
        gd5, exe5 = fake_game(os.path.join(self.root, 'D'), 'The Sims 4')
        steam_root = os.path.join(self.root, 'Steam')
        lib2 = os.path.join(self.root, 'Lib2')
        s_exe = touch(os.path.join(lib2, 'steamapps', 'common', 'The Sims 4', 'Game', 'Bin', 'TS4_x64.exe'))
        touch(os.path.join(steam_root, 'steamapps', 'libraryfolders.vdf'),
              ('"libraryfolders"\n{\n "0" { "path" "%s" }\n "1" { "path" "%s" }\n}\n'
               % (steam_root.replace('\\', '\\\\'), lib2.replace('\\', '\\\\'))).encode())
        lnk = os.path.join(self.root, 'The Sims 4.lnk')
        # 2. running process
        c = no_clues(processes=lambda: [exe1])
        self.assertEqual(G.search(c)[0]['source'], 'running game')
        # 3. shortcut: TS4_x64.exe target, and TS4.exe with Game\Bin next to it
        c = no_clues(shortcuts=lambda: [lnk], resolve=lambda ps: {lnk: exe2})
        self.assertEqual(os.path.normcase(G.search(c)[0]['exe']), os.path.normcase(exe2))
        c = no_clues(shortcuts=lambda: [lnk], resolve=lambda ps: {lnk: os.path.join(gd2, 'TS4.exe')})
        self.assertEqual(os.path.normcase(G.search(c)[0]['exe']), os.path.normcase(exe2))
        self.assertTrue(G.search(c)[0]['source'].startswith('shortcut'))
        # 4. registry
        c = no_clues(registry=lambda: [('registry (Maxis)', gd3)])
        r = G.search(c)[0]
        self.assertEqual((os.path.normcase(r['exe']), r['store']), (os.path.normcase(exe3), 'ea'))
        # 5. Steam libraries
        c = no_clues(steam=lambda: steam_root)
        r = G.search(c)[0]
        self.assertEqual((os.path.normcase(r['exe']), r['store']), (os.path.normcase(s_exe), 'steam'))
        # 6. common folders on the fixed drives
        c = no_clues(drives=lambda: [os.path.join(self.root, 'D') + '\\'])
        self.assertEqual(os.path.normcase(G.search(c)[0]['exe']), os.path.normcase(exe5))
        # the order: a running game wins over everything else; all candidates, deduplicated
        c = no_clues(processes=lambda: [exe1, exe1], registry=lambda: [('registry (Maxis)', gd3)],
                     drives=lambda: [os.path.join(self.root, 'D') + '\\'])
        self.assertEqual(G.search(c)[0]['source'], 'running game')
        self.assertEqual(len(G.search(c, first_only=False)), 3)
        # a clue that points at nothing (no exe there) is skipped; a clue that raises is skipped
        c = no_clues(processes=lambda: [os.path.join(self.root, 'gone', 'TS4_x64.exe')],
                     registry=lambda: (_ for _ in ()).throw(OSError('no registry')),
                     drives=lambda: [os.path.join(self.root, 'D') + '\\'])
        self.assertEqual(os.path.normcase(G.search(c)[0]['exe']), os.path.normcase(exe5))
        self.assertEqual(G.search(no_clues()), [])

    def test_studio_shortcuts_are_ignored(self):
        d = os.path.join(self.root, 'Desktop')
        touch(os.path.join(d, 'The Sims 4.lnk'))
        touch(os.path.join(d, 'Sims 4 Studio.lnk'))
        touch(os.path.join(d, 'Other.lnk'))
        found = [os.path.basename(p) for p in G.find_shortcuts([d])]
        self.assertEqual(found, ['The Sims 4.lnk'])

    @unittest.skipUnless(os.name == 'nt', 'Windows shortcuts')
    def test_real_shortcut_is_resolved(self):
        gd, exe = fake_game(self.root)
        lnk = os.path.join(self.root, 'Desktop', 'The Sims 4.lnk')
        os.makedirs(os.path.dirname(lnk))
        ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%s'); $s.TargetPath='%s'; $s.Save()"
              % (lnk.replace("'", "''"), exe.replace("'", "''")))
        subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', ps], capture_output=True,
                       timeout=60, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if not os.path.exists(lnk):
            self.skipTest('could not create a shortcut')
        self.assertEqual(os.path.normcase(G.resolve_shortcuts([lnk])[lnk]), os.path.normcase(exe))
        self.assertEqual(os.path.normcase(G.lnk_target(lnk)), os.path.normcase(exe))       # the pure-Python reader
        c = G.Clues(processes=lambda: [], shortcuts=lambda: G.find_shortcuts([os.path.dirname(lnk)]),
                    registry=lambda: [], steam=lambda: None, drives=lambda: [])
        self.assertEqual(os.path.normcase(G.search(c)[0]['exe']), os.path.normcase(exe))


class Remembered(Base):
    def test_user_choice_is_saved_and_wins(self):
        gd, exe = fake_game(self.root, 'mine')
        gd2, exe2 = fake_game(self.root, 'other')
        c = no_clues(processes=lambda: [exe2])
        r = G.set_game_path(os.path.join(gd, 'Game'), self.sims, self.home)
        self.assertTrue(r['ok'])
        with open(os.path.join(self.home, 'settings.json'), encoding='utf-8') as f:
            doc = json.load(f)
        self.assertEqual(os.path.normcase(doc['game_exe']), os.path.normcase(exe))
        self.assertIn('saved', doc)
        g = G.locate_game(self.sims, self.home, c, use_cache=False)
        self.assertTrue(g['found'] and g['saved'])
        self.assertEqual(os.path.normcase(g['exe']), os.path.normcase(exe))
        self.assertEqual(g['source'], 'your choice')
        # the chosen folder disappears (drive letter changed): not found, and it says so - no silent fallback
        shutil.rmtree(gd)
        g = G.locate_game(self.sims, self.home, c, use_cache=False)
        self.assertFalse(g['found'])
        self.assertTrue(g['saved'])
        self.assertIn('no longer at', g['message'])
        self.assertIsNone(G.find_game(self.sims, self.home, c, use_cache=False))
        bad = G.set_game_path(self.root, self.sims, self.home)
        self.assertFalse(bad['ok'])
        self.assertIn('does not hold The Sims 4', bad['message'])

    def test_running_game_is_remembered(self):
        gd, exe = fake_game(self.root)
        c = no_clues(processes=lambda: [exe])
        g = G.locate_game(self.sims, self.home, c, remember=True, use_cache=False)
        self.assertEqual(g['source'], 'running game')
        self.assertFalse(g['saved'])
        self.assertEqual(os.path.normcase(G.read_settings(self.sims, self.home)['auto_exe']), os.path.normcase(exe))
        g = G.locate_game(self.sims, self.home, no_clues(), use_cache=False)       # the game is closed now
        self.assertTrue(g['found'])
        self.assertEqual(g['source'], 'running game')
        # remember=False writes nothing
        home2 = os.path.join(self.root, 'home2')
        G.locate_game(self.sims, home2, c, remember=False, use_cache=False)
        self.assertFalse(os.path.exists(os.path.join(home2, 'settings.json')))
        # a remembered path that went away: searched again
        shutil.rmtree(gd)
        self.assertFalse(G.locate_game(self.sims, self.home, no_clues(), use_cache=False)['found'])


class Browse(Base):
    def setUp(self):
        super().setUp()
        self.gd, self.exe = fake_game(self.root)
        drive = os.path.join(self.root, 'drive')
        os.makedirs(os.path.join(drive, 'Games', 'Stuff'))
        os.makedirs(os.path.join(drive, 'SteamLibrary', 'steamapps', 'common'))
        os.makedirs(os.path.join(drive, 'EA Games'))
        os.makedirs(os.path.join(drive, '$Recycle.Bin'))
        hidden = os.path.join(drive, 'HiddenOne')
        os.makedirs(hidden)
        subprocess.run(['attrib', '+h', hidden], capture_output=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        touch(os.path.join(drive, 'a file.txt'))
        self.drive = drive
        api.configure(sims=self.sims, home=self.home, db_path=os.path.join(self.root, 'lib.sqlite'), processes=False,
                      check_game=False, game_clues=no_clues(processes=lambda: [self.exe],
                                                            drives=lambda: [drive + '\\']))

    def tearDown(self):
        api.reset()
        super().tearDown()

    def test_this_pc_and_one_level(self):
        r = api.browse()
        self.assertTrue(r['ok'])
        self.assertIsNone(r['path'])
        self.assertEqual([d['name'] for d in r['drives']], [self.drive])
        self.assertEqual(len(r['entries']), 1)
        self.assertEqual([os.path.normcase(s['exe']) for s in r['suggestions']], [os.path.normcase(self.exe)])
        r = api.browse(self.drive)
        names = [e['name'] for e in r['entries']]
        self.assertEqual(names, ['EA Games', 'Games', 'SteamLibrary'])          # sorted, folders only
        self.assertNotIn('HiddenOne', names)
        self.assertNotIn('$Recycle.Bin', names)
        hints = {e['name']: e['hint'] for e in r['entries']}
        self.assertEqual(hints['EA Games'], 'EA games folder')
        self.assertEqual(hints['SteamLibrary'], 'Steam')
        r2 = api.browse(os.path.join(self.drive, 'SteamLibrary', 'steamapps'))
        self.assertEqual(r2['entries'][0]['hint'], 'Steam library')
        self.assertEqual(os.path.normcase(r2['parent']), os.path.normcase(os.path.join(self.drive, 'SteamLibrary')))
        r = api.browse(self.root)
        game = [e for e in r['entries'] if e['name'] == 'The Sims 4'][0]
        self.assertTrue(game['is_game'])
        self.assertEqual(game['hint'], 'Looks like The Sims 4')
        self.assertTrue(api.browse(os.path.join(self.gd, 'Game', 'Bin'))['is_game'])
        self.assertFalse(api.browse(os.path.join(self.root, 'nope'))['ok'])

    @unittest.skipUnless(os.name == 'nt', 'Windows ACLs')
    def test_access_denied_folder_is_skipped(self):
        locked = os.path.join(self.drive, 'Locked')
        os.makedirs(locked)
        user = os.environ.get('USERNAME')
        r = subprocess.run(['icacls', locked, '/deny', '%s:(RD)' % user], capture_output=True,
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            if r.returncode != 0:
                self.skipTest('could not lock a folder')
            names = [e['name'] for e in api.browse(self.drive)['entries']]
            self.assertNotIn('Locked', names)
            self.assertIn('Games', names)
            self.assertFalse(api.browse(locked)['ok'])
        finally:
            subprocess.run(['icacls', locked, '/remove:d', user], capture_output=True,
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))

    def test_set_game_path_and_status(self):
        for shape in (self.gd, os.path.join(self.gd, 'Game'), os.path.join(self.gd, 'Game', 'Bin'), self.exe):
            r = api.set_game_path(shape)
            self.assertTrue(r['ok'], shape)
            self.assertEqual(os.path.normcase(r['exe']), os.path.normcase(self.exe))
            self.assertEqual(os.path.normcase(r['game_dir']), os.path.normcase(self.gd))
        self.assertFalse(api.set_game_path(self.drive)['ok'])
        g = api.status()['game']
        self.assertTrue(g['found'] and g['saved'])
        self.assertEqual(g['source'], 'your choice')
        shutil.rmtree(self.gd)
        G._CACHE.clear()
        api.configure(game_clues=no_clues())
        g = api.status()['game']
        self.assertFalse(g['found'])
        self.assertIn('no longer at', g['message'])
        self.assertEqual(os.path.normcase(g['lost_path']), os.path.normcase(self.gd))


if __name__ == '__main__':
    unittest.main()
