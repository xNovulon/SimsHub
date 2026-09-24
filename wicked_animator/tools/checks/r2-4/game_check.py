"""R2-4 checks: voices, moments, effects and cum on the skin (spec_game 2-5 "Verify", plan R2-4 checks).

    python tools/checks/r2-4/game_check.py [--port 8854] [--pin <dir>] [--no-ui]

Starts backend/server.py on the port (8854, or the next free one above 8870), checks the routes and the backend
(voices, Tray voices, cum layers and textures), runs the browser checks (game_ui_check.js), then builds the 4-moment
proto the app baked into a package offline in %TEMP% and compares its XML with spec_game 3. Nothing is written into
Documents\\Electronic Arts\\The Sims 4. Outputs: cache/checks/r2-4/report.json + report.txt. Exits 0 only when every
item passes.
"""
import argparse, io, json, os, re, socket, subprocess, sys, tempfile, time, urllib.request, urllib.error
sys.dont_write_bytecode = True
import xml.etree.ElementTree as ET

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
BACKEND = os.path.join(ROOT, 'backend')
OUT = os.path.join(ROOT, 'cache', 'checks', 'r2-4')
sys.path.insert(0, BACKEND)
sys.path.insert(0, os.path.join(ROOT, 'tools', 'checks', 'lib'))
import harness as HN

REFUSED = {8765, 8766, 8777, 8802, 8804}
RESULTS = []

# spec_game 3: the XML block for the proto (a CLIMAX, 2 sims)
EXPECTED = '''      <L n="animation_events_list">
        <U>
          <T n="event_type">UNDRESS</T>
          <T n="event_start_timecode">0.5</T>
          <T n="event_target">a1</T>
          <T n="naked_type">TOP</T>
        </U>
        <U>
          <T n="event_type">REMOVE_CONDOM</T>
          <T n="event_start_timecode">1.8</T>
          <T n="event_target">a0</T>
        </U>
        <U>
          <T n="event_type">EFFECT</T>
          <T n="event_start_timecode">2</T>
          <T n="event_end_timecode">3</T>
          <T n="event_target">a0</T>
          <T n="effect_name">pet_small_drool_front</T>
          <T n="effect_joint_name">b__Penis_Tip</T>
          <U n="dont_run_if">
            <T n="actor_has_condom">1</T>
          </U>
        </U>
        <U>
          <T n="event_type">CUM</T>
          <T n="event_start_timecode">2.1</T>
          <T n="event_target">a1</T>
          <T n="cum_layer_type">FACE</T>
          <T n="cum_layer_level">2</T>
        </U>
      </L>'''
# spec_game 5: level-1 rects (u0-u1 / v0-v1) decoded from WickedWhims' Default group, and level 3 where given
SPEC_RECTS = {
    'FACE': {1: (.432, .570, .398, .448), 3: (.354, .612, .336, .448)},
    'CHEST': {1: (.064, .110, .543, .592), 3: (.064, .212, .529, .610)},
    'BELLY': {1: (.088, .126, .628, .694)},
    'UPPER_BACK': {1: (.356, .453, .534, .608)},
    'LOWER_BACK': {1: (.353, .391, .628, .673)},
    'VAGINA': {1: (.106, .131, .708, .724), 3: (.106, .159, .708, .748)},
    'BUTT': {1: (.385, .420, .686, .719)},
    'FEET': {1: (.063, .224, .955, .982)},
}


def check(group, name, ok, detail=''):
    RESULTS.append({'group': group, 'check': name, 'ok': bool(ok), 'detail': str(detail)})
    print('%-4s %-12s %-66s %s' % ('PASS' if ok else 'FAIL', group, name[:66], str(detail)[:160]), flush=True)
    return ok


def guarded(group):
    def deco(fn):
        def run(*a, **k):
            try:
                return fn(*a, **k)
            except Exception as ex:
                import traceback
                traceback.print_exc()
                check(group, fn.__name__ + ' (crashed)', False, repr(ex))
        return run
    return deco


def get(port, route, raw=False, timeout=300):
    try:
        with urllib.request.urlopen('http://127.0.0.1:%d/api/%s' % (port, route), timeout=timeout) as r:
            data = r.read()
            return (r.status, data, r.headers.get('Content-Type')) if raw else json.loads(data.decode('utf-8'))
    except urllib.error.HTTPError as ex:
        if raw:
            return ex.code, ex.read(), ex.headers.get('Content-Type')
        raise


def free(port):
    with socket.socket() as s:
        try:
            s.bind(('127.0.0.1', port))
            return True
        except OSError:
            return False


def start(port):
    if port in REFUSED:
        raise SystemExit('refusing port %d' % port)
    if not free(port) or HN._status(port, 0.5):
        port = next(p for p in range(8871, 8899) if p not in REFUSED and free(p) and not HN._status(p, 0.3))
    return HN.start_server(port, log_dir=OUT), port


# ------------------------------------------------------------------ 1. voices (routes + Tray)
@guarded('1 voices')
def check_voices(port):
    import eaaudio, trayfmt
    from clipfmt import fnv32
    v = get(port, 'voices')
    lines = v['lines']
    check('1 voices', '/api/voices returns >= 5,500 lines', len(lines) >= 5500, len(lines))
    bad = [x['name'] for x in lines if eaaudio._LINE_BLOCK.search(x['name']) or re.search(r'_(ca|cb|pa)$', x['name'])]
    check('1 voices', 'no line matches _LINE_BLOCK, none ends in ca/cb/pa', not bad, bad[:3])
    # Tray sims: their own voice (the light route the Sounds step uses), adults only
    females, males, wrong, kids, kid_refused = 0, 0, [], 0, 0
    for hh in trayfmt.list_households():
        for i, s in enumerate(trayfmt.household_sims(hh['id'])['sims']):
            adult = s.get('age') in ('youngadult', 'adult', 'elder') and s.get('species', 'human') == 'human'
            code, body, _ = get(port, 'tray_voice?tray=%s&index=%d' % (hh['id'], i), raw=True)
            if not adult:
                kids += 1
                kid_refused += code == 404
                continue
            r = json.loads(body.decode('utf-8'))
            want = eaaudio.ADULT_VOICES['male' if s.get('gender') == 'male' else 'female']
            if s.get('gender') == 'male':
                males += 1
            else:
                females += 1
            if r.get('voice') not in want or r.get('voice') != eaaudio.voice_for_actor(s.get('voice_actor'), s.get('gender')):
                wrong.append((s.get('first'), s.get('gender'), r))
    check('1 voices', 'every adult Tray sim: female -> fa/fc/fd, male -> ma/mb/mc (/api/tray_voice)', females and not wrong,
          '%d women, %d men, wrong: %s' % (females, males, wrong[:2]))
    check('1 voices', '/api/tray_voice never answers for a child, teen or pet', kid_refused == kids, '%d/%d refused' % (kid_refused, kids))
    # there is no man in this Tray: the male path of the same function
    ok = all(eaaudio.voice_for_actor(fnv32(c), 'male') == c for c in ('ma', 'mb', 'mc')) and eaaudio.voice_for_actor(None, 'male') == 'ma' \
        and eaaudio.voice_for_actor(fnv32('ca'), 'male') == 'ma'
    check('1 voices', 'a male Tray sim gets ma/mb/mc (his own; none or a child code -> ma)', ok, 'voice_for_actor')
    a = get(port, 'sound?name=vo_expr_moan_pleasure_30f_cm&voice=fa', raw=True)
    b = get(port, 'sound?name=vo_expr_moan_pleasure_30f_cm&voice=ma', raw=True)
    check('1 voices', '/api/sound?voice= gives her and him different takes', a[0] == 200 and b[0] == 200 and a[1] != b[1],
          '%d / %d bytes' % (len(a[1]), len(b[1])))


# ------------------------------------------------------------------ 2. cum layers
@guarded('2 cum')
def check_cum(port):
    import skintex
    from PIL import Image
    L = get(port, 'cum_layers')
    ok = sorted(L) == sorted(skintex.CUM_TYPES) and all(len(L[t]) == 3 and [x['level'] for x in L[t]] == [1, 2, 3] for t in L) \
        and all(0 <= v <= 1 for t in L for x in L[t] for v in x['rect']) and all(x['rect'][0] < x['rect'][2] and x['rect'][1] < x['rect'][3] for t in L for x in L[t])
    check('2 cum', 'cum_layers() has 8 types x 3 levels, rects inside [0, 1]', ok, {t: len(L[t]) for t in L})
    worst = 0.0
    for t, levels in SPEC_RECTS.items():
        for lv, (u0, u1, v0, v1) in levels.items():
            r = L[t][lv - 1]['rect']
            worst = max(worst, abs(r[0] - u0), abs(r[2] - u1), abs(r[1] - v0), abs(r[3] - v1))
    check('2 cum', 'the rects match spec_game 5 (within 0.005 incl. the 2 px pad)', worst <= 0.005, 'worst %.4f' % worst)
    x = L['FACE'][2]
    code, png, ctype = get(port, 'cum_tex?inst=' + x['inst'], raw=True)
    im = Image.open(io.BytesIO(png)) if code == 200 else None
    u0, v0, u1, v1 = x['rect']
    want = (round((u1 - u0) * 1024), round((v1 - v0) * 2048))
    check('2 cum', '/api/cum_tex serves the cropped PNG at atlas size (1024x2048)', code == 200 and ctype == 'image/png' and im.mode == 'RGBA'
          and abs(im.size[0] - want[0]) <= 1 and abs(im.size[1] - want[1]) <= 1, (code, ctype, im and im.size, want))
    alpha = im.getchannel('A') if im else None
    check('2 cum', 'the picture has cum on it (not empty) and a see-through border', alpha and alpha.getbbox() and alpha.getpixel((0, 0)) == 0, alpha and alpha.getbbox())
    code2, _, _ = get(port, 'cum_tex?inst=0123456789abcdef', raw=True)
    code3, _, _ = get(port, 'cum_tex?inst=../../config', raw=True)
    check('2 cum', 'cum_tex: 404 for anything not listed', code2 == 404 and code3 == 404, (code2, code3))
    parts = skintex.cum_parts()
    check('2 cum', "cum_parts() reads WickedWhims' Default group (3 CAS parts per type)", len(parts) == 8 and all(len(v) == 3 for v in parts.values()),
          {k: len(v) for k, v in parts.items()})


# ------------------------------------------------------------------ 3. the proto: XML, round trip, offline package
@guarded('3 moments XML')
def check_proto():
    import exporter, gamedata
    path = os.path.join(OUT, 'proto.baked.json')
    if not os.path.exists(path):
        return check('3 moments XML', 'the app baked the 4-moment proto', False, 'no proto.baked.json (run the browser checks)')
    with open(path, encoding='utf-8') as f:
        baked = json.load(f)
    check('3 moments XML', 'the app baked the 4-moment proto (CLIMAX, 2 sims, a note left out)', len(baked.get('events') or []) == 4 and baked.get('category') == 'CLIMAX',
          [(e['type'], e['target'], e['start']) for e in baked.get('events') or []])
    res, info = exporter.animation_resources(baked, metas={}, present=set())
    import wwpackage as W
    xml = next(d for t, g, i, d in res if t == W.SNIPPET).decode('utf-8')
    with open(os.path.join(OUT, 'proto_snippet.xml'), 'w', encoding='utf-8') as f:
        f.write(xml)
    got = xml[xml.find('      <L n="animation_events_list">'):]
    got = got[:got.find('      </L>') + len('      </L>')] if '      </L>' in got else ''
    check('3 moments XML', 'exporting it gives exactly the spec_game 3 block', got == EXPECTED, 'equal' if got == EXPECTED else 'differs: see proto_snippet.xml')
    root = ET.fromstring(xml.encode('utf-8'))
    an = root.find("L[@n='animations_list']")[0]
    kids = [c.get('n') for c in an]
    check('3 moments XML', 'animation_xml output parses with xml.etree; the list follows the actors',
          kids.index('animation_events_list') == kids.index('animation_actors_list') + 1, kids[-3:])
    back = gamedata.parse_events(an)
    want = sorted(({k: v for k, v in e.items()} for e in baked['events']), key=lambda e: (e['start'], e['type']))
    norm = lambda es: [{k: (round(v, 4) if isinstance(v, float) else v) for k, v in e.items()} for e in es]
    check('3 moments XML', 'gamedata.parse_events on our own export returns the same moments', norm(back) == norm(want),
          'same %d' % len(back) if norm(back) == norm(want) else back)
    check('3 moments XML', 'the export info counts 4 moments, no warnings about them', info.get('events') == 4 and not any('moment' in w for w in info['warnings']),
          (info.get('events'), info['warnings'][:2]))
    out_dir = tempfile.mkdtemp(prefix='r24_proto_')
    pkg = HN.offline_export(baked, out_dir)
    tmp = os.path.normcase(os.path.abspath(tempfile.gettempdir()))
    check('3 moments XML', 'the offline package is built in %TEMP% (never into Mods)', os.path.exists(pkg) and os.path.normcase(pkg).startswith(tmp),
          '%s (%d bytes)' % (pkg, os.path.getsize(pkg)))


# ------------------------------------------------------------------ 4. files: main.js / timeline.js untouched by R2-4
@guarded('4 files')
def check_files():
    mine = re.compile(r"moments\.js|cumskin|effects\.js|EffectLayer|features/game|finishPreset|voicePool\(sim, set\) => ")
    hits = []
    for f in ('web/js/main.js', 'web/js/timeline.js', 'web/index.html', 'web/css/app.css'):
        with open(os.path.join(ROOT, f), encoding='utf-8') as fh:
            text = fh.read()
        hits += ['%s: %s' % (f, m.group(0)) for m in mine.finditer(text)]
    check('4 files', 'no R2-4 code in main.js, timeline.js, index.html or app.css (it plugs in through the hooks)', not hits, hits[:3])
    for f in ('web/js/audio.js', 'web/js/moments.js', 'web/js/effects.js', 'web/js/cumskin.js', 'web/js/features/game.js',
              'web/js/steps/sounds.js', 'web/js/dialogs/sound.js', 'web/js/details.js'):
        r = subprocess.run(['node', '--check', os.path.join(ROOT, f)], capture_output=True, text=True)
        check('4 files', 'syntax: %s' % f, r.returncode == 0, (r.stderr or '').strip()[:200])
    for f in ('backend/skintex.py', 'backend/ext_game.py'):
        try:
            import ast
            with open(os.path.join(ROOT, f), encoding='utf-8') as fh:
                ast.parse(fh.read())
            check('4 files', 'syntax: %s' % f, True)
        except SyntaxError as ex:
            check('4 files', 'syntax: %s' % f, False, ex)


def run_ui(port, pin):
    cmd = ['node', os.path.join(os.path.dirname(__file__), 'game_ui_check.js'), str(port)] + (['--pin', pin] if pin else [])
    print('\n$ ' + ' '.join(cmd), flush=True)
    t0 = time.time()
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=1800)
    with open(os.path.join(OUT, 'ui_check.log'), 'w', encoding='utf-8') as f:
        f.write(r.stdout + '\n' + r.stderr)
    try:
        with open(os.path.join(OUT, 'ui_report.json'), encoding='utf-8') as f:
            rep = json.load(f)
    except Exception as ex:
        return check('5 browser', 'the browser checks ran', False, '%s: %s' % (ex, (r.stderr or r.stdout)[-300:]))
    for row in rep['rows']:
        check('5 browser', row['name'], row['ok'], json.dumps(row.get('detail'))[:300] if row.get('detail') is not None else '')
    check('5 browser', 'browser checks: %d passed, %d failed (%.0f s)' % (rep['passed'], rep['failed'], time.time() - t0), rep['failed'] == 0 and r.returncode == 0,
          'see ui_check.log')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=8854)
    ap.add_argument('--pin', default=None, help='serve these web files instead of the live ones (development only)')
    ap.add_argument('--no-ui', action='store_true')
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    t0 = time.time()
    server, port = start(a.port)
    print('server on port %d (pid %d)' % (port, server.pid), flush=True)
    try:
        check_voices(port)
        check_cum(port)
        if not a.no_ui:
            run_ui(port, a.pin)
        check_proto()
        check_files()
    finally:
        HN.stop_server(server)
    passed = sum(r['ok'] for r in RESULTS)
    summary = {'passed': passed, 'failed': len(RESULTS) - passed, 'seconds': round(time.time() - t0, 1), 'port': port, 'pinned': bool(a.pin),
               'results': RESULTS}
    with open(os.path.join(OUT, 'report.json'), 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=1)
    with open(os.path.join(OUT, 'report.txt'), 'w', encoding='utf-8') as f:
        for r in RESULTS:
            f.write('%-4s %-12s %-66s %s\n' % ('PASS' if r['ok'] else 'FAIL', r['group'], r['check'][:66], r['detail'][:300]))
        f.write('\n%d passed, %d failed in %.0f s (port %d%s)\n' % (passed, len(RESULTS) - passed, summary['seconds'], port, ', pinned files' if a.pin else ''))
    print('\n%d passed, %d failed in %.0f s' % (passed, len(RESULTS) - passed, summary['seconds']))
    sys.exit(0 if passed == len(RESULTS) and RESULTS else 1)


if __name__ == '__main__':
    main()
