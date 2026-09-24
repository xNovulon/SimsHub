import sqlite3
db = sqlite3.connect(r'file:C:\Users\basim\Tools\sims4_speedkit\data\library.sqlite?mode=ro', uri=True)
q = lambda s, *a: db.execute(s, a).fetchall()
T = 0x7FB6AD8A
print('manifest rows by (g,i,off,comp):', q('select g,i,off,comp,count(*) from res where t=? group by 1,2,3,4', T))
print('pkgs with manifest:', q('select count(distinct pkg), count(*) from res where t=?', T))
print('pkgs with >1 manifest:', q('select count(*) from (select pkg from res where t=? group by pkg having count(*)>1)', T))
print('manifest pkgs by root:', q('select p.root,count(*) from res r join pkg p on p.id=r.pkg where r.t=? group by 1', T))
print('total pkgs:', q('select root,count(*),sum(size),sum(n) from pkg group by root'))
print('total res:', q('select count(*) from res'))
# rows vs distinct TGIs within merged packages
print('merged pkgs rows / distinct per pkg:', q('''select sum(c), sum(d) from (select r.pkg, count(*) c, count(distinct r.t||':'||r.g||':'||r.i) d from res r
   where r.pkg in (select pkg from res where t=?) group by r.pkg)''', T))
print('err pkgs:', q('select count(*) from pkg where err is not null and err != ""'))
