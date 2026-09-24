"""UI smoke test for your own sounds: the Add sound dialog (web/js/dialogs/sound.js) against the real server.

    python tools/checks/own_sounds/smoke_ui.py [port]        (default port 8794; never 8765 / 8766)

No game is needed. A sound is made beforehand into a temp saves folder (with the synthetic template of
test_own_sounds.py), the server is started on that folder (ANIMATOR_SAVES), and a small page served by Playwright
loads the app's own dialog module with a stand-in `app`. Checked: "Your own sound files" lists the sound, Listen
fetches /api/sound for it and the browser decodes it, clicking it places it at the playhead, and uploading a file
that is not a sound - or a real one on a computer without creator sounds to copy settings from - shows the server's
message in the dialog. 'three' (the 3D library, from a CDN the test can't reach) is a stand-in module: the dialog
never uses it.
"""
import io
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_own_sounds as T  # noqa: E402  (sets ANIMATOR_SAVES to its temp folder)

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8794
assert PORT not in (8765, 8766, 8777)
BASE = 'http://127.0.0.1:%d' % PORT
WEB = os.path.join(T.ROOT, 'web')


def chromium():
    """CHROMIUM, else a Chromium in PLAYWRIGHT_BROWSERS_PATH (or /opt/pw-browsers) - whichever build is installed,
    so a Playwright package that expects another build still runs; None = Playwright's own choice."""
    import glob
    if os.environ.get('CHROMIUM'):
        return os.environ['CHROMIUM']
    root = os.environ.get('PLAYWRIGHT_BROWSERS_PATH') or '/opt/pw-browsers'
    found = sorted(glob.glob(os.path.join(root, 'chromium-*', 'chrome-linux', 'chrome')))
    return found[-1] if found else None


def three_stub():
    names = set()
    for fn in ('animation.js', 'bones.js'):
        with open(os.path.join(WEB, 'js', fn), encoding='utf-8') as f:
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
<link rel="stylesheet" href="/css/app.css"><link rel="stylesheet" href="/css/features/faces.css">
</head><body><div id="modal-root"></div><div id="toasts"></div>
<script type="module">
import { openAddSoundDialog } from '/js/dialogs/sound.js';
import { SoundPlayer } from '/js/audio.js';
const sim = { id: 's1', label: 'Sim 1', frame: 'yf', sounds: [] };
const app = window.app = {
  store: { frame: 12, sim: id => (id === sim.id ? sim : null), checkpoint() {} },
  sounds: [], voiceLines: [], audio: new SoundPlayer(), edits: 0, afterEdit() { this.edits++; },
};
window.sim = sim;
window.open_ = () => openAddSoundDialog(app, 's1');
window.ready = true;
</script></body></html>"""


def wav_bytes(seconds=0.8, rate=44100):
    t = np.arange(int(rate * seconds)) / rate
    b = io.BytesIO()
    sf.write(b, 0.5 * np.sin(2 * np.pi * 300 * t), rate, format='WAV', subtype='PCM_16')
    return b.getvalue()


def main():
    # 1. one sound made beforehand (synthetic template), in the temp saves folder the server will use
    with T.FakeMods():
        made = T.M.add(wav_bytes(), 'Smoke Moan.wav', 'voice')
    saves = os.environ['ANIMATOR_SAVES']
    env = dict(os.environ, ANIMATOR_PORT=str(PORT), ANIMATOR_SAVES=saves, HOME=os.path.join(T.TMP, 'home'))
    os.makedirs(env['HOME'], exist_ok=True)
    log = open(os.path.join(T.TMP, 'server.log'), 'wb')
    srv = subprocess.Popen([sys.executable, os.path.join(T.ROOT, 'backend', 'server.py')], env=env, stdout=log, stderr=log)
    results = {}
    try:
        for _ in range(100):
            try:
                with urllib.request.urlopen(BASE + '/api/my_sounds', timeout=2) as r:
                    listed = json.loads(r.read())
                break
            except Exception:
                time.sleep(0.2)
        else:
            raise RuntimeError('server did not start')
        results['api_list'] = [x['name'] for x in listed]
        assert results['api_list'] == [made['name']], results
        with urllib.request.urlopen(BASE + '/api/sound?name=' + made['name'], timeout=10) as r:
            wav = r.read()
            assert r.headers['Content-Type'] == 'audio/wav' and wav[:4] == b'RIFF'

        with sync_playwright() as p:
            browser = p.chromium.launch(args=['--autoplay-policy=no-user-gesture-required'], executable_path=chromium())
            page = browser.new_page()
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.route(BASE + '/__smoke.html', lambda route: route.fulfill(status=200, content_type='text/html', body=PAGE))
            page.route(BASE + '/__three_stub.js', lambda route: route.fulfill(status=200, content_type='text/javascript', body=three_stub()))
            page.goto(BASE + '/__smoke.html')
            page.wait_for_function('window.ready === true')
            page.evaluate('window.open_()')
            page.select_option('#modal-root select', 'mine')
            row = page.locator('.proj-item.my-sound')
            row.first.wait_for(timeout=10000)
            results['row_text'] = row.first.inner_text()
            assert 'Smoke Moan.wav' in results['row_text'], results
            # Listen: the browser fetches and decodes the stored game audio
            decoded = page.evaluate("""async name => { const b = await app.audio.load(name); return b ? { sec: b.duration, rate: b.sampleRate } : null; }""", made['name'])
            results['browser_decoded'] = decoded
            assert decoded and abs(decoded['sec'] - made['seconds']) < 0.05, decoded
            # a file that is not a sound: the server's message shows in the dialog
            page.set_input_files('#modal-root input[type=file]', files=[{'name': 'broken.wav', 'mimeType': 'audio/wav', 'buffer': b'not a sound' * 50}])
            page.locator('.my-sound-error').wait_for(timeout=10000)
            results['error_broken'] = page.locator('.my-sound-error').inner_text()
            assert 'WAV, MP3, OGG or FLAC' in results['error_broken'], results
            # a real sound, but this computer has no creator sounds to copy settings from (no game here)
            page.set_input_files('#modal-root input[type=file]', files=[{'name': 'new.wav', 'mimeType': 'audio/wav', 'buffer': wav_bytes(0.5, 22050)}])
            page.wait_for_function("document.querySelector('.my-sound-error') && /Mods folder/.test(document.querySelector('.my-sound-error').textContent)", timeout=20000)
            results['error_no_template'] = page.locator('.my-sound-error').inner_text()
            # an MP3: the page decodes it and sends 16-bit WAV (the server reads it: it gets as far as the template)
            sent = []
            page.on('request', lambda r: sent.append(r.headers.get('content-type')) if '/api/my_sound?' in r.url else None)
            b = io.BytesIO()
            sf.write(b, 0.4 * np.sin(np.arange(22050) / 4.0), 22050, format='MP3')
            page.evaluate("document.querySelector('.my-sound-error').remove()")
            page.set_input_files('#modal-root input[type=file]', files=[{'name': 'song.mp3', 'mimeType': 'audio/mpeg', 'buffer': b.getvalue()}])
            page.wait_for_function("document.querySelector('.my-sound-error') && /Mods folder/.test(document.querySelector('.my-sound-error').textContent)", timeout=20000)
            results['mp3_sent_as'] = sent[-1]
            assert sent[-1] == 'audio/wav', sent
            # longer than 30 s: stopped in the page with the same message the server gives
            b = io.BytesIO()
            sf.write(b, np.zeros(8000 * 31) + 0.1, 8000, format='WAV', subtype='PCM_16')
            n_before = len(sent)
            page.set_input_files('#modal-root input[type=file]', files=[{'name': 'long.wav', 'mimeType': 'audio/wav', 'buffer': b.getvalue()}])
            page.wait_for_function("document.querySelector('.my-sound-error') && /up to 30 seconds/.test(document.querySelector('.my-sound-error').textContent)", timeout=20000)
            results['error_long'] = page.locator('.my-sound-error').inner_text()
            assert len(sent) == n_before, 'a too long file is not sent'
            if os.environ.get('SHOT'):
                page.set_viewport_size({'width': 1100, 'height': 760})
                page.screenshot(path=os.environ['SHOT'])
            # pick the existing sound: placed at the playhead as a voice
            page.locator('.proj-item.my-sound').first.click()
            page.wait_for_function('window.sim.sounds.length === 1')
            results['placed'] = page.evaluate('window.sim.sounds')
            assert results['placed'] == [{'frame': 12, 'name': made['name'], 'kind': 'voice'}], results
            assert page.evaluate('app.edits') == 1
            results['toast'] = page.locator('#toasts').inner_text()
            assert 'Smoke Moan.wav at frame 12' in results['toast'], results
            # the lip-sync panel (its "Play this sound in the game too" button) loads with the new import
            results['lipsyncui_loads'] = page.evaluate("import('/js/lipsyncui.js').then(m => typeof m.playFileAlong === 'function', e => String(e))")
            assert results['lipsyncui_loads'] is True, results
            results['page_errors'] = errors
            assert not errors, errors
            browser.close()
    finally:
        srv.terminate()
        srv.wait(10)
        log.close()
    print(json.dumps(results, indent=1))
    print('SMOKE OK')
    import shutil
    shutil.rmtree(T.TMP, ignore_errors=True)


if __name__ == '__main__':
    main()
