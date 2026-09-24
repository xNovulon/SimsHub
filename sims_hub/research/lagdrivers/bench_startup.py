"""Read-only lower-bound benchmark of the per-launch work that scales with a CC library.
Phase 1: read DBPF header + index table of every package (what any resource manager must do).
Phase 2: read + zlib-decompress every CAS part (CASP 0x034AEECB) - the game builds its CAS catalog from these.
Phase 3 (optional): same for CAS thumbnails 0x3C1AF1F2 (read only, no decode).
Never writes anything under the Sims 4 folders.
usage: python bench_startup.py [--root Mods|Mods_parked|all] [--limit-pkgs N] [--thumbs]
"""
import sqlite3, time, zlib, struct, os, sys, argparse

ROOTS = {'Mods': r'C:\Users\basim\Documents\Electronic Arts\The Sims 4\Mods',
         'Mods_parked': r'C:\Users\basim\Documents\Electronic Arts\The Sims 4\Mods_parked'}
ap = argparse.ArgumentParser()
ap.add_argument('--root', default='all'); ap.add_argument('--limit-pkgs', type=int, default=0)
ap.add_argument('--thumbs', action='store_true')
a = ap.parse_args()
db = sqlite3.connect(r'C:\Users\basim\Tools\sims4_speedkit\data\library.sqlite')
q = 'select id, root, rel from pkg where err is null' + ('' if a.root == 'all' else f" and root='{a.root}'") + ' order by id'
pkgs = db.execute(q).fetchall()
if a.limit_pkgs: pkgs = pkgs[:a.limit_pkgs]

t0 = time.perf_counter(); idx_bytes = 0; n_entries = 0
for pid, root, rel in pkgs:
    with open(os.path.join(ROOTS[root], rel.replace('/', os.sep)), 'rb') as f:
        h = f.read(96)
        cnt, isz, ipos = struct.unpack_from('<I', h, 36)[0], struct.unpack_from('<I', h, 44)[0], struct.unpack_from('<I', h, 64)[0]
        f.seek(ipos); idx_bytes += len(f.read(isz)); n_entries += cnt
t1 = time.perf_counter()
print(f'phase1 index: {len(pkgs)} pkgs, {n_entries} entries, {idx_bytes/1e6:.1f} MB index read in {t1-t0:.2f}s')

def phase(t, decode):
    tot_r = tot_m = n = 0; start = time.perf_counter(); t_io = t_dec = 0.0
    for pid, root, rel in pkgs:
        rows = db.execute('select off, fsize, msize, comp from res where pkg=? and t=? and comp!=65504 order by off', (pid, t)).fetchall()
        if not rows: continue
        with open(os.path.join(ROOTS[root], rel.replace('/', os.sep)), 'rb') as f:
            for off, fs, ms, comp in rows:
                s = time.perf_counter(); f.seek(off); b = f.read(fs); e = time.perf_counter(); t_io += e - s
                if decode and comp == 0x5A42:
                    b = zlib.decompress(b); t_dec += time.perf_counter() - e
                tot_r += fs; tot_m += len(b); n += 1
    el = time.perf_counter() - start
    return n, tot_r, tot_m, el, t_io, t_dec

n, r, m, el, tio, tdec = phase(0x034AEECB, True)
print(f'phase2 CASP: {n} parts, read {r/1e6:.0f} MB, inflated {m/1e6:.0f} MB, wall {el:.1f}s (io {tio:.1f}s, zlib {tdec:.1f}s)')
if a.thumbs:
    n, r, m, el, tio, tdec = phase(0x3C1AF1F2, False)
    print(f'phase3 CAS thumbs: {n}, read {r/1e6:.0f} MB, wall {el:.1f}s (io {tio:.1f}s)')
