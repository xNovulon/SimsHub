"""Read-only: per-read cost of CASP reads on a subset of packages, run twice (second = warm)."""
import sqlite3, time, zlib, os
ROOTS = {'Mods': r'C:\Users\basim\Documents\Electronic Arts\The Sims 4\Mods',
         'Mods_parked': r'C:\Users\basim\Documents\Electronic Arts\The Sims 4\Mods_parked'}
db = sqlite3.connect(r'C:\Users\basim\Tools\sims4_speedkit\data\library.sqlite')
pk = db.execute("select p.id,p.root,p.rel,count(*) c from res r join pkg p on p.id=r.pkg where r.t=? group by p.id order by c desc limit 8 offset 40", (0x034AEECB,)).fetchall()
rows = {pid: db.execute('select off,fsize,comp from res where pkg=? and t=? order by off', (pid, 0x034AEECB)).fetchall() for pid,_,_,_ in pk}
for run in (1, 2, 3):
    n = 0; tio = 0; tz = 0; span = 0
    for pid, root, rel, c in pk:
        r = rows[pid]
        with open(os.path.join(ROOTS[root], rel.replace('/', os.sep)), 'rb') as f:
            for off, fs, comp in r:
                s = time.perf_counter(); f.seek(off); b = f.read(fs); e = time.perf_counter(); tio += e - s
                if comp == 0x5A42: zlib.decompress(b); tz += time.perf_counter() - e
                n += 1
        span += r[-1][0] - r[0][0]
    print(f'run{run}: {n} CASP reads, io {tio:.2f}s = {1e6*tio/n:.0f} us/read, zlib {tz:.2f}s; CASP spread over {span/1e9:.1f} GB of file')
