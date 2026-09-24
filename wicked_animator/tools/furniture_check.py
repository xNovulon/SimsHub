"""Visual check of the real game furniture meshes read by backend/objmesh.py.

    python tools/furniture_check.py                 # every reference object that matters for the check
    python tools/furniture_check.py DOUBLE_BED SOFA # just these locations (or object ids, 'NAME@state')
    python tools/furniture_check.py --all           # every location in cache/ww_example_objects.json

For each object it renders front (camera at +Z looking -Z, +X to the right), side (camera at -X, the object's front
+Z to the right), top (looking down, +Z at the bottom) and a 3/4 view with a numpy z-buffer, textured with the game's
own diffuse textures. A 1 m grid (0.1 m minor lines) is drawn behind, the origin WickedWhims places the actors at is
marked with a red cross, and the top surface (mattress / seat / counter top) height is drawn as a dashed line.
Output: cache/furniture/check_<LOCATION>.png plus check_overview.png.
"""
import os, sys, time, json

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'backend'))

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import objmesh

OUT = objmesh.CACHE_DIR
DEFAULT = ['DOUBLE_BED', 'SINGLE_BED', 'SOFA', 'LOVESEAT', 'CHAIR_LIVING', 'CHAIR_DINING', 'COUNTER', 'TABLE_DINING_2X',
           'DESK', 'BATHTUB', 'SHOWER', 'SHOWER_TUB', 'HOTTUB', 'CORNER_BATHTUB', 'OPEN_SHOWER', 'HOTTUB_INGROUND']
PPM = 170          # pixels per metre
BG, GRID, GRID_MINOR = (246, 246, 243), (170, 170, 170), (222, 222, 218)

_tex_cache = {}


def _texture(name):
    if not name:
        return None
    if name not in _tex_cache:
        try:
            _tex_cache[name] = np.asarray(Image.open(os.path.join(OUT, name)).convert('RGBA')).astype(np.float32)
        except Exception:
            _tex_cache[name] = None
    return _tex_cache[name]


def _font(size):
    for f in ('arial.ttf', 'segoeui.ttf', 'DejaVuSans.ttf'):
        try:
            return ImageFont.truetype(f, size)
        except Exception:
            pass
    return ImageFont.load_default()


def render(obj, view, ppm=PPM, pad=0.35):
    """-> (PIL image, world->pixel function). view: 'front' | 'side' | 'top' | 'persp'."""
    b = obj['bounds']
    lo, hi = np.array(b['min']), np.array(b['max'])
    lo = np.minimum(lo, 0); hi = np.maximum(hi, 0)
    if view == 'front':
        R = np.eye(3)                                   # screen x = X, y = Y, depth = Z
    elif view == 'side':
        R = np.array([[0, 0, 1], [0, 1, 0], [-1, 0, 0]], float)   # screen x = Z, depth = -X (camera at -X)
    elif view == 'top':
        R = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]], float)   # screen x = X, screen up = -Z, depth = Y
    else:
        a, e = np.radians(35), np.radians(28)
        ry = np.array([[np.cos(a), 0, np.sin(a)], [0, 1, 0], [-np.sin(a), 0, np.cos(a)]])
        rx = np.array([[1, 0, 0], [0, np.cos(e), -np.sin(e)], [0, np.sin(e), np.cos(e)]])
        R = rx @ ry
    corners = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]) @ R.T
    smin, smax = corners.min(0) - pad, corners.max(0) + pad
    W = int((smax[0] - smin[0]) * ppm); H = int((smax[1] - smin[1]) * ppm)

    def to_px(p):
        s = np.asarray(p, float) @ R.T
        return np.stack([(s[..., 0] - smin[0]) * ppm, (smax[1] - s[..., 1]) * ppm, s[..., 2]], -1)

    img = np.zeros((H, W, 3), np.float32); img[:] = BG
    zbuf = np.full((H, W), -np.inf, np.float32)
    covered = np.zeros((H, W), bool)
    light = np.array([0.35, 0.8, 0.5]); light /= np.linalg.norm(light)
    # opaque meshes first, transparent after (blended over)
    for m in sorted(obj['meshes'], key=lambda m: m['transparent']):
        P = np.array(m['positions'], float).reshape(-1, 3)
        N = np.array(m['normals'], float).reshape(-1, 3) if m['normals'] else None
        UV = np.array(m['uvs'], float).reshape(-1, 2) if m['uvs'] else None
        F = np.array(m['faces'], int).reshape(-1, 3)
        S = to_px(P)
        tex = _texture(m['texture'])
        for f in F:
            a, bb, c = S[f]
            x0 = max(int(np.floor(min(a[0], bb[0], c[0]))), 0); x1 = min(int(np.ceil(max(a[0], bb[0], c[0]))), W - 1)
            y0 = max(int(np.floor(min(a[1], bb[1], c[1]))), 0); y1 = min(int(np.ceil(max(a[1], bb[1], c[1]))), H - 1)
            if x1 < x0 or y1 < y0:
                continue
            den = (bb[1] - c[1]) * (a[0] - c[0]) + (c[0] - bb[0]) * (a[1] - c[1])
            if abs(den) < 1e-12:
                continue
            xs, ys = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
            w0 = ((bb[1] - c[1]) * (xs - c[0]) + (c[0] - bb[0]) * (ys - c[1])) / den
            w1 = ((c[1] - a[1]) * (xs - c[0]) + (a[0] - c[0]) * (ys - c[1])) / den
            w2 = 1 - w0 - w1
            inside = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
            if not inside.any():
                continue
            z = w0 * a[2] + w1 * bb[2] + w2 * c[2]
            zb = zbuf[y0:y1 + 1, x0:x1 + 1]
            vis = inside & (z > zb)
            if not vis.any():
                continue
            # shading: two-sided lambert with the face normal (vertex normals when present)
            pa, pb, pc = P[f]
            fn = np.cross(pb - pa, pc - pa); fn /= (np.linalg.norm(fn) + 1e-12)
            if N is not None:
                vn = N[f].mean(0); vn /= (np.linalg.norm(vn) + 1e-12)
                fn = vn if np.dot(vn, fn) > -0.2 else fn
            shade = 0.45 + 0.55 * abs(float(np.dot(fn, light)))
            if tex is not None and UV is not None:
                uv = w0[..., None] * UV[f[0]] + w1[..., None] * UV[f[1]] + w2[..., None] * UV[f[2]]
                th, tw = tex.shape[:2]
                tx = np.clip((uv[..., 0] % 1.0) * tw, 0, tw - 1).astype(int)
                ty = np.clip((uv[..., 1] % 1.0) * th, 0, th - 1).astype(int)   # DirectX UVs: v = 0 is the top row
                col = tex[ty, tx]
                rgb, alpha = col[..., :3], col[..., 3:4] / 255.0
            else:
                rgb = np.full(xs.shape + (3,), 190.0, np.float32); alpha = np.ones(xs.shape + (1,), np.float32)
            rgb = rgb * shade
            region = img[y0:y1 + 1, x0:x1 + 1]
            if m['transparent']:
                al = np.clip(alpha, 0.25, 1.0)
                region[vis] = (rgb * al + region * (1 - al))[vis]
            else:
                region[vis] = rgb[vis]
                zb[vis] = z[vis]
            covered[y0:y1 + 1, x0:x1 + 1] |= vis
    return img, covered, to_px, (W, H), R


def _dashed(d, p0, p1, fill, dash=8):
    x0, y0 = p0; x1, y1 = p1
    L = max(abs(x1 - x0), abs(y1 - y0)); n = int(L // dash)
    for k in range(0, n, 2):
        t0, t1 = k / max(n, 1), min((k + 1) / max(n, 1), 1)
        d.line([(x0 + (x1 - x0) * t0, y0 + (y1 - y0) * t0), (x0 + (x1 - x0) * t1, y0 + (y1 - y0) * t1)], fill=fill, width=2)


def draw_view(obj, view, title):
    img, covered, to_px, (W, H), R = render(obj, view)
    # grid behind the object: blend grid lines only where the object is not
    canvas = Image.new('RGB', (W, H), BG)
    d = ImageDraw.Draw(canvas)
    if view != 'persp':
        inv = np.linalg.inv(R)
        # screen axes in world: grid every 0.1 m / 1 m along the two screen axes through the origin
        o = to_px([0, 0, 0])
        for k in range(-60, 61):
            v = k / 10.0
            major = (k % 10 == 0)
            col = GRID if major else GRID_MINOR
            x = o[0] + v * PPM; y = o[1] - v * PPM
            if 0 <= x < W:
                d.line([(x, 0), (x, H)], fill=col, width=2 if major else 1)
            if 0 <= y < H:
                d.line([(0, y), (W, y)], fill=col, width=2 if major else 1)
    else:
        # floor grid (y = 0) in the 3/4 view
        for k in range(-3, 4):
            p0, p1 = to_px([k, 0, -3]), to_px([k, 0, 3])
            d.line([tuple(p0[:2]), tuple(p1[:2])], fill=GRID, width=1)
            p0, p1 = to_px([-3, 0, k]), to_px([3, 0, k])
            d.line([tuple(p0[:2]), tuple(p1[:2])], fill=GRID, width=1)
    base = np.asarray(canvas).astype(np.float32)
    base[covered] = img[covered]
    out = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(out)
    f = _font(15)
    # origin marker (WickedWhims' actor origin)
    o = to_px([0, 0, 0])
    d.line([(o[0] - 14, o[1]), (o[0] + 14, o[1])], fill=(220, 20, 20), width=3)
    d.line([(o[0], o[1] - 14), (o[0], o[1] + 14)], fill=(220, 20, 20), width=3)
    # axis arrows: +X red, +Y green, +Z blue (0.5 m)
    for axis, colr, lab in ((0, (200, 40, 40), '+X'), (1, (40, 150, 40), '+Y'), (2, (40, 70, 210), '+Z')):
        v = np.zeros(3); v[axis] = 0.5
        e = to_px(v)
        if np.hypot(e[0] - o[0], e[1] - o[1]) > 6:
            d.line([(o[0], o[1]), (e[0], e[1])], fill=colr, width=3)
            d.text((e[0] + 4, e[1] - 8), lab, fill=colr, font=f)
    sh = obj.get('surface_height')
    if sh and view in ('front', 'side'):
        y = to_px([0, sh, 0])[1]
        _dashed(d, (0, y), (W, y), (230, 120, 0))
        d.text((6, y - 20), 'top surface %.3f m' % sh, fill=(200, 100, 0), font=f)
    d.text((6, 4), title, fill=(30, 30, 30), font=_font(17))
    return out


def check(loc_or_id):
    """'DOUBLE_BED', an object id, or either with '@state' ('@none' = no geometry state, '@0x1234abcd', '@Normal')."""
    t0 = time.time()
    spec, _, st = str(loc_or_id).partition('@')
    state = None if not st else (0 if st.lower() == 'none' else st)
    oid = int(spec) if spec.isdigit() else objmesh.example_objects().get(spec.upper())
    if oid is None:
        print('%-16s no object' % spec)
        return None
    if state is None and not spec.isdigit():
        state = objmesh.LOCATION_STATES.get(spec.upper())
    obj = objmesh.object_mesh(oid, state=state)
    loc = spec.upper() + ('@' + st if st else '')
    t_load = time.time() - t0
    st = ('  [%s]' % obj['geometry_state']) if obj.get('geometry_state') else ''
    views = [draw_view(obj, v, '%s  %s%s  (%s)' % (loc, obj['name'], st, v)) for v in ('front', 'side', 'top', 'persp')]
    Wt = max(views[0].width + views[1].width, views[2].width + views[3].width, 1000) + 10
    Ht = max(views[0].height, views[1].height) + max(views[2].height, views[3].height)
    sheet = Image.new('RGB', (Wt + 10, Ht + 60), (255, 255, 255))
    sheet.paste(views[0], (0, 0)); sheet.paste(views[1], (views[0].width + 10, 0))
    y2 = max(views[0].height, views[1].height) + 10
    sheet.paste(views[2], (0, y2)); sheet.paste(views[3], (views[2].width + 10, y2))
    b = obj['bounds']
    size = [b['max'][k] - b['min'][k] for k in range(3)]
    info = 'size %.3f x %.3f x %.3f m (w x h x d)   min %s  max %s   top surface %s m   origin %s' % (
        size[0], size[1], size[2], b['min'], b['max'], obj.get('surface_height'), obj.get('origin'))
    ImageDraw.Draw(sheet).text((6, Ht + 22), info, fill=(0, 0, 0), font=_font(15))
    path = os.path.join(OUT, 'check_%s.png' % loc)
    sheet.save(path)
    print('%-16s %-34s w %.3f h %.3f d %.3f  min %s max %s  top %s  load %.2fs  -> %s' % (
        loc, obj['name'], size[0], size[1], size[2], b['min'], b['max'], obj.get('surface_height'), t_load, path))
    return sheet


if __name__ == '__main__':
    names = sys.argv[1:] or DEFAULT
    overview = 'check_overview.png'
    if names == ['--all']:
        names, overview = list(objmesh.example_objects()), 'check_overview_all.png'
    sheets = []
    for n in names:
        try:
            s = check(n)
        except Exception as ex:
            import traceback; traceback.print_exc()
            print('%-16s FAILED %r' % (n, ex)); s = None
        if s is not None:
            sheets.append((n, s))
    if len(sheets) > 1:
        thumbs = []
        for n, s in sheets:
            t = s.copy(); t.thumbnail((700, 560)); thumbs.append(t)
        cols = 3
        rows = (len(thumbs) + cols - 1) // cols
        ov = Image.new('RGB', (cols * 710, rows * 570), (255, 255, 255))
        for k, t in enumerate(thumbs):
            ov.paste(t, ((k % cols) * 710, (k // cols) * 570))
        ov.save(os.path.join(OUT, overview))
