import sys
from mk_pkg import write
K = (0x034AEECB, 0x80000000, 0xAAAAAAAAAAAAAAAA)
write(r'merge\s1.package', [(*K, b'1' * 100, False), (0x034AEECB, 0x80000000, 1, b'x' * 50, False),
                            (0x7FB6AD8A, 0, 5, b'fake-manifest-type-nonzero-instance', False)])
write(r'merge\s2.package', [(*K, b'2' * 120, False), (0x034AEECB, 0x80000000, 2, b'y' * 50, True)])
