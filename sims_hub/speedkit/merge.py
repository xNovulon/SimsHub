"""The script-safe auto-merger and the download Inbox.

Merging many loose .package files into a few bigger ones saves the game a little work per file at every
start (0.5-10 ms per file; research/research_results.json -> merging and its corrections) and puts the
catalog records (CAS parts, thumbnails, objects, SimData, tuning, strings) at the front of each merged
file. It must never change what the game loads. This module therefore only merges packages whose every
resource is either unique in the library or byte-for-byte (or decompressed) identical to every other copy,
so the merged file's place in the load order cannot matter.

    p = plan_merge(lib)                      # read-only: groups of loose packages to merge
    print(json.dumps(p.summary(), indent=1))
    apply_merge(p, lib)                      # dry run: what would be written
    apply_merge(p, lib, dry_run=False)       # real run: Journal kind 'merge', invariant check, auto-undo
    process_inbox(lib)                       # dry run of the Inbox; dry_run=False installs (Journal 'inbox')
    undo('20260924-101500-merge')            # journal.undo + keeps Mods_parked/_manifest.json consistent

Never merged (plan_merge excludes them and says why): .ts4script files; packages the companions
classifier calls core/addon/orphan/weak/broken (companions.never_merge); load-order sensitive names
(companions.load_order_sensitive: '!', '~', '_', 'zz', numbered prefixes, known lighting mods); S4S merges
(they hold a 0x7FB6AD8A manifest); unreadable or empty packages; packages with deleted-flag entries or one
key twice; packages any of whose keys conflict (different content, or a copy that cannot be read) with
another loaded package (speedkit.hashing); packages the game does not load (more than 5 folders deep, or
shadowed by the same path in Mods); SpeedKit's own files (the fast pack, used pack, earlier merges);
everything under a FitStudio folder; files the other chat's mods_switch.py keeps in its lean set (its KEEP
list: a merged file is not on it, so 'lean' would park them); packages in a folder that holds a .ts4script
(like dedup, those are treated as script companions); packages already at or above the target size; loose
packages in Mods while Mods_parked holds 'SpeedKit Merged/' parked as a whole folder (creating
Mods/SpeedKit Merged would stop mods_switch 'full' from restoring that folder).

Groups: by root (a group never spans Mods and Mods_parked), category and folder. Categories: CAS (CAS parts,
skin tones), BuildBuy (objects, walls, floors), Tuning (the classifier's 'tuning' kind: XML tuning with no
script link - these only merge with tuning from the SAME folder), Sliders (sliders, presets, sculpts) and
Other. CC groups are formed per top-level folder. Groups are filled in load order up to target_bytes
(1 GB); no merged file exceeds max_bytes (1.9e9, below EA's largest 1.98e9 and 2^31-1).

Output: '<root>/SpeedKit Merged/<Category>_NNN.package' in the root the sources are in. A merged file in
Mods_parked is ADDED to Mods_parked/_manifest.json (the other chat's mods_switch.py format, {"moved": [...]})
unless a folder entry already covers it, so 'full' restores it. Numbers are unique across both roots
(mods_switch never restores a file whose name is taken in Mods). Each merged file starts with an S4S
manifest (speedkit.manifest.build_flat) listing every source, so Sims 4 Studio can unmerge it; identical
resources held by several sources are written once and listed under each source (S4S does the same).

Journals: apply_merge uses kind 'merge' (put_new the merged file, quarantine the sources); process_inbox uses
kind 'inbox'. Changes to Mods_parked/_manifest.json are recorded in <journal>.merge.json next to the journal,
and undo() in this module reverses them together with the journal - undo 'merge' and 'inbox' journals with
merge.undo, not journal.undo, or the parking manifest keeps entries for files that are gone.
"""
import ast
import datetime
import json
import os
import re
import shutil
import sys
import tempfile
import time
import zipfile
import zlib
from collections import Counter, defaultdict, namedtuple

from .dbpf import Package, PackageWriter, DELETED, key_of
from .hashing import (DEFAULT_ROOTS, THREADS, HashCache, Copy, hash_copies, key_status, effective_map,
                      hash_package, data_digest, digest)
from .journal import Journal, undo as journal_undo, file_digest
from .library import SIMS, game_running, signed64, unsigned64
from .manifest import MANIFEST_TYPE, MANIFEST_KEY, build_flat, decode as manifest_decode, sanitize_name
from .manifest import payload as manifest_payload
from .dedup import index_problems, shadowed_paths, sims_folder, NAMEMAP, MIN_FREE
from . import companions

MERGED_DIR = 'SpeedKit Merged'
LOOSE_DIR = 'SpeedKit Loose'
TARGET_BYTES = 1_000_000_000
MAX_BYTES = 1_900_000_000            # below EA's largest package (1.98e9) and 2^31-1 (S4S can still re-merge)
HARD_LIMIT = (1 << 31) - 1
TMP_SUFFIX = '.speedkit-merge'       # a merged file while it is written ('+.writing') and verified
PARK_MANIFEST = '_manifest.json'     # the other chat's mods_switch.py parking manifest in Mods_parked
CATEGORIES = ('CAS', 'BuildBuy', 'Tuning', 'Sliders', 'Other')
NEW_CATEGORY = 'New'                 # the Inbox's merged files: SpeedKit Merged/New_NNN.package
NAME_RX = re.compile(r'^([A-Za-z]+)_(\d{3,})\.package$', re.I)
PARTIAL_SUFFIXES = ('.crdownload', '.part', '.partial', '.download', '.tmp', '.opdownload')
OTHER_ARCHIVES = ('.rar', '.7z', '.tar', '.gz', '.tgz', '.bz2', '.xz')
PARKED_NOTE = ' - put into the parked folder "%s" (it is parked whole; it loads after switching to full)'
INBOX_RESERVED = {'_done', '_staging'}
INBOX_IGNORED = {'desktop.ini', 'thumbs.db', '.ds_store'}
# The other chat's switch: what its 'lean' keeps in Mods. Merging one of those files would take it out of the lean
# (studio) set, because the merged file is not on the KEEP list. Read from its source (never executed); this copy
# (2026-09-24) is used when the file is missing or cannot be parsed.
MODS_SWITCH = os.path.join(os.path.expanduser('~'), 'Tools', 'sims4_fitstudio', 'mods_switch.py')
STUDIO_KEEP = ('Resource.cfg', 'desktop.ini', 'scripts/TURBODRIVER_WickedWhims_Scripts.ts4script',
               'scripts/TURBODRIVER_WickedWhims_Tuning.package', 'scripts/desktop.ini',
               'animation/WW_LAMABOY_Animation.package', 'animation/WW_LAMABOY_Animations.package',
               'animation/desktop.ini', 'FitStudio/')
# what zipfile can raise while extracting a member (bad CRC, Deflate64, encrypted, name Windows forbids, disk full)
ZIP_ERRORS = (OSError, EOFError, RuntimeError, NotImplementedError, ValueError, zipfile.BadZipFile,
              zipfile.LargeZipFile, zlib.error)

# ------------------------------------------------------------------------------------------ resource types
T_CASP, T_TONE, T_OBJD, T_COBJ = 0x034AEECB, 0x0354796A, 0xC0DB5AE7, 0x319E4F1D
T_CWAL, T_CFLR, T_SIMDATA, T_STBL = 0xD5F0F921, 0xB4F762C9, 0x545AC67A, 0x220557DA
T_SMOD, T_CPRE, T_SCUL, T_BGEO, T_DMAP, T_BOND = 0xC5F6763E, 0xEAA32ADD, 0x9D1AB874, 0x067CAA11, 0xDB43E069, 0x0355E0A6
THUMB_TYPES = {0x3C1AF1F2, 0x3C2A8647, 0x5B282D45, 0xCD9DE247}       # CAS / build-buy / body part / preset thumbnails
BUILDBUY_TYPES = {T_OBJD, T_COBJ, T_CWAL, T_CFLR}
SLIDER_TYPES = {T_SMOD, T_CPRE, T_SCUL, T_BGEO, T_DMAP, T_BOND}
BULK_TYPES = {0x015A1849, 0x3453CF95, 0x2BC04EDF, 0xBA856C78, 0x00B2D882, 0xB6C8B6A0, 0x01661233, 0x01D10F34,
              T_BGEO, T_DMAP, T_BOND, 0x6B20C4F3, 0xBC4A5044, 0x8EAF13DE, 0xAC16FBEC, 0xD382BF57, 0x01D0E75D}
# catalog records first (what the game reads at start-up), then strings, then meshes/textures/clips
_RANK = {T_CASP: 0, T_TONE: 2, T_SMOD: 2, T_CPRE: 2, T_SCUL: 2, T_OBJD: 3, T_COBJ: 4, T_CWAL: 4, T_CFLR: 4,
         T_SIMDATA: 5, T_STBL: 7}


def rank(t):
    """Where a resource of type t goes in a merged file: 0 CASP, 1 thumbnails, 2 TONE/slider/preset records,
    3 OBJD, 4 COBJ/CWAL/CFLR, 5 SimData, 6 XML tuning and other small records, 7 STBL, 8 meshes/textures/clips."""
    if t in _RANK:
        return _RANK[t]
    if t in THUMB_TYPES:
        return 1
    if t in BULK_TYPES:
        return 8
    return 6


def category_of(types, kind):
    """Merge category of a package from its resource types and its companions verdict kind."""
    if kind == 'tuning':
        return 'Tuning'
    if types & {T_CASP, T_TONE}:
        return 'CAS'
    if types & BUILDBUY_TYPES:
        return 'BuildBuy'
    if types & SLIDER_TYPES:
        return 'Sliders'
    return 'Other'


class MergeError(Exception):
    pass


class InvariantError(MergeError):
    """apply_merge / process_inbox changed what the game would load; the journal has been undone."""


# ------------------------------------------------------------------------------------------ small helpers
def _stem(rel):
    n = rel.replace('\\', '/').rsplit('/', 1)[-1]
    return n[:-len('.package')] if n.lower().endswith('.package') else os.path.splitext(n)[0]


def _parent(rel):
    return rel.rsplit('/', 1)[0] if '/' in rel else ''


def _top(rel):
    return rel.split('/', 1)[0] if '/' in rel else ''


def _changed(path, size, mtime):
    try:
        st = os.stat(path)
    except OSError:
        return 'missing'
    if st.st_size != size or abs(st.st_mtime - mtime) >= 1e-3:
        return 'changed since the library scan'
    return None


def _inside(path, base):
    path, base = os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.abspath(base))
    return path == base or path.startswith(base.rstrip('\\/') + os.sep)


def _free(path):
    p = os.path.abspath(path)
    while not os.path.exists(p) and os.path.dirname(p) != p:
        p = os.path.dirname(p)
    return shutil.disk_usage(p).free


def _drive(path):
    return os.path.splitdrive(os.path.abspath(path))[0].upper()


def is_speedkit_file(rel):
    """True for SpeedKit's own files (fast pack, used pack, merged/loose output, the monitor script)."""
    return any('speedkit' in part.lower() for part in rel.replace('\\', '/').split('/'))


def is_fitstudio(rel):
    return any(part.lower() == 'fitstudio' for part in rel.replace('\\', '/').split('/')[:-1])


def _write_json_atomic(path, data):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, path)


# ------------------------------------------------------------------------------------------ parking manifest
def read_park_manifest(parked):
    """Mods_parked/_manifest.json as {"moved": [...], ...}, None if there is none. Raises MergeError on a
    malformed file (SpeedKit then refuses rather than guess what the other tool meant)."""
    path = os.path.join(parked, PARK_MANIFEST)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding='utf-8') as f:
            m = json.load(f)
    except (OSError, ValueError) as e:
        raise MergeError('%s cannot be read (%s); fix or move it before merging parked mods' % (path, e))
    if not isinstance(m, dict) or not isinstance(m.get('moved'), list) or not all(isinstance(x, str) for x in m['moved']):
        raise MergeError('%s is not {"moved": [paths]}; fix or move it before merging parked mods' % path)
    return m


def park_covered(moved, rel):
    """True if the parking manifest lists rel itself or a folder ('dir/') that holds it (ignoring case)."""
    low = rel.replace('\\', '/').lower()
    for e in moved:
        el = e.replace('\\', '/').lower()
        if el == low or (el.endswith('/') and low.startswith(el)):
            return True
    return False


def park_manifest_add(parked, rels):
    """Add rels (relative to Mods, forward slashes) to Mods_parked/_manifest.json unless already covered.
    Read-modify-write with an atomic replace; entries of the other tool are kept. Returns the entries added."""
    m = read_park_manifest(parked)
    if m is None:
        m = {'moved': []}
    added = []
    for r in rels:
        if not park_covered(m['moved'] + added, r):
            added.append(r)
    if added:
        m['moved'].extend(added)
        os.makedirs(parked, exist_ok=True)
        _write_json_atomic(os.path.join(parked, PARK_MANIFEST), m)
    return added


def park_manifest_remove(parked, rels):
    """Remove exactly these entries (as SpeedKit added them). Returns the entries removed."""
    m = read_park_manifest(parked)
    if m is None:
        return []
    drop = set(rels)
    gone = [e for e in m['moved'] if e in drop]
    if gone:
        m['moved'] = [e for e in m['moved'] if e not in drop]
        _write_json_atomic(os.path.join(parked, PARK_MANIFEST), m)
    return gone


def _moved_or_none(parked):
    """The parking manifest's entries, [] if there is none, None if it cannot be read."""
    if not parked:
        return []
    try:
        return (read_park_manifest(parked) or {'moved': []})['moved']
    except MergeError:
        return None


def park_dir_block(mods, parked, rel, moved):
    """The parking-manifest folder entry ('dir/') that a NEW file at Mods/<rel> would stop mods_switch 'full'
    from restoring, or None. 'full' skips an entry whose name is taken in Mods, so creating Mods/<dir> while
    Mods_parked/<dir> is parked as a whole folder would leave that folder (and every mod in it) parked for good.
    Only entries that hold rel, whose folder exists in Mods_parked and not in Mods, count."""
    if not mods or not parked or not moved:
        return None
    low = rel.replace('\\', '/').lower()
    for e in moved:
        el = e.replace('\\', '/').lower()
        if el.endswith('/') and low.startswith(el):
            d = e.replace('\\', '/').rstrip('/').replace('/', os.sep)
            if os.path.isdir(os.path.join(parked, d)) and not os.path.exists(os.path.join(mods, d)):
                return e
    return None


def studio_keep(path=None):
    """mods_switch.py's KEEP list (paths relative to Mods, folders end with '/'): what its 'lean' leaves in Mods.
    Parsed from the file's source with ast (the other tool's code is never run); STUDIO_KEEP if that fails."""
    try:
        with open(path or MODS_SWITCH, encoding='utf-8') as f:
            tree = ast.parse(f.read())
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'KEEP' for t in node.targets):
                keep = ast.literal_eval(node.value)
                if isinstance(keep, (list, tuple)) and all(isinstance(k, str) for k in keep):
                    return list(keep)
    except (OSError, SyntaxError, ValueError, UnicodeDecodeError):
        pass
    return list(STUDIO_KEEP)


def studio_kept(rel, keep):
    """True if mods_switch's lean keeps rel (the file itself or a folder that holds it; ignoring case)."""
    low = rel.replace('\\', '/').lower()
    for k in keep:
        kl = k.replace('\\', '/').lower()
        if low == kl or (kl.endswith('/') and (low + '/').startswith(kl)):
            return True
    return False


def _record_path(journal_home, jid):
    return os.path.join(journal_home, 'journal', jid + '.merge.json')


def _save_record(journal_home, jid, rec):
    _write_json_atomic(_record_path(journal_home, jid), rec)


# ------------------------------------------------------------------------------------------ plan
Source = namedtuple('Source', 'id root rel path size mtime n')


class Group:
    """One merged file to write: its sources (all in one root), category, folder and output path."""

    def __init__(self, root, category, folder):
        self.root, self.category, self.folder = root, category, folder
        self.sources = []
        self.keys = set()          # every live key of the sources (what the invariant check compares)
        self.copies = 0            # resource copies in the sources
        self.est = 96 + 4 + 8      # estimated size of the merged file
        self.src_bytes = 0
        self.out_rel = None
        self.park_listed = None    # parked groups: True if Mods_parked/_manifest.json lists every source

    @property
    def dup_copies(self):
        """Resource copies that are written once because another source holds the identical resource."""
        return self.copies - len(self.keys)

    def to_dict(self):
        return {'out': '%s/%s' % (self.root, self.out_rel), 'category': self.category, 'folder': self.folder,
                'sources': ['%s/%s' % (s.root, s.rel) for s in self.sources], 'source_bytes': self.src_bytes,
                'estimated_bytes': self.est, 'resources': len(self.keys), 'identical_copies_written_once': self.dup_copies,
                'park_listed': self.park_listed}


class MergePlan:
    """The result of plan_merge()."""

    def __init__(self, roots, target_bytes, max_bytes):
        self.roots = tuple(roots)
        self.target_bytes, self.max_bytes = target_bytes, max_bytes
        self.groups = []
        self.excluded = {}          # pkg id -> reason
        self.alone = {}             # pkg id -> reason (mergeable, but nothing to merge it with)
        self.names = {}             # pkg id -> 'root/rel'
        self.sizes = {}             # pkg id -> bytes
        self.warnings = []
        self.index_problems = []
        self.ignore_namemap = False
        self.created = time.time()

    def lenient_types(self):
        """Types whose copies may differ between merged sources (tool metadata): NameMap with ignore_namemap."""
        return {NAMEMAP} if self.ignore_namemap else set()

    @property
    def check_keys(self):
        out = set()
        for g in self.groups:
            out |= g.keys
        return {k for k in out if k[0] not in self.lenient_types()}

    def summary(self):
        reasons = Counter(r.split(':')[0] for r in self.excluded.values())
        rbytes = Counter()
        for pid, r in self.excluded.items():
            rbytes[r.split(':')[0]] += self.sizes.get(pid, 0)
        return {
            'roots': list(self.roots), 'target_bytes': self.target_bytes, 'max_bytes': self.max_bytes,
            'ignore_namemap': self.ignore_namemap,
            'packages_seen': len(self.excluded) + len(self.alone) + sum(len(g.sources) for g in self.groups),
            'groups': len(self.groups), 'packages_merged': sum(len(g.sources) for g in self.groups),
            'source_bytes': sum(g.src_bytes for g in self.groups),
            'merged_files_estimated_bytes': sum(g.est for g in self.groups),
            'files_saved': sum(len(g.sources) - 1 for g in self.groups),
            'mergeable_but_alone': len(self.alone),
            'excluded': len(self.excluded),
            'excluded_by_reason': dict(reasons.most_common()),
            'excluded_bytes_by_reason': dict(rbytes.most_common()),
            'by_category': dict(Counter(g.category for g in self.groups)),
            'warnings': self.warnings, 'index_problems': len(self.index_problems),
        }

    def to_dict(self, top=50):
        return {'summary': self.summary(), 'groups': [g.to_dict() for g in self.groups],
                'alone': sorted(self.names[p] for p in self.alone)[:top],
                'excluded_examples': {r: sorted(self.names[p] for p, x in self.excluded.items() if x.split(':')[0] == r)[:8]
                                      for r in {x.split(':')[0] for x in self.excluded.values()}},
                'index_problems': self.index_problems[:top]}


def _taken_numbers(lib, roots):
    """{category lower: set of numbers} already used by '<Category>_NNN.package' in any root's SpeedKit Merged."""
    out = defaultdict(set)
    for r in roots:
        d = os.path.join(lib.roots[r], MERGED_DIR)
        if os.path.isdir(d):
            for n in os.listdir(d):
                m = NAME_RX.match(n.split(TMP_SUFFIX)[0])
                if m:
                    out[m.group(1).lower()].add(int(m.group(2)))
    for p in lib.packages():
        if p.rel.lower().startswith(MERGED_DIR.lower() + '/'):
            m = NAME_RX.match(p.rel.split('/')[-1])
            if m:
                out[m.group(1).lower()].add(int(m.group(2)))
    return out


def _next_number(taken, cat):
    used = taken[cat.lower()]
    n = max(used, default=0) + 1
    used.add(n)
    return n


def plan_merge(lib, roots=DEFAULT_ROOTS, target_bytes=TARGET_BYTES, max_bytes=MAX_BYTES, verdicts=None,
               cache_path=None, companions_cache=None, progress=None, threads=THREADS, min_group=2,
               protect_script_folders=True, ignore_namemap=False, keep=None):
    """Groups of loose packages to merge. Read-only (the hash and companions caches are written).

    lib: speedkit.library.Library with a current index (scan it first). roots: the roots laid over each other.
    verdicts: {pkg_id: companions.Verdict} (default: companions.classify(lib, roots, cache_path=companions_cache)).
    cache_path: the hash cache (default data/hash.sqlite). min_group: smallest number of packages worth merging.
    protect_script_folders: never merge packages that sit in a folder holding a .ts4script (default, like dedup).
    ignore_namemap: treat NameMap (0x0166038C) resources as tool metadata, like dedup's option of the same name:
    a differing NameMap copy then does not stop a package from merging (the merged file keeps the first source's
    copy and every source still lists the key), and NameMaps are left out of the after-merge check. S4S writes
    most NameMaps at key 0166038C:00000000:0000000000000000, so by default (NameMap = content, because whether
    the game reads CC NameMaps is unknown) nearly every package that has one counts as conflicting.
    keep: mods_switch.py's KEEP list (default: studio_keep()); files its 'lean' keeps in Mods are never merged.
    Returns a MergePlan."""
    roots = (roots,) if isinstance(roots, str) else tuple(roots)
    if not 0 < target_bytes <= max_bytes <= HARD_LIMIT:
        raise ValueError('need 0 < target_bytes <= max_bytes <= 2^31-1')
    keep = studio_keep() if keep is None else list(keep)
    P = MergePlan(roots, target_bytes, max_bytes)
    P.ignore_namemap = ignore_namemap
    ignored = P.lenient_types()
    pkgs = {p.id: p for p in lib.packages() if p.root in roots}
    P.names = {pid: '%s/%s' % (p.root, p.rel) for pid, p in pkgs.items()}
    P.sizes = {pid: p.size for pid, p in pkgs.items()}
    P.index_problems = index_problems(lib, roots)
    if P.index_problems:
        P.warnings.append('%d files changed since the library scan - rescan before applying' % len(P.index_problems))
    if 'Mods' in lib.roots and lib.resource_cfg('Mods') is not None and not lib.resource_cfg_is_default('Mods'):
        P.warnings.append('Mods/Resource.cfg is not the default one: merging is refused (load rules differ)')
    shadowed = set(shadowed_paths(lib, roots))
    positions = lib.order_positions(roots)
    if verdicts is None:
        kw = {'cache_path': companions_cache} if companions_cache else {}
        verdicts = companions.classify(lib, roots, **kw)
    script_dirs = {_parent(s.rel).lower() for s in lib.scripts() if s.root in roots}
    merged = {pid for (pid,) in lib.db.execute('select distinct pkg from res where t=?', (MANIFEST_TYPE,))}
    moved = None
    if 'Mods_parked' in roots and 'Mods_parked' in lib.roots:
        try:
            moved = (read_park_manifest(lib.roots['Mods_parked']) or {'moved': []})['moved']
        except MergeError as e:
            P.warnings.append(str(e))

    # 1. cheap checks
    cand = []
    for pid, p in sorted(pkgs.items(), key=lambda kv: positions.get(kv[0], 1 << 40)):
        v = verdicts.get(pid)
        why = None
        if p.rel.lower() in shadowed:
            why = 'shadowed: the same path exists in Mods and Mods_parked'
        elif pid not in positions:
            why = 'not loaded: more than 5 folders deep'
        elif p.err:
            why = 'unreadable: %s' % p.err
        elif is_speedkit_file(p.rel):
            why = 'speedkit: a SpeedKit file'
        elif is_fitstudio(p.rel):
            why = 'fitstudio: under a FitStudio folder'
        elif studio_kept(p.rel, keep):
            why = 'studio set: mods_switch.py keeps it in Mods in its lean set'
        elif companions.load_order_sensitive(p.rel):
            why = 'load-order name: its name or folder decides where it loads'
        elif pid in merged:
            why = 'already merged: holds an S4S manifest'
        elif v is None:
            why = 'unclassified: no companions verdict'
        elif companions.never_merge(v):
            why = 'script companion: %s%s' % (v.kind, ' of ' + v.script if v.script else '')
        elif v.kind == 'empty' or not p.n:
            why = 'empty: no resources'
        elif protect_script_folders and _parent(p.rel).lower() in script_dirs:
            why = 'next to a script: its folder holds a .ts4script'
        elif p.size >= target_bytes:
            why = 'already big: %d bytes' % p.size
        elif _changed(p.path, p.size, p.mtime):
            why = 'changed: %s' % _changed(p.path, p.size, p.mtime)
        elif p.root == 'Mods_parked' and moved is None:
            why = 'parking manifest: Mods_parked/_manifest.json cannot be read'
        if why:
            P.excluded[pid] = why
        else:
            cand.append(pid)

    # 2. index facts of the candidates
    info = {}
    for pid in list(cand):
        rows = lib.entries(pid)            # (t, g, i signed, off, fsize, msize, comp)
        keys = [(t, g, unsigned64(i)) for t, g, i, *_ in rows]
        why = None
        if any(r[6] == DELETED for r in rows):
            why = 'deleted entries: holds deleted-flag entries'
        elif len(set(keys)) != len(keys):
            why = 'key twice: holds one resource key twice'
        elif any(r[0] == MANIFEST_TYPE for r in rows):
            why = 'already merged: holds an S4S manifest'
        if why:
            P.excluded[pid] = why
            cand.remove(pid)
            continue
        info[pid] = (keys, [r[4] for r in rows], {r[0] for r in rows})

    # 3. content conflicts with any other loaded package
    if cand:
        dups = hash_copies(lib, roots, progress, cache_path, threads)
        conflict, unread = Counter(), Counter()
        for key, cs in dups.items():
            if key[0] == MANIFEST_TYPE or key[0] in ignored:
                continue
            st = key_status(cs)
            if st == 'conflict':
                for c in cs:
                    conflict[c.pkg] += 1
            elif st == 'undecidable':
                for c in cs:
                    unread[c.pkg] += 1
        for pid in list(cand):
            if conflict[pid]:
                P.excluded[pid] = 'conflict: %d of its resources differ from another package\'s copy' % conflict[pid]
            elif unread[pid]:
                P.excluded[pid] = 'undecidable: %d of its resources have a copy that cannot be read' % unread[pid]
            else:
                continue
            cand.remove(pid)

    # 4. buckets (root, category, folder) in load order, filled up to target_bytes
    buckets = defaultdict(list)
    for pid in cand:
        p = pkgs[pid]
        cat = category_of(info[pid][2], verdicts[pid].kind)
        folder = _parent(p.rel) if cat == 'Tuning' else _top(p.rel)
        listed = park_covered(moved, p.rel) if p.root == 'Mods_parked' else None
        buckets[(p.root, cat, folder.lower(), listed)].append(pid)
    taken = _taken_numbers(lib, lib.roots)
    # a merged file in Mods must not create Mods/SpeedKit Merged while that folder is parked whole (mods_switch
    # 'full' would then never restore the parked one)
    block = park_dir_block(lib.roots.get('Mods'), lib.roots.get('Mods_parked'), MERGED_DIR + '/x.package',
                           moved if moved is not None else _moved_or_none(lib.roots.get('Mods_parked')))
    if block and any(k[0] == 'Mods' for k in buckets):
        P.warnings.append('Mods_parked holds the parked folder "%s": loose packages in Mods are not merged until '
                          'it is restored (a new Mods/%s would stop mods_switch full from restoring it)' % (block, MERGED_DIR))
    for (root, cat, _, listed), pids in sorted(buckets.items(), key=lambda kv: (roots.index(kv[0][0]), CATEGORIES.index(kv[0][1]),
                                                                                 kv[0][2], str(kv[0][3]))):
        if root == 'Mods' and block:
            for pid in pids:
                P.excluded[pid] = 'parked folder: Mods_parked holds "%s" as a whole folder' % block
            continue
        folder = _parent(pkgs[pids[0]].rel) if cat == 'Tuning' else _top(pkgs[pids[0]].rel)
        bins = []
        g = None
        for pid in pids:
            p = pkgs[pid]
            keys, sizes, _ = info[pid]
            if g is not None:
                new = [(k, s) for k, s in zip(keys, sizes) if k not in g.keys]
                add = sum(s for _, s in new) + 32 * len(new) + 24 + len(_stem(p.rel).encode()) + 16 * len(keys)
                if g.est + add > target_bytes:
                    g = None
            if g is None:
                g = Group(root, cat, folder)
                g.park_listed = listed
                bins.append(g)
            new = [(k, s) for k, s in zip(keys, sizes) if k not in g.keys]
            g.est += sum(s for _, s in new) + 32 * len(new) + 24 + len(_stem(p.rel).encode()) + 16 * len(keys)
            g.keys.update(keys)
            g.copies += len(keys)
            g.src_bytes += p.size
            g.sources.append(Source(pid, p.root, p.rel, p.path, p.size, p.mtime, p.n))
        for g in bins:
            if len(g.sources) < min_group:
                for s in g.sources:
                    P.alone[s.id] = 'alone: nothing else of its kind in %s/%s' % (root, folder or '(root)')
                continue
            if root == 'Mods_parked' and listed is False and moved and park_covered(moved, MERGED_DIR + '/x.package'):
                # 'full' never restores these sources, but it would restore a merged file in a listed folder
                for s in g.sources:
                    P.excluded[s.id] = ('parked folder: its sources are not in the parking manifest but %s/ is'
                                        % MERGED_DIR)
                continue
            g.out_rel = '%s/%s_%03d.package' % (MERGED_DIR, cat, _next_number(taken, cat))
            P.groups.append(g)
    return P


# ------------------------------------------------------------------------------------------ writing
class Part:
    """One input of a merged file.

    path/size/mtime: the package (it must still have this size and mtime). name: the S4S manifest source
    name for it; the manifest then lists every key taken from it, in index order. manifest_sources: instead of
    name, the exact [(name, [keys])] to list (used when a merged New_NNN file is rewritten with more CC).
    take: the keys to copy (None: every resource except an S4S manifest)."""

    def __init__(self, path, size, mtime, name=None, manifest_sources=None, take=None):
        self.path, self.size, self.mtime = path, size, mtime
        self.name = name
        self.manifest_sources = manifest_sources
        self.take = take


def _layout(parts):
    """Read the parts' indexes. Returns (items, dups, sources): items = [(rank, part, order, key, entry)] in
    write order (catalog first, then part order, then index order); dups = [(key, (part, entry), (part, entry))]
    for keys an earlier part holds as well (written once, must be identical); sources = the manifest's
    [(name, [keys])]."""
    items, dups, seen, sources = [], [], {}, []
    for pi, part in enumerate(parts):
        why = _changed(part.path, part.size, part.mtime)
        if why:
            raise MergeError('%s %s' % (part.path, why))
        with Package(part.path) as p:
            entries = p.entries
        taken = []
        for n, e in enumerate(entries):
            k = key_of(e)
            if e.t == MANIFEST_TYPE and part.take is None:
                continue
            if part.take is not None and k not in part.take:
                continue
            if e.comp == DELETED:
                raise MergeError('%s holds a deleted-flag entry %08X:%08X:%016X' % ((part.path,) + k))
            taken.append(k)
            if k in seen:
                if seen[k][0] == pi:
                    raise MergeError('%s holds %08X:%08X:%016X twice' % ((part.path,) + k))
                dups.append((k, seen[k], (pi, e)))
                continue
            seen[k] = (pi, e)
            items.append((rank(e.t), pi, n, k, e))
        if part.take is not None and set(taken) != set(part.take):
            raise MergeError('%s no longer holds every resource the plan expects' % part.path)
        if part.manifest_sources is not None:
            listed = {tuple(k) for _, keys in part.manifest_sources for k in keys}
            if listed != set(taken):
                raise MergeError('the S4S manifest of %s does not list exactly its resources' % part.path)
            sources.extend(part.manifest_sources)
        else:
            sources.append((part.name or _stem(part.path), taken))
    items.sort(key=lambda x: x[:3])
    return items, dups, sources


class _Reader:
    """Keeps one source package open at a time (a merged file may have thousands of sources)."""

    def __init__(self, parts):
        self.parts, self.cur, self.pkg = parts, None, None

    def raw(self, pi, e):
        if pi != self.cur:
            self.close()
            self.pkg = Package(self.parts[pi].path)
            self.cur = pi
        return self.pkg.raw(e)

    def close(self):
        if self.pkg is not None:
            self.pkg.close()
        self.pkg = self.cur = None


def write_merged(parts, out_path, max_bytes=MAX_BYTES, cache=None, final=None, lenient_types=()):
    """Write the merged package to out_path + TMP_SUFFIX (via PackageWriter's '.writing'), then re-read it and
    verify: the S4S manifest first and readable, every resource bit-exact (bytes and index fields) against its
    source, every copy written once identical to the one written. Returns (tmp_path, stats). Raises MergeError
    (temp files removed) on any problem. With a HashCache and final=(root, rel, ...) the raw hashes of the new
    file are cached under the file's final name so the after-check need not read it again. lenient_types: types
    (NameMap with ignore_namemap) whose later copies may differ; the first part's copy is written."""
    tmp = out_path + TMP_SUFFIX
    for leftover in (tmp, tmp + '.writing'):
        if os.path.exists(leftover):
            raise MergeError('a temporary file from an earlier run is in the way: %s' % leftover)
    items, dups, sources = _layout(parts)
    listed = {tuple(k) for _, keys in sources for k in keys}
    if listed != {k for _, _, _, k, _ in items}:
        raise MergeError('the manifest would not list exactly the resources written (%d listed, %d written)'
                         % (len(listed), len(items)))
    man = build_flat(sources)
    est = 96 + len(man) + sum(e.fsize for *_, e in items) + 32 * (len(items) + 1) + 4
    if est > max_bytes:
        raise MergeError('%s would be %d bytes, over the %d limit' % (out_path, est, max_bytes))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    rd = _Reader(parts)
    try:
        with PackageWriter(tmp) as w:
            w.add(MANIFEST_KEY, man)
            for _, pi, _, k, e in items:
                w.add_raw(e, rd.raw(pi, e))
    except BaseException:
        rd.close()
        if os.path.exists(tmp + '.writing'):
            os.remove(tmp + '.writing')
        raise
    try:
        stats = _verify_merged(parts, tmp, man, items, dups, rd, max_bytes, cache, final, set(lenient_types))
    except BaseException:
        rd.close()
        os.remove(tmp)
        raise
    rd.close()
    for part in parts:                                   # nothing changed under us while we read
        why = _changed(part.path, part.size, part.mtime)
        if why:
            os.remove(tmp)
            raise MergeError('%s %s while it was merged' % (part.path, why))
    return tmp, stats


def _verify_merged(parts, tmp, man, items, dups, rd, max_bytes, cache, final, lenient):
    st = os.stat(tmp)
    if st.st_size > max_bytes:
        raise MergeError('%s is %d bytes, over the %d limit' % (tmp, st.st_size, max_bytes))
    rows = []
    nbytes = 0
    with Package(tmp) as new:
        es = new.entries
        if len(es) != len(items) + 1:
            raise MergeError('merged file has %d resources, expected %d' % (len(es), len(items) + 1))
        if key_of(es[0]) != MANIFEST_KEY or manifest_payload(new.raw(es[0]), es[0].comp, es[0].msize) != man:
            raise MergeError('the S4S manifest of the merged file does not read back')
        for (_, pi, _, k, e), b in zip(items, es[1:]):
            if key_of(b) != k:
                raise MergeError('resource order differs at %08X:%08X:%016X' % k)
            if (e.fsize, e.msize, e.comp, e.committed) != (b.fsize, b.msize, b.comp, b.committed):
                raise MergeError('index entry of %08X:%08X:%016X changed' % k)
            rb = new.raw(b)
            if rd.raw(pi, e) != rb:
                raise MergeError('bytes of %08X:%08X:%016X differ from %s' % (k + (parts[pi].path,)))
            nbytes += len(rb)
            if cache is not None and final is not None:
                raw = digest(rb)
                rows.append((final[0], final[1], st.st_size, st.st_mtime, b.t, b.g, signed64(b.i), b.off, b.comp,
                             raw, cache.data_of(raw, b.comp), None))
    for k, (pa, ea), (pb, eb) in dups:
        if k[0] in lenient:
            continue
        ra, rb = rd.raw(pa, ea), rd.raw(pb, eb)
        if ra == rb and ea.comp == eb.comp:
            continue
        try:
            same = data_digest(ra, ea.comp, ea.msize) == data_digest(rb, eb.comp, eb.msize)
        except Exception as ex:
            raise MergeError('cannot compare the two copies of %08X:%08X:%016X: %s' % (k + (ex,)))
        if not same:
            raise MergeError('%s and %s hold different %08X:%08X:%016X' % ((parts[pa].path, parts[pb].path) + k))
    if cache is not None and rows:
        cache.store(rows)
    return {'resources': len(items), 'identical_copies_written_once': len(dups), 'bytes_verified': nbytes,
            'size': st.st_size}


# ------------------------------------------------------------------------------------------ apply
def _scopes(roots):
    roots = tuple(roots)
    return [roots] + ([('Mods',)] if 'Mods' in roots and len(roots) > 1 else [])


def _effective(lib, roots, keys, cache_path, progress, threads):
    keys = sorted(keys)
    return {scope: effective_map(lib, scope, keys, cache_path, progress, threads) for scope in _scopes(roots)}


def _diff(before, after, limit=50):
    out = []
    for scope, b in before.items():
        a = after[scope]
        for k, v in b.items():
            if a.get(k) != v:
                out.append(('+'.join(scope), '%08X:%08X:%016X' % k, v, a.get(k)))
                if len(out) >= limit:
                    return out
    return out


def _homes(lib, roots, sims, journal_home):
    sims = sims or sims_folder(lib, roots)
    journal_home = journal_home or (os.path.join(sims, 'SpeedKit') if sims else None)
    if journal_home and any(_inside(journal_home, b) or _inside(b, journal_home) for b in lib.roots.values()):
        raise MergeError('the journal folder %s must not be inside (or hold) a mod folder' % journal_home)
    return sims, journal_home


def _roll_back(jid, journal_home, check_game, lib, parked):
    """Undo a journal after a failure (files and parking manifest). Returns a sentence (never raises)."""
    try:
        undo(jid, home=journal_home, check_game=check_game)
        note = 'journal %s was undone' % jid
    except Exception as e:
        note = ('journal %s could NOT be undone (%s); undo it later with: python -m speedkit.merge undo %s'
                % (jid, e, jid))
    try:
        lib.scan()
    except Exception:
        pass
    return note


def apply_merge(plan, lib, dry_run=True, quarantine_home=None, journal_home=None, sims=None, check_game=True,
                cache_path=None, progress=None, threads=THREADS, min_free=MIN_FREE):
    """Carry out a merge plan. Dry run by default (returns what would be written; changes nothing).

    Real run: refuses while the game runs, if the library changed since the scan, if a package is in both roots,
    if Mods/Resource.cfg is not the default, or if the plan is stale. For each group: write the merged file next
    to its final place as '<name>.package.speedkit-merge', verify it bit-exact, then Journal kind 'merge':
    put_new the merged file, add it to Mods_parked/_manifest.json when it is parked, quarantine the sources.
    Afterwards it rescans lib and checks that the content the game uses for every key of every source is
    unchanged (all roots laid over each other, and Mods alone); on a mismatch, or any failure, it undoes
    everything and raises. quarantine_home may be on another drive (e.g. E:) to keep C: free."""
    t0 = time.time()
    sims, journal_home = _homes(lib, plan.roots, sims, journal_home)
    groups = [g for g in plan.groups]
    res = {'dry_run': dry_run, 'journal': None, 'journal_home': journal_home, 'written': [], 'quarantined': [],
           'park_manifest_added': [], 'groups': len(groups),
           'new_bytes': sum(g.est for g in groups), 'source_bytes': sum(g.src_bytes for g in groups)}
    if dry_run:
        res['would_write'] = [g.to_dict() for g in groups]
        res['stale_sources'] = [s.rel for g in groups for s in g.sources if _changed(s.path, s.size, s.mtime)]
        res['warnings'] = list(plan.warnings)
        return res
    if not groups:
        return res
    if not sims:
        raise MergeError('the library roots have no common parent folder: pass sims=')
    if check_game and game_running():
        raise MergeError('The Sims 4 is running - close it first.')
    if 'Mods' in lib.roots and lib.resource_cfg('Mods') is not None and not lib.resource_cfg_is_default('Mods'):
        raise MergeError('Mods/Resource.cfg is not the default one; merging could change what loads')
    problems = index_problems(lib, plan.roots)
    if problems:
        raise MergeError('the library changed since it was scanned (%s) - rescan and plan again' % problems[:3])
    shadowed = shadowed_paths(lib, plan.roots)
    if shadowed:
        raise MergeError('%d packages exist in both Mods and Mods_parked (e.g. %s)' % (len(shadowed), shadowed[0]))
    current = {(p.root, p.rel): p for p in lib.packages()}
    parked = lib.roots.get('Mods_parked')
    for g in groups:
        if len({s.root for s in g.sources}) != 1 or g.sources[0].root != g.root:
            raise MergeError('a group spans Mods and Mods_parked: %s' % g.out_rel)
        for s in g.sources:
            p = current.get((s.root, s.rel))
            if p is None or p.size != s.size or abs(p.mtime - s.mtime) >= 1e-3 or not _inside(s.path, sims):
                raise MergeError('%s/%s changed since the plan was made - plan again' % (s.root, s.rel))
        for r in lib.roots:
            if os.path.exists(os.path.join(lib.roots[r], g.out_rel.replace('/', os.sep))):
                raise MergeError('%s/%s already exists - plan again' % (r, g.out_rel))
    if any(g.root == 'Mods_parked' for g in groups):
        man = read_park_manifest(parked) or {'moved': []}    # refuses a malformed manifest before changing anything
        for g in groups:
            if g.root == 'Mods_parked' and (any(park_covered(man['moved'], s.rel) != g.park_listed for s in g.sources)
                                            or (not g.park_listed and park_covered(man['moved'], g.out_rel))):
                raise MergeError('Mods_parked/_manifest.json changed since the plan was made - plan again')
    for g in groups:
        block = g.root == 'Mods' and park_dir_block(lib.roots.get('Mods'), parked, g.out_rel, _moved_or_none(parked))
        if block:
            raise MergeError('Mods_parked holds the parked folder "%s"; writing Mods/%s would stop mods_switch full '
                             'from restoring it - switch to full, then plan again' % (block, g.out_rel))
    need = sum(g.est for g in groups)
    for r in {g.root for g in groups}:
        if _free(lib.roots[r]) - need < min_free:
            raise MergeError('not enough free space on %s for %.2f GB of merged files' % (_drive(lib.roots[r]), need / 1e9))
    if quarantine_home and _drive(quarantine_home) != _drive(lib.roots[groups[0].root]):
        qneed = sum(g.src_bytes for g in groups)
        if _free(quarantine_home) - qneed < min_free:
            raise MergeError('not enough free space in %s for %.2f GB of originals' % (quarantine_home, qneed / 1e9))
    keys = plan.check_keys
    before = _effective(lib, plan.roots, keys, cache_path, progress, threads)
    bad = [(s, k, v) for s, m in before.items() for k, v in m.items() if v and v.startswith('error:')]
    if bad:
        raise MergeError('cannot read %d resources the check depends on, e.g. %r - nothing was changed' % (len(bad), bad[:2]))

    j = Journal('merge', '%d merged files from %d packages' % (len(groups), sum(len(g.sources) for g in groups)),
                home=journal_home, sims=sims, check_game=check_game, quarantine_home=quarantine_home)
    res['journal'] = j.id
    rec = {'kind': 'merge', 'journal': j.id, 'parked_root': parked, 'park_manifest_added': [],
           'quarantined_parked_sources': [], 'groups': [g.to_dict() for g in groups]}
    _save_record(journal_home, j.id, rec)
    cache = HashCache(cache_path)
    tmp = None
    try:
        for n, g in enumerate(groups):
            if progress:
                progress('merge', n, len(groups), g.out_rel)
            final = os.path.join(lib.roots[g.root], g.out_rel.replace('/', os.sep))
            parts = [Part(s.path, s.size, s.mtime, name=_stem(s.rel)) for s in g.sources]
            tmp, st = write_merged(parts, final, plan.max_bytes, cache, (g.root, g.out_rel), plan.lenient_types())
            j.put_new(tmp, final)
            tmp = None
            res['written'].append('%s/%s' % (g.root, g.out_rel))
            if g.root == 'Mods_parked' and g.park_listed:     # 'full' restores the merged file like its sources
                added = park_manifest_add(parked, [g.out_rel])
                rec['park_manifest_added'] += added
                res['park_manifest_added'] += added
                _save_record(journal_home, j.id, rec)
            man = read_park_manifest(parked) if (g.root == 'Mods_parked') else None
            for s in g.sources:
                if man is not None and park_covered(man['moved'], s.rel):
                    rec['quarantined_parked_sources'].append(s.rel)
                j.quarantine(s.path)
                res['quarantined'].append('%s/%s' % (s.root, s.rel))
            _save_record(journal_home, j.id, rec)
        j.close('committed')
    except BaseException as e:
        cache.close()
        if tmp and os.path.exists(tmp):
            os.remove(tmp)
        j.close('failed: %s' % e)
        note = _roll_back(j.id, journal_home, check_game, lib, parked)
        if not isinstance(e, Exception):
            raise
        raise MergeError('%s; %s' % (e, note)) from e
    cache.close()
    try:
        lib.scan()
        after = _effective(lib, plan.roots, keys, cache_path, progress, threads)
        changed = _diff(before, after)
    except BaseException as e:
        note = _roll_back(j.id, journal_home, check_game, lib, parked)
        if not isinstance(e, Exception):
            raise
        raise MergeError('the check after the merge failed (%s); %s' % (e, note)) from e
    res['invariant'] = {'keys_compared': len(keys), 'scopes': ['+'.join(s) for s in before], 'changed': changed}
    if changed:
        note = _roll_back(j.id, journal_home, check_game, lib, parked)
        raise InvariantError('the game would load different content after merging (%d keys, e.g. %r); %s'
                             % (len(changed), changed[:3], note))
    res['seconds'] = round(time.time() - t0, 1)
    return res


def _package_keys(lib, pid):
    return [(t, g, unsigned64(i)) for t, g, i, *_ in lib.entries(pid)]


# ------------------------------------------------------------------------------------------ undo
def undo(journal_id, home=None, check_game=True, dry_run=False):
    """Undo a 'merge' or 'inbox' journal: journal.undo() plus the Mods_parked/_manifest.json entries.

    Entries SpeedKit added for files that the undo takes away are removed again; parked sources that come back
    from quarantine are listed again if the other tool dropped their entry meanwhile. Refuses (before changing
    anything) if a profile switch moved a merged file between Mods and Mods_parked since, or if restoring a file
    into Mods would recreate a folder that is parked whole (mods_switch 'full' could then no longer restore it):
    switch back first. If the files were put back but the parking manifest could not be fixed (e.g. the other
    tool had broken it), running undo again only fixes the manifest."""
    home = home or os.path.join(SIMS, 'SpeedKit')
    rec = None
    rp = _record_path(home, journal_id)
    if os.path.exists(rp):
        with open(rp, encoding='utf-8') as f:
            rec = json.load(f)
    jp = os.path.join(home, 'journal', journal_id + '.json')
    with open(jp, encoding='utf-8') as f:
        j = json.load(f)
    sims = j.get('sims') or SIMS
    if j.get('state') == 'undone' and rec is not None and not rec.get('undone'):
        if dry_run:
            return [('parking manifest: repair', journal_id)]
        actions = []                          # the files are back already; only the manifest is left
    else:
        mods = os.path.join(sims, 'Mods')
        parked = (rec or {}).get('parked_root') or os.path.join(sims, 'Mods_parked')
        moved = _moved_or_none(parked) if os.path.isdir(parked) else []
        for s in j['steps']:
            if s.get('undone'):
                continue
            if s['op'] == 'put_new' and not os.path.exists(s['path']):
                rel = os.path.relpath(s['path'], sims)
                parts = rel.split(os.sep, 1)
                if len(parts) == 2 and parts[0] in ('Mods', 'Mods_parked'):
                    other = os.path.join(sims, 'Mods_parked' if parts[0] == 'Mods' else 'Mods', parts[1])
                    if os.path.exists(other):
                        raise MergeError('%s was moved to %s by a profile switch since; switch back first, then undo'
                                         % (s['path'], other))
            elif s['op'] == 'quarantine' and _inside(s['path'], mods) and (
                    s.get('done') or (os.path.exists(s['q']) and not os.path.exists(s['path']))):
                rel = os.path.relpath(s['path'], mods).replace(os.sep, '/')
                block = park_dir_block(mods, parked, rel, moved)
                if block:
                    raise MergeError('%s would be restored into Mods/%s, which a profile switch parked as a whole '
                                     'folder since; switch back first, then undo' % (s['path'], block))
        actions = journal_undo(journal_id, home=home, check_game=check_game, dry_run=dry_run)
        if dry_run or rec is None:
            return actions
    parked = rec.get('parked_root')
    if parked:
        gone = [r for r in rec.get('park_manifest_added', [])
                if not os.path.exists(os.path.join(parked, r.replace('/', os.sep)))]
        if gone:
            park_manifest_remove(parked, gone)
            actions.append(('parking manifest: removed', ', '.join(gone)))
        back = [r for r in rec.get('quarantined_parked_sources', [])
                if os.path.exists(os.path.join(parked, r.replace('/', os.sep)))]
        if back:
            added = park_manifest_add(parked, back)
            if added:
                actions.append(('parking manifest: listed again', ', '.join(added)))
    rec['undone'] = True
    _save_record(home, journal_id, rec)
    return actions


# ------------------------------------------------------------------------------------------ Inbox
def inbox_path(lib=None, sims=None):
    """SIMS/SpeedKit/Inbox of the Sims 4 folder that holds lib's roots (the real one by default)."""
    if sims is None and lib is not None:
        sims = sims_folder(lib, tuple(r for r in ('Mods', 'Mods_parked') if r in lib.roots))
    return os.path.join(sims or SIMS, 'SpeedKit', 'Inbox')


def ensure_inbox(lib=None, sims=None):
    """Create the Inbox (and _done) if missing; returns its path. Only SpeedKit's own folder is touched."""
    p = inbox_path(lib, sims)
    os.makedirs(os.path.join(p, '_done'), exist_ok=True)
    return p


class InFile:
    """One .package / .ts4script of a dropped download."""

    def __init__(self, name, path, item):
        self.name, self.path, self.item = name, path, item
        self.script = name.lower().endswith('.ts4script')
        self.size = os.path.getsize(path)
        self.action = None        # update | install | merge | loose | duplicate
        self.dest = None          # (root, rel)
        self.replaces = None      # (root, rel) of the installed file this one replaces
        self.why = ''
        self.entries = []
        self.content = {}         # key -> content id (hex data hash, or 'raw:..' if it cannot be decoded)
        self.tuning = False
        self.odd = ''             # why it cannot go into a merge (S4S merge, deleted entries, key twice)
        self.new_keys = set()
        self.identical = 0
        self.conflicts = 0
        self.park_list = False    # a new file in Mods_parked: add it to Mods_parked/_manifest.json

    def to_dict(self):
        d = {'file': self.name, 'action': self.action, 'why': self.why}
        if self.dest:
            d['to'] = '%s/%s' % self.dest
        if self.replaces:
            d['replaces'] = '%s/%s' % self.replaces
        if self.park_list and self.dest and self.dest[0] == 'Mods_parked' and self.dest != self.replaces:
            d['added_to_parking_manifest'] = True
        if not self.script:
            d.update({'new_resources': len(self.new_keys), 'already_installed_resources': self.identical,
                      'conflicting_resources': self.conflicts})
        return d


class InItem:
    """One thing dropped into the Inbox: a .zip, a folder, a .package or a .ts4script."""

    def __init__(self, path):
        self.path = path
        self.name = os.path.basename(path)
        base = self.name if os.path.isdir(path) else os.path.splitext(self.name)[0]
        self.download = sanitize_name(base) or 'Download'
        self.extra = []           # loose .package files dropped next to a loose .ts4script of the same name
        self.files = []
        self.other = []           # other files of the download (readme, .cfg...): not installed, kept in _done
        self.status = 'pending'   # pending | refused | skipped | done
        self.why = ''

    def to_dict(self):
        d = {'item': self.name, 'status': self.status, 'why': self.why, 'files': [f.to_dict() for f in self.files]}
        if self.extra:
            d['with'] = [os.path.basename(p) for p in self.extra]
        if self.other:
            d['not_installed'] = self.other[:20]
        return d


def _script_base(name):
    stem = os.path.splitext(name)[0].lower()
    for suffix in ('_scripts', '_script', ' scripts', ' script', '-scripts', '-script'):
        if stem.endswith(suffix):
            return stem[:-len(suffix)]
    return stem


def _list_inbox(inbox):
    """The dropped items. A loose .package whose name starts with the name of a loose .ts4script (without a
    '_Scripts' suffix) belongs to that script: e.g. CoolMod_Scripts.ts4script + CoolMod_Tuning.package."""
    items = []
    for n in sorted(os.listdir(inbox), key=str.lower):
        if n in INBOX_RESERVED or n.lower() in INBOX_IGNORED:
            continue
        items.append(InItem(os.path.join(inbox, n)))
    scripts = [it for it in items if it.name.lower().endswith('.ts4script') and os.path.isfile(it.path)
               and len(_script_base(it.name)) >= 4]
    out = []
    for it in items:
        if it.name.lower().endswith('.package') and os.path.isfile(it.path):
            stem = it.name[:-len('.package')].lower()
            owner = next((s for s in sorted(scripts, key=lambda s: -len(_script_base(s.name)))
                          if stem.startswith(_script_base(s.name))), None)
            if owner is not None:
                owner.extra.append(it.path)
                continue
        out.append(it)
    return out


def _safe_member(name):
    p = name.replace('\\', '/')
    return not (p.startswith('/') or ':' in p or any(x == '..' for x in p.split('/')))


def _expand(item, staging):
    """Fill item.files (readable paths; zip members are extracted into staging). Sets item.status on refusal."""
    low = item.name.lower()
    if low.endswith(PARTIAL_SUFFIXES):
        item.status, item.why = 'skipped', 'still downloading'
        return
    if os.path.isdir(item.path):
        found = []
        for dp, dn, fn in os.walk(item.path):
            for n in fn:
                if n.lower().endswith(('.zip',) + OTHER_ARCHIVES):
                    item.status, item.why = 'refused', 'holds an archive (%s): extract it first' % n
                    return
                if n.lower().endswith(('.package', '.ts4script')):
                    found.append((n, os.path.join(dp, n)))
                elif n.lower() not in INBOX_IGNORED:
                    item.other.append(os.path.relpath(os.path.join(dp, n), item.path).replace(os.sep, '/'))
    elif low.endswith('.zip'):
        try:
            z = zipfile.ZipFile(item.path)
        except ZIP_ERRORS as e:
            item.status, item.why = 'refused', 'not a readable zip (%s)' % e
            return
        with z:
            members = [m for m in z.infolist() if not m.is_dir()]
            for m in members:
                if not _safe_member(m.filename):
                    item.status, item.why = 'refused', 'unsafe path inside the zip: %s' % m.filename
                    return
                if m.filename.lower().endswith(('.zip',) + OTHER_ARCHIVES):
                    item.status, item.why = 'refused', 'holds another archive (%s): extract it first' % m.filename
                    return
            mods = [m for m in members if m.filename.lower().endswith(('.package', '.ts4script'))]
            item.other = [m.filename for m in members if m not in mods
                          and m.filename.replace('\\', '/').rsplit('/', 1)[-1].lower() not in INBOX_IGNORED]
            need = sum(m.file_size for m in mods)
            if need and _free(staging) - need < (1 << 30):
                item.status, item.why = 'refused', 'not enough free space to extract %.2f GB' % (need / 1e9)
                return
            dest = tempfile.mkdtemp(prefix='zip-', dir=staging)
            found = []
            for n, m in enumerate(mods):
                target = os.path.join(dest, '%04d' % n)
                os.makedirs(target, exist_ok=True)
                out = os.path.join(target, os.path.basename(m.filename.replace('\\', '/')))
                try:            # one bad member refuses this download only, never the whole Inbox run
                    with z.open(m) as src, open(out, 'wb') as dst:
                        shutil.copyfileobj(src, dst, 1 << 20)
                except ZIP_ERRORS as e:
                    item.status, item.why = 'refused', ('cannot extract %s (%s: %s): extract the zip by hand'
                                                        % (m.filename, type(e).__name__, e))
                    return
                found.append((os.path.basename(out), out))
    elif low.endswith(OTHER_ARCHIVES):
        item.status, item.why = 'refused', 'SpeedKit can only open .zip archives: extract it first'
        return
    elif low.endswith(('.package', '.ts4script')):
        found = [(item.name, item.path)] + [(os.path.basename(p), p) for p in item.extra]
    else:
        item.status, item.why = 'refused', 'not a mod file (.package, .ts4script or .zip)'
        return
    if not found:
        item.status, item.why = 'refused', 'no .package or .ts4script inside'
        return
    names = Counter(n.lower() for n, _ in found)
    twice = [n for n, c in names.items() if c > 1]
    if twice:
        item.status, item.why = 'refused', 'two files named %s in one download: install it by hand' % twice[0]
        return
    item.files = [InFile(n, p, item) for n, p in sorted(found, key=lambda x: x[0].lower())]


def _read_infile(f):
    """Index + content hashes of a dropped package. Returns an error text or None."""
    try:
        with Package(f.path) as p:
            f.entries = [e for e in p.entries]
            for e in f.entries:
                if e.comp == DELETED:
                    f.odd = 'holds deleted-flag entries'
                    continue
                raw = p.raw(e)
                try:
                    f.content[key_of(e)] = data_digest(raw, e.comp, e.msize).hex()
                except Exception:
                    f.content[key_of(e)] = 'raw:%04X:%s' % (e.comp, digest(raw).hex())
    except Exception as e:
        try:
            with open(f.path, 'rb') as fh:
                is_zip = fh.read(4) == b'PK\x03\x04'
        except OSError:
            is_zip = False
        if is_zip:
            return '%s is a zip archive named .package: rename it to .zip and drop it again' % f.name
        return '%s is not a valid package (%s)' % (f.name, e)
    keys = [key_of(e) for e in f.entries if e.comp != DELETED]
    if any(e.t == MANIFEST_TYPE for e in f.entries):
        f.odd = f.odd or 'is already an S4S merge'
    elif len(set(keys)) != len(keys):
        f.odd = f.odd or 'holds one resource key twice'
    elif not keys:
        f.odd = f.odd or 'is empty'
    try:
        facts = companions.package_facts(f.path)
        f.tuning = bool(facts['xml'] or facts['mfm'])
    except Exception as e:
        return '%s cannot be read (%s)' % (f.name, e)
    return None


def _loaded_copies(lib, roots, keys, exclude=()):
    """{key: [hashing.Copy]} of every loaded copy of the keys (load order), leaving out packages in exclude."""
    pos = lib.order_positions(roots)
    db = lib.db
    db.execute('drop table if exists temp.mg_keys')
    db.execute('create temp table mg_keys(t integer, g integer, i integer, primary key(t, g, i))')
    db.executemany('insert or ignore into temp.mg_keys values(?,?,?)', ((t, g, signed64(i)) for t, g, i in keys))
    out = defaultdict(list)
    q = """select r.t, r.g, r.i, r.pkg, r.rowid, r.off, r.fsize, r.msize, r.comp from temp.mg_keys k
           join res r on r.t = k.t and r.g = k.g and r.i = k.i where r.comp != ?"""
    for t, g, i, pid, rowid, off, fs, ms, comp in db.execute(q, (DELETED,)):
        if pid in pos and pid not in exclude:
            key = (t, g, unsigned64(i))
            out[key].append(Copy(key, pid, pos[pid], rowid, off, fs, ms, comp))
    db.execute('drop table temp.mg_keys')
    for v in out.values():
        v.sort(key=lambda c: (c.pos, c.rowid))
    return out


def _hash_data(lib, copies, cache_path=None):
    """Fill raw/data/err of hashing.Copy objects with the data hash of every copy (cache first, then read)."""
    if not copies:
        return
    pkgs = {p.id: p for p in lib.packages()}
    cache = HashCache(cache_path)
    try:
        need = defaultdict(list)
        by_pkg = defaultdict(list)
        for c in copies:
            by_pkg[c.pkg].append(c)
        for pid, cs in by_pkg.items():
            p = pkgs[pid]
            known = cache.lookup(p.rel, p.size, p.mtime)
            for c in cs:
                hit = known.get((c.key[0], c.key[1], signed64(c.key[2]), c.off))
                if hit:
                    c.raw, c.data, c.err = hit
                if c.data is None and c.raw is not None and c.err is None:
                    c.data = cache.data_of(c.raw, c.comp)
                if c.data is None and c.err is None:
                    need[pid].append(c)
        rows = []
        for pid, cs in need.items():
            p = pkgs[pid]
            items = sorted(((c.off, c.fsize, c.comp, c.msize, True, c) for c in cs), key=lambda x: x[0])
            results, _ = hash_package(p.path, p.size, p.mtime, items)
            for c, raw, data, err, cacheable in results:
                c.raw, c.err = raw, err
                if data is not None or raw is None:
                    c.data = data
                if cacheable:
                    rows.append((p.root, p.rel, p.size, p.mtime, c.key[0], c.key[1], signed64(c.key[2]), c.off,
                                 c.comp, raw, c.data, err))
        if rows:
            cache.store(rows)
    finally:
        cache.close()


def _name_index(lib, roots):
    """{file name lower: [(root, rel)]} of every installed .package and .ts4script."""
    out = defaultdict(list)
    for p in lib.packages():
        if p.root in roots:
            out[p.rel.rsplit('/', 1)[-1].lower()].append((p.root, p.rel))
    for s in lib.scripts():
        if s.root in roots:
            out[s.rel.rsplit('/', 1)[-1].lower()].append((s.root, s.rel))
    return out


def _unique_dir(lib, name, taken):
    """A folder name under Mods that exists in neither root (mods_switch cannot restore over a taken name) and
    that no other download of this run uses."""
    base = name.rstrip(' .') or 'Download'
    base = re.sub('(?i)speedkit', 'SK', base)          # SpeedKit names are reserved for SpeedKit's own files
    if base.lower() == 'fitstudio':
        base = 'Download ' + base
    cand, n = base, 2
    while cand.lower() in taken or any(os.path.exists(os.path.join(lib.roots[r], cand)) for r in lib.roots):
        cand = '%s (%d)' % (base, n)
        n += 1
    taken.add(cand.lower())
    return cand


def _free_rel(lib, rel, taken):
    """rel, or rel with ' (2)', ' (3)'... before the extension if a file is there in either root or planned."""
    stem, ext = os.path.splitext(rel)
    cand, n = rel, 2
    while cand.lower() in taken or any(os.path.exists(os.path.join(lib.roots[r], cand.replace('/', os.sep)))
                                       for r in lib.roots):
        cand = '%s (%d)%s' % (stem, n, ext)
        n += 1
    taken.add(cand.lower())
    return cand


def _same_file(path, f):
    """True if the file at path has exactly f's bytes."""
    try:
        if os.path.getsize(path) != f.size:
            return False
        if getattr(f, '_digest', None) is None:
            f._digest = file_digest(f.path)
        return file_digest(path) == f._digest
    except OSError:
        return False


def _output_root(lib, folder, moved):
    """'Mods' for SpeedKit's own output folder (SpeedKit Merged / SpeedKit Loose), or 'Mods_parked' when that
    folder is parked whole: a new Mods/<folder> would stop mods_switch 'full' from restoring it, so the new file
    joins the parked folder instead (covered by its entry, 'full' brings it back with the rest)."""
    return 'Mods_parked' if park_dir_block(lib.roots.get('Mods'), lib.roots.get('Mods_parked'),
                                           folder + '/x.package', moved) else 'Mods'


def _plan_inbox(lib, items, roots, cache_path, target_bytes=TARGET_BYTES, ignore_namemap=False):
    """Decide what happens to every file of every item (see process_inbox). Returns {'merged': root,
    'loose': root}: where new SpeedKit Merged / SpeedKit Loose files go (see _output_root)."""
    names = _name_index(lib, roots)
    pkg_by_path = {(p.root, p.rel): p for p in lib.packages()}
    taken = set()
    dirs = set()
    moved = []
    if 'Mods_parked' in lib.roots:
        try:
            moved = (read_park_manifest(lib.roots['Mods_parked']) or {'moved': []})['moved']
        except MergeError:
            moved = None
    outs = {'merged': _output_root(lib, MERGED_DIR, moved), 'loose': _output_root(lib, LOOSE_DIR, moved)}
    # 1. read packages; refuse items with unreadable packages or alternative versions inside one download
    for it in items:
        if it.status != 'pending':
            continue
        for f in it.files:
            if not f.script:
                err = _read_infile(f)
                if err:
                    it.status, it.why = 'refused', err
                    break
        if it.status != 'pending':
            continue
        seen = {}
        for f in it.files:
            for k, c in f.content.items():
                if k[0] in (NAMEMAP, MANIFEST_TYPE):     # tool metadata S4S writes at instance 0 in every file
                    continue
                if k in seen and seen[k][1] != c:
                    it.status, it.why = 'refused', ('%s and %s change the same things differently (alternative versions?):'
                                                    ' put only the one you want in the Inbox' % (seen[k][0], f.name))
                    break
                seen.setdefault(k, (f.name, c))
            if it.status != 'pending':
                break
    live = [it for it in items if it.status == 'pending']
    by_size = defaultdict(list)                        # installed .package and .ts4script files by size
    for p in lib.packages():
        if p.root in roots:
            by_size[p.size].append((p.root, p.rel))
    for x in lib.scripts():
        if x.root in roots:
            by_size[x.size].append((x.root, x.rel))
    # 2. updates (same file name as an installed file) and untouched installs
    replaced = set()
    for it in live:
        matches = {}
        anchors = {}                                   # scripts installed already under another name
        for f in it.files:
            same = next((rr for rr in by_size.get(f.size, ()) if _same_file(lib.path(*rr), f)), None)
            if same is not None and same[1].rsplit('/', 1)[-1].lower() != f.name.lower():
                f.action, f.dest = 'duplicate', same            # e.g. downloaded again under another name
                f.why = 'the same file is already installed as %s/%s' % same
                f.identical = len(f.content)
                if f.script:
                    anchors[f] = same          # its companions of this download go next to that script
                continue
            m = names.get(f.name.lower(), [])
            if len(m) > 1:
                it.status, it.why = 'refused', 'several installed files are named %s: update it by hand' % f.name
                break
            if m and not f.script:
                pk = pkg_by_path.get(m[0])
                if pk is None or not set(_package_keys(lib, pk.id)) & set(f.content):
                    m = []                     # same name only (e.g. 'hair.package'), different CC: not an update
            if m and (is_fitstudio(m[0][1]) or is_speedkit_file(m[0][1])):
                it.status, it.why = 'refused', '%s would replace %s/%s, which SpeedKit does not manage' % ((f.name,) + m[0])
                break
            if m:
                matches[f] = m[0]
        if it.status != 'pending':
            continue
        has_script = any(f.script for f in it.files)
        home = None
        listed = False
        for f, (r, rel) in sorted(list(matches.items()) + list(anchors.items()),
                                  key=lambda kv: (not kv[0].script, kv[0].name.lower())):
            if rel.count('/') <= 1:
                home = (r, _parent(rel))
                if r == 'Mods_parked':
                    if moved is None:
                        it.status, it.why = 'refused', 'Mods_parked/_manifest.json cannot be read; fix it first'
                    else:
                        listed = park_covered(moved, rel)   # new files join the listing of the file they sit next to
                break
        if it.status != 'pending':
            continue
        if home is None:
            home = ('Mods', _unique_dir(lib, it.download, dirs))
        for f in it.files:
            if f.action == 'duplicate':
                continue
            if f in matches:
                r, rel = matches[f]
                if _same_file(lib.path(r, rel), f):
                    f.action, f.why, f.dest = 'duplicate', 'the same file is already installed', (r, rel)
                    continue
                f.action, f.replaces = 'update', (r, rel)
                if f.script and rel.count('/') > 1:
                    f.dest = (home[0], _free_rel(lib, '/'.join(x for x in (home[1], f.name) if x), taken))
                    f.why = 'replaces an older copy that was too deep to load'
                    f.park_list = listed
                else:
                    f.dest = (r, rel)
                    f.why = 'replaces the installed file of the same name'
                if (r, rel) in pkg_by_path:
                    replaced.add(pkg_by_path[(r, rel)].id)
            elif has_script or f.tuning or f.odd or f.size > target_bytes or companions.load_order_sensitive(f.name):
                order = not has_script and companions.load_order_sensitive(f.name)
                f.action = 'install'
                f.why = ('part of a script mod' if has_script
                         else 'load-order name (installed untouched at the top of Mods, where its name decides when '
                              'it loads)' if order
                         else 'gameplay tuning (never merged)' if f.tuning
                         else 'too big to merge' if not f.odd else f.odd + ' (installed as it is)')
                # a '!'/'zz'/numbered name only works where its name is compared: at the root, not in a folder
                f.dest = (home[0], _free_rel(lib, f.name if order else '/'.join(x for x in (home[1], f.name) if x),
                                             taken))
                f.park_list = listed
    # 3. CC: compare with the library (without the files being replaced) and with each other
    cc = [f for it in live if it.status == 'pending' for f in it.files if f.action is None]
    installed = {}                                     # content of untouched installs in this run
    for it in live:
        for f in it.files:
            if it.status == 'pending' and f.action in ('install', 'update'):
                for k, c in f.content.items():
                    installed.setdefault(k, set()).add(c)
    keys = {k for f in cc for k in f.content}
    lib_copies = _loaded_copies(lib, roots, keys, exclude=replaced)
    first = [cs[0] for cs in lib_copies.values()]      # the copy the game uses (first loaded)
    _hash_data(lib, first, cache_path)
    inbox_content = defaultdict(set)
    for f in cc:
        for k, c in f.content.items():
            inbox_content[k].add(c)
    for f in cc:
        for k, c in f.content.items():
            known = ({lib_copies[k][0].content()} if k in lib_copies else set()) | installed.get(k, set())
            if ignore_namemap and k[0] == NAMEMAP:
                if known:
                    f.identical += 1                   # tool metadata: keep the installed one
                else:
                    f.new_keys.add(k)
            elif c.startswith('raw:'):
                f.conflicts += 1                       # cannot be decoded: cannot be compared
            elif known:                                # installed already: what the game uses now decides
                if known == {c}:
                    f.identical += 1
                else:
                    f.conflicts += 1
            elif len(inbox_content[k]) > 1:            # new, but two downloads disagree about it
                f.conflicts += 1
            else:
                f.new_keys.add(k)
        if f.conflicts:
            f.action = 'loose'
            f.why = '%d resources differ from what is installed or from another download' % f.conflicts
            f.dest = (outs['loose'], _free_rel(lib, '%s/%s' % (LOOSE_DIR, f.name), taken))
            if outs['loose'] != 'Mods':
                f.why += PARKED_NOTE % LOOSE_DIR
        elif not f.new_keys:
            f.action, f.why = 'duplicate', 'everything in it is already installed'
        else:
            f.action = 'merge'
            f.why = 'new CC' + (' (%d resources already installed were left out)' % f.identical if f.identical else '')
            if outs['merged'] != 'Mods':
                f.why += PARKED_NOTE % MERGED_DIR
    return outs


def _new_targets(lib, merges, target_bytes, max_bytes, root='Mods'):
    """Which New_NNN files (in root's SpeedKit Merged) the merged CC goes into: [(root, rel, old Pkg or None,
    [InFile])]. Numbers are unique across both roots."""
    olds = []
    for p in lib.packages(root):
        m = NAME_RX.match(p.rel.split('/')[-1])
        if p.rel.lower().startswith(MERGED_DIR.lower() + '/') and p.rel.count('/') == 1 and m \
                and m.group(1).lower() == NEW_CATEGORY.lower():
            olds.append((int(m.group(2)), p))
    olds.sort(key=lambda x: x[0])
    taken = _taken_numbers(lib, lib.roots)
    out = []
    cur = None
    size = 0
    newest = olds[-1][1] if olds else None
    if newest is not None and newest.size < target_bytes and not _changed(newest.path, newest.size, newest.mtime):
        try:
            man = manifest_decode(manifest_payload(*_manifest_entry(newest.path)))
            with Package(newest.path) as p:
                live = [key_of(e) for e in p.entries if e.t != MANIFEST_TYPE]
                deleted = any(e.comp == DELETED for e in p.entries)
            listed = {tuple(k) for _, s in man.walk() for k in s.keys}
            if not man.folders and not deleted and len(set(live)) == len(live) and listed == set(live):
                cur = (root, newest.rel, newest, [])  # SpeedKit's own layout: safe to rewrite with more CC
                size = newest.size
                out.append(cur)
        except Exception:
            cur = None
    for f in merges:
        est = sum(e.fsize + 32 for e in f.entries if key_of(e) in f.new_keys) + 64 + 16 * len(f.new_keys)
        if cur is None or size + est > target_bytes:
            cur = (root, '%s/%s_%03d.package' % (MERGED_DIR, NEW_CATEGORY, _next_number(taken, NEW_CATEGORY)), None, [])
            out.append(cur)
            size = 96
        cur[3].append(f)
        size += est
    return [t for t in out if t[3]]


def _manifest_entry(path):
    with Package(path) as p:
        e = next((e for e in p.entries if e.t == MANIFEST_TYPE), None)
        if e is None:
            raise MergeError('%s has no S4S manifest' % path)
        return p.raw(e), e.comp, e.msize


def process_inbox(lib, dry_run=True, inbox=None, journal_home=None, sims=None, check_game=True,
                  target_bytes=TARGET_BYTES, max_bytes=MAX_BYTES, cache_path=None, today=None, progress=None,
                  ignore_namemap=False, min_free=MIN_FREE):
    """Install what the user dropped into SIMS/SpeedKit/Inbox. Dry run by default (nothing is written in the
    Sims 4 folder; zips are opened in the system temp folder).

    Per item (a .zip, a folder, a .package or a .ts4script; .rar/.7z are refused with 'extract it first'):
      * a file with the same name as an installed .package/.ts4script is an UPDATE: it replaces that file in
        place (the old one goes to quarantine), in whichever root it is (a parked mod stays parked);
      * a download that holds a .ts4script is a script mod: its .ts4script and .package files (its companions)
        go untouched into Mods/<download name>/ (one folder deep), or next to the script it updates;
      * packages with XML tuning (gameplay mods), S4S merges and other odd packages go untouched into the same
        folder - they are never merged;
      * other .package files are CC: a file that is byte-for-byte an installed file is not installed again;
        resources identical to the copy the game loads now are left out, a package with a resource that differs
        from it (or from another download's copy) goes to Mods/SpeedKit Loose/ unmerged, the rest are merged into
        Mods/SpeedKit Merged/New_NNN.package (the newest one below target_bytes is rewritten with the new CC
        added; the old version is quarantined). ignore_namemap: a NameMap (0x0166038C) that differs from the
        installed one does not make a package 'loose' (the installed NameMap is kept), like plan_merge's option;
      * a standalone package with a load-order name ('!', '~', '_', 'zz', numbered prefixes) is installed
        untouched at the top of Mods (its name decides when it loads; a merge or a folder would lose that);
      * when SpeedKit Merged / SpeedKit Loose is parked as a whole folder (mods_switch lean), new files go into
        that parked folder rather than creating it again in Mods (which would stop 'full' from restoring it);
      * processed items move to Inbox/_done/<date>/. Refused items stay in the Inbox with the reason reported.
      * a zip member that cannot be extracted (Deflate64, encrypted, bad CRC, a name Windows forbids) refuses
        that download only.
    Real run: Journal kind 'inbox'; refuses if less than min_free bytes would stay free on the Mods drive; after
    the run the library is rescanned and every merged resource is checked to be the one the game loads (undone
    automatically if not). Returns a report of what went where."""
    if not 0 < target_bytes <= max_bytes <= HARD_LIMIT:
        raise ValueError('need 0 < target_bytes <= max_bytes <= 2^31-1')
    roots = tuple(r for r in ('Mods', 'Mods_parked') if r in lib.roots)
    sims, journal_home = _homes(lib, roots, sims, journal_home)
    if not sims and (inbox is None or not dry_run):
        # never fall back to the real Sims 4 folder for a library built on other roots
        raise MergeError('the library roots have no common parent folder: pass sims=')
    inbox = inbox or inbox_path(sims=sims)
    today = today or datetime.date.today().isoformat()
    rep = {'dry_run': dry_run, 'inbox': inbox, 'journal': None, 'items': [], 'merged_into': [], 'warnings': []}
    if not os.path.isdir(inbox):
        if dry_run:
            rep['warnings'].append('the Inbox folder does not exist yet (it is created on the first real run)')
            return rep
        ensure_inbox(sims=sims)
        return rep
    if not dry_run:
        if not sims or not _inside(inbox, sims):
            raise MergeError('the Inbox must be inside the Sims 4 folder that holds the mods')
        if check_game and game_running():
            raise MergeError('The Sims 4 is running - close it first.')
        problems = index_problems(lib, roots)
        if problems:
            raise MergeError('the library changed since it was scanned (%s) - rescan first' % problems[:3])
        os.makedirs(os.path.join(inbox, '_staging'), exist_ok=True)
        staging = tempfile.mkdtemp(prefix='run-', dir=os.path.join(inbox, '_staging'))
    else:
        staging = tempfile.mkdtemp(prefix='speedkit_inbox_')
    try:
        items = _list_inbox(inbox)
        for it in items:
            _expand(it, staging)
        outs = _plan_inbox(lib, items, roots, cache_path, target_bytes, ignore_namemap)
        merges = [f for it in items if it.status == 'pending' for f in it.files if f.action == 'merge']
        targets = _new_targets(lib, merges, target_bytes, max_bytes, outs['merged'])
        for root, rel, old, fs in targets:
            for f in fs:
                f.dest = (root, rel)
            rep['merged_into'].append({'file': '%s/%s' % (root, rel), 'appends_to_existing': old is not None,
                                       'downloads': [f.name for f in fs]})
        for it in items:
            if it.status == 'pending':
                it.status = 'would be done' if dry_run else 'pending'
        if dry_run:
            rep['items'] = [it.to_dict() for it in items]
            return rep
        _run_inbox(lib, items, targets, rep, roots, sims, journal_home, inbox, staging, today, check_game,
                   max_bytes, cache_path, progress, {NAMEMAP} if ignore_namemap else set(), min_free)
        rep['items'] = [it.to_dict() for it in items]
        return rep
    finally:
        shutil.rmtree(staging, ignore_errors=True)       # only SpeedKit's own extracted/staged copies
        if not dry_run:
            try:
                os.rmdir(os.path.dirname(staging))       # Inbox/_staging, if empty
            except OSError:
                pass


def _stage(f, staging):
    """A copy of a dropped file in staging (same drive as Mods), so the original can move to _done."""
    if _inside(f.path, staging):
        return f.path
    d = tempfile.mkdtemp(dir=staging)
    out = os.path.join(d, f.name)
    shutil.copy2(f.path, out)
    if file_digest(out) != file_digest(f.path):
        raise MergeError('copy of %s is not identical' % f.path)
    return out


def _run_inbox(lib, items, targets, rep, roots, sims, journal_home, inbox, staging, today, check_game, max_bytes,
               cache_path, progress, lenient=frozenset(), min_free=MIN_FREE):
    live = [it for it in items if it.status == 'pending']
    if not live:
        return
    parked = lib.roots.get('Mods_parked')
    if any(f.dest and f.dest[0] == 'Mods_parked' for it in live for f in it.files):
        read_park_manifest(parked)
    # disk space: staged copies of loose dropped files (zip members are already extracted) + the New_NNN files
    need = sum(f.size for it in live for f in it.files
               if f.action in ('install', 'update', 'loose') and not _inside(f.path, staging))
    need += sum((old.size if old is not None else 0) + sum(f.size for f in fs) for _, _, old, fs in targets)
    if need and _free(lib.roots['Mods']) - need < min_free:
        raise MergeError('not enough free space on %s to install %.2f GB (%.1f GB must stay free)'
                         % (_drive(lib.roots['Mods']), need / 1e9, min_free / 1e9))
    # before-map of the New_NNN files that get appended to
    old_keys = set()
    for _, rel, old, fs in targets:
        if old is not None:
            old_keys |= {k for k in _package_keys(lib, old.id) if k[0] != MANIFEST_TYPE and k[0] not in lenient}
    before = _effective(lib, roots, old_keys, cache_path, None, THREADS) if old_keys else {}
    j = Journal('inbox', '%d downloads' % len(live), home=journal_home, sims=sims, check_game=check_game)
    rep['journal'] = j.id
    rec = {'kind': 'inbox', 'journal': j.id, 'parked_root': parked, 'park_manifest_added': [],
           'quarantined_parked_sources': []}
    _save_record(journal_home, j.id, rec)
    expect = {}                                # (root, rel) -> file digest of untouched installs
    tmp = None
    cache = HashCache(cache_path)
    try:
        for it in live:
            for f in it.files:
                if f.action not in ('install', 'update', 'loose'):
                    continue
                dst = os.path.join(lib.roots[f.dest[0]], f.dest[1].replace('/', os.sep))
                src = _stage(f, staging)
                expect[f.dest] = file_digest(src)
                if f.action == 'update':
                    old = os.path.join(lib.roots[f.replaces[0]], f.replaces[1].replace('/', os.sep))
                    if f.replaces == f.dest:
                        j.replace(src, dst)
                    else:
                        j.quarantine(old)
                        j.put_new(src, dst)
                else:
                    j.put_new(src, dst)
                if f.dest[0] == 'Mods_parked' and f.dest != f.replaces and f.park_list:   # a NEW parked file
                    added = park_manifest_add(parked, [f.dest[1]])
                    rec['park_manifest_added'] += added
                    _save_record(journal_home, j.id, rec)
        for troot, rel, old, fs in targets:
            final = os.path.join(lib.roots[troot], rel.replace('/', os.sep))
            parts = []
            if old is not None:
                man = manifest_decode(manifest_payload(*_manifest_entry(old.path)))
                parts.append(Part(old.path, old.size, old.mtime,
                                  manifest_sources=[(s.name, [tuple(k) for k in s.keys]) for s in man.sources]))
            for f in fs:
                st = os.stat(f.path)
                parts.append(Part(f.path, st.st_size, st.st_mtime, name=_stem(f.name), take=set(f.new_keys)))
            tmp, st = write_merged(parts, final, max_bytes, cache, (troot, rel), lenient)
            if old is not None:
                j.replace(tmp, final)
            else:
                j.put_new(tmp, final)
            tmp = None
        done = os.path.join(inbox, '_done', today)
        for it in live:
            for path in [it.path] + it.extra:
                name = os.path.basename(path)
                dst = os.path.join(done, name)
                n = 2
                while os.path.exists(dst):
                    base, ext = os.path.splitext(name) if not os.path.isdir(path) else (name, '')
                    dst = os.path.join(done, '%s (%d)%s' % (base, n, ext))
                    n += 1
                j.move(path, dst)
            it.status = 'done'
        j.close('committed')
    except BaseException as e:
        cache.close()
        if tmp and os.path.exists(tmp):
            os.remove(tmp)
        j.close('failed: %s' % e)
        note = _roll_back(j.id, journal_home, check_game, lib, parked)
        if not isinstance(e, Exception):
            raise
        raise MergeError('%s; %s' % (e, note)) from e
    cache.close()
    # after-check: untouched files arrived bit-exact; merged CC is what the game loads; old New_NNN unchanged
    try:
        lib.scan()
        wrong = []
        for (r, rel), d in expect.items():
            p = os.path.join(lib.roots[r], rel.replace('/', os.sep))
            if not os.path.exists(p) or file_digest(p) != d:
                wrong.append(('file', '%s/%s' % (r, rel)))
        want, want_root = {}, {}
        for troot, rel, old, fs in targets:
            for f in fs:
                for k in f.new_keys:
                    if k[0] not in lenient:
                        want[k] = f.content[k]
                        want_root[k] = troot
        got = _effective(lib, roots, set(want), cache_path, None, THREADS) if want else {}
        for scope, m in got.items():
            for k, v in m.items():
                if 'Mods_parked' not in scope and want_root[k] == 'Mods_parked':
                    continue                   # a file put into a parked folder is not loaded by Mods alone
                if v != want[k]:
                    wrong.append(('merged', '+'.join(scope), '%08X:%08X:%016X' % k))
        if before:
            wrong += [('kept',) + x[1:2] for x in _diff(before, _effective(lib, roots, old_keys, cache_path, None, THREADS))]
    except BaseException as e:
        note = _roll_back(j.id, journal_home, check_game, lib, parked)
        if not isinstance(e, Exception):
            raise
        raise MergeError('the check after installing failed (%s); %s' % (e, note)) from e
    rep['invariant'] = {'untouched_files': len(expect), 'merged_resources': len(want), 'kept_resources': len(old_keys),
                        'wrong': wrong[:20]}
    if wrong:
        note = _roll_back(j.id, journal_home, check_game, lib, parked)
        raise InvariantError('after installing, %d things are not as expected (e.g. %r); %s' % (len(wrong), wrong[:3], note))


# ------------------------------------------------------------------------------------------ CLI
def _gb(n):
    return '%.2f GB' % (n / 1e9)


def main(argv=None):
    import argparse
    from .library import Library, DEFAULT_DB
    from .journal import HOME
    try:
        sys.stdout.reconfigure(errors='backslashreplace')
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description='Merge loose CC safely, and install downloads from the SpeedKit Inbox.')
    ap.add_argument('command', choices=('plan', 'apply', 'inbox', 'undo'))
    ap.add_argument('journal', nargs='?', help='journal id for undo')
    ap.add_argument('--db', default=DEFAULT_DB, help='library index')
    ap.add_argument('--scan', action='store_true', help='bring the library index up to date first')
    ap.add_argument('--cache', default=None, help='hash cache (default data/hash.sqlite)')
    ap.add_argument('--companions-cache', default=None, help='companions cache (default data/companions.sqlite)')
    ap.add_argument('--quarantine', default=None, help='quarantine folder for merged originals (e.g. on E:)')
    ap.add_argument('--journal-home', default=None)
    ap.add_argument('--json', help='write the full plan / report here')
    ap.add_argument('--ignore-namemap', action='store_true', help='NameMap resources are tool metadata (like dedup)')
    ap.add_argument('--apply', action='store_true', help='really change files (otherwise a dry run)')
    a = ap.parse_args(argv)
    if a.command == 'undo':
        for act in undo(a.journal, home=a.journal_home or HOME, dry_run=not a.apply):
            print('  %s: %s' % act)
        if not a.apply:
            print('(dry run - add --apply to undo)')
        return 0
    lib = Library(a.db)
    if a.scan:
        lib.scan(verbose=True)
    if a.command == 'inbox':
        rep = process_inbox(lib, dry_run=not a.apply, journal_home=a.journal_home, cache_path=a.cache,
                            ignore_namemap=a.ignore_namemap)
        for w in rep['warnings']:
            print('note:', w)
        for it in rep['items']:
            print('%s: %s%s' % (it['item'], it['status'], (' - ' + it['why']) if it['why'] else ''))
            for f in it['files']:
                print('    %-40s %-9s %s' % (f['file'], f['action'] or '-', f.get('to', f['why'])))
            if it.get('not_installed'):
                print('    not installed (kept in Inbox\\_done): %s' % ', '.join(it['not_installed']))
        for m in rep['merged_into']:
            print('merged into %s%s: %s' % (m['file'], ' (added to it)' if m['appends_to_existing'] else '',
                                             ', '.join(m['downloads'])))
    else:
        p = plan_merge(lib, cache_path=a.cache, companions_cache=a.companions_cache, ignore_namemap=a.ignore_namemap)
        s = p.summary()
        print('%d groups: %d packages (%s) -> %d merged files (%s); %d files fewer'
              % (s['groups'], s['packages_merged'], _gb(s['source_bytes']), s['groups'],
                 _gb(s['merged_files_estimated_bytes']), s['files_saved']))
        print('not merged: %d packages; %d mergeable but alone' % (s['excluded'], s['mergeable_but_alone']))
        for r, n in s['excluded_by_reason'].items():
            print('  %-16s %4d  (%s)' % (r, n, _gb(s['excluded_bytes_by_reason'][r])))
        for w in s['warnings']:
            print('warning:', w)
        for g in p.groups:
            print('  %s/%s <- %d packages (%s)' % (g.root, g.out_rel, len(g.sources), _gb(g.src_bytes)))
        rep = p.to_dict()
        if a.command == 'apply':
            rep['apply'] = apply_merge(p, lib, dry_run=not a.apply, quarantine_home=a.quarantine,
                                       journal_home=a.journal_home, cache_path=a.cache)
            print(json.dumps({k: v for k, v in rep['apply'].items() if k != 'would_write'}, indent=1, default=str))
    if a.json:
        with open(a.json, 'w', encoding='utf-8') as f:
            json.dump(rep, f, indent=1, default=str)
    return 0


if __name__ == '__main__':
    sys.exit(main())
