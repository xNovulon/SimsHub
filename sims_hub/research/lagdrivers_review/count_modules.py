"""Read-only: count Python modules in every .ts4script (from library.sqlite script table) and the game's zips."""
import sqlite3, zipfile, os
ROOTS = {'Mods': r'C:\Users\basim\Documents\Electronic Arts\The Sims 4\Mods',
         'Mods_parked': r'C:\Users\basim\Documents\Electronic Arts\The Sims 4\Mods_parked'}
db = sqlite3.connect(r'C:\Users\basim\Tools\sims4_speedkit\data\library.sqlite')
tot = 0; totb = 0; rows = []; nsrc = 0; depths = {}
for root, rel, size, mt in db.execute('select * from script'):
    p = os.path.join(ROOTS[root], rel.replace('/', os.sep))
    depths[rel.count('/')] = depths.get(rel.count('/'), 0) + 1
    try: z = zipfile.ZipFile(p)
    except Exception as e: print('BAD', rel, e); continue
    pyc = [i for i in z.infolist() if i.filename.endswith('.pyc')]
    py = [i for i in z.infolist() if i.filename.endswith('.py')]
    nsrc += len(py)
    b = sum(i.file_size for i in pyc); tot += len(pyc); totb += b
    rows.append((len(pyc), b, root, rel, len(py)))
rows.sort(reverse=True)
print('script files', len(rows), 'pyc modules', tot, 'bytes', round(totb/1e6, 1), 'MB; .py sources', nsrc, 'depth(slashes in rel):', depths)
for r in rows[:8]: print('  ', r[0], round(r[1]/1e6, 2), 'MB', r[2], r[3], 'py:', r[4])
gz = r'E:\The Sims 4\Data\Simulation\Gameplay'
gt = 0; gb = 0
for n in ('base.zip', 'core.zip', 'simulation.zip'):
    z = zipfile.ZipFile(os.path.join(gz, n)); pyc = [i for i in z.infolist() if i.filename.endswith('.pyc')]
    gt += len(pyc); gb += sum(i.file_size for i in pyc); print(n, len(pyc), round(sum(i.file_size for i in pyc)/1e6, 1), 'MB')
print('game total', gt, round(gb/1e6, 1), 'MB')
