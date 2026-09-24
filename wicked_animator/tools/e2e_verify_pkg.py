# Package checks for tools/e2e.js (new export rules: uid-tagged stage names, frame-count clip names, roles,
# CLIMAX hold). Built by cache/fixwave/verify2/e2e/make_tools_e2e.py from cache/e2e/verify_pkg.py.
"""E2E helper: checks packages written by the app's export endpoints.

    python verify_pkg.py single <package> <expect.json>
    python verify_pkg.py bundle <package> <expect.json>

expect.json = {"bakes": [baked project, ...], "packable": [sound names that must be packed], "readme": path, "zip": path,
               "progression": name, "stages": {uid: stage}}
Prints one JSON object: {"checks": [[name, ok, detail], ...], "info": {...}}.
"""
import sys, json, math, os, struct, zipfile, urllib.request
sys.path.insert(0, r'C:\Users\basim\Tools\sims4_animator\backend')
from dbpf import read_index, read_resource          # noqa: E402
from clipfmt import parse_clip, fnv64, decode_frames  # noqa: E402
import exporter as X                                 # noqa: E402
import wwpackage as W                                # noqa: E402
PORT = os.environ.get('ANIMATOR_PORT', '8765')
import xml.etree.ElementTree as ET                  # noqa: E402

SNIPPET, CLIP, HDR, T_SOUND, T_AUDIO = 0x7DF2169C, 0x6B20C4F3, 0xBC4A5044, 0xFD04E3BE, 0x01A527DB
checks, info = [], {}


def C(name, ok, detail=None):
    checks.append([name, bool(ok), detail])


def safe_name(text):
    import re
    s = re.sub(r'[^A-Za-z0-9]+', '_', text).strip('_')
    return s[:60] or 'Animation'


def stage_name(author, name, uid=None):
    return X.stage_name((author or '').strip() or 'Fit Studio', (name or '').strip() or 'My animation', uid)


def ticks_of(bake):
    fps = float(bake.get('fps') or 30)
    hold = int(round(X.HOLD_SECONDS * fps)) if bake.get('category') == 'CLIMAX' and int(bake.get('loops', 10)) == 1 else 0
    return int(bake['frames']) + hold, hold


def parse_snippet(data):
    root = ET.fromstring(data)
    anims = []
    lst = root.find("L[@n='animations_list']")
    for t in (lst.findall('T') if lst is not None else []):
        d = {}
        for x in t.findall('T'):
            n = x.get('n')
            if n == 'animation_actors_list':
                d['actors'] = []
                for a in x.findall('T'):
                    ad = {}
                    for y in a.findall('T'):
                        if y.get('n') == 'actor_interactions':
                            ad['interactions'] = [{z.get('n'): z.text for z in it.findall('T')} for it in y.findall('T')]
                        else:
                            ad[y.get('n')] = y.text
                    d['actors'].append(ad)
            else:
                d[n] = x.text
        anims.append(d)
    return root, anims


RIG = None


def rig_hashes():
    global RIG
    if RIG is None:
        r = json.load(urllib.request.urlopen('http://127.0.0.1:%s/api/rig?key=au' % PORT))
        RIG = {b['name']: b['hash'] for b in r['bones']}
    return RIG


def qerr(a, b):
    na = math.sqrt(sum(x * x for x in a)) or 1
    nb = math.sqrt(sum(x * x for x in b)) or 1
    d = abs(sum(x * y for x, y in zip(a, b)) / na / nb)
    return math.degrees(2 * math.acos(min(1.0, d)))


def verify_clip(pkg, idx, clip_name, bake, actor, label):
    frames, fps = int(bake['frames']), float(bake.get('fps', 30))
    ticks, hold = ticks_of(bake)
    inst = fnv64(clip_name)
    clips = [e for e in idx if e['type'] == CLIP and e['inst'] == inst]
    hdrs = [e for e in idx if e['type'] == HDR and e['inst'] == inst]
    C(f'{label}: CLIP instance == fnv64("{clip_name}")', len(clips) == 1, '%d found' % len(clips))
    C(f'{label}: clip header with the same instance', len(hdrs) == 1, '%d found' % len(hdrs))
    if not clips:
        return
    c = parse_clip(read_resource(pkg, clips[0]))
    k = c['codec']
    C(f'{label}: clip name inside the CLIP matches', c.get('clip_name') == clip_name and k['name'] == clip_name, [c.get('clip_name'), k['name']])
    C(f'{label}: tick count = project frames + hold ({ticks})', k['num_ticks'] == ticks, k['num_ticks'])
    C(f'{label}: duration = ticks/fps', abs(c['duration'] - ticks / fps) < 1e-4, c['duration'])
    bad, maxtick, nchan = 0, 0, 0
    decoded = {}
    for ch in k['channels']:
        nchan += 1
        fr = decode_frames(ch)
        for tick, vals in fr:
            maxtick = max(maxtick, tick)
            if not all(math.isfinite(v) for v in vals):
                bad += 1
        decoded[(ch['target'], ch['sub'])] = fr
    C(f'{label}: every decoded channel value is finite ({nchan} channels)', bad == 0, bad)
    C(f'{label}: no key past the last tick', maxtick <= ticks - 1, maxtick)
    # the decoded clip reproduces the baked tracks
    H = rig_hashes()
    worst_q, worst_t, compared = 0.0, 0.0, 0
    for bone, tr in actor['tracks'].items():
        h = H.get(bone)
        if h is None:
            continue
        for sub, key in ((2, 'r'), (1, 't')):
            vals = tr.get(key)
            fr = decoded.get((h, sub))
            if not vals or fr is None:
                continue
            m = dict(fr)
            for f in range(0, frames, 7):
                got = m.get(f) if len(fr) > 1 else fr[0][1]
                if got is None:
                    continue
                want = vals[f]
                compared += 1
                if sub == 2:
                    worst_q = max(worst_q, qerr(got, want))
                else:
                    worst_t = max(worst_t, max(abs(a - b) for a, b in zip(got, want)))
    C(f'{label}: decoded clip matches the baked pose (rot < 0.5 deg, pos < 2 mm)', compared > 0 and worst_q < 0.5 and worst_t < 0.002,
      {'compared': compared, 'worst_rot_deg': round(worst_q, 4), 'worst_pos_m': round(worst_t, 5)})
    # events
    snd = []
    lip = False
    for et, d in c['events']:
        if et == 3:
            sec = struct.unpack_from('<f', d, 8)[0]
            name = d[12:140].split(b'\0')[0].decode('ascii', 'replace')
            snd.append((round(sec, 4), name))
        if et == 19:
            lip = True
    want = sorted(((round(s['frame'] / fps, 4), s['name']) for s in actor.get('sounds') or []))
    C(f'{label}: sound events at the right seconds ({len(want)})', sorted(snd) == want,
      None if sorted(snd) == want else {'got': sorted(snd)[:8], 'want': want[:8]})
    voices = any(s.get('kind') == 'voice' for s in actor.get('sounds') or [])
    want_lip = bool(voices or actor.get('mouthMoves') or actor.get('tongueUsed'))
    C(f'{label}: lip-sync-off exactly when voice/mouthMoves/tongueUsed (v={voices}, m={actor.get("mouthMoves")}, t={actor.get("tongueUsed")})', lip == want_lip, lip)
    hc = parse_clip(read_resource(pkg, hdrs[0]) + b'\0' * 64) if hdrs else None
    if hc:
        C(f'{label}: clip header names the clip and carries the same events', hc.get('clip_name') == clip_name and len(hc['events']) == len(c['events']),
          [hc.get('clip_name'), len(hc['events']), len(c['events'])])
    info[clip_name] = {'channels': nchan, 'events': len(c['events']), 'sounds': len(snd)}


def verify_anim(pkg, idx, snip, bake, label, expect_next=None, expect_random=None):
    base = stage_name(bake.get('author'), bake.get('name'), bake.get('uid'))
    data = read_resource(pkg, snip)
    try:
        root, anims = parse_snippet(data)
        C(f'{label}: snippet XML is well-formed', True)
    except ET.ParseError as ex:
        C(f'{label}: snippet XML is well-formed', False, str(ex))
        return None
    C(f'{label}: snippet class/name/instance', root.get('c') == 'WickedWoohooAnimationPackage' and root.get('n') == base
      and int(root.get('s')) == (fnv64(base) | (1 << 63)) and snip['inst'] == int(root.get('s')),
      [root.get('c'), root.get('n'), root.get('s'), snip['inst']])
    C(f'{label}: one animation in the snippet', len(anims) == 1, len(anims))
    a = anims[0]
    C(f'{label}: display name / author', a.get('animation_raw_display_name') == bake['name'] and a.get('animation_author') == bake['author'],
      [a.get('animation_raw_display_name'), a.get('animation_author')])
    C(f'{label}: category', a.get('animation_category') == bake['category'], a.get('animation_category'))
    C(f'{label}: locations', a.get('animation_locations') == ', '.join(bake['locations']), a.get('animation_locations'))
    C(f'{label}: loops', a.get('animation_loops') == str(int(bake.get('loops', 10))), a.get('animation_loops'))
    C(f'{label}: stage name', a.get('animation_stage_name') == base, a.get('animation_stage_name'))
    tags = [t.strip() for t in (a.get('animation_tags') or '').split(',') if t.strip()]
    want_tags = list(bake.get('tags') or [])
    voices = any(s.get('kind') == 'voice' for ac in bake['actors'] for s in ac.get('sounds') or [])
    if voices and 'CUSTOM_VOICE_SFX' not in want_tags:
        want_tags.append('CUSTOM_VOICE_SFX')
    C(f'{label}: tags', tags == want_tags, {'got': tags, 'want': want_tags})
    actors = a.get('actors') or []
    C(f'{label}: actors = sims ({len(bake["actors"])})', len(actors) == len(bake['actors']), len(actors))
    ticks, hold = ticks_of(bake)
    if hold:
        C(f'{label}: CLIMAX played once has animation_negative_duration_offset', a.get('animation_negative_duration_offset') is not None and abs(float(a['animation_negative_duration_offset']) - hold / float(bake.get('fps') or 30)) < 1e-3, a.get('animation_negative_duration_offset'))
    else:
        C(f'{label}: no negative duration offset', a.get('animation_negative_duration_offset') is None, a.get('animation_negative_duration_offset'))
    pairs = W.interaction_pairs([{'gender': b['gender'], 'body': b.get('body'), 'role': b.get('role')} for b in bake['actors']])
    act = bake['category'] if bake['category'] != 'CLIMAX' else (bake.get('act') or 'VAGINAL')
    for i, (ax, bx) in enumerate(zip(actors, bake['actors'])):
        clip = '%s_%df_%d' % (base, ticks, i + 1)
        role = W.role_of({'gender': bx['gender'], 'body': bx.get('body'), 'role': bx.get('role')})
        want_tags = (['ROLE_GIVER'] if role in ('giver', 'both') else []) + (['ROLE_RECEIVER'] if role in ('receiver', 'both') else [])
        C(f'{label}: actor {i} tags {want_tags}', [t.strip() for t in (ax.get('animation_actor_tags') or '').split(',') if t.strip()] == want_tags, ax.get('animation_actor_tags'))
        so = ax.get('animation_allow_strapon') == '1'
        want_so = bool(bx.get('strapon')) or (bx['gender'] == 'MALE' and role != 'receiver')
        C(f'{label}: actor {i} strapon {want_so} (role {role}, gender {bx["gender"]}, strapon {bx.get("strapon")})', so == want_so, ax.get('animation_allow_strapon'))
        if role == 'receiver' and bx['gender'] == 'FEMALE' and not bx.get('strapon'):
            C(f'{label}: receiving woman {i} never gets a strap-on', not so)
        if bx['gender'] == 'BOTH':
            C(f'{label}: actor {i} BOTH has pref gender', ax.get('animation_pref_gender') == X.PREF_GENDER.get(bx.get('body')), ax.get('animation_pref_gender'))
        want_feet = bool(bx.get('bareFeet')) or bake['category'] == 'FOOTJOB'
        C(f'{label}: actor {i} nude feet {want_feet}', (ax.get('animation_force_nude_feet') == '1') == want_feet, ax.get('animation_force_nude_feet'))
        C(f'{label}: actor {i} visible tongue == tongueUsed {bool(bx.get("tongueUsed"))}', (ax.get('animation_has_visible_tongue') == '1') == bool(bx.get('tongueUsed')), ax.get('animation_has_visible_tongue'))
        mine = [(t, m) for f, t, m in pairs if f == i]
        got = ax.get('interactions') or []
        C(f'{label}: actor {i} interactions follow interaction_pairs', [int(g.get('receiving_actor_id')) for g in got] == [t for t, _ in mine], {'got': got, 'want': mine})
        for g, (t, m) in zip(got, mine):
            cum = m and W.has_penis({'gender': bx['gender'], 'body': bx.get('body')})
            C(f'{label}: actor {i}->{t} cum layer', g.get('receiving_actor_cum_layers') == (W.CUM_LAYERS.get(act) if cum else None), g)
            C(f'{label}: actor {i}->{t} cum inside', g.get('receiving_actor_cum_inside') == ('1' if cum and act in W.CUM_INSIDE_ACTS else '0'), g)
            C(f'{label}: actor {i}->{t} category {act}', g.get('receiving_actor_category') == act, g)
        C(f'{label}: actor {i} clip name', ax.get('animation_clip_name') == clip, ax.get('animation_clip_name'))
        C(f'{label}: actor {i} gender {bx["gender"]}', ax.get('animation_genders') == bx['gender'], ax.get('animation_genders'))
        C(f'{label}: actor {i} naked type', ax.get('animation_naked_type') == (bx.get('naked') or bake.get('naked')), ax.get('animation_naked_type'))
        if bx['gender'] == 'FEMALE' and bx.get('body') == 'yf':
            C(f'{label}: animation_has_animated_vagina on the female actor', ax.get('animation_has_animated_vagina') == '1',
              {'xml': ax.get('animation_has_animated_vagina'), 'bake.animatedVagina': bx.get('animatedVagina')})
        if bx['gender'] == 'MALE':
            C(f'{label}: no animated vagina flag on the male actor', ax.get('animation_has_animated_vagina') is None, ax.get('animation_has_animated_vagina'))
        verify_clip(pkg, idx, clip, bake, bx, f'{label} actor {i}')
    nxt = [x.strip() for x in (a.get('animation_next_stages') or '').split(',') if x.strip()]
    if expect_next is not None:
        C(f'{label}: animation_next_stages = {expect_next}', nxt == expect_next, nxt)
    if expect_random is not None:
        got = a.get('animation_allowed_for_random')
        C(f'{label}: animation_allowed_for_random {"absent" if expect_random else "0"}', (got is None) if expect_random else (got == '0'), got)
    return base


def main():
    mode, pkg, exp_path = sys.argv[1], sys.argv[2], sys.argv[3]
    exp = json.load(open(exp_path, encoding='utf-8'))
    C('package file exists', os.path.isfile(pkg), pkg)
    idx = read_index(pkg)
    snips = [e for e in idx if e['type'] == SNIPPET]
    info['resources'] = len(idx)
    info['by_type'] = {}
    for e in idx:
        info['by_type']['%08X' % e['type']] = info['by_type'].get('%08X' % e['type'], 0) + 1
    bakes = exp['bakes']
    C('one snippet per animation (%d)' % len(bakes), len(snips) == len(bakes), len(snips))
    keys = [(e['type'], e['group'], e['inst']) for e in idx]
    C('no duplicate resource keys', len(keys) == len(set(keys)), len(keys) - len(set(keys)))
    n_clips = sum(1 for e in idx if e['type'] == CLIP)
    C('one CLIP per sim', n_clips == sum(len(b['actors']) for b in bakes), n_clips)
    by_name = {b['name']: stage_name(b.get('author'), b.get('name'), b.get('uid')) for b in bakes}
    C('stage names unique in the package', len(set(by_name.values())) == len(bakes), by_name)
    info['stage_names'] = by_name
    for i, b in enumerate(bakes):
        base = stage_name(b.get('author'), b.get('name'), b.get('uid'))
        s = [e for e in snips if e['inst'] == (fnv64(base) | (1 << 63))]
        if not s:
            C(f'snippet for "{b["name"]}"', False, 'missing')
            continue
        en = exp.get('next', {}).get(b['name'])
        if en is not None:
            en = [by_name.get(x, x) for x in en]
        er = exp.get('random', {}).get(b['name'])
        verify_anim(pkg, idx, s[0], b, b['name'], en, er)
    packable = exp.get('packable') or []
    if mode == 'bundle':
        sound_insts = {e['inst'] for e in idx if e['type'] == T_SOUND}
        missing = [n for n in packable if fnv64(n) not in sound_insts and (fnv64(n) | (1 << 63)) not in sound_insts]
        C('every sound from other mods is packed (%d)' % len(packable), not missing, missing)
        info['sound_resources'] = len(sound_insts)
        info['audio_resources'] = sum(1 for e in idx if e['type'] == T_AUDIO)
        if packable:
            C('packed sounds bring their audio', info['audio_resources'] > 0, info['audio_resources'])
        rd = exp.get('readme')
        if rd:
            C('README exists', os.path.isfile(rd), rd)
            if os.path.isfile(rd):
                txt = open(rd, encoding='utf-8').read()
                C('README lists every animation', all(b['name'] in txt for b in bakes))
                if exp.get('progression'):
                    C('README lists the progression', 'PROGRESSIONS' in txt and exp['progression'] in txt, txt[-600:])
        zp = exp.get('zip')
        if zp:
            C('zip exists', os.path.isfile(zp), zp)
            if os.path.isfile(zp):
                with zipfile.ZipFile(zp) as z:
                    names = z.namelist()
                    C('zip holds the .package and README.txt', any(n.endswith('.package') for n in names) and 'README.txt' in names, names)
                    pk = [n for n in names if n.endswith('.package')]
                    if pk:
                        C('zipped package = the package on disk', z.read(pk[0]) == open(pkg, 'rb').read())
    print(json.dumps({'checks': checks, 'info': info}))


if __name__ == '__main__':
    try:
        main()
    except Exception as ex:
        import traceback
        C('verifier ran', False, traceback.format_exc())
        print(json.dumps({'checks': checks, 'info': info}))
