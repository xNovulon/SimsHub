"""ccbrowser - the Library page's CC browser (pictures + categories) and the Saves page's "what CC does this
save use, and what is missing". docs/ccbrowser.md explains it for people; this docstring is for code.

    idx = CCIndex(db_path)                          # data/ccbrowser.sqlite (beside library.sqlite)
    idx.scan(lib, refs=refs, save_names=...)        # incremental; reads the library index + a few CAS parts
    idx.query(category='hair', q='braid', used='unused', offset=0, limit=60)
    thumbs = ThumbCache(dir)                        # data/ccthumbs/ (never inside the game's folders)
    item_picture(idx, thumbs, item_id, lib_roots)   # -> (bytes, content type) or None, made once, then cached
    part_picture(lib, thumbs, 'cas', instance, extra_sources)
    usage_report(lib, refs_subset, game, idx, side) # one save (or the Tray): files used, per sim, missing CC
    set_aside(idx, ids, sims=..., home=...)         # Journal kind 'setaside': files go to the safe copies

Facts it relies on (research/usedcc: verify_casp.json and usedcc.casp_header, 2,000 of 2,025 CAS parts of a
real library parsed with this layout; research/dupes and lagdrivers/dbstats for the image types):
  * CAS part (CASP 0x034AEECB): u32 version, u32 key-list offset (from byte 8), u32 preset count, the part's
    name (.NET 7-bit length, UTF-16BE), then a version-dependent header up to u32 body type, u32 body sub
    type, u32 age/gender (layout of TS4SimRipper's CASP.cs, versions 0x1B-0x34). Version 18 parts (25 of the
    sample) do not parse: they fall back to "Other CAS".
  * CAS thumbnails (THUM 0x3C1AF1F2) use the CAS part's instance, in groups 1, 2, 0x101, 0x102. Only ~30% of
    the sampled CC parts ship one; the game makes the others into <Sims 4>\\localthumbcache.package, so that
    file (read-only) is the fallback, and the only picture a MISSING part can still have.
  * Build/Buy thumbnails: 0x3C2A8647 (the object's instance), and 0x5B282D45 / 0x9C925813 / 0xCD9DE247 seen in
    real packages; 0x2F7D0004 is a plain PNG (icons of gameplay mods). Most are PNG; some are JFIF, and EA's
    alpha-in-JPEG variant keeps a grayscale PNG mask in an APP0 segment 'ALFA' + u32 big-endian length (at
    byte 0x18 when it follows the JFIF segment). decode_image() handles all three (and DDS via Pillow).
  * A save stores only ID numbers of the CC its sims wear and its lots use (speedkit.usedpack). EA's CAS part
    and object ids are all below 2^32; a bigger id that is neither in the library nor in the game is CC that
    is installed nowhere. Its name is only known when a copy turns up in the Hub's safe copies (quarantine),
    the Inbox, Downloads or Desktop (side_update/side_find - a .zip there is looked inside too, by its
    .package entries); its picture only when the game's thumbnail cache still has it.

Nothing here writes to Mods, Mods_parked, saves or Tray, except set_aside(), which moves files out of Mods into
the safe copies through a Journal (undoable, refuses while the game runs, never touches script mods).
"""
import collections
import hashlib
import io
import json
import os
import re
import sqlite3
import struct
import threading
import time
import zipfile

from .dbpf import Package, read_entries, open_shared, decompress, DELETED
from .library import signed64, unsigned64
from . import usedpack as U

INDEX_VERSION = 4              # bump when classification changes: every file is looked at again (4: merged, walls)
THUMB_VERSION = 1              # bump when picture making changes: every picture is made again
THUMB_SIZE = 256               # longest side of a cached picture, in pixels
SAMPLE_CASP = 12               # CAS parts read per file to decide its categories
BIG = U.BIG
SIDE_ZIP_MAX_BYTES = 512 * 1024 * 1024   # .package entries in a .zip bigger than this (uncompressed) are skipped

# ------------------------------------------------------------------------------------------ resource types
T_CASP, T_THUM, T_TONE, T_OBJD, T_COBJ, T_OTHM = U.T_CASP, U.T_THUM, U.T_TONE, U.T_OBJD, U.T_COBJ, U.T_OTHM
MERGE_LIST = 0x7FB6AD8A          # Sims 4 Studio's list of what went into a merge (tool metadata, not content)
T_CWAL, T_CFLR, T_SMOD, T_SCUL, T_PELT = U.T_CWAL, U.T_CFLR, U.T_SMOD, U.T_SCUL, U.T_PELT
T_CFEN = 0x0418FE2A            # fence
T_MERGE_LIST = 0x7FB6AD8A      # Sims 4 Studio's list of the files merged into this one
T_CLIP = 0x6B20C4F3            # animation clip (poses, WickedWhims animations)
T_PRESET = 0xEAA32ADD          # CAS preset
T_THUM_BB, T_THUM_2, T_THUM_3, T_PNG = 0x5B282D45, 0x9C925813, 0xCD9DE247, 0x2F7D0004
CAS_PICS = (T_THUM,)
OBJECT_PICS = (T_OTHM, T_THUM_BB, T_THUM_2, T_THUM_3)
ANY_PICS = CAS_PICS + OBJECT_PICS + (T_PNG,)
# resources that are pictures, meshes, textures or bookkeeping: a file with nothing else is not a gameplay mod
ASSET_TYPES = {U.T_GEOM, U.T_RLE2, U.T_LRLE, U.T_RLES, U.T_IMG, U.T_DST, U.T_RMAP, U.T_BOND, U.T_BGEO, U.T_DMAP,
               U.T_MODL, U.T_MLOD, U.T_FTPT, U.T_RSLT, U.T_LITE, U.T_RIG, U.T_MATD, U.T_HSC, T_THUM, T_OTHM,
               T_THUM_BB, T_THUM_2, T_THUM_3, T_PNG, 0x0166038C, 0x7FB6AD8A, 0x736884F1, 0x025ED6F4, 0xD5F0F921}

# ------------------------------------------------------------------------------------------ categories
CATEGORIES = [
    ('hair', 'Hair'), ('hat', 'Hats'), ('top', 'Tops'), ('bottom', 'Bottoms'), ('fullbody', 'Full outfits'),
    ('shoes', 'Shoes'), ('accessory', 'Accessories'), ('makeup', 'Makeup'), ('eyes', 'Eyes & brows'),
    ('skin', 'Skin & tattoos'), ('cas_other', 'Other CAS'), ('pets', 'Pets'), ('sliders', 'Sliders & presets'),
    ('buildbuy', 'Furniture & objects'), ('walls', 'Walls & floors'), ('poses', 'Poses & animations'),
    ('gameplay', 'Gameplay mods'), ('script', 'Script mods'), ('other', 'Other'),
]
CATEGORY_LABELS = dict(CATEGORIES)
CAS_CATEGORIES = {'hair', 'hat', 'top', 'bottom', 'fullbody', 'shoes', 'accessory', 'makeup', 'eyes', 'skin',
                  'cas_other', 'pets'}

# the game's BodyType enum (1..61 are stable since the base game; later ones fall back to "Other CAS")
BODY_TYPES = {
    1: ('hat', 'Hat'), 2: ('hair', 'Hair'), 3: ('cas_other', 'Head'), 4: ('cas_other', 'Teeth'),
    5: ('fullbody', 'Full outfit'), 6: ('top', 'Top'), 7: ('bottom', 'Bottom'), 8: ('shoes', 'Shoes'),
    9: ('accessory', 'Belt'), 10: ('accessory', 'Earrings'), 11: ('accessory', 'Glasses'),
    12: ('accessory', 'Necklace'), 13: ('accessory', 'Gloves'), 14: ('accessory', 'Bracelet'),
    15: ('accessory', 'Bracelet'), 16: ('accessory', 'Lip ring'), 17: ('accessory', 'Lip ring'),
    18: ('accessory', 'Nose ring'), 19: ('accessory', 'Nose ring'), 20: ('accessory', 'Brow ring'),
    21: ('accessory', 'Brow ring'), 22: ('accessory', 'Ring'), 23: ('accessory', 'Ring'), 24: ('accessory', 'Ring'),
    25: ('accessory', 'Ring'), 26: ('accessory', 'Ring'), 27: ('accessory', 'Ring'), 28: ('hair', 'Facial hair'),
    29: ('makeup', 'Lipstick'), 30: ('makeup', 'Eyeshadow'), 31: ('makeup', 'Eyeliner'), 32: ('makeup', 'Blush'),
    33: ('makeup', 'Face paint'), 34: ('eyes', 'Eyebrows'), 35: ('eyes', 'Eye color'), 36: ('accessory', 'Socks'),
    37: ('makeup', 'Mascara'), 38: ('skin', 'Forehead crease'), 39: ('skin', 'Freckles'), 40: ('skin', 'Dimple'),
    41: ('skin', 'Dimple'), 42: ('accessory', 'Tights'), 43: ('skin', 'Mole'), 44: ('skin', 'Mole'),
    45: ('skin', 'Tattoo'), 46: ('skin', 'Tattoo'), 47: ('skin', 'Tattoo'), 48: ('skin', 'Tattoo'),
    49: ('skin', 'Tattoo'), 50: ('skin', 'Tattoo'), 51: ('skin', 'Tattoo'), 52: ('skin', 'Tattoo'),
    53: ('skin', 'Tattoo'), 54: ('skin', 'Tattoo'), 55: ('skin', 'Mole'), 56: ('skin', 'Mole'),
    57: ('skin', 'Mouth crease'), 58: ('skin', 'Skin overlay'), 59: ('pets', 'Fur'), 60: ('pets', 'Ears'),
    61: ('pets', 'Tail'),
}

# words that are never a creator's name (file names like 'Hair_Long_01' or 'CC_top.package')
_NOT_CREATORS = {'the', 'cc', 'mod', 'mods', 'sims', 'sims4', 'ts4', 's4', 'sim', 'new', 'my', 'hair', 'top',
                 'tops', 'dress', 'shoes', 'set', 'pack', 'merged', 'merge', 'female', 'male', 'fem', 'teen',
                 'adult', 'child', 'kid', 'kids', 'toddler', 'infant', 'default', 'replacement', 'override',
                 'recolor', 'recolour', 'retexture', 'mesh', 'maxis', 'mm', 'alpha', 'acc', 'accessory', 'makeup',
                 'skin', 'eyes', 'eye', 'lipstick', 'blush', 'nails', 'earrings', 'necklace', 'build', 'buy',
                 'object', 'objects', 'deco', 'clutter', 'poses', 'pose', 'animation', 'animations', 'tattoo',
                 'speedkit', 'yf', 'ym', 'af', 'am', 'cf', 'cm', 'tf', 'tm', 'ef', 'em', 'pf', 'pm', 'hf', 'hm',
                 'bottom', 'bottoms', 'outfit', 'full', 'body', 'fullbody', 'shoe', 'hat', 'hats', 'slider',
                 'sliders', 'preset', 'presets', 'tone', 'tones', 'mcc', 'part', 'file', 'files', 'copy', 'v1', 'v2'}


def guess_creator(filename):
    """A creator name guessed from a file name ('[Sentate] Venus Dress', 'Simstrouble_Hair_Pack',
    'Peacemaker - sofa'), or None. Only a guess: many files do not name their creator."""
    base = os.path.splitext(os.path.basename(filename))[0].strip()
    m = re.match(r'^[\[(\{]\s*([^\])\}]{2,40}?)\s*[\])\}]', base)
    if m:
        cand = m.group(1).strip()
    else:
        m = re.match(r'^([A-Za-z][A-Za-z0-9.\'&+]{1,30}?)(?:\s*[-_~]\s*|\s+-\s+|\s*\|\s*)', base)
        if not m:
            m = re.match(r'^([A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+)(?=[A-Z_ -]|$)', base)   # CamelCase prefix
        cand = m.group(1) if m else None
    if not cand:
        return None
    cand = cand.strip(' .-_')
    low = cand.lower()
    if len(cand) < 3 or low in _NOT_CREATORS or low.isdigit() or re.fullmatch(r'[a-z]{1,2}\d*', low):
        return None
    return cand


def folder_of(rel):
    """The top folder of a file in Mods ('' for a file at the Mods root)."""
    rel = rel.replace('\\', '/')
    return rel.split('/', 1)[0] if '/' in rel else ''


# ------------------------------------------------------------------------------------------ CAS part header
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


def casp_info(data):
    """{'version', 'name', 'body_type', 'age_gender'} of a CAS part resource, or None when it does not parse.
    body_type is None when the header layout is not known for its version (then it is filed as Other CAS)."""
    if len(data) < 16:
        return None
    try:
        v, toff = struct.unpack_from('<II', data, 0)
        nlen, p = _read_7bit(data, 12)
        name = data[p:p + nlen].decode('utf-16-be', 'replace').strip('\x00').strip()
        p += nlen
        out = {'version': v, 'name': name, 'body_type': None, 'age_gender': None}
        if v < 0x1B or v > 0x40:
            return out
        p += 4 + 2 + 4 + 4 + 1                     # sort priority, secondary sort, outfit id, aural, parm flags
        if v >= 39:
            p += 1                                 # parm flags 2
        if v >= 50:
            p += 2                                 # layer id
        if v >= 51:
            n = struct.unpack_from('<i', data, p)[0]
            if not 0 <= n < 64:
                return out
            p += 4 + 8 * n
        else:
            p += 8 + (8 if v >= 41 else 0)
        p += 8 if v > 36 else 4                    # exclude modifier region flags
        nf = struct.unpack_from('<i', data, p)[0]
        if not 0 <= nf < 4096:
            return out
        p += 4 + nf * (6 if v >= 37 else 4)        # tags
        p += 12 + (4 if v >= 0x2B else 0) + 1      # price, title, description (+ create description), texture space
        bt, _sub, ag = struct.unpack_from('<III', data, p)
        if 0 < bt < 512 and 8 + toff <= len(data):
            out['body_type'], out['age_gender'] = bt, ag
        return out
    except (struct.error, IndexError, ValueError):
        return None


def body_category(body_type):
    """(category key, plain name) of a body type."""
    if body_type in BODY_TYPES:
        return BODY_TYPES[body_type]
    return ('cas_other', 'Other CAS')


# ------------------------------------------------------------------------------------------ pictures
def _jpeg_alpha(data):
    """(start, end, png bytes) of EA's 'ALFA' alpha segment in a JPEG, or None."""
    p = 2
    n = len(data)
    while p + 4 <= n and data[p] == 0xFF:
        marker = data[p + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            p += 2
            continue
        seglen = int.from_bytes(data[p + 2:p + 4], 'big')
        if 0xE0 <= marker <= 0xEF and data[p + 4:p + 8] == b'ALFA':
            ln = int.from_bytes(data[p + 8:p + 12], 'big')
            png = data[p + 12:p + 12 + ln]
            end = max(p + 2 + seglen, p + 12 + ln) if seglen >= 8 else p + 12 + ln
            return p, end, png
        if marker == 0xDA:                         # image data starts: no more headers
            break
        p += 2 + seglen
    if data[0x18:0x1C] == b'ALFA':                 # a writer that put it there without a proper segment
        ln = int.from_bytes(data[0x1C:0x20], 'big')
        return 0x14, 0x20 + ln, data[0x20:0x20 + ln]
    return None


def decode_image(data):
    """A PIL image (RGBA) from a thumbnail resource: PNG, JPEG/JFIF, EA's JPEG with an 'ALFA' PNG mask, or DDS.
    Raises ValueError when it is not a picture Pillow can read."""
    from PIL import Image
    if not data:
        raise ValueError('empty')
    alpha = None
    if data[:3] == b'\xff\xd8\xff':
        found = _jpeg_alpha(data)
        if found:
            start, end, png = found
            try:
                alpha = Image.open(io.BytesIO(png))
                alpha.load()
            except Exception:
                alpha = None
            try:
                img = Image.open(io.BytesIO(data))
                img.load()
            except Exception:                        # a decoder that trips over the mask: cut it out and retry
                img = Image.open(io.BytesIO(data[:start] + data[end:]))
                img.load()
        else:
            img = Image.open(io.BytesIO(data))
            img.load()
        img = img.convert('RGB')
        if alpha is not None:
            a = alpha.convert('L')                   # EA's mask is grayscale: white = solid
            if alpha.mode in ('RGBA', 'LA', 'PA'):
                own = alpha.convert('RGBA').getchannel('A')
                if own.getextrema() != (255, 255):   # a mask that carries real transparency itself
                    a = own
            if a.size != img.size:
                a = a.resize(img.size)
            img.putalpha(a)
        return img.convert('RGBA')
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as e:
        raise ValueError('not a picture (%s)' % type(e).__name__)
    return img.convert('RGBA')


def make_thumb(data, size=THUMB_SIZE):
    """(bytes, content type): the picture scaled to fit size x size, as WebP (PNG when Pillow has no WebP)."""
    from PIL import Image, features
    img = decode_image(data)
    if img.width < 2 or img.height < 2:
        raise ValueError('picture too small')
    img.thumbnail((size, size), Image.LANCZOS)
    buf = io.BytesIO()
    if features.check('webp'):
        img.save(buf, 'WEBP', quality=80, method=4)
        return buf.getvalue(), 'image/webp'
    img.save(buf, 'PNG', optimize=True)
    return buf.getvalue(), 'image/png'


class ThumbCache:
    """Pictures made once and kept on disk, keyed by the source file (path, size, mtime) and the resource key,
    so a changed file gets a new picture and browsing never reads a package twice. A picture that could not be
    made is remembered as a tiny '.none' file (with the same key, so a changed file is tried again)."""

    def __init__(self, folder):
        self.folder = folder

    def key(self, source_key, size, mtime, rk):
        t, g, i = rk
        raw = '%s|%d|%d|%08X:%08X:%016X|%d' % (source_key.lower(), size, int(round(mtime * 1000)), t, g, i,
                                              THUMB_VERSION)
        return hashlib.blake2b(raw.encode('utf-8', 'replace'), digest_size=16).hexdigest()

    def _path(self, k, ext):
        return os.path.join(self.folder, k[:2], k + ext)

    def get(self, k):
        """(bytes, type) | 'none' (known to have no picture) | None (not made yet)."""
        for ext, ctype in (('.webp', 'image/webp'), ('.png', 'image/png')):
            p = self._path(k, ext)
            try:
                with open(p, 'rb') as f:
                    return f.read(), ctype
            except OSError:
                continue
        return 'none' if os.path.exists(self._path(k, '.none')) else None

    def put(self, k, blob, ctype):
        ext = '.webp' if ctype == 'image/webp' else '.png' if blob is not None else '.none'
        p = self._path(k, ext)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = '%s.%d.%d.tmp' % (p, os.getpid(), threading.get_ident())
        with open(tmp, 'wb') as f:
            f.write(blob or b'')
        os.replace(tmp, p)

    def make(self, k, read_fn):
        """The cached picture, made with read_fn() (-> resource bytes) the first time; None when there is none."""
        hit = self.get(k)
        if hit == 'none':
            return None
        if hit:
            return hit
        try:
            blob, ctype = make_thumb(read_fn())
        except ImportError:                          # no Pillow: nothing is remembered, pictures just do not show
            return None
        except Exception:
            try:
                self.put(k, None, None)
            except OSError:
                pass
            return None
        try:
            self.put(k, blob, ctype)
        except OSError:
            pass
        return blob, ctype


def locate(roots, root, rel, size=None):
    """Where a library file is now: at its root, or at the same place in the other root (a Mods switch moved
    it). None when it is in neither."""
    order = [root] + [r for r in roots if r != root]
    for r in order:
        if r not in roots:
            continue
        p = os.path.join(roots[r], rel.replace('/', os.sep))
        try:
            st = os.stat(p)
        except OSError:
            continue
        if size is None or r == root or st.st_size == size:
            return p
    return None


def read_resource(path, rk):
    """One resource of a package, decompressed (the first copy of that key in the file)."""
    t, g, i = rk
    with Package(path) as pkg:
        for e in pkg.entries:
            if e.t == t and e.g == g and e.i == i and e.comp != DELETED:
                return pkg.read(e)
    raise KeyError('%08X:%08X:%016X is not in %s' % (t, g, i, os.path.basename(path)))


class ExtraPictures:
    """Pictures outside the library: the game's own thumbnail cache (<Sims 4>\\localthumbcache.package) and any
    package in the side folders (safe copies, Inbox). Indexes are read once per file size/mtime."""

    def __init__(self, files=(), shared=None):
        self.files = [f for f in files if f]
        self._idx = shared._idx if shared is not None else {}          # file indexes, shared by every view
        self._lock = shared._lock if shared is not None else threading.Lock()

    def with_files(self, files):
        """The same index cache over another list of files (one per request: the server is threaded)."""
        return ExtraPictures(files, shared=self)

    def _index(self, path):
        try:
            st = os.stat(path)
        except OSError:
            return None
        ck = (path, st.st_size, st.st_mtime_ns)
        with self._lock:
            if ck in self._idx:
                return self._idx[ck]
        out = {}
        try:
            with open_shared(path) as f:
                for e in read_entries(f):
                    if e.t in ANY_PICS and e.comp != DELETED:
                        cur = out.get((e.t, e.i))
                        if cur is None or e.fsize > cur.fsize:
                            out[(e.t, e.i)] = e
        except Exception:
            out = {}
        with self._lock:
            for k in [k for k in self._idx if k[0] == path]:
                self._idx.pop(k)
            self._idx[ck] = (st, out)
        return self._idx[ck]

    def find(self, types, instance):
        """(path, st, entry) of the biggest picture of one of the types with that instance, or None."""
        for path in self.files:
            got = self._index(path)
            if not got:
                continue
            st, idx = got
            best = None
            for t in types:
                e = idx.get((t, instance))
                if e is not None and (best is None or e.fsize > best.fsize):
                    best = e
            if best is not None:
                return path, st, best
        return None


def _picture_from_extra(thumbs, extra, types, instance):
    if extra is None:
        return None
    hit = extra.find(types, instance)
    if not hit:
        return None
    path, st, e = hit
    k = thumbs.key('extra:' + path, st.st_size, st.st_mtime, (e.t, e.g, e.i))

    def read():
        with open_shared(path) as f:
            f.seek(e.off)
            return decompress(f.read(e.fsize), e.comp, e.msize)
    return thumbs.make(k, read)


def _ensure_pic_indexes(db):
    """Small partial indexes on the library's resource table, so a picture is found by instance at once."""
    for t in (T_THUM, T_OTHM):
        try:
            db.execute('create index if not exists cc_pic_%08x on res(i) where t = %d' % (t, t))
        except sqlite3.Error:
            pass


def part_picture(lib, thumbs, kind, instance, extra=None, skip_pkgs=()):
    """(bytes, type) of the picture of one CAS part ('cas') or object ('object') by its instance: the library's
    own thumbnail with that instance, else the game's thumbnail cache / side folders. None when there is none."""
    types = CAS_PICS if kind == 'cas' else OBJECT_PICS
    best = None
    if lib is not None:
        for t in types:
            # the type is written into the SQL (not a parameter) so the partial index cc_pic_<type> is used
            sql = 'select pkg, g, fsize from res where t = %d and i = ? and comp != ?' % t
            for pkg, g, fs in lib.db.execute(sql, (signed64(instance), DELETED)):
                if pkg in skip_pkgs:
                    continue
                if best is None or fs > best[3]:
                    best = (t, g, pkg, fs)
    if best is not None:
        t, g, pkg, _ = best
        row = lib.db.execute('select root, rel, size, mtime from pkg where id=?', (pkg,)).fetchone()
        if row:
            root, rel, size, mtime = row
            path = locate(lib.roots, root, rel, size)
            if path:
                k = thumbs.key(rel, size, mtime, (t, g, instance))
                got = thumbs.make(k, lambda: read_resource(path, (t, g, instance)))
                if got:
                    return got
    return _picture_from_extra(thumbs, extra, types, instance)


# ------------------------------------------------------------------------------------------ the index
SCHEMA = """
create table if not exists meta(k text primary key, v text);
create table if not exists item(
    id integer primary key, kind text, root text, rel text, relkey text unique, name text, folder text,
    creator text, size integer, mtime real, category text, cats text, body text, part_name text,
    n_res integer, n_cas integer, n_obj integer, thumb text, broken text, dup_of text, used integer,
    used_by text, version integer, extra text);
create index if not exists item_cat on item(category);
create index if not exists item_folder on item(folder);
create index if not exists item_creator on item(creator);
create table if not exists side_file(id integer primary key, path text unique, size integer, mtime real,
                                     place text, name text);
create table if not exists side_res(file integer, t integer, i integer);
create index if not exists side_res_i on side_res(i);
create table if not exists side_zip(path text primary key, size integer, mtime real);
"""

SORTS = {'name': 'lower(name), id', 'newest': 'mtime desc, id', 'biggest': 'size desc, id',
         'folder': 'lower(folder), lower(name), id', 'category': 'category, lower(name), id'}
FLAGS = ('duplicate', 'broken')
MAX_LIMIT = 200


def _connect(path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    db = sqlite3.connect(path, timeout=15, check_same_thread=False)
    try:
        db.execute('pragma journal_mode=wal')
    except sqlite3.Error:
        pass
    db.executescript(SCHEMA)
    # an index from before 'extra' (merged file, walls/floors/fences inside) gets the column; the version bump
    # then fills it in as every file is looked at again
    if 'extra' not in {r[1] for r in db.execute('pragma table_info(item)')}:
        db.execute('alter table item add column extra text')
        db.commit()
    return db


class CCIndex:
    """data/ccbrowser.sqlite: one row per CC file (packages and script mods) with its category, picture key,
    duplicate/broken flags and which saves use it. Readers may use it while a scan writes (WAL)."""

    def __init__(self, path):
        self.path = path
        self.db = _connect(path)

    def close(self):
        self.db.close()

    def meta(self, k, default=None):
        row = self.db.execute('select v from meta where k=?', (k,)).fetchone()
        return row[0] if row else default

    def set_meta(self, k, v):
        self.db.execute('insert or replace into meta values(?,?)', (k, str(v)))

    # ---------------------------------------------------------------- scanning
    def scan(self, lib, refs=None, save_names=None, progress=None, skip=None, max_seconds=None):
        """Bring the index up to the library index's state (Library.scan() first). Only new or changed files are
        read, a few CAS parts each; moved files (Mods <-> Mods_parked) keep their row. refs (usedpack Refs) marks
        what the saves and Tray use; save_names maps a save file name ('Slot_00000014.save') to its own name.
        skip(rel) -> True leaves a file out (SpeedKit's own packs). Returns counts."""
        t0 = time.time()
        tell = progress or (lambda *a, **k: None)
        skip = skip or (lambda rel: False)
        roots_pref = list(lib.roots)
        known = {rk: (iid, size, mtime, root, ver) for iid, rk, size, mtime, root, ver in
                 self.db.execute("select id, relkey, size, mtime, root, version from item where kind='package'")}
        pkgs = sorted((p for p in lib.packages() if not skip(p.rel)),
                      key=lambda p: (roots_pref.index(p.root) if p.root in roots_pref else 99, p.id))
        chosen, shadow = {}, set()
        for p in pkgs:
            k = p.rel.lower()
            if k in chosen:
                shadow.add(p.id)          # the same file name in the other root: the Mods copy is the one shown
                continue
            chosen[k] = p
        todo, moved = [], 0
        for k, p in chosen.items():
            old = known.get(k)
            if old and old[1] == p.size and abs((old[2] or 0) - p.mtime) < 1e-3 and old[4] == INDEX_VERSION:
                if old[3] != p.root:
                    self.db.execute('update item set root=? where id=?', (p.root, old[0]))
                    moved += 1
                continue
            todo.append(p)
        n = len(todo)
        tell('cc', 0.0, 'Looking at %d new or changed CC files' % n if n else 'All CC files are already sorted')
        last = time.time()
        done = 0
        for p in todo:
            info = classify(lib, p)
            self._upsert(p, info)
            done += 1
            if time.time() - last > 0.5:
                last = time.time()
                self.db.commit()
                tell('cc', round(0.85 * done / max(1, n), 3), 'Sorting CC files: %s of %s' % (
                    format(done, ','), format(n, ',')))
            if max_seconds and time.time() - t0 > max_seconds:
                break
        # script mods: nothing to read
        scripts = {}
        for s in lib.scripts():
            if skip(s.rel) or os.path.basename(s.rel).lower() == 'speedkit_monitor.ts4script':
                continue
            k = s.rel.lower()
            if k not in scripts or s.root == roots_pref[0]:
                scripts[k] = s
        for k, s in scripts.items():
            row = self.db.execute('select id from item where relkey=?', (k,)).fetchone()
            vals = ('script', s.root, s.rel, k, os.path.basename(s.rel), folder_of(s.rel),
                    guess_creator(s.rel), s.size, s.mtime, 'script', 'script', None, None, 0, 0, 0, '', None,
                    INDEX_VERSION)
            if row:
                self.db.execute('update item set kind=?, root=?, rel=?, relkey=?, name=?, folder=?, creator=?, size=?, '
                                'mtime=?, category=?, cats=?, body=?, part_name=?, n_res=?, n_cas=?, n_obj=?, thumb=?, '
                                'broken=?, version=? where id=?', vals + (row[0],))
            else:
                self.db.execute('insert into item(kind, root, rel, relkey, name, folder, creator, size, mtime, '
                                'category, cats, body, part_name, n_res, n_cas, n_obj, thumb, broken, version) '
                                'values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', vals)
        # files that are gone
        live = set(chosen) | set(scripts)
        gone = [iid for iid, rk in self.db.execute('select id, relkey from item') if rk not in live]
        self.db.executemany('delete from item where id=?', [(g,) for g in gone])
        self.db.commit()
        tell('cc', 0.88, 'Finding duplicate and damaged files')
        skip_ids = shadow | {p.id for p in lib.packages() if skip(p.rel)}
        self._flags(lib, chosen, skip_ids)
        _ensure_pic_indexes(lib.db)
        tell('cc', 0.94, 'Matching CC with the saves that use it')
        used_known = self._usage(lib, chosen, refs, save_names or {}) if refs is not None else False
        self.set_meta('scanned', time.strftime('%Y-%m-%dT%H:%M:%S'))
        self.set_meta('used_known', 1 if used_known else 0)
        self.set_meta('generation', int(self.meta('generation', 0) or 0) + 1)
        self.set_meta('complete', 1 if done == n else 0)
        self.db.commit()
        total = self.db.execute('select count(*) from item').fetchone()[0]
        return {'items': total, 'read': done, 'left': n - done, 'moved': moved, 'removed': len(gone),
                'seconds': round(time.time() - t0, 1)}

    def _upsert(self, p, info):
        k = p.rel.lower()
        extra = {k2: info[k2] for k2 in ('merged', 'walls', 'floors', 'fences') if info.get(k2)}
        vals = ('package', p.root, p.rel, k, os.path.basename(p.rel), folder_of(p.rel), guess_creator(p.rel),
                p.size, p.mtime, info['category'], ','.join(info['cats']), info.get('body'), info.get('part_name'),
                info['n_res'], info['n_cas'], info['n_obj'], info.get('thumb') or '', info.get('broken'),
                INDEX_VERSION, json.dumps(extra) if extra else None)
        row = self.db.execute('select id from item where relkey=?', (k,)).fetchone()
        if row:
            self.db.execute('update item set kind=?, root=?, rel=?, relkey=?, name=?, folder=?, creator=?, size=?, '
                            'mtime=?, category=?, cats=?, body=?, part_name=?, n_res=?, n_cas=?, n_obj=?, thumb=?, '
                            'broken=?, version=?, extra=? where id=?', vals + (row[0],))
        else:
            self.db.execute('insert into item(kind, root, rel, relkey, name, folder, creator, size, mtime, category, '
                            'cats, body, part_name, n_res, n_cas, n_obj, thumb, broken, version, extra) '
                            'values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', vals)

    def _flags(self, lib, chosen, skip_ids):
        """dup_of: ONE other file holds every resource this one has (CAS parts, objects, tuning, pictures - everything
        but Sims 4 Studio's merge list), with the same content, and that file is not marked itself - so removing every
        file marked Duplicate never loses anything. Files in a folder with a script mod are never marked. A merge that only shares some
        of its parts with other files is not a duplicate (the duplicate clean-up removes just those extra copies).
        Of two files holding the same parts one stays unmarked: the one whose name doesn't look like a copy, then the
        one in Mods, then the bigger one, then the one the game loads first."""
        db = lib.db
        rel_of = {p.id: p.rel for p in chosen.values()}
        root_of = {p.id: p.root for p in chosen.values()}
        first = next(iter(lib.roots), 'Mods')          # the folder the game loads (Mods before Mods_parked)
        script_dirs = {(s.root, os.path.dirname(s.rel).lower()) for s in lib.scripts()}
        where = [p.id for p in chosen.values() if p.id not in skip_ids
                 and (p.root, os.path.dirname(p.rel).lower()) not in script_dirs]
        keys, owners, loc = collections.defaultdict(set), collections.defaultdict(set), {}
        for pkg, t, g, i, off, fsize, msize, comp in db.execute(
                'select pkg, t, g, i, off, fsize, msize, comp from res where t in (?, ?) and comp != ?',
                (T_CASP, T_OBJD, DELETED)):
            if pkg in skip_ids or pkg not in rel_of:
                continue
            k = (t, g, i)
            keys[pkg].add(k)
            owners[k].add(pkg)
            loc[(pkg, k)] = (off, fsize, msize, comp)
        copy_like = re.compile(r'(^copy of |[ _-]copy\b|\(\d+\)\.package$| - copy)', re.I)
        drop_first = sorted((p for p in where if keys.get(p)), key=lambda p: (
            0 if copy_like.search(os.path.basename(rel_of[p])) else 1, 0 if root_of[p] != first else 1,
            len(keys[p]), -p))
        files = {}

        def raw(pkg, k):
            off, fsize, msize, comp = loc[(pkg, k)]
            f = files.get(pkg)
            if f is None:
                if len(files) > 64:
                    for x in files.values():
                        x.close()
                    files.clear()
                f = files[pkg] = open(lib.path(root_of[pkg], rel_of[pkg]), 'rb')
            f.seek(off)
            return f.read(fsize), comp, msize

        def same(a, b, k):
            ra, rb = raw(a, k), raw(b, k)
            if ra[0] == rb[0]:
                return True
            try:
                from .hashing import data_digest
                return data_digest(*ra) == data_digest(*rb)
            except Exception:
                return False

        def rows(pkg):
            return {(t, g, i): (off, fsize, msize, comp) for t, g, i, off, fsize, msize, comp in db.execute(
                'select t, g, i, off, fsize, msize, comp from res where pkg = ? and comp != ? and t != ?',
                (pkg, DELETED, MERGE_LIST))}

        def holds_all(p, o):
            """o has every resource of p, with the same content"""
            mine, theirs = rows(p), rows(o)
            if not set(mine) <= set(theirs):
                return False
            for k in mine:
                loc[(p, k)], loc[(o, k)] = mine[k], theirs[k]
                if not same(p, o, k):
                    return False
            return True

        marked = {}
        try:
            for p in drop_first:
                ks = keys[p]
                if any(len(owners[k]) < 2 for k in ks):
                    continue
                holders = set.intersection(*(owners[k] for k in ks)) - {p} - set(marked)
                for o in sorted(holders, key=lambda o: (0 if root_of[o] == first else 1, -len(keys[o]), o)):
                    try:
                        if holds_all(p, o):
                            marked[p] = o
                            break
                    except OSError:
                        continue
        finally:
            for x in files.values():
                x.close()
        # a file marked as the copy of one that is marked later: name the one that stays
        for p in marked:
            o, seen = marked[p], {p}
            while o in marked and o not in seen:
                seen.add(o)
                o = marked[o]
            marked[p] = o
        self.db.execute('update item set dup_of=null')
        self.db.executemany('update item set dup_of=? where relkey=?',
                            [(rel_of[o], rel_of[p].lower()) for p, o in marked.items()])

    def _usage(self, lib, chosen, refs, save_names):
        """used / used_by for every package: does a current save or the Tray reference one of its CAS parts, looks
        or objects. Script mods and gameplay mods stay unknown (None)."""
        by_rel = {p.id: p.rel.lower() for p in chosen.values()}
        srcs = []                                        # (label, {category: ids})
        tray = collections.defaultdict(set)
        for s in refs.selected():
            ids = refs.by_fp.get(s.fp) or {}
            if s.kind == 'save':
                stem = s.name[:-5] if s.name.lower().endswith('.save') else s.name
                srcs.append((save_names.get(s.name) or save_names.get(stem) or stem, ids))
            elif s.kind != 'backup':
                for cat, v in ids.items():
                    tray[cat] |= set(v)
        if tray:
            srcs.append(('In-game library', tray))
        want = collections.defaultdict(lambda: collections.defaultdict(set))    # t -> instance -> source indexes
        cat_types = {U.PART: (T_CASP,), U.PART_OTHER: (T_CASP,), U.TONE: (T_TONE,), U.SCULPT: (T_SCUL,),
                     U.MODIFIER: (T_SMOD,), U.PELT: (T_PELT,), U.OBJECT: (T_OBJD, T_COBJ)}
        for n, (_label, ids) in enumerate(srcs):
            for cat, types in cat_types.items():
                for v in ids.get(cat, ()):
                    for t in types:
                        want[t][v].add(n)
        used = collections.defaultdict(set)
        for t, inst in want.items():
            for pkg, i in lib.db.execute('select pkg, i from res where t=? and comp != ?', (t, DELETED)):
                hit = inst.get(unsigned64(i))
                if hit and pkg in by_rel:
                    used[by_rel[pkg]] |= hit
        self.db.execute("update item set used=null, used_by=null")
        self.db.execute("update item set used=0 where kind='package' and category in (%s)" %
                        ','.join("'%s'" % c for c in sorted(CAS_CATEGORIES | {'buildbuy', 'walls', 'sliders'})))
        self.db.executemany('update item set used=1, used_by=? where relkey=?',
                            [(json.dumps(sorted(srcs[n][0] for n in hits)), rk) for rk, hits in used.items()])
        return True

    # ---------------------------------------------------------------- reading
    def state(self):
        n = self.db.execute('select count(*) from item').fetchone()[0]
        return {'state': 'ready' if n or self.meta('scanned') else 'missing', 'items': n,
                'when': self.meta('scanned'), 'used_known': self.meta('used_known') == '1',
                'complete': self.meta('complete', '1') == '1', 'generation': int(self.meta('generation', 0) or 0)}

    def _where(self, category=None, folder=None, creator=None, q=None, used=None, flag=None, skip=()):
        w, a = [], []
        if category and 'category' not in skip:
            w.append("(category = ? or (',' || cats || ',') like ?)")
            a += [category, '%%,%s,%%' % category]
        if folder is not None and folder != '' and 'folder' not in skip:
            w.append('folder = ?')
            a.append('' if folder == '(root)' else folder)
        if creator and 'creator' not in skip:
            w.append('creator = ?')
            a.append(creator)
        if q:
            for word in q.lower().split()[:6]:
                like = '%' + word.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
                w.append("(lower(rel) like ? escape '\\' or lower(coalesce(part_name, '')) like ? escape '\\' or "
                         "lower(coalesce(creator, '')) like ? escape '\\')")
                a += [like, like, like]
        if used == 'used':
            w.append('used = 1')
        elif used == 'unused':
            w.append('used = 0')
        if flag == 'duplicate':
            w.append('dup_of is not null')
        elif flag == 'broken':
            w.append('broken is not null')
        return (' where ' + ' and '.join(w)) if w else '', a

    def query(self, category=None, folder=None, creator=None, q=None, used=None, flag=None, sort='name', offset=0,
              limit=60):
        """One page of items plus counts: {'total', 'offset', 'limit', 'items', 'categories', 'counts'}."""
        limit = max(1, min(MAX_LIMIT, int(limit or 60)))
        offset = max(0, int(offset or 0))
        where, args = self._where(category, folder, creator, q, used, flag)
        total = self.db.execute('select count(*) from item' + where, args).fetchone()[0]
        rows = self.db.execute('select * from item%s order by %s limit ? offset ?' % (
            where, SORTS.get(sort, SORTS['name'])), args + [limit, offset])
        cols = [c[0] for c in rows.description]
        items = [dict(zip(cols, r)) for r in rows]
        # category counts under every filter except the category itself
        cw, ca = self._where(None, folder, creator, q, used, flag)
        counts = collections.Counter()
        for cat, cats, c in self.db.execute('select category, cats, count(*) from item%s group by category, cats'
                                            % cw, ca):
            for k in set((cats or cat or 'other').split(',')) | {cat}:
                counts[k] += c
        fw, fa = self._where(category, folder, creator, q, None, None)
        flags = dict(zip(('used', 'unused', 'duplicate', 'broken'), self.db.execute(
            'select sum(used = 1), sum(used = 0), sum(dup_of is not null), sum(broken is not null) from item' + fw,
            fa).fetchone()))
        return {'total': total, 'offset': offset, 'limit': limit, 'items': items,
                'categories': dict(counts), 'flags': {k: v or 0 for k, v in flags.items()}}

    def facets(self):
        """Folders and guessed creators with how many files each (for the filter lists)."""
        folders = [{'name': f or '(root)', 'n': n} for f, n in self.db.execute(
            'select folder, count(*) from item group by folder order by lower(folder)')]
        creators = [{'name': c, 'n': n} for c, n in self.db.execute(
            'select creator, count(*) c from item where creator is not null group by creator having c > 1 '
            'order by lower(creator)')]
        return {'folders': folders, 'creators': creators}

    def get(self, item_id):
        row = self.db.execute('select * from item where id=?', (int(item_id),))
        cols = [c[0] for c in row.description]
        r = row.fetchone()
        return dict(zip(cols, r)) if r else None

    def by_relkeys(self, relkeys):
        out = {}
        rks = list(relkeys)
        for n in range(0, len(rks), 500):
            part = rks[n:n + 500]
            cur = self.db.execute('select * from item where relkey in (%s)' % ','.join('?' * len(part)), part)
            cols = [c[0] for c in cur.description]
            for r in cur:
                d = dict(zip(cols, r))
                out[d['relkey']] = d
        return out

    def forget(self, ids):
        self.db.executemany('delete from item where id=?', [(int(i),) for i in ids])
        self.set_meta('generation', int(self.meta('generation', 0) or 0) + 1)
        self.db.commit()

    # ---------------------------------------------------------------- side folders (safe copies, Inbox, Downloads, Desktop)
    def _side_res(self, cur, entries):
        self.db.executemany('insert into side_res values(?,?,?)',
                            [(cur.lastrowid, e.t, signed64(e.i)) for e in entries])

    @staticmethod
    def _like_prefix(s):
        return s.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'

    def side_update(self, places, limit=20000):
        """Index the .package files under each (place, folder), including each .package entry inside a .zip
        there (directory entries ignored, entries over 512 MB uncompressed skipped, a broken zip skipped
        quietly): which CAS parts / objects / pictures they hold. A zip entry is stored as one row whose path
        is '<zip path>|<inner path>' (the inner path is never used to write anywhere - only its basename, kept
        separately as the row's plain display name). Unchanged files, and unchanged zips (by size + mtime),
        are not read again. Returns the number of files and zip archives looked at."""
        seen, seen_entries = set(), set()
        count = 0
        for place, folder in places:
            if not folder or not os.path.isdir(folder):
                continue
            for dp, dn, fn in os.walk(folder):
                for name in fn:
                    low = name.lower()
                    if low.endswith('.package'):
                        if count >= limit:
                            continue
                        count += 1
                        path = os.path.join(dp, name)
                        try:
                            st = os.stat(path)
                        except OSError:
                            continue
                        seen.add(path)
                        row = self.db.execute('select id, size, mtime from side_file where path=?', (path,)).fetchone()
                        if row and row[1] == st.st_size and abs(row[2] - st.st_mtime) < 1e-3:
                            continue
                        if row:
                            self.db.execute('delete from side_res where file=?', (row[0],))
                            self.db.execute('delete from side_file where id=?', (row[0],))
                        try:
                            with open_shared(path) as f:
                                entries = [e for e in read_entries(f) if e.comp != DELETED and e.t in (
                                    T_CASP, T_OBJD, T_COBJ, T_TONE, T_SCUL, T_SMOD, T_PELT)]
                        except Exception:
                            entries = []
                        cur = self.db.execute('insert into side_file(path, size, mtime, place, name) values(?,?,?,?,?)',
                                              (path, st.st_size, st.st_mtime, place, name))
                        self._side_res(cur, entries)
                    elif low.endswith('.zip'):
                        zpath = os.path.join(dp, name)
                        try:
                            zst = os.stat(zpath)
                        except OSError:
                            continue
                        seen.add(zpath)
                        prefix = self._like_prefix(zpath + '|')
                        zrow = self.db.execute('select size, mtime from side_zip where path=?', (zpath,)).fetchone()
                        if zrow and zrow[0] == zst.st_size and abs(zrow[1] - zst.st_mtime) < 1e-3:
                            for (p,) in self.db.execute("select path from side_file where path like ? escape '\\'",
                                                        (prefix,)):
                                seen_entries.add(p)
                            continue
                        old_ids = self.db.execute("select id from side_file where path like ? escape '\\'",
                                                  (prefix,)).fetchall()
                        for fid, in old_ids:
                            self.db.execute('delete from side_res where file=?', (fid,))
                        self.db.execute("delete from side_file where path like ? escape '\\'", (prefix,))
                        try:
                            zf = zipfile.ZipFile(zpath)
                        except Exception:
                            zf = None
                        if zf is not None:
                            try:
                                for info in zf.infolist():
                                    if info.is_dir() or not info.filename.lower().endswith('.package'):
                                        continue
                                    if info.file_size > SIDE_ZIP_MAX_BYTES or count >= limit:
                                        continue
                                    count += 1
                                    inner = info.filename.replace('\\', '/')
                                    disp = os.path.basename(inner) or inner
                                    vpath = '%s|%s' % (zpath, info.filename)
                                    try:
                                        with zf.open(info) as zsrc:
                                            # bounded regardless of what info.file_size claims: a crafted zip
                                            # can declare a small size and still decompress to much more
                                            data = zsrc.read(SIDE_ZIP_MAX_BYTES + 1)
                                        if len(data) > SIDE_ZIP_MAX_BYTES:
                                            continue
                                        entries = [e for e in read_entries(io.BytesIO(data)) if e.comp != DELETED and
                                                  e.t in (T_CASP, T_OBJD, T_COBJ, T_TONE, T_SCUL, T_SMOD, T_PELT)]
                                    except Exception:
                                        continue
                                    cur = self.db.execute(
                                        'insert or replace into side_file(path, size, mtime, place, name) '
                                        'values(?,?,?,?,?)', (vpath, zst.st_size, zst.st_mtime, place, disp))
                                    self._side_res(cur, entries)
                                    seen_entries.add(vpath)
                            except Exception:                # a zip that trips up mid-read: keep what was read
                                pass
                            finally:
                                zf.close()
                        self.db.execute('insert or replace into side_zip(path, size, mtime) values(?,?,?)',
                                        (zpath, zst.st_size, zst.st_mtime))
        for fid, path in self.db.execute('select id, path from side_file').fetchall():
            alive = (path in seen_entries) if '|' in path else (path in seen)
            if not alive:
                self.db.execute('delete from side_res where file=?', (fid,))
                self.db.execute('delete from side_file where id=?', (fid,))
        for zpath, in self.db.execute('select path from side_zip').fetchall():
            if zpath not in seen:
                self.db.execute('delete from side_zip where path=?', (zpath,))
        self.db.commit()
        return len(seen)

    def side_find(self, instances):
        """{instance: [(path, place, name, t)]} for the instances found in the side folders (path is a plain
        file path, or '<zip path>|<inner path>' for a copy found inside a .zip there)."""
        out = collections.defaultdict(list)
        inst = list(instances)
        for n in range(0, len(inst), 500):
            part = [signed64(v) for v in inst[n:n + 500]]
            for i, t, path, place, name in self.db.execute(
                    'select r.i, r.t, f.path, f.place, f.name from side_res r join side_file f on f.id = r.file '
                    'where r.i in (%s)' % ','.join('?' * len(part)), part):
                out[unsigned64(i)].append((path, place, name, t))
        return out

    def side_files(self):
        return [p for (p,) in self.db.execute('select path from side_file order by mtime desc')]


# ------------------------------------------------------------------------------------------ classifying one file
def _pick_thumb(rows, want_instances, types):
    """'t:g:i' of the best picture among rows [(t, g, i, fsize)]: one with a wanted instance first (biggest)."""
    best = None
    for pref in (True, False):
        for t, g, i, fs in rows:
            if t not in types or (pref and i not in want_instances):
                continue
            if best is None or fs > best[3]:
                best = (t, g, i, fs)
        if best:
            break
    return '%08X:%08X:%016X' % best[:3] if best else ''


def classify(lib, p):
    """What one library package is: {'category', 'cats', 'body', 'part_name', 'n_res', 'n_cas', 'n_obj', 'thumb',
    'broken'}. Reads the library index and at most SAMPLE_CASP CAS parts of the file."""
    out = {'category': 'other', 'cats': ['other'], 'body': None, 'part_name': None, 'n_res': p.n or 0, 'n_cas': 0,
           'n_obj': 0, 'thumb': '', 'broken': None}
    if p.err:
        out['broken'] = "This file is damaged: the game can't read it."
        return out
    if not p.n:
        out['broken'] = 'This file is empty.'
        return out
    db = lib.db
    types = collections.Counter(dict(db.execute('select t, count(*) from res where pkg=? and comp != ? group by t',
                                                (p.id, DELETED)).fetchall()))
    pics = [(t, g, unsigned64(i), fs) for t, g, i, fs in db.execute(
        'select t, g, i, fsize from res where pkg=? and comp != ? and t in (%s)' % ','.join(str(t) for t in ANY_PICS),
        (p.id, DELETED))]
    out['n_cas'] = types[T_CASP]
    out['n_obj'] = types[T_OBJD]
    out['merged'] = bool(types[T_MERGE_LIST])
    out['walls'], out['floors'], out['fences'] = types[T_CWAL], types[T_CFLR], types[T_CFEN]
    cats = collections.Counter()
    if types[T_CASP]:
        rows = db.execute('select g, i, off, fsize, msize, comp from res where pkg=? and t=? and comp != ? '
                          'order by off', (p.id, T_CASP, DELETED)).fetchall()
        step = max(1, len(rows) // SAMPLE_CASP)
        sample = rows[::step][:SAMPLE_CASP]
        path = locate(lib.roots, p.root, p.rel, p.size)
        infos = []
        if path:
            try:
                with open_shared(path) as f:
                    for g, i, off, fs, ms, comp in sample:
                        try:
                            f.seek(off)
                            info = casp_info(decompress(f.read(fs), comp, ms))
                        except Exception:
                            info = None
                        infos.append((unsigned64(i), info))
            except OSError:
                infos = []
        body_names = collections.Counter()
        # each sampled part stands for its share of all the file's CAS parts, so a big merge's outfits weigh what
        # they really are against its floors or objects (which are counted in full)
        share = types[T_CASP] / max(1, len(infos))
        for i, info in infos:
            cat, bname = body_category(info.get('body_type') if info else None)
            cats[cat] += share
            if info and info.get('body_type'):
                body_names[bname] += 1
        if not infos:
            cats['cas_other'] += 1
        primary = cats.most_common(1)[0][0]
        rep = next((i for i, info in infos if info and body_category(info.get('body_type'))[0] == primary), None)
        rep_info = next((info for i, info in infos if i == rep), None)
        out['part_name'] = (rep_info or {}).get('name') or next((info['name'] for _, info in infos
                                                                  if info and info.get('name')), None)
        out['body'] = body_names.most_common(1)[0][0] if body_names else None
        want = {rep} if rep is not None else set()
        out['thumb'] = (_pick_thumb(pics, want, CAS_PICS) or _pick_thumb(pics, {i for i, _ in infos}, CAS_PICS)
                        or _pick_thumb(pics, set(), CAS_PICS))
        if not out['thumb'] and rep is not None:
            out['thumb'] = 'cache:cas:%016X' % rep          # the game's own thumbnail cache may have it
        elif not out['thumb'] and rows:
            out['thumb'] = 'cache:cas:%016X' % unsigned64(rows[0][1])
    if types[T_TONE]:
        cats['skin'] += types[T_TONE]
    if types[T_PELT]:
        cats['pets'] += types[T_PELT]
    if not cats and (types[T_SMOD] or types[T_SCUL] or types[T_PRESET] or types[U.T_BGEO] or types[U.T_DMAP]):
        cats['sliders'] += 1
    if types[T_OBJD] or types[T_COBJ]:
        cats['buildbuy'] += max(types[T_OBJD], types[T_COBJ]) + (1 if not cats else 0)
        if not out['thumb'] or out['thumb'].startswith('cache:'):
            objs = {unsigned64(i) for (i,) in db.execute('select i from res where pkg=? and t in (?, ?) and comp != ?',
                                                         (p.id, T_OBJD, T_COBJ, DELETED))}
            th = _pick_thumb(pics, objs, OBJECT_PICS) or _pick_thumb(pics, set(), OBJECT_PICS)
            if th:
                out['thumb'] = th
            elif not out['thumb'] and objs:
                out['thumb'] = 'cache:object:%016X' % min(objs)
    if types[T_CWAL] or types[T_CFLR] or types[T_CFEN]:
        cats['walls'] += types[T_CWAL] + types[T_CFLR] + types[T_CFEN] + (1 if not cats else 0)
        if not out['thumb']:
            out['thumb'] = _pick_thumb(pics, set(), CAS_PICS + OBJECT_PICS)
    # animations count whatever else the file holds: a merged animation pack often carries props, outfits or
    # tuning too, and still belongs under Poses & animations (weighted by its number of clips, like the rest)
    if types[T_CLIP]:
        cats['poses'] += types[T_CLIP]
        if not out['thumb']:
            out['thumb'] = _pick_thumb(pics, set(), ANY_PICS)
    if not cats:
        if any(t not in ASSET_TYPES for t in types):
            cats['gameplay'] += 1
        else:
            cats['other'] += 1
        if not out['thumb']:
            out['thumb'] = _pick_thumb(pics, set(), ANY_PICS)
    order = [c for c, _ in cats.most_common()]
    out['category'] = order[0]
    out['cats'] = order
    return out


# ------------------------------------------------------------------------------------------ item pictures
def item_picture(idx, thumbs, item_id, roots, extra=None, lib=None):
    """(bytes, type) of one item's picture, or None (no picture, file gone, or not a picture). A file without a
    thumbnail of its own ('cache:<kind>:<instance>') borrows the same part's thumbnail from another library file
    (lib), else the game's thumbnail cache (extra)."""
    row = idx.get(item_id)
    if not row or not row.get('thumb'):
        return None
    th = row['thumb']
    if th.startswith('cache:'):
        _, kind, inst = th.split(':')
        if lib is not None:
            return part_picture(lib, thumbs, kind, int(inst, 16), extra)
        return _picture_from_extra(thumbs, extra, CAS_PICS if kind == 'cas' else OBJECT_PICS, int(inst, 16))
    try:
        t, g, i = (int(x, 16) for x in th.split(':'))
    except ValueError:
        return None
    k = thumbs.key(row['rel'], row['size'], row['mtime'], (t, g, i))
    hit = thumbs.get(k)
    if hit == 'none':
        return None
    if hit:
        return hit
    path = locate(roots, row['root'], row['rel'], row['size'])
    if not path:
        return None
    return thumbs.make(k, lambda: read_resource(path, (t, g, i)))


# ------------------------------------------------------------------------------------------ one save's CC
def _rows_by_instance(db, types, instances):
    """{instance: [(t, pkg)]} for every library resource of the types with one of the instances."""
    out = collections.defaultdict(list)
    if not instances:
        return out
    db.execute('drop table if exists temp.cc_want')
    db.execute('create temp table cc_want(i integer primary key)')
    db.executemany('insert or ignore into temp.cc_want values(?)', ((signed64(v),) for v in instances))
    for t in types:
        for pkg, i in db.execute('select pkg, i from res where t=? and comp != ? and i in (select i from temp.cc_want)',
                                 (t, DELETED)):
            out[unsigned64(i)].append((t, pkg))
    db.execute('drop table temp.cc_want')
    return out


def _hex(v):
    return '%016X' % v


def usage_report(lib, refs, game=None, idx=None, played_household=None, skip=None, side=None, limit_sims=400):
    """The CC one save (or the Tray) uses, from usedpack Refs narrowed to it (savepacks.save_refs):
      files:      [{'relkey', 'rel', 'root', 'name', 'folder', 'item' (index row or None), 'parts', 'objects',
                    'looks', 'first_part', 'first_object', 'sims'}] - installed CC files it uses, most used first
      households: [{'name', 'id', 'played', 'sims': [{'name', 'role', 'files': [file index], 'parts', 'missing'}]}]
      missing:    [{'id', 'key', 'kind', 'sims', 'households', 'found': [{'place', 'name', 'path'}]}]
      counts:     {'files', 'parts', 'objects', 'looks', 'missing', 'sims'}
    game: usedpack.GameIds (EA's own ids) or None (then ids below 2^32 are taken to be EA's). skip(rel) leaves out
    SpeedKit's own packs. side: a CCIndex whose side folders were indexed (safe copies, Inbox)."""
    skip = skip or (lambda rel: False)
    parts = refs.ids(U.PART) | refs.ids(U.PART_OTHER)
    objs = refs.ids(U.OBJECT)
    looks = {}
    for cat, t in U.LOOK_CATS:
        for v in refs.ids(cat):
            looks[v] = t
    pkgs = {p.id: p for p in lib.packages()}
    own = {pid for pid, p in pkgs.items() if skip(p.rel)}
    load = lib.order_positions(tuple(lib.roots))       # a part in several files: the first loaded copy is worn

    def by_load(rows):
        return sorted((r for r in rows if r[1] not in own), key=lambda r: load.get(r[1], 1 << 40))

    def is_ea(t, v):
        if game is not None:
            return game.has(t, v)
        return v < BIG

    cas_rows = _rows_by_instance(lib.db, (T_CASP,), parts)
    obj_rows = _rows_by_instance(lib.db, (T_OBJD, T_COBJ), objs)
    look_rows = _rows_by_instance(lib.db, sorted(set(looks.values())), set(looks))
    files = {}

    def add(pkg, what, v):
        p = pkgs.get(pkg)
        if p is None or pkg in own:
            return None
        rk = p.rel.lower()
        f = files.get(rk)
        if f is None:
            f = files[rk] = {'relkey': rk, 'rel': p.rel, 'root': p.root, 'name': os.path.basename(p.rel),
                             'folder': folder_of(p.rel), 'parts': set(), 'objects': set(), 'looks': set(), 'sims': set()}
        elif p.root == 'Mods' and f['root'] != 'Mods':
            f['root'] = 'Mods'
        f[what].add(v)
        return rk

    part_file = {}
    missing = {}
    for v in parts:
        if is_ea(T_CASP, v):
            continue
        rows = by_load(cas_rows.get(v, ()))
        if rows:
            for t, pkg in rows:
                rk = add(pkg, 'parts', v)
                if rk:
                    part_file.setdefault(v, rk)
        elif v >= BIG and not cas_rows.get(v):
            missing[v] = {'kind': 'cas', 't': T_CASP}
    objs_found = set()
    for v in objs:
        if is_ea(T_OBJD, v) or (game is not None and game.has(T_COBJ, v)):
            continue
        rows = [r for r in obj_rows.get(v, ()) if r[1] not in own]
        if rows:
            objs_found.add(v)
            for t, pkg in rows:
                add(pkg, 'objects', v)
        elif v >= BIG and not obj_rows.get(v):
            missing[v] = {'kind': 'object', 't': T_OBJD}
    for v, t in looks.items():
        if is_ea(t, v):
            continue
        rows = by_load(look_rows.get(v, ()))
        if rows:
            for tt, pkg in rows:
                rk = add(pkg, 'looks', v)
                if rk:
                    part_file.setdefault(v, rk)
        elif v >= BIG and not look_rows.get(v):
            missing[v] = {'kind': 'look', 't': t}
    # sims and households
    order = sorted(files.values(), key=lambda f: (-(len(f['parts']) + len(f['objects']) + len(f['looks'])),
                                                  f['name'].lower()))
    pos = {f['relkey']: n for n, f in enumerate(order)}
    hh = collections.OrderedDict()
    miss_sims = collections.defaultdict(set)
    miss_hh = collections.defaultdict(set)
    n_sims = 0
    for s in refs.sim_list():
        n_sims += 1
        worn = s.parts | s.looks
        fl = sorted({pos[part_file[v]] for v in worn if v in part_file and part_file[v] in pos})
        miss = [v for v in worn if v in missing]
        name = s.name or ('(mannequin)' if s.role == 'mannequin' else 'A sim without a name')
        hname = s.household or ('Mannequins' if s.role == 'mannequin' else 'Sims without a household')
        for v in worn:
            rk = part_file.get(v)
            if rk in files and len(files[rk]['sims']) < 50:
                files[rk]['sims'].add(name)
        for v in miss:
            miss_sims[v].add(name)
            miss_hh[v].add(hname)
        if not fl and not miss:
            continue
        key = (hname, s.household_id)
        h = hh.get(key)
        if h is None:
            h = hh[key] = {'name': hname, 'id': _hex(s.household_id or 0), 'sims': [],
                           'played': bool(played_household) and s.household_id == played_household}
        if len(h['sims']) < limit_sims:
            h['sims'].append({'name': name, 'role': s.role, 'files': fl,
                              'parts': sum(1 for v in worn if v in part_file), 'missing': len(miss)})
    households = sorted(hh.values(), key=lambda h: (not h['played'], h['name'] == 'Mannequins', h['name'].lower()))
    for h in households:
        h['sims'].sort(key=lambda s: (-s['missing'], -s['parts'], s['name'].lower()))
    # what is known about missing CC (also in Downloads / Desktop, plain or inside a .zip - side.side_find)
    found = side.side_find(missing) if (side is not None and missing) else {}
    miss_out = []
    for v, m in sorted(missing.items(), key=lambda kv: (-len(miss_sims.get(kv[0], ())), kv[1]['kind'], kv[0])):
        places = []
        for path, place, name, t in found.get(v, ()):
            if (place, name) not in [(x['place'], x['name']) for x in places]:
                zip_name = os.path.basename(path.split('|', 1)[0]) if '|' in path else None
                places.append({'place': place, 'name': name, 'path': path, 'creator': guess_creator(name),
                               'zip': zip_name})
        miss_out.append({'id': _hex(v), 'key': '%08X:00000000:%s' % (m['t'], _hex(v)), 'kind': m['kind'],
                         'sims': sorted(miss_sims.get(v, ()))[:12], 'sims_count': len(miss_sims.get(v, ())),
                         'households': sorted(miss_hh.get(v, ()))[:6], 'found': places[:3]})
    rows = idx.by_relkeys([f['relkey'] for f in order]) if idx is not None else {}
    out_files = []
    for f in order:
        out_files.append({'relkey': f['relkey'], 'rel': f['rel'], 'root': f['root'], 'name': f['name'],
                          'folder': f['folder'], 'item': rows.get(f['relkey']), 'parts': len(f['parts']),
                          'objects': len(f['objects']), 'looks': len(f['looks']),
                          'first_part': _hex(min(f['parts'])) if f['parts'] else None,
                          'first_object': _hex(min(f['objects'])) if f['objects'] else None,
                          'sims': sorted(f['sims'])[:8], 'sims_count': len(f['sims'])})
    counts = {'files': len(out_files), 'parts': sum(1 for v in parts if v in part_file),
              'objects': len(objs_found), 'looks': sum(1 for v in looks if v in part_file),
              'missing': len(miss_out), 'sims': n_sims, 'found': sum(1 for m in miss_out if m['found'])}
    return {'files': out_files, 'households': households, 'missing': miss_out, 'counts': counts}


# ------------------------------------------------------------------------------------------ setting files aside
def set_aside(idx, ids, sims, home, check_game=True, progress=None, journal_cls=None):
    """Move CC files out of Mods into the Hub's safe copies (<home>\\quarantine\\<change id>\\...) through one
    Journal of kind 'setaside', so 'Undo last change' puts them back. Script mods, files in the set-aside
    folder (a mode switch put them there) and files that changed since the last look are refused.
    Returns {'journal', 'done': [names], 'refused': [(name, why)]}."""
    from .journal import Journal
    J = journal_cls or Journal
    tell = progress or (lambda *a, **k: None)
    mods = os.path.join(sims, 'Mods')
    ok, refused = [], []
    for iid in ids:
        row = idx.get(iid)
        if not row:
            refused.append(('#%s' % iid, 'It is no longer in the CC list. Use "Look again".'))
            continue
        name = row['name']
        if row['kind'] == 'script':
            refused.append((name, 'Script mods are not changed by the Hub.'))
            continue
        path = os.path.join(mods, row['rel'].replace('/', os.sep))
        if row['root'] != 'Mods' or not os.path.isfile(path):
            refused.append((name, "It is not in the Mods folder right now (moved out by Quick Start or one-save mode). "
                                  "Switch to Full Start first."))
            continue
        st = os.stat(path)
        if st.st_size != row['size'] or abs(st.st_mtime - row['mtime']) > 1e-3:
            refused.append((name, 'It changed since the last look. Use "Look again" first.'))
            continue
        ok.append((row, path))
    if not ok:
        return {'journal': None, 'done': [], 'refused': refused}
    names = [r['name'] for r, _ in ok]
    note = 'set aside %d CC file%s: %s' % (len(ok), '' if len(ok) == 1 else 's', ', '.join(names[:5]) +
                                           (' ...' if len(names) > 5 else ''))
    done = []
    try:
        with J('setaside', note, home=home, sims=sims, check_game=check_game) as j:
            for n, (row, path) in enumerate(ok):
                tell('setaside', round(n / len(ok), 3), 'Setting aside %s' % row['name'])
                j.quarantine(path)
                done.append(row)
    finally:
        if done:
            idx.forget([r['id'] for r in done])
    return {'journal': j.id, 'done': [r['name'] for r in done], 'refused': refused}
