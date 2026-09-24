"""Count XML tuning resources in the CC library by sniffing a sample of each resource type (read-only)."""
import sqlite3, zlib, os
ROOTS = {'Mods': r'C:\Users\basim\Documents\Electronic Arts\The Sims 4\Mods',
         'Mods_parked': r'C:\Users\basim\Documents\Electronic Arts\The Sims 4\Mods_parked'}
db = sqlite3.connect(r'C:\Users\basim\Tools\sims4_speedkit\data\library.sqlite')
types = db.execute('select t, count(*), sum(msize) from res where comp in (0, 23106) group by t').fetchall()
xml_types = []; total = 0; total_b = 0
for t, n, ms in types:
    rows = db.execute('select p.root, p.rel, r.off, r.fsize, r.comp from res r join pkg p on p.id=r.pkg where r.t=? and r.comp in (0,23106) limit 3', (t,)).fetchall()
    hits = 0
    for root, rel, off, fs, comp in rows:
        with open(os.path.join(ROOTS[root], rel.replace('/', os.sep)), 'rb') as f:
            f.seek(off); b = f.read(min(fs, 1 << 20))
        try:
            if comp == 23106: b = zlib.decompressobj().decompress(b, 64)
        except Exception: continue
        if b.lstrip(b'\xef\xbb\xbf').startswith((b'<?xml', b'<I ', b'<M ')): hits += 1
    if hits:
        xml_types.append((n, t, ms)); total += n; total_b += ms
xml_types.sort(reverse=True)
print('XML tuning resources:', total, 'in', len(xml_types), 'types,', round(total_b/1e6, 1), 'MB uncompressed')
for n, t, ms in xml_types[:12]: print(f'  {t:08X} {n}')
