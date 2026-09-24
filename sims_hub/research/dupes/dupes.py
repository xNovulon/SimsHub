"""Content-level duplicate analysis of the Sims 4 mod library (index in data/library.sqlite).

Read-only on the library: packages are opened 'rb' and only the byte ranges listed in the index
are read. Everything written goes next to this script.

    python dupes.py scan       # read + hash every copy of every duplicated key  -> hashes.npz
    python dupes.py analyze    # classify keys, package redundancy, savings      -> result.json, keys.tsv.gz
    python dupes.py header P   # print DBPF header / index layout of package P (2 GiB check)
    python dupes.py all        # scan + analyze

Hashing: blake2b(digest_size=16) of the stored bytes ("raw"). For keys whose copies are not all
byte-identical, every copy is also decompressed (zlib 0x5A42, RefPack 0xFFFF) and the uncompressed
bytes are hashed ("unc"), so copies that differ only in compression still count as identical.
"""
import collections, gzip, hashlib, itertools, json, os, sqlite3, struct, sys, threading, time, zlib
from concurrent.futures import ThreadPoolExecutor

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.normpath(os.path.join(HERE, '..', '..', 'data', 'library.sqlite'))
SIMS = os.path.join(os.path.expanduser('~'), 'Documents', 'Electronic Arts', 'The Sims 4')
HASHES = os.path.join(HERE, 'hashes.npz')
RESULT = os.path.join(HERE, 'result.json')
KEYS_TSV = os.path.join(HERE, 'keys.tsv.gz')

ZLIB, REFPACK, NONE = 0x5A42, 0xFFFF, 0
GAP = 256 << 10          # coalesce reads when the hole between two resources is below this
WIN = 16 << 20           # max bytes per read() call
CHUNK = 8 << 20          # streaming chunk for huge resources
WORKERS = 6
S4S_MANIFEST = 0x7FB6AD8A  # Sims 4 Studio merged-package manifest (metadata, game ignores it)
CASP = 0x034AEECB
NAMEMAP = 0x0166038C

TYPE_NAMES = {
    0x034AEECB: 'CASP (CAS part)', 0x3453CF95: 'RLE2 image', 0x3C1AF1F2: 'CAS thumbnail (PNG)',
    0x2BC04EDF: 'LRLE image', 0x015A1849: 'GEOM (CAS mesh)', 0xBC4A5044: 'Clip header',
    0x6B20C4F3: 'Animation clip', 0x00B2D882: 'DST image', 0x545AC67A: 'SimData',
    0xBA856C78: 'RLES image', 0x220557DA: 'STBL (string table)', 0xAC16FBEC: 'RegionMap',
    0xE882D22F: 'Interaction tuning', 0x6017E896: 'Buff tuning', 0x0C772E27: 'Loot tuning',
    0xCB5FDDC7: 'Trait tuning', 0x067CAA11: 'BGEO (blend geometry)', 0x0166038C: 'NameMap',
    0x7FB6AD8A: 'S4S merge manifest', 0x03B33DDF: 'Tuning (generic)', 0xC0DB5AE7: 'OBJD',
    0x319E4F1D: 'COBJ', 0x01661233: 'MODL', 0x01D10F34: 'MLOD', 0x01D0E75D: 'MATD', 0x02019972: 'MTST',
    0xD382BF57: 'FTPT (footprint)', 0x3C2A8647: 'Buy/Build thumbnail (PNG)', 0x0354796A: 'TONE (skin tone)',
    0x02D5DF13: 'ASM (animation state machine)', 0xEE17C6AD: 'Animation tuning', 0xB61DE6B4: 'Object tuning',
    0x0904DF10: 'Relationship bit tuning', 0x7DF2169C: 'Snippet tuning', 0x9C07855D: 'Snippet?',
    0x62E94D38: 'XML (combined tuning)', 0xB0311D0F: 'RLE (light cookie?)', 0x8EAF13DE: 'RIG',
    0xD3044521: 'RSLT (slot)', 0xAC03A936: 'Mood tuning', 0xE5105066: 'Statistic tuning',
    0x2F7D0004: 'PNG image', 0x00DE5AC5: 'ThumbnailCache?', 0xEAA32ADD: 'CAS preset?',
}


def tname(t):
    return TYPE_NAMES.get(t, '%08X' % t)


def pkg_path(root, rel):
    return os.path.join(SIMS, root, *rel.split('/'))


# ----------------------------------------------------------------------------------------- RefPack
def refpack_decompress(d):
    """EA RefPack/QFS as used by TS4 'internal' compression (0xFFFF)."""
    flags = d[0]
    if d[1] != 0xFB:
        raise ValueError('bad RefPack magic %02X%02X' % (d[0], d[1]))
    p = 2
    w = 4 if flags & 0x80 else 3
    if flags & 0x01:
        p += w
    size = int.from_bytes(d[p:p + w], 'big'); p += w
    out = bytearray()
    n = len(d)
    while p < n:
        cc = d[p]; p += 1
        if cc < 0x80:
            b1 = d[p]; p += 1
            plain = cc & 3; copy = ((cc & 0x1C) >> 2) + 3; off = ((cc & 0x60) << 3) + b1 + 1
        elif cc < 0xC0:
            b1, b2 = d[p], d[p + 1]; p += 2
            plain = b1 >> 6; copy = (cc & 0x3F) + 4; off = ((b1 & 0x3F) << 8) + b2 + 1
        elif cc < 0xE0:
            b1, b2, b3 = d[p], d[p + 1], d[p + 2]; p += 3
            plain = cc & 3; copy = ((cc & 0x0C) << 6) + b3 + 5; off = ((cc & 0x10) << 12) + (b1 << 8) + b2 + 1
        elif cc < 0xFC:
            plain = ((cc & 0x1F) << 2) + 4; copy = 0; off = 0
        else:
            plain = cc & 3; copy = 0; off = 0
        out += d[p:p + plain]; p += plain
        if copy:
            s = len(out) - off
            if s < 0:
                raise ValueError('RefPack back-reference before start')
            if off >= copy:
                out += out[s:s + copy]
            else:
                for k in range(copy):
                    out.append(out[s + k])
        if cc >= 0xFC:
            break
    if len(out) != size:
        raise ValueError('RefPack size %d != header %d' % (len(out), size))
    return bytes(out)


# ------------------------------------------------------------------------------------------- load
def load_rows(db):
    """All index rows whose (t,g,i) occurs 2+ times, sorted by key. Returns numpy structured array."""
    t0 = time.time()
    db.execute('drop table if exists temp.dk')
    db.execute('create temp table dk as select t,g,i from res group by t,g,i having count(*)>1')
    cur = db.execute('select r.rowid, r.pkg, r.t, r.g, r.i, r.off, r.fsize, r.msize, r.comp '
                     'from res r join temp.dk using(t,g,i) order by r.t, r.g, r.i, r.pkg, r.off')
    dt = np.dtype([('rid', 'i8'), ('pkg', 'i4'), ('t', 'u4'), ('g', 'u4'), ('i', 'i8'), ('off', 'i8'),
                   ('fsize', 'i8'), ('msize', 'i8'), ('comp', 'i4')])
    rows = np.array(cur.fetchall(), dtype=dt)
    # key index
    kchange = np.ones(len(rows), bool)
    kchange[1:] = (rows['t'][1:] != rows['t'][:-1]) | (rows['g'][1:] != rows['g'][:-1]) | (rows['i'][1:] != rows['i'][:-1])
    kid = np.cumsum(kchange) - 1
    print('loaded %d copies of %d duplicated keys in %.1fs' % (len(rows), kid[-1] + 1, time.time() - t0), flush=True)
    return rows, kid.astype(np.int32)


def key_uniform(rows, kid):
    """Per row: True when every copy of its key has the same (comp, fsize, msize)."""
    nk = int(kid[-1]) + 1
    out = np.ones(nk, bool)
    for f in ('comp', 'fsize', 'msize'):
        v = rows[f]
        mn = np.full(nk, np.iinfo(np.int64).max); mx = np.full(nk, np.iinfo(np.int64).min)
        np.minimum.at(mn, kid, v.astype(np.int64)); np.maximum.at(mx, kid, v.astype(np.int64))
        out &= mn == mx
    return out


# ------------------------------------------------------------------------------------------- scan
class Hasher:
    def __init__(self, n):
        self.raw = np.zeros((n, 16), np.uint8)
        self.unc = np.zeros((n, 16), np.uint8)
        self.status = np.zeros(n, np.int8)    # 0 unread, 1 raw hashed, 2 raw+unc hashed, -1 decode error, -2 read error
        self.unclen = np.full(n, -1, np.int64)
        self.err = {}
        self.bytes_read = 0
        self.lock = threading.Lock()
        self.done_pkgs = 0

    @staticmethod
    def _h(b):
        return np.frombuffer(hashlib.blake2b(b, digest_size=16).digest(), np.uint8)

    def _unc_hash(self, comp, data):
        """(digest, uncompressed length) of uncompressed content."""
        if comp == NONE:
            return self._h(data), len(data)
        if comp == ZLIB:
            if len(data) <= CHUNK:
                u = zlib.decompress(data)
                return self._h(u), len(u)
            d = zlib.decompressobj(); h = hashlib.blake2b(digest_size=16); n = 0
            buf = data
            while True:
                u = d.decompress(buf, CHUNK)
                h.update(u); n += len(u)
                buf = d.unconsumed_tail
                if not buf:
                    break
            u = d.flush(); h.update(u); n += len(u)
            return np.frombuffer(h.digest(), np.uint8), n
        if comp == REFPACK:
            u = refpack_decompress(bytes(data))
            return self._h(u), len(u)
        raise ValueError('unsupported compression %04X' % comp)

    def _one(self, j, comp, data, want_unc):
        self.raw[j] = self._h(data)
        st = 1
        if comp == NONE:
            self.unc[j] = self.raw[j]; self.unclen[j] = len(data); st = 2
        elif want_unc:
            try:
                self.unc[j], self.unclen[j] = self._unc_hash(comp, data); st = 2
            except Exception as e:  # noqa
                st = -1; self.err[int(j)] = '%s: %s' % (type(e).__name__, e)
        self.status[j] = st

    def package(self, path, items):
        """items: list of (row index, off, fsize, comp, want_unc) sorted by off."""
        nread = 0
        try:
            f = open(path, 'rb', buffering=0)
        except OSError as e:
            for it in items:
                self.status[it[0]] = -2; self.err[int(it[0])] = str(e)
            return
        with f:
            k = 0
            while k < len(items):
                j, off, fs, comp, wu = items[k]
                if fs > WIN:                      # huge resource: stream raw hash; buffer only if needed
                    f.seek(off)
                    if wu and comp != NONE:
                        data = f.read(fs); nread += len(data)
                        if len(data) != fs:
                            self.status[j] = -2; self.err[int(j)] = 'short read'
                        else:
                            self._one(j, comp, data, True)
                        del data
                    else:
                        h = hashlib.blake2b(digest_size=16); left = fs
                        while left:
                            b = f.read(min(CHUNK, left)); nread += len(b)
                            if not b:
                                break
                            h.update(b); left -= len(b)
                        self.raw[j] = np.frombuffer(h.digest(), np.uint8)
                        if comp == NONE:
                            self.unc[j] = self.raw[j]; self.unclen[j] = fs; self.status[j] = 2
                        else:
                            self.status[j] = 1
                    k += 1
                    continue
                # coalesce a window of small resources
                start = off; end = off + fs; m = k + 1
                while m < len(items):
                    o2, f2 = items[m][1], items[m][2]
                    if f2 > WIN or o2 - end > GAP or o2 + f2 - start > WIN:
                        break
                    end = max(end, o2 + f2); m += 1
                f.seek(start)
                buf = f.read(end - start); nread += len(buf)
                mv = memoryview(buf)
                for j2, o2, f2, c2, w2 in items[k:m]:
                    a = o2 - start
                    if a + f2 > len(buf):
                        self.status[j2] = -2; self.err[int(j2)] = 'short read'
                        continue
                    self._one(j2, c2, mv[a:a + f2], w2)
                del mv, buf
                k = m
        with self.lock:
            self.bytes_read += nread
            self.done_pkgs += 1


def run_pass(h, rows, sel, want_unc, pkgs, label):
    """Hash rows[sel]; want_unc: bool array (per row) whether to decompress."""
    idx = np.nonzero(sel)[0]
    by_pkg = collections.defaultdict(list)
    for j in idx:
        r = rows[j]
        by_pkg[int(r['pkg'])].append((int(j), int(r['off']), int(r['fsize']), int(r['comp']), bool(want_unc[j])))
    tasks = []
    for p, items in by_pkg.items():
        items.sort(key=lambda x: x[1])
        tasks.append((sum(x[2] for x in items), p, items))
    tasks.sort(reverse=True)                       # biggest first for load balance
    total = sum(t[0] for t in tasks)
    print('%s: %d copies in %d packages, %.2f GB stored' % (label, len(idx), len(tasks), total / 1e9), flush=True)
    h.bytes_read = 0; h.done_pkgs = 0
    t0 = time.time()
    with ThreadPoolExecutor(WORKERS) as ex:
        futs = [ex.submit(h.package, pkg_path(*pkgs[p][:2]), items) for _, p, items in tasks]
        last = 0
        while True:
            done = sum(fu.done() for fu in futs)
            if time.time() - last > 30 or done == len(futs):
                last = time.time(); el = last - t0
                print('  %s %d/%d pkgs  %.1f GB read  %.0fs  %.0f MB/s' % (label, done, len(futs), h.bytes_read / 1e9, el,
                      h.bytes_read / 1e6 / max(el, 1e-3)), flush=True)
            if done == len(futs):
                break
            time.sleep(2)
        for fu in futs:
            fu.result()
    return time.time() - t0


def load_pkgs(db):
    return {r[0]: r[1:] for r in db.execute('select id, root, rel, size, mtime, n from pkg')}


def scan():
    db = sqlite3.connect(DB)
    pkgs = load_pkgs(db)
    rows, kid = load_rows(db)
    uni = key_uniform(rows, kid)[kid]
    h = Hasher(len(rows))
    # pass 1: raw hash everything; decompress copies of keys whose (comp,fsize,msize) are not uniform
    want1 = ~uni
    t1 = run_pass(h, rows, np.ones(len(rows), bool), want1, pkgs, 'pass1')
    b1 = h.bytes_read
    # pass 2: keys whose raw hashes differ but where some copy has no uncompressed hash yet
    nk = int(kid[-1]) + 1
    first = np.zeros(nk, np.int64); first[kid[::-1]] = np.arange(len(rows))[::-1]
    same_raw = np.all(h.raw == h.raw[first[kid]], axis=1)
    key_diff = np.zeros(nk, bool); np.logical_or.at(key_diff, kid, ~same_raw)
    need2 = key_diff[kid] & (h.status == 1)
    t2 = run_pass(h, rows, need2, np.ones(len(rows), bool), pkgs, 'pass2') if need2.any() else 0.0
    b2 = h.bytes_read if need2.any() else 0
    np.savez_compressed(HASHES, rid=rows['rid'], raw=h.raw, unc=h.unc, status=h.status, unclen=h.unclen)
    meta = {'pass1_seconds': round(t1, 1), 'pass1_bytes': b1, 'pass2_seconds': round(t2, 1), 'pass2_bytes': b2,
            'pass2_copies': int(need2.sum()), 'pass1_decompressed_copies': int((want1 & (rows['comp'] != 0)).sum()),
            'errors': {str(int(rows['rid'][j])): e for j, e in list(h.err.items())[:200]}, 'n_errors': len(h.err),
            'workers': WORKERS}
    with open(os.path.join(HERE, 'scan_meta.json'), 'w') as f:
        json.dump(meta, f, indent=1)
    print('scan done', meta['n_errors'], 'errors;', 'pass1 %.0fs %.1f GB, pass2 %.0fs %.1f GB' % (t1, b1 / 1e9, t2, b2 / 1e9), flush=True)


# ----------------------------------------------------------------------------------------- header
def header(path):
    with open(path, 'rb') as f:
        h = f.read(96)
        size = os.fstat(f.fileno()).st_size
    count, pos_low, isz = struct.unpack_from('<III', h, 36)
    pos = struct.unpack_from('<I', h, 64)[0]
    pos64 = struct.unpack_from('<Q', h, 64)[0]
    lim = 1 << 31
    info = {'path': path, 'file_size': size, 'beyond_2^31_bytes': max(0, size - lim), 'version': struct.unpack_from('<II', h, 4),
            'index_count': count, 'index_pos_low@40': pos_low, 'index_pos@64(u32)': pos, 'index_pos@64(u64)': pos64,
            'index_size': isz, 'index_end': pos + isz, 'index_start_below_2^31': pos < lim,
            'index_bytes_beyond_2^31': max(0, pos + isz - max(pos, lim)),
            'index_entry_bytes': (isz - 4) / count if count else None}
    if info['index_bytes_beyond_2^31']:
        per = info['index_entry_bytes']
        first_entry = int((lim - pos - 4) // per) if per else None
        info['first_index_entry_crossing_2^31'] = first_entry
        info['index_entries_touching_beyond_2^31'] = count - first_entry if per else None
    return info


# ---------------------------------------------------------------------------------------- analyze
def parse_s4s_manifest(b):
    """Sims 4 Studio merge manifest (type 0x7FB6AD8A) -> (version, [(source_name, [(t, g, i_unsigned)])], parsed_exactly).
    Layout reverse-engineered from the files in this library: u32 version, u64 (0), u32 n_sources, then per source:
    u32 name_len, name (UTF-8, no extension), u32 n_keys, n_keys * (u64 instance, u32 type, u32 group)."""
    ver = struct.unpack_from('<I', b, 0)[0]
    p = 12
    n = struct.unpack_from('<I', b, p)[0]; p += 4
    out = []
    for _ in range(n):
        ln = struct.unpack_from('<I', b, p)[0]; p += 4
        name = b[p:p + ln].decode('utf-8', 'replace'); p += ln
        nk = struct.unpack_from('<I', b, p)[0]; p += 4
        keys = [struct.unpack_from('<QII', b, p + 16 * q) for q in range(nk)]
        p += 16 * nk
        out.append((name, [(t, g, i) for i, t, g in keys]))
    return ver, out, p == len(b)


def decompress(comp, d):
    if comp == ZLIB:
        return zlib.decompress(d)
    if comp == REFPACK:
        return refpack_decompress(d)
    return d


def read_resource(root, rel, off, fsize, comp):
    with open(pkg_path(root, rel), 'rb') as f:
        f.seek(off); d = f.read(fsize)
    return decompress(comp, d)


def s4s_sources(db, pkgs):
    """{(pkg, t, g, i_signed): original source file name} from every S4S merge manifest in the library."""
    src = {}
    stats = collections.Counter()
    names = collections.defaultdict(set)
    for pid, off, fs, comp in db.execute('select pkg, off, fsize, comp from res where t=?', (S4S_MANIFEST,)).fetchall():
        stats['manifests'] += 1
        try:
            ver, lst, exact = parse_s4s_manifest(read_resource(pkgs[pid][0], pkgs[pid][1], off, fs, comp))
        except Exception:
            stats['parse_errors'] += 1
            continue
        stats['parsed_exactly'] += exact
        stats['version_%d' % ver] += 1
        for name, keys in lst:
            stats['source_entries'] += 1
            names[name.lower()].add(pid)
            for t, g, i in keys:
                src[(pid, t, g, i - (1 << 64) if i >= (1 << 63) else i)] = name
    stats['distinct_source_names'] = len(names)
    stats['source_names_in_2plus_packages'] = sum(len(v) > 1 for v in names.values())
    return src, dict(stats), names


def xml_name(b):
    head = b[:800]
    if b'<?xml' not in head[:100] and not head.lstrip()[:3] in (b'<I ', b'<M '):
        return None
    s = head.decode('utf-8', 'replace')
    a = s.find(' n="')
    return s[a + 4:s.find('"', a + 4)] if a >= 0 else None


def load_order_key(rel):
    """Order in which the game would load this package if it sat at Mods/<rel>: depth-first, each folder's
    entries in NTFS (upper-cased) name order; the FIRST loaded copy of a resource wins (scumbumbo, MTS t=604303)."""
    return tuple(c.upper() for c in rel.split('/'))


def analyze():
    t0 = time.time()
    db = sqlite3.connect(DB)
    pkgs = load_pkgs(db)                        # id -> (root, rel, size, mtime, n)
    rows, kid = load_rows(db)
    z = np.load(HASHES)
    assert (z['rid'] == rows['rid']).all(), 'hashes.npz does not match the current index - rerun scan'
    raw, unc, status, unclen = z['raw'], z['unc'], z['status'], z['unclen']
    raw_b = [bytes(x) for x in raw]; unc_b = [bytes(x) for x in unc]
    N = len(rows); nk = int(kid[-1]) + 1
    bounds = np.searchsorted(kid, np.arange(nk + 1))
    kfirst = bounds[:-1]; nc = np.diff(bounds)
    pk = rows['pkg']; T = rows['t']; G = rows['g']; I = rows['i']; FS = rows['fsize']; MS = rows['msize']; CP = rows['comp']; OFF = rows['off']
    ktype = T[kfirst]
    lok = {p: load_order_key(v[1]) for p, v in pkgs.items()}
    rank = {p: r for r, p in enumerate(sorted(pkgs, key=lambda p: lok[p]))}

    def pname(p):
        return '%s/%s' % (pkgs[p][0], pkgs[p][1])
    script_dirs = {(r, rel.rsplit('/', 1)[0] if '/' in rel else '') for r, rel in db.execute('select root, rel from script')}
    in_script_dir = {p: (v[0], v[1].rsplit('/', 1)[0] if '/' in v[1] else '') in script_dirs for p, v in pkgs.items()}

    # ---------------- classify every duplicated key
    cls = np.zeros(nk, np.int8)       # 1 identical bytes, 2 identical after decompression, 3 conflict, 4 undecidable
    variant = np.zeros(N, np.int16)
    nvar = np.ones(nk, np.int16)
    covered = np.zeros(N, bool)       # a copy of the same content exists in ANOTHER package
    winner = np.zeros(nk, np.int64)   # row index of the load-order winner
    undecodable_keys = []
    for k in range(nk):
        a, b = int(bounds[k]), int(bounds[k + 1])
        r0 = raw_b[a]
        if all(raw_b[j] == r0 for j in range(a + 1, b)):
            cls[k] = 1
        elif (status[a:b] == 1).any() or (status[a:b] == -2).any():
            cls[k] = 4                    # not hashed uncompressed / unreadable (should not happen after pass 2)
        else:
            # copies that failed to decompress are identified by their stored bytes
            cid = [unc_b[j] if status[j] == 2 else b'raw:' + raw_b[j] for j in range(a, b)]
            if (status[a:b] < 0).any():
                undecodable_keys.append(k)
            if all(c == cid[0] for c in cid):
                cls[k] = 2
            else:
                cls[k] = 3
                ids = {}
                for j in range(a, b):
                    variant[j] = ids.setdefault(cid[j - a], len(ids))
                nvar[k] = len(ids)
        winner[k] = min(range(a, b), key=lambda j: (rank[int(pk[j])], int(OFF[j])))
        if cls[k] == 4:
            continue
        vp = collections.defaultdict(set)
        for j in range(a, b):
            vp[int(variant[j])].add(int(pk[j]))
        for j in range(a, b):
            covered[j] = len(vp[int(variant[j])]) > 1
    ident = (cls == 1) | (cls == 2)
    conf = cls == 3
    rowcls = cls[kid]
    print('classified in %.1fs' % (time.time() - t0), flush=True)

    res = {'generated': time.strftime('%Y-%m-%d %H:%M:%S'), 'db': DB,
           'hash': 'blake2b-128 of stored bytes; of uncompressed bytes where stored bytes differ'}
    try:
        meta = json.load(open(os.path.join(HERE, 'scan_meta.json')))
        res['scan'] = meta
    except Exception:
        pass
    res['decode'] = {
        'errors_by_comp': {('%04X' % c): int(((status < 0) & (CP == c)).sum()) for c in np.unique(CP)},
        'uncompressed_len_ne_msize': int(((status == 2) & (unclen != MS)).sum()),
        'refpack_copies_in_dup_keys': int((CP == REFPACK).sum()),
        'refpack_decoded': int(((CP == REFPACK) & (status == 2)).sum()),
        'refpack_not_decoded_because_bytes_identical': int(((CP == REFPACK) & (status == 1)).sum()),
        'refpack_decode_failed': int(((CP == REFPACK) & (status < 0)).sum()),
        'keys_with_undecodable_copies': [
            {'key': '%08X:%08X:%016X' % (T[bounds[k]], G[bounds[k]], int(I[bounds[k]]) & 0xFFFFFFFFFFFFFFFF),
             'class': {2: 'identical_after_decompress', 3: 'conflict'}.get(int(cls[k])),
             'bad_copies_in': sorted({pname(int(pk[j])) for j in range(bounds[k], bounds[k + 1]) if status[j] < 0}),
             'copies': int(nc[k])} for k in undecodable_keys],
    }
    npk = np.array([len(set(pk[bounds[k]:bounds[k + 1]].tolist())) for k in range(nk)])
    sumfs = np.add.reduceat(FS, kfirst)

    def summary(m):
        return {'keys': int(m.sum()), 'copies': int(nc[m].sum()), 'stored_bytes': int(sumfs[m].sum())}
    lib_n, lib_b = db.execute('select count(*), sum(fsize) from res').fetchone()
    res['totals'] = {
        'library_packages': len(pkgs), 'library_resources': lib_n, 'library_stored_bytes': lib_b,
        'distinct_keys': lib_n - N + nk,
        'dup_keys': nk, 'dup_copies': N, 'dup_copies_stored_bytes': int(FS.sum()),
        'dup_keys_only_within_one_package': int((npk == 1).sum()),
        'identical_bytes': summary(cls == 1), 'identical_after_decompress': summary(cls == 2),
        'conflicting': summary(conf), 'undecidable': summary(cls == 4),
        'conflicting_excl_s4s_manifest': summary(conf & (ktype != S4S_MANIFEST)),
    }

    # ---------------- savings
    minfs = np.minimum.reduceat(FS, kfirst)
    minms = np.minimum.reduceat(MS, kfirst); summs = np.add.reduceat(MS, kfirst)
    sav = {'identical_keys_keep_one_copy': {
        'copies_removed': int((nc[ident] - 1).sum()),
        'stored_bytes_removed': int((sumfs[ident] - minfs[ident]).sum()),
        'uncompressed_bytes_removed': int((summs[ident] - minms[ident]).sum()),
        'casp_copies_removed': int((nc[ident & (ktype == CASP)] - 1).sum())}}
    sv_n = sv_b = sv_casp = 0
    ck = conf & (ktype != S4S_MANIFEST)
    for k in np.nonzero(ck)[0]:
        a, b = int(bounds[k]), int(bounds[k + 1]); w = int(winner[k])
        byv = collections.defaultdict(list)
        for j in range(a, b):
            byv[int(variant[j])].append(j)
        for v, js in byv.items():
            keep = w if w in js else js[0]
            for j in js:
                if j != keep:
                    sv_n += 1; sv_b += int(FS[j]); sv_casp += int(T[j] == CASP)
    sav['conflicting_keys_drop_same_variant_copies'] = {'copies_removed': sv_n, 'stored_bytes_removed': sv_b, 'casp_copies_removed': sv_casp}
    wfs = FS[winner]
    sav['conflicting_keys_keep_only_load_order_winner'] = {
        'copies_removed': int((nc[ck] - 1).sum()), 'stored_bytes_removed': int((sumfs[ck] - wfs[ck]).sum()),
        'casp_copies_removed': int((nc[ck & (ktype == CASP)] - 1).sum()),
        'note': 'the game uses only the first-loaded copy of a key, so the others are dead weight; this keeps the copy that '
                'would win if the whole library sat in Mods with its current relative paths'}
    sav['all_dup_keys_keep_one_copy'] = {
        'copies_removed': int((nc[ident | ck] - 1).sum()),
        'stored_bytes_removed': int((sumfs[ident] - minfs[ident]).sum() + (sumfs[ck] - wfs[ck]).sum())}
    casp_all = db.execute('select count(*) from res where t=?', (CASP,)).fetchone()[0]
    casp_keys = db.execute('select count(*) from (select 1 from res where t=? group by g, i)', (CASP,)).fetchone()[0]
    sav['casp'] = {'casp_copies_in_library': casp_all, 'casp_distinct_keys': casp_keys, 'casp_redundant_copies': casp_all - casp_keys,
                   'casp_dup_keys_identical': int((ident & (ktype == CASP)).sum()),
                   'casp_dup_keys_conflicting': int((conf & (ktype == CASP)).sum()),
                   'casp_copies_removed_identical_only': sav['identical_keys_keep_one_copy']['casp_copies_removed'],
                   'casp_copies_removed_keep_one_per_key': int((nc[(ident | ck) & (ktype == CASP)] - 1).sum())}
    res['savings'] = sav

    # ---------------- per type
    bytype = {}
    for t in np.unique(ktype):
        m = ktype == t
        cm = m & conf
        e = {'name': tname(int(t)), 'dup_keys': int(m.sum()), 'copies': int(nc[m].sum()),
             'identical_keys': int((m & ident).sum()), 'identical_after_decompress_keys': int((m & (cls == 2)).sum()),
             'conflicting_keys': int(cm.sum()), 'undecidable_keys': int((m & (cls == 4)).sum()),
             'identical_copies_removable': int((nc[m & ident] - 1).sum()),
             'identical_stored_bytes_removable': int((sumfs[m & ident] - minfs[m & ident]).sum())}
        if cm.any():
            e['conflict_same_msize_keys'] = int(sum(len(set(MS[bounds[k]:bounds[k + 1]].tolist())) == 1 for k in np.nonzero(cm)[0]))
        bytype['%08X' % t] = e
    res['by_type'] = dict(sorted(bytype.items(), key=lambda kv: -kv[1]['copies']))

    # ---------------- provenance from S4S merge manifests
    src, sstats, srcnames = s4s_sources(db, pkgs)

    def source_of(j):
        s = src.get((int(pk[j]), int(T[j]), int(G[j]), int(I[j])))
        return s if s is not None else '[file] ' + pkgs[int(pk[j])][1].rsplit('/', 1)[-1]
    prov = collections.Counter()
    for k in np.nonzero(ident)[0]:
        a, b = int(bounds[k]), int(bounds[k + 1])
        names = {source_of(j).lower() for j in range(a, b)}
        tag = 'same_source_name' if len(names) == 1 else 'different_source_names'
        prov['identical_keys_' + tag] += 1
        prov['identical_redundant_copies_' + tag] += b - a - 1
    for k in np.nonzero(ck)[0]:
        a, b = int(bounds[k]), int(bounds[k + 1])
        names = {source_of(j).lower() for j in range(a, b)}
        prov['conflicting_keys_' + ('same_source_name' if len(names) == 1 else 'different_source_names')] += 1
    multi = {n: sorted(ps) for n, ps in srcnames.items() if len(ps) > 1}
    res['provenance'] = {'s4s_manifests': sstats, **dict(prov),
                         'source_files_merged_into_2plus_packages_examples': [
                             {'source': n, 'packages': [pname(p) for p in ps]}
                             for n, ps in sorted(multi.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:25]]}

    # ---------------- conflicts
    pairs = collections.Counter(); pair_types = collections.defaultdict(collections.Counter)
    pkg_conf = collections.Counter(); hint = collections.Counter(); src_pairs = collections.Counter()
    kinds = collections.Counter(); script_conf = collections.Counter(); folder_pairs = collections.Counter()
    examples_by_type = collections.defaultdict(list)
    diff_candidates = collections.defaultdict(list)
    for k in np.nonzero(ck)[0]:
        a, b = int(bounds[k]), int(bounds[k + 1]); t = int(ktype[k])
        byv = collections.defaultdict(list)
        for j in range(a, b):
            byv[int(variant[j])].append(j)
        pv = collections.defaultdict(set)
        for v, js in byv.items():
            for j in js:
                pv[int(pk[j])].add(v)
        plist = sorted(pv)
        for x, y in itertools.combinations(plist, 2):
            if pv[x] != pv[y]:
                pairs[(x, y)] += 1; pair_types[(x, y)][t] += 1
        folders = sorted({pkgs[p][1].split('/')[0] if '/' in pkgs[p][1] else '(root)' for p in plist})
        folder_pairs[' + '.join(folders)] += 1
        for p in plist:
            pkg_conf[p] += 1
        if any(in_script_dir[p] for p in plist):
            script_conf[tname(t)] += 1
        vms = {v: max(int(MS[j]) for j in js) for v, js in byv.items()}
        vmt = {v: max(pkgs[int(pk[j])][3] for j in js) for v, js in byv.items()}
        wv = int(variant[int(winner[k])])
        same_ms = len(set(MS[a:b].tolist())) == 1
        kinds['same_msize_different_bytes' if same_ms else 'different_msize'] += 1
        if not same_ms:
            big = max(vms, key=vms.get)
            hint['winner_is_biggest_msize' if wv == big else 'winner_is_not_biggest_msize'] += 1
        if len(set(vmt.values())) > 1:
            new = max(vmt, key=vmt.get)
            hint['winner_in_newest_pkg' if wv == new else 'winner_not_in_newest_pkg'] += 1
            if not same_ms:
                hint['biggest_msize_in_newest_pkg' if max(vms, key=vms.get) == new else 'biggest_msize_not_in_newest_pkg'] += 1
        else:
            hint['all_variants_same_pkg_mtime'] += 1
        srcs = tuple(sorted({source_of(j) for j in range(a, b)}, key=str.lower))
        if len(srcs) == 2:
            src_pairs[srcs] += 1
        if len(examples_by_type[t]) < 3:
            examples_by_type[t].append(int(k))
        if nvar[k] == 2 and same_ms and len(diff_candidates[t]) < 150:
            diff_candidates[t].append(int(k))
    conf_types = collections.Counter({int(t): int(c) for t, c in zip(*np.unique(ktype[ck], return_counts=True))})

    # CASP format version (u32 at offset 0) of every variant of every conflicting CASP: a direct "newer export" signal
    need = collections.defaultdict(list)
    for k in np.nonzero(ck & (ktype == CASP))[0]:
        seen = set()
        for j in range(int(bounds[k]), int(bounds[k + 1])):
            if int(variant[j]) not in seen:
                seen.add(int(variant[j])); need[int(pk[j])].append(j)
    casp_ver = {}
    for p, js in need.items():
        with open(pkg_path(*pkgs[p][:2]), 'rb') as f:
            for j in sorted(js, key=lambda j: int(OFF[j])):
                f.seek(int(OFF[j]))
                try:
                    casp_ver[j] = struct.unpack_from('<I', decompress(int(CP[j]), f.read(int(FS[j]))), 0)[0]
                except Exception:
                    pass
    cv = collections.Counter(); cvh = collections.Counter()
    for k in np.nonzero(ck & (ktype == CASP))[0]:
        a, b = int(bounds[k]), int(bounds[k + 1])
        vv = {}
        for j in range(a, b):
            if j in casp_ver:
                vv.setdefault(int(variant[j]), casp_ver[j])
        if len(vv) < int(nvar[k]):
            cv['unreadable'] += 1; continue
        wv = vv.get(int(variant[int(winner[k])]))
        for v in vv.values():
            cvh[v] += 1
        if len(set(vv.values())) == 1:
            cv['all_variants_same_casp_version'] += 1
        else:
            cv['winner_has_highest_casp_version' if wv == max(vv.values()) else 'winner_has_older_casp_version'] += 1
            vms = {}
            for j in range(a, b):
                vms[int(variant[j])] = max(vms.get(int(variant[j]), 0), int(MS[j]))
            cv['biggest_msize_is_highest_version' if vv[max(vms, key=vms.get)] == max(vv.values()) else 'biggest_msize_is_older_version'] += 1
    hint_casp = {'counts': dict(cv), 'casp_version_histogram_over_variants': {str(k): v for k, v in sorted(cvh.items())}}

    # byte-level difference on a sample of 2-variant, same-size conflicts
    diffs = {}
    for t, ks in diff_candidates.items():
        if conf_types[t] < 20:
            continue
        nd = []
        for k in ks:
            a, b = int(bounds[k]), int(bounds[k + 1])
            js = {}
            for j in range(a, b):
                js.setdefault(int(variant[j]), j)
            try:
                d0, d1 = [read_resource(pkgs[int(pk[j])][0], pkgs[int(pk[j])][1], int(OFF[j]), int(FS[j]), int(CP[j])) for j in js.values()]
            except Exception:
                continue
            x = np.frombuffer(d0, np.uint8); y = np.frombuffer(d1, np.uint8)
            if len(x) == len(y):
                nd.append(int((x != y).sum()))
        if nd:
            nd.sort()
            diffs[tname(t)] = {'sampled': len(nd), 'median_bytes_differing': nd[len(nd) // 2], 'max_bytes_differing': nd[-1],
                               'le_16_bytes_differing': sum(v <= 16 for v in nd)}

    ex = []
    for t, c in conf_types.most_common(20):
        for k in examples_by_type[t][:2]:
            a, b = int(bounds[k]), int(bounds[k + 1])
            e = {'type': tname(t), 'key': '%08X:%08X:%016X' % (T[a], G[a], int(I[a]) & 0xFFFFFFFFFFFFFFFF), 'copies': []}
            for j in sorted(range(a, b), key=lambda j: rank[int(pk[j])]):
                p = int(pk[j])
                cpy = {'pkg': pname(p), 'source': source_of(j), 'variant': int(variant[j]), 'fsize': int(FS[j]), 'msize': int(MS[j]),
                       'comp': '%04X' % CP[j], 'pkg_mtime': time.strftime('%Y-%m-%d', time.localtime(pkgs[p][3])),
                       'load_order_winner': j == int(winner[k])}
                try:
                    nm = xml_name(read_resource(pkgs[p][0], pkgs[p][1], int(OFF[j]), int(FS[j]), int(CP[j])))
                    if nm:
                        cpy['tuning_name'] = nm
                except Exception:
                    pass
                e['copies'].append(cpy)
            ex.append(e)
    res['conflicts'] = {
        'keys': int(ck.sum()), 'by_type': {tname(t): c for t, c in conf_types.most_common()},
        'kinds': dict(kinds),
        'variants_histogram': {str(v): int(c) for v, c in sorted(collections.Counter(nvar[ck].tolist()).items())},
        'copies_histogram': {str(v): int(c) for v, c in sorted(collections.Counter(nc[ck].tolist()).items())},
        'hints': dict(hint),
        'casp_version_hint': hint_casp,
        'byte_diff_sample_same_size_2_variants': diffs,
        'keys_touching_script_mod_folder_packages_by_type': dict(script_conf.most_common()),
        'top_level_folder_combinations': dict(folder_pairs.most_common(20)),
        'n_package_pairs': len(pairs),
        'top_package_pairs': [{'a': pname(x), 'b': pname(y), 'conflicting_keys': n,
                               'types': {tname(t): c for t, c in pair_types[(x, y)].most_common(4)}}
                              for (x, y), n in pairs.most_common(40)],
        'top_packages': [{'pkg': pname(p), 'conflicting_keys': n} for p, n in pkg_conf.most_common(30)],
        'top_source_file_pairs': [{'sources': list(s), 'conflicting_keys': n} for s, n in src_pairs.most_common(40)],
        'examples': ex,
    }

    # ---------------- per-package redundancy
    tot = {p: {'n': 0, 'fsize': 0, 'manifest_n': 0, 'manifest_fsize': 0} for p in pkgs}
    for p, n, s in db.execute('select pkg, count(*), sum(fsize) from res group by pkg'):
        tot[p]['n'] = n; tot[p]['fsize'] = s
    for p, n, s in db.execute('select pkg, count(*), sum(fsize) from res where t=? group by pkg', (S4S_MANIFEST,)):
        tot[p]['manifest_n'] = n; tot[p]['manifest_fsize'] = s
    per = {p: {'n': tot[p]['n'], 'manifest_n': tot[p]['manifest_n'], 'dup_n': 0, 'covered_n': 0, 'covered_fsize': 0,
               'conflict_uncovered_n': 0, 'conflicting_keys': pkg_conf.get(p, 0)} for p in pkgs}
    rows_of_pkg = collections.defaultdict(list)
    for j in range(N):
        p = int(pk[j]); e = per[p]
        rows_of_pkg[p].append(j)
        e['dup_n'] += 1
        if T[j] == S4S_MANIFEST:
            continue
        if covered[j]:
            e['covered_n'] += 1; e['covered_fsize'] += int(FS[j])
        else:
            if rowcls[j] == 3:
                e['conflict_uncovered_n'] += 1
            if T[j] == NAMEMAP:
                e['uncovered_namemap_n'] = e.get('uncovered_namemap_n', 0) + 1
    for p, e in per.items():
        real_n = tot[p]['n'] - tot[p]['manifest_n']
        real_b = tot[p]['fsize'] - tot[p]['manifest_fsize']
        e['unique_key_n'] = tot[p]['n'] - e['dup_n']
        e['uncovered_n'] = real_n - e['covered_n']
        e['fully_redundant'] = real_n > 0 and e['uncovered_n'] == 0
        # NameMap (0x0166038C) only maps instance ids to names for tools; with it ignored:
        e['fully_redundant_ignoring_namemap'] = real_n > 0 and e['uncovered_n'] - e.get('uncovered_namemap_n', 0) == 0
        e['covered_frac_bytes'] = round(e['covered_fsize'] / real_b, 4) if real_b else 0.0
        e['in_script_mod_folder'] = in_script_dir[p]
    # greedy: drop fully redundant packages one at a time while every (key, variant) keeps a copy and no
    # conflicting key's load-order winner variant changes
    def win_var(js):
        return int(variant[min(js, key=lambda j: (rank[int(pk[j])], int(OFF[j])))])

    def greedy(flag, ignore):
        alive = collections.defaultdict(list)
        for j in range(N):
            alive[int(kid[j])].append(j)
        removed = []; blocked = set()
        cands = sorted((p for p, e in per.items() if e[flag]), key=lambda p: (pkgs[p][0] == 'Mods', -pkgs[p][2]))
        for p in cands:
            ok = True
            for j in rows_of_pkg[p]:
                if int(T[j]) in ignore:
                    continue
                k = int(kid[j])
                rest = [x for x in alive[k] if int(pk[x]) != p]
                if not any(variant[x] == variant[j] for x in rest):
                    ok = False; break
                if cls[k] == 3 and win_var(rest) != win_var(alive[k]):
                    ok = False; blocked.add(p); break
            if ok:
                for j in rows_of_pkg[p]:
                    k = int(kid[j])
                    alive[k] = [x for x in alive[k] if int(pk[x]) != p]
                removed.append(p)
        return removed, blocked
    removed, blocked_winner = greedy('fully_redundant', {S4S_MANIFEST})
    removed_nm, _ = greedy('fully_redundant_ignoring_namemap', {S4S_MANIFEST, NAMEMAP})
    fr = [p for p, e in per.items() if e['fully_redundant']]
    hist = collections.Counter()
    for p, e in per.items():
        f = e['covered_frac_bytes']
        b10 = min(int(f * 10), 9) * 10
        hist['100% (fully redundant)' if e['fully_redundant'] else ('0%' if f == 0 else '%02d-%02d%%' % (b10, b10 + 10))] += 1
    res['redundancy'] = {
        'fully_redundant_packages': len(fr), 'fully_redundant_bytes': int(sum(pkgs[p][2] for p in fr)),
        'removable_together_packages': len(removed), 'removable_together_bytes': int(sum(pkgs[p][2] for p in removed)),
        'removable_together': [{'pkg': pname(p), 'size': pkgs[p][2], 'n': per[p]['n']} for p in removed],
        'ignoring_namemap': {
            'fully_redundant_packages': sum(e['fully_redundant_ignoring_namemap'] for e in per.values()),
            'fully_redundant_bytes': int(sum(pkgs[p][2] for p, e in per.items() if e['fully_redundant_ignoring_namemap'])),
            'removable_together_packages': len(removed_nm), 'removable_together_bytes': int(sum(pkgs[p][2] for p in removed_nm)),
            'extra_vs_strict': [{'pkg': pname(p), 'size': pkgs[p][2]} for p in removed_nm if p not in removed]},
        'fully_redundant_but_kept': [{'pkg': pname(p), 'reason': 'would change a load-order winner' if p in blocked_winner else 'its twin was removed instead'}
                                     for p in fr if p not in removed],
        'near_redundant_ge_80pct_bytes': [{'pkg': pname(p), 'size': pkgs[p][2], 'covered_frac_bytes': e['covered_frac_bytes'],
                                           'uncovered_n': e['uncovered_n'], 'n': e['n']}
                                          for p, e in sorted(per.items(), key=lambda kv: -kv[1]['covered_frac_bytes'])
                                          if not e['fully_redundant'] and e['covered_frac_bytes'] >= 0.8],
        'covered_bytes_fraction_histogram': dict(sorted(hist.items())),
    }
    res['per_package'] = [{'pkg': pname(p), 'size': pkgs[p][2], **e}
                          for p, e in sorted(per.items(), key=lambda kv: (-kv[1]['covered_fsize'], kv[0]))]
    # ---------------- packages that sit next to a .ts4script but whose resources were ALSO merged into S4S merges
    rid_idx = {int(r): j for j, r in enumerate(rows['rid'])}
    merged = {p for p in pkgs if tot[p]['manifest_n']}
    comp_out = []
    for p in sorted(pkgs, key=lambda p: pkgs[p][1].lower()):
        if not in_script_dir[p] or p in merged:
            continue
        stem = pkgs[p][1].rsplit('/', 1)[-1].rsplit('.', 1)[0].lower()
        cnt = collections.defaultdict(lambda: [0, 0, 0, 0])   # merged pkg -> [shared, identical, differing, differing & P bigger]
        for ra, rb, mp, ma, mb in db.execute('select r1.rowid, r2.rowid, r2.pkg, r1.msize, r2.msize from res r1 join res r2 '
                                             'on r1.t=r2.t and r1.g=r2.g and r1.i=r2.i and r2.pkg!=r1.pkg where r1.pkg=?', (p,)):
            if mp not in merged:
                continue
            ja, jb = rid_idx[ra], rid_idx[rb]
            c = cnt[mp]; c[0] += 1
            if cls[kid[ja]] in (1, 2) or variant[ja] == variant[jb]:
                c[1] += 1
            else:
                c[2] += 1; c[3] += ma > mb
        n_real = tot[p]['n']
        for mp, (sh, same, dif, pbig) in cnt.items():
            name_hit = mp in srcnames.get(stem, ())
            if sh >= max(2, n_real // 2) or name_hit:
                types = collections.Counter(tname(t) for (t,) in db.execute('select t from res where pkg=?', (p,)))
                comp_out.append({'pkg': pname(p), 'n': n_real, 'types': dict(types.most_common(3)), 'merged_into': pname(mp),
                                 'source_name_in_merge_manifest': name_hit, 'shared_keys': sh, 'identical': same, 'differing': dif,
                                 'differing_where_standalone_is_bigger': pbig,
                                 'load_order_winner': pname(p) if rank[p] < rank[mp] else pname(mp)})
    res['script_folder_packages_inside_merges'] = comp_out
    # conflicts between two standalone (not S4S-merged) packages: typically alternative versions installed together
    alt = [(n, x, y) for (x, y), n in pairs.items() if x not in merged and y not in merged]
    alt.sort(key=lambda e: (-e[0], pkgs[e[1]][1]))
    res['standalone_conflict_pairs'] = {
        'n_pairs': len(alt),
        'top': [{'a': pname(x), 'b': pname(y), 'conflicting_keys': n, 'n_a': tot[x]['n'], 'n_b': tot[y]['n'],
                 'types': {tname(t): c for t, c in pair_types[(x, y)].most_common(3)},
                 'load_order_winner': pname(x) if rank[x] < rank[y] else pname(y)} for n, x, y in alt[:60]]}

    # ---------------- the currently active set (root 'Mods') on its own
    act = {p for p in pkgs if pkgs[p][0] == 'Mods'}
    a_stats = collections.Counter(); a_small_win = []; a_pairs = collections.Counter()
    for k in range(nk):
        if ktype[k] == S4S_MANIFEST:
            continue
        a, b = int(bounds[k]), int(bounds[k + 1])
        js = [j for j in range(a, b) if int(pk[j]) in act]
        if len(js) < 2:
            continue
        vs = {int(variant[j]) for j in js} if cls[k] == 3 else {0}
        if len(vs) == 1:
            a_stats['identical_keys'] += 1; a_stats['redundant_copies'] += len(js) - 1
            a_stats['redundant_stored_bytes'] += int(sum(FS[j] for j in js) - min(FS[j] for j in js))
            continue
        a_stats['conflicting_keys'] += 1
        a_pairs[' + '.join(sorted({pkgs[int(pk[j])][1] for j in js}))] += 1
        w = min(js, key=lambda j: (rank[int(pk[j])], int(OFF[j])))
        if MS[w] < max(MS[j] for j in js) and len(a_small_win) < 40:
            e = {'type': tname(int(T[w])), 'key': '%08X:%08X:%016X' % (T[w], G[w], int(I[w]) & 0xFFFFFFFFFFFFFFFF),
                 'winner': pkgs[int(pk[w])][1], 'winner_msize': int(MS[w]),
                 'others': [{'pkg': pkgs[int(pk[j])][1], 'msize': int(MS[j])} for j in js if j != w]}
            if T[w] in (0x7DF2169C, 0x03B33DDF, 0xE882D22F, 0x6017E896, 0x0C772E27, 0xCB5FDDC7, 0x545AC67A) or MS[w] < 5_000_000:
                try:
                    nm = xml_name(read_resource(pkgs[int(pk[w])][0], pkgs[int(pk[w])][1], int(OFF[w]), int(FS[w]), int(CP[w])))
                    if nm:
                        e['tuning_name'] = nm
                except Exception:
                    pass
            a_small_win.append(e)
    res['active_mods_only'] = {'packages': sorted(pkgs[p][1] for p in act), **dict(a_stats),
                               'conflict_package_sets': dict(a_pairs.most_common(20)),
                               'conflicts_where_load_order_winner_is_not_the_biggest_copy': a_small_win}

    big = sorted(pkgs, key=lambda p: -pkgs[p][2])[:3]
    res['header_check'] = [header(pkg_path(*pkgs[p][:2])) for p in big]
    res['packages_over_2GiB'] = [pname(p) for p in pkgs if pkgs[p][2] >= 1 << 31]
    res['resources_ending_beyond_2GiB'] = int(db.execute('select count(*) from res where off + fsize > 2147483648').fetchone()[0])

    with open(RESULT, 'w', encoding='utf-8') as f:
        json.dump(res, f, indent=1, default=int, ensure_ascii=False)
    cname = {1: 'identical', 2: 'identical_unc', 3: 'conflict', 4: 'undecidable'}
    with gzip.open(KEYS_TSV, 'wt', encoding='utf-8') as f:
        f.write('# pkg ids = library.sqlite pkg.id; copies = pkg:variant:fsize:msize:comp; * = load-order winner\n')
        f.write('type\tgroup\tinstance\tclass\tcopies\tvariants\tcopies_list\n')
        for k in range(nk):
            a, b = int(bounds[k]), int(bounds[k + 1])
            f.write('%08X\t%08X\t%016X\t%s\t%d\t%d\t%s\n' % (
                T[a], G[a], int(I[a]) & 0xFFFFFFFFFFFFFFFF, cname[int(cls[k])], b - a, nvar[k],
                ','.join('%s%d:%d:%d:%d:%X' % ('*' if j == winner[k] else '', pk[j], variant[j], FS[j], MS[j], CP[j]) for j in range(a, b))))
    print('analyze done in %.0fs -> %s' % (time.time() - t0, RESULT), flush=True)


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'all'
    if cmd in ('scan', 'all'):
        scan()
    if cmd in ('analyze', 'all'):
        analyze()
    if cmd == 'header':
        for p in sys.argv[2:]:
            print(json.dumps(header(p), indent=1))
