"""For a random CASP sample, look closer at referenced keys that resolve neither in the library nor in the game."""
import collections, os, random, sqlite3, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import usedcc as U

db = U.lib()
g = sqlite3.connect(U.GAMEDB)
paths = U.pkg_paths(db)
rows = db.execute('select pkg, i, off, fsize, comp from res where t=? and comp != 65535', (U.T_CASP,)).fetchall()
random.seed(int(sys.argv[1]) if len(sys.argv) > 1 else 7)
sample = sorted(random.sample(rows, 3000), key=lambda r: (r[0], r[2]))
rd = U.PkgReader()
why = collections.Counter()
examples = collections.defaultdict(list)
for pkg, i, off, fs, comp in sample:
    refs = U.casp_refs(rd.read(paths[pkg], off, fs, comp))
    for t, gg, ii in refs:
        if t == 0 and ii == 0:
            continue
        si = U.s64(ii)
        if db.execute('select 1 from res where t=? and g=? and i=?', (t, gg, si)).fetchone():
            continue
        if g.execute('select 1 from k where t=? and g=? and i=?', (t, gg, si)).fetchone():
            continue
        lt = db.execute('select g from res where t=? and i=? limit 1', (t, si)).fetchone()
        gt = g.execute('select g from k where t=? and i=? limit 1', (t, si)).fetchone()
        la = db.execute('select t from res where i=? limit 1', (si,)).fetchone() if not lt else None
        ga = g.execute('select t from k where i=? limit 1', (si,)).fetchone() if not gt else None
        if lt:
            k = 'same t+i in library, other group (%08X vs %08X)' % (lt[0], gg)
            kk = 'lib_other_group'
        elif gt:
            k = 'game_other_group'; kk = k
        elif la or ga:
            kk = 'instance exists as other type'
        else:
            kk = 'instance nowhere'
        why[(U.tname(t), kk)] += 1
        if len(examples[(U.tname(t), kk)]) < 3:
            examples[(U.tname(t), kk)].append((os.path.basename(paths[pkg]), U.U64hex(i), '%08X:%08X:%016X' % (t, gg, ii), lt, gt, la, ga))
for k, v in sorted(why.items()):
    print(k, v, examples[k][:2])
print('casps', len(sample), 'casps with any missing ref:')
