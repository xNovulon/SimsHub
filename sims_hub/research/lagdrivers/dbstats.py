import sqlite3, time
db = sqlite3.connect(r'C:\Users\basim\Tools\sims4_speedkit\data\library.sqlite')
c = db.cursor()
print(c.execute("select root,count(*),sum(size)/1e9,sum(n) from pkg group by root").fetchall())
print(c.execute("select count(*),sum(size)/1e9 from script").fetchall())
rows = c.execute("select t,count(*),sum(fsize)/1e9,sum(msize)/1e9 from res where comp!=0xFFE0 group by t order by count(*) desc limit 25").fetchall()
names={0x034AEECB:'CASP',0x015A1849:'GEOM',0x00B2D882:'DDS/_IMG',0x3453CF95:'RLE2',0xBA856C78:'RLES',0x3C1AF1F2:'CAS thumb',0x5B282D45:'BB thumb?',0x736884F1:'VPXY',0xAC16FBEC:'RMAP',0x0354796A:'TONE',0x220557DA:'STBL',0x319E4F1D:'COBJ',0xC0DB5AE7:'OBJD',0x01661233:'MODL',0x01D10F34:'MLOD',0x8EAF13DE:'RIG',0x025ED6F4:'SIMO',0x6017E896:'BUFF xml',0x545AC67A:'SimData',0x0166038C:'NameMap',0x7FB6AD8A:'S4S merge manifest',0x6B20C4F3:'CLIP',0xD382BF57:'FTPT',0x3C2A8647:'thumb',0x9C925813:'thumb',0xCD9DE247:'PNG?',0x2F7D0004:'PNG',0x00DE5AC5:'RSLT?',0x0355E0A6:'BOND',0x71BDB8A2:'STYL?',0xB52F5055:'BGEO?',0x81CA1A10:'MTBL',0xD5F0F921:'CWAL',0x0418FE2A:'CFEN',0x03B4C61D:'LITE',0xE882D22F:'Interaction xml',0x0C772E27:'Loot xml',0x7DF2169C:'Snippet?',0xE231B3D8:'ObjMod?',0x2A8A5E22:'trait?',0xB61DE6B4:'Object tuning xml',0x9D1AB874:'script?',0x0333406C:'XML tuning',0x62E94D38:'XML',0xCB5FDDC7:'Trait xml',0xAC03A936:'MOOD?',0x03E9D964:'Pose?' }
tot=0
for t,n,fs,ms in rows:
    print(f"{t:08X} {names.get(t,''):22s} n={n:9d} disk={fs:8.2f}GB mem={ms:8.2f}GB")
print(c.execute("select count(*), sum(fsize)/1e9, sum(msize)/1e9 from res where comp!=0xFFE0").fetchall())
