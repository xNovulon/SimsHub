import os, sqlite3, struct, sys, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import usedcc as U

db = U.lib()
paths = U.pkg_paths(db)
want = set(int(x) for x in sys.argv[1].split(',')) if len(sys.argv) > 1 else {46, 49, 50, 51}
rows = db.execute('select pkg,i,off,fsize,comp from res where t=? limit 20000', (U.T_CASP,)).fetchall()
random.seed(2)
random.shuffle(rows)
rd = U.PkgReader()
seen = {}
for pkg, i, off, fs, comp in rows:
    d = rd.read(paths[pkg], off, fs, comp)
    v = struct.unpack_from('<I', d)[0]
    if v in want and v not in seen:
        seen[v] = 1
        toff = struct.unpack_from('<I', d, 4)[0]
        print('=== ver', v, paths[pkg][-50:], hex(U.u64(i)), 'len', len(d), 'tgi at', 8 + toff)
        h = d[:8 + toff]
        for k in range(0, len(h), 32):
            print('%04x  %s' % (k, h[k:k + 32].hex(' ')))
        refs = U.casp_refs(d)
        print([(U.tname(t), hex(g)) for t, g, ii in refs])
    if len(seen) == len(want):
        break
