"""peexports.py <dll> [regex]: list exported names of a PE file (read-only, no deps)."""
import struct, sys, re
d = open(sys.argv[1], 'rb').read()
rx = re.compile(sys.argv[2]) if len(sys.argv) > 2 else None
pe = struct.unpack_from('<I', d, 0x3c)[0]
nsec = struct.unpack_from('<H', d, pe + 6)[0]
optsz = struct.unpack_from('<H', d, pe + 20)[0]
opt = pe + 24
magic = struct.unpack_from('<H', d, opt)[0]
dd = opt + (112 if magic == 0x20b else 96)
exp_rva, exp_sz = struct.unpack_from('<II', d, dd)
imp_rva, imp_sz = struct.unpack_from('<II', d, dd + 8)
secs = []
so = opt + optsz
for i in range(nsec):
    name, vsz, va, rsz, rptr = struct.unpack_from('<8sIIII', d, so + 40 * i)
    secs.append((va, max(vsz, rsz), rptr))
def off(rva):
    for va, sz, rp in secs:
        if va <= rva < va + sz:
            return rva - va + rp
    raise ValueError(hex(rva))
def cstr(o):
    return d[o:d.index(b'\0', o)].decode('latin1')
names = []
if exp_rva:
    e = off(exp_rva)
    nnames, afn, anames, aord = struct.unpack_from('<IIII', d, e + 24)[0], *struct.unpack_from('<III', d, e + 28)
    for i in range(nnames):
        names.append(cstr(off(struct.unpack_from('<I', d, off(anames) + 4 * i)[0])))
print('exports:', len(names))
for n in names:
    if rx is None or rx.search(n):
        print('  E', n)
# imports (dll names)
if imp_rva:
    o = off(imp_rva)
    while True:
        oft, ts, fc, nm, ft = struct.unpack_from('<IIIII', d, o)
        if nm == 0: break
        dll = cstr(off(nm))
        thunk = off(oft or ft)
        fn = []
        while True:
            v = struct.unpack_from('<Q' if magic == 0x20b else '<I', d, thunk)[0]
            if v == 0: break
            if not (v >> 63 if magic == 0x20b else v >> 31):
                fn.append(cstr(off(v & 0x7fffffff) + 2))
            thunk += 8 if magic == 0x20b else 4
        sel = [f for f in fn if rx is None or rx.search(f)]
        print('import', dll, len(fn), sel if rx else '')
        o += 20
