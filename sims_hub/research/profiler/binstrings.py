"""binstrings.py <file> <regex> [maxhits]: ASCII and UTF-16LE strings in a binary matching regex (read-only)."""
import re, sys
f, pat = sys.argv[1], sys.argv[2]
mx = int(sys.argv[3]) if len(sys.argv) > 3 else 60
d = open(f, 'rb').read()
rx = re.compile(pat, re.I)
hits = {}
for m in re.finditer(rb'[\x20-\x7e]{4,}', d):
    s = m.group().decode()
    if rx.search(s):
        hits.setdefault('A:' + s[:200], m.start())
for m in re.finditer(rb'(?:[\x20-\x7e]\x00){4,}', d):
    s = m.group().decode('utf-16-le')
    if rx.search(s):
        hits.setdefault('W:' + s[:200], m.start())
print(len(hits), 'hits')
for k, v in sorted(hits.items(), key=lambda kv: kv[1])[:mx]:
    print('0x%08x %s' % (v, k))
