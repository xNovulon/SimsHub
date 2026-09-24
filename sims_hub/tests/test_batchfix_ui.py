"""The Tools page's "CC that may need a Sims 4 Studio fix" card and its line in the patch-day notice, in a real browser
(Playwright + Chromium), with the Hub started in example-data mode the way a person would (python -m speedkit.hub
--serve --stub --port <free port>). Checks what is drawn, that the buttons call the server (the requests are
watched), and that the page logs no script errors. Only 127.0.0.1 is reachable. Skipped without Playwright/Chromium."""
import json
import os
import subprocess
import sys
import time
import unittest
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from tests.test_care_ui import ROOT, _chromium, _free_port, sync_playwright  # noqa: E402


@unittest.skipUnless(sync_playwright is not None, 'Playwright is not installed')
class BatchFixUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw = sync_playwright().start()
        try:
            exe = _chromium()
            try:
                cls.browser = cls.pw.chromium.launch(**({'executable_path': exe} if exe else {}))
            except Exception:
                if not exe:
                    raise unittest.SkipTest('no Chromium for Playwright')
                raise
        except BaseException:
            cls.pw.stop()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def setUp(self):
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
                        break
            except Exception:
                time.sleep(0.1)
        else:
            raise RuntimeError('the Hub did not start')
        self.page = self.browser.new_page(viewport={'width': 1440, 'height': 1100})
        self.errors, self.calls = [], []
        self.page.route('**/*', lambda route: route.continue_() if route.request.url.startswith(self.base)
                        else route.abort())
        self.page.on('pageerror', lambda e: self.errors.append(str(e)))
        self.page.on('console', lambda m: self.errors.append(m.text)
                     if m.type == 'error' and 'net::ERR_FAILED' not in m.text else None)
        self.page.on('request', self._request)

    def stop_hub(self):
        self.proc.terminate()
        try:
            self.proc.wait(10)
        except subprocess.TimeoutExpired:
            self.proc.kill()

    def tearDown(self):
        self.page.close()
        self.assertEqual(self.errors, [], 'script errors on the page')

    def _request(self, req):
        if '/api/' in req.url:
            body = json.loads(req.post_data or '{}') if req.method == 'POST' else None
            self.calls.append((req.method, req.url.split('/api/', 1)[1], body))

    def tasks(self, action):
        return [b['args'] for m, path, b in self.calls if m == 'POST' and path == 'task' and b.get('action') == action]

    def finish_task(self, done_title):
        self.page.wait_for_selector('.task h2:has-text("%s")' % done_title, timeout=15000)
        self.page.click('.task [data-close]')
        self.page.wait_for_selector('.overlay', state='detached', timeout=5000)

    def test_patch_day_notice_line(self):
        self.page.goto(self.base + '#home')
        p = self.page
        p.wait_for_selector('[data-care="patch-banner"] [data-care="batchfix-line"]', timeout=15000)
        line = p.inner_text('[data-care="patch-banner"] [data-care="batchfix-line"]')
        self.assertIn('10 CC files may need a Sims 4 Studio fix', line)
        self.assertIn('Update Sliders (Werewolf Patch)', line)
        p.click('[data-care="batchfix-line"] a')
        p.wait_for_selector('#care-batchfix .bf-fix', timeout=10000)
        self.assertIn('10 CC files may need a Sims 4 Studio fix', p.inner_text('#care-patch'))

    def test_tools_card(self):
        self.page.goto(self.base + '#tools')
        p = self.page
        p.wait_for_selector('#care-batchfix .bf-fix', timeout=15000)
        card = p.inner_text('#care-batchfix')
        for words in ('CC that may need a Sims 4 Studio fix', 'CC files are never changed here',
                      '10 CC files may need a Sims 4 Studio batch fix', 'Update Sliders (Werewolf Patch)',
                      'Update Eye Colors for Infants (Infants Patch)', 'Disable Shoes for Werewolves',
                      'Disallow CC for Default Garment', 'Update CAS CC Pets Patch',
                      'Tools › Content Management › Batch Fixes › CAS › Update Sliders (Werewolf Patch)',
                      'Sims 4 Studio keeps a copy of each file it changes', 'May need',
                      'parked by Quick Start or one-save mode'):
            self.assertIn(words, card)
        self.assertEqual(p.locator('#care-batchfix .bf-fix').count(), 5)
        # the files are folded away; opening shows them with their reason
        sliders = p.locator('#care-batchfix .bf-fix[data-fix="sliders_werewolf"]')
        self.assertFalse(sliders.locator('details').evaluate('d => d.open'))
        sliders.locator('summary').click()
        rows = sliders.inner_text()
        self.assertIn('Obscurus_NoseShape_Sliders.package', rows)
        self.assertIn('All 4 sliders use the format from before the June 2022 game update', rows)
        # "Open folder" asks the server for that file
        sliders.locator('[data-act="bf-open"]').first.click()
        p.wait_for_selector('.toast:has-text("would open now")', timeout=5000)
        self.assertIn(('POST', 'batchfix/open', {'rel': 'Sliders/Obscurus_NoseShape_Sliders.package'}), self.calls)
        # "Set these aside instead" asks first, then sets them aside (undoable) with why "fix"
        sliders.locator('[data-act="bf-aside"]').click()
        p.wait_for_selector('.modal:has-text("Set 3 files aside?")')
        p.click('.modal [data-yes]')
        self.finish_task('Set aside')
        self.assertEqual(self.tasks('set_aside'), [{'rels': ['Sliders/Obscurus_NoseShape_Sliders.package',
                                                             'Sliders/Chin Width Slider 2021.package',
                                                             'Sliders/Enhanced_Butt_Slider.package'], 'why': 'fix'}])
        p.wait_for_selector('#care-batchfix .bf-fix[data-fix="sliders_werewolf"] summary:has-text("(3 set aside)")',
                            timeout=10000)
        self.assertIn('until it gets a Sims 4 Studio fix', p.inner_text('#care-patch'))
        p.wait_for_selector('.change:has-text("Set CC aside until it gets a Sims 4 Studio fix")', timeout=10000)
        # "Check again" runs the check as a task
        p.click('[data-act="bf-scan"]')
        self.finish_task('Check finished')
        self.assertEqual(self.tasks('batch_fix_scan'), [{}])


if __name__ == '__main__':
    unittest.main()
