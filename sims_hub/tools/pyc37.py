"""Read and disassemble Python 3.7 .pyc files (the Sims 4's Python) from a newer Python.

usage: python pyc37.py <ts4script> <module/path.pyc> [function-name-filter]
       python pyc37.py <ts4script> --grep <regex>      (modules whose names/consts match)
"""
import struct, sys, re, zipfile

OPS = {1: 'POP_TOP', 2: 'ROT_TWO', 3: 'ROT_THREE', 4: 'DUP_TOP', 5: 'DUP_TOP_TWO', 9: 'NOP', 10: 'UNARY_POSITIVE',
       11: 'UNARY_NEGATIVE', 12: 'UNARY_NOT', 15: 'UNARY_INVERT', 16: 'BINARY_MATRIX_MULTIPLY', 17: 'INPLACE_MATRIX_MULTIPLY',
       19: 'BINARY_POWER', 20: 'BINARY_MULTIPLY', 22: 'BINARY_MODULO', 23: 'BINARY_ADD', 24: 'BINARY_SUBTRACT',
       25: 'BINARY_SUBSCR', 26: 'BINARY_FLOOR_DIVIDE', 27: 'BINARY_TRUE_DIVIDE', 28: 'INPLACE_FLOOR_DIVIDE',
       29: 'INPLACE_TRUE_DIVIDE', 50: 'GET_AITER', 51: 'GET_ANEXT', 52: 'BEFORE_ASYNC_WITH', 55: 'INPLACE_ADD',
       56: 'INPLACE_SUBTRACT', 57: 'INPLACE_MULTIPLY', 59: 'INPLACE_MODULO', 60: 'STORE_SUBSCR', 61: 'DELETE_SUBSCR',
       62: 'BINARY_LSHIFT', 63: 'BINARY_RSHIFT', 64: 'BINARY_AND', 65: 'BINARY_XOR', 66: 'BINARY_OR', 67: 'INPLACE_POWER',
       68: 'GET_ITER', 69: 'GET_YIELD_FROM_ITER', 70: 'PRINT_EXPR', 71: 'LOAD_BUILD_CLASS', 72: 'YIELD_FROM',
       73: 'GET_AWAITABLE', 75: 'INPLACE_LSHIFT', 76: 'INPLACE_RSHIFT', 77: 'INPLACE_AND', 78: 'INPLACE_XOR',
       79: 'INPLACE_OR', 80: 'BREAK_LOOP', 81: 'WITH_CLEANUP_START', 82: 'WITH_CLEANUP_FINISH', 83: 'RETURN_VALUE',
       84: 'IMPORT_STAR', 85: 'SETUP_ANNOTATIONS', 86: 'YIELD_VALUE', 87: 'POP_BLOCK', 88: 'END_FINALLY', 89: 'POP_EXCEPT',
       90: 'STORE_NAME', 91: 'DELETE_NAME', 92: 'UNPACK_SEQUENCE', 93: 'FOR_ITER', 94: 'UNPACK_EX', 95: 'STORE_ATTR',
       96: 'DELETE_ATTR', 97: 'STORE_GLOBAL', 98: 'DELETE_GLOBAL', 100: 'LOAD_CONST', 101: 'LOAD_NAME', 102: 'BUILD_TUPLE',
       103: 'BUILD_LIST', 104: 'BUILD_SET', 105: 'BUILD_MAP', 106: 'LOAD_ATTR', 107: 'COMPARE_OP', 108: 'IMPORT_NAME',
       109: 'IMPORT_FROM', 110: 'JUMP_FORWARD', 111: 'JUMP_IF_FALSE_OR_POP', 112: 'JUMP_IF_TRUE_OR_POP',
       113: 'JUMP_ABSOLUTE', 114: 'POP_JUMP_IF_FALSE', 115: 'POP_JUMP_IF_TRUE', 116: 'LOAD_GLOBAL', 119: 'CONTINUE_LOOP',
       120: 'SETUP_LOOP', 121: 'SETUP_EXCEPT', 122: 'SETUP_FINALLY', 124: 'LOAD_FAST', 125: 'STORE_FAST',
       126: 'DELETE_FAST', 130: 'RAISE_VARARGS', 131: 'CALL_FUNCTION', 132: 'MAKE_FUNCTION', 133: 'BUILD_SLICE',
       135: 'LOAD_CLOSURE', 136: 'LOAD_DEREF', 137: 'STORE_DEREF', 138: 'DELETE_DEREF', 141: 'CALL_FUNCTION_KW',
       142: 'CALL_FUNCTION_EX', 143: 'SETUP_WITH', 144: 'EXTENDED_ARG', 145: 'LIST_APPEND', 146: 'SET_ADD',
       147: 'MAP_ADD', 148: 'LOAD_CLASSDEREF', 149: 'BUILD_LIST_UNPACK', 150: 'BUILD_MAP_UNPACK',
       151: 'BUILD_MAP_UNPACK_WITH_CALL', 152: 'BUILD_TUPLE_UNPACK', 153: 'BUILD_SET_UNPACK', 154: 'SETUP_ASYNC_WITH',
       155: 'FORMAT_VALUE', 156: 'BUILD_CONST_KEY_MAP', 157: 'BUILD_STRING', 158: 'BUILD_TUPLE_UNPACK_WITH_CALL',
       160: 'LOAD_METHOD', 161: 'CALL_METHOD'}
CMP = ['<', '<=', '==', '!=', '>', '>=', 'in', 'not in', 'is', 'is not', 'exception match', 'BAD']
JREL = {'FOR_ITER', 'JUMP_FORWARD', 'SETUP_LOOP', 'SETUP_EXCEPT', 'SETUP_FINALLY', 'SETUP_WITH', 'SETUP_ASYNC_WITH'}
JABS = {'JUMP_IF_FALSE_OR_POP', 'JUMP_IF_TRUE_OR_POP', 'JUMP_ABSOLUTE', 'POP_JUMP_IF_FALSE', 'POP_JUMP_IF_TRUE', 'CONTINUE_LOOP'}


class Code:
    def __repr__(self):
        return '<code %s>' % self.co_name


class Reader:
    def __init__(self, data):
        self.d, self.p, self.refs = data, 0, []

    def u8(self):
        v = self.d[self.p]; self.p += 1; return v

    def i32(self):
        v = struct.unpack_from('<i', self.d, self.p)[0]; self.p += 4; return v

    def raw(self, n):
        v = self.d[self.p:self.p + n]; self.p += n; return v

    def obj(self):
        code = self.u8()
        flag = code & 0x80
        t = chr(code & 0x7f)
        idx = None
        if flag:
            idx = len(self.refs); self.refs.append(None)
        if t == '0': v = NotImplemented
        elif t == 'N': v = None
        elif t == 'F': v = False
        elif t == 'T': v = True
        elif t == 'S': v = StopIteration
        elif t == '.': v = Ellipsis
        elif t == 'i': v = self.i32()
        elif t == 'l':
            n = self.i32(); v = 0
            for k in range(abs(n)):
                v |= struct.unpack_from('<H', self.d, self.p + 2 * k)[0] << (15 * k)
            self.p += 2 * abs(n); v = -v if n < 0 else v
        elif t == 'g': v = struct.unpack_from('<d', self.d, self.p)[0]; self.p += 8
        elif t == 'y': v = complex(*struct.unpack_from('<dd', self.d, self.p)); self.p += 16
        elif t == 's': v = self.raw(self.i32())
        elif t in 'tuaA': v = self.raw(self.i32()).decode('utf-8', 'replace')
        elif t in 'zZ': v = self.raw(self.u8()).decode('utf-8', 'replace')
        elif t in '([<>':
            n = self.i32()
            if flag and t == '(':
                pass
            items = [self.obj() for _ in range(n)]
            v = tuple(items) if t == '(' else items if t == '[' else set(map(_h, items)) if t == '<' else frozenset(map(_h, items))
        elif t == ')':
            n = self.u8(); v = tuple(self.obj() for _ in range(n))
        elif t == '{':
            v = {}
            while True:
                k = self.obj()
                if k is NotImplemented:
                    break
                v[_h(k)] = self.obj()
        elif t == 'c':
            c = Code()
            if idx is not None:
                self.refs[idx] = c
            (c.co_argcount, c.co_kwonlyargcount, c.co_nlocals, c.co_stacksize, c.co_flags) = [self.i32() for _ in range(5)]
            c.co_code = self.obj(); c.co_consts = self.obj(); c.co_names = self.obj(); c.co_varnames = self.obj()
            c.co_freevars = self.obj(); c.co_cellvars = self.obj(); c.co_filename = self.obj(); c.co_name = self.obj()
            c.co_firstlineno = self.i32(); c.co_lnotab = self.obj()
            v = c
        elif t == 'r':
            v = self.refs[self.i32()]
        else:
            raise ValueError('marshal type %r at %d' % (t, self.p))
        if idx is not None and t != 'c':
            self.refs[idx] = v
        return v


def _h(x):
    try:
        hash(x); return x
    except TypeError:
        return repr(x)


def load(data):
    return Reader(data[16:]).obj()


def lines(c):
    """offset -> line number"""
    out, line, off = {}, c.co_firstlineno, 0
    tab = c.co_lnotab
    for i in range(0, len(tab), 2):
        out.setdefault(off, line)
        off += tab[i]
        d = tab[i + 1]
        line += d - 256 if d >= 128 else d
    out.setdefault(off, line)
    return out


def dis(c, depth=0, out=None):
    out = out if out is not None else []
    pad = '    ' * depth
    args = c.co_varnames[:c.co_argcount + c.co_kwonlyargcount]
    out.append('%sdef %s(%s):   # line %d' % (pad, c.co_name, ', '.join(args), c.co_firstlineno))
    code = c.co_code
    free = tuple(c.co_cellvars) + tuple(c.co_freevars)
    ext = 0
    ln = lines(c)
    for off in range(0, len(code), 2):
        op, arg = code[off], code[off + 1] | ext
        name = OPS.get(op, 'OP%d' % op)
        if name == 'EXTENDED_ARG':
            ext = arg << 8; continue
        ext = 0
        if op < 90:
            s = ''
        elif name == 'LOAD_CONST':
            v = c.co_consts[arg]; s = ('<code %s>' % v.co_name) if isinstance(v, Code) else repr(v)[:120]
        elif name in ('LOAD_NAME', 'STORE_NAME', 'DELETE_NAME', 'LOAD_ATTR', 'STORE_ATTR', 'DELETE_ATTR', 'LOAD_GLOBAL',
                      'STORE_GLOBAL', 'DELETE_GLOBAL', 'IMPORT_NAME', 'IMPORT_FROM', 'LOAD_METHOD'):
            s = c.co_names[arg]
        elif name in ('LOAD_FAST', 'STORE_FAST', 'DELETE_FAST'):
            s = c.co_varnames[arg]
        elif name in ('LOAD_DEREF', 'STORE_DEREF', 'LOAD_CLOSURE', 'DELETE_DEREF', 'LOAD_CLASSDEREF'):
            s = free[arg] if arg < len(free) else arg
        elif name == 'COMPARE_OP':
            s = CMP[arg]
        elif name in JREL:
            s = 'to %d' % (off + 2 + arg)
        elif name in JABS:
            s = 'to %d' % arg
        else:
            s = arg
        mark = ('%5d' % ln[off]) if off in ln else '     '
        out.append('%s  %s %5d %-22s %s' % (pad, mark, off, name, s))
    for k in c.co_consts:
        if isinstance(k, Code):
            dis(k, depth + 1, out)
    return out


def walk(c):
    yield c
    for k in c.co_consts:
        if isinstance(k, Code):
            yield from walk(k)


def strings(c):
    seen = []
    for k in walk(c):
        for s in list(k.co_names) + [x for x in k.co_consts if isinstance(x, str)]:
            if s not in seen:
                seen.append(s)
    return seen


def outline(c, depth=0, out=None):
    out = out if out is not None else []
    for k in c.co_consts:
        if isinstance(k, Code):
            args = k.co_varnames[:k.co_argcount + k.co_kwonlyargcount]
            out.append('%s%s(%s)  line %d' % ('    ' * depth, k.co_name, ', '.join(args), k.co_firstlineno))
            outline(k, depth + 1, out)
    return out


if __name__ == '__main__':
    z = zipfile.ZipFile(sys.argv[1])
    if sys.argv[2] == '--grep':
        rx = re.compile(sys.argv[3], re.I)
        for n in z.namelist():
            if n.endswith('.pyc'):
                hits = [s for s in strings(load(z.read(n))) if rx.search(s)]
                if hits:
                    print(n, hits[:12])
        sys.exit()
    c = load(z.read(sys.argv[2]))
    mode = sys.argv[3] if len(sys.argv) > 3 else '--outline'
    if mode == '--outline':
        print('\n'.join(outline(c)))
    elif mode == '--strings':
        print(strings(c))
    elif mode == '--all':
        print('\n'.join(dis(c)))
    else:
        for k in walk(c):
            if re.fullmatch(mode, k.co_name):
                print('\n'.join(dis(k)))
