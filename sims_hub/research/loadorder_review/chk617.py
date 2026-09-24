import os, sqlite3
root = r'C:\Users\basim\Documents\Electronic Arts\The Sims 4\Mods_parked'
db = sqlite3.connect(r'C:\Users\basim\Tools\sims4_speedkit\data\library.sqlite')
have = {r for (r,) in db.execute("select rel from pkg where root='Mods_parked'")}
found = []
for dp, dn, fn in os.walk(root):
    for f in fn:
        if f.lower().endswith('.package'):
            found.append(os.path.relpath(os.path.join(dp, f), root).replace(os.sep, '/'))
print(len(found), [f for f in found if f not in have], [h for h in have if h not in found][:5])
