"""Real Sims 4 furniture meshes (the objects WickedWhims animations are made on), at the game's exact size and origin.

    object_mesh(obj_def_id, lod=0, piece=0, state=None)
        -> {'name', 'meshes': [{'positions', 'normals', 'uvs', 'faces', 'texture', 'transparent', 'alpha_test',
            'water', 'skinned', 'skin': {'bones', 'rest', 'rq', 'idx', 'w'} (only when 'skinned': the mesh's rest
            pose and per-vertex blend weights, in the same object space as 'positions'), ...}], 'bounds': {'min',
            'max'}, 'surface_height', 'geometry_state', ...}  (JSON-cached)
    furniture_for_location(name)     -> object_mesh() of the object shown for a location (SHOWN, else WickedWhims'
                                        reference object), or None
    all_locations()                  -> [{'location', 'object_id', 'name', 'bounds', 'surface_height',
                                          'geometry_state', 'slots'}] for every location with a resolvable object
    prop_list()                      -> [{'guid', 'objName', 'name', 'uses', 'source'}]: the props the animation
                                          library uses that the game or Mods has (adults only), most used first
    props_missing(anim_id)           -> the prop GUIDs a library animation needs that are not installed
    mods_objects()                   -> custom-content furniture in Mods with a top to sit or lie on (+ its spots)

Objects are read from the game's packages, else from the packages in Mods (custom content: props, furniture) - the
two resource indexes _GAME (_index_v1.pkl) and _MODS (_mods_index_v1.pkl).

Seat and lying spots ('slots'): the object rig's _IKtarget_butt_N joints (seats; the joint's local +Z is the way a
seated sim faces) with their _IKtarget_L/R_foot_N foot spots, sorted into 'seat', 'edge' (a bed's side: feet on the
floor) and 'in' (sitting up in a bed); plus computed 'lie' spots on anything long and wide enough to lie on.
'surface_grid' is the top-most up-facing height per 5 cm cell (millimetres), for "is this point on the furniture".

Coordinates are game space in metres: Y up, a sim at rest faces +Z and +X is the sim's left. The origin is the point
WickedWhims places the actors at: `turbo_game_object.get_position(bone_name='b__ROOT__')` (the object's b__ROOT__
joint in its rest pose; the object's own position when the rig has no such joint), and the axes are the object's
orientation (WickedWhims only uses the object's yaw). For every reference object checked the b__ROOT__ joint sits at
the model origin, which is also the object's position / footprint origin: the centre of its footprint on the floor
(y = 0 is the floor the object stands on). Objects face +Z: a sofa's seat is on the +Z side of its back, a bed's
headboard is at -Z and its foot at +Z, a counter's front edge is at +Z.

Game formats as found (checked against the game's own files; layouts follow s4pi's RCOL wrappers):

- OBJD 0xC0DB5AE7: u16 version, u32 table offset -> u16 count, (u32 property id, u32 offset) pairs.
  0xE7F07786 name (u32 len + ascii), 0x8D20ACC6 model TGIs, 0xE206AE4F rig TGIs, 0xECD5A95F material variant name.
  A TGI list is u32 (4 x count), then per TGI: u32 instance high, u32 instance low, u32 type, u32 group.
- RCOL container (MODL, MLOD, ...): u32 version, public chunk count, 0, external count, internal count, internal
  ITGs (u64 inst, u32 type, u32 group), external ITGs, (u32 offset, u32 size) per internal chunk.
  A chunk reference is u32: high nibble 0 = public chunk, 1 = private chunk (index + public count), 2/3 = external
  resource (3 = delayed-load); low 28 bits = index + 1 (0 = none).
- MODL 0x01661233 (v0x300): bounds (6 f32), ..., LOD entries at the end, 20 bytes each: chunk ref, flags, u32 LOD
  id (0/1/2 = high/medium/low detail, 0x1000x = shadow LODs), min/max camera distance. LOD 0 is normally a separate
  MLOD resource (same instance, group 0), lower LODs live inside the MODL.
- MLOD 0x01D10F34 (v0x205): meshes: u32 size, name hash, material (MATD or MTST), VRTF, VBUF, IBUF refs, u32
  primitive type (low byte, 3 = triangle list) | flags << 8 (0x08 = drop shadow, 0x10 shadow caster, 0x40 pickable,
  0x1000 = rendered: meshes without it are invisible pick proxies),
  stream offset (bytes into VBUF), start vertex, start index, min vertex index, vertex count, primitive count, bounds,
  SKIN ref, joint hashes (u32 count + u32s), scale/offset ref (a small MATD with PosOffset/PosScale/UVOffset/UVScale),
  geometry states (u32 count + 20 bytes each), parent name, mirror plane (4 f32), u32 (v > 0x203).
- VRTF 0x01D0E723: 'VRTF', version, stride, element count, extended flag; elements (usage, usage index, format,
  offset) as bytes (u32/u32/u32/u8 when extended). A mesh without a VRTF (decals) uses the 52-byte default: float3
  position, float3 normal, float2 UV, UByte4 blend indices, UByte4 weights, float3 tangent. Most objects use a
  32-byte vertex (some 24/28 bytes without tangent/UV1; different formats share one VBUF):
      Position Short4 (xyz * PosScale + PosOffset; PosScale = 1/16383, w = 16383), Normal UByte4N ((b - 128) / 127,
      x y z order, 4th byte 128), UV0 Short2 (s / 32767 * UVScale + UVOffset, DirectX convention: v = 0 is the top
      row of the texture - load the PNG with texture.flipY = false, like the sims' skin), BlendIndex UByte4 (into the
      mesh's joint list), BlendWeight UByte4N, Tangent UByte4N, UV1 Short2 (lightmap).
- VBUF 0x01D0E6FB: 'VBUF', version, flags, swizzle ref, raw vertices (shared by all meshes of an MLOD).
- IBUF 0x01D0E70F: 'IBUF', version, flags (1 = differenced, 2 = 32-bit), u32, then int16 indices; differenced
  buffers store index[i] - index[i - 1] over the whole buffer (so a running sum gives absolute indices). Indices are
  relative to the mesh's first vertex (VBUF byte stream offset + start vertex x stride), counter-clockwise front
  faces.
- MTST 0x02019972: material set: default ref, then (MATD ref, state hash, material variant hash) - the variant is
  fnv32 of the OBJD's material variant name (e.g. 'set11-materialVariant'), state 0 = normal, 'Burnt' etc.
- MATD 0x01D0E75D: shader hash (Phong 0xB9105A6D, DropShadow 0xC09C7582, ...), 'MTRL' block of (param hash, type,
  count, offset from 'MTRL'); texture params (type 4) are 16 bytes: an ITG or GIT key of a DST/RLE texture.
- SKIN 0x01D0E76B: joint hashes + 3x4 inverse bind matrices; RIG 0x8EAF13DE (rigfmt) gives the rest pose. Skinned
  meshes are posed with the rig's rest pose, like the game shows an idle object (mostly rest x inverse bind =
  identity; the murphy beds' mattress is modelled open and folded into the cabinet by the rest pose).
- Geometry states (per mesh: state hash, start index, min vertex, vertex count, triangle count; 0 triangles = hidden)
  switch parts on and off (toilet lid, murphy bed/loveseat, rolled/unrolled yoga mat, hot tub cover). Chosen: the
  'Normal' state, else the OBJD's thumbnail state (0x4233F8A0) unless it is the generic 'thumbnail' look, else the
  only other state, else 'thumbnail', else none; object_mesh(state=...) overrides it.
- Meshes whose flags lack 0x1000 are invisible pick proxies and are skipped, as are drop shadows (flag 0x08 /
  DropShadow shader, named 'dropShadow1'...). Water surfaces (BasinWater etc.) are kept but flagged 'water'.
"""
import glob, json, os, pickle, re, struct, threading, time

import numpy as np

from dbpf import read_index, read_resource
from clipfmt import fnv32
from rigfmt import parse_rig
import texfmt

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.normpath(os.path.join(HERE, '..', 'cache', 'furniture'))
# WickedWhims' reference object per place: shipped with the app in data/, else the copy an older build left in cache/
EXAMPLES_SHIPPED = os.path.normpath(os.path.join(HERE, '..', 'data', 'ww_example_objects.json'))
EXAMPLES = os.path.normpath(os.path.join(HERE, '..', 'cache', 'ww_example_objects.json'))
INDEX_VERSION = 1       # the resource index (_index_v1.pkl): unchanged, never rebuilt for a new object format
VERSION = 3             # object JSON and locations_v3.json: 2 = seat/lying spots and the surface grid, 3 = skin data
                        # (bones/rest/rq/idx/w) on skinned meshes, for posing a bed's bedding to a bed animation

T_OBJD, T_MODL, T_MLOD, T_RIG, T_FTPT = 0xC0DB5AE7, 0x01661233, 0x01D10F34, 0x8EAF13DE, 0xD382BF57
T_MATD, T_MTST, T_VRTF, T_VBUF, T_IBUF, T_SKIN = 0x01D0E75D, 0x02019972, 0x01D0E723, 0x01D0E6FB, 0x01D0E70F, 0x01D0E76B
TEX_TYPES = set(texfmt.TEXTURE_TYPES)
INDEXED = {T_OBJD, T_MODL, T_MLOD, T_RIG, T_MATD, T_MTST, T_VRTF, T_VBUF, T_IBUF, T_SKIN} | TEX_TYPES

P_NAME, P_MODEL, P_RIG, P_VARIANT, P_THUMB_STATE = 0xE7F07786, 0x8D20ACC6, 0xE206AE4F, 0xECD5A95F, 0x4233F8A0
H_STATE_NORMAL, H_STATE_THUMBNAIL = fnv32('Normal'), fnv32('thumbnail')
STATE_NAMES = {fnv32(n): n for n in ('Normal', 'thumbnail', 'Blanket')}
H_POS_OFFSET, H_POS_SCALE, H_UV_OFFSET, H_UV_SCALE = fnv32('PosOffset'), fnv32('PosScale'), fnv32('UVOffset'), fnv32('UVScale')
H_DIFFUSE, H_ALPHA_MAP, H_ALPHA_THRESHOLD = fnv32('DiffuseMap'), fnv32('AlphaMap'), fnv32('AlphaMaskThreshold')
H_DECAL = fnv32('DecalMap')
H_ROOT = fnv32('b__ROOT__')
SHADER_PHONG = fnv32('Phong')

# shaders whose meshes are not visible furniture: shadows, outlines, wall/floor cut-outs, occluders
SKIP_SHADERS = {fnv32(n) for n in ('DropShadow', 'ShadowMap', 'ObjOutline', 'ObjOutlineColorStateTexture', 'WallCutout',
                                   'CutoutMask', 'ObjectCutout', 'Cutout', 'Occluder', 'Invisible', 'Hidden', 'Portal')}
ALPHA_SHADERS = {fnv32(n) for n in ('PhongAlpha', 'SpecularAlpha', 'Glass', 'GlassForObjects', 'GlassForObjectsTranslucent',
                                    'GlassForPortals', 'GlassForFences', 'ObjectsTranslucent', 'Additive', 'Water',
                                    'BasinWater', 'StandingWater', 'WaterPool', 'Leaf')}
SHADER_NAMES = {fnv32(n): n for n in ('Phong', 'PhongAlpha', 'PhongFlat', 'SpecularAlpha', 'Glass', 'GlassForObjects',
                                      'GlassForObjectsTranslucent', 'GlassForPortals', 'ObjectsTranslucent', 'Additive',
                                      'Water', 'BasinWater', 'StandingWater', 'WaterPool', 'Leaf', 'Painting', 'Counters',
                                      'Mirror', 'Decal', 'DecalOnly', 'Instanced', 'Fence', 'AnimatedTextures',
                                      'Candle', 'CandleFlame', 'Fire', 'Rug')}
SHADER_NAMES.update({h: 'skip' for h in SKIP_SHADERS})
# water surfaces (a tub's or hot tub's water): only shown while filled - flagged so the viewer can hide them
WATER_SHADERS = {fnv32(n) for n in ('Water', 'BasinWater', 'StandingWater', 'WaterPool')}

# VRTF element formats: (numpy dtype, components, normalise divisor or None)
_FMT = {0: ('<f4', 1, None), 1: ('<f4', 2, None), 2: ('<f4', 3, None), 3: ('<f4', 4, None), 4: ('u1', 4, None),
        5: ('u1', 4, 255.0), 6: ('<i2', 2, None), 7: ('<i2', 4, None), 8: ('u1', 4, 255.0), 9: ('<i2', 2, 32767.0),
        10: ('<i2', 4, 32767.0), 11: ('<u2', 2, 65535.0), 12: ('<u2', 4, 65535.0), 15: ('<f2', 2, None),
        16: ('<f2', 4, None)}
U_POS, U_NORMAL, U_UV, U_BLEND_INDEX, U_BLEND_WEIGHT, U_TANGENT, U_COLOUR = range(7)
DEFAULT_VRTF = {'stride': 52, 'elements': [(U_POS, 0, 2, 0), (U_NORMAL, 0, 2, 12), (U_UV, 0, 1, 24),
                                           (U_BLEND_INDEX, 0, 4, 32), (U_BLEND_WEIGHT, 0, 5, 36), (U_TANGENT, 0, 2, 40)]}


# ------------------------------------------------------------------ game packages + resource index
def _game_dir():
    import gamedata
    return gamedata.game_dir()


def packages():
    """Every client package: delta builds (base game, then each pack's) override full builds."""
    g = _game_dir()
    deltas = sorted(glob.glob(os.path.join(g, 'Data', 'Client', 'ClientDeltaBuild*.package'))) + \
        sorted(glob.glob(os.path.join(g, 'Delta', '*', 'ClientDeltaBuild*.package')))
    fulls = sorted(glob.glob(os.path.join(g, 'Data', 'Client', 'ClientFullBuild*.package'))) + \
        sorted(glob.glob(os.path.join(g, '*', 'ClientFullBuild*.package')))
    return deltas + fulls


def mods_packages():
    """Every .package in Mods (not Mods_parked: the game only loads Mods) whose folder or file name passes the
    adults-only block list (gamedata.blocked_path)."""
    import gamedata
    out = []
    for p in glob.glob(os.path.join(gamedata.MODS_DIR, '**', '*.package'), recursive=True):
        if not gamedata.blocked_path(p):
            out.append(p)
    return sorted(out)


def _mods_root():
    import gamedata
    return gamedata.SIMS_DIR


class _ResIndex:
    """(type, group, instance) -> package entry for the resource types furniture needs, over a set of packages,
    pickled next to the furniture cache as _<name>_v<version>.pkl.

    _GAME: the game's client packages (about 10-20 s over ~260 packages, once; the file stays _index_v1.pkl).
    _MODS: the packages in Mods (custom content objects and their meshes; checked again for new or changed files at
    most every `recheck` seconds, because mods_switch / SpeedKit move packs in and out of Mods while the app runs)."""

    def __init__(self, name, packages_fn, version, root_fn=None, recheck=None):
        self.name, self.packages_fn, self.version = name, packages_fn, version
        self.root_fn = root_fn or _game_dir
        self.recheck = recheck
        self._lock = threading.Lock()
        self._tgi = self._ti = self._pkgs = self._sig = None
        self._checked = 0.0

    @property
    def path(self):
        return os.path.join(CACHE_DIR, '_%s_v%d.pkl' % (self.name, self.version))

    def signature(self):
        return self._sig

    def clear(self):
        """Read again on the next use (the game's folder changed)."""
        with self._lock:
            self._tgi = self._ti = self._pkgs = self._sig = None
            self._checked = 0.0

    def load(self):
        with self._lock:
            now = time.time()
            if self._tgi is not None and (self.recheck is None or now - self._checked < self.recheck):
                return
            pk = self.packages_fn()
            sig = [(p, os.path.getsize(p), int(os.path.getmtime(p))) for p in pk]
            self._checked = now
            if self._tgi is not None and sig == self._sig:
                return
            path = self.path
            if os.path.exists(path):
                try:
                    with open(path, 'rb') as f:
                        cached = pickle.load(f)
                    if cached['sig'] == sig:
                        self._pkgs, self._tgi, self._ti, self._sig = cached['pkgs'], cached['tgi'], cached['ti'], sig
                        return
                except Exception:
                    pass
            tgi, ti = {}, {}
            for k, p in enumerate(pk):
                try:
                    entries = read_index(p)
                except Exception:
                    continue          # an empty delta package, a damaged mod
                for e in entries:
                    t = e['type']
                    if t not in INDEXED or (e['size'] == 0 and e['mem'] == 0):
                        continue
                    loc = (k, e['pos'], e['size'], e['mem'], e['comp'])
                    tgi.setdefault((t, e['group'], e['inst']), loc)
                    ti.setdefault((t, e['inst']), loc)
            self._pkgs, self._tgi, self._ti, self._sig = pk, tgi, ti, sig
            os.makedirs(CACHE_DIR, exist_ok=True)
            tmp = '%s.%d.tmp' % (path, os.getpid())
            try:
                with open(tmp, 'wb') as f:
                    pickle.dump({'sig': sig, 'pkgs': pk, 'tgi': tgi, 'ti': ti}, f, protocol=pickle.HIGHEST_PROTOCOL)
                os.replace(tmp, path)
            except OSError:            # another copy of the app has the file open: keep the index in memory
                try:
                    os.remove(tmp)
                except OSError:
                    pass

    def _loc(self, t, g, i):
        self.load()
        loc = self._tgi.get((t, g, i)) if g is not None else None
        if loc is None:
            loc = self._ti.get((t, i))
        return loc

    def read(self, t, g, i):
        loc = self._loc(t, g, i)
        if loc is None:
            return None
        k, pos, size, mem, comp = loc
        return read_resource(self._pkgs[k], {'pos': pos, 'size': size, 'mem': mem, 'comp': comp})

    def has(self, t, i):
        return self._loc(t, None, i) is not None

    def where(self, t, i):
        loc = self._loc(t, None, i)
        return os.path.relpath(self._pkgs[loc[0]], self.root_fn()) if loc else None

    def instances(self, t):
        """Every instance of resource type t in these packages."""
        self.load()
        return [i for (tt, i) in self._ti if tt == t]


_GAME = _ResIndex('index', packages, INDEX_VERSION)
_MODS = _ResIndex('mods_index', mods_packages, 1, root_fn=_mods_root, recheck=30.0)
_Index = _GAME            # older callers (hair.py) read the game's resources through this name


def reset():
    """The game's folder was picked again: both indexes are read again when next needed."""
    _GAME.clear()
    _MODS.clear()


def _read(t, g, i):
    """A resource from the game, else from Mods (custom content objects, props and their meshes and textures)."""
    data = _GAME.read(t, g, i)
    return data if data is not None else _MODS.read(t, g, i)


def _where(t, i):
    """Where a resource is: the game package (relative to the game folder), else 'Mods\\...' (relative to The Sims 4
    folder), else None."""
    return _GAME.where(t, i) or _MODS.where(t, i)


def source_of(guid):
    """'game' | 'mods' | None: where an object definition is found."""
    if _GAME.has(T_OBJD, int(guid)):
        return 'game'
    if _MODS.has(T_OBJD, int(guid)):
        return 'mods'
    return None


# ------------------------------------------------------------------ OBJD
def parse_objd(d):
    ver, tpos = struct.unpack_from('<HI', d, 0)
    n = struct.unpack_from('<H', d, tpos)[0]
    props = dict(struct.unpack_from('<II', d, tpos + 2 + 8 * k) for k in range(n))
    out = {'version': ver, 'props': props}

    def string(pid):
        if pid not in props:
            return None
        o = props[pid]
        ln = struct.unpack_from('<I', d, o)[0]
        return d[o + 4:o + 4 + ln].decode('ascii', 'replace')

    def tgis(pid):
        if pid not in props:
            return []
        o = props[pid]
        n4 = struct.unpack_from('<I', d, o)[0]
        res = []
        for k in range(n4 // 4):
            hi, lo, t, g = struct.unpack_from('<IIII', d, o + 4 + 16 * k)
            res.append((t, g, (hi << 32) | lo))
        return res

    out['name'] = string(P_NAME)
    out['thumbnail_state'] = struct.unpack_from('<I', d, props[P_THUMB_STATE])[0] if P_THUMB_STATE in props else 0
    out['variant'] = string(P_VARIANT)
    out['models'] = tgis(P_MODEL)
    out['rigs'] = tgis(P_RIG)
    return out


# ------------------------------------------------------------------ RCOL
class RCOL:
    def __init__(self, data):
        self.version, self.public, _, n_ext, n_int = struct.unpack_from('<5I', data, 0)
        p = 20
        self.internal = []
        for _ in range(n_int):
            inst, t, g = struct.unpack_from('<QII', data, p); p += 16
            self.internal.append((t, g, inst))
        self.external = []
        for _ in range(n_ext):
            inst, t, g = struct.unpack_from('<QII', data, p); p += 16
            self.external.append((t, g, inst))
        self.chunks = []
        for _ in range(n_int):
            pos, size = struct.unpack_from('<II', data, p); p += 8
            self.chunks.append(data[pos:pos + size])

    def resolve(self, ref):
        """Chunk reference -> (chunk bytes, RCOL that owns it) or (None, None)."""
        if not ref:
            return None, None
        kind, i = ref >> 28, (ref & 0x0FFFFFFF) - 1
        if kind == 0 and i < len(self.chunks):
            return self.chunks[i], self
        if kind == 1 and i + self.public < len(self.chunks):
            return self.chunks[i + self.public], self
        if kind in (2, 3) and i < len(self.external):
            t, g, inst = self.external[i]
            data = _read(t, g, inst)
            if data is None:
                return None, None
            if data[:4] in (b'MATD', b'MTST', b'VRTF', b'VBUF', b'IBUF', b'SKIN', b'MLOD', b'MODL'):
                return data, self    # a bare chunk
            other = RCOL(data)
            return (other.chunks[0] if other.chunks else None), other
        return None, None


def parse_modl(c):
    assert c[:4] == b'MODL', c[:4]
    ver, count = struct.unpack_from('<II', c, 4)
    bounds = struct.unpack_from('<6f', c, 12)
    lods = []
    base = len(c) - 20 * count
    for k in range(count):
        ref, flags, lod_id, zmin, zmax = struct.unpack_from('<IIIff', c, base + 20 * k)
        lods.append({'ref': ref, 'flags': flags, 'id': lod_id, 'zmin': zmin, 'zmax': zmax})
    return {'version': ver, 'bounds': bounds, 'lods': lods}


def parse_mlod(c):
    assert c[:4] == b'MLOD', c[:4]
    ver, count = struct.unpack_from('<II', c, 4)
    p = 12
    meshes = []
    for _ in range(count):
        size = struct.unpack_from('<I', c, p)[0]; p += 4
        start = p
        (name, mat, vrtf, vbuf, ibuf, prim, stream_off, start_vertex, start_index, min_vertex, n_vert,
         n_prim) = struct.unpack_from('<IIIIIIIiiiii', c, p); p += 48
        bounds = struct.unpack_from('<6f', c, p); p += 24
        skin = struct.unpack_from('<I', c, p)[0]; p += 4
        nj = struct.unpack_from('<I', c, p)[0]; p += 4
        joints = list(struct.unpack_from('<%dI' % nj, c, p)); p += 4 * nj
        scale_offset = struct.unpack_from('<I', c, p)[0]; p += 4
        ng = struct.unpack_from('<I', c, p)[0]; p += 4
        states = [struct.unpack_from('<Iiiii', c, p + 20 * k) for k in range(ng)]; p += 20 * ng
        parent = 0
        if ver > 0x201:
            parent = struct.unpack_from('<I', c, p)[0]
        meshes.append({'name': name, 'material': mat, 'vrtf': vrtf, 'vbuf': vbuf, 'ibuf': ibuf,
                       'primitive': prim & 0xFF, 'flags': prim >> 8, 'stream_offset': stream_off,
                       'start_vertex': start_vertex, 'start_index': start_index, 'min_vertex': min_vertex,
                       'vertex_count': n_vert, 'primitive_count': n_prim, 'bounds': bounds, 'skin': skin,
                       'joints': joints, 'scale_offset': scale_offset, 'states': states, 'parent': parent})
        p = start + size
    return {'version': ver, 'meshes': meshes}


def parse_vrtf(c):
    assert c[:4] == b'VRTF', c[:4]
    ver, stride, count, ext = struct.unpack_from('<IIII', c, 4)
    p = 20
    els = []
    for _ in range(count):
        if ext:
            usage, uidx, fmt = struct.unpack_from('<III', c, p); off = c[p + 12]; p += 13
        else:
            usage, uidx, fmt, off = c[p], c[p + 1], c[p + 2], c[p + 3]; p += 4
        els.append((usage, uidx, fmt, off))
    return {'stride': stride, 'elements': els}


def _element(raw, stride, fmt, off):
    """(n, stride) uint8 vertices -> (n, comps) float64 for one element."""
    dt, comps, div = _FMT[fmt]
    size = np.dtype(dt).itemsize * comps
    a = np.ascontiguousarray(raw[:, off:off + size]).view(dt).reshape(len(raw), comps).astype(np.float64)
    return a / div if div else a


def parse_ibuf(c):
    assert c[:4] == b'IBUF', c[:4]
    ver, flags, _ = struct.unpack_from('<III', c, 4)
    data = c[16:]
    a = np.frombuffer(data[:len(data) // 4 * 4] if flags & 2 else data[:len(data) // 2 * 2],
                      '<i4' if flags & 2 else '<i2').astype(np.int64)
    if flags & 1:
        a = np.cumsum(a)
    return a


def parse_matd(c):
    """-> {'shader', 'name', 'params': {hash: (type, values)}}; texture params hold (type, group, instance) keys."""
    assert c[:4] == b'MATD', c[:4]
    ver, name, shader, length = struct.unpack_from('<IIII', c, 4)
    p = 20 + (8 if ver >= 0x103 else 0)
    mtrl = p
    params = {}
    if c[p:p + 4] == b'MTRL':
        _, data_size, count = struct.unpack_from('<III', c, p + 4)
        for k in range(count):
            h, typ, n, off = struct.unpack_from('<IIII', c, p + 16 + 16 * k)
            o = mtrl + off
            base = typ & 0xFFFF
            if base == 1:
                params[h] = ('f', list(struct.unpack_from('<%df' % n, c, o)))
            elif base == 2:
                params[h] = ('i', list(struct.unpack_from('<%di' % n, c, o)))
            elif base == 4 and n == 4:
                raw = c[o:o + 16]
                inst, t, g = struct.unpack_from('<QII', raw, 0)        # ITG
                g2, inst2, t2 = struct.unpack_from('<IQI', raw, 0)     # GIT
                keys = [(t, g, inst), (t2, g2, inst2)]
                params[h] = ('tex', [k for k in keys if k[0] in TEX_TYPES])
            else:
                params[h] = ('?', c[o:o + 4 * n])
    return {'name': name, 'shader': shader, 'params': params}


def parse_mtst(c):
    assert c[:4] == b'MTST', c[:4]
    ver, name, default, count = struct.unpack_from('<IIII', c, 4)
    step = 12 if ver >= 0x300 else 8
    entries = []
    for k in range(count):
        if step == 12:
            ref, state, variant = struct.unpack_from('<III', c, 20 + 12 * k)
        else:
            (ref, state), variant = struct.unpack_from('<II', c, 20 + 8 * k), 0
        entries.append((ref, state, variant))
    return {'name': name, 'default': default, 'entries': entries}


def parse_skin(c):
    assert c[:4] == b'SKIN', c[:4]
    ver, n = struct.unpack_from('<II', c, 4)
    hashes = list(struct.unpack_from('<%dI' % n, c, 12))
    mats = np.frombuffer(c[12 + 4 * n:12 + 4 * n + 48 * n], '<f4').reshape(n, 3, 4).astype(np.float64)
    out = {}
    for h, m in zip(hashes, mats):
        full = np.eye(4); full[:3, :] = m
        out[h] = full
    return out


# ------------------------------------------------------------------ rig rest pose
def _quat_matrix(x, y, z, w):
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def rig_rest(rig_key):
    """RIG TGI -> {bone hash: 4x4 model-space rest matrix}, {bone hash: name}."""
    if rig_key is None:
        return {}, {}
    data = _read(*rig_key)
    if not data:
        return {}, {}
    try:
        r = parse_rig(data)
    except Exception:
        return {}, {}
    local = []
    for b in r['bones']:
        m = np.eye(4)
        m[:3, :3] = _quat_matrix(*b['rot']) * np.array(b['scale'])[None, :]
        m[:3, 3] = b['pos']
        local.append(m)
    world = [None] * len(local)

    def get(k):
        if world[k] is None:
            par = r['bones'][k]['parent']
            world[k] = local[k] if par < 0 or par == k else get(par) @ local[k]
        return world[k]
    mats, names = {}, {}
    for k, b in enumerate(r['bones']):
        mats[b['hash']] = get(k)
        names[b['hash']] = b['name']
    return mats, names


# ------------------------------------------------------------------ textures
def _export_texture(key):
    """(type, group, instance) -> PNG file name under cache/furniture (written once), or None."""
    t, g, inst = key
    fname = 'tex_%016x.png' % inst
    path = os.path.join(CACHE_DIR, fname)
    if os.path.exists(path):
        return fname
    data = _read(t, g, inst)
    if not data:
        return None
    try:
        rgba = texfmt.decode(data)
    except Exception:
        return None
    from PIL import Image
    tmp = '%s.%d.tmp.png' % (path, os.getpid())
    Image.fromarray(np.ascontiguousarray(rgba), 'RGBA').save(tmp, optimize=False)
    os.replace(tmp, path)
    return fname


def _alpha_stats(fname):
    """-> (fraction of texels with alpha < 200, highest alpha) of an exported texture."""
    from PIL import Image
    try:
        a = np.asarray(Image.open(os.path.join(CACHE_DIR, fname)))[:, :, 3]
    except Exception:
        return 0.0, 255
    return float((a < 200).mean()), int(a.max())


# ------------------------------------------------------------------ the mesh builder
def _pick_material(rc, ref, variant_hash):
    """Mesh material ref (MATD or MTST) -> parsed MATD for the object's material variant in its normal state."""
    c, owner = rc.resolve(ref)
    if c is None:
        return None
    if c[:4] == b'MATD':
        return parse_matd(c)
    if c[:4] != b'MTST':
        return None
    ms = parse_mtst(c)
    chosen = None
    for want in ((variant_hash, 0), (0, 0)):
        for r, state, var in ms['entries']:
            if (var, state) == want:
                chosen = r
                break
        if chosen:
            break
    if chosen is None:
        chosen = ms['default'] or (ms['entries'][0][0] if ms['entries'] else 0)
    mc, _ = owner.resolve(chosen)
    return parse_matd(mc) if mc is not None and mc[:4] == b'MATD' else None


def _mat_to_quat(R):
    """3x3 rotation matrix (columns normalised first, in case a parent bone carries scale) -> (x, y, z, w)."""
    c0, c1, c2 = R[:, 0], R[:, 1], R[:, 2]
    m00, m10, m20 = c0 / (np.linalg.norm(c0) or 1.0)
    m01, m11, m21 = c1 / (np.linalg.norm(c1) or 1.0)
    m02, m12, m22 = c2 / (np.linalg.norm(c2) or 1.0)
    tr = m00 + m11 + m22
    if tr > 0:
        s = np.sqrt(tr + 1.0) * 2
        w, x, y, z = 0.25 * s, (m21 - m12) / s, (m02 - m20) / s, (m10 - m01) / s
    elif m00 > m11 and m00 > m22:
        s = np.sqrt(1.0 + m00 - m11 - m22) * 2
        w, x, y, z = (m21 - m12) / s, 0.25 * s, (m01 + m10) / s, (m02 + m20) / s
    elif m11 > m22:
        s = np.sqrt(1.0 + m11 - m00 - m22) * 2
        w, x, y, z = (m02 - m20) / s, (m01 + m10) / s, 0.25 * s, (m12 + m21) / s
    else:
        s = np.sqrt(1.0 + m22 - m00 - m11) * 2
        w, x, y, z = (m10 - m01) / s, (m02 + m20) / s, (m12 + m21) / s, 0.25 * s
    return float(x), float(y), float(z), float(w)


def _round_weights(w):
    """(n, 4) blend weights (rows already summing to ~1) -> rows rounded to 4 decimals that still sum to exactly 1
    (the rounding error is folded into each row's biggest weight)."""
    r = np.round(w, 4)
    diff = np.round(1.0 - r.sum(1), 4)
    rows = np.arange(len(r))
    imax = np.argmax(r, axis=1)
    r[rows, imax] = np.round(r[rows, imax] + diff, 4)
    return r


def _build_mesh(rc, m, variant_hash, rest, bone_names, report, state=0):
    for name, s_index, s_min, s_count, s_prims in m['states']:
        if state and name == state:          # this geometry state's own index range (0 triangles = hidden)
            if s_prims == 0:
                report.append('skip mesh %08x: hidden in geometry state %08x' % (m['name'], state))
                return None
            m = dict(m, start_index=s_index, min_vertex=s_min, vertex_count=s_count, primitive_count=s_prims)
    if m['primitive'] != 3:
        report.append('skip mesh %08x: primitive type %d' % (m['name'], m['primitive']))
        return None
    if m['flags'] & 0x08:
        report.append('skip mesh %08x: drop shadow' % m['name'])
        return None
    if not m['flags'] & 0x1000:
        # every rendered mesh has flag 0x1000; the ones without it are pick/selection proxies (boxes and quads
        # around a wall shower, a towel, a picnic blanket, a rug ...) that the game never draws
        report.append('skip mesh %08x: pick proxy (not rendered)' % m['name'])
        return None
    if not m['vbuf'] or not m['ibuf']:
        report.append('skip mesh %08x: no vertex or index buffer' % m['name'])
        return None
    mat = _pick_material(rc, m['material'], variant_hash)
    shader = mat['shader'] if mat else 0
    if shader in SKIP_SHADERS:
        report.append('skip mesh %08x: shader %s' % (m['name'], SHADER_NAMES.get(shader, '%08x' % shader)))
        return None
    # meshes without a VRTF (decals) use the default layout: float3 position, float3 normal, float2 UV, blend
    # indices, blend weights, float3 tangent = 52 bytes
    vf = parse_vrtf(rc.resolve(m['vrtf'])[0]) if m['vrtf'] else DEFAULT_VRTF
    vc, _ = rc.resolve(m['vbuf'])
    vflags = struct.unpack_from('<I', vc, 8)[0]
    stride = vf['stride']
    # meshes with different vertex formats share one VBUF: the stream offset is in bytes
    first = 16 + m['stream_offset'] + (m['start_vertex'] + m['min_vertex']) * stride
    if first + m['vertex_count'] * stride > len(vc):
        report.append('skip mesh %08x: vertices past the end of the buffer' % m['name'])
        return None
    verts = np.frombuffer(vc, np.uint8, count=m['vertex_count'] * stride, offset=first).reshape(-1, stride)
    idx = parse_ibuf(rc.resolve(m['ibuf'])[0])
    faces = idx[m['start_index']:m['start_index'] + 3 * m['primitive_count']].reshape(-1, 3) - m['min_vertex']
    if len(faces) and (faces.min() < 0 or faces.max() >= len(verts)):
        report.append('skip mesh %08x: indices out of range' % m['name'])
        return None

    so = {}
    if m['scale_offset']:
        sc, _ = rc.resolve(m['scale_offset'])
        if sc is not None and sc[:4] == b'MATD':
            so = {h: v[1] for h, v in parse_matd(sc)['params'].items() if v[0] == 'f'}
    els = {(u, ui): (fmt, off) for u, ui, fmt, off in vf['elements']}
    pos = None
    if (U_POS, 0) in els:
        fmt, off = els[(U_POS, 0)]
        a = _element(verts, stride, fmt, off)
        if fmt == 7:           # Short4: xyz * PosScale + PosOffset (w carries 1 / scale when there is no scale chunk)
            if H_POS_SCALE in so:
                pos = a[:, :3] * np.array(so[H_POS_SCALE][:3]) + np.array(so.get(H_POS_OFFSET, [0, 0, 0])[:3])
            else:
                w = np.where(a[:, 3:4] > 0, a[:, 3:4], 32767.0)
                pos = a[:, :3] / w
        else:
            pos = a[:, :3]
    if pos is None:
        return None
    if vflags & 0x4:
        report.append('mesh %08x: VBUF flag 0x%x (differenced vertices) - not seen in the reference objects' % (m['name'], vflags))
    nrm = None
    if (U_NORMAL, 0) in els:
        fmt, off = els[(U_NORMAL, 0)]
        if fmt in (4, 5, 8):   # bytes: (b - 128) / 127
            b = np.ascontiguousarray(verts[:, off:off + 4]).astype(np.float64)
            nrm = (b[:, :3] - 128.0) / 127.0
        else:
            nrm = _element(verts, stride, fmt, off)[:, :3]
    uv = None
    if (U_UV, 0) in els:
        fmt, off = els[(U_UV, 0)]
        a = _element(verts, stride, fmt, off)[:, :2]
        if fmt == 6:           # Short2: s / 32767 * UVScale + UVOffset
            a = a / 32767.0 * np.array(so.get(H_UV_SCALE, [1, 1])[:2]) + np.array(so.get(H_UV_OFFSET, [0, 0])[:2])
        uv = a

    # skinned meshes: pose with the rig's rest pose (world = sum_i w_i * rest_i * inverse_bind_i * bind position)
    moved = 0.0
    skin = None
    if m['skin'] and m['joints'] and rest and (U_BLEND_INDEX, 0) in els:
        sk, _ = rc.resolve(m['skin'])
        inv = parse_skin(sk) if sk is not None and sk[:4] == b'SKIN' else {}
        fi, oi = els[(U_BLEND_INDEX, 0)]
        bi = np.ascontiguousarray(verts[:, oi:oi + 4]).astype(np.int64)
        if (U_BLEND_WEIGHT, 0) in els:
            fw, ow = els[(U_BLEND_WEIGHT, 0)]
            bw = _element(verts, stride, fw, ow)[:, :4]
        else:
            bw = np.zeros((len(verts), 4)); bw[:, 0] = 1
        mats = []
        for h in m['joints']:
            if h in rest and h in inv:
                mats.append(rest[h] @ inv[h])
            else:
                mats.append(np.eye(4))
        mats = np.array(mats)
        bi = np.clip(bi, 0, len(mats) - 1)
        dev = np.abs(mats - np.eye(4)[None]).max() if len(mats) else 0.0
        if dev > 1e-4:
            hp = np.c_[pos, np.ones(len(pos))]
            acc = np.zeros_like(pos); nacc = np.zeros_like(pos)
            wsum = bw.sum(1, keepdims=True); wsum[wsum == 0] = 1
            for k in range(4):
                mk = mats[bi[:, k]]                                   # (n, 4, 4)
                acc += bw[:, k:k + 1] / wsum * np.einsum('nij,nj->ni', mk, hp)[:, :3]
                if nrm is not None:
                    nacc += bw[:, k:k + 1] / wsum * np.einsum('nij,nj->ni', mk[:, :3, :3], nrm)
            moved = float(np.abs(acc - pos).max())
            pos = acc
            if nrm is not None:
                nrm = nacc / (np.linalg.norm(nacc, axis=1, keepdims=True) + 1e-12)
            report.append('mesh %08x: skinned with the rig rest pose (moved up to %.3f m)' % (m['name'], moved))
        if len(m['joints']) > 1:
            # bone rest pose (in the same object space as the returned positions) + per-vertex weights, so a bed's
            # bedding can be posed at runtime by the bed rig's own animation (see exporter.py's bedAnim)
            root_off = rest[H_ROOT][:3, 3] if H_ROOT in rest else np.zeros(3)
            names_out, rest_pos, rest_q = [], [], []
            for h in m['joints']:
                names_out.append(bone_names.get(h, '%08x' % h))
                M = rest.get(h)
                if M is None:
                    rest_pos.append([0.0, 0.0, 0.0]); rest_q.append([0.0, 0.0, 0.0, 1.0])
                else:
                    rest_pos.append([round(float(v), 5) for v in (M[:3, 3] - root_off)])
                    rest_q.append([round(float(v), 5) for v in _mat_to_quat(M[:3, :3])])
            bw_fixed = bw.copy()
            bw_fixed[bw_fixed.sum(1) == 0, 0] = 1          # an unweighted vertex: pin it to its first bone
            wn = bw_fixed / bw_fixed.sum(1, keepdims=True)
            w4 = _round_weights(wn)
            skin = {'bones': names_out, 'rest': rest_pos, 'rq': rest_q,
                    'idx': [int(v) for v in bi.reshape(-1)], 'w': [float(v) for v in w4.reshape(-1)]}

    texture, alpha_tex = None, False
    params = mat['params'] if mat else {}
    for h in (H_DIFFUSE, H_DECAL):
        if texture is None and h in params and params[h][0] == 'tex':
            for key in params[h][1]:
                texture = _export_texture(key)
                if texture:
                    break
    transparent = shader in ALPHA_SHADERS
    threshold = params[H_ALPHA_THRESHOLD][1][0] if H_ALPHA_THRESHOLD in params and params[H_ALPHA_THRESHOLD][0] == 'f' else 0.0
    alpha_test = round(threshold / 255.0 if threshold > 1 else threshold, 3)
    if texture and (transparent or H_ALPHA_MAP in params or alpha_test > 0):
        see_through, top_alpha = _alpha_stats(texture)
        if alpha_test > 0 and top_alpha < alpha_test * 255:
            report.append('skip mesh %08x: fully cut out by its alpha mask' % m['name'])
            return None
        # glass and other see-through materials: an alpha shader, or an AlphaMap texture that really is see-through
        # (Phong keeps other data in the alpha of mostly-opaque textures); alpha-tested cut-outs stay opaque
        alpha_tex = see_through > 0.05 and alpha_test == 0 and (shader != SHADER_PHONG or H_ALPHA_MAP in params)
    return {'pos': pos, 'nrm': nrm, 'uv': uv, 'faces': faces, 'texture': texture, 'water': shader in WATER_SHADERS,
            'alpha_test': alpha_test,
            'transparent': bool(transparent or alpha_tex), 'shader': SHADER_NAMES.get(shader, '%08x' % shader),
            'mesh': '%08x' % m['name'], 'skinned': bool(m['skin'] and len(m['joints']) > 1), 'skin': skin}


def _height_map(meshes, cell=0.02):
    """Top-most surface seen from above on a `cell` grid: (x0, z0, cell, top (D, W) heights or -inf, upward (D, W)
    True where that top-most triangle faces up), or None when there are no triangles."""
    tris = []
    for P, F in meshes:
        if len(F) == 0:
            continue
        a, b, c = P[F[:, 0]], P[F[:, 1]], P[F[:, 2]]
        n = np.cross(b - a, c - a)
        ln = np.linalg.norm(n, axis=1) + 1e-12
        up = n[:, 1] / ln
        tris.append((a, b, c, up))
    if not tris:
        return None
    allp = np.concatenate([np.concatenate([a, b, c]) for a, b, c, _ in tris])
    x0, z0 = allp[:, 0].min(), allp[:, 2].min()
    W = int((allp[:, 0].max() - x0) / cell) + 2
    D = int((allp[:, 2].max() - z0) / cell) + 2
    top = np.full((D, W), -np.inf)
    upward = np.zeros((D, W), bool)
    for a, b, c, up in tris:
        for k in range(len(a)):
            pa, pb, pc = a[k], b[k], c[k]
            ax, az = (pa[0] - x0) / cell, (pa[2] - z0) / cell
            bx, bz = (pb[0] - x0) / cell, (pb[2] - z0) / cell
            cx, cz = (pc[0] - x0) / cell, (pc[2] - z0) / cell
            i0, i1 = int(max(np.floor(min(ax, bx, cx)), 0)), int(min(np.ceil(max(ax, bx, cx)), W - 1))
            j0, j1 = int(max(np.floor(min(az, bz, cz)), 0)), int(min(np.ceil(max(az, bz, cz)), D - 1))
            den = (bz - cz) * (ax - cx) + (cx - bx) * (az - cz)
            if abs(den) < 1e-9 or i1 < i0 or j1 < j0:
                continue
            xs, zs = np.meshgrid(np.arange(i0, i1 + 1) + 0.5, np.arange(j0, j1 + 1) + 0.5)
            w0 = ((bz - cz) * (xs - cx) + (cx - bx) * (zs - cz)) / den
            w1 = ((cz - az) * (xs - cx) + (ax - cx) * (zs - cz)) / den
            w2 = 1 - w0 - w1
            inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
            y = w0 * pa[1] + w1 * pb[1] + w2 * pc[1]
            sub = top[j0:j1 + 1, i0:i1 + 1]
            vis = inside & (y > sub)
            sub[vis] = y[vis]
            upward[j0:j1 + 1, i0:i1 + 1][vis] = up[k] > 0.7
    return x0, z0, cell, top, upward


def top_surface(meshes, cell=0.02, lo=-1.0, hi=2.0):
    """Height of the biggest up-facing surface seen from above (a bed's mattress/blanket top, a seat, a counter or
    table top, a blanket on the floor): a 2 cm height map of the top-most up-facing triangles, then the most common
    1 cm height band between `lo` and `hi` metres. None when nothing qualifies."""
    hm = _height_map(meshes, cell)
    if hm is None:
        return None
    _, _, _, top, upward = hm
    h = top[upward & (top > lo) & (top < hi)]
    if len(h) < 20:
        return None
    bins = np.round(h * 100).astype(int)
    vals, counts = np.unique(bins, return_counts=True)
    # smooth over +-1 cm so a slightly sloped cushion still counts as one surface
    sm = np.array([counts[np.abs(vals - v) <= 1].sum() for v in vals])
    best = vals[int(np.argmax(sm))]
    return round(float(np.median(h[np.abs(bins - best) <= 1])), 3)


GRID_NONE = -32768


def surface_grid(meshes, lo=-1.0, hi=2.0, cell=0.05):
    """Top-most up-facing height per 5 cm cell (mm, int), for 'is this point inside the furniture'.
    -> {'x0', 'z0', 'cell', 'w', 'd', 'h': [row-major: z rows, then x; -32768 = nothing]} or None.
    Rasterised at half the cell size, each cell keeps the highest of its 2 x 2 sub-cells."""
    hm = _height_map(meshes, cell / 2.0)
    if hm is None:
        return None
    x0, z0, c0, top, up = hm
    k = 2
    h = np.where(up & (top > lo) & (top < hi), top, -np.inf)
    D, W = h.shape
    pd, pw = (-D) % k, (-W) % k
    if pd or pw:
        h = np.pad(h, ((0, pd), (0, pw)), constant_values=-np.inf)
    h = h.reshape(h.shape[0] // k, k, h.shape[1] // k, k).max(axis=(1, 3))
    mm = np.where(np.isfinite(h), np.round(h * 1000), GRID_NONE).astype(int)
    return {'x0': round(float(x0), 4), 'z0': round(float(z0), 4), 'cell': cell, 'w': int(mm.shape[1]),
            'd': int(mm.shape[0]), 'h': [int(v) for v in mm.reshape(-1)]}


def grid_height(grid, x, z):
    """Height (m) of the surface grid at (x, z), or None where there is nothing."""
    if not grid:
        return None
    i = int(np.floor((x - grid['x0']) / grid['cell']))
    j = int(np.floor((z - grid['z0']) / grid['cell']))
    if not (0 <= i < grid['w'] and 0 <= j < grid['d']):
        return None
    v = grid['h'][j * grid['w'] + i]
    return None if v == GRID_NONE else v / 1000.0


_SLOT_JOINT = re.compile(r'^_IKtarget_(butt|L_foot|R_foot)_?(\d*)$', re.I)
_SLOT_SKIP = re.compile(r'(child|toddler|infant|_c_|_p_)', re.I)
SLOT_TOL = 0.06          # a cell counts as the same surface within 6 cm of the surface height


def _walk(grid, surface, pos, d, step=0.05, limit=3.0):
    """How far (m) the surface goes on from pos in direction d = (x, y, z) (cells within SLOT_TOL of the surface
    height)."""
    dist, s = 0.0, step
    while s <= limit:
        h = grid_height(grid, pos[0] + d[0] * s, pos[2] + d[2] * s)
        if h is None or abs(h - surface) > SLOT_TOL:
            break
        dist = s
        s += step
    return dist


def _slots(rest, bone_names, root_offset, grid, surface):
    """Seat, foot and lying spots of an object (object space, metres, WickedWhims' origin):
    [{'n', 'kind': 'seat'|'edge'|'in', 'pos', 'dir', 'feet': {'L', 'R'}} ..., {'n': 100 + i, 'kind': 'lie', 'pos',
    'dir'}]. dir = (x, 0, z): the way a seated sim faces; for a lying spot, from the head toward the feet."""
    seats, feet = {}, {}
    for h, M in rest.items():
        name = bone_names.get(h, '')
        m = _SLOT_JOINT.match(name)
        if not m or _SLOT_SKIP.search(name):
            continue
        n = int(m.group(2) or 0)
        pos = [round(float(v), 3) for v in (M[:3, 3] - root_offset)]
        if m.group(1).lower() == 'butt':
            z = np.array([M[0, 2], M[2, 2]], float)
            ln = float(np.linalg.norm(z))
            d = z / ln if ln > 1e-6 else np.array([0.0, 1.0])
            seats[n] = {'n': n, 'pos': pos, 'dir': [round(float(d[0]), 3), 0.0, round(float(d[1]), 3)]}
        else:
            feet.setdefault(n, {})['L' if m.group(1)[0].upper() == 'L' else 'R'] = pos
    out = []
    region = _lie_region(grid, surface)
    for n in sorted(seats):
        st = seats[n]
        d = st['dir']
        kind = 'seat'
        if grid and surface is not None:
            front = _walk(grid, surface, st['pos'], d)
            behind = _walk(grid, surface, st['pos'], (-d[0], 0.0, -d[2]))
            if front >= 0.4:
                kind = 'in'
            elif front < 0.45 and (behind >= 0.9 or _on_region(region, grid, st['pos'])):
                kind = 'edge'
        f = feet.get(n, {})
        out.append(dict(st, kind=kind, feet={'L': f.get('L'), 'R': f.get('R')}))
    out += _lying_spots(out, grid, surface)
    return out


def _regions(mask):
    """Connected regions (4-neighbour) of a boolean grid -> [(rows, cols)] arrays of cell indices."""
    seen = np.zeros_like(mask, bool)
    D, W = mask.shape
    regions = []
    for j0 in range(D):
        for i0 in range(W):
            if not mask[j0, i0] or seen[j0, i0]:
                continue
            stack, cells = [(j0, i0)], []
            seen[j0, i0] = True
            while stack:
                j, i = stack.pop()
                cells.append((j, i))
                for jj, ii in ((j + 1, i), (j - 1, i), (j, i + 1), (j, i - 1)):
                    if 0 <= jj < D and 0 <= ii < W and mask[jj, ii] and not seen[jj, ii]:
                        seen[jj, ii] = True
                        stack.append((jj, ii))
            regions.append(np.array(cells))
    return regions


def _lie_region(grid, surface):
    """The biggest region of the surface (cells within SLOT_TOL of its height) at least 1.7 m long and 0.55 m wide,
    as an array of (row, col) cells, or None."""
    if not grid or surface is None:
        return None
    c = grid['cell']
    h = np.array(grid['h'], float).reshape(grid['d'], grid['w'])
    valid = h != GRID_NONE
    hm = np.where(valid, h / 1000.0, -np.inf)
    mask = valid & (np.abs(hm - surface) <= SLOT_TOL)
    best = None
    for cells in _regions(mask):
        dz = (cells[:, 0].max() - cells[:, 0].min() + 1) * c
        dx = (cells[:, 1].max() - cells[:, 1].min() + 1) * c
        if max(dx, dz) >= 1.7 - 1e-6 and min(dx, dz) >= 0.55 - 1e-6 and (best is None or len(cells) > len(best)):
            best = cells
    return best


def _on_region(cells, grid, pos):
    if cells is None:
        return False
    i = int(np.floor((pos[0] - grid['x0']) / grid['cell']))
    j = int(np.floor((pos[2] - grid['z0']) / grid['cell']))
    return bool(((cells[:, 0] == j) & (cells[:, 1] == i)).any())


def _lying_spots(seats, grid, surface):
    """Lying spots where the surface has a region at least 1.7 m long and 0.55 m wide (beds, sofas, blankets, mats):
    on beds one per in-bed seat at the head end (0.55 m along its facing) plus one in the middle; elsewhere one on
    the region's long axis through its centre, the head at the end next to higher cells (a headboard or an arm)."""
    best = _lie_region(grid, surface)
    if best is None:
        return []
    c = grid['cell']
    y = round(float(surface), 3)
    spots = []
    inbed = [x for x in seats if x['kind'] == 'in']
    if inbed:
        # the in-bed seats at the head end: the ones with the higher cells (headboard) right behind them
        def behind_height(st):
            hs = [grid_height(grid, st['pos'][0] - st['dir'][0] * s, st['pos'][2] - st['dir'][2] * s)
                  for s in np.arange(0.05, 0.651, 0.05)]
            return max([v for v in hs if v is not None] or [-1.0])
        groups = {}
        for st in inbed:
            groups.setdefault((round(st['dir'][0], 1), round(st['dir'][2], 1)), []).append(st)
        key = max(groups, key=lambda k: (round(max(behind_height(st) for st in groups[k]), 2), k[1], k[0]))
        heads = list({(st['pos'][0], st['pos'][2]): st for st in
                      sorted(groups[key], key=lambda st: (st['pos'][0], st['pos'][2]))}.values())
        for st in heads:
            d = st['dir']
            spots.append(([st['pos'][0] + d[0] * 0.55, y, st['pos'][2] + d[2] * 0.55], d))
        if len(heads) == 2:
            (a, d), (b, _) = spots
            spots.insert(1, ([(a[0] + b[0]) / 2, y, (a[2] + b[2]) / 2], d))
    else:
        rows, cols = best[:, 0], best[:, 1]
        cx = grid['x0'] + (cols.min() + cols.max() + 1) / 2 * c
        cz = grid['z0'] + (rows.min() + rows.max() + 1) / 2 * c
        along_z = (rows.max() - rows.min()) >= (cols.max() - cols.min())
        if along_z:
            lo_end, hi_end = grid['z0'] + rows.min() * c, grid['z0'] + (rows.max() + 1) * c
            h_lo = grid_height(grid, cx, lo_end - c / 2) or -1.0
            h_hi = grid_height(grid, cx, hi_end + c / 2) or -1.0
            d = [0.0, 0.0, -1.0] if h_hi > h_lo + 0.02 else [0.0, 0.0, 1.0]
        else:
            lo_end, hi_end = grid['x0'] + cols.min() * c, grid['x0'] + (cols.max() + 1) * c
            h_lo = grid_height(grid, lo_end - c / 2, cz) or -1.0
            h_hi = grid_height(grid, hi_end + c / 2, cz) or -1.0
            d = [-1.0, 0.0, 0.0] if h_hi > h_lo + 0.02 else [1.0, 0.0, 0.0]
        spots.append(([cx, y, cz], d))
    return [{'n': 100 + i, 'kind': 'lie', 'pos': [round(float(v), 3) for v in p], 'dir': [float(v) for v in d]}
            for i, (p, d) in enumerate(spots)]


def _state_hash(state):
    if state is None or state == '':
        return None
    if isinstance(state, int):
        return state
    t = str(state)
    if t.lower().startswith('0x'):
        return int(t, 16)
    return fnv32(t)


def _build(obj_def_id, lod=0, piece=0, state=None):
    t0 = time.time()
    od_raw = _read(T_OBJD, 0, obj_def_id)
    if od_raw is None:
        raise KeyError('object definition %d not found in the game or in Mods' % obj_def_id)
    od = parse_objd(od_raw)
    if not od['models']:
        raise ValueError('object %d (%s) has no model' % (obj_def_id, od['name']))
    piece = max(0, min(int(piece), len(od['models']) - 1))
    variant_hash = fnv32(od['variant']) if od['variant'] else 0
    # model k goes with rig k (modular counters / sectionals list one model + rig per piece; piece 0 = as placed)
    rig_key = od['rigs'][piece] if piece < len(od['rigs']) else (od['rigs'][0] if od['rigs'] else None)
    rest, bone_names = rig_rest(rig_key)
    root = rest.get(H_ROOT)
    root_offset = root[:3, 3].copy() if root is not None else np.zeros(3)
    report = []
    parts = []
    data = _read(*od['models'][piece])
    if data is None:
        raise KeyError('object %d (%s): model not found' % (obj_def_id, od['name']))
    rc = RCOL(data)
    modl = parse_modl(rc.chunks[0])
    lods = sorted([x for x in modl['lods'] if not x['id'] & 0x10000], key=lambda x: x['id'])
    pick = next((x for x in lods if x['id'] == lod), lods[0] if lods else None)
    ml, owner = None, None
    if pick is not None:
        mc, owner = rc.resolve(pick['ref'])
        if mc is not None and mc[:4] == b'MLOD':
            ml = parse_mlod(mc)
    if ml is None:
        raise ValueError('object %d (%s): no mesh LOD' % (obj_def_id, od['name']))
    # geometry states (lid up/down, murphy bed open/closed, hot tub cover...): pick what the game shows normally
    states = []
    for m in ml['meshes']:
        for g in m['states']:
            if g[0] not in states:
                states.append(g[0])
    chosen = _state_hash(state)
    if chosen is None:
        # 'Normal' if the object has it, else the state its OBJD names for thumbnails (unless that is the generic
        # catalog 'thumbnail' look), else its only other state (yoga mat / sleeping bag laid out), else 'thumbnail'
        thumb = od['thumbnail_state']
        others = [h for h in states if h != H_STATE_THUMBNAIL]
        only = others[0] if len(others) == 1 else 0
        chosen = next((h for h in (H_STATE_NORMAL, thumb if thumb != H_STATE_THUMBNAIL else 0, only,
                                   H_STATE_THUMBNAIL) if h and h in states), 0)
    for m in ml['meshes']:
        try:
            r = _build_mesh(owner, m, variant_hash, rest, bone_names, report, chosen)
        except Exception as ex:           # one odd mesh should not lose the object
            report.append('mesh %08x failed: %r' % (m['name'], ex))
            r = None
        if r is not None:
            parts.append(r)
    meshes = []
    lo, hi = np.full(3, np.inf), np.full(3, -np.inf)
    for r in parts:
        p = r['pos'] - root_offset
        if not r['water']:
            lo, hi = np.minimum(lo, p.min(0)), np.maximum(hi, p.max(0))
        entry = {
            'positions': [round(float(c), 5) for c in p.reshape(-1)],
            'normals': [round(float(c), 4) for c in r['nrm'].reshape(-1)] if r['nrm'] is not None else [],
            'uvs': [round(float(c), 5) for c in r['uv'].reshape(-1)] if r['uv'] is not None else [],
            'faces': [int(i) for i in r['faces'].reshape(-1)],
            'texture': r['texture'], 'transparent': r['transparent'], 'alpha_test': r['alpha_test'], 'water': r['water'],
            'shader': r['shader'], 'mesh': r['mesh'], 'skinned': r['skinned']}
        if r.get('skin') is not None:
            entry['skin'] = r['skin']
        meshes.append(entry)
    if not meshes:
        raise ValueError('object %d (%s): no visible meshes (%s)' % (obj_def_id, od['name'], '; '.join(report)))
    solid = [(r['pos'] - root_offset, r['faces']) for r in parts if not r['transparent'] and not r['water']]
    surface = top_surface(solid)
    grid = surface_grid(solid)
    try:
        slots = _slots(rest, bone_names, root_offset, grid, surface)
    except Exception as ex:            # an odd rig should not lose the object
        report.append('slots failed: %r' % ex)
        slots = []
    return {
        'id': obj_def_id, 'name': od['name'], 'variant': od['variant'], 'lod': pick['id'], 'version': VERSION,
        'piece': piece, 'pieces': len(od['models']),
        'geometry_state': STATE_NAMES.get(chosen, '%08x' % chosen) if chosen else None,
        'geometry_states': [STATE_NAMES.get(h, '%08x' % h) for h in states],
        'meshes': meshes,
        'bounds': {'min': [round(float(v), 4) for v in lo], 'max': [round(float(v), 4) for v in hi]},
        'surface_height': surface,
        'surface_grid': grid,
        'slots': slots,
        'modl_bounds': [round(v, 4) for v in modl['bounds']],
        'origin': 'b__ROOT__' if root is not None else 'object position',
        'root_offset': [round(float(v), 5) for v in root_offset],
        'package': _where(T_OBJD, obj_def_id),
        'notes': report,
        'build_seconds': round(time.time() - t0, 2),
    }


_mem = {}
_mem_lock = threading.Lock()
_build_lock = threading.Lock()      # one build at a time (server threads): no duplicate work, no tmp-file races


def _load_json(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding='utf-8') as f:
            value = json.load(f)
        return value if value.get('version') == VERSION else None
    except Exception:
        return None


def object_mesh(obj_def_id, lod=0, piece=0, state=None):
    """Real game mesh of an object definition, in game-space metres with WickedWhims' origin (see module doc).
    -> {'name', 'meshes': [{'positions', 'normals', 'uvs', 'faces', 'texture', 'transparent', ...}], 'bounds', ...}
    positions/normals/uvs/faces are flat lists (xyz, xyz, uv, triangle index triples); 'texture' is a PNG file name
    under cache/furniture (DirectX UVs: load with flipY = false); 'water' marks water surfaces.
    piece: which of the object's models (modular counters/sectionals have several; 0 = as placed).
    state: geometry state name or '0x...' hash (None = 'Normal', else the catalog thumbnail state, else none).
    Cached in cache/furniture/<id>.json (other LODs/pieces/states get their own file)."""
    obj_def_id = int(obj_def_id)
    key = (obj_def_id, lod, piece, state)
    with _mem_lock:
        if key in _mem:
            return _mem[key]
    sh = _state_hash(state)
    suffix = ''.join(['_lod%d' % lod if lod else '', '_p%d' % piece if piece else '',
                      '_s%08x' % sh if sh is not None else ''])
    path = os.path.join(CACHE_DIR, '%d%s.json' % (obj_def_id, suffix))
    value = _load_json(path)
    if value is None:
        with _build_lock:
            value = _load_json(path)          # another thread may have built it meanwhile
            if value is None:
                value = _build(obj_def_id, lod, piece, state)
                os.makedirs(CACHE_DIR, exist_ok=True)
                tmp = '%s.%d.tmp' % (path, os.getpid())
                with open(tmp, 'w', encoding='utf-8') as f:
                    json.dump(value, f, separators=(',', ':'))
                os.replace(tmp, path)
    with _mem_lock:
        _mem[key] = value
    return value


# ------------------------------------------------------------------ WickedWhims locations
def example_objects():
    """WickedWhims' reference object definition id per sex location name (data/ or cache/ww_example_objects.json)."""
    with open(EXAMPLES_SHIPPED if os.path.exists(EXAMPLES_SHIPPED) else EXAMPLES, encoding='utf-8') as f:
        s = f.read()
    return json.loads(s[s.index('{'):])        # the file may start with a count line


# geometry state to show for a location when the automatic choice is not the in-use look
LOCATION_STATES = {'BLANKET': 'Blanket'}

# Objects shown instead of the reference object, first one the game has: beds with no headboard or footboard, so
# nothing is in the way of legs over the ends. Same rig, spots and mattress height as the reference bed (the double
# bed's rig is shared by every double bed; the single ones carry the same _bind_SB_ bones).
SHOWN = {
    'DOUBLE_BED': [241642, 68856, 20902],      # Eco Lifestyle mattress on pallets, Outdoor Retreat air bed, base game
                                               # (low headboard)
    'SINGLE_BED': [68869, 22953],              # Outdoor Retreat air bed, base game (low headboard)
}


def shown_object(loc):
    """The object id shown for a location: the first of SHOWN the game has, else WickedWhims' reference object."""
    loc = str(loc).upper()
    for oid in SHOWN.get(loc, ()):
        try:
            if source_of(oid) == 'game':
                return oid
        except Exception:
            break
    return example_objects().get(loc)


def furniture_for_location(name):
    """Mesh of the object shown for a location name (e.g. 'DOUBLE_BED'), or None."""
    loc = str(name).upper()
    oid = shown_object(loc)
    if oid is None:
        return None
    try:
        m = object_mesh(oid, state=LOCATION_STATES.get(loc))
    except (KeyError, ValueError):
        ref = example_objects().get(loc)
        if ref is None or ref == oid:
            return None
        try:
            m = object_mesh(ref, state=LOCATION_STATES.get(loc))
        except (KeyError, ValueError):
            return None
    return dict(m, location=loc)


def all_locations():
    """Every location with a resolvable reference object:
    [{'location', 'object_id', 'name', 'bounds', 'surface_height', 'geometry_state', 'slots'}] (cached)."""
    path = os.path.join(CACHE_DIR, 'locations_v%d.json' % VERSION)
    ex = example_objects()
    shown = {loc: shown_object(loc) for loc in SHOWN}
    if os.path.exists(path):
        try:
            with open(path, encoding='utf-8') as f:
                cached = json.load(f)
            if cached.get('examples') == ex and cached.get('shown') == shown:
                return cached['locations']
        except Exception:
            pass
    out = []
    for loc in ex:
        try:
            m = furniture_for_location(loc)
        except Exception:
            m = None
        if m is None:
            continue
        out.append({'location': loc, 'object_id': m['id'], 'name': m['name'], 'bounds': m['bounds'],
                    'surface_height': m['surface_height'], 'geometry_state': m['geometry_state'],
                    'slots': m.get('slots') or []})
    tmp = '%s.%d.tmp' % (path, os.getpid())
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump({'examples': ex, 'shown': shown, 'locations': out}, f, separators=(',', ':'))
    os.replace(tmp, path)
    return out


# ------------------------------------------------------------------ props (WickedWhims animation_props_list)
# Objects a sim holds or that stand in the scene during an animation (spec_bodies 10). A WickedWhims prop is an
# ordinary game or custom-content object: its OBJD instance is the prop GUID, and its rig (b__ROOT__ -> transformBone
# -> _FX_ for every EA prop) is moved by the prop clip's transformBone track.
PROPS_VERSION = 1
# adults only: child, teen, baby, school and pet things are never offered as props (on top of gamedata._BLOCK_WORDS)
_PROP_BLOCK = re.compile(r'homework|crib|pacifier|stroller|highchair|bottleBaby|babyBottle|bucketToy|diaper|potty|'
                         r'rattle|nursery|toyDoll|dollHouse|toyBall|toyHand|toyBox|toyTrain|BBY|school|kidsRoom|'
                         r'playMat|sippyCup|bassinet|changingTable', re.I)
_PROP_BLOCK_WORDS = re.compile(r'(?<![a-z])(pets?|dolphins?|avian|chickens?|roosters?|cows?|llamas?|goats?|sheep|pigs?|'
                               r'stuffed ?animals?|plushies?)(?![a-z])', re.I)
# hand-written names for the props creators use most (the rest are made from the object's name by nice())
PROP_LABELS = {
    'gadgetSmlPhoneCellGEN_01': 'Phone (cell)', 'gadgetSmlPhoneCellGEN_01_game': 'Phone (cell, gaming)',
    'handcuffGEN_01_set1': 'Handcuffs', 'drinkTumbler_EP08GENjuiceConfident': 'Drink (tumbler)',
    'magicWand_GP08GEN09_set1': 'Magic wand', 'cameraFilm_EP06GEN_set1': 'Film camera',
    'cameraFilm_EP06GENlow_set1': 'Film camera (small)', 'bookSkillManualComedy': 'Book (comedy manual)',
    'gameConsoleController_EP03GEN_set1': 'Game controller', 'motherPlant_GP07GEN': 'Mother plant',
    'drone_EP06GENlow_set1': 'Drone', 'photoCameraLrg_EP06GEN_set1': 'Photo camera (big)',
    'sitDiningSC_02_set1': 'Dining chair', 'bottleCulinaryGEN_01': 'Bottle',
    'sitDiningGENDeskChair_01_set1': 'Desk chair', 'toolStylusGENPencil_01': 'Pencil',
    'GameCards_GP01GEN': 'Playing cards', 'toolKnifeChefGEN_01_prop': 'Chef knife',
    'bookOpenSmlGEN_01': 'Book (open)', 'sitDining_EP02PUB_set1': 'Pub chair', 'drink_flirtypotion': 'Flirty potion',
    'toolSpoonGEN_01_prop': 'Spoon', 'photoCameraLrg_EP07RWcamouflage_set1': 'Photo camera (camouflage)',
    'voodooDollGEN_01': 'Voodoo doll', 'drinkCupOOLONGTea_01': 'Tea cup', 'stereoTableLOW_01_set1': 'Stereo',
    'simRay_EP01GEN01_set1': 'SimRay', 'drinkFlaskGEN_01_focused': 'Flask',
    'bottleMassage_EP07GENSunscreen_set1': 'Sunscreen', 'computerDesktopPortable_EF15RWfreelancer_set1': 'Laptop',
    'spongeGEN_01_prop': 'Sponge', 'drinkCan_GP01GENjuice_Expensive': 'Drink can', 'ringWED_01': 'Wedding ring',
    'toolMoneyStack_GEN': 'Money stack', 'toolPaddle_EP08GEN': 'Paddle', 'boxingGloveLeftGEN_01': 'Boxing glove (left)',
    'boxingGloveRightGEN_01': 'Boxing glove (right)', 'bottleMassage_GP02GEN_ylangYlang': 'Massage oil',
    'bottleMassage_GP02GEN_lotus': 'Massage oil (lotus)', 'eyelinerGEN_set1': 'Eyeliner',
    'photoCamera_EP01GENModerate_set1': 'Photo camera', 'drinkCupLrgGENSlushie_01': 'Slushie',
    'toolWrenchGENPipe_01': 'Pipe wrench', 'drinkCupGENCoffee_01': 'Coffee cup', 'drink_Stemmed_empty': 'Wine glass',
    'gadgetSmlPhoneHandsetGEN_01': 'Phone (handset)', 'toolMassageStone_GP02GEN': 'Massage stone',
    'mistletoe_EP05GEN': 'Mistletoe', 'boxGift_GEN_set1': 'Gift box', 'flowerSingleSmlGEN_01': 'Flower',
    'toolNailFileGEN_set1': 'Nail file', 'toolBlushBrushGEN_set1': 'Blush brush', 'paintBrushGEN_01': 'Paint brush',
}
_PACK_CODE = re.compile(r'(?:EP|GP|SP|FP|EF)\d{2}', re.I)
_NOISE = {'gen', 'sml', 'lrg', 'med', 'low', 'high', 'sc', 'qa', 'gf', 'cl', 'fc', 'rw', 'al', 'mis', 'prop', 'tud', 'set',
          'noir', 'ico', 'lod', 'x', 'c', 'm'}
_FIRST = {'sit': ' seat', 'sculpt': '', 'gadget': '', 'tool': '', 'deco': '', 'clutter': ''}


def nice(obj_name):
    """A plain name for an object: 'gadgetSmlPhoneCellGEN_01' -> 'Phone (cell)' (PROP_LABELS), else the object's name
    without pack codes, set and version numbers, creator prefixes and size words, camelCase split:
    'drinkCanGENEnergy_01' -> 'Drink can energy', 'sitDining_EP03METALstrappy_set10' -> 'Dining METAL strappy seat'."""
    name = str(obj_name or '').strip()
    if name in PROP_LABELS:
        return PROP_LABELS[name]
    name = name.split(':')[-1]
    toks = [t for t in re.split(r'[_\s]+', name) if t]
    # a creator's prefix ('LAMABOY_sculpt...', '0_tool...') in front of an EA-style name (which starts lower case)
    if len(toks) > 1 and (toks[0].isupper() or toks[0].isdigit() or (not toks[0][:1].islower() and toks[1][:1].islower())):
        toks = toks[1:]
    words = []
    for t in toks:
        if re.fullmatch(r'\d+|set\d+', t, re.I):
            continue
        t = _PACK_CODE.sub(' ', t).replace('GEN', ' ')
        # a capitals run glued to a word: 'METALstrappy' -> 'METAL strappy', 'FCRooster' -> 'FC Rooster',
        # 'LOWWoodwork' -> 'LOW Woodwork', 'OOLONGTea' -> 'OOLONG Tea'
        t = re.sub(r'([A-Z]{2,})([a-z]+)', lambda m: (m.group(1)[:-1] + ' ' + m.group(1)[-1] + m.group(2))
                   if m.group(1)[:-1].lower() in _NOISE or len(m.group(2)) <= 3
                   else m.group(1) + ' ' + m.group(2), t)
        for w in re.findall(r'[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+', t):
            if w.lower() in _NOISE or w.isdigit():
                continue
            words.append(w)
    if not words:
        return name or 'Prop'
    tail = ''
    if words[0].lower() in _FIRST and len(words) > 1:
        tail = _FIRST[words[0].lower()]
        words = words[1:]
    text = ' '.join(w.lower() for w in words) + tail
    return text[:1].upper() + text[1:]


def _words(name):
    """'sculptTableTUDDog_01' -> 'sculpt Table TUD Dog 01': camelCase, ALLCAPS runs and underscores split apart."""
    s = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', str(name or ''))
    s = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1 \2', s)
    return s.replace('_', ' ').replace('-', ' ')


def prop_blocked(obj_name, package=None):
    """True for objects that are never offered as props (adults only): child, teen, baby, school, animal and pet
    things, by the object's name (camelCase split too) or its package's path."""
    import gamedata
    raw = str(obj_name or '')
    split = _words(raw)
    if _PROP_BLOCK.search(raw) or _PROP_BLOCK_WORDS.search(split) or gamedata._BLOCK_WORDS.search(split):
        return True
    return bool(package) and gamedata.blocked_path(package)


def _objd_name(guid):
    data = _read(T_OBJD, 0, int(guid))
    if data is None:
        return None
    try:
        return parse_objd(data)['name'] or ''
    except Exception:
        return None


def _sig_hash(value):
    import hashlib
    return hashlib.md5(json.dumps(value, sort_keys=True, default=str).encode('utf-8')).hexdigest()


def _parked_objds(guids):
    """{guid: 'Mods_parked\\...\\pack.package'} for prop objects that only a parked pack has (the game does not load
    Mods_parked: the pack has to go back into Mods). Adults only: blocked packs are never named."""
    import gamedata
    want, found = set(guids), {}
    if not want:
        return found
    for p in sorted(glob.glob(os.path.join(gamedata.PARKED_DIR, '**', '*.package'), recursive=True)):
        if gamedata.blocked_path(p):
            continue
        try:
            idx = read_index(p)
        except Exception:
            continue
        for e in idx:
            if e['type'] == T_OBJD and e['inst'] in want and e['inst'] not in found:
                found[e['inst']] = os.path.relpath(p, gamedata.SIMS_DIR)
        if len(found) == len(want):
            break
    return found


_props_lock = threading.Lock()
_props = None


def _prop_data():
    """{'sig', 'items', 'missing': {animation id: [guid strings]}, 'parked': {guid: package}} made from the animation
    library (cached in cache/furniture/props_v1.json while the library and Mods stay the same)."""
    global _props
    import gamedata
    with _props_lock:
        lib = gamedata.library()
        _MODS.load()
        sig = json.loads(json.dumps([_sig_hash(lib['signature']), _MODS.signature(), PROPS_VERSION]))
        if _props is not None and _props.get('sig') == sig:
            return _props
        path = os.path.join(CACHE_DIR, 'props_v%d.json' % PROPS_VERSION)
        try:
            with open(path, encoding='utf-8') as f:
                cached = json.load(f)
            if cached.get('sig') == sig:
                cached['missing'] = {int(k): v for k, v in cached['missing'].items()}
                cached['parked'] = {int(k): v for k, v in cached['parked'].items()}
                _props = cached
                return _props
        except (OSError, ValueError, KeyError, AttributeError):
            pass
        uses, entries = {}, []
        for a in lib['animations']:
            for p in a.get('props') or []:
                gs = p.get('guids') or [p['guid']]
                entries.append((a['id'], gs))
                for g in gs:
                    uses[g] = uses.get(g, 0) + 1
        items, known, blocked = [], set(), set()
        for g, n in uses.items():
            src = source_of(g)
            if src is None:
                continue
            name = _objd_name(g)
            pkg = _where(T_OBJD, g) if src == 'mods' else None
            if name is None or prop_blocked(name, pkg):
                blocked.add(g)
                continue
            known.add(g)
            items.append({'guid': str(g), 'objName': name, 'name': nice(name), 'uses': n, 'source': src})
        items.sort(key=lambda x: (-x['uses'], x['name'].lower()))
        missing = {}
        for aid, gs in entries:
            if not any(g in known or g in blocked for g in gs):
                lst = missing.setdefault(aid, [])
                for g in gs:
                    if str(g) not in lst:
                        lst.append(str(g))
        parked = _parked_objds({int(g) for gs in missing.values() for g in gs})
        _props = {'sig': sig, 'items': items, 'missing': missing, 'parked': parked}
        os.makedirs(CACHE_DIR, exist_ok=True)
        tmp = '%s.%d.tmp' % (path, os.getpid())
        try:
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump({'sig': sig, 'items': items, 'missing': {str(k): v for k, v in missing.items()},
                           'parked': {str(k): v for k, v in parked.items()}}, f, separators=(',', ':'))
            os.replace(tmp, path)
        except OSError:
            try:
                os.remove(tmp)
            except OSError:
                pass
        return _props


def prop_list():
    """Every prop the animation library uses that the game or Mods has, adults only: [{'guid' (a string: 64-bit ids
    do not fit a JavaScript number), 'objName', 'name', 'uses', 'source': 'game'|'mods'}], most used first."""
    return _prop_data()['items']


def props_missing(anim_id):
    """The prop GUIDs (strings) a library animation needs that neither the game nor Mods has (a prop pack that is not
    installed, or only in Mods_parked) - [] when it has everything or has no props."""
    try:
        return _prop_data()['missing'].get(int(anim_id), [])
    except Exception:
        return []


def missing_props():
    """{animation id: {'guids': [...], 'parked': [packages in Mods_parked that have them]}} for every library
    animation that needs a prop pack."""
    d = _prop_data()
    return {aid: {'guids': gs, 'parked': sorted({d['parked'][int(g)] for g in gs if int(g) in d['parked']})}
            for aid, gs in d['missing'].items()}


def prop_ok(guid):
    """Can this object be shown as a prop? It exists (game or Mods) and passes the adults-only filters."""
    try:
        g = int(guid)
    except (TypeError, ValueError):
        return False
    src = source_of(g)
    if src is None:
        return False
    name = _objd_name(g)
    return name is not None and not prop_blocked(name, _where(T_OBJD, g) if src == 'mods' else None)


# ------------------------------------------------------------------ custom-content furniture in Mods
MODS_OBJECTS_VERSION = 1
_FURNITURE_WORDS = re.compile(r'(?<![a-z])(bed|beds|sofa|couch|loveseat|sectional|chair|seat|sit|stool|bench|ottoman|'
                              r'table|desk|counter|bar|tub|bathtub|hottub|sauna|shower|lounger|chaise|futon|mattress|'
                              r'daybed|pouf|cushion|swing|hammock|piano|dresser|vanity|island|pool)(?![a-z])', re.I)
_NOT_FURNITURE = re.compile(r'jig|invisible|positioning|stageMark|paintWall|puddle|arrow|rug|wallpaper|window|door|'
                            r'fence|light|lamp|mirrorWall|curtain', re.I)
_mods_objects_lock = threading.Lock()
_mods_objects = None


def _modl_bounds(od):
    try:
        data = _read(*od['models'][0])
        if data is None:
            return None
        return parse_modl(RCOL(data).chunks[0])['bounds']
    except Exception:
        return None


def _has_seat_joints(rig_key):
    try:
        data = _read(*rig_key)
        r = parse_rig(data) if data else None
    except Exception:
        return False
    return bool(r) and any(_SLOT_JOINT.match(b['name'] or '') and not _SLOT_SKIP.search(b['name'] or '') for b in r['bones'])


_KIND_WORDS = (('bed', r'bed|beds|mattress|futon|daybed'), ('sofa', r'sofa|couch|loveseat|sectional|chaise|lounger'),
               ('chair', r'chair|seat|sit|stool|bench|ottoman|pouf'), ('swing', r'swing|hammock'),
               ('tub', r'tub|bathtub|hottub|sauna|shower|pool'), ('counter', r'counter|bar|island|vanity'),
               ('table', r'table|desk|dresser|piano'))


def _kind_of(obj):
    """A guess at what the object is: 'bed', 'sofa', 'chair', 'swing', 'tub', 'counter', 'table', 'lie' (long enough
    to lie on) or 'surface' - from its spots, else its name, else the height of its top."""
    kinds = [s['kind'] for s in obj.get('slots') or []]
    if 'lie' in kinds and ('in' in kinds or 'edge' in kinds):
        return 'bed'
    seats = kinds.count('seat') + kinds.count('edge')
    if seats >= 2:
        return 'sofa'
    if seats == 1:
        return 'chair'
    words = _words(obj.get('objName'))
    for kind, rx in _KIND_WORDS:
        if re.search(r'(?<![a-z])(%s)(?![a-z])' % rx, words, re.I):
            return kind
    h = obj.get('surface_height') or 0
    if 'lie' in kinds and h < 0.6:
        return 'lie'
    return 'counter' if h >= 0.85 else 'table' if h >= 0.6 else 'surface'


def mods_objects(max_build=400):
    """Custom-content furniture in Mods that sims can be placed on (for "Move to another place", R3-3):
    [{'guid' (string), 'objName', 'name', 'package', 'kind' (_kind_of: 'bed', 'sofa', 'chair', 'swing', 'tub',
      'counter', 'table', 'lie', 'surface'), 'bounds', 'surface_height', 'slots', 'pieces', 'model',
      'swatches': [guids of its recolours]}]. Its mesh: object_mesh(int(guid)) (the same shape as the game's objects).

    Placeable: at least 40 x 40 cm on the floor, up to 3.5 m high, an up-facing top 0.15 - 1.3 m high, and seat or
    lying spots in its rig or a furniture word in its name (bed, sofa, chair, table, counter ...). Adults only: names
    and packages on the block lists are left out. Cached (cache/furniture/mods_objects_v1.json) while Mods stays the
    same; at most `max_build` objects not read before are read per call (the rest follow on the next call)."""
    global _mods_objects
    with _mods_objects_lock:
        _MODS.load()
        sig = json.loads(json.dumps([_MODS.signature(), MODS_OBJECTS_VERSION]))
        if _mods_objects is not None and _mods_objects.get('sig') == sig and _mods_objects.get('complete'):
            return _mods_objects['items']
        path = os.path.join(CACHE_DIR, 'mods_objects_v%d.json' % MODS_OBJECTS_VERSION)
        prev = {}
        try:
            with open(path, encoding='utf-8') as f:
                cached = json.load(f)
            if cached.get('sig') == sig:
                if cached.get('complete'):
                    _mods_objects = cached
                    return cached['items']
                prev = cached.get('seen') or {}          # objects judged in an unfinished pass over the same Mods
        except (OSError, ValueError, AttributeError):
            pass
        if _mods_objects is not None and _mods_objects.get('sig') == sig:
            prev = _mods_objects.get('seen') or prev
        items, seen, built, complete = [], {}, 0, True
        by_model, bad_models = {}, set()      # recolours ('swatches') share their object's model: one entry each
        for g in sorted(_MODS.instances(T_OBJD)):
            key = str(g)
            if key in prev:                      # judged before (an unfinished pass over the same Mods)
                p = prev[key]
                seen[key] = p
                if p and 'swatch_of' not in p:
                    p = seen[key] = dict(p, swatches=[])
                    by_model[tuple(p['model'])] = p
                    items.append(p)
                continue
            try:
                od = parse_objd(_MODS.read(T_OBJD, None, g))
            except Exception:
                seen[key] = None
                continue
            name, pkg = od['name'] or '', _MODS.where(T_OBJD, g)
            if not od['models'] or prop_blocked(name, pkg) or _NOT_FURNITURE.search(name):
                seen[key] = None
                continue
            model = [int(x) for x in od['models'][0]]
            mk = tuple(model)
            if mk in by_model:
                seen[key] = {'swatch_of': by_model[mk]['guid']}
                continue
            if mk in bad_models:
                seen[key] = None
                continue
            b = _modl_bounds(od)
            words = _FURNITURE_WORDS.search(_words(name))
            if (not b or (b[3] - b[0]) < 0.4 or (b[5] - b[2]) < 0.4 or b[4] < 0.15 or (b[4] - b[1]) > 3.5
                    or not (words or (od['rigs'] and _has_seat_joints(od['rigs'][0])))):
                seen[key] = None
                bad_models.add(mk)
                continue
            if built >= max_build:
                complete = False
                continue
            built += 1
            try:
                m = object_mesh(g)
            except Exception:
                m = None
            bb, h = (m['bounds'], m.get('surface_height')) if m else (None, None)
            if (h is None or not 0.15 <= h <= 1.3 or (bb['max'][0] - bb['min'][0]) < 0.4
                    or (bb['max'][2] - bb['min'][2]) < 0.4):
                seen[key] = None
                bad_models.add(mk)
                continue
            it = {'guid': key, 'objName': name, 'name': nice(name), 'package': pkg, 'bounds': bb, 'surface_height': h,
                  'slots': m.get('slots') or [], 'pieces': m.get('pieces', 1), 'model': model, 'swatches': []}
            it['kind'] = _kind_of(it)
            seen[key] = by_model[mk] = it
            items.append(it)
        by_guid = {it['guid']: it for it in items}
        for key, p in seen.items():
            if p and p.get('swatch_of') in by_guid:
                by_guid[p['swatch_of']]['swatches'].append(key)
        items.sort(key=lambda x: (x['kind'], x['name'].lower()))
        _mods_objects = {'sig': sig, 'items': items, 'complete': complete, 'seen': seen}
        os.makedirs(CACHE_DIR, exist_ok=True)
        tmp = '%s.%d.tmp' % (path, os.getpid())
        try:
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(_mods_objects, f, separators=(',', ':'))
            os.replace(tmp, path)
        except OSError:
            try:
                os.remove(tmp)
            except OSError:
                pass
        return items
