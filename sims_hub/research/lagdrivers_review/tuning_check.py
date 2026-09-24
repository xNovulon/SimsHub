"""Read-only: re-estimate XML tuning count by sampling up to 40 random resources per type (all compressions readable)."""
import sqlite3, zlib, os, random
random.seed(7)
ROOTS = {'Mods': r'C:\Users\basim\Documents\Electronic Arts\The Sims 4\Mods',
         'Mods_parked': r'C:\Users\basim\Documents\Electronic Arts\The Sims 4\Mods_parked'}
db = sqlite3.connect(r'C:\Users\basim\Tools\sims4_speedkit\data\library.sqlite')
types = db.execute('select t, count(*), sum(msize), sum(comp not in (0,23106)) from res group by t').fetchall()
def isxml(root, rel, off, fs, comp):
    with open(os.path.join(ROOTS[root], rel.replace('/', os.sep)), 'rb') as f:
        f.seek(off); b = f.read(min(fs, 1 << 16))
    if comp == 23106: b = zlib.decompressobj().decompress(b, 64)
    return b.lstrip(b'\xef\xbb\xbf').lstrip()[:5] in (b'<?xml', b'<I n=', b'<M n=') or b.lstrip(b'\xef\xbb\xbf').lstrip().startswith((b'<?xml', b'<I ', b'<M '))
est = 0; est_b = 0; out = []; zero_first3 = []
for t, n, ms, other in types:
    if ms / n > 2e6: continue  # skip big binary types quickly
    ids = [r[0] for r in db.execute('select rowid from res where t=? and comp in (0,23106)', (t,))]
    if not ids: continue
    pick = random.sample(ids, min(40, len(ids)))
    h = 0
    for rid in pick:
        row = db.execute('select p.root,p.rel,r.off,r.fsize,r.comp from res r join pkg p on p.id=r.pkg where r.rowid=?', (rid,)).fetchone()
        try: h += isxml(*row)
        except Exception: pass
    if h:
        frac = h / len(pick); est += n * frac; est_b += ms * frac; out.append((n, t, frac, other))
out.sort(reverse=True)
print('estimated XML tuning resources', round(est), 'types with any XML', len(out), 'MB', round(est_b/1e6, 1))
for n, t, f, o in out[:15]: print(f'  {t:08X} n={n} xmlfrac={f:.2f} non-zlib={o}')
print('partial types:', [(f'{t:08X}', n, round(f, 2)) for n, t, f, o in out if f < 1])
pid = db.execute("select id from pkg where rel like 'sim/68.package'").fetchone()
print('sim/68 pkg', pid)
