"""Hair meshes for the preview: a CAS part's LOD0 GEOMs skinned to auRig, and its diffuse texture as a PNG.

Read-only from the game's own packages and the user's Mods (the same readers the Tray bodies use). Nothing is
downloaded and nothing is written outside cache/hair.

    hair_mesh(casp_inst, shape=None)
                          -> {'casp', 'name', 'origin', 'meshes': [{positions, normals, uvs, faces, bones, weights}],
                              'texture': 'hair_<inst>_v1.png' or None}            (cached as cache/hair/<inst>_v1.json)
                             shape: a Tray sim's trayfmt.sim_body_spec(). The hair then gets that sim's body shape,
                             as in the game: its sliders' BONDs (a height or neck slider moves the head, and the hair
                             with it), DMaps and blends go through the hair's own skin weights and UV1, exactly as
                             morph.morph_body() does for the body. Without it the hair fits the default body only.
    hair_for_name(name, shape=None)
                          -> hair_mesh() of a base-game hair by its CAS part name (e.g. 'yfHair_PonyTailTight_Brown')
    presets()             -> [{'name', 'style', 'colour', 'frame', 'label', 'swatch'}] base-game adult hair that exists

Adults only: hair is only ever asked for adult sims (the Tray route refuses others), preset names start with yf/ym,
and a CAS part without an adult age flag (young adult / adult / elder) is refused.
"""
import json, os, re, threading, time
from collections import OrderedDict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, '..', 'cache', 'hair')
VERSION = 2                # 2: the uncut hair of LOD 0 (not the hat-cut one with the most vertices), no placeholders
T_CASP, T_GEOM = 0x034AEECB, 0x015A1849
ADULT_FLAGS = 0x10 | 0x20 | 0x40            # young adult, adult, elder

# base-game adult hair, checked at runtime (a missing name is dropped)
PRESETS = {
    'yf': ['yfHair_PonyTailTight', 'yfHair_LongWavy', 'yfHair_LongStraight', 'yfHair_ShortBob', 'yfHair_UpdoBun',
           'yfHair_MedWavySweptSoft', 'yfHair_AfroMedium', 'yfHair_LongRocker'],
    'ym': ['ymHair_DreamyCrew', 'ymHair_ShortSpikey', 'ymHair_MediumCurly', 'ymHair_MediumLong', 'ymHair_Fauxhawk',
           'ymHair_MediumPartedLeft'],
}
STYLE_LABELS = {
    'yfHair_PonyTailTight': 'Ponytail', 'yfHair_LongWavy': 'Long waves', 'yfHair_LongStraight': 'Long straight',
    'yfHair_ShortBob': 'Short bob', 'yfHair_UpdoBun': 'Bun', 'yfHair_MedWavySweptSoft': 'Soft waves',
    'yfHair_AfroMedium': 'Afro', 'yfHair_LongRocker': 'Long layers',
    'ymHair_ShortSpikey': 'Short spiky', 'ymHair_MediumCurly': 'Curly', 'ymHair_MediumLong': 'Medium long',
    'ymHair_Fauxhawk': 'Fauxhawk', 'ymHair_DreamyCrew': 'Crew cut', 'ymHair_MediumPartedLeft': 'Side part',
}
# the colour dots, in this order; each tries the game's names in turn (styles name some colours differently)
COLOURS = [
    ('Black', '#1d1a1c', ['Black', 'NeutralBlack']),
    ('DarkBrown', '#3b2619', ['DarkBrown', 'WarmBrown']),
    ('Brown', '#6a4127', ['Brown', 'WarmBrown', 'DarkBrown']),
    ('LightBrown', '#94693f', ['LightBrown', 'DirtyBlonde']),
    ('Blonde', '#d2ad6a', ['Blonde', 'NeutralBlonde', 'DirtyBlonde']),
    ('Auburn', '#8a3b1f', ['Auburn']),
    ('Red', '#b8401f', ['Red', 'Orange', 'Auburn']),
    ('Platinum', '#e8dcc0', ['Platinum', 'LightBlonde', 'WhiteBlonde']),
]
DEFAULT_STYLE = {'yf': 'yfHair_PonyTailTight', 'ym': 'ymHair_DreamyCrew', 'yf_futa': 'yfHair_ShortBob'}
DEFAULT_COLOUR = {'yf': 'Brown', 'ym': 'DarkBrown', 'yf_futa': 'Blonde'}      # reads well on the dark stage

_lock = threading.Lock()
_mem = {}                  # casp instance -> result (this process)
_shaped = OrderedDict()    # (casp instance, tray id, sim index) -> result shaped to that sim (the last SHAPED_KEEP)
SHAPED_KEEP = 24
_geom_mem = OrderedDict()  # casp instance -> (the chosen GEOMs, how they were chosen) (the last 32)
PLACEHOLDER_SIZE = 0.02    # a GEOM smaller than 2 cm is a stand-in: the hair is painted on the scalp in the game
_pkg_tex = {}              # package path -> {(type, inst): entry}


def _to_int(v):
    if isinstance(v, int):
        return v
    s = str(v).strip().lower()
    return int(s, 16) if s.startswith('0x') else int(s)


def _blocked(name):
    try:
        import gamedata
        return bool(gamedata._BLOCK_WORDS.search(name.replace('_', ' ').replace('-', ' ')))
    except Exception:
        return False


def presets():
    """Every preset style x colour that exists in the game, adult names only, in the order of PRESETS / COLOURS."""
    import casptex
    names = casptex.casp_by_name()
    out = []
    for frame, styles in PRESETS.items():
        for style in styles:
            for colour, swatch, tries in COLOURS:
                name = next((style + '_' + c for c in tries if (style + '_' + c) in names), None)
                if not name or _blocked(name) or any(p['name'] == name for p in out):
                    continue
                out.append({'name': name, 'style': style, 'colour': colour, 'frame': frame,
                            'label': STYLE_LABELS.get(style, style.split('_', 1)[-1]), 'swatch': swatch})
    return out


def default_for(frame, items=None):
    """{'name': ...} of the default preset for a body ('yf' brown ponytail, 'ym' dark brown crew cut, futa blonde
    short bob; the style's first colour when that one is missing) or None."""
    style = DEFAULT_STYLE.get(frame)
    mine = [p for p in (items if items is not None else presets()) if p['style'] == style]
    hit = next((p for p in mine if p['colour'] == DEFAULT_COLOUR.get(frame)), None) or (mine[0] if mine else None)
    return {'name': hit['name']} if hit else None


def hair_for_name(name, shape=None):
    import casptex
    if not re.match(r'^[ya][fm]Hair_', name or '') or _blocked(name):
        raise ValueError('Only the adult hair presets can be asked for by name.')
    inst = casptex.casp_by_name().get(name)
    if inst is None:
        return {'casp': None, 'name': name, 'origin': None, 'meshes': [], 'texture': None}
    return hair_mesh(inst, shape)


# ------------------------------------------------------------------ the mesh
def _geoms(inst, casp=None, origin=None):
    """The hair mesh the game shows without a hat: one GEOM of the CAS part's LOD 0.

    A hair's LOD 0 lists three GEOMs of one instance (three groups): the hair itself and two versions cut off at a
    hat's line, so a hat can cover the top. The cut ones can have more vertices than the hair (a denser cut edge), so
    the hair is the one that reaches highest (its top within 5 mm: then the one with more vertices). A GEOM under
    PLACEHOLDER_SIZE is a stand-in (shaved styles are painted on the scalp): no mesh. -> [read_geom() dict] or []."""
    import morph, casptex
    inst = _to_int(inst)
    with _lock:
        if inst in _geom_mem:
            _geom_mem.move_to_end(inst)
            return _geom_mem[inst][0]
    if casp is None:
        d = morph.PART_INDEX.read(T_CASP, inst)
        casp = casptex.parse_casp(d) if d else {}
    if origin is None:
        origin = morph.PART_INDEX.origin(T_CASP, inst)
    keys = casp.get('geoms') or [tgi for _, tgi in casp.get('all_geoms') or []]
    found, seen = [], set()
    for t, g, i in keys:
        if (t, g, i) in seen:
            continue
        seen.add((t, g, i))
        raw = (morph.PART_INDEX.read(t, i, g, origin) if origin else None) or morph.PART_INDEX.read(t, i, g)
        if raw is None:
            continue
        try:
            gm = morph.read_geom(raw)
        except Exception:
            continue
        n = int(gm.get('n', 0))
        pos = np.asarray(gm.get('positions'), np.float64).reshape(-1, 3) if n else np.zeros((0, 3))
        if n < 16 or float(np.linalg.norm(pos.max(0) - pos.min(0))) < PLACEHOLDER_SIZE:
            continue
        found.append((float(np.percentile(pos[:, 1], 99.5)), n, g, gm))
    pick = []
    how = 'placeholder' if seen else 'none'
    if found:
        tallest = max(f[0] for f in found)
        best = max((f for f in found if f[0] >= tallest - 0.005), key=lambda f: f[1])
        pick = [best[3]]
        how = 'group 0x%08x of %d (top %.3f, %d vertices)' % (best[2], len(found), best[0], best[1])
    with _lock:
        _geom_mem[inst] = (pick, how)
        while len(_geom_mem) > 32:
            _geom_mem.popitem(last=False)
    return pick


def _geom_choice(inst):
    with _lock:
        hit = _geom_mem.get(_to_int(inst))
    return hit[1] if hit else None


def _mesh_json(g, rig_index, head):
    n = int(g['n'])
    pos = np.asarray(g['positions'], np.float64).reshape(-1, 3)
    nrm = np.asarray(g['normals'], np.float64).reshape(-1, 3) if g.get('normals') is not None else np.zeros_like(pos)
    uvs = g['uvsets'][0] if g.get('uvsets') else np.zeros((n, 2), np.float32)
    faces = np.asarray(g['faces'], np.int64)
    hashes = g.get('bone_hashes') or []
    remap = np.array([rig_index.get(h, head) for h in hashes] + [head], np.int64)
    if g.get('bones') is not None:
        b = np.asarray(g['bones'], np.int64).reshape(-1, 4)
        b = remap[np.clip(b, 0, len(remap) - 1)]
        w = np.asarray(g['weights'], np.float64).reshape(-1, 4)
    else:                                                     # no skinning at all: the head carries it
        b = np.full((n, 4), head, np.int64)
        w = np.zeros((n, 4)); w[:, 0] = 1
    s = w.sum(1, keepdims=True)
    none = s[:, 0] < 1e-6
    w = np.where(s > 1e-6, w / np.maximum(s, 1e-6), 0)
    if none.any():                                            # a vertex with no weight: the head carries it
        b[none] = head; w[none] = 0; w[none, 0] = 1
    ok = (faces >= 0) & (faces < n)
    if not ok.all():
        faces = faces[:len(faces) // 3 * 3].reshape(-1, 3)
        faces = faces[(faces >= 0).all(1) & (faces < n).all(1)].ravel()
    return {'positions': np.round(pos, 5).ravel().tolist(), 'normals': np.round(nrm, 4).ravel().tolist(),
            'uvs': np.round(np.asarray(uvs, np.float64), 5).ravel().tolist(), 'faces': faces.astype(int).tolist(),
            'bones': b.ravel().astype(int).tolist(), 'weights': np.round(w, 4).ravel().tolist()}


def _pkg_index(path):
    import casptex
    from dbpf import read_index
    idx = _pkg_tex.get(path)
    if idx is None:
        idx = {}
        try:
            for e in read_index(path):
                if e['type'] in casptex.TEX_TYPES and e['size'] > 0:
                    idx.setdefault((e['type'], e['inst']), e)
        except Exception:
            pass
        _pkg_tex[path] = idx
    return idx


def _texture_bytes(tgi, pkg_path):
    """The diffuse image bytes: 1) the CAS part's own package 2) the game's index (every pack) 3) the packages next to
    the CAS part 4) the base-game texture index."""
    import casptex, objmesh
    from dbpf import read_resource
    t0, g0, inst = tgi
    order = [t0] + [t for t in casptex.TEX_TYPES if t != t0]
    if pkg_path:
        idx = _pkg_index(pkg_path)
        for t in order:
            e = idx.get((t, inst))
            if e:
                return read_resource(pkg_path, e)
    for t in order:
        try:
            d = objmesh._Index.read(t, None, inst)
        except Exception:
            d = None
        if d:
            return d
    if pkg_path:
        folder = os.path.dirname(pkg_path)
        try:
            near = [os.path.join(folder, f) for f in sorted(os.listdir(folder)) if f.lower().endswith('.package')][:40]
        except OSError:
            near = []
        for p in near:
            if p == pkg_path:
                continue
            idx = _pkg_index(p)
            for t in order:
                e = idx.get((t, inst))
                if e:
                    return read_resource(p, e)
    try:
        _, d = casptex.Resources.read_texture(inst)
        return d
    except Exception:
        return None


def _write_png(img, path, max_w=1024):
    from PIL import Image
    im = Image.fromarray(np.ascontiguousarray(img), 'RGBA')
    if im.width > max_w:
        im = im.resize((max_w, max(1, round(im.height * max_w / im.width))), Image.BOX)
    tmp = path + '.tmp'
    im.save(tmp, 'PNG', compress_level=3)
    os.replace(tmp, path)


def _rig_ids():
    import gamedata
    rig = gamedata.rig('au')
    rig_index = {b['hash']: k for k, b in enumerate(rig['bones'])}
    head = next(k for k, b in enumerate(rig['bones']) if b['name'] == 'b__Head__')
    return rig_index, head


def hair_mesh(casp_inst, shape=None):
    """A hair CAS part as preview meshes + a texture file name (see the module doc). The plain hair is cached on disk
    and in memory; a hair shaped to a sim (shape = its sim_body_spec) only in memory (the last SHAPED_KEEP)."""
    base = _hair_base(casp_inst)
    if not shape or not base.get('meshes'):
        return base
    inst = _to_int(casp_inst)
    key = (inst, str(shape.get('tray_id')), int(shape.get('sim_index') or 0))
    with _lock:
        if key in _shaped:
            _shaped.move_to_end(key)
            return _shaped[key]
    out = dict(base, meshes=_shaped_meshes(inst, shape), shaped_for=shape.get('name') or '')
    with _lock:
        _shaped[key] = out
        while len(_shaped) > SHAPED_KEEP:
            _shaped.popitem(last=False)
    return out


def _shaped_meshes(inst, spec):
    """The hair's GEOM deformed by one sim's body shape: the same ops, in the same order, on a fresh bind-pose rig, as
    morph.morph_body() runs on that sim's body - so the hair sits where the game puts it on that head."""
    import morph
    t0 = time.time()
    rig_index, head = _rig_ids()
    prefix = spec.get('prefix') or 'yf'
    ops, _ = morph.resolve_morphs(spec, prefix)
    out = []
    for g in _geoms(inst, None, None):
        if int(g.get('n', 0)) <= 0:
            continue
        r = morph.apply_modifiers(g, spec, prefix, ops=ops)
        g2 = dict(g, positions=np.asarray(r['positions'], np.float64).reshape(-1, 3),
                  normals=np.asarray(r['normals'], np.float64).reshape(-1, 3))
        m = _mesh_json(g2, rig_index, head)
        m['stats'] = dict(r['stats'], seconds=round(time.time() - t0, 3))
        out.append(m)
    return out


def _hair_base(casp_inst):
    import morph, casptex, texfmt
    inst = _to_int(casp_inst)
    with _lock:
        if inst in _mem:
            return _mem[inst]
    os.makedirs(CACHE, exist_ok=True)
    jpath = os.path.join(CACHE, '%016x_v%d.json' % (inst, VERSION))
    if os.path.isfile(jpath):
        try:
            with open(jpath, encoding='utf-8') as f:
                out = json.load(f)
            if not out.get('texture') or os.path.isfile(os.path.join(CACHE, out['texture'])):
                with _lock:
                    _mem[inst] = out
                return out
        except Exception:
            pass
    t0 = time.time()
    row = morph.PART_INDEX.find(T_CASP, inst)
    missing = {'casp': '0x%016x' % inst, 'name': None, 'origin': None, 'meshes': [], 'texture': None}
    if row is None:
        return missing                                  # not installed: no hair, no error (not cached: it may come)
    origin = 'cc' if int(row['pkg']) < morph.PART_INDEX.n_cc else 'game'
    pkg_path = morph.PART_INDEX.paths[int(row['pkg'])]
    d = morph.PART_INDEX.read(T_CASP, inst)
    casp = casptex.parse_casp(d)
    if not (casp.get('age_gender', 0) & ADULT_FLAGS):
        raise ValueError('That CAS part is not for adults.')
    if casp.get('body_type') not in (2,):             # hair only
        raise ValueError('That CAS part is not hair.')
    rig_index, head = _rig_ids()
    geoms = _geoms(inst, casp, origin)
    meshes = [_mesh_json(g, rig_index, head) for g in geoms if int(g.get('n', 0)) > 0]
    out = {'casp': '0x%016x' % inst, 'name': casp.get('name'), 'origin': origin, 'meshes': meshes, 'texture': None,
           'mesh': _geom_choice(inst),
           'unknown_bones': sorted({'0x%08x' % h for g in geoms for h in (g.get('bone_hashes') or []) if h not in rig_index})}
    if not meshes:
        # a stand-in GEOM only (shaved styles): the game paints this hair on the scalp - nothing to show as a mesh
        out['painted'] = _geom_choice(inst) == 'placeholder'
        out['seconds'] = round(time.time() - t0, 3)
        with _lock:
            _mem[inst] = out
        return out
    tgi = (casp.get('textures') or {}).get('diffuse')
    if tgi:
        try:
            raw = _texture_bytes(tgi, pkg_path)
            if raw:
                img = texfmt.decode(raw)
                name = 'hair_%016x_v%d.png' % (inst, VERSION)
                _write_png(img, os.path.join(CACHE, name))
                out['texture'] = name
        except Exception as ex:
            out['texture_error'] = str(ex)
    out['seconds'] = round(time.time() - t0, 3)
    tmp = jpath + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(out, f, separators=(',', ':'))
    os.replace(tmp, jpath)
    with _lock:
        _mem[inst] = out
    return out


def tray_spec(tray_id, index):
    """trayfmt.sim_body_spec() of an adult human Tray sim (anyone else is refused)."""
    import trayfmt
    spec = trayfmt.sim_body_spec(tray_id, int(index))
    if spec.get('age') not in ('youngadult', 'adult', 'elder') or spec.get('species', 'human') != 'human':
        raise ValueError('Only adult sims can be used.')
    return spec


def tray_hair(tray_id, index, spec=None):
    """The hair a Tray sim wears ({'casp', 'name', 'origin'}), or None. Adults only."""
    spec = spec or tray_spec(tray_id, index)
    hp = spec.get('hair_part')
    if not hp:
        return None
    return {'casp': hp.get('casp_instance'), 'name': hp.get('name'), 'origin': hp.get('origin')}


def texture_path(name):
    """The PNG a hair texture was written to, or None (the name must be one this module wrote)."""
    base = os.path.basename(name or '')
    if not re.match(r'^hair_[0-9a-f]{16}_v\d+\.png$', base):
        return None
    p = os.path.join(CACHE, base)
    return p if os.path.isfile(p) else None
