"""Which mod resources override EA's own resources (same type/group/instance as a game package)?
Those are default replacements / tuning overrides: load-order sensitive, never safe to dedup
against each other blindly. Read-only on the game folder. Writes ea_overrides.json here."""
import os, sys, json, sqlite3, collections, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'tools'))
from scan_library import read_index
from dbpf_read import DB, u64

def ea_keys(root=r'E:\The Sims 4'):
    keys = set()
    for dp, dn, fn in os.walk(root):
        for f in fn:
            if f.lower().endswith('.package'):
                try:
                    for t, g, i, *_ in read_index(os.path.join(dp, f)):
                        keys.add((t << 96) | (g << 64) | i)
                except Exception:
                    pass
    return keys

t0 = time.time()
ea = ea_keys()
print('EA keys', len(ea), '%.0fs' % (time.time() - t0))
db = sqlite3.connect(DB)
by_type = collections.Counter(); by_pkg = collections.Counter(); n = 0
pk = {pid: (r + '/' + rel) for pid, r, rel in db.execute('select id, root, rel from pkg')}
for pid, t, g, i in db.execute('select pkg, t, g, i from res where comp != 65504'):
    if (t << 96) | (g << 64) | u64(i) in ea:
        n += 1; by_type['%08X' % t] += 1; by_pkg[pk[pid]] += 1
out = {'ea_keys': len(ea), 'mod_resources_overriding_ea': n, 'by_type': dict(by_type.most_common()),
       'packages': dict(by_pkg.most_common())}
json.dump(out, open(os.path.join(HERE, 'ea_overrides.json'), 'w', encoding='utf-8'), indent=1)
print(n, 'overrides in', len(by_pkg), 'packages; top types', by_type.most_common(10), '%.0fs' % (time.time() - t0))
