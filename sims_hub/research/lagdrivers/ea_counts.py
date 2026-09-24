"""Count resources in the game's own packages (index only, read-only) for comparison with the CC library."""
import os, sys, time
sys.path.insert(0, r'C:\Users\basim\Tools\sims4_speedkit\tools')
from scan_library import read_index
from collections import Counter
root = r'E:\The Sims 4'
t0 = time.perf_counter(); c = Counter(); size = 0; npk = 0; nres = 0; casp_bytes = 0
casp_keys = set()
for dp, dn, fn in os.walk(root):
    for f in fn:
        if f.lower().endswith('.package'):
            p = os.path.join(dp, f)
            try: r = read_index(p)
            except Exception as e: continue
            npk += 1; size += os.path.getsize(p); nres += len(r)
            for t, g, i, o, fs, ms, cp in r:
                c[t] += 1
                if t == 0x034AEECB: casp_keys.add(i); casp_bytes += ms
print(f'{npk} EA packages, {size/1e9:.1f} GB, {nres} index entries, scanned in {time.perf_counter()-t0:.1f}s')
for t, name in [(0x034AEECB,'CASP'),(0x3C1AF1F2,'CAS thumb'),(0x015A1849,'GEOM'),(0x3453CF95,'RLE2'),(0x2BC04EDF,'LRLE'),(0x00B2D882,'DDS'),(0x319E4F1D,'COBJ'),(0xC0DB5AE7,'OBJD')]:
    print(f'{name:10s} {c[t]:9d}')
print('unique CASP instances', len(casp_keys), 'CASP uncompressed MB', round(casp_bytes/1e6))
