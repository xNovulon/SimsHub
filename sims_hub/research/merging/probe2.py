import sqlite3, zlib, struct, collections, os
DB=r'C:\Users\basim\Tools\sims4_speedkit\data\library.sqlite'
SIMS=r'C:\Users\basim\Documents\Electronic Arts\The Sims 4'
db=sqlite3.connect(DB)
T=0x7FB6AD8A
def u64(i): return i & 0xFFFFFFFFFFFFFFFF
rows=db.execute('select p.id,p.root,p.rel,r.off,r.fsize,r.msize,r.comp,p.n from res r join pkg p on p.id=r.pkg where r.t=?',(T,)).fetchall()
agg=collections.Counter(); ex=[]
typ_missing=collections.Counter(); typ_extra=collections.Counter()
nameenc=collections.Counter(); dupnames=0; dup_within=0; cross=0
for pid,root,rel,off,fs,ms,comp,n in rows:
    with open(os.path.join(SIMS,root,rel),'rb') as f:
        f.seek(off); d=zlib.decompress(f.read(fs))
    cnt=struct.unpack_from('<I',d,12)[0]; p=16
    man=[]; names=[]
    for k in range(cnt):
        L=struct.unpack_from('<I',d,p)[0]; p+=4
        nm=d[p:p+L]; p+=L; names.append(nm)
        try: nm.decode('ascii'); nameenc['ascii']+=1
        except: 
            try: nm.decode('utf-8'); nameenc['utf8']+=1
            except: nameenc['other']+=1
        c=struct.unpack_from('<I',d,p)[0]; p+=4
        for j in range(c):
            i,t,g=struct.unpack_from('<QII',d,p); p+=16
            man.append((t,g,i,k))
    if len(set(names))!=len(names): dupnames+=1
    pk=set((t,g,u64(i)) for t,g,i in db.execute('select t,g,i from res where pkg=? and comp!=65504',(pid,)))
    ms_=collections.Counter((t,g,i) for t,g,i,k in man)
    dup_within+= sum(1 for v in ms_.values() if v>1)
    mset=set(ms_)
    missing=pk-mset-{(T,0,0)}; extra=mset-pk
    for t,g,i in missing: typ_missing[hex(t)]+=1
    for t,g,i in extra: typ_extra[hex(t)]+=1
    agg['pk']+=len(pk); agg['man_unique']+=len(mset); agg['man_rows']+=len(man); agg['missing']+=len(missing); agg['extra']+=len(extra)
    if missing or extra: ex.append((rel,len(pk),len(mset),len(missing),len(extra)))
print(agg); print('names',nameenc,'pkgs with duplicate source names',dupnames,'TGIs listed in >1 source',dup_within)
print('missing from manifest by type',typ_missing.most_common(12))
print('manifest entries not in package by type',typ_extra.most_common(12))
print(len(ex)); [print(e) for e in ex[:20]]
