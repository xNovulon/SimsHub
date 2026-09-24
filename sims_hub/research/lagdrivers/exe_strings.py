"""Read-only string search in a game binary (ASCII + UTF-16LE).
usage: python exe_strings.py <exe> <regex> [minlen]
Prints offset, encoding, string for every string matching regex (case-insensitive)."""
import re, sys

path, pat = sys.argv[1], re.compile(sys.argv[2], re.I)
minlen = int(sys.argv[3]) if len(sys.argv) > 3 else 4
data = open(path, 'rb').read()
seen = set()
for m in re.finditer(rb'[\x20-\x7e]{%d,}' % minlen, data):
    s = m.group().decode('ascii')
    if pat.search(s) and s not in seen:
        seen.add(s); print(hex(m.start()), 'A', s)
for m in re.finditer(rb'(?:[\x20-\x7e]\x00){%d,}' % minlen, data):
    s = m.group().decode('utf-16le')
    if pat.search(s) and s not in seen:
        seen.add(s); print(hex(m.start()), 'W', s)
