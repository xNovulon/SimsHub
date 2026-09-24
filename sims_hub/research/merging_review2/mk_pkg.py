"""Minimal independent DBPF 2.1 writer for scratch test packages (research folder only)."""
import struct, zlib, sys
sys.path.insert(0, r'C:\Users\basim\Tools\sims4_speedkit\research\merging')
import s4s_manifest as m

def write(path, entries):
    """entries: list of (t,g,i,data,compress_bool)"""
    body = bytearray(); recs = []
    for t, g, i, data, comp in entries:
        stored = zlib.compress(data) if comp else data
        recs.append((t, g, i, 96 + len(body), len(stored), len(data), 0x5A42 if comp else 0))
        body += stored
    idx = bytearray(struct.pack('<I', 0))
    for t, g, i, off, fs, ms, c in recs:
        idx += struct.pack('<IIIIIIIHH', t, g, i >> 32, i & 0xFFFFFFFF, off, fs | 0x80000000, ms, c, 1)
    idxpos = 96 + len(body)
    hdr = bytearray(96)
    hdr[0:4] = b'DBPF'
    struct.pack_into('<II', hdr, 4, 2, 1)
    struct.pack_into('<III', hdr, 36, len(recs), 0, len(idx))
    struct.pack_into('<I', hdr, 60, 3)
    struct.pack_into('<I', hdr, 64, idxpos)
    with open(path, 'wb') as f:
        f.write(hdr); f.write(body); f.write(idx)

if __name__ == '__main__':
    out = sys.argv[1]
    A = (0x034AEECB, 0x80000000, 0x1111111111111111)
    B = (0x034AEECB, 0x80000000, 0x2222222222222222)
    C = (0x3C1AF1F2, 0x00000001, 0x3333333333333333)   # listed, missing
    D = (0x3C1AF1F2, 0x00000001, 0x4444444444444444)   # present, unlisted
    E = (0x00B2D882, 0x00000000, 0x5555555555555555)   # zlib
    F = (0x545AC67A, 0x00000000, 0x6666666666666666)   # listed twice (two sources)
    root = m.Folder('', [m.Folder('Deep', [m.Folder('Er', [], [m.Package('Leaf', [B])])], [])],
                    [m.Package('Alpha', [A, C, E, F]), m.Package('Beta', [F]), m.Package('Case', [A]), m.Package('case', [B])])
    man = m.Manifest(7, root)   # version 7: does S4S care?
    raw = m.build(man)
    write(out, [(*A, b'A' * 100, False), (m.MANIFEST_TYPE, 0, 0, raw, False),
                (*B, b'B' * 100, False), (*D, b'D' * 100, False), (*E, bytes(range(256)) * 4, True), (*F, b'F' * 77, False)])
    print('wrote', out)
