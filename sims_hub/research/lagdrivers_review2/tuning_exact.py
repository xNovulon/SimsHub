"""Read-only: exact count of XML resources in the library. Reads the first bytes of every resource whose
type is not a known binary type, inflates the start, classifies as XML if first non-space char is '<'."""
import os, sys, time, sqlite3, zlib
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
S = r'C:\Users\basim\Documents\Electronic Arts\The Sims 4'
db = sqlite3.connect(r'C:\Users\basim\Tools\sims4_speedkit\data\library.sqlite')
BIN = {0x3453CF95,0x2BC04EDF,0x015A1849,0x00B2D882,0x6B20C4F3,0x034AEECB,0x3C1AF1F2,0xBA856C78,0xAC16FBEC,
       0x01D10F34,0x01661233,0x736884F1,0x8EAF13DE,0x3C2A8647,0x5B282D45,0x9C925813,0x0354796A,0x220557DA,
       0x545AC67A,0x0166038C,0x7FB6AD8A,0xD382BF57,0xBC4A5044,0x0355E0A6,0xC0DB5AE7,0x319E4F1D,0x025ED6F4}
pk = {}
for pid, root, rel in db.execute('select id, root, rel from pkg'):
    p = os.path.join(S, root, rel.replace('/', os.sep))
    if not os.path.exists(p): p = os.path.join(S, 'Mods_parked', rel.replace('/', os.sep))
    pk[pid] = (p, rel)
rows = defaultdict(list)
for pid, t, off, fs, ms, comp in db.execute('select pkg, t, off, fsize, msize, comp from res where comp in (0,23106)'):
    if t not in BIN: rows[pid].append((t, off, fs, ms, comp))
print('candidates', sum(len(v) for v in rows.values()))
def work(pid):
    p, rel = pk[pid]; c = Counter(); b = Counter(); first = Counter()
    if not os.path.exists(p): return pid, c, b, first
    fd = os.open(p, os.O_RDONLY | os.O_BINARY)
    try:
        for t, off, fs, ms, comp in rows[pid]:
            os.lseek(fd, off, 0); d = os.read(fd, min(fs, 4096))
            try:
                if comp == 23106: d = zlib.decompressobj().decompress(d, 512)
            except Exception: continue
            s = d.lstrip(b'\xef\xbb\xbf').lstrip()
            if s[:1] == b'<':
                c[t] += 1; b[t] += ms; first[s[:5]] += 1
    finally: os.close(fd)
    return pid, c, b, first
t0 = time.perf_counter(); C = Counter(); B = Counter(); F = Counter(); per = Counter()
with ThreadPoolExecutor(8) as ex:
    for pid, c, b, f in ex.map(work, list(rows)):
        C.update(c); B.update(b); F.update(f); per[pk[pid][1]] = sum(c.values()), sum(b.values())
print(f'XML resources {sum(C.values())} in {len(C)} types, {sum(B.values())/1e6:.1f} MB uncompressed, {time.perf_counter()-t0:.1f}s')
print('first bytes', F.most_common(8))
for t, n in C.most_common(10): print(f'  {t:08X} {n}')
for rel, (n, m) in sorted(per.items(), key=lambda kv: -kv[1][0])[:6]: print('  pkg', rel, n, round(m/1e6, 1), 'MB')
