import zlib, sys, os
sys.path.insert(0, r'C:\Users\basim\Tools\sims4_speedkit\research\merging')
import s4s_manifest as m
base = r'C:\Users\basim\Documents\Electronic Arts\The Sims 4\Mods_parked\LittleMsSam Pack'
for rel in [('LittleMsSam_CanIComeOver', 'LittleMsSam_CanIComeOver.package'), ('LittleMsSam_WhereAreYou', 'LittleMsSam_WhereAreYou.package')]:
    p = os.path.join(base, *rel)
    bad = 0
    with open(p, 'rb') as f:
        for t, g, i, off, fs, ms, comp in m.read_index(p):
            if comp != 0x5A42: continue
            f.seek(off); raw = f.read(fs)
            try:
                zlib.decompress(raw)
            except zlib.error as e:
                o = zlib.decompressobj(); out = o.decompress(raw)
                print(rel[1], '%08X' % t, 'off', off, fs, '->', len(out), 'msize', ms, 'eof', o.eof, 'err', e, 'tail', raw[-6:].hex())
                bad += 1
    print('bad', bad)
