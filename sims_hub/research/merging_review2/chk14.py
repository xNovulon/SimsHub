import sqlite3
g = sqlite3.connect(r'file:C:\Users\basim\Tools\sims4_speedkit\research\usedcc\game_keys.sqlite?mode=ro', uri=True)
print('rows, pkgs, min i, max i', g.execute('select count(*), count(distinct pkg), min(i), max(i) from k').fetchone())
print('distinct tgi', g.execute('select count(*) from (select distinct t,g,i from k)').fetchone())
g.execute(r"attach 'file:C:/Users/basim/Tools/sims4_speedkit/data/library.sqlite?mode=ro' as L")
print('mod rows overriding EA, pkgs', g.execute('select count(*), count(distinct r.pkg) from L.res r where r.comp != 65504 and exists (select 1 from k where k.t=r.t and k.g=r.g and k.i=r.i)').fetchone())
