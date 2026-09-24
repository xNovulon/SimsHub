import re, sys
path=sys.argv[1]; a=int(sys.argv[2],16); b=int(sys.argv[3],16)
d=open(path,'rb').read()[a:b]
out=[]
for m in re.finditer(rb'[\x20-\x7e]{3,}', d): out.append((m.start()+a,'A',m.group().decode()))
for m in re.finditer(rb'(?:[\x20-\x7e]\x00){3,}', d): out.append((m.start()+a,'W',m.group().decode('utf-16le')))
for o,k,s in sorted(out): print(hex(o),k,s)
