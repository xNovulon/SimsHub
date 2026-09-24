"""build_owner_map.py [out.json]: map every code object's co_filename (and (co_filename, co_name, firstlineno))
in the user's .ts4script files to the owning archive (read-only). Reports ambiguous keys.
Used to attribute external samples (which only see co_filename/co_name) to a mod."""
import sys, os, json, zipfile, sqlite3, collections
sys.path.insert(0, r'C:\Users\basim\Tools\sims4_speedkit\tools')
from pyc37 import load, walk
ROOT = r'C:\Users\basim\Documents\Electronic Arts\The Sims 4'
db = sqlite3.connect(r'file:C:\Users\basim\Tools\sims4_speedkit\data\library.sqlite?mode=ro', uri=True)
by_file = collections.defaultdict(set); by_func = collections.defaultdict(set); ncode = 0
for root, rel in db.execute('select root, rel from script'):
    owner = rel.split('/')[-1]
    z = zipfile.ZipFile(os.path.join(ROOT, root, rel.replace('/', os.sep)))
    for n in z.namelist():
        if n.endswith('.pyc'):
            for c in walk(load(z.read(n))):
                by_file[c.co_filename].add(owner); by_func['%s|%s|%d' % (c.co_filename, c.co_name, c.co_firstlineno)].add(owner); ncode += 1
        elif n.endswith('.py'):  # source compiled by zipimport gets co_filename = <archive>\<name>
            by_file[os.path.join(ROOT, root, rel.replace('/', os.sep), n.replace('/', os.sep))].add(owner)
amb_f = {k: sorted(v) for k, v in by_file.items() if len(v) > 1}
amb_fn = {k: sorted(v) for k, v in by_func.items() if len(v) > 1}
print('code objects %d, distinct co_filename %d (ambiguous %d), distinct (file,func,line) %d (ambiguous %d)' % (
    ncode, len(by_file), len(amb_f), len(by_func), len(amb_fn)))
for k, v in list(amb_f.items())[:10]:
    print('  ambiguous co_filename %r -> %s' % (k, v))
for k, v in list(amb_fn.items())[:5]:
    print('  ambiguous func %r -> %s' % (k, v))
out = {'by_file': {k: sorted(v)[0] for k, v in by_file.items() if len(v) == 1},
       'by_func': {k: sorted(v)[0] for k, v in by_func.items() if len(v) == 1},
       'game_prefixes': ['T:\\InGame\\Gameplay\\Scripts\\', 'D:\\dev\\TS4\\_deploy\\']}
if len(sys.argv) > 1:
    json.dump(out, open(sys.argv[1], 'w'))
    print('wrote', sys.argv[1])
