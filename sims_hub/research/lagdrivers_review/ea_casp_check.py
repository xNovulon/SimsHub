"""Read-only: count EA CASP entries/unique instances, split by package family, and overlap with CC CASP instances."""
import os, sys, time, sqlite3
sys.path.insert(0, r'C:\Users\basim\Tools\sims4_speedkit\tools')
from scan_library import read_index, signed64
from collections import Counter
root = r'E:\The Sims 4'
T = 0x034AEECB
fam = Counter(); famu = {}
ea = set(); npk = 0; nres = 0; size = 0
t0 = time.perf_counter()
for dp, dn, fn in os.walk(root):
    for f in fn:
        if f.lower().endswith('.package'):
            p = os.path.join(dp, f)
            try: r = read_index(p)
            except Exception: continue
            npk += 1; nres += len(r); size += os.path.getsize(p)
            key = f.split('_')[0] if '_' in f else f[:-8]
            for t, g, i, o, fs, ms, cp in r:
                if t == T and cp != 0xFFE0:
                    ea.add(signed64(i)); fam[key] += 1; famu.setdefault(key, set()).add(i)
print(npk, 'pkgs', round(size/1e9,1), 'GB', nres, 'entries', round(time.perf_counter()-t0,1), 's')
print('EA CASP entries', sum(fam.values()), 'unique', len(ea))
for k, v in fam.most_common(12): print('  ', k, v, 'unique', len(famu[k]))
db = sqlite3.connect(r'C:\Users\basim\Tools\sims4_speedkit\data\library.sqlite')
cc = set(r[0] for r in db.execute('select distinct i from res where t=?', (T,)))
print('CC unique', len(cc), 'CC instances also in EA', len(cc & ea))
