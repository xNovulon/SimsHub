import sqlite3, zlib, struct, collections, os, sys
DB=r'C:\Users\basim\Tools\sims4_speedkit\data\library.sqlite'
SIMS=r'C:\Users\basim\Documents\Electronic Arts\The Sims 4'
db=sqlite3.connect(DB)
T=0x7FB6AD8A
def u64(i): return i & 0xFFFFFFFFFFFFFFFF
def man_of(rel):
    pid,root,off,fs=db.execute('select p.id,p.root,r.off,r.fsize from res r join pkg p on p.id=r.pkg where r.t=? and p.rel=?',(T,rel)).fetchone()
    with open(os.path.join(SIMS,root,rel),'rb') as f:
        f.seek(off); d=zlib.decompress(f.read(fs))
    cnt=struct.unpack_from('<I',d,12)[0]; p=16; man=[]; names=[]
    for k in range(cnt):
        L=struct.unpack_from('<I',d,p)[0]; p+=4
        names.append(d[p:p+L].decode('utf-8')); p+=L
        c=struct.unpack_from('<I',d,p)[0]; p+=4
        for j in range(c):
            i,t,g=struct.unpack_from('<QII',d,p); p+=16; man.append((t,g,i,k))
    pk=[(t,g,u64(i),off,fs,ms,comp) for t,g,i,off,fs,ms,comp in db.execute('select t,g,i,off,fsize,msize,comp from res where pkg=? order by off',(pid,))]
    return names,man,pk
for rel in sys.argv[1:]:
    names,man,pk=man_of(rel)
    mset={(t,g,i) for t,g,i,k in man}; pset={(t,g,i) for t,g,i,*_ in pk}
    print('==',rel,'sources',len(names),names[:5])
    miss=sorted(pset-mset); extra=sorted(mset-pset)
    print(' missing', [ '%08x:%08x:%016x'%x for x in miss[:6]])
    print(' extra  ', [ '%08x:%08x:%016x'%x for x in extra[:6]])
    # order of resources in package vs manifest
    order=[(t,g,i) for t,g,i,*_ in pk]
    mo=[(t,g,i) for t,g,i,k in man]
    print(' first 5 pkg order', ['%08x:%08x:%016x'%x for x in order[:5]])
    print(' first 5 man order', ['%08x:%08x:%016x'%x for x in mo[:5]])
    # positions of missing in pkg by offset
    idx={x:n for n,x in enumerate(order)}
    pos=sorted(idx[m] for m in miss)
    if pos: print(' missing positions in offset order: min',pos[0],'max',pos[-1],'of',len(order))
