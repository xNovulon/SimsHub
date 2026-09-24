"""xref.py <ts4script> <regex>: every function (module:qualname) whose names or string consts match."""
import sys, re, zipfile
from pyc37 import load, walk, Code
z = zipfile.ZipFile(sys.argv[1]); rx = re.compile(sys.argv[2])
for n in z.namelist():
    if not n.endswith('.pyc'):
        continue
    top = load(z.read(n))
    def rec(c, qual):
        for k in c.co_consts:
            if isinstance(k, Code):
                q = (qual + '.' if qual else '') + k.co_name
                hits = sorted({s for s in list(k.co_names) + [x for x in k.co_consts if isinstance(x, str)] if rx.fullmatch(s)})
                if hits:
                    print('%-80s %s' % (n.replace('.pyc', '') + ':' + q + ':' + str(k.co_firstlineno), hits))
                rec(k, q)
    rec(top, '')
