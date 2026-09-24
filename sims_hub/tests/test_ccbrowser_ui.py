"""The CC browser in a real browser (Playwright + Chromium, headless) against the Hub started in example-data mode:
    python3 -m speedkit.hub --serve --stub --port <a free port, never 8765/8766>
Checks that pictures really render, that category / search / page / "used" filters work, that files can be set aside
(and show up in Recent changes), that a save's CC window shows its files, households and missing CC, and that the page
logs no errors. The internet is cut off (only 127.0.0.1 is reachable), so the web font's failure is expected; so are
404s for pictures the example data does not have (the page shows the category's icon instead).

Skipped when Playwright or a Chromium build is not installed. Browsers are looked up in PLAYWRIGHT_BROWSERS_PATH (or
/opt/pw-browsers); nothing is downloaded."""
import glob
import json
import os
import re
import socket
import subprocess
import sys
import time
import unittest
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')

try:
    from playwright.sync_api import sync_playwright
except ImportError:                     # pragma: no cover
    sync_playwright = None

BROWSERS = os.environ.get('PLAYWRIGHT_BROWSERS_PATH') or '/opt/pw-browsers'


def chromium_executables():
    pats = ('chromium-*/chrome-linux/chrome', 'chromium_headless_shell-*/chrome-linux/headless_shell',
            'chromium-*/chrome-win/chrome.exe', 'chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium')
    out = []
    for pat in pats:
        out += sorted(glob.glob(os.path.join(BROWSERS, pat)), reverse=True)
    return out


def free_port():
    while True:
        s = socket.socket()
        s.bind(('127.0.0.1', 0))
        port = s.getsockname()[1]
        s.close()
        if port not in (8765, 8766):
            return port


def launch(p):
    try:
        return p.chromium.launch()
    except Exception:
        for exe in chromium_executables():
            try:
                return p.chromium.launch(executable_path=exe)
            except Exception:
                continue
    return None


@unittest.skipIf(sync_playwright is None, 'Playwright is not installed')
class CCBrowserUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = free_port()
        env = dict(os.environ, SIMS_HUB_STUB_DELAY='0.05', PYTHONUNBUFFERED='1')
        cls.proc = subprocess.Popen([sys.executable, '-m', 'speedkit.hub', '--serve', '--stub', '--port', str(cls.port)],
                                    cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        cls.base = 'http://127.0.0.1:%d' % cls.port
        end = time.time() + 20
        while True:
            try:
                with urllib.request.urlopen(cls.base + '/api/ping', timeout=2) as r:
                    if json.loads(r.read())['engine'] == 'stub':
                        break
            except Exception:
                if time.time() > end or cls.proc.poll() is not None:
                    cls.proc.kill()
                    raise unittest.SkipTest('the Hub did not start')
                time.sleep(0.2)
        cls.pw = sync_playwright().start()
        cls.browser = launch(cls.pw)
        if cls.browser is None:
            cls.pw.stop()
            cls.proc.kill()
            raise unittest.SkipTest('no Chromium build for Playwright under %s' % BROWSERS)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.proc.terminate()
        try:
            cls.proc.wait(10)
        except subprocess.TimeoutExpired:
            cls.proc.kill()
        cls.proc.stdout.close()

    def setUp(self):
        self.page = self.browser.new_page(viewport={'width': 1400, 'height': 1000})
        self.errors = []

        def console(m):
            if m.type != 'error':
                return
            url = (m.location or {}).get('url', '')
            if not url.startswith(self.base) or re.search(r'/api/cc/(pic|thumb)/', url):
                return          # the web font (offline) and pictures the example data has not got: both expected
            self.errors.append('%s (%s)' % (m.text, url))
        self.page.on('console', console)
        self.page.on('pageerror', lambda e: self.errors.append('page error: %s' % e))
        self.page.route(re.compile(r'^https?://(?!127\.0\.0\.1)'), lambda route: route.abort())

    def tearDown(self):
        self.page.close()
        self.assertEqual(self.errors, [])

    # ---------------------------------------------------------------- helpers
    def open_library(self):
        self.page.goto(self.base + '/#library')
        self.page.wait_for_selector('#cc-browser .cc-card img')

    def cards(self):
        return self.page.eval_on_selector_all('#cc-browser .cc-card', 'els => els.map(e => ({cat: e.dataset.cat, '
                                              'name: e.querySelector(".cc-meta b").textContent}))')

    def wait_count(self, text):
        self.page.wait_for_function('t => (document.querySelector("#cc-browser .cc-count") || {}).textContent.includes(t)',
                                    arg=text)

    # ---------------------------------------------------------------- the Library page
    def test_pictures_render(self):
        self.open_library()
        self.page.wait_for_function('() => [...document.querySelectorAll("#cc-browser .cc-pic img")]'
                                    '.filter(i => i.complete && i.naturalWidth > 0).length >= 6')
        n = self.page.eval_on_selector_all('#cc-browser .cc-pic img', 'els => els.filter(i => i.naturalWidth > 0).length')
        self.assertGreaterEqual(n, 6)
        self.assertEqual(len(self.cards()), 60)
        self.assertIn('Showing 1–60 of', self.page.inner_text('#cc-browser .cc-count'))
        # a file without a picture shows its category's icon
        self.assertGreater(self.page.eval_on_selector_all('#cc-browser .cc-ph svg', 'els => els.length'), 0)

    def test_category_search_and_pages(self):
        self.open_library()
        self.page.click('.cc-cat[data-key="hair"]')
        self.wait_count('of 46')
        self.assertEqual({c['cat'] for c in self.cards()}, {'hair'})
        self.page.fill('#cc-q', 'braids')
        self.wait_count('of 5')
        self.assertTrue(all('braids' in c['name'].lower() for c in self.cards()))
        self.assertEqual(self.page.evaluate('document.activeElement.id'), 'cc-q')     # the box keeps focus
        self.page.click('#cc-browser [data-cc="clear"]')
        self.page.wait_for_function('() => !document.querySelector("#cc-browser .cc-count").textContent.includes("of 5")')
        self.page.click('#cc-browser .cc-pager [data-cc="page"]:has-text("Next")')
        self.page.wait_for_function('() => document.querySelector("#cc-browser .cc-pager").textContent.includes("Page 2 of")')
        self.assertIn('Showing 61–120', self.page.inner_text('#cc-browser .cc-count'))
        self.page.select_option('[data-cc-f="flag"]', 'duplicate')
        self.wait_count('of 6')
        self.page.select_option('[data-cc-f="flag"]', '')
        self.page.select_option('[data-cc-f="used"]', 'unused')
        self.page.wait_for_function('() => [...document.querySelectorAll("#cc-browser .cc-card")].length > 0 && '
                                    '[...document.querySelectorAll("#cc-browser .cc-card")].every(c => c.textContent.includes("Not used"))')

    def test_details_and_set_aside(self):
        self.open_library()
        before = int(re.search(r'of ([\d,]+)', self.page.inner_text('#cc-browser .cc-count')).group(1).replace(',', ''))
        self.page.click('.cc-cat[data-key="buildbuy"]')
        self.wait_count('of 40')
        card = self.page.query_selector('#cc-browser .cc-card:not(:has(.cc-badge:has-text("Put away")))')
        card.click()
        self.page.wait_for_selector('.cc-detail')
        self.assertIn('Build/Buy', self.page.inner_text('.cc-facts'))
        self.page.click('.modal [data-aside]')
        self.page.wait_for_selector('.modal [data-yes]')
        self.assertIn('Undo last change', self.page.inner_text('.modal'))
        self.page.click('.modal [data-yes]')
        self.page.wait_for_selector('.task footer:not(.hidden) [data-close]', timeout=20000)
        self.assertIn('Set aside 1 file', self.page.inner_text('.task'))
        self.page.click('.task [data-close]')
        self.wait_count('of 39')
        self.page.click('.cc-cat[data-key=""]')
        self.wait_count('of %s' % format(before - 1, ','))
        self.page.goto(self.base + '/#tools')
        self.page.wait_for_selector('.change.next')
        self.assertIn('Set CC files aside', self.page.inner_text('.change.next'))

    def test_scan_shows_progress_in_the_card(self):
        self.open_library()
        self.page.click('#cc-browser [data-cc="scan"]')
        self.page.wait_for_selector('#cc-browser .cc-progress:not(.hidden)')
        self.page.wait_for_selector('#cc-browser .cc-progress.hidden', state='attached', timeout=20000)
        self.assertEqual(self.page.query_selector_all('.overlay'), [])       # no big progress window for this
        self.page.wait_for_selector('.toast:has-text("Sorted")')

    # ---------------------------------------------------------------- the Saves page
    def test_a_saves_cc(self):
        self.page.goto(self.base + '/#saves')
        self.page.wait_for_selector('.cc-save-btn[data-slot="Slot_00000003"]')
        self.page.click('.cc-save-btn[data-slot="Slot_00000003"]')
        self.page.wait_for_selector('.cc-wide .cc-card img')
        self.assertIn('37 missing', self.page.inner_text('.cc-wide header'))
        self.page.wait_for_function('() => [...document.querySelectorAll(".cc-wide .cc-pic img")].some(i => i.naturalWidth > 0)')
        self.page.click('.cc-tabs [data-tab="sims"]')
        self.page.wait_for_selector('.cc-hh .cc-sim')
        self.assertIn('Played household', self.page.inner_text('.cc-wide .body'))
        self.page.click('.cc-tabs [data-tab="missing"]')
        self.page.wait_for_selector('.cc-miss')
        text = self.page.inner_text('.cc-wide .body')
        self.assertIn('Saves only store an ID number', text)
        self.assertIn('In the safe copies', text)
        self.assertIn('Not found on this PC', text)
        self.assertRegex(text, r'[0-9A-F]{16}')
        self.page.keyboard.press('Escape')
        self.page.click('[data-act="save-cc"][data-slot="tray"]')
        self.page.wait_for_selector('.cc-wide .cc-card')
        self.assertIn('in-game library', self.page.inner_text('.cc-wide header'))


if __name__ == '__main__':
    unittest.main()
