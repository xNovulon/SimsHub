"""Demonstrates the order in which Windows FindFirstFileW/FindNextFileW (what TS4_x64.exe's
resource-config walker uses, no sorting) returns entries on NTFS, versus Explorer's
"logical" sort and Python's plain sorted().  Creates a throwaway tree ONLY under this
research folder, walks it depth-first exactly like the game (directories are descended
into at the point they are encountered), prints the resulting load order, then deletes it.
"""
import ctypes, os, shutil, functools
from ctypes import wintypes

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '_order_demo_tmp')

names_files = ['!!!Lighting.package', '_Overrides.package', 'zzz_Last.package', '~tilde.package',
               '000_first.package', '10_x.package', '9_x.package', 'Apple.package', 'apple2.package',
               '[TS4]thing.package', '@at.package', 'Zeta.package', 'aa_inner.package']
names_dirs = ['AA', '_Folder', 'zzz', '!Dir', 'b_dir']

shutil.rmtree(ROOT, ignore_errors=True)
os.makedirs(ROOT)
for d in names_dirs:
    os.makedirs(os.path.join(ROOT, d))
    open(os.path.join(ROOT, d, 'inner.package'), 'wb').close()
for n in names_files:
    open(os.path.join(ROOT, n), 'wb').close()

k32 = ctypes.WinDLL('kernel32', use_last_error=True)


class WIN32_FIND_DATAW(ctypes.Structure):
    _fields_ = [('dwFileAttributes', wintypes.DWORD), ('ftCreationTime', wintypes.FILETIME),
                ('ftLastAccessTime', wintypes.FILETIME), ('ftLastWriteTime', wintypes.FILETIME),
                ('nFileSizeHigh', wintypes.DWORD), ('nFileSizeLow', wintypes.DWORD),
                ('dwReserved0', wintypes.DWORD), ('dwReserved1', wintypes.DWORD),
                ('cFileName', wintypes.WCHAR * 260), ('cAlternateFileName', wintypes.WCHAR * 14)]


k32.FindFirstFileW.restype = wintypes.HANDLE
k32.FindFirstFileW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(WIN32_FIND_DATAW)]
k32.FindNextFileW.argtypes = [wintypes.HANDLE, ctypes.POINTER(WIN32_FIND_DATAW)]
k32.FindClose.argtypes = [wintypes.HANDLE]
INVALID = wintypes.HANDLE(-1).value


def find(dirpath):
    fd = WIN32_FIND_DATAW()
    h = k32.FindFirstFileW(dirpath + '\\*', ctypes.byref(fd))
    if h == INVALID:
        return
    try:
        while True:
            yield fd.cFileName, bool(fd.dwFileAttributes & 0x10)
            if not k32.FindNextFileW(h, ctypes.byref(fd)):
                break
    finally:
        k32.FindClose(h)


def walk(dirpath, rel=''):
    for name, isdir in find(dirpath):
        if name in ('.', '..'):
            continue
        if isdir:
            yield from walk(os.path.join(dirpath, name), rel + name + '/')
        elif name.lower().endswith('.package'):
            yield rel + name


order = list(walk(ROOT))
shlw = ctypes.WinDLL('shlwapi')
shlw.StrCmpLogicalW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
explorer = sorted(order, key=functools.cmp_to_key(lambda a, b: shlw.StrCmpLogicalW(a, b)))
print('FindFirstFileW depth-first order (= TS4 load order within one Priority):')
for i, p in enumerate(order, 1):
    print(f'  {i:2d}. {p}')
print('\nExplorer (StrCmpLogicalW) order of the same relative paths, for comparison:')
print('  ' + ' | '.join(explorer))
print('\nos.scandir order equals FindFirstFileW order:',
      [e.name for e in os.scandir(ROOT)] == [n for n, _ in find(ROOT) if n not in ('.', '..')])
shutil.rmtree(ROOT)
