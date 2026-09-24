"""Read-only: walk Mods + Mods_parked (skip _old_caches), read+parse every package index, insert keys in a dict. Twice."""
import os, sys, time
sys.path.insert(0, r'C:\Users\basim\Tools\sims4_speedkit\tools')
from scan_library import read_index
S = r'C:\Users\basim\Documents\Electronic Arts\The Sims 4'
paths = []
for r in ('Mods', 'Mods_parked'):
    for dp, dn, fn in os.walk(os.path.join(S, r)):
        dn[:] = [d for d in dn if d != '_old_caches']
        paths += [os.path.join(dp, f) for f in fn if f.lower().endswith('.package')]
for run in (1, 2):
    t0 = time.perf_counter(); d = {}; n = 0; sz = 0
    for p in paths:
        e = read_index(p); n += len(e); sz += os.path.getsize(p)
        for t, g, i, *_ in e: d[(t, g, i)] = p
    print(f'run{run}: {len(paths)} pkgs {sz/1e9:.1f} GB, {n} entries, {len(d)} unique TGI, read+parse+dict {time.perf_counter()-t0:.2f}s')
