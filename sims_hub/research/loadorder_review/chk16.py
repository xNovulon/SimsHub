import sqlite3, collections
db = sqlite3.connect(r'C:\Users\basim\Tools\sims4_speedkit\data\library.sqlite')
nsw = db.execute("select id, rel from pkg where root='Mods_parked' and rel like '%NORTHERN SIBERIA%'").fetchall()
print(len(nsw))
keysets = {}
for pid, rel in nsw:
    ks = db.execute('select t, g, i, msize from res where pkg=? and comp != 65504', (pid,)).fetchall()
    keysets[rel] = ks
tset = collections.Counter()
for rel, ks in keysets.items():
    tset[tuple(sorted(set((hex(t), g, i) for t, g, i, _ in ks)))] += 1
for k, v in tset.items(): print(v, 'pkgs share key set', k)
for rel, ks in list(keysets.items())[:3]: print(rel, [(hex(t), m) for t, g, i, m in ks])
# duplicated keys in Mods_parked: how many differ in msize (true content-size difference) vs only fsize
q = '''select r.t, r.g, r.i, count(distinct r.pkg), count(distinct r.msize), count(distinct r.fsize), count(distinct r.fsize||'/'||r.msize)
       from res r join pkg p on p.id=r.pkg where p.root='Mods_parked' and r.comp != 65504
       group by r.t, r.g, r.i having count(distinct r.pkg) > 1'''
n = dm = df = dpair = 0; bytype = collections.Counter()
for t, g, i, np_, nm, nf, npair in db.execute(q):
    n += 1
    if npair > 1: dpair += 1; bytype[hex(t)] += 1
    if nm > 1: dm += 1
print('dup keys', n, 'differ (fsize,msize)', dpair, 'differ msize', dm)
print(bytype.most_common(12))
