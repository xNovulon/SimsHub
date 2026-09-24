"""R2-4 fix: every adult Tray sim shows its own skin tone (game, pack or custom content), or a stand-in - never white.

    python tools/checks/r2-4/skin_tones.py [--port 8883] [--no-shots]

Starts backend/server.py on port 8883 (ANIMATOR_PORT; saves and exports point at a folder in %TEMP%), then for ALL
adult Tray sims asks /api/tray -> /api/tray_sim -> /api/skin and counts how many show their real tone, how many a
stand-in, and how many errors (must be 0). Every skin must look like skin (not white). Then 2 Tray sims the app could
not texture before (one whose CC tone is in Mods_parked, one whose CC tone is installed nowhere) are opened in the app
at 1366x768 (tools/checks/lib/harness.js, 2 screenshots each). Read-only on the game, Mods, Mods_parked and Tray.
Outputs: cache/checks/r2-4/skin_tones.json + skin_tones.txt + skin_tone_*.png. Exits 0 only when every item passes.
"""
import argparse, io, json, os, socket, subprocess, sys, tempfile, time, urllib.request, urllib.error
sys.dont_write_bytecode = True
for _s in (sys.stdout, sys.stderr):          # sims' names may use any letters
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
BACKEND = os.path.join(ROOT, 'backend')
OUT = os.path.join(ROOT, 'cache', 'checks', 'r2-4')
sys.path.insert(0, BACKEND)
sys.path.insert(0, os.path.join(ROOT, 'tools', 'checks', 'lib'))
import harness as HN

REFUSED = {8765, 8766, 8777, 8802, 8804}
RESULTS = []
ADULT = ('youngadult', 'adult', 'elder')


def check(group, name, ok, detail=''):
    RESULTS.append({'group': group, 'check': name, 'ok': bool(ok), 'detail': str(detail)})
    print('%-4s %-9s %-70s %s' % ('PASS' if ok else 'FAIL', group, name[:70], str(detail)[:170]), flush=True)
    return ok


def get(port, route, timeout=600):
    """-> (status, body bytes, headers)"""
    try:
        with urllib.request.urlopen('http://127.0.0.1:%d/api/%s' % (port, route), timeout=timeout) as r:
            return r.status, r.read(), r.headers
    except urllib.error.HTTPError as ex:
        return ex.code, ex.read(), ex.headers


def free(port):
    with socket.socket() as s:
        try:
            s.bind(('127.0.0.1', port))
            return True
        except OSError:
            return False


def skin_colour(png):
    """(mean RGB of the atlas, looks like skin?) - white / near-white or empty pictures are not skin."""
    from PIL import Image
    import numpy as np
    im = Image.open(io.BytesIO(png)).convert('RGBA')
    a = np.asarray(im).astype(np.float32)
    H, W = a.shape[:2]
    body = a[int(H * 0.52):int(H * 0.76), int(W * 0.02):int(W * 0.48), :3]      # torso and arms
    mean = body.reshape(-1, 3).mean(0)
    white = (body.min(axis=2) > 235).mean()
    ok = im.size == (1024, 2048) and mean.min() < 225 and white < 0.2 and mean.max() - mean.min() > 8
    return [round(float(x), 1) for x in mean], round(float(white), 3), ok


def before_lookup():
    """Offline: which tones the old lookup (base game + WickedWhims only) could not find, and which tones are
    installed at all (a TONE in the game, a pack, Mods or Mods_parked - outside blocked folders)."""
    import casptex, morph, gamedata
    M = morph.MORPH_INDEX

    def find(inst):
        if casptex.load_tone(inst) is not None:
            return True
        row = M.find(morph.T_TONE, inst)
        return row is not None and not gamedata.blocked_path(M.paths[int(row['pkg'])])
    return lambda inst: casptex.load_tone(inst) is None, find


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=8883)
    ap.add_argument('--no-shots', action='store_true')
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    t0 = time.time()
    port = a.port
    if port in REFUSED:
        raise SystemExit('refusing port %d' % port)
    if not free(port) or HN._status(port, 0.5):
        port = next(p for p in range(8884, 8899) if p not in REFUSED and free(p) and not HN._status(p, 0.3))
    saves = tempfile.mkdtemp(prefix='r24_skin_saves_')
    exports = tempfile.mkdtemp(prefix='r24_skin_exports_')
    ts = time.time()
    server = HN.start_server(port, env={'ANIMATOR_SAVES': saves, 'WICKED_EXPORTS_DIR': exports}, log_dir=OUT)
    start_s = time.time() - ts
    print('server on port %d (pid %d), answered after %.1f s' % (port, server.pid, start_s), flush=True)
    rows, shots = [], None
    try:
        check('0 start', 'the server answers quickly (no Mods indexing at start)', start_s < 20, '%.1f s' % start_s)
        old_missing, installed = before_lookup()
        # ---- 1. all adult Tray sims: tray -> tray_sim -> skin
        code, body, _ = get(port, 'tray')
        households = json.loads(body.decode('utf-8')) if code == 200 else []
        sims = [(hh['id'], s['index'], ('%s %s' % (s.get('first', ''), s.get('last', ''))).strip(), s.get('gender'))
                for hh in households for s in hh['sims']]
        import trayfmt
        adults_offline = sum(1 for hh in trayfmt.list_households() for s in hh['sims']
                             if s['age'] in ADULT and s['species'] == 'human')
        check('1 tray', '/api/tray lists every adult Tray sim', code == 200 and len(sims) == adults_offline,
              '%d listed, %d adult humans in the Tray' % (len(sims), adults_offline))
        for tray, index, name, gender in sims:
            r = {'tray': tray, 'index': index, 'name': name, 'gender': gender}
            t1 = time.time()
            code, body, _ = get(port, 'tray_sim?tray=%s&index=%d' % (tray, index))
            r['tray_sim_s'] = round(time.time() - t1, 2)
            if code != 200:
                r.update(kind='error', error='tray_sim %d: %s' % (code, body[:200]))
                rows.append(r)
                continue
            ts_ = json.loads(body.decode('utf-8'))
            r.update(frame=ts_['frame'], tone=ts_.get('tone', ''), standin_flag=ts_.get('toneStandIn'), tone_info=ts_.get('toneInfo'))
            inst = int(r['tone'], 16) if r['tone'] else 0
            r['failed_before'] = bool(inst) and old_missing(inst)
            r['installed'] = bool(inst) and installed(inst)
            t1 = time.time()
            code, png, hd = get(port, 'skin?frame=%s&tone=%s' % (r['frame'], r['tone']))
            r['skin_s'] = round(time.time() - t1, 2)
            if code != 200 or (hd.get('Content-Type') or '') != 'image/png':
                r.update(kind='error', error='skin %d %s: %s' % (code, hd.get('Content-Type'), png[:200]))
                rows.append(r)
                continue
            r['header'] = hd.get('X-Skin-Tone')
            r['used'] = hd.get('X-Skin-Tone-Used')
            r['source'] = hd.get('X-Skin-Tone-Source')
            r['mean'], r['white'], looks = skin_colour(png)
            if not looks:
                r.update(kind='error', error='the skin does not look like skin: mean %s, %.0f%% white' % (r['mean'], r['white'] * 100))
            else:
                r['kind'] = 'real' if r['header'] == 'real' else 'standin'
            t1 = time.time()
            code2, png2, _ = get(port, 'skin?frame=%s&tone=%s' % (r['frame'], r['tone']))
            r['skin_again_s'] = round(time.time() - t1, 2)
            r['same_again'] = code2 == 200 and png2 == png
            rows.append(r)
            print('  %-7s %-28s tone %-16s %-9s %-7s used %s mean %s  (%.1f s + %.1f s)' % (
                r['kind'], name[:28], r['tone'], r.get('source'), 'before:X' if r['failed_before'] else '', r.get('used'),
                r.get('mean'), r['tray_sim_s'], r['skin_s']), flush=True)
        real = [r for r in rows if r.get('kind') == 'real']
        stand = [r for r in rows if r.get('kind') == 'standin']
        errors = [r for r in rows if r.get('kind') == 'error']
        before = [r for r in rows if r.get('failed_before')]
        counts = '%d real, %d stand-in, %d errors (of %d)' % (len(real), len(stand), len(errors), len(rows))
        check('2 skin', 'every adult Tray sim gets a skin: %s' % counts, len(rows) == len(sims) and not errors,
              [e['name'] + ': ' + e['error'] for e in errors][:3])
        check('2 skin', 'no skin comes out white (torso/arms mean colour, near-white share)',
              all(r.get('mean') and min(r['mean']) < 225 and r['white'] < 0.2 for r in rows),
              'palest mean %s' % max((r['mean'] for r in rows if r.get('mean')), key=lambda m: min(m), default=None))
        cc_real = [r for r in before if r.get('kind') == 'real']
        check('2 skin', 'the sims the app could not find a tone for before all get a skin now (%d)' % len(before),
              before and all(r.get('kind') in ('real', 'standin') for r in before),
              '%d of them show their own CC / pack tone, %d a stand-in' % (len(cc_real), len(before) - len(cc_real)))
        wrong_real = [r['name'] for r in rows if r.get('installed') and r.get('kind') != 'real']
        check('2 skin', 'every sim whose tone is installed (game, pack, Mods, Mods_parked) shows that very tone',
              not wrong_real and all(r['used'] == r['tone'] for r in real), wrong_real[:3])
        wrong_stand = [r['name'] for r in stand if r.get('installed')]
        check('2 skin', 'stand-ins only for tones installed nowhere (the default tone then)',
              not wrong_stand and all(r['source'] == 'default' and r['used'] != r['tone'] for r in stand),
              '%d stand-ins, sources %s' % (len(stand), sorted({r['source'] for r in stand})))
        flag_bad = [r['name'] for r in rows if r.get('kind') in ('real', 'standin') and bool(r.get('standin_flag')) != (r['kind'] == 'standin')]
        check('2 skin', 'tray_sim.toneStandIn agrees with /api/skin\'s X-Skin-Tone header', not flag_bad, flag_bad[:3])
        check('2 skin', 'asking again gives the same picture', all(r.get('same_again') for r in rows if r.get('kind') != 'error'))
        slow = sorted(rows, key=lambda r: -r.get('skin_s', 0))[:1]
        check('3 speed', 'a skin asked again comes from the cache (< 1 s each)', all(r.get('skin_again_s', 9) < 1.0 for r in rows),
              'slowest again %.2f s' % max((r.get('skin_again_s', 0) for r in rows), default=0))
        check('3 speed', 'first skin per sim in reasonable time (< 60 s)', all(r.get('skin_s', 0) < 60 for r in rows),
              'slowest %s %.1f s' % (slow[0]['name'], slow[0].get('skin_s', 0)) if slow else '')
        # ---- 3. odd requests never error
        odd = {}
        for q in ('skin?frame=yf&tone=zz', 'skin?frame=yf&tone=..%2F..%2Fconfig', 'skin?frame=..%2Fx&tone=3840',
                  'skin?frame=cf&tone=3840', 'skin?frame=ym&tone=ffffffffffffffff', 'skin?frame=yf'):
            c, png, hd = get(port, q)
            odd[q] = (c, hd.get('X-Skin-Tone'), hd.get('Content-Type'))
        check('4 odd', 'odd tones / frames still answer a skin picture (200, never an error)',
              all(v[0] == 200 and v[2] == 'image/png' for v in odd.values()), odd)
        check('4 odd', 'no tone -> the default tone counts as real; an unknown tone -> stand-in',
              odd['skin?frame=yf'][1] == 'real' and odd['skin?frame=yf&tone=zz'][1] == 'standin'
              and odd['skin?frame=ym&tone=ffffffffffffffff'][1] == 'standin', {k: v[1] for k, v in odd.items()})
        # ---- 4. screenshots: two sims that had no tone before, in the app
        if not a.no_shots:
            women = [r for r in before if r.get('gender') == 'female'] or before
            pick = [next((r for r in women if r.get('kind') == 'real' and r.get('source') == 'cc'), None),
                    next((r for r in women if r.get('kind') == 'standin'), None)]
            pick = [p for p in pick if p]
            spec = [{'tray': p['tray'], 'index': p['index'], 'name': p['name'], 'tag': '%d_%s' % (k + 1, p['kind'])}
                    for k, p in enumerate(pick)]
            fn = os.path.join(OUT, 'skin_tones_shots_in.json')
            with open(fn, 'w', encoding='utf-8') as f:
                json.dump(spec, f)
            cmd = ['node', os.path.join(os.path.dirname(__file__), 'skin_tones_shots.js'), str(port), fn]
            print('\n$ ' + ' '.join(cmd), flush=True)
            pr = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=1800)
            try:
                shots = json.loads([ln for ln in pr.stdout.splitlines() if ln.startswith('{')][-1])
            except Exception as ex:
                shots = None
                check('5 shots', 'the app screenshots ran', False, '%s %s' % (ex, (pr.stderr or pr.stdout)[-300:]))
            if shots:
                files = [f for s in shots['sims'] for f in s['files']]
                check('5 shots', '4 screenshots at 1366x768 of 2 Tray sims that had no skin tone before',
                      len(files) == 4 and all(os.path.exists(f) for f in files), files)
                check('5 shots', 'in the app both wear a skin texture (skinReady, material map)',
                      all(s['skinReady'] is True and s['textured'] for s in shots['sims']),
                      [(s['name'], s['tone'], s['skinReady'], s['textured']) for s in shots['sims']])
                check('5 shots', 'no page errors', not shots['errors'], shots['errors'][:2])
    finally:
        HN.stop_server(server)
    passed = sum(r['ok'] for r in RESULTS)
    summary = {'passed': passed, 'failed': len(RESULTS) - passed, 'seconds': round(time.time() - t0, 1), 'port': port,
               'counts': {'real': sum(r.get('kind') == 'real' for r in rows), 'standin': sum(r.get('kind') == 'standin' for r in rows),
                          'errors': sum(r.get('kind') == 'error' for r in rows), 'sims': len(rows),
                          'failed_before': sum(bool(r.get('failed_before')) for r in rows)},
               'results': RESULTS, 'sims': rows, 'shots': shots}
    with open(os.path.join(OUT, 'skin_tones.json'), 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=1, default=str)
    with open(os.path.join(OUT, 'skin_tones.txt'), 'w', encoding='utf-8') as f:
        for r in RESULTS:
            f.write('%-4s %-9s %-70s %s\n' % ('PASS' if r['ok'] else 'FAIL', r['group'], r['check'][:70], r['detail'][:300]))
        f.write('\n%s\n%d passed, %d failed in %.0f s (port %d)\n' % (json.dumps(summary['counts']), passed, len(RESULTS) - passed,
                                                                  summary['seconds'], port))
    print('\n%s' % json.dumps(summary['counts']))
    print('%d passed, %d failed in %.0f s' % (passed, len(RESULTS) - passed, summary['seconds']))
    sys.exit(0 if passed == len(RESULTS) and RESULTS else 1)


if __name__ == '__main__':
    main()
