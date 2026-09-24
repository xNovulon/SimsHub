"""Read-only scan of a game binary for strings related to Resource.cfg parsing / mod loading.
Usage: python exe_strings.py <binary> <regex> [context_strings]
Prints printable ASCII and UTF-16LE strings (len>=4) matching regex, with file offset, plus
neighbouring strings (by offset order) for context.
"""
import re, sys, mmap

path, pat = sys.argv[1], re.compile(sys.argv[2].encode() if False else sys.argv[2], re.I)
ctx = int(sys.argv[3]) if len(sys.argv) > 3 else 0

with open(path, 'rb') as f:
    mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    data = mm[:]

strings = []
for m in re.finditer(rb'[\x20-\x7e]{4,}', data):
    strings.append((m.start(), 'A', m.group().decode('ascii')))
for m in re.finditer(rb'(?:[\x20-\x7e]\x00){4,}', data):
    strings.append((m.start(), 'W', m.group().decode('utf-16le')))
strings.sort()
idx = [i for i, s in enumerate(strings) if pat.search(s[2])]
shown = set()
for i in idx:
    for j in range(max(0, i - ctx), min(len(strings), i + ctx + 1)):
        if j in shown:
            continue
        shown.add(j)
        off, kind, s = strings[j]
        mark = '>>' if j == i else '  '
        print(f"{mark} {off:#010x} {kind} {s[:200]}")
    if ctx:
        print('--')
