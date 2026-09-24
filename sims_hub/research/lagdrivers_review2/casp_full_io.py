"""Read-only: read every CASP in the library (walk-based paths via DB rel, skipping missing) with
(a) 8 threads, unbuffered os.read after lseek, and (b) single-thread mmap. Reports wall time."""
import os, sys, time, sqlite3, mmap, zlib
from concurrent.futures import ThreadPoolExecutor
S = r'C:\Users\basim\Documents\Electronic Arts\The Sims 4'
db = sqlite3.connect(r'C:\Users\basim\Tools\sims4_speedkit\data\library.sqlite')
T = 0x034AEECB
jobs = []
for pid, root, rel in db.execute('select id, root, rel from pkg order by id').fetchall():
    p = os.path.join(S, root, rel.replace('/', os.sep))
    if not os.path.exists(p):
        alt = os.path.join(S, 'Mods_parked', rel.replace('/', os.sep))
        if os.path.exists(alt): p = alt
        else: continue
    rows = db.execute('select off, fsize, comp from res where pkg=? and t=? and comp!=65504 order by off', (pid, T)).fetchall()
    if rows: jobs.append((p, rows))
N = sum(len(r) for _, r in jobs)
def work(job, inflate):
    p, rows = job; b = 0
    fd = os.open(p, os.O_RDONLY | os.O_BINARY)
    try:
        for off, fs, comp in rows:
            os.lseek(fd, off, 0); d = os.read(fd, fs); b += len(d)
            if inflate and comp == 0x5A42: zlib.decompress(d)
    finally: os.close(fd)
    return b
mode = sys.argv[1]
t0 = time.perf_counter()
if mode == 'threads':
    with ThreadPoolExecutor(8) as ex: tot = sum(ex.map(lambda j: work(j, True), jobs))
elif mode == 'single':
    tot = sum(work(j, True) for j in jobs)
elif mode == 'mmap':
    tot = 0
    for p, rows in jobs:
        with open(p, 'rb') as f:
            m = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            for off, fs, comp in rows:
                d = m[off:off+fs]; tot += len(d)
                if comp == 0x5A42: zlib.decompress(d)
            m.close()
print(f'{mode}: {len(jobs)} pkgs, {N} CASPs, {tot/1e6:.0f} MB read+inflate, wall {time.perf_counter()-t0:.1f}s')
