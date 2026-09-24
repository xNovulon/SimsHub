import os, sqlite3, struct
BASE = r'C:\Users\basim\Documents\Electronic Arts\The Sims 4'
db = sqlite3.connect(r'C:\Users\basim\Tools\sims4_speedkit\data\library.sqlite')
print('pkgs > 2^31:', db.execute('select root, rel, size from pkg where size > 2147483648').fetchall())
print('pkgs > 2e9:', db.execute('select count(*) from pkg where size > 2000000000').fetchone())
print('total pkgs:', db.execute('select root, count(*), sum(size) from pkg group by root').fetchall())
root, rel, size = db.execute('select root, rel, size from pkg order by size desc limit 1').fetchone()
p = os.path.join(BASE, root, *rel.split('/'))
print(rel, size, os.path.getsize(p))
with open(p, 'rb') as f: h = f.read(96)
cnt, p28, isz = struct.unpack_from('<III', h, 0x24); p40 = struct.unpack_from('<Q', h, 0x40)[0]
print('entries', cnt, 'pos28', hex(p28), 'isize', isz, 'pos40(q)', hex(p40), 'idx end', p40 + isz, 'crosses 2^31:', p40 < 2**31 <= p40 + isz)
print('max(off+fsize) this pkg:', db.execute('select max(off+fsize) from res r join pkg p on p.id=r.pkg where p.root=? and p.rel=?', (root, rel)).fetchone())
print('max(off+fsize) all:', db.execute('select max(off+fsize) from res').fetchone())
