"""R1-E checks 1-4: the Game Doctor scan, Park / Turn back on, the WickedWhims log, and the real folder (read-only).

    python tools/checks/r1e/doctor_check.py [--skip-real]

1. Fixture  %TEMP%\\wa_doctor\\The Sims 4 (WICKED_SIMS_DIR), built here from resources copied out of real packages
   (read-only) plus hand-made XML: a script 3 folders deep, a non-WW package with an auRig RIG, an animation XML
   with the placeholder place, LOVESE, ORLAJOB and a missing clip, a disabled list with [10, 2], two packs with the
   same clip name, two body overrides of one part, a pack the adult filter hides, plus the user's own tools built
   to look like problems (the Sims Hub's SpeedKit_Monitor.ts4script and fast packs, a sound kit in Mods\\FitStudio,
   two versions of one pack in Mods\\animation): never a problem, never offered for parking.
2. Park (fixture only): the move, the manifest compared byte for byte with one mods_switch.py's own save_manifest
   writes in a temp dir, refusal while a (fake) TS4_x64.exe runs; Mods\\FitStudio, Mods\\animation, the Sims Hub's
   files and WickedWhims' files refused.
3. Log: the real sample lines give 1 played + 1 problem for the author, other authors ignored; a 20 MB log in < 1 s.
4. Real folder, read-only: the scan completes; Mods / Mods_parked / WickedWhims' settings unchanged; timings; the
   user's own tools are never a problem.

Prints a PASS/FAIL table, writes cache/checks/r1e/doctor_check.json, exits 0 only when everything passes.
"""
import json
import os
import shutil
import sys
import tempfile
import time
import zipfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
BACKEND = os.path.join(ROOT, 'backend')
OUT = os.path.join(ROOT, 'cache', 'checks', 'r1e')
sys.path.insert(0, BACKEND)

REAL_SIMS = os.path.join(os.path.expanduser('~'), 'Documents', 'Electronic Arts', 'The Sims 4')
FIX_ROOT = os.path.join(tempfile.gettempdir(), 'wa_doctor')
FIX = os.path.join(FIX_ROOT, 'The Sims 4')
BIG = os.path.join(tempfile.gettempdir(), 'wa_doctor_big', 'The Sims 4')
MODS_SWITCH = r'C:\Users\basim\Tools\sims4_fitstudio\mods_switch.py'
NOT_RUNNING = 'INFO: No tasks are running which match the specified criteria.\r\n'
RUNNING = '\r\nTS4_x64.exe                  24816 Console                    1  4,512,300 K\r\n'

rows = []


def check(name, ok, detail=''):
    rows.append({'name': name, 'ok': bool(ok), 'detail': detail})
    return ok


# ------------------------------------------------------------------ fixture
SAMPLE_LOG = [
    "09/24/26 01:53:38 [VERSION_REGISTRY/INFO] Running The Sims 4 version 1.126.73.1030...",
    "09/24/26 01:53:38 [VERSION_REGISTRY/INFO] Running WickedWhims v185k...",
    "09/24/26 02:04:50 [ANIMATIONS/WARN] [INVALID EVENT] Sex Animation 'FS Proof' by 'FitStudio test' has invalid effect event.",
    "09/24/26 02:04:50 [ANIMATIONS/WARN] [INVALID EVENT] Sex Animation 'Other Anim' by 'Someone Else' has invalid cum type event.",
    "09/24/26 02:04:53 [ANIMATIONS/INFO] Loaded 235 sex animation tunings with valid 235 animation instances and 2 animation overrides.",
    "09/24/26 02:04:53 [ANIMATIONS/INFO] Disabled Animations: 0 individually, 20 dynamically.",
    "09/24/26 02:04:54 [ANIMATIONS/INFO] Took 7.239s to load 212 available sex animations.",
    "09/24/26 02:06:15 [SEX/INFO] Sims  played 'FS Proof' sex animation by 'FitStudio test'.",
    "09/24/26 02:06:15 [SEX/INFO] Sims 'Male Sim 1'+'Female Sim 2' played 'FS Proof' sex animation by 'FitStudio test'.",
    "09/24/26 02:07:02 [SEX/INFO] Sims 'Sim A'+'Sim B' played 'Stay Still_Fingering' sex animation by 'LAMABOY'.",
]


def real_played_lines():
    """The played lines from the user's own log (read-only), so the check uses the real text."""
    p = os.path.join(REAL_SIMS, 'WickedWhimsInfoLog.log')
    out = []
    try:
        with open(p, 'rb') as f:
            for raw in f:
                if b"played '" in raw and b'sex animation by' in raw:
                    out.append(raw.decode('utf-8', 'replace').rstrip('\r\n'))
    except OSError:
        pass
    return out


def anim_xml(pkg_name, anims):
    """A WickedWhims animation snippet in the template's layout."""
    parts = ['<?xml version="1.0" encoding="utf-8"?>',
             '<I c="WickedWhimsAnimationPackage" i="snippet" m="wickedwhims.sex.animations.animations_tuning" n="%s" s="%d">'
             % (pkg_name, abs(hash(pkg_name)) % 10 ** 17),
             '  <T n="wickedwhims_animations">1</T>', '  <L n="animations_list">']
    for a in anims:
        parts.append('    <U>')
        parts.append('      <T n="animation_raw_display_name">%s</T>' % a['name'])
        parts.append('      <T n="animation_author">%s</T>' % a.get('author', 'Doctor Fixture'))
        if a.get('locations') is not None:
            parts.append('      <T n="animation_locations">%s</T>' % a['locations'])
        if a.get('custom'):
            parts.append('      <T n="animation_custom_locations">%s</T>' % a['custom'])
        parts.append('      <T n="animation_category">%s</T>' % a.get('category', 'VAGINAL'))
        parts.append('      <L n="animation_actors_list">')
        for i, (clip, typ, gender) in enumerate(a['actors']):
            parts.append('        <U><T n="actor_id">%d</T><T n="animation_clip_name">%s</T><T n="animation_type">%s</T>'
                         '<T n="animation_genders">%s</T></U>' % (i, clip, typ, gender))
        parts.append('      </L>')
        parts.append('    </U>')
    parts += ['  </L>', '</I>']
    return '\n'.join(parts).encode('utf-8')


def build_fixture():
    import dbpf, doctor, wwpackage
    from clipfmt import fnv64
    tmp = os.path.abspath(tempfile.gettempdir()).lower()
    if not os.path.abspath(FIX_ROOT).lower().startswith(tmp):
        raise SystemExit('fixture must live in %TEMP%')
    shutil.rmtree(FIX_ROOT, ignore_errors=True)
    mods = os.path.join(FIX, 'Mods')
    os.makedirs(mods)
    w = lambda rel, data: _write(os.path.join(FIX, rel), data)

    real_mods = os.path.join(REAL_SIMS, 'Mods')
    ww_tuning = os.path.join(real_mods, 'scripts', 'TURBODRIVER_WickedWhims_Tuning.package')
    ww_script = os.path.join(real_mods, 'scripts', 'TURBODRIVER_WickedWhims_Scripts.ts4script')
    lama = os.path.join(real_mods, 'animation', 'WW_LAMABOY_Animation.package')
    own = os.path.join(real_mods, 'FitStudio', 'MyAnimations')

    # resources copied out of the real packages (read-only)
    idx = dbpf.read_index(ww_tuning)
    nude = doctor.nude_parts(ww_tuning)
    rig = next(e for e in idx if e['type'] == doctor.T_RIG and (e['inst'] & doctor.LOW) == doctor.AURIG)
    rig_res = (doctor.T_RIG, rig['group'], rig['inst'], dbpf.read_resource(ww_tuning, rig))
    casps = [(doctor.T_CASP, e['group'], e['inst'], dbpf.read_resource(ww_tuning, e)) for e in idx
             if e['type'] == doctor.T_CASP and e['inst'] in nude]
    yf_bottom = next(r for r in casps if r[2] == 0x1990)
    lidx = [e for e in dbpf.read_index(lama) if e['type'] == doctor.T_CLIP][:4]
    clip_bytes = [dbpf.read_resource(lama, e) for e in lidx]

    w('Mods/Resource.cfg', b'Priority 500\r\n' + b''.join(b'PackedFile ' + b'*/' * k + b'*.package\r\n' for k in range(6)))
    _mk(mods, 'scripts')
    shutil.copyfile(ww_script, os.path.join(mods, 'scripts', 'TURBODRIVER_WickedWhims_Scripts.ts4script'))
    w('Mods/scripts/TURBODRIVER_WickedWhims_Tuning.package', wwpackage.build_package([rig_res] + casps))
    # 1. a script mod three folders deep
    zbuf = os.path.join(FIX_ROOT, 'script.zip')
    with zipfile.ZipFile(zbuf, 'w') as z:
        z.writestr('fixture_mod/__init__.py', '# fixture\n')
    _mk(mods, 'Deep', 'One', 'Two')
    shutil.copyfile(zbuf, os.path.join(mods, 'Deep', 'One', 'Two', 'Bad_Script.ts4script'))
    # 2. a non-WickedWhims package with WickedWhims' rig inside
    w('Mods/RigMod/Old_Rig_Fix.package', wwpackage.build_package([rig_res]))
    # two body overrides of the same nude part (female bottom)
    w('Mods/Bodies/Body_A_Bottom.package', wwpackage.build_package([yf_bottom]))
    w('Mods/Bodies/Body_B_Bottom.package', wwpackage.build_package([yf_bottom]))
    # 3. animation pack A: one good animation and one of each mistake
    hi = 1 << 63
    A = [
        {'name': 'Fixture Good', 'locations': 'FLOOR', 'actors': [('TestA_ok_x', 'VAGINAL', 'FEMALE'), ('TestA_shared_y', 'VAGINAL', 'MALE')]},
        {'name': 'Fixture Placeholder', 'locations': '', 'custom': '123456789, 987654321', 'actors': [('TestA_ok_x', 'VAGINAL', 'FEMALE')]},
        {'name': 'Fixture Loveseat', 'locations': 'LOVESE', 'actors': [('TestA_ok_x', 'VAGINAL', 'FEMALE')]},
        {'name': 'Fixture Oral', 'locations': 'SOFA', 'category': 'ORLAJOB', 'actors': [('TestA_ok_x', 'ORALJOB', 'FEMALE')]},
        {'name': 'Fixture Missing Clip', 'locations': 'DOUBLE_BED', 'actors': [('TestA_missing_clip_z', 'VAGINAL', 'FEMALE')]},
        {'name': 'Fixture Odd Act', 'locations': 'FLOOR', 'category': 'HANDJOB', 'actors': [('TestA_ok_x', 'HANJOB', 'FEMALE')]},
    ]
    res_a = [(doctor.T_SNIPPET, 0, fnv64('DoctorFixture:PackA') | hi, anim_xml('DoctorFixture:PackA', A)),
             (doctor.T_CLIP, 0x48000000, fnv64('TestA_ok_x') | hi, clip_bytes[0]),
             (doctor.T_CLIP, 0x48000000, fnv64('TestA_shared_y') | hi, clip_bytes[1])]
    w('Mods/Anims/Test_Pack_A.package', wwpackage.build_package(res_a))
    # 5. pack B: another animation whose clip has the same name as one of A's (different motion)
    B = [{'name': 'Fixture Pack B', 'locations': 'FLOOR', 'actors': [('TestA_shared_y', 'VAGINAL', 'MALE'), ('TestB_own_x', 'VAGINAL', 'FEMALE')]}]
    res_b = [(doctor.T_SNIPPET, 0, fnv64('DoctorFixture:PackB') | hi, anim_xml('DoctorFixture:PackB', B)),
             (doctor.T_CLIP, 0x48000000, fnv64('TestA_shared_y') | hi, clip_bytes[2]),
             (doctor.T_CLIP, 0x48000000, fnv64('TestB_own_x') | hi, clip_bytes[3])]
    w('Mods/Anims/Test_Pack_B.package', wwpackage.build_package(res_b))
    # a pack the adults-only filter hides (a gender that is not an adult one); its names must never show
    H = [{'name': 'Hidden Fixture Name', 'author': 'Hidden Fixture Author', 'locations': 'FLOOR',
          'actors': [('TestH_clip_x', 'VAGINAL', 'UNKNOWN_MALE')]}]
    w('Mods/Anims/Other_Pack.package', wwpackage.build_package(
        [(doctor.T_SNIPPET, 0, fnv64('DoctorFixture:PackH') | hi, anim_xml('DoctorFixture:PackH', H)),
         (doctor.T_CLIP, 0x48000000, fnv64('TestH_clip_x') | hi, clip_bytes[0])]))
    # this app's own export (copied) - never parked
    exports = sorted(f for f in os.listdir(own) if f.endswith('.package')) if os.path.isdir(own) else []
    _mk(mods, 'FitStudio', 'MyAnimations')
    if exports:
        shutil.copyfile(os.path.join(own, exports[0]), os.path.join(mods, 'FitStudio', 'MyAnimations', 'FitStudio_Test_Own.package'))
    else:
        w('Mods/FitStudio/MyAnimations/FitStudio_Test_Own.package', wwpackage.build_package([]))
    # the user's own tools, each built to look like a problem - the Doctor must leave every one alone:
    # the Sims Hub's in-game monitor at the Mods root; its fast packs (merged CC: a nude body, WickedWhims' rig, a
    # motion name another pack uses, an animation with the template's place; and one file no reader can open);
    # Fit Studio's sound kit with a body; and two versions of the same pack in Mods\animation, one with a rig, a
    # missing place and a motion name that Test_Pack_B also uses.
    with zipfile.ZipFile(os.path.join(mods, 'SpeedKit_Monitor.ts4script'), 'w') as z:
        z.writestr('speedkit_monitor/__init__.py', '# fixture\n')
    F = [{'name': 'Fast Copy', 'locations': '', 'custom': '123456789, 987654321', 'actors': [('TestF_missing_q', 'VAGINAL', 'FEMALE')]}]
    w('Mods/!!!!!SpeedKit_Fast_001.package', wwpackage.build_package(
        [rig_res, yf_bottom, (doctor.T_CLIP, 0x48000000, fnv64('TestA_shared_y') | hi, clip_bytes[1]),
         (doctor.T_SNIPPET, 0, fnv64('DoctorFixture:Fast') | hi, anim_xml('DoctorFixture:Fast', F))]))
    w('Mods/!!!!!SpeedKit_Fast_002.package', b'DBPF but not really a package')
    w('Mods/FitStudio/Sounds/FitStudio_Sound_Kit.package', wwpackage.build_package([yf_bottom]))
    O = [{'name': 'Own Pack Anim', 'author': 'Own Creator', 'locations': 'FLOOR', 'actors': [('TestO_x', 'VAGINAL', 'FEMALE')]},
         {'name': 'Own Pack No Place', 'author': 'Own Creator', 'locations': '', 'actors': [('TestO_x', 'VAGINAL', 'FEMALE')]}]
    own_res = [(doctor.T_SNIPPET, 0, fnv64('DoctorFixture:Own') | hi, anim_xml('DoctorFixture:Own', O)),
               (doctor.T_CLIP, 0x48000000, fnv64('TestO_x') | hi, clip_bytes[0])]
    w('Mods/animation/WW_Own_Pack.package', wwpackage.build_package(
        own_res + [(doctor.T_CLIP, 0x48000000, fnv64('TestB_own_x') | hi, clip_bytes[0])]))
    w('Mods/animation/WW_Own_Packs.package', wwpackage.build_package(own_res + [rig_res]))
    # 4. WickedWhims' settings: [10, 2] (its default) and all Oral animations switched off; two single ones
    ww = 'saves/WickedWhimsMod/'
    w(ww + 'dynamic_disabled_animations.json', json.dumps({'disabled_animation_types': [[10, 2], [1, 3]],
                                                            'autonomy_disabled_animation_types': [],
                                                            'controversial_animations_state': False}).encode())
    w(ww + 'all_disabled_animations.json', json.dumps({'disabled_animations': ['9f2c' * 10, '41ab' * 10],
                                                       'autonomy_disabled_animations': [],
                                                       'disabled_dance_animations': []}).encode())
    for name in ('last_version_control.ww',):
        src = os.path.join(REAL_SIMS, 'saves', 'WickedWhimsMod', name)
        if os.path.isfile(src):
            shutil.copyfile(src, os.path.join(FIX, *ww.split('/'), name))
    for name in ('GameVersion.txt', 'Options.ini'):
        src = os.path.join(REAL_SIMS, name)
        if os.path.isfile(src):
            shutil.copyfile(src, os.path.join(FIX, name))
    # Mods_parked with a manifest in mods_switch's format
    w('Mods_parked/Old Folder/readme.txt', b'parked earlier\n')
    w('Mods_parked/_manifest.json', json.dumps({'moved': ['Old Folder/']}, indent=1).encode())
    lines = SAMPLE_LOG[:7] + (real_played_lines() or SAMPLE_LOG[7:9]) + SAMPLE_LOG[9:]
    w('WickedWhimsInfoLog.log', ('\n'.join(lines) + '\n').encode('utf-8'))
    return {'nude_parts': len(nude), 'casps': len(casps), 'clips_copied': len(clip_bytes), 'own_export': bool(exports),
            'log_lines': len(lines)}


def _mk(*parts):
    os.makedirs(os.path.join(*parts), exist_ok=True)
    return True


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data)


# ------------------------------------------------------------------ checks
def by_id(cards, cid):
    return next((c for c in cards if c['id'] == cid), None)


def tool_mentions(cards):
    """Every place a card (other than the green 'own' card) names one of the user's own tools, or offers to park one.
    A clash card may name the user's pack as the one that stays, but never with a button on it."""
    import doctor
    out = []
    for c in cards:
        if c['id'] == 'own':
            continue
        acts = [c.get('action')] + [i.get('action') for i in c.get('items') or []]
        for a in acts:
            if a and a.get('kind') == 'park' and doctor.is_user_tool(a.get('file') or ''):
                out.append((c['id'], 'park', a['file']))
        stays = c['id'].startswith('clips:')
        for i in c.get('items') or []:
            f = i.get('file') or i.get('label') or ''
            if doctor.is_user_tool(f) and not (stays and 'stays' in (i.get('detail') or '')):
                out.append((c['id'], 'item', f))
        if c.get('file') and doctor.is_user_tool(c['file']):
            out.append((c['id'], 'card', c['file']))
        if c['level'] in ('red', 'yellow') and not stays:
            blob = json.dumps(c).lower()
            for word in ('speedkit_monitor', '!!!!!speedkit_fast', 'mods/fitstudio', 'mods/animation/'):
                if word in blob:
                    out.append((c['id'], 'text', word))
    return out


def check_1():
    import doctor
    os.environ['WICKED_SIMS_DIR'] = FIX
    res = doctor.scan()
    cards = res['cards']
    with open(os.path.join(OUT, 'fixture_cards.json'), 'w', encoding='utf-8') as f:
        json.dump(res, f, indent=1, default=str)
    c = by_id(cards, 'depth:scripts')
    check('1a script 3 folders deep -> red', c and c['level'] == 'red' and any(i['file'] == 'Deep/One/Two/Bad_Script.ts4script' for i in c['items']),
          c and c['title'])
    c = by_id(cards, 'rig')
    check('1b non-WW package with auRig RIG -> red "rig clash"', c and c['level'] == 'red'
          and [i['file'] for i in c['items']] == ['RigMod/Old_Rig_Fix.package'] and c['items'][0]['action']['kind'] == 'park',
          c and c['title'])
    c = by_id(cards, 'pack:Anims/Test_Pack_A.package')
    want = {'placeholder': 1, 'unknown_place': 1, 'bad_category': 1, 'missing_clip': 1, 'bad_act': 1}
    labels = ' | '.join(l['label'] for l in (c or {}).get('lines', []))
    check('1c pack A counts: placeholder, LOVESE, ORLAJOB, missing clip (+ odd act)', c and c['counts'] == want
          and c['never'] == 4 and c['total'] == 6 and 'LOVESE' in labels and 'ORLAJOB' in labels and 'TestA_missing_clip_z' in labels,
          '%s | never %s of %s | %s' % (c and c['counts'], c and c['never'], c and c['total'], labels))
    d = next((x for x in cards if x['id'].startswith('dyn:') and x.get('entry') == [10, 2]), None)
    check('1d disabled [10, 2] -> the explanation text', d and 'need a prop' in d['text'] and "normal setting" in d['text'],
          d and d['text'])
    o = next((x for x in cards if x['id'].startswith('dyn:') and x.get('entry') == [1, 3]), None)
    check("1d' disabled [1, 3] -> \"All 'Oral' animations ...\"", o and o['text'].startswith("All 'Oral' animations are switched off")
          and o['action']['label'] == 'Turn back on', o and o['text'])
    s = by_id(cards, 'single:player')
    check('1d" two single ones -> "2 animations are switched off one by one"', s and s['text'].startswith('2 animations are switched off one by one'),
          s and s['text'])
    c = by_id(cards, 'clips:Anims/Test_Pack_A.package|Anims/Test_Pack_B.package')
    check('1e two packs with the same clip name -> a clash card', c and c['level'] == 'yellow' and 'same motion names' in c['title'],
          c and c['text'])
    c = by_id(cards, 'body:female bottom')
    check('1f two body overrides of one part -> "body clash"', c and c['level'] == 'red' and len(c['items']) == 2, c and c['title'])
    c = by_id(cards, 'packs:blocked')
    blob = json.dumps(cards)
    check("1g adult filter: listed only by file name, never previewed", c and [i['label'] for i in c['items']] == ['Other_Pack.package']
          and 'Hidden Fixture' not in blob and 'TestH_clip' not in blob, c and c['title'])
    c = by_id(cards, 'install:ok')
    check('1h WickedWhims installed + versions', c and c['level'] == 'green' and 'v185' in c['title'], c and (c['title'] + ' / ' + c['text']))
    red = [x['title'] for x in cards if x['level'] == 'red']
    check('1i nothing else red', sorted(red) == sorted(["Another mod changes WickedWhims' skeleton", 'More than one body for the female bottom',
                                                        'Script mods are too deep in folders']), red)
    # the user's own tools: never a problem, never offered for parking; one green card lists them
    bad = tool_mentions(cards)
    o = by_id(cards, 'own')
    check("1k your own tools (Sims Hub monitor + fast packs, Mods\\FitStudio, Mods\\animation) are never a problem",
          not bad and o and o['level'] == 'green' and [i['id'] for i in o['items']] == ['fitstudio', 'animation', 'monitor', 'packs']
          and not any(i.get('action') for i in o['items']),
          bad or [(i['label'], i['detail']) for i in (o or {}).get('items', [])])
    c = by_id(cards, 'clips:Anims/Test_Pack_B.package|animation/WW_Own_Pack.package')
    acts = [(i['file'], (i.get('action') or {}).get('kind')) for i in (c or {}).get('items', [])]
    check('1l a clash with one of your own packs offers to park only the other pack', c and c['level'] == 'yellow'
          and sorted(acts) == [('Anims/Test_Pack_B.package', 'park'), ('animation/WW_Own_Pack.package', None)]
          and 'WW_Own_Pack.package is one of your own files and stays' in c['text'], c and c['text'])
    # cache: a second scan reads nothing again
    res2 = doctor.scan()
    check('1j repeat scan uses the cache (path, size, mtime)', res2['summary']['read'] == 0 and res2['summary']['cached'] == res['summary']['read'],
          res2['summary'])
    return res


def check_2():
    import doctor, gamelog
    os.environ['WICKED_SIMS_DIR'] = FIX
    mods, parked = os.path.join(FIX, 'Mods'), os.path.join(FIX, 'Mods_parked')
    gamelog.TASKLIST = lambda: RUNNING
    r = doctor.park('Bodies/Body_A_Bottom.package')
    check('2a refused while TS4_x64.exe runs (fake tasklist)', r['ok'] is False and r['reason'] == 'game_running'
          and os.path.isfile(os.path.join(mods, 'Bodies', 'Body_A_Bottom.package')), r)
    r = doctor.enable({'file': 'dynamic', 'list': 'disabled_animation_types', 'entry': [1, 3]})
    check("2a' Turn back on refused while the game runs", r['ok'] is False and r['reason'] == 'game_running', r)
    gamelog.TASKLIST = lambda: NOT_RUNNING
    r1 = doctor.park('FitStudio/MyAnimations/FitStudio_Test_Own.package')
    r2 = doctor.park('scripts/TURBODRIVER_WickedWhims_Tuning.package')
    r3 = doctor.park('scripts/TURBODRIVER_WickedWhims_Scripts.ts4script')
    try:
        doctor.park('../saves/WickedWhimsMod/all_disabled_animations.json')
        r4 = 'accepted'
    except ValueError as ex:
        r4 = 'ValueError: %s' % ex
    check('2b Mods\\FitStudio and WickedWhims files refused, paths outside Mods refused',
          r1['reason'] == 'own' and r2['reason'] == 'ww' and r3['reason'] == 'ww' and r4.startswith('ValueError')
          and os.path.isfile(os.path.join(mods, 'FitStudio', 'MyAnimations', 'FitStudio_Test_Own.package')), [r1['reason'], r2['reason'], r3['reason'], r4])
    tools = ['SpeedKit_Monitor.ts4script', '!!!!!SpeedKit_Fast_001.package', 'animation/WW_Own_Pack.package',
             'FitStudio/Sounds/FitStudio_Sound_Kit.package']
    rs = [doctor.park(t) for t in tools]
    with open(os.path.join(parked, '_manifest.json'), 'rb') as f:
        man = json.load(f)
    check("2b' the Sims Hub's monitor and fast pack, Mods\\animation and the sound kit are refused (nothing moves)",
          [x['reason'] for x in rs] == ['hub', 'hub', 'own', 'own'] and all(os.path.isfile(os.path.join(mods, *t.split('/'))) for t in tools)
          and man == {'moved': ['Old Folder/']}, [(x['reason'], x['error']) for x in rs])
    r = doctor.park('RigMod/Old_Rig_Fix.package')
    moved = r.get('ok') and not os.path.exists(os.path.join(mods, 'RigMod', 'Old_Rig_Fix.package')) \
        and os.path.isfile(os.path.join(parked, 'RigMod', 'Old_Rig_Fix.package'))
    check('2c Park moves the file to Mods_parked', moved, r)
    with open(os.path.join(parked, '_manifest.json'), 'rb') as f:
        ours = f.read()
    m = json.loads(ours)
    check("2d manifest entry appended (mods_switch's layout: path inside Mods, forward slashes)",
          m == {'moved': ['Old Folder/', 'RigMod/Old_Rig_Fix.package']}, m)
    # mods_switch.py's own functions, run in a temp folder (its source is only read; lean/full are never called)
    before = os.stat(MODS_SWITCH).st_mtime
    ns = {'__name__': 'mods_switch_readonly'}
    with open(MODS_SWITCH, encoding='utf-8') as f:
        exec(compile(f.read(), MODS_SWITCH, 'exec'), ns)
    tmp = tempfile.mkdtemp(prefix='wa_doctor_ms_')
    ns['PARKED'] = tmp
    ns['MANIFEST'] = os.path.join(tmp, '_manifest.json')
    ns['save_manifest']({'moved': ['Old Folder/', 'RigMod/Old_Rig_Fix.package']})
    with open(ns['MANIFEST'], 'rb') as f:
        theirs = f.read()
    ns['MANIFEST'] = os.path.join(parked, '_manifest.json')
    loaded = ns['load_manifest']()
    shutil.rmtree(tmp, ignore_errors=True)
    check("2e manifest bytes == mods_switch.save_manifest's (temp dir)", ours == theirs and loaded == m,
          '%d bytes, identical: %s' % (len(ours), ours == theirs))
    # full() would put it back: the entry points at the parked file and at a free place in Mods
    rel = m['moved'][-1]
    check("2f mods_switch's restore rule finds the parked file", os.path.exists(os.path.join(parked, rel.rstrip('/')))
          and not os.path.exists(os.path.join(mods, rel.rstrip('/'))), rel)
    check('2g mods_switch.py untouched', os.stat(MODS_SWITCH).st_mtime == before, MODS_SWITCH)
    # Turn back on
    r = doctor.enable({'file': 'dynamic', 'list': 'disabled_animation_types', 'entry': [1, 3]})
    backups = [r.get('backup')]
    with open(os.path.join(FIX, 'saves', 'WickedWhimsMod', 'dynamic_disabled_animations.json'), encoding='utf-8') as f:
        dyn = json.load(f)
    check('2h Turn back on removes only that entry (backup kept)', r['ok'] and r['changed'] and dyn['disabled_animation_types'] == [[10, 2]]
          and os.path.isfile(r['backup']) and dyn.get('controversial_animations_state') is False, dyn)
    r = doctor.enable({'file': 'individual'})
    with open(os.path.join(FIX, 'saves', 'WickedWhimsMod', 'all_disabled_animations.json'), encoding='utf-8') as f:
        one = json.load(f)
    check("2i Turn them all back on empties the one-by-one list", r['ok'] and one['disabled_animations'] == [] and 'disabled_dance_animations' in one, one)
    gamelog.TASKLIST = None
    for b in backups + [r.get('backup')]:          # the fixture's backup copies are not kept in the app's cache
        if b and os.path.isfile(b):
            os.remove(b)


def check_3():
    import gamelog
    os.environ['WICKED_SIMS_DIR'] = FIX
    r = gamelog.read('FitStudio test', check_running=False)
    ok = len(r['played']) == 1 and len(r['problems']) == 1 and r['played'][0]['name'] == 'FS Proof' \
        and r['problems'][0]['text'] == 'WickedWhims skipped a moment: the effect needs a name'
    check('3a fixture log: 1 played + 1 problem for the author', ok,
          'played %s @%s sims=%s; problem: %s' % (len(r['played']), r['played'] and r['played'][0]['clock'],
                                                  r['played'] and r['played'][0]['sims'], r['problems'] and r['problems'][0]['text']))
    others = [x['author'] for x in r['played'] + r['problems'] if x['author'].lower() != 'fitstudio test']
    check('3b other authors ignored', not others and r['counts']['played_all'] >= 3 and r['counts']['problems_all'] == 2, r['counts'])
    r2 = gamelog.read('FitStudio test', 'FS Proof', since=time.time() + 3600, check_running=False)
    check('3c "since" hides older lines', not r2['played'] and not r2['problems'], len(r2['played']))
    check('3d session summary (versions, animations ready)', r['session'].get('game_version') == '1.126.73.1030'
          and r['session'].get('ww_version') == 'v185k' and r['session'].get('available') == 212, r['session'])
    # a 20 MB log: only the tail is read
    os.makedirs(BIG, exist_ok=True)
    path = os.path.join(BIG, 'WickedWhimsInfoLog.log')
    filler = "09/24/26 03:00:00 [SEX_AUTONOMY/INFO] Sim Filler Sim is forbidden by the hunger need.\n"
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(SAMPLE_LOG[:2]) + '\n')
        f.write(filler * (20 * 1024 * 1024 // len(filler)))
        f.write('\n'.join(SAMPLE_LOG[2:]) + '\n')
    size = os.path.getsize(path)
    os.environ['WICKED_SIMS_DIR'] = BIG
    t = time.perf_counter()
    r = gamelog.read('FitStudio test', check_running=False)
    dt = time.perf_counter() - t
    check('3e a %.0f MB log is read in < 1 s (tail only)' % (size / 1048576), dt < 1.0 and len(r['played']) == 1 and len(r['problems']) == 1,
          '%.3f s, played %d, problems %d' % (dt, len(r['played']), len(r['problems'])))
    os.environ['WICKED_SIMS_DIR'] = FIX
    shutil.rmtree(os.path.dirname(BIG), ignore_errors=True)       # the 20 MB test log is not kept
    return {'big_log_seconds': round(dt, 3), 'big_log_bytes': size}


def snapshot(root):
    n, total, newest, dirs = 0, 0, 0.0, {}
    for dp, dn, fn in os.walk(root):
        dirs[dp] = os.stat(dp).st_mtime
        for f in fn:
            st = os.stat(os.path.join(dp, f))
            n += 1
            total += st.st_size
            newest = max(newest, st.st_mtime)
    return {'files': n, 'bytes': total, 'newest': newest, 'dirs': len(dirs), 'dir_mtimes': sum(dirs.values())}


def check_4():
    import doctor
    os.environ.pop('WICKED_SIMS_DIR', None)
    roots = {k: os.path.join(REAL_SIMS, *k.split('/')) for k in ('Mods', 'Mods_parked', 'saves/WickedWhimsMod')}
    before = {k: snapshot(v) for k, v in roots.items()}
    top_before = {f: os.stat(os.path.join(REAL_SIMS, f)).st_mtime for f in os.listdir(REAL_SIMS)}
    # the first run: without this check's own caches (cache/doctor), so everything is read from the packages
    for p in (doctor._cache_file(), os.path.join(doctor.CACHE_DIR, 'game_v1.pkl')):
        if os.path.exists(p):
            os.remove(p)
    doctor._game_mem = None
    t = time.time()
    first = doctor.scan()
    t1 = time.time() - t
    t = time.time()
    second = doctor.scan()
    t2 = time.time() - t
    after = {k: snapshot(v) for k, v in roots.items()}
    top_after = {f: os.stat(os.path.join(REAL_SIMS, f)).st_mtime for f in os.listdir(REAL_SIMS)}
    s = first['summary']
    check('4a real folder: the scan completes', first['cards'] and second['cards'] and s['mods_packages'] >= 1,
          '%d cards; %d files in Mods, %d packages set aside, %.1f GB' % (len(first['cards']), s['mods_files'], s['parked_packages'], s['bytes'] / 1e9))
    same = before == after
    check('4b Mods, Mods_parked and WickedWhims settings unchanged (count, bytes, mtimes)', same,
          {k: (before[k]['files'], before[k]['bytes']) for k in before} if same else {'before': before, 'after': after})
    changed = sorted(f for f in top_after if top_before.get(f) != top_after[f])
    check('4c nothing new or changed in the The Sims 4 folder', not changed or all(f in ('WickedWhimsInfoLog.log', 'lastCrash.txt') for f in changed), changed)
    check('4d first full scan < 3 min', t1 < 180, '%.1f s for %.0f GB (%d packages read)' % (t1, s['bytes'] / 1e9, s['read']))
    check('4e repeat scan < 10 s', t2 < 10, '%.2f s (%d cached)' % (t2, second['summary']['cached']))
    bad = tool_mentions(second['cards'])
    o = by_id(second['cards'], 'own')
    check("4f real folder: your own tools (FitStudio, animation, Sims Hub) are never a problem or parked",
          not bad and o and o['level'] == 'green', bad or [(i['label'], i['detail']) for i in o['items']])
    with open(os.path.join(OUT, 'real_cards.json'), 'w', encoding='utf-8') as f:
        json.dump(second, f, indent=1, default=str)
    return {'first_s': round(t1, 2), 'repeat_s': round(t2, 2), 'summary': s,
            'cards': [(c['level'], c['title']) for c in second['cards']]}


def main():
    os.makedirs(OUT, exist_ok=True)
    info = {}
    info['fixture'] = build_fixture()
    if '--build-fixture' in sys.argv:            # doctor_ui.js: a fresh fixture for the UI run, nothing else
        with open(os.path.join(FIX_ROOT, 'tasklist.txt'), 'w', encoding='utf-8') as f:
            f.write(NOT_RUNNING)
        print(json.dumps({'fixture': FIX, 'tasklist': os.path.join(FIX_ROOT, 'tasklist.txt'), **info['fixture']}))
        return
    check('0 fixture built in %TEMP%', os.path.isdir(os.path.join(FIX, 'Mods')), FIX)
    check_1()
    check_2()
    info['log'] = check_3()
    if '--skip-real' not in sys.argv:
        info['real'] = check_4()
    w = max(len(r['name']) for r in rows)
    print('\nR1-E doctor_check')
    print('-' * 120)
    for r in rows:
        d = r['detail'] if isinstance(r['detail'], str) else json.dumps(r['detail'], default=str)
        print('%s  %s  %s' % ('PASS' if r['ok'] else 'FAIL', r['name'].ljust(w), d[:300]))
    bad = sum(1 for r in rows if not r['ok'])
    print('-' * 120)
    print('%d PASS, %d FAIL' % (len(rows) - bad, bad))
    with open(os.path.join(OUT, 'doctor_check.json'), 'w', encoding='utf-8') as f:
        json.dump({'rows': rows, 'info': info}, f, indent=1, default=str)
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
