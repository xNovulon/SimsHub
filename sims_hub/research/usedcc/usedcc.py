"""usedcc - which CC do the user's sims / lots actually use?

Read-only on the game and on the Sims 4 user folder. Everything written goes next to this file.

    python usedcc.py verify [N]     parse N random CASPs (+ all RefPack ones), check the TGI-list layout,
                                    count referenced types and whether they resolve in the library / game
    python usedcc.py scan           read every save (*.save, *.save.ver*, *.day.ver*) + Tray item and
                                    collect every 64-bit value (generic protobuf walk) -> ids.sqlite
    python usedcc.py report         intersect the collected ids with the library -> numbers + used-pack size

Library index: ../../data/library.sqlite (res.i is a SIGNED 64-bit instance).
"""
import collections, json, os, random, sqlite3, struct, sys, time, zlib

HERE = os.path.dirname(os.path.abspath(__file__))
SIMS = os.path.join(os.path.expanduser('~'), 'Documents', 'Electronic Arts', 'The Sims 4')
LIBDB = os.path.join(HERE, '..', '..', 'data', 'library.sqlite')
GAME = r'E:\The Sims 4'

T_CASP = 0x034AEECB
T_GEOM = 0x015A1849
T_RLE2 = 0x3453CF95
T_LRLE = 0x2BC04EDF
T_RLES = 0xBA856C78
T_IMG = 0x00B2D882     # _IMG / DDS
T_THUM = 0x3C1AF1F2    # CAS part thumbnail (PNG), instance == CASP instance
T_RMAP = 0xAC16FBEC
T_BOND = 0x0355E0A6
T_OBJD = 0xC0DB5AE7
T_COBJ = 0x319E4F1D
T_TONE = 0x0354796A
T_SMOD = 0xC5F6763E
T_CPRE = 0xEAA32ADD    # CAS preset
T_SIMO = 0x025ED6F4    # sim outfit (sim template "outfit" resource)
T_DMAP = 0xDB43E069
T_BGEO = 0x067CAA11
T_BUFF_TUNING = 0x6017E896
T_STBL = 0x220557DA
T_OBJ_THUMB = 0x3C2A8647  # buy/build thumbnail
T_MLOD = 0x01D10F34
T_MODL = 0x01661233
T_FTPT = 0xD382BF57
T_RSLT = 0xD3044521
T_LITE = 0x03B4C61D

NAMES = {T_CASP: 'CASP', T_GEOM: 'GEOM', T_RLE2: 'RLE2', T_LRLE: 'LRLE', T_RLES: 'RLES', T_IMG: '_IMG',
         T_THUM: 'THUM', T_RMAP: 'RMAP', T_BOND: 'BOND', T_OBJD: 'OBJD', T_COBJ: 'COBJ', T_TONE: 'TONE',
         T_SMOD: 'SMOD', T_CPRE: 'CPRE', T_SIMO: 'SIMO', T_DMAP: 'DMAP', T_BGEO: 'BGEO',
         T_BUFF_TUNING: 'BUFF', T_STBL: 'STBL', T_OBJ_THUMB: 'OTHM', T_MLOD: 'MLOD', T_MODL: 'MODL',
         T_FTPT: 'FTPT', T_RSLT: 'RSLT', T_LITE: 'LITE', 0: 'null'}


def tname(t):
    return NAMES.get(t, '%08X' % t)


def s64(i):
    return i - (1 << 64) if i >= (1 << 63) else i


def u64(i):
    return i & 0xFFFFFFFFFFFFFFFF


def U64hex(i):
    return '%016X' % u64(i)


# ----------------------------------------------------------------------------- DBPF / compression

def refpack_decompress(src):
    """EA RefPack ("internal compression", DBPF comp 0xFFFF)."""
    flags = src[0]
    if src[1] != 0xFB:
        raise ValueError('not RefPack (magic %02X%02X)' % (src[0], src[1]))
    if flags & 0x80:
        size = int.from_bytes(src[2:6], 'big'); p = 6
    else:
        size = int.from_bytes(src[2:5], 'big'); p = 5
    if flags & 0x01:          # compressed size also stored
        p += 4 if flags & 0x80 else 3
    out = bytearray()
    n = len(src)
    while p < n:
        b0 = src[p]
        if b0 < 0x80:
            b1 = src[p + 1]; p += 2
            plain = b0 & 3; clen = ((b0 & 0x1C) >> 2) + 3; coff = ((b0 & 0x60) << 3) + b1 + 1
        elif b0 < 0xC0:
            b1 = src[p + 1]; b2 = src[p + 2]; p += 3
            plain = b1 >> 6; clen = (b0 & 0x3F) + 4; coff = ((b1 & 0x3F) << 8) + b2 + 1
        elif b0 < 0xE0:
            b1 = src[p + 1]; b2 = src[p + 2]; b3 = src[p + 3]; p += 4
            plain = b0 & 3; clen = ((b0 & 0x0C) << 6) + b3 + 5; coff = ((b0 & 0x10) << 12) + (b1 << 8) + b2 + 1
        elif b0 < 0xFC:
            plain = ((b0 & 0x1F) << 2) + 4; p += 1
            out += src[p:p + plain]; p += plain
            continue
        else:
            plain = b0 & 3; p += 1
            out += src[p:p + plain]
            break
        if plain:
            out += src[p:p + plain]; p += plain
        start = len(out) - coff
        if coff >= clen:
            out += out[start:start + clen]
        else:                  # overlapping copy: repeat the period
            chunk = out[start:]
            while clen > 0:
                take = chunk[:clen]
                out += take
                clen -= len(take)
                chunk = out[start:]
    if len(out) != size:
        raise ValueError('RefPack size mismatch %d != %d' % (len(out), size))
    return bytes(out)


def decode(raw, comp, msize=None):
    if comp == 0:
        return raw
    if comp == 0x5A42:
        return zlib.decompress(raw)
    if comp == 0xFFFF:
        return refpack_decompress(raw)
    raise ValueError('compression 0x%04X not handled' % comp)


def read_index(path):
    """[(t, g, i_unsigned, off, fsize, msize, comp)] - same as tools/scan_library.read_index"""
    sys.path.insert(0, os.path.join(HERE, '..', '..', 'tools'))
    from scan_library import read_index as ri
    return ri(path)


class PkgReader:
    """Cache of open file handles for reading many resources."""
    def __init__(self):
        self.fh = {}

    def read(self, path, off, fsize, comp, msize=None):
        f = self.fh.get(path)
        if f is None:
            if len(self.fh) > 64:
                for x in self.fh.values():
                    x.close()
                self.fh.clear()
            f = self.fh[path] = open(path, 'rb')
        f.seek(off)
        return decode(f.read(fsize), comp, msize)

    def close(self):
        for x in self.fh.values():
            x.close()
        self.fh.clear()


def lib():
    return sqlite3.connect('file:%s?mode=ro' % os.path.abspath(LIBDB).replace('\\', '/'), uri=True)


LOCALDB = os.path.join(HERE, 'libti.sqlite')


def libti():
    """Local copy of the library index with (t,i) and (i) indexes (the shared DB only has (t,g,i) and (pkg)),
    rebuilt when library.sqlite is newer. Lives in this research folder."""
    src = os.path.abspath(LIBDB)
    if not os.path.exists(LOCALDB) or os.path.getmtime(LOCALDB) < os.path.getmtime(src):
        if os.path.exists(LOCALDB):
            os.remove(LOCALDB)
        t0 = time.time()
        db = sqlite3.connect('file:%s' % LOCALDB.replace(os.sep, '/'), uri=True)
        db.execute("attach database ? as L", ('file:%s?mode=ro' % src.replace(os.sep, '/'),))
        db.executescript("""create table res as select * from L.res; create table pkg as select * from L.pkg;
            create index res_tgi on res(t,g,i); create index res_ti on res(t,i); create index res_i on res(i); analyze;""")
        db.commit()
        db.execute('detach database L')
        db.close()
        print('built %s in %.1fs' % (LOCALDB, time.time() - t0))
    return sqlite3.connect(LOCALDB)


def pkg_paths(db):
    return {pid: os.path.join(SIMS, root, rel) for pid, root, rel in db.execute('select id, root, rel from pkg')}


# ----------------------------------------------------------------------------- CASP

def casp_refs(data):
    """Resource keys listed in a CASP (0x034AEECB) resource, in list order (index 0 is usually a null key).

    Layout (verified on this library): uint32 version; uint32 tgi_offset, counted from byte 8 (so the list
    starts at data[8 + tgi_offset]); ... header ...; at the list: uint8 count, then count x 16-byte entries
    in I-G-T order: uint64 instance, uint32 group, uint32 type (little endian). The list runs to the end
    of the resource. Returns [(t, g, i_unsigned)]."""
    p = 8 + struct.unpack_from('<I', data, 4)[0]
    n = data[p]
    if p + 1 + 16 * n > len(data):
        raise ValueError('CASP TGI list overruns resource')
    out = []
    for k in range(n):
        i, g, t = struct.unpack_from('<QII', data, p + 1 + 16 * k)
        out.append((t, g, i))
    return out


def casp_header(data):
    """Parse the whole CASP header (layout of CmarNYC TS4SimRipper src/CASP.cs, versions 0x1B-0x34) and
    return a dict. 'tail_ok' is True when parsing ended exactly where the TGI list starts (8 + tgi_offset),
    which cross-checks the layout; key fields are byte indexes into casp_refs(data)."""
    v, toff = struct.unpack_from('<II', data, 0)
    tgi_pos = 8 + toff
    h = {'version': v}
    p = 12                                   # presetCount (uint32) at 8
    nlen = data[p]; p += 1                   # .NET 7-bit length prefix, big-endian UTF-16 name
    if nlen & 0x80:
        nlen = (nlen & 0x7F) | (data[p] << 7); p += 1
    h['name'] = data[p:p + nlen].decode('utf-16-be', 'replace'); p += nlen
    p += 4 + 2                               # sortPriority, swatch order
    h['outfit_id'] = struct.unpack_from('<I', data, p)[0]; p += 4
    p += 4                                   # aural material hash
    h['parm_flags'] = data[p]; p += 1
    if v >= 39: p += 1                       # parmFlags2
    if v >= 50: p += 2                       # layer id
    if v >= 51:
        n = struct.unpack_from('<i', data, p)[0]; p += 4 + 8 * n
    else:
        p += 8
        if v >= 41: p += 8
    p += 8 if v > 36 else 4                  # excludeModifierRegionFlags
    nf = struct.unpack_from('<i', data, p)[0]; p += 4
    p += nf * (6 if v >= 37 else 4)          # tags: uint16 category + uint32 (uint16 before v37) value
    h['tags'] = nf
    p += 12                                  # price, title key, description key
    if v >= 0x2B: p += 4
    p += 1                                   # texture space
    h['body_type'], h['body_sub_type'], h['age_gender'] = struct.unpack_from('<III', data, p); p += 12
    if v >= 32:
        h['species'] = struct.unpack_from('<I', data, p)[0]; p += 4
    if v >= 34:
        h['pack_id'] = struct.unpack_from('<H', data, p)[0]; p += 2 + 1 + 9
    else:
        u = data[p]; p += 1
        if u: p += 1
    nsw = data[p]; p += 1 + 4 * nsw
    h['swatches'] = nsw
    h['buff_key'] = data[p]; h['variant_thumb_key'] = data[p + 1]; p += 2
    if v >= 28: p += 8                       # voice effect
    if v >= 30:
        um = data[p]; p += 1
        if um: p += 12
    if v >= 31: p += 4                       # occult bit field
    if v >= 0x2E: p += 8                     # unknown uint64
    if v >= 38:
        h['opposite_gender_part'] = struct.unpack_from('<Q', data, p)[0]; p += 8
    if v >= 39:
        h['fallback_part'] = struct.unpack_from('<Q', data, p)[0]; p += 8
    if v >= 44: p += 8 + 3 * 12              # opacity (min, inc) + hue/sat/brightness sliders (min, max, inc)
    if v >= 0x2E:
        n = data[p]; p += 1 + n
    h['naked_key'] = data[p]; h['parent_key'] = data[p + 1]; p += 2
    h['sort_layer'] = struct.unpack_from('<i', data, p)[0]; p += 4
    lods = []
    nl = data[p]; p += 1
    for _ in range(nl):
        level = data[p]; p += 1 + 4
        na = data[p]; p += 1 + 12 * na
        nk = data[p]; p += 1
        lods.append((level, list(data[p:p + nk]))); p += nk
    h['lods'] = lods
    ns = data[p]; h['slot_keys'] = list(data[p + 1:p + 1 + ns]); p += 1 + ns
    h['diffuse_key'], h['shadow_key'], h['composition'], h['region_map_key'] = data[p:p + 4]; p += 4
    no = data[p]; p += 1 + 5 * no
    h['normal_key'], h['specular_key'] = data[p], data[p + 1]; p += 2
    if v >= 27: p += 4                       # shared UV map space
    if v >= 29:
        h['emission_key'] = data[p]; p += 1
    if v >= 42: p += 1
    if v >= 49: p += 1
    if v >= 52: p += 1
    h['tail_ok'] = p == tgi_pos
    h['end'] = p
    h['tgi_pos'] = tgi_pos
    return h


# ----------------------------------------------------------------------------- game (EA) key index

GAMEDB = os.path.join(HERE, 'game_keys.sqlite')


def build_game_index(types=None):
    """Index (t,g,i) of the EA game packages (read-only on E:\\The Sims 4) -> game_keys.sqlite here."""
    if os.path.exists(GAMEDB):
        os.remove(GAMEDB)
    db = sqlite3.connect(GAMEDB)
    db.execute('create table k(t integer, g integer, i integer, pkg text, msize integer)')
    n = 0
    t0 = time.time()
    for dp, dn, fn in os.walk(GAME):
        for f in fn:
            if not f.lower().endswith('.package'):
                continue
            path = os.path.join(dp, f)
            try:
                idx = read_index(path)
            except Exception as e:
                print('skip', path, e)
                continue
            rel = os.path.relpath(path, GAME)
            db.executemany('insert into k values(?,?,?,?,?)',
                           [(t, g, s64(i), rel, ms) for t, g, i, off, fs, ms, c in idx
                            if types is None or t in types])
            n += 1
    db.execute('create index k_tgi on k(t,g,i)')
    db.execute('create index k_ti on k(t,i)')
    db.execute('create index k_i on k(i)')
    db.execute('analyze')
    db.commit()
    print('game index: %d packages in %.1fs' % (n, time.time() - t0))


# ----------------------------------------------------------------------------- (a) verify CASP layout

def verify(n_sample=2000, seed=1):
    db = lib()
    paths = pkg_paths(db)
    rows = db.execute('select rowid, pkg, g, i, off, fsize, msize, comp from res where t=?', (T_CASP,)).fetchall()
    random.seed(seed)
    sample = [r for r in rows if r[7] == 0xFFFF] + random.sample([r for r in rows if r[7] != 0xFFFF], n_sample)
    sample.sort(key=lambda r: (r[1], r[4]))
    gdb = sqlite3.connect(GAMEDB) if os.path.exists(GAMEDB) else None
    rd = PkgReader()
    st = collections.Counter()
    ver = collections.Counter()
    types = collections.Counter()
    resolved = collections.Counter()
    thumbs = collections.Counter()
    key_use = collections.Counter()
    hdr_ver = collections.Counter()
    bad = []
    t0 = time.time()
    for rowid, pkg, g, i, off, fsize, msize, comp in sample:
        try:
            data = rd.read(paths[pkg], off, fsize, comp)
        except Exception as e:
            st['read_fail_%04X' % comp] += 1
            bad.append((paths[pkg], i, str(e)))
            continue
        st['parsed_comp_%04X' % comp] += 1
        v, toff = struct.unpack_from('<II', data, 0)
        ver[v] += 1
        try:
            refs = casp_refs(data)
        except Exception as e:
            st['tgi_fail'] += 1
            bad.append((paths[pkg], i, str(e)))
            continue
        p = 8 + toff
        if p + 1 + 16 * len(refs) == len(data):
            st['tgi_list_ends_at_eof'] += 1
        else:
            st['tgi_list_not_at_eof'] += 1
        try:
            h = casp_header(data)
            st['header_tail_ok' if h['tail_ok'] else 'header_tail_mismatch'] += 1
            hdr_ver[(v, h['tail_ok'])] += 1
            if not h['tail_ok'] and len(bad) < 40:
                bad.append((paths[pkg], U64hex(i), 'v%d header ended at %d, list at %d' % (v, h['end'], h['tgi_pos'])))
            if h['tail_ok']:
                for k in ('naked_key', 'parent_key', 'diffuse_key', 'shadow_key', 'region_map_key',
                          'normal_key', 'specular_key', 'emission_key', 'buff_key', 'variant_thumb_key'):
                    if k in h:
                        idx = h[k]
                        key_use[(k, tname(refs[idx][0]) if idx < len(refs) else 'out_of_range')] += 1
                for level, ks in h['lods']:
                    for idx in ks:
                        key_use[('lod%d' % level, tname(refs[idx][0]) if idx < len(refs) else 'out_of_range')] += 1
        except Exception as e:
            st['header_fail'] += 1
            hdr_ver[(v, 'exc')] += 1
            if len(bad) < 40:
                bad.append((paths[pkg], U64hex(i), 'v%d header exception %r' % (v, e)))
        for t, gg, ii in refs:
            if t == 0 and gg == 0 and ii == 0:
                types['null'] += 1
                continue
            types[tname(t)] += 1
            if db.execute('select 1 from res where t=? and g=? and i=? limit 1', (t, gg, s64(ii))).fetchone():
                resolved[(tname(t), 'library')] += 1
            elif gdb and gdb.execute('select 1 from k where t=? and g=? and i=? limit 1', (t, gg, s64(ii))).fetchone():
                resolved[(tname(t), 'game')] += 1
            else:
                resolved[(tname(t), 'missing')] += 1
        # thumbnail keyed by the CASP instance?
        th = db.execute('select g from res where t=? and i=?', (T_THUM, i)).fetchall()
        thumbs['has_thum_same_instance' if th else 'no_thum_same_instance'] += 1
        for (tg,) in set(th):
            thumbs['thum_group_%08X' % tg] += 1
    rd.close()
    print('sampled %d CASPs in %.1fs' % (len(sample), time.time() - t0))
    out = {'status': dict(st), 'versions': {str(k): v for k, v in sorted(ver.items())},
           'ref_types': dict(types.most_common()),
           'resolution': {'%s/%s' % k: v for k, v in sorted(resolved.items())},
           'thumbnails': dict(thumbs.most_common(20)),
           'key_fields': {'%s->%s' % k: v for k, v in sorted(key_use.items())},
           'header_by_version': {'%s/%s' % k: v for k, v in sorted(hdr_ver.items(), key=str)},
           'failures': bad[:40]}
    print(json.dumps(out, indent=1))
    with open(os.path.join(HERE, 'verify_casp.json'), 'w') as f:
        json.dump(out, f, indent=1)


# ----------------------------------------------------------------------------- (b) scan saves + tray

import pbwalk

ASSET_TYPES = {T_RLE2, T_LRLE, T_GEOM, T_IMG, T_THUM, T_RLES, T_RMAP, T_MLOD, T_MODL, T_STBL, T_OBJ_THUMB,
               0x6B20C4F3, 0xBC4A5044, 0x01A527DB, 0x7FB6AD8A, 0x376840D7, 0xB6C8B6A0, 0x62ECC59A, 0x626F60CE}
IMAGE_SAVE_TYPES = {0x0F, 0x10, 0x14, 0xE88DB35F}
SAVES = os.path.join(SIMS, 'saves')
TRAY = os.path.join(SIMS, 'Tray')
TRAY_EXT = ('.householdbinary', '.trayitem', '.sgi', '.hhi', '.room', '.blueprint', '.bpi', '.rmi')
BIG = 1 << 32

# path suffixes (protobuf field numbers; 0 = element of a packed list) with a known meaning, from the game's
# own schema (Game/Bin/Python/generated.zip: Outfits.proto, FileSerialization.proto, PersistenceBlobs.proto)
SEMANTIC = [
    ((21, 1, 5, 1, 8), 'outfit_part'),       # SimData.outfits(21).outfits(1).parts(5)=IdList .ids(1): packed fixed64
    ((28, 5, 1, 1), 'genetic_part'),         # SimData.genetic_data(28).parts_list(5).parts(1).id(1) uint64
    ((28, 6, 1, 1), 'genetic_part'),         # ... growth_parts_list(6)
    ((1, 30), 'object_guid'),                # ObjectList.objects(1).guid(30) = object definition id (uint64)
    ((18, 1, 0), 'sculpt'),                  # SimData.facial_attr(18) = BlobSimFacialCustomizationData .sculpts(1) packed
    ((18, 2, 1), 'face_modifier'), ((18, 3, 1), 'body_modifier'),     # .face/body_modifiers(2/3).key(1)
    ((18, 4, 1), 'face_modifier'), ((18, 5, 1), 'body_modifier'),     # aged_face/body_modifiers
    ((12, 1, 0), 'sculpt'),                  # MannequinSimData.facial_attributes(12)
    ((12, 2, 1), 'face_modifier'), ((12, 3, 1), 'body_modifier'),
    ((12, 4, 1), 'face_modifier'), ((12, 5, 1), 'body_modifier'),
    ((6, 10), 'skin_tone'),                  # SaveGameData.sims(6).skin_tone(10) / SimList.sims(1).skin_tone(10)
    ((1, 1, 10), 'skin_tone'),
    ((15, 13), 'skin_tone'),                 # SaveGameData.mannequins(15).skin_tone(13)
    ((63, 1, 1), 'pelt_layer'),              # SimData.pelt_layers(63).layers(1).layer_id(1)
]
_SEM_LAST = {suf[-1] for suf, _ in SEMANTIC}


def semantic(path):
    for suf, name in SEMANTIC:
        if path[-len(suf):] == suf:
            return name
    return None


def load_idsets():
    """({unsigned instance: (library types...)} for non-asset types, sorted numpy array of the ids >= 2^32)"""
    import numpy as np
    db = lib()
    lib_ids = {}
    for t, i in db.execute('select distinct t, i from res'):
        if t in ASSET_TYPES:
            continue
        u = u64(i)
        prev = lib_ids.get(u)
        if prev is None:
            lib_ids[u] = (t,)
        elif t not in prev:
            lib_ids[u] = prev + (t,)
    big = np.array(sorted(u for u in lib_ids if u >= BIG), dtype=np.uint64)
    return lib_ids, big


def raw_scan(buf, s, e, big):
    """every unaligned 8-byte little-endian value in buf[s:e] that is a library instance >= 2^32"""
    import numpy as np
    mv = memoryview(buf)[s:e]
    n = len(mv)
    found = []
    for k in range(8):
        m = (n - k) // 8
        if m <= 0:
            continue
        a = np.frombuffer(mv[k:k + 8 * m], dtype='<u8')
        a = a[a >= BIG]
        if len(a) == 0:
            continue
        idx = np.searchsorted(big, a)
        idx[idx >= len(big)] = 0
        found.extend(int(x) for x in a[big[idx] == a])
    return found


def looks_image(b, s=0):
    h = bytes(b[s:s + 4])
    return h[:3] == b'\xff\xd8\xff' or h == b'\x89PNG'


class Collector:
    def __init__(self, lib_ids, big):
        self.lib_ids, self.big = lib_ids, big
        self.hits = collections.Counter()      # (value, path) -> n  (library instances, any path)
        self.typed = collections.Counter()     # (category, value) -> n (known-meaning paths, any value)
        self.opaque = collections.Counter()
        self.raw_hits = collections.Counter()  # (value, path) -> n  from raw 8-byte scan of opaque blobs
        self.values = 0

    def emit(self, path, v):
        self.values += 1
        if v in self.lib_ids:
            self.hits[(v, path)] += 1
        if path[-1] in _SEM_LAST:
            name = semantic(path)
            if name:
                self.typed[(name, v)] += 1

    def op(self, buf):
        def f(path, s, e):
            self.opaque[path] += e - s
            if e - s >= 8 and not looks_image(buf, s):
                for v in raw_scan(buf, s, e, self.big):
                    self.raw_hits[(v, path + ('raw',))] += 1
        return f

    def proto(self, buf, start=0, end=None, prefix=()):
        return pbwalk.walk(buf, self.emit, self.op(buf), start, end, prefix)

    def raw(self, buf, prefix):
        for v in raw_scan(buf, 0, len(buf), self.big):
            self.raw_hits[(v, prefix + ('raw',))] += 1


def scan_file(args):
    path, kind = args
    lib_ids, big = _G['ids']
    c = Collector(lib_ids, big)
    info = {'file': path, 'kind': kind, 'resources': 0, 'images': 0, 'unparsed': 0, 'bytes': 0}
    t0 = time.time()
    if kind == 'save':
        with open(path, 'rb') as f:
            for t, g, i, off, fs, ms, comp in read_index(path):
                if comp == 0xFFE0:           # deleted record
                    info['deleted'] = info.get('deleted', 0) + 1
                    continue
                f.seek(off)
                try:
                    data = decode(f.read(fs), comp)
                except Exception as e:
                    info.setdefault('errors', []).append('%08X:%016X %s' % (t, i, e))
                    continue
                info['resources'] += 1
                info['bytes'] += len(data)
                if t in IMAGE_SAVE_TYPES or looks_image(data):
                    info['images'] += 1
                    continue
                if not c.proto(data, prefix=('R%X' % t,)):
                    info['unparsed'] += 1
                    c.raw(data, ('R%X' % t,))
    else:
        data = open(path, 'rb').read()
        info['bytes'] = len(data)
        ext = os.path.splitext(path)[1].lower()
        ok = False
        if ext in ('.sgi', '.hhi', '.bpi', '.rmi'):
            info['images'] += 1          # thumbnails (obfuscated JPEG), no ids
            ok = True
        elif ext == '.trayitem':
            ok = c.proto(data, 8, None, ('trayitem',))
        elif ext == '.householdbinary':
            L = struct.unpack_from('<I', data, 12)[0]
            ok = c.proto(data, 16, 16 + L, ('hh',)) or c.proto(data, 16, None, ('hh',))
        if not ok:
            info['unparsed'] += 1
            c.raw(data, (ext[1:],))
            # ObjectData.guid tag (field 30 varint = bytes F0 01) inside C++-framed lot data (.blueprint/.room)
            p = data.find(b'\xf0\x01')
            while p >= 0:
                try:
                    v, _ = pbwalk._varint(data, p + 2, len(data))
                    if v in lib_ids:
                        c.hits[(v, (ext[1:], 'tag30'))] += 1
                    c.typed[('object_guid_tag30', v)] += 1
                except ValueError:
                    pass
                p = data.find(b'\xf0\x01', p + 2)
    info['secs'] = round(time.time() - t0, 2)
    info['values'] = c.values
    return info, dict(c.hits), dict(c.typed), dict(c.raw_hits), {'.'.join(map(str, k)): v for k, v in c.opaque.most_common(10)}


_G = {}


def _init():
    _G['ids'] = load_idsets()


def list_sources():
    out = []
    for n in sorted(os.listdir(SAVES)):
        p = os.path.join(SAVES, n)
        if os.path.isfile(p) and '.save' in n:
            out.append((p, 'save'))
    for n in sorted(os.listdir(TRAY)):
        if n.lower().endswith(TRAY_EXT):
            out.append((os.path.join(TRAY, n), 'tray'))
    return out


def scan(workers=2, only=None):
    import multiprocessing as mp
    srcs = list_sources()
    if only:
        srcs = [s for s in srcs if only in s[0]]
    srcs.sort(key=lambda s: -os.path.getsize(s[0]))       # big saves first
    out = sqlite3.connect(os.path.join(HERE, 'ids.sqlite'))
    out.executescript("""drop table if exists src; drop table if exists hit; drop table if exists typed; drop table if exists raw;
        create table src(id integer primary key, file text, kind text, info text);
        create table hit(src integer, v integer, path text, n integer);
        create table typed(src integer, cat text, v integer, n integer);
        create table raw(src integer, v integer, path text, n integer);""")
    t0 = time.time()
    with mp.Pool(workers, initializer=_init) as pool:
        for k, (info, hits, typed, raw, opaque) in enumerate(pool.imap_unordered(scan_file, srcs, chunksize=1)):
            info['opaque'] = opaque
            sid = out.execute('insert into src(file, kind, info) values(?,?,?)',
                              (info['file'], info['kind'], json.dumps(info))).lastrowid
            out.executemany('insert into hit values(?,?,?,?)', [(sid, s64(v), '.'.join(map(str, p)), n) for (v, p), n in hits.items()])
            out.executemany('insert into typed values(?,?,?,?)', [(sid, c, s64(v), n) for (c, v), n in typed.items()])
            out.executemany('insert into raw values(?,?,?,?)', [(sid, s64(v), '.'.join(map(str, p)), n) for (v, p), n in raw.items()])
            out.commit()
            if info['kind'] == 'save' or k % 100 == 0:
                print('%4d/%d %6.1fs %s %.0f MB %ss values=%d hits=%d typed=%d raw=%d' % (
                    k + 1, len(srcs), time.time() - t0, os.path.basename(info['file']), info['bytes'] / 1e6,
                    info['secs'], info['values'], len(hits), len(typed), len(raw)), flush=True)
    out.commit()
    print('scan done in %.1fs' % (time.time() - t0))


# ----------------------------------------------------------------------------- (c) report: what does a used-only pack need?

TEXTURE_TYPES = (T_RLE2, T_LRLE, T_RLES, T_IMG)
T_SCUL = 0x9D1AB874


def embedded_keys(data, types, db, skip=None):
    """Resource keys embedded anywhere in `data` (IGT, ITG or TGI 16-byte layouts) that exist in the library."""
    out = set()
    n = len(data)
    for k in range(0, n - 15):
        i, a, b = struct.unpack_from('<QII', data, k)
        cands = []
        if b in types: cands.append((b, a, i))          # I G T  (CASP)
        if a in types:
            cands.append((a, b, i))                     # I T G  (RCOL)
            cands.append((a, b, ((i & 0xFFFFFFFF) << 32) | (i >> 32)))   # Ihi Ilo T G  (OBJD properties)
        t = struct.unpack_from('<I', data, k)[0]
        if t in types:
            g, ii = struct.unpack_from('<IQ', data, k + 4)
            cands.append((t, g, ii))                    # T G I
        for key in cands:
            if key == skip or key in out or key[2] == 0:
                continue
            if db.execute('select 1 from res where t=? and g=? and i=? limit 1', (key[0], key[1], s64(key[2]))).fetchone():
                out.add(key)
    return out


class Pack:
    """Unique resource keys a used-only pack needs; one on-disk copy per key is counted."""
    def __init__(self, db):
        self.db = db
        self.keys = {}           # (t,g,i) -> (fsize, msize, pkg)
        self.why = collections.Counter()

    def add(self, key, why):
        if key in self.keys:
            return True
        r = self.db.execute('select fsize, msize, pkg from res where t=? and g=? and i=? order by pkg limit 1',
                            (key[0], key[1], s64(key[2]))).fetchone()
        if not r:
            return False
        self.keys[key] = r
        self.why[why] += 1
        return True

    def add_instance(self, t, i, why):
        n = 0
        for (g,) in self.db.execute('select distinct g from res where t=? and i=?', (t, s64(i))).fetchall():
            n += self.add((t, g, i), why)
        return n

    def totals(self):
        by = collections.Counter(); byn = collections.Counter(); mem = 0
        for (t, g, i), (fs, ms, pkg) in self.keys.items():
            by[tname(t)] += fs; byn[tname(t)] += 1; mem += ms
        return {'keys': len(self.keys), 'bytes_on_disk': sum(by.values()), 'bytes_uncompressed': mem,
                'by_type_bytes': dict(by.most_common()), 'by_type_count': dict(byn.most_common())}


def cas_closure(db, gdb, paths, used):
    """CASPs (every group copy of each used instance) + every key in their TGI lists that exists in the
    library + their THUM thumbnails. EA-game keys are not packed. Falls back to same type/other group and
    to another texture type with the same instance when the exact key is not in the library."""
    pack = Pack(db)
    rd = PkgReader()
    res_stats = collections.Counter()
    missing_by_type = collections.Counter()
    missing_examples = []
    t0 = time.time()
    for v in sorted(used):
        for g, pkg, off, fs, comp in db.execute('select g, pkg, off, fsize, comp from res where t=? and i=? group by g', (T_CASP, s64(v))).fetchall():
            pack.add((T_CASP, g, v), 'CASP')
            try:
                refs = casp_refs(rd.read(paths[pkg], off, fs, comp))
            except Exception:
                res_stats['casp_unreadable'] += 1
                continue
            for t, gg, ii in refs:
                if t == 0 or ii == 0:
                    continue
                if pack.add((t, gg, ii), 'ref ' + tname(t)):
                    res_stats['exact'] += 1
                elif gdb.execute('select 1 from k where t=? and g=? and i=? limit 1', (t, gg, s64(ii))).fetchone():
                    res_stats['ea_game'] += 1
                elif pack.add_instance(t, ii, 'ref-other-group ' + tname(t)):
                    res_stats['same_type_other_group'] += 1
                elif t in TEXTURE_TYPES and any(pack.add_instance(tt, ii, 'ref-other-texture-type ' + tname(tt)) for tt in TEXTURE_TYPES if tt != t):
                    res_stats['other_texture_type'] += 1
                else:
                    res_stats['missing'] += 1
                    missing_by_type[tname(t)] += 1
                    if len(missing_examples) < 10:
                        missing_examples.append('%s CASP %016X -> %s %08X:%08X:%016X' % (os.path.basename(paths[pkg]), v, tname(t), t, gg, ii))
        pack.add_instance(T_THUM, v, 'THUM (CASP instance)')
    rd.close()
    return pack, res_stats, missing_by_type, missing_examples, round(time.time() - t0, 1)


def write_manifest(pack, paths, out):
    """t, g, i (hex), bytes on disk, source package - the input a lean-pack builder would copy from."""
    with open(out, 'w', encoding='utf-8') as f:
        f.write('type\tgroup\tinstance\tfsize\tpackage\n')
        for (t, g, i), (fs, ms, pkg) in sorted(pack.keys.items()):
            f.write('%08X\t%08X\t%016X\t%d\t%s\n' % (t, g, i, fs, paths[pkg]))


def report():
    ids = sqlite3.connect(os.path.join(HERE, 'ids.sqlite'))
    db = libti()
    gdb = sqlite3.connect(GAMEDB)
    paths = pkg_paths(db)
    R = {}
    srcs = {sid: (f, kind, json.loads(info)) for sid, f, kind, info in ids.execute('select id, file, kind, info from src')}

    def is_current(sid):
        f, kind, _ = srcs[sid]
        return kind == 'tray' or (f.endswith('.save') and '.ver' not in f)
    R['sources'] = {
        'saves_all': sum(1 for s in srcs.values() if s[1] == 'save'),
        'saves_current_slots': sum(1 for sid, s in srcs.items() if s[1] == 'save' and is_current(sid)),
        'tray_files': sum(1 for s in srcs.values() if s[1] == 'tray'),
        'tray_by_ext': dict(collections.Counter(os.path.splitext(s[0])[1] for s in srcs.values() if s[1] == 'tray')),
        'tray_unparsed_raw_scanned': sum(1 for s in srcs.values() if s[1] == 'tray' and s[2]['unparsed']),
        'uncompressed_bytes_walked': sum(s[2]['bytes'] for s in srcs.values()),
        'values_walked': sum(s[2].get('values', 0) for s in srcs.values()),
        'resource_errors': sum(len(s[2].get('errors', [])) for s in srcs.values()),
    }

    def typed_vals(cats, current_only=False):
        out = collections.Counter()
        q = 'select src, v, n from typed where cat in (%s)' % ','.join('?' * len(cats))
        for sid, v, n in ids.execute(q, cats):
            if current_only and not is_current(sid):
                continue
            out[u64(v)] += n
        return out

    def lib_inst(t):
        return set(u64(i) for (i,) in db.execute('select distinct i from res where t=?', (t,)))

    def game_inst(t):
        return set(u64(i) for (i,) in gdb.execute('select distinct i from k where t=?', (t,)))

    lib_casp, game_casp = lib_inst(T_CASP), game_inst(T_CASP)

    def classify(vals, libset, gameset):
        c = collections.Counter()
        for v in vals:
            inl, ing = v in libset, v in gameset
            c['cc' if inl and not ing else 'override_of_ea' if inl else 'ea' if ing else 'unknown'] += 1
        return dict(c)

    # ---------------- CAS parts
    cas = {}
    used_casp = set()
    for label, cur in (('all_saves_and_tray', False), ('current_saves_and_tray', True)):
        parts = typed_vals(('outfit_part', 'genetic_part'), cur)
        cas[label] = {'distinct_part_ids': len(parts), 'classes': classify(parts, lib_casp, game_casp)}
        if not cur:
            used_casp = set(v for v in parts if v in lib_casp)
    # per source kind
    for kind in ('save', 'tray'):
        parts = collections.Counter()
        for sid, v, n in ids.execute("select src, v, n from typed where cat in ('outfit_part','genetic_part')"):
            if srcs[sid][1] == kind:
                parts[u64(v)] += n
        cas['from_' + kind] = {'distinct_part_ids': len(parts), 'classes': classify(parts, lib_casp, game_casp)}
    # CASP library ids >= 2^32 seen on paths that are not outfit/genetic paths (other mods' data etc.)
    other = collections.Counter()
    for v, path in ids.execute('select v, path from hit'):
        u = u64(v)
        if u in lib_casp and u >= BIG and u not in used_casp:
            other[path] += 1
    cas['casp_ids_seen_elsewhere_only'] = {'distinct': len(set(u64(v) for v, p in ids.execute('select v, path from hit') if u64(v) in lib_casp and u64(v) >= BIG and u64(v) not in used_casp)),
                                           'top_paths': other.most_common(8)}
    cas['share_of_library_unique_casps'] = round(len(used_casp) / len(lib_casp), 5)
    cas['library_unique_casps'] = len(lib_casp)
    cas['used_cc_casps'] = len(used_casp)
    R['cas_parts'] = cas

    # packages holding the used CASPs
    per_pkg = collections.Counter()
    copies = 0
    for v in used_casp:
        rows = db.execute('select distinct pkg from res where t=? and i=?', (T_CASP, s64(v))).fetchall()
        copies += len(rows)
        for (p,) in rows:
            per_pkg[p] += 1
    R['cas_parts']['packages_holding_used_casps'] = len(per_pkg)
    R['cas_parts']['copies_of_used_casps_in_library'] = copies
    R['cas_parts']['top_packages'] = [(paths[p].split('The Sims 4\\')[1], n) for p, n in per_pkg.most_common(15)]

    # ---------------- closure for used CASPs (all save versions + tray) and for current slots + tray only
    pack, res_stats, missing_by_type, missing_examples, secs = cas_closure(db, gdb, paths, used_casp)
    R['cas_pack'] = pack.totals()
    R['cas_pack']['ref_resolution'] = dict(res_stats)
    R['cas_pack']['missing_by_type'] = dict(missing_by_type)
    R['cas_pack']['missing_examples'] = missing_examples
    R['cas_pack']['secs'] = secs
    write_manifest(pack, paths, os.path.join(HERE, 'used_pack_keys.tsv'))
    cur_parts = typed_vals(('outfit_part', 'genetic_part'), True)
    used_cur = set(v for v in cur_parts if v in lib_casp)
    p2, st2, mb2, _, _ = cas_closure(db, gdb, paths, used_cur)
    R['cas_pack_current_only'] = dict(p2.totals(), used_cc_casps=len(used_cur), ref_resolution=dict(st2))

    # ---------------- skin tones, sculpts, sliders
    other_cc = {}
    for cat, t in (('skin_tone', T_TONE), ('sculpt', T_SCUL), ('face_modifier', T_SMOD), ('body_modifier', T_SMOD)):
        vals = typed_vals((cat,))
        libset, gameset = lib_inst(t), game_inst(t)
        used = set(v for v in vals if v in libset)
        other_cc[cat] = {'distinct_values': len(vals), 'classes': classify(vals, libset, gameset),
                         'library_%s_total' % tname(t): len(libset), 'used_cc_ids': sorted('%016X' % v for v in used)[:50]}
    R['sim_look'] = other_cc
    look_pack = Pack(db)
    types = set(t for (t,) in db.execute('select distinct t from res')) - {0}
    rd = PkgReader()
    for cat, t in (('skin_tone', T_TONE), ('sculpt', T_SCUL), ('face_modifier', T_SMOD), ('body_modifier', T_SMOD)):
        libset = lib_inst(t)
        for v in set(typed_vals((cat,))):
            if v not in libset:
                continue
            for g, pkg, off, fs, comp in db.execute('select g, pkg, off, fsize, comp from res where t=? and i=? group by g', (t, s64(v))).fetchall():
                look_pack.add((t, g, v), tname(t))
                try:
                    data = rd.read(paths[pkg], off, fs, comp)
                except Exception:
                    continue
                for key in embedded_keys(data, types, db, skip=(t, g, v)):
                    look_pack.add(key, 'ref ' + tname(key[0]))
    rd.close()
    R['sim_look_pack'] = look_pack.totals()

    # ---------------- build/buy objects
    lib_objd, lib_cobj = lib_inst(T_OBJD), lib_inst(T_COBJ)
    game_objd = game_inst(T_OBJD)
    obj_paths = collections.Counter()
    used_obj = set()
    for sid, v, path, n in ids.execute('select src, v, path, n from hit'):
        u = u64(v)
        if (u in lib_objd or u in lib_cobj) and (path.endswith('.1.30') or path.endswith('tag30')):
            used_obj.add(u); obj_paths[path.rsplit('.', 3)[0] if path.endswith('.1.30') else path] += 1
    guids = typed_vals(('object_guid',))
    R['objects'] = {'distinct_guid_values_on_ObjectList_paths': len(guids),
                    'classes': classify(guids, lib_objd | lib_cobj, game_objd),
                    'used_cc_objects': len(used_obj), 'library_objd': len(lib_objd),
                    'paths': obj_paths.most_common(10)}
    obj_pack = Pack(db)
    rd = PkgReader()
    frontier = []
    for v in used_obj:
        for t in (T_OBJD, T_COBJ, T_OBJ_THUMB):
            obj_pack.add_instance(t, v, tname(t))
        for t, g, pkg, off, fs, comp in db.execute('select t, g, pkg, off, fsize, comp from res where t in (?,?) and i=? group by t, g', (T_OBJD, T_COBJ, s64(v))).fetchall():
            frontier.append((t, g, v, pkg, off, fs, comp))
    seen = set()
    while frontier:
        t, g, v, pkg, off, fs, comp = frontier.pop()
        if (t, g, v) in seen:
            continue
        seen.add((t, g, v))
        try:
            data = rd.read(paths[pkg], off, fs, comp)
        except Exception:
            continue
        for key in embedded_keys(data, types, db, skip=(t, g, v)):
            if key[0] in (T_CASP,):
                continue
            new = key not in obj_pack.keys
            obj_pack.add(key, 'ref ' + tname(key[0]))
            if new and key[0] not in TEXTURE_TYPES and key[0] not in (T_THUM, T_OBJ_THUMB):
                r = db.execute('select pkg, off, fsize, comp from res where t=? and g=? and i=? limit 1', (key[0], key[1], s64(key[2]))).fetchone()
                if r:
                    frontier.append((key[0], key[1], key[2]) + tuple(r))
    rd.close()
    R['objects_pack'] = obj_pack.totals()

    # ---------------- anything else from the library that the saves mention (ids >= 2^32 only, any path)
    extra = collections.Counter()
    for v, path in ids.execute('select distinct v, path from hit'):
        u = u64(v)
        if u >= BIG:
            for t in db.execute('select distinct t from res where t not in (?,?,?) and i=?', (T_CASP, T_OBJD, T_COBJ, s64(u))).fetchall():
                extra[tname(t[0])] += 1
    R['other_library_ids_mentioned_in_saves_by_type'] = dict(extra.most_common(20))
    R['raw_scan_hits'] = ids.execute('select count(*), count(distinct v) from raw').fetchone()

    lib_total = db.execute('select sum(size) from pkg').fetchone()[0]
    R['library_bytes'] = lib_total
    with open(os.path.join(HERE, 'report.json'), 'w') as f:
        json.dump(R, f, indent=1)
    print(json.dumps(R, indent=1)[:20000])


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'verify'
    if cmd == 'verify':
        verify(int(sys.argv[2]) if len(sys.argv) > 2 else 2000)
    elif cmd == 'gameindex':
        build_game_index()
    elif cmd == 'report':
        report()
    elif cmd == 'scan':
        scan(int(sys.argv[2]) if len(sys.argv) > 2 else 2, sys.argv[3] if len(sys.argv) > 3 else None)
