"""Read-only: print DBPF header fields of the largest packages in the library and flag any whose
index (or data) lies at/after 2 GiB (2**31) or 4 GiB (2**32).
DBPF 2.x header: 'DBPF', major@4, minor@8, ..., index entry count@0x24, index pos (legacy)@0x28,
index size@0x2C, ..., index pos@0x40 (uint32)."""
import os, sqlite3, struct, sys

BASE = r'C:\Users\basim\Documents\Electronic Arts\The Sims 4'
DB = r'C:\Users\basim\Tools\sims4_speedkit\data\library.sqlite'
db = sqlite3.connect(DB)
limit = int(sys.argv[1]) if len(sys.argv) > 1 else 80
rows = db.execute('select root, rel, size, n from pkg order by size desc limit ?', (limit,)).fetchall()
flagged = 0
for root, rel, size, n in rows:
    p = os.path.join(BASE, root, *rel.split('/'))
    with open(p, 'rb') as f:
        h = f.read(96)
    major, minor = struct.unpack_from('<II', h, 4)
    count, pos28, isize = struct.unpack_from('<III', h, 0x24)
    pos40 = struct.unpack_from('<I', h, 0x40)[0]
    idx = pos40 or pos28
    maxend = db.execute('select max(off+fsize) from res r join pkg p on p.id=r.pkg where p.root=? and p.rel=?',
                        (root, rel)).fetchone()[0]
    flag = idx >= 2 ** 31 or size > 2 ** 31
    flagged += flag
    if flag or rows.index((root, rel, size, n)) < 3:
        print(f'{rel}: size={size} ({size - 2**31:+d} vs 2GiB) DBPF {major}.{minor} entries={count} (db n={n}) '
              f'index@{idx} (0x{idx:08x}) size={isize} last_resource_end={maxend} '
              f'{"INDEX >= 2GiB" if idx >= 2**31 else ""}')
print('flagged (file > 2 GiB or index >= 2 GiB):', flagged)
