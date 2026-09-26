"""The sim's composited body texture atlas (what the game builds at run time for the SimSkin shader).

Layout: one 1:2 atlas (the game's is 1024x2048) shared by every body GEOM through UV channel 0, with v measured
from the TOP of the image (row = v * height; DirectX convention) - head island v 0.25-0.50 (eyeballs at
u 0.00-0.10, v 0.251-0.302), torso/arms v 0.50-0.78, legs/bottom v 0.66-0.90, feet v 0.90-0.99; WickedWhims'
genitals use the lower-right quarter. CAS diffuse textures are full-atlas images (WickedWhims ships 2048x4096 ones:
scaled down); normal maps are partial (body quarter only) and speculars half size - neither is composited here.

Compositing (after TS4SimRipper's SkinBlender "37", with the detail alpha fix described below):
  1. details  = the game's grey skin-detail map for the age/gender (hard-coded instances, neutral physique)
                + its detail overlay (alpha over). WickedWhims replaces the young-adult female overlay (breasts).
  2. details += every CAS part with composition method 3 ("grey shading": WW nipples, penis) - alpha over.
     Where the details are transparent (the face: its features live in the skin tone texture) they count as
     the neutral grey DETAIL_NEUTRAL, so the face blends seamlessly into the head.
  3. skin     = the TONE's skin-set-0 colour texture, blended per channel with the details:
                soft light (x1.2), then overlay mixed in by the tone's pass-2 opacity, then a soft-light
                colourise with the tone's hue/saturation, then a slight contrast curve.
  4. + the TONE's overlay texture for the age/gender (alpha over; only children have one in the base game).
  5. + the other CAS parts, sorted by composition method (descending) then sort layer: shadow map first
       (as a black, half-strength shadow), then the diffuse, alpha over (makeup methods 2/4 scaled by the
       tone's makeup opacities). E.g. WickedWhims' female bottom (vulva colour), the eye colour, eyebrows.
  6. transparent texels are filled with the average skin colour so bilinear filtering / mip-mapping on the mesh
     never pulls in black.

Skin tones (tone_source / resolve_tone / skin_for): the base game's tones (and WickedWhims') come from Resources as
before. Tray sims often wear a custom-content (CC) tone from Mods / Mods_parked, or a pack's tone (EP/GP/SP builds,
which Resources does not index): those are found through morph.MORPH_INDEX (TONE is one of its types; it covers Mods,
Mods_parked and every pack, cached on disk, loaded lazily) and their textures are read from the tone's own package
first. A tone that is not installed at all, or can't be read, gets a stand-in: the nearest base-game tone by its
swatch colour (or hue/saturation) when the TONE is there, else DEFAULT_TONE. skin_for() never raises.
"""
import os, re, json, hashlib, threading, time, traceback
import numpy as np
from PIL import Image

import texfmt
import casptex
from casptex import Resources, load_casp, load_tone, parse_tone, T_GEOM, T_TONE, TEX_TYPES

HERE = os.path.dirname(os.path.abspath(__file__))
TEX_CACHE = os.path.normpath(os.path.join(HERE, '..', 'cache', 'tex'))
CACHE_VERSION = 3

# ------------------------------------------------------------------ constants
AGE_BITS = {'b': 0x1, 'p': 0x2, 'c': 0x4, 't': 0x8, 'y': 0x10, 'a': 0x20, 'e': 0x40, 'i': 0x80}
GENDER_BITS = {'m': 0x1000, 'f': 0x2000}

# skin-detail maps: (age bit, gender bit) -> (neutral physique map, overlay) instances (TS4SimRipper's table;
# the game code picks them, no resource links them). Stored as LRLE in the delta builds, RLE2 in the old full builds.
DETAILS = {
    (0x08, 0x1000): (0x48F11375333EDB51, 0xA062AF087257C3AA),
    (0x10, 0x1000): (0x58F8275474E1AE00, 0xA3EC609A2DAB31D3),
    (0x20, 0x1000): (0x308855B3BFF0E848, 0x265B16FA4E7DA19B),
    (0x40, 0x1000): (0x24DFF8E30DC7E5DC, 0x25EBBD9BED791D4F),
    (0x08, 0x2000): (0x737A5FF0EB729888, 0xF85FB112905485DB),
    (0x10, 0x2000): (0x36C865290B1F4E79, 0x0A136CA1147B1772),
    (0x20, 0x2000): (0x59093C1074E2C911, 0x53F13B3669333A6A),
    (0x40, 0x2000): (0x2356ABE32AC4C255, 0x1E1930AE6138725E),
    (0x04, 0x1000): (0x9CB2C5C93E357C62, 0),
    (0x04, 0x2000): (0x9CB2C5C93E357C62, 0),
    (0x02, 0x1000): (0xD19E353A4001EC4D, 0),
    (0x02, 0x2000): (0xD19E353A4001EC4D, 0),
}
DETAIL_NEUTRAL = 0.75      # grey level of the detail maps around the face (the face itself is transparent)

DEFAULT_TONE = 0x3840      # a light warm tone (swatch #FFD3AF)
EYE_UV_RECT = (0.0, 0.2505, 0.1035, 0.3018)   # (u0, v0, u1, v1): both eyeballs of the head GEOM map here
EYE_COLORS = ['Amber', 'Aqua', 'Black', 'Blue', 'Brown', 'DarkBlue', 'DarkBrown', 'Gray', 'Green', 'HazelBlue',
              'HazelBlueDark', 'HazelGrayBrown', 'HazelGreen', 'HazelOliveGreen', 'LightBlue', 'LightBrown',
              'LightGreen', 'Purple']

# default nude parts per body frame when gamedata.BODIES is not usable: [(role, [names, first found wins])]
_FALLBACK_PARTS = {
    'yf': [('top', ['yfTop_Nude']), ('bottom', ['TURBODRIVER_NudeBottom_AF_201604300033066128', 'yfBottom_Nude']),
           ('feet', ['yfShoes_Nude']), ('head', ['yfHead'])],
    'ym': [('top', ['TURBODRIVER_Nude_Top_Male', 'ymTop_Nude']),
           ('penis_soft', ['TURBODRIVER_Penis_Soft_Male', 'ymBottom_Nude']),
           ('feet', ['ymShoes_Nude']), ('head', ['ymHead'])],
    'yf_futa': [('top', ['yfTop_Nude']), ('penis_soft', ['TURBODRIVER_Penis_Soft_Female', 'yfBottom_Nude']),
                ('feet', ['yfShoes_Nude']), ('head', ['yfHead'])],
}
# roles never composited (identical texture to another role, or their own material)
_SKIP_ROLES = {'penis_hard'}


def frame_flags(frame):
    """'yf' -> (age bit, gender bit). Frames: [t|y|a|e|c|p][f|m] (+ suffix like '_futa')."""
    f = frame.lower()
    age = AGE_BITS.get(f[0], 0x10)
    gender = GENDER_BITS.get(f[1] if len(f) > 1 else 'f', 0x2000)
    return age, gender


# ------------------------------------------------------------------ texture cache
_mem = {}
_mem_lock = threading.Lock()


def _cache_file(name):
    os.makedirs(TEX_CACHE, exist_ok=True)
    return os.path.join(TEX_CACHE, name)


def _save_png(im, fn, **kw):
    """Write a PNG through a private temporary file, so two requests building the same picture at once never
    leave a half-written file (the bytes are the same as a direct save)."""
    tmp = '%s.%d-%d.tmp' % (fn, os.getpid(), threading.get_ident())
    try:
        im.save(tmp, 'PNG', **kw)
        os.replace(tmp, fn)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        if not os.path.exists(fn):
            raise


# ------------------------------------------------------------------ other packages (CC and pack tones)
_pkg_lock = threading.Lock()
_pkg_mem = {}                      # path -> ((size, mtime), {(type, inst): entry}) for textures and TONEs


def _package_entries(path):
    """{(type, instance): entry} of a package's textures and skin tones (kept for the last 24 packages)."""
    try:
        st = os.stat(path)
    except OSError:
        return {}
    sig = (st.st_size, int(st.st_mtime))
    with _pkg_lock:
        hit = _pkg_mem.get(path)
        if hit and hit[0] == sig:
            return hit[1]
    from dbpf import read_index
    wanted = set(TEX_TYPES) | {T_TONE}
    try:
        idx = {(e['type'], e['inst']): e for e in read_index(path) if e['type'] in wanted and e['size'] > 0}
    except Exception:
        idx = {}
    with _pkg_lock:
        if len(_pkg_mem) >= 24:
            _pkg_mem.pop(next(iter(_pkg_mem)))
        _pkg_mem[path] = (sig, idx)
    return idx


def _package_texture(path, inst):
    """(type, path, entry) of a texture instance in one package (LRLE > RLE2 > DST > RLES > raw DDS), or None."""
    idx = _package_entries(path)
    for t in TEX_TYPES:
        e = idx.get((t, inst))
        if e is not None:
            return t, path, e
    return None


def _texture_entry(inst, ww=True, packages=()):
    """Like Resources.texture_entry, but the given packages (a CC tone's own package, a pack's builds) come first."""
    for p in packages or ():
        hit = _package_texture(p, inst)
        if hit is not None:
            return hit
    return Resources.texture_entry(inst, ww)


def texture(inst, size=None, ww=True, packages=()):
    """Decoded texture as float32 RGBA array in [0, 1], resized to (size, 2*size) when size is given (atlas
    textures) - or None. Resized results are cached as PNG files under cache/tex/. packages: look in these package
    files first (a CC or pack skin tone's own textures), then in the game."""
    if not inst:
        return None
    hit = _texture_entry(inst, ww, packages)
    if hit is None:
        return None
    t, path, e = hit
    src = '%s_%08X_%X' % (os.path.splitext(os.path.basename(path))[0][:24], t, e['pos'])
    key = (inst, src, size)
    with _mem_lock:
        if key in _mem:
            return _mem[key].astype(np.float32) / 255.0
    fn = _cache_file('t_%016X_%s_%s.png' % (inst, hashlib.md5(src.encode()).hexdigest()[:8], size or 'native'))
    arr = None
    if os.path.exists(fn):
        try:
            arr = np.asarray(Image.open(fn).convert('RGBA'))
        except Exception:
            arr = None
    if arr is None:
        from dbpf import read_resource
        arr = texfmt.decode(read_resource(path, e))
        if size and arr.shape[:2] != (2 * size, size):
            arr = np.asarray(Image.fromarray(arr, 'RGBA').resize((size, 2 * size), Image.BILINEAR if arr.shape[1] < size else Image.BOX))
        _save_png(Image.fromarray(arr, 'RGBA'), fn, compress_level=1)
    with _mem_lock:                         # small in-memory cache of the 8-bit images (~8 MB each)
        if len(_mem) >= 16:
            _mem.pop(next(iter(_mem)))
        _mem[key] = arr
    return arr.astype(np.float32) / 255.0


def part_texture(casp_key, kind='diffuse', size=1024, ww=True):
    """A CAS part's texture (diffuse, shadow, specular, normal, region_map...) as a PIL RGBA image.
    casp_key: CASP name, instance or parsed dict. Diffuse/shadow come back at atlas size (size x 2*size);
    size=None keeps the native resolution (WickedWhims' are 2048x4096). None if the part has no such texture."""
    c = load_casp(casp_key, ww=ww)
    if not c or not c['textures'].get(kind):
        return None
    inst = c['textures'][kind][2]
    arr = texture(inst, size if kind in ('diffuse', 'shadow') else None, ww)
    if arr is None:
        return None
    return Image.fromarray((arr * 255 + 0.5).astype(np.uint8), 'RGBA')


# ------------------------------------------------------------------ parts
def default_parts(frame, ww=True):
    """[(role, parsed CASP)] of the nude body for a frame, like gamedata.body() picks them."""
    roles = None
    try:
        import gamedata
        roles = gamedata.BODIES.get(frame, (None, None))[1]
        if roles and not isinstance(roles[0], tuple):          # older gamedata: plain name list
            roles = [(n, [n]) for n in roles]
    except Exception:
        roles = None
    roles = roles or _FALLBACK_PARTS.get(frame) or _FALLBACK_PARTS['yf' if frame_flags(frame)[1] == 0x2000 else 'ym']
    names = casptex.casp_by_name()
    out = []
    for role, cands in roles:
        if role in _SKIP_ROLES:
            continue
        for n in cands:
            if n in names:
                c = load_casp(names[n], ww=ww)
                if c and c['name'] == n:
                    out.append((role, c))
                    break
    return out


def eye_part(color='Brown', ww=True):
    """Eye colour CAS part: a colour from EYE_COLORS (-> yfMakeupEyeColor_<color>, used by every age and both
    genders) or a full CASP name / instance."""
    if not color:
        return None
    if isinstance(color, str) and color in EYE_COLORS:
        color = 'yfMakeupEyeColor_' + color
    return load_casp(color, ww=ww)


# ------------------------------------------------------------------ blending helpers (float32, [0,1])
def _over(dst, src, opacity=1.0):
    """Alpha-over src onto dst (both straight-alpha RGBA float arrays), in place on dst. Only the bounding box of
    src's visible texels is touched (most CAS layers paint a small part of the atlas)."""
    vis = src[:, :, 3] > 0
    rows = np.flatnonzero(vis.any(1))
    if not len(rows):
        return dst
    cols = np.flatnonzero(vis[rows[0]:rows[-1] + 1].any(0))
    ys, xs = slice(rows[0], rows[-1] + 1), slice(cols[0], cols[-1] + 1)
    s, d = src[ys, xs], dst[ys, xs]
    sa = s[:, :, 3:4] * opacity
    da = d[:, :, 3:4]
    oa = sa + da * (1 - sa)
    safe = np.where(oa > 1e-6, oa, 1)
    d[:, :, :3] = (s[:, :, :3] * sa + d[:, :, :3] * da * (1 - sa)) / safe
    d[:, :, 3:4] = oa
    return dst


def _hsl_rgb(h, s, l):
    """TS4SimRipper GetRGB: hue 0-239, saturation 0-240, luminance 0-240 -> rgb floats 0-1."""
    l = min(l / 240.0, 1.0)
    if s == 0:
        return np.array([l, l, l], np.float32)
    s = s / 240.0
    t1 = l * (1 + s) if l < 0.5 else (l + s) - l * s
    t2 = 2 * l - t1
    H = h / 239.0

    def ch(v):
        if v < 0:
            v += 1
        elif v > 1:
            v -= 1
        if 6 * v < 1:
            c = t2 + (t1 - t2) * 6 * v
        elif 2 * v < 1:
            c = t1
        elif 3 * v < 2:
            c = t2 + (t1 - t2) * (0.666 - v) * 6
        else:
            c = t2
        return min(max(c, 0.0), 1.0)
    return np.array([ch(H + 0.333), ch(H), ch(H - 0.333)], np.float32)


def blend_skin(color, detail, tone, neutral=DETAIL_NEUTRAL):
    """color: tone texture RGB (H, W, 3); detail: RGBA details (H, W, 4); tone: parsed TONE. -> RGB float32."""
    d = detail[:, :, :3] - np.float32(neutral)            # transparent details count as the neutral grey
    d *= detail[:, :, 3:4]
    d += np.float32(neutral)
    c = color.astype(np.float32, copy=False)
    t = c * (1 - c)                                         # pass 1: soft light (1-2d)c^2 + 2dc, "too dark" x1.2
    t *= d
    t *= 2
    t += c * c
    t *= np.float32(1.2)
    np.minimum(t, 1, out=t)
    p2 = np.float32(tone['pass2_opacity'] / 100.0)
    if p2 > 0:                                              # pass 2: overlay, mixed in by the pass-2 opacity
        ov = np.where(t > 0.5, 1 - (2 - 2 * d) * (1 - t), 2 * d * t)
        ov -= t
        ov *= p2
        t += ov
    if tone['saturation'] <= 100:                           # colourise: soft light with the hue/sat colour
        o = _hsl_rgb(tone['hue'], tone['saturation'], 100)
        t = t * (t * (1 - 2 * o) + 2 * o)
    t -= np.float32(0.75)                                   # slight contrast around 0.75
    t *= np.float32(1.1)
    t += np.float32(0.75)
    return np.clip(t, 0, 1, out=t)


def _shadow_layer(sh):
    """TS4SimRipper DisplayableShadow: dark parts of a shadow map -> black at up to half opacity."""
    out = np.zeros_like(sh)
    v = ((sh[:, :, 0] + sh[:, :, 2]) * 127.5 - 150) * 3.5
    v = np.clip(v, 0, 255)
    out[:, :, 3] = np.where(sh[:, :, 3] > 0, (255 - v) / 2 / 255.0, 0)
    return out


def _fill_transparent(rgba):
    """Opaque atlas: transparent texels get the mean colour of the opaque ones (then alpha = 1)."""
    a = rgba[:, :, 3]
    solid = a > 0.5
    if solid.any():
        mean = rgba[:, :, :3][solid].mean(0)
    else:
        mean = np.array([0.8, 0.6, 0.5], np.float32)
    rgba[:, :, :3] = rgba[:, :, :3] * a[:, :, None] + mean * (1 - a[:, :, None])
    rgba[:, :, 3] = 1.0
    return rgba


# ------------------------------------------------------------------ main entry points
def _load_part(key, ww=True):
    """load_casp(), or - for custom content in Mods (a Tray sim's own makeup, tattoos...) - the CAS part from the
    part index hair and clothes read from, with its package's path ('pkg_path') so its textures are found there."""
    c = load_casp(key, ww=ww)
    if c or isinstance(key, (str, dict)):
        return c
    try:
        import morph
        row = morph.PART_INDEX.find(casptex.T_CASP, key)
        if row is None:
            return None
        c = casptex.parse_casp(morph.PART_INDEX.read(casptex.T_CASP, key))
    except Exception:
        traceback.print_exc()
        return None
    path = morph.PART_INDEX.paths[int(row['pkg'])]
    c['instance'] = key
    c['package'] = os.path.basename(path)
    c['pkg_path'] = path
    return c


def casptex_int(v):
    try:
        return int(v, 16) if isinstance(v, str) else int(v)
    except (TypeError, ValueError):
        return 0


def _pkgs(p):
    return (p['pkg_path'],) if p.get('pkg_path') else ()


def _part_list(frame, part_casps, ww, eyes):
    if part_casps is None:
        parts = [c for _, c in default_parts(frame, ww)]
    else:
        parts = [c for c in (_load_part(k, ww=ww) for k in part_casps) if c]
    if eyes:
        ec = eye_part(eyes if isinstance(eyes, str) else 'Brown', ww)
        if ec and all(p['instance'] != ec['instance'] for p in parts):
            parts.append(ec)
    return parts


def _atlas_key(frame, parts, tone_inst, size, ww, opaque, tone_sig=None):
    sig = [CACHE_VERSION, frame, tone_inst, size, bool(ww), bool(opaque), DETAIL_NEUTRAL,
           [(p['instance'], p.get('package'), p['textures'].get('diffuse'), p['textures'].get('shadow')) for p in parts]]
    for key in ('diffuse', 'shadow'):
        for p in parts:
            tgi = p['textures'].get(key)
            if tgi:
                hit = _texture_entry(tgi[2], ww, _pkgs(p))
                sig.append(os.path.basename(hit[1]) + ':%X' % hit[2]['pos'] if hit else None)
    if tone_sig is not None:            # a CC / pack tone: its package too (base-game tones keep their old keys)
        sig.append(tone_sig)
    return hashlib.md5(json.dumps(sig, default=str).encode()).hexdigest()[:12]


def _tone_sig(src):
    """Cache-key part for a tone that is not the base game's: where it was read from (None for base-game tones)."""
    if not src or src['kind'] == 'game':
        return None
    try:
        st = os.stat(src['path'])
        return ['tone', src['kind'], os.path.basename(src['path']), src['entry']['pos'], st.st_size, int(st.st_mtime)]
    except OSError:
        return ['tone', src['kind'], os.path.basename(src['path']), src['entry']['pos']]


_build_locks = {}
_build_locks_lock = threading.Lock()


def _build_lock(fn):
    with _build_locks_lock:
        lk = _build_locks.get(fn)
        if lk is None:
            if len(_build_locks) > 256:
                _build_locks.clear()
            lk = _build_locks[fn] = threading.Lock()
        return lk


def skin_atlas_path(frame, part_casps=None, tone_inst=None, size=1024, ww=True, eyes='Brown', opaque=True):
    """Like skin_atlas() but returns the cached PNG's path (built if needed) - handy for serving the file as is."""
    info = {}
    skin_atlas(frame, part_casps, tone_inst, size, ww, eyes, opaque, info)
    return info['file']


def skin_atlas(frame, part_casps=None, tone_inst=None, size=1024, ww=True, eyes='Brown', opaque=True, info=None):
    """The sim's composited body texture atlas as a PIL RGBA image of size x 2*size.

    frame      body frame: 'yf' (young adult / adult female), 'ym', 'yf_futa', or any [t|y|a|e][f|m]
    part_casps CAS parts to show: names, instances or parsed CASPs. None = the frame's nude body parts as
               gamedata.BODIES lists them (top, bottom / penis, feet, head, tongue).
    tone_inst  skin tone (TONE) instance; None = DEFAULT_TONE. See skin_tones().
    ww         use WickedWhims' package (its CAS parts and the game textures it replaces); False = plain game.
    eyes       eye colour name (EYE_COLORS) or None for the skin-detail map's grey placeholder eyes.
    opaque     fill transparent texels with the mean skin colour (recommended for rendering).
    info       optional dict that receives the layer list and timings.
    """
    tone_inst = tone_inst or DEFAULT_TONE
    parts = _part_list(frame, part_casps, ww, eyes)
    key = _atlas_key(frame, parts, tone_inst, size, ww, opaque, _tone_sig(tone_source(tone_inst)))
    fn = _cache_file('atlas_%s_%X_%d_%s_%s.png' % (frame, tone_inst, size, 'ww' if ww else 'game', key))
    if info is not None:
        info['file'] = fn
        info['parts'] = [(p['name'], p['composition'], p['sort_layer'], p.get('package')) for p in parts]

    def cached():
        if os.path.exists(fn):
            try:
                im = Image.open(fn)
                im.load()
                if info is not None:
                    info['cached'] = True
                return im
            except Exception:
                pass
        return None
    im = cached()
    if im is not None:
        return im
    with _build_lock(fn):              # one build per picture, even when several requests ask for it at once
        im = cached()
        if im is not None:
            return im
        t0 = time.time()
        arr = build_atlas(frame, parts, tone_inst, size, ww, opaque, info)
        im = Image.fromarray((arr * 255 + 0.5).astype(np.uint8), 'RGBA')
        _save_png(im, fn, compress_level=3)
    if info is not None:
        info['seconds'] = round(time.time() - t0, 2)
        info['cached'] = False
    return im


def build_atlas(frame, parts, tone_inst, size=1024, ww=True, opaque=True, info=None):
    """skin_atlas() without the cache: float32 RGBA (2*size, size, 4)."""
    W, H = size, 2 * size
    age, gender = frame_flags(frame)
    src = tone_source(tone_inst)
    if src is None:
        raise KeyError('skin tone %X not found' % tone_inst)
    tone, tone_pkgs = src['tone'], src['packages']
    layers = []
    # 1-2. details
    det_inst, det_ov = DETAILS.get((age, gender), DETAILS[(0x10, gender)])
    details = texture(det_inst, W, ww)
    details = details.copy() if details is not None else np.zeros((H, W, 4), np.float32)
    layers.append(('detail', '%016X' % det_inst))
    ov = texture(det_ov, W, ww)
    if ov is not None:
        _over(details, ov)
        layers.append(('detail overlay', '%016X' % det_ov))
    shading = [p for p in parts if p['composition'] == 3]
    others = [p for p in parts if p['composition'] != 3]
    for p in sorted(shading, key=lambda p: p['sort_layer']):
        tgi = p['textures'].get('diffuse')
        tex = texture(tgi[2], W, ww) if tgi else None
        if tex is not None:
            _over(details, tex)
            layers.append(('grey shading (comp 3) -> details', p['name']))
    # 3. skin colour
    sset = tone['skin_sets'][0]
    col = texture(sset['texture'], W, ww, tone_pkgs)
    if col is None:
        col = np.ones((H, W, 4), np.float32) * np.array([0.6, 0.45, 0.35, 1.0], np.float32)
    layers.append(('tone colour', '%016X' % sset['texture']))
    out = np.empty((H, W, 4), np.float32)
    out[:, :, :3] = blend_skin(col[:, :, :3], details, tone)
    out[:, :, 3] = col[:, :, 3]
    # 4. tone overlay for the age/gender
    tov = casptex.tone_overlay_for(tone, age | gender)
    if tov:
        tex = texture(tov, W, ww, tone_pkgs)
        if tex is not None:
            _over(out, tex)
            layers.append(('tone overlay', '%016X' % tov))
    # 5. other parts
    for p in sorted(others, key=lambda p: (-p['composition'], p['sort_layer'])):
        sh = p['textures'].get('shadow')
        if sh:
            tex = texture(sh[2], W, ww, _pkgs(p))
            if tex is not None and tex[:, :, 3].any():
                _over(out, _shadow_layer(tex))
                layers.append(('shadow', p['name']))
        tgi = p['textures'].get('diffuse')
        tex = texture(tgi[2], W, ww, _pkgs(p)) if tgi else None
        if tex is None or not tex[:, :, 3].any():
            continue
        op = 1.0
        if p['composition'] == 2:
            op = sset.get('makeup_opacity', 1.0)
        elif p['composition'] == 4:
            op = sset.get('makeup_opacity2', 1.0)
        _over(out, tex, op)
        layers.append(('diffuse (comp %d, layer %d)' % (p['composition'], p['sort_layer']), p['name']))
    if opaque:
        _fill_transparent(out)
    if info is not None:
        info['layers'] = layers
        info['tone'] = {k: tone[k] for k in ('hue', 'saturation', 'pass2_opacity', 'swatch_colors')}
    return out


def eye_texture(frame='yf', color='Brown', ww=True, size=1024):
    """The eye colour texture: the region of the atlas both eyeballs of the head GEOM map to (UV rect EYE_UV_RECT,
    ~106x105 px of a 1024x2048 atlas). Eye colours are ordinary CAS parts (body type Eyecolor, e.g.
    yfMakeupEyeColor_Brown: every age, both genders) whose full-atlas diffuse only paints that rectangle; the skin
    atlas already includes it (skin_atlas(eyes=...)). Returns a PIL RGBA crop; .info['uv_rect'] holds the UV rect."""
    c = eye_part(color, ww)
    if not c or not c['textures'].get('diffuse'):
        return None
    arr = texture(c['textures']['diffuse'][2], size, ww)
    u0, v0, u1, v1 = EYE_UV_RECT
    H, W = arr.shape[:2]
    crop = arr[int(v0 * H):int(np.ceil(v1 * H)), int(u0 * W):int(np.ceil(u1 * W))]
    im = Image.fromarray((crop * 255 + 0.5).astype(np.uint8), 'RGBA')
    im.info['uv_rect'] = EYE_UV_RECT
    im.info['part'] = c['name']
    return im


def skin_tones():
    """All skin tones: [{instance, hex, swatch, hue, saturation, pass2_opacity, skin_type, sort_order, ...}]."""
    return casptex.list_tones()


# ------------------------------------------------------------------ skin tones: where they come from, stand-ins
_tone_lock = threading.Lock()
_tone_mem = {}                     # instance -> tone_source() answer (None: installed nowhere)
_resolve_mem = {}                  # (instance, size, ww) -> resolve_tone() answer
_game_tone_list = []               # [(instance, swatch rgb or None, hue, saturation, pass2 opacity)], made once
_FRAME_OK = re.compile(r'^[yae][fm](?:_[a-z]{1,12})?$')     # adult body frames only (yf, ym, yf_futa, ef, ...)


def _tone_int(tone):
    """A tone as the app sends it ('000000007911fa53', '0x3840', 14400) -> int; None / '' / 0 -> None;
    anything unreadable -> -1 (treated as a tone that is not installed)."""
    if tone is None or tone == '' or tone == 0:
        return None
    if isinstance(tone, int):
        return tone if 0 < tone < (1 << 64) else -1
    s = str(tone).strip().lower()
    s = s[2:] if s.startswith('0x') else s
    if not s or len(s) > 16 or not re.match(r'^[0-9a-f]+$', s):
        return -1
    return int(s, 16) or None


def _pack_packages(path):
    """Where a pack tone's textures are: that pack's delta builds, then its full builds (the tone's own file among
    them). CC tones ship their textures in their own package."""
    try:
        import glob, gamedata
        g = gamedata.game_dir()
    except Exception:
        return (path,)
    code = os.path.basename(os.path.dirname(path))        # EP01 for EP01\ClientFullBuild0 and Delta\EP01\ClientDeltaBuild0
    out = sorted(glob.glob(os.path.join(g, 'Delta', code, 'ClientDeltaBuild*.package'))) + \
        sorted(glob.glob(os.path.join(g, code, 'ClientFullBuild*.package')))
    norm = {os.path.normcase(os.path.abspath(p)) for p in out}
    if os.path.normcase(os.path.abspath(path)) not in norm:
        out.insert(0, path)
    return tuple(out)


def _extra_tone_rows(inst):
    """[(rank, package path, entry, is_cc)] of the TONE resources with this instance that Resources doesn't index,
    from morph.MORPH_INDEX (Mods, Mods_parked and every pack's client builds; cached on disk, loaded on first use).
    Rank: Mods 0, the game's packs 1, Mods_parked 2 (what the game would load first)."""
    import morph
    M = morph.MORPH_INDEX
    M._load()
    try:
        insts, ridx = M._by_type[T_TONE]
        i = np.uint64(inst)
        rows = [M.rows[r] for r in ridx[np.searchsorted(insts, i, 'left'):np.searchsorted(insts, i, 'right')]]
    except KeyError:                                           # no TONE anywhere outside the base game
        rows = []
    except AttributeError:                                     # another index layout: its first hit only
        row = M.find(T_TONE, inst)
        rows = [] if row is None else [row]
    import gamedata
    parked = os.path.normcase(os.path.abspath(gamedata.PARKED_DIR))
    out = []
    for k, row in enumerate(rows):
        if int(row['size']) <= 0:
            continue
        pi = int(row['pkg'])
        path = M.paths[pi]
        cc = pi < M.n_cc
        in_parked = os.path.normcase(os.path.abspath(path)).startswith(parked + os.sep)
        e = {'type': T_TONE, 'group': int(row['group']), 'inst': inst, 'pos': int(row['pos']), 'size': int(row['size']),
             'mem': int(row['mem']), 'comp': int(row['comp'])}
        out.append(((2 if in_parked else 0) if cc else 1, k, path, e, cc))
    out.sort(key=lambda x: (x[0], x[1]))
    return [(rank, path, e, cc) for rank, _, path, e, cc in out]


def tone_source(inst):
    """Where a skin tone comes from -> {'inst', 'tone' (parsed TONE), 'kind': 'game' | 'pack' | 'cc', 'path',
    'entry', 'packages' (look for its textures there first)}, or None when it is installed nowhere.
    Base-game (and WickedWhims') tones come from Resources exactly as before. Adults only: CC in a folder or file
    whose name hits gamedata's block list is never used."""
    if not inst or inst < 0:
        return None
    with _tone_lock:
        if inst in _tone_mem:
            return _tone_mem[inst]
    src = None
    try:
        t = load_tone(inst)
    except Exception:
        t = None
    if t is not None:
        hit = Resources.find(T_TONE, inst)
        src = {'inst': inst, 'tone': t, 'kind': 'game', 'path': hit[0] if hit else None, 'entry': hit[1] if hit else None,
               'packages': ()}
    else:
        import gamedata
        from dbpf import read_resource
        for _rank, path, e, cc in _extra_tone_rows(inst):   # an error here is not remembered (tried again next time)
            if cc and gamedata.blocked_path(path):
                continue
            try:
                t = parse_tone(read_resource(path, e))
            except Exception:
                continue                                        # a damaged TONE: the next copy, if any
            t['instance'] = inst
            src = {'inst': inst, 'tone': t, 'kind': 'cc' if cc else 'pack', 'path': path, 'entry': e,
                   'packages': (path,) if cc else _pack_packages(path)}
            break
    with _tone_lock:
        _tone_mem[inst] = src
    return src


def _tone_readable(src, size=1024, ww=True):
    """Can the tone's own colour texture be read? Base-game tones always count (they build as before). The decoded
    texture lands in the texture cache, so the atlas build that follows reuses it."""
    if src['kind'] == 'game':
        return True
    try:
        sets = src['tone'].get('skin_sets') or []
        col = texture(sets[0]['texture'], size, ww, src['packages']) if sets else None
        return col is not None and bool((col[:, :, 3] > 0).any())
    except Exception:
        traceback.print_exc()
        return False


def _hex_rgb(h):
    try:
        v = int(str(h).lstrip('#'), 16)
        return ((v >> 16) & 255, (v >> 8) & 255, v & 255)
    except (TypeError, ValueError):
        return None


def _lab(rgb):
    """sRGB 0-255 -> CIE Lab (D65), for 'nearest colour'."""
    c = np.asarray(rgb, np.float64) / 255.0
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    xyz = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]]) @ c
    xyz = xyz / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16.0 / 116.0)
    return np.array([116 * f[1] - 16, 500 * (f[0] - f[1]), 200 * (f[1] - f[2])])


def _game_tones():
    """The base game's tones with their swatch colour and colourise values (those always build)."""
    with _tone_lock:
        if _game_tone_list:
            return list(_game_tone_list)
    out = []
    for t in casptex.list_tones():
        out.append((t['instance'], _hex_rgb(t.get('swatch')), t.get('hue', 0), t.get('saturation', 0),
                    t.get('pass2_opacity', 0)))
    with _tone_lock:
        _game_tone_list[:] = out
    return out


def nearest_game_tone(tone, exclude=None):
    """The base-game tone closest to a parsed TONE: by swatch colour (CIE Lab) when it has one, else by its
    hue / saturation / pass-2 opacity. DEFAULT_TONE when nothing compares."""
    games = [g for g in _game_tones() if g[0] != exclude]
    rgb = _hex_rgb((tone.get('swatch_colors') or [None])[0])
    best = None
    if rgb is not None:
        lab = _lab(rgb)
        for inst, sw, *_ in games:
            if sw is not None:
                d = float(np.linalg.norm(_lab(sw) - lab))
                if best is None or d < best[0]:
                    best = (d, inst)
    if best is None:
        hue, sat, p2 = tone.get('hue', 0), tone.get('saturation', 0), tone.get('pass2_opacity', 0)
        for inst, _sw, h, s, p in games:
            dh = abs(h - hue) % 240
            d = min(dh, 240 - dh) / 2.4 + abs(s - sat) / 2.4 + abs(p - p2)
            if best is None or d < best[0]:
                best = (d, inst)
    return best[1] if best else DEFAULT_TONE


def resolve_tone(tone, size=1024, ww=True):
    """The tone a skin is built with -> {'asked': '%016x' or '', 'used': int, 'status': 'real' | 'standin',
    'source': 'game' | 'pack' | 'cc' | 'nearest' | 'default', 'reason': None | 'missing' | 'unreadable',
    'package': file name of a CC / pack tone}. No tone asked -> the default tone ('real'). Remembered per tone."""
    inst = _tone_int(tone)
    asked = '' if inst is None else ('%016x' % inst if inst > 0 else str(tone))
    if inst is None:
        return {'asked': '', 'used': DEFAULT_TONE, 'status': 'real', 'source': 'default', 'reason': None, 'package': None}
    key = (inst, size, bool(ww))
    with _tone_lock:
        if key in _resolve_mem:
            return dict(_resolve_mem[key])
    src = tone_source(inst) if inst > 0 else None
    if src is not None and _tone_readable(src, size, ww):
        out = {'asked': asked, 'used': inst, 'status': 'real', 'source': src['kind'], 'reason': None,
               'package': os.path.basename(src['path']) if src['path'] and src['kind'] != 'game' else None}
    elif src is not None:
        out = {'asked': asked, 'used': nearest_game_tone(src['tone'], exclude=inst), 'status': 'standin',
               'source': 'nearest', 'reason': 'unreadable', 'package': os.path.basename(src['path']) if src['path'] else None}
    else:
        out = {'asked': asked, 'used': DEFAULT_TONE, 'status': 'standin', 'source': 'default', 'reason': 'missing',
               'package': None}
    with _tone_lock:
        _resolve_mem[key] = out
    return dict(out)


def tone_info(info):
    """resolve_tone()'s answer for the app (JSON): {status, source, used: '%016x', reason, package}."""
    return {'status': info['status'], 'source': info['source'], 'used': '%016x' % info['used'] if info.get('used') else '',
            'reason': info.get('reason'), 'package': info.get('package')}


def _flat_skin(size=1024):
    """Last resort: a plain skin-coloured atlas (never white)."""
    fn = _cache_file('flat_skin_%d.png' % size)
    if not os.path.exists(fn):
        _save_png(Image.new('RGBA', (size, 2 * size), (214, 167, 139, 255)), fn)
    return fn


def skin_for(frame='yf', tone=None, size=1024, ww=True, look=None):
    """The skin atlas PNG to show for a body frame and a skin tone -> (path, info as resolve_tone()). Never raises:
    a tone that isn't installed or can't be read gets a stand-in (info['status'] == 'standin'); a build that fails
    falls back to the nearest base-game tone, then the default tone, then a plain skin-coloured picture.
    frame: an adult body frame (yf, ym, yf_futa, ...); anything else shows 'yf'.
    look: a Tray sim's own painted parts (trayfmt.look_parts(): makeup, brows, eye colour, skin details, tattoos) on
    top of the nude body; one that is not installed is left out. With its own eye colour the default brown goes."""
    frame = frame if isinstance(frame, str) and _FRAME_OK.match(frame) else 'yf'
    parts, eyes = None, 'Brown'
    if look:
        parts = [c['instance'] for _, c in default_parts(frame, ww)]
        for p in look:
            inst = casptex_int(p['casp_instance'])
            if inst and inst not in parts:
                parts.append(inst)
                if p.get('body_type') == 35:                # EYECOLOR
                    eyes = None
    try:
        info = resolve_tone(tone, size, ww)
    except Exception:
        traceback.print_exc()
        info = {'asked': str(tone or ''), 'used': DEFAULT_TONE, 'status': 'standin', 'source': 'default',
                'reason': 'missing', 'package': None}
    try:
        return skin_atlas_path(frame, parts, tone_inst=info['used'], size=size, ww=ww, eyes=eyes), info
    except Exception:
        traceback.print_exc()
    tried = {info['used']}
    fallbacks = []
    try:
        src = tone_source(info['used'])
        if src is not None and src['kind'] != 'game':
            fallbacks.append((nearest_game_tone(src['tone'], exclude=info['used']), 'nearest'))
    except Exception:
        traceback.print_exc()
    fallbacks.append((DEFAULT_TONE, 'default'))
    for inst, source in fallbacks:
        if inst in tried:
            continue
        tried.add(inst)
        try:
            path = skin_atlas_path(frame, parts, tone_inst=inst, size=size, ww=ww, eyes=eyes)
        except Exception:
            traceback.print_exc()
            continue
        info = dict(info, used=inst, status='standin', source=source, reason=info.get('reason') or 'unreadable')
        inst_asked = _tone_int(tone)
        if inst_asked:                                     # next time straight to the stand-in
            with _tone_lock:
                _resolve_mem[(inst_asked, size, bool(ww))] = dict(info)
        return path, info
    return _flat_skin(size), dict(info, used=0, status='standin', source='flat', reason=info.get('reason') or 'unreadable')


# ------------------------------------------------------------------ WickedWhims' cum layers (spec_game 5)
# WickedWhims shows cum as CAS parts (face paint, sort layer 7500): 8 body parts x 3 levels, listed in its tuning
# snippet 'TURBODRIVER:WickedWhims_CASParts_Cum_Layers' (group "Default"). Each diffuse is a full-atlas 2048x4096
# image that paints one small rectangle, so only that rectangle is kept: cropped, halved to the app's 1024x2048
# atlas and cached as a PNG. The app paints it over the sim's skin at the rectangle (rect = u0, v0, u1, v1; v from
# the top, like the atlas).
CUM_TYPES = ('FACE', 'CHEST', 'BELLY', 'UPPER_BACK', 'LOWER_BACK', 'VAGINA', 'BUTT', 'FEET')
CUM_VERSION = 1
CUM_LAYERS_PATH = os.path.normpath(os.path.join(HERE, '..', 'cache', 'cum_layers_v1.json'))
_cum_lock = threading.Lock()
_cum_mem = {}


def _ww_snippets(pkg):
    """(instance, xml text) of every tuning snippet in a package."""
    import dbpf
    for e in dbpf.read_index(pkg):
        if e['type'] != 0x7DF2169C:
            continue
        try:
            yield e['inst'], dbpf.read_resource(pkg, e).decode('utf-8', 'replace')
        except Exception:
            continue


def cum_parts(group='Default'):
    """{type: [CASP instance for level 1, 2, 3]} from WickedWhims' cum layer snippet (its 'Default' group).
    {} when WickedWhims' tuning package is not found."""
    import gamedata
    import xml.etree.ElementTree as ET
    pkg = gamedata.ww_tuning_package()
    if not pkg:
        return {}
    out = {}
    for _inst, text in _ww_snippets(pkg):
        if '_Cum_Layers' not in text[:800]:
            continue
        try:
            root = ET.fromstring(text.encode('utf-8'))
        except ET.ParseError:
            continue
        if not str(root.get('n', '')).endswith('_Cum_Layers'):
            continue
        for u in root.iter('U'):
            f = {c.get('n'): (c.text or '').strip() for c in u if c.get('n')}
            if f.get('cas_part_type', '').upper() != 'CUM' or f.get('cas_part_group') != group:
                continue
            sub = f.get('cas_part_subtype', '').upper()
            if sub not in CUM_TYPES:
                continue
            ids = []
            for x in f.get('cas_part_ids', '').split(','):
                try:
                    ids.append(int(x.strip()))
                except ValueError:
                    pass
            if ids:
                out[sub] = ids[:3]
    return {t: out[t] for t in CUM_TYPES if t in out}


def _cum_png(inst):
    return _cache_file('cum_%016x_v%d.png' % (inst, CUM_VERSION))


def _decode_native(inst, ww=True):
    """A texture at its own size (uint8 RGBA), without writing the big image into the cache."""
    hit = Resources.texture_entry(inst, ww)
    if hit is None:
        return None
    _t, path, e = hit
    from dbpf import read_resource
    return texfmt.decode(read_resource(path, e))


def _half(arr):
    """2x2 average of an RGBA uint8 image with even sides, in premultiplied alpha (no dark edges)."""
    a = arr[:, :, 3:4].astype(np.float32) / 255.0
    rgb = arr[:, :, :3].astype(np.float32) * a
    h, w = arr.shape[0] // 2, arr.shape[1] // 2

    def pool(x):
        return x.reshape(h, 2, w, 2, x.shape[2]).mean(axis=(1, 3))
    rgb, a = pool(rgb), pool(a)
    out = np.zeros((h, w, 4), np.uint8)
    safe = np.where(a > 1e-6, a, 1.0)
    out[:, :, :3] = np.clip(rgb / safe + 0.5, 0, 255).astype(np.uint8)
    out[:, :, 3] = np.clip(a[:, :, 0] * 255 + 0.5, 0, 255).astype(np.uint8)
    return out


def _cum_layer(inst, atlas_w=1024):
    """Crop one cum part's diffuse to its painted rectangle (alpha > 4, 2 px pad), scaled to an atlas_w-wide atlas.
    -> [u0, v0, u1, v1] (the PNG is written to the texture cache), or None."""
    c = load_casp(inst, ww=True)
    if not c or not c['textures'].get('diffuse'):
        return None
    arr = _decode_native(c['textures']['diffuse'][2])
    if arr is None:
        return None
    H, W = arr.shape[:2]
    vis = arr[:, :, 3] > 4
    rows, cols = np.flatnonzero(vis.any(1)), np.flatnonzero(vis.any(0))
    if not len(rows):
        return None
    y0, y1 = max(0, rows[0] - 2), min(H, rows[-1] + 3)
    x0, x1 = max(0, cols[0] - 2), min(W, cols[-1] + 3)
    k = W / float(atlas_w)
    if abs(k - 2.0) < 1e-9:
        # even edges, so the half-size image lands on whole atlas pixels
        y0, x0 = y0 - y0 % 2, x0 - x0 % 2
        y1, x1 = min(H, y1 + y1 % 2), min(W, x1 + x1 % 2)
        crop = _half(np.ascontiguousarray(arr[y0:y1, x0:x1]))
    else:
        crop = arr[y0:y1, x0:x1]
        size = (max(1, int(round((x1 - x0) / k))), max(1, int(round((y1 - y0) / k))))
        if size != (crop.shape[1], crop.shape[0]):
            crop = np.asarray(Image.fromarray(crop, 'RGBA').resize(size, Image.LANCZOS))
    Image.fromarray(crop, 'RGBA').save(_cum_png(inst), compress_level=6)
    return [round(float(x0) / W, 6), round(float(y0) / H, 6), round(float(x1) / W, 6), round(float(y1) / H, 6)]


def _cum_sig(pkg, group):
    try:
        return [CUM_VERSION, group, os.path.basename(pkg), os.path.getsize(pkg), int(os.path.getmtime(pkg))]
    except (OSError, TypeError):
        return None


def cum_layers(group='Default'):
    """{type: [{level, inst: '%016x', rect: [u0, v0, u1, v1]}]} for WickedWhims' cum parts (8 types x 3 levels),
    rects in UV of the 1:2 atlas (v from the top). Cached in cache/cum_layers_v1.json (keyed by the tuning package's
    size and mtime) with the cropped PNGs in cache/tex. {} without WickedWhims."""
    import gamedata
    pkg = gamedata.ww_tuning_package()
    if not pkg:
        return {}
    sig = _cum_sig(pkg, group)
    with _cum_lock:
        hit = _cum_mem.get(group)
        if hit and hit[0] == sig:
            return hit[1]
        layers = None
        try:
            with open(CUM_LAYERS_PATH, encoding='utf-8') as f:
                saved = json.load(f)
            if saved.get('sig') == sig and all(os.path.exists(_cum_png(int(x['inst'], 16)))
                                               for v in saved['layers'].values() for x in v):
                layers = saved['layers']
        except (OSError, ValueError, KeyError, TypeError):
            layers = None
        if layers is None:
            layers = {}
            for typ, insts in cum_parts(group).items():
                out = []
                for level, inst in enumerate(insts, 1):
                    try:
                        rect = _cum_layer(inst)
                    except Exception:
                        rect = None
                    if rect:
                        out.append({'level': level, 'inst': '%016x' % inst, 'rect': rect})
                if out:
                    layers[typ] = out
            os.makedirs(os.path.dirname(CUM_LAYERS_PATH), exist_ok=True)
            tmp = CUM_LAYERS_PATH + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump({'sig': sig, 'layers': layers}, f, indent=1)
            os.replace(tmp, CUM_LAYERS_PATH)
        _cum_mem[group] = (sig, layers)
        return layers


def cum_texture_path(inst):
    """The cropped PNG of one cum part - only for the instances cum_layers() lists (else None)."""
    try:
        want = '%016x' % (int(inst, 16) if isinstance(inst, str) else int(inst))
    except (TypeError, ValueError):
        return None
    for items in cum_layers().values():
        for x in items:
            if x['inst'] == want:
                p = _cum_png(int(want, 16))
                return p if os.path.exists(p) else None
    return None
