"""Sims 4 Studio merged-package manifest: read, write and edit it.

When Sims 4 Studio (S4S) merges packages it adds one resource that lists which source package every
resource came from; "Unmerge" uses it to rebuild the original files. This module is a byte-exact
codec for that resource so SpeedKit can build packages S4S can still unmerge, and can keep an
existing manifest correct after removing resources from a merged pack.

Facts it relies on (research/merging + the skeptic's corrections in research_results.json; checked
against S4S 3.2.6.3's own IL and by running its merge/unmerge code on scratch files):
  * Resource type 0x7FB6AD8A = FNV-1 32 of "s4smergedpackagemanifest". S4S writes it as key
    7FB6AD8A:00000000:0000000000000000, zlib, first in the file, but it finds it by TYPE only (the
    first resource of that type) and does not check version, position or compression.
    So never put any other resource of that type into a package.
  * Payload, little-endian:
        u32 version (always 1; S4S never checks it)
        FOLDER  := u32 name_len, UTF-8 name, u32 n_folders, FOLDER[n], u32 n_sources, SOURCE[n]
        SOURCE  := u32 name_len, UTF-8 name (file name WITHOUT ".package"), i32 n_keys,
                   n_keys x (u64 instance, u32 type, u32 group)      <- instance first
    The root folder is named "". Every merge in this library is flat (0 sub-folders).
  * Unmerge writes <folder path>/<name>.package for every source and copies each listed key that
    exists in the package (missing keys are skipped silently; resources listed nowhere are dropped).
    Names go through Path.Combine unchecked (separators / '..' / drive letters escape the output
    folder) and File.Create on a case-insensitive disk ('X' and 'x' become one file). Hence
    sanitize_name(): SpeedKit only ever WRITES safe, case-insensitively unique names, while
    decode()/encode() stay faithful to whatever S4S wrote (real manifests hold names with trailing
    spaces or dots and even ".package" inside the name).
  * A key listed under several sources is written to each on unmerge, with the winner's bytes.

    folder = decode(payload)             # Folder tree (root.version keeps the version field)
    payload == encode(folder)            # byte-exact for all 165 manifests in the library
    data = build_flat([('Some CC', [(t, g, i), ...]), ...])
    writer.add(MANIFEST_KEY, data)       # add it FIRST to a PackageWriter
"""
import re
import struct
import zlib

from .dbpf import Package, ZLIB, DELETED, decompress

MANIFEST_TYPE = 0x7FB6AD8A
MANIFEST_KEY = (MANIFEST_TYPE, 0, 0)

_RESERVED = ({'CON', 'PRN', 'AUX', 'NUL', 'CONIN$', 'CONOUT$'} | {'COM%s' % n for n in '123456789¹²³'}
             | {'LPT%s' % n for n in '123456789¹²³'})
# Windows-forbidden characters, control characters and lone surrogates (not encodable as UTF-8).
_BAD_CHARS = re.compile('[\\\\/:*?"<>|\\x00-\\x1f\\ud800-\\udfff]')
MAX_NAME = 180      # UTF-16 units; S4S appends ".package" (NTFS allows 255 per name) and joins it to a folder


def fnv1_32(text):
    """FNV-1 32-bit hash of the lower-cased text (how S4S derives the manifest type id)."""
    h = 0x811C9DC5
    for c in text.lower().encode('utf-8'):
        h = (h * 0x01000193) & 0xFFFFFFFF
        h ^= c
    return h


assert fnv1_32('S4SMergedPackageManifest') == MANIFEST_TYPE


class Source:
    """One source package inside a manifest: its name (no ".package") and its [(t, g, i)] keys."""

    def __init__(self, name, keys=None):
        self.name = name
        self.keys = list(keys or [])

    def __repr__(self):
        return 'Source(%r, %d keys)' % (self.name, len(self.keys))


class Folder:
    """A manifest folder. The root folder is named '' and also carries the manifest's version."""

    def __init__(self, name='', folders=None, sources=None, version=1):
        self.name = name
        self.folders = list(folders or [])
        self.sources = list(sources or [])
        self.version = version

    def walk(self, prefix=''):
        """Yield (folder_path, Source) for every source, depth-first in S4S order."""
        path = (prefix + '/' + self.name).strip('/') if self.name else prefix
        for s in self.sources:
            yield path, s
        for f in self.folders:
            yield from f.walk(path)

    def __repr__(self):
        return 'Folder(%r, %d folders, %d sources)' % (self.name, len(self.folders), len(self.sources))


# ------------------------------------------------------------------ decode / encode
def decode(data):
    """Decompressed manifest payload -> root Folder. Raises ValueError on a malformed payload."""
    p = 0

    def u32(fmt='<I'):
        nonlocal p
        if p + 4 > len(data):
            raise ValueError('manifest ends early at byte %d' % p)
        v = struct.unpack_from(fmt, data, p)[0]
        p += 4
        return v

    def text():
        nonlocal p
        n = u32()
        if p + n > len(data):
            raise ValueError('name runs past the end of the manifest at byte %d' % p)
        s = data[p:p + n].decode('utf-8')
        p += n
        return s

    def folder(depth):
        nonlocal p
        if depth > 64:
            raise ValueError('manifest folders nested too deep')
        f = Folder(text())
        for _ in range(u32()):
            f.folders.append(folder(depth + 1))
        for _ in range(u32()):
            name = text()
            count = u32('<i')
            if count < 0 or p + 16 * count > len(data):
                raise ValueError('bad key count %d for source %r' % (count, name))
            keys = [(t, g, i) for i, t, g in struct.iter_unpack('<QII', data[p:p + 16 * count])]
            p += 16 * count
            f.sources.append(Source(name, keys))
        return f

    version = u32()
    root = folder(0)
    root.version = version
    if p != len(data):
        raise ValueError('%d bytes left over after the manifest' % (len(data) - p))
    return root


def encode(folder):
    """Root Folder -> payload bytes, exactly as S4S lays it out. Names are written as given
    (use sanitize_name / check_names before building a manifest for a new package)."""
    out = bytearray(struct.pack('<I', folder.version))

    def text(s):
        b = s.encode('utf-8')
        out.extend(struct.pack('<I', len(b)))
        out.extend(b)

    def put(f):
        text(f.name)
        out.extend(struct.pack('<I', len(f.folders)))
        for sub in f.folders:
            put(sub)
        out.extend(struct.pack('<I', len(f.sources)))
        for s in f.sources:
            text(s.name)
            out.extend(struct.pack('<i', len(s.keys)))
            for t, g, i in s.keys:
                out.extend(struct.pack('<QII', i & 0xFFFFFFFFFFFFFFFF, t, g))

    put(folder)
    return bytes(out)


# ------------------------------------------------------------------ names
def fold_name(name):
    """Case-insensitive identity of a file name, for "same file on a Windows disk?" checks: every
    character upper-cased on its own (how NTFS compares names), then lower-cased. For ASCII this is
    name.lower(); it also catches pairs that differ only under one rule ('s'/'ſ', 'σ'/'ς', 'i'/'ı')."""
    return ''.join(c.upper() if len(c.upper()) == 1 else c for c in name).lower()


def _cap(s, limit):
    """s cut to at most `limit` UTF-16 code units (the unit Windows measures file names in)."""
    n = 0
    for k, c in enumerate(s):
        n += 2 if ord(c) > 0xFFFF else 1
        if n > limit:
            return s[:k]
    return s


def sanitize_name(name, taken=None):
    """A source name S4S can unmerge safely.

    Removes a trailing ".package" (S4S appends it), replaces path separators, ':' (drive letters),
    other characters Windows forbids and lone surrogates with '_', collapses '..', strips trailing dots
    and spaces, renames reserved device names (CON, NUL, COM1, COM¹...), caps the length at MAX_NAME
    UTF-16 units and never returns ''. With `taken` (a set of fold_name() keys already used in the same
    folder; for ASCII names that is simply the lower-cased name) the result is made unique ignoring
    case by appending " (2)", " (3)"... and its key is added to `taken`.
    """
    s = name.strip()
    if s.lower().endswith('.package'):
        s = s[:-len('.package')]
    s = _BAD_CHARS.sub('_', s)
    while '..' in s:
        s = s.replace('..', '.')
    s = s.rstrip(' .').lstrip(' ')
    if s.split('.')[0].strip().upper() in _RESERVED:
        s = '_' + s
    s = _cap(s, MAX_NAME).rstrip(' .') or '_'
    if taken is not None:
        base, n = s, 2
        while fold_name(s) in taken:
            suffix = ' (%d)' % n
            s = _cap(base, MAX_NAME - len(suffix)).rstrip(' .') + suffix
            n += 1
        taken.add(fold_name(s))
    return s


def check_names(folder):
    """Problems an S4S unmerge would have with this manifest's names: [(folder_path, name, problem)]."""
    out = []

    def visit(f, path):
        seen = set()
        for s in f.sources:
            if sanitize_name(s.name) != s.name:
                out.append((path, s.name, 'unsafe name'))
            if fold_name(s.name) in seen:
                out.append((path, s.name, 'same name as another source in this folder (ignoring case)'))
            seen.add(fold_name(s.name))
        for sub in f.folders:
            if sanitize_name(sub.name) != sub.name:
                out.append((path, sub.name, 'unsafe folder name'))
            visit(sub, (path + '/' + sub.name).strip('/'))

    visit(folder, '')
    return out


# ------------------------------------------------------------------ building and editing
def build_flat(sources):
    """Flat manifest payload for a package merged from `sources` = [(name, [(t, g, i), ...]), ...].

    Names are sanitized and made unique ignoring case (a second "x" becomes "x (2)", see fold_name); keys of the
    manifest type itself are left out; a key repeated inside one source is listed once. Store the
    result under MANIFEST_KEY as the package's first resource (PackageWriter.add(MANIFEST_KEY, data)).
    """
    root = Folder('')
    taken = set()
    for name, keys in sources:
        seen = set()
        kept = []
        for k in keys:
            k = (k[0], k[1], k[2] & 0xFFFFFFFFFFFFFFFF)
            if k[0] == MANIFEST_TYPE or k in seen:
                continue
            seen.add(k)
            kept.append(k)
        root.sources.append(Source(sanitize_name(name, taken), kept))
    return encode(root)


def sources_of(data):
    """{source name: set of (t, g, i)} for a manifest payload. Sources inside folders are named
    'folder/sub/name'; two entries with the same path are united."""
    out = {}
    for path, s in decode(data).walk():
        out.setdefault((path + '/' + s.name) if path else s.name, set()).update(s.keys)
    return out


def rewrite_without(data, removed_keys):
    """The manifest payload with every key in `removed_keys` taken out of every source. Sources and
    folders that become empty are dropped (ones that were already empty stay, as S4S wrote them)."""
    removed = {(t, g, i & 0xFFFFFFFFFFFFFFFF) for t, g, i in removed_keys}
    root = decode(data)

    def prune(f):
        kept_sources = []
        for s in f.sources:
            had = len(s.keys)
            s.keys = [k for k in s.keys if k not in removed]
            if s.keys or not had:
                kept_sources.append(s)
        f.sources = kept_sources
        kept_folders = []
        for sub in f.folders:
            was_empty = not sub.sources and not sub.folders
            prune(sub)
            if sub.sources or sub.folders or was_empty:
                kept_folders.append(sub)
        f.folders = kept_folders

    prune(root)
    return encode(root)


# ------------------------------------------------------------------ reading from a package
def payload(raw, comp, msize=None):
    """Decompress a stored manifest. zlib is read tolerantly: a few tools write streams without the
    final block / checksum, which S4S and the game accept."""
    if comp == ZLIB:
        d = zlib.decompressobj()
        out = d.decompress(raw)
        if not d.eof and msize is not None and len(out) < msize:
            raise ValueError('truncated zlib stream (%d of %d bytes)' % (len(out), msize))
        return out
    return decompress(raw, comp, msize)


def find_entry(pkg):
    """The entry S4S would use as the manifest (first of type 0x7FB6AD8A), or None."""
    return next((e for e in pkg.entries if e.t == MANIFEST_TYPE), None)


def read_payload(path_or_pkg):
    """Decompressed manifest payload of a package (path or open dbpf.Package), or None if unmerged."""
    if isinstance(path_or_pkg, Package):
        e = find_entry(path_or_pkg)
        return None if e is None else payload(path_or_pkg.raw(e), e.comp, e.msize)
    with Package(path_or_pkg) as p:
        return read_payload(p)


def read(path_or_pkg):
    """Root Folder of a package's manifest, or None if the package is not an S4S merge."""
    data = read_payload(path_or_pkg)
    return None if data is None else decode(data)


def unmerge_report(folder, entries):
    """What an S4S unmerge of a package would do, given its manifest and dbpf entries:
    {'sources', 'listed', 'missing' (listed keys not in the package: skipped), 'unlisted' (resources
    listed nowhere: dropped), 'name_problems'}."""
    live = {(e.t, e.g, e.i) for e in entries if e.comp != DELETED and e.t != MANIFEST_TYPE}
    listed = set()
    n = 0
    for _, s in folder.walk():
        n += 1
        listed.update(s.keys)
    return {'sources': n, 'listed': len(listed), 'missing': len(listed - live),
            'unlisted': len(live - listed), 'name_problems': len(check_names(folder))}


def main():
    import argparse
    import sys
    if hasattr(sys.stdout, 'reconfigure'):          # source names may hold any Unicode (CJK, mojibake)
        sys.stdout.reconfigure(errors='backslashreplace')
    ap = argparse.ArgumentParser(description='Show the Sims 4 Studio merge manifest of a package.')
    ap.add_argument('package')
    ap.add_argument('--keys', action='store_true', help='list every key')
    a = ap.parse_args()
    with Package(a.package) as p:
        root = read(p)
        if root is None:
            print('not an S4S merged package (no %08X resource)' % MANIFEST_TYPE)
            return
        rep = unmerge_report(root, p.entries)
    print('version %d; %d sources, %d keys listed, %d listed-but-missing, %d unlisted, %d name problems'
          % (root.version, rep['sources'], rep['listed'], rep['missing'], rep['unlisted'], rep['name_problems']))
    for path, s in root.walk():
        print('  %-70s %6d keys' % ((path + '/' + s.name).strip('/'), len(s.keys)))
        if a.keys:
            for k in s.keys:
                print('      %08X:%08X:%016X' % k)


if __name__ == '__main__':
    main()
