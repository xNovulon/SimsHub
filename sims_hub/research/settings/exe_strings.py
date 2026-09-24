import re, sys, mmap
path = sys.argv[1]; pats = [p.encode() for p in sys.argv[2:]]
with open(path,'rb') as f:
    mm = mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ)
    data = mm[:]
ascii_re = re.compile(rb'[\x20-\x7e]{4,}')
seen=set()
for m in ascii_re.finditer(data):
    s=m.group()
    if any(re.search(p, s, re.I) for p in pats):
        if s not in seen:
            seen.add(s); print('A', hex(m.start()), s.decode('ascii'))
u16 = re.compile(rb'(?:[\x20-\x7e]\x00){4,}')
for m in u16.finditer(data):
    s=m.group().decode('utf-16le').encode()
    if any(re.search(p, s, re.I) for p in pats):
        if s not in seen:
            seen.add(s); print('W', hex(m.start()), s.decode())
