"""Minimal DBPF 2.x (Sims 4 .package) index reader/writer."""
import struct, zlib, collections, sys

NAMES = {0x034AEECB: 'CASP', 0x015A1849: 'GEOM', 0x6B20C4F3: 'CLIP', 0x0354796A: 'TONE', 0x220557DA: 'STBL',
         0x7DF2169C: 'SNIPPET(tuning)', 0x545AC67A: 'SimData', 0x00B2D882: 'DDS/IMG', 0x3453CF95: 'RLE2',
         0xBA856C78: 'RLES', 0x319E4F1D: 'COBJ', 0xC0DB5AE7: 'OBJD', 0x01661233: 'MODL', 0x01D10F34: 'MLOD',
         0x8B18FF6E: 'CLHD(clip header)', 0x02D5DF13: 'ASM(jazz)', 0xE882D22F: 'Interaction tuning', 0x0333406C: 'XML tuning',
         0xAC16FBEC: 'RMAP', 0x8EAF13DE: 'RIG', 0xD382BF57: 'FTPT', 0x3C1AF1F2: 'THUM', 0xCD9DE247: 'PNG', 0x2F7D0004: 'PNG2'}


def read_index(path):
    with open(path, 'rb') as f:
        head = f.read(96)
        assert head[:4] == b'DBPF', path
        count = struct.unpack_from('<I', head, 36)[0]
        index_size = struct.unpack_from('<I', head, 44)[0]
        index_pos = struct.unpack_from('<I', head, 64)[0] or struct.unpack_from('<I', head, 40)[0]
        f.seek(index_pos)
        idx = f.read(index_size)
    flags = struct.unpack_from('<I', idx, 0)[0]
    p = 4
    const = {}
    for i, name in enumerate(('type', 'group', 'inst_hi')):
        if flags & (1 << i):
            const[name] = struct.unpack_from('<I', idx, p)[0]; p += 4
    out = []
    for _ in range(count):
        e = {}
        for name in ('type', 'group', 'inst_hi'):
            if name in const:
                e[name] = const[name]
            else:
                e[name] = struct.unpack_from('<I', idx, p)[0]; p += 4
        inst_lo, pos, size, memsize = struct.unpack_from('<IIII', idx, p); p += 16
        e['inst'] = (e.pop('inst_hi') << 32) | inst_lo
        e['pos'], e['size'], e['mem'] = pos, size & 0x7FFFFFFF, memsize
        if size & 0x80000000:
            e['comp'], e['committed'] = struct.unpack_from('<HH', idx, p); p += 4
        else:
            e['comp'] = 0
        out.append(e)
    return out


def read_resource(path, e):
    with open(path, 'rb') as f:
        f.seek(e['pos']); data = f.read(e['size'])
    if e['comp'] == 0x5A42:
        return zlib.decompress(data)
    if e['comp'] in (0, 0x0000):
        return data
    if e['comp'] == 0xFFFF:
        return refpack(data)
    return data


def refpack(data):
    # EA RefPack decompression
    flags = data[0]
    p = 2
    size_len = 4 if flags & 0x80 else 3
    size = int.from_bytes(data[p:p + size_len], 'big'); p += size_len
    out = bytearray()
    while p < len(data):
        b0 = data[p]
        if b0 < 0x80:
            b1 = data[p + 1]; p += 2
            plain = b0 & 3; cnt = ((b0 & 0x1C) >> 2) + 3; off = ((b0 & 0x60) << 3) + b1 + 1
        elif b0 < 0xC0:
            b1, b2 = data[p + 1], data[p + 2]; p += 3
            plain = (b1 & 0xC0) >> 6; cnt = (b0 & 0x3F) + 4; off = ((b1 & 0x3F) << 8) + b2 + 1
        elif b0 < 0xE0:
            b1, b2, b3 = data[p + 1], data[p + 2], data[p + 3]; p += 4
            plain = b0 & 3; cnt = ((b0 & 0x0C) << 6) + b3 + 5; off = ((b0 & 0x10) << 12) + (b1 << 8) + b2 + 1
        elif b0 < 0xFC:
            plain = ((b0 & 0x1F) << 2) + 4; cnt = 0; p += 1
        else:
            plain = b0 & 3; cnt = 0; p += 1
        out += data[p:p + plain]; p += plain
        for _ in range(cnt):
            out.append(out[-off])
        if b0 >= 0xFC:
            break
    return bytes(out)


if __name__ == '__main__':
    for path in sys.argv[1:]:
        idx = read_index(path)
        c = collections.Counter(NAMES.get(e['type'], '%08X' % e['type']) for e in idx)
        print(__import__('os').path.basename(path), len(idx), dict(c.most_common(14)))
