"""Read-only: independent re-run of claim 2 stats (round-trip every manifest)."""
import sys, zlib, time, collections
sys.path.insert(0, r'C:\Users\basim\Tools\sims4_speedkit\research\merging')
import s4s_manifest as m
from resolve import db, path
t0 = time.time()
c = db()
rows = c.execute('select p.root,p.rel,p.size,r.off,r.fsize,r.msize,r.comp from res r join pkg p on p.id=r.pkg where r.t=?', (m.MANIFEST_TYPE,)).fetchall()
ok = bad = missing = 0; st = collections.Counter(); maxsrc = 0; vers = collections.Counter(); multi = 0; rootnames = collections.Counter()
for root, rel, size, off, fs, ms, comp in rows:
    p = path(root, rel, size)
    if not p: missing += 1; continue
    with open(p, 'rb') as f:
        f.seek(off); raw = f.read(fs)
    data = zlib.decompress(raw)
    assert len(data) == ms
    mf = m.parse(data)
    ok += m.build(mf) == data; bad += m.build(mf) != data
    pk = mf.packages()
    vers[mf.version] += 1; rootnames[mf.root.name] += 1
    st['folders'] += len(mf.root.folders); st['sources'] += len(pk); st['keys'] += sum(len(x.keys) for _, x in pk)
    maxsrc = max(maxsrc, len(pk))
    cnt = collections.Counter(k for _, x in pk for k in x.keys)
    st['keys_in_gt1_source'] += sum(1 for k, v in cnt.items() if v > 1)
    st['key_listings_beyond_first'] += sum(v - 1 for v in cnt.values() if v > 1)
print('ok', ok, 'bad', bad, 'missing files', missing, dict(st), 'max sources', maxsrc, 'versions', dict(vers), 'root names', dict(rootnames), '%.1fs' % (time.time() - t0))
