import os, struct, time
S = r'C:\Users\basim\Documents\Electronic Arts\The Sims 4'
paths = []
for r in ('Mods', 'Mods_parked'):
    for dp, dn, fn in os.walk(os.path.join(S, r)):
        dn[:] = [d for d in dn if d != '_old_caches']
        paths += [os.path.join(dp, f) for f in fn if f.lower().endswith('.package')]
for run in (1, 2):
    t0 = time.perf_counter(); b = 0; n = 0
    for p in paths:
        with open(p, 'rb', buffering=0) as f:
            h = f.read(96); cnt, isz, ipos = struct.unpack_from('<I', h, 36)[0], struct.unpack_from('<I', h, 44)[0], struct.unpack_from('<I', h, 64)[0]
            f.seek(ipos); b += len(f.read(isz)); n += cnt
    print(f'raw run{run}: {len(paths)} pkgs {n} entries {b/1e6:.1f} MB {time.perf_counter()-t0:.2f}s')
