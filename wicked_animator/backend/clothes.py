"""Clothes for the preview, to check clipping with outfits: the CAS parts of a Tray sim's outfits, or a few basic EA
outfits for the plain bodies, as meshes skinned to auRig with their diffuse texture.

The parts are read exactly like hair (hair.py): the CAS part from the game's packages or the user's Mods (CC and
recolours included), its LOD 0 GEOMs (hair.lod0_geoms), the skinning mapped to the rig (hair._mesh_json) and its
diffuse image (hair._texture_bytes). A Tray sim's clothes get that sim's body shape the way its hair does
(hair.shape_geoms: the same BONDs, DMaps and blends as morph.morph_body() puts on the body).

Preview only: nothing here is ever written into an exported animation. Read-only on the game and Mods folders;
decoded parts are cached in cache/clothes.

    outfits_of(spec)           -> [{key, category, category_id, index, label, parts: [{casp, body_type,
                                   body_type_name, kind}]}]   the wearable outfits of a trayfmt.sim_body_spec()
    pick_outfit(outfits, key)  -> the outfit a key ('EVERYDAY', 'FORMAL:1') names, or None
    wearable(parts)            -> the parts the preview shows (clothes, shoes, hats, accessories), in drawing order
    basic_outfits(frame)       -> [{id, label, parts}] base-game outfits for a plain body ('yf', 'ym', 'yf_futa')
    part_mesh(casp, shape)     -> {casp, name, origin, body_type, kind, meshes, texture, cache} (like hair_mesh)
    cache_key(inst, pkg_path)  -> the cache file stem: the part's instance + its package's name, size and date
    texture_path(name)         -> the PNG a part's texture was written to (only names this module wrote)

Adults only: Tray sims must be young adults, adults or elders, and a CAS part without an adult age flag is refused.
"""
import hashlib
import json
import os
import re
import threading
import time
from collections import OrderedDict

import numpy as np

import hair

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, '..', 'cache', 'clothes')
VERSION = 1
T_CASP = hair.T_CASP
ADULT_FLAGS = hair.ADULT_FLAGS
FEMALE, MALE = 0x2000, 0x1000
MIN_SIZE = 0.005            # a GEOM smaller than 5 mm is a stand-in (earrings and rings are bigger than that)

# body type (trayfmt.BODY_TYPES / the CASP's body_type) -> what it is in the preview; anything else (hair, head,
# makeup, skin details, tattoos...) is not clothing
KIND = {1: 'hat', 5: 'full', 6: 'top', 7: 'bottom', 8: 'shoes', 36: 'socks', 42: 'tights'}
for _bt in (9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 88):
    KIND[_bt] = 'accessory'  # cummerbund, earrings, glasses, necklace, gloves, bracelets, rings, back attachment
ORDER = ['full', 'top', 'bottom', 'tights', 'socks', 'shoes', 'hat', 'accessory']

CATEGORY_LABEL = {'EVERYDAY': 'Everyday', 'FORMAL': 'Formal', 'ATHLETIC': 'Athletic', 'SLEEP': 'Sleep', 'PARTY': 'Party',
                  'SWIMWEAR': 'Swimwear', 'HOTWEATHER': 'Hot weather', 'COLDWEATHER': 'Cold weather',
                  'CAREER': 'Career', 'SITUATION': 'Situation', 'SPECIAL': 'Special', 'BATUU': 'Batuu',
                  'SMALL_BUSINESS': 'Small business'}
CATEGORY_ORDER = list(CATEGORY_LABEL)
SKIP_CATEGORIES = {'CURRENT_OUTFIT', 'BATHING'}          # the bathing outfit is the nude body

# Basic outfits for the plain bodies: base-game CAS parts found by their EA names (the game's own CASP names, read
# with casptex.casp_by_name). Per slot the shortest matching name that is really that body type, for adults and for
# that frame's gender wins; a slot nothing matches is left out, an outfit whose first slot is missing is not offered.
BASIC = [
    ('underwear', 'Underwear', {
        'yf': [('top', r'^yfTop_.*(Bra|Underwear|Bralette)'), ('bottom', r'^yfBottom_.*(Underwear|Pant(y|ies)|Brief|Knickers)')],
        'ym': [('bottom', r'^ymBottom_.*(Underwear|Boxer|Brief)')]}),
    ('casual', 'Casual', {
        'yf': [('top', r'^yfTop_.*(Tee|TShirt|Tank)'), ('bottom', r'^yfBottom_.*(Jeans|Denim)'),
               ('shoes', r'^yfShoes_.*(Sneaker|Trainer|Flats)')],
        'ym': [('top', r'^ymTop_.*(Tee|TShirt)'), ('bottom', r'^ymBottom_.*(Jeans|Denim)'),
               ('shoes', r'^ymShoes_.*(Sneaker|Trainer)')]}),
    ('swim', 'Swimwear', {
        'yf': [('top', r'^yfTop_.*Bikini'), ('bottom', r'^yfBottom_.*Bikini')],
        'ym': [('bottom', r'^ymBottom_.*(Swim|Trunks|Boardshort)')]}),
]
BODY_TYPE_OF = {'top': 6, 'bottom': 7, 'shoes': 8, 'full': 5}

_lock = threading.Lock()
_mem = OrderedDict()        # cache key -> plain part (the last 64)
_shaped = OrderedDict()     # (cache key, tray id, sim index) -> part shaped to that sim (the last 48)
_geom_mem = OrderedDict()   # casp instance -> (GEOMs, fallback bone) (the last 32)
_basic = {}                 # frame -> basic_outfits() answer (this process)


def _to_int(v):
    return hair._to_int(v)


def _hex(v):
    return '0x%016x' % (_to_int(v) & 0xFFFFFFFFFFFFFFFF)


# ------------------------------------------------------------------ outfits
def wearable(parts):
    """The parts of an outfit the preview shows: clothes, shoes, socks and tights, hats and accessories (not hair,
    head, makeup or skin details). Each once, in drawing order (full body, top, bottom, ..., accessories).
    parts: [{casp_instance | casp, body_type, ...}] -> [{casp, body_type, body_type_name, kind, ...}]"""
    out, seen = [], set()
    for p in parts or []:
        bt = int(p.get('body_type') or 0)
        kind = KIND.get(bt)
        inst = p.get('casp_instance') or p.get('casp')
        if not kind or inst in (None, '', 0, '0x0000000000000000'):
            continue
        try:
            key = _to_int(inst)
        except (TypeError, ValueError):
            continue
        if not key or key in seen:
            continue
        seen.add(key)
        q = {k: v for k, v in p.items() if k not in ('casp_instance',)}
        q.update(casp=_hex(key), body_type=bt, kind=kind)
        out.append(q)
    out.sort(key=lambda q: ORDER.index(q['kind']))
    return out


def outfits_of(spec):
    """The outfits of a Tray sim (spec = trayfmt.sim_body_spec(), or anything with its 'outfits' list) the preview
    can show, in the game's category order: [{key 'CATEGORY:index', category, category_id, index, label, parts}].
    The bathing outfit (the nude body) and outfits without anything to wear are left out. A category with more than
    one outfit numbers them: 'Everyday', 'Everyday 2'."""
    per = {}
    for o in (spec or {}).get('outfits') or []:
        cat = str(o.get('category'))
        if cat in SKIP_CATEGORIES:
            continue
        parts = wearable(o.get('parts'))
        if not parts:
            continue
        per.setdefault(cat, []).append((int(o.get('index') or 0), o, parts))
    out = []
    for cat in sorted(per, key=lambda c: (CATEGORY_ORDER.index(c) if c in CATEGORY_ORDER else 99, c)):
        items = sorted(per[cat], key=lambda x: x[0])
        base = CATEGORY_LABEL.get(cat, cat.replace('_', ' ').title())
        for k, (idx, o, parts) in enumerate(items):
            out.append({'key': '%s:%d' % (cat, idx), 'category': cat, 'category_id': o.get('category_id'),
                        'index': idx, 'label': base if k == 0 else '%s %d' % (base, k + 1), 'parts': parts})
    return out


def pick_outfit(outfits, key):
    """The outfit `key` names ('EVERYDAY' = its first, 'FORMAL:1'), or None."""
    if not key:
        return None
    cat, _, idx = str(key).partition(':')
    try:
        idx = int(idx) if idx else None
    except ValueError:
        return None
    same = [o for o in outfits if o['category'] == cat]
    if idx is None:
        return same[0] if same else None
    return next((o for o in same if o['index'] == idx), None)


def current_key(spec):
    """The key of the outfit the sim was saved in (or None when that one has nothing to show)."""
    cur = (spec or {}).get('current_outfit') or {}
    if not cur or cur.get('category') in SKIP_CATEGORIES:
        return None
    return '%s:%d' % (cur.get('category'), int(cur.get('index') or 0))


def tray_outfits(tray_id, index):
    """A Tray sim's outfits for the Clothes control: {name, outfits, current}. Each part also says whether it is
    installed ('origin': 'game' / 'cc' / None) and its CAS part name. Adults only (hair.tray_spec refuses others)."""
    import trayfmt
    spec = hair.tray_spec(tray_id, index)
    outs = outfits_of(spec)
    for o in outs:
        for p in o['parts']:
            try:
                p.update({k: v for k, v in trayfmt._part_info(_to_int(p['casp']), True).items() if k != 'casp_instance'})
            except Exception:
                p['origin'] = None
    cur = current_key(spec)
    return {'name': spec.get('name') or '', 'outfits': outs, 'current': cur if pick_outfit(outs, cur) else None}


# ------------------------------------------------------------------ basic outfits
def resolve_basic(frame, names, load):
    """The BASIC outfits for a frame, found in `names` ({CAS part name: instance}); load(instance) -> parsed CASP
    (casptex.parse_casp) or None. -> [{id, label, parts: [{casp, name, body_type, kind}]}]"""
    fk = 'ym' if frame == 'ym' else 'yf'
    gender = MALE if fk == 'ym' else FEMALE
    out = []
    for oid, label, per in BASIC:
        parts = []
        for n, (slot, rx) in enumerate(per.get(fk, [])):
            want = BODY_TYPE_OF[slot]
            rxc = re.compile(rx, re.I)
            cands = sorted((nm for nm in names if rxc.search(nm) and not hair._blocked(nm)), key=lambda s: (len(s), s))
            hit = None
            for nm in cands[:40]:
                try:
                    c = load(names[nm])
                except Exception:
                    c = None
                if not c or c.get('body_type') != want or not (c.get('age_gender', 0) & ADULT_FLAGS):
                    continue
                if not (c.get('age_gender', 0) & gender) or not (c.get('geoms') or c.get('all_geoms')):
                    continue
                hit = {'casp': _hex(names[nm]), 'name': nm, 'body_type': want, 'kind': KIND[want]}
                break
            if hit:
                parts.append(hit)
            elif n == 0:
                break
        if parts and parts[0]['kind'] == per[fk][0][0]:
            out.append({'id': oid, 'label': label, 'parts': parts})
    return out


def basic_outfits(frame):
    """resolve_basic() on the game's own CAS parts (base game; WickedWhims' overrides as the game shows them)."""
    import casptex
    fk = 'ym' if frame == 'ym' else 'yf'
    with _lock:
        if fk in _basic:
            return _basic[fk]
    res = resolve_basic(fk, casptex.casp_by_name(), lambda inst: casptex.load_casp(inst))
    with _lock:
        _basic[fk] = res
    return res


# ------------------------------------------------------------------ one part
def cache_key(inst, pkg_path):
    """'<instance>_<package signature>_v<VERSION>': a recolour or an updated CC package gets a new key, the same
    package the same one."""
    try:
        st = os.stat(pkg_path)
        sig = '%s|%d|%d' % (os.path.basename(pkg_path).lower(), st.st_size, int(st.st_mtime))
    except (OSError, TypeError):
        sig = os.path.basename(pkg_path or '').lower()
    return '%016x_%s_v%d' % (_to_int(inst), hashlib.sha1(sig.encode('utf-8')).hexdigest()[:8], VERSION)


def _dedupe(found):
    """LOD 0 GEOMs without repeats: two with the same vertex count and bounds (within 1 mm) are one mesh listed twice."""
    out = []
    for top, n, g, gm in sorted(found, key=lambda f: f[2]):
        pos = np.asarray(gm['positions'], np.float64).reshape(-1, 3)
        box = np.concatenate([pos.min(0), pos.max(0)])
        if any(n == n2 and np.abs(box - b2).max() < 1e-3 for n2, b2, _ in out):
            continue
        out.append((n, box, gm))
    return [gm for _, _, gm in out]


def fallback_bone(geoms, rig_index, default):
    """The rig bone a part leans on most (its known bones' summed weights) - where a vertex whose bones the rig doesn't
    know goes; `default` when none is known."""
    acc = {}
    for g in geoms:
        hashes = g.get('bone_hashes') or []
        if g.get('bones') is None or not hashes:
            continue
        b = np.asarray(g['bones'], np.int64).reshape(-1, 4)
        w = np.asarray(g['weights'], np.float64).reshape(-1, 4)
        for k, hsh in enumerate(hashes):
            if hsh in rig_index:
                s = float(w[b == k].sum())
                if s > 0:
                    acc[rig_index[hsh]] = acc.get(rig_index[hsh], 0.0) + s
    return max(acc, key=acc.get) if acc else default


def _rig():
    import gamedata
    rig = gamedata.rig('au')
    rig_index = {b['hash']: k for k, b in enumerate(rig['bones'])}
    names = {b['name']: k for k, b in enumerate(rig['bones'])}
    return rig_index, names.get('b__Pelvis__', names.get('b__ROOT_bind__', 0))


def _part_geoms(inst, casp=None, origin=None):
    """(GEOMs, fallback bone) of a part's LOD 0 (in memory, the last 32)."""
    inst = _to_int(inst)
    with _lock:
        if inst in _geom_mem:
            _geom_mem.move_to_end(inst)
            return _geom_mem[inst]
    found, listed = hair.lod0_geoms(inst, casp, origin, min_size=MIN_SIZE)
    geoms = _dedupe(found)
    rig_index, pelvis = _rig()
    hit = (geoms, fallback_bone(geoms, rig_index, pelvis), listed)
    with _lock:
        _geom_mem[inst] = hit
        while len(_geom_mem) > 32:
            _geom_mem.popitem(last=False)
    return hit


def _remember(table, key, value, keep):
    with _lock:
        table[key] = value
        table.move_to_end(key)
        while len(table) > keep:
            table.popitem(last=False)


def part_mesh(casp_inst, shape=None):
    """A clothing CAS part as preview meshes + a texture file name (see the module doc). shape: a Tray sim's
    sim_body_spec() - the part then gets that sim's body shape, as its hair does. The plain part is cached on disk
    (cache/clothes/<cache_key>.json + clothes_<cache_key>.png) and in memory; a shaped one in memory only."""
    base = _part_base(casp_inst)
    if not shape or not base.get('meshes'):
        return base
    key = (base['cache'], str(shape.get('tray_id')), int(shape.get('sim_index') or 0))
    with _lock:
        if key in _shaped:
            _shaped.move_to_end(key)
            return _shaped[key]
    geoms, fb, _ = _part_geoms(casp_inst)
    rig_index, _ = _rig()
    out = dict(base, meshes=hair.shape_geoms(geoms, shape, rig_index, fb, drop_unknown=True),
               shaped_for=shape.get('name') or '')
    _remember(_shaped, key, out, 48)
    return out


def _part_base(casp_inst):
    import morph, casptex, texfmt
    inst = _to_int(casp_inst)
    row = morph.PART_INDEX.find(T_CASP, inst)
    if row is None:                                   # not installed: nothing to show, no error (not cached: it may come)
        return {'casp': _hex(inst), 'name': None, 'origin': None, 'meshes': [], 'texture': None}
    origin = 'cc' if int(row['pkg']) < morph.PART_INDEX.n_cc else 'game'
    pkg_path = morph.PART_INDEX.paths[int(row['pkg'])]
    key = cache_key(inst, pkg_path)
    with _lock:
        if key in _mem:
            _mem.move_to_end(key)
            return _mem[key]
    os.makedirs(CACHE, exist_ok=True)
    jpath = os.path.join(CACHE, key + '.json')
    if os.path.isfile(jpath):
        try:
            with open(jpath, encoding='utf-8') as f:
                out = json.load(f)
            if not out.get('texture') or os.path.isfile(os.path.join(CACHE, out['texture'])):
                _remember(_mem, key, out, 64)
                return out
        except Exception:
            pass
    t0 = time.time()
    casp = casptex.parse_casp(morph.PART_INDEX.read(T_CASP, inst))
    if not (casp.get('age_gender', 0) & ADULT_FLAGS):
        raise ValueError('That CAS part is not for adults.')
    bt = casp.get('body_type')
    if bt not in KIND:
        raise ValueError('That CAS part is not clothing.')
    geoms, fb, listed = _part_geoms(inst, casp, origin)
    rig_index, _ = _rig()
    meshes = [_mesh(g, rig_index, fb) for g in geoms]
    out = {'casp': _hex(inst), 'name': casp.get('name'), 'origin': origin, 'body_type': bt, 'kind': KIND[bt],
           'meshes': meshes, 'texture': None, 'cache': key,
           'unknown_bones': sorted({'0x%08x' % h for g in geoms for h in (g.get('bone_hashes') or []) if h not in rig_index})}
    if not meshes:
        # only a stand-in GEOM, or none: the game paints this part on the skin (tights, socks, most gloves)
        out['painted'] = listed > 0 or not casp.get('geoms')
        out['seconds'] = round(time.time() - t0, 3)
        _remember(_mem, key, out, 64)
        return out
    tgi = (casp.get('textures') or {}).get('diffuse')
    if tgi:
        try:
            raw = hair._texture_bytes(tgi, pkg_path)
            if raw:
                name = 'clothes_%s.png' % key
                hair._write_png(texfmt.decode(raw), os.path.join(CACHE, name))
                out['texture'] = name
        except Exception as ex:
            out['texture_error'] = str(ex)
    out['seconds'] = round(time.time() - t0, 3)
    tmp = jpath + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(out, f, separators=(',', ':'))
    os.replace(tmp, jpath)
    _remember(_mem, key, out, 64)
    return out


def _mesh(g, rig_index, fb):
    return hair._mesh_json(g, rig_index, fb, drop_unknown=True)


def texture_path(name):
    """The PNG a part's texture was written to, or None (the name must be one this module wrote)."""
    base = os.path.basename(name or '')
    if not re.match(r'^clothes_[0-9a-f]{16}_[0-9a-f]{8}_v\d+\.png$', base):
        return None
    p = os.path.join(CACHE, base)
    return p if os.path.isfile(p) else None
