"""Read-only: time reading header+index of every package (phase 1 of lagdrivers bench), plus parse cost."""
import sqlite3, time, struct, os, sys
sys.path.insert(0, r'C:\Users\basim\Tools\sims4_speedkit\tools')
from scan_library import read_index
ROOTS = {'Mods': r'C:\Users\basim\Documents\Electronic Arts\The Sims 4\Mods',
         'Mods_parked': r'C:\Users\basim\Documents\Electronic Arts\The Sims 4\Mods_parked'}
db = sqlite3.connect(r'C:\Users\basim\Tools\sims4_speedkit\data\library.sqlite')
pkgs = db.execute('select id, root, rel from pkg order by id').fetchall()
t0 = time.perf_counter(); n=0; b=0
for pid, root, rel in pkgs:
    with open(os.path.join(ROOTS[root], rel.replace('/', os.sep)), 'rb') as f:
        h = f.read(96); cnt, isz, ipos = struct.unpack_from('<I', h, 36)[0], struct.unpack_from('<I', h, 44)[0], struct.unpack_from('<I', h, 64)[0]
        f.seek(ipos); b += len(f.read(isz)); n += cnt
t1 = time.perf_counter()
print(f'raw index read: {len(pkgs)} pkgs {n} entries {b/1e6:.1f} MB {t1-t0:.2f}s')
t0 = time.perf_counter(); m = 0; d = {}
for pid, root, rel in pkgs:
    for e in read_index(os.path.join(ROOTS[root], rel.replace('/', os.sep))):
        d[(e[0], e[1], e[2])] = pid; m += 1
print(f'read+parse+hash-insert: {m} entries, {len(d)} unique keys, {time.perf_counter()-t0:.2f}s')
