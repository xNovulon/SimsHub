"""Two scratch source packages sharing key K with different bytes (for S4S merge-order test)."""
import sys
sys.path.insert(0, r'C:\Users\basim\Tools\sims4_speedkit')
from speedkit.dbpf import PackageWriter
K = (0x034AEECB, 0x80000000, 0xAAAAAAAAAAAAAAAA)
with PackageWriter(sys.argv[1] + r'\src1.package') as w:
    w.add(K, b'1' * 100, compress=False)
    w.add((0x034AEECB, 0x80000000, 0x1), b'x' * 50, compress=False)
with PackageWriter(sys.argv[1] + r'\src2.package') as w:
    w.add(K, b'2' * 120, compress=False)
    w.add((0x034AEECB, 0x80000000, 0x2), b'y' * 50, compress=False)
