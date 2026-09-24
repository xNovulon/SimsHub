"""CAS part (CASP, 0x034AEECB) and skin tone (TONE, 0x0354796A) parsing for textures, plus a resource index
over the game's client packages and WickedWhims' tuning package (which, like the game, overrides by TGI).

Field layouts follow s4pi's CASPartResource/SkinToneResource and CmarNYC's TS4SimRipper (CASP versions up to 0x35).
"""
import os, struct, threading, pickle, glob

from dbpf import read_index, read_resource

T_CASP, T_TONE, T_GEOM = 0x034AEECB, 0x0354796A, 0x015A1849
T_DST, T_RLE2, T_RLES, T_LRLE, T_DDS_RAW, T_RMAP = 0x00B2D882, 0x3453CF95, 0xBA856C78, 0x2BC04EDF, 0xB6C8B6A0, 0xAC16FBEC
TEX_TYPES = (T_LRLE, T_RLE2, T_DST, T_RLES, T_DDS_RAW)
WANTED_TYPES = set(TEX_TYPES) | {T_CASP, T_TONE, T_GEOM, T_RMAP}

AGE = {0x1: 'baby', 0x2: 'toddler', 0x4: 'child', 0x8: 'teen', 0x10: 'young_adult', 0x20: 'adult', 0x40: 'elder',
       0x80: 'infant'}
GENDER = {0x1000: 'male', 0x2000: 'female'}
BODY_TYPES = {0: 'All', 1: 'Hat', 2: 'Hair', 3: 'Head', 4: 'Face', 5: 'Body', 6: 'Top', 7: 'Bottom', 8: 'Shoes',
              9: 'Accessories', 0x1C: 'FacialHair', 0x1D: 'Lipstick', 0x1E: 'Eyeshadow', 0x1F: 'Eyeliner', 0x20: 'Blush',
              0x21: 'Facepaint', 0x22: 'Eyebrows', 0x23: 'Eyecolor', 0x24: 'Socks', 0x25: 'Mascara', 0x26: 'ForeheadCrease',
              0x27: 'Freckles', 0x2A: 'Tights', 0x3A: 'SkinOverlay', 0x3B: 'FurBody', 0x3C: 'EarLeft', 0x3D: 'EarRight',
              0x3E: 'Tail', 0x44: 'Occult Eye/Teeth'}


def age_gender_names(flags):
    return [n for b, n in AGE.items() if flags & b] + [n for b, n in GENDER.items() if flags & b]


# ------------------------------------------------------------------ resource index
def _game_dir():
    import gamedata
    return gamedata.game_dir()


def _ww_package():
    try:
        import gamedata
        return gamedata.ww_tuning_package()
    except Exception:
        return None


class Resources:
    """(type, instance) -> [(package, entry), ...] for textures, CASPs, TONEs and GEOMs, highest priority first:
    WickedWhims' tuning package, then the game's delta builds, then its full builds. Empty (deleted) entries skipped."""
    _lock = threading.Lock()
    _idx = None
    _pkgs = None
    _ww = None

    @classmethod
    def packages(cls):
        d = os.path.join(_game_dir(), 'Data', 'Client')
        game = sorted(glob.glob(os.path.join(d, 'ClientDeltaBuild*.package'))) + \
            sorted(glob.glob(os.path.join(d, 'ClientFullBuild*.package')))
        ww = _ww_package()
        return ([ww] if ww else []) + game

    @classmethod
    def index(cls):
        with cls._lock:
            if cls._idx is None:
                pkgs = cls.packages()
                sig = [(p, os.path.getsize(p), int(os.path.getmtime(p))) for p in pkgs]
                cache = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'cache', 'tex', 'resindex.pickle')
                idx = None
                try:
                    with open(cache, 'rb') as f:
                        saved = pickle.load(f)
                    if saved['sig'] == sig:
                        idx = saved['idx']
                except Exception:
                    idx = None
                if idx is None:
                    idx = {}
                    for pi, p in enumerate(pkgs):
                        for e in read_index(p):
                            if e['type'] in WANTED_TYPES and e['size'] > 0:
                                idx.setdefault((e['type'], e['inst']), []).append(
                                    (pi, e['group'], e['pos'], e['size'], e['mem'], e['comp']))
                    os.makedirs(os.path.dirname(cache), exist_ok=True)
                    with open(cache + '.tmp', 'wb') as f:
                        pickle.dump({'sig': sig, 'idx': idx}, f, protocol=4)
                    os.replace(cache + '.tmp', cache)
                cls._idx, cls._pkgs = idx, pkgs
                ww = _ww_package()
                cls._ww = pkgs.index(ww) if ww in pkgs else None
            return cls._idx

    @classmethod
    def _hits(cls, t, inst, group=None, ww=True):
        hits = cls.index().get((t, inst)) or []
        if not ww and cls._ww is not None:
            hits = [h for h in hits if h[0] != cls._ww]
        if group is not None and hits:
            exact = [h for h in hits if h[1] == group]
            hits = exact or hits
        return hits

    @classmethod
    def _entry(cls, t, inst, h):
        pi, g, pos, size, mem, comp = h
        return cls._pkgs[pi], {'type': t, 'group': g, 'inst': inst, 'pos': pos, 'size': size, 'mem': mem, 'comp': comp}

    @classmethod
    def find(cls, t, inst, group=None, ww=True):
        """Best (package path, entry dict) for a type + instance, or None. ww=False ignores WickedWhims' package."""
        hits = cls._hits(t, inst, group, ww)
        return cls._entry(t, inst, hits[0]) if hits else None

    @classmethod
    def read(cls, t, inst, group=None, ww=True):
        hit = cls.find(t, inst, group, ww)
        return read_resource(*hit) if hit else None

    @classmethod
    def source(cls, t, inst, group=None, ww=True):
        """File name of the package a resource comes from (for cache keys / reports)."""
        hit = cls.find(t, inst, group, ww)
        return os.path.basename(hit[0]) if hit else None

    @classmethod
    def instances(cls, t):
        return [i for (tt, i) in cls.index() if tt == t]

    @classmethod
    def texture_entry(cls, inst, ww=True):
        """(type, package path, entry) of the image a texture instance resolves to, or None.
        CASPs name a key of one image type (usually RLE2 0x3453CF95 or DST 0x00B2D882) but the game's newer delta
        builds often ship the same instance as another type (LRLE) - e.g. the heads' old baked RLE2 preview textures
        are superseded by empty LRLEs. So: highest-priority package first (WickedWhims, delta, full), then
        LRLE > RLE2 > DST > RLES > raw DDS, like TS4SimRipper."""
        best = None
        for rank, t in enumerate(TEX_TYPES):
            for h in cls._hits(t, inst, None, ww):
                key = (h[0], rank)
                if best is None or key < best[0]:
                    best = (key, t, h)
                break
        if best is None:
            return None
        _, t, h = best
        path, e = cls._entry(t, inst, h)
        return t, path, e

    @classmethod
    def read_texture(cls, inst, prefer=None, ww=True):
        """Texture bytes for an instance, whatever image type it is: (type, bytes) or (None, None).
        prefer: read this type if it exists at all (skips the package-priority choice)."""
        if prefer is not None:
            d = cls.read(prefer, inst, ww=ww)
            if d and len(d) > 16:
                return prefer, d
        hit = cls.texture_entry(inst, ww)
        if not hit:
            return None, None
        t, path, e = hit
        return t, read_resource(path, e)


# ------------------------------------------------------------------ CASP
class _R:
    def __init__(self, d, p=0):
        self.d, self.p = d, p

    def u8(self):
        v = self.d[self.p]; self.p += 1; return v

    def u16(self):
        v = struct.unpack_from('<H', self.d, self.p)[0]; self.p += 2; return v

    def i16(self):
        v = struct.unpack_from('<h', self.d, self.p)[0]; self.p += 2; return v

    def u32(self):
        v = struct.unpack_from('<I', self.d, self.p)[0]; self.p += 4; return v

    def i32(self):
        v = struct.unpack_from('<i', self.d, self.p)[0]; self.p += 4; return v

    def u64(self):
        v = struct.unpack_from('<Q', self.d, self.p)[0]; self.p += 8; return v

    def f32(self):
        v = struct.unpack_from('<f', self.d, self.p)[0]; self.p += 4; return v

    def raw(self, n):
        v = self.d[self.p:self.p + n]; self.p += n; return v

    def str7_utf16be(self):
        n, shift = 0, 0
        while True:
            b = self.u8(); n |= (b & 0x7F) << shift; shift += 7
            if not b & 0x80:
                break
        return self.raw(n).decode('utf-16-be', 'replace')


def casp_name(d):
    return _R(d, 12).str7_utf16be()


def parse_casp(d):
    """CASP bytes -> dict (name, version, body_type, age_gender, composition, sort_layer, textures, tgis, ...).
    textures: {'diffuse', 'shadow', 'region_map', 'normal', 'specular', 'emission'} -> (type, group, instance) or None."""
    r = _R(d)
    version = r.u32()
    tgi_off = r.u32() + 8
    preset_count = r.u32()
    name = r.str7_utf16be()
    out = {'version': version, 'name': name}
    out['sort_priority'] = r.f32()
    out['swatch_order'] = r.u16()
    out['outfit_id'] = r.u32()
    out['material_hash'] = r.u32()
    out['param_flags'] = r.u8()
    if version >= 39:
        out['param_flags2'] = r.u8()
    if version >= 50:
        out['layer_id'] = r.u16()
    if version >= 51:
        n = r.u32()
        out['exclude_part_flags'] = [r.u64() for _ in range(n)]
    else:
        out['exclude_part_flags'] = [r.u64()]
        if version >= 41:
            out['exclude_part_flags'].append(r.u64())
    out['exclude_modifier_region_flags'] = r.u64() if version >= 37 else r.u32()
    ntags = r.u32()
    tags = []
    for _ in range(ntags):
        cat = r.u16()
        val = r.u32() if version >= 37 else r.u16()
        tags.append((cat, val))
    out['tags'] = tags
    out['price'] = r.u32()
    out['title_key'] = r.u32()
    out['desc_key'] = r.u32()
    if version >= 43:
        out['create_desc_key'] = r.u32()
    out['texture_space'] = r.u8()
    out['body_type'] = r.u32()
    out['body_type_name'] = BODY_TYPES.get(out['body_type'], str(out['body_type']))
    out['body_subtype'] = r.u32()
    out['age_gender'] = r.u32()
    out['ages_genders'] = age_gender_names(out['age_gender'])
    out['species'] = r.u32() if version >= 32 else 1
    if version >= 34:
        out['pack_id'] = r.u16(); out['pack_flags'] = r.u8(); r.raw(9)
    else:
        u2 = r.u8()
        if u2:
            r.u8()
    ncol = r.u8()
    out['swatch_colors'] = ['#%06X' % (r.u32() & 0xFFFFFF) for _ in range(ncol)]
    out['buff_key'] = r.u8()
    out['variant_thumb_key'] = r.u8()
    if version >= 28:
        out['voice_effect'] = r.u64()
    if version >= 30:
        n = r.u8()
        if n:
            out['material_sets'] = (r.u32(), r.u32(), r.u32())
    if version >= 31:
        out['hide_for_occult'] = r.u32()
    if version >= 46:
        out['unknown46'] = r.u64()
    if version >= 38:
        out['opposite_gender_part'] = r.u64()
    if version >= 39:
        out['fallback_part'] = r.u64()
    if version >= 44:
        out['opacity_slider'] = (r.f32(), r.f32())
        out['hue_slider'] = (r.f32(), r.f32(), r.f32())
        out['saturation_slider'] = (r.f32(), r.f32(), r.f32())
        out['brightness_slider'] = (r.f32(), r.f32(), r.f32())
    if version >= 46:
        n = r.u8(); r.raw(n)
    out['naked_key'] = r.u8()
    out['parent_key'] = r.u8()
    out['sort_layer'] = r.i32()
    lods = []
    for _ in range(r.u8()):
        lod = r.u8(); r.u32()
        assets = [(r.i32(), r.i32(), r.i32()) for _ in range(r.u8())]
        keys = list(r.raw(r.u8()))
        lods.append({'lod': lod, 'assets': assets, 'keys': keys})
    out['lods'] = lods
    out['slot_keys'] = list(r.raw(r.u8()))
    k_diffuse = r.u8()
    k_shadow = r.u8()
    out['composition'] = r.u8()
    k_region = r.u8()
    out['overrides'] = [(r.u8(), r.f32()) for _ in range(r.u8())]
    k_normal = r.u8()
    k_specular = r.u8()
    out['uv_override'] = r.u32() if version >= 27 else 0
    k_emission = r.u8() if version >= 29 else 0xFF
    # TGI list (instance, group, type)
    q = tgi_off
    cnt = d[q]; q += 1
    tgis = []
    for _ in range(cnt):
        inst, grp, typ = struct.unpack_from('<QII', d, q); q += 16
        tgis.append((typ, grp, inst))
    out['tgis'] = tgis

    def key(k):
        if k < len(tgis) and tgis[k][2]:
            return tgis[k]
        return None
    out['keys'] = {'diffuse': k_diffuse, 'shadow': k_shadow, 'region_map': k_region, 'normal': k_normal,
                   'specular': k_specular, 'emission': k_emission}
    out['textures'] = {n: key(k) for n, k in out['keys'].items()}
    out['geoms'] = [tgis[k] for l in lods if l['lod'] == 0 for k in l['keys'] if k < len(tgis) and tgis[k][0] == T_GEOM]
    out['all_geoms'] = [(l['lod'], tgis[k]) for l in lods for k in l['keys'] if k < len(tgis) and tgis[k][0] == T_GEOM]
    out['parsed_to'] = r.p
    out['tgi_offset'] = tgi_off
    return out


_casp_names = None
_casp_lock = threading.Lock()


def _scan_casp_names():
    """{name: instance}, reading only the head of each CASP (the name sits at byte 12). Package priority order."""
    import zlib
    from dbpf import refpack
    bypkg = {}
    for (t, inst), hits in Resources.index().items():
        if t == T_CASP:
            pi, g, pos, size, mem, comp = hits[0]
            bypkg.setdefault(pi, []).append((pos, size, comp, inst))
    names = {}
    for pi in sorted(bypkg):
        with open(Resources._pkgs[pi], 'rb') as f:
            for pos, size, comp, inst in sorted(bypkg[pi]):
                f.seek(pos)
                raw = f.read(size)
                try:
                    if comp == 0x5A42:
                        d = zlib.decompressobj().decompress(raw, 1024)
                    elif comp == 0xFFFF:
                        d = refpack(raw)
                    else:
                        d = raw
                    if len(d) > 16:
                        names.setdefault(casp_name(d), inst)
                except Exception:
                    pass
    return names


def casp_by_name():
    """{name: instance} for every CASP (WickedWhims' overrides win), cached."""
    global _casp_names
    with _casp_lock:
        if _casp_names is None:
            cache = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'cache', 'tex', 'caspnames.pickle')
            Resources.index()
            sig = [(p, os.path.getsize(p), int(os.path.getmtime(p))) for p in Resources._pkgs]
            names = None
            try:
                with open(cache, 'rb') as f:
                    saved = pickle.load(f)
                if saved['sig'] == sig:
                    names = saved['names']
            except Exception:
                pass
            if names is None:
                names = _scan_casp_names()
                with open(cache + '.tmp', 'wb') as f:
                    pickle.dump({'sig': sig, 'names': names}, f, protocol=4)
                os.replace(cache + '.tmp', cache)
            _casp_names = names
        return _casp_names


def load_casp(key, ww=True):
    """key: CASP instance (int) or name (str) -> parsed dict (with 'instance' and 'package'), or None.
    ww=False reads the game's own CASP even when WickedWhims overrides it (e.g. yfTop_Nude, yfBottom_Nude)."""
    if isinstance(key, dict):
        return key
    if isinstance(key, str):
        inst = casp_by_name().get(key)
        if inst is None:
            return None
    else:
        inst = key
    hit = Resources.find(T_CASP, inst, ww=ww)
    if not hit:
        return None
    d = read_resource(*hit)
    if not d or len(d) < 32:
        return None
    c = parse_casp(d)
    c['instance'] = inst
    c['package'] = os.path.basename(hit[0])
    return c


# ------------------------------------------------------------------ TONE
def parse_tone(d):
    """TONE bytes -> dict: skin_sets [{texture, overlay, overlay_multiplier, makeup_opacity, makeup_opacity2}],
    overlays [{age_gender, ages_genders, texture}], saturation, hue, pass2_opacity, tags, swatch_colors, sort_order,
    tuning, skin_type, slider (low, high, increment)."""
    r = _R(d)
    version = r.u32()
    out = {'version': version}
    sets = []
    if version >= 10:
        for _ in range(r.u8()):
            sets.append({'texture': r.u64(), 'overlay': r.u64(), 'overlay_multiplier': r.f32(),
                         'makeup_opacity': r.f32(), 'makeup_opacity2': r.f32()})
    else:
        sets.append({'texture': r.u64(), 'overlay': 0, 'overlay_multiplier': 1.0})
    overlays = []
    for _ in range(r.u32()):
        ag = r.u32()
        overlays.append({'age_gender': ag, 'ages_genders': age_gender_names(ag), 'texture': r.u64()})
    out['overlays'] = overlays
    out['saturation'] = r.u16()
    out['hue'] = r.u16()
    out['pass2_opacity'] = r.u32()
    tags = []
    for _ in range(r.u32()):
        cat = r.u16()
        tags.append((cat, r.u32() if version >= 7 else r.u16()))
    out['tags'] = tags
    if version < 10:
        mo = r.f32()
        sets[0]['makeup_opacity'] = mo
    out['swatch_colors'] = ['#%06X' % (r.u32() & 0xFFFFFF) for _ in range(r.u8())]
    out['sort_order'] = r.f32()
    if version < 10:
        sets[0]['makeup_opacity2'] = r.f32()
    if version >= 8:
        out['tuning'] = r.u64()
    if version > 10:
        out['skin_type'] = {1: 'warm', 2: 'neutral', 3: 'cool', 4: 'misc'}.get(r.u16(), 'other')
        out['slider'] = (r.f32(), r.f32(), r.f32())
    out['skin_sets'] = sets
    return out


def load_tone(inst):
    d = Resources.read(T_TONE, inst)
    if not d:
        return None
    t = parse_tone(d)
    t['instance'] = inst
    return t


def tone_overlay_for(tone, age_gender_flags):
    """The TONE's per age/gender overlay texture instance (0 if none). age_gender_flags e.g. 0x2030 = YA+adult female."""
    ages, gender = age_gender_flags & 0xFF, age_gender_flags & 0xF000
    for o in tone['overlays']:
        if (o['age_gender'] & ages) and (o['age_gender'] & gender):
            return o['texture']
    return 0


def list_tones():
    """Every skin tone in the game: [{instance, version, hue, saturation, pass2_opacity, swatch, sort_order, skin_type,
    texture}], sorted like the CAS panel (skin type, then sort order)."""
    out = []
    for inst in Resources.instances(T_TONE):
        try:
            t = load_tone(inst)
        except Exception:
            continue
        if not t:
            continue
        out.append({'instance': inst, 'hex': '%016X' % inst, 'version': t['version'], 'hue': t['hue'],
                    'saturation': t['saturation'], 'pass2_opacity': t['pass2_opacity'],
                    'swatch': t['swatch_colors'][0] if t['swatch_colors'] else None, 'sort_order': t['sort_order'],
                    'skin_type': t.get('skin_type'), 'texture': '%016X' % t['skin_sets'][0]['texture'],
                    'overlays': len(t['overlays']), 'tags': t['tags']})
    order = {'warm': 0, 'neutral': 1, 'cool': 2, 'misc': 3}
    out.sort(key=lambda x: (order.get(x['skin_type'], 4), x['sort_order']))
    return out
