"""Index of the game's own resources (read-only on E:\\The Sims 4), so other tools can tell which mod
resources replace or override something EA ships.

What the game loads (research/loadorder + merging + lagdrivers notes, checked against the cfg files
on this machine, game 1.126.73.1030):
  * Base game: Data/Client/Resource.cfg and Data/Simulation/Resource.cfg.
  * Every pack folder EPxx/GPxx/SPxx/FPxx: ResourceClient.cfg and ResourceSimulation.cfg.
  * Patch deltas Delta/<pack>/: ResourceClient.cfg and ResourceSimulation.cfg.
  Each cfg lists "Priority <n>" and "PackedFile <pattern>" lines; patterns are relative to the cfg's
  folder ('*' and '?' wildcards, e.g. ClientDeltaBuild*.package, Strings_*.package for all 18
  languages). "Select <cond> ... End" blocks (ConsoleTray, consoles only) are skipped, and so are the
  *_LE.cfg files (Legacy Edition) and Game/Bin/res (loose fonts, no packages). A file several
  patterns match is registered once; the pattern with the fewest wildcard folder segments gives
  its Priority, the earlier line on a tie. Higher Priority wins between game copies of a key; all
  game priorities are negative, and Mods (500) beat all of them.
  * 5,080 packages / ~4.86M index rows / ~2.62M distinct keys; 4,035 of the files are string
    tables (whether the engine opens every language is unverified).
  * Patch deltas carry 96,751 "deleted" records (compression 0xFFE0). Queries ignore them and count
    a key as present when any game package holds a live copy; for ~24k keys a delta's deletion has a
    higher priority than the live copy, so has() can over-report those - the safe direction when
    the question is "does this mod resource override something of EA's?".

Stored in data/game.sqlite: gpkg(id, rel, size, mtime, priority, cfg, n, err) and
gres(pkg, t, g, i, off, fsize, msize, comp) with the instance SIGNED 64-bit like library.sqlite.
scan() is incremental by size + mtime, so it only re-reads packages a patch changed.

    gi = GameIndex(); gi.scan()
    gi.has(0x034AEECB, 0, 0x1234)        # is this CAS part a game resource?
    gi.override_keys(lib)                # library keys that replace/override game resources
"""
import fnmatch
import os
import re
import sqlite3
import time
from urllib.request import pathname2url

from . import dbconn
from .dbpf import read_entries, DELETED
from .library import PROJECT, signed64, unsigned64

GAME_DIR = r'E:\The Sims 4'
DEFAULT_DB = os.path.join(PROJECT, 'data', 'game.sqlite')
PACK_DIR = re.compile(r'^(EP|GP|SP|FP)\d+$', re.I)
PACK_CFGS = ('ResourceClient.cfg', 'ResourceSimulation.cfg')

SCHEMA = """
create table if not exists gpkg(id integer primary key, rel text unique, size integer, mtime real,
                                priority integer, cfg text, n integer, err text);
create table if not exists gres(pkg integer, t integer, g integer, i integer, off integer, fsize integer,
                                msize integer, comp integer);
"""
INDEXES = """
create index if not exists gres_key on gres(t, g, i, comp);
create index if not exists gres_pkg on gres(pkg);
"""


# ---------------------------------------------------------------- Resource.cfg
def parse_cfg(path):
    """[(line_no, priority, pattern)] for every PackedFile line of a Resource.cfg, in file order.
    Lines inside Select ... End blocks are left out (console-only content)."""
    out = []
    priority = 0
    depth = 0
    with open(path, encoding='utf-8-sig', errors='replace') as f:     # a BOM must not hide the first line
        for n, line in enumerate(f, 1):
            words = line.split()
            if not words:
                continue
            kw = words[0].lower()
            if kw == 'select':
                depth += 1
            elif kw == 'end':
                depth = max(0, depth - 1)
            elif depth:
                continue
            elif kw == 'priority' and len(words) == 2:
                try:
                    priority = int(words[1])
                except ValueError:
                    pass
            elif kw == 'packedfile' and len(words) >= 2:
                pattern = ' '.join(words[1:]).replace('\\', '/')
                while pattern.startswith('./'):
                    pattern = pattern[2:]
                out.append((n, priority, pattern))
    return out


def _wild(seg):
    return seg == '...' or any(c in seg for c in '*?')


def _matches(pattern, rel):
    """Does a cfg pattern (segments split on '/') match a relative path? Case-insensitive."""
    ps = pattern.lower().split('/')
    rs = rel.lower().split('/')

    def m(a, b):
        if not a:
            return not b
        if a[0] == '...':
            return any(m(a[1:], b[k:]) for k in range(len(b)))
        return bool(b) and fnmatch.fnmatchcase(b[0], a[0]) and m(a[1:], b[1:])

    return m(ps, rs)


def cfg_files(game_dir=GAME_DIR):
    """The Resource.cfg files the game reads, as paths relative to game_dir ('/' separated)."""
    out = []
    for d in ('Data/Client', 'Data/Simulation'):
        if os.path.isfile(os.path.join(game_dir, d, 'Resource.cfg')):
            out.append(d + '/Resource.cfg')
    packs = [n for n in os.listdir(game_dir) if PACK_DIR.match(n) and os.path.isdir(os.path.join(game_dir, n))]
    delta = os.path.join(game_dir, 'Delta')
    deltas = sorted(n for n in os.listdir(delta) if os.path.isdir(os.path.join(delta, n))) if os.path.isdir(delta) else []
    for base in sorted(packs) + ['Delta/' + n for n in deltas]:
        for c in PACK_CFGS:
            if os.path.isfile(os.path.join(game_dir, base, c)):
                out.append(base + '/' + c)
    return out


def loaded_packages(game_dir=GAME_DIR):
    """[(rel, priority, cfg_rel)] for every .package some game cfg loads, rel '/' separated."""
    out = {}
    for cfg in cfg_files(game_dir):
        folder = os.path.dirname(os.path.join(game_dir, cfg))
        lines = parse_cfg(os.path.join(game_dir, cfg))
        if not lines:
            continue
        deep = any('...' in p for _, _, p in lines)
        max_depth = max(p.count('/') for _, _, p in lines)
        files = []
        for dp, dn, fn in os.walk(folder):
            sub = os.path.relpath(dp, folder).replace('\\', '/')
            depth = 0 if sub == '.' else sub.count('/') + 1
            if not deep and depth >= max_depth:
                dn[:] = []
            for name in fn:
                if name.lower().endswith('.package'):
                    files.append(name if sub == '.' else sub + '/' + name)
        base = os.path.relpath(folder, game_dir).replace('\\', '/')
        for rel in files:
            best = None
            for n, prio, pat in lines:
                if _matches(pat, rel):
                    wild = sum(1 for s in pat.split('/')[:-1] if _wild(s))
                    if best is None or wild < best[0]:
                        best = (wild, prio)
            if best is not None:
                out.setdefault(base + '/' + rel, (best[1], cfg))
    return [(rel, prio, cfg) for rel, (prio, cfg) in sorted(out.items())]


# ---------------------------------------------------------------- the index
class GameIndex:
    """Keys of every resource the game itself loads, kept in a small SQLite cache."""

    def __init__(self, db=DEFAULT_DB, game_dir=GAME_DIR):
        self.db_path = db
        self.game_dir = game_dir
        os.makedirs(os.path.dirname(os.path.abspath(db)), exist_ok=True)
        self.db = dbconn.connect(db, uri=True)
        self.db.executescript(SCHEMA)

    def scan(self, verbose=False):
        """Bring the index up to date with the game folder (only changed packages are re-read).
        Returns {'packages', 'reread', 'removed', 'rows', 'seconds'}."""
        t0 = time.time()
        plan = loaded_packages(self.game_dir)
        known = {rel: (pid, size, mtime) for pid, rel, size, mtime in
                 self.db.execute('select id, rel, size, mtime from gpkg')}
        seen = set()
        reread = rows = 0
        self.db.execute('pragma synchronous=off')
        for k, (rel, prio, cfg) in enumerate(plan):
            full = os.path.join(self.game_dir, rel.replace('/', os.sep))
            try:
                st = os.stat(full)
            except OSError:
                continue
            seen.add(rel)
            old = known.get(rel)
            if old and old[1] == st.st_size and abs(old[2] - st.st_mtime) < 1e-3:
                self.db.execute('update gpkg set priority=?, cfg=? where id=?', (prio, cfg, old[0]))
                continue
            if old:
                self.db.execute('delete from gres where pkg=?', (old[0],))
                self.db.execute('delete from gpkg where id=?', (old[0],))
            try:
                with open(full, 'rb') as f:
                    entries, err = read_entries(f), None
            except Exception as e:
                entries, err = [], '%s: %s' % (type(e).__name__, e)
            cur = self.db.execute('insert into gpkg(rel, size, mtime, priority, cfg, n, err) values(?,?,?,?,?,?,?)',
                                  (rel, st.st_size, st.st_mtime, prio, cfg, len(entries), err))
            self.db.executemany('insert into gres values(?,?,?,?,?,?,?,?)',
                                [(cur.lastrowid, e.t, e.g, signed64(e.i), e.off, e.fsize, e.msize, e.comp)
                                 for e in entries])
            reread += 1
            rows += len(entries)
            if verbose and reread % 500 == 0:
                print('  %d/%d packages read, %d rows, %.0fs' % (k + 1, len(plan), rows, time.time() - t0))
        gone = [pid for rel, (pid, _, _) in known.items() if rel not in seen]
        for pid in gone:
            self.db.execute('delete from gres where pkg=?', (pid,))
            self.db.execute('delete from gpkg where id=?', (pid,))
        self.db.commit()
        self.db.executescript(INDEXES)
        self.db.commit()
        self.db.execute('pragma synchronous=full')
        stats = {'packages': len(seen), 'reread': reread, 'removed': len(gone), 'rows': rows,
                 'seconds': round(time.time() - t0, 1)}
        if verbose:
            print('game scan: %(packages)d packages, %(reread)d re-read (%(rows)d rows), %(removed)d gone, '
                  '%(seconds)ss' % stats)
        return stats

    # ------------------------------------------------------------ queries
    def has(self, t, g, i):
        """Does any game package hold this key (deleted markers excluded)?"""
        return self.db.execute('select 1 from gres where t=? and g=? and i=? and comp!=? limit 1',
                               (t, g, signed64(i), DELETED)).fetchone() is not None

    def _require_scanned(self):
        """An index that was never scanned would answer "not a game resource" for everything."""
        if self.db.execute('select 1 from gpkg limit 1').fetchone() is None:
            raise RuntimeError('the game index %s is empty: run GameIndex.scan() first' % self.db_path)

    def ids_of_type(self, t):
        """Set of (unsigned) instance ids the game ships for resource type t, any group.
        Raises RuntimeError if the index was never scanned."""
        self._require_scanned()
        return {unsigned64(i) for (i,) in
                self.db.execute('select distinct i from gres where t=? and comp!=?', (t, DELETED))}

    def where(self, t, g, i):
        """[(rel, priority)] of the game packages holding this key, the copy the game uses first."""
        rows = self.db.execute('select p.rel, p.priority from gres r join gpkg p on p.id=r.pkg '
                               'where r.t=? and r.g=? and r.i=? and r.comp!=?', (t, g, signed64(i), DELETED))
        return sorted(rows, key=lambda r: -r[1])

    def override_keys(self, lib, roots=('Mods', 'Mods_parked')):
        """Set of (t, g, i) keys that packages of the library `lib` in `roots` share with the game:
        default replacements and tuning overrides. Reads lib's database read-only; scan the
        library first if files may have moved. While the query runs (7-40 s) it holds a read lock on
        lib's database, so give it a private copy rather than a library.sqlite other tools write to.
        Raises RuntimeError if the game index was never scanned (an empty answer would be wrong)."""
        self._require_scanned()
        roots = (roots,) if isinstance(roots, str) else tuple(roots)     # 'Mods' is one root, not 4 letters
        uri = 'file:' + pathname2url(os.path.abspath(lib.db_path)) + '?mode=ro'
        self.db.execute('attach database ? as lib', (uri,))
        try:
            marks = ','.join('?' * len(roots))
            q = ('select distinct r.t, r.g, r.i from lib.res r join lib.pkg p on p.id = r.pkg '
                 'where p.root in (%s) and r.comp != ? and exists '
                 '(select 1 from main.gres x where x.t = r.t and x.g = r.g and x.i = r.i and x.comp != ?)' % marks)
            return {(t, g, unsigned64(i)) for t, g, i in self.db.execute(q, tuple(roots) + (DELETED, DELETED))}
        finally:
            self.db.execute('detach database lib')

    def stats(self):
        """Counts for reports: packages, rows, distinct keys, string-table packages, max priority."""
        one = lambda q: self.db.execute(q).fetchone()[0]
        return {'packages': one('select count(*) from gpkg'),
                'unreadable': one('select count(*) from gpkg where err is not null'),
                'rows': one('select count(*) from gres'),
                'distinct_keys': one('select count(*) from (select distinct t, g, i from gres)'),
                'string_packages': one("select count(*) from gpkg where rel like '%/Strings^_%' escape '^'"),
                'bytes': one('select coalesce(sum(size), 0) from gpkg')}

    def close(self):
        self.db.close()


def main():
    import argparse
    ap = argparse.ArgumentParser(description='Index the game packages (read-only) into data/game.sqlite.')
    ap.add_argument('--db', default=DEFAULT_DB)
    ap.add_argument('--game', default=GAME_DIR)
    ap.add_argument('--overrides', action='store_true', help='also count library keys that override game keys')
    a = ap.parse_args()
    gi = GameIndex(a.db, a.game)
    gi.scan(verbose=True)
    print(gi.stats())
    if a.overrides:
        from .library import Library
        t0 = time.time()
        keys = gi.override_keys(Library())
        print('library keys that also exist in the game: %d (%.1fs)' % (len(keys), time.time() - t0))


if __name__ == '__main__':
    main()
