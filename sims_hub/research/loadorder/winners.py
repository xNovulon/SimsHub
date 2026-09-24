"""Read-only. Reproduce TS4's package load order for a folder and decide which copy of every
duplicated resource key the game will use.

Model (see research notes):
  * The resource-config walker enumerates with FindFirstFileW/FindNextFileW (no sorting) and descends
    into a sub-folder at the moment it meets it -> on NTFS that is a depth-first walk in
    upper-cased ordinal name order (folders and files interleaved). os.scandir() uses the same API,
    so we simply walk the real folder with it.
  * Default Mods Resource.cfg: one group, Priority 500, PackedFile */.../*.package up to 5 sub-folders.
  * Same Priority -> the FIRST loaded copy of a type/group/instance key is used (Scumbumbo 2017,
    MTS t=604303 + his Conflict Detector 1.3.0).

Usage: python winners.py [Mods|Mods_parked] [--max-depth 5] [--show N]
Treats the chosen root as if it were the Mods folder.
"""
import argparse, os, sqlite3, collections

BASE = r'C:\Users\basim\Documents\Electronic Arts\The Sims 4'
DB = r'C:\Users\basim\Tools\sims4_speedkit\data\library.sqlite'


def game_order(root, max_depth):
    order = []

    def walk(path, rel, depth):
        with os.scandir(path) as it:
            for e in it:                      # FindFirstFileW order, NOT sorted
                if e.is_dir(follow_symlinks=True):
                    if depth < max_depth:
                        walk(e.path, rel + e.name + '/', depth + 1)
                elif e.name.lower().endswith('.package'):
                    order.append(rel + e.name)
    walk(root, '', 0)
    return order


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('root', nargs='?', default='Mods_parked')
    ap.add_argument('--max-depth', type=int, default=5)
    ap.add_argument('--show', type=int, default=15)
    a = ap.parse_args()
    order = game_order(os.path.join(BASE, a.root), a.max_depth)
    pos = {rel: i for i, rel in enumerate(order)}
    db = sqlite3.connect(DB)
    pk = {pid: rel for pid, rel in db.execute('select id, rel from pkg where root=?', (a.root,))}
    missing = [rel for rel in pk.values() if rel not in pos]
    print(f'{a.root}: {len(order)} packages would load; {len(missing)} indexed packages not reached '
          f'(too deep / not on disk)')
    # duplicated keys across packages of this root
    q = '''select r.t, r.g, r.i, r.pkg, r.fsize, r.msize from res r join pkg p on p.id=r.pkg
           where p.root=? and r.comp != 65504 and (r.t, r.g, r.i) in (
             select t, g, i from res r2 join pkg p2 on p2.id=r2.pkg where p2.root=? and r2.comp != 65504
             group by t, g, i having count(distinct r2.pkg) > 1)'''
    groups = collections.defaultdict(list)
    for t, g, i, pid, fs, ms in db.execute(q, (a.root, a.root)):
        groups[(t, g, i)].append((pos.get(pk[pid], 10 ** 9), pk[pid], fs, ms))
    differing = 0
    wins = collections.Counter()
    losses = collections.Counter()
    for key, copies in groups.items():
        copies.sort()
        if len({(c[2], c[3]) for c in copies}) > 1:
            differing += 1
            wins[copies[0][1]] += 1
            for c in copies[1:]:
                losses[c[1]] += 1
    print(f'duplicated keys: {len(groups)}; keys whose copies differ in size: {differing}')
    print(f'\npackages that WIN the most differing keys (first in load order):')
    for rel, n in wins.most_common(a.show):
        print(f'  #{pos.get(rel, -1):4d} {n:6d}  {rel}')
    print(f'\npackages that LOSE the most differing keys (shadowed by an earlier package):')
    for rel, n in losses.most_common(a.show):
        print(f'  #{pos.get(rel, -1):4d} {n:6d}  {rel}')
    # lighting-mod example
    nsw = [r for r in order if 'Better In-Game Lighting' in r]
    if nsw:
        print(f'\n{len(nsw)} NORTHERN SIBERIA WINDS lighting variants present; the game would use only:')
        print('  ', nsw[0])


if __name__ == '__main__':
    main()
