"""find_module_refs.py <regex> [types...]: search tuning XML resources (read-only) for module/class references."""
import sqlite3, zlib, os, re, sys, collections
ROOT = r'C:\Users\basim\Documents\Electronic Arts\The Sims 4'
db = sqlite3.connect(r'file:C:\Users\basim\Tools\sims4_speedkit\data\library.sqlite?mode=ro', uri=True)
rx = re.compile(sys.argv[1].encode())
types = [int(x, 16) for x in sys.argv[2:]] or [0xE882D22F]
pk = {r[0]: os.path.join(ROOT, r[1], r[2].replace('/', os.sep)) for r in db.execute('select id, root, rel from pkg')}
hits = collections.Counter(); scanned = 0; ex = {}
rows = db.execute('select pkg, t, g, i, off, fsize, comp from res where t in (%s) order by pkg, off' % ','.join('?' * len(types)), types).fetchall()
fh = None; cur = None
for pkg, t, g, i, off, fsize, comp in rows:
    if pkg != cur:
        if fh: fh.close()
        fh = open(pk[pkg], 'rb'); cur = pkg
    fh.seek(off); b = fh.read(fsize)
    if comp == 0x5A42:
        try: b = zlib.decompress(b)
        except Exception: continue
    elif comp not in (0,):
        continue
    scanned += 1
    for m in rx.finditer(b):
        hits[(os.path.relpath(pk[pkg], ROOT), m.group().decode('latin1'))] += 1
        ex.setdefault(pk[pkg], b[max(0, m.start() - 120):m.end() + 60])
print('scanned', scanned)
for k, v in hits.most_common(40): print(v, k)
for k, v in list(ex.items())[:3]: print(k, v)
