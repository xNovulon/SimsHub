"""Read the index of every .package in the mod library (Mods + Mods_parked) into SQLite.

Only package headers and indexes are read - never resource contents - so a full scan of
hundreds of GB takes seconds. Nothing in the library is written to.

    python scan_library.py [out.sqlite]
"""
import os, struct, sqlite3, sys, time

SIMS = os.path.join(os.path.expanduser('~'), 'Documents', 'Electronic Arts', 'The Sims 4')
ROOTS = {'Mods': os.path.join(SIMS, 'Mods'), 'Mods_parked': os.path.join(SIMS, 'Mods_parked')}
SKIP_DIRS = {'_old_caches'}
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB = os.path.join(HERE, '..', 'data', 'library.sqlite')


def read_index(path):
    """[(type, group, instance, offset, file_size, mem_size, compression)] or raises."""
    with open(path, 'rb') as f:
        head = f.read(96)
        if len(head) < 96 or head[:4] != b'DBPF':
            raise ValueError('not a DBPF package (starts with %r)' % head[:4])
        count, pos_low, size = struct.unpack_from('<III', head, 36)
        pos = struct.unpack_from('<I', head, 64)[0] or pos_low
        if count == 0:
            return []
        f.seek(pos)
        data = f.read(size)
    flags = struct.unpack_from('<I', data, 0)[0]
    p = 4
    const = {}
    for bit, key in ((1, 't'), (2, 'g'), (4, 'ih')):
        if flags & bit:
            const[key] = struct.unpack_from('<I', data, p)[0]
            p += 4
    out = []
    for _ in range(count):
        if 't' in const:
            t = const['t']
        else:
            t = struct.unpack_from('<I', data, p)[0]; p += 4
        if 'g' in const:
            g = const['g']
        else:
            g = struct.unpack_from('<I', data, p)[0]; p += 4
        if 'ih' in const:
            ih = const['ih']
        else:
            ih = struct.unpack_from('<I', data, p)[0]; p += 4
        il, off, fsize, msize = struct.unpack_from('<IIII', data, p)
        p += 16
        comp = 0
        if fsize & 0x80000000:
            comp = struct.unpack_from('<H', data, p)[0]
            p += 4
        out.append((t, g, (ih << 32) | il, off, fsize & 0x7FFFFFFF, msize, comp))
    return out


def signed64(i):
    return i - (1 << 64) if i >= (1 << 63) else i


def main(db_path=DEFAULT_DB):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    for f in (db_path, db_path + '-wal', db_path + '-shm'):     # the Hub keeps it in WAL: its log goes too
        if os.path.exists(f):
            os.remove(f)
    db = sqlite3.connect(db_path)
    db.executescript("""
        create table pkg(id integer primary key, root text, rel text, size integer, mtime real, n integer, err text);
        create table res(pkg integer, t integer, g integer, i integer, off integer, fsize integer, msize integer, comp integer);
        create table script(root text, rel text, size integer, mtime real);
    """)
    t0 = time.time()
    total = 0
    for root_name, root in ROOTS.items():
        if not os.path.isdir(root):
            continue
        for dp, dn, fn in os.walk(root):
            dn[:] = sorted(d for d in dn if d not in SKIP_DIRS)
            for n in sorted(fn):
                path = os.path.join(dp, n)
                rel = os.path.relpath(path, root).replace('\\', '/')
                low = n.lower()
                st = os.stat(path)
                if low.endswith('.ts4script'):
                    db.execute('insert into script values(?,?,?,?)', (root_name, rel, st.st_size, st.st_mtime))
                    continue
                if not low.endswith('.package'):
                    continue
                try:
                    entries, err = read_index(path), None
                except Exception as e:
                    entries, err = [], '%s: %s' % (type(e).__name__, e)
                cur = db.execute('insert into pkg(root,rel,size,mtime,n,err) values(?,?,?,?,?,?)',
                                 (root_name, rel, st.st_size, st.st_mtime, len(entries), err))
                db.executemany('insert into res values(?,?,?,?,?,?,?,?)',
                               [(cur.lastrowid, t, g, signed64(i), off, fs, ms, c) for t, g, i, off, fs, ms, c in entries])
                total += len(entries)
    db.execute('create index res_tgi on res(t,g,i)')
    db.execute('create index res_pkg on res(pkg)')
    db.commit()
    n_pkg = db.execute('select count(*) from pkg').fetchone()[0]
    print('scanned %d packages, %d resources in %.1fs -> %s' % (n_pkg, total, time.time() - t0, os.path.abspath(db_path)))


if __name__ == '__main__':
    main(*sys.argv[1:])
