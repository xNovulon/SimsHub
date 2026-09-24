import sqlite3, gzip, collections, dupes, sys, struct, numpy as np
sys.stdout.reconfigure(encoding='utf-8')
db = sqlite3.connect(dupes.DB); pkgs = dupes.load_pkgs(db)
rows = []
with gzip.open(dupes.KEYS_TSV, 'rt', encoding='utf-8') as f:
    for line in f:
        if line.startswith('034AEECB') and '\tconflict\t' in line:
            p = line.rstrip('\n').split('\t')
            if p[5] == '2':
                cps = [c.lstrip('*').split(':') for c in p[6].split(',')]
                if len({c[3] for c in cps}) == 1:
                    rows.append((p, cps))
print('same-size 2-variant CASP conflicts:', len(rows))
off_hist = collections.Counter(); ver_pairs = collections.Counter(); field = collections.Counter()
for p, cps in rows[:400]:
    t, g, i = int(p[0], 16), int(p[1], 16), int(p[2], 16)
    i_s = i - (1 << 64) if i >= (1 << 63) else i
    got = {}
    for c in cps:
        if c[1] in got: continue
        pid = int(c[0])
        off, fs, comp = db.execute('select off, fsize, comp from res where pkg=? and t=? and g=? and i=?', (pid, t, g, i_s)).fetchone()
        got[c[1]] = dupes.read_resource(pkgs[pid][0], pkgs[pid][1], off, fs, comp)
    a, b = list(got.values())[:2]
    x = np.frombuffer(a, np.uint8); y = np.frombuffer(b, np.uint8)
    d = np.nonzero(x != y)[0]
    ver = struct.unpack_from('<I', a, 0)[0]
    # name: 7-bit length prefix (bytes), UTF-16BE
    q = 12; ln = 0; sh = 0
    while True:
        bb = a[q]; q += 1; ln |= (bb & 0x7F) << sh; sh += 7
        if not bb & 0x80: break
    after = q + ln
    rel = tuple(int(o) - after for o in d)
    off_hist[rel[:3]] += 1
    ver_pairs[(ver, struct.unpack_from('<I', b, 0)[0])] += 1
    # field guess: sortPriority f32 @after, secondarySortIndex u16 @+4, propertyID u32 @+6, auralMaterialHash u32 @+10, paramFlags u8 @+14
    for o in rel:
        name = ('head(<name)' if o < -ln else 'name' if o < 0 else 'sortPriority' if o < 4 else 'secondarySortIndex' if o < 6 else 'propertyID' if o < 10 else 'auralMaterialHash' if o < 14 else 'paramFlags' if o < 15 else 'later(+%d)' % o)
        field[name] += 1
print('version pairs', ver_pairs.most_common(5))
print('differing field (per byte)', field.most_common(12))
print('first differing offsets rel. to end of name', off_hist.most_common(8))
