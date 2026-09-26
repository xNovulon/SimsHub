"""Everything the animator reads from the game and the Mods folders, cached as JSON.

- rigs (auRig adult, cuRig child, puRig toddler, iuRig infant) from the game's client packages
- nude bodies (top + bottom + feet + head meshes) for each body frame, skinned to the rig
- the WickedWhims animation library: every animation in Mods and Mods_parked, with its clips
"""
import json, os, re, struct, threading, time, glob

from dbpf import read_index, read_resource
from clipfmt import parse_clip, decode_frames, decode_track, fnv32, fnv64
from rigfmt import parse_rig
from geomfmt import parse_geom
import gamefind

HOME = gamefind.HOME
SIMS_DIR = gamefind.SIMS_DIR           # Documents\Electronic Arts\The Sims 4 (wherever Windows keeps Documents)
MODS_DIR = os.path.join(SIMS_DIR, 'Mods')
PARKED_DIR = os.path.join(SIMS_DIR, 'Mods_parked')
HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, '..', 'cache')
CONFIG = gamefind.CONFIG

T_CLIP, T_CLIP_HEADER, T_RIG, T_GEOM, T_CASP, T_SNIPPET, T_STBL = (
    0x6B20C4F3, 0xBC4A5044, 0x8EAF13DE, 0x015A1849, 0x034AEECB, 0x7DF2169C, 0x220557DA)

RIGS = {'au': 'auRig', 'cu': 'cuRig', 'pu': 'puRig', 'iu': 'iuRig'}
# body frame -> (rig, [(role, [CAS part names, first found wins])]). With WickedWhims installed its own nude parts
# (and its adult rig with penis, testicle/vagina, anus, butt and tongue bones) replace the game's, like in the game.
_TONGUE = 'TURBODRIVER_[Noir and Dark Sims 4] Realistic Tongue - CAS_white_202307211954082820'
BODIES = {
    'yf': ('au', [('top', ['yfTop_Nude']),
                  ('bottom', ['TURBODRIVER_NudeBottom_AF_201604300033066128', 'yfBottom_Nude']),
                  ('feet', ['yfShoes_Nude']), ('head', ['yfHead']), ('tongue', [_TONGUE])]),
    'ym': ('au', [('top', ['TURBODRIVER_Nude_Top_Male', 'ymTop_Nude']),
                  ('penis_soft', ['TURBODRIVER_Penis_Soft_Male', 'ymBottom_Nude']),
                  ('penis_hard', ['TURBODRIVER_Penis_Hard_Male']),
                  ('feet', ['ymShoes_Nude']), ('head', ['ymHead']), ('tongue', [_TONGUE])]),
    # a female body with a penis (WickedWhims' futa parts)
    'yf_futa': ('au', [('top', ['yfTop_Nude']),
                       ('penis_soft', ['TURBODRIVER_Penis_Soft_Female']),
                       ('penis_hard', ['TURBODRIVER_Penis_Hard_Female']),
                       ('feet', ['yfShoes_Nude']), ('head', ['yfHead']), ('tongue', [_TONGUE])]),
}
BODY_VERSION = 3


def ww_tuning_package():
    """WickedWhims' tuning package (Mods, or parked), or None."""
    for root in (MODS_DIR, PARKED_DIR):
        for p in glob.glob(os.path.join(root, '**', 'TURBODRIVER_WickedWhims_Tuning.package'), recursive=True):
            return p
    return None


def config():
    try:
        with open(CONFIG, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def game_dir():
    """The game's install folder (gamefind.py: picked in the app, or found). FileNotFoundError when it isn't there."""
    return gamefind.game_dir()


def set_game_dir(path):
    """A folder the user picked in the app: remembered, and everything read from the old one (or from none) is read again."""
    r = gamefind.set_game_dir(path)
    if r.get('ok'):
        forget_game_reads()
    return r


def forget_game_reads():
    """Everything this engine has read from the game's folder is dropped, so nothing mixes two installs: it is read
    again from the new folder when next needed (the window may reuse a running engine, so a restart isn't enough)."""
    import sys
    global _clip_index
    _Client._index = None
    _clip_index = None
    m = sys.modules                       # only modules already in use can hold anything
    if 'objmesh' in m:
        m['objmesh'].reset()
    if 'casptex' in m:
        R = m['casptex'].Resources
        R._idx = R._pkgs = R._ww = None
    if 'morph' in m:
        mo = m['morph']
        for ix in (mo.MORPH_INDEX, mo.PART_INDEX):
            with ix._lock:
                ix._loaded = False
        with mo._cache_lock:
            mo._cache.clear()
    if 'eaclips' in m:
        e = m['eaclips']
        e._idx = e._by_name = e._lib = e._faces = None
    if 'eaaudio' in m:
        m['eaaudio']._Index.reset()
    if 'skintex' in m:
        s = m['skintex']
        for d in (s._mem, s._pkg_mem, s._tone_mem, s._resolve_mem, s._cum_mem):
            d.clear()
        s._game_tone_list[:] = []
    if 'hair' in m:
        hr = m['hair']
        for d in (hr._mem, hr._shaped, hr._geom_mem, hr._pkg_tex):
            d.clear()
    if 'trayfmt' in m:
        P = m['trayfmt']._Protos
        P._pool, P._classes = None, {}


def client_packages():
    """Newest first: delta builds override full builds."""
    d = os.path.join(game_dir(), 'Data', 'Client')
    return sorted(glob.glob(os.path.join(d, 'ClientDeltaBuild*.package'))) + sorted(glob.glob(os.path.join(d, 'ClientFullBuild*.package')))


def _cache_path(name):
    os.makedirs(CACHE, exist_ok=True)
    return os.path.join(CACHE, name)


def _store(path, value):
    """Writes a cache file at once. The temporary file is private to this process and thread, so two copies of the
    app building the same cache never write into one file. If the finished file can't be put in place (the other
    copy has it open), this copy keeps its result in memory and the next start tries again."""
    tmp = '%s.%d-%d.tmp' % (path, os.getpid(), threading.get_ident())
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(value, f, separators=(',', ':'))
        os.replace(tmp, path)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass


def _load_cache(path):
    """A cache file's content, or None when it is missing or damaged (then it is made again)."""
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _cached(name, build):
    path = _cache_path(name)
    value = _load_cache(path) if os.path.exists(path) else None
    if value is not None:
        return value
    value = build()
    _store(path, value)
    return value


class _Client:
    """Lazy index of the game's client packages: (type, group, instance) -> (package, entry)."""
    _lock = threading.Lock()
    _index = None

    @classmethod
    def index(cls):
        with cls._lock:
            if cls._index is None:
                idx = {}
                ww = ww_tuning_package()
                for p in ([ww] if ww else []) + client_packages():
                    for e in read_index(p):
                        if e['type'] in (T_RIG, T_GEOM, T_CASP):
                            idx.setdefault((e['type'], e['group'], e['inst']), (p, e))
                cls._index = idx
            return cls._index

    @classmethod
    def read(cls, t, g, i):
        hit = cls.index().get((t, g, i))
        return read_resource(*hit) if hit else None


def _casp_name(d):
    p, n, shift = 12, 0, 0
    while True:
        b = d[p]; p += 1; n |= (b & 0x7F) << shift; shift += 7
        if not b & 0x80:
            break
    return d[p:p + n].decode('utf-16-be', 'replace')


def _casp_tgis(d):
    off = struct.unpack_from('<I', d, 4)[0] + 8
    cnt = d[off]; q = off + 1; out = []
    for _ in range(cnt):
        inst, grp, typ = struct.unpack_from('<QII', d, q); q += 16
        out.append((typ, grp, inst))
    return out


# ------------------------------------------------------------------ rigs
def rig(key='au'):
    def build():
        data = _Client.read(T_RIG, 0, fnv64(RIGS[key]))
        r = parse_rig(data)
        return {'name': RIGS[key], 'bones': [
            {'name': b['name'], 'parent': b['parent'], 'pos': b['pos'], 'rot': b['rot'], 'scale': b['scale'],
             'hash': b['hash'], 'opposite': b['opposite']} for b in r['bones']]}
    return _cached('rig_%s_ww%d.json' % (key, 1 if ww_tuning_package() else 0), build)


# ------------------------------------------------------------------ bodies
def _find_casp(name):
    for (t, g, i), (p, e) in _Client.index().items():
        if t == T_CASP:
            d = read_resource(p, e)
            if len(d) > 16:
                try:
                    if _casp_name(d) == name:
                        return d
                except Exception:
                    pass
    return None


def body(frame='yf'):
    rig_key, roles = BODIES[frame]

    def build():
        r = rig(rig_key)
        bone_index = {b['hash']: k for k, b in enumerate(r['bones'])}
        known = set(bone_index)
        # one pass over the CAS parts to find all wanted names (WickedWhims' come first in the index)
        wanted = {n: None for _, names in roles for n in names}
        for (t, g, i), (p, e) in _Client.index().items():
            if t == T_CASP:
                d = read_resource(p, e)
                if len(d) > 16:
                    try:
                        n = _casp_name(d)
                    except Exception:
                        continue
                    if n in wanted and wanted[n] is None:
                        wanted[n] = d
        meshes = []
        for role, names in roles:
            name = next((n for n in names if wanted.get(n) is not None), None)
            if name is None:
                continue
            d = wanted[name]
            geoms = []
            for t, g, i in _casp_tgis(d):
                if t == T_GEOM:
                    raw = _Client.read(t, g, i)
                    if raw:
                        try:
                            geoms.append(parse_geom(raw, known))
                        except Exception:
                            pass
            if not geoms:
                continue
            gm = max(geoms, key=lambda x: len(x['positions']))
            remap = [bone_index.get(h, 0) for h in gm['bone_hashes']]
            meshes.append({
                'part': name,
                'role': role,
                'positions': [round(c, 5) for v in gm['positions'] for c in v],
                'normals': [round(c, 4) for v in gm['normals'] for c in v],
                'uvs': [round(c, 5) for v in gm['uvs'] for c in v],
                'bones': [remap[k] if k < len(remap) else 0 for b in gm['bones'] for k in b],
                'weights': [round(w, 4) for ws in gm['weights'] for w in ws],
                'faces': gm['faces'],
            })
        return {'frame': frame, 'rig': rig_key, 'meshes': meshes, 'ww': bool(ww_tuning_package())}
    return _cached('body_%s_v%d_ww%d.json' % (frame, BODY_VERSION, 1 if ww_tuning_package() else 0), build)


# ------------------------------------------------------------------ WickedWhims library
def animation_packages():
    out = []
    for root in (MODS_DIR, PARKED_DIR):
        for p in glob.glob(os.path.join(root, '**', '*.package'), recursive=True):
            out.append(p)
    return sorted(out)


def _stbl(data):
    """English-agnostic string table: {hash: text}."""
    out = {}
    if data[:4] != b'STBL':
        return out
    version = struct.unpack_from('<H', data, 4)[0]
    count = struct.unpack_from('<Q', data, 7)[0]
    p = 21
    for _ in range(count):
        if p + 7 > len(data):
            break
        key = struct.unpack_from('<I', data, p)[0]; p += 4
        p += 1  # flags
        n = struct.unpack_from('<H', data, p)[0]; p += 2
        out[key] = data[p:p + n].decode('utf-8', 'replace'); p += n
    return out


def _field(el, name):
    """Text of the first direct child <T n="name"> of el ('' when missing)."""
    for c in el:
        if c.get('n') == name:
            return (c.text or '').strip()
    return ''


def _parse_animation_xml(xml):
    """WickedWhims animation snippet XML -> list of {name/raw, author, locations, category, actors[]}.

    Read as real XML (comments, field order and the list tag don't matter): each actor's clip, every
    animation_genders value and every animation_pref_gender entry come from that actor's own element. An actor with
    no gender gets '' (WickedWhims itself refuses such an animation), never a made-up 'BOTH'."""
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(xml.encode('utf-8') if isinstance(xml, str) else xml)
    except ET.ParseError:
        return []
    anims = []
    for lst in root.iter():
        if lst.get('n') != 'animations_list':
            continue
        for an in lst:
            acts = next((c for c in an if c.get('n') == 'animation_actors_list'), None)
            if acts is None:
                continue
            actors = []
            for a in acts:
                genders = [(c.text or '').strip() for c in a if c.get('n') == 'animation_genders']
                prefs = [p.strip() for c in a if c.get('n') == 'animation_pref_gender' for p in (c.text or '').split(',') if p.strip()]
                genders = [g for g in genders if g]
                # older templates name the actor's clip 'animation_name' (WickedWhims still reads it)
                clip = _field(a, 'animation_clip_name') or _field(a, 'animation_name')
                actors.append({'clip': clip, 'gender': genders[0] if genders else '',
                               'genders': genders, 'prefs': prefs})
            if not actors or not all(x['clip'] for x in actors):
                continue
            a = {
                'raw_name': _field(an, 'animation_raw_display_name'),
                'name_key': _field(an, 'animation_display_name'),
                'author': _field(an, 'animation_author'),
                'locations': [x.strip() for x in _field(an, 'animation_locations').split(',') if x.strip()],
                'category': _field(an, 'animation_category'),
                'tags': [x.strip().upper() for x in _field(an, 'animation_tags').replace(';', ',').split(',') if x.strip()],
                'actors': actors,
            }
            props = _parse_props(an)
            if props:
                a['props'] = props
            anims.append(a)
    return anims


def _parse_props(an):
    """The props of one WickedWhims animation element (its animation_props_list, an <L> or a <T> list of <T>/<U>
    items) -> [{'guid': int, 'clip': str}] (a prop entry whose prop_guids lists several objects, space or comma
    separated, also gets 'guids': every one of them - WickedWhims uses the first it can make)."""
    lst = next((c for c in an if c.get('n') == 'animation_props_list'), None)
    if lst is None:
        return []
    out = []
    for item in lst:
        guids = []
        for g in re.split(r'[\s,;]+', _field(item, 'prop_guids')):
            try:
                v = int(g, 0) if g.lower().startswith('0x') else int(g)
            except ValueError:
                continue
            if v > 0 and v not in guids:
                guids.append(v)
        clip = _field(item, 'prop_animation_clip_name')
        if not guids:
            continue
        p = {'guid': guids[0], 'clip': clip}
        if len(guids) > 1:
            p['guids'] = guids
        out.append(p)
    return out


# Adults only. Animations with child, toddler, infant, teen or animal actors, and packs/creators known for that
# content, are never indexed, previewed, copied from or used for sounds - whatever is in the Mods folders.
_ADULT_GENDER = re.compile(r'^(?:(?:VAMPIRE|WITCH|SPELLCASTER|ALIEN|MERMAID|WEREWOLF|GHOST|SERVO|PLANTSIM|FAIRY|OCCULT)_)?(?:MALE|FEMALE|BOTH)$')
# Whole words (teen[a-z]* also catches teenage, teenaged, teenager(s); preteen and pre-teen are caught too).
_BLOCK_WORDS = re.compile(r'(?<![a-z])(fallen|atf|child|children|kid|kids|toddlers?|infants?|bab(?:y|ies)|(?:pre ?)?teen[a-z]*|'
                          r'adolescen[a-z]*|juveniles?|(?:pre ?)?pubescen[a-z]*|loli|shota|minors?|brats?|underage[a-z]*|'
                          r'school ?girls?|cub|puppy|kitten|dog|cat|horse|animal|bestiality|zoo)(?![a-z])', re.I)


# creator typos made only of adult words (e.g. 'FEMALEMALE'); WickedWhims ignores them, they say nothing about age
_ADULT_TYPO = re.compile(r'^(?:MALE|FEMALE|BOTH)+$')


def adult_animation(a):
    """True only when every actor has a gender, every gender and preferred gender is an adult one, and no name,
    author, package or clip name hits the block list."""
    if not a['actors']:
        return False
    for x in a['actors']:
        genders = x.get('genders') or ([x['gender']] if x.get('gender') else [])
        if not genders or any(not _ADULT_GENDER.match(g.upper()) for g in genders):
            return False
        if any(not (_ADULT_GENDER.match(p.upper()) or _ADULT_TYPO.match(p.upper())) for p in x.get('prefs') or []):
            return False
    text = ' '.join([a.get('name', ''), a.get('author', ''), a.get('package', '')] + [x['clip'] for x in a['actors']])
    return not _BLOCK_WORDS.search(text.replace('_', ' ').replace('-', ' '))


def blocked_path(path):
    """A package whose folder or file name hits the adults-only block list (never used for sounds)."""
    try:
        rel = os.path.relpath(path, SIMS_DIR) if os.path.isabs(path) else path
    except ValueError:            # another drive
        rel = path
    return bool(_BLOCK_WORDS.search(rel.replace('_', ' ').replace('-', ' ')))


_lib_lock = threading.Lock()
_library = None
_clip_index = None


def _library_signature():
    return [[p, int(os.path.getmtime(p)), os.path.getsize(p)] for p in animation_packages()]   # lists: equal to the cached (JSON) copy


def library():
    """{'animations': [...], 'clips': {clip name lower: [package, entry]}} built once and cached."""
    global _library, _clip_index
    with _lib_lock:
        if _library is not None:
            return _library
        sig = _library_signature()
        # 5: teenage/teenaged/teenager (and other forms) on the block list; 6: each animation's props
        # (animation_props_list -> 'props': [{guid, clip}], only on animations that have props)
        path = _cache_path('library6.json')
        cached = _load_cache(path) if os.path.exists(path) else None
        if isinstance(cached, dict) and cached.get('signature') == sig:
            _library = cached
            return _library
        animations, clip_locs = [], {}
        for p, _, _ in sig:
            try:
                idx = read_index(p)
            except Exception:
                continue
            clips_here = {e['inst']: e for e in idx if e['type'] == T_CLIP}
            if not clips_here:
                continue          # CAS / build packages: nothing to animate with
            strings = {}
            snippets = [e for e in idx if e['type'] == T_SNIPPET]
            wanted = []
            for e in snippets:
                if e['mem'] > 8_000_000:
                    continue
                try:
                    d = read_resource(p, e)
                except Exception:
                    continue      # a damaged resource in someone's merged package
                head = d[:300]
                if b'AnimationPackage' in head and (b'WickedWoohoo' in head or b'WickedWhims' in head):
                    wanted.append(d.decode('utf-8', 'replace'))
            if wanted and any('animation_display_name' in x for x in wanted):
                for e in idx:
                    if e['type'] == T_STBL and ((e['inst'] >> 56) & 0xFF) == 0x00:   # English tables
                        try:
                            strings.update(_stbl(read_resource(p, e)))
                        except Exception:
                            pass
            for xml in wanted:
                for a in _parse_animation_xml(xml):
                    name = a['raw_name']
                    if not name and a['name_key']:
                        try:
                            name = strings.get(int(a['name_key'], 0), '')
                        except ValueError:
                            name = ''
                    a['name'] = name or (a['actors'][0]['clip'])
                    a['package'] = os.path.relpath(p, SIMS_DIR)
                    del a['raw_name'], a['name_key']
                    animations.append(a)
            for inst, e in clips_here.items():
                clip_locs[str(inst)] = [p, e['pos'], e['size'], e['mem'], e['comp']]
        animations = [a for a in animations if adult_animation(a)]
        for a in animations:
            for x in a['actors']:
                x.pop('genders', None), x.pop('prefs', None)
        keep = {str(fnv64(x['clip'])) for a in animations for x in a['actors']}
        clip_locs = {k: v for k, v in clip_locs.items() if k in keep}
        for k, a in enumerate(animations):
            a['id'] = k
            a['available'] = all(str(fnv64(x['clip'])) in clip_locs for x in a['actors'])
        _library = {'signature': sig, 'animations': animations, 'clips': clip_locs, 'built': time.time()}
        _store(path, _library)
        return _library


def read_clip_bytes(clip_name):
    loc = library()['clips'].get(str(fnv64(clip_name)))
    if not loc:
        return None
    p, pos, size, mem, comp = loc
    return read_resource(p, {'pos': pos, 'size': size, 'mem': mem, 'comp': comp})


def tracks_from_clip(data, clip_name, rig_key='au', step=1):
    """Decoded CLIP bytes: {'name', 'ticks', 'fps', 'tracks': {bone name: {'t': [[tick,x,y,z]], 'r': [[tick,x,y,z,w]]}}}.
    Shared by creator clips (clip_tracks) and the game's own clips (eaclips.tracks). Constant channels (the game's
    clips carry them: types 9-12, 17) become one key at tick 0."""
    c = parse_clip(data)
    k = c['codec']
    names = {b['hash']: b['name'] for b in rig(rig_key)['bones']}
    tracks = {}
    for ch in k['channels']:
        name = names.get(ch['target'])
        if name is None or ch['sub'] not in (1, 2):
            continue
        frames = decode_track(ch)
        if not frames:
            continue
        if step > 1 and len(frames) > 2:
            frames = frames[::step] + ([frames[-1]] if (len(frames) - 1) % step else [])
        key = 't' if ch['sub'] == 1 else 'r'
        tracks.setdefault(name, {})[key] = [[t] + [round(v, 5) for v in vals] for t, vals in frames]
    return {'name': clip_name, 'ticks': k['num_ticks'], 'fps': round(1.0 / k['tick_length']), 'tracks': tracks}


def clip_tracks(clip_name, rig_key='au', step=1):
    """Decoded creator clip: {'ticks', 'fps', 'tracks': {bone name: {'t': [[tick,x,y,z]], 'r': [[tick,x,y,z,w]]}}}"""
    data = read_clip_bytes(clip_name)
    if data is None:
        return None
    return tracks_from_clip(data, clip_name, rig_key, step)


# ------------------------------------------------------------------ creator moments (animation_events_list)
EVENT_TYPES = ('EFFECT', 'CUM', 'UNDRESS', 'REMOVE_CONDOM')
CUM_TYPES = ('FACE', 'CHEST', 'BELLY', 'UPPER_BACK', 'LOWER_BACK', 'VAGINA', 'BUTT', 'FEET')
NAKED_TYPES = ('TOP', 'TOP_UNDERWEAR', 'BOTTOM', 'BOTTOM_UNDERWEAR', 'SHOES', 'ALL', 'FORCE_ALL')
# what creators wrote -> what they meant (BACK is WickedWhims' alias of UPPER_BACK; FOOT is invalid there)
_CUM_FIX = {'BACK': 'UPPER_BACK', 'FOOT': 'FEET'}
# not rig bones -> the bone WickedWhims meant (its own remap table is never used)
_JOINT_FIX = {'b__penis_tip01': 'b__Penis_Tip', 'b__penis_tip02': 'b__Penis_Tip', 'b__penis_tip03': 'b__Penis_Tip',
              'b__tounge__4': 'b__Tounge__3'}


def _num(text, default=None):
    """A creator's number: '0,3' (comma decimals) reads as 0.3."""
    try:
        return float(str(text).strip().replace(',', '.'))
    except (TypeError, ValueError):
        return default


def parse_events(anim_el):
    """The moments of one WickedWhims animation element (its animation_events_list, <L>/<T> lists and <U>/<T> items
    alike) -> [{type, start, end?, target, cum_layer_type?, cum_layer_level?, naked_type?, effect_name?,
    effect_joint_name?, skip_with_condom}], the same shape the exporter writes. Seconds with comma decimals are read;
    the type is upper-cased; BACK -> UPPER_BACK and FOOT -> FEET; only 'aN' (actor) targets are kept; entries
    WickedWhims itself drops (no effect name or joint, unknown cum layer or naked type) are left out."""
    lst = next((c for c in anim_el if c.get('n') == 'animation_events_list'), None)
    if lst is None:
        return []
    out = []
    for item in lst:
        f = {}
        skip = False
        for c in item:
            n = c.get('n')
            if n == 'dont_run_if':
                for x in c:
                    if x.get('n') == 'actor_has_condom' and _num(x.text, 0) == 1:
                        skip = True
            elif n:
                f[n] = (c.text or '').strip()
        typ = f.get('event_type', '').strip().upper()
        if typ not in EVENT_TYPES:
            continue
        m = re.match(r'^a(\d+)$', f.get('event_target', '').strip().lower())
        if not m:
            continue
        start = max(0.0, _num(f.get('event_start_timecode'), 0.0))
        e = {'type': typ, 'start': round(start, 4), 'target': int(m.group(1)), 'skip_with_condom': skip}
        if typ == 'EFFECT':
            name = f.get('effect_name', '').strip()
            joint = f.get('effect_joint_name', '').strip()
            if not name or not joint:
                continue
            end = _num(f.get('event_end_timecode'), 9999.0)
            e.update(end=round(max(start, end), 4), effect_name=name, effect_joint_name=_JOINT_FIX.get(joint.lower(), joint))
        elif typ == 'CUM':
            ct = f.get('cum_layer_type', '').strip().upper()
            ct = _CUM_FIX.get(ct, ct)
            if ct not in CUM_TYPES:
                continue
            level = int(_num(f.get('cum_layer_level'), 1) or 1)
            e.update(cum_layer_type=ct, cum_layer_level=max(1, min(3, level)))
        elif typ == 'UNDRESS':
            nt = f.get('naked_type', '').strip().upper()
            if nt not in NAKED_TYPES:
                continue
            e['naked_type'] = nt
        out.append(e)
    return out


def _animation_elements(xml):
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(xml.encode('utf-8') if isinstance(xml, str) else xml)
    except ET.ParseError:
        return
    for lst in root.iter():
        if lst.get('n') == 'animations_list':
            yield from lst


def _element_clips(an):
    acts = next((c for c in an if c.get('n') == 'animation_actors_list'), None)
    if acts is None:
        return []
    return [(_field(a, 'animation_clip_name') or _field(a, 'animation_name')).lower() for a in acts]


def animation_events(anim):
    """The creator's moments of a library animation ({package, actors: [{clip}]}), read again from its package only
    (not kept in the library cache). [] when the package or the animation is gone."""
    rel = anim.get('package') or ''
    path = os.path.join(SIMS_DIR, rel)
    if not rel or not os.path.isfile(path) or blocked_path(path):
        return []
    clips = [x['clip'].lower() for x in anim.get('actors') or [] if x.get('clip')]
    if not clips:
        return []
    try:
        idx = read_index(path)
    except Exception:
        return []
    needle = clips[0].encode('utf-8')
    for e in idx:
        if e['type'] != T_SNIPPET or e['mem'] > 8_000_000:
            continue
        try:
            d = read_resource(path, e)
        except Exception:
            continue
        if needle not in d.lower() or b'AnimationPackage' not in d[:300]:
            continue
        for an in _animation_elements(d.decode('utf-8', 'replace')):
            if _element_clips(an) == clips:
                return parse_events(an)
    return []


# ------------------------------------------------------------------ sound catalogue
_SOUND_KINDS = [
    ('clap', ('plap', 'slap', 'clap', 'punch', 'pound', 'smack', 'spank', 'impact', 'hit_', 'massagetable', 'thud', 'bump')),
    ('wet', ('oj_sound', 'blowjob', 'bj_', 'kiss', 'suck', 'slurp', 'lick', 'eat', 'drink', 'wet', 'squish', 'splash', 'bubble', 'gulp', 'chew', 'squelch')),
]


def sound_kind(name):
    n = name.lower()
    for kind, words in _SOUND_KINDS:
        if any(w in n for w in words):
            return kind
    return 'voice' if n.startswith(('vo_', 'voe_')) else 'other'


_sounds_lock = threading.Lock()
_sounds = None


def sounds():
    """Sound names that WickedWhims animations use in their clips, with how often (from clip headers).

    Kept with the animation library's package list: when packs move between Mods and Mods_parked (mods_switch,
    SpeedKit) the list is made again, so each sound's 'source' and 'package' say where it is now."""
    global _sounds
    with _sounds_lock:
        if _sounds is not None:
            return _sounds
        sig = library()['signature']
        path = _cache_path('sounds6.json')     # 6: made from library5
        cached = _load_cache(path) if os.path.exists(path) else None
        if isinstance(cached, dict) and cached.get('signature') == sig and isinstance(cached.get('sounds'), list):
            _sounds = cached['sounds']
            return _sounds
        out = _build_sounds()
        _store(path, {'signature': sig, 'sounds': out})
        _sounds = out
        return out


def _build_sounds():
    """[{name, count, kind, source, package}] from the clip headers of the adult library's clips."""
    counts = {}
    allowed = {int(k) for k in library()['clips']}
    for p in animation_packages():
        try:
            idx = read_index(p)
        except Exception:
            continue
        for e in idx:
            if e['type'] != T_CLIP_HEADER or e['inst'] not in allowed:
                continue
            try:
                c = parse_clip(read_resource(p, e) + b'\0' * 64)
            except Exception:
                continue
            for t, d in c['events']:
                if t == 3 and len(d) >= 140:
                    name = d[12:140].split(b'\0')[0].decode('ascii', 'replace').strip()
                    if name:
                        counts[name] = counts.get(name, 0) + 1
    where = _sound_sources()
    out = []
    for n, c in counts.items():
        h = fnv64(n)
        src = where.get(h) or where.get(h | (1 << 63)) or ['unknown', '']
        out.append({'name': n, 'count': c, 'kind': sound_kind(n), 'source': src[0], 'package': src[1]})
    out.sort(key=lambda x: -x['count'])
    return out


T_SOUND = 0xFD04E3BE


def _sound_sources():
    """sound resource instance -> [where, package]: 'game', 'mods' (loads now) or 'parked' (needs a parked pack)."""
    where = {}
    game = glob.glob(os.path.join(game_dir(), '**', 'Client*Build*.package'), recursive=True)
    for label, paths in (('game', game), ('mods', glob.glob(os.path.join(MODS_DIR, '**', '*.package'), recursive=True)),
                         ('parked', glob.glob(os.path.join(PARKED_DIR, '**', '*.package'), recursive=True))):
        for p in paths:
            if label != 'game' and blocked_path(p):
                continue          # adults only: blocked packs are never a sound source
            try:
                idx = read_index(p)
            except Exception:
                continue
            for e in idx:
                if e['type'] == T_SOUND and e['inst'] not in where:
                    where[e['inst']] = [label, os.path.relpath(p, SIMS_DIR) if label != 'game' else '']
    return where
