import sys, zlib
sys.path.insert(0, r'C:\Users\basim\Tools\sims4_speedkit\research\merging')
from dbpf_read import decompress
from resolve import db, path
c = db()
for t in (0x6BF15BBE, 0x73E93EEB):
    rows = c.execute('select p.root,p.rel,p.size,r.g,r.i,r.off,r.fsize,r.msize,r.comp from res r join pkg p on p.id=r.pkg where r.t=?', (t,)).fetchall()
    print('%08X: %d copies in %d pkgs' % (t, len(rows), len({r[1] for r in rows})))
    shown = 0
    for root, rel, size, g, i, off, fs, ms, comp in rows:
        if rel.endswith('sim/16.package') or shown < 2:
            with open(path(root, rel, size), 'rb') as f:
                f.seek(off); d = decompress(f.read(fs), comp, ms)
            print('  ', rel, '%08X %016X' % (g, i & (2**64-1)), repr(d[:160]))
            shown += 1
    if t == 0x73E93EEB:
        heads = {}
        for root, rel, size, g, i, off, fs, ms, comp in rows:
            with open(path(root, rel, size), 'rb') as f:
                f.seek(off); d = decompress(f.read(fs), comp, ms)
            heads[d[:40]] = heads.get(d[:40], 0) + 1
        print('  distinct heads', heads)
