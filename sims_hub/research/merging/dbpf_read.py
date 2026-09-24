"""Read-only helpers: fetch and decompress one resource from a .package given its index row.

Used by s4s_manifest.py and companions.py. Never writes to the package.
"""
import os
import struct
import zlib

SIMS = os.path.join(os.path.expanduser('~'), 'Documents', 'Electronic Arts', 'The Sims 4')
ROOTS = {'Mods': os.path.join(SIMS, 'Mods'), 'Mods_parked': os.path.join(SIMS, 'Mods_parked')}
DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'data', 'library.sqlite')

COMP_NONE, COMP_ZLIB, COMP_REFPACK, COMP_STREAM, COMP_DELETED = 0, 0x5A42, 0xFFFF, 0xFFFE, 0xFFE0


def u64(i):
    return i & 0xFFFFFFFFFFFFFFFF


def refpack_decompress(src):
    """EA RefPack/QFS ('internal compression', 0xFFFF). Header: flags byte, 0xFB, 3- or 4-byte BE size."""
    p = 0
    flags = src[0]
    if src[1] != 0xFB:
        raise ValueError('not refpack')
    p = 2
    nbytes = 4 if flags & 0x80 else 3
    size = int.from_bytes(src[p:p + nbytes], 'big')
    p += nbytes
    if flags & 0x01:  # compressed-size field present
        p += nbytes
    out = bytearray()
    n = len(src)
    while p < n:
        b0 = src[p]
        if b0 < 0x80:
            b1 = src[p + 1]; p += 2
            plain = b0 & 3
            clen = ((b0 >> 2) & 7) + 3
            off = ((b0 & 0x60) << 3) + b1 + 1
        elif b0 < 0xC0:
            b1, b2 = src[p + 1], src[p + 2]; p += 3
            plain = b1 >> 6
            clen = (b0 & 0x3F) + 4
            off = ((b1 & 0x3F) << 8) + b2 + 1
        elif b0 < 0xE0:
            b1, b2, b3 = src[p + 1], src[p + 2], src[p + 3]; p += 4
            plain = b0 & 3
            clen = ((b0 & 0x0C) << 6) + b3 + 5
            off = ((b0 & 0x10) << 12) + (b1 << 8) + b2 + 1
        elif b0 < 0xFC:
            plain = ((b0 & 0x1F) << 2) + 4; clen = 0; off = 0; p += 1
        else:
            plain = b0 & 3; clen = 0; off = 0; p += 1
        out += src[p:p + plain]; p += plain
        if clen:
            start = len(out) - off
            if off >= clen:
                out += out[start:start + clen]
            else:
                for k in range(clen):
                    out.append(out[start + k])
        if b0 >= 0xFC:
            break
    return bytes(out[:size])


def decompress(raw, comp, msize=None):
    if comp == COMP_ZLIB:
        # tolerant: some tools write zlib streams without the final block/adler32 (seen in 2
        # LittleMsSam packages); the game only needs msize bytes, so accept a short stream.
        o = zlib.decompressobj()
        out = o.decompress(raw)
        if not o.eof and msize is not None and len(out) < msize:
            raise zlib.error('truncated zlib stream (%d of %d bytes)' % (len(out), msize))
        return out
    if comp == COMP_REFPACK:
        return refpack_decompress(raw)
    if comp == COMP_NONE:
        return raw
    if comp == COMP_DELETED:
        return b''
    # streamable (0xFFFE) - treat as raw, callers only sniff
    return raw


def pkg_path(root, rel):
    return os.path.join(ROOTS[root], rel.replace('/', os.sep))


class PackageReader:
    """Keeps one file handle open per package; read(off, fsize, comp) -> bytes."""

    def __init__(self, path):
        self.f = open(path, 'rb')

    def read(self, off, fsize, comp, msize=None):
        self.f.seek(off)
        return decompress(self.f.read(fsize), comp, msize)

    def close(self):
        self.f.close()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()
