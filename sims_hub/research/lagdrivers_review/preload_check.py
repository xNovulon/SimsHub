"""Read-only: what resource types are in EA's SimulationPreload packages, and is CASP data contiguous there?"""
import os, sys
sys.path.insert(0, r'C:\Users\basim\Tools\sims4_speedkit\tools')
from scan_library import read_index
from collections import Counter
for dp, dn, fn in os.walk(r'E:\The Sims 4'):
    for f in fn:
        if 'preload' in f.lower():
            p = os.path.join(dp, f); r = read_index(p)
            c = Counter(t for t, *_ in r)
            casp = sorted(o for t, g, i, o, fs, ms, cp in r if t == 0x034AEECB)
            span = (casp[-1] - casp[0]) / 1e6 if casp else 0
            csize = sum(fs for t, g, i, o, fs, ms, cp in r if t == 0x034AEECB) / 1e6
            print(os.path.relpath(p, r'E:\The Sims 4'), round(os.path.getsize(p)/1e6), 'MB', len(r), 'entries', [(f'{t:08X}', n) for t, n in c.most_common(6)], f'CASP bytes {csize:.0f} MB spread over {span:.0f} MB')
