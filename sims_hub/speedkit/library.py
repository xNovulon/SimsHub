"""The mod library: every package and script in Mods and Mods_parked, their indexes, and the game's load order.

Facts this module relies on (research/research_results.json, loadorder + its review):
  * The game walks Mods depth-first with FindFirstFileW/FindNextFileW, no sorting: on NTFS that is
    upper-cased ordinal name order, and a sub-folder is entered at the point its name comes up.
    os.scandir() returns the same order for a real folder.
  * The default Resource.cfg loads *.package up to 5 folders below Mods, all at Priority 500.
  * Same Priority: the FIRST loaded copy of a type/group/instance key is used; later copies are ignored.
  * .ts4script files load from the Mods root or one folder down only, whatever Resource.cfg says.
Mods_parked mirrors Mods paths (another tool parks files there and puts them back at the same place),
so the "full" library is Mods + Mods_parked laid over each other at the same relative paths.
"""
import os, sqlite3, subprocess, threading, time
from collections import namedtuple

from . import dbconn
from .dbpf import read_entries, open_shared, DELETED

SIMS = os.path.join(os.path.expanduser('~'), 'Documents', 'Electronic Arts', 'The Sims 4')
MODS = os.path.join(SIMS, 'Mods')
PARKED = os.path.join(SIMS, 'Mods_parked')
ROOTS = {'Mods': MODS, 'Mods_parked': PARKED}
SKIP_DIRS = {'_old_caches'}          # thumbnail caches parked by the other tool: never mods
MAX_DEPTH = 5                        # default Resource.cfg: PackedFile */*/*/*/*/*.package
PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(PROJECT, 'data', 'library.sqlite')

DEFAULT_RESOURCE_CFG = ['Priority 500', 'PackedFile *.package', 'PackedFile */*.package', 'PackedFile */*/*.package',
                        'PackedFile */*/*/*.package', 'PackedFile */*/*/*/*.package', 'PackedFile */*/*/*/*/*.package']

Pkg = namedtuple('Pkg', 'id root rel path size mtime n err')
Script = namedtuple('Script', 'root rel path size mtime')

SCHEMA = """
create table if not exists pkg(id integer primary key, root text, rel text, size integer, mtime real, n integer, err text,
                               unique(root, rel));
create table if not exists res(pkg integer, t integer, g integer, i integer, off integer, fsize integer, msize integer,
                               comp integer);
create table if not exists script(root text, rel text, size integer, mtime real, primary key(root, rel));
create table if not exists other(root text, rel text, size integer, kind text, primary key(root, rel));
create index if not exists res_tgi on res(t, g, i);
create index if not exists res_pkg on res(pkg);
"""


def signed64(i):
    return i - (1 << 64) if i >= (1 << 63) else i


def unsigned64(i):
    return i + (1 << 64) if i < 0 else i


def ntfs_key(name):
    """Sort key matching NTFS directory order: each UTF-16 unit upper-cased on its own, then ordinal."""
    out = []
    for ch in name:
        u = ch.upper()
        c = u if len(u) == 1 else ch
        code = ord(c)
        if code > 0xFFFF:                      # astral char: two UTF-16 units, surrogates sort as they are
            code -= 0x10000
            out.extend((0xD800 + (code >> 10), 0xDC00 + (code & 0x3FF)))
        else:
            out.append(code)
    return out


def depth_of(rel):
    return rel.count('/')


def game_running():
    """True if TS4_x64.exe runs - and also True when that cannot be checked (fail safe)."""
    try:
        r = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq TS4_x64.exe', '/NH', '/FO', 'CSV'],
                           capture_output=True, text=True, timeout=30,
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if r.returncode != 0:
            return True
        return 'ts4_x64.exe' in r.stdout.lower()
    except Exception:
        return True


# One scan at a time in this process: a second one waits for the first (then finds little to do) instead of both
# writing at once. A scan stays one transaction, so nothing ever sees a half-updated library; readers see the
# library as it was until the scan commits (WAL). Everyday use waits up to dbconn's 60 s for a lock; only a scan
# waits longer (SCAN_WAIT, for another scan to finish), and it says so when even that runs out.
_SCAN_LOCK = threading.Lock()
SCAN_WAIT = 900


class StillScanning(RuntimeError):
    """Another scan of the mods has been running for longer than SCAN_WAIT."""


class Library:
    def __init__(self, db_path=DEFAULT_DB, roots=None):
        self.db_path = db_path
        self.roots = dict(roots or ROOTS)
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db = dbconn.connect(db_path)
        self.db.executescript(SCHEMA)

    def path(self, root, rel):
        return os.path.join(self.roots[root], rel.replace('/', os.sep))

    # ---------------------------------------------------------------- scanning
    def scan(self, verbose=False):
        """Bring the index up to date. Only packages whose size or mtime changed are re-read."""
        if not _SCAN_LOCK.acquire(timeout=SCAN_WAIT):
            raise StillScanning('Your mods are still being read. Try again in a few minutes.')
        try:
            # a scan may wait long for another writer (e.g. another program on the same file); reads stay quick
            self.db.execute('pragma busy_timeout=%d' % (SCAN_WAIT * 1000))
            try:
                return self._scan(verbose)
            finally:
                self.db.execute('pragma busy_timeout=%d' % int(dbconn.DEFAULT_TIMEOUT * 1000))
        finally:
            _SCAN_LOCK.release()

    def _scan(self, verbose=False):
        t0 = time.time()
        known = {(r, rel): (pid, size, mtime) for pid, r, rel, size, mtime in
                 self.db.execute('select id, root, rel, size, mtime from pkg')}
        seen = set()
        reread = 0
        self.db.execute('delete from script')
        self.db.execute('delete from other')
        for root_name, root in self.roots.items():
            if not os.path.isdir(root):
                continue
            for dp, dn, fn in os.walk(root):
                dn[:] = [d for d in dn if d not in SKIP_DIRS]
                for n in fn:
                    full = os.path.join(dp, n)
                    rel = os.path.relpath(full, root).replace('\\', '/')
                    low = n.lower()
                    try:
                        st = os.stat(full)
                    except OSError:
                        continue
                    if low.endswith('.ts4script'):
                        self.db.execute('insert or replace into script values(?,?,?,?)', (root_name, rel, st.st_size, st.st_mtime))
                        continue
                    if not low.endswith('.package'):
                        kind = 'resource.cfg' if low == 'resource.cfg' else os.path.splitext(low)[1] or 'none'
                        self.db.execute('insert or replace into other values(?,?,?,?)', (root_name, rel, st.st_size, kind))
                        continue
                    seen.add((root_name, rel))
                    old = known.get((root_name, rel))
                    if old and old[1] == st.st_size and abs(old[2] - st.st_mtime) < 1e-3:
                        continue
                    if old:
                        self.db.execute('delete from res where pkg=?', (old[0],))
                        self.db.execute('delete from pkg where id=?', (old[0],))
                    try:
                        with open_shared(full) as f:
                            entries, err = read_entries(f), None
                    except Exception as e:
                        entries, err = [], '%s: %s' % (type(e).__name__, e)
                    cur = self.db.execute('insert into pkg(root, rel, size, mtime, n, err) values(?,?,?,?,?,?)',
                                          (root_name, rel, st.st_size, st.st_mtime, len(entries), err))
                    self.db.executemany('insert into res values(?,?,?,?,?,?,?,?)',
                                        [(cur.lastrowid, e.t, e.g, signed64(e.i), e.off, e.fsize, e.msize, e.comp)
                                         for e in entries])
                    reread += 1
        gone = [pid for key, (pid, _, _) in known.items() if key not in seen]
        for pid in gone:
            self.db.execute('delete from res where pkg=?', (pid,))
            self.db.execute('delete from pkg where id=?', (pid,))
        self.db.commit()
        stats = {'packages': len(seen), 'reread': reread, 'removed': len(gone), 'seconds': round(time.time() - t0, 2)}
        if verbose:
            print('library scan: %(packages)d packages, %(reread)d re-read, %(removed)d gone, %(seconds)ss' % stats)
        return stats

    # ---------------------------------------------------------------- queries
    def packages(self, root=None):
        q = 'select id, root, rel, size, mtime, n, err from pkg'
        rows = self.db.execute(q + (' where root=?' if root else ''), (root,) if root else ())
        return [Pkg(pid, r, rel, self.path(r, rel), size, mtime, n, err) for pid, r, rel, size, mtime, n, err in rows]

    def scripts(self, root=None):
        q = 'select root, rel, size, mtime from script'
        rows = self.db.execute(q + (' where root=?' if root else ''), (root,) if root else ())
        return [Script(r, rel, self.path(r, rel), size, mtime) for r, rel, size, mtime in rows]

    def entries(self, pkg_id):
        return self.db.execute('select t, g, i, off, fsize, msize, comp from res where pkg=?', (pkg_id,)).fetchall()

    def resource_cfg(self, root='Mods'):
        p = os.path.join(self.roots[root], 'Resource.cfg')
        if not os.path.exists(p):
            return None
        with open(p, encoding='utf-8', errors='replace') as f:
            return [l.strip() for l in f if l.strip()]

    def resource_cfg_is_default(self, root='Mods'):
        lines = self.resource_cfg(root)
        return lines is not None and [l.lower() for l in lines] == [l.lower() for l in DEFAULT_RESOURCE_CFG]

    def nested_resource_cfgs(self):
        return [(r, rel) for r, rel in self.db.execute("select root, rel from other where kind='resource.cfg'") if '/' in rel]

    # ---------------------------------------------------------------- load order
    def load_order(self, roots=('Mods', 'Mods_parked'), max_depth=MAX_DEPTH):
        """Packages in the order the game would load them if every root were laid over Mods.

        Returns [(root, rel)], earliest first. Packages deeper than max_depth folders are left out
        (the default Resource.cfg never loads them). With a single real root the result equals the
        game's own FindFirstFileW walk; with several roots the folders are merged by NTFS name order.
        """
        tree = {}
        taken = set()
        rows = sorted(self.db.execute('select id, root, rel from pkg'),
                      key=lambda x: roots.index(x[1]) if x[1] in roots else len(roots))
        for pid, r, rel in rows:
            if r not in roots or depth_of(rel) > max_depth:
                continue
            if rel.upper() in taken:          # same path in an earlier root: that copy is the one in Mods
                continue
            taken.add(rel.upper())
            node = tree
            parts = rel.split('/')
            for d in parts[:-1]:
                node = node.setdefault(('d', d.upper()), {'__name__': d})
            node[('f', parts[-1].upper(), r)] = (r, rel, parts[-1])
        out = []

        def walk(node):
            items = []
            for k, v in node.items():
                if k == '__name__':
                    continue
                name = v['__name__'] if k[0] == 'd' else v[2]
                items.append((ntfs_key(name), 0 if k[0] == 'd' else 1, roots.index(k[2]) if k[0] == 'f' else 0, k, v))
            items.sort(key=lambda x: (x[0], x[2]))
            for _, kind, _, k, v in items:
                if kind == 0:
                    walk(v)
                else:
                    out.append(v[:2])
        walk(tree)
        return out

    def order_positions(self, roots=('Mods', 'Mods_parked')):
        """pkg id -> position in load order (packages that never load are absent)."""
        ids = {(r, rel): pid for pid, r, rel in self.db.execute('select id, root, rel from pkg')}
        return {ids[k]: n for n, k in enumerate(self.load_order(roots)) if k in ids}

    def duplicated_keys(self, roots=('Mods', 'Mods_parked')):
        """{(t,g,i): [(position, pkg_id, fsize, msize, comp), ...] sorted by load position} for keys in 2+ loaded packages."""
        pos = self.order_positions(roots)
        self.db.execute('drop table if exists temp.loaded')
        self.db.execute('create temp table loaded(pkg integer primary key, pos integer)')
        self.db.executemany('insert into temp.loaded values(?,?)', pos.items())
        q = """select r.t, r.g, r.i, l.pos, r.pkg, r.fsize, r.msize, r.comp
               from res r join temp.loaded l on l.pkg = r.pkg
               where r.comp != ? and (r.t, r.g, r.i) in (
                   select r2.t, r2.g, r2.i from res r2 join temp.loaded l2 on l2.pkg = r2.pkg
                   where r2.comp != ? group by r2.t, r2.g, r2.i having count(*) > 1)"""
        out = {}
        for t, g, i, p, pid, fs, ms, c in self.db.execute(q, (DELETED, DELETED)):
            out.setdefault((t, g, unsigned64(i)), []).append((p, pid, fs, ms, c))
        self.db.commit()                   # ends the read, so the library file's log can be tidied up (WAL)
        for v in out.values():
            v.sort()
        return out

    def winners(self, roots=('Mods', 'Mods_parked')):
        """{(t,g,i): pkg_id of the copy the game uses} for duplicated keys (first loaded wins)."""
        return {k: v[0][1] for k, v in self.duplicated_keys(roots).items()}

    def close(self):
        self.db.close()
