"""Screenshot smoke test of every Hub page, against the example-data stub, in headless Chrome.

Chrome runs offline (every request except 127.0.0.1 goes to a dead proxy), so this also proves the page
works without the internet (the Plus Jakarta Sans web font fails and Segoe UI is used). Each page is loaded once with --dump-dom to
check what it shows, and screenshotted to tests/_hub_screens/ (or SIMS_HUB_SCREENS) for a person to look at.

Skipped when Chrome is not installed. Run just this file:  python -m unittest discover -s tests -p "test_hub_screens.py"
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from speedkit.hub import server, stub_api  # noqa: E402

CHROME = next((p for p in (
    r'C:\Program Files\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
    os.path.expandvars(r'%LocalAppData%\Google\Chrome\Application\chrome.exe'),
    r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe') if os.path.isfile(p)), None)
OUT = os.environ.get('SIMS_HUB_SCREENS') or os.path.join(os.path.dirname(os.path.abspath(__file__)), '_hub_screens')

# (name, url, window size, what the page must show)
PAGES = [
    ('home', '/#home', (1440, 1000), ['Start The Sims 4', 'Quick Start', 'Full Start', 'Chrome is using 20 GB', '755,662',
                                    'Loading a lot took 22 s']),
    ('home_1280x720', '/#home', (1280, 720), ['Quick Start']),
    ('saves', '/#saves', (1440, 1000), ['Wicked Nights', '12,480 CC items', 'Play this save', 'Novulon · Del Sol Valley']),
    ('saves_1100x700', '/#saves', (1100, 700), ['Legacy Challenge']),
    ('library', '/#library', (1440, 1200), ['Add new downloads', 'Sentate_Venus_Dress.package', 'Free up space', 'Library report', 'Inbox']),
    ('performance', '/#performance', (1440, 2000), ['How far away sims keep full detail', 'speedkit.lag', 'faster', 'Graphics']),
    ('tools', '/#tools', (1440, 1250), ["Open Novulon's Wicked Animator", 'Undo last change', 'Switched to Full Start', 'E:\\The Sims 4',
                                         'Added 3 new downloads', 'Installed the SpeedKit Monitor', 'Removed extra copies of CC']),
    ('tools_900x800', '/#tools', (900, 800), ['Recent changes']),
    ('finder', '/?open=finder#home', (1440, 1000), ['Find The Sims 4', 'Found on this PC', 'Use this', 'Games (E:)', '402 GB free']),
    ('finder_folder', '/?open=finder&path=E%3A%5C#home', (1440, 1000), ['SteamLibrary', 'Steam', 'Select']),
    ('finder_game_folder', '/?open=finder&path=E%3A%5CThe%20Sims%204#home', (1440, 1000), ['This folder is The Sims 4', 'Game', 'Data']),
    ('confirm_undo', '/?open=undo#tools', (1440, 1000), ['Undo the last change?', 'Switched to Full Start', 'Keep it']),
    ('confirm_cleanup', '/?open=cleanup#library', (1440, 1000), ['Free up 18.2 GB?', '4,210']),
]
# pages that need the example data changed first: name -> (url, size, must show, setup(state))
SPECIAL = {
    'home_game_running': ('/#home', (1440, 1000), ['The Sims 4 is running'], lambda s: s.update(game_running=True)),
    # the game block exactly as speedkit/api.py status() gives it when the game is missing / was moved
    'home_game_missing': ('/#home', (1440, 1000), ["wasn't found on this PC", 'Locate The Sims 4'],
                          lambda s: s.update(game={'found': False, 'exe': None, 'game_dir': None, 'store': None, 'source': None,
                                                   'saved': False, 'message': "The Sims 4 wasn't found on this PC. Click 'Locate "
                                                                              "The Sims 4' and select its folder."})),
    'home_game_moved': ('/#home', (1440, 1000), ['The game is no longer at', 'D:\\Games\\The Sims 4'],
                        lambda s: s.update(game={'found': False, 'exe': None, 'game_dir': None, 'store': None, 'source': 'your choice',
                                                 'saved': True, 'message': "The game is no longer at D:\\Games\\The Sims 4. Click "
                                                                           "'Locate The Sims 4' and select its folder."})),
    'tools_game_moved': ('/#tools', (1440, 1000), ['The game is no longer at', 'Locate The Sims 4'],
                         lambda s: s.update(game={'found': False, 'exe': None, 'game_dir': None, 'store': None, 'source': 'your choice',
                                                  'saved': True, 'message': "The game is no longer at D:\\Games\\The Sims 4. Click "
                                                                            "'Locate The Sims 4' and select its folder."})),
    'home_fresh_install': ('/#home', (1440, 1000), ['Not timed yet', 'Max Quality, lag fixed'],
                           lambda s: s.update(load_times=[], journals=[], graphics={'state': 'tuned', 'label': 'SpeedKit Max Quality - '
                                                                                    'sharp graphics without the lag',
                                                                                    'can_tune': False, 'details': []},
                                              memory={'free_gb': 22.4, 'total_gb': 31.3, 'warnings': [], 'top': []})),
    'tools_empty': ('/#tools', (1440, 1000), ['No changes yet'], lambda s: s.update(journals=[])),
    'saves_empty': ('/#saves', (1440, 800), ['No saves yet'], lambda s: s.update(saves=[])),
}


def chrome(url, size, extra, budget=6000, online=False):
    prof = tempfile.mkdtemp(prefix='hubshot_')
    try:
        args = [CHROME, '--headless=new', '--disable-gpu', '--hide-scrollbars', '--no-first-run', '--no-default-browser-check',
                '--disable-extensions', '--mute-audio', '--user-data-dir=' + prof, '--window-size=%d,%d' % size,
                '--virtual-time-budget=%d' % budget, '--enable-logging=stderr', '--v=0']
        if not online:     # Chrome never sends loopback through a proxy, so only the internet is cut off
            args.append('--proxy-server=http://127.0.0.1:9')
        args += extra + [url]
        p = subprocess.run(args, capture_output=True, timeout=120)
        return p.stdout.decode('utf-8', 'replace'), p.stderr.decode('utf-8', 'replace')
    finally:
        shutil.rmtree(prof, ignore_errors=True)


def page_errors(stderr):
    return [ln for ln in stderr.splitlines() if 'CONSOLE' in ln and re.search(r'Uncaught|TypeError|ReferenceError|SyntaxError', ln)]


@unittest.skipUnless(CHROME, 'Chrome/Edge is not installed')
class HubScreens(unittest.TestCase):
    def setUp(self):
        stub_api.reset()
        stub_api.DELAY = 0
        stub_api.HOLD = None
        self.httpd = server.make_server(0, api=stub_api, log_path=os.path.join(tempfile.gettempdir(), 'hub_test.log'))
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = 'http://127.0.0.1:%d' % self.httpd.port
        os.makedirs(OUT, exist_ok=True)

    def tearDown(self):
        stub_api.HOLD = None
        self.httpd.shutdown()
        self.httpd.server_close()
        stub_api.reset()

    def check(self, name, path, size, must, online=False):
        """One Chrome run both dumps the page's DOM and screenshots it, so the picture is of the page that was
        checked. A page that is not there yet (slow machine) is tried again with more time."""
        png = os.path.join(OUT, name + '.png')
        for attempt, budget in enumerate((6000, 10000, 16000)):
            if os.path.exists(png):
                os.remove(png)
            dom, err = chrome(self.base + path, size, ['--dump-dom', '--screenshot=' + png], budget=budget, online=online)
            text = re.sub(r'<[^>]+>', ' ', dom)
            text = re.sub(r'\s+', ' ', text.replace('&amp;', '&').replace('&#39;', "'").replace('&quot;', '"'))
            if all(m in text for m in must):
                break
        for m in must:
            self.assertIn(m, text, '%s: the page should show %r' % (name, m))
        self.assertEqual(page_errors(err), [], name + ': script errors')
        self.assertTrue(os.path.isfile(png) and os.path.getsize(png) > 5000, name + ': no screenshot')
        # no jargon on any page
        # (the stub's change notes are as technical as the engine's: the page must turn them into plain words)
        for word in ('CASP', 'journal', 'Journal', '.package files', 'dedup', ' packages', 'policy', 'park ', 'merged files',
                     'thumbnail cache', 'RenderSim', 'Clip planes'):
            self.assertNotIn(word, text, '%s: shows the word %r' % (name, word))
        return text

    def test_pages(self):
        with ThreadPoolExecutor(4) as ex:
            futs = [ex.submit(self.check, *p) for p in PAGES]
            for f in futs:
                f.result()

    def test_with_web_font(self):
        # the same page when the internet is there (Plus Jakarta Sans); it must look right either way
        self.check('home_webfont', '/#home', (1440, 1000), ['Start The Sims 4'], online=True)

    def test_special_states(self):
        for name, (path, size, must, setup) in SPECIAL.items():
            with self.subTest(name):
                stub_api.reset()
                setup(stub_api.STATE)
                self.httpd.hub.forget()
                self.check(name, path, size, must)

    def test_cc_card_matches_mode(self):
        # the "CC items loaded" card describes the mode the Mods folder is in now (it once said "Only what your
        # sims and lots need." in Studio mode)
        said = {'full': 'Everything is loaded.', 'fast': 'Only what your sims and lots need.',
                'save': 'Only what this save needs.',
                'studio': 'Only WickedWhims and your animations - for animation work.',
                'custom': 'Changed by hand or by another tool.'}
        now = {'full': 755662, 'fast': 15905, 'save': 14102, 'studio': 167, 'custom': 90211}
        for mode, sentence in said.items():
            with self.subTest(mode):
                stub_api.reset()
                prof = {'name': mode, 'save_slot': 'Slot_00000014' if mode == 'save' else None,
                        'label': "Play this save - only the CC of 'Wicked Nights'" if mode == 'save' else mode}
                stub_api.STATE['profile'] = prof
                stub_api.STATE['library']['cas_now'] = now[mode]
                self.httpd.hub.forget()
                text = self.check('home_cc_' + mode, '/#home', (1440, 1000), [sentence, '{:,}'.format(now[mode])])
                for other, s in said.items():
                    if other != mode:
                        self.assertNotIn(s, text, '%s mode: the card says %r' % (mode, s))

    def test_task_overlays(self):
        hub = self.httpd.hub
        # a task caught in the middle: three steps done, the fourth waiting
        stub_api.HOLD, stub_api.HOLD_AT = threading.Event(), 3
        hub.start('play', {'target': 'fast'})
        try:
            self.check('task_running', '/#home', (1440, 1000), ['Starting Quick Start', 'Updating the SpeedKit Monitor'])
        finally:
            stub_api.HOLD.set()
        for _ in range(200):
            if hub.current is None:
                break
            threading.Event().wait(0.02)
        self.check('task_done', '/?open=last#home', (1440, 1000), ['All set', 'Chrome is using 20 GB', 'OK'])
        # a failure: there is nothing left to undo
        stub_api.STATE['journals'] = []
        hub.start('undo_last', {})
        for _ in range(200):
            if hub.current is None:
                break
            threading.Event().wait(0.02)
        self.check('task_failed', '/?open=last#tools', (1440, 1000), ["That didn't work", 'There is nothing to undo.'])


if __name__ == '__main__':
    unittest.main()
