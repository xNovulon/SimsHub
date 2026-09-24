"""Sample the game's own RLE2/LRLE texture headers for comparison (read-only)."""
import os, sys, struct, zlib, random
sys.path.insert(0, r'C:\Users\basim\Tools\sims4_speedkit\tools')
from scan_library import read_index
from collections import Counter
random.seed(2)
pk = []
for dp, dn, fn in os.walk(r'E:\The Sims 4'):
    for f in fn:
        if f.startswith('ClientFullBuild') and f.endswith('.package'): pk.append(os.path.join(dp, f))
entries = {0x3453CF95: [], 0x2BC04EDF: []}
for p in pk:
    for t, g, i, o, fs, ms, cp in read_index(p):
        if t in entries and cp in (0, 0x5A42): entries[t].append((p, o, fs, cp))
for t, name in ((0x3453CF95, 'RLE2'), (0x2BC04EDF, 'LRLE')):
    c = Counter(); pick = random.sample(entries[t], min(3000, len(entries[t])))
    for p, o, fs, cp in pick:
        with open(p, 'rb') as f: f.seek(o); b = f.read(min(fs, 4096))
        if cp == 0x5A42: b = zlib.decompressobj().decompress(b, 256)
        w, h = struct.unpack_from('<HH', b, 8); c[max(w, h)] += 1
    tot = sum(c.values())
    print(f'EA {name}: population {len(entries[t])} in {len(pk)} ClientFullBuild pkgs; ' + ', '.join(f'{k}px {100*v/tot:.1f}%' for k, v in sorted(c.items(), key=lambda kv: -kv[0]) if v/tot >= 0.005))
