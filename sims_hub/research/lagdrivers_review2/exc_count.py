import re, collections, sys
p = r'C:\Users\basim\Documents\Electronic Arts\The Sims 4\lastException_63925876431.txt'
d = open(p, encoding='utf-8', errors='replace').read()
reps = re.findall(r'<report>(.*?)</report>', d, re.S)
c = collections.Counter(); cat = collections.Counter(); times = []
for r in reps:
    m = re.search(r'<desyncdata>(.*?)</desyncdata>', r, re.S)
    body = m.group(1) if m else r
    e = re.findall(r'([A-Za-z_.]+(?:Error|Exception)[^\n&]{0,90})', body)
    last = e[-1] if e else '?'
    c[last[:110]] += 1
    cat[re.search(r'<categoryid>(.*?)</categoryid>', r).group(1)[:80] if '<categoryid>' in r else '?'] += 1
    t = re.search(r'<createtime>(.*?)</createtime>', r)
    if t: times.append(t.group(1))
print(len(reps), 'reports; time range', times[:1], times[-1:])
for k, v in c.most_common(10): print(v, k)
print('--- categoryid')
for k, v in cat.most_common(10): print(v, k)
