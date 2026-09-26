"""Sim body shape: apply a sim's physique, sliders (SimModifiers) and sculpts to GEOM meshes.

How the game does it (formats as in TS4 SimRipper by CmarNYC and s4pi):
  SimModifier  SMOD 0xC5F6763E  -> BGEO key (delay-load list), DMap shape + DMap normal keys, BOND (bone delta) key
  Sculpt       0x9D1AB874       -> same three kinds of morph + textures; one sculpt per face region
  DMap         0xDB43E069       deformer map: a 2D grid of xyz deltas addressed by the mesh's SECOND uv set (uv1);
                                x = |W*u| (left half mirrored, x delta negated when the vertex has x < 0), y = H*v.
                                Each texel has a skin-tight delta and a robe delta blended by vertex tag bits 0-5;
                                vertex tag bits 8-15 /64 scale the whole morph. position -= delta * weight.
  BGEO         0x067CAA11       blend geometry: per-vertex-ID position/normal deltas (heads), position += delta * weight
  BOND         0x0355E0A6       bone delta: offset/scale/rotation of a rig bone; vertices move with their skin weight
                                on that bone and its descendants (pivot = bone's bind-pose world position).
Physique (SimData.physique "heavy,fit,lean,bony,pregnant,hips_wide,hips_narrow,waist_wide,waist_narrow") uses the
DMaps named <prefix>Body_Heavy_Shape / _Normals etc. (prefix yf/ym/ef/em/cu/pu); elders also get <e?>Body_Average.
Order of application: BGEO, then DMaps, then BONDs (each BOND also moves the rig for the next one), as SimRipper.

Resources are looked up in the game (delta builds before full builds, all packs) and in Mods + Mods_parked
(custom sliders override the game). Indexes are cached in cache/tray/index_morph.* and index_parts.*
(rebuilt when any package's mtime/size changes: ~11 s morph types, ~16 s CAS parts incl. Mods_parked).

Entry points: resolve_morphs(spec) -> ops, apply_modifiers(mesh, modifiers, 'yf'), morph_body(gamedata.body(f), spec).
"""
import glob, json, os, struct, threading, time

import numpy as np

from dbpf import read_index, read_resource

from gamefind import HOME, SIMS_DIR
HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(HERE, '..', 'cache', 'tray')

T_CASP, T_GEOM, T_SMOD, T_DMAP, T_BGEO, T_BOND, T_SCULPT, T_TONE = (
    0x034AEECB, 0x015A1849, 0xC5F6763E, 0xDB43E069, 0x067CAA11, 0x0355E0A6, 0x9D1AB874, 0x0354796A)
MORPH_TYPES = (T_SMOD, T_DMAP, T_BGEO, T_BOND, T_SCULPT, T_TONE)
PART_TYPES = (T_CASP, T_GEOM)

PHYSIQUE_NAMES = ['Body_Heavy', 'Body_Fit', 'Body_Lean', 'Body_Bony', 'Body_Pregnant',
                  'Hips_Wide', 'Hips_Narrow', 'Waist_Wide', 'Waist_Narrow']
PHYSIQUE_KEYS = ['heavy', 'fit', 'lean', 'bony', 'pregnant', 'hips_wide', 'hips_narrow', 'waist_wide', 'waist_narrow']
# SimRegion (SMOD/Sculpt): only EARS/TAIL restrict which parts a morph touches
REGIONS = {0: 'EYES', 1: 'NOSE', 2: 'MOUTH', 3: 'CHEEKS', 4: 'CHIN', 5: 'JAW', 6: 'FOREHEAD', 8: 'BROWS', 9: 'EARS',
           10: 'HEAD', 12: 'FULLFACE', 14: 'CHEST', 15: 'UPPERCHEST', 16: 'NECK', 17: 'SHOULDERS', 18: 'UPPERARM',
           19: 'LOWERARM', 20: 'HANDS', 21: 'WAIST', 22: 'HIPS', 23: 'BELLY', 24: 'BUTT', 25: 'THIGHS', 26: 'LOWERLEG',
           27: 'FEET', 28: 'BODY', 29: 'UPPERBODY', 30: 'LOWERBODY', 31: 'TAIL', 32: 'FUR', 33: 'FORELEGS',
           34: 'HINDLEGS', 99: 'ALL'}
# base-game CAS parts the animator's nude bodies are built from (instance -> name, verified at load time)
NUDE_CASP = {'yfTop_Nude': 0x198C, 'yfShoes_Nude': 0x198F, 'yfBottom_Nude': 0x1990, 'ymTop_Nude': 0x19A2,
             'ymShoes_Nude': 0x19A3, 'ymBottom_Nude': 0x19AE, 'yfHead': 0x1B41, 'ymHead': 0x229C}
# slider names from the game's CAS modifier tuning (<prefix>head<name>, e.g. yfheadChest_Big); used for labels only
MODIFIER_NAMES = (
    'Belly_Big Belly_Small Body_Heavy Body_Fit Body_Lean Body_Bony Waist_Wide Waist_Narrow Hips_Wide Hips_Narrow '
    'Chest_Big Chest_Small Chest_Droop Chest_Lift Chest_Expand Chest_Contract Chest_Deep Chest_Shallow UpperArm_Big '
    'UpperArm_Small LowerArm_Big LowerArm_Small Thighs_Big Thighs_Small LowerLeg_Big LowerLeg_Small Shoulders_Wide '
    'Shoulders_Narrow Neck_Thick Neck_Thin Neck_BackContract Neck_BackExtend Butt_Big Butt_Small Feet_Big Feet_Small '
    'Hands_Big Hands_Small Eyes_Big Eyes_Small Eyes_Far Eyes_Up Eyes_Down Eyes_RotateUp Eyes_RotateDown Eyes_forward '
    'Eyes_SocketsUp Eyes_SocketsDown Eyes_SocketsFar Eyes_SocketsClose Head_FaceForward Head_FaceBackward Head_Long '
    'Head_Short Head_WideBone Head_NarrowBone Nose_BumpUp Nose_BumpDown Nose_RotateOut Nose_RotateIn Nose_Long '
    'Nose_Down Nose_Up Nose_Big Nose_Small Nose_Wide Nose_Narrow Nose_BridgeWide Nose_BrowBridgeDown Nose_NostrilNarrow '
    'Mouth_Up Mouth_Down Mouth_Wide Mouth_Narrow Mouth_Forward Mouth_CurveUp Mouth_CurveDown Chin_Forward '
    'Chin_Backward Chin_Up Chin_Down Jaw_Wide Jaw_Underbite Jaw_Down Jaw_Up Brows_Up').split()


def _game_dir():
    import gamedata
    return gamedata.game_dir()


def _to_int(v):
    if isinstance(v, int):
        return v
    s = str(v).strip()
    return int(s, 16) if s.lower().startswith('0x') else int(s)


def fnv64(s):
    h = 0xCBF29CE484222325
    for b in s.lower().encode('utf-8'):
        h = ((h * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF) ^ b
    return h


# ------------------------------------------------------------------ resource index (game + CC)
def _package_sources(include_cc=True):
    g = _game_dir()
    cc = []
    if include_cc:
        for d in ('Mods', 'Mods_parked'):
            cc += sorted(glob.glob(os.path.join(SIMS_DIR, d, '**', '*.package'), recursive=True))
    delta = (sorted(glob.glob(os.path.join(g, 'Data', 'Client', 'ClientDeltaBuild*.package'))) +
             sorted(glob.glob(os.path.join(g, 'Delta', '*', 'ClientDeltaBuild*.package'))))
    full = (sorted(glob.glob(os.path.join(g, 'Data', 'Client', 'ClientFullBuild*.package'))) +
            sorted(p for p in glob.glob(os.path.join(g, '*', 'ClientFullBuild*.package'))
                   if os.path.basename(os.path.dirname(p))[:2] in ('EP', 'GP', 'SP', 'FP')))
    return cc + delta + full, len(cc)


class ResIndex:
    """(type, instance) and (type, group, instance) -> resource location, first hit in priority order wins."""
    _DT = np.dtype([('type', '<u4'), ('group', '<u4'), ('inst', '<u8'), ('pkg', '<u2'),
                    ('pos', '<u4'), ('size', '<u4'), ('mem', '<u4'), ('comp', '<u2')])

    def __init__(self, name, types, include_cc=True):
        self.name, self.types, self.include_cc = name, tuple(types), include_cc
        self._lock = threading.Lock()
        self._loaded = False

    def _load(self):
        with self._lock:
            if self._loaded:
                return
            t0 = time.time()
            paths, n_cc = _package_sources(self.include_cc)
            sig = []
            for p in paths:
                try:
                    st = os.stat(p)
                    sig.append([os.path.relpath(p, SIMS_DIR) if p.startswith(SIMS_DIR) else p, int(st.st_mtime), st.st_size])
                except OSError:
                    pass
            os.makedirs(CACHE_DIR, exist_ok=True)
            base = os.path.join(CACHE_DIR, 'index_%s' % self.name)
            rows = None
            if os.path.exists(base + '.json') and os.path.exists(base + '.npy'):
                try:
                    with open(base + '.json', encoding='utf-8') as f:
                        meta = json.load(f)
                    if meta.get('signature') == sig and meta.get('types') == list(self.types):
                        rows = np.load(base + '.npy')
                except Exception:
                    rows = None
            if rows is None:
                chunks = []
                for k, (rel, _, _) in enumerate(sig):
                    p = rel if os.path.isabs(rel) else os.path.join(SIMS_DIR, rel)
                    try:
                        entries = read_index(p)
                    except Exception:
                        continue                                  # empty / damaged package
                    sel = [e for e in entries if e['type'] in self.types]
                    if not sel:
                        continue
                    a = np.zeros(len(sel), self._DT)
                    a['type'] = [e['type'] for e in sel]; a['group'] = [e['group'] for e in sel]
                    a['inst'] = [e['inst'] for e in sel]; a['pkg'] = k
                    a['pos'] = [e['pos'] for e in sel]; a['size'] = [e['size'] for e in sel]
                    a['mem'] = [e['mem'] for e in sel]; a['comp'] = [e['comp'] for e in sel]
                    chunks.append(a)
                rows = np.concatenate(chunks) if chunks else np.zeros(0, self._DT)
                np.save(base + '.npy', rows)
                with open(base + '.json', 'w', encoding='utf-8') as f:
                    json.dump({'signature': sig, 'types': list(self.types), 'built': time.time()}, f)
            self.paths = [rel if os.path.isabs(rel) else os.path.join(SIMS_DIR, rel) for rel, _, _ in sig]
            self.n_cc = sum(1 for rel, _, _ in sig if not os.path.isabs(rel))
            self.rows = rows
            # per type: instances sorted (stable, so rows keep priority order among equal instances)
            self._by_type = {}
            for t in np.unique(rows['type']).tolist():
                rt = np.nonzero(rows['type'] == t)[0]
                order = np.argsort(rows['inst'][rt], kind='stable')
                self._by_type[t] = (rows['inst'][rt][order], rt[order])
            self._loaded = True
            self.load_time = time.time() - t0

    def find(self, t, i, g=None, where='any'):
        """First (highest priority) row; where = 'any' | 'game' | 'cc'."""
        self._load()
        hit = self._by_type.get(t)
        if hit is None:
            return None
        insts, ridx = hit
        i = np.uint64(i)
        lo, hi = np.searchsorted(insts, i, 'left'), np.searchsorted(insts, i, 'right')
        for r in ridx[lo:hi]:
            if g is not None and int(self.rows['group'][r]) != g:
                continue
            if where != 'any' and (int(self.rows['pkg'][r]) < self.n_cc) != (where == 'cc'):
                continue
            return self.rows[r]
        return None

    def count(self, t):
        self._load()
        hit = self._by_type.get(t)
        return 0 if hit is None else len(hit[0])

    def read(self, t, i, g=None, where='any'):
        row = self.find(t, i, g, where)
        if row is None:
            return None
        e = {'pos': int(row['pos']), 'size': int(row['size']), 'mem': int(row['mem']), 'comp': int(row['comp'])}
        return read_resource(self.paths[int(row['pkg'])], e)

    def origin(self, t, i, g=None):
        """'game', 'cc' or None."""
        row = self.find(t, i, g)
        if row is None:
            return None
        return 'cc' if int(row['pkg']) < self.n_cc else 'game'


MORPH_INDEX = ResIndex('morph', MORPH_TYPES)
PART_INDEX = ResIndex('parts', PART_TYPES)          # big (game + CC CAS parts); only loaded when parts are resolved


# ------------------------------------------------------------------ resource parsers
def _rcol_keys(d):
    """Common header of SMOD/Sculpt/BGEO/BOND: -> (keys dict, offset of the object data)."""
    ctx, n_pub, n_ext, n_delay, n_obj = struct.unpack_from('<5I', d, 0)
    p = 20
    itg = lambda q: (struct.unpack_from('<Q', d, q)[0], struct.unpack_from('<I', d, q + 8)[0], struct.unpack_from('<I', d, q + 12)[0])
    pub = [itg(p + 16 * k) for k in range(n_pub)]; p += 16 * n_pub
    ext = [itg(p + 16 * k) for k in range(n_ext)]; p += 16 * n_ext
    delay = [itg(p + 16 * k) for k in range(n_delay)]; p += 16 * n_delay
    objs = [struct.unpack_from('<II', d, p + 8 * k) for k in range(n_obj)]; p += 8 * n_obj
    start = objs[0][0] if objs and 0 < objs[0][0] < len(d) else p
    return {'public': pub, 'external': ext, 'delay': delay}, start


def _itg(d, p):
    inst, typ, grp = struct.unpack_from('<QII', d, p)
    return {'inst': inst, 'type': typ, 'group': grp}, p + 16


def parse_smod(d):
    keys, p = _rcol_keys(d)
    version, age_gender, region = struct.unpack_from('<3I', d, p); p += 12
    sub_region = 0
    if version >= 144:
        sub_region = struct.unpack_from('<I', d, p)[0]; p += 4
    link_tag = struct.unpack_from('<I', d, p)[0]; p += 4
    bond, p = _itg(d, p)
    dmap_shape, p = _itg(d, p)
    dmap_normal, p = _itg(d, p)
    n = struct.unpack_from('<I', d, p)[0]; p += 4
    bones = [struct.unpack_from('<If', d, p + 8 * k) for k in range(n)]
    return {'version': version, 'age_gender': age_gender, 'region': region, 'sub_region': sub_region,
            'link_tag': link_tag, 'bgeo': [k[0] for k in keys['delay'] if k[0]], 'bond': bond['inst'],
            'dmap_shape': dmap_shape['inst'], 'dmap_normal': dmap_normal['inst'], 'bone_entries': bones}


def parse_sculpt(d):
    keys, p = _rcol_keys(d)
    version, age_gender, region = struct.unpack_from('<3I', d, p); p += 12
    sub_region = 0
    if version > 0x60:
        sub_region = struct.unpack_from('<I', d, p)[0]; p += 4
    link_tag = struct.unpack_from('<I', d, p)[0]; p += 4
    texture, p = _itg(d, p)
    if version > 0x60:
        _, p = _itg(d, p); _, p = _itg(d, p)          # specular, bump map
    p += 1
    dmap_shape, p = _itg(d, p)
    dmap_normal, p = _itg(d, p)
    bond = {'inst': 0}
    if version > 0x60:
        bond, p = _itg(d, p)
    return {'version': version, 'age_gender': age_gender, 'region': region, 'sub_region': sub_region,
            'bgeo': [k[0] for k in keys['delay'] if k[0]], 'bond': bond['inst'],
            'dmap_shape': dmap_shape['inst'], 'dmap_normal': dmap_normal['inst'], 'texture': texture['inst']}


def parse_bond(d):
    keys, p = _rcol_keys(d)
    version, n = struct.unpack_from('<II', d, p); p += 8
    a = np.frombuffer(d, dtype=np.dtype([('hash', '<u4'), ('offset', '<f4', 3), ('scale', '<f4', 3), ('quat', '<f4', 4)]),
                      count=n, offset=p)
    return {'version': version, 'adjustments': a}


def parse_bgeo(d):
    keys, p = _rcol_keys(d)
    if d[p:p + 4] != b'BGEO':
        raise ValueError('not a BGEO')
    version, n_lod, n_verts, n_vec = struct.unpack_from('<4I', d, p + 4); p += 20
    lods = [struct.unpack_from('<3I', d, p + 12 * k) for k in range(n_lod)]; p += 12 * n_lod
    blend = np.frombuffer(d, '<i2', n_verts, p).astype(np.int32); p += 2 * n_verts
    vec = np.frombuffer(d, '<u2', 3 * n_vec, p).reshape(-1, 3)
    vec = (vec ^ np.uint16(0x8000)).view(np.int16).astype(np.float32) / 8000.0   # int16 stored with its sign bit flipped
    # LOD 0 only: running vector index = cumulative sum of the packed offsets
    base, nv0 = lods[0][0], lods[0][1]
    b0 = blend[:nv0]
    return {'lods': lods, 'index_base': base, 'n0': nv0, 'pos': (b0 & 1) > 0, 'nrm': (b0 & 2) > 0,
            'index': np.cumsum(b0 >> 2), 'vectors': vec}


def parse_dmap(d):
    """-> {'shape': bool, 'width', 'height', 'min_col', 'max_col', 'min_row', 'max_row', 'skin': (rows, cols, 3), 'robe': ...}"""
    version, dwidth, height, age_gender = struct.unpack_from('<4I', d, 0); p = 16
    species = 0
    if version > 5:
        species = struct.unpack_from('<I', d, p)[0]; p += 4
    physique, shape_or_normals = d[p], d[p + 1]; p += 2
    min_col, max_col, min_row, max_row = struct.unpack_from('<4I', d, p); p += 16
    robe_channel = d[p]; p += 1
    if version > 6:
        skin_min, skin_delta = struct.unpack_from('<2f', d, p); p += 8
        if robe_channel == 0:
            robe_min, robe_delta = struct.unpack_from('<2f', d, p); p += 8
        else:
            robe_min, robe_delta = skin_min, skin_delta
    else:
        skin_min, skin_delta = (-0.2, 0.4) if shape_or_normals == 0 else (-0.75, 1.5)
        robe_min, robe_delta = skin_min, skin_delta
    total = struct.unpack_from('<i', d, p)[0]; p += 4
    out = {'version': version, 'shape': shape_or_normals == 0, 'physique': physique, 'age_gender': age_gender,
           'species': species, 'width': dwidth // 2, 'height': height, 'min_col': min_col, 'max_col': max_col,
           'min_row': min_row, 'max_row': max_row, 'skin': None, 'robe': None}
    if total == 0 or max_col == 0:
        return out
    w = max_col - min_col + 1
    rows = max_row - min_row + 1
    skin = np.full((rows, w, 3), 0x80, np.uint8)
    robe = np.full((rows, w, 3), 0x80, np.uint8)
    for r in range(rows):
        size = struct.unpack_from('<H', d, p)[0]
        comp = d[p + 2]
        if comp == 2:                                             # no data
            p += size if size >= 3 else 3
            continue
        ch = d[p + 3]
        px = 6 if ch == 0 else 3
        if comp == 0:
            a = np.frombuffer(d, np.uint8, w * px, p + 4).reshape(w, px)
        else:                                                      # RLE: [run length][pixel] ...
            n_idx = d[p + 4]
            q = p + 5 + 4 * n_idx
            end = p + size
            runs = np.frombuffer(d, np.uint8, (end - q) // (px + 1) * (px + 1), q).reshape(-1, px + 1)
            lens = runs[:, 0].astype(np.int64)
            cs = np.cumsum(lens)
            nrun = int(np.searchsorted(cs, w) + 1)
            a = np.repeat(runs[:nrun, 1:], lens[:nrun], axis=0)[:w]
            if len(a) < w:
                a = np.vstack([a, np.full((w - len(a), px), 0x80, np.uint8)])
        skin[r] = a[:, :3]
        if ch == 0:
            robe[r] = a[:, 3:6]
        elif ch == 2:
            robe[r] = a[:, :3]
        p += size
    def decode(b, mn, dl):
        v = b.astype(np.float32) * (dl / 255.0) + mn
        v[b == 0x80] = 0.0
        return v
    out['skin'] = decode(skin, skin_min, skin_delta)
    out['robe'] = decode(robe, robe_min, robe_delta)
    return out


def read_geom(data):
    """Full GEOM (RCOL) reader: every vertex channel incl. uv1, tags and vertex ids, uv stitches and exact bone hashes."""
    ver, public, unused, n_ext, n_int = struct.unpack_from('<5I', data, 0)
    p = 20 + 16 * (n_int + n_ext)
    c = struct.unpack_from('<I', data, p)[0]
    if data[c:c + 4] != b'GEOM':
        raise ValueError('not a GEOM')
    version, tgi_off, tgi_size, shader = struct.unpack_from('<4I', data, c + 4)
    q = c + 20
    if shader:
        q += 4 + struct.unpack_from('<I', data, q)[0]
    merge_group, sort_order, n_verts, n_fmt = struct.unpack_from('<4I', data, q); q += 16
    fmts = [struct.unpack_from('<IIB', data, q + 9 * k) for k in range(n_fmt)]; q += 9 * n_fmt
    fields, uv_n = [], 0
    for k, (usage, dtype, size) in enumerate(fmts):
        name = 'c%d' % k
        if usage in (1, 2, 6) and size == 12:
            fields.append((name, '<f4', 3))
        elif usage == 3 and size == 8:
            fields.append((name, '<f4', 2))
        elif usage in (7, 10) and size == 4:
            fields.append((name, '<u4'))
        elif usage == 5 and size == 16:
            fields.append((name, '<f4', 4))
        else:
            fields.append((name, 'u1', size))
    vdt = np.dtype(fields)
    verts = np.frombuffer(data, vdt, n_verts, q); q += n_verts * vdt.itemsize
    out = {'version': version, 'shader': shader, 'formats': fmts, 'n': n_verts, 'uvsets': []}
    for k, (usage, dtype, size) in enumerate(fmts):
        col = verts['c%d' % k]
        if usage == 1:
            out['positions'] = col.astype(np.float32)
        elif usage == 2:
            out['normals'] = col.astype(np.float32)
        elif usage == 3 and size == 8:
            out['uvsets'].append(col.astype(np.float32))
        elif usage == 4:
            out['bones'] = col.astype(np.int32)
        elif usage == 5:
            out['weights'] = (col.astype(np.float32) / 255.0) if size == 4 else col.astype(np.float32)
        elif usage == 6:
            out['tangents'] = col.astype(np.float32)
        elif usage == 7:
            out['tags'] = col.astype(np.uint32)
        elif usage == 10:
            out['vertex_ids'] = col.astype(np.int64)
    n_sub = struct.unpack_from('<I', data, q)[0]; q += 4
    bpi = data[q]; q += 1
    n_idx = struct.unpack_from('<I', data, q)[0]; q += 4
    out['faces'] = np.frombuffer(data, '<u2' if bpi == 2 else '<u4', n_idx, q).astype(np.int32); q += n_idx * bpi
    stitches = {}
    if version >= 12:
        n = struct.unpack_from('<I', data, q)[0]; q += 4
        for _ in range(n):
            vi, cnt = struct.unpack_from('<ii', data, q); q += 8
            uvs = struct.unpack_from('<%df' % (2 * cnt), data, q); q += 8 * cnt
            stitches.setdefault(vi, (uvs[0], uvs[1]))
        if version >= 13:
            n = struct.unpack_from('<I', data, q)[0]; q += 4 + 6 * n
        n = struct.unpack_from('<I', data, q)[0]; q += 4 + n * (66 if version >= 14 else 63)
    nb = struct.unpack_from('<I', data, q)[0]; q += 4
    out['bone_hashes'] = list(struct.unpack_from('<%dI' % nb, data, q))
    out['uv_stitches'] = stitches
    return out


# ------------------------------------------------------------------ cached loaders
_cache = {}
_cache_lock = threading.Lock()


def _cached(key, build):
    with _cache_lock:
        if key in _cache:
            return _cache[key]
    v = build()
    with _cache_lock:
        _cache[key] = v
    return v


def smod(inst):
    def build():
        d = MORPH_INDEX.read(T_SMOD, inst)
        return parse_smod(d) if d else None
    return _cached(('smod', inst), build)


def sculpt(inst):
    def build():
        d = MORPH_INDEX.read(T_SCULPT, inst)
        return parse_sculpt(d) if d else None
    return _cached(('sculpt', inst), build)


def dmap(inst):
    def build():
        d = MORPH_INDEX.read(T_DMAP, inst)
        return parse_dmap(d) if d else None
    return _cached(('dmap', inst), build)


def bgeo(inst):
    def build():
        d = MORPH_INDEX.read(T_BGEO, inst)
        return parse_bgeo(d) if d else None
    return _cached(('bgeo', inst), build)


def bond(inst):
    def build():
        d = MORPH_INDEX.read(T_BOND, inst)
        return parse_bond(d) if d else None
    return _cached(('bond', inst), build)


def casp_name(d):
    p, n, shift = 12, 0, 0
    while True:
        b = d[p]; p += 1; n |= (b & 0x7F) << shift; shift += 7
        if not b & 0x80:
            break
    return d[p:p + n].decode('utf-16-be', 'replace')


def casp_tgis(d):
    off = struct.unpack_from('<I', d, 4)[0] + 8
    cnt = d[off]; q = off + 1; out = []
    for _ in range(cnt):
        inst, grp, typ = struct.unpack_from('<QII', d, q); q += 16
        out.append((typ, grp, inst))
    return out


def part_geom(casp_inst, where='any'):
    """LOD0 (most vertices) GEOM of a CAS part, read in full; where = 'any' (CC overrides game), 'game' or 'cc'.
    None when the part or its mesh is missing. The dict has 'origin' ('game'/'cc') and 'casp_name'."""
    def build():
        row = PART_INDEX.find(T_CASP, casp_inst, None, where)
        if row is None:
            return None
        d = PART_INDEX.read(T_CASP, casp_inst, None, where)
        origin = 'cc' if int(row['pkg']) < PART_INDEX.n_cc else 'game'
        best = None
        for t, g, i in casp_tgis(d):
            if t != T_GEOM:
                continue
            raw = PART_INDEX.read(t, i, g, origin) or PART_INDEX.read(t, i, g)
            if raw is None:
                continue
            try:
                gm = read_geom(raw)
            except Exception:
                continue
            if best is None or gm['n'] > best['n']:
                best = gm
        if best is not None:
            best['casp_name'] = casp_name(d)
            best['origin'] = origin
        return best
    return _cached(('geom', casp_inst, where), build)


def nude_part_geom(name, where='game'):
    """GEOM of one of the animator's nude-body parts by CAS part name. where='game' is the mesh gamedata.body()
    uses; 'any' gives what the game shows with the current Mods (e.g. WickedWhims' default-replacement bodies)."""
    return part_geom(NUDE_CASP[name], where) if name in NUDE_CASP else None


# ------------------------------------------------------------------ rig
def _qmul(a, b):
    x1, y1, z1, w1 = a[..., 0], a[..., 1], a[..., 2], a[..., 3]
    x2, y2, z2, w2 = b[..., 0], b[..., 1], b[..., 2], b[..., 3]
    return np.stack([w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2, w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
                     w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2, w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2], -1)


def _qconj(q):
    return q * np.array([-1, -1, -1, 1], q.dtype)


def _qmat(q):
    x, y, z, w = q[..., 0], q[..., 1], q[..., 2], q[..., 3]
    return np.stack([np.stack([1 - 2 * y * y - 2 * z * z, 2 * x * y - 2 * z * w, 2 * x * z + 2 * y * w], -1),
                     np.stack([2 * x * y + 2 * z * w, 1 - 2 * x * x - 2 * z * z, 2 * y * z - 2 * x * w], -1),
                     np.stack([2 * x * z - 2 * y * w, 2 * y * z + 2 * x * w, 1 - 2 * x * x - 2 * y * y], -1)], -2)


def _qclean(q):
    q = np.array(q, np.float64)
    n = np.dot(q, q)
    if n < 1e-12:
        return np.array([0, 0, 0, 1.0])
    if abs(n - 1) > 1e-6:
        s = q[0] ** 2 + q[1] ** 2 + q[2] ** 2
        q = q / np.sqrt(n) if s > 1 else np.array([q[0], q[1], q[2], np.sqrt(1 - s)])
    return q


def _fq_mul(a, b):
    x1, y1, z1, w1 = a; x2, y2, z2, w2 = b
    return (w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2, w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
            w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2, w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2)


def _fq_mat(q):
    x, y, z, w = q
    return ((1 - 2 * y * y - 2 * z * z, 2 * x * y - 2 * z * w, 2 * x * z + 2 * y * w),
            (2 * x * y + 2 * z * w, 1 - 2 * x * x - 2 * z * z, 2 * y * z - 2 * x * w),
            (2 * x * z - 2 * y * w, 2 * y * z + 2 * x * w, 1 - 2 * x * x - 2 * y * y))


class Rig:
    """Bind-pose rig state that BONDs modify (local pos/rot per bone; world matrices/rotations derived).

    Same math as SimRipper's RIG: local = R(q) + diag(scale - 1) with translation pos; global = parent * local.
    """

    def __init__(self, bones):
        self.bones = bones
        self.hash_index = {b['hash']: k for k, b in enumerate(bones)}
        self.parent = [b['parent'] for b in bones]
        self.children = [[] for _ in bones]
        for k, pa in enumerate(self.parent):
            if pa >= 0:
                self.children[pa].append(k)
        self.pos = [tuple(float(c) for c in b['pos']) for b in bones]
        self.rot = [tuple(_qclean(b['rot']).tolist()) for b in bones]
        self.scale = [tuple(float(c) for c in b.get('scale', (1, 1, 1))) for b in bones]
        self._desc = {}
        self.update()

    def update(self):
        n = len(self.bones)
        g_rot, g_m, g_t = [None] * n, [None] * n, [None] * n
        for k in range(n):
            r = _fq_mat(self.rot[k]); sc = self.scale[k]; p = self.pos[k]
            m = tuple(tuple(r[i][j] + ((sc[i] - 1) if i == j else 0.0) for j in range(3)) for i in range(3))
            pa = self.parent[k]
            if pa >= 0:
                M, T = g_m[pa], g_t[pa]
                g_m[k] = tuple(tuple(M[i][0] * m[0][j] + M[i][1] * m[1][j] + M[i][2] * m[2][j] for j in range(3))
                               for i in range(3))
                g_t[k] = tuple(M[i][0] * p[0] + M[i][1] * p[1] + M[i][2] * p[2] + T[i] for i in range(3))
                g_rot[k] = _fq_mul(g_rot[pa], self.rot[k])
            else:
                g_m[k], g_t[k], g_rot[k] = m, p, self.rot[k]
        self.g_rot = np.array(g_rot, np.float64)
        self.world = np.array(g_t, np.float64)

    def descendants(self, k):
        if k not in self._desc:
            out, stack = [], [k]
            while stack:
                b = stack.pop(); out.append(b); stack += self.children[b]
            self._desc[k] = out
        return self._desc[k]

    def morph_rotation(self, k):
        pa = self.parent[k]
        return self.g_rot[pa] if pa >= 0 else self.g_rot[k]

    def apply_bond(self, adj, weight):
        """Rig update after a BOND (SimRipper RIG.BoneMorpher): offset/rotate the bone, scale its descendants' offsets."""
        if not weight:
            return
        for a in adj:
            k = self.hash_index.get(int(a['hash']))
            if k is None:
                continue
            off, sc, q = [float(c) for c in a['offset']], [float(c) for c in a['scale']], _qclean(a['quat']).tolist()
            self.pos[k] = tuple(self.pos[k][i] + off[i] * weight for i in range(3))
            wq = (q[0] * weight, q[1] * weight, q[2] * weight, q[3])
            nq = sum(c * c for c in wq) ** 0.5
            self.rot[k] = _fq_mul(self.rot[k], tuple(c / nq for c in wq))
            f = [sc[i] * weight + 1 for i in range(3)]
            for c in self.descendants(k)[1:]:
                self.pos[c] = tuple(self.pos[c][i] * f[i] for i in range(3))
        self.update()

    def state(self):
        return list(self.pos), list(self.rot)

    def restore(self, st):
        self.pos, self.rot = list(st[0]), list(st[1])
        self.update()


def load_rig(rig_key='au'):
    import gamedata
    return Rig(gamedata.rig(rig_key)['bones'])


# ------------------------------------------------------------------ morph list
AGE_LETTER = {1: 'b', 128: 'i', 2: 'p', 4: 'c', 8: 'y', 16: 'y', 32: 'y', 64: 'e'}


def physique_prefix(age_gender):
    """'yf' style prefix: teen/young adult/adult -> y, elder e, child c, toddler p; + f/m (u below teen)."""
    if isinstance(age_gender, str):
        return age_gender[:2]
    age, gender = age_gender
    a = AGE_LETTER.get(age, 'y')
    return a + ('u' if a in 'pcib' else ('m' if gender in (4096, 'male', 'm') else 'f'))


def modifier_name(inst, prefix='yf'):
    """Best-effort label for a SimModifier instance (hash of a known slider name), else None."""
    table = _cached(('modnames', prefix), lambda: {fnv64(prefix + 'head' + n): n for n in MODIFIER_NAMES})
    return table.get(_to_int(inst))


def resolve_morphs(spec, age_gender='yf', include_face=True):
    """Turn a sim's shape data into primitive morph ops.

    spec: dict with any of
      'physique': {heavy: .., fit: ..} or list of 9 floats,
      'face_modifiers'/'body_modifiers'/'modifiers': [{modifier_instance, value}],
      'sculpts': [instance, ...]
    (sim_body_spec() output and trayfmt.household_sims() sims both work.) A plain list is treated as modifiers.
    -> [{'kind': 'dmap'|'bgeo'|'bond', 'inst' | 'shape'/'normal', 'weight', 'region', 'source'}], report
    """
    if isinstance(spec, list):
        spec = {'modifiers': spec}
    prefix = physique_prefix(age_gender)
    ops, report = [], {'missing': [], 'smods': 0, 'sculpts': 0, 'physique': 0}

    def add_resources(r, weight, source):
        region = r.get('region', 99)
        for b in r.get('bgeo', []):
            ops.append({'kind': 'bgeo', 'inst': b, 'weight': weight, 'region': region, 'source': source})
        if r.get('dmap_shape'):
            ops.append({'kind': 'dmap', 'shape': r['dmap_shape'], 'normal': r.get('dmap_normal') or 0,
                        'weight': weight, 'region': region, 'source': source})
        if r.get('bond'):
            ops.append({'kind': 'bond', 'inst': r['bond'], 'weight': weight, 'region': region, 'source': source})

    # elders always wear the "average" elder body
    if prefix[0] == 'e':
        sh, nm = fnv64(prefix + 'Body_Average_Shape'), fnv64(prefix + 'Body_Average_Normals')
        if MORPH_INDEX.find(T_DMAP, sh) is not None:
            ops.append({'kind': 'dmap', 'shape': sh, 'normal': nm, 'weight': 1.0, 'region': 99, 'source': 'elder'})
    phys = spec.get('physique')
    if phys is not None:
        vals = [phys.get(k, 0.0) for k in PHYSIQUE_KEYS] if isinstance(phys, dict) else list(phys)
        for k, v in enumerate(vals[:len(PHYSIQUE_NAMES)]):
            if v and v > 0:
                name = prefix + PHYSIQUE_NAMES[k]
                sh, nm = fnv64(name + '_Shape'), fnv64(name + '_Normals')
                if MORPH_INDEX.find(T_DMAP, sh) is None:
                    report['missing'].append(name + '_Shape')
                    continue
                ops.append({'kind': 'dmap', 'shape': sh, 'normal': nm, 'weight': float(v), 'region': 99,
                            'source': 'physique:' + PHYSIQUE_KEYS[k]})
                report['physique'] += 1
    # sculpts: one per region, the last listed wins
    by_region = {}
    for s in spec.get('sculpts', []) if include_face else []:
        inst = _to_int(s['sculpt_instance'] if isinstance(s, dict) else s)
        sc = sculpt(inst)
        if sc is None:
            report['missing'].append('sculpt 0x%016x' % inst)
            continue
        by_region[sc['region']] = (inst, sc)
    for region, (inst, sc) in by_region.items():
        add_resources(sc, 1.0, 'sculpt:0x%016x' % inst)
        report['sculpts'] += 1
    if 'modifiers' in spec:                  # combined list (sim_body_spec) wins over the separate face/body lists
        mods = [m for m in spec['modifiers'] if include_face or not (isinstance(m, dict) and m.get('kind') == 'face')]
    else:
        mods = (list(spec.get('face_modifiers', [])) if include_face else []) + list(spec.get('body_modifiers', []))
    for m in mods:
        inst = _to_int(m['modifier_instance'] if isinstance(m, dict) else m[0])
        value = float(m['value'] if isinstance(m, dict) else m[1])
        if not value:
            continue
        sm = smod(inst)
        if sm is None:
            report['missing'].append('smod 0x%016x' % inst)
            continue
        add_resources(sm, value, 'smod:0x%016x' % inst)
        report['smods'] += 1
    return ops, report


# ------------------------------------------------------------------ applying
def _sample_dmap(dm, uv1, mirror, robe_mult):
    """Deltas of one deformer map at the given uv1 coordinates (N,2) -> (N,3) (zeros outside the map)."""
    n = len(uv1)
    out = np.zeros((n, 3), np.float32)
    if dm is None or dm['skin'] is None:
        return out
    x = np.trunc(np.abs(dm['width'] * uv1[:, 0]) - dm['min_col'] - 0.5).astype(np.int64)
    y = np.trunc(dm['height'] * uv1[:, 1] - dm['min_row'] - 0.5).astype(np.int64)
    rows, cols = dm['skin'].shape[:2]
    y = np.where(y > rows - 1, np.int64(max(rows - 1, 0)), y)
    ok = (x >= 0) & (x < cols) & (y >= 0) & (y < rows)
    xi, yi = x[ok], y[ok]
    s = dm['skin'][yi, xi].copy()
    r = dm['robe'][yi, xi].copy()
    flip = mirror[ok]
    s[flip, 0] *= -1; r[flip, 0] *= -1
    rm = robe_mult[ok][:, None]
    out[ok] = s * (1 - rm) + r * rm
    return out


_names_lock = threading.Lock()
_cc_names = None


def _active_casp_names():
    """{CAS part name: [instance]} for the parts in Mods (active CC) and the WickedWhims tuning package."""
    global _cc_names
    with _names_lock:
        if _cc_names is None:
            names = {}
            pk = glob.glob(os.path.join(SIMS_DIR, 'Mods', '**', '*.package'), recursive=True)
            pk += glob.glob(os.path.join(SIMS_DIR, 'Mods_parked', '**', 'TURBODRIVER_WickedWhims_Tuning.package'),
                            recursive=True)
            for path in pk:
                try:
                    entries = read_index(path)
                except Exception:
                    continue
                for e in entries:
                    if e['type'] == T_CASP:
                        try:
                            names.setdefault(casp_name(read_resource(path, e)), []).append(e['inst'])
                        except Exception:
                            pass
            _cc_names = names
        return _cc_names


def casp_instances_by_name(name):
    """Candidate CAS part instances for a part name (known game nude parts + active CC / WickedWhims)."""
    out = list(_active_casp_names().get(name, []))
    if name in NUDE_CASP:
        out.append(NUDE_CASP[name])
    return out


def mesh_extras(mesh):
    """The full GEOM (uv1, tags, vertex ids, uv stitches) behind a gamedata.body() mesh: same part name, same
    vertex count and positions. Looked up in the game and in CC (WickedWhims replaces some nude parts)."""
    pos = np.asarray(mesh['positions'], np.float64).reshape(-1, 3)
    for inst in casp_instances_by_name(mesh.get('part', '')):
        for where in ('any', 'game', 'cc'):
            g = part_geom(inst, where)
            if g is not None and g['n'] == len(pos) and np.allclose(g['positions'], pos, atol=2e-3):
                return g
    return None


def _mesh_arrays(mesh, rig=None):
    """Normalise a mesh dict (gamedata.body() flat lists, or read_geom() arrays) into numpy arrays + extras."""
    pos = np.asarray(mesh['positions'], np.float64).reshape(-1, 3)
    nrm = np.asarray(mesh['normals'], np.float64).reshape(-1, 3) if len(mesh.get('normals', [])) else np.zeros_like(pos)
    n = len(pos)
    extra = mesh
    if ('uv1' not in mesh and 'uvsets' not in mesh) or 'tags' not in mesh:
        extra = mesh_extras(mesh) or mesh
    uvsets = extra.get('uvsets')
    uv1 = np.asarray(mesh['uv1'], np.float64).reshape(-1, 2) if 'uv1' in mesh else (
        uvsets[1].astype(np.float64) if uvsets is not None and len(uvsets) > 1 else None)
    tags = np.asarray(extra['tags'], np.int64) if 'tags' in extra else None
    vids = np.asarray(extra['vertex_ids'], np.int64) if 'vertex_ids' in extra else None
    stitches = extra.get('uv_stitches') or {}
    if uv1 is not None and stitches:
        uv1 = uv1.copy()
        for vi, uv in stitches.items():
            if 0 <= vi < n:
                uv1[vi] = uv
    # skinning as rig bone indices
    bones = weights = None
    if 'bones' in mesh and 'weights' in mesh:
        b = np.asarray(mesh['bones'], np.int64).reshape(-1, 4)
        w = np.asarray(mesh['weights'], np.float64).reshape(-1, 4)
        if 'bone_hashes' in mesh and rig is not None:            # GEOM-local indices -> rig indices
            remap = np.array([rig.hash_index.get(h, -1) for h in mesh['bone_hashes']] + [-1], np.int64)
            b = remap[np.clip(b, 0, len(remap) - 1)]
        bones, weights = b, w
    return {'pos': pos, 'nrm': nrm, 'uv1': uv1, 'tags': tags, 'vids': vids, 'bones': bones, 'weights': weights}


def _apply_blend_and_maps(m, ops):
    """BGEO then DMap ops on one mesh (arrays from _mesh_arrays); returns new pos, nrm and counts."""
    pos, nrm = m['pos'].copy(), m['nrm'].copy()
    orig_x = m['pos'][:, 0]
    stats = {'bgeo': 0, 'dmap': 0, 'bond': 0}
    vids, uv1, tags = m['vids'], m['uv1'], m['tags']
    if vids is not None:                                         # 1. BGEO (meshes with vertex ids: heads)
        for op in ops:
            if op['kind'] != 'bgeo':
                continue
            bg = bgeo(op['inst'])
            if bg is None:
                continue
            k = vids - bg['index_base']
            ok = (k >= 0) & (k < bg['n0'])
            if not ok.any():
                continue
            vi = np.nonzero(ok)[0]; bi = k[ok]
            idx = bg['index'][bi]
            hp, hn = bg['pos'][bi], bg['nrm'][bi]
            w = op['weight']
            pos[vi[hp]] += bg['vectors'][idx[hp]] * w
            nidx = idx[hn] + hp[hn].astype(np.int64)
            nrm[vi[hn]] += bg['vectors'][np.clip(nidx, 0, len(bg['vectors']) - 1)] * w
            stats['bgeo'] += 1
    if uv1 is not None and tags is not None:                     # 2. DMaps (need uv1 + tags)
        mirror = orig_x < 0
        robe_mult = (tags & 0x3F).astype(np.float32) / 63.0
        vert_w = np.minimum(((tags & 0xFF00) >> 8).astype(np.float32) / 64.0, 1.0)
        for op in ops:
            if op['kind'] != 'dmap' or op['region'] in (9, 31):   # EARS / TAIL morphs only touch ears / tails
                continue
            ds = dmap(op['shape'])
            if ds is None or ds['skin'] is None:
                continue
            f = (op['weight'] * vert_w)[:, None]
            pos -= _sample_dmap(ds, uv1, mirror, robe_mult) * f
            if op.get('normal'):
                dn = dmap(op['normal'])
                if dn is not None and dn['skin'] is not None:
                    nrm -= _sample_dmap(dn, uv1, mirror, robe_mult) * f
            stats['dmap'] += 1
    return pos, nrm, stats


def _bond_transforms(adj, rig):
    """World-space pivot/offset/scale/rotation of each adjustment of one BOND for the current rig state."""
    out = []
    nb = len(rig.bones)
    for a in adj:
        k = rig.hash_index.get(int(a['hash']))
        if k is None:
            continue
        isdesc = np.zeros(nb + 1, bool); isdesc[rig.descendants(k)] = True
        R = rig.morph_rotation(k)
        world_scale = np.linalg.norm(_qmat(R) @ np.diag(np.array(a['scale'], np.float64) + 1), axis=1) - 1
        world_off = _qmul(_qmul(R, np.array([*a['offset'], 0.0])), _qconj(R))[:3]
        world_q = _qmul(_qmul(R, _qclean(a['quat'])), _qconj(R))
        out.append((isdesc, rig.world[k].copy(), world_scale, world_off, world_q))
    return out


def _apply_bond_mesh(pos, nrm, bones, weights, transforms, weight, nb):
    """SimRipper GEOM.BoneMorpher for each adjustment: vertices move with their weight on the bone's subtree,
    around the bone's world position. Positions update after the whole BOND, normals right away."""
    delta = np.zeros_like(pos)
    bsafe = np.where(bones >= 0, bones, nb)
    for isdesc, piv, world_scale, world_off, world_q in transforms:
        bw = (weights * isdesc[bsafe]).sum(1)
        sel = np.nonzero(bw > 0)[0]
        if not len(sel):
            continue
        aw = bw[sel] * weight
        wq = np.empty((len(sel), 4))
        wq[:, :3] = world_q[:3] * aw[:, None]; wq[:, 3] = world_q[3]
        wq /= np.linalg.norm(wq, axis=1, keepdims=True)
        M = _qmat(wq)
        M[:, [0, 1, 2], [0, 1, 2]] += world_scale[None, :] * aw[:, None]   # SimRipper's "scale.X - 2y^2 - 2z^2"
        newp = np.einsum('mij,mj->mi', M, pos[sel] - piv) + world_off[None, :] * aw[:, None] + piv
        delta[sel] += newp - pos[sel]
        try:
            nn = np.einsum('mij,mj->mi', np.linalg.inv(M).transpose(0, 2, 1), nrm[sel])
            nrm[sel] = nn / np.maximum(np.linalg.norm(nn, axis=1, keepdims=True), 1e-9)
        except np.linalg.LinAlgError:
            pass
    pos += delta


def _run(meshes, ops, rig):
    """All ops on a list of _mesh_arrays() dicts; BONDs go through one shared, progressively updated rig."""
    results = []
    for m in meshes:
        results.append(list(_apply_blend_and_maps(m, ops)))
    nbond = 0
    for op in ops:
        if op['kind'] != 'bond' or not op['weight']:
            continue
        bd = bond(op['inst'])
        if bd is None:
            continue
        tr = _bond_transforms(bd['adjustments'], rig)
        for m, r in zip(meshes, results):
            if m['bones'] is not None:
                _apply_bond_mesh(r[0], r[1], m['bones'], m['weights'], tr, op['weight'], len(rig.bones))
                r[2]['bond'] += 1
        rig.apply_bond(bd['adjustments'], op['weight'])
        nbond += 1
    for r in results:
        lens = np.linalg.norm(r[1], axis=1, keepdims=True)
        r[1] = np.where(lens > 1e-8, r[1] / np.maximum(lens, 1e-8), r[1])
    return results, nbond


def _rig_key(age_gender):
    return {'c': 'cu', 'p': 'pu', 'i': 'iu'}.get(physique_prefix(age_gender)[0], 'au')


def apply_modifiers(geom_mesh, modifiers, age_gender='yf', rig=None, ops=None):
    """Deform one mesh by a sim's shape.

    geom_mesh: a mesh from gamedata.body(frame)['meshes'] (flat lists; uv1/tags/vertex ids come from the same GEOM,
               found by part name) or a read_geom()/part_geom() dict (arrays + own bone hashes).
    modifiers: [{modifier_instance, value}] or a spec dict (physique, face/body modifiers, sculpts; see resolve_morphs).
    age_gender: 'yf' / 'ym' / 'ef' / 'cu' ... (physique DMap prefix) or (age_id, gender_id).
    rig: a Rig (load_rig('au')); BONDs need it and move it. A fresh bind-pose rig is used when omitted.
         To morph several meshes of one sim consistently use morph_body() (or pass the same fresh rig per mesh).
    -> {'positions': [...], 'normals': [...], 'stats': {...}}  (flat lists like the input)
    """
    if ops is None:
        ops, _ = resolve_morphs(modifiers, age_gender)
    if rig is None:
        rig = load_rig(_rig_key(age_gender))
    m = _mesh_arrays(geom_mesh, rig)
    (res,), _ = _run([m], ops, rig)
    return {'positions': np.round(res[0], 5).ravel().tolist(), 'normals': np.round(res[1], 4).ravel().tolist(),
            'stats': res[2]}


def morph_body(body, spec, age_gender=None, extra_ops=()):
    """Deform every mesh of a gamedata.body(frame) dict for one sim (spec = sim_body_spec() or a trayfmt sim).
    extra_ops: more morph ops (e.g. genital_ops()), applied after the sim's own.

    Returns a copy of body with positions/normals replaced, plus 'morph': {ops, bonds, stats per mesh, missing,
    seconds, rig_world (bind-pose bone world positions after the BONDs), rig_local (their local positions)}.
    """
    t0 = time.time()
    age_gender = age_gender or (spec.get('prefix') if isinstance(spec, dict) else None) or body.get('frame', 'yf')
    ops, report = resolve_morphs(spec or {}, age_gender)
    ops = list(ops) + list(extra_ops or ())
    rig = load_rig(body.get('rig', 'au'))
    meshes = [_mesh_arrays(m, rig) for m in body['meshes']]
    results, nbond = _run(meshes, ops, rig)
    out = dict(body)
    out['meshes'] = []
    for m, (p, n, st) in zip(body['meshes'], results):
        mm = dict(m)
        mm['positions'] = np.round(p, 5).ravel().tolist()
        mm['normals'] = np.round(n, 4).ravel().tolist()
        out['meshes'].append(mm)
    out['morph'] = {'ops': len(ops), 'bonds': nbond,
                    'stats': {m.get('part', str(k)): r[2] for k, (m, r) in enumerate(zip(body['meshes'], results))},
                    'missing': report['missing'], 'report': report, 'seconds': round(time.time() - t0, 3),
                    'rig_world': np.round(rig.world, 5).tolist(),
                    'rig_local': [[round(float(c), 6) for c in p] for p in rig.pos]}
    return out


# ------------------------------------------------------------------ WickedWhims' genital sliders (other bodies)
# SMOD instance for + and - of each slider, from TURBODRIVER_WickedWhims_Tuning.package (spec_bodies Appendix E).
# Every one is a BOND on the penis / testicle bones, age-gender flags 0x3078 (young adult, adult, elder).
WW_GENITAL = {
    'length': (0x8671C77071F2AFF9, 0x8840355462D87DC7),     # Base01, Mid, Mid01 +8.5 mm / -10 mm along the shaft
    'girth': (0x98C42024FE7A347B, 0xB370D15F6C548B1F),      # Base scale x,z +0.2 (Tip y +0.2) / -0.1
    'balls': (0x421760CDF81556E4, 0x87786E997C342226),      # Penis_Testicles scale x,z +-0.3
    'apart': (0xAEA3835E81F8D39B, 0xFFA5A8DF04BA4B95),      # L/R testicle x +-1 cm
    'tilt': (0x9239ADCB049D13FE, 0xC01BD87DBC759F6E),       # Penis_Base turns about z +-11.4 deg (+ aims up)
}


def genital_ops(values):
    """{'length': -1..1, ...} -> bond ops like resolve_morphs' (kind 'bond', inst = the SMOD's BOND, weight = |v|).
    A value is clamped to -1..1; the '+' SMOD is used above 0, the '-' one below. Unknown keys are ignored."""
    ops = []
    for key, v in (values or {}).items():
        if key not in WW_GENITAL:
            continue
        try:
            v = max(-1.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            continue
        if not v:
            continue
        s = smod(WW_GENITAL[key][0 if v > 0 else 1])
        if s and s['bond']:
            ops.append({'kind': 'bond', 'inst': s['bond'], 'weight': abs(v), 'region': 99, 'source': 'ww:' + key})
    return ops


def rest_delta(rig_key, rig_world, threshold=1e-4):
    """How far each bone's rest (bind) position moved, as a change of its local position in the preview's skeleton.
    The preview keeps every bone's rest rotation, so a BOND that turns or scales a bone (tilt, girth) still puts its
    children where the game has them: each bone's new local position is taken from the morphed rig's world position,
    through its parent's unchanged rotation. -> {bone name: [dx, dy, dz]} (moves under `threshold` m left out)."""
    import gamedata
    bones = gamedata.rig(rig_key)['bones']
    base = Rig(bones)
    world = np.asarray(rig_world, np.float64)
    out = {}
    for k, b in enumerate(bones):
        pa = b['parent']
        if pa < 0:
            new_local = world[k]
        else:
            rot = _qmat(np.asarray(base.g_rot[pa], np.float64))
            new_local = rot.T @ (world[k] - world[pa])
        d = new_local - np.asarray(base.pos[k], np.float64)
        if float(np.linalg.norm(d)) > threshold:
            out[b['name']] = [round(float(c), 6) for c in d]
    return out


def body_variant(body, spec=None, genital=None, age_gender=None):
    """morph_body with WickedWhims' genital sliders on top (genital = {'length': -1..1, ...}); the result also has
    'rest_delta' ({bone: [dx, dy, dz]}, see rest_delta()), so the preview skeleton bends at the moved joints."""
    out = morph_body(body, spec or {}, age_gender, extra_ops=genital_ops(genital))
    out['rest_delta'] = rest_delta(body.get('rig', 'au'), out['morph']['rig_world'])
    return out


# ------------------------------------------------------------------ checking helpers
def export_obj(path, body):
    with open(path, 'w') as f:
        base = 1
        for m in body['meshes']:
            f.write('o %s\n' % m.get('part', 'mesh'))
            P = np.asarray(m['positions']).reshape(-1, 3)
            for v in P:
                f.write('v %.5f %.5f %.5f\n' % tuple(v))
            F = np.asarray(m['faces']).reshape(-1, 3) + base
            for a, b, c in F:
                f.write('f %d %d %d\n' % (a, b, c))
            base += len(P)


def silhouette(bodies, labels, path, size=420):
    """Front (x/y) and side (z/y) orthographic silhouettes of several bodies side by side (PIL)."""
    from PIL import Image, ImageDraw
    allp = np.concatenate([np.asarray(m['positions']).reshape(-1, 3) for b in bodies for m in b['meshes']])
    lo, hi = allp.min(0), allp.max(0)
    scale = (size - 40) / (hi[1] - lo[1])
    cols = [(60, 110, 200), (200, 70, 60), (60, 160, 90), (170, 110, 30)]
    panel_w = int(max(hi[0] - lo[0], hi[2] - lo[2]) * scale) + 40
    img = Image.new('RGB', (panel_w * 2 * len(bodies), size + 20), 'white')
    dr = ImageDraw.Draw(img)
    for bi, b in enumerate(bodies):
        for view in range(2):
            ox = (bi * 2 + view) * panel_w + panel_w // 2
            for m in b['meshes']:
                P = np.asarray(m['positions']).reshape(-1, 3)
                F = np.asarray(m['faces']).reshape(-1, 3)
                hx = P[:, 0] if view == 0 else P[:, 2]
                X = ox + hx * scale
                Y = size - 10 - (P[:, 1] - lo[1]) * scale
                for a, c, d in F:
                    dr.polygon([(X[a], Y[a]), (X[c], Y[c]), (X[d], Y[d])], fill=cols[bi % len(cols)])
            dr.text((ox - panel_w // 2 + 4, 2), '%s %s' % (labels[bi], 'front' if view == 0 else 'side'), fill='black')
    img.save(path)
    return path


def overlay(body_a, body_b, path, size=700):
    """Front + side outlines of two bodies drawn over each other (blue = a, red = b)."""
    from PIL import Image, ImageDraw, ImageChops
    allp = np.concatenate([np.asarray(m['positions']).reshape(-1, 3) for b in (body_a, body_b) for m in b['meshes']])
    lo, hi = allp.min(0), allp.max(0)
    scale = (size - 40) / (hi[1] - lo[1])
    panel_w = int(max(hi[0] - lo[0], hi[2] - lo[2]) * scale) + 60
    layers = []
    for b in (body_a, body_b):
        im = Image.new('L', (panel_w * 2, size + 20), 0)
        dr = ImageDraw.Draw(im)
        for view in range(2):
            ox = view * panel_w + panel_w // 2
            for m in b['meshes']:
                P = np.asarray(m['positions']).reshape(-1, 3)
                F = np.asarray(m['faces']).reshape(-1, 3)
                X = ox + (P[:, 0] if view == 0 else P[:, 2]) * scale
                Y = size - 10 - (P[:, 1] - lo[1]) * scale
                for a, c, d in F:
                    dr.polygon([(X[a], Y[a]), (X[c], Y[c]), (X[d], Y[d])], fill=255)
        layers.append(im)
    a, b = layers
    bg = Image.new('RGB', a.size, 'white')
    both = ImageChops.multiply(a, b)
    out = Image.composite(Image.new('RGB', a.size, (150, 150, 150)), bg, both)
    out = Image.composite(Image.new('RGB', a.size, (220, 40, 40)), out, ImageChops.subtract(b, a))
    out = Image.composite(Image.new('RGB', a.size, (40, 80, 220)), out, ImageChops.subtract(a, b))
    out.save(path)
    return path


if __name__ == '__main__':
    # python morph.py "Goldbloom" "Mavis"  -> OBJ before/after + front/side overlays in cache/tray
    import sys
    import gamedata, trayfmt
    for q in sys.argv[1:] or ['Goldbloom']:
        hits = trayfmt.find_sims(q)
        if not hits:
            print('no sim matches', q); continue
        tid, k, name = hits[0]
        spec = trayfmt.sim_body_spec(tid, k)
        if spec['frame'] not in gamedata.BODIES:
            print(name, 'has no animator body frame yet:', spec['frame']); continue
        body = gamedata.body(spec['frame'])
        out = morph_body(body, spec)
        tag = ''.join(c for c in name.lower() if c.isalnum())[:24] or 'sim'
        os.makedirs(CACHE_DIR, exist_ok=True)
        export_obj(os.path.join(CACHE_DIR, '%s_before.obj' % spec['frame']), body)
        export_obj(os.path.join(CACHE_DIR, '%s_after.obj' % tag), out)
        img = overlay(body, out, os.path.join(CACHE_DIR, 'ov_%s.png' % tag), size=600)
        print('%s (%s %s, frame %s): %d ops, %.2fs, missing %d -> %s' % (
            name, spec['age'], spec['gender'], spec['frame'], out['morph']['ops'], out['morph']['seconds'],
            len(out['morph']['missing']), img))
