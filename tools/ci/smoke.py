"""Boot smoke test for both apps, in a real headless browser (Playwright + Chromium).

Starts each app the way a person would - or its stand-in for what it needs and doesn't have here - opens it, visits
every page, and fails loudly if anything stops it from rendering. This is the check that would have caught
wicked_animator/web/js/home.js's lost ')' (Sep 2026): it froze the animator on "Could not start" for every user,
because nothing had opened it in a real page before that file reached everyone through main.

    python tools/ci/smoke.py                 both apps (the default)
    python tools/ci/smoke.py --hub            just the Hub
    python tools/ci/smoke.py --animator       just the animator
    python tools/ci/smoke.py --shots DIR      save a last screenshot of each app there

Runs the same way on Windows (this PC) and on CI (.github/workflows/dev-gate.yml). Needs Playwright's Python package
and its Chromium (`pip install playwright && python -m playwright install chromium`). Ports are picked free, and
never 8765/8766/8777 - the user's own installed apps, and the animator's own checks, use those. Exit code 0 means
everything passed.
"""
import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HUB = os.path.join(ROOT, 'sims_hub')
ANIMATOR = os.path.join(ROOT, 'wicked_animator')
REFUSED = {8765, 8766, 8777}   # the user's Wicked Animator, their Sims Hub, and the animator's own check harness

rows = []


def row(name, ok, detail=''):
    rows.append((name, bool(ok), str(detail)))
    return ok


def free_port():
    while True:
        s = socket.socket()
        s.bind(('127.0.0.1', 0))
        port = s.getsockname()[1]
        s.close()
        if port not in REFUSED:
            return port


def wait_http(url, ready, timeout=20):
    """Polls url until ready(body_bytes) is true; raises with the last problem seen otherwise."""
    deadline = time.time() + timeout
    last = 'no answer yet'
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as r:
                if ready(r.read()):
                    return
                last = 'answered, but not ready yet'
        except Exception as e:
            last = str(e)
        time.sleep(0.15)
    raise RuntimeError('%s: %s' % (url, last))


def stop(proc):
    proc.terminate()
    try:
        proc.wait(10)
    except subprocess.TimeoutExpired:
        proc.kill()


# ---------------------------------------------------------------------------------------------- the Hub
def check_hub(shots):
    from playwright.sync_api import sync_playwright

    port = free_port()
    env = dict(os.environ, SIMS_HUB_STUB_DELAY='0.02', PYTHONPATH=HUB)
    proc = subprocess.Popen([sys.executable, '-m', 'speedkit.hub', '--serve', '--stub', '--port', str(port)],
                            cwd=HUB, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = 'http://127.0.0.1:%d/' % port
    try:
        try:
            wait_http(base + 'api/ping', lambda b: json.loads(b).get('engine') == 'stub', timeout=30)
        except Exception as e:
            row('Hub: the stub server starts', False, str(e))
            return
        row('Hub: the stub server starts', True, base)

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            try:
                page = browser.new_page(viewport={'width': 1440, 'height': 1100})
                errors = []
                # only 127.0.0.1 is reachable - the web font fails quietly, as it does offline for a real user
                page.route('**/*', lambda r: r.continue_() if r.request.url.startswith(base) else r.abort())
                page.on('pageerror', lambda e: errors.append('pageerror: ' + str(e)))
                page.on('console', lambda m: errors.append('console: ' + m.text)
                        if m.type == 'error' and 'net::ERR_FAILED' not in m.text else None)
                for name in ('home', 'saves', 'library', 'performance', 'tools'):
                    try:
                        page.goto(base + '#' + name, timeout=20000)
                        # the page's own head element (title + intro line), or Home's (its own markup) - the
                        # convention this repo's own UI tests already use (tests/test_care_ui.py CareUI.open)
                        page.wait_for_selector('#page .page-head, #page .hello', timeout=15000)
                        row('Hub: #%s renders' % name, True)
                    except Exception as e:
                        row('Hub: #%s renders' % name, False, str(e).splitlines()[0])
                if shots:
                    page.screenshot(path=os.path.join(shots, 'hub_last.png'))
                row('Hub: no script errors on any page', not errors, ' | '.join(errors[:6]))
                page.close()
            finally:
                browser.close()
    finally:
        stop(proc)


# ---------------------------------------------------------------------------------------------- the animator
def three_dir():
    """A local three.js 0.160 build (WA_THREE_DIR, or the 'three' package from npm), or None to use the CDN (fine on
    CI, which has internet; tools/checks/lib/pw.js does the same thing for the animator's own checks)."""
    tries = [os.environ.get('WA_THREE_DIR')]
    try:
        out = subprocess.run(['npm', 'root', '-g'], capture_output=True, text=True, check=True, shell=(os.name == 'nt'))
        tries.append(os.path.join(out.stdout.strip(), 'three'))
    except Exception:
        pass
    for d in tries:
        if d and os.path.isfile(os.path.join(d, 'build', 'three.module.js')):
            return os.path.abspath(d)
    return None


def check_animator(shots):
    from playwright.sync_api import sync_playwright

    port = free_port()
    env = dict(os.environ, ANIMATOR_PORT=str(port), PYTHONUNBUFFERED='1')
    server_script = os.path.join(ANIMATOR, 'tools', 'checks', 'lib', 'fake_game_server.py')
    proc = subprocess.Popen([sys.executable, server_script], cwd=ANIMATOR, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = 'http://127.0.0.1:%d' % port
    try:
        try:
            wait_http(base + '/api/status', lambda b: True, timeout=30)
        except Exception as e:
            row('Animator: the stand-in game server starts', False, str(e))
            return
        row('Animator: the stand-in game server starts', True, base)

        with sync_playwright() as pw:
            browser = pw.chromium.launch(args=['--use-gl=swiftshader', '--enable-webgl', '--ignore-gpu-blocklist'])
            try:
                page = browser.new_page(viewport={'width': 1366, 'height': 768})
                errors = []
                page.on('pageerror', lambda e: errors.append('pageerror: ' + str(e)))
                page.on('console', lambda m: errors.append('console: ' + m.text) if m.type == 'error' else None)
                page.add_init_script("try { localStorage.setItem('fsa.tourDone', 'true'); "
                                      "localStorage.removeItem('fsa.autosave'); } catch (e) {}")
                three = three_dir()
                if three:
                    def cdn(route):
                        rel = route.request.url.split('/three@0.160.0/', 1)[1].split('?')[0]
                        f = os.path.join(three, *rel.split('/'))
                        if os.path.isfile(f):
                            route.fulfill(status=200, content_type='application/javascript', body=open(f, 'rb').read())
                        else:
                            route.fulfill(status=404, body='')
                    page.route('https://cdn.jsdelivr.net/npm/three@0.160.0/**', cdn)

                page.goto(base + '/?slot=test', wait_until='domcontentloaded', timeout=30000)
                started = False
                try:
                    page.wait_for_selector('#loading.done', state='attached', timeout=45000)
                    started = page.evaluate('!!window.app')
                    row('Animator: the app starts (#loading.done, window.app)', started)
                except Exception as e:
                    text = ''
                    try:
                        text = page.inner_text('#loading-text')
                    except Exception:
                        pass
                    row('Animator: the app starts (#loading.done, window.app)', False, (text or str(e)).splitlines()[0])

                shown = ''
                try:
                    shown = page.inner_text('#loading-text')
                except Exception:
                    pass
                row('Animator: no "Could not start"', 'Could not start' not in shown, shown)

                if started:
                    try:
                        page.wait_for_selector('#home .home-top', timeout=10000)
                        row('Animator: the Home screen renders (#home .home-top)', True)
                    except Exception as e:
                        row('Animator: the Home screen renders (#home .home-top)', False, str(e).splitlines()[0])

                if shots:
                    page.screenshot(path=os.path.join(shots, 'animator_last.png'))
                # a font that never loads (no internet on some CI runners) or a GPU stall in software rendering are
                # the app's environment, not its code - the same allowances tools/checks/wired/ui_smoke.js makes
                ignore = ('Failed to load resource', 'fonts.googleapis', 'fonts.gstatic', 'swiftshader', 'GroupMarkerNotSet')
                bad = [e for e in errors if not any(s in e for s in ignore)]
                row('Animator: no other page errors', not bad, ' | '.join(bad[:6]))
                page.close()
            finally:
                browser.close()
    finally:
        stop(proc)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--hub', action='store_true', help='just the Hub')
    ap.add_argument('--animator', action='store_true', help='just the animator')
    ap.add_argument('--shots', default=None, help='folder to save a last screenshot of each app in')
    a = ap.parse_args()
    both = not a.hub and not a.animator
    if a.shots:
        os.makedirs(a.shots, exist_ok=True)

    if a.hub or both:
        check_hub(a.shots)
    if a.animator or both:
        check_animator(a.shots)

    w = max((len(n) for n, _ok, _d in rows), default=10)
    print('\nBoot smoke test\n' + '-' * min(160, w + 20))
    for n, ok, d in rows:
        print('%s  %s  %s' % ('PASS' if ok else 'FAIL', n.ljust(w), d[:300]))
    bad = sum(1 for _n, ok, _d in rows if not ok)
    print('-' * min(160, w + 20) + '\n%d PASS, %d FAIL' % (len(rows) - bad, bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
