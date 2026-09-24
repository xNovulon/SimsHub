"""Read and write Sims 4 .package files (DBPF 2.1).

Resources are copied as stored (compressed bytes, sizes and compression kind unchanged), so a
merged or rewritten package holds bit-identical resources. Decompression (zlib and the game's
internal RefPack) is only needed to look inside a resource.
"""
import os, struct, sys, zlib
from collections import namedtuple

Entry = namedtuple('Entry', 't g i off fsize msize comp committed')

ZLIB = 0x5A42
REFPACK = 0xFFFF
STREAMABLE = 0xFFFE
DELETED = 0xFFE0
NONE = 0x0000

HEADER = struct.Struct('<4sIIIIIIIIIIIIIIII28x')  # 96 bytes


class DBPFError(Exception):
    pass


def key_of(e):
    return (e.t, e.g, e.i)


def read_entries(f):
    """Index of an open package file as a list of Entry (instance as unsigned 64-bit)."""
    f.seek(0)
    head = f.read(96)
    if len(head) < 96 or head[:4] != b'DBPF':
        raise DBPFError('not a DBPF package')
    major, minor = struct.unpack_from('<II', head, 4)
    if major != 2:
        raise DBPFError('DBPF version %d.%d is not a Sims 4 package' % (major, minor))
    count, pos_low, size = struct.unpack_from('<III', head, 36)
    pos = struct.unpack_from('<I', head, 64)[0] or pos_low
    if count == 0:
        return []
    f.seek(pos)
    data = f.read(size)
    if len(data) < size:
        raise DBPFError('index runs past the end of the file')
    flags = struct.unpack_from('<I', data, 0)[0]
    p = 4
    const = {}
    for bit, name in ((1, 't'), (2, 'g'), (4, 'ih')):
        if flags & bit:
            const[name] = struct.unpack_from('<I', data, p)[0]
            p += 4
    out = []
    for _ in range(count):
        if 't' in const:
            t = const['t']
        else:
            t = struct.unpack_from('<I', data, p)[0]; p += 4
        if 'g' in const:
            g = const['g']
        else:
            g = struct.unpack_from('<I', data, p)[0]; p += 4
        if 'ih' in const:
            ih = const['ih']
        else:
            ih = struct.unpack_from('<I', data, p)[0]; p += 4
        il, off, fsize, msize = struct.unpack_from('<IIII', data, p)
        p += 16
        comp, committed = NONE, 1
        if fsize & 0x80000000:
            comp, committed = struct.unpack_from('<HH', data, p)
            p += 4
        out.append(Entry(t, g, (ih << 32) | il, off, fsize & 0x7FFFFFFF, msize, comp, committed))
    return out


def open_shared(path):
    """Open a file for reading without stopping others from renaming or deleting it meanwhile.

    Python's open() on Windows does not share delete access, so while SpeedKit reads a package the
    game, Windows or another tool could not rename it. This uses FILE_SHARE_READ|WRITE|DELETE.
    """
    if sys.platform != 'win32':
        return open(path, 'rb')
    import ctypes, msvcrt
    from ctypes import wintypes
    k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    GENERIC_READ, SHARE_ALL, OPEN_EXISTING, NORMAL = 0x80000000, 0x7, 3, 0x80
    h = k32.CreateFileW(os.path.abspath(path), GENERIC_READ, SHARE_ALL, None, OPEN_EXISTING, NORMAL, None)
    if h == wintypes.HANDLE(-1).value or h is None:
        err = ctypes.get_last_error()
        raise OSError(err, ctypes.FormatError(err), path)
    fd = msvcrt.open_osfhandle(h, os.O_RDONLY | getattr(os, 'O_BINARY', 0))
    return os.fdopen(fd, 'rb')


class Package:
    """A package opened for reading (without blocking renames). Use as a context manager."""

    def __init__(self, path):
        self.path = path
        self.f = open_shared(path)
        try:
            self.entries = read_entries(self.f)
        except Exception:
            self.f.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        self.f.close()

    def raw(self, e):
        """The resource exactly as stored in the file."""
        self.f.seek(e.off)
        data = self.f.read(e.fsize)
        if len(data) != e.fsize:
            raise DBPFError('resource %08X:%08X:%016X runs past the end of %s' % (e.t, e.g, e.i, self.path))
        return data

    def read(self, e):
        """The resource decompressed."""
        return decompress(self.raw(e), e.comp, e.msize)

    def find(self, t, g=None, i=None):
        return [e for e in self.entries if e.t == t and (g is None or e.g == g) and (i is None or e.i == i)]


def decompress(data, comp, msize=None):
    if comp == NONE:
        return data
    if comp == ZLIB:
        return zlib.decompress(data)
    if comp == REFPACK:
        return refpack_decompress(data)
    if comp == DELETED:
        return b''
    raise DBPFError('unsupported compression 0x%04X' % comp)


def refpack_decompress(src):
    """The game's internal compression (RefPack/QFS)."""
    flags, magic = src[0], src[1]
    if magic != 0xFB:
        raise DBPFError('bad RefPack header %02X%02X' % (flags, magic))
    wide = 4 if flags & 0x80 else 3
    p = 2
    if flags & 0x01:          # compressed size stored first
        p += wide
    size = int.from_bytes(src[p:p + wide], 'big')
    p += wide
    out = bytearray()
    n = len(src)
    while p < n:
        b0 = src[p]
        if b0 < 0x80:
            b1 = src[p + 1]; p += 2
            plain = b0 & 0x03
            count = ((b0 & 0x1C) >> 2) + 3
            dist = ((b0 & 0x60) << 3) + b1 + 1
        elif b0 < 0xC0:
            b1, b2 = src[p + 1], src[p + 2]; p += 3
            plain = (b1 >> 6) & 0x03
            count = (b0 & 0x3F) + 4
            dist = ((b1 & 0x3F) << 8) + b2 + 1
        elif b0 < 0xE0:
            b1, b2, b3 = src[p + 1], src[p + 2], src[p + 3]; p += 4
            plain = b0 & 0x03
            count = ((b0 & 0x0C) << 6) + b3 + 5
            dist = ((b0 & 0x10) << 12) + (b1 << 8) + b2 + 1
        elif b0 < 0xFC:
            p += 1
            plain = ((b0 & 0x1F) << 2) + 4
            count = 0
        else:
            p += 1
            plain = b0 & 0x03
            out += src[p:p + plain]
            break
        out += src[p:p + plain]
        p += plain
        if count:
            start = len(out) - dist
            if start < 0:
                raise DBPFError('RefPack copy before start of data')
            if dist >= count:
                out += out[start:start + count]
            else:
                for k in range(count):
                    out.append(out[start + k])
    if len(out) != size:
        raise DBPFError('RefPack produced %d bytes, header says %d' % (len(out), size))
    return bytes(out)


class PackageWriter:
    """Write a new package. Resources are added as stored bytes; the file appears only on close().

        with PackageWriter(path) as w:
            w.add_raw(entry, raw_bytes)          # copy from another package unchanged
            w.add((t, g, i), data)               # new resource, zlib-compressed
    """

    def __init__(self, path):
        self.path = path
        self.tmp = path + '.writing'
        self.f = open(self.tmp, 'wb')
        self.f.write(b'\0' * 96)
        self.index = []
        self.keys = set()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.close()
        else:
            self.abort()

    def _put(self, t, g, i, raw, msize, comp, committed=1):
        k = (t, g, i)
        if k in self.keys:
            raise DBPFError('resource %08X:%08X:%016X added twice' % k)
        pos = self.f.tell()
        if pos + len(raw) > 0xFFFFFFFF:
            raise DBPFError('package would pass 4 GiB')
        self.f.write(raw)
        self.index.append((t, g, i, pos, len(raw), msize, comp, committed))
        self.keys.add(k)

    def add_raw(self, e, raw):
        if len(raw) != e.fsize:
            raise DBPFError('raw size %d does not match the entry (%d)' % (len(raw), e.fsize))
        self._put(e.t, e.g, e.i, raw, e.msize, e.comp, e.committed)

    def add(self, key, data, compress=True):
        t, g, i = key
        if compress and len(data) > 64:
            packed = zlib.compress(data, 9)
            if len(packed) < len(data):
                return self._put(t, g, i, packed, len(data), ZLIB)
        self._put(t, g, i, data, len(data), NONE)

    def size(self):
        return self.f.tell()

    def close(self):
        pos = self.f.tell()
        body = bytearray(struct.pack('<I', 0))
        for t, g, i, off, fsize, msize, comp, committed in self.index:
            body += struct.pack('<IIIIIIIHH', t, g, i >> 32, i & 0xFFFFFFFF, off, fsize | 0x80000000, msize, comp, committed)
        self.f.write(body)
        if pos + len(body) > 0xFFFFFFFF:
            self.abort()
            raise DBPFError('package would pass 4 GiB')
        self.f.seek(0)
        self.f.write(HEADER.pack(b'DBPF', 2, 1, 0, 0, 0, 0, 0, 0, len(self.index), 0, len(body), 0, 0, 0, 3, pos))
        self.f.flush()
        os.fsync(self.f.fileno())
        self.f.close()
        os.replace(self.tmp, self.path)

    def abort(self):
        try:
            self.f.close()
        finally:
            if os.path.exists(self.tmp):
                os.remove(self.tmp)
