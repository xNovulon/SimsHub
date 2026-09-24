"""UI smoke test of the "Fit hands to each sim's body" switch in Send to game (web/js/dialogs/export.js +
web/js/features/bodyfit.js), against the real server's files.

    python tools/checks/bodyfit/smoke_ui.py [port]        (default 8794; never 8765 / 8766)

A small page served by Playwright opens the app's own Send to game dialog with a stand-in `app` (two sims; the first
holds the second with its right hand for the whole loop and with its left hand for part of it). Checked: the switch
is there and OFF for a new animation, with its text; turning it on sets project.fitBodies, marks the animation
changed and says 1 hold is fitted and 1 is not; the bake hook then lists the right hand under 'ik' and the left under
'ikSkipped' (nothing when off); Send to game posts that payload and the success card shows the How to test line;
turning it off removes fitBodies again. 'three' is a stand-in module (the CDN is out of reach; the dialog never uses
it); /api/export is answered by the test, nothing is written.
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
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8794
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


PAGE = """<!doctype html><html><head><meta charset="utf-8">
<script type="importmap">{"imports": {"three": "/__three_stub.js", "three/addons/": "/__three_stub_addons/"}}</script>
<link rel="stylesheet" href="/css/app.css">
</head><body><div id="modal-root"></div><div id="toasts"></div>
<script type="module">
import { openExportDialog } from '/js/dialogs/export.js';
import { install } from '/js/features/bodyfit.js';
const p = { uid: 'u1', name: 'Hold test', author: 'Tester', category: 'TEASING', locations: ['FLOOR'], tags: ['KISSING'],
  length: 60, fps: 30, loops: 10,
  sims: [
    { id: 's1', label: 'Sim 1', frame: 'ym', keys: [{ frame: 0 }], sounds: [{ frame: 1, name: 'x', kind: 'clap' }],
      pins: { 'R hand': { sim: 's2', bone: 'b__Spine1__', off: [0, 0, 0], label: 'waist' },
              'L hand': { sim: 's2', bone: 'b__Head__', off: [0, 0, 0], label: 'head', from: 10, to: 30, fade: 3 },
              'L foot': [0, 0, 0] } },
    { id: 's2', label: 'Sim 2', frame: 'yf', keys: [{ frame: 0 }], sounds: [], pins: {} },
  ] };
const hooks = { bake: [], exportChecks: [] };
const app = window.app = {
  hooks, dirty: 0, saved: 0,
  store: { project: p, setDirty(on) { if (on) app.dirty++; }, checkpoint() {} },
  runHook(name, ...args) { return (hooks[name] || []).map(fn => fn(...args)); },
  showStep() {}, refreshTitle() {}, emit() {},
  async save() { app.saved++; return true; },
  bake() {
    const payload = { name: p.name, author: p.author, frames: p.length, fps: p.fps, actors: p.sims.map(s => ({ gender: 'BOTH', tracks: {}, sounds: [] })) };
    app.runHook('bake', payload, p, {});
    return payload;
  },
};
install(app);
window.p = p;
window.open_ = () => openExportDialog(app);
window.ready = true;
</script></body></html>"""


def main():
    tmp = tempfile.mkdtemp(prefix='wa_bodyfit_ui_')
    env = dict(os.environ, ANIMATOR_PORT=str(PORT), ANIMATOR_SAVES=os.path.join(tmp, 'saves'), HOME=os.path.join(tmp, 'home'))
    os.makedirs(env['HOME'], exist_ok=True)
    log = open(os.path.join(tmp, 'server.log'), 'wb')
    srv = subprocess.Popen([sys.executable, os.path.join(ROOT, 'backend', 'server.py')], env=env, stdout=log, stderr=log)
    results = {}
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(BASE + '/js/dialogs/export.js', timeout=2).read()
                break
            except Exception:
                time.sleep(0.2)
        else:
            raise RuntimeError('server did not start')
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=chromium())
            page = browser.new_page(viewport={'width': 1100, 'height': 900})
            errors, posted = [], []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.route(BASE + '/__smoke.html', lambda r: r.fulfill(status=200, content_type='text/html', body=PAGE))
            page.route(BASE + '/__three_stub.js', lambda r: r.fulfill(status=200, content_type='text/javascript', body=three_stub()))

            def fake_export(route):
                posted.append(json.loads(route.request.post_data))
                route.fulfill(status=200, content_type='application/json', body=json.dumps({
                    'path': '/tmp/(test)/x.package', 'package': 'x.package', 'clips': [], 'bytes': 1024, 'next': [],
                    'next_names': [], 'random': True, 'sound_kit': None, 'replaced': [], 'warnings': [], 'own_sounds': 0,
                    'fit_bodies': sum(len(a.get('ik') or []) for a in posted[-1]['actors'])}))
            page.route(BASE + '/api/export', fake_export)
            page.goto(BASE + '/__smoke.html')
            page.wait_for_function('window.ready === true')
            page.evaluate('window.open_()')
            row = page.locator('.fit-bodies .toggle-row')
            row.wait_for(timeout=10000)
            results['title'] = row.locator('b').inner_text()
            results['text'] = row.locator('span').first.inner_text()
            assert results['title'] == 'Fit hands to each sim’s body (experimental – test in game)', results
            assert 'Needs a check in the game' in results['text'] and 'not the partner' in results['text'], results
            box = row.locator('input[type=checkbox]')
            assert not box.is_checked(), 'off by default'
            assert page.evaluate('app.bake().actors.every(a => !a.ik && !a.ikSkipped)')
            # on
            row.locator('label.switch').click()
            assert page.evaluate('window.p.fitBodies === true') and page.evaluate('app.dirty') == 1
            results['note_on'] = page.locator('.fit-note').inner_text()
            assert results['note_on'] == '1 hold will be fitted; 1 that holds for part of the loop only will not.', results
            baked = page.evaluate('app.bake()')
            results['baked_on'] = {'fitBodies': baked.get('fitBodies'), 'ik': [a.get('ik') for a in baked['actors']],
                                   'ikSkipped': [a.get('ikSkipped') for a in baked['actors']]}
            assert baked['fitBodies'] is True and baked['actors'][0]['ik'] == [{'limb': 'R hand'}], results
            assert baked['actors'][0]['ikSkipped'] == ['L hand'] and 'ik' not in baked['actors'][1], results
            if os.environ.get('SHOT'):
                page.screenshot(path=os.environ['SHOT'])
            # off again, then on, and send
            row.locator('label.switch').click()
            assert page.evaluate("!('fitBodies' in window.p)") and page.locator('.fit-note').inner_text() == ''
            row.locator('label.switch').click()
            page.locator('#modal-root footer .btn.primary').click()
            page.wait_for_selector('.fit-test', timeout=10000)
            results['success_line'] = page.locator('.fit-test').inner_text()
            assert 'How to test' in results['success_line'], results
            assert posted and posted[-1]['fitBodies'] is True and posted[-1]['actors'][0]['ik'] == [{'limb': 'R hand'}]
            assert page.evaluate('app.saved') == 1
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
