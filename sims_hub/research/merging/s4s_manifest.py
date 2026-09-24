"""Decode / encode the Sims 4 Studio merged-package manifest (resource type 0x7FB6AD8A).

Type id   0x7FB6AD8A = FNV-1 32-bit hash of "s4smergedpackagemanifest" (S4S class
          S4Studio.Data.IO.Package.S4SMergedPackageManifest; its static Type field is
          FNV.Hash32("S4SMergedPackageManifest"), and S4S hashes lower-cased).
Key       S4S writes it as (0x7FB6AD8A, group 0, instance 0), zlib-compressed (0x5A42), as the
          first resource (offset 96). S4S *reads* it by type only (first resource of that type).

Payload (little-endian, verified byte-exact against all 165 manifests in this library):

  off  size  field
  0    u32   version                      always 1 (S4S sets 1, never checks it on read)
  4    FOLDER root                         S4S names the root "" (empty)

  FOLDER :=
       u32   name_len                      byte length (UTF-8), no terminator
       ...   name                          UTF-8
       u32   folder_count
       FOLDER[folder_count]                sub-folders, recursive (S4S "merge folder" keeps
                                           the source directory tree; Batch/window merge = flat)
       u32   package_count
       PACKAGE[package_count]

  PACKAGE :=
       u32   name_len, name (UTF-8)        source file name WITHOUT ".package"
       i32   resource_count
       KEY[resource_count]                 16 bytes each, instance first:
            u64 instance, u32 type, u32 group

  For the usual flat manifest that is: 01000000 | 00000000 (root name "") | 00000000 (no
  sub-folders) | u32 package_count | packages...  - i.e. what looks like "version + 8 zero
  bytes + count" in a hex dump.

Unmerge (S4S PackageMergeUtility.UnmergeMergedFolder): for every PACKAGE it creates
<out>/<folder path>/<name>.package and, for each KEY, looks the full TGI up in the merged
package's index; found -> raw (still-compressed) bytes copied; not found -> silently skipped.
So what S4S needs from a package WE build, to be able to un-merge it:
  1. one resource of type 0x7FB6AD8A (use group 0 / instance 0 like S4S), data zlib or
     uncompressed, in the layout above;
  2. every KEY listed must exist in the index with exactly that type/group/instance -
     otherwise that resource is silently lost from the un-merged file;
  3. every resource we want back must be listed under some PACKAGE (resources not listed
     are dropped by un-merge);
  4. names must be valid file names (no path separators; duplicates in the same folder are
     fused into one entry by S4S when merging).
S4S also refuses to merge beyond 2 GB ("Merged package cannot exceed 2GB", checked against
0x7FFFFFFF) and, when a source is itself merged, flattens that source's manifest into the
new one (keeping folder paths). Duplicate TGIs: first source wins (later copies skipped),
but each source's manifest entry still lists the key, so un-merge re-creates the duplicate.

usage:
  python s4s_manifest.py <package> [--json] [--layout] [--verify]
  python s4s_manifest.py --selftest      (round-trip every manifest in library.sqlite)
"""
import argparse
import json
import os
import sqlite3
import struct
import sys
import zlib

MANIFEST_TYPE = 0x7FB6AD8A
COMP_ZLIB = 0x5A42


def fnv1_32(s):
    h = 0x811C9DC5
    for c in s.lower().encode('utf-8'):
        h = (h * 0x01000193) & 0xFFFFFFFF
        h ^= c
    return h


assert fnv1_32('S4SMergedPackageManifest') == MANIFEST_TYPE


class Folder:
    def __init__(self, name='', folders=None, packages=None):
        self.name, self.folders, self.packages = name, folders or [], packages or []

    def walk(self, prefix=''):
        """yield (folder_path, package) for every package, depth-first like S4S."""
        path = (prefix + '/' + self.name).strip('/') if self.name else prefix
        for p in self.packages:
            yield path, p
        for f in self.folders:
            yield from f.walk(path)

    def to_json(self):
        return {'name': self.name, 'folders': [f.to_json() for f in self.folders],
                'packages': [p.to_json() for p in self.packages]}


class Package:
    def __init__(self, name, keys=None):
        self.name, self.keys = name, keys or []   # keys: [(type, group, instance)]

    def to_json(self):
        return {'name': self.name, 'resources': len(self.keys),
                'keys': ['%08X:%08X:%016X' % k for k in self.keys]}


class Manifest:
    def __init__(self, version=1, root=None):
        self.version, self.root = version, root or Folder('')

    def packages(self):
        return list(self.root.walk())

    def to_json(self, keys=False):
        d = {'version': self.version, 'root': self.root.to_json()}
        if not keys:
            def strip(f):
                for p in f['packages']:
                    p.pop('keys')
                for g in f['folders']:
                    strip(g)
            strip(d['root'])
        return d


# ------------------------------------------------------------------ decode
def parse(data, layout=None):
    """bytes (decompressed) -> Manifest. `layout` (list) receives (offset, size, field, value)."""
    p = 0

    def rd(fmt, field):
        nonlocal p
        v = struct.unpack_from(fmt, data, p)
        if layout is not None:
            layout.append((p, struct.calcsize(fmt), field, v if len(v) > 1 else v[0]))
        p += struct.calcsize(fmt)
        return v if len(v) > 1 else v[0]

    def rstr(field):
        nonlocal p
        n = rd('<I', field + '.len')
        s = data[p:p + n].decode('utf-8')
        if layout is not None:
            layout.append((p, n, field, s))
        p += n
        return s

    def folder(depth):
        nonlocal p
        f = Folder(rstr('folder.name'))
        for _ in range(rd('<I', 'folder.folder_count')):
            f.folders.append(folder(depth + 1))
        for _ in range(rd('<I', 'folder.package_count')):
            name = rstr('package.name')
            cnt = rd('<i', 'package.resource_count')
            keys = []
            if layout is not None and cnt:
                layout.append((p, 16 * cnt, 'package.keys[%d] (u64 instance,u32 type,u32 group)' % cnt, None))
            for i, t, g in struct.iter_unpack('<QII', data[p:p + 16 * cnt]):
                keys.append((t, g, i))
            p += 16 * cnt
            f.packages.append(Package(name, keys))
        return f

    version = rd('<I', 'version')
    m = Manifest(version, folder(0))
    if p != len(data):
        raise ValueError('trailing %d bytes after manifest' % (len(data) - p))
    return m


# ------------------------------------------------------------------ encode
def build(manifest):
    out = bytearray(struct.pack('<I', manifest.version))

    def wstr(s):
        b = s.encode('utf-8')
        out.extend(struct.pack('<I', len(b)))
        out.extend(b)

    def folder(f):
        wstr(f.name)
        out.extend(struct.pack('<I', len(f.folders)))
        for g in f.folders:
            folder(g)
        out.extend(struct.pack('<I', len(f.packages)))
        for pk in f.packages:
            if any(c in pk.name for c in '\\/:*?"<>|'):
                raise ValueError('invalid file name in manifest: %r' % pk.name)
            wstr(pk.name)
            out.extend(struct.pack('<i', len(pk.keys)))
            for t, g, i in pk.keys:
                out.extend(struct.pack('<QII', i & 0xFFFFFFFFFFFFFFFF, t, g))

    folder(manifest.root)
    return bytes(out)


def build_resource(manifest, level=9):
    """-> (type, group, instance, stored_bytes, mem_size, compression) ready for a DBPF writer."""
    raw = build(manifest)
    return MANIFEST_TYPE, 0, 0, zlib.compress(raw, level), len(raw), COMP_ZLIB


def from_sources(sources):
    """sources: iterable of (name_without_ext, [(t,g,i), ...]) in merge order -> flat Manifest."""
    root = Folder('')
    byname = {}
    for name, keys in sources:
        pk = byname.get(name)
        if pk is None:
            pk = byname[name] = Package(name, [])
            root.packages.append(pk)
        seen = set(pk.keys)
        for k in keys:
            if k[0] == MANIFEST_TYPE or k in seen:
                continue
            seen.add(k)
            pk.keys.append(k)
    return Manifest(1, root)


# ------------------------------------------------------------------ package access (read-only)
def read_index(path):
    with open(path, 'rb') as f:
        head = f.read(96)
        if head[:4] != b'DBPF':
            raise ValueError('not a DBPF package')
        count, pos_low, size = struct.unpack_from('<III', head, 36)
        pos = struct.unpack_from('<I', head, 64)[0] or pos_low
        f.seek(pos)
        data = f.read(size)
    flags = struct.unpack_from('<I', data, 0)[0]
    p, const = 4, {}
    for bit, key in ((1, 't'), (2, 'g'), (4, 'ih')):
        if flags & bit:
            const[key] = struct.unpack_from('<I', data, p)[0]
            p += 4
    out = []
    for _ in range(count):
        vals = {}
        for key in ('t', 'g', 'ih'):
            if key in const:
                vals[key] = const[key]
            else:
                vals[key] = struct.unpack_from('<I', data, p)[0]
                p += 4
        il, off, fsize, msize = struct.unpack_from('<IIII', data, p)
        p += 16
        comp = 0
        if fsize & 0x80000000:
            comp = struct.unpack_from('<H', data, p)[0]
            p += 4
        out.append((vals['t'], vals['g'], (vals['ih'] << 32) | il, off, fsize & 0x7FFFFFFF, msize, comp))
    return out


def read_manifest(path, layout=None):
    idx = read_index(path)
    ent = next((e for e in idx if e[0] == MANIFEST_TYPE), None)
    if ent is None:
        return None, idx, None
    t, g, i, off, fs, ms, comp = ent
    with open(path, 'rb') as f:
        f.seek(off)
        raw = f.read(fs)
    data = zlib.decompress(raw) if comp == COMP_ZLIB else raw
    return parse(data, layout), idx, ent


def verify(manifest, idx):
    """How an S4S un-merge of this package would go."""
    live = {(t, g, i) for t, g, i, off, fs, ms, comp in idx if comp != 0xFFE0 and t != MANIFEST_TYPE}
    listed, dup = set(), 0
    missing = []
    for path, pk in manifest.packages():
        for k in pk.keys:
            if k in listed:
                dup += 1
            listed.add(k)
            if k not in live:
                missing.append((path + '/' + pk.name).strip('/') + ': %08X:%08X:%016X' % k)
    unlisted = live - listed
    names = [(path + '/' + pk.name).strip('/').lower() for path, pk in manifest.packages()]
    return {
        'source_packages': len(names),
        'listed_keys': sum(len(pk.keys) for _, pk in manifest.packages()),
        'unique_listed': len(listed),
        'keys_in_several_sources': dup,
        'index_resources': len(live),
        'listed_but_missing (lost on unmerge)': len(missing),
        'unlisted (dropped on unmerge)': len(unlisted),
        'duplicate_source_names': len(names) - len(set(names)),
        'missing_examples': missing[:5],
        'unlisted_types': sorted({'%08X' % k[0] for k in unlisted})[:20],
    }


def selftest():
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, here)
    from dbpf_read import DB, pkg_path
    db = sqlite3.connect(DB)
    rows = db.execute('select p.root, p.rel, r.off, r.fsize, r.comp, r.g, r.i from res r join pkg p on p.id = r.pkg '
                      'where r.t = ?', (MANIFEST_TYPE,)).fetchall()
    ok = bad = 0
    stats = {'folders': 0, 'packages': 0, 'keys': 0, 'nonzero_gi': 0, 'max_sources': 0}
    for root, rel, off, fs, comp, g, i in rows:
        with open(pkg_path(root, rel), 'rb') as f:
            f.seek(off)
            raw = f.read(fs)
        data = zlib.decompress(raw) if comp == COMP_ZLIB else raw
        m = parse(data)
        if build(m) == data:
            ok += 1
        else:
            bad += 1
            print('MISMATCH', rel)
        pk = m.packages()
        stats['folders'] += len(m.root.folders)
        stats['packages'] += len(pk)
        stats['keys'] += sum(len(p.keys) for _, p in pk)
        stats['nonzero_gi'] += (g != 0 or i != 0)
        stats['max_sources'] = max(stats['max_sources'], len(pk))
    print('round-trip byte-exact: %d ok, %d mismatch; %s' % (ok, bad, stats))
    return bad == 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('package', nargs='?')
    ap.add_argument('--json', action='store_true', help='dump manifest as JSON (with keys)')
    ap.add_argument('--layout', action='store_true', help='print field-by-field offsets (first 40 fields)')
    ap.add_argument('--verify', action='store_true', help='compare manifest with the package index')
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        sys.exit(0 if selftest() else 1)
    if not a.package:
        ap.error('package path required')
    layout = [] if a.layout else None
    m, idx, ent = read_manifest(a.package, layout)
    if m is None:
        print('no S4S manifest (type %08X) - S4S will say "not a merged package"' % MANIFEST_TYPE)
        return
    t, g, i, off, fs, ms, comp = ent
    print('manifest key %08X:%08X:%016X at offset %d, stored %d bytes, %d decompressed, compression 0x%04X'
          % (t, g, i, off, fs, ms, comp))
    if layout is not None:
        for o, n, field, v in layout[:40]:
            print('  +%06X %6d  %-45s %s' % (o, n, field, '' if v is None else repr(v)[:60]))
    if a.json:
        print(json.dumps(m.to_json(keys=True), indent=1))
    else:
        for path, pk in m.packages()[:50]:
            print('  %-70s %6d keys' % ((path + '/' + pk.name).strip('/'), len(pk.keys)))
        if len(m.packages()) > 50:
            print('  ... %d more' % (len(m.packages()) - 50))
    if a.verify:
        print(json.dumps(verify(m, idx), indent=1))


if __name__ == '__main__':
    main()
