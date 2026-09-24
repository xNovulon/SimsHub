"""The game's own animation clips (EA), read-only: an index over every client package, adult names only, decoded
tracks, the romance reference library, idle layers and real game faces.

    index()                 -> {'names': {inst: name}, 'clips': {inst: location}, ...}   (cache/eaclips_v1.pickle)
    names()                 -> sorted adult clip names that have clip data
    adult(name)             -> a_ / a2a_ / a2o_ clip without child, teen, pet or family words
    tracks(name, step=1)    -> the same shape as gamedata.clip_tracks (constant channels included)
    library()               -> romance pairs (x/y clips): WooHoo, kisses, make-outs, cuddles...  (ea_library_v1.json)
    idles()                 -> curated breathing / small-shift loops, grouped by place
    idle_deltas(name)       -> per-tick turn of the upper body bones relative to tick 0, made to loop
    face_library()          -> ~150 real Sims faces at their strongest moment (ea_faces_v1.json)
    status() / start_background() -> the first build takes a while: it runs in a background thread

Packages: objmesh.packages() (every Client*Build*.package of the base game and each pack; delta builds first, so a
delta copy of a clip overrides the full build's). Clip names come from the clip headers (0xBC4A5044, name at byte 56).
Nothing is written anywhere but cache/.
"""
import json, math, os, pickle, re, struct, threading, time, zlib

import numpy as np

import gamedata as G
from clipfmt import parse_clip, decode_track, fnv64
from dbpf import read_index, refpack

T_CLIP, T_CLIP_HEADER = 0x6B20C4F3, 0xBC4A5044
INDEX_VERSION = 1
INDEX_PATH = os.path.join(G.CACHE, 'eaclips_v1.pickle')
LIBRARY_PATH = os.path.join(G.CACHE, 'ea_library_v1.json')
FACES_PATH = os.path.join(G.CACHE, 'ea_faces_v1.json')

_ADULT = re.compile(r'^(a_|a2a_|a2o_)', re.I)
# cache/research/scripts/clip_cats.py BAD list, plus pens, cross-age and family clips, school and toys
BAD = re.compile(r'(child|toddler|infant|baby|babies|teen|kid|puberty|bassinet|crib|cat|dog|horse|pet|animalPen|'
                 r'crossAge|family|school|scout|dollhouse|toy|prom_|_prom|homework|parent)', re.I)

# the 30 face bones of key.faceBones (web/js/bones.js FACE_CHANNEL)
FACE = ['b__L_UpLid__', 'b__R_UpLid__', 'b__L_LoLid__', 'b__R_LoLid__', 'b__L_Mouth__', 'b__R_Mouth__',
        'b__UpLip__', 'b__LoLip__', 'b__L_UpLip__', 'b__R_UpLip__', 'b__L_LoLip__', 'b__R_LoLip__',
        'b__L_InBrow__', 'b__R_InBrow__', 'b__L_MidBrow__', 'b__R_MidBrow__', 'b__L_OutBrow__', 'b__R_OutBrow__',
        'b__L_Cheek__', 'b__R_Cheek__', 'b__L_Squint__', 'b__R_Squint__', 'b__L_Eye__', 'b__R_Eye__']
FACE_CHANNEL = FACE + ['b__Jaw__', 'b__Tounge__1', 'b__Tounge__2', 'b__Tounge__3', 'b__CAS_L_Nostril__',
                       'b__CAS_R_Nostril__']
# face_rank.py: the bones whose turn measures how strong a face is
_RANK_BONE = re.compile(r'(Brow|Lid|Lip|Mouth|Cheek|Jaw|Squint)')

# romance library categories (clip_cats.py), first match wins
CATEGORIES = [('woohoo', 'WooHoo', r'woohoo'), ('makeout', 'Make-outs', r'makeOut'), ('kiss', 'Kisses', r'kiss'),
              ('cuddle', 'Cuddles', r'cuddle|snuggle|spoon'), ('bed', 'In bed together', r'_bed_'),
              ('massage', 'Massages', r'massage'), ('hug', 'Hugs', r'embrace|hug(?!e)')]
CATEGORIES = [(i, label, re.compile(rx, re.I)) for i, label, rx in CATEGORIES]
PLACE_NAMES = {'hottub': 'Hot tub', 'hotsprings': 'Hot springs', 'steamroom': 'Steam room', 'rocketship': 'Rocket ship',
               'treehouse': 'Treehouse', 'photobooth': 'Photo booth', 'romanticblanket': 'Picnic blanket',
               'sleepingpod': 'Sleeping pod', 'walkinsafe': 'Walk-in safe', 'secretpassageway': 'Secret passage',
               'islandwaterfall': 'Island waterfall', 'leafpile': 'Leaf pile', 'pierattractions': 'Pier',
               'showertub': 'Shower tub', 'closetvenue': 'Closet', 'heartbed': 'Heart bed',
               'fairyrelatedwoohoo': 'Fairy ring', 'vampirepowers': 'Vampire', 'soc': 'Standing', 'world': 'Anywhere',
               'bed': 'Bed', 'sofa': 'Sofa', 'loveseat': 'Loveseat', 'seated': 'Seated', 'sectionalsofas': 'Sofa',
               'restaurantbooth': 'Booth', 'picnictable': 'Picnic table', 'sleepingbag': 'Sleeping bag',
               'massagetable': 'Massage table', 'massagechair': 'Massage chair'}

# idle layers: (group id, label, [regex over adult _x/_y clip names])
IDLE_GROUPS = [
    ('bed', 'In bed', [r'^a2o_(bed|sleepingBag)_(relax|nap|sleep|crosslegged)_idle_breathe\w*_x$',
                       r'^a2a_bed_intimate_idle_breathe_[xy]$', r'^a2o_romanticBlanket_crosslegged_idle_breathe_x$']),
    ('seated', 'Seated', [r'^a2a_(seated|sectionalSofas|restaurantBooth|picnicTable)(_seated)?_intimate_idle_breathe_[xy]$',
                          r'^a2o_massageChair_reclined_idle_breathe_x$']),
    ('kneel', 'Kneeling', [r'^a_idle_kneel_x$', r'^a_idle_look(Left|Right)_kneel_x$',
                           r'^a2o_(bed|romanticBlanket)_kneel_idle_breathe_x$']),
    ('stand', 'Standing', [r'^a_idle_neutral_loop_[123]_x$', r'^a_idle_M_shiftLeft_(long)?[bB]reathe_x$',
                           r'^a_idle_M_shiftLeft_weightShift_x$', r'^a_idle_(female_sway|sway_female)_x$']),
    ('cuddle', 'Cuddling', [r'^a2a_bed_cuddle_idle_breathe(_prototype)?_[xy]$',
                            r'^a2a_romanticBlanket_intimate_idle_breathe_[xy]$']),
]
IDLE_BONES = ['b__Spine0__', 'b__Spine1__', 'b__Spine2__', 'b__Neck__', 'b__Head__', 'b__L_Clavicle__',
              'b__R_Clavicle__', 'b__L_UpperArm__', 'b__R_UpperArm__', 'b__L_Forearm__', 'b__R_Forearm__', 'b__Pelvis__']

# face library sources: (group id, label, regex, take all?)
FACE_SOURCES = [('overlay', 'Expressions', r'facialOverlay', True), ('mood', 'Moods', r'^a_UI_mood', True),
                ('react', 'Reactions', r'^a_react', False), ('laugh', 'Laughs', r'laugh|giggle', False),
                ('pleasure', 'Pleasure & pain', r'pain|moan|pleasure|orgasm|climax|ecstat|swoon|sigh|gasp|blush', False),
                ('kiss', 'Kisses', r'kiss', False), ('makeout', 'Make-outs', r'makeOut', False),
                ('woohoo', 'WooHoo', r'woohoo', False)]
FACE_TOP = 15
FACE_CANDIDATES = 400        # clips ranked per category (face_rank.py)


def adult(name):
    n = name or ''
    return bool(_ADULT.match(n)) and not BAD.search(n) and not G._BLOCK_WORDS.search(n.replace('_', ' '))


# ------------------------------------------------------------------ background build + status
_state_lock = threading.Lock()
_state = {'index': 'missing', 'library': 'missing', 'faces': 'missing', 'error': None, 'started': None,
          'finished': None, 'faces_done': 0, 'faces_total': 0}
_thread = None


def status():
    with _state_lock:
        st = dict(_state)
    for key, path in (('library', LIBRARY_PATH), ('faces', FACES_PATH)):
        if st[key] == 'missing' and os.path.exists(path):
            st[key] = 'cached'
    if st['index'] == 'missing' and os.path.exists(INDEX_PATH):
        st['index'] = 'cached'
    st['ready'] = st['library'] in ('ready', 'cached') and st['faces'] in ('ready', 'cached')
    return st


def _set(**kw):
    with _state_lock:
        _state.update(kw)


def start_background():
    """Build the index, the library and the face library in a background thread (once). Returns status()."""
    global _thread
    with _state_lock:
        running = _thread is not None and _thread.is_alive()
        if not running:
            _thread = threading.Thread(target=build_all, name='eaclips-build', daemon=True)
            _thread.start()
    return status()


def build_all():
    _set(started=time.time(), error=None)
    try:
        index()
        library()
        face_library()
    except Exception as ex:       # logged; the app keeps working without the game's clips
        import traceback
        traceback.print_exc()
        _set(error=str(ex) or repr(ex))
    _set(finished=time.time())


# ------------------------------------------------------------------ index
_idx_lock = threading.RLock()
_idx = None


def _packages():
    import objmesh
    return objmesh.packages()


def _read_at(f, pos, size, comp):
    f.seek(pos)
    data = f.read(size)
    if comp == 0x5A42:
        return zlib.decompress(data)
    if comp == 0xFFFF:
        return refpack(data)
    return data


def _header_name(d):
    """Clip name and duration from a clip header (the name at byte 56, else found by parsing)."""
    dur = struct.unpack_from('<f', d, 8)[0] if len(d) >= 12 else 0.0
    if len(d) > 60:
        n = struct.unpack_from('<i', d, 56)[0]
        if 1 <= n <= 256 and 60 + n <= len(d):
            raw = d[60:60 + n]
            if all(32 < c < 127 for c in raw):
                return raw.decode('ascii'), dur
    try:
        return parse_clip(d + b'\0' * 64).get('clip_name') or None, dur
    except Exception:
        return None, dur


def index():
    """{'version', 'signature', 'packages', 'clips': {inst: (pkg, pos, size, mem, comp)}, 'names': {inst: name},
    'seconds': {inst: duration}} over every client package; cached in cache/eaclips_v1.pickle."""
    global _idx
    with _idx_lock:
        if _idx is not None:
            return _idx
        _set(index='building')
        pkgs = _packages()
        gd = G.game_dir()
        sig = [(os.path.relpath(p, gd), os.path.getsize(p), int(os.path.getmtime(p))) for p in pkgs]
        if os.path.exists(INDEX_PATH):
            try:
                with open(INDEX_PATH, 'rb') as f:
                    cached = pickle.load(f)
                if cached.get('version') == INDEX_VERSION and cached.get('signature') == sig:
                    cached['packages'] = pkgs
                    _idx = cached
                    _set(index='ready')
                    return _idx
            except Exception:
                pass
        t0 = time.time()
        clips, headers = {}, {}
        for k, p in enumerate(pkgs):
            try:
                entries = read_index(p)
            except Exception:
                continue          # an empty delta package
            for e in entries:
                if e['size'] == 0 or e['comp'] == 0xFFE0:
                    continue
                if e['type'] == T_CLIP:
                    clips.setdefault(e['inst'], (k, e['pos'], e['size'], e['mem'], e['comp']))
                elif e['type'] == T_CLIP_HEADER:
                    headers.setdefault(e['inst'], (k, e['pos'], e['size'], e['mem'], e['comp']))
        names, secs = {}, {}
        by_pkg = {}
        for inst, loc in headers.items():
            by_pkg.setdefault(loc[0], []).append((loc[1], inst, loc))
        for k, items in by_pkg.items():
            try:
                with open(pkgs[k], 'rb') as f:
                    for _, inst, (_, pos, size, mem, comp) in sorted(items):
                        try:
                            name, dur = _header_name(_read_at(f, pos, size, comp))
                        except Exception:
                            continue
                        if name:
                            names[inst] = name
                            secs[inst] = round(float(dur), 4)
            except OSError:
                continue
        _idx = {'version': INDEX_VERSION, 'signature': sig, 'packages': pkgs, 'clips': clips, 'names': names,
                'seconds': secs, 'build_seconds': round(time.time() - t0, 1)}
        tmp = '%s.%d.tmp' % (INDEX_PATH, os.getpid())
        try:
            with open(tmp, 'wb') as f:
                pickle.dump(dict(_idx, packages=None), f, protocol=pickle.HIGHEST_PROTOCOL)
            os.replace(tmp, INDEX_PATH)
        except OSError:
            try:
                os.remove(tmp)
            except OSError:
                pass
        _set(index='ready')
        return _idx


_by_name = None


def _name_map():
    global _by_name
    idx = index()
    if _by_name is None or _by_name[0] is not idx:
        m = {}
        for inst, n in idx['names'].items():
            if inst in idx['clips']:
                m.setdefault(n.lower(), inst)
        _by_name = (idx, m)
    return _by_name[1]


def names():
    """Adult clip names that have clip data (sorted)."""
    return sorted(n for n in (index()['names'].get(i) for i in _name_map().values()) if n and adult(n))


def clip_bytes(name):
    inst = _name_map().get((name or '').lower())
    if inst is None:
        return None
    idx = index()
    k, pos, size, mem, comp = idx['clips'][inst]
    with open(idx['packages'][k], 'rb') as f:
        return _read_at(f, pos, size, comp)


def tracks(name, step=1):
    """Decoded EA clip, the same shape as gamedata.clip_tracks: {name, ticks, fps, tracks: {bone: {'t', 'r'}}}.
    Adult clips only. Constant channels (types 9-12, 17) are one key at tick 0."""
    if not adult(name):
        raise LookupError('not an adult game clip')
    data = clip_bytes(name)
    if data is None:
        raise LookupError('clip not found: %s' % name)
    out = G.tracks_from_clip(data, _real_name(name), 'au', max(1, int(step or 1)))
    out['source'] = 'ea'
    return out


def _real_name(name):
    inst = _name_map().get((name or '').lower())
    return index()['names'].get(inst, name)


# ------------------------------------------------------------------ words
def _words(text):
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
    text = re.sub(r'([A-Za-z])(\d)', r'\1 \2', text)
    return [w for w in re.split(r'[_\s]+', text) if w]


def nice(base):
    """'a2a_bed_wooHoo_HS_loop1' -> 'Bed WooHoo HS loop 1'."""
    b = re.sub(r'^(a2a_|a2o_|a_)', '', base)
    b = re.sub(r'^Interactable_', '', b, flags=re.I)
    b = re.sub(r'woo_?hoo', 'WooHoo', b, flags=re.I)
    words = _words(b.replace('WooHoo', 'WOOHOOX'))
    words = ['WooHoo' if w.upper() == 'WOOHOOX' else w for w in words]
    out = []
    for i, w in enumerate(words):
        if w == 'WooHoo' or (len(w) <= 3 and w.isupper()):
            out.append(w)
        else:
            out.append(w.lower())
    s = ' '.join(out)
    return s[:1].upper() + s[1:]


def place_of(base):
    m = re.match(r'^a2a_(?:Interactable_)?([A-Za-z0-9]+)', base, re.I)
    raw = m.group(1) if m else ''
    key = raw.lower()
    if key in PLACE_NAMES:
        return PLACE_NAMES[key]
    w = ' '.join(_words(raw)).lower()
    return w[:1].upper() + w[1:] if w else 'Anywhere'


# ------------------------------------------------------------------ romance reference library
_lib_lock = threading.Lock()
_lib = None


def _sig_key():
    return [list(x) for x in index()['signature']]


def library():
    """[{id: 'ea:' + base, name, author: 'The Sims 4', locations: [place], category, kind, loop, seconds,
    actors: ['BOTH', 'BOTH'], clips: [x, y]}] - adult two-sim romance clips (a2a_..._x / _y pairs)."""
    global _lib
    with _lib_lock:
        if _lib is not None:
            return _lib
        _set(library='building')
        sig = _sig_key()
        cached = G._load_cache(LIBRARY_PATH) if os.path.exists(LIBRARY_PATH) else None
        if isinstance(cached, dict) and cached.get('signature') == sig and isinstance(cached.get('items'), list):
            _lib = cached['items']
            _set(library='ready')
            return _lib
        idx = index()
        have = {n for n in names()}
        low = {n.lower(): n for n in have}
        secs = {idx['names'][i].lower(): idx['seconds'].get(i, 0) for i in _name_map().values() if i in idx['names']}
        items = []
        for n in sorted(have):
            if not n.lower().startswith('a2a_') or not n.endswith('_x'):
                continue
            base = n[:-2]
            y = low.get((base + '_y').lower())
            if not y:
                continue
            cat = next(((i, label) for i, label, rx in CATEGORIES if rx.search(base)), None)
            if not cat:
                continue
            items.append({'id': 'ea:' + base, 'name': nice(base), 'author': 'The Sims 4', 'locations': [place_of(base)],
                          'category': cat[1], 'kind': cat[0], 'loop': bool(re.search(r'loop|idle', base, re.I)),
                          'seconds': secs.get(n.lower(), 0), 'actors': ['BOTH', 'BOTH'], 'clips': [n, y], 'tags': []})
        _lib = items
        G._store(LIBRARY_PATH, {'signature': sig, 'items': items})
        _set(library='ready')
        return _lib


def library_entry(entry_id):
    base = str(entry_id or '')
    return next((a for a in library() if a['id'] == base or a['id'] == 'ea:' + base), None)


# ------------------------------------------------------------------ sampling helpers
def _norm(q):
    q = np.asarray(q, float)
    n = np.linalg.norm(q, axis=-1, keepdims=True)
    return q / np.where(n > 0, n, 1)


def _sample(frames, ticks, quat):
    """(ticks, n) array: keys interpolated linearly per tick (quaternions normalised, same hemisphere), held
    before the first and after the last key."""
    if not frames:
        return None
    ts = np.array([t for t, _ in frames], float)
    vs = np.array([v for _, v in frames], float)
    if quat:
        vs = _norm(vs)
        for i in range(1, len(vs)):
            if np.dot(vs[i - 1], vs[i]) < 0:
                vs[i] = -vs[i]
    grid = np.arange(max(1, ticks), dtype=float)
    out = np.stack([np.interp(grid, ts, vs[:, c]) for c in range(vs.shape[1])], axis=1)
    return _norm(out) if quat else out


def _qmul(a, b):
    ax, ay, az, aw = np.moveaxis(a, -1, 0)
    bx, by, bz, bw = np.moveaxis(b, -1, 0)
    return np.stack([aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
                     aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz], axis=-1)


def _qinv(q):
    return q * np.array([-1, -1, -1, 1.0])


def _qangle(a, b):
    d = np.abs(np.sum(_norm(a) * _norm(b), axis=-1))
    return np.degrees(2 * np.arccos(np.clip(d, 0, 1)))


def _slerp(a, b, t):
    """Per-row slerp between quaternion arrays a and b (shape (n, 4)), t shape (n,)."""
    a, b = _norm(a), _norm(b)
    d = np.sum(a * b, axis=-1)
    b = np.where(d[:, None] < 0, -b, b)
    d = np.abs(d)
    th = np.arccos(np.clip(d, -1, 1))
    s = np.sin(th)
    small = s < 1e-6
    w0 = np.where(small, 1 - t, np.sin((1 - t) * th) / np.where(small, 1, s))
    w1 = np.where(small, t, np.sin(t * th) / np.where(small, 1, s))
    return _norm(w0[:, None] * a + w1[:, None] * b)


def _channels(name):
    """(ticks, fps, {bone: {1: frames, 2: frames}}) of a clip."""
    data = clip_bytes(name)
    if data is None:
        raise LookupError('clip not found: %s' % name)
    k = parse_clip(data)['codec']
    bones = {b['hash']: b['name'] for b in G.rig('au')['bones']}
    out = {}
    for ch in k['channels']:
        b = bones.get(ch['target'])
        if b is None or ch['sub'] not in (1, 2):
            continue
        fr = decode_track(ch)
        if fr:
            out.setdefault(b, {})[ch['sub']] = fr
    return k['num_ticks'], round(1.0 / k['tick_length']) if k['tick_length'] else 30, out


# ------------------------------------------------------------------ idle layers
def idles():
    """[{name, label, group, group_label}] - the game's breathing and small-shift loops, by place."""
    have = names()
    out = []
    for gid, glabel, rxs in IDLE_GROUPS:
        pats = [re.compile(r) for r in rxs]
        for n in have:
            if any(p.search(n) for p in pats):
                label = nice(re.sub(r'_[xy]$', '', n)).replace('idle breathe', 'breathing').replace('Idle ', '')
                if n.lower().startswith('a2a_'):
                    label += ' (sim 1)' if n.endswith('_x') else ' (sim 2)'
                out.append({'name': n, 'label': label, 'group': gid, 'group_label': glabel})
    return out


def _root_shift(chans, ticks):
    """The hips' small weight shift (b__ROOT_bind__'s move since tick 0) in the body's own frame at tick 0, per tick,
    blended back to 0 over the last 15% when the clip doesn't end where it starts. None when it moves < 0.5 mm."""
    fr = chans.get('b__ROOT_bind__', {}).get(1)
    p = _sample(fr, ticks, False) if fr else None
    if p is None:
        return None
    d = p - p[:1]
    rq = chans.get('b__ROOT_bind__', {}).get(2)
    q0 = _sample(rq, ticks, True)[0] if rq else None
    if q0 is None:
        rest = next((b for b in G.rig('au')['bones'] if b['name'] == 'b__ROOT_bind__'), None)
        q0 = np.array(rest['rot'] if rest else [0, 0, 0, 1.0], float)
    # rotate by q0^-1: v' = q^-1 v q
    qi = np.repeat(_qinv(_norm(np.array([q0], float))), len(d), axis=0)
    vq = np.concatenate([d, np.zeros((len(d), 1))], axis=1)
    local = _qmul(_qmul(qi, vq), _qinv(qi))[:, :3]
    if np.linalg.norm(local[-1]) > 0.001:
        t0 = int(math.floor(0.85 * (ticks - 1)))
        span = max(1, ticks - 1 - t0)
        w = np.clip((np.arange(ticks) - t0) / span, 0, 1)
        w = w * w * (3 - 2 * w)
        local = local * (1 - w)[:, None]
    if np.max(np.linalg.norm(local, axis=1)) < 0.0005:
        return None
    return [[round(float(c), 5) for c in row] for row in local]


def idle_deltas(name):
    """{name, ticks, fps, bones: {bone: [[x,y,z,w] per tick]}, shift?: [[x,y,z] per tick]} for IDLE_BONES: each
    tick's turn relative to tick 0 in the bone's own space (q0^-1 q(t)); the pelvis at half strength. `shift` is the
    hips' weight shift in metres, in the body's frame at tick 0 (the app turns it with the sim's hips). When the
    clip's end is more than 1 degree (1 mm) from its start, the last 15% is blended back to tick 0, so it loops
    without a jump."""
    if name not in {x['name'] for x in idles()}:
        raise LookupError('not a game idle: %s' % name)
    ticks, fps, chans = _channels(name)
    ticks = max(2, ticks)
    out = {}
    for b in IDLE_BONES:
        fr = chans.get(b, {}).get(2)
        q = _sample(fr, ticks, True) if fr else None
        if q is None:
            continue
        d = _qmul(np.repeat(_qinv(q[:1]), len(q), axis=0), q)
        d = _norm(d)
        ident = np.tile([0, 0, 0, 1.0], (len(d), 1))
        if b == 'b__Pelvis__':
            d = _slerp(ident, d, np.full(len(d), 0.5))
        if _qangle(d[-1], d[0]) > 1.0:
            t0 = int(math.floor(0.85 * (ticks - 1)))
            span = max(1, ticks - 1 - t0)
            w = np.clip((np.arange(ticks) - t0) / span, 0, 1)
            w = w * w * (3 - 2 * w)                          # ease in and out
            d = _slerp(d, ident, w)
        if np.max(_qangle(d, ident)) < 0.05:
            continue                                         # this bone doesn't move in the clip
        out[b] = [[round(float(c), 5) for c in row] for row in d]
    res = {'name': name, 'ticks': ticks, 'fps': fps, 'bones': out}
    shift = _root_shift(chans, ticks)
    if shift:
        res['shift'] = shift
    return res


# ------------------------------------------------------------------ real game faces
_faces_lock = threading.Lock()
_faces = None


def _rest():
    return {b['name']: b for b in G.rig('au')['bones']}


def _face_profile(name, rest):
    """(score in degrees, peak tick, {bone: {'r': [...], 't': [...]}}) of a clip's strongest face, or None."""
    try:
        ticks, fps, chans = _channels(name)
    except Exception:
        return None
    ticks = max(1, ticks)
    total = np.zeros(ticks)
    rot = {}
    for b in FACE_CHANNEL:
        fr = chans.get(b, {}).get(2)
        if not fr:
            continue
        q = _sample(fr, ticks, True)
        rot[b] = q
        if _RANK_BONE.search(b) and b in rest:
            total += _qangle(q, np.tile(rest[b]['rot'], (ticks, 1)))
    if not rot:
        return None
    peak = int(np.argmax(total))
    bones = {}
    for b in FACE_CHANNEL:
        e = {}
        if b in rot:
            e['r'] = [round(float(c), 5) for c in rot[b][peak]]
        fr = chans.get(b, {}).get(1)
        if fr:
            e['t'] = [round(float(c), 5) for c in _sample(fr, ticks, False)[peak]]
        if e:
            bones[b] = e
    return round(float(total[peak]), 1), peak, bones


def _face_label(name, group):
    b = re.sub(r'_[xy]$', '', name)
    b = re.sub(r'^(a_UI_mood_|a_facialOverlay_|a_react_|a2a_|a2o_|a_)', '', b, flags=re.I)
    return nice('a_' + b)


def _near(a, b, tol=2.0):
    """Two faces that look the same: every shared face bone within tol degrees."""
    keys = [k for k in a if 'r' in a[k] and k in b and 'r' in b[k]]
    if not keys or len(keys) < 0.8 * max(len(a), len(b)):
        return False
    qa = np.array([a[k]['r'] for k in keys])
    qb = np.array([b[k]['r'] for k in keys])
    return float(np.max(_qangle(qa, qb))) < tol


def face_library():
    """[{id, label, group, group_label, clip, tick, score, bones: {bone: {'r': [x,y,z,w], 't'?: [x,y,z]}}}]:
    every facial overlay and mood clip, plus the 15 strongest faces of reactions, laughs, pleasure and pain,
    kisses, make-outs and WooHoo (face_rank.py: the summed turn of the face bones at the clip's peak tick), without
    near-duplicates. Bones are absolute local values, like key.faceBones. Cached in cache/ea_faces_v1.json."""
    global _faces
    with _faces_lock:
        if _faces is not None:
            return _faces
        sig = _sig_key()
        cached = G._load_cache(FACES_PATH) if os.path.exists(FACES_PATH) else None
        if isinstance(cached, dict) and cached.get('signature') == sig and isinstance(cached.get('faces'), list):
            _faces = cached['faces']
            _set(faces='ready')
            return _faces
        _set(faces='building')
        rest = _rest()
        sims = [n for n in names() if re.search(r'_[xy]$', n)]
        chosen, used = [], set()
        plan = []
        for gid, glabel, rx, take_all in FACE_SOURCES:
            r = re.compile(rx, re.I)
            plan.append((gid, glabel, take_all, [n for n in sims if r.search(n)][:FACE_CANDIDATES]))
        _set(faces_total=sum(len(p[3]) for p in plan), faces_done=0)
        done = 0
        for gid, glabel, take_all, cands in plan:
            ranked = []
            for n in cands:
                done += 1
                if done % 50 == 0:
                    _set(faces_done=done)
                if n in used:
                    continue
                prof = _face_profile(n, rest)
                if not prof or not prof[2] or prof[0] <= 0:
                    continue
                ranked.append((prof[0], n, prof[1], prof[2]))
            ranked.sort(key=lambda x: -x[0])
            kept = 0
            for score, n, tick, bones in ranked:
                if not take_all and kept >= FACE_TOP:
                    break
                if any(_near(bones, c['bones']) for c in chosen):
                    continue
                chosen.append({'id': 'ea:' + n, 'label': _face_label(n, gid), 'group': gid, 'group_label': glabel,
                               'clip': n, 'tick': tick, 'score': score, 'bones': bones})
                used.add(n)
                kept += 1
        _faces = chosen
        G._store(FACES_PATH, {'signature': sig, 'faces': chosen})
        _set(faces='ready', faces_done=done)
        return _faces
