"""Other bodies and hair (R2-3), read-only on the game and Mods folders.

    GET /api/body_variant?frame=ym&length=&girth=&balls=&apart=&tilt=
          WickedWhims' genital sliders (-1..1 each) on a body: {frame, body: {frame, rig, meshes, ww, rest_delta}}
    GET /api/body_variant?tray=<id>&index=<i>[&length=...]
          an adult Tray sim's own body (like /api/tray_sim) plus rest_delta and its hair: {frame, name, tone, hair, body}
    GET /api/hair?casp=0x... | ?name=yfHair_... [&shape_tray=<id>&shape_index=<i>] | ?tray=<id>&index=<i>
          {casp, name, origin, meshes: [{positions, normals, uvs, faces, bones, weights}], texture}
          (origin null and no meshes: the hair isn't installed - no error). tray= is that sim's own hair on that
          sim's body shape; shape_tray= puts any hair on a Tray sim's body shape (sliders that move the head move the
          hair too - see hair.hair_mesh).
    GET /api/hair_tex?file=hair_<inst>_v1.png     the hair's diffuse texture (only files hair.py wrote)
    GET /api/hair_presets                         [{name, style, colour, frame, label, swatch}] + defaults

Adults only: Tray sims must be young adults, adults or elders (humans); preset names start with yf / ym; a hair CAS
part without an adult age flag is refused.
"""
import threading
from collections import OrderedDict

import gamedata as G

ADULT_AGES = ('youngadult', 'adult', 'elder')
_variants = OrderedDict()             # query key -> answer (at most 12 kept)
_vlock = threading.Lock()


def _vals(q):
    import morph
    out = {}
    for k in morph.WW_GENITAL:
        v = q.get(k)
        if v in (None, ''):
            continue
        try:
            f = max(-1.0, min(1.0, float(v)))
        except ValueError:
            raise ValueError('%s must be a number from -1 to 1' % k)
        if f:
            out[k] = round(f, 3)
    return out


def _mesh_out(m, mm):
    pos, nrm = mm.get('positions'), mm.get('normals')
    return dict(m, positions=[round(float(c), 5) for c in (pos if pos is not None else m['positions'])],
                normals=[round(float(c), 4) for c in (nrm if nrm is not None else m['normals'])])


def _tray_spec(q):
    import trayfmt
    spec = trayfmt.sim_body_spec(q['tray'], int(q.get('index', 0)))
    if spec.get('age') not in ADULT_AGES or spec.get('species', 'human') != 'human':
        raise ValueError('Only adult sims can be used.')
    return spec


def _body_variant(q):
    import morph
    vals = _vals(q)
    tray = q.get('tray')
    key = (tray, q.get('index') if tray else None, q.get('frame') if not tray else None, tuple(sorted(vals.items())))
    with _vlock:
        if key in _variants:
            _variants.move_to_end(key)
            return _variants[key]
    out = {}
    if tray:
        spec = _tray_spec(q)
        frame = spec.get('frame') if spec.get('frame') in ('yf', 'ym') else ('ym' if spec.get('gender') == 'male' else 'yf')
        tone = spec.get('tone_inst')
        hp = spec.get('hair_part') or {}
        out.update({'name': spec.get('name') or '', 'gender': spec.get('gender'), 'age': spec.get('age'),
                    'tone': ('%016x' % int(tone, 16) if isinstance(tone, str) else '%016x' % tone) if tone else '',
                    'hair': {'casp': hp.get('casp_instance'), 'name': hp.get('name'), 'origin': hp.get('origin')} if hp else None})
    else:
        frame = q.get('frame', 'ym')
        if frame not in G.BODIES:
            raise LookupError('unknown body')
        spec = {}
    body = G.body(frame)
    if not spec and not vals:
        variant = dict(body, rest_delta={}, morph={})
    else:
        variant = morph.body_variant(body, spec, vals, spec.get('prefix') if spec else None)
    meshes = [_mesh_out(m, mm) for m, mm in zip(body['meshes'], variant['meshes'])]
    out.update({'frame': frame, 'values': vals,
                'body': {'frame': frame, 'rig': body['rig'], 'meshes': meshes, 'ww': body.get('ww'),
                         'rest_delta': variant.get('rest_delta') or {}}})
    with _vlock:
        _variants[key] = out
        while len(_variants) > 12:
            _variants.popitem(last=False)
    return out


def _hair(q):
    import hair
    if q.get('tray'):
        spec = hair.tray_spec(q['tray'], q.get('index', 0))
        info = hair.tray_hair(q['tray'], q.get('index', 0), spec)
        if not info or not info.get('casp'):
            return {'casp': None, 'name': None, 'origin': None, 'meshes': [], 'texture': None}
        if info.get('origin') is None:
            return {'casp': info['casp'], 'name': info.get('name'), 'origin': None, 'meshes': [], 'texture': None}
        return hair.hair_mesh(info['casp'], spec)
    shape = hair.tray_spec(q['shape_tray'], q.get('shape_index', 0)) if q.get('shape_tray') else None
    if q.get('name'):
        return hair.hair_for_name(q['name'], shape)
    if q.get('casp'):
        try:
            return hair.hair_mesh(q['casp'], shape)
        except (TypeError, ValueError) as ex:
            raise ValueError(str(ex) or 'bad CAS part')
    raise ValueError('Ask for a hair by casp=, name= or tray= and index=.')


def _hair_tex(q):
    import hair
    path = hair.texture_path(q.get('file'))
    if not path:
        raise LookupError('no texture')
    with open(path, 'rb') as f:
        return f.read(), 'image/png'


def _hair_presets(q):
    import hair
    items = hair.presets()
    defaults = {}
    for frame in hair.DEFAULT_STYLE:
        d = hair.default_for(frame, items)
        if d:
            defaults[frame] = d['name']
    return {'items': items, 'defaults': defaults}


def _warm_parts():
    """The CAS part index loads in the background, so the first hair on screen comes quickly."""
    import morph
    morph.PART_INDEX._load()


GET = {'body_variant': _body_variant, 'hair': _hair, 'hair_tex': _hair_tex, 'hair_presets': _hair_presets}
WARM = [_warm_parts]
