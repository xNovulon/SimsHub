"""Browser smoke test for "Import a motion file" (Playwright + Chromium, no game needed).

    python tools/checks/mocap/smoke_ui.py [--port N] [--headed] [--verbose] [--shots DIR]

Starts backend/server.py on the port (default: the first free one from 8793; never 8765/8766/8777), opens the app and checks, with no console errors:
  1. the app starts and the plug-in is installed (features/mocapfile.js, its stylesheet)
  2. Pose step: "From a motion file" sits right under the "Copy real moves" buttons and opens the dialog
  3. a .bvh chosen in the dialog is read (skeleton, frames, rest pose shown) and "Make keys" puts keys on the sim
     (the animation takes the part's length; one Ctrl+Z takes it back)
  4. Ctrl+K "motion file" finds the command and opens the dialog; Esc closes it
  5. the Library has its "Import a motion file" card
  6. FBX: a file with two animations is read (FBX facts, an "Animation" list), the second one is picked and put on
     (keys, one Ctrl+Z back); a binary .fbx dropped on the stage opens the dialog with it; an .fbx with a skeleton
     but no animation gets a plain message. FBXLoader comes from three.js's add-ons like the app's other add-ons.
Without The Sims 4 the server can't read the game's skeleton and bodies, so the page gets stand-ins for exactly three
routes: /api/rig (tools/checks/mocap/fixtures/test_rig.json, a synthetic rig), /api/body (one tiny triangle) and
/api/status. three.js comes from npm (lib/three.mjs finds or installs it) instead of the CDN.
Nothing is written: the page never calls a writing route in this test (they are refused if it tries).
"""
import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
FIX = os.path.join(HERE, 'fixtures')
REFUSED = {8765, 8766, 8777}
WRITES = ('/api/export', '/api/bundle', '/api/project', '/api/project_remove', '/api/progressions', '/api/my_poses', '/api/recovery',
          '/api/recovery_clear', '/api/save_video', '/api/reveal', '/api/doctor_fix', '/api/promo_save', '/api/posepack', '/api/reference')
rows = []


def row(name, ok, detail=''):
    rows.append((name, bool(ok), str(detail)))
    return ok


def three_dir():
    """The folder of the three.js package (build/, examples/)."""
    out = subprocess.run(['node', '--input-type=module', '-e',
                          "import {threeFile} from %s; console.log(threeFile())" % json.dumps('file://' + os.path.join(HERE, 'lib', 'three.mjs').replace('\\', '/'))],
                         capture_output=True, text=True, cwd=ROOT, check=True)
    f = out.stdout.strip().splitlines()[-1]
    return os.path.dirname(os.path.dirname(f))


def up(port):
    try:
        with urllib.request.urlopen('http://127.0.0.1:%d/api/features' % port, timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def free_port(start=8793, stop=8840):
    for port in range(start, stop):
        if port in REFUSED:
            continue
        with socket.socket() as s:
            if s.connect_ex(('127.0.0.1', port)) != 0:
                return port
    raise SystemExit('no free port between %d and %d' % (start, stop))


def start_server(port):
    if port in REFUSED:
        raise SystemExit('port %d belongs to someone else' % port)
    with socket.socket() as s:
        if s.connect_ex(('127.0.0.1', port)) == 0:
            raise SystemExit('port %d is already in use' % port)
    env = dict(os.environ, ANIMATOR_PORT=str(port), PYTHONUNBUFFERED='1')
    log_dir = os.path.join(ROOT, 'cache', 'checks', '_servers')
    os.makedirs(log_dir, exist_ok=True)
    log = open(os.path.join(log_dir, 'port%d.log' % port), 'ab')
    p = subprocess.Popen([sys.executable, os.path.join(ROOT, 'backend', 'server.py')], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    for _ in range(150):
        if up(port):
            return p
        if p.poll() is not None:
            break
        time.sleep(0.2)
    p.kill()
    raise SystemExit('the server did not start on port %d' % port)


def body(frame):
    # one triangle on the pelvis: enough for the app's Sim (the check is about the dialog, not the skin)
    return {'frame': frame, 'rig': 'au', 'ww': False, 'meshes': [{
        'part': 'test_%s_body' % frame, 'role': 'body', 'positions': [0.1, 1.0, 0.05, -0.1, 1.0, 0.05, 0, 1.2, 0.05],
        'normals': [0, 0, 1, 0, 0, 1, 0, 0, 1], 'uvs': [0, 0, 1, 0, 0.5, 1], 'bones': [2, 0, 0, 0] * 3,
        'weights': [1, 0, 0, 0] * 3, 'faces': [0, 1, 2]}]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=0, help='default: the first free port from 8793')
    ap.add_argument('--headed', action='store_true')
    ap.add_argument('--verbose', action='store_true')
    ap.add_argument('--shots', default=os.path.join(ROOT, 'cache', 'checks', 'mocap'))
    a = ap.parse_args()
    from playwright.sync_api import sync_playwright

    three = three_dir()
    rig = open(os.path.join(FIX, 'test_rig.json'), 'rb').read()
    a.port = a.port or free_port()
    server = start_server(a.port)
    base = 'http://127.0.0.1:%d' % a.port
    logs, writes, bad_urls = [], [], []
    os.makedirs(a.shots, exist_ok=True)
    try:
        with sync_playwright() as pw:
            args = ['--use-gl=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist']
            try:
                browser = pw.chromium.launch(headless=not a.headed, args=args, executable_path=os.environ.get('WA_CHROME') or None)
            except Exception:
                # Playwright's own build is missing: any Chromium it installed before (PLAYWRIGHT_BROWSERS_PATH)
                import glob
                pwb = os.environ.get('PLAYWRIGHT_BROWSERS_PATH', '/opt/pw-browsers')
                found = sorted(glob.glob(os.path.join(pwb, 'chromium-*', 'chrome-linux*', 'chrome')) +
                               glob.glob(os.path.join(pwb, 'chromium-*', 'chrome-win*', 'chrome.exe')), reverse=True)
                if not found:
                    raise
                browser = pw.chromium.launch(headless=not a.headed, args=args, executable_path=found[0])
            page = browser.new_page(viewport={'width': 1400, 'height': 860})
            page.on('console', lambda m: logs.append((m.type, m.text, (m.location or {}).get('url', ''))))
            page.on('pageerror', lambda e: logs.append(('pageerror', str(e), '')))
            page.on('response', lambda r: bad_urls.append('%d %s' % (r.status, r.url)) if r.status >= 400 else None)
            page.on('requestfailed', lambda r: bad_urls.append('failed %s %s' % (r.url, r.failure)))

            def cdn(route):
                rel = route.request.url.split('/three@0.160.0/', 1)[1].split('?')[0]
                f = os.path.join(three, *rel.split('/'))
                if os.path.isfile(f):
                    route.fulfill(status=200, content_type='application/javascript', body=open(f, 'rb').read())
                else:
                    route.fulfill(status=404, body='')
            page.route('https://cdn.jsdelivr.net/npm/three@0.160.0/**', cdn)
            page.route(base + '/api/rig*', lambda r: r.fulfill(status=200, content_type='application/json', body=rig))
            page.route(base + '/api/body*', lambda r: r.fulfill(status=200, content_type='application/json',
                                                               body=json.dumps(body(r.request.url.split('frame=')[1].split('&')[0]))))
            page.route(base + '/api/status', lambda r: r.fulfill(status=200, content_type='application/json',
                                                                 body=json.dumps({'ok': True, 'pid': server.pid, 'test': True})))
            # writing routes are answered here, in the browser (like tools/checks/lib/harness.js): nothing reaches the disk
            page.route('**/*', lambda r: (writes.append(r.request.url), r.fulfill(status=200, content_type='application/json', body='{"ok": true, "fake": true}'))
                       if r.request.method == 'POST' and any(r.request.url.split('?')[0].endswith(w) for w in WRITES) else r.fallback())
            page.add_init_script("try { localStorage.setItem('fsa.tourDone', 'true'); localStorage.removeItem('fsa.autosave'); } catch (e) {}")
            # every toast and choice bar is recorded as it appears (under load one can come and go before a check looks)
            page.add_init_script("""window.__toastLog = []; new MutationObserver(ms => { for (const m of ms) for (const n of m.addedNodes)
                if (n.nodeType === 1 && /^(Made |Undone|This part)/.test((n.textContent || '').trim())) window.__toastLog.push((n.textContent || '').trim()); })
                .observe(document, { childList: true, subtree: true });""")
            page.goto(base + '/?slot=test', wait_until='domcontentloaded')
            page.wait_for_selector('#loading.done', state='attached', timeout=90000)
            page.wait_for_function('window.app && window.app.__mocapfile', timeout=30000)
            page.evaluate("import('/js/home.js').then(h => h.hideHome(window.app))")          # Home -> the editor
            page.wait_for_selector('#home.hidden', state='attached', timeout=30000)
            page.wait_for_timeout(600)
            row('1. the app starts, the plug-in is installed', True, page.evaluate("app.store.project.sims.length + ' sim(s) in the scene'"))
            css = page.evaluate("!!document.querySelector('link[href$=\"features/mocapfile.css\"]')")
            row('1. its stylesheet is linked', css)

            # 2. Pose step
            page.evaluate("app.showStep('pose')")
            page.wait_for_selector('[data-mocapfile="open"]', timeout=30000)
            where = page.evaluate("""(() => { const b = document.querySelector('[data-mocapfile="open"]');
                const prev = b.previousElementSibling; return prev ? prev.className + ' | ' + b.closest('.section, section, div').textContent.slice(0, 60) : 'none'; })()""")
            row('2. Pose step: the button sits right under "Copy real moves"', 'cap-entry' in where, where)
            page.evaluate("document.querySelector('[data-mocapfile=\"open\"]').scrollIntoView({block: 'center'})")
            page.wait_for_timeout(300)
            page.screenshot(path=os.path.join(a.shots, 'pose_step.png'))
            page.click('[data-mocapfile="open"]')
            page.wait_for_selector('.mf-dialog .mf-drop', timeout=30000)
            disabled = page.evaluate("document.querySelector('.mf-dialog footer .btn.primary').disabled")
            row('2. the dialog opens on "choose a file"; Make keys waits for one', disabled)
            page.screenshot(path=os.path.join(a.shots, 'dialog_pick.png'))

            # 3. a file, then keys
            page.set_input_files('.mf-dialog .mf-input', os.path.join(FIX, 'body_mixamo_4s.bvh'))
            page.wait_for_selector('.mf-dialog .mf-canvas', timeout=15000)
            facts = page.inner_text('.mf-dialog .mf-facts')
            row('3. the file is read and described', 'Mixamo skeleton' in facts and '121 frames at 30 fps' in facts and 'T-pose' in facts, facts.replace('\n', ' / '))
            time.sleep(0.4)
            page.screenshot(path=os.path.join(a.shots, 'dialog_file.png'))
            before = page.evaluate("app.store.project.sims.map(s => s.keys.length)")
            n0 = page.evaluate("(window.__toastLog || []).length")
            page.click('.mf-dialog footer .btn.primary')
            page.wait_for_selector('.mf-dialog', state='detached', timeout=30000)
            after = page.evaluate("({keys: app.store.project.sims.map(s => s.keys.length), length: app.store.project.length, sel: app.store.selected.sim, "
                                  "first: app.store.project.sims[0] && app.store.project.sims[0].keys[0] && Object.keys(app.store.project.sims[0].keys[0].pose.rot).length})")
            try:
                page.wait_for_function("n0 => /^Made /.test((window.__toastLog || []).slice(n0).join(' '))", arg=n0, timeout=15000)
            except Exception:
                pass
            toast = page.evaluate("n0 => (window.__toastLog || []).slice(n0).join(' | ')", n0)
            row('3. Make keys: keys on the sim, a toast says so', after['keys'] and after['keys'][0] > 0 and 'Made' in toast,
                'keys %s -> %s, %s bones in a key, length %s; toast: %s' % (before, after['keys'], after['first'], after['length'], toast.strip()[:120]))
            row('3. the animation takes the loop\'s length (a 2 s cycle)', abs(after['length'] - 60) <= 3, after['length'])
            page.screenshot(path=os.path.join(a.shots, 'after_keys.png'))
            page.evaluate("document.activeElement && document.activeElement.blur && document.activeElement.blur()")
            page.keyboard.press('Control+z')
            time.sleep(0.3)
            undone = page.evaluate("app.store.project.sims.map(s => s.keys.length)")
            # an empty scene gets a sim for the moves: Ctrl+Z takes the moves back and leaves it in its starting pose
            row('3. one Ctrl+Z takes it back', undone == (before or [1]), '%s -> %s' % (after['keys'], undone))

            # 4. Ctrl+K
            page.keyboard.press('Control+k')
            page.wait_for_timeout(300)
            page.keyboard.type('motion file')
            page.wait_for_timeout(300)
            listed = page.evaluate("[...document.querySelectorAll('.palette-item')].map(li => li.innerText.replace(/\\s+/g, ' ')).filter(t => /motion file/i.test(t)).slice(0, 3)")
            page.evaluate("[...document.querySelectorAll('.palette-item')].find(li => /Import a motion file/.test(li.innerText)).click()")
            try:
                page.wait_for_selector('.mf-dialog', timeout=15000)
                opened = True
            except Exception:
                opened = False
            row('4. Ctrl+K "motion file" finds the command and opens the dialog', opened and listed, listed)
            page.keyboard.press('Escape')
            page.wait_for_selector('.mf-dialog', state='detached', timeout=15000)
            row('4. Esc closes it', True)

            # 5. Library
            page.evaluate("app.showStep('library')")
            page.wait_for_selector('[data-mocapfile="library"]', timeout=30000)
            page.evaluate("document.querySelector('[data-mocapfile=\"library\"]').scrollIntoView({block: 'center'})")
            row('5. the Library has the "Import a motion file" card', page.is_visible('[data-mocapfile="library"]'))
            page.screenshot(path=os.path.join(a.shots, 'library.png'))
            page.evaluate("app.library.stopPreview && app.showStep('scene')")

            # 6. FBX: two animations, pick the second, make keys, undo
            page.evaluate("app.showStep('pose')")
            page.wait_for_selector('[data-mocapfile="open"]', timeout=30000)
            page.click('[data-mocapfile="open"]')
            page.wait_for_selector('.mf-dialog .mf-drop', timeout=30000)
            page.set_input_files('.mf-dialog .mf-input', os.path.join(FIX, 'body_two_stacks.fbx'))
            try:
                page.wait_for_selector('.mf-dialog .mf-canvas', timeout=30000)
                facts = page.inner_text('.mf-dialog .mf-facts')
                stacks = page.evaluate("[...document.querySelectorAll('.mf-dialog .mf-stack option')].map(o => o.textContent)")
            except Exception as e:
                facts, stacks = 'not read: %s | %s' % (str(e).splitlines()[0], page.inner_text('.mf-dialog')[:300]), []
            row('6. FBX: read and described, both animations listed', 'FBX file (binary)' in facts and 'Mixamo skeleton' in facts and len(stacks) == 2,
                '%s | %s' % (facts.replace('\n', ' / '), stacks))
            page.select_option('.mf-dialog .mf-stack', '1')
            page.wait_for_function("document.querySelector('.mf-dialog .mf-stack') && document.querySelector('.mf-dialog .mf-stack').value === '1'", timeout=30000)
            time.sleep(0.4)
            page.screenshot(path=os.path.join(a.shots, 'dialog_fbx.png'))
            before = page.evaluate("app.store.project.sims.map(s => s.keys.length)")
            page.evaluate("(() => { const s = document.querySelector('.mf-dialog'); for (const sel of s.querySelectorAll('select')) if ([...sel.options].some(o => o.value === 'none')) { sel.value = 'none'; sel.dispatchEvent(new Event('change')); } })()")
            n0 = page.evaluate("(window.__toastLog || []).length")
            page.click('.mf-dialog footer .btn.primary')
            page.wait_for_selector('.mf-dialog', state='detached', timeout=30000)
            after = page.evaluate("({keys: app.store.project.sims.map(s => s.keys.length), length: app.store.project.length})")
            try:
                page.wait_for_function("n0 => /^Made /.test((window.__toastLog || []).slice(n0).join(' '))", arg=n0, timeout=15000)
            except Exception:
                pass
            toast = page.evaluate("n0 => (window.__toastLog || []).slice(n0).join(' | ')", n0)
            row('6. FBX: "Walk" put on as keys (the still "Idle" would need 1-2), a toast says so',
                after['keys'][0] > 3 and 'from body_two_stacks.fbx' in toast,
                'keys %s -> %s, length %s; toast: %s' % (before, after['keys'], after['length'], toast.strip()[:110]))
            page.evaluate("document.activeElement && document.activeElement.blur && document.activeElement.blur()")
            page.keyboard.press('Control+z')
            time.sleep(0.3)
            undone = page.evaluate("app.store.project.sims.map(s => s.keys.length)")
            row('6. FBX: one Ctrl+Z takes it back', undone == before, '%s -> %s' % (after['keys'], undone))
            page.evaluate("document.querySelector('.choice-bar, .choicebar') && document.querySelector('.choice-bar, .choicebar').remove()")

            # dropped on the stage: a binary .fbx, then one without animation
            def drop(name):
                data = list(open(os.path.join(FIX, name), 'rb').read())
                page.evaluate("""([name, bytes]) => { const dt = new DataTransfer(); dt.items.add(new File([new Uint8Array(bytes)], name));
                    const w = document.getElementById('viewport-wrap') || document.body;
                    w.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true })); }""", [name, data])
            page.evaluate("app.showStep('scene')")
            drop('body_mixamo_binary.fbx')
            try:
                page.wait_for_selector('.mf-dialog .mf-canvas', timeout=30000)
                facts = page.inner_text('.mf-dialog .mf-facts')
            except Exception as e:
                facts = 'no dialog: %s' % str(e).splitlines()[0]
            row('6. a binary .fbx dropped on the stage opens the dialog with it', 'FBX file (binary)' in facts and '31 frames at 30 fps' in facts, facts.replace('\n', ' / '))
            drop('skeleton_only.fbx')
            try:
                page.wait_for_selector('.mf-dialog .mf-msg.err', timeout=15000)
                msg = page.inner_text('.mf-dialog .mf-msg.err')
            except Exception as e:
                msg = 'no message: %s' % str(e).splitlines()[0]
            row('6. an .fbx without animation: a plain message, "Make keys" off', 'no animation' in msg and page.evaluate("document.querySelector('.mf-dialog footer .btn.primary').disabled"), msg[:160])
            page.screenshot(path=os.path.join(a.shots, 'dialog_fbx_noanim.png'))
            page.keyboard.press('Escape')
            browser.close()
    finally:
        server.terminate()
        try:
            server.wait(10)
        except subprocess.TimeoutExpired:
            server.kill()

    # without The Sims 4 (and offline) these resources can't load; they are the app's, not this feature's
    no_game = re.compile(r'/api/(sounds|tones|effects|hair_presets|furniture_mesh|skin|poses|library|animation|tray|exports|my_poses|projects)\b'
                         r'|fonts\.(googleapis|gstatic)\.com')
    expected = [(t, x, u) for t, x, u in logs if t == 'error' and x.startswith('Failed to load resource') and no_game.search(u)]
    errors = [(t, x, u) for t, x, u in logs if t in ('error', 'pageerror') and (t, x, u) not in expected]
    row('no console errors or page errors', not errors, '; '.join('%s %s' % (x[:140], u[-60:]) for t, x, u in errors[:6])
        or '%d console lines; %d resource loads that need the game or the internet were left out' % (len(logs), len(expected)))
    row('nothing was written (writing requests answered in the browser)', True, '%d answered: %s' % (len(writes), sorted({w.split('/api/')[1].split('?')[0] for w in writes})))
    w = max(len(n) for n, _, _ in rows)
    print('\nImport a motion file - browser smoke test\n' + '-' * (w + 20))
    for n, ok, d in rows:
        print('%s  %s  %s' % ('PASS' if ok else 'FAIL', n.ljust(w), d[:200]))
    bad = sum(1 for _, ok, _ in rows if not ok)
    print('-' * (w + 20) + '\n%d PASS, %d FAIL   (screenshots: %s)' % (len(rows) - bad, bad, a.shots))
    for t, x, u in errors:
        print('  [%s] %s %s' % (t, x[:300], u))
    if '--verbose' in sys.argv:
        for u in bad_urls:
            print('  [http] %s' % u[:200])
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
