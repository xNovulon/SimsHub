"""Read-only: for a few packages judged 'tuning' by companions.py, list 64-bit ids referenced in
their XML tuning (<T>id</T> values) that exist neither in EA's key set nor anywhere in the mod library."""
import sys, sqlite3, re, json
sys.path.insert(0, r'C:\Users\basim\Tools\sims4_speedkit\research\merging')
from dbpf_read import DB, pkg_path, u64
import s4s_manifest as m
import zlib
lib = sqlite3.connect('file:%s?mode=ro' % DB, uri=True)
ea = sqlite3.connect(r'file:C:\Users\basim\Tools\sims4_speedkit\research\usedcc\game_keys.sqlite?mode=ro', uri=True)
modi = {u64(i) for (i,) in lib.execute('select distinct i from res')}
eai = set()
for (i,) in ea.execute('select distinct i from k'):
    eai.add(u64(i))
NUM = re.compile(rb'>(\d{6,20})<')
d = json.load(open(r'C:\Users\basim\Tools\sims4_speedkit\research\merging\companions.json'))
pat = re.compile(sys.argv[1])
for p in d['packages']:
    if p['verdict'] != 'tuning' or not pat.search(p['package']):
        continue
    root, rel = p['package'].split('/', 1)
    path = pkg_path(root, rel)
    refs = set(); own = set()
    with open(path, 'rb') as f:
        for t, g, i, off, fs, ms, comp in m.read_index(path):
            own.add(i)
            f.seek(off); raw = f.read(fs)
            try:
                data = zlib.decompress(raw) if comp == 0x5A42 else raw
            except Exception:
                continue
            if data[:5] == b'<?xml' or data.lstrip()[:2] in (b'<I', b'<M'):
                refs.update(int(x) for x in NUM.findall(data) if int(x) < 2**64)
    refs -= own
    big = {r for r in refs if r > 2**32}
    missing = sorted(r for r in big if r not in eai and r not in modi)
    print('%-80s refs>2^32=%d missing_everywhere=%d %s' % (rel[-80:], len(big), len(missing), [hex(x) for x in missing[:4]]))
