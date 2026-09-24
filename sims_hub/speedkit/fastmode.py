"""fastmode - the FAST profile: which packages it leaves out, and the small pack that keeps everything working.

The library holds 755,662 CAS parts (CASP index entries); 755,461 of them sit in the 189 S4S-merged
packs under sim/ (research 'lagdrivers': startup cost follows the number of CAS parts, not GB). The fast
profile parks those CAS catalogs and loads, in their place, one small pack that holds exactly what the
rest of the game still needs from them:

    parked = park_set(lib)                       # [(root, rel)] the fast profile leaves out (+ .reasons)
    plan = plan_pack(lib, refs, parked)          # read-only: which resources, from which copy, and why
    build_pack(plan)                             # dry run: the package layout
    build_pack(plan, dry_run=False)              # SIMS\\SpeedKit\\fastpack\\!!!!!SpeedKit_Fast_001.package ...
    status()                                     # fresh / stale, and why
    update_pack(lib, refs, dry_run=False)        # a small delta package, or a rebuild when needed
    verify(lib, refs)                            # what fast mode would miss compared to the full library

What the pack holds (plan_pack), each key as the copy the FULL library uses (first in lib.load_order over
Mods + Mods_parked), and only when that copy is in a parked package:
  (a) usedpack.plan(): the CC the saves and Tray use (worn CAS parts with their meshes/textures/thumbnails,
      skin tones, sculpts, sliders, pet coats, lot objects, every CC wall/floor, and the default
      replacements of worn EA items);
  (b) every non-asset resource of the parked packages - XML tuning of every type, SimData, string tables,
      animations (ASM/CLIP/CLHD), sounds, anything unknown - plus every key that overrides one of EA's
      (speedkit.game_index), plus every key a kept package also has but a parked copy wins ("shadowed"),
      so script mods, animations and default replacements behave as with the whole library. EA-override
      and shadowed CAS parts / objects / tones / sliders are added with their whole closure (a CAS part
      without its meshes and textures would show broken);
  (c) CAS parts, objects, tones, sculpts, sliders and pet coats that stay needed without a save naming
      them: the ones kept packages list themselves (their closure), and every CC id (64-bit, or a 32-bit
      one the game does not ship) found in the XML tuning / SimData that stays loaded (kept packages + the
      pack) or hard-coded in a .ts4script, when a parked package holds it - again with its whole closure
      (usedpack's CASP key-list code is reused by handing usedpack.plan() the ids); plus every asset key
      that tuning writes out in full as 'type:group:instance' (icons such as WickedWhims'
      cas_part_display_icon).
The S4S manifest (0x7FB6AD8A), NameMap (0x0166038C) and S4S's batch-fix history (0x6BF15BBE) are never
packed: the game does not read them, and a stray manifest would confuse Sims 4 Studio.

The pack files are named '!!!!!SpeedKit_Fast_###.package': in the game's NTFS walk (upper-cased ordinal
name order; a folder is entered where its name comes up) that sorts before every name the library has
(letters, digits, '!!!Mods/'...), so the pack loads first and each of its keys wins over any stale copy in
a kept package - the fast profile uses the same copy of every key the full library does. Only a name
starting with 6+ '!' (or '!!!!!' and a character below 'S', or a space) would load before it: plan_pack
reports such kept packages (stats['loads_before_pack']) and verify() flags a pack key they also hold.
Inside, catalog records come first (CASP, THUM, TONE, OBJD, COBJ, SimData, tuning, STBL), then meshes,
textures and clips.

Nothing here touches Mods or Mods_parked (the profile switcher moves packages). build_pack/update_pack
write only into SIMS\\SpeedKit\\fastpack (outside Mods, so the game running does not matter there) through
a Journal, and roll back on failure. fastpack.json always stays in that folder; the profile switcher may
move the pack's .package files to the Mods root - status(), update_pack() and verify() find them there.
"""
import collections
import hashlib
import json
import os
import re
import shutil
import time
import zlib

import numpy as np

from .dbpf import Package, PackageWriter, DBPFError, read_entries, decompress, open_shared, DELETED, ZLIB
from .library import SIMS, SKIP_DIRS, game_running, ntfs_key, unsigned64
from .journal import Journal, JournalError
from . import usedpack as U
from . import companions

ROOTS2 = ('Mods', 'Mods_parked')
DEFAULT_OUT = os.path.join(SIMS, 'SpeedKit', 'fastpack')
PACK_PREFIX = '!!!!!SpeedKit_Fast_'
PACK_NAME = PACK_PREFIX + '%03d.package'
DELTA_FIRST = 900                      # delta packages are numbered 900, 901, ...
DELTA_LIMIT = 500_000_000              # above this (all deltas together) update_pack rebuilds instead
MANIFEST = 'fastpack.json'
KEYS_FILE = 'fastpack_keys.tsv'
FREE_MARGIN = 1 << 30
MAX_XML = 8 << 20
BIG = 1 << 32
MANIFEST_VERSION = 1

# ------------------------------------------------------------------------------------------ types
T_MANIFEST, T_NAMEMAP, T_S4S_HISTORY = 0x7FB6AD8A, 0x0166038C, 0x6BF15BBE
T_ASM, T_CLIP, T_CLHD = 0x02D5DF13, 0x6B20C4F3, 0xBC4A5044
T_CPRE, T_SIMO = 0xEAA32ADD, 0x025ED6F4
T_AUDIO, T_VIDEO = 0x01A527DB, 0x376840D7
SIMS3_CAS = {0x736884F1, 0x033A1435, 0x0333406C, 0x062C8204}   # listed only by dead Sims 3 (v18) CASPs
CAS_ASSETS = {U.T_CASP, U.T_THUM, U.T_TONE, U.T_GEOM, U.T_RLE2, U.T_LRLE, U.T_RLES, U.T_IMG, U.T_DST, U.T_RMAP,
              U.T_BOND, U.T_BGEO, U.T_DMAP, U.T_SCUL, U.T_SMOD, U.T_HSC, U.T_PELT, T_CPRE, T_SIMO} | SIMS3_CAS
BB_ASSETS = {U.T_OBJD, U.T_COBJ, U.T_OTHM, U.T_MODL, U.T_MLOD, U.T_FTPT, U.T_RSLT, U.T_LITE, U.T_RIG, U.T_MATD,
             U.T_CWAL, U.T_CFLR}
ASSET_TYPES = CAS_ASSETS | BB_ASSETS
SKIP_TYPES = {T_MANIFEST, T_NAMEMAP, T_S4S_HISTORY}
# catalog records that need their closure (meshes, textures, ...) to work, and the usedpack id category
# that makes usedpack.plan() add them with it
CATALOG = {U.T_CASP: U.PART, U.T_TONE: U.TONE, U.T_SCUL: U.SCULPT, U.T_SMOD: U.MODIFIER, U.T_PELT: U.PELT,
           U.T_OBJD: U.OBJECT, U.T_COBJ: U.OBJECT}
TYPE_NAMES = dict(U.TYPE_NAMES)
TYPE_NAMES.update({T_ASM: 'ASM', T_CLIP: 'CLIP', T_CLHD: 'CLHD', T_CPRE: 'CPRE', T_SIMO: 'SIMO', T_AUDIO: 'AUDIO',
                   T_VIDEO: 'VIDEO', 0x6017E896: 'BUFF', 0xE882D22F: 'INTERACTION'})

# pack order: catalog records first, then the rest of the small data, then meshes / textures / clips
RANK = {U.T_CASP: 0, U.T_THUM: 1, U.T_TONE: 2, U.T_OBJD: 3, U.T_COBJ: 4, U.T_SIMDATA: 5}
R_TUNING, R_STBL, R_SMALL_ASSET, R_BULK = 6, 7, 8, 9
BULK_TYPES = set(U.BULK_TYPES) | {T_CLIP, T_CLHD, T_AUDIO, T_VIDEO}

# ------------------------------------------------------------------------------------------ park rules
PARK_MIN_CASP = 20            # a CAS catalog: at least this many CAS parts ...
PARK_MIN_SHARE = 0.6          # ... and at least this share of its bytes CAS/BuildBuy assets
BIG_CAS_BYTES = 50_000_000    # or one big standalone CAS file (a 200 MB hair with 3 parts)
BIG_CAS_SHARE = 0.8
MERGED_COMPANION_MIN_CASP = 200     # an S4S merge the classifier ties to a script is parked only when it is
MERGED_COMPANION_MAX_SCRIPT = 0.10  # a real CC catalog whose script content is a small part
COMPANION_KINDS = ('core', 'addon', 'orphan', 'weak')
PLAN_RULES_VERSION = 2              # bump when plan_pack starts carrying more: packs of older rules are stale


def rules_fingerprint():
    """The rules a pack was planned with (park thresholds, companion rules, plan version). A pack built
    under other rules may lack what a package parked only under the new ones holds, so status() calls it
    stale even when no file changed."""
    rules = (PLAN_RULES_VERSION, PARK_MIN_CASP, PARK_MIN_SHARE, BIG_CAS_BYTES, BIG_CAS_SHARE,
             MERGED_COMPANION_MIN_CASP, MERGED_COMPANION_MAX_SCRIPT, COMPANION_KINDS, companions.RULES_VERSION)
    return hashlib.blake2b(repr(rules).encode(), digest_size=8).hexdigest()


def tname(t):
    """Short name of a resource type (hex when unknown)."""
    return TYPE_NAMES.get(t, '%08X' % t)


def key_text(k):
    return '%08X:%08X:%016X' % k


class FastPackError(Exception):
    """The fast pack cannot be built or updated as asked (the message says why and what to do)."""


# ------------------------------------------------------------------------------------------ pack families
SAVE_PREFIX = '!!!!!SpeedKit_Save_'     # per-save packs: '!!!!!SpeedKit_Save_<slot hex>_###.package'
SAVE_MANIFEST = 'savepack.json'
SAVE_KEYS_FILE = 'savepack_keys.tsv'
_PACK_RX = re.compile(r'^(!!!!!SpeedKit_Fast_\d{3}|!!!!!SpeedKit_Save_[0-9A-Fa-f]{8}_\d{3}|SpeedKit_UsedCC_\d{3})'
                      r'\.package$', re.I)
_SAVE_PACK_RX = re.compile(r'^!!!!!SpeedKit_Save_([0-9A-Fa-f]{8})_(\d{3})\.package$', re.I)
MONITOR_REL = 'SpeedKit_Monitor.ts4script'


class PackKind:
    """One family of SpeedKit packs: how its files are named and which save/Tray files it is planned from.

    FAST (the fast profile's pack, planned from every current save + Tray) and, per save slot, the save
    pack of speedkit.savepacks (planned from that one save file). Every function that finds, builds or
    checks a pack takes kind=...; the default is FAST. File names are exact: '<prefix>###.package'."""

    def __init__(self, prefix, manifest, keys_file, label, journal_kind, save_file=None):
        self.prefix = prefix
        self.manifest = manifest
        self.keys_file = keys_file
        self.label = label
        self.journal_kind = journal_kind
        self.save_file = save_file          # None: every current save + Tray counts; else only this save file
        self._rx = re.compile('^' + re.escape(prefix) + r'(\d{3})\.package$', re.I)

    def name(self, n):
        return '%s%03d.package' % (self.prefix, n)

    def matches(self, name):
        return bool(self._rx.match(name))

    def number(self, name):
        m = self._rx.match(name)
        return int(m.group(1)) if m else None

    def counts(self, path, kind):
        """Does this save/Tray source (usedpack.list_sources) count for this pack?"""
        if self.save_file is None:
            return kind != 'backup'
        return kind == 'save' and os.path.basename(path).lower() == self.save_file.lower()

    def __repr__(self):
        return '<PackKind %s>' % self.prefix


FAST = PackKind(PACK_PREFIX, MANIFEST, KEYS_FILE, 'fast pack', 'fastpack')


def save_kind(slot):
    """The PackKind of the save pack of one save slot ('Slot_00000014'; the 8 hex digits are kept)."""
    m = re.match(r'^Slot_([0-9A-Fa-f]{8})$', slot or '')
    if not m:
        raise ValueError('not a save slot name: %r (expected Slot_ + 8 hex digits)' % (slot,))
    return PackKind(SAVE_PREFIX + m.group(1).lower() + '_', SAVE_MANIFEST, SAVE_KEYS_FILE,
                    'save pack of %s' % slot, 'savepack', save_file=slot + '.save')


def save_pack_slot(name):
    """'Slot_<hex>' for a save pack file name ('!!!!!SpeedKit_Save_<hex>_###.package'), else None."""
    m = _SAVE_PACK_RX.match(os.path.basename(name.replace('\\', '/')))
    return 'Slot_' + m.group(1).lower() if m else None


def is_speedkit_pack(rel):
    """True for SpeedKit's own pack files, by exact name: '!!!!!SpeedKit_Fast_###.package' (this module),
    '!!!!!SpeedKit_Save_<8 hex>_###.package' (speedkit.savepacks) and 'SpeedKit_UsedCC_###.package'
    (usedpack), wherever they sit. They are never the user's mods, so plans and library fingerprints
    ignore them."""
    return bool(_PACK_RX.match(rel.replace('\\', '/').rsplit('/', 1)[-1]))


def is_speedkit_file(rel):
    """SpeedKit's own files, by exact name: the two pack patterns and Mods\\SpeedKit_Monitor.ts4script (at the
    Mods root). Only these are exempt from parking and from the library fingerprint. Everything else -
    including the merger's 'SpeedKit Merged\\<Category>_NNN.package' and 'SpeedKit Loose\\' files - is the
    user's CC and follows the normal rules."""
    rel = rel.replace('\\', '/')
    return is_speedkit_pack(rel) or rel.lower() == MONITOR_REL.lower()


class LibraryView:
    """A Library without SpeedKit's own pack files. When the fast pack sits in the Mods root (the fast
    profile) a rescan indexes it; it holds the winners' copies and loads first, so counting it as a mod
    would make every plan think the kept packages already provide everything. Everything else is the
    wrapped Library's (usedpack and companions accept the view in its place)."""

    def __init__(self, lib):
        self.lib = lib
        self.db = lib.db
        self.db_path = lib.db_path
        self.roots = lib.roots

    def __getattr__(self, name):
        return getattr(self.lib, name)

    def path(self, root, rel):
        return self.lib.path(root, rel)

    def packages(self, root=None):
        return [p for p in self.lib.packages(root) if not is_speedkit_pack(p.rel)]

    def load_order(self, roots=ROOTS2, max_depth=None):
        order = self.lib.load_order(roots) if max_depth is None else self.lib.load_order(roots, max_depth)
        return [x for x in order if not is_speedkit_pack(x[1])]

    def order_positions(self, roots=ROOTS2):
        ids = _ids(self)
        return {ids[k]: n for n, k in enumerate(self.load_order(roots)) if k in ids}


def _view(lib):
    return lib if isinstance(lib, LibraryView) else LibraryView(lib)


def _roots(roots):
    return (roots,) if isinstance(roots, str) else tuple(roots)


def _ids(view):
    return {(r, rel): pid for pid, r, rel in view.db.execute('select id, root, rel from pkg')}


def _sims_of(root_dirs):
    """The Sims 4 folder holding a library's roots (their common parent). A library whose roots do not
    share a parent has no Sims folder: refuse rather than fall back to the real one."""
    parents = {os.path.normcase(os.path.dirname(os.path.abspath(d))) for d in root_dirs.values()}
    if len(parents) != 1:
        raise ValueError('the library roots %s do not share one Sims 4 folder; pass sims= explicitly' % root_dirs)
    return os.path.dirname(os.path.abspath(next(iter(root_dirs.values()))))


def _inside(path, base):
    path, base = os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.abspath(base))
    return path == base or path.startswith(base.rstrip('\\/') + os.sep)


def loads_before(rel, name=PACK_NAME % 1):
    """Does the package at this Mods-relative path load before the pack file `name` in the Mods root? The
    game walks Mods in NTFS name order (upper-cased, ordinal) and enters a folder where its name comes up,
    so only the first part of the path counts: '!!!!!!Early.package' or a ' Space' folder load first,
    '!!!Mods/' and '000/' after the pack."""
    first = rel.replace('\\', '/').split('/')[0]
    return ntfs_key(first) < ntfs_key(name)


def _package_stats(view, pids):
    """{pkg_id: Counter(entries, bytes, casp, cas_bytes, bb_bytes, other_bytes, meta_bytes, merged)} (live entries)."""
    out = {pid: collections.Counter() for pid in pids}
    for pid, t, n, b in view.db.execute('select pkg, t, count(*), sum(fsize) from res where comp != ? group by pkg, t',
                                        (DELETED,)):
        c = out.get(pid)
        if c is None:
            continue
        c['entries'] += n
        c['bytes'] += b
        if t == U.T_CASP:
            c['casp'] += n
        if t == T_MANIFEST:
            c['merged'] = 1
        if t in SKIP_TYPES:
            c['meta_bytes'] += b
        elif t in CAS_ASSETS:
            c['cas_bytes'] += b
        elif t in BB_ASSETS:
            c['bb_bytes'] += b
        else:
            c['other_bytes'] += b
    return out


# ------------------------------------------------------------------------------------------ park_set
class ParkSet(list):
    """The packages the FAST profile leaves out: a list of (root, rel) in load order.

    reasons: {(root, rel): short reason}; kept: [(root, rel)] of the loaded packages it keeps, with
    keep_reasons; info: {(root, rel): {'casp', 'bytes', 'asset_share', 'script_share', 'kind'}};
    stats: counts, bytes and CAS parts parked / kept."""

    def __init__(self, items=()):
        super().__init__(items)
        self.reasons = {}
        self.kept = []
        self.keep_reasons = {}
        self.info = {}
        self.stats = {}

    def rels(self):
        """Set of the parked relative paths (the profile switcher works by rel; roots change on every switch)."""
        return {rel for _, rel in self}


def _decide(rel, st, verdict, err):
    """(park?, reason) for one loaded package."""
    low = rel.replace('\\', '/').lower()
    top = low.split('/')[0] if '/' in low else ''
    if top == 'fitstudio':
        return False, 'FitStudio (the animation studio mod)'
    if top == 'animation':
        return False, 'WickedWhims animation pack (animation/ folder)'
    if is_speedkit_file(rel):
        return False, 'SpeedKit file'
    if err:
        return False, 'index unreadable (%s): left as it is' % err
    body = max(1, st['bytes'] - st['meta_bytes'])
    asset = st['cas_bytes'] + st['bb_bytes']
    share = asset / body
    casp = st['casp']
    heavy = ((casp >= PARK_MIN_CASP and share >= PARK_MIN_SHARE)
             or (casp >= 1 and asset >= BIG_CAS_BYTES and share >= BIG_CAS_SHARE))
    if not heavy:
        return False, 'not a CAS catalog (%d CAS parts, %d%% CAS/BuildBuy assets)' % (casp, round(100 * share))
    if verdict is None:
        return False, 'no companion verdict for it: kept to be safe'
    if verdict.kind in COMPANION_KINDS:
        script = st['other_bytes'] / body
        if st['merged'] and casp >= MERGED_COMPANION_MIN_CASP and script <= MERGED_COMPANION_MAX_SCRIPT:
            return True, ('S4S-merged CC pack (%d CAS parts, %.2f GB) with some script-mod content (%s); that '
                          'content (%.1f MB) goes into the fast pack' % (casp, st['bytes'] / 1e9, verdict.kind,
                                                                        st['other_bytes'] / 1e6))
        return False, 'script-mod companion (%s of %s)' % (verdict.kind, verdict.script or 'a missing script')
    if verdict.kind in ('broken', 'empty'):
        return False, 'classified %s: left as it is' % verdict.kind
    return True, 'CAS catalog: %d CAS parts, %.2f GB, %d%% CAS/BuildBuy assets' % (casp, st['bytes'] / 1e9,
                                                                                 round(100 * share))


def park_set(lib, roots=ROOTS2, verdicts=None, cache_path=companions.DEFAULT_CACHE, game_dir=companions.GAME_DIR):
    """The packages the FAST profile leaves out, as a ParkSet: a list of (root, rel) (plus .reasons).

    Parked: CAS-heavy CC catalogs - at least PARK_MIN_CASP CAS parts with >= 60% of the bytes CAS/BuildBuy
    assets, or one big (>= 50 MB, >= 80% assets) standalone CAS file. In practice that is the sim/ merges;
    tuning, slider, preset and skin/default-replacement packages have few or no CAS parts and stay.
    Never parked: .ts4script files (only packages are considered), anything under animation/ (the
    WickedWhims animation packs) or FitStudio/, SpeedKit's own files, unreadable packages, and packages
    speedkit.companions classifies core/addon/orphan/weak - except an S4S-merged CC pack with at least
    MERGED_COMPANION_MIN_CASP CAS parts whose script content (non-asset bytes) is at most 10%: that one is
    parked and plan_pack() carries its script content in the fast pack. Packages the game never loads
    (deeper than Resource.cfg reaches, or a Mods_parked copy shadowed by the same path in Mods) are in
    neither list. verdicts: {pkg_id: companions.Verdict}; computed with companions.classify(cache_path,
    game_dir) when None. Read-only."""
    view = _view(lib)
    roots = _roots(roots)
    ids = _ids(view)
    loaded = [(k, ids[k]) for k in view.load_order(roots) if k in ids]
    stats = _package_stats(view, {pid for _, pid in loaded})
    errs = {p.id: p.err for p in view.packages()}
    if verdicts is None:
        verdicts = companions.classify(view, roots, cache_path=cache_path, game_dir=game_dir)
    out = ParkSet()
    tot = collections.Counter()
    for key, pid in loaded:
        st = stats[pid]
        v = verdicts.get(pid)
        park, why = _decide(key[1], st, v, errs.get(pid))
        body = max(1, st['bytes'] - st['meta_bytes'])
        out.info[key] = {'casp': st['casp'], 'bytes': st['bytes'], 'kind': v.kind if v else None,
                         'asset_share': round((st['cas_bytes'] + st['bb_bytes']) / body, 3),
                         'script_share': round(st['other_bytes'] / body, 3)}
        side = 'parked' if park else 'kept'
        tot[side] += 1
        tot[side + '_bytes'] += st['bytes']
        tot[side + '_casp'] += st['casp']
        if park:
            out.append(key)
            out.reasons[key] = why
        else:
            out.kept.append(key)
            out.keep_reasons[key] = why
    out.stats = {'loaded': len(loaded), 'parked': tot['parked'], 'parked_bytes': tot['parked_bytes'],
                 'parked_casp': tot['parked_casp'], 'kept': tot['kept'], 'kept_bytes': tot['kept_bytes'],
                 'kept_casp': tot['kept_casp'], 'full_casp': tot['parked_casp'] + tot['kept_casp']}
    return out


# ------------------------------------------------------------------------------------------ plan
FastItem = collections.namedtuple('FastItem', 't g i pkg off fsize msize comp why part')


class FastPlan:
    """What the fast pack holds.

    items: {(t, g, i): FastItem} - the full-library winner copy of each key (always in a parked package),
    part 'a' (saves/Tray), 'b' (script/tuning content, EA overrides, shadowed keys) or 'c' (needed by kept
    CC, tuning, SimData or scripts). packages: {pkg_id: {'root', 'rel', 'size', 'mtime'}} the copies come
    from. parked: the ParkSet it was planned for. stats: counts and bytes (see summary()). sources: the
    saves/Tray fingerprints. library: [[rel, size, mtime]] of every mod file (the library fingerprint).
    absent / unloadable / households: usedpack's report of CC the saves use that is installed nowhere."""

    def __init__(self):
        self.items = {}
        self.packages = {}
        self.parked = ParkSet()
        self.roots = ROOTS2
        self.root_dirs = {}
        self.sims = None
        self.sources = []
        self.include_backups = False
        self.library = []
        self.library_fp = ''
        self.absent = {}
        self.unloadable = {}
        self.households = []
        self.stats = {}

    def total_bytes(self):
        return sum(it.fsize for it in self.items.values())

    def summary(self):
        """{'keys', 'bytes', 'parts': {part: {'keys', 'bytes'}}, 'by_type': {name: [keys, bytes]}, 'cas_parts'}."""
        parts = {p: {'keys': 0, 'bytes': 0} for p in 'abc'}
        by_t = collections.defaultdict(lambda: [0, 0])
        for it in self.items.values():
            parts[it.part]['keys'] += 1
            parts[it.part]['bytes'] += it.fsize
            by_t[tname(it.t)][0] += 1
            by_t[tname(it.t)][1] += it.fsize
        return {'keys': len(self.items), 'bytes': self.total_bytes(), 'parts': parts,
                'by_type': dict(sorted(by_t.items(), key=lambda x: -x[1][1])),
                'cas_parts': self.stats.get('cas_parts', {}), 'source_packages': len(self.packages)}


def _fake_refs(ids_by_cat, name):
    """A usedpack.Refs that 'references' the given ids, so usedpack.plan() adds them with their closure."""
    fp = 'fastmode:' + name
    src = U.Source(name, name, 'fastmode', True, 0, 0, fp)
    return U.Refs([src], {fp: {cat: set(v) for cat, v in ids_by_cat.items() if v}}, {}, {}, False)


def _object_closure(view, roots, game, objs):
    """{key: usedpack Item} for object ids: OBJD/COBJ, their thumbnails and everything they embed (models,
    LODs, footprints, slots, rigs, materials, textures) - usedpack's object walk (_Planner.resolve_embedded)
    without its own-package tuning/STBL steps: plan_pack carries every non-asset resource of the parked
    packages anyway, and those steps read every string table of the package once per object."""
    if not objs:
        return {}
    pl = U._Planner(view, roots, game)
    try:
        rows, _ = pl.by_instance([U.T_OBJD, U.T_COBJ], objs)
        thumbs, _ = pl.by_instance([U.T_OTHM], {k[2] for k in rows})
        for key, row in list(rows.items()) + list(thumbs.items()):
            pl.add(key, row, tname(key[0]))
        frontier = [pl.items[k] for k in rows]
        while frontier:
            new = pl.resolve_embedded(frontier, U.OBJECT_REF_TYPES, 'object ref')
            frontier = [pl.items[k] for k in new if k[0] in U.OBJECT_CONTAINERS]
        return pl.items
    finally:
        pl.close()


def _closure_items(view, roots, game, ids_by_cat, name):
    """{key: usedpack Item} for the given catalog ids with everything they need: CAS parts, tones, sculpts,
    sliders and pet coats through usedpack.plan() (CASP key lists with their fallbacks, thumbnails, look
    references), objects through _object_closure."""
    out = {}
    cas = {cat: v for cat, v in ids_by_cat.items() if v and cat != U.OBJECT}
    if cas:
        out.update(U.plan(view, _fake_refs(cas, name), roots, game=game, build_surfaces=False, ea_overrides=False,
                          allow_unparsed=True).items)
    for key, it in _object_closure(view, roots, game, ids_by_cat.get(U.OBJECT, set())).items():
        out.setdefault(key, it)
    return out


def _read_resource(f, off, fsize, comp, msize):
    """One resource decompressed; zlib read tolerantly (short streams are accepted like the game does)."""
    f.seek(off)
    raw = f.read(fsize)
    if len(raw) != fsize:
        raise DBPFError('resource runs past the end of the file')
    if comp == ZLIB:
        d = zlib.decompressobj()
        out = d.decompress(raw)
        if not d.eof and len(out) < msize:
            raise zlib.error('truncated zlib stream')
        return out
    return decompress(raw, comp, msize)


# numbers in tuning text: decimal, 0x-hex, and bare 16-digit hex (S4S style T:G:I keys)
_DEC = re.compile(rb'(?<![0-9A-Za-z_.])([0-9]{5,20})(?![0-9A-Za-z_])')
_HEX0X = re.compile(rb'0[xX]([0-9A-Fa-f]{5,16})(?![0-9A-Fa-f])')
_HEX16 = re.compile(rb'(?<![0-9A-Za-z_])([0-9A-Fa-f]{16})(?![0-9A-Za-z_])')
# a full resource key written in tuning: 'type:group:instance' in hex (icons: 00B2D882:00000000:...)
_TGI = re.compile(rb'(?<![0-9A-Za-z_])([0-9A-Fa-f]{8})[:\-_]([0-9A-Fa-f]{8})[:\-_]([0-9A-Fa-f]{16})(?![0-9A-Za-z_])')
# CC catalog records whose instance is below 2^32 (older tools; 1,821 of them in the parked sim/ merges -
# e.g. the makeup CAS parts a CC chair's buff sets). The tuning scan follows ids from here up that the game
# does not ship; below it, numbers in tuning are counts and flags, not ids.
SMALL_ID_MIN = 1 << 16


def xml_ids(data, low=BIG):
    """Every value >= low (default 2^32, 64-bit ids only) written in a tuning file (decimal, 0x hex or bare
    16-digit hex)."""
    out = set(map(int, _DEC.findall(data)))
    out.update(int(x, 16) for x in _HEX0X.findall(data))
    out.update(int(x, 16) for x in _HEX16.findall(data))
    return {v for v in out if low <= v <= U.M64}


def xml_keys(data, types=None):
    """Full resource keys (t, g, i) written as hex 'type:group:instance' in a tuning file (types: only those)."""
    out = set()
    for t, g, i in _TGI.findall(data):
        k = (int(t, 16), int(g, 16), int(i, 16))
        if k[2] and (types is None or k[0] in types):
            out.add(k)
    return out


def is_cc_id(t, i, game):
    """Is instance i of catalog type t one the tuning scan follows: 64-bit, or at least SMALL_ID_MIN and not
    one the game ships (then it is CC with a 32-bit instance, not an EA id or a small number)?"""
    return i >= BIG or (i >= SMALL_ID_MIN and not game.has(t, i))


def _in_sorted(a, targets):
    """The values of uint64 array a that are in the sorted uint64 array targets."""
    if not len(a) or not len(targets):
        return a[:0]
    idx = np.searchsorted(targets, a)
    idx[idx >= len(targets)] = 0
    return a[targets[idx] == a]


def member(values, targets):
    """Set of the ints in values that are in the sorted uint64 array targets."""
    if not values:
        return set()
    a = np.fromiter((v for v in values if 0 <= v <= U.M64), dtype=np.uint64)
    return {int(x) for x in _in_sorted(a, targets)}


def binary_ids(data, targets, low=BIG):
    """Values >= low (default 2^32) of the sorted uint64 array targets found as 8-byte little-endian words at
    any offset."""
    n = len(data)
    found = set()
    if n < 8 or not len(targets):
        return found
    for k in range(8):
        m = (n - k) // 8
        if m <= 0:
            continue
        a = np.frombuffer(data, dtype='<u8', count=m, offset=k)
        found.update(int(x) for x in _in_sorted(a[a >= low], targets))
    return found


class _Reader:
    """Reads resources from library packages (FILE_SHARE_DELETE handles, at most 32 open)."""

    def __init__(self, view, pkgs):
        self.view, self.pkgs = view, pkgs
        self.files = collections.OrderedDict()
        self.errors = 0

    def read(self, pkg, off, fsize, comp, msize):
        f = self.files.get(pkg)
        if f is None:
            if len(self.files) >= 32:
                self.files.popitem(last=False)[1].close()
            f = self.files[pkg] = open_shared(U._locate(self.view, self.pkgs[pkg]))
        return _read_resource(f, off, fsize, comp, msize)

    def close(self):
        for f in self.files.values():
            f.close()
        self.files.clear()


def text_ids(data, t, tarr, st, low=BIG, keys=None):
    """ids of the sorted uint64 array tarr (values >= low) named by one resource: SimData by 8-byte value,
    XML tuning by text. keys: a set that also receives the asset keys the XML names as 'type:group:instance'
    (icons and the like)."""
    if t == U.T_SIMDATA:
        st['simdata_read'] += 1
        return binary_ids(data, tarr, low)
    if data[:512].lstrip(b'\xef\xbb\xbf \r\n\t').startswith(b'<'):
        st['xml_read'] += 1
        if keys is not None:
            keys |= xml_keys(data, ASSET_TYPES)
        return member(xml_ids(data, low), tarr)
    return set()


def _scan_refs(reader, rows, tarr, st, low=BIG, keys=None):
    """ids of tarr found in the tuning / SimData rows [(pkg, off, fsize, comp, msize, t)] (see text_ids)."""
    found = set()
    for pkg, off, fs, comp, ms, t in sorted(rows, key=lambda r: (r[0], r[1])):
        try:
            data = reader.read(pkg, off, fs, comp, ms)
        except Exception:
            reader.errors += 1
            continue
        found |= text_ids(data, t, tarr, st, low, keys)
    return found


def _catalog_arrays(sets):
    """{category: set of instances} -> (sorted uint64 array of all of them, {category: sorted array})."""
    per = {cat: np.unique(np.fromiter(s, dtype=np.uint64, count=len(s))) for cat, s in sets.items() if s}
    allv = np.unique(np.concatenate(list(per.values()))) if per else np.zeros(0, np.uint64)
    return allv, per


def _cats_of(ids, per):
    """{category: set of ids} for ids, by which per-category arrays hold them."""
    out = collections.defaultdict(set)
    for cat, arr in per.items():
        out[cat] |= member(ids, arr)
    return out


def _is_text_candidate(t, msize):
    return t == U.T_SIMDATA or (t not in ASSET_TYPES and t not in companions.BINARY_TYPES and t not in SKIP_TYPES
                                and msize <= MAX_XML)


def _script_ids(view, cache_path):
    """64-bit int constants hard-coded in the library's .ts4script files (companions' cached bytecode facts)."""
    db = companions._open_cache(cache_path)
    try:
        out = set()
        for s in companions._script_index(view, db):
            out |= s['ids']
        return out
    finally:
        db.close()


def library_listing_index(view):
    """[[rel, size, mtime]] of every package and script in the library index (SpeedKit's files left out)."""
    rows = [[p.rel, p.size, round(p.mtime, 3)] for p in view.packages() if not is_speedkit_file(p.rel)]
    rows += [[s.rel, s.size, round(s.mtime, 3)] for s in view.scripts() if not is_speedkit_file(s.rel)]
    return sorted(rows, key=lambda r: (r[0].lower(), r[1], r[2]))


def library_listing_disk(root_dirs):
    """The same listing read from disk now (both roots; a file the profile switcher moved keeps its entry)."""
    rows = []
    for root in root_dirs.values():
        if not os.path.isdir(root):
            continue
        for dp, dn, fn in os.walk(root):
            dn[:] = [d for d in dn if d not in SKIP_DIRS]
            for n in fn:
                low = n.lower()
                if not low.endswith(('.package', '.ts4script')):
                    continue
                full = os.path.join(dp, n)
                rel = os.path.relpath(full, root).replace('\\', '/')
                if is_speedkit_file(rel) or is_speedkit_pack(rel):
                    continue
                try:
                    st = os.stat(full)
                except OSError:
                    continue
                rows.append([rel, st.st_size, round(st.st_mtime, 3)])
    return sorted(rows, key=lambda r: (r[0].lower(), r[1], r[2]))


def listing_fingerprint(rows):
    return hashlib.blake2b(json.dumps(rows).encode(), digest_size=16).hexdigest()


BC_CACHE_VERSION = 1


def _bc_key(library_fp, parked_rels, roots, use_scripts, game):
    """What parts b and c depend on: the library's files (rel, size, mtime - root-independent), the parked
    set, SpeedKit's rules, the game's package listing (EA overrides and EA ids) and use_scripts. They do not
    depend on the saves, so one cached b/c serves the fast pack and every save pack."""
    info = getattr(game, 'info', None) or {}
    parts = (BC_CACHE_VERSION, library_fp, sorted(r.upper() for r in parked_rels), list(roots), bool(use_scripts),
             rules_fingerprint(), info.get('fingerprint') or '-', SMALL_ID_MIN, MAX_XML)
    return hashlib.blake2b(json.dumps(parts).encode(), digest_size=16).hexdigest()


def _load_bc(path, key, by_rel, parked_ids):
    """The cached b/c items for key as {key: FastItem} (+ stats), or None (no cache, another key, a package
    that cannot be matched to exactly one loaded parked package)."""
    import gzip
    try:
        with gzip.open(path, 'rt', encoding='utf-8') as f:
            doc = json.load(f)
    except (OSError, ValueError, EOFError):
        return None
    if not isinstance(doc, dict) or doc.get('version') != BC_CACHE_VERSION or doc.get('key') != key:
        return None
    items = {}
    pid_of = {}
    try:
        for t, g, i, rel, off, fs, ms, comp, why, part in doc['items']:
            pid = pid_of.get(rel)
            if pid is None:
                cand = [p for p in by_rel.get(rel.upper(), ()) if p in parked_ids]
                if len(cand) != 1:
                    return None
                pid = pid_of[rel] = cand[0]
            items[(t, g, i)] = FastItem(t, g, i, pid, off, fs, ms, comp, why, part)
    except (KeyError, TypeError, ValueError):
        return None
    return {'items': items, 'stats': doc.get('stats') or {}}


def _save_bc(path, key, bc, pkgs):
    """Write the b/c items (package by relative path, so a rescan or a profile switch does not matter)."""
    import gzip
    rows = [[it.t, it.g, it.i, pkgs[it.pkg].rel, it.off, it.fsize, it.msize, it.comp, it.why, it.part]
            for it in bc['items'].values()]
    doc = {'version': BC_CACHE_VERSION, 'key': key, 'created': time.strftime('%Y-%m-%d %H:%M:%S'),
           'items': rows, 'stats': bc['stats']}
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + '.tmp'
    try:
        with gzip.open(tmp, 'wt', encoding='utf-8', compresslevel=5) as f:
            json.dump(doc, f, default=str)
        os.replace(tmp, path)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass


def cached_bc(lib, parked, game, bc_cache, roots=ROOTS2, use_scripts=True):
    """Parts (b)/(c) from bc_cache when it matches the library, parked set, rules and game as they are now:
    {'items': {key: FastItem}, 'stats'}; None when there is no valid cache (plan_pack would compute them).
    Read-only; used to tell whether a plan will be quick and to count the CAS parts a pack would load."""
    if not bc_cache or not os.path.exists(bc_cache):
        return None
    view = _view(lib)
    roots = _roots(roots)
    ids = _ids(view)
    pos = {ids[k]: n for n, k in enumerate(view.load_order(roots)) if k in ids}
    by_rel = collections.defaultdict(list)
    for (r, rel), pid in ids.items():
        if pid in pos:
            by_rel[rel.upper()].append(pid)
    parked_ids = set()
    for r, rel in [(e[0], e[1]) for e in parked]:
        pid = ids.get((r, rel))
        if pid not in pos:
            cand = by_rel.get(rel.upper(), [])
            pid = cand[0] if len(cand) == 1 else None
        if pid is None:
            return None
        parked_ids.add(pid)
    pkgs = {p.id: p for p in view.packages()}
    key = _bc_key(listing_fingerprint(library_listing_index(view)), [pkgs[p].rel for p in parked_ids], roots,
                  use_scripts, game)
    return _load_bc(bc_cache, key, by_rel, parked_ids)


def _plan_bc(view, roots, pos, pkgs, parked_ids, kept_ids, game, overrides, use_scripts, cache_path, verbose, lap):
    """Parts (b) and (c) of the pack - everything the fast profile needs from the parked packages that does not
    depend on the saves. Returns {'items': {key: FastItem}, 'stats': {...}}."""
    st = collections.defaultdict(collections.Counter)
    items = {}

    def add(key, pkg, off, fs, ms, comp, why, part):
        if pkg in parked_ids and key not in items and key[0] not in SKIP_TYPES:
            items[key] = FastItem(key[0], key[1], key[2], pkg, off, fs, ms, comp, why, part)
            return True
        return False

    def add_plan_items(plan_items, part, prefix):
        new = []
        for key, it in plan_items.items():
            if it.pkg not in parked_ids:
                st[part]['provided_by_kept'] += 1
            elif add(key, it.pkg, it.off, it.fsize, it.msize, it.comp, prefix + it.why, part):
                new.append(key)
        return new

    # ---- one pass over the index: kept keys, and the parked copies (b) needs
    kept_list = ','.join(str(p) for p in sorted(kept_ids)) or '-1'
    parked_list = ','.join(str(p) for p in sorted(parked_ids)) or '-1'
    q = 'select t, g, i, pkg, off, fsize, msize, comp from res where comp != ? and pkg in (%s)'
    kept_best = {}
    kept_cat = collections.defaultdict(set)
    kept_text = []
    for t, g, i, pkg, off, fs, ms, comp in view.db.execute(q % kept_list, (DELETED,)):
        if t in SKIP_TYPES:
            continue
        i = unsigned64(i)
        k = (t, g, i)
        p = pos[pkg]
        cur = kept_best.get(k)
        if cur is None or p < cur[0]:
            kept_best[k] = (p, pkg, off, fs, ms, comp)
        if t in CATALOG:
            kept_cat[CATALOG[t]].add(i)
        if _is_text_candidate(t, ms):
            kept_text.append((pkg, off, fs, comp, ms, t))
    # the parked side, filtered by SQLite: catalog instances (for the tuning scan), every non-asset copy,
    # and the asset copies of keys a kept package also has or that override EA's
    parked_cat = collections.defaultdict(set)
    cat_list = ','.join(str(t) for t in sorted(CATALOG))
    for t, i in view.db.execute('select t, i from res where comp != ? and pkg in (%s) and +t in (%s)'
                                % (parked_list, cat_list), (DELETED,)):     # '+t': read rows package by package
        i = unsigned64(i)
        if is_cc_id(t, i, game):
            parked_cat[CATALOG[t]].add(i)
    parked_best = {}

    def take(t, g, i, pkg, off, fs, ms, comp):
        k = (t, g, unsigned64(i))
        p = pos[pkg]
        cur = parked_best.get(k)
        if cur is None or p < cur[0]:
            parked_best[k] = (p, pkg, off, fs, ms, comp)

    marks = ','.join(str(t) for t in sorted(ASSET_TYPES | SKIP_TYPES))
    for row in view.db.execute(q % parked_list + ' and t not in (%s)' % marks, (DELETED,)):
        take(*row)
    wanted = [k for k in kept_best if k[0] in ASSET_TYPES] + [k for k in overrides if k[0] in ASSET_TYPES]
    view.db.execute('drop table if exists temp.fm_want')
    view.db.execute('create temp table fm_want(t integer, g integer, i integer)')
    view.db.executemany('insert into temp.fm_want values(?,?,?)', ((t, g, U.signed64(i)) for t, g, i in set(wanted)))
    for row in view.db.execute('select r.t, r.g, r.i, r.pkg, r.off, r.fsize, r.msize, r.comp from temp.fm_want w '
                               'join res r on r.t = w.t and r.g = w.g and r.i = w.i '
                               'where r.comp != ? and r.pkg in (%s)' % parked_list, (DELETED,)):
        take(*row)
    view.db.execute('drop table temp.fm_want')
    lap('index_pass')

    # ---- (b) script/tuning content, EA overrides and shadowed keys whose winner is parked
    closure = collections.defaultdict(set)
    for k, row in sorted(parked_best.items(), key=lambda kv: kv[1][0]):
        kb = kept_best.get(k)
        if kb is not None and kb[0] < row[0]:
            continue                                  # a kept package has the winning copy
        t = k[0]
        if kb is not None:
            kind = 'shadowed'
        elif k in overrides:
            kind = 'EA override'
        else:
            kind = ('SimData' if t == U.T_SIMDATA else 'string table' if t == U.T_STBL else
                    'animation' if t in (T_ASM, T_CLIP, T_CLHD) else 'tuning/other')
        st['b_kinds'][kind] += 1
        if t in CATALOG and kind != 'tuning/other':
            closure[CATALOG[t]].add(k[2])
            st['b']['catalog_with_closure'] += 1
        add(k, row[1], row[2], row[3], row[4], row[5], '%s %s' % (kind, tname(t)), 'b')
    add_plan_items(_closure_items(view, roots, game, closure, 'overrides'), 'b', 'override/shadowed closure: ')
    lap('b_closure')
    if verbose:
        print('  (b) script content, overrides, shadowed: %d keys' % sum(1 for it in items.values()
                                                                         if it.part == 'b'), flush=True)

    # ---- (c1) what kept CC lists itself: kept CAS parts, objects, tones, sliders with their closure
    add_plan_items(_closure_items(view, roots, game, kept_cat, 'kept'), 'c', 'kept CC needs: ')
    lap('c_kept_closure')

    # ---- (c2) ids in tuning / SimData that stays loaded (kept + pack) and in scripts, held by parked packages.
    # The saves' part (a) adds no text resource the scan would miss: its tuning/SimData/STBL are parked winners,
    # which (b) holds already.
    tarr, per_cat = _catalog_arrays(parked_cat)
    del parked_cat
    reader = _Reader(view, pkgs)
    scan_st = collections.Counter()
    done_ids = set()
    named_keys = set()                        # asset keys the tuning writes out in full (icons, ...)
    try:
        rows = list(kept_text)
        rows += [(it.pkg, it.off, it.fsize, it.comp, it.msize, it.t) for it in items.values()
                 if _is_text_candidate(it.t, it.msize)]
        seen_rows = set((r[0], r[1]) for r in rows)
        found = _scan_refs(reader, rows, tarr, scan_st, SMALL_ID_MIN, named_keys)
        st['c']['tuning_ids'] = len(found)
        st['c']['tuning_small_ids'] = sum(1 for v in found if v < BIG)
        lap('c_tuning_scan')
        if use_scripts:
            try:
                sids = member(_script_ids(view, cache_path), tarr)
            except Exception as e:                    # no cache / unreadable script: report, do not fail
                sids = set()
                st['c']['script_ids_error:' + type(e).__name__] += 1
            st['c']['script_ids'] = len(sids)
            found |= sids
        rounds = 0
        while found - done_ids and rounds < 8:
            rounds += 1
            new_ids = found - done_ids
            done_ids |= new_ids
            new = add_plan_items(_closure_items(view, roots, game, _cats_of(new_ids, per_cat), 'tuning%d' % rounds),
                                 'c', 'tuning ref: ')
            more = [(items[k].pkg, items[k].off, items[k].fsize, items[k].comp, items[k].msize, items[k].t)
                    for k in new if _is_text_candidate(k[0], items[k].msize)]
            more = [r for r in more if (r[0], r[1]) not in seen_rows]
            seen_rows.update((r[0], r[1]) for r in more)
            found = _scan_refs(reader, more, tarr, scan_st, SMALL_ID_MIN, named_keys) | done_ids
        st['c']['rounds'] = rounds
        lap('c_tuning_closure')
        st['c']['ids_followed'] = len(done_ids)
        # asset keys the loaded tuning names in full (e.g. WickedWhims' cas_part_display_icon, an _IMG in
        # the same sim/ merge): their full-library copy, when it is parked
        for k, row in _loaded_keys(view, pos, [k for k in named_keys if k not in items]).items():
            if row[1] not in parked_ids:
                st['c']['tuning_keys_provided_by_kept'] += 1
            elif add(k, row[1], row[2], row[3], row[4], row[5], 'tuning key ' + tname(k[0]), 'c'):
                st['c']['tuning_keys'] += 1
        lap('c_tuning_keys')
    finally:
        st['c']['unreadable'] = reader.errors
        reader.close()
    if verbose:
        print('  (c) needed by kept CC / tuning / scripts: %d keys' % sum(1 for it in items.values()
                                                                        if it.part == 'c'), flush=True)
    stats = {'b_kinds': dict(st['b_kinds']),
             'provided_by_kept': {p: st[p]['provided_by_kept'] for p in 'bc'},
             'b_catalog_with_closure': st['b']['catalog_with_closure'],
             'c_scan': dict(scan_st, **{k: v for k, v in st['c'].items()}),
             'overrides': len(overrides)}
    return {'items': items, 'stats': stats}


def plan_pack(lib, refs, parked=None, kept=None, roots=ROOTS2, game=None, overrides=None, include_backups=False,
              allow_unparsed=False, use_scripts=True, cache_path=companions.DEFAULT_CACHE, game_db=None,
              game_dir=None, verbose=False, bc_cache=None, pack_name=None, progress=None):
    """Work out the fast pack. Read-only. Returns a FastPlan (see the module docstring for parts a/b/c).

    parked: park_set(lib) (computed when None); kept: the loaded packages the fast profile keeps (default:
    every loaded package not parked; given, the two lists must not overlap and must cover every loaded
    package - ValueError otherwise). refs: usedpack.scan_references() (or, for a save pack, the refs of one
    save - see speedkit.savepacks). game: usedpack.load_game_ids(); overrides: the set of library keys that
    override EA's (default GameIndex(game_db, game_dir).override_keys(lib)); use_scripts: also follow ids
    hard-coded in scripts. Refuses when a save/Tray file that counts has no scan result, unless allow_unparsed.

    bc_cache: a file (gzip JSON) holding parts (b) and (c), which do not depend on the saves: keyed by the
    library's files, the parked set, SpeedKit's rules and the game, so a new save costs only part (a) (the
    ~60 s of index pass, override lookup and tuning scan are skipped). None: no cache. pack_name: the first
    pack file's name (for the 'loads before the pack' check; default the fast pack's). progress(step, fraction,
    message) is told about the long steps."""
    t0 = time.time()
    view = _view(lib)
    roots = _roots(roots)
    if parked is None:
        parked = park_set(view, roots, cache_path=cache_path)
    ids = _ids(view)
    order = view.load_order(roots)
    pos = {ids[k]: n for n, k in enumerate(order) if k in ids}
    by_rel = collections.defaultdict(list)
    for (r, rel), pid in ids.items():
        if pid in pos:
            by_rel[rel.upper()].append(pid)

    def resolve(entries, what):
        out = set()
        for e in entries:
            r, rel = e[0], e[1]
            pid = ids.get((r, rel))
            if pid not in pos:                 # moved to the other root since the list was made: same rel
                cand = by_rel.get(rel.upper(), [])
                pid = cand[0] if len(cand) == 1 else None
            if pid is None:
                raise ValueError('%s package %s/%s is not a loaded library package - rescan the library and '
                                 'compute the park set again' % (what, r, rel))
            out.add(pid)
        return out

    parked_ids = resolve(parked, 'parked')
    if kept is not None:
        kept_ids = resolve(kept, 'kept')
        if kept_ids & parked_ids:
            raise ValueError('%d packages are both parked and kept' % len(kept_ids & parked_ids))
        neither = set(pos) - parked_ids - kept_ids
        if neither:                           # the pack would miss what they hold: refuse rather than guess
            rels = sorted(r for (_, r), pid in ids.items() if pid in neither)
            raise ValueError('%d loaded packages are neither parked nor kept (e.g. %s): every package the full '
                             'library loads must be in one of the two lists' % (len(neither), rels[0]))
    kept_ids = set(pos) - parked_ids              # anything not parked loads in the fast profile
    pkgs = {p.id: p for p in view.packages()}
    if game is None:
        game = U.load_game_ids(**({'game_dir': game_dir} if game_dir else {}))
    P = FastPlan()
    P.parked = parked if isinstance(parked, ParkSet) else ParkSet(parked)
    P.roots, P.root_dirs = roots, dict(view.roots)
    P.sims = _sims_of({r: view.roots[r] for r in roots if r in view.roots})
    P.include_backups = include_backups
    P.library = library_listing_index(view)
    P.library_fp = listing_fingerprint(P.library)
    timings = collections.OrderedDict()
    tick = [t0]

    def lap(name):
        now = time.time()
        timings[name] = round(now - tick[0], 1)
        tick[0] = now

    def tell(step, fraction, message):
        if progress:
            try:
                progress(step, fraction, message)
            except Exception:
                pass

    # ---- (b) + (c): from the cache when the library, the parked set, the rules and the game are unchanged
    parked_rels = [pkgs[p].rel for p in parked_ids if p in pkgs]
    key = _bc_key(P.library_fp, parked_rels, roots, use_scripts, game) if bc_cache else None
    bc = _load_bc(bc_cache, key, by_rel, parked_ids) if bc_cache else None
    cache_state = 'off' if not bc_cache else ('hit' if bc is not None else 'miss')
    lap('bc_cache_' + cache_state)
    if bc is None:
        tell('plan', None, 'Working out what scripts, tuning and animations need (a few minutes the first time)')
        if overrides is None:
            from .game_index import GameIndex, DEFAULT_DB, GAME_DIR
            gi = GameIndex(game_db or DEFAULT_DB, game_dir or GAME_DIR)
            try:
                overrides = gi.override_keys(view.lib, roots)
            finally:
                gi.close()
        lap('setup_overrides')
        bc = _plan_bc(view, roots, pos, pkgs, parked_ids, kept_ids, game, overrides, use_scripts, cache_path, verbose,
                      lap)
        if bc_cache:
            _save_bc(bc_cache, key, bc, pkgs)

    # ---- (a) the CC the saves (and Tray) use
    tell('plan', None, 'Working out which custom content your sims and lots use')
    items = P.items
    provided_a = 0
    up = U.plan(view, refs, roots, include_backups=include_backups, game=game, allow_unparsed=allow_unparsed)
    for k, it in up.items.items():
        if it.pkg not in parked_ids:
            provided_a += 1
        elif k[0] not in SKIP_TYPES and k not in items:
            items[k] = FastItem(k[0], k[1], k[2], it.pkg, it.off, it.fsize, it.msize, it.comp, it.why, 'a')
    P.sources, P.absent, P.unloadable, P.households = up.sources, up.absent, up.unloadable, up.households
    lap('a_usedpack_plan')
    if verbose:
        print('  (a) used CC: %d keys from parked packages' % len(items), flush=True)
    for k, it in bc['items'].items():
        if k not in items:
            items[k] = it

    for pid in {it.pkg for it in items.values()}:
        p = pkgs[pid]
        P.packages[pid] = {'root': p.root, 'rel': p.rel, 'size': p.size, 'mtime': p.mtime}
    # kept packages that the game reaches before the pack at the Mods root ('!!!!!!x.package', ' x/'): their
    # copy of a pack key would win in fast mode although the full library uses the parked one
    first = pack_name or PACK_NAME % 1
    early_ids = {pid for pid in kept_ids if loads_before(pkgs[pid].rel, first)}
    early = sorted(pkgs[pid].rel for pid in early_ids)
    clash = []
    if early_ids:
        early_keys = {(t, g, unsigned64(i)) for t, g, i in view.db.execute(
            'select t, g, i from res where comp != ? and pkg in (%s)' % ','.join(str(p) for p in sorted(early_ids)),
            (DELETED,))}
        clash = [k for k in items if k in early_keys]
    if verbose and clash:
        print('  WARNING: %d pack keys are also in kept packages that load before the pack (e.g. %s)'
              % (len(clash), early[0]), flush=True)
    kept_list = ','.join(str(p) for p in sorted(kept_ids)) or '-1'
    parked_list = ','.join(str(p) for p in sorted(parked_ids)) or '-1'
    kept_casp = view.db.execute('select count(*) from res where t=? and comp != ? and pkg in (%s)' % kept_list,
                                (U.T_CASP, DELETED)).fetchone()[0]
    parked_casp = view.db.execute('select count(*) from res where t=? and comp != ? and pkg in (%s)' % parked_list,
                                  (U.T_CASP, DELETED)).fetchone()[0]
    full_casp = kept_casp + parked_casp
    pack_casp = sum(1 for k in items if k[0] == U.T_CASP)
    s = P.summary()
    bst = bc['stats']
    P.stats = {
        'parts': s['parts'],
        'b_kinds': bst.get('b_kinds', {}),
        'provided_by_kept': dict(bst.get('provided_by_kept', {}), a=provided_a),
        'a_usedpack': {k: v for k, v in up.stats.items() if k in ('cas', 'looks', 'objects', 'surfaces',
                                                                  'ea_restyled', 'absent_counts',
                                                                  'households_with_missing_cc', 'keys', 'bytes')},
        'b_catalog_with_closure': bst.get('b_catalog_with_closure', 0),
        'c_scan': bst.get('c_scan', {}),
        'packages': {'loaded': len(pos), 'parked': len(parked_ids), 'kept': len(kept_ids),
                     'parked_bytes': sum(pkgs[p].size for p in parked_ids),
                     'kept_bytes': sum(pkgs[p].size for p in kept_ids)},
        'cas_parts': {'full': full_casp, 'kept': kept_casp, 'pack': pack_casp, 'fast': kept_casp + pack_casp,
                      'fast_percent': round(100.0 * (kept_casp + pack_casp) / max(1, full_casp), 2)},
        'overrides': bst.get('overrides'),
        'loads_before_pack': {'packages': len(early), 'examples': early[:10], 'pack_keys_they_hold': len(clash)},
        'bc_cache': cache_state,
        'timings': dict(timings),
        'seconds': round(time.time() - t0, 1),
    }
    P.stats.update({'keys': s['keys'], 'bytes': s['bytes']})
    if verbose:
        print('plan: %d keys, %.2f GB in %.0fs (b/c cache %s)' % (s['keys'], s['bytes'] / 1e9, P.stats['seconds'],
                                                                 cache_state), flush=True)
    return P


# ------------------------------------------------------------------------------------------ layout
def _rank(t):
    if t in RANK:
        return RANK[t]
    if t in BULK_TYPES:
        return R_BULK
    if t == U.T_STBL:
        return R_STBL
    if t in ASSET_TYPES:
        return R_SMALL_ASSET
    return R_TUNING


def _order(plan, items=None):
    """Items in pack order: CASP, THUM, TONE, OBJD, COBJ, SimData, tuning/other, STBL, small assets, then
    meshes/textures/clips; within a type in source order, so the sources are read sequentially."""
    paths = {pid: (p['root'], p['rel']) for pid, p in plan.packages.items()}
    items = plan.items.values() if items is None else items
    return sorted(items, key=lambda it: (_rank(it.t), it.t if _rank(it.t) < R_BULK else 0, paths[it.pkg], it.off))


def layout(plan, max_package_bytes=1_900_000_000, items=None):
    """Split the ordered items into packages no bigger than max_package_bytes: [[FastItem, ...], ...]."""
    if not 0 < max_package_bytes <= U.MAX_PACKAGE_LIMIT:
        raise ValueError('max_package_bytes must be between 1 and %d (2 GiB)' % U.MAX_PACKAGE_LIMIT)
    groups, cur, size = [], [], 96 + 4
    for it in _order(plan, items):
        need = it.fsize + 32
        if cur and size + need > max_package_bytes:
            groups.append(cur)
            cur, size = [], 96 + 4
        cur.append(it)
        size += need
    if cur:
        groups.append(cur)
    return groups


# ------------------------------------------------------------------------------------------ where the pack is
def read_manifest(out_dir=DEFAULT_OUT, kind=None):
    """fastpack.json (savepack.json for a save pack) of the pack in out_dir, or None (a damaged file raises
    ValueError)."""
    p = os.path.join(out_dir, (kind or FAST).manifest)
    if not os.path.exists(p):
        return None
    with open(p, encoding='utf-8') as f:
        return json.load(f)


def find_pack(out_dir=DEFAULT_OUT, mods_dir=None, manifest=None, kind=None):
    """Where the pack files listed in fastpack.json are now: {'where': 'fastpack'|'mods'|'split'|'missing'|
    'none', 'dir': folder or None, 'files': {name: path}, 'missing': [names], 'wrong_size': [names],
    'duplicated': [names in both folders], 'extra': [paths of fast pack files fastpack.json does not list]}.
    The profile switcher moves the .package files to the Mods root for the fast profile; fastpack.json
    always stays in out_dir. A file in both folders makes it 'split' (the game would load the Mods copy,
    which may be an older build); an unlisted pack file in Mods would load first in every profile."""
    kind = kind or FAST
    man = manifest if manifest is not None else read_manifest(out_dir, kind)
    if man is None:
        return {'where': 'none', 'dir': None, 'files': {}, 'missing': [], 'wrong_size': [], 'duplicated': [],
                'extra': []}
    mods_dir = mods_dir or (man.get('root_dirs') or {}).get('Mods')
    dirs = [('fastpack', out_dir)]
    if mods_dir and os.path.normcase(os.path.abspath(mods_dir)) != os.path.normcase(os.path.abspath(out_dir)):
        dirs.append(('mods', mods_dir))
    files, missing, wrong, dup, where = {}, [], [], [], set()
    for p in man.get('packages', []):
        hits = [(tag, os.path.join(d, p['name'])) for tag, d in dirs if os.path.isfile(os.path.join(d, p['name']))]
        if not hits:
            missing.append(p['name'])
            continue
        if len(hits) > 1:
            dup.append(p['name'])
        tag, path = hits[0]
        files[p['name']] = path
        where.add(tag)
        if os.path.getsize(path) != p['bytes']:
            wrong.append(p['name'])
    listed = {p['name'].lower() for p in man.get('packages', [])}
    extra = [os.path.join(d, n) for _, d in dirs for n in _stray_pack_files(d, kind) if n.lower() not in listed]
    if not files:
        w, d = 'missing', None
    elif len(where) > 1 or dup:
        w, d = 'split', None
    else:
        w = where.pop()
        d = out_dir if w == 'fastpack' else mods_dir
    return {'where': w, 'dir': d, 'files': files, 'missing': missing, 'wrong_size': wrong, 'duplicated': dup,
            'extra': extra}


def _stray_pack_files(folder, kind=None):
    """Names of the pack files of one family (default: the fast pack) in a folder."""
    kind = kind or FAST
    if not folder or not os.path.isdir(folder):
        return []
    return sorted(n for n in os.listdir(folder) if kind.matches(n) and is_speedkit_pack(n))


# ------------------------------------------------------------------------------------------ build
def _destinations(plan, out_dir, pack_dir, sims):
    """Check where build_pack/update_pack may write; returns True when pack_dir is the Mods root (the
    game must not be running then)."""
    for d, what in ((out_dir, 'out_dir'), (pack_dir, 'pack_dir')):
        if not _inside(d, sims):
            raise ValueError('%s must be inside the Sims 4 folder %s' % (what, sims))
        for protected in ('saves', 'Tray'):
            if _inside(d, os.path.join(sims, protected)):
                raise ValueError('%s may not be inside the %s folder' % (what, protected))
        park = plan.root_dirs.get('Mods_parked')
        if park and _inside(d, park):
            raise ValueError('%s may not be inside Mods_parked' % what)
    mods = plan.root_dirs.get('Mods')
    if mods and _inside(out_dir, mods):
        raise ValueError('fastpack.json does not belong in Mods: keep out_dir outside it (pack_dir may be Mods)')
    if mods and _inside(pack_dir, mods):
        if os.path.normcase(os.path.abspath(pack_dir)) != os.path.normcase(os.path.abspath(mods)):
            raise ValueError('the fast pack must sit in the Mods root (its name makes it load first there)')
        return True
    return False


class _Sub:
    """A plan-like view of some items (a delta), for usedpack's source checks."""

    def __init__(self, plan, items):
        self.items = {(it.t, it.g, it.i): it for it in items}
        self.packages = {pid: plan.packages[pid] for pid in {it.pkg for it in items}}
        self.root_dirs = plan.root_dirs


def _write_packages(plan, groups, names, staging, check_copy=True, verbose=False):
    """Write each group bit-exact into staging/<name>; re-read and compare every resource when check_copy.
    Returns [{'path', 'keys', 'bytes'}]."""
    sub = _Sub(plan, [it for g in groups for it in g])
    lib_paths = U._check_sources(sub)
    entries = U._source_entries(sub, lib_paths)
    files = collections.OrderedDict()
    out = []
    try:
        for name, g in zip(names, groups):
            path = os.path.join(staging, name)
            digests = {}
            with PackageWriter(path) as w:
                for it in g:
                    e = entries[(it.pkg, it.t, it.g, it.i)]
                    f = files.get(it.pkg)
                    if f is None:
                        if len(files) >= 32:
                            files.popitem(last=False)[1].close()
                        f = files[it.pkg] = U._open_source(sub, it.pkg, lib_paths)
                    f.seek(e.off)
                    raw = f.read(e.fsize)
                    w.add_raw(e, raw)
                    if check_copy:
                        digests[(it.t, it.g, it.i)] = (hashlib.blake2b(raw, digest_size=16).digest(),
                                                       e.fsize, e.msize, e.comp)
            if check_copy:
                with Package(path) as pk:
                    if len(pk.entries) != len(g):
                        raise DBPFError('%s: %d resources written, %d planned' % (name, len(pk.entries), len(g)))
                    for e in sorted(pk.entries, key=lambda e: e.off):
                        want = digests.get((e.t, e.g, e.i))
                        got = (hashlib.blake2b(pk.raw(e), digest_size=16).digest(), e.fsize, e.msize, e.comp)
                        if want != got:
                            raise DBPFError('%s: %s is not a bit-exact copy' % (name, key_text((e.t, e.g, e.i))))
            out.append({'path': path, 'keys': len(g), 'bytes': os.path.getsize(path)})
            if verbose:
                print('  wrote %s: %d keys, %.2f GB' % (name, len(g), out[-1]['bytes'] / 1e9), flush=True)
    finally:
        U._close_all(files)
    return out


def _manifest(plan, packages, old=None):
    per_src = collections.defaultdict(lambda: [0, 0])
    for it in plan.items.values():
        per_src[it.pkg][0] += 1
        per_src[it.pkg][1] += it.fsize
    s = plan.summary()
    return {
        'version': MANIFEST_VERSION,
        'rules': rules_fingerprint(),
        'built': (old or {}).get('built') or time.strftime('%Y-%m-%d %H:%M:%S'),
        'updated': time.strftime('%Y-%m-%d %H:%M:%S'),
        'roots': list(plan.roots),
        'root_dirs': plan.root_dirs,
        'include_backups': plan.include_backups,
        'packages': packages,
        'keys': sum(p['keys'] for p in packages),           # resources in the pack files (base + deltas)
        'bytes': sum(p['bytes'] for p in packages),         # size of the pack files on disk
        'plan_keys': s['keys'],
        'parts': s['parts'],
        'cas_parts': plan.stats.get('cas_parts', {}),
        'counts': {k: v for k, v in plan.stats.items() if k not in ('parts', 'cas_parts')},
        'saves_and_tray': plan.sources,
        'library': {'fingerprint': plan.library_fp, 'files': plan.library},
        'parked': [{'root': r, 'rel': rel, 'why': plan.parked.reasons.get((r, rel), '')} for r, rel in plan.parked],
        'sources': sorted(({'root': plan.packages[pid]['root'], 'rel': plan.packages[pid]['rel'], 'keys': n,
                            'bytes': b} for pid, (n, b) in per_src.items()), key=lambda x: -x['bytes']),
        'absent': {k: ['%016X' % v for v in vs] for k, vs in plan.absent.items()},
        'unloadable': {k: ['%016X' % v for v in vs] for k, vs in plan.unloadable.items()},
        'households_with_missing_cc': plan.households,
    }


def _keys_tsv(plan, groups, names, old_lines=None):
    lines = list(old_lines or ['package\ttype\tgroup\tinstance\tfsize\tpart\twhy\tsource'])
    for name, g in zip(names, groups):
        for it in g:
            src = plan.packages[it.pkg]
            lines.append('%s\t%08X\t%08X\t%016X\t%d\t%s\t%s\t%s/%s' % (name, it.t, it.g, it.i, it.fsize, it.part,
                                                                    it.why, src['root'], src['rel']))
    return lines


def _check_space(sims, need):
    free = shutil.disk_usage(sims).free
    if free < need + FREE_MARGIN:
        raise OSError('the fast pack needs %.1f GB free on the Sims 4 drive, only %.1f GB is'
                      % ((need + FREE_MARGIN) / 1e9, free / 1e9))


def _install(j, home, staged, out_dir, pack_dir, quarantine, check_game, kind=None):
    """Move staged files into place through the journal. Order: the old manifest leaves first (so a
    half-replaced pack never has a manifest vouching for it), then the old files, then the new packages,
    the keys file and - last - the new manifest."""
    kind = kind or FAST
    if check_game and game_running():
        raise JournalError('The Sims 4 was started meanwhile; nothing was moved. Try again once it is closed.')
    man = os.path.join(out_dir, kind.manifest)
    if os.path.exists(man):
        j.quarantine(man)
    for p in quarantine:
        if os.path.exists(p):
            j.quarantine(p)
    for p in sorted(staged, key=lambda p: (os.path.basename(p) == kind.manifest, os.path.basename(p) == kind.keys_file)):
        name = os.path.basename(p)
        dest = os.path.join(pack_dir if name.lower().endswith('.package') else out_dir, name)
        if os.path.exists(dest):
            j.replace(p, dest)
        else:
            j.put_new(p, dest)


def _run_journal(note, sims, home, check_game, work, kind=None):
    """Run work(journal, staging) in a Journal of the pack family's kind ('fastpack' / 'savepack'); on any
    failure remove our staging files and undo the journal's finished steps (so the previous pack is back).
    The staging folder holds an owner file (pid), so a later run can tell a crashed build's leftovers
    (cleanup_staging). Returns the journal id."""
    kind = kind or FAST
    j = Journal(kind.journal_kind, note, home=home, sims=sims, check_game=check_game)
    staging = os.path.join(home, 'staging', j.id)
    os.makedirs(staging, exist_ok=True)
    with open(os.path.join(staging, STAGING_OWNER), 'w', encoding='utf-8') as f:
        json.dump({'pid': os.getpid(), 'started': time.time(), 'journal': j.id}, f)
    try:
        work(j, staging)
        j.close('committed')
    except BaseException as ex:
        j.close('failed: %s' % (ex,))
        U._roll_back(j, home, os.path.dirname(staging), ex)
        raise
    finally:
        if os.path.isdir(staging):
            for n in os.listdir(staging):          # our own staging copies, never user files
                try:
                    os.remove(os.path.join(staging, n))
                except OSError:
                    pass
            try:
                os.rmdir(staging)
            except OSError:
                pass
    return j.id


# ------------------------------------------------------------------------------------------ disk hygiene
STAGING_OWNER = '.speedkit_owner.json'
PACK_JOURNAL_KINDS = ('fastpack', 'savepack', 'usedpack')
_STAGED_RX = re.compile(r'^(!!!!!SpeedKit_Fast_\d{3}|!!!!!SpeedKit_Save_[0-9A-Fa-f]{8}_\d{3}|SpeedKit_UsedCC_\d{3})'
                        r'\.package(\.writing|\.tmp)?$|^(fastpack|savepack|usedpack)(\.json|_keys\.tsv)$', re.I)
STALE_STAGING_SECONDS = 6 * 3600       # a staging folder without an owner file and an open journal: stale after this


def pack_family(name):
    """'fast', 'save:<hex>' or 'used' for a SpeedKit pack file name, else None."""
    n = os.path.basename(name.replace('\\', '/'))
    if not is_speedkit_pack(n):
        return None
    slot = save_pack_slot(n)
    if slot:
        return 'save:' + slot[5:]
    return 'fast' if n.lower().startswith(PACK_PREFIX.lower()) else 'used'


def _pid_alive(pid, started=None):
    """Is process pid running (and, when started is given, did it start no later than that)? Unknown -> True."""
    if not isinstance(pid, int) or pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if os.name != 'nt':
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    h = k32.OpenProcess(0x1000, False, pid)          # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return ctypes.get_last_error() == 5           # access denied: some process has it
    try:
        code = wintypes.DWORD()
        if not k32.GetExitCodeProcess(h, ctypes.byref(code)) or code.value != 259:     # STILL_ACTIVE
            return False
        if started is not None:
            ft = [wintypes.FILETIME() for _ in range(4)]
            if k32.GetProcessTimes(h, *[ctypes.byref(x) for x in ft]):
                created = ((ft[0].dwHighDateTime << 32) | ft[0].dwLowDateTime) / 1e7 - 11644473600.0
                if created > started + 2.0:            # the pid was reused by a newer process
                    return False
        return True
    finally:
        k32.CloseHandle(h)


def _journal_doc(home, jid):
    try:
        with open(os.path.join(home, 'journal', jid + '.json'), encoding='utf-8') as f:
            doc = json.load(f)
        return doc if isinstance(doc, dict) else None
    except (OSError, ValueError):
        return None


def _write_journal_doc(home, doc):
    path = os.path.join(home, 'journal', doc['id'] + '.json')
    with open(path + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(doc, f, indent=1)
    os.replace(path + '.tmp', path)


def _remove_file(path):
    try:
        os.remove(path)
    except PermissionError:
        import stat
        os.chmod(path, stat.S_IWRITE)
        os.remove(path)


def cleanup_staging(home, dry_run=False, now=None):
    """Remove what a crashed pack build left in <home>\\staging\\<journal id>: the build's own staged pack files,
    manifest and keys file (SpeedKit output; nothing else is touched, and a folder with anything else in it
    stays). A folder counts as left over when its owner process (STAGING_OWNER) is gone, or - for folders of
    older builds without an owner file - when its journal is closed or has been open for STALE_STAGING_SECONDS.
    A still-open journal of a dead build is marked 'failed: interrupted' (undo still works). Only pack journal
    kinds (fastpack, savepack, usedpack) are looked at. Returns [{'folder', 'files', 'bytes'}]."""
    root = os.path.join(home, 'staging')
    out = []
    if not os.path.isdir(root):
        return out
    now = time.time() if now is None else now
    for jid in sorted(os.listdir(root)):
        folder = os.path.join(root, jid)
        if not os.path.isdir(folder):
            continue
        doc = _journal_doc(home, jid)
        kind = (doc or {}).get('kind') or jid.split('-')[2] if len(jid.split('-')) > 2 else None
        if kind not in PACK_JOURNAL_KINDS:
            continue
        owner = None
        try:
            with open(os.path.join(folder, STAGING_OWNER), encoding='utf-8') as f:
                owner = json.load(f)
        except (OSError, ValueError):
            owner = None
        state = (doc or {}).get('state')
        if isinstance(owner, dict):
            if _pid_alive(owner.get('pid'), owner.get('started')):
                continue
        elif state == 'open' and now - os.path.getmtime(folder) < STALE_STAGING_SECONDS:
            continue
        files, size, other = [], 0, False
        for dp, dn, fn in os.walk(folder):
            for n in fn:
                p = os.path.join(dp, n)
                if n == STAGING_OWNER or _STAGED_RX.match(n):
                    files.append(p)
                    try:
                        size += os.path.getsize(p)
                    except OSError:
                        pass
                else:
                    other = True
        out.append({'folder': folder, 'files': len(files), 'bytes': size, 'kept_other_files': other})
        if dry_run:
            continue
        for p in files:
            try:
                _remove_file(p)
            except OSError:
                pass
        for dp, dn, fn in sorted(os.walk(folder, topdown=False), key=lambda x: -len(x[0])):
            try:
                os.rmdir(dp)
            except OSError:
                pass
        if doc is not None and state == 'open':
            doc['state'] = 'failed: interrupted (its staging folder was cleaned up %s)' % time.strftime('%Y-%m-%d %H:%M:%S')
            try:
                _write_journal_doc(home, doc)
            except OSError:
                pass
    return out


def prune_quarantine(home, keep=1, dry_run=False, kinds=PACK_JOURNAL_KINDS):
    """Keep at most the newest `keep` previous copies of each pack family (the fast pack, each save pack, the
    used-CC pack) in SpeedKit's quarantine and delete the older ones. Packs are SpeedKit's own, regenerable
    output (7-8 GB each), so a rebuild must not pile them up on C:.

    Looked at: the pack files (exact SpeedKit pack names only) that journals of the pack kinds moved into
    their quarantine folder, and the new pack files an undo of such a journal set aside ('_undone_new'). Open
    journals (a build in progress, or crashed) are never touched. Every pruned copy is recorded in its
    journal ('pruned' on the step, the journal's 'pruned' list); a committed journal whose pack copies are
    all gone gets the state 'pruned' (it can no longer be undone). Returns {'pruned': [{'journal', 'path',
    'bytes'}], 'bytes': freed, 'kept': {family: journal id}}."""
    jdir = os.path.join(home, 'journal')
    report = {'pruned': [], 'bytes': 0, 'kept': {}}
    if not os.path.isdir(jdir):
        return report
    docs = {}
    copies = collections.defaultdict(lambda: collections.defaultdict(list))   # family -> jid -> [(path, step)]
    for n in sorted(os.listdir(jdir)):
        if not n.endswith('.json'):
            continue
        doc = _journal_doc(home, n[:-5])
        if not doc or doc.get('kind') not in kinds or doc.get('state') == 'open' or 'id' not in doc:
            continue
        qdir = doc.get('quarantine') or os.path.join(home, 'quarantine', doc['id'])
        docs[doc['id']] = doc
        for idx, s in enumerate(doc.get('steps', [])):
            if s.get('op') != 'quarantine' or s.get('undone') or s.get('pruned'):
                continue
            q = s.get('q') or ''
            fam = pack_family(q)
            if fam and _inside(q, qdir) and os.path.isfile(q):
                copies[fam][doc['id']].append((q, idx))
        undone_new = os.path.join(qdir, '_undone_new')
        if os.path.isdir(undone_new):
            for dp, dn, fn in os.walk(undone_new):
                for f in fn:
                    fam = pack_family(f)
                    if fam:
                        copies[fam][doc['id']].append((os.path.join(dp, f), None))
    changed = set()
    for fam, by_j in copies.items():
        order = sorted(by_j)                       # journal ids start with their time
        keep_ids = order[-keep:] if keep > 0 else []
        if keep_ids:
            report['kept'][fam] = keep_ids[-1]
        for jid in order:
            if jid in keep_ids:
                continue
            doc = docs[jid]
            for path, idx in by_j[jid]:
                try:
                    size = os.path.getsize(path)
                except OSError:
                    size = 0
                report['pruned'].append({'journal': jid, 'path': path, 'bytes': size})
                report['bytes'] += size
                if dry_run:
                    continue
                try:
                    _remove_file(path)
                except OSError as e:
                    report['pruned'][-1]['error'] = str(e)
                    continue
                if idx is not None:
                    doc['steps'][idx]['pruned'] = True
                doc.setdefault('pruned', []).append(path)
                changed.add(jid)
    if not dry_run:
        for jid in changed:
            doc = docs[jid]
            doc['pruned_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
            left = [s for s in doc.get('steps', []) if s.get('op') == 'quarantine' and not s.get('undone')
                    and not s.get('pruned') and pack_family(s.get('q') or '')]
            if doc.get('state') != 'undone' and not left:
                doc['state'] = 'pruned'
                doc['note'] = (doc.get('note') or '') + ' [older pack copies deleted to save disk space]'
            try:
                _write_journal_doc(home, doc)
            except OSError:
                pass
            qdir = doc.get('quarantine') or os.path.join(home, 'quarantine', jid)
            if os.path.isdir(qdir):
                for dp, dn, fn in sorted(os.walk(qdir, topdown=False), key=lambda x: -len(x[0])):
                    try:
                        os.rmdir(dp)
                    except OSError:
                        pass
    return report


def build_pack(plan, out_dir=None, max_package_bytes=1_900_000_000, dry_run=True, check_game=False, pack_dir=None,
               sims=None, home=None, check_copy=True, verbose=False, kind=None, prune=False):
    """Write the fast pack: '!!!!!SpeedKit_Fast_001.package', 002, ... plus fastpack.json and fastpack_keys.tsv.

    out_dir: where fastpack.json lives (default <Sims 4>\\SpeedKit\\fastpack of the plan's library). pack_dir:
    where the .package files go (default out_dir; the Mods root when the fast profile is active - then the
    game must not run, whatever check_game says). Every resource is copied bit-exact (add_raw) from the
    copy the plan chose and, with check_copy, re-read and compared. Returns [{'path', 'keys', 'bytes'
    (, 'journal')}]; dry_run (default) only returns the layout. A real run checks the sources are unchanged
    since the plan (usedpack.PlanStale), refuses without the pack's size + 1 GiB free, refuses when pack
    files of an earlier build sit in the other folder (Mods root vs fastpack), stages the files under
    SpeedKit\\staging and moves them into place through Journal('fastpack') - older pack files are
    quarantined, never deleted; a failure undoes the journal. journal.undo(result[0]['journal']) restores the
    previous pack. Outside Mods the game running does not matter, so check_game defaults to False.
    kind: the pack family (default FAST; speedkit.savepacks passes a save pack's). prune: afterwards keep only
    the newest previous copy of each pack family in SpeedKit's quarantine (prune_quarantine)."""
    kind = kind or FAST
    groups = layout(plan, max_package_bytes)
    if len(groups) >= DELTA_FIRST:
        raise FastPackError('the fast pack would need %d packages' % len(groups))
    sims = sims or plan.sims or _sims_of(plan.root_dirs)
    out_dir = out_dir or os.path.join(sims, 'SpeedKit', 'fastpack')
    pack_dir = pack_dir or out_dir
    names = [kind.name(n + 1) for n in range(len(groups))]
    result = [{'path': os.path.join(pack_dir, name), 'keys': len(g), 'bytes': 96 + 4 + sum(it.fsize + 32 for it in g),
               'parts': dict(collections.Counter(it.part for it in g))} for name, g in zip(names, groups)]
    if dry_run:
        return result
    home = home or os.path.join(sims, 'SpeedKit')
    in_mods = _destinations(plan, out_dir, pack_dir, sims)
    check_game = check_game or in_mods
    for other in {os.path.normcase(os.path.abspath(d)) for d in (out_dir, plan.root_dirs.get('Mods')) if d}:
        if other != os.path.normcase(os.path.abspath(pack_dir)) and _stray_pack_files(other, kind):
            raise FastPackError('%s files are also in %s (the %s); building into %s would load two packs. '
                                'Switch profile first, or pass pack_dir=%r' % (
                                    kind.label, other, 'pack is deployed' if in_mods is False else 'pack folder',
                                    pack_dir, other))
    _check_space(sims, sum(r['bytes'] for r in result))
    old = [os.path.join(pack_dir, n) for n in _stray_pack_files(pack_dir, kind)] + [os.path.join(out_dir,
                                                                                             kind.keys_file)]

    def work(j, staging):
        written = _write_packages(plan, groups, names, staging, check_copy, verbose)
        for r, w in zip(result, written):
            r['bytes'] = w['bytes']
        pk = [{'name': n, 'keys': len(g), 'bytes': w['bytes'], 'kind': 'base'} for n, g, w in zip(names, groups, written)]
        with open(os.path.join(staging, kind.manifest), 'w', encoding='utf-8') as f:
            json.dump(_manifest(plan, pk), f, indent=1)
        with open(os.path.join(staging, kind.keys_file), 'w', encoding='utf-8') as f:
            f.write('\n'.join(_keys_tsv(plan, groups, names)) + '\n')
        _install(j, home, [w['path'] for w in written] + [os.path.join(staging, kind.keys_file),
                                                          os.path.join(staging, kind.manifest)],
                 out_dir, pack_dir, old, check_game, kind)

    jid = _run_journal('%s: %d keys, %.2f GB -> %s' % (kind.label, len(plan.items), plan.total_bytes() / 1e9, pack_dir),
                       sims, home, check_game, work, kind)
    for r in result:
        r['journal'] = jid
    if prune:
        prune_quarantine(home)
    return result


# ------------------------------------------------------------------------------------------ status / update
def _saves_changed(man, saves_dir, tray_dir, pack_kind=None):
    """Names of save/Tray files that are new or changed since the pack was built (removed ones do not matter).
    A save pack (pack_kind.save_file) only looks at its own save file."""
    pack_kind = pack_kind or FAST
    rec = man.get('saves_and_tray', [])
    quick = {(r['name'], r['size'], r['mtime_ns']) for r in rec}
    fps = {r['fp'] for r in rec}
    b = man.get('include_backups', False)
    out = []
    for path, kind in U.list_sources(saves_dir, tray_dir):
        if kind == 'backup' and not b:
            continue
        if kind != 'backup' and not pack_kind.counts(path, kind):
            continue
        try:
            st = os.stat(path)
            if (os.path.basename(path), st.st_size, st.st_mtime_ns) in quick:
                continue
            if U.fingerprint(path, st.st_size) not in fps:
                out.append(os.path.basename(path))
        except OSError:
            continue
    return out


def _library_diff(old_rows, new_rows):
    """(added, removed, changed) relative paths between two library listings."""
    old = collections.defaultdict(list)
    new = collections.defaultdict(list)
    for rel, size, mt in old_rows:
        old[rel.lower()].append((size, mt, rel))
    for rel, size, mt in new_rows:
        new[rel.lower()].append((size, mt, rel))
    added = sorted(v[0][2] for k, v in new.items() if k not in old)
    removed = sorted(v[0][2] for k, v in old.items() if k not in new)
    changed = sorted(v[0][2] for k, v in new.items() if k in old and sorted(x[:2] for x in v)
                     != sorted(x[:2] for x in old[k]))
    return added, removed, changed


def status(out_dir=DEFAULT_OUT, root_dirs=None, saves_dir=None, tray_dir=None, check_saves=True, kind=None):
    """Is the fast pack in out_dir up to date? Returns {'state': 'fresh'|'stale'|'missing', 'why': [...],
    'library_changed', 'saves_changed' (names), 'pack': find_pack(...), 'keys', 'bytes', 'built'}.

    Stale when a pack file is missing or has another size, sits in both the fastpack folder and Mods, or a
    fast pack file fastpack.json does not list is there (the game would load it first); when any mod file
    (package or script, either root; the profile switcher's moves between roots do not count) was added,
    removed or changed; when a save/Tray file is new or changed; or when SpeedKit's park/plan rules
    (rules_fingerprint) are not the ones the pack was built with. root_dirs default to the ones recorded at
    build time; saves and Tray default to the Sims 4 folder holding them. kind: the pack family (default
    FAST; a save pack only counts its own save file)."""
    kind = kind or FAST
    try:
        man = read_manifest(out_dir, kind)
    except ValueError as e:
        return {'state': 'stale', 'why': ['%s is damaged (%s): rebuild' % (kind.manifest, e)], 'library_changed': True,
                'saves_changed': [], 'pack': {'where': 'none', 'files': {}}}
    if man is None or man.get('version') != MANIFEST_VERSION:
        return {'state': 'missing', 'why': ['no %s has been built yet' % kind.label if man is None else
                                            '%s is from another version: rebuild' % kind.manifest],
                'library_changed': True, 'saves_changed': [], 'pack': {'where': 'none', 'files': {}}}
    root_dirs = root_dirs or man.get('root_dirs') or {}
    sims = _sims_of(root_dirs) if root_dirs else SIMS
    why = []
    pack = find_pack(out_dir, root_dirs.get('Mods'), man, kind)
    if pack['missing']:
        why.append('pack files missing: %s' % ', '.join(pack['missing']))
    if pack['wrong_size']:
        why.append('pack files changed: %s' % ', '.join(pack['wrong_size']))
    if pack['duplicated']:
        why.append('pack files are in both the pack folder and Mods: %s' % ', '.join(pack['duplicated']))
    elif pack['where'] == 'split':
        why.append('pack files are split between the pack folder and Mods')
    if pack['extra']:
        why.append('%s files that %s does not list: %s'
                   % (kind.label, kind.manifest, ', '.join(os.path.basename(p) for p in pack['extra'])))
    if man.get('rules') != rules_fingerprint():
        why.append("SpeedKit's rules for what the fast profile leaves out changed since the pack was built")
    now = library_listing_disk(root_dirs)
    lib_changed = listing_fingerprint(now) != man.get('library', {}).get('fingerprint')
    if lib_changed:
        added, removed, changed = _library_diff(man.get('library', {}).get('files', []), now)
        bits = ['%d %s (e.g. %s)' % (len(x), label, x[0]) for x, label in
                ((added, 'new'), (removed, 'gone'), (changed, 'changed')) if x]
        why.append('the mod library changed: ' + ('; '.join(bits) or 'listing differs'))
    saves = []
    if check_saves:
        saves = _saves_changed(man, saves_dir or os.path.join(sims, 'saves'), tray_dir or os.path.join(sims, 'Tray'),
                               kind)
        if saves:
            why.append('%d save/Tray files are new or changed (e.g. %s)' % (len(saves), saves[0]))
    return {'state': 'stale' if why else 'fresh', 'why': why, 'library_changed': lib_changed or bool(
        pack['missing'] or pack['wrong_size'] or pack['where'] == 'split' or pack['extra']),
            'saves_changed': saves, 'pack': pack,
            'keys': man.get('keys'), 'bytes': man.get('bytes'), 'built': man.get('built'),
            'updated': man.get('updated')}


def pack_index(out_dir=DEFAULT_OUT, manifest=None, kind=None):
    """{(t, g, i): (path, Entry)} of every resource in the pack files listed in fastpack.json, wherever they
    are (fastpack folder or Mods root). Files are read in name order, the order the game loads them."""
    man = manifest if manifest is not None else read_manifest(out_dir, kind)
    if man is None:
        return {}
    out = {}
    files = find_pack(out_dir, (man.get('root_dirs') or {}).get('Mods'), man, kind)['files']
    for name in sorted(files, key=lambda n: n.upper()):
        with open_shared(files[name]) as f:
            for e in read_entries(f):
                if e.comp != DELETED:
                    out.setdefault((e.t, e.g, e.i), (files[name], e))
    return out


def pack_keys(out_dir=DEFAULT_OUT, manifest=None, kind=None):
    """{(t, g, i): Entry} of every resource in the pack (see pack_index)."""
    return {k: e for k, (_, e) in pack_index(out_dir, manifest, kind).items()}


def _key_sources(out_dir, kind=None):
    """{(t, g, i): source rel} from fastpack_keys.tsv (None if the file is missing or damaged)."""
    path = os.path.join(out_dir, (kind or FAST).keys_file)
    if not os.path.exists(path):
        return None
    out = {}
    try:
        with open(path, encoding='utf-8') as f:
            lines = f.read().splitlines()
        for line in lines[1:]:
            if not line:
                continue
            c = line.split('\t')
            out[(int(c[1], 16), int(c[2], 16), int(c[3], 16))] = c[-1].split('/', 1)[1]
    except (ValueError, IndexError, OSError):
        return None
    return out


def pack_problems(lib, out_dir=DEFAULT_OUT, roots=ROOTS2, limit=20, kind=None):
    """Pack keys that no longer reproduce the full library (from the index as it is now): the key is gone
    from the library, or its winning copy is not the one the pack holds (another package, or other
    bytes). Returns [(key text, why)] (at most limit) - empty means the pack can be kept and only
    extended. A missing/damaged keys file counts as a problem."""
    kind = kind or FAST
    view = _view(lib)
    man = read_manifest(out_dir, kind)
    src = _key_sources(out_dir, kind)
    if man is None or src is None:
        return [('-', 'no %s / %s' % (kind.manifest, kind.keys_file))]
    pack = pack_keys(out_dir, man, kind)
    ids = _ids(view)
    pos = {ids[k]: n for n, k in enumerate(view.load_order(roots)) if k in ids}
    rels = {pid: rel for (r, rel), pid in ids.items()}
    # the pack's source packages must be exactly the files it copied (size + mtime as recorded)
    then = collections.defaultdict(set)
    for rel, size, mt in man.get('library', {}).get('files', []):
        then[rel.upper()].add((size, mt))
    now = {p.id: (p.size, round(p.mtime, 3)) for p in view.packages()}
    changed = {rels[pid].upper() for pid in pos if now.get(pid) not in then.get(rels[pid].upper(), ())}
    rows = _loaded_keys(view, pos, list(pack))
    out = []
    for k, e in pack.items():
        row = rows.get(k)
        if row is None:
            why = 'no longer in the library'
        elif k not in src or rels[row[1]].upper() != src[k].upper():
            why = 'the library now uses the copy in %s' % rels[row[1]]
        elif rels[row[1]].upper() in changed:
            why = 'its source %s changed' % src[k]
        elif (row[3], row[4], row[5]) != (e.fsize, e.msize, e.comp):
            why = 'its source %s changed' % src[k]
        else:
            continue
        out.append((key_text(k), why))
        if len(out) >= limit:
            break
    return out


def update_pack(lib, refs, out_dir=None, parked=None, max_package_bytes=1_900_000_000, delta_limit=DELTA_LIMIT,
                dry_run=True, check_game=False, sims=None, home=None, verbose=False, kind=None, prune=False,
                **plan_kw):
    """Bring the fast pack up to date with the least work. Scan the library first: an index that does not
    match the files on disk is refused (FastPackError), since a pack planned from it would be wrong.

      fresh                                   -> 'none'
      no pack, a pack file missing / resized  -> 'rebuild'
      otherwise (saves/Tray or the library changed) plan again, then:
        a pack key no longer reproduces the full library (its package changed or went, or another copy
        now wins - pack_problems)             -> 'rebuild'
        every needed key is in the pack       -> 'refresh' (only fastpack.json is rewritten)
        some are missing                      -> 'delta': one more package '!!!!!SpeedKit_Fast_900.package'
                                                 (901, ...) next to the others, unless all deltas together
                                                 would pass delta_limit (500 MB) -> 'rebuild'
    So a change to a kept package (FitStudio exporting an animation, a script mod update) or a new save
    costs a delta or nothing, and only a change to what the pack copied costs a rebuild. Returns
    {'action', 'why', 'missing_keys', 'missing_bytes', 'result', 'plan', 'journal'}; dry_run (default) only
    reports. plan_kw go to plan_pack (game, overrides, cache_path, bc_cache, progress ...). kind: the pack
    family (default FAST). prune: keep only the newest previous copy of each pack family in the quarantine."""
    kind = kind or FAST
    view = _view(lib)
    root_dirs = dict(view.roots)
    lib_sims = _sims_of(root_dirs)                  # where the saves and Tray are
    sims = sims or lib_sims                         # where the journal and the pack live
    out_dir = out_dir or os.path.join(sims, 'SpeedKit', 'fastpack')
    st = status(out_dir, root_dirs, os.path.join(lib_sims, 'saves'), os.path.join(lib_sims, 'Tray'), kind=kind)
    res = {'action': 'none', 'why': st['why'], 'missing_keys': 0, 'missing_bytes': 0, 'result': None}
    if st['state'] == 'fresh':
        return res
    if library_listing_index(view) != library_listing_disk(root_dirs):
        raise FastPackError('the library index is out of date (files changed since the last scan): scan the '
                            'library, then update the fast pack')
    parked = parked if parked is not None else park_set(view, plan_kw.get('roots', ROOTS2),
                                                        cache_path=plan_kw.get('cache_path', companions.DEFAULT_CACHE))
    plan_kw.setdefault('pack_name', kind.name(1))
    plan = plan_pack(view, refs, parked, verbose=verbose, **plan_kw)
    res['plan'] = plan
    pack = st['pack']
    pack_dir = pack.get('dir') or out_dir
    try:
        man = read_manifest(out_dir, kind) if st['state'] != 'missing' else None
    except ValueError:                       # damaged fastpack.json: rebuild (the build quarantines it)
        man = None

    def rebuild(why):
        res['action'] = 'rebuild'
        res['why'] = st['why'] + [why]
        res['result'] = build_pack(plan, out_dir, max_package_bytes, dry_run, check_game, pack_dir=pack_dir, sims=sims,
                                   home=home, verbose=verbose, kind=kind, prune=prune)
        res['journal'] = res['result'][0].get('journal') if res['result'] else None
        return res

    if man is None or st['state'] == 'missing':
        return rebuild('no usable pack: full build')
    if pack['missing'] or pack['wrong_size'] or pack['where'] == 'split' or pack.get('extra'):
        return rebuild('pack files missing, changed, doubled or unlisted: full rebuild')
    probs = pack_problems(view, out_dir, plan.roots, kind=kind)
    if probs:
        return rebuild('the pack no longer matches the library (e.g. %s: %s): full rebuild' % probs[0])
    have = pack_keys(out_dir, man, kind)
    missing = [it for k, it in plan.items.items() if k not in have]
    res['missing_keys'] = len(missing)
    res['missing_bytes'] = sum(it.fsize for it in missing)
    deltas = [p for p in man['packages'] if p.get('kind') == 'delta']
    if missing and res['missing_bytes'] + sum(p['bytes'] for p in deltas) > delta_limit:
        return rebuild('%d missing keys (%.0f MB) with the earlier deltas pass %.0f MB' % (
            len(missing), res['missing_bytes'] / 1e6, delta_limit / 1e6))
    n = max([DELTA_FIRST - 1] + [kind.number(p['name']) or DELTA_FIRST - 1 for p in deltas]) + 1
    if missing and n > 999:                  # names must stay '###' so is_speedkit_pack() knows them
        return rebuild('delta numbers used up: full rebuild')
    name = kind.name(n)
    res['action'] = 'delta' if missing else 'refresh'
    groups = layout(plan, max_package_bytes, missing) if missing else []
    if len(groups) > 1:
        return rebuild('the delta does not fit one package')
    if dry_run:
        res['result'] = [{'path': os.path.join(pack_dir, name), 'keys': len(missing),
                          'bytes': 96 + 4 + sum(it.fsize + 32 for it in missing)}] if missing else []
        return res
    home = home or os.path.join(sims, 'SpeedKit')
    in_mods = _destinations(plan, out_dir, pack_dir, sims)
    check_game = check_game or in_mods
    if missing:
        _check_space(sims, res['missing_bytes'])
    keys_path = os.path.join(out_dir, kind.keys_file)
    with open(keys_path, encoding='utf-8') as f:
        old_lines = f.read().splitlines()

    def work(j, staging):
        written = _write_packages(plan, groups, [name], staging) if groups else []
        pk = list(man['packages']) + [{'name': name, 'keys': w['keys'], 'bytes': w['bytes'], 'kind': 'delta'}
                                      for w in written]
        with open(os.path.join(staging, kind.manifest), 'w', encoding='utf-8') as f:
            json.dump(_manifest(plan, pk, man), f, indent=1)
        with open(os.path.join(staging, kind.keys_file), 'w', encoding='utf-8') as f:
            f.write('\n'.join(_keys_tsv(plan, groups, [name], old_lines)) + '\n')
        _install(j, home, [w['path'] for w in written] + [os.path.join(staging, kind.keys_file),
                                                          os.path.join(staging, kind.manifest)],
                 out_dir, pack_dir, [], check_game, kind)
        # where the delta is now (not the staging copy, which is gone)
        res['result'] = [dict(w, path=os.path.join(pack_dir, os.path.basename(w['path']))) for w in written]

    jid = _run_journal('%s %s: %d keys, %.1f MB' % (kind.label, res['action'], len(missing), res['missing_bytes'] / 1e6),
                       sims, home, check_game, work, kind)
    for r in res['result'] or []:
        r['journal'] = jid
    res['journal'] = jid
    if prune:
        prune_quarantine(home)
    return res


# ------------------------------------------------------------------------------------------ verify
VERIFY_CHECKS = U.VERIFY_CHECKS


def _loaded_keys(view, pos, keys):
    """{key: (pos, pkg, off, fsize, msize, comp)} of the loaded copy each key's winner is, for the keys
    that the loaded library has at all (batched through a temp table)."""
    out = {}
    if not keys:
        return out
    db = view.db
    db.execute('drop table if exists temp.fm_keys')
    db.execute('create temp table fm_keys(t integer, g integer, i integer)')
    db.executemany('insert into temp.fm_keys values(?,?,?)', ((t, g, U.signed64(i)) for t, g, i in keys))
    for t, g, i, pkg, off, fs, ms, comp in db.execute(
            'select r.t, r.g, r.i, r.pkg, r.off, r.fsize, r.msize, r.comp from temp.fm_keys k '
            'join res r on r.t = k.t and r.g = k.g and r.i = k.i where r.comp != ?', (DELETED,)):
        p = pos.get(pkg)
        if p is None:
            continue
        k = (t, g, unsigned64(i))
        cur = out.get(k)
        if cur is None or p < cur[0]:
            out[k] = (p, pkg, off, fs, ms, comp)
    db.execute('drop table temp.fm_keys')
    return out


def verify(lib, refs, out_dir=None, parked=None, game=None, overrides=None, include_backups=None,
           use_scripts=True, cache_path=companions.DEFAULT_CACHE, game_db=None, game_dir=None, limit=200, kind=None):
    """What the fast profile (the kept packages + the pack in out_dir) would miss compared to the full
    library (Mods + Mods_parked). Read-only. Returns {'ok', 'missing': [(check, what, detail)],
    'different': [...], 'installed_nowhere': {category: count}, 'checked': {...}}; 'ok' means 'missing' and
    'different' are empty - then all that is missing is CC installed nowhere (missing in the full library too).

    Checks, each against the library index as it is now:
      refs      every CAS part / tone / sculpt / slider / pet coat / object the saves and Tray use that the
                full library loads is loaded in fast mode (pack or kept package);
      closure   every mesh/texture key those CAS parts list that the full library has, fast mode has too;
      tuning    every CC CAS part / object / tone / sculpt / slider / pet coat id (64-bit, or a 32-bit one the
                game does not ship) in the XML tuning and SimData fast mode loads, or hard-coded in a script,
                that the full library loads, fast mode loads too (and its closure); so does every asset key
                the tuning writes out in full ('00B2D882:00000000:...' icons);
      order     no kept package that the game reaches before a pack file ('!!!!!!x.package') holds another
                copy of one of its keys (it would win in fast mode);
      winners   every key a kept package has, every non-asset key and every EA override: where the full
                library's copy is in a parked package, the pack has that key ('different' if fast mode would
                use a kept package's copy instead, 'missing' if it would have none);
      pack      each pack resource has the size/compression of the full library's copy (else the pack is
                stale: 'different').
    parked defaults to fastpack.json's list (by relative path, whichever root the file is in now)."""
    view = _view(lib)
    root_dirs = dict(view.roots)
    sims = _sims_of(root_dirs)
    out_dir = out_dir or os.path.join(sims, 'SpeedKit', 'fastpack')
    kind = kind or FAST
    man = read_manifest(out_dir, kind)
    if man is None:
        raise FileNotFoundError('no %s in %s' % (kind.manifest, out_dir))
    b = man.get('include_backups', False) if include_backups is None else include_backups
    if b and not refs.backups_scanned:
        raise ValueError('the pack was built with .ver backups; verify with scan_references(include_backups=True)')
    roots = tuple(man.get('roots') or ROOTS2)
    ids = _ids(view)
    order = view.load_order(roots)
    pos = {ids[k]: n for n, k in enumerate(order) if k in ids}
    parked_rels = ({x['rel'].upper() for x in man.get('parked', [])} if parked is None
                   else {rel.upper() for _, rel in parked})
    parked_ids = {pid for (r, rel), pid in ids.items() if pid in pos and rel.upper() in parked_rels}
    kept_ids = set(pos) - parked_ids
    pkgs = {p.id: p for p in view.packages()}
    game = game if game is not None else U.load_game_ids(**({'game_dir': game_dir} if game_dir else {}))
    if overrides is None:
        from .game_index import GameIndex, DEFAULT_DB, GAME_DIR
        gi = GameIndex(game_db or DEFAULT_DB, game_dir or GAME_DIR)
        try:
            overrides = gi.override_keys(view.lib, roots)
        finally:
            gi.close()
    pack_loc = pack_index(out_dir, man, kind)
    pack = {k: e for k, (_, e) in pack_loc.items()}
    missing, different = [], []
    checked = collections.Counter()

    def miss(check, what, detail=''):
        if len(missing) < limit:
            missing.append((check, what, detail))
        checked['missing_' + check] += 1

    def differ(check, what, detail=''):
        if len(different) < limit:
            different.append((check, what, detail))
        checked['different_' + check] += 1

    # stream the index: kept keys (+ their tuning), catalog instances of the full library and of fast mode
    q = 'select t, g, i, pkg, off, fsize, msize, comp from res where comp != ? and pkg in (%s)'
    kept_best, kept_text = {}, []
    full_cat = {t: set() for t in CATALOG}
    fast_cat = {t: set() for t in CATALOG}
    for t, g, i, pkg, off, fs, ms, comp in view.db.execute(
            q % (','.join(str(p) for p in sorted(kept_ids)) or '-1'), (DELETED,)):
        if t in SKIP_TYPES:
            continue
        i = unsigned64(i)
        k = (t, g, i)
        p = pos[pkg]
        cur = kept_best.get(k)
        if cur is None or p < cur[0]:
            kept_best[k] = (p, pkg, off, fs, ms, comp)
        if t in CATALOG:
            full_cat[t].add(i)
            fast_cat[t].add(i)
        if _is_text_candidate(t, ms):
            kept_text.append((pkg, off, fs, comp, ms, t))
    for k in pack:
        if k[0] in CATALOG:
            fast_cat[k[0]].add(k[2])
    parked_list = ','.join(str(p) for p in sorted(parked_ids)) or '-1'
    for t, i in view.db.execute('select t, i from res where comp != ? and pkg in (%s) and +t in (%s)'
                                % (parked_list, ','.join(str(t) for t in sorted(CATALOG))), (DELETED,)):
        full_cat[t].add(unsigned64(i))
    parked_best = {}

    def take(t, g, i, pkg, off, fs, ms, comp):
        k = (t, g, unsigned64(i))
        p = pos[pkg]
        cur = parked_best.get(k)
        if cur is None or p < cur[0]:
            parked_best[k] = (p, pkg, off, fs, ms, comp)

    marks = ','.join(str(t) for t in sorted(ASSET_TYPES | SKIP_TYPES))
    for row in view.db.execute(q % parked_list + ' and t not in (%s)' % marks, (DELETED,)):
        take(*row)
    wanted = {k for k in list(pack) + list(kept_best) + list(overrides) if k[0] in ASSET_TYPES}
    view.db.execute('drop table if exists temp.fm_want')
    view.db.execute('create temp table fm_want(t integer, g integer, i integer)')
    view.db.executemany('insert into temp.fm_want values(?,?,?)', ((t, g, U.signed64(i)) for t, g, i in wanted))
    for row in view.db.execute('select r.t, r.g, r.i, r.pkg, r.off, r.fsize, r.msize, r.comp from temp.fm_want w '
                               'join res r on r.t = w.t and r.g = w.g and r.i = w.i '
                               'where r.comp != ? and r.pkg in (%s)' % parked_list, (DELETED,)):
        take(*row)
    view.db.execute('drop table temp.fm_want')

    # refs: the ids the saves and Tray use
    absent = collections.Counter()
    for cat, types in VERIFY_CHECKS:
        for v in refs.ids(cat, b):
            checked['refs'] += 1
            if any(v in full_cat[t] for t in types):
                if not any(v in fast_cat[t] for t in types):
                    miss('refs', '%s %016X' % (cat, v), 'loaded by the full library, not in fast mode')
            elif v >= BIG and cat != U.PART_OTHER and not any(game.has(t, v) for t in types):
                absent[cat] += 1

    reader = _Reader(view, pkgs)
    pack_files = {}

    def fast_copy(key):
        """The data of the copy of key fast mode uses: the pack's, else the first kept package's."""
        if key in pack_loc:
            path, e = pack_loc[key]
            f = pack_files.get(path)
            if f is None:
                f = pack_files[path] = open_shared(path)
            return _read_resource(f, e.off, e.fsize, e.comp, e.msize)
        row = kept_best.get(key)
        if row is None:
            raise KeyError(key)
        return reader.read(row[1], row[2], row[3], row[5], row[4])

    def check_closure(instances, check):
        """Mesh/texture keys listed by fast mode's copies of these CAS parts: present in fast mode when the
        full library has them."""
        casps = [k for k in list(pack) + list(kept_best) if k[0] == U.T_CASP and k[2] in instances]
        listed = {}
        for k in set(casps):
            try:
                lst = U.casp_refs(fast_copy(k))
            except Exception:
                checked[check + '_unreadable'] += 1
                continue
            checked[check + '_casps'] += 1
            for rk in lst:
                if rk[0] in U.CASP_REF_TYPES and rk[2]:
                    listed.setdefault(rk, k[2])
        need = [rk for rk in listed if rk not in pack and rk not in kept_best]
        for rk in _loaded_keys(view, pos, need):
            miss(check, key_text(rk), 'listed by CAS part %016X' % listed[rk])

    try:
        check_closure(refs.ids(U.PART, b) | refs.ids(U.PART_OTHER, b), 'closure')
        check_closure({k[2] for k in kept_best if k[0] == U.T_CASP}, 'kept_closure')
        # tuning / SimData / scripts fast mode loads
        tarr, per_cat = _catalog_arrays({t: {v for v in s if is_cc_id(t, v, game)} for t, s in full_cat.items()})
        scan_st = collections.Counter()
        named_keys = set()
        found = _scan_refs(reader, kept_text, tarr, scan_st, SMALL_ID_MIN, named_keys)
        for k, e in pack.items():
            if _is_text_candidate(k[0], e.msize):
                try:
                    found |= text_ids(fast_copy(k), k[0], tarr, scan_st, SMALL_ID_MIN, named_keys)
                except Exception:
                    scan_st['unreadable'] += 1
        if use_scripts:
            try:
                found |= member(_script_ids(view, cache_path), tarr)
            except Exception:
                checked['script_ids_unavailable'] += 1
        checked.update({'tuning_' + k: v for k, v in scan_st.items()})
        checked['tuning_ids'] = len(found)
        for t, arr in per_cat.items():
            for v in sorted(member(found, arr)):
                if v not in fast_cat[t]:
                    miss('tuning', '%s %016X' % (tname(t), v), 'named in tuning / SimData / a script')
        check_closure(found, 'tuning_closure')
        # asset keys the tuning names in full (icons ...): the full library has them -> fast mode too
        checked['tuning_keys'] = len(named_keys)
        for rk in _loaded_keys(view, pos, [k for k in named_keys if k not in pack and k not in kept_best]):
            miss('tuning_keys', key_text(rk), 'named in full in tuning fast mode loads')
        # kept packages the game reaches before the pack file: their copy of a pack key would win
        before = collections.defaultdict(dict)
        for k, (path, e) in pack_loc.items():
            kb = kept_best.get(k)
            if kb is None:
                continue
            name = os.path.basename(path)
            early = before[name].get(kb[1])
            if early is None:
                early = before[name][kb[1]] = loads_before(pkgs[kb[1]].rel, name)
            if not early:
                continue
            checked['order'] += 1
            try:
                same = fast_copy(k) == reader.read(kb[1], kb[2], kb[3], kb[5], kb[4])
            except Exception:
                same = False
            if not same:
                differ('order', key_text(k), 'kept %s loads before %s and would win over it' % (pkgs[kb[1]].rel, name))
    finally:
        reader.close()
        for f in pack_files.values():
            f.close()

    # winners: keys whose full-library copy is in a parked package and that fast mode needs
    for k, row in parked_best.items():
        kb = kept_best.get(k)
        if kb is not None and kb[0] < row[0]:
            continue                                     # the winner is kept: fast mode has it
        if k in pack:
            e = pack[k]
            checked['pack'] += 1
            if (e.fsize, e.msize, e.comp) != (row[3], row[4], row[5]):
                differ('pack', key_text(k), 'the pack copy is not the library\'s (%s): rebuild' % pkgs[row[1]].rel)
            continue
        if not (kb is not None or k[0] not in ASSET_TYPES or k in overrides):
            continue
        checked['winners'] += 1
        if kb is not None:
            differ('winners', key_text(k), 'fast mode would use a kept package\'s copy, not %s' % pkgs[row[1]].rel)
        else:
            miss('winners', key_text(k), 'only in parked %s' % pkgs[row[1]].rel)
    for k, e in pack.items():                            # pack keys whose winner is kept now: stale pack
        kb = kept_best.get(k)
        if kb is not None and (k not in parked_best or kb[0] < parked_best[k][0]):
            if (e.fsize, e.msize, e.comp) != (kb[3], kb[4], kb[5]):
                differ('pack', key_text(k), 'the pack overrides kept %s with an older copy: rebuild'
                       % pkgs[kb[1]].rel)
    n_missing = sum(v for k, v in checked.items() if k.startswith('missing_'))
    n_diff = sum(v for k, v in checked.items() if k.startswith('different_'))
    return {'ok': not n_missing and not n_diff, 'missing': missing, 'different': different,
            'installed_nowhere': dict(absent), 'checked': dict(checked)}


# ------------------------------------------------------------------------------------------ CLI
def _gb(n):
    return '%.2f GB' % (n / 1e9)


def main(argv=None):
    """CLI: python -m speedkit.fastmode park|plan|build [--really]|status|update [--really]|verify.

    Read-only unless --really. For real-library dry runs point --library/--refs-db/--companions-cache/
    --game-ids-db/--game-db at private copies."""
    import argparse
    import sys
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(errors='backslashreplace')
    ap = argparse.ArgumentParser(description='The FAST profile: what it parks, and the pack that keeps it working.')
    ap.add_argument('cmd', choices=['park', 'plan', 'build', 'status', 'update', 'verify'])
    ap.add_argument('--library', default=None, help='library.sqlite to read (never scanned here)')
    ap.add_argument('--refs-db', default=U.DEFAULT_REFS_DB)
    ap.add_argument('--game-ids-db', default=U.DEFAULT_GAME_DB)
    ap.add_argument('--game-db', default=None, help='game.sqlite of speedkit.game_index')
    ap.add_argument('--companions-cache', default=companions.DEFAULT_CACHE)
    ap.add_argument('--out', default=None, help='fastpack folder (default <Sims 4>\\SpeedKit\\fastpack)')
    ap.add_argument('--sims', default=None, help='build/update: Sims 4 folder for the journal (tests)')
    ap.add_argument('--workers', type=int, default=3)
    ap.add_argument('--backups', action='store_true')
    ap.add_argument('--list', action='store_true', help='park: list every package')
    ap.add_argument('--json', default=None, help='write the numbers to this file')
    ap.add_argument('--really', action='store_true', help='build/update: write (default is a dry run)')
    a = ap.parse_args(argv)
    from .library import Library
    if a.cmd == 'status':
        st = status(a.out or DEFAULT_OUT)
        print('fast pack: %s' % st['state'])
        for w in st['why']:
            print('  -', w)
        return st
    lib = Library(a.library) if a.library else Library()
    parked = park_set(lib, cache_path=a.companions_cache)
    s = parked.stats
    print('park: %d of %d loaded packages parked (%s, %d CAS parts); %d kept (%s, %d CAS parts)' % (
        s['parked'], s['loaded'], _gb(s['parked_bytes']), s['parked_casp'], s['kept'], _gb(s['kept_bytes']),
        s['kept_casp']))
    if a.cmd == 'park':
        if a.list:
            for key in parked:
                print('  PARK %-60s %s' % ('/'.join(key), parked.reasons[key]))
            for key in parked.kept:
                print('  keep %-60s %s' % ('/'.join(key), parked.keep_reasons[key]))
        return parked
    refs = U.scan_references(cache_db=a.refs_db, workers=a.workers, include_backups=a.backups)
    print('refs: %d sources, %d parsed; errors: %s' % (refs.stats['sources'], refs.stats['parsed'],
                                                       refs.stats['errors'] or 'none'))
    game = U.load_game_ids(cache_db=a.game_ids_db)
    kw = dict(game=game, cache_path=a.companions_cache, include_backups=a.backups)
    if a.game_db:
        kw['game_db'] = a.game_db
    if a.cmd == 'verify':
        v = verify(lib, refs, a.out, game=game, cache_path=a.companions_cache, game_db=a.game_db)
        print('verify: %s; installed nowhere: %s' % ('OK' if v['ok'] else 'PROBLEMS', v['installed_nowhere']))
        for m in v['missing'][:30] + v['different'][:30]:
            print('  ', m)
        return v
    if a.cmd == 'update':
        r = update_pack(lib, refs, a.out, parked, dry_run=not a.really, sims=a.sims, verbose=True, **kw)
        print('update: %s (%s)' % (r['action'], '; '.join(r['why'])))
        return r
    p = plan_pack(lib, refs, parked, verbose=True, **kw)
    sm = p.summary()
    print('pack: %d keys, %s from %d packages' % (sm['keys'], _gb(sm['bytes']), sm['source_packages']))
    for part, d in sm['parts'].items():
        print('  (%s) %7d keys %10s' % (part, d['keys'], _gb(d['bytes'])))
    c = sm['cas_parts']
    print('CAS parts (CASP index entries): full %d, fast %d (%.2f%%)' % (c['full'], c['fast'], c['fast_percent']))
    out = {'park': s, 'plan': p.stats, 'by_type': sm['by_type']}
    if a.cmd == 'build':
        res = build_pack(p, a.out, dry_run=not a.really, sims=a.sims, verbose=True)
        for r in res:
            print('%s %-70s %6d keys %s' % ('wrote' if a.really else 'would write', r['path'], r['keys'], _gb(r['bytes'])))
        out['layout'] = res
    if a.json:
        with open(a.json, 'w', encoding='utf-8') as f:
            json.dump(out, f, indent=1, default=str)
    return p


if __name__ == '__main__':
    main()
