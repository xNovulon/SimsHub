"""Sample CC texture headers (RLE2/RLES, LRLE, DDS) and report resolution distribution. Read-only.
usage: python texture_sizes.py [samples_per_type]"""
import sqlite3, zlib, os, struct, sys, random
from collections import Counter
ROOTS = {'Mods': r'C:\Users\basim\Documents\Electronic Arts\The Sims 4\Mods',
         'Mods_parked': r'C:\Users\basim\Documents\Electronic Arts\The Sims 4\Mods_parked'}
N = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
db = sqlite3.connect(r'C:\Users\basim\Tools\sims4_speedkit\data\library.sqlite')
random.seed(1)

def dims(t, b):
    if t in (0x3453CF95, 0xBA856C78):  # RLE2 / RLES: fourcc, version, w, h
        return struct.unpack_from('<HH', b, 8)
    if t == 0x2BC04EDF:  # LRLE: magic, version, w, h
        return struct.unpack_from('<HH', b, 8)
    if t == 0x00B2D882 and b[:4] == b'DDS ':
        h, w = struct.unpack_from('<II', b, 12); return w, h
    return None

for t, name in ((0x3453CF95, 'RLE2'), (0x2BC04EDF, 'LRLE'), (0x00B2D882, 'DDS'), (0xBA856C78, 'RLES')):
    ids = [r[0] for r in db.execute('select rowid from res where t=? and comp in (0,23106)', (t,))]
    pick = random.sample(ids, min(N, len(ids)))
    c = Counter(); bad = 0
    for rid in pick:
        root, rel, off, fs, comp = db.execute('select p.root, p.rel, r.off, r.fsize, r.comp from res r join pkg p on p.id=r.pkg where r.rowid=?', (rid,)).fetchone()
        with open(os.path.join(ROOTS[root], rel.replace('/', os.sep)), 'rb') as f:
            f.seek(off); b = f.read(min(fs, 4096))
        try:
            if comp == 23106: b = zlib.decompressobj().decompress(b, 256)
            d = dims(t, b)
        except Exception: d = None
        if not d: bad += 1; continue
        c[max(d)] += 1
    tot = sum(c.values()) or 1
    top = sorted(c.items(), key=lambda kv: -kv[0])
    print(f'{name}: population {len(ids)}, sampled {len(pick)}, unreadable {bad}; max-side share: ' +
          ', '.join(f'{k}px {100*v/tot:.1f}%' for k, v in top if v/tot >= 0.005))
