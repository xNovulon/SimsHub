"""R1-F checks: game data backend (voices, moments XML, effect names, EA clips and faces, furniture spots).

    python tools/checks/r1f/game_check.py [--port 8846] [--quick]

Offline checks plus one server run (backend/server.py under an audit hook, on port 8846 or the next free one above
8850) for the routes. Nothing is written into Documents\\Electronic Arts\\The Sims 4: exports are built in memory or
in %TEMP%. Outputs go to cache/checks/r1f/ (report.json, report.txt, *.png). Exits 0 only when every item passes.
"""
import argparse, glob, json, math, os, random, re, socket, subprocess, sys, tempfile, time, urllib.request
sys.dont_write_bytecode = True        # Python's own .pyc files are not app output; keep the write audit clean
import xml.etree.ElementTree as ET

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
BACKEND = os.path.join(ROOT, 'backend')
OUT = os.path.join(ROOT, 'cache', 'checks', 'r1f')
BASE = os.path.join(OUT, 'baseline')
TEMP = tempfile.gettempdir()
sys.path.insert(0, BACKEND)
REFUSED = {8765, 8766, 8777, 8802, 8804}

# ------------------------------------------------------------------ write audit for this process
AUDIT_SELF = os.path.join(TEMP, 'r1f_audit_check.jsonl')
AUDIT_SERVER = os.path.join(TEMP, 'r1f_audit_server.jsonl')
for _p in (AUDIT_SELF, AUDIT_SERVER):
    try:
        os.remove(_p)
    except OSError:
        pass
_afd = os.open(AUDIT_SELF, os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, 'O_BINARY', 0))
_WF = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC
_busy = [False]


def _hook(event, args):
    if _busy[0]:
        return
    _busy[0] = True
    try:
        path = None
        if event == 'open':
            p, mode, flags = (list(args) + [None, None, None])[:3]
            if (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (mode is None and isinstance(flags, int) and flags & _WF):
                path = p
        elif event in ('os.rename', 'os.replace'):
            path = args[1]
        elif event in ('os.remove', 'os.rmdir', 'os.mkdir', 'shutil.rmtree'):
            path = args[0]
        if isinstance(path, bytes):
            path = path.decode('utf-8', 'replace')
        if isinstance(path, str):
            os.write(_afd, (json.dumps({'kind': event, 'path': os.path.abspath(path)}) + '\n').encode('utf-8'))
    except Exception:
        pass
    finally:
        _busy[0] = False


sys.addaudithook(_hook)

# ------------------------------------------------------------------ results
RESULTS = []


def check(group, name, ok, detail=''):
    RESULTS.append({'group': group, 'check': name, 'ok': bool(ok), 'detail': str(detail)})
    print('%-4s %-10s %-62s %s' % ('PASS' if ok else 'FAIL', group, name[:62], str(detail)[:150]), flush=True)
    return ok


def guarded(group, name):
    def deco(fn):
        def run(*a, **k):
            try:
                return fn(*a, **k)
            except Exception as ex:
                import traceback
                traceback.print_exc()
                check(group, name + ' (crashed)', False, repr(ex))
        return run
    return deco


# ------------------------------------------------------------------ server
def _status(port, timeout=2.0):
    try:
        with urllib.request.urlopen('http://127.0.0.1:%d/api/status' % port, timeout=timeout) as r:
            return json.loads(r.read().decode('utf-8'))
    except Exception:
        return None


def _free(port):
    with socket.socket() as s:
        try:
            s.bind(('127.0.0.1', port))
            return True
        except OSError:
            return False


def start_server(port):
    if port in REFUSED:
        raise SystemExit('refusing port %d' % port)
    if not _free(port) or _status(port, 0.5):
        port = next(p for p in range(8851, 8899) if p not in REFUSED and _free(p))
    env = dict(os.environ, ANIMATOR_PORT=str(port), PYTHONUNBUFFERED='1', R1F_AUDIT_LOG=AUDIT_SERVER,
               PYTHONDONTWRITEBYTECODE='1')
    log = open(os.path.join(OUT, 'server_%d.log' % port), 'ab')
    p = subprocess.Popen([sys.executable, os.path.join(os.path.dirname(__file__), 'audited_server.py')], cwd=ROOT,
                         env=env, stdout=log, stderr=subprocess.STDOUT, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    t0 = time.time()
    while time.time() - t0 < 180:
        if p.poll() is not None:
            raise RuntimeError('server stopped at once (see %s)' % log.name)
        s = _status(port)
        if s and s.get('ok') and s.get('pid') == p.pid:
            return p, port
        time.sleep(0.4)
    p.kill()
    raise TimeoutError('server did not answer')


def stop_server(p):
    try:
        subprocess.run(['taskkill', '/PID', str(p.pid), '/F', '/T'], capture_output=True)
    except Exception:
        p.kill()


def get(port, route, timeout=600):
    with urllib.request.urlopen('http://127.0.0.1:%d/api/%s' % (port, route), timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8'))


# ------------------------------------------------------------------ 1. voices
@guarded('1 voices', 'voices')
def check_voices(port):
    import eaaudio, trayfmt
    from clipfmt import fnv32
    t0 = time.time()
    v = get(port, 'voices')
    lines = v['lines']
    check('1 voices', '/api/voices has >= 5,500 lines', len(lines) >= 5500, '%d lines (%.1f s)' % (len(lines), time.time() - t0))
    bad = [x['name'] for x in lines if eaaudio._LINE_BLOCK.search(x['name']) or re.search(r'_(ca|cb|pa)$', x['name'])]
    check('1 voices', 'no line matches _LINE_BLOCK or ends in ca/cb/pa', not bad, '%d bad %s' % (len(bad), bad[:3]))
    codes = set(eaaudio.ADULT_VOICES['female'] + eaaudio.ADULT_VOICES['male'])
    check('1 voices', 'every line has only adult voices (fa fc fd ma mb mc)',
          all(x['voices'] and set(x['voices']) <= codes for x in lines), v['codes'])
    check('1 voices', 'lines carry tags, a length and lowprob',
          all('tags' in x and 'lowprob' in x and 'gender' in x for x in lines) and sum(1 for x in lines if x['sec']) > 5000,
          '%d with a length' % sum(1 for x in lines if x['sec']))
    by_hash = {fnv32(c): c for c in eaaudio.ACTOR_CODES}
    n, wrong, own = 0, [], 0
    for hh in trayfmt.list_households():
        for s in trayfmt.household_sims(hh['id'])['sims']:
            if s.get('age') not in ('youngadult', 'adult', 'elder') or s.get('species', 'human') != 'human':
                continue
            n += 1
            code = eaaudio.voice_for_actor(s.get('voice_actor'), s.get('gender'))
            ok = code in eaaudio.ADULT_VOICES['male' if s.get('gender') == 'male' else 'female']
            own += by_hash.get(s.get('voice_actor')) == code
            if not ok:
                wrong.append((s.get('first'), s.get('gender'), code))
    check('1 voices', 'every Tray sim: female -> fa/fc/fd, male -> ma/mb/mc', n > 0 and not wrong,
          '%d adult Tray sims, %d with their own game voice, wrong: %s' % (n, own, wrong[:3]))
    check('1 voices', 'voice_for_actor for a man without a voice -> ma',
          eaaudio.voice_for_actor(None, 'male') == 'ma' and eaaudio.voice_for_actor(fnv32('mc'), 'male') == 'mc'
          and eaaudio.voice_for_actor(fnv32('ca'), 'female') == 'fa', 'ok')
    hh = trayfmt.list_households()[0]
    spec = trayfmt.sim_body_spec(hh['id'], 0, resolve=False)
    check('1 voices', 'trayfmt.sim_body_spec passes voice_actor and voice_pitch',
          'voice_actor' in spec and 'voice_pitch' in spec, (spec.get('voice_actor'), spec.get('voice_pitch')))
    ts = get(port, 'tray_sim?tray=%s&index=0' % hh['id'])
    check('1 voices', '/api/tray_sim gives the sim its voice (female voice for her)',
          ts.get('voice') in eaaudio.ADULT_VOICES['female' if ts.get('gender') != 'male' else 'male'],
          '%s %s voice=%s pitch=%s' % (ts.get('name'), ts.get('gender'), ts.get('voice'), ts.get('voicePitch')))
    ea_layout = bytes(12) + (5).to_bytes(4, 'little') + b'vo_ab\x00'
    ww_layout = bytes(12) + b'vo_expr_moan'.ljust(128, b'\x00')
    check('1 voices', '_event_sound_name reads both layouts',
          eaaudio._event_sound_name(ea_layout) == 'vo_ab' and eaaudio._event_sound_name(ww_layout) == 'vo_expr_moan', 'EA + WW')


# ------------------------------------------------------------------ 2. moments XML
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
PROTO_EVENTS = [
    {'type': 'CUM', 'target': 1, 'start': 2.1, 'cum_layer_type': 'FACE', 'cum_layer_level': 2, 'skip_with_condom': False},
    {'type': 'EFFECT', 'target': 0, 'start': 2.0, 'end': 3.0, 'effect_name': 'pet_small_drool_front',
     'effect_joint_name': 'b__Penis_Tip', 'skip_with_condom': True},
    {'type': 'UNDRESS', 'target': 1, 'start': 0.5, 'naked_type': 'TOP', 'skip_with_condom': False},
    {'type': 'REMOVE_CONDOM', 'target': 0, 'start': 1.8, 'skip_with_condom': False}]


def _snippet(resources):
    import wwpackage as W
    return next(d for t, g, i, d in resources if t == W.SNIPPET).decode('utf-8')


def _anim_el(xml):
    root = ET.fromstring(xml.encode('utf-8'))
    return root.find("L[@n='animations_list']")[0]


def _baked(fid):
    with open(os.path.join(BASE, fid + '.baked.json'), encoding='utf-8') as f:
        return json.load(f)


@guarded('2 moments', 'moments')
def check_moments():
    import exporter, gamedata, wwpackage as W
    b = _baked('magic_bj')
    b.update(category='CLIMAX', loops=1, act='ORALJOB', events=PROTO_EVENTS)
    res, info = exporter.animation_resources(b, metas={}, present=set())
    xml = _snippet(res)
    with open(os.path.join(OUT, 'proto_snippet.xml'), 'w', encoding='utf-8') as f:
        f.write(xml)
    got = xml[xml.find('      <L n="animation_events_list">'):]
    got = got[:got.find('      </L>') + len('      </L>')] if '      </L>' in got else ''
    check('2 moments', 'the 4-moment proto gives exactly the spec_game 3 block', got == EXPECTED,
          'equal' if got == EXPECTED else 'differs (see proto_snippet.xml)')
    try:
        an = _anim_el(xml)
        kids = [c.get('n') for c in an]
        ok = kids.index('animation_events_list') == kids.index('animation_actors_list') + 1
        check('2 moments', 'parses with xml.etree; the list sits after the actors', ok, kids[-3:])
    except Exception as ex:
        check('2 moments', 'parses with xml.etree', False, ex)
        return
    check('2 moments', 'the export info counts the moments', info.get('events') == 4, info.get('events'))
    back = gamedata.parse_events(an)
    want = sorted([dict(e) for e in PROTO_EVENTS], key=lambda e: (e['start'], e['type']))
    norm = lambda es: [{k: v for k, v in e.items()} for e in es]
    check('2 moments', 'parse_events(own export) round-trips', norm(back) == norm(want),
          'same %d moments' % len(back) if norm(back) == norm(want) else back)
    creator = ET.fromstring('''<T><T n="animation_actors_list"><T><T n="animation_clip_name">c1</T></T></T>
      <T n="animation_events_list">
        <T><T n="event_type">cum</T><T n="event_start_timecode">0,3</T><T n="event_target">a1</T><T n="cum_layer_type">FOOT</T><T n="cum_layer_level">1</T></T>
        <T><T n="event_type">CUM</T><T n="event_start_timecode">1.5</T><T n="event_target">a0</T><T n="cum_layer_type">BACK</T><T n="cum_layer_level">5</T></T>
        <T><T n="event_type">EFFECT</T><T n="event_start_timecode">1</T><T n="event_target">o</T><T n="effect_name">x</T><T n="effect_joint_name">b__Head__</T></T>
        <T><T n="event_type">UNDRESS</T><T n="event_start_timecode">1</T><T n="event_target">a0</T><T n="naked_type">NONE</T></T>
        <T><T n="event_type">EFFECT</T><T n="event_start_timecode">2</T><T n="event_target">a0</T><T n="effect_name">sim_pee</T><T n="effect_joint_name">b__Penis_Tip01</T>
           <T n="dont_run_if"><T n="actor_has_condom">1</T></T></T>
      </T></T>''')
    ev = gamedata.parse_events(creator)
    ok = (len(ev) == 3 and ev[0]['start'] == 0.3 and ev[0]['cum_layer_type'] == 'FEET' and ev[1]['cum_layer_type'] == 'UPPER_BACK'
          and ev[1]['cum_layer_level'] == 3 and ev[2]['effect_joint_name'] == 'b__Penis_Tip' and ev[2]['skip_with_condom'])
    check('2 moments', "FOOT->FEET, BACK->UPPER_BACK, '0,3'->0.3, aN only, invalid dropped", ok,
          [(e['type'], e['start'], e.get('cum_layer_type') or e.get('effect_joint_name')) for e in ev])
    b2 = _baked('magic_cowgirl')
    b2['events'] = [{'type': 'EFFECT', 'target': 1, 'start': 1, 'end': 2, 'effect_name': 'sim_pee',
                     'effect_joint_name': 'b__Penis_Tip01'},
                    {'type': 'EFFECT', 'target': 0, 'start': 1, 'effect_name': 'pet_small_drool',
                     'effect_joint_name': 'b__Tounge__4'}]
    res2, _ = exporter.animation_resources(b2, metas={}, present=set())
    x2 = _snippet(res2)
    clip_bytes = b''.join(d for t, g, i, d in res2 if t == exporter.T_CLIP)
    from clipfmt import fnv32
    bad = [n for n in ('b__Penis_Tip01', 'b__Penis_Tip02', 'b__Penis_Tip03', 'b__Tounge__4') if n in x2]
    hashes = [fnv32(n).to_bytes(4, 'little') for n in ('b__Penis_Tip01', 'b__Penis_Tip02', 'b__Penis_Tip03', 'b__Tounge__4')]
    check('2 moments', 'b__Penis_Tip01-03 / b__Tounge__4 are never written', not bad and 'b__Penis_Tip<' in x2
          and 'b__Tounge__3' in x2 and not any(h in clip_bytes for h in hashes), 'remapped to b__Penis_Tip / b__Tounge__3')
    b3 = _baked('magic_cowgirl')
    b3['events'] = [{'type': 'EFFECT', 'target': 0, 'start': 0.5, 'effect_name': 'EffectName', 'effect_joint_name': 'b__Head__'},
                    {'type': 'NOTE', 'target': 0, 'start': 0.1},
                    {'type': 'CUM', 'target': 5, 'start': 0.1, 'cum_layer_type': 'FACE', 'cum_layer_level': 1}]
    res3, info3 = exporter.animation_resources(b3, metas={}, present=set())
    x3 = _snippet(res3)
    check('2 moments', 'an invalid effect is dropped with a plain warning', 'EffectName' not in x3 and
          any('is not a game effect' in w for w in info3['warnings']) and 'animation_events_list' not in x3, info3['warnings'][:2])
    b4 = _baked('magic_cowgirl')
    fem = [i for i, a in enumerate(b4['actors']) if a.get('body') != 'ym']
    b4['actors'][fem[0]]['sounds'] = list(b4['actors'][fem[0]].get('sounds') or []) + [
        {'frame': 5, 'name': 'vo_expr_moan_pleasure_30f_ma', 'kind': 'voice'},
        {'frame': 6, 'name': 'vo_expr_giggle_ca', 'kind': 'voice'}]
    res4, info4 = exporter.animation_resources(b4, metas={}, present=set())
    w4 = info4['warnings']
    check('2 moments', "warns about another gender's / a non-adult voice line", any("another gender's voice line" in w for w in w4)
          and any('not an adult voice line' in w for w in w4) and 'vo_expr_giggle_ca' not in info4['sounds'], w4[:2])
    # cum_after
    b5 = _baked('magic_cowgirl')
    b5['actors'][fem[0]]['cumAfter'] = 'NONE'
    x5 = _snippet(exporter.animation_resources(b5, metas={}, present=set())[0])
    b6 = _baked('magic_cowgirl')
    b6['actors'][fem[0]]['cumAfter'] = ['FACE', 'BACK', 'FOOT', 'nonsense']
    x6 = _snippet(exporter.animation_resources(b6, metas={}, present=set())[0])
    b7 = _baked('magic_cowgirl')
    b7['actors'][fem[0]]['cumAfter'] = 'AUTO'
    x7 = _snippet(exporter.animation_resources(b7, metas={}, present=set())[0])
    x0 = _snippet(exporter.animation_resources(_baked('magic_cowgirl'), metas={}, present=set())[0])
    check('2 moments', 'receiving_actor_cum_layers follows cumAfter (NONE/list/AUTO)',
          '>DISABLED<' in x5 and '>FACE, UPPER_BACK, FEET<' in x6 and x7 == x0 and 'VAGINA' in x0,
          'NONE->DISABLED, list->FACE, UPPER_BACK, FEET, AUTO->unchanged')
    # retiming keeps "to the end" at the end; clamping
    lines, _ = W.events_xml([{'type': 'EFFECT', 'target': 0, 'start': -1, 'end': 99, 'effect_name': 'sim_pee',
                              'effect_joint_name': 'b__Penis_Tip'}], 1, 3.0)
    check('2 moments', 'start/end clamped to the clip; %.4f without trailing zeros, a dot',
          '<T n="event_start_timecode">0</T>' in '\n'.join(lines) and '<T n="event_end_timecode">3</T>' in '\n'.join(lines)
          and W._sec(1.23456) == '1.2346' and W._sec(2.5) == '2.5', W._sec(1 / 3))
    # a real creator animation's moments
    lib = gamedata.library()['animations']
    found = None
    for a in lib:
        if 'LAMABOY' in a.get('package', ''):
            ev = gamedata.animation_events(a)
            if ev:
                found = (a['name'], len(ev))
                break
    check('2 moments', 'animation_events(anim) reads a creator animation', bool(found), found)


# ------------------------------------------------------------------ 3. export regression
@guarded('3 export', 'export regression')
def check_regression():
    import exporter, wwpackage
    sys.path.insert(0, os.path.dirname(__file__))
    fids = sorted(os.path.basename(p)[:-len('.baked.json')] for p in glob.glob(os.path.join(BASE, '*.baked.json')))
    out_dir = os.path.join(TEMP, 'r1f_export_now')
    os.makedirs(out_dir, exist_ok=True)
    same = []
    for fid in fids:
        baked = _baked(fid)
        res, info = exporter.animation_resources(baked, metas={}, present=set())
        data = wwpackage.build_package(res)
        with open(os.path.join(out_dir, fid + '.package'), 'wb') as f:
            f.write(data)
        with open(os.path.join(BASE, fid + '.package'), 'rb') as f:
            base = f.read()
        same.append(data == base)
        check('3 export', 'byte-identical: %s' % fid, data == base, '%d bytes' % len(data))
    check('3 export', 'all fixtures without new fields are unchanged', fids and all(same), '%d/%d' % (sum(same), len(fids)))


# ------------------------------------------------------------------ 4. effects
@guarded('4 effects', 'effects')
def check_effects(port):
    import vfx
    t0 = time.time()
    n = len(vfx.names())
    check('4 effects', 'len(vfx.names()) == 34081', n == 34081, '%d (%.1f s)' % (n, time.time() - t0))
    bad = [c[0] for c in vfx.CURATED if not vfx.valid(c[0])]
    check('4 effects', 'every CURATED name is valid', not bad, '%d curated, invalid: %s' % (len(vfx.CURATED), bad))
    check('4 effects', "valid('EffectName') and valid('sim_pee_c') are False",
          vfx.valid('EffectName') is False and vfx.valid('sim_pee_c') is False, 'both False')
    eq = vfx.adult_equivalent('ep02_jump_stand_c_sim_drips_lthigh')
    check('4 effects', 'adult_equivalent(ep02_jump_stand_c_sim_drips_lthigh)', eq == 'ep02_jump_stand_sim_drips_lthigh', eq)
    check('4 effects', "adult_equivalent('sim_pee_c') == 'sim_pee'", vfx.adult_equivalent('sim_pee_c') == 'sim_pee', 'ok')
    joints_ok = all(vfx.joint_ok(j['bone']) for j in vfx.JOINTS) and not vfx.joint_ok('b__Penis_Tip01') \
        and not vfx.joint_ok('b__Tounge__4')
    check('4 effects', 'every JOINTS bone is a rig bone (Tip01/Tounge__4 not)', joints_ok, '%d parts' % len(vfx.JOINTS))
    r = get(port, 'effects?joint=b__Penis_Tip')
    check('4 effects', '/api/effects: popular (tip first), joints, groups',
          r['popular'] and r['popular'][0]['at_joint'] >= r['popular'][-1]['at_joint'] and len(r['joints']) == len(vfx.JOINTS),
          '%d popular, first %s' % (len(r['popular']), r['popular'][0]['name']))
    s = get(port, 'effects?q=drool')
    check('4 effects', '/api/effects?q=drool finds adult drool effects, curated first',
          s['items'] and s['items'][0]['name'] == 'pet_small_drool_front' and all(vfx.adult(x['name']) for x in s['items']),
          '%d items' % len(s['items']))
    c = get(port, 'effects?check=sim_pee_c,EffectName,pet_small_drool_front')['checks']
    check('4 effects', '/api/effects?check= gives valid + adult equivalent',
          c['sim_pee_c'] == {'valid': False, 'equivalent': 'sim_pee'} and c['EffectName']['equivalent'] is None
          and c['pet_small_drool_front']['valid'], c['sim_pee_c'])
    child = [x for x in vfx.names() if vfx.adult(x) and re.search(r'child|toddler|infant|(?<![a-z])(c|p|t|i)(?![a-z])', x.replace('_', ' '))]
    check('4 effects', 'no adult-flagged name has child words or age tokens', not child, child[:3])


# ------------------------------------------------------------------ 5. EA clips
def _fk(tracks, rig, t=0):
    import numpy as np

    def qm(q):
        x, y, z, w = q
        return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                         [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                         [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])

    def sample(keys):
        best = keys[0]
        for k in keys:
            if k[0] <= t:
                best = k
        return best[1:]
    W = {}
    for b in rig:
        tr = tracks.get(b['name'], {})
        M = np.eye(4)
        M[:3, :3] = qm(sample(tr['r']) if tr.get('r') else b['rot'])
        M[:3, 3] = sample(tr['t']) if tr.get('t') else b['pos']
        W[b['name']] = W[rig[b['parent']]['name']] @ M if b['parent'] >= 0 else M
    return W


@guarded('5 EA clips', 'EA clips')
def check_ea(port, quick=False):
    import numpy as np
    import eaclips, gamedata
    t0 = time.time()
    names = eaclips.names()
    rnd = random.Random(1234)
    sample = rnd.sample(names, min(1000, len(names)) if not quick else 200)
    errors, empty = [], 0
    for n in sample:
        try:
            tr = eaclips.tracks(n)
            empty += sum(1 for b in tr['tracks'].values() for k in b.values() if not k)
        except Exception as ex:
            errors.append((n, repr(ex)))
    check('5 EA clips', '%d random adult EA clips parse with 0 errors' % len(sample), not errors and empty == 0,
          '%d errors, %d empty tracks, %d adult names, %.0f s' % (len(errors), empty, len(names), time.time() - t0))
    rig = gamedata.rig('au')['bones']
    rest = {b['name']: b for b in rig}
    tx = eaclips.tracks('a2a_bed_wooHoo_HS_loop1_x')
    ty = eaclips.tracks('a2a_bed_wooHoo_HS_loop1_y')
    rb = tx['tracks'].get('b__ROOT_bind__', {}).get('r')
    const_ok = rb == [[0, 0.5, 0.5, 0.5, 0.5]] and rb[0][1:] == [round(v, 5) for v in rest['b__ROOT_bind__']['rot']]
    check('5 EA clips', 'bed WooHoo x/y: constant channels decode (b__ROOT_bind__ = rest)', const_ok
          and ty['tracks'].get('b__ROOT_bind__', {}).get('r') == rb, rb)
    worst, lying, heights = 0.0, True, []
    for t in range(0, tx['ticks'], 5):
        Wx, Wy = _fk(tx['tracks'], rig, t), _fk(ty['tracks'], rig, t)
        d = float(np.linalg.norm(Wx['b__Pelvis__'][:3, 3] - Wy['b__Pelvis__'][:3, 3]))
        worst = max(worst, d)
        for Wm in (Wx, Wy):
            axis = Wm['b__Head__'][:3, 3] - Wm['b__Pelvis__'][:3, 3]
            lying = lying and abs(axis[1]) < 0.35 * np.linalg.norm(axis)
            heights.append(round(float(Wm['b__Pelvis__'][1, 3]), 3))
    check('5 EA clips', 'bed WooHoo x/y: pelvises meet within a few cm, both lie flat', worst <= 0.05 and lying,
          'max pelvis gap %.3f m, pelvis height %.2f-%.2f m, body axis horizontal' % (worst, min(heights), max(heights)))
    # without the constant channel the sim would be turned 120 degrees (identity instead of the rest turn)
    bad = dict(tx['tracks'])
    bad['b__ROOT_bind__'] = {'r': [[0, 0, 0, 0, 1]]}
    Wb = _fk(bad, rig, 0)
    axis = Wb['b__Head__'][:3, 3] - Wb['b__Pelvis__'][:3, 3]
    check('5 EA clips', '(control) a wrong b__ROOT_bind__ would not lie flat', abs(axis[1]) > 0.35 * np.linalg.norm(axis),
          'axis %s' % np.round(axis, 2))
    st = get(port, 'ea_status')
    t1 = time.time()
    while not st.get('ready') and time.time() - t1 < 600:
        time.sleep(2)
        st = get(port, 'ea_status')
    faces = get(port, 'ea_faces')
    fl = faces.get('faces') or []
    badw = [f['clip'] for f in fl if eaclips.BAD.search(f['clip']) or gamedata._BLOCK_WORDS.search(f['clip'].replace('_', ' '))
            or not eaclips.adult(f['clip'])]
    check('5 EA clips', '/api/ea_faces has >= 120 faces, no BAD words', faces.get('ready') and len(fl) >= 120 and not badw,
          '%d faces (%s), bad %s' % (len(fl), ', '.join(sorted({f['group'] for f in fl})), badw[:2]))
    fb_ok = all(set(f['bones']) <= set(eaclips.FACE_CHANNEL) and all('r' in v or 't' in v for v in f['bones'].values())
                for f in fl)
    check('5 EA clips', 'faces hold only FACE_CHANNEL bones as local {r, t}', fl and fb_ok,
          '%d bones in the first' % len(fl[0]['bones']) if fl else '')
    lib = get(port, 'ea_library?cat=woohoo')
    all_lib = eaclips.library()
    raw = _raw_woohoo_pairs(eaclips)
    blocked = [b for b in raw if not eaclips.adult(b + '_x')]
    check('5 EA clips', 'ea_library: 326 WooHoo pairs in the game, 321 after the adult filter',
          lib['ready'] and len(raw) == 326 and lib['total'] == len(raw) - len(blocked) and
          all(re.match(r'a2a_animalPen', b) for b in blocked),
          '%d in the game, %d offered (%d animal-pen pairs dropped by the spec 6 filter), %d loops, %d places' % (
              len(raw), lib['total'], len(blocked), sum(1 for a in all_lib if a['kind'] == 'woohoo' and a['loop']),
              len({a['locations'][0] for a in all_lib if a['kind'] == 'woohoo'})))
    badlib = [a['id'] for a in all_lib if not all(eaclips.adult(c) for c in a['clips'])]
    check('5 EA clips', 'ea_library: no BAD word in any name', not badlib,
          '%d pairs: %s' % (len(all_lib), json.dumps(lib.get('categories'))))
    anim = get(port, 'ea_animation?id=ea:a2a_bed_wooHoo_HS_loop1&step=2')
    check('5 EA clips', '/api/ea_animation returns both decoded clips', len(anim['clips']) == 2 and
          all(c['tracks'] for c in anim['clips']), '%s: %d + %d bones' % (anim['name'], len(anim['clips'][0]['tracks']),
                                                                         len(anim['clips'][1]['tracks'])))
    idl = get(port, 'ea_idles')
    items = [x for g in idl['groups'] for x in g['items']]
    worst_loop, worst_step = 0.0, 0.0
    for x in items:
        d = get(port, 'ea_idle?name=' + x['name'])
        for q in d['bones'].values():
            q = np.array(q)
            worst_loop = max(worst_loop, float(eaclips._qangle(q[-1], q[0])))
            worst_step = max(worst_step, float(np.max(eaclips._qangle(q[1:], q[:-1]))))
    check('5 EA clips', 'every idle loops (tick 0 vs the end < 0.5 deg)', items and worst_loop < 0.5,
          '%d idles in %s, worst %.3f deg (biggest tick step %.2f deg)' % (
              len(items), '/'.join(g['id'] for g in idl['groups']), worst_loop, worst_step))


def _raw_woohoo_pairs(eaclips):
    idx = eaclips.index()
    alln = {idx['names'][i] for i in eaclips._name_map().values()}
    low = {n.lower() for n in alln}
    return sorted(n[:-2] for n in alln if n.lower().startswith('a2a_') and n.endswith('_x')
                  and (n[:-2] + '_y').lower() in low and re.search('woohoo', n, re.I))


# ------------------------------------------------------------------ 6. furniture
@guarded('6 furniture', 'furniture')
def check_furniture():
    import objmesh
    idx_path = os.path.join(ROOT, 'cache', 'furniture', '_index_v1.pkl')
    with open(os.path.join(BASE, 'index_v1_stat.json')) as f:
        before = json.load(f)
    t0 = time.time()
    sofa = objmesh._build(55200)            # a fresh build, not the cached JSON
    bed = objmesh._build(288627)
    single = objmesh._build(51719)
    seats = [s for s in sofa['slots'] if s['kind'] == 'seat']
    ok = len(seats) == 3 and len(sofa['slots']) == 3 and all(abs(s['pos'][1] - 0.485) < 0.005 and
                                                               abs(s['dir'][0]) < 0.05 and abs(s['dir'][1]) < 1e-9 and s['dir'][2] > 0.99
                                                               and s['feet']['L'] and abs(s['feet']['L'][1] - 0.112) < 0.005
                                                               for s in seats)
    check('6 furniture', 'object_mesh(55200): 3 seats at y 0.485, dir (0,0,1), feet y 0.112', ok,
          [(s['pos'], s['dir']) for s in seats])
    edge = [s for s in bed['slots'] if s['kind'] == 'edge']
    inb = sorted(s['n'] for s in bed['slots'] if s['kind'] == 'in')
    lie = [s for s in bed['slots'] if s['kind'] == 'lie']
    ok = (len(edge) == 4 and all(abs(abs(s['dir'][0]) - 1) < 0.05 and abs(s['pos'][1] - 0.61) < 0.005 for s in edge)
          and inb == [9, 10, 12, 13] and len(lie) == 3 and all(abs(s['pos'][2] + 0.29) < 0.02 and s['dir'] == [0.0, 0.0, 1.0]
                                                                and abs(s['pos'][1] - 0.562) < 0.005 for s in lie)
          and sorted(round(s['pos'][0], 3) for s in lie) == [-0.386, 0.0, 0.386])
    check('6 furniture', 'object_mesh(288627): 4 edge, in-bed 9/10/12/13, 3 lie at z -0.29', ok,
          'edge %s; in %s; lie %s' % ([s['n'] for s in edge], inb, [s['pos'] for s in lie]))
    sk = {s['n']: s['kind'] for s in single['slots']}
    check('6 furniture', '(extra) single bed: side seats are edges, 1 lying spot', [k for k in sk.values()].count('edge') == 4
          and [k for k in sk.values()].count('lie') == 1, sk)
    g = bed['surface_grid']
    pts = [objmesh.grid_height(g, x, z) for x in (-0.5, 0, 0.5) for z in (-0.3, 0, 0.5)]
    med = sorted(pts)[len(pts) // 2] if all(p is not None for p in pts) else None
    check('6 furniture', 'surface_grid: 5 cm cells in mm, mattress cells at 0.562 (median, all within 6 cm)',
          g and g['cell'] == 0.05 and len(g['h']) == g['w'] * g['d'] and med is not None and abs(med - 0.562) <= 0.005
          and all(abs(p - 0.562) <= objmesh.SLOT_TOL for p in pts)
          and objmesh.grid_height(g, 0, 5) is None, '%dx%d cells, mattress %s' % (g['w'], g['d'], pts))
    check('6 furniture', 'object JSON VERSION 2, index INDEX_VERSION 1', objmesh.VERSION == 2 and objmesh.INDEX_VERSION == 1
          and sofa['version'] == 2, 'ok')
    st = os.stat(idx_path)
    check('6 furniture', 'the _index_v1.pkl mtime is unchanged after a rebuild',
          int(st.st_mtime) == before['mtime'] and st.st_size == before['size'], '%d (%.1f s)' % (int(st.st_mtime), time.time() - t0))
    _draw_slots(bed, os.path.join(OUT, 'bed_slots.png'), 'Double bed (288627): seats, edges, in-bed seats, lying spots')
    _draw_slots(sofa, os.path.join(OUT, 'sofa_slots.png'), 'Sofa (55200): three seats with feet')


def _draw_slots(obj, path, title):
    """Top-down picture of the surface grid (grey = height) with the spots (a check picture for the round gate)."""
    from PIL import Image, ImageDraw
    g = obj['surface_grid']
    S, M = 12, 90                     # pixels per cell, margin (so foot spots off the furniture show too)
    W, D = g['w'] * S, g['d'] * S
    im = Image.new('RGB', (W + 2 * M, D + 2 * M + 30), (24, 20, 28))
    dr = ImageDraw.Draw(im)
    hs = [v for v in g['h'] if v != -32768]
    lo, hi = min(hs), max(hs)
    for j in range(g['d']):
        for i in range(g['w']):
            v = g['h'][j * g['w'] + i]
            if v == -32768:
                continue
            c = int(60 + 170 * (v - lo) / max(1, hi - lo))
            dr.rectangle([M + i * S, 30 + M + j * S, M + i * S + S - 1, 30 + M + j * S + S - 1], fill=(c, c, c))
    X = lambda x: M + (x - g['x0']) / g['cell'] * S
    Z = lambda z: 30 + M + (z - g['z0']) / g['cell'] * S
    col = {'seat': (80, 200, 255), 'edge': (255, 170, 60), 'in': (120, 255, 120), 'lie': (255, 80, 160)}
    for s in obj['slots']:
        x, z = X(s['pos'][0]), Z(s['pos'][2])
        c = col.get(s['kind'], (255, 255, 255))
        dr.ellipse([x - 6, z - 6, x + 6, z + 6], outline=c, width=3)
        dr.line([x, z, x + s['dir'][0] * 30, z + s['dir'][2] * 30], fill=c, width=3)
        dr.text((x + 7, z - 14), '%s %d' % (s['kind'], s['n']), fill=c)
        for f in (s.get('feet') or {}).values():
            if f:
                dr.rectangle([X(f[0]) - 3, Z(f[2]) - 3, X(f[0]) + 3, Z(f[2]) + 3], fill=c)
    dr.text((10, 10), title + '  (top view, +Z down; squares = foot spots)', fill=(255, 255, 255))
    im.save(path)


# ------------------------------------------------------------------ 7. nothing written outside cache/ and %TEMP%
def check_writes():
    allowed = [os.path.normcase(os.path.join(ROOT, 'cache')), os.path.normcase(os.path.realpath(TEMP)),
               os.path.normcase(TEMP)]
    rows = []
    for p in (AUDIT_SELF, AUDIT_SERVER):
        if os.path.exists(p):
            with open(p, encoding='utf-8') as f:
                rows += [json.loads(line) for line in f if line.strip()]
    outside = []
    for r in rows:
        pth = os.path.normcase(os.path.abspath(r['path']))
        if not any(pth == a or pth.startswith(a + os.sep) for a in allowed):
            outside.append(r)
    sims = os.path.normcase(os.path.join(os.path.expanduser('~'), 'Documents', 'Electronic Arts', 'The Sims 4'))
    in_game = [r for r in outside if os.path.normcase(r['path']).startswith(sims)]
    check('7 writes', 'nothing written outside cache/ and %TEMP% (audited)', not outside,
          '%d writes audited (check + server), outside: %s' % (len(rows), outside[:3]))
    check('7 writes', 'nothing written into Documents\\Electronic Arts\\The Sims 4', not in_game, '%d' % len(in_game))


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=8846)
    ap.add_argument('--quick', action='store_true')
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    t0 = time.time()
    server, port = start_server(a.port)
    print('server on port %d (pid %d)' % (port, server.pid), flush=True)
    try:
        check_regression()
        check_moments()
        check_effects(port)
        check_voices(port)
        check_furniture()
        check_ea(port, a.quick)
    finally:
        stop_server(server)
    time.sleep(0.5)
    check_writes()
    passed = sum(r['ok'] for r in RESULTS)
    summary = {'passed': passed, 'failed': len(RESULTS) - passed, 'seconds': round(time.time() - t0, 1), 'port': port,
               'results': RESULTS}
    with open(os.path.join(OUT, 'report.json'), 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=1)
    with open(os.path.join(OUT, 'report.txt'), 'w', encoding='utf-8') as f:
        for r in RESULTS:
            f.write('%-4s %-10s %-62s %s\n' % ('PASS' if r['ok'] else 'FAIL', r['group'], r['check'][:62], r['detail'][:300]))
        f.write('\n%d passed, %d failed in %.0f s\n' % (passed, len(RESULTS) - passed, summary['seconds']))
    print('\n%d passed, %d failed in %.0f s' % (passed, len(RESULTS) - passed, summary['seconds']))
    sys.exit(0 if passed == len(RESULTS) and RESULTS else 1)


if __name__ == '__main__':
    main()
