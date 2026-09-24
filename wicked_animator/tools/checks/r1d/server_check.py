"""R1-D server checks (build_plan R1-D checks 1 and 2).

    python tools/checks/r1d/server_check.py --port 8844

1. Server: MIME types for .mjs/.wasm, the CSP header, add-on routes (GET, POST, POST_RAW, errors, name clashes, WARM),
   /api/features. The temporary files it makes are inert (ext routes are named zz_check_*, the feature module does
   nothing unless the page sets window.__zzCheck) and are deleted at the end.
2. Installer against a mock HTTP server on a temporary port (WICKED_CAPTURE_FILES): a good hash installs, a bad hash
   leaves no file, a second run skips finished files, an interrupted run resumes, only the named tar members are
   written, capture_status reports progress. Nothing is downloaded from the internet and nothing is written into
   web/vendor/mediapipe (every install goes into %TEMP%).
Outputs: cache/checks/r1d/server_check.json (+ the PASS/FAIL table on stdout). Exit 0 only when everything passes.
"""
import argparse, base64, hashlib, http.server, importlib, io, json, os, shutil, socket, sys, tarfile, tempfile
import threading, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
BACKEND = os.path.join(ROOT, 'backend')
OUT = os.path.join(ROOT, 'cache', 'checks', 'r1d')
sys.path.insert(0, os.path.join(ROOT, 'tools', 'checks', 'lib'))
sys.path.insert(0, BACKEND)
import harness as H  # noqa: E402

ROWS = []


def row(name, ok, detail=''):
    ROWS.append({'name': name, 'ok': bool(ok), 'detail': detail})
    return ok


# ---------------------------------------------------------------------------------------------------- http helpers
def req(port, path, method='GET', body=None, ctype=None, headers=None):
    url = 'http://127.0.0.1:%d%s' % (port, path)
    data = body if isinstance(body, (bytes, type(None))) else json.dumps(body).encode('utf-8')
    r = urllib.request.Request(url, data=data, method=method)
    if ctype:
        r.add_header('Content-Type', ctype)
    for k, v in (headers or {}).items():
        r.add_header(k, v)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as ex:
        return ex.code, dict(ex.headers), ex.read()


def js(b):
    try:
        return json.loads(b.decode('utf-8'))
    except Exception:
        return None


# ---------------------------------------------------------------------------------------------------- mock server
class Mock:
    """A tiny file server on 127.0.0.1 with Range support, a one-time cut-off and a speed limit per file."""

    def __init__(self):
        self.files, self.cut, self.slow, self.log = {}, {}, {}, []
        mock = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, *a):
                pass

            def do_GET(self):
                path = self.path.split('?')[0]
                rng = self.headers.get('Range')
                mock.log.append({'path': path, 'range': rng})
                data = mock.files.get(path)
                if data is None:
                    self.send_response(404); self.send_header('Content-Length', '0'); self.end_headers(); return
                start = 0
                if rng and rng.startswith('bytes='):
                    start = int(rng[6:].split('-')[0])
                    if start >= len(data):
                        self.send_response(416); self.send_header('Content-Length', '0'); self.end_headers(); return
                    self.send_response(206)
                    self.send_header('Content-Range', 'bytes %d-%d/%d' % (start, len(data) - 1, len(data)))
                else:
                    self.send_response(200)
                body = data[start:]
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Content-Type', 'application/octet-stream')
                self.end_headers()
                cut = mock.cut.pop(path, None)                  # one time only: drop the line after N bytes
                limit = len(body) if cut is None else max(0, cut - start)
                sent, step = 0, 65536
                while sent < limit:
                    n = min(step, limit - sent)
                    try:
                        self.wfile.write(body[sent:sent + n])
                    except OSError:
                        return
                    sent += n
                    if path in mock.slow:
                        time.sleep(n / mock.slow[path])
                if cut is not None:
                    self.close_connection = True
                    try:
                        self.wfile.flush()
                        self.connection.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass

        self.httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def url(self, path):
        return 'http://127.0.0.1:%d%s' % (self.port, path)

    def stop(self):
        self.httpd.shutdown()


def b64(kind, data):
    return base64.b64encode(hashlib.new(kind, data).digest()).decode('ascii')


def make_tarball():
    """A fake npm tarball: the three wanted files plus files that must NOT be written."""
    members = {
        'package/vision_bundle.mjs': b'export const fake = 1;\n' * 50,
        'package/wasm/vision_wasm_internal.js': b'// loader\n' * 300,
        'package/wasm/vision_wasm_internal.wasm': os.urandom(200000),
        'package/wasm/vision_wasm_nosimd_internal.wasm': os.urandom(1000),    # not wanted
        'package/README.md': b'# readme\n',                                   # not wanted
        'package/../escape.txt': b'must never be written\n',                  # not wanted (path escape)
    }
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w:gz') as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue(), members


def table(mock, tgz, members, models, bad_hash=False):
    t = [{'name': 'MediaPipe runtime', 'kind': 'tar', 'part': 'tasks-vision-test.tgz', 'url': mock.url('/tasks-vision.tgz'),
          'size': None, 'approx': len(tgz), 'hash': 'sha512', 'value': b64('sha512', tgz),
          'members': [{'member': m, 'dest': m[len('package/'):], 'size': len(members[m])}
                      for m in ('package/vision_bundle.mjs', 'package/wasm/vision_wasm_internal.js',
                                'package/wasm/vision_wasm_internal.wasm')]}]
    for name, data in models.items():
        t.append({'name': name, 'dest': 'models/' + name, 'size': len(data), 'hash': 'md5',
                  'value': 'AAAAAAAAAAAAAAAAAAAAAA==' if bad_hash else b64('md5', data), 'url': mock.url('/models/' + name)})
    return t


def write_table(path, root, files):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'root': root, 'files': files}, f)


def all_files(root):
    out = set()
    for d, _, fs in os.walk(root):
        for f in fs:
            out.add(os.path.relpath(os.path.join(d, f), root).replace('\\', '/'))
    return out


# ---------------------------------------------------------------------------------------------------- 2. installer
def check_installer(tmp, mock):
    tgz, members = make_tarball()
    models = {'pose_test.task': os.urandom(1500000), 'face_test.task': os.urandom(300000)}
    mock.files['/tasks-vision.tgz'] = tgz
    for n, d in models.items():
        mock.files['/models/' + n] = d
    tpath = os.path.join(tmp, 'table.json')
    os.environ['WICKED_CAPTURE_FILES'] = tpath
    import capture_install as CI
    importlib.reload(CI)

    # a) good hashes install
    root = os.path.join(tmp, 'good')
    write_table(tpath, root, table(mock, tgz, members, models))
    st = CI.install()
    got_ok = st and st['installed'] and not st['error']
    same = all(open(os.path.join(root, m[len('package/'):]), 'rb').read() == members[m]
               for m in ('package/vision_bundle.mjs', 'package/wasm/vision_wasm_internal.js', 'package/wasm/vision_wasm_internal.wasm'))
    same = same and all(open(os.path.join(root, 'models', n), 'rb').read() == d for n, d in models.items())
    row('2a good hash installs', got_ok and same, {'installed': st and st['installed'], 'error': st and st['error'], 'content_equal': same})

    # b) only the named tar members are written (and nothing outside the folder)
    files = all_files(root)
    want = {'vision_bundle.mjs', 'wasm/vision_wasm_internal.js', 'wasm/vision_wasm_internal.wasm',
            'models/pose_test.task', 'models/face_test.task', 'manifest.json'}
    escaped = os.path.exists(os.path.join(tmp, 'escape.txt')) or os.path.exists(os.path.join(root, '..', 'escape.txt'))
    man = json.load(open(os.path.join(root, 'manifest.json'), encoding='utf-8'))
    row('2b only the named tar members are written', files == want and not escaped and man.get('version') == '1.0.1',
        {'files': sorted(files), 'extra': sorted(files - want), 'missing': sorted(want - files), 'escaped': escaped,
         'manifest_version': man.get('version')})

    # c) a second run skips finished files (no request at all)
    mock.log.clear()
    st2 = CI.install()
    row('2c second run skips finished files', st2['installed'] and not mock.log, {'requests': mock.log[:5]})

    # d) a bad hash leaves no file (neither the file nor its .part)
    root_bad = os.path.join(tmp, 'bad')
    write_table(tpath, root_bad, [x for x in table(mock, tgz, members, models, bad_hash=True) if x.get('kind') != 'tar'])
    st3 = CI.install()
    left = all_files(root_bad) if os.path.isdir(root_bad) else set()
    row('2d bad hash leaves no file', (not st3['installed']) and 'damaged' in (st3['error'] or '') and not left,
        {'error': st3['error'], 'files_left': sorted(left)})

    # e) an interrupted run resumes (Range from where it stopped; the result is whole and right)
    root_res = os.path.join(tmp, 'resume')
    big = {'pose_test.task': models['pose_test.task']}
    write_table(tpath, root_res, [x for x in table(mock, tgz, members, big) if x.get('kind') != 'tar'])
    cut_at = 600000
    mock.cut['/models/pose_test.task'] = cut_at
    mock.log.clear()
    st4 = CI.install()
    part = os.path.join(root_res, 'models', 'pose_test.task.part')
    part_size = os.path.getsize(part) if os.path.isfile(part) else 0
    first_failed = (not st4['installed']) and part_size > 0
    mock.log.clear()
    st5 = CI.install()
    ranges = [x['range'] for x in mock.log if x['path'] == '/models/pose_test.task']
    whole = os.path.isfile(os.path.join(root_res, 'models', 'pose_test.task')) and \
        open(os.path.join(root_res, 'models', 'pose_test.task'), 'rb').read() == big['pose_test.task']
    row('2e interrupted run resumes', first_failed and st5['installed'] and whole and ranges == ['bytes=%d-' % part_size]
        and not os.path.exists(part),
        {'first_error': st4['error'], 'part_bytes_after_cut': part_size, 'second_run_ranges': ranges, 'whole_and_equal': whole})
    del os.environ['WICKED_CAPTURE_FILES']
    return tgz, members, models


def check_status_route(port, tmp, mock, tgz, members, models):
    """2f: POST /api/capture_install on a server started with WICKED_CAPTURE_FILES, polling /api/capture_status."""
    root = os.path.join(tmp, 'route')
    slow = {'slow_test.task': os.urandom(3000000)}
    mock.files['/models/slow_test.task'] = slow['slow_test.task']
    mock.slow['/models/slow_test.task'] = 2000000          # about 1.5 s
    write_table(os.path.join(tmp, 'route_table.json'), root, table(mock, tgz, members, slow))
    code, _, b = req(port, '/api/capture_status')
    before = js(b) or {}
    code2, _, b2 = req(port, '/api/capture_install', 'POST', {}, 'application/json')
    started = js(b2) or {}
    seen, t0 = [], time.time()
    while time.time() - t0 < 30:
        _, _, b3 = req(port, '/api/capture_status')
        s = js(b3) or {}
        seen.append((round(time.time() - t0, 2), s.get('busy'), s.get('done_bytes'), s.get('total_bytes')))
        if not s.get('busy') and (s.get('installed') or s.get('error')):
            break
        time.sleep(0.1)
    final = s
    mids = [x for x in seen if x[1] and x[3] and 0 < x[2] < x[3]]
    row('2f capture_status reports progress', code == 200 and code2 == 200 and before.get('installed') is False
        and started.get('busy') is True and len(mids) >= 2 and final.get('installed') is True,
        {'before_missing': before.get('missing'), 'post_busy': started.get('busy'), 'progress_samples': len(mids),
         'first_mid': mids[:1], 'last_mid': mids[-1:], 'final_installed': final.get('installed'), 'error': final.get('error')})
    # the route refuses other web sites
    code3, _, _ = req(port, '/api/capture_install', 'POST', {}, 'application/json', {'Origin': 'http://evil.example'})
    row('2g capture_install refuses other sites', code3 == 403, {'status': code3})


UI_JS = r'''
const H = require(process.argv[2]);
(async () => {
  const port = +process.argv[3], shotFile = process.argv[4];
  const { browser, page, logs } = await H.open(port, {});
  let out = {};
  try {
    out = await page.evaluate(async () => {
      const cap = await import('/js/capture.js');
      const st = cap.openCaptureStudio(window.app, { source: 'video' });
      for (let i = 0; i < 80 && st.step !== 'install'; i++) await new Promise(r => setTimeout(r, 100));
      const first = st.step;
      const btn = document.querySelector('.cap-studio .cap-foot .cap-go');
      btn.click();
      const seen = [];
      const t0 = performance.now();
      let txt = '';
      while (performance.now() - t0 < 40000) {
        txt = (document.querySelector('.cap-bar-text') || {}).textContent || '';
        const bar = document.querySelector('.cap-bar i');
        seen.push([Math.round(performance.now() - t0), txt, bar ? bar.style.transform : '']);
        if (/Ready!/.test(txt) || document.querySelector('.cap-bar-text.err')) break;
        await new Promise(r => setTimeout(r, 120));
      }
      return { first, final: txt, polls: seen.length, partial: seen.filter(x => /^\d+% - /.test(x[1]) && !/^0% /.test(x[1])).length, sample: seen.slice(0, 3).concat(seen.slice(-2)) };
    });
    await H.shot(page, shotFile);
    await new Promise(r => setTimeout(r, 1300));
    out.stepAfter = await page.evaluate(async () => { const s = (await import('/js/capture.js')).studioOpen(); return s && s.step; });
    out.errors = logs.filter(l => l.type === 'pageerror' || l.type === 'error').map(l => l.text).slice(0, 5);
  } catch (e) { out.crash = String(e && e.stack || e); }
  console.log('@@' + JSON.stringify(out));
  await browser.close();
})();
'''


def check_install_ui(port, tmp, mock, tgz, members):
    """2i: the Download button in the studio (not installed yet) fills its bar, says Ready! and goes on to Pick."""
    import subprocess
    root = os.path.join(tmp, 'route_ui')
    slow = {'slow_ui.task': os.urandom(3000000)}
    mock.files['/models/slow_ui.task'] = slow['slow_ui.task']
    mock.slow['/models/slow_ui.task'] = 1500000           # about 2 s, so the bar is seen filling
    write_table(os.path.join(tmp, 'route_table.json'), root, table(mock, tgz, members, slow))
    script = os.path.join(tmp, 'install_ui.js')
    with open(script, 'w', encoding='utf-8') as f:
        f.write(UI_JS)
    shot = os.path.join(OUT, 'studio_0b_download_ready.png')
    harness_js = os.path.join(ROOT, 'tools', 'checks', 'lib', 'harness.js')
    try:
        p = subprocess.run(['node', script, harness_js, str(port), shot], cwd=ROOT, capture_output=True, text=True,
                           timeout=240, encoding='utf-8', errors='replace')
        line = next((x for x in p.stdout.splitlines() if x.startswith('@@')), None)
        res = json.loads(line[2:]) if line else {'stdout': p.stdout[-400:], 'stderr': p.stderr[-400:]}
    except Exception as ex:
        res = {'crash': repr(ex)}
    installed_there = os.path.isfile(os.path.join(root, 'models', 'slow_ui.task'))
    row('2i studio Download button: the bar fills, "Ready!", then Pick (mock server)',
        res.get('first') == 'install' and 'Ready!' in (res.get('final') or '') and res.get('partial', 0) >= 2
        and res.get('stepAfter') == 'pick' and installed_there and not res.get('errors'),
        dict(res, installed_into_temp=installed_there, screenshot=os.path.relpath(shot, ROOT)))


# ---------------------------------------------------------------------------------------------------- 1. server
EXT = r'''"""TEMPORARY file made by tools/checks/r1d/server_check.py - deleted when the check ends. Inert: only zz_check_* routes."""
WARMED = []


def _get(q):
    return {'ok': True, 'q': q}


def _bad(q):
    raise ValueError('That is not a valid thing.')


def _missing(q):
    raise LookupError('Nothing here.')


def _boom(q):
    raise RuntimeError('boom')


def _raw(q):
    return (b'\x89PNG\r\n\x1a\nzz', 'image/png')


def _warm_state(q):
    return {'warmed': bool(WARMED)}


def _post(body, q):
    return {'echo': body, 'q': q}


def _upload(data, ctype, q):
    return {'bytes': len(data), 'type': ctype, 'q': q}


def _clash(*a):
    return {'clash': True}


def _warm():
    WARMED.append(1)


GET = {'zz_check_get': _get, 'zz_check_bad': _bad, 'zz_check_missing': _missing, 'zz_check_boom': _boom,
       'zz_check_raw': _raw, 'zz_check_warm': _warm_state, 'status': _clash}
POST = {'zz_check_post': _post, 'export': _clash}
POST_RAW = {'zz_check_upload': (_upload, ('image/', 'video/'))}
WARM = [_warm]
'''

FEATURE = '''// TEMPORARY file made by tools/checks/r1d/server_check.py - deleted when the check ends.
// Inert: it does nothing unless the page set window.__zzCheck.
export function install(app) { if (window.__zzCheck) window.__zzCheck.ran = true; }
'''


def check_server(port, log_path):
    # MIME types
    code, hd, _ = req(port, '/vendor/zz_check/x.mjs')
    row('1a .mjs is text/javascript', code == 200 and hd.get('Content-Type', '').startswith('text/javascript'), hd.get('Content-Type'))
    code, hd, _ = req(port, '/vendor/zz_check/x.wasm')
    row('1b .wasm is application/wasm', code == 200 and hd.get('Content-Type') == 'application/wasm',
        {'type': hd.get('Content-Type'), 'cache': hd.get('Cache-Control')})
    row('1c /vendor/ files are kept (immutable)', 'immutable' in (hd.get('Cache-Control') or ''), hd.get('Cache-Control'))
    csp = {}
    for p in ('/', '/js/main.js', '/vendor/zz_check/x.mjs'):
        _, h2, _ = req(port, p)
        csp[p] = h2.get('Content-Security-Policy')
    row('1d CSP connect-src on /, .js and .mjs', all(v == "connect-src 'self' blob: data:" for v in csp.values()), csp)

    # add-on routes
    code, _, b = req(port, '/api/zz_check_get?a=1')
    row('1e ext GET answers', code == 200 and js(b) == {'ok': True, 'q': {'a': '1'}}, js(b))
    code, _, b = req(port, '/api/zz_check_post?x=2', 'POST', {'hello': 1}, 'application/json')
    row('1f ext POST answers', code == 200 and js(b) == {'echo': {'hello': 1}, 'q': {'x': '2'}}, js(b))
    code, _, b = req(port, '/api/zz_check_upload?n=3', 'POST', b'\x89PNG\r\n\x1a\n' + b'0' * 100, 'image/png')
    code_bad, _, _ = req(port, '/api/zz_check_upload', 'POST', b'hello', 'text/plain')
    row('1g ext POST_RAW answers (and refuses other types)', code == 200 and (js(b) or {}).get('bytes') == 108
        and (js(b) or {}).get('type') == 'image/png' and code_bad == 415, {'answer': js(b), 'text_plain': code_bad})
    code, _, b = req(port, '/api/zz_check_bad')
    code404, _, b404 = req(port, '/api/zz_check_missing')
    code500, _, _ = req(port, '/api/zz_check_boom')
    row('1h ValueError gives 400 (LookupError 404, other 500)', code == 400 and (js(b) or {}).get('error') == 'That is not a valid thing.'
        and code404 == 404 and code500 == 500, {'400': js(b), '404': js(b404), '500': code500})
    code, hd, b = req(port, '/api/zz_check_raw')
    row('1i (bytes, type) goes out raw', code == 200 and hd.get('Content-Type') == 'image/png' and b.startswith(b'\x89PNG'),
        {'type': hd.get('Content-Type'), 'bytes': len(b)})
    code, _, b = req(port, '/api/status')
    st = js(b) or {}
    log = open(log_path, encoding='utf-8', errors='replace').read() if os.path.isfile(log_path) else ''
    row('1j built-in name clash keeps the built-in', code == 200 and st.get('ok') is True and 'clash' not in st
        and "/api/status is one of the app's own routes" in log and "/api/export is one of the app's own routes" in log,
        {'status_keys': sorted(st)[:8], 'warned': "/api/status is one of the app's own routes" in log})
    code, _, b = req(port, '/api/zz_check_post', 'POST', {'a': 1}, 'application/json', {'Origin': 'http://evil.example'})
    row('1k ext POST keeps the Origin rule', code == 403, {'status': code})
    t0, warmed = time.time(), False
    while time.time() - t0 < 120:
        _, _, b = req(port, '/api/zz_check_warm')
        if (js(b) or {}).get('warmed'):
            warmed = True
            break
        time.sleep(0.5)
    row('1l WARM hooks run in the warm-up', warmed, {'seconds': round(time.time() - t0, 1)})
    code, _, b = req(port, '/api/features')
    f = js(b) or {}
    row('1m /api/features lists web/js/features/zz_check.js', code == 200 and 'zz_check.js' in f.get('js', [])
        and isinstance(f.get('css'), list), f)
    # R1-F's request: a library animation comes with its creator moments (the same list /api/animation_events gives)
    found = None
    for i in range(0, 400, 7):
        c1, _, b1 = req(port, '/api/animation_events?id=%d' % i)
        ev = (js(b1) or {}).get('events') if c1 == 200 else None
        if ev:
            found = (i, ev)
            break
    if found:
        c2, _, b2 = req(port, '/api/animation?id=%d&step=8' % found[0])
        got = (js(b2) or {}).get('events') if c2 == 200 else None
        row('1o /api/animation carries the moments (events)', got == found[1],
            {'id': found[0], 'events': len(found[1]), 'same_as_animation_events': got == found[1]})
    else:
        c2, _, b2 = req(port, '/api/animation?id=0&step=8')
        got = (js(b2) or {}).get('events') if c2 == 200 else None
        row('1o /api/animation carries the moments (events)', isinstance(got, list), {'id': 0, 'events': got, 'note': 'no animation with moments found'})
    # plan 2.7 duty: a Tray sim brings its game voice (read-only on the user's Tray; skipped when it has no sims)
    c, _, b = req(port, '/api/tray')
    hh = js(b) if c == 200 else None
    first = next(((h['id'], s['index']) for h in (hh or []) for s in h.get('sims', [])), None)
    if first:
        c, _, b = req(port, '/api/tray_sim?tray=%s&index=%d' % first)
        s = js(b) or {}
        row('1p tray_sim brings the sim\'s voice and pitch', c == 200 and s.get('voice') in ('fa', 'fc', 'fd', 'ma', 'mb', 'mc')
            and isinstance(s.get('voicePitch'), (int, float)), {'status': c, 'voice': s.get('voice'), 'voicePitch': s.get('voicePitch'),
                                                              'gender': s.get('gender')})
    else:
        row('1p tray_sim brings the sim\'s voice and pitch (no Tray sims here - skipped)', True, {'households': len(hh or [])})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=8844)
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix='wa_r1d_')
    ext_path = os.path.join(BACKEND, 'ext_zz_check.py')
    feat_dir = os.path.join(ROOT, 'web', 'js', 'features')
    feat_path = os.path.join(feat_dir, 'zz_check.js')
    vend = os.path.join(ROOT, 'web', 'vendor', 'zz_check')
    made_feat_dir = not os.path.isdir(feat_dir)
    mock = Mock()
    p = None
    port = a.port
    try:
        with open(ext_path, 'w', encoding='utf-8') as fh:
            fh.write(EXT)
        os.makedirs(feat_dir, exist_ok=True)
        with open(feat_path, 'w', encoding='utf-8') as fh:
            fh.write(FEATURE)
        os.makedirs(vend, exist_ok=True)
        with open(os.path.join(vend, 'x.mjs'), 'w') as fh:
            fh.write('export default 1;\n')
        with open(os.path.join(vend, 'x.wasm'), 'wb') as fh:
            fh.write(b'\x00asm\x01\x00\x00\x00')

        # the installer's route test needs its own table file; the server reads it on every call
        route_table = os.path.join(tmp, 'route_table.json')
        with open(route_table, 'w') as fh:
            json.dump({'root': os.path.join(tmp, 'route'), 'files': []}, fh)
        try:
            p = H.start_server(port, env={'WICKED_CAPTURE_FILES': route_table})
        except H.PortBusy:
            port = H.free_port(8851)
            p = H.start_server(port, env={'WICKED_CAPTURE_FILES': route_table})
        log_path = os.path.join(ROOT, 'cache', 'checks', '_servers', 'port%d.log' % port)

        check_server(port, log_path)
        tgz, members, models = check_installer(tmp, mock)
        check_status_route(port, tmp, mock, tgz, members, models)
        check_install_ui(port, tmp, mock, tgz, members)
        vendor_real = os.path.join(ROOT, 'web', 'vendor', 'mediapipe')
        row('2h nothing was written into web/vendor/mediapipe', sorted(os.listdir(vendor_real)) == ['LICENSE.txt'],
            sorted(os.listdir(vendor_real)))
    finally:
        H.stop_server(p)
        mock.stop()
        for f in (ext_path, feat_path):
            try:
                os.remove(f)
            except OSError:
                pass
        pyc = os.path.join(BACKEND, '__pycache__')
        if os.path.isdir(pyc):
            for f in os.listdir(pyc):
                if f.startswith('ext_zz_check.'):
                    try:
                        os.remove(os.path.join(pyc, f))
                    except OSError:
                        pass
        if made_feat_dir and os.path.isdir(feat_dir) and not os.listdir(feat_dir):
            os.rmdir(feat_dir)
        shutil.rmtree(vend, ignore_errors=True)
        shutil.rmtree(tmp, ignore_errors=True)
    row('1n temporary files removed', not os.path.exists(ext_path) and not os.path.exists(feat_path) and not os.path.exists(vend), '')
    ok = all(r['ok'] for r in ROWS)
    with open(os.path.join(OUT, 'server_check.json'), 'w', encoding='utf-8') as fh:
        json.dump({'port': port, 'ok': ok, 'rows': ROWS, 'time': time.strftime('%Y-%m-%d %H:%M:%S')}, fh, indent=1)
    w = max(len(r['name']) for r in ROWS)
    print('\nR1-D server checks (port %d)' % port)
    for r in ROWS:
        d = r['detail'] if isinstance(r['detail'], str) else json.dumps(r['detail'])
        print('%s  %s  %s' % ('PASS' if r['ok'] else 'FAIL', r['name'].ljust(w), d[:300]))
    bad = sum(not r['ok'] for r in ROWS)
    print('%d PASS, %d FAIL' % (len(ROWS) - bad, bad))
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
