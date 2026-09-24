"""Read-only: same subset, compare buffered f.seek/read vs unbuffered os.pread-like vs mmap."""
import sqlite3, time, os, mmap
ROOTS = {'Mods': r'C:\Users\basim\Documents\Electronic Arts\The Sims 4\Mods',
         'Mods_parked': r'C:\Users\basim\Documents\Electronic Arts\The Sims 4\Mods_parked'}
db = sqlite3.connect(r'C:\Users\basim\Tools\sims4_speedkit\data\library.sqlite')
pk = db.execute("select p.id,p.root,p.rel,count(*) c from res r join pkg p on p.id=r.pkg where r.t=? group by p.id order by c desc limit 8 offset 40", (0x034AEECB,)).fetchall()
rows = {pid: db.execute('select off,fsize from res where pkg=? and t=? order by off', (pid, 0x034AEECB)).fetchall() for pid,_,_,_ in pk}
def run_unbuf():
    n=0; s=time.perf_counter()
    for pid, root, rel, c in pk:
        with open(os.path.join(ROOTS[root], rel.replace('/', os.sep)), 'rb', buffering=0) as f:
            for off, fs in rows[pid]: f.seek(off); f.read(fs); n+=1
    return n, time.perf_counter()-s
def run_mmap():
    n=0; s=time.perf_counter()
    for pid, root, rel, c in pk:
        with open(os.path.join(ROOTS[root], rel.replace('/', os.sep)), 'rb') as f:
            m = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            for off, fs in rows[pid]: bytes(m[off:off+fs]); n+=1
            m.close()
    return n, time.perf_counter()-s
for fn in (run_unbuf, run_unbuf, run_mmap, run_mmap):
    n, t = fn(); print(fn.__name__, n, f'{t:.2f}s {1e6*t/n:.0f} us/read')
