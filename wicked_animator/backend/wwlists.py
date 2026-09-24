"""WickedWhims' own animation lists for the Doctor's Browse tab (needs.md section 1): every installed animation with
its WickedWhims "identifier", and the two lists a player changes by hand - Favorites and "Turn off".

    browse(q)       {ready, building, done, total, proof, writes, items, places, acts, counts}   (read-only)
    proof()         does our identifier formula reproduce the entries already in the user's WickedWhims files?
    mark(body)      {action: 'favorite'|'turn_off', id: <identifier>, on: bool}   - only on a click in the app
    identifier(a)   the identifier WickedWhims gives one animation (None when WickedWhims would refuse to load it)

THE IDENTIFIER (read from WickedWhims' own script, v185k: wickedwhims/sex/animations/animation_instance.pyc,
SexAnimationInstance.get_identifier, with animations_loader._create_sex_animation_instance for the values):
sha1(utf-8 of the concatenated str() of, skipping None)
    display name (animation_raw_display_name, else the string-table hash of animation_display_name, in decimal),
    author, 'SexCategoryType.<CATEGORY>', the number of actors,
    the .name of every place (a Python set of SexLocationType ints, so in CPython's set order),
    object_animation_clip_name, object_geometry_state or None, object_material_state or None,
    'SexGenderType.<GENDER>' of every actor, then every actor's clip name, then every actor's
    x, y, z (float32 - the game's native Vector3) and angle offset (degrees) - actors sorted by gender (men first),
    each prop's clip name (or (clip, geometry state) as a tuple), and the version when it is above 1.

PROOF (read-only, tools/checks/r3-2): on this PC the formula reproduces 232 of the 232 animations WickedWhims lists as
installed (last_installed_sex_animations.ww), 76 of 80 favorites, 69 of 70 playlist entries and 49 of 50 recently
used ones (the rest belong to packs that are no longer on the PC). proof() repeats the comparison every time, so a
WickedWhims update that changes the formula switches writing off by itself: the app then keeps Favorites and
"Turn off" to itself and says so.

Writes (mark) happen only on a click, only while The Sims 4 is closed, only for an adult animation that is on this PC,
and only when proof() holds. The file is backed up first (cache/doctor/backups) and replaced in one step, in exactly
the format WickedWhims writes it (favorites: one identifier per line, CRLF; all_disabled_animations.json: json.dump).

Adults only: packages whose path hits the block list are never read; an animation that fails
gamedata.adult_animation is never listed, previewed or counted in the proof.
WICKED_SIMS_DIR (tests) replaces the 'The Sims 4' folder (through doctor.sims_dir()).
"""
import hashlib
import json
import math
import os
import pickle
import re
import struct
import threading
import time
import traceback
import xml.etree.ElementTree as ET

import doctor as D
from dbpf import read_index, read_resource

CACHE_VERSION = 1
T_SNIPPET, T_STBL = 0x7DF2169C, 0x220557DA

CATEGORIES = {'TEASING': 0, 'HANDJOB': 1, 'FOOTJOB': 2, 'ORALJOB': 3, 'VAGINAL': 4, 'ANAL': 5, 'CLIMAX': 6}
ACT_WORDS = {'TEASING': 'Teasing', 'HANDJOB': 'Handjob', 'FOOTJOB': 'Footjob', 'ORALJOB': 'Oral', 'VAGINAL': 'Vaginal',
             'ANAL': 'Anal', 'CLIMAX': 'Climax'}
# SexGenderType (wickedwhims/sex/enums/sex_gender.pyc). SERVO_FEMALE shares 15 with MERMAID_FEMALE: an alias, so its
# str() is the first name, MERMAID_FEMALE.
GENDERS = [('NONE', 0), ('MALE', 1), ('VAMPIRE_MALE', 2), ('GHOST_MALE', 3), ('ALIEN_MALE', 4), ('MERMAID_MALE', 5),
           ('WITCH_MALE', 6), ('SERVO_MALE', 7), ('WEREWOLF_MALE', 8), ('FAIRY_MALE', 9), ('FEMALE', 11),
           ('VAMPIRE_FEMALE', 12), ('GHOST_FEMALE', 13), ('ALIEN_FEMALE', 14), ('MERMAID_FEMALE', 15),
           ('WITCH_FEMALE', 16), ('SERVO_FEMALE', 15), ('WEREWOLF_FEMALE', 17), ('FAIRY_FEMALE', 18),
           ('VAMPIRE_BOTH', 22), ('GHOST_BOTH', 23), ('ALIEN_BOTH', 24), ('MERMAID_BOTH', 25), ('WITCH_BOTH', 26),
           ('SERVO_BOTH', 27), ('WEREWOLF_BOTH', 28), ('FAIRY_BOTH', 29), ('BOTH', 50)]
GENDER_VALUE = dict(GENDERS)
GENDER_NAME = {}
for _n, _v in GENDERS:
    GENDER_NAME.setdefault(_v, _n)

# Is the proof good enough to write? Most of what WickedWhims lists as installed must come out the same (at least
# 10 of them), or - with no installed list yet - most favorites.
PROOF_MIN = 10
PROOF_SHARE = 0.9
PROOF_FAV_MIN, PROOF_FAV_SHARE = 5, 0.8

FAVORITES = 'sex_animations_favorites.ww'
DISABLED = 'all_disabled_animations.json'
_ID = re.compile(r'^[0-9a-f]{40}$')


# ------------------------------------------------------------------ the identifier
def _f32(x):
    return struct.unpack('<f', struct.pack('<f', x))[0]


def _num(text, default=0.0):
    try:
        return float(str(text).strip())
    except (TypeError, ValueError):
        return default


def _human(v):
    """get_human_sex_gender_variant: NONE, MALE, FEMALE or BOTH."""
    if v == 0:
        return 0
    if 1 <= v <= 9:
        return 1
    if 11 <= v <= 18:
        return 11
    return 50


def _places(raw):
    """_parse_sex_animation_location_types: a set of SexLocationType values (unknown names dropped), in the order
    CPython iterates a set of small ints built in that order - the order WickedWhims sees them in."""
    raw = raw if raw is not None else 'NONE'
    if not raw:
        return []
    names = raw.split(',') if ',' in raw else [raw]
    s = set()
    for n in names:
        n = n.strip().upper()
        if n and n in D.LOCATION_TYPES:
            s.add(D.LOCATION_TYPES[n])
    return list(s)


def identifier(a):
    """The identifier WickedWhims gives an animation parsed by parse_xml(), or None when WickedWhims would refuse
    to load it (no name, no author, a misspelled act, no place, a sim without a gender...)."""
    disp = a.get('raw') or ''
    if not disp:
        try:
            key = int(str(a.get('display') or '').strip(), 0)
        except ValueError:
            return None
        if not key:
            return None
        disp = str(key)
    author = a.get('author') or ''
    if not author:
        return None
    cat = str(a.get('category') or '').upper().strip()
    if cat not in CATEGORIES:
        return None
    actors = a.get('actors') or []
    if not actors or len(actors) > 10:
        return None
    ids = [x.get('actor_id', '') for x in actors]
    if len(set(ids)) != len(ids):
        return None
    places = _places(a.get('locations'))
    if not places and not (a.get('custom') or '').strip():
        return None
    acts = []
    for x in actors:
        g = GENDER_VALUE.get(str(x.get('genders') or '').upper().strip(), 0)
        if g == 0:
            return None
        pref = _human(GENDER_VALUE.get(str(x.get('pref') or '').upper().strip(), 0))
        if pref == 50:
            pref = 0                                   # "unspecific preferenced gender" becomes NONE
        human = _human(g)
        acts.append(((human if human != 50 else (pref or 50)), g, x))
    acts.sort(key=lambda t: t[0])                     # stable, like list.sort
    parts = [disp, author, 'SexCategoryType.' + cat, str(len(actors))]
    parts += [D.LOCATION_NAMES[v] for v in places]
    parts += [a.get('obj_clip') or '', a.get('obj_geo') or None, a.get('obj_mat') or None]
    parts += ['SexGenderType.' + GENDER_NAME[g] for _, g, _x in acts]
    parts += [x.get('clip') or '' for _, _g, x in acts]
    for _, _g, x in acts:
        xs, ys, zs = _num(x.get('x')), _num(x.get('y')), _num(x.get('z'))
        if xs or ys or zs:
            xs, ys, zs = _f32(xs), _f32(ys), _f32(zs)
        else:
            xs = ys = zs = 0.0
        ang = _num(x.get('angle')) or math.degrees(_num(x.get('facing')))
        parts += [xs, ys, zs, float(ang)]
    for p in a.get('props') or []:
        parts.append((p.get('clip') or '', p['geo']) if p.get('geo') else (p.get('clip') or ''))
    try:
        v = int(str(a.get('version') or '1').strip())
    except ValueError:
        v = 1
    parts.append(v if v > 1 else None)
    base = ''.join(p if isinstance(p, str) else str(p) for p in parts if p is not None)
    return hashlib.sha1(base.encode('utf-8')).hexdigest()


# ------------------------------------------------------------------ reading the packages
def _fields(el):
    out = {}
    for c in el:
        out.setdefault(c.get('n'), c)
    return out


def _txt(d, k, default=''):
    c = d.get(k)
    if c is None:
        return default
    return (c.text or '').strip()


def parse_xml(data):
    """A WickedWhims animation snippet -> [raw animation dicts] with every field the identifier needs."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return []
    out = []
    for lst in root.iter():
        if lst.get('n') != 'animations_list':
            continue
        for an in lst:
            if not len(an):
                continue
            d = _fields(an)
            actors = []
            al = d.get('animation_actors_list')
            for x in (al if al is not None else []):
                f = _fields(x)
                genders = [(c.text or '').strip() for c in x if c.get('n') == 'animation_genders']
                actors.append({'actor_id': _txt(f, 'actor_id'),
                               'clip': _txt(f, 'animation_clip_name') or _txt(f, 'animation_name'),
                               'type': _txt(f, 'animation_type'), 'genders': _txt(f, 'animation_genders'),
                               'all_genders': [g for g in genders if g],
                               'pref': _txt(f, 'animation_pref_gender'),
                               'x': _txt(f, 'animation_x_offset'), 'y': _txt(f, 'animation_y_offset'),
                               'z': _txt(f, 'animation_z_offset'), 'angle': _txt(f, 'animation_angle_offset'),
                               'facing': _txt(f, 'animation_facing_offset')})
            props = []
            pl = d.get('animation_props_list')
            for p in (pl if pl is not None else []):
                f = _fields(p)
                props.append({'clip': _txt(f, 'prop_animation_clip_name'), 'geo': _txt(f, 'prop_geometry_state')})
            out.append({'display': _txt(d, 'animation_display_name'), 'raw': _txt(d, 'animation_raw_display_name'),
                        'author': _txt(d, 'animation_author'), 'locations': _txt(d, 'animation_locations', 'NONE'),
                        'custom': _txt(d, 'animation_custom_locations'), 'category': _txt(d, 'animation_category'),
                        'obj_clip': _txt(d, 'object_animation_clip_name'), 'obj_geo': _txt(d, 'object_geometry_state'),
                        'obj_mat': _txt(d, 'object_material_state'), 'version': _txt(d, 'animation_version', '1'),
                        'hidden': _txt(d, 'animation_hidden', '0'), 'actors': actors, 'props': props})
    return out


def _adult(a, rel):
    import gamedata as G
    b = {'name': a.get('raw') or '', 'author': a.get('author') or '', 'package': rel,
         'actors': [{'clip': x.get('clip') or '', 'gender': x.get('genders') or '', 'genders': x.get('all_genders') or [],
                     'prefs': [p.strip() for p in (x.get('pref') or '').split(',') if p.strip()]} for x in a.get('actors') or []]}
    return G.adult_animation(b)


def _stbl(path, idx):
    out = {}
    for e in idx:
        if e['type'] == T_STBL and ((e['inst'] >> 56) & 0xFF) == 0x00:      # English tables
            try:
                out.update(D._stbl(read_resource(path, e)))
            except Exception:
                pass
    return out


def _nice_place(v):
    return D.LOCATION_NAMES.get(v, str(v)).replace('_', ' ').lower().capitalize()


def package_entries(path, rel):
    """Every WickedWhims animation in one package -> ([adult entries], number of animations not shown)."""
    try:
        idx = read_index(path)
    except Exception:
        return [], 0
    anims = []
    for e in idx:
        if e['type'] != T_SNIPPET or e['mem'] > 8_000_000:
            continue
        try:
            data = read_resource(path, e)
        except Exception:
            continue
        if b'animations_list' not in data:
            continue
        anims.extend(parse_xml(data))
    if not anims:
        return [], 0
    strings = _stbl(path, idx) if any(a['display'] and not a['raw'] for a in anims) else {}
    out, hidden = [], 0
    for a in anims:
        name = a['raw']
        if not name:
            try:
                name = strings.get(int(a['display'], 0), '')
            except ValueError:
                name = ''
        if not _adult(dict(a, raw=name), rel):
            hidden += 1                                   # never named, listed or counted anywhere
            continue
        ident = identifier(a)
        if not ident:
            continue                                      # WickedWhims never loads it (the Doctor explains why)
        cat = a['category'].upper().strip()
        places = _places(a['locations'])
        out.append({'id': ident, 'name': name or a['actors'][0]['clip'], 'author': a['author'], 'act': cat,
                    'places': [D.LOCATION_NAMES.get(v, str(v)) for v in places if v],
                    'custom': bool((a.get('custom') or '').strip()),
                    'sims': len(a['actors']), 'clips': [x['clip'] for x in a['actors']],
                    'genders': [x['genders'].upper() for x in a['actors']], 'props': len(a['props']),
                    'hidden': a.get('hidden') not in ('', '0', 'False', 'false')})
    return out, hidden


# ------------------------------------------------------------------ the index (cached per package)
_lock = threading.Lock()
_state = {'running': False, 'done': 0, 'total': 0, 'items': None, 'hidden': 0, 'error': None, 'built': 0, 'sig': None}


def _cache_file():
    """One cache per 'The Sims 4' folder, so a test's fake folder never pushes out the real one."""
    tag = hashlib.sha1(os.path.normcase(os.path.abspath(D.sims_dir())).encode('utf-8')).hexdigest()[:10]
    return os.path.join(D.CACHE_DIR, 'wwlists_v%d_%s.pickle' % (CACHE_VERSION, tag))


def _packages():
    out = []
    for where, root in (('mods', D.mods_dir()), ('parked', D.parked_dir())):
        if not os.path.isdir(root):
            continue
        for dp, dn, fn in os.walk(root):
            for n in fn:
                if not n.lower().endswith('.package'):
                    continue
                full = os.path.join(dp, n)
                rel = D._rel(full, D.sims_dir())
                if D._blocked_rel(rel):
                    continue                              # adults only: never opened
                try:
                    st = os.stat(full)
                except OSError:
                    continue
                out.append((where, rel, full, st.st_size, int(st.st_mtime)))
    return sorted(out, key=lambda t: t[1].lower())


def _build():
    pk = _packages()
    sig = [(rel, size, mt) for _w, rel, _f, size, mt in pk]
    try:
        with open(_cache_file(), 'rb') as f:
            cache = pickle.load(f)
        if not isinstance(cache, dict) or cache.get('root') != D.sims_dir():
            cache = {}
    except Exception:
        cache = {}
    per = cache.get('packages') or {}
    items, hidden, fresh = [], 0, {}
    with _lock:
        _state.update({'done': 0, 'total': len(pk)})
    for k, (where, rel, full, size, mt) in enumerate(pk):
        hit = per.get(rel)
        if hit and hit[0] == size and hit[1] == mt:
            entries, hid = hit[2], hit[3]
        else:
            entries, hid = package_entries(full, rel)
        fresh[rel] = (size, mt, entries, hid)
        hidden += hid
        for e in entries:
            items.append(dict(e, where=where, file=rel))
        with _lock:
            _state['done'] = k + 1
    try:
        os.makedirs(D.CACHE_DIR, exist_ok=True)
        tmp = _cache_file() + '.tmp'
        with open(tmp, 'wb') as f:
            pickle.dump({'root': D.sims_dir(), 'packages': fresh}, f, protocol=4)
        os.replace(tmp, _cache_file())
    except Exception:
        traceback.print_exc()
    return items, hidden, sig


def _run():
    try:
        items, hidden, sig = _build()
        with _lock:
            _state.update({'running': False, 'items': items, 'hidden': hidden, 'built': time.time(), 'sig': sig,
                           'error': None})
    except Exception as ex:
        traceback.print_exc()
        with _lock:
            _state.update({'running': False, 'error': str(ex) or repr(ex)})


def ensure(force=False, wait=False):
    """Start (or reuse) the index. A finished one is reused unless a package changed (checked at most every 5 s)."""
    with _lock:
        if _state['running']:
            t = None
        else:
            stale = force or _state['items'] is None
            if not stale and time.time() - _state['built'] > 5:
                sig = [(rel, size, mt) for _w, rel, _f, size, mt in _packages()]
                stale = sig != _state['sig']
                if not stale:
                    _state['built'] = time.time()
            if stale:
                _state.update({'running': True, 'error': None})
                t = threading.Thread(target=_run, daemon=True, name='wwlists')
                t.start()
            else:
                t = None
    if wait and t:
        t.join()
    return status()


def status():
    with _lock:
        return {k: _state[k] for k in ('running', 'done', 'total', 'error')}


def items():
    with _lock:
        return list(_state['items'] or [])


# ------------------------------------------------------------------ WickedWhims' own files (read-only here)
def _lines(path):
    try:
        with open(path, encoding='utf-8') as f:
            return [x.strip() for x in f.read().splitlines() if x.strip()]
    except (OSError, UnicodeDecodeError):
        return []


def ww_files():
    """{name: [identifiers]} read from saves\\WickedWhimsMod (read-only)."""
    d = D.ww_saves_dir()
    out = {'installed': _lines(os.path.join(d, 'last_installed_sex_animations.ww')),
           'favorites': _lines(os.path.join(d, FAVORITES)),
           'recent': _lines(os.path.join(d, 'animations_recently_used.ww')),
           'use_count': [x.split('=')[0].strip() for x in _lines(os.path.join(d, 'animations_use_count.ww'))],
           'playlists': []}
    for line in _lines(os.path.join(d, 'sex_animations_playlists.ww')):
        out['playlists'] += [p.strip() for p in line.split(',') if _ID.match(p.strip())]
    dis = D._read_json(os.path.join(d, DISABLED))
    out['disabled'] = list((dis or {}).get('disabled_animations') or []) if isinstance(dis, dict) else []
    out['autonomy_disabled'] = list((dis or {}).get('autonomy_disabled_animations') or []) if isinstance(dis, dict) else []
    for k in out:
        out[k] = [x.lower() for x in out[k] if isinstance(x, str) and _ID.match(x.lower())]
    return out


def ww_version():
    try:
        with open(os.path.join(D.ww_saves_dir(), 'last_version_control.ww'), encoding='utf-8') as f:
            lines = [x.strip() for x in f.read().splitlines() if x.strip()]
        return next((x for x in reversed(lines) if x.lower().startswith('v')), lines[-1] if lines else '')[:20]
    except OSError:
        return ''


def proof(ids=None):
    """Compare our identifiers with the entries WickedWhims itself wrote (read-only). -> {proven, installed: [matched,
    total], favorites: [...], playlists, recent, use_count, version, text}"""
    ids = set(ids if ids is not None else (x['id'] for x in items()))
    files = ww_files()
    res = {'version': ww_version()}
    for k in ('installed', 'favorites', 'playlists', 'recent', 'use_count'):
        uniq = set(files[k])
        res[k] = [len(uniq & ids), len(uniq)]
    m, n = res['installed']
    fm, fn = res['favorites']
    ok = (n >= PROOF_MIN and m >= PROOF_MIN and m >= PROOF_SHARE * n) or \
         (n < PROOF_MIN and fn >= PROOF_FAV_MIN and fm >= PROOF_FAV_MIN and fm >= PROOF_FAV_SHARE * fn)
    res['proven'] = bool(ok)
    if ok:
        res['text'] = ("Checked against WickedWhims' own lists: %d of %d installed animations and %d of %d favorites "
                       "have exactly the name this app works out." % (m, n, fm, fn))
    elif not n and not fn:
        res['text'] = ("WickedWhims hasn't listed your animations yet (start The Sims 4 with WickedWhims once). Until "
                       "then Favorite and Turn off are kept in this app only.")
    else:
        res['text'] = ("This WickedWhims version (%s) names animations differently from what this app knows (%d of %d "
                       "match), so Favorite and Turn off are kept in this app only." % (res['version'] or '?', m, n))
    return res


# ------------------------------------------------------------------ Browse
def browse(q=None):
    q = q or {}
    st = ensure(force=str(q.get('refresh', '')).lower() in ('1', 'true', 'yes'))
    if st['running'] or _state['items'] is None:
        return {'ready': False, 'building': True, 'done': st['done'], 'total': st['total'], 'error': st['error'],
                'items': []}
    all_items = items()
    pr = proof([x['id'] for x in all_items])
    files = ww_files()
    fav, off = set(files['favorites']), set(files['disabled'])
    lib = _library_ids()
    text = (q.get('q') or '').lower().strip()
    where = q.get('where') or 'mods'
    place, act = q.get('place') or '', (q.get('act') or '').upper()
    sims = int(q.get('sims') or 0)
    only = q.get('only') or ''
    out, places, acts, counts = [], {}, {}, {'mods': 0, 'parked': 0, 'fav': 0, 'off': 0}
    seen, counted = set(), set()
    for x in all_items:
        if (x['where'], x['id']) not in counted:
            counted.add((x['where'], x['id']))
            counts[x['where']] = counts.get(x['where'], 0) + 1
        if where != 'all' and x['where'] != where:
            continue
        key = x['id']
        if key in seen:
            continue                                      # the same animation in two packages: listed once
        seen.add(key)
        is_fav, is_off = key in fav, key in off
        counts['fav'] += is_fav
        counts['off'] += is_off
        for p in x['places'] or (['CUSTOM'] if x['custom'] else []):
            places[p] = places.get(p, 0) + 1
        acts[x['act']] = acts.get(x['act'], 0) + 1
        if place and place not in x['places'] and not (place == 'CUSTOM' and x['custom']):
            continue
        if act and x['act'] != act:
            continue
        if sims and x['sims'] != sims:
            continue
        if only == 'fav' and not is_fav:
            continue
        if only == 'off' and not is_off:
            continue
        if text and text not in x['name'].lower() and text not in x['author'].lower():
            continue
        out.append({'id': key, 'name': x['name'], 'author': x['author'], 'act': x['act'],
                    'act_label': ACT_WORDS.get(x['act'], x['act'].title()),
                    'places': [p.replace('_', ' ').lower().capitalize() for p in x['places']] or (['Custom object'] if x['custom'] else []),
                    'sims': x['sims'], 'genders': x['genders'], 'where': x['where'], 'file': x['file'],
                    'fav': is_fav, 'off': is_off, 'props': x['props'], 'hidden': x['hidden'],
                    'lib': lib.get(_join_key(x['file'], x['author'], x['clips']))})
    out.sort(key=lambda r: (not r['fav'], r['name'].lower()))
    page = max(0, int(q.get('page') or 0))
    return {'ready': True, 'total': len(out), 'items': out[page * 150:(page + 1) * 150], 'proof': pr,
            'writes': 'ww' if pr['proven'] else 'app', 'places': places, 'acts': acts, 'counts': counts,
            'not_shown': _state['hidden'], 'sims_dir': D.sims_dir()}


def _join_key(rel, author, clips):
    return (rel.replace('\\', '/').lower(), (author or '').lower(), tuple(c.lower() for c in clips))


_lib_cache = {'sig': None, 'map': {}}


def _library_ids():
    """(package, author, clips) -> the app library's id, for the 3D preview (gamedata reads the real Mods folder;
    under WICKED_SIMS_DIR only packages with the same place and name join)."""
    try:
        import gamedata as G
        lib = G.library()
    except Exception:
        traceback.print_exc()
        return {}
    sig = (id(lib), len(lib['animations']))
    if _lib_cache['sig'] != sig:
        m = {}
        for a in lib['animations']:
            if not a.get('available'):
                continue
            m.setdefault(_join_key(a.get('package') or '', a.get('author') or '', [x['clip'] for x in a['actors']]), a['id'])
        _lib_cache.update({'sig': sig, 'map': m})
    return _lib_cache['map']


# ------------------------------------------------------------------ the two writes (on a click only)
def _refuse(reason, text):
    return {'ok': False, 'reason': reason, 'error': text}


def _write_lines(path, lines):
    """WickedWhims' own way: writelines(identifier + '\\n') in text mode on Windows -> CRLF after every line."""
    tmp = path + '.wa.tmp'
    with open(tmp, 'wb') as f:
        f.write(''.join(x + '\r\n' for x in lines).encode('utf-8'))
    os.replace(tmp, path)


def mark(body):
    """{action: 'favorite'|'turn_off', id, on} -> changes WickedWhims' own list (see the module docstring)."""
    action = (body or {}).get('action')
    if action not in ('favorite', 'turn_off'):
        raise ValueError('Unknown list.')
    ident = str((body or {}).get('id') or '').strip().lower()
    if not _ID.match(ident):
        raise ValueError('That is not an animation of yours.')
    on = bool((body or {}).get('on', True))
    ensure(wait=True)
    all_items = items()
    known = {x['id']: x for x in all_items}
    if ident not in known:
        return _refuse('unknown', "That animation isn't on this PC any more - press Rescan.")
    pr = proof(list(known))
    if not pr['proven']:
        return _refuse('not_proven', pr['text'])
    busy = D._game_check()
    if busy:
        return busy
    d = D.ww_saves_dir()
    if not os.path.isdir(d):
        return _refuse('no_ww', "WickedWhims' settings folder isn't there yet - start The Sims 4 with WickedWhims once.")
    name = known[ident]['name']
    if action == 'favorite':
        path = os.path.join(d, FAVORITES)
        lines = _lines(path)
        have = ident in (x.lower() for x in lines)
        if have == on:
            return {'ok': True, 'changed': False, 'on': on, 'text': 'That was already so.'}
        backup = D._backup(path) if os.path.exists(path) else None
        lines = lines + [ident] if on else [x for x in lines if x.lower() != ident]
        _write_lines(path, lines)
        return {'ok': True, 'changed': True, 'on': on, 'backup': backup,
                'text': ('"%s" is a favorite in WickedWhims now.' if on else '"%s" is no longer a WickedWhims favorite.') % name}
    path = os.path.join(d, DISABLED)
    data = D._read_json(path) if os.path.exists(path) else None
    if data is None and os.path.exists(path):
        return _refuse('unreadable', "WickedWhims' switch-off list couldn't be read, so nothing was changed.")
    if not isinstance(data, dict):
        data = {'disabled_animations': [], 'autonomy_disabled_animations': [], 'disabled_dance_animations': []}
    cur = [x for x in (data.get('disabled_animations') or []) if isinstance(x, str)]
    have = ident in (x.lower() for x in cur)
    if have == on:
        return {'ok': True, 'changed': False, 'on': on, 'text': 'That was already so.'}
    backup = D._backup(path) if os.path.exists(path) else None
    data['disabled_animations'] = cur + [ident] if on else [x for x in cur if x.lower() != ident]
    for k in ('autonomy_disabled_animations', 'disabled_dance_animations'):
        data.setdefault(k, [])
    D._write_json(path, data)
    return {'ok': True, 'changed': True, 'on': on, 'backup': backup,
            'text': ('"%s" is turned off - WickedWhims won\'t offer it.' if on else '"%s" is turned back on.') % name}
