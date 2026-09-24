"""scan_scripts.py: for every .ts4script in Mods and Mods_parked (read-only): entries, top-level packages,
.py vs .pyc, pyc magic, sample co_filename values, and profiling-relevant API usage."""
import sys, os, zipfile, sqlite3, collections, re
sys.path.insert(0, r'C:\Users\basim\Tools\sims4_speedkit\tools')
from pyc37 import load, walk, Code
ROOT = r'C:\Users\basim\Documents\Electronic Arts\The Sims 4'
db = sqlite3.connect(r'file:C:\Users\basim\Tools\sims4_speedkit\data\library.sqlite?mode=ro', uri=True)
API = re.compile(r'^(threading|_thread|setprofile|settrace|_current_frames|start_new_thread|cProfile|perf_counter|add_alarm|add_alarm_real_time|register|process_event|Zone|update|inject|wraps|c_api_server_tick|on_tick)$')
toplevel_owner = collections.defaultdict(set)
for root, rel, size in db.execute('select root, rel, size from script order by root, rel'):
    p = os.path.join(ROOT, root, rel.replace('/', os.sep))
    z = zipfile.ZipFile(p)
    names = [n for n in z.namelist() if not n.endswith('/')]
    pyc = [n for n in names if n.endswith('.pyc')]
    py = [n for n in names if n.endswith('.py')]
    tops = sorted({n.split('/')[0].rsplit('.', 1)[0] if '/' not in n else n.split('/')[0] for n in pyc + py})
    for t in tops: toplevel_owner[t].add(rel.split('/')[-1])
    magics = collections.Counter(z.read(n)[:4].hex() for n in pyc)
    fnames = collections.Counter(); apis = collections.Counter()
    for n in pyc:
        try:
            c = load(z.read(n))
        except Exception as e:
            fnames['<unmarshal error %s>' % type(e).__name__] += 1; continue
        fnames[c.co_filename] += 1
        for k in walk(c):
            for s in k.co_names:
                if API.match(s): apis[s] += 1
    print('=' * 100)
    print('%s/%s  size=%d  files=%d pyc=%d py=%d other=%d' % (root, rel, size, len(names), len(pyc), len(py), len(names) - len(pyc) - len(py)))
    print('  top-level:', tops[:12], '...' if len(tops) > 12 else '')
    print('  magic:', dict(magics))
    print('  py files:', py[:10])
    fl = list(fnames.items())
    print('  co_filename samples (%d distinct):' % len(fl))
    for f, cnt in fl[:4]:
        print('     ', repr(f))
    print('  api names:', dict(apis))
print('=' * 100)
dup = {k: v for k, v in toplevel_owner.items() if len(v) > 1}
print('top-level names shared by >1 ts4script:', dup)
