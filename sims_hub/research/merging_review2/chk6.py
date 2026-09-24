"""Read-only: recompute claim 6 (S4S unmerge loss) over all S4S manifests, using current file locations."""
import sys, collections, json
sys.path.insert(0, r'C:\Users\basim\Tools\sims4_speedkit\research\merging')
import s4s_manifest as m
from resolve import db, path
c = db()
rows = c.execute('select p.root,p.rel,p.size from res r join pkg p on p.id=r.pkg where r.t=?', (m.MANIFEST_TYPE,)).fetchall()
S = collections.Counter(); unl_types = collections.Counter(); retype_pairs = collections.Counter()
for root, rel, size in rows:
    mf, idx, ent = m.read_manifest(path(root, rel, size))
    live = {(t, g, i) for t, g, i, off, fs, ms, comp in idx if comp != 0xFFE0 and t != m.MANIFEST_TYPE}
    listed = {k for _, p in mf.packages() for k in p.keys}
    missing = listed - live; unlisted = live - listed
    bf = {k for k in unlisted if k[0] == 0x6BF15BBE}; other = unlisted - bf
    S['n'] += 1
    S['has_bf'] += bool(bf); S['bf_res'] += len(bf)
    S['lossless_strict'] += (not missing and not unlisted)
    S['no_nonbf_drop'] += (not other)
    S['no_nonbf_drop_and_no_missing'] += (not other and not missing)
    S['pkgs_drop_nonbf'] += bool(other); S['pkgs_missing'] += bool(missing)
    S['unlisted_nonbf'] += len(other); S['listed_missing'] += len(missing)
    mi = collections.defaultdict(set)
    for t, g, i in missing: mi[(g, i)].add(t)
    for t, g, i in other:
        unl_types['%08X' % t] += 1
        if (g, i) in mi:
            S['retyped'] += 1
            for mt in mi[(g, i)]: retype_pairs['%08X->%08X' % (mt, t)] += 1
print(json.dumps(S, indent=0)); print('unlisted non-bf types', unl_types.most_common(12)); print('retype pairs', retype_pairs.most_common(8))
