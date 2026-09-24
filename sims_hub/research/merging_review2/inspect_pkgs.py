"""Read-only: dump index + manifest of scratch packages (research folder only)."""
import sys, zlib
sys.path.insert(0, r'C:\Users\basim\Tools\sims4_speedkit\research\merging')
import s4s_manifest as m
for path in sys.argv[1:]:
    idx = m.read_index(path)
    print('==', path)
    with open(path, 'rb') as f:
        hdr = f.read(96)
        import struct
        print('  header major/minor', struct.unpack_from('<II', hdr, 4), 'count', struct.unpack_from('<I', hdr, 36)[0], 'idxpos', struct.unpack_from('<I', hdr, 64)[0])
        for t, g, i, off, fs, ms, comp in idx:
            f.seek(off); raw = f.read(fs)
            data = zlib.decompress(raw) if comp == 0x5A42 else raw
            print('  %08X:%08X:%016X off=%d fs=%d ms=%d comp=%04X head=%r' % (t, g, i, off, fs, ms, comp, data[:12]))
    mf, idx, ent = m.read_manifest(path)
    if mf:
        for p, pk in mf.packages():
            print('   manifest src %r/%r keys=%s' % (p, pk.name, ['%08X:%08X:%016X' % k for k in pk.keys]))
