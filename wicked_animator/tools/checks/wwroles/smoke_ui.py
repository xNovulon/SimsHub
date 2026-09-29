"""UI smoke test of the Details step's new Roles/Orientation/Duration preview (web/js/details.js + tags.js), against
the real server's files - see needs.md: "add F+M in wicked animator in the tags menu, same with orientation and
should add duration automatically".

    python tools/checks/wwroles/smoke_ui.py [port]        (default 8942; never 8765 / 8766)

A small page served by Playwright calls renderDetails() straight from web/js/details.js with a stand-in `app` (two
sims: a plain FEMALE and a plain MALE) - the same approach as tools/checks/bodyfit/smoke_ui.py. Checked: the Roles/
Orientation preview line and the Duration hint show the right text for two plain-gendered sims; switching a sim to
"Either" reveals a "Prefers" choice and both live texts update (guessing from the sim's own body first, then the
explicit choice); switching back removes it again. 'three' is a stand-in module (the CDN is out of reach; Details
never uses it, only web/js/state.js imports something that does).
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
WEB = os.path.join(ROOT, 'web')
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8942
assert PORT not in (8765, 8766, 8777)
BASE = 'http://127.0.0.1:%d' % PORT


def chromium():
    import glob
    if os.environ.get('CHROMIUM'):
        return os.environ['CHROMIUM']
    root = os.environ.get('PLAYWRIGHT_BROWSERS_PATH') or '/opt/pw-browsers'
    found = sorted(glob.glob(os.path.join(root, 'chromium-*', 'chrome-linux', 'chrome')))
    return found[-1] if found else None


def three_stub():
    names = set()
    for fn in ('animation.js', 'bones.js', 'state.js', 'posemath.js'):
        path = os.path.join(WEB, 'js', fn)
        if os.path.isfile(path):
            with open(path, encoding='utf-8') as f:
                names |= set(re.findall(r'THREE\.([A-Za-z0-9_]+)', f.read()))
    out = []
    for n in sorted(names):
        if n == 'MathUtils':
            out.append('export const MathUtils = { degToRad: d => d * Math.PI / 180, radToDeg: r => r * 180 / Math.PI, clamp: (v, a, b) => Math.min(b, Math.max(a, v)) };')
        elif n[:1].isupper():
            out.append('export class %s { constructor(...a) { this.args = a; } }' % n)
        else:
            out.append('export const %s = 0;' % n)
    return '\n'.join(out)


# 5.1s a loop x 10 loops = 51s - the owner's own example ("Duration: 51s")
PAGE = """<!doctype html><html><head><meta charset="utf-8">
<script type="importmap">{"imports": {"three": "/__three_stub.js", "three/addons/": "/__three_stub_addons/"}}</script>
<link rel="stylesheet" href="/css/app.css">
</head><body><div id="root"></div>
<script type="module">
import { renderDetails } from '/js/details.js';
const p = { uid: 'u1', name: 'Roles test', author: 'Tester', category: 'VAGINAL', locations: ['FLOOR'], tags: [],
  length: 153, fps: 30, loops: 10,
  sims: [
    { id: 's1', label: 'Sim 1', frame: 'yf', gender: 'FEMALE', color: '#f66' },
    { id: 's2', label: 'Sim 2', frame: 'ym', gender: 'MALE', color: '#6cf' },
  ] };
const root = document.getElementById('root');
const app = window.app = {
  store: { project: p, checkpoint() {}, setDirty() {} },
  refreshTitle() {}, showStep() {},
  roleOf(s) { return s.role === 'giver' || s.role === 'receiver' || s.role === 'both' ? s.role :
    (s.frame === 'ym' || s.frame === 'yf_futa' || s.gender === 'MALE' ? 'giver' : 'receiver'); },
  bareFeetOf(s) { return typeof s.bareFeet === 'boolean' ? s.bareFeet : false; },
  renderStep() { root.innerHTML = ''; renderDetails(app, root); },
};
window.p = p;
app.renderStep();
window.ready = true;
</script></body></html>"""


def main():
    tmp = tempfile.mkdtemp(prefix='wa_roles_ui_')
    env = dict(os.environ, ANIMATOR_PORT=str(PORT), ANIMATOR_SAVES=os.path.join(tmp, 'saves'), HOME=os.path.join(tmp, 'home'))
    os.makedirs(env['HOME'], exist_ok=True)
    log = open(os.path.join(tmp, 'server.log'), 'wb')
    srv = subprocess.Popen([sys.executable, os.path.join(ROOT, 'backend', 'server.py')], env=env, stdout=log, stderr=log)
    results = {}
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(BASE + '/js/details.js', timeout=2).read()
                break
            except Exception:
                time.sleep(0.2)
        else:
            raise RuntimeError('server did not start')
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=chromium())
            page = browser.new_page(viewport={'width': 1100, 'height': 1400})
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.route(BASE + '/__smoke.html', lambda r: r.fulfill(status=200, content_type='text/html', body=PAGE))
            page.route(BASE + '/__three_stub.js', lambda r: r.fulfill(status=200, content_type='text/javascript', body=three_stub()))
            page.goto(BASE + '/__smoke.html')
            page.wait_for_function('window.ready === true')

            preview = page.locator('.ww-preview')
            preview.wait_for(timeout=10000)
            results['roles_preview_plain'] = preview.inner_text()
            assert results['roles_preview_plain'] == 'Roles: F+M · Orientation: HE', results

            hints = page.locator('.hint')
            duration_hint = next(t for t in hints.all_inner_texts() if 'Duration:' in t)
            results['duration_hint'] = duration_hint
            assert 'Duration: 51s' in duration_hint, results     # 5.1s x 10 loops, ceil'd - the owner's own example

            # sim 1's "Plays which part in WickedWhims" select is the first one in its sim-game card
            sim1 = page.locator('.sim-game').first
            gender_select = sim1.locator('select').first
            assert not sim1.get_by_text('Prefers').count(), 'no "Prefers" row for a plain gender'

            gender_select.select_option('BOTH')
            results['roles_preview_both_no_choice'] = page.locator('.ww-preview').inner_text()
            # a BOTH sim with no explicit choice guesses from its own body (yf -> FEMALE), like the exporter
            assert results['roles_preview_both_no_choice'] == 'Roles: B/F+M · Orientation: HE', results
            assert sim1.get_by_text('Prefers').count() == 1, 'the "Prefers" row appears once Either is picked'

            prefers_select = sim1.locator('select').nth(1)
            prefers_select.select_option('MALE')
            results['roles_preview_both_male'] = page.locator('.ww-preview').inner_text()
            assert results['roles_preview_both_male'] == 'Roles: B/M+M · Orientation: HO', results

            sim1_after = page.locator('.sim-game').first
            sim1_after.locator('select').first.select_option('FEMALE')
            results['roles_preview_back_to_plain'] = page.locator('.ww-preview').inner_text()
            assert results['roles_preview_back_to_plain'] == 'Roles: F+M · Orientation: HE', results
            assert not page.locator('.sim-game').first.get_by_text('Prefers').count(), 'switching off Either drops "Prefers" again'

            if os.environ.get('SHOT'):
                page.screenshot(path=os.environ['SHOT'], full_page=True)
            results['page_errors'] = errors
            assert not errors, errors
            browser.close()
    finally:
        srv.terminate()
        srv.wait(10)
        log.close()
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
    print(json.dumps(results, indent=1))
    print('SMOKE OK')


if __name__ == '__main__':
    main()
