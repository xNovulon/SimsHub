"""Content hashes of the resources that exist more than once in the mod library, with a persistent cache.

Two copies of a type/group/instance key are "the same resource" only if their bytes say so. This module
reads the copies and hashes them (blake2b, 16-byte digest):

  raw   the resource exactly as stored in the package (usually zlib-compressed). Computed for every copy
        of every duplicated key.
  data  the decompressed resource. Computed only for keys whose copies are NOT all stored identically
        (same bytes and same compression), because the same content can be stored with different
        compression (3.4k keys in this library). For an uncompressed copy data == raw, for free.

Facts this relies on (research/research_results.json -> dupes, and its review):
  * 660k copies / 80 GB of duplicated keys hash in about 105 s on this NVMe when each package's reads are
    sorted by offset, neighbouring resources are read in one call, and 6-8 threads read different
    packages at once (one thread is several times slower).
  * zlib (0x5A42) and RefPack (0xFFFF) are the only compressions in the library. A few zlib streams
    (two LittleMsSam packages) have no final block / adler32 but still inflate to the full size, so a
    stream is accepted when its output length equals the index's uncompressed size.
  * 7 eyebrow textures in sim/111 and sim/PRALINESIMS_MERGED are not valid zlib. Such a copy gets an
    error; its key is 'undecidable' unless every copy is stored byte-identically.
  * The library index (speedkit.library) can be older than the files: every package is stat()ed before
    it is read, and a package whose size or mtime changed is not read (its copies get an error).

The cache lives in data/hash.sqlite:
  copy(root, rel, size, mtime, t, g, i, off -> raw, data, err)
      one row per hashed copy; mtime is stored in whole milliseconds and `off` tells apart the rare
      packages that hold the same key twice. Lookups ignore `root`, so a package the other tool moves
      between Mods and Mods_parked (same relative path, size and mtime) is not read again. A package
      that is rewritten gets a new size/mtime and therefore new rows.
  content(raw, comp -> data)
      the data hash of a stored byte string, so any copy of any key with the same stored bytes reuses a
      data hash computed once.
Read errors are never cached (they may be temporary); decode errors are (they belong to the bytes).

    copies = hash_copies(lib)                 # {(t, g, i): [Copy, ...]} in load order
    dups = hash_duplicates(lib)               # {(t, g, i): [(pkg_id, raw, data_or_None), ...]}
    key_status(dups[key])                     # 'identical' | 'conflict' | 'undecidable'
    effective_map(lib, ('Mods',), keys)       # {key: content hash of the copy the game uses}
"""
import hashlib
import os
import sqlite3
import time
import zlib
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from .dbpf import NONE, ZLIB, REFPACK, DELETED, refpack_decompress
from .library import PROJECT, signed64, unsigned64

DEFAULT_CACHE = os.path.join(PROJECT, 'data', 'hash.sqlite')
DEFAULT_ROOTS = ('Mods', 'Mods_parked')
THREADS = 8
GAP = 256 << 10          # read two resources in one call when the hole between them is smaller than this
WINDOW = 8 << 20         # most bytes read in one call
CHUNK = 4 << 20          # resources bigger than WINDOW are hashed in pieces of this size

SCHEMA = """
create table if not exists copy(root text, rel text, size integer, mtime integer, t integer, g integer, i integer,
                                off integer, raw blob, data blob, err text,
                                primary key(root, rel, size, mtime, t, g, i, off));
create index if not exists copy_file on copy(rel, size, mtime);
create table if not exists content(raw blob, comp integer, data blob, primary key(raw, comp));
"""


def digest(b):
    """blake2b-128 of a bytes-like object."""
    return hashlib.blake2b(b, digest_size=16).digest()


def mtime_ms(mtime):
    """An mtime as the cache stores it: whole milliseconds."""
    return int(round(mtime * 1000))


class Copy:
    """One stored copy of a key: where it is, how it is stored, and its hashes once known.

    pkg/pos: library package id and its position in the load order; rowid/off tell copies inside one
    package apart (rowid follows the package's index order). raw/data are 16-byte digests or None.
    err is None, or why the copy could not be read ('cannot read ...') or decoded ('cannot decompress ...').
    """
    __slots__ = ('key', 'pkg', 'pos', 'rowid', 'off', 'fsize', 'msize', 'comp', 'raw', 'data', 'err')

    def __init__(self, key, pkg, pos, rowid, off, fsize, msize, comp):
        self.key, self.pkg, self.pos, self.rowid = key, pkg, pos, rowid
        self.off, self.fsize, self.msize, self.comp = off, fsize, msize, comp
        self.raw = self.data = self.err = None

    def content(self):
        """Content id: the data hash in hex; 'raw:<comp>:<hex>' when the copy cannot be decompressed;
        'error:<why>' when it could not be read at all."""
        if self.data is not None:
            return self.data.hex()
        if self.raw is not None:
            return 'raw:%04X:%s' % (self.comp, self.raw.hex())
        return 'error:%s' % (self.err or 'not hashed')

    def __repr__(self):
        return 'Copy(%08X:%08X:%016X pkg=%d pos=%d off=%d %s)' % (
            self.key[0], self.key[1], self.key[2], self.pkg, self.pos, self.off, self.content()[:20])


# ---------------------------------------------------------------------------------------------- cache
class HashCache:
    """The persistent hash cache (see the module docstring)."""

    def __init__(self, path=None):
        self.path = path or DEFAULT_CACHE
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.executescript(SCHEMA)

    def lookup(self, rel, size, mtime):
        """{(t, g, i_signed, off): (raw, data, err)} for a package file state, from any root."""
        out = {}
        for t, g, i, off, raw, data, err in self.db.execute(
                'select t, g, i, off, raw, data, err from copy where rel=? and size=? and mtime=?',
                (rel, size, mtime_ms(mtime))):
            out[(t, g, i, off)] = (raw, data, err)
        return out

    def data_of(self, raw, comp):
        """Data hash already known for these stored bytes, or None."""
        if comp == NONE:
            return raw
        row = self.db.execute('select data from content where raw=? and comp=?', (raw, comp)).fetchone()
        return row[0] if row else None

    def store(self, rows):
        """Save hashed copies: rows of (root, rel, size, mtime, t, g, i_signed, off, comp, raw, data, err)."""
        self.db.executemany('insert or replace into copy values(?,?,?,?,?,?,?,?,?,?,?)',
                            [(r[0], r[1], r[2], mtime_ms(r[3]), r[4], r[5], r[6], r[7], r[9], r[10], r[11])
                             for r in rows])
        self.db.executemany('insert or ignore into content values(?,?,?)',
                            [(r[9], r[8], r[10]) for r in rows if r[10] is not None and r[8] != NONE])
        self.db.commit()

    def prune(self, live):
        """Delete rows of package states that no longer exist. live: set of (rel, size, mtime).
        Returns the number of rows removed. Content rows are kept (they are keyed by bytes, not files)."""
        want = {(rel, size, mtime_ms(m)) for rel, size, m in live}
        stale = [f for f in self.db.execute('select distinct rel, size, mtime from copy') if tuple(f) not in want]
        n = 0
        for rel, size, m in stale:
            n += self.db.execute('delete from copy where rel=? and size=? and mtime=?', (rel, size, m)).rowcount
        self.db.commit()
        return n

    def close(self):
        self.db.close()


# ---------------------------------------------------------------------------------------------- reading
def _read_exact(f, n):
    parts = []
    while n > 0:
        b = f.read(n)
        if not b:
            break
        parts.append(b)
        n -= len(b)
    return parts[0] if len(parts) == 1 else b''.join(parts)


def _inflate_into(dec, h, data):
    """Feed stored zlib bytes to a decompressobj, hashing the output in bounded pieces. Returns bytes out."""
    n = 0
    buf = data
    while buf:
        out = dec.decompress(buf, CHUNK)
        h.update(out)
        n += len(out)
        buf = dec.unconsumed_tail
        if dec.eof:
            break
    return n


def data_digest(stored, comp, msize):
    """Digest of a resource's decompressed bytes. Raises ValueError (or zlib.error) if it cannot be decoded
    or does not decode to the index's uncompressed size (msize)."""
    if comp == NONE:
        return digest(stored)
    if comp == ZLIB:
        dec = zlib.decompressobj()
        h = hashlib.blake2b(digest_size=16)
        n = _inflate_into(dec, h, stored)
        tail = dec.flush()      # an unfinished stream (no final block) just stops here
        h.update(tail)
        n += len(tail)
    elif comp == REFPACK:
        out = refpack_decompress(bytes(stored))
        h = hashlib.blake2b(out, digest_size=16)
        n = len(out)
    else:
        raise ValueError('unsupported compression 0x%04X' % comp)
    if n != msize:
        raise ValueError('decompressed to %d bytes, the index says %d' % (n, msize))
    return h.digest()


def _hash_one(stored, item):
    off, fsize, comp, msize, want_data, ref = item
    raw = digest(stored)
    if comp == NONE:
        return ref, raw, raw, None, True
    if not want_data:
        return ref, raw, None, None, True
    try:
        return ref, raw, data_digest(stored, comp, msize), None, True
    except Exception as e:
        return ref, raw, None, 'cannot decompress: %s' % e, True


def _hash_streamed(f, item):
    """Hash one big resource without holding it in memory (RefPack is small and read whole)."""
    off, fsize, comp, msize, want_data, ref = item
    f.seek(off)
    h = hashlib.blake2b(digest_size=16)
    inflate = want_data and comp == ZLIB
    dec, hd, n, err = (zlib.decompressobj(), hashlib.blake2b(digest_size=16), 0, None) if inflate else (None, None, 0, None)
    whole = [] if (want_data and comp == REFPACK) else None
    left = fsize
    while left:
        b = _read_exact(f, min(CHUNK, left))
        if not b:
            return ref, None, None, 'cannot read: resource runs past the end of the file', False
        left -= len(b)
        h.update(b)
        if inflate and err is None:
            try:
                n += _inflate_into(dec, hd, b)
            except zlib.error as e:
                err = 'cannot decompress: %s' % e
        if whole is not None:
            whole.append(b)
    raw = h.digest()
    if comp == NONE:
        return ref, raw, raw, None, True
    if not want_data:
        return ref, raw, None, None, True
    if comp == REFPACK:
        return _hash_one(b''.join(whole), item)
    if comp != ZLIB:
        return ref, raw, None, 'cannot decompress: unsupported compression 0x%04X' % comp, True
    if err is None:
        tail = dec.flush()
        hd.update(tail)
        n += len(tail)
        if n != msize:
            err = 'cannot decompress: decompressed to %d bytes, the index says %d' % (n, msize)
    return ref, raw, (None if err else hd.digest()), err, True


def hash_package(path, size, mtime, items):
    """Hash resources of one package file. items: [(off, fsize, comp, msize, want_data, ref)] sorted by off.

    Returns ([(ref, raw, data, err, cacheable)], bytes_read). Nothing is read if the file's size or mtime
    differ from the given ones (the library index would be stale)."""
    try:
        st = os.stat(path)
        if st.st_size != size or abs(st.st_mtime - mtime) >= 1e-3:
            return [(it[5], None, None, 'cannot read: file changed since the library scan', False) for it in items], 0
        f = open(path, 'rb', buffering=0)
    except OSError as e:
        return [(it[5], None, None, 'cannot read: %s' % e, False) for it in items], 0
    out = []
    nread = 0
    with f:
        k = 0
        while k < len(items):
            start, fs = items[k][0], items[k][1]
            if fs > WINDOW:
                out.append(_hash_streamed(f, items[k]))
                nread += fs
                k += 1
                continue
            end = start + fs
            m = k + 1
            while m < len(items):
                o2, f2 = items[m][0], items[m][1]
                if f2 > WINDOW or o2 - end > GAP or max(end, o2 + f2) - start > WINDOW:
                    break
                end = max(end, o2 + f2)
                m += 1
            f.seek(start)
            buf = _read_exact(f, end - start)
            nread += len(buf)
            mv = memoryview(buf)
            for it in items[k:m]:
                a = it[0] - start
                if a + it[1] > len(buf):
                    out.append((it[5], None, None, 'cannot read: resource runs past the end of the file', False))
                else:
                    out.append(_hash_one(mv[a:a + it[1]], it))
            mv.release()
            k = m
    return out, nread


def _read_copies(cache, pkgs, need, threads, progress, label):
    """Read and hash copies. need: [(Copy, want_data)]. Fills the Copy objects and the cache."""
    if not need:
        return {'packages': 0, 'copies': 0, 'bytes_read': 0, 'seconds': 0.0}
    t0 = time.time()
    by_pkg = defaultdict(list)
    for c, want in need:
        by_pkg[c.pkg].append((c.off, c.fsize, c.comp, c.msize, want, c))
    tasks = sorted(by_pkg.items(), key=lambda kv: -sum(x[1] for x in kv[1]))   # biggest first
    total_bytes = sum(x[1] for _, items in tasks for x in items)
    done = nbytes = 0
    with ThreadPoolExecutor(max(1, threads)) as ex:
        futs = {}
        for pid, items in tasks:
            p = pkgs[pid]
            items.sort(key=lambda x: x[0])
            futs[ex.submit(hash_package, p.path, p.size, p.mtime, items)] = pid
        for fu in as_completed(futs):
            p = pkgs[futs[fu]]
            results, nread = fu.result()
            rows = []
            for c, raw, data, err, cacheable in results:
                c.raw, c.err = raw, err
                if data is not None or raw is None:
                    c.data = data
                if cacheable:
                    rows.append((p.root, p.rel, p.size, p.mtime, c.key[0], c.key[1], signed64(c.key[2]), c.off,
                                 c.comp, raw, c.data, err))
            cache.store(rows)
            done += 1
            nbytes += nread
            if progress:
                progress(label, done, len(tasks), nbytes, total_bytes)
    return {'packages': len(tasks), 'copies': len(need), 'bytes_read': nbytes, 'seconds': round(time.time() - t0, 1)}


def _from_cache(cache, pkgs, copies):
    """Fill copies from the cache (per package). Returns the number of copies found."""
    by_pkg = defaultdict(list)
    for c in copies:
        by_pkg[c.pkg].append(c)
    hits = 0
    for pid, cs in by_pkg.items():
        p = pkgs[pid]
        known = cache.lookup(p.rel, p.size, p.mtime)
        if not known:
            continue
        for c in cs:
            hit = known.get((c.key[0], c.key[1], signed64(c.key[2]), c.off))
            if hit:
                c.raw, c.data, c.err = hit
                hits += 1
    return hits


def _loaded_table(lib, roots, name='hk_loaded'):
    lib.db.execute('drop table if exists temp.%s' % name)
    lib.db.execute('create temp table %s(pkg integer primary key, pos integer)' % name)
    lib.db.executemany('insert into temp.%s values(?,?)' % name, lib.order_positions(roots).items())


def duplicate_copies(lib, roots=DEFAULT_ROOTS):
    """{(t, g, i): [Copy, ...]} for every key stored more than once among the packages the game would load
    from `roots` (laid over each other); copies sorted by load order (first = the copy the game uses).
    Not hashed yet. Deleted-flag entries are ignored, like speedkit.library does.

    The index is read in one sequential pass that SQLite sorts by key (about 11 s for 2.36M entries);
    going through the key index instead reads the table in random order and takes 3-15 times longer."""
    _loaded_table(lib, tuple(roots))
    q = """select r.t, r.g, r.i, l.pos, r.pkg, r.rowid, r.off, r.fsize, r.msize, r.comp
           from res r not indexed join temp.hk_loaded l on l.pkg = r.pkg
           where r.comp != ? order by r.t, r.g, r.i"""
    groups = {}
    run = []

    def close_run():
        if len(run) > 1:
            t, g, i = run[0][:3]
            key = (t, g, unsigned64(i))
            groups[key] = sorted((Copy(key, pid, pos, rowid, off, fs, ms, comp)
                                  for _, _, _, pos, pid, rowid, off, fs, ms, comp in run),
                                 key=lambda c: (c.pos, c.rowid))

    for row in lib.db.execute(q, (DELETED,)):
        if run and row[:3] != run[0][:3]:
            close_run()
            run = []
        run.append(row)
    close_run()
    lib.db.execute('drop table temp.hk_loaded')
    return groups


def hash_copies(lib, roots=DEFAULT_ROOTS, progress=None, cache_path=None, threads=THREADS, stats=None):
    """Every copy of every duplicated key, hashed: {(t, g, i): [Copy, ...]} in load order.

    Raw hashes for all copies; data hashes for every copy of a key whose copies are not all stored
    identically. Uses and fills the cache. progress(label, done_packages, total_packages, bytes_read,
    bytes_total) is called after each package read. If `stats` (a dict) is given it receives the numbers
    of the two reading passes."""
    pkgs = {p.id: p for p in lib.packages()}
    groups = duplicate_copies(lib, roots)
    cache = HashCache(cache_path)
    try:
        allc = [c for cs in groups.values() for c in cs]
        hits = _from_cache(cache, pkgs, allc)
        # pass 1: stored bytes. Decompress at once where the copies are stored with different sizes or
        # compression - their stored bytes cannot all be equal, so the data hash will be needed anyway.
        need = []
        for cs in groups.values():
            uniform = len({(c.fsize, c.msize, c.comp) for c in cs}) == 1
            for c in cs:
                if c.raw is None:
                    need.append((c, not uniform))
        s1 = _read_copies(cache, pkgs, need, threads, progress, 'raw')
        # pass 2: keys whose copies are stored differently need the data hash of every copy
        need = []
        derived = []
        for cs in groups.values():
            if len({(c.raw, c.comp) for c in cs}) < 2:
                continue
            for c in cs:
                if c.data is None and c.err is None and c.raw is not None:
                    d = cache.data_of(c.raw, c.comp)
                    if d is not None:
                        c.data = d
                        derived.append(c)
                    else:
                        need.append((c, True))
        s2 = _read_copies(cache, pkgs, need, threads, progress, 'data')
        if derived:
            cache.store([(pkgs[c.pkg].root, pkgs[c.pkg].rel, pkgs[c.pkg].size, pkgs[c.pkg].mtime, c.key[0], c.key[1],
                          signed64(c.key[2]), c.off, c.comp, c.raw, c.data, c.err) for c in derived])
    finally:
        cache.close()
    if stats is not None:
        stats.update({'keys': len(groups), 'copies': len(allc), 'cache_hits': hits, 'pass1': s1, 'pass2': s2,
                      'data_from_content_cache': len(derived)})
    return groups


def hash_duplicates(lib, roots=DEFAULT_ROOTS, progress=None, cache_path=None, threads=THREADS):
    """{(t, g, i): [(pkg_id, rawhash, datahash_or_None), ...]} for every key stored more than once in the
    packages loaded from `roots`, copies in load order (the first is the one the game uses)."""
    groups = hash_copies(lib, roots, progress, cache_path, threads)
    return {k: [(c.pkg, c.raw, c.data) for c in cs] for k, cs in groups.items()}


def key_status(copies):
    """'identical', 'conflict' or 'undecidable' for the copies of one key.

    copies: a list of Copy, or of (pkg_id, rawhash, datahash_or_None) as hash_duplicates returns.
    identical   - all stored the same way (same raw hash and compression), or all decompress to the same data
    conflict    - the decompressed data differs between copies
    undecidable - a copy could not be read or decoded and the stored bytes differ, so it is unknown"""
    raws = set()
    datas = []
    for c in copies:
        if isinstance(c, Copy):
            raw, data, comp = c.raw, c.data, c.comp
        else:
            raw, data, comp = c[1], c[2], None
        if raw is None:
            return 'undecidable'
        raws.add((raw, comp))
        datas.append(data)
    if all(d is not None for d in datas):
        return 'identical' if len(set(datas)) == 1 else 'conflict'
    if len(raws) == 1:
        return 'identical'
    return 'undecidable'


# ---------------------------------------------------------------------------------------------- effective content
def effective_copies(lib, roots, keys):
    """{key: Copy} of the copy the game would use (first in load order) for each key present in `roots`.
    Not hashed. Keys that no loaded package holds are absent from the result."""
    _loaded_table(lib, tuple(roots))
    db = lib.db
    db.execute('drop table if exists temp.hk_keys')
    db.execute('create temp table hk_keys(t integer, g integer, i integer, primary key(t, g, i))')
    db.executemany('insert or ignore into temp.hk_keys values(?,?,?)', ((t, g, signed64(i)) for t, g, i in keys))
    q = """select r.t, r.g, r.i, l.pos, r.pkg, r.rowid, r.off, r.fsize, r.msize, r.comp
           from temp.hk_keys k join res r on r.t = k.t and r.g = k.g and r.i = k.i
           join temp.hk_loaded l on l.pkg = r.pkg where r.comp != ?"""
    best = {}
    for t, g, i, pos, pid, rowid, off, fs, ms, comp in db.execute(q, (DELETED,)):
        key = (t, g, unsigned64(i))
        cur = best.get(key)
        if cur is None or (pos, rowid) < (cur.pos, cur.rowid):
            best[key] = Copy(key, pid, pos, rowid, off, fs, ms, comp)
    db.execute('drop table temp.hk_keys')
    db.execute('drop table temp.hk_loaded')
    return best


def effective_map(lib, roots, keys, cache_path=None, progress=None, threads=THREADS):
    """{key: content hash of the copy the game uses} for the packages loaded from `roots`.

    The hash is the hex data hash (blake2b-128 of the decompressed resource), so it does not depend on
    which package or compression holds the content. A copy that cannot be decompressed gives
    'raw:<comp>:<hex>'; one that cannot be read gives 'error:<why>'. Keys no loaded package holds map to
    None. Missing hashes are read (and cached); data hashes are shared through the content cache."""
    keys = list(keys)
    pkgs = {p.id: p for p in lib.packages()}
    best = effective_copies(lib, roots, keys)
    cache = HashCache(cache_path)
    try:
        chosen = list(best.values())
        _from_cache(cache, pkgs, chosen)
        need = []
        for c in chosen:
            if c.data is None and c.err is None:
                if c.raw is not None:
                    c.data = cache.data_of(c.raw, c.comp)
                if c.data is None:
                    need.append((c, True))
        _read_copies(cache, pkgs, need, threads, progress, 'effective')
    finally:
        cache.close()
    return {k: (best[k].content() if k in best else None) for k in keys}


# ---------------------------------------------------------------------------------------------- CLI
def main():
    import argparse
    from .library import Library, DEFAULT_DB
    ap = argparse.ArgumentParser(description='Hash every duplicated resource of the mod library (read-only).')
    ap.add_argument('--db', default=DEFAULT_DB, help='library index (not rescanned here)')
    ap.add_argument('--cache', default=DEFAULT_CACHE)
    ap.add_argument('--roots', default=','.join(DEFAULT_ROOTS))
    ap.add_argument('--threads', type=int, default=THREADS)
    a = ap.parse_args()
    lib = Library(a.db)
    last = [0.0]

    def progress(label, done, total, nbytes, tbytes):
        if time.time() - last[0] > 5 or done == total:
            last[0] = time.time()
            print('  %-9s %4d/%d packages  %6.2f / %.2f GB' % (label, done, total, nbytes / 1e9, tbytes / 1e9), flush=True)
    stats = {}
    t0 = time.time()
    groups = hash_copies(lib, tuple(a.roots.split(',')), progress, a.cache, a.threads, stats)
    counts = defaultdict(int)
    for cs in groups.values():
        counts[key_status(cs)] += 1
    print('%d duplicated keys, %d copies in %.1fs: %s' % (len(groups), stats['copies'], time.time() - t0, dict(counts)))
    print('pass 1 %s; pass 2 %s; cache hits %d' % (stats['pass1'], stats['pass2'], stats['cache_hits']))


if __name__ == '__main__':
    main()
