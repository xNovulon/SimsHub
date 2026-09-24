"""sig.py <zip> <path.pyc> [qualname-regex]: full Python 3.7 signatures (defaults, *args, **kw) of functions in a pyc."""
import sys, re, zipfile
sys.path.insert(0, r'C:\Users\basim\Tools\sims4_speedkit\tools')
from pyc37 import load, Code, OPS

def instrs(c):
    code, ext, out = c.co_code, 0, []
    for off in range(0, len(code), 2):
        op, arg = code[off], code[off + 1] | ext
        if OPS.get(op) == 'EXTENDED_ARG':
            ext = arg << 8; continue
        ext = 0
        out.append((OPS.get(op, op), arg))
    return out

def sigs(c, qual, out):
    ins = instrs(c)
    for k, (op, arg) in enumerate(ins):
        if op == 'MAKE_FUNCTION' and k >= 2 and ins[k - 2][0] == 'LOAD_CONST' and isinstance(c.co_consts[ins[k - 2][1]], Code):
            f = c.co_consts[ins[k - 2][1]]; name = c.co_consts[ins[k - 1][1]]
            j = k - 3; defaults = (); kwd = {}
            if arg & 8:  # closure tuple
                if ins[j][0] == 'BUILD_TUPLE':
                    j -= ins[j][1] + 1
                else:
                    j -= 1
            if arg & 4: j -= 1
            if arg & 2:
                if ins[j][0] == 'BUILD_CONST_KEY_MAP':
                    n = ins[j][1]; keys = c.co_consts[ins[j - 1][1]]
                    vals = [c.co_consts[a] if o == 'LOAD_CONST' else '<expr>' for o, a in ins[j - 1 - n:j - 1]]
                    kwd = dict(zip(keys, vals)); j -= n + 2
                else:
                    j -= 1
            if arg & 1:
                if ins[j][0] == 'LOAD_CONST':
                    defaults = c.co_consts[ins[j][1]]
                elif ins[j][0] == 'BUILD_TUPLE':
                    defaults = ('<expr>',) * ins[j][1]
            na, nk = f.co_argcount, f.co_kwonlyargcount
            names = list(f.co_varnames[:na]); kwo = list(f.co_varnames[na:na + nk])
            parts = []
            for i, a in enumerate(names):
                di = i - (na - len(defaults))
                parts.append(a + ('=' + repr(defaults[di]) if di >= 0 else ''))
            idx = na + nk
            if f.co_flags & 4:
                parts.append('*' + f.co_varnames[idx]); idx += 1
            elif kwo:
                parts.append('*')
            for a in kwo:
                parts.append(a + ('=' + repr(kwd[a]) if a in kwd else ''))
            if f.co_flags & 8:
                parts.append('**' + f.co_varnames[idx])
            out.append('%s(%s)  # line %d%s' % (name, ', '.join(parts), f.co_firstlineno, '  [generator]' if f.co_flags & 0x20 else ''))
    for k in c.co_consts:
        if isinstance(k, Code):
            sigs(k, qual, out)

z = zipfile.ZipFile(sys.argv[1]); top = load(z.read(sys.argv[2]))
out = []; sigs(top, '', out)
rx = re.compile(sys.argv[3]) if len(sys.argv) > 3 else None
for s in out:
    if rx is None or rx.search(s.split('(')[0]):
        print(s)
