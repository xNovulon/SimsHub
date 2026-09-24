"""Generic protobuf wire-format walker (no schema).

Emits every varint / fixed64 / fixed32 value together with the path of field numbers that led to it.
A length-delimited blob is recursed into when it parses cleanly as a message. Otherwise, if it is small,
it is also read as a packed varint list (path marker 0) and, when its length is a multiple of 8, as a
packed fixed64 list (marker 8) - the game's IdList.ids (outfit CAS parts) is packed fixed64. A blob that
is small and a multiple of 8 is read as fixed64 even when it also parses as a message (a fixed64 list can
look like a message by accident). Large non-message blobs go to the `opaque` callback."""
import struct

PACKED_MAX = 1 << 16
M64 = 0xFFFFFFFFFFFFFFFF


def _varint(b, p, n):
    r = 0; s = 0
    while True:
        if p >= n or s > 63:
            raise ValueError
        c = b[p]; p += 1
        r |= (c & 0x7F) << s
        if c < 0x80:
            return r & M64, p
        s += 7


def parse_message(b, start=0, end=None):
    """-> list of (field, wiretype, value_or_(start,end)) if b[start:end] is a clean message, else None."""
    n = len(b) if end is None else end
    p = start
    out = []
    try:
        while p < n:
            key, p = _varint(b, p, n)
            f, wt = key >> 3, key & 7
            if f == 0 or f > 536870911:
                return None
            if wt == 0:
                v, p = _varint(b, p, n); out.append((f, 0, v))
            elif wt == 1:
                if p + 8 > n: return None
                out.append((f, 1, struct.unpack_from('<Q', b, p)[0])); p += 8
            elif wt == 2:
                ln, p = _varint(b, p, n)
                if p + ln > n: return None
                out.append((f, 2, (p, p + ln))); p += ln
            elif wt == 5:
                if p + 4 > n: return None
                out.append((f, 5, struct.unpack_from('<I', b, p)[0])); p += 4
            else:
                return None
    except (ValueError, IndexError):
        return None
    return out if p == n else None


def parse_packed(b, start, end):
    out = []
    p = start
    try:
        while p < end:
            v, p = _varint(b, p, end)
            out.append(v)
    except ValueError:
        return None
    return out


def walk(b, emit, opaque=None, start=0, end=None, path=(), depth=0, max_depth=40):
    fields = parse_message(b, start, end)
    if fields is None:
        return False
    for f, wt, v in fields:
        pth = path + (f,)
        if wt != 2:
            emit(pth, v)
            continue
        s, e = v
        ln = e - s
        if ln == 0:
            continue
        is_msg = depth < max_depth and walk(b, emit, opaque, s, e, pth, depth + 1, max_depth)
        if ln <= PACKED_MAX:
            if ln % 8 == 0:
                p8 = pth + (8,)
                for x in struct.unpack_from('<%dQ' % (ln // 8), b, s):
                    emit(p8, x)
            if not is_msg:
                packed = parse_packed(b, s, e)
                if packed is not None:
                    p0 = pth + (0,)
                    for x in packed:
                        emit(p0, x)
        elif not is_msg and opaque is not None:
            opaque(pth, s, e)
    return True
