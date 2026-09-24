import sqlite3, sys
sys.path.insert(0, r'C:\Users\basim\Tools\sims4_speedkit\research\merging')
import s4s_manifest as m
from resolve import path
c = sqlite3.connect(r'file:C:\Users\basim\Tools\sims4_speedkit\data\library.sqlite?mode=ro', uri=True)
def pid(like):
    r = c.execute('select id, root, rel, size from pkg where rel like ?', (like,)).fetchall(); assert len(r) == 1, r; return r[0]
for merged, live, src in [('sim/m27.package', '%TURBODRIVER_WickedWhims_Tuning.package', 'TURBODRIVER_WickedWhims_Tuning'),
                          ('sim/m9.package', '%lot51_plumbbros.package', 'lot51_plumbbros')]:
    a = pid(merged); b = pid(live)
    A = {(t, g, i): (ms, fs, comp) for t, g, i, ms, fs, comp in c.execute('select t,g,i,msize,fsize,comp from res where pkg=? and comp!=65504', (a[0],))}
    B = {(t, g, i): (ms, fs, comp) for t, g, i, ms, fs, comp in c.execute('select t,g,i,msize,fsize,comp from res where pkg=? and comp!=65504', (b[0],))}
    common = A.keys() & B.keys()
    diffm = sum(1 for k in common if A[k][0] != B[k][0])
    diffany = sum(1 for k in common if A[k][:2] != B[k][:2])
    mf, idx, ent = m.read_manifest(path(a[1], a[2], a[3]))
    srcs = [(p, pk) for p, pk in mf.packages() if src.lower() in pk.name.lower()]
    print(merged, 'vs', b[2], ': live keys', len(B), 'merged keys', len(A), 'common', len(common), 'msize differs', diffm, '(msize or fsize differs', diffany, ')')
    for p, pk in srcs:
        ks = {(t, g, i if i < 2**63 else i - 2**64) for t, g, i in pk.keys}
        print('   manifest source %r: %d keys, %d in live pkg' % (pk.name, len(pk.keys), len(ks & B.keys())))
