"""batchfix - CC that may need one of Sims 4 Studio's batch fixes, and which one (docs/batchfix.md).

The Hub never changes a CC file itself. It reads the files, matches them against a short list of well-known
problems that Sims 4 Studio (S4S) has a batch fix for, and tells the player which fix to run and why.

    store = Store(db_path)                          # data/batchfix.sqlite (beside library.sqlite)
    store.scan(lib, progress=..., skip=...)         # incremental: only new or changed files are read
    store.findings()                                # {fix id: [{'root', 'rel', 'parts', 'total', 'detail'}]}
    FIXES / FIX_BY_ID                               # what each fix is, its S4S menu path and its sources

Only problems that can be told from the file's own data are checked (sources in docs/batchfix.md):

  sliders_werewolf  HotSpotControl (0x8B18FF6E) version below 0x0F. The June 2022 update (Werewolves) made the
                    game ignore older ones; CmarNYC's TS4SliderConverter fixes them by raising the version to
                    0x0F and nothing else. S4S: CAS > "Update Sliders (Werewolf Patch)".
  eyes_infants      Eye color CAS parts (body type 35) for toddlers but without the infant age flag (0x80). Made
                    before infants (March 2023): infants can't use them, and default replacements give infants
                    the wrong (vampire) eyes. S4S: CAS > "Update Eye Colors for Infants (Infants Patch)".
  shoes_werewolves  Shoes (body type 8) for teens or older, human, whose "disabled for occult" field does not have
                    the werewolf bit (OccultType.WEREWOLF = 32; CAS parts before version 0x1F have no such field).
                    Werewolves then keep them on in wolf form. S4S: CAS > "Disable Shoes for Werewolves".
  nude_default      A new clothing part (not a replacement of an EA part) with a "default for body type" flag
                    (parameter flags bit 0, or flags 2 bits 1-2 in version 39+). The game may put it on sims as
                    their default - most visibly in the nude/bath outfit. S4S: CAS > "Disallow CC for Default
                    Garment".
  pets_patch        CAS parts older than version 0x20 (the layout before Cats & Dogs, November 2017, which added
                    the species field). S4S: CAS > "Update CAS CC Pets Patch".

CAS part layout (TS4SimRipper CASP.cs, research/usedcc/casp_simripper.cs; s4pi CASPFlags.cs for the flags): u32
version, u32 key-list offset, u32 preset count, name (7-bit length, UTF-16BE), f32 sort priority, u16 swatch
order, u32 outfit id, u32 material hash, u8 flags, [v39+] u8 flags2, [v50+] u16 layer id, exclude-part flags
([v51+] i32 count + u64 each, else u64 [+ u64 in v41+]), exclude-modifier-region flags (u64 in v37+, else u32),
i32 tag count + tags (u16 category + u32 value in v37+, else u16), u32 price, u32 title, u32 description,
[v43+] u32, u8 texture space, u32 body type, u32 body sub type, u32 age/gender, [v32+] u32 species, [v34+] u16
pack id + u8 pack flags + 9 bytes, else u8 (+u8 when not 0), u8 color count + u32 each, u8 buff key, u8 swatch
key, [v28+] u64 voice effect, [v30+] u8 material count (+ 3 x u32 when not 0), [v31+] u32 occult-disabled bits.

Nothing here writes to the game's folders. Results are kept per file (size + modified time), so a second check
reads only new or changed files.
"""
import json
import os
import sqlite3
import struct
import time
import zlib

from .dbpf import open_shared, decompress, DELETED, ZLIB
from .library import unsigned64

DETECT_VERSION = 1                 # bump when a detector changes: every file is read again
T_CASP = 0x034AEECB
T_HOTC = 0x8B18FF6E
HOTC_CURRENT = 0x0F
CASP_SPECIES = 0x20                # first CAS part version with a species field (Cats & Dogs)
CASP_OCCULT = 0x1F                 # first CAS part version with the occult-disabled bits
EA_MAX = 1 << 32                   # EA's CAS part ids are all below 2^32; bigger ones are new CC
BT_SHOES, BT_EYECOLOR = 8, 35
AGE_TODDLER, AGE_INFANT = 0x02, 0x80
AGE_TEEN_UP = 0x08 | 0x10 | 0x20 | 0x40
OCC_WEREWOLF = 32                  # OccultType.WEREWOLF (sims/occult/occult_enums.py); HUMAN 1, ALIEN 2 (s4pi)
SPECIES_HUMAN = 1
# clothing and accessories: hats, full body, tops, bottoms, shoes, accessories (9-27), socks, tights
CLOTHING = {1, 5, 6, 7, 8, 36, 42} | set(range(9, 28))
MAX_READ = 64 << 20                # a single resource bigger than this is not a CAS part or slider: skipped

S4S_PATH = ['Tools', 'Content Management', 'Batch Fixes']
SRC_S4S_INFO = 'https://sims4studio.com/thread/37124/batch-fix-information'
SRC_SRSLY = 'https://srslysims.net/tutorials/sims4studio_batchfix/'

FIXES = [
    {'id': 'sliders_werewolf', 'name': 'Update Sliders (Werewolf Patch)', 'section': 'CAS',
     'update': 'It came with the June 2022 game update (Werewolves).',
     'problem': 'Sliders made before the June 2022 game update stop working: moving them does nothing.',
     'what': 'sliders',
     'sources': ['https://sims4studio.com/thread/28677/studio-updates-werewolves-batch-fixes',
                 'https://github.com/Oops19/cmarNYC_TS4SliderConverter',
                 'https://modthesims.info/d/668332/', SRC_SRSLY]},
    {'id': 'eyes_infants', 'name': 'Update Eye Colors for Infants (Infants Patch)', 'section': 'CAS',
     'update': 'It came with the March 2023 game update (infants).',
     'problem': "Eye colors made before infants came can't be used by infants, and replacements of the game's eye "
                'colors can give infants the wrong eyes.',
     'what': 'eye colors',
     'sources': ['https://sims4studio.com/thread/31336/studio-updates-infant-patch-growing',
                 'https://www.patreon.com/posts/info-about-cc-80044208',
                 'https://sims4studio.com/thread/31299/infant-update-default-eye-replacements']},
    {'id': 'shoes_werewolves', 'name': 'Disable Shoes for Werewolves', 'section': 'CAS',
     'update': 'It came with the June 2022 game update (Werewolves).',
     'problem': 'Shoes that are not turned off for werewolves stay on when a Sim changes into a werewolf.',
     'what': 'shoes',
     'sources': ['https://sims4studio.com/thread/28904/studio-updates-revised-batch-fixes',
                 'https://sims4studio.com/thread/29014/help-werewolves-shoes',
                 'https://sims4studioofficial.tumblr.com/post/689424635086979072/studio-updates-with-more-werewolf-batch-fixes']},
    {'id': 'nude_default', 'name': 'Disallow CC for Default Garment', 'section': 'CAS',
     'update': 'It is not caused by a game update: the setting is copied from the game item the CC was made from.',
     'problem': 'Clothing marked as a default item can end up on Sims by itself, most often in their nude '
                '(bath) outfit.',
     'what': 'clothing items',
     'sources': ['https://sims4studio.com/thread/22091/disallow-default-garment-working-s4s', SRC_SRSLY,
                 'https://github.com/s4ptacle/Sims4Tools/blob/master/s4pi%20Wrappers/CASPartResource/CASPFlags.cs']},
    {'id': 'pets_patch', 'name': 'Update CAS CC Pets Patch', 'section': 'CAS',
     'update': 'It came with the November 2017 game update (Cats & Dogs).',
     'problem': 'Create a Sim items made before the Cats & Dogs update can go missing or show up wrong '
                '(for example a stiff "wooden doll" look).',
     'what': 'Create a Sim items',
     'sources': ['https://sims4studio.com/thread/11767/batch-fix-cas-cc',
                 'https://sims4studio.com/thread/10933/thread-reports-post-pets-problems', SRC_SRSLY]},
]
FIX_BY_ID = {f['id']: f for f in FIXES}
for _f in FIXES:
    _f['menu'] = S4S_PATH + [_f['section'], _f['name']]


# ------------------------------------------------------------------------------------------ reading a CAS part
def _read_7bit(data, p):
    n = shift = 0
    while True:
        b = data[p]
        p += 1
        n |= (b & 0x7F) << shift
        if not b & 0x80:
            return n, p
        shift += 7
        if shift > 28:
            raise ValueError('bad length')


def casp_fields(data):
    """The fields the detectors need, as far as they could be read: {'version', 'flags', 'flags2', 'body_type',
    'age_gender', 'species', 'occult'} ('occult' None before version 0x1F; missing keys when the part stops
    parsing before them). None when not even the version is there."""
    if len(data) < 16:
        return None
    v = struct.unpack_from('<I', data, 0)[0]
    out = {'version': v}
    if v < 0x1B or v > 0x40:                     # layout not known: only the version is used
        return out
    try:
        nlen, p = _read_7bit(data, 12)
        p += nlen + 4 + 2 + 4 + 4                # name, sort priority, swatch order, outfit id, material hash
        out['flags'] = data[p]
        p += 1
        out['flags2'] = 0
        if v >= 39:
            out['flags2'] = data[p]
            p += 1
        if v >= 50:
            p += 2
        if v >= 51:
            n = struct.unpack_from('<i', data, p)[0]
            if not 0 <= n < 64:
                return out
            p += 4 + 8 * n
        else:
            p += 8 + (8 if v >= 41 else 0)
        p += 8 if v >= 37 else 4
        nt = struct.unpack_from('<i', data, p)[0]
        if not 0 <= nt < 4096:
            return out
        p += 4 + nt * (6 if v >= 37 else 4)
        p += 12 + (4 if v >= 43 else 0) + 1
        bt, _sub, ag = struct.unpack_from('<III', data, p)
        p += 12
        if not 0 < bt < 512:
            return out
        out['body_type'], out['age_gender'] = bt, ag
        out['species'] = SPECIES_HUMAN
        if v >= 32:
            out['species'] = struct.unpack_from('<I', data, p)[0]
            p += 4
        if v >= 34:
            p += 2 + 1 + 9
        else:
            p += 2 if data[p] else 1
        p += 1 + 4 * data[p]                     # swatch colors
        p += 2                                   # buff key, swatch key
        if v >= 28:
            p += 8
        if v >= 30:
            p += 1 + (12 if data[p] else 0)
        out['occult'] = None
        if v >= 31:
            out['occult'] = struct.unpack_from('<I', data, p)[0]
    except (struct.error, IndexError, ValueError):
        pass
    return out


# ------------------------------------------------------------------------------------------ the detectors
def casp_problems(info, instance):
    """The fix ids one CAS part may need (a list, usually empty)."""
    if not info:
        return []
    out = []
    v = info['version']
    if 0 < v < CASP_SPECIES:
        out.append('pets_patch')
    bt, ag = info.get('body_type'), info.get('age_gender')
    if bt is None or ag is None:
        return out
    if bt == BT_EYECOLOR and ag & AGE_TODDLER and not ag & AGE_INFANT:
        out.append('eyes_infants')
    if bt == BT_SHOES and ag & AGE_TEEN_UP and info.get('species', SPECIES_HUMAN) == SPECIES_HUMAN and \
            'occult' in info and not (info['occult'] or 0) & OCC_WEREWOLF:
        out.append('shoes_werewolves')
    if bt in CLOTHING and instance >= EA_MAX and (info.get('flags', 0) & 0x01 or info.get('flags2', 0) & 0x06):
        out.append('nude_default')
    return out


def hotc_problems(data):
    if len(data) < 4:
        return []
    v = struct.unpack_from('<I', data, 0)[0]
    return ['sliders_werewolf'] if v < HOTC_CURRENT else []


def _head(raw, comp, msize, want):
    """The first `want` bytes of a resource (zlib ones are only partly unpacked)."""
    if comp == ZLIB:
        d = zlib.decompressobj()
        return d.decompress(raw, want)
    return decompress(raw, comp, msize)[:want]


def check_package(path, rows):
    """{fix id: {'parts': n, 'detail': str}} for one package. rows: (t, i, off, fsize, msize, comp) of its CAS
    parts and sliders. Parts that can't be read are skipped (the CC browser reports damaged files)."""
    hits, totals, versions = {}, {}, {}
    with open_shared(path) as f:
        for t, i, off, fs, ms, comp in rows:
            if comp == DELETED or fs <= 0 or fs > MAX_READ:
                continue
            try:
                f.seek(off)
                raw = f.read(fs)
                if t == T_HOTC:
                    head = _head(raw, comp, ms, 8)
                    probs = hotc_problems(head)
                    totals['sliders'] = totals.get('sliders', 0) + 1
                    if probs:
                        versions.setdefault('sliders_werewolf', set()).add(struct.unpack_from('<I', head)[0])
                else:
                    info = casp_fields(_head(raw, comp, ms, 1 << 16))
                    totals['cas'] = totals.get('cas', 0) + 1
                    probs = casp_problems(info, unsigned64(i))
                    if 'pets_patch' in probs:
                        versions.setdefault('pets_patch', set()).add(info['version'])
            except Exception:
                continue
            for fid in probs:
                hits[fid] = hits.get(fid, 0) + 1
    out = {}
    for fid, n in hits.items():
        total = totals.get('sliders' if fid == 'sliders_werewolf' else 'cas', n)
        out[fid] = {'parts': n, 'total': total, 'versions': sorted(versions.get(fid, ()))}
    return out


def why(fid, hit):
    """One plain sentence: why this file may need this fix."""
    n, total = hit.get('parts', 1), hit.get('total', 0) or 0
    one = n == 1 and total <= 1
    count = ('All %d' % n) if n == total else ('%d of %d' % (n, total)) if total > n else ('%d' % n)
    vers = '/'.join(str(x) for x in hit.get('versions') or [])
    if fid == 'sliders_werewolf':
        what = 'The slider uses' if one else '%s sliders use' % count
        return '%s the format from before the June 2022 game update%s.' % (
            what, ' (format %s; the game reads %d now)' % (vers, HOTC_CURRENT) if vers else '')
    if fid == 'eyes_infants':
        what = 'The eye color is' if one else '%s eye colors are' % count
        return '%s made for toddlers and older, but not marked for infants.' % what
    if fid == 'shoes_werewolves':
        what = 'The shoes are' if one else '%s shoe items are' % count
        return '%s not turned off for werewolves.' % what
    if fid == 'nude_default':
        what = 'The clothing item is' if one else '%s clothing items are' % count
        return '%s marked as a default item for %s body part.' % (what, 'its' if one else 'their')
    if fid == 'pets_patch':
        what = 'It was' if one else '%s Create a Sim items were' % count
        return '%s made before the Cats & Dogs update of November 2017%s.' % (
            what, ' (format %s; items made since then use 32 or higher)' % vers if vers else '')
    return 'It may need this fix.'


# ------------------------------------------------------------------------------------------ the results store
SCHEMA = """
create table if not exists file(relkey text primary key, root text, rel text, size integer, mtime real,
                                version integer, hits text);
create table if not exists meta(k text primary key, v text);
"""


class Store:
    def __init__(self, path):
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.db = sqlite3.connect(path, timeout=30)
        self.db.executescript(SCHEMA)

    def close(self):
        self.db.close()

    def meta(self, k, default=None):
        row = self.db.execute('select v from meta where k=?', (k,)).fetchone()
        return row[0] if row else default

    def set_meta(self, k, v):
        self.db.execute('insert or replace into meta values(?,?)', (k, str(v)))

    def scan(self, lib, progress=None, skip=None):
        """Bring the results up to the library index's state (Library.scan() first). Reads the CAS parts and
        sliders of new or changed files only. skip(rel) -> True leaves a file out (SpeedKit's own packs).
        A file in both Mods and Mods_parked is checked once, as the Mods copy. Returns counts."""
        t0 = time.time()
        tell = progress or (lambda *a, **k: None)
        skip = skip or (lambda rel: False)
        order = list(lib.roots)
        known = {rk: (size, mtime, ver, root) for rk, size, mtime, ver, root in
                 self.db.execute('select relkey, size, mtime, version, root from file')}
        chosen = {}
        for p in sorted(lib.packages(), key=lambda p: order.index(p.root) if p.root in order else 99):
            if skip(p.rel):
                continue
            chosen.setdefault(p.rel.lower(), p)
        todo = []
        for k, p in chosen.items():
            old = known.get(k)
            if old and old[0] == p.size and abs((old[1] or 0) - p.mtime) < 1e-3 and old[2] == DETECT_VERSION:
                if old[3] != p.root:
                    self.db.execute('update file set root=?, rel=? where relkey=?', (p.root, p.rel, k))
                continue
            todo.append(p)
        # which of them hold anything to look at: one query instead of one per file
        want = {}
        if 0 < len(todo) <= 2000:                # a few changed files: their own rows (the pkg index)
            for p in todo:
                rows = lib.db.execute('select t, i, off, fsize, msize, comp from res where pkg=? and t in (?, ?) and '
                                      'comp != ? order by off', (p.id, T_CASP, T_HOTC, DELETED)).fetchall()
                if rows:
                    want[p.id] = rows
        elif todo:                               # a first check: one pass over the whole table
            ids = {p.id for p in todo}
            for pid, t, i, off, fs, ms, comp in lib.db.execute(
                    'select pkg, t, i, off, fsize, msize, comp from res where t in (?, ?) and comp != ? order by pkg, off',
                    (T_CASP, T_HOTC, DELETED)):
                if pid in ids:
                    want.setdefault(pid, []).append((t, i, off, fs, ms, comp))
        n = len(todo)
        tell('batchfix', 0.0, 'Checking %s new or changed CC files' % format(n, ',') if n
             else 'All CC files were checked before')
        last, done, found = time.time(), 0, 0
        for p in todo:
            hits = {}
            rows = want.get(p.id)
            if rows and not p.err:
                try:
                    hits = check_package(lib.path(p.root, p.rel), rows)
                except OSError:
                    hits = {}
            found += bool(hits)
            self.db.execute('insert or replace into file values(?,?,?,?,?,?,?)',
                            (p.rel.lower(), p.root, p.rel, p.size, p.mtime, DETECT_VERSION,
                             json.dumps(hits, separators=(',', ':')) if hits else ''))
            done += 1
            if time.time() - last > 0.5:
                last = time.time()
                self.db.commit()
                tell('batchfix', round(done / max(1, n), 3), 'Checking CC files: %s of %s' % (
                    format(done, ','), format(n, ',')))
        gone = [k for k in known if k not in chosen]
        self.db.executemany('delete from file where relkey=?', [(k,) for k in gone])
        self.set_meta('scanned', time.strftime('%Y-%m-%dT%H:%M:%S'))
        self.set_meta('files', len(chosen))
        self.db.commit()
        return {'files': len(chosen), 'read': done, 'removed': len(gone), 'seconds': round(time.time() - t0, 1)}

    def findings(self):
        """{fix id: [{'root', 'rel', 'parts', 'total', 'versions'}]} (files sorted by path)."""
        out = {}
        for root, rel, hits in self.db.execute("select root, rel, hits from file where hits != '' order by relkey"):
            try:
                doc = json.loads(hits)
            except ValueError:
                continue
            for fid, h in doc.items():
                if fid in FIX_BY_ID and isinstance(h, dict):
                    out.setdefault(fid, []).append(dict(h, root=root, rel=rel))
        return out

    def state(self):
        s = self.meta('scanned')
        return {'scanned': s, 'files': int(self.meta('files', 0) or 0) if s else 0}
