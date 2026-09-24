"""Read-only: resample CC RLE2/LRLE sizes (new seed) and EA RLE2/LRLE across ALL EA packages (not only ClientFullBuild)."""
import os, sys, struct, zlib, random, sqlite3
sys.path.insert(0, r'C:\Users\basim\Tools\sims4_speedkit\tools')
from scan_library import read_index
from collections import Counter
random.seed(11)
ROOTS = {'Mods': r'C:\Users\basim\Documents\Electronic Arts\The Sims 4\Mods',
         'Mods_parked': r'C:\Users\basim\Documents\Electronic Arts\The Sims 4\Mods_parked'}
def dims(p, o, fs, cp):
    with open(p, 'rb') as f: f.seek(o); b = f.read(min(fs, 4096))
    if cp == 0x5A42: b = zlib.decompressobj().decompress(b, 256)
    return struct.unpack_from('<HH', b, 8), b[:8]
db = sqlite3.connect(r'C:\Users\basim\Tools\sims4_speedkit\data\library.sqlite')
for t, name in ((0x3453CF95, 'RLE2'), (0x2BC04EDF, 'LRLE')):
    rows = db.execute('select p.root,p.rel,r.off,r.fsize,r.comp from res r join pkg p on p.id=r.pkg where r.t=? and r.comp in (0,23106)', (t,)).fetchall()
    c = Counter(); wh = Counter()
    for root, rel, o, fs, cp in random.sample(rows, 800):
        try: (w, h), mg = dims(os.path.join(ROOTS[root], rel.replace('/', os.sep)), o, fs, cp)
        except Exception: continue
        c[max(w, h)] += 1; wh[(w, h)] += 1
    tot = sum(c.values()); print('CC', name, len(rows), {k: round(100*v/tot, 1) for k, v in sorted(c.items(), reverse=True)}, wh.most_common(4))
ea = {0x3453CF95: [], 0x2BC04EDF: []}
for dp, dn, fn in os.walk(r'E:\The Sims 4'):
    for f in fn:
        if f.endswith('.package') and f.startswith('Client'):
            p = os.path.join(dp, f)
            try: r = read_index(p)
            except Exception: continue
            for t, g, i, o, fs, ms, cp in r:
                if t in ea and cp in (0, 0x5A42): ea[t].append((p, o, fs, cp))
for t, name in ((0x3453CF95, 'RLE2'), (0x2BC04EDF, 'LRLE')):
    c = Counter(); wh = Counter()
    for p, o, fs, cp in random.sample(ea[t], 800):
        (w, h), mg = dims(p, o, fs, cp); c[max(w, h)] += 1; wh[(w, h)] += 1
    tot = sum(c.values()); print('EA all Client*', name, len(ea[t]), {k: round(100*v/tot, 1) for k, v in sorted(c.items(), reverse=True)}, wh.most_common(4))
