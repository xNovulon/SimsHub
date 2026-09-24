"""Where do the referenced-but-unknown CAS part ids come from, and which skin-tone paths hit library TONEs?"""
import sqlite3, collections, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import usedcc as U
ids = sqlite3.connect(os.path.join(U.HERE, 'ids.sqlite')); db = U.libti(); g = sqlite3.connect(U.GAMEDB)
lib_casp = set(U.u64(i) for (i,) in db.execute('select distinct i from res where t=?', (U.T_CASP,)))
game_casp = set(U.u64(i) for (i,) in g.execute('select distinct i from k where t=?', (U.T_CASP,)))
srcs = {sid: (f, k) for sid, f, k in ids.execute('select id, file, kind from src')}
parts = collections.defaultdict(set)
for sid, v in ids.execute("select src, v from typed where cat in ('outfit_part','genetic_part')"):
    parts[U.u64(v)].add(sid)
unk = [v for v in parts if v not in lib_casp and v not in game_casp]
print('unknown', len(unk), 'small(<2^32)', sum(1 for v in unk if v < 2**32), 'zero', sum(1 for v in unk if v == 0))
kinds = collections.Counter()
cur = 0
for v in unk:
    ks = set(srcs[s][1] for s in parts[v])
    kinds['+'.join(sorted(ks))] += 1
    if any(srcs[s][1] == 'tray' or ('.ver' not in srcs[s][0] and srcs[s][0].endswith('.save')) for s in parts[v]):
        cur += 1
print('unknown by source kind', dict(kinds), 'in current slots/tray', cur)
big = [v for v in unk if v >= 2**32]
anyl = sum(1 for v in big if db.execute('select 1 from res where i=? limit 1', (U.s64(v),)).fetchone())
anyg = sum(1 for v in big if g.execute('select 1 from k where i=? limit 1', (U.s64(v),)).fetchone())
print('big unknown', len(big), 'exist as some other type in library', anyl, 'in game', anyg)
small = sorted(v for v in unk if v < 2**32)
print('small unknown sample', [hex(v) for v in small[:12]], '...', [hex(v) for v in small[-5:]])
anysm = sum(1 for v in small if g.execute('select 1 from k where i=? limit 1', (U.s64(v),)).fetchone())
print('small unknown that exist as some type in game', anysm)
tone = set(U.u64(i) for (i,) in db.execute('select distinct i from res where t=?', (U.T_TONE,)))
gt = set(U.u64(i) for (i,) in g.execute('select distinct i from k where t=?', (U.T_TONE,)))
pc = collections.Counter()
for v, path in ids.execute('select v, path from hit'):
    if U.u64(v) in tone and (path.endswith('.10') or path.endswith('.13')):
        pc[path] += 1
print('TONE hits by path', pc.most_common(12))
exact = set(U.u64(v) for v, path in ids.execute("select v, path from hit where path in ('RD.6.10','RD.15.13','hh.1.6.10','hh.1.15.13')") if U.u64(v) in tone)
print('library TONE on exact SimData.skin_tone paths', len(exact), 'not EA ids', len(exact - gt))
