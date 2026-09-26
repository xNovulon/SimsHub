"""Which original mod a resource of a merged package came from.

A merge made by Sims 4 Studio (or a tool that writes the same list: Sims 4 Mod Manager, the Sims Hub) holds a
resource of type 0x7FB6AD8A naming every source file and the resources that came from it. Same format as the
Sims Hub's speedkit/manifest.py (the animator keeps its own reader so it never depends on the Hub).

    names = sources_of(path, idx, keys)    # {(t, g, i): 'Original Mod.package'} for the keys found in the list
"""
import struct

from dbpf import read_resource

MANIFEST_TYPE = 0x7FB6AD8A
MASK = 0xFFFFFFFFFFFFFFFF


def _decode(data):
    """[(folder, name, [(t, g, i)])] of a decompressed merge list. Raises ValueError when it is malformed."""
    p = 0
    out = []

    def u32(fmt='<I'):
        nonlocal p
        if p + 4 > len(data):
            raise ValueError('merge list ends early')
        v = struct.unpack_from(fmt, data, p)[0]
        p += 4
        return v

    def text():
        nonlocal p
        n = u32()
        if p + n > len(data):
            raise ValueError('name runs past the end')
        s = data[p:p + n].decode('utf-8', 'replace')
        p += n
        return s

    def folder(prefix, depth):
        nonlocal p
        if depth > 64:
            raise ValueError('folders nested too deep')
        name = text()
        path = (prefix + '/' + name).strip('/') if name else prefix
        subs = [folder(path, depth + 1) for _ in range(u32())]
        for _ in range(u32()):
            src = text()
            count = u32('<i')
            if count < 0 or p + 16 * count > len(data):
                raise ValueError('bad key count')
            keys = [(t, g, i) for i, t, g in struct.iter_unpack('<QII', data[p:p + 16 * count])]
            p += 16 * count
            out.append((path, src, keys))
        return subs

    u32()                       # version
    folder('', 0)
    return out


def sources_of(path, idx, keys):
    """{(t, g, i): source file name} for the wanted keys, or {} when the package has no (readable) merge list."""
    want = {(t & 0xFFFFFFFF, g & 0xFFFFFFFF, i & MASK) for t, g, i in keys}
    if not want:
        return {}
    e = next((x for x in idx if x['type'] == MANIFEST_TYPE), None)
    if e is None:
        return {}
    try:
        lst = _decode(read_resource(path, e))
    except Exception:
        return {}
    out = {}
    for folder, name, ks in lst:
        label = name if name.lower().endswith('.package') else name + '.package'
        for k in ks:
            k = (k[0] & 0xFFFFFFFF, k[1] & 0xFFFFFFFF, k[2] & MASK)
            if k in want and k not in out:
                out[k] = label
    return out
