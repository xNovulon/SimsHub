"""Micro-benchmark: cost of reading N small packages vs 1 merged package with the same resources.

Measures what the game must do per file at startup before it can use any resource: open the
file, read the 96-byte DBPF header and the index. Uses FILE_FLAG_NO_BUFFERING (Windows) so the
OS file cache is bypassed and every read reaches the device, plus a normal (warm cache) pass.
Everything is created under research/merging/bench/ (synthetic data, no game or mod files).

    python bench_pkgcount.py [n_files] [res_per_file]
"""
import ctypes
import os
import random
import struct
import sys
import time
from ctypes import wintypes

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.join(HERE, 'bench')

k32 = ctypes.WinDLL('kernel32', use_last_error=True)
k32.CreateFileW.restype = wintypes.HANDLE
k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                            wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
k32.ReadFile.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
                         wintypes.LPVOID]
k32.SetFilePointerEx.argtypes = [wintypes.HANDLE, ctypes.c_longlong, ctypes.POINTER(ctypes.c_longlong),
                                 wintypes.DWORD]
k32.VirtualAlloc.restype = wintypes.LPVOID
k32.VirtualAlloc.argtypes = [wintypes.LPVOID, ctypes.c_size_t, wintypes.DWORD, wintypes.DWORD]
GENERIC_READ, OPEN_EXISTING, NO_BUF, SHARE_READ = 0x80000000, 3, 0x20000000, 1
INVALID = wintypes.HANDLE(-1).value
SECTOR = 4096


def write_package(path, resources):
    """resources: [(t, g, i, bytes)] -> minimal valid DBPF 2.1 package (uncompressed)."""
    body = bytearray()
    entries = []
    for t, g, i, data in resources:
        entries.append((t, g, i, 96 + len(body), len(data)))
        body += data
    index = bytearray(struct.pack('<I', 0))
    for t, g, i, off, size in entries:
        index += struct.pack('<IIIIIII', t, g, i >> 32, i & 0xFFFFFFFF, off, size, size)
    head = bytearray(96)
    head[0:4] = b'DBPF'
    struct.pack_into('<II', head, 4, 2, 1)
    struct.pack_into('<III', head, 36, len(entries), 0, len(index))
    struct.pack_into('<I', head, 60, 3)
    struct.pack_into('<I', head, 64, 96 + len(body))
    with open(path, 'wb') as f:
        f.write(head); f.write(body); f.write(index)


def read_unbuffered(path, buf):
    h = k32.CreateFileW(path, GENERIC_READ, SHARE_READ, None, OPEN_EXISTING, NO_BUF, None)
    if h == INVALID:
        raise OSError(ctypes.get_last_error())
    got = wintypes.DWORD()
    k32.ReadFile(h, buf, SECTOR, ctypes.byref(got), None)
    head = ctypes.string_at(buf, 96)
    count, _, size = struct.unpack_from('<III', head, 36)
    pos = struct.unpack_from('<I', head, 64)[0]
    start = pos - pos % SECTOR
    length = ((pos + size - start) + SECTOR - 1) // SECTOR * SECTOR
    k32.SetFilePointerEx(h, start, None, 0)
    k32.ReadFile(h, buf, length, ctypes.byref(got), None)
    k32.CloseHandle(h)
    return count


def read_buffered(path):
    with open(path, 'rb') as f:
        head = f.read(96)
        count, _, size = struct.unpack_from('<III', head, 36)
        f.seek(struct.unpack_from('<I', head, 64)[0])
        f.read(size)
    return count


def main(n_files=2000, per=20):
    os.makedirs(BENCH, exist_ok=True)
    small_dir = os.path.join(BENCH, 'small')
    os.makedirs(small_dir, exist_ok=True)
    merged = os.path.join(BENCH, 'merged.package')
    rnd = random.Random(1)
    allres = []
    if not os.path.exists(merged) or len(os.listdir(small_dir)) != n_files:
        for k in range(n_files):
            res = [(0x034AEECB, 0x80000000, rnd.getrandbits(64), os.urandom(rnd.randint(500, 3000)))
                   for _ in range(per)]
            write_package(os.path.join(small_dir, 'p%05d.package' % k), res)
            allres += res
        write_package(merged, allres)
    files = sorted(os.path.join(small_dir, x) for x in os.listdir(small_dir))
    buf = k32.VirtualAlloc(None, 64 << 20, 0x3000, 0x04)
    out = {}
    for label, paths in (('%d small packages' % len(files), files), ('1 merged package', [merged])):
        for mode in ('unbuffered', 'warm'):
            best = []
            for rep in range(3):
                t0 = time.perf_counter()
                n = 0
                for p in paths:
                    n += read_unbuffered(p, buf) if mode == 'unbuffered' else read_buffered(p)
                best.append(time.perf_counter() - t0)
            out[(label, mode)] = (min(best), max(best), n)
            print('%-22s %-10s  min %.3fs  max %.3fs  (%d resources indexed)' % (label, mode, min(best), max(best), n))
    s_small = out[('%d small packages' % len(files), 'unbuffered')][0]
    s_big = out[('1 merged package', 'unbuffered')][0]
    print('per-file overhead (unbuffered): %.3f ms/file' % ((s_small - s_big) / len(files) * 1000))
    # directory enumeration cost (the game walks Mods recursively)
    t0 = time.perf_counter()
    for _ in range(3):
        sum(1 for _ in os.scandir(small_dir))
    print('directory scan of %d entries: %.2f ms' % (len(files), (time.perf_counter() - t0) / 3 * 1000))


if __name__ == '__main__':
    main(*[int(x) for x in sys.argv[1:]])
