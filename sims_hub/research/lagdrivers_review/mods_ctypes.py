import zipfile, os, sqlite3
ROOTS = {'Mods': r'C:\Users\basim\Documents\Electronic Arts\The Sims 4\Mods', 'Mods_parked': r'C:\Users\basim\Documents\Electronic Arts\The Sims 4\Mods_parked'}
db = sqlite3.connect(r'C:\Users\basim\Tools\sims4_speedkit\data\library.sqlite')
for root, rel, s, m in db.execute('select * from script'):
    z = zipfile.ZipFile(os.path.join(ROOTS[root], rel.replace('/', os.sep)))
    hits = [n for n in z.namelist() if 'ctypes' in n.lower()]
    refs = 0
    for n in z.namelist():
        if n.endswith('.pyc') and (b'ctypes' in z.read(n) or b'_ctypes' in z.read(n)): refs += 1
    if hits or refs: print(rel, hits[:3], 'modules referencing ctypes:', refs)
