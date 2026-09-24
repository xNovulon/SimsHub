"""Build an edge-case merged package (scratch only): manifest LAST and UNCOMPRESSED, one subfolder,
one listed-but-missing key, one unlisted resource, one zlib resource, same name differing in case."""
import sys, os
sys.path.insert(0, r'C:\Users\basim\Tools\sims4_speedkit')
sys.path.insert(0, r'C:\Users\basim\Tools\sims4_speedkit\research\merging')
from speedkit.dbpf import PackageWriter
import s4s_manifest as m
out = sys.argv[1]
A = (0x034AEECB, 0x80000000, 0x1111111111111111)
B = (0x034AEECB, 0x80000000, 0x2222222222222222)
C = (0x3C1AF1F2, 0x00000001, 0x3333333333333333)   # listed, missing from index
D = (0x3C1AF1F2, 0x00000001, 0x4444444444444444)   # in index, unlisted
E = (0x00B2D882, 0x00000000, 0x5555555555555555)   # zlib-compressed
root = m.Folder('', [m.Folder('Sub', [], [m.Package('InSub', [B])])],
                [m.Package('Top', [A, C, E]), m.Package('Other', [A])])
raw = m.build(m.Manifest(1, root))
with PackageWriter(out) as w:
    w.add(A, b'A' * 100, compress=False)
    w.add(B, b'B' * 100, compress=False)
    w.add(D, b'D' * 100, compress=False)
    w.add(E, bytes(range(256)) * 4, compress=True)
    w.add((m.MANIFEST_TYPE, 0, 0), raw, compress=False)
print('built', out, os.path.getsize(out))
