import zipfile, sys, os, sqlite3, re
G = r'E:\The Sims 4\Data\Simulation\Gameplay'
for n in ('base.zip', 'core.zip', 'simulation.zip'):
    z = zipfile.ZipFile(os.path.join(G, n))
    print(n, [x for x in z.namelist() if re.search(r'(^|/)paths\.py', x)])
S = r'C:\Users\basim\Documents\Electronic Arts\The Sims 4'
tot = 0; totc = 0
for dp, dn, fn in os.walk(S):
    if 'Mods' not in dp: continue
    for f in fn:
        if f.endswith('.ts4script'):
            z = zipfile.ZipFile(os.path.join(dp, f)); names = z.namelist()
            m = [x for x in names if re.match(r'.+\.py[co]$', x)]
            tot += len(m); totc += sum(z.getinfo(x).file_size for x in m)
            print(os.path.relpath(os.path.join(dp, f), S), len(m), len(names))
print('total importable .pyc/.pyo', tot, round(totc/1e6, 2), 'MB')
