"""Read-only: recompute claim 6 (unmerge loss) over all S4S manifests."""
import sys, sqlite3, collections
sys.path.insert(0, r'C:\Users\basim\Tools\sims4_speedkit\research\merging')
import s4s_manifest as m
from dbpf_read import DB, pkg_path
db = sqlite3.connect('file:%s?mode=ro' % DB, uri=True)
rows = db.execute('select p.root,p.rel from res r join pkg p on p.id=r.pkg where r.t=?', (m.MANIFEST_TYPE,)).fetchall()
cats = collections.Counter()
tot_unlisted_non_bf = 0; tot_missing = 0; retyped = 0; has_bf = 0; bf_only = 0; lossless_strict = 0
drop_non_bf_pkgs = 0; missing_pkgs = 0
for root, rel in rows:
    mf, idx, ent = m.read_manifest(pkg_path(root, rel))
    live = {(t, g, i) for t, g, i, off, fs, ms, comp in idx if comp != 0xFFE0 and t != m.MANIFEST_TYPE}
    listed = {k for _, p in mf.packages() for k in p.keys}
    missing = listed - live
    unlisted = live - listed
    bf = {k for k in unlisted if k[0] == 0x6BF15BBE}
    other = unlisted - bf
    if bf: has_bf += 1
    if not missing and not unlisted: lossless_strict += 1
    if not missing and not other: bf_only += 1
    if other: drop_non_bf_pkgs += 1
    if missing: missing_pkgs += 1
    tot_unlisted_non_bf += len(other); tot_missing += len(missing)
    mi = {(g, i) for t, g, i in missing}
    retyped += sum(1 for t, g, i in other if (g, i) in mi)
print(dict(n=len(rows), lossless_strict=lossless_strict, lossless_except_batchfix=bf_only, has_batchfix=has_bf,
           pkgs_dropping_non_bf=drop_non_bf_pkgs, pkgs_with_missing=missing_pkgs,
           unlisted_non_bf=tot_unlisted_non_bf, listed_missing=tot_missing, retyped_same_gi=retyped))
