"""R2-6 check (the backend): pose packs laid out like Sims 4 Studio's, the adults-only lock, the promo kit's post text,
and that nothing is written outside %TEMP%.

    python tools/checks/r2-6/posepack_check.py [--port 8856]

1. The reference: one adult S4S pose pack from the user's Mods (read only): "Kd89_3dstudios:PosePack_202501180016151289"
   ("[Kd89] She knows how to play - Animation", F + M on a couch) in the merged Mods_parked packages. Its resources are
   counted (snippet, clips, clip headers, pictures, string tables and their languages), its XML fields listed, its
   clips read; the S4S picture size is the most common one over every pose pack in that package. Cached in
   cache/checks/r2-6/reference.json (read again when the package changes).
2. Our packs are built offline into %TEMP% from the requests the app sent in share_ui.js (cache/checks/r2-6/
   posepack_couple1.json: a couple, 1 key; posepack_solo3.json: one sim, 3 keys) - or from the rig's rest pose when
   those are missing - and compared with the reference.
3. The lock refuses explicit requests with the one-line message.
4. The server: POST /api/posepack and /api/promo_save against a server whose WICKED_EXPORTS_DIR is a %TEMP% folder;
   the real exports folder and Mods\\FitStudio are listed before and after (nothing changes).
Exits 0 only when everything passes.
"""
import base64, collections, glob, json, os, re, struct, sys, tempfile, time, urllib.request, zlib
import xml.etree.ElementTree as ET

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
BACKEND = os.path.join(ROOT, 'backend')
OUT = os.path.join(ROOT, 'cache', 'checks', 'r2-6')
sys.path.insert(0, BACKEND)
sys.path.insert(0, os.path.join(ROOT, 'tools', 'checks', 'lib'))
import harness as H          # noqa: E402
import gamedata as G         # noqa: E402
import posepack as PP        # noqa: E402
import ext_share             # noqa: E402
import texfmt                # noqa: E402
from clipfmt import fnv64, parse_clip, decode_track   # noqa: E402
from dbpf import read_index, read_resource              # noqa: E402

REF = 'Kd89_3dstudios:PosePack_202501180016151289'
REF_PKG = os.path.join(G.PARKED_DIR, 'animation', 'anim1.package')
rows = []


def check(name, ok, detail=''):
    rows.append((name, bool(ok), detail))
    print('%s  %s  %s' % ('PASS' if ok else 'FAIL', name, str(detail)[:300]))
    return ok


def png(path, rgba, w, h):
    raw = b''.join(b'\x00' + bytes(rgba[y * w * 4:(y + 1) * w * 4]) for y in range(h))
    chunk = lambda t, d: struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xFFFFFFFF)
    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0))
                + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


def xml_fields(xml):
    """The XML's shape without its values: element tags with their n= names, in order (one pose entry only)."""
    root = ET.fromstring(xml)
    out = [('I', root.get('c'), root.get('m'), root.get('i'))]
    for el in root:
        if el.tag == 'L':
            out.append(('L', el.get('n')))
            first = el[0] if len(el) else None
            if first is not None:
                out.append(('item', tuple(c.get('n') for c in first)))
        else:
            out.append((el.tag, el.get('n')))
    return out


# ------------------------------------------------------------------ 1. the reference (read only)
def find_pack(path, name):
    idx = read_index(path)
    snip = None
    for e in idx:
        if e['type'] != PP.T_SNIPPET:
            continue
        d = read_resource(path, e)
        if b'PosePackInstance' in d[:600] and ('n="%s"' % name).encode() in d[:600]:
            snip = (e, d.decode('utf-8'))
            break
    return idx, snip


def reference():
    cache = os.path.join(OUT, 'reference.json')
    st = os.stat(REF_PKG) if os.path.isfile(REF_PKG) else None
    if st and os.path.isfile(cache):
        c = json.load(open(cache, encoding='utf-8'))
        if c.get('mtime') == st.st_mtime and c.get('size') == st.st_size:
            return c
    paths = [REF_PKG] if st else sorted(glob.glob(os.path.join(G.PARKED_DIR, '**', '*.package'), recursive=True)
                                         + glob.glob(os.path.join(G.MODS_DIR, '**', '*.package'), recursive=True))
    for path in paths:
        idx, snip = find_pack(path, REF)
        if not snip:
            continue
        e, xml = snip
        by = collections.defaultdict(list)
        for x in idx:
            by[x['inst']].append(x)
        poses = re.findall(r'<T n="pose_name">([^<]*)</T>', xml)
        types = collections.Counter({'%08X' % PP.T_SNIPPET: 1})
        clips = []
        for pn in poses:
            for x in by.get(fnv64(pn), []):
                types['%08X' % x['type']] += 1
                if x['type'] == PP.T_CLIP:
                    c = parse_clip(read_resource(path, x))
                    clips.append({'version': c['version'], 'rig': c['rig_ns'], 'events': [t for t, _ in c['events']],
                                  'ev19': [b.hex() for t, b in c['events'] if t == 19], 'ticks': c['codec']['num_ticks']})
        icons = set(int(v, 16) for v in re.findall(r'2f7d0004:00000000:([0-9a-f]+)', xml))
        for ic in icons:
            for x in by.get(ic, []):
                types['%08X' % x['type']] += 1
        keys = set(int(v, 16) for v in re.findall(r'>0x([0-9A-Fa-f]{8})<', xml) if int(v, 16))
        langs = []
        for x in idx:
            if x['type'] == PP.T_STBL and x['group'] == PP.STBL_GROUP:
                d = read_resource(path, x)
                if d[:4] == b'STBL' and keys & set(PP.read_stbl(d)):
                    langs.append('%02X' % (x['inst'] >> 56))
                    types['%08X' % PP.T_STBL] += 1
        # the picture size S4S writes: the most common one over every pose pack in this package
        sizes = collections.Counter()
        for x in idx:
            if x['type'] != PP.T_SNIPPET:
                continue
            d = read_resource(path, x)
            if b'PosePackInstance' not in d[:600]:
                continue
            for v in re.findall(rb'<T n="sort_order">\d+</T><T n="icon">2f7d0004:00000000:([0-9a-f]+)', d)[:3]:
                for y in by.get(int(v, 16), []):
                    if y['type'] == PP.T_IMG:
                        dd = read_resource(path, y)
                        if dd[:4] == b'DDS ':
                            sizes[(struct.unpack_from('<I', dd, 16)[0], struct.unpack_from('<I', dd, 12)[0], dd[84:88].decode('latin1'),
                                   struct.unpack_from('<I', dd, 28)[0])] += 1
        top = sizes.most_common(1)[0] if sizes else ((0, 0, '', 0), 0)
        out = {'package': os.path.relpath(path, G.SIMS_DIR), 'mtime': os.stat(path).st_mtime, 'size': os.stat(path).st_size,
               'name': REF, 'poses': len(poses), 'types': dict(types), 'languages': sorted(langs), 'fields': xml_fields(xml),
               'clips': clips, 'snippet_instance_ok': e['inst'] == (fnv64(REF) | 1 << 63),
               'icon_format': list(top[0]), 'icon_format_count': top[1], 'icon_formats_total': sum(sizes.values()),
               'sort_name': re.search(r'<T n="sort_name">([^<]*)</T>', xml).group(1)}
        json.dump(out, open(cache, 'w', encoding='utf-8'), indent=1)
        return out
    return None


# ------------------------------------------------------------------ helpers
def load_req(name, fallback):
    p = os.path.join(OUT, name)
    if os.path.isfile(p):
        return json.load(open(p, encoding='utf-8')), True
    return fallback, False


def rest_request(n_sims, n_keys):
    rig = G.rig('au')
    tracks = {b['name']: {'t': [b['pos']], 'r': [b['rot']]} for b in rig['bones']}
    pic = {'w': 64, 'h': 64, 'rgba': base64.b64encode(bytes([120, 60, 140, 255]) * 4096).decode()}
    poses = [{'label': 'Pose %d - Sim %d' % (k + 1, s + 1), 'sim': s, 'frame': k * 30, 'tracks': tracks, 'icon': pic}
             for k in range(n_keys) for s in range(n_sims)]
    return {'name': 'R26 rest poses', 'author': 'Novulon', 'uid': 'a-r26', 'install': False,
            'meta': {'category': 'TEASING', 'tags': [], 'events': [], 'actors': [{'naked': 'NONE', 'keyed': []}] * n_sims},
            'poses': poses, 'icon': pic}


def decoded(req):
    """The request as the server turns it into build() input (pictures from base64)."""
    r = dict(req)
    r['icon'] = ext_share._pic(req.get('icon'))
    r['poses'] = [dict(p, icon=ext_share._pic(p.get('icon'))) for p in req.get('poses') or []]
    return r


def snapshot(folder):
    out = {}
    if os.path.isdir(folder):
        for dp, dn, fn in os.walk(folder):
            for f in fn:
                p = os.path.join(dp, f)
                try:
                    out[p] = (os.path.getmtime(p), os.path.getsize(p))
                except OSError:
                    pass
    return out


def post(port, route, body):
    req = urllib.request.Request('http://127.0.0.1:%d/api/%s' % (port, route), data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as ex:
        return ex.code, json.loads(ex.read().decode() or '{}')


def main():
    port = int(sys.argv[sys.argv.index('--port') + 1]) if '--port' in sys.argv else 8856
    os.makedirs(OUT, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix='wa_r26_py_')
    rig = G.rig('au')

    # ---- 1. reference
    t0 = time.time()
    ref = reference()
    if not check('reference S4S pose pack found in your Mods (read only)', ref, ref and '%s in %s (%.1f s)' % (ref['sort_name'], ref['package'], time.time() - t0)):
        print('No S4S pose pack found - the format is not guessed (plan R2-6).')
        return report()
    check('reference: resource layout', ref['types'] == {'7DF2169C': 1, '6B20C4F3': 2, 'BC4A5044': 2, '00B2D882': 3, '220557DA': 18} and ref['snippet_instance_ok'],
          ref['types'])
    check('reference: S4S picture size (most common over its pose packs)', ref['icon_format'] == [64, 64, 'DST5', 7],
          '%s in %d of %d' % (ref['icon_format'], ref['icon_format_count'], ref['icon_formats_total']))

    # ---- 2. our packs vs the reference
    couple, from_app = load_req('posepack_couple1.json', rest_request(2, 1))
    res, info = PP.build(decoded(couple), rig)
    st = PP.structure(res)
    check('couple (1 key, 2 sims) - resource types and counts equal the reference', st['types'] == ref['types'], '%s (from the app: %s)' % (st['types'], from_app))
    check('languages equal the reference (18 string tables)', st['languages'] == ref['languages'], st['languages'])
    check('pictures in the S4S size (64x64 DST5, 7 mipmaps)', st['icons'] == [tuple(ref['icon_format'])], st['icons'])
    xml = next(d for t, g, i, d in res if t == PP.T_SNIPPET).decode('utf-8')
    check('snippet XML: the same fields in the same order as S4S', json.loads(json.dumps(xml_fields(xml))) == json.loads(json.dumps(ref['fields'])), xml_fields(xml))
    snip = next((t, g, i) for t, g, i, d in res if t == PP.T_SNIPPET)
    check('snippet key like S4S (group 0, FNV64 of the name, high bit)', snip[1] == 0 and snip[2] == fnv64(info['name']) | 1 << 63 and re.match(r'^[^:]+:PosePack_\d{18}$', info['name']), info['name'])
    clip = parse_clip(next(d for t, g, i, d in res if t == PP.T_CLIP))
    rc = ref['clips'][0]
    ev19 = [b.hex() for t, b in clip['events'] if t == 19]
    check('pose clips like S4S (version 14, rig x, event 19 as S4S writes it, 2 ticks)',
          clip['version'] == rc['version'] and clip['rig_ns'] == rc['rig'] and ev19 == rc['ev19'][:1] and clip['codec']['num_ticks'] == PP.POSE_TICKS,
          {'ours': [clip['version'], clip['rig_ns'], ev19, clip['codec']['num_ticks']], 'ref': [rc['version'], rc['rig'], rc['ev19'][:1], rc['ticks']]})
    names = {PP.read_stbl(d)[k] for t, g, i, d in res if t == PP.T_STBL for k in PP.read_stbl(d)}
    check('names in the string table', {'R26 Couple poses' if from_app else 'R26 rest poses', 'Novulon'} <= names and any(' - ' in n for n in names), sorted(names)[:6])
    pkg = os.path.join(tmp, 'couple.package')
    with open(pkg, 'wb') as f:
        f.write(__import__('wwpackage').build_package(res))
    idx = read_index(pkg)
    check('the package reads back (DBPF index)', len(idx) == len(res) and all(read_resource(pkg, e) for e in idx[:5]), '%d resources, %d bytes' % (len(idx), os.path.getsize(pkg)))

    # one shared origin: the two clips keep the sims' places (pelvis 0.9 m apart, like on the stage)
    if from_app:
        pel = []
        for t, g, i, d in res:
            if t != PP.T_CLIP:
                continue
            c = parse_clip(d)
            hsh = next(b['hash'] for b in rig['bones'] if b['name'] == 'b__Pelvis__')
            ch = next(x for x in c['codec']['channels'] if x['target'] == hsh and x['sub'] == 1)
            pel.append(decode_track(ch)[0][1])
        gap = ((pel[0][0] - pel[1][0]) ** 2 + (pel[0][2] - pel[1][2]) ** 2) ** 0.5
        check('couple clips share one origin (keep their spacing)', 0.5 < gap < 1.4, '%.3f m apart' % gap)

    # pictures: real pictures of the sims, not a blank
    for k, (t, g, i, d) in enumerate([r for r in res if r[0] == PP.T_IMG][:3]):
        img = texfmt.decode_dds(d)
        png(os.path.join(OUT, 'icon_%d.png' % k), img.reshape(-1).tobytes(), img.shape[1], img.shape[0])
    img = texfmt.decode_dds([d for t, g, i, d in res if t == PP.T_IMG][1])
    spread = float(img[..., :3].std())
    check('pictures decode (64x64) and show something', img.shape[:2] == (64, 64) and (spread > 8 or not from_app), 'colour spread %.1f' % spread)

    solo, from_app3 = load_req('posepack_solo3.json', rest_request(1, 3))
    res3, info3 = PP.build(decoded(solo), rig)
    xml3 = next(d for t, g, i, d in res3 if t == PP.T_SNIPPET).decode('utf-8')
    st3 = PP.structure(res3)
    check('3 keys give 3 poses', xml3.count('<U>') == 3 and st3['types'].get('6B20C4F3') == 3 and st3['types'].get('00B2D882') == 4,
          '%s (from the app: %s)' % (st3['types'], from_app3))
    # the pose in the clip is the key's pose (pose 2's left upper arm, as the app baked it)
    if from_app3:
        c2 = parse_clip([d for t, g, i, d in res3 if t == PP.T_CLIP][1])
        hsh = next(b['hash'] for b in rig['bones'] if b['name'] == 'b__L_UpperArm__')
        ch = next(x for x in c2['codec']['channels'] if x['target'] == hsh and x['sub'] == 2)
        q = decode_track(ch)[0][1]
        want = solo['poses'][1]['tracks']['b__L_UpperArm__']['r'][0]
        dot = abs(sum(a * b for a, b in zip(q, want)))
        check("each clip holds its key's pose", dot > 0.999, 'dot %.5f' % dot)

    # ---- 3. the lock
    baked_path = os.path.join(OUT, 'baked_cowgirl.json')
    if os.path.isfile(baked_path):
        baked = json.load(open(baked_path, encoding='utf-8'))
        meta = {'category': baked.get('category'), 'tags': baked.get('tags'), 'events': [],
                'actors': [{'naked': a.get('naked'), 'strapon': a.get('strapon'), 'invisibleTeeth': a.get('invisibleTeeth'), 'keyed': []} for a in baked['actors']]}
        poses = [{'sim': i, 'tracks': PP.pose_tracks(a['tracks'], 45), 'label': 'x'} for i, a in enumerate(baked['actors'])]
        # the openings as baked (pose_tracks leaves genital bones out - look at the raw frame)
        raw = [{'sim': i, 'tracks': {n: {k: [v[45]] for k, v in tr.items() if v} for n, tr in a['tracks'].items() if n in PP.OPENINGS}} for i, a in enumerate(baked['actors'])]
        try:
            PP.build({'name': 'x', 'author': 'y', 'meta': meta, 'poses': poses}, rig)
            check('lock: an explicit animation (Magic cowgirl) is refused', False, 'it was built')
        except PP.Refused as ex:
            msg = str(ex)
            check('lock: an explicit animation (Magic cowgirl) is refused with the one-line message', 'non-explicit poses only' in msg and 'teens too' in msg and '\n' not in msg, msg)
        # the app tells an open opening from each sim's own rest (a body's joints rest a few mm off the rig's); the
        # server refuses on the app's word, and on its own only for turned openings (no false alarm on a body's rest)
        opened = PP.lock({'category': 'TEASING', 'actors': [{'naked': 'NONE', 'open': True}]})
        rest_ok = PP.lock({'category': 'TEASING', 'actors': [{'naked': 'NONE'}]}, raw, rig)
        check("lock: an opening the app saw open is refused; a body's own rest is no false alarm", opened == ['an opening that is open'] and rest_ok == [], (opened, rest_ok))
    for label, meta, want in [
            ('nude outfit', {'category': 'TEASING', 'actors': [{'naked': 'ALL'}]}, 'undressed sims'),
            ('genital keys', {'category': 'TEASING', 'actors': [{'naked': 'NONE', 'keyed': ['b__Penis_Mid']}]}, 'genital or opening keys'),
            ('a WW act', {'category': 'ANAL', 'actors': [{'naked': 'NONE'}]}, 'a WickedWhims act (Anal)'),
            ('an act tag', {'category': 'TEASING', 'tags': ['BLOWJOB'], 'actors': [{'naked': 'NONE'}]}, 'a WickedWhims act (Blowjob)'),
            ('moments', {'category': 'TEASING', 'events': ['UNDRESS'], 'actors': [{'naked': 'NONE'}]}, 'WickedWhims moments (cum, undress, effects)'),
            ('strap-on', {'category': 'TEASING', 'actors': [{'naked': 'NONE', 'strapon': True}]}, 'a strap-on')]:
        r = PP.lock(meta)
        check('lock: %s refused' % label, r == [want], r)
    check('lock: kissing, standing, clothed Teasing is fine', PP.lock({'category': 'TEASING', 'tags': ['KISSING', 'STANDING'], 'actors': [{'naked': 'NONE'}]}) == [])
    gen = PP.pose_tracks({'b__Penis_Tip': {'r': [[0, 0, 0, 1]]}, 'b__Up_Vagina__': {'t': [[0, 0, 0]]}, 'b__Head__': {'r': [[0, 0, 0, 1]]}}, 0)
    check('genital bones never go into a pose clip', list(gen) == ['b__Head__'], list(gen))

    # ---- 4. post text (the bundle README's facts) with sound credits
    b = json.load(open(baked_path, encoding='utf-8')) if os.path.isfile(baked_path) else {'name': 'R26', 'author': 'Novulon', 'category': 'VAGINAL', 'tags': ['COWGIRL'], 'locations': ['DOUBLE_BED'], 'actors': [{'gender': 'FEMALE'}, {'gender': 'MALE'}]}
    snd = next((s for s in G.sounds() if s.get('source') in ('mods', 'parked') and 'TURBODRIVER' not in (s.get('package') or '') and not G.blocked_path(s.get('package') or '')), None)
    if snd:
        b = json.loads(json.dumps(b))
        b['actors'][0].setdefault('sounds', []).append({'frame': 10, 'name': snd['name'], 'kind': 'voice'})
    text = ext_share.post_text(b)
    with open(os.path.join(OUT, 'post_text_python.txt'), 'w', encoding='utf-8') as f:
        f.write(text)
    need = [b.get('name') or 'R26', 'Acts: Vaginal', 'Cowgirl', 'Places: Double bed', 'Sims: 2', 'Needs: WickedWhims by TURBODRIVER', 'Animation by Novulon', "Made with Novulon's Wicked Animator"]
    if snd:
        need.append('Sounds from %s' % os.path.basename(snd['package']))
    check('post text: name, acts, places, sims, needed mods and credits', all(n in text for n in need), [n for n in need if n not in text] or text.splitlines()[0])

    # ---- 5. the server, writing only into %TEMP%
    real = [ext_share.X.EXPORTS, os.path.join(G.MODS_DIR, 'FitStudio')]
    before = {r: snapshot(r) for r in real}
    test_exports = os.path.join(tmp, 'exports')
    server = None
    for p in (port, 8871, 8872, 8873, 8874, 8875):
        try:
            server = H.start_server(p, env={'WICKED_EXPORTS_DIR': test_exports})
            port = p
            break
        except Exception as ex:
            print('port %d: %s' % (p, str(ex).splitlines()[0]))
    if not check('test server started (WICKED_EXPORTS_DIR in %TEMP%)', server, port):
        return report()
    try:
        info = json.loads(urllib.request.urlopen('http://127.0.0.1:%d/api/posepack' % port, timeout=30).read().decode())
        check('GET /api/posepack: the lock lists and the test folder', info.get('test_folder') and os.path.normcase(info['exports']) == os.path.normcase(test_exports) and 'VAGINAL' in info['explicit_kinds'], info.get('exports'))
        body = dict(solo, install=True)
        code, r = post(port, 'posepack', body)
        ok = code == 200 and os.path.isfile(r.get('package', '')) and os.path.isfile(r.get('installed') or '')
        check('POST /api/posepack writes the pack (+ README, + "in my game" copy) into %TEMP%', ok and r['package'].lower().startswith(tmp.lower()) and r['installed'].lower().startswith(tmp.lower())
              and os.path.isfile(os.path.join(r['folder'], 'README.txt')), r.get('package') if code == 200 else r)
        if code == 200:
            check('server-built pack: 3 poses, S4S layout', r['structure']['types'] == st3['types'] and r['poses'] == 3, r['structure']['types'])
        bad = dict(solo, meta={'category': 'VAGINAL', 'tags': ['COWGIRL'], 'actors': [{'naked': 'ALL'}]})
        code, r = post(port, 'posepack', bad)
        check('POST /api/posepack refuses an explicit pack (400, one line)', code == 400 and 'non-explicit poses only' in r.get('error', ''), (code, r.get('error')))
        gif = open(os.path.join(OUT, 'promo_side.gif'), 'rb').read() if os.path.isfile(os.path.join(OUT, 'promo_side.gif')) else b'GIF89a'
        kit = {'name': b.get('name') or 'R26', 'author': 'Novulon', 'baked': b,
               'files': [{'name': 'R26 - side.gif', 'data': base64.b64encode(gif).decode()}, {'name': 'R26 - thumbnail.png', 'data': base64.b64encode(b'\x89PNG').decode()}]}
        code, r = post(port, 'promo_save', kit)
        files = sorted(os.listdir(r['folder'])) if code == 200 and os.path.isdir(r.get('folder', '')) else []
        check('POST /api/promo_save: one folder in %TEMP% with the files and "Post text.txt"', code == 200 and r['folder'].lower().startswith(tmp.lower())
              and 'Post text.txt' in files and 'R26 - side.gif' in files, files or r)
        if code == 200:
            check('POST /api/promo_save: the post text has the credits', 'Made with' in r['post_text'] and 'Acts:' in r['post_text'] and (not snd or 'Sounds from' in r['post_text']), r['post_text'].splitlines()[:3])
        code, r = post(port, 'promo_save', {'name': 'x', 'files': [{'name': '..\\..\\evil.gif', 'data': ''}]})
        check('POST /api/promo_save: only plain file names (no folders)', code in (200, 400) and (code == 400 or all(os.path.dirname(f['path']).lower().startswith(tmp.lower()) for f in r.get('files', []))), (code, r.get('error')))
        code, r = post(port, 'promo_save', {'name': 'x', 'files': [{'name': 'evil.exe', 'data': ''}]})
        check('POST /api/promo_save: only the kit\'s file kinds', code == 400, (code, r.get('error')))
    finally:
        H.stop_server(server)
    after = {r: snapshot(r) for r in real}
    changed = {r: sorted(set(after[r].items()) ^ set(before[r].items()))[:4] for r in real if after[r] != before[r]}
    check('nothing was written outside %TEMP% (real exports folder and Mods\\FitStudio unchanged)', not changed, changed or 'unchanged')
    return report()


def report():
    print('\nR2-6 pose packs and promo kit (backend)')
    print('-' * 100)
    for name, ok, detail in rows:
        print('%s  %-78s %s' % ('PASS' if ok else 'FAIL', name, str(detail)[:160]))
    bad = sum(1 for r in rows if not r[1])
    print('-' * 100)
    print('%d PASS, %d FAIL' % (len(rows) - bad, bad))
    with open(os.path.join(OUT, 'posepack_check_report.json'), 'w', encoding='utf-8') as f:
        json.dump([{'name': n, 'ok': o, 'detail': str(d)[:600]} for n, o, d in rows], f, indent=1)
    return 0 if bad == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
