"""The Hub's patch-day, game-error, save-backup and load-time sections in a real browser (Playwright + Chromium).

Starts the Hub in example-data mode exactly as a person would (python -m speedkit.hub --serve --stub --port <free
port>), opens Home, Saves and Tools, checks the new sections are drawn, presses their buttons and checks each one
calls the server (the requests are watched), and that the page logs no script errors. The internet is cut off
(only 127.0.0.1 is allowed), so the web font fails quietly as it does offline.

Skipped when Playwright or its Chromium is missing. Chromium is looked up in PLAYWRIGHT_BROWSERS_PATH (default
/opt/pw-browsers) when Playwright's own build number is not installed.
"""
import glob
import json
import os
import socket
import subprocess
import sys
import time
import unittest
import urllib.request

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')

try:
    from playwright.sync_api import sync_playwright
except ImportError:                                  # pragma: no cover
    sync_playwright = None


def _chromium():
    base = os.environ.get('PLAYWRIGHT_BROWSERS_PATH') or '/opt/pw-browsers'
    for pat in ('chromium-*/chrome-linux/chrome', 'chromium-*/chrome-linux64/chrome', 'chromium-*/chrome-win/chrome.exe'):
        found = sorted(glob.glob(os.path.join(base, pat)))
        if found:
            return found[-1]
    return None


def _free_port():
    while True:
        s = socket.socket()
        s.bind(('127.0.0.1', 0))
        port = s.getsockname()[1]
        s.close()
        if port not in (8765, 8766):
            return port


@unittest.skipUnless(sync_playwright is not None, 'Playwright is not installed')
class CareUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw = sync_playwright().start()
        try:
            try:
                cls.browser = cls.pw.chromium.launch()
            except Exception:
                exe = _chromium()
                if not exe:
                    raise unittest.SkipTest('no Chromium for Playwright')
                cls.browser = cls.pw.chromium.launch(executable_path=exe)
        except BaseException:
            cls.pw.stop()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def start_hub(self):
        """A fresh Hub (fresh example data) for every test, started the way a person would."""
        self.port = _free_port()
        env = dict(os.environ, SIMS_HUB_STUB_DELAY='0.02', PYTHONPATH=ROOT)
        self.proc = subprocess.Popen([sys.executable, '-m', 'speedkit.hub', '--serve', '--stub', '--port', str(self.port)],
                                     cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(self.stop_hub)
        self.base = 'http://127.0.0.1:%d/' % self.port
        for _ in range(150):
            try:
                with urllib.request.urlopen(self.base + 'api/ping', timeout=1) as r:
                    if json.loads(r.read()).get('engine') == 'stub':
                        return
            except Exception:
                time.sleep(0.1)
        raise RuntimeError('the Hub did not start')

    def stop_hub(self):
        self.proc.terminate()
        try:
            self.proc.wait(10)
        except subprocess.TimeoutExpired:
            self.proc.kill()

    def setUp(self):
        self.start_hub()
        self.page = self.browser.new_page(viewport={'width': 1440, 'height': 1100})
        self.errors, self.calls = [], []
        self.page.route('**/*', lambda route: route.continue_() if route.request.url.startswith(self.base)
                        else route.abort())
        self.page.on('pageerror', lambda e: self.errors.append(str(e)))
        self.page.on('console', lambda m: self.errors.append(m.text)
                     if m.type == 'error' and 'net::ERR_FAILED' not in m.text else None)
        self.page.on('request', self._request)

    def tearDown(self):
        self.page.close()
        self.assertEqual(self.errors, [], 'script errors on the page')

    def _request(self, req):
        if '/api/' in req.url:
            body = None
            if req.method == 'POST':
                try:
                    body = json.loads(req.post_data or '{}')
                except ValueError:
                    body = req.post_data
            self.calls.append((req.method, req.url.split('/api/', 1)[1], body))

    def tasks(self, action):
        return [b['args'] for m, path, b in self.calls if m == 'POST' and path == 'task' and b.get('action') == action]

    def open(self, page):
        self.page.goto(self.base + '#' + page)
        self.page.wait_for_selector('#page .page-head, #page .hello', timeout=15000)

    def finish_task(self, done_title):
        self.page.wait_for_selector('.task h2:has-text("%s")' % done_title, timeout=15000)
        self.page.click('.task [data-close]')
        self.page.wait_for_selector('.overlay', state='detached', timeout=5000)

    # ------------------------------------------------------------------------------------------ Home
    def test_home(self):
        self.open('home')
        p = self.page
        p.wait_for_selector('[data-care="patch-banner"]', timeout=10000)
        self.assertIn('The Sims 4 was updated', p.inner_text('[data-care="patch-banner"]'))
        self.assertIn('4 script mods are older than the latest game update', p.inner_text('[data-care="patch-banner"]'))
        self.assertIn('2 new game errors', p.inner_text('[data-care="errors-banner"]'))
        savings = p.inner_text('[data-care="savings"]')
        for words in ('How long the game takes to load', 'Quick Start', 'Full Start', 'about 6 min less per start than Full Start'):
            self.assertIn(words, savings)
        self.assertTrue(any(path.startswith('load_savings') for _, path, _ in self.calls))
        # "Dismiss" tells the server and the notice goes
        p.click('[data-act="care-patch-seen"]')
        p.wait_for_selector('[data-care="patch-banner"]', state='detached', timeout=5000)
        self.assertIn(('POST', 'patchday/seen', {}), self.calls)
        # "See which mod" leads to the Tools page's error list
        p.click('[data-care="errors-banner"] a')
        p.wait_for_selector('#care-errors', timeout=10000)

    # ------------------------------------------------------------------------------------------ Tools
    def test_tools_patch_day(self):
        self.open('tools')
        p = self.page
        p.wait_for_selector('#care-patch [data-care-pick]', timeout=10000)
        card = p.inner_text('#care-patch')
        for words in ('After a game update', 'MCCC', 'Kuttoe', "doesn't prove a mod is broken", 'SET ASIDE FOR NOW',
                      'Srsly Pack'):
            self.assertIn(words, card)
        self.assertEqual(p.locator('#care-patch [data-care-pick]').count(), 4)
        p.uncheck('[data-care-pick="Kuttoe/kuttoe_tweaks.ts4script"]')
        self.assertIn('(3)', p.inner_text('[data-act="care-aside"]'))
        p.click('[data-act="care-aside"]')
        p.wait_for_selector('.modal:has-text("Set 3 script mods aside?")')
        p.click('.modal [data-yes]')
        self.finish_task('Set aside')
        args = self.tasks('set_aside')
        self.assertEqual(len(args), 1)
        self.assertEqual(args[0]['why'], 'patch')
        self.assertNotIn('Kuttoe/kuttoe_tweaks.ts4script', args[0]['rels'])
        self.assertEqual(len(args[0]['rels']), 3)
        # the page asks again and shows them set aside, each with its own "Put back"
        p.wait_for_selector('#care-patch [data-act="care-back"][data-rel="MCCC/mc_cmd_center.ts4script"]', timeout=10000)
        p.click('#care-patch [data-act="care-back"][data-rel="MCCC/mc_cmd_center.ts4script"]')
        self.finish_task('Mods put back')
        self.assertEqual(self.tasks('put_back'), [{'rels': ['MCCC/mc_cmd_center.ts4script']}])
        # the change is in Recent changes, in plain words, and can be undone
        p.wait_for_selector('.change:has-text("Put mods back")', timeout=10000)
        self.assertTrue(p.is_enabled('[data-act="undo"]'))

    def test_tools_errors(self):
        self.open('tools')
        p = self.page
        p.wait_for_selector('#care-errors .care-error', timeout=10000)
        card = p.inner_text('#care-errors')
        for words in ('Which mod caused this error?', 'MCCC', "AttributeError: 'NoneType' object has no attribute",
                      '14 times', 'Probably UI Cheats Extension', 'Errors marked as seen (1)'):
            self.assertIn(words, card)
        # the raw details are there, folded away
        det = p.locator('#care-errors .care-error').first.locator('details')
        self.assertFalse(det.evaluate('d => d.open'))
        det.locator('summary').click()
        self.assertIn('mc_zone.py', det.inner_text())
        p.click('[data-act="care-error-aside"][data-name="MCCC"]')
        p.wait_for_selector('.modal:has-text("Set MCCC aside?")')
        p.click('.modal [data-yes]')
        self.finish_task('Set aside')
        self.assertEqual(self.tasks('set_aside'), [{'rels': ['MCCC/mc_cmd_center.ts4script'], 'why': 'error'}])
        p.wait_for_selector('#care-errors .care-error:has-text("MCCC") .chip:has-text("Set aside")', timeout=10000)
        p.click('[data-act="care-errors-seen"]')
        p.wait_for_selector('#care-errors .care-status:has-text("No new errors")', timeout=5000)
        self.assertIn(('POST', 'errors/seen', {}), self.calls)

    # ------------------------------------------------------------------------------------------ Saves
    def test_saves_backups(self):
        self.open('saves')
        p = self.page
        p.wait_for_selector('[data-care="backups"] [data-act="care-restore"]', timeout=15000)
        card = p.inner_text('[data-care="backups"]')
        for words in ('Save backups', 'Made manually', 'Made on patch day', 'Wicked Nights'):
            self.assertIn(words, card)
        p.wait_for_selector('.save .care-size:has-text("48 MB")', timeout=10000)
        self.assertIn('Growing fast', p.inner_text('.save:has-text("Wicked Nights")'))
        n = p.locator('[data-care="backups"] .care-row').count()
        p.click('[data-act="care-backup"]')
        self.finish_task('Saves backed up')
        self.assertEqual(self.tasks('backup_saves'), [{}])
        p.wait_for_function('n => document.querySelectorAll(\'[data-care="backups"] .care-row\').length > n', arg=n,
                            timeout=10000)
        first = p.locator('[data-act="care-restore"]').first
        backup_id = first.get_attribute('data-backup')
        first.click()
        p.wait_for_selector('.modal:has-text("Restore these saves?")')
        p.click('.modal [data-yes]')
        self.finish_task('Saves restored')
        self.assertEqual(self.tasks('restore_saves'), [{'backup': backup_id}])
        # undoable from the Tools page
        self.open('tools')
        p.wait_for_selector('.change.next:has-text("Restored saves from a backup")', timeout=10000)


if __name__ == '__main__':
    unittest.main()
