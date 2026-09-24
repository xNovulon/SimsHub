import sqlite3, zlib, struct, collections, os
DB=r'C:\Users\basim\Tools\sims4_speedkit\data\library.sqlite'
SIMS=r'C:\Users\basim\Documents\Electronic Arts\The Sims 4'
db=sqlite3.connect(DB)
T=0x7FB6AD8A
hdr=collections.Counter(); problems=[]; stats=[]
rows=db.execute('select p.id,p.root,p.rel,r.off,r.fsize,r.msize,r.comp,p.n from res r join pkg p on p.id=r.pkg where r.t=?',(T,)).fetchall()
for pid,root,rel,off,fs,ms,comp,n in rows:
    with open(os.path.join(SIMS,root,rel),'rb') as f:
        f.seek(off); b=f.read(fs)
    d=zlib.decompress(b) if comp==0x5A42 else b
    assert len(d)==ms,(rel,len(d),ms)
    v,a,b2,cnt=struct.unpack_from('<IIII',d,0)
    hdr[(v,a,b2)]+=1
    p=16; tot=0; names=[]
    try:
        for k in range(cnt):
            L=struct.unpack_from('<I',d,p)[0]; p+=4
            name=d[p:p+L]; p+=L
            c=struct.unpack_from('<I',d,p)[0]; p+=4
            p+=16*c; tot+=c; names.append(name)
    except Exception as e:
        problems.append((rel,'exc',e)); continue
    stats.append((rel,cnt,tot,n,len(d)-p))
    if p!=len(d): problems.append((rel,'trailing',len(d)-p))
print('headers',hdr)
print('problems',problems[:10],len(problems))
nonascii=0
print('sample stats (rel, pkgs, entries, pkg.n, trailing):')
for s in stats[:8]: print(s)
print('entries vs pkg.n diff distribution', collections.Counter(s[3]-s[2] for s in stats).most_common(10))
