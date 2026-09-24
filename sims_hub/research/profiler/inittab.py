"""inittab.py <python dll>: recover the builtin-module table (_PyImport_Inittab) by pointer scanning (read-only)."""
import struct, sys, re
d = open(sys.argv[1], 'rb').read()
pe = struct.unpack_from('<I', d, 0x3c)[0]
nsec = struct.unpack_from('<H', d, pe + 6)[0]
optsz = struct.unpack_from('<H', d, pe + 20)[0]
opt = pe + 24
imagebase = struct.unpack_from('<Q', d, opt + 24)[0]
secs = []
so = opt + optsz
for i in range(nsec):
    name, vsz, va, rsz, rptr = struct.unpack_from('<8sIIII', d, so + 40 * i)
    secs.append((name.rstrip(b'\0').decode(), va, max(vsz, rsz), rptr, rsz))
def rva2off(rva):
    for n, va, sz, rp, rs in secs:
        if va <= rva < va + sz: return rva - va + rp
def off2rva(o):
    for n, va, sz, rp, rs in secs:
        if rp <= o < rp + rs: return o - rp + va
def cstr_at_va(v):
    o = rva2off(v - imagebase)
    if o is None: return None
    e = d.find(b'\0', o, o + 64)
    if e < 0: return None
    s = d[o:e]
    return s.decode() if re.fullmatch(rb'[A-Za-z_][A-Za-z0-9_.]*', s) else None
o = d.find(b'\x00_thread\x00') + 1
va = imagebase + off2rva(o)
p = d.find(struct.pack('<Q', va))
while p >= 0:
    # verify table: walk back to start
    start = p
    while True:
        n = struct.unpack_from('<Q', d, start - 16)[0]
        if cstr_at_va(n) is None: break
        start -= 16
    names = []
    q = start
    while True:
        n, f = struct.unpack_from('<QQ', d, q)
        if n == 0: break
        s = cstr_at_va(n)
        if s is None: break
        names.append(s); q += 16
    if len(names) > 10:
        print('table at file off 0x%x, %d entries' % (start, len(names)))
        print(' '.join(names))
    p = d.find(struct.pack('<Q', va), p + 1)
