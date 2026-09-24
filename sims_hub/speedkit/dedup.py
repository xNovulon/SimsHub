"""Remove duplicate copies of resources from the mod library without changing what the game uses.

The library (Mods + Mods_parked laid over each other) holds 2.36M resource entries; about 250k
type/group/instance keys are stored in 2-10 packages at once, mostly because the same CC file was merged
into several Sims 4 Studio merges. plan() works out which copies can go; apply() rewrites or quarantines
packages one at a time through a Journal, checks that the game still sees the same content for every key,
and undoes everything by itself if not.

Facts this relies on (research/research_results.json: dupes, loadorder, merging and their reviews):
  * Within one Resource.cfg priority the game walks Mods depth-first in NTFS name order and uses the
    FIRST loaded copy of a key (in-game proven for tuning in 2017, not re-tested on 1.126 for CC).
    speedkit.library.load_order() reproduces that walk; Mods_parked mirrors Mods paths.
  * 226k duplicated keys are byte-identical in every copy and 3.4k more are identical once decompressed;
    ~20k really conflict. Content is compared with speedkit.hashing (blake2b of stored / decompressed bytes).
  * Type 0x7FB6AD8A is Sims 4 Studio's merge manifest: tool metadata listing which source file each
    resource came from. EA ships none and the game has no use for it. It is never deduplicated; when a
    merged package is rewritten its manifest is rewritten without the removed keys (speedkit.manifest),
    and the check after apply() ignores this type.
  * Type 0x0166038C (NameMap) maps instance ids to names for tools. EA ships 21 of them, and whether the
    game reads CC ones is unknown, so by default it is ordinary content. With ignore_namemap=True it is
    treated like the manifest (never deduplicated, not counted when deciding that a package is empty).
  * Script-mod companion packages (speedkit.companions, or the research snapshot
    research/merging/companions.json) and every package in a folder that holds a .ts4script are
    "protected": they never lose a resource and are never rewritten, and their copy is the one kept.
  * speedkit.dbpf.PackageWriter.add_raw copies a resource bit-exact (verified on real packages), refuses
    the same key twice and files over 4 GiB. A few merges hold one key twice; such a package is skipped
    if both copies would stay.
  * Another tool (Tools/sims4_fitstudio/mods_switch.py) moves files between Mods (the set the game loads
    now) and Mods_parked. Every key the game loads from Mods keeps a copy in Mods. Deduplication assumes
    the library is used as a whole: if a stripped package is later enabled WITHOUT the package that kept
    the copy, that resource is missing. Undo a dedup journal before re-arranging files by hand.

Policies:
  'identical' (default): for a key whose copies all hold the same data, keep one copy and drop the rest.
      The copy kept is a protected package's copy if there is one (all protected copies stay), else the
      earliest-loaded copy in Mods if the key is there (so the set the game loads now keeps it), else the
      earliest-loaded copy. Safe under any load order, because every copy is the same.
  'winner' (experimental): additionally, for conflicting keys keep only the copy the game uses (first in
      load order, and the first in Mods) and drop the losing copies (not for keys stored twice inside one
      package, whose in-file order is unknown). Keeps current behaviour but loses the other versions for
      good once the quarantine is emptied, and a package enabled later without the winner's package then
      falls back to nothing instead of its own version.

Disk space: a replaced original is moved to the journal's quarantine. With the quarantine on the same drive
as Mods (the default, SpeedKit\\quarantine) the move is instant but disk usage first GROWS by the size of
every rewritten file; the saving appears when the quarantine is emptied. With journal_home on another drive
the originals are copied there and the Mods drive only ever needs room for the file being written.
apply() skips a package when a drive would fall below min_free; free_space() simulates the same run.

    p = plan(lib)                              # read-only; hashes are cached in data/hash.sqlite
    print(json.dumps(report(p, lib), indent=1))
    apply(p, lib)                              # dry run: what would happen, free-space needs
    apply(p, lib, dry_run=False)               # real run (refuses while TS4_x64.exe runs)
"""
import json
import os
import shutil
import stat
import sys
import time
from collections import Counter, defaultdict

from .dbpf import Package, PackageWriter, key_of, DELETED
from .hashing import DEFAULT_ROOTS, THREADS, HashCache, digest, hash_copies, key_status, effective_map
from . import journal as _journal_mod
from .journal import Journal, undo, list_journals
from .library import SIMS, PROJECT, SKIP_DIRS, game_running, signed64, unsigned64
from .manifest import MANIFEST_TYPE, payload as manifest_payload, rewrite_without as manifest_without, sources_of

NAMEMAP = 0x0166038C
METADATA = (MANIFEST_TYPE, NAMEMAP)      # tool metadata: never evidence that a package carries script tuning
POLICIES = ('identical', 'winner')
TMP_SUFFIX = '.speedkit-dedup'           # new file while it is written (+'.writing') and verified
COMPANIONS_JSON = os.path.join(PROJECT, 'research', 'merging', 'companions.json')
PROTECTED_VERDICTS = ('companion', 'weak', 'orphan')
MIN_FREE = 5 << 30                       # apply() never lets a drive fall below this much free space

TYPE_NAMES = {
    0x034AEECB: 'CASP (CAS part)', 0x3453CF95: 'RLE2 image', 0x3C1AF1F2: 'CAS thumbnail', 0x2BC04EDF: 'LRLE image',
    0x015A1849: 'GEOM (CAS mesh)', 0xBC4A5044: 'Clip header', 0x6B20C4F3: 'Animation clip', 0x00B2D882: 'DST image',
    0x545AC67A: 'SimData', 0xBA856C78: 'RLES image', 0x220557DA: 'STBL (strings)', 0xAC16FBEC: 'RegionMap',
    0xE882D22F: 'Interaction tuning', 0x6017E896: 'Buff tuning', 0x0C772E27: 'Loot tuning', 0xCB5FDDC7: 'Trait tuning',
    0x067CAA11: 'BGEO', NAMEMAP: 'NameMap', MANIFEST_TYPE: 'S4S merge manifest', 0x03B33DDF: 'Tuning',
    0xC0DB5AE7: 'OBJD', 0x319E4F1D: 'COBJ', 0x01661233: 'MODL', 0x01D10F34: 'MLOD', 0x01D0E75D: 'MATD',
    0x02019972: 'MTST', 0xD382BF57: 'Footprint', 0x3C2A8647: 'Build/buy thumbnail', 0x0354796A: 'TONE (skin tone)',
    0x02D5DF13: 'ASM', 0xEE17C6AD: 'Animation tuning', 0xB61DE6B4: 'Object tuning', 0x7DF2169C: 'Snippet tuning',
    0x62E94D38: 'Combined tuning', 0x8EAF13DE: 'RIG', 0xD3044521: 'Slot', 0x6BF15BBE: 'S4S batch-fix log',
    0xB6C8B6A0: 'DDS image',
}


class DedupError(Exception):
    pass


class InvariantError(DedupError):
    """apply() changed what the game would load; the journal has been undone."""


def tname(t):
    """Readable name of a resource type."""
    return TYPE_NAMES.get(t, '%08X' % t)


def _folder(rel):
    return rel.rsplit('/', 1)[0].lower() if '/' in rel else ''


def _changed(path, size, mtime):
    """Why a file no longer matches (size, mtime), or None if it does."""
    try:
        st = os.stat(path)
    except OSError:
        return 'missing'
    if st.st_size != size or abs(st.st_mtime - mtime) >= 1e-3:
        return 'changed since the library scan'
    return None


def _drive(path):
    return os.path.splitdrive(os.path.abspath(path))[0].upper()


def _free(path):
    """Free bytes on the drive of path (or of its nearest existing parent folder)."""
    p = os.path.abspath(path)
    while not os.path.exists(p) and os.path.dirname(p) != p:
        p = os.path.dirname(p)
    return shutil.disk_usage(p).free


def sims_folder(lib, roots=DEFAULT_ROOTS):
    """The Sims 4 folder that holds the library roots (their common parent), or None if they have none.
    apply() confines its journal to this folder, so a library built on a fake tree only touches that tree;
    with no common parent it refuses to guess (it never falls back to the real Sims 4 folder)."""
    parents = {os.path.normcase(os.path.dirname(os.path.abspath(lib.roots[r]))) for r in roots if r in lib.roots}
    if len(parents) == 1:
        return os.path.dirname(os.path.abspath(lib.roots[next(r for r in roots if r in lib.roots)]))
    return None


def _inside(path, base):
    """True if path is base or lies below it (case-insensitive, like Windows)."""
    path, base = os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.abspath(base))
    return path == base or path.startswith(base.rstrip('\\/') + os.sep)


# ---------------------------------------------------------------------------------------------- protection
def companion_rels(path=COMPANIONS_JSON):
    """Lower-cased relative paths (without the Mods/Mods_parked prefix) of packages that research/merging
    classified as script companions (companion, weak or orphan). Empty if the file is missing or path is None."""
    if not path:
        return set()
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return set()
    out = set()
    for p in data.get('packages', []):
        if p.get('verdict') in PROTECTED_VERDICTS:
            parts = p['package'].split('/', 1)
            out.add((parts[1] if len(parts) == 2 and parts[0] in ('Mods', 'Mods_parked') else p['package']).lower())
    return out


def _companions_kw(companions_cache):
    return {} if companions_cache is None else {'cache_path': companions_cache}


def companion_ids(lib, roots=DEFAULT_ROOTS, source='auto', companions_json=COMPANIONS_JSON, companions_cache=None):
    """(package ids classified as script companions, which source said so).

    source 'classifier': speedkit.companions.classify(), every verdict never_merge() is true for
    (core, addon, orphan, weak, broken). 'json': the research snapshot research/merging/companions.json
    (companion, weak, orphan), matched by relative path in either root. 'auto': the classifier, or the
    JSON if the classifier is missing or fails. None: no companion list. companions_cache: the classifier's
    cache file (default: its own data/companions.sqlite, which it reads and writes)."""
    if source in ('auto', 'classifier'):
        try:
            from . import companions
            verdicts = companions.classify(lib, tuple(roots), **_companions_kw(companions_cache))
            return {pid for pid, v in verdicts.items() if companions.never_merge(v)}, 'speedkit.companions'
        except Exception:
            if source == 'classifier':
                raise
    if source in ('auto', 'json'):
        rels = companion_rels(companions_json)
        return {p.id for p in lib.packages() if p.rel.lower() in rels}, 'research/merging/companions.json'
    return set(), 'none'


def stale_copy_merges(lib, roots, protected, companions_cache=None):
    """S4S merges in `protected` that are protected only because they hold copies of script-mod files that
    also exist as standalone protected packages (e.g. sim/m27 holding an old TURBODRIVER_WickedWhims_Tuning):
    every merge source that carries script-linked resources (speedkit.companions.script_bearing_sources) has
    a standalone protected package of the same name, or the classifier's verdict is 'weak' and no such source
    was found. Merges that are script add-ons in their own right (WickedWhims animation packs, a script
    mod's only copy of its tuning) are never in this set. Empty if the classifier is unavailable."""
    merged = {pid for (pid,) in lib.db.execute('select distinct pkg from res where t=?', (MANIFEST_TYPE,))}
    cand = merged & set(protected)
    if not cand:
        return set()
    try:
        from . import companions
        verdicts = companions.classify(lib, tuple(roots), **_companions_kw(companions_cache))
        bearing = companions.script_bearing_sources(lib, tuple(roots), **_companions_kw(companions_cache))
    except Exception:
        return set()
    names = {p.id: p.rel for p in lib.packages()}
    standalone = [names[pid] for pid in set(protected) - merged if pid in names]
    out = set()
    for pid in cand:
        sources = bearing.get(pid, [])
        v = verdicts.get(pid)
        if sources:
            if all(any(_same_name(s, rel) for rel in standalone) for s in sources):
                out.add(pid)
        elif v is not None and v.kind == 'weak':
            out.add(pid)
    return out


def _protection(lib, roots=DEFAULT_ROOTS, source='auto', include_merged=True, companions_json=COMPANIONS_JSON,
                companions_cache=None):
    ids, used = companion_ids(lib, roots, source, companions_json, companions_cache)
    script_dirs = {_folder(s.rel) for s in lib.scripts()}
    near_script = {p.id for p in lib.packages() if _folder(p.rel) in script_dirs}
    note = ''
    if not include_merged:
        freed = stale_copy_merges(lib, roots, ids | near_script, companions_cache) - near_script
        ids -= freed
        note = ' (%d S4S merges holding only stale copies of standalone script files not protected)' % len(freed)
    return ids | near_script, used + ' + packages next to a .ts4script' + note


def default_protected(lib, roots=DEFAULT_ROOTS, source='auto', include_merged=True, companions_json=COMPANIONS_JSON,
                      companions_cache=None):
    """Package ids that must never lose a resource: script-mod companions (see companion_ids; source=None
    skips them) and every package in a folder that holds a .ts4script (in either root).

    include_merged=False does not protect the S4S merges of stale_copy_merges(): merges the classifier flags
    only because some merged source is a copy of a standalone script-mod file (e.g. sim/m27 holding an old
    WickedWhims tuning copy). Their identical copies can then go (the standalone companion keeps its copy);
    differing ones stay as conflicts. Merges that are script add-ons themselves stay protected."""
    return _protection(lib, roots, source, include_merged, companions_json, companions_cache)[0]


def index_problems(lib, roots=DEFAULT_ROOTS):
    """Packages and scripts whose file on disk no longer matches the library index: [(root/rel, why)].
    Covers changed, missing and new .package and .ts4script files (the index must be current before
    apply(); protection depends on which folders hold a script)."""
    known = {(p.root, p.rel): p for p in lib.packages() if p.root in roots}
    known.update({(s.root, s.rel): s for s in lib.scripts() if s.root in roots})
    out = []
    seen = set()
    for root in roots:
        base = lib.roots.get(root)
        if not base or not os.path.isdir(base):
            continue
        for dp, dn, fn in os.walk(base):
            dn[:] = [d for d in dn if d not in SKIP_DIRS]
            for n in fn:
                if not n.lower().endswith(('.package', '.ts4script')):
                    continue
                full = os.path.join(dp, n)
                rel = os.path.relpath(full, base).replace('\\', '/')
                seen.add((root, rel))
                p = known.get((root, rel))
                if p is None:
                    out.append(('%s/%s' % (root, rel), 'not in the library index'))
                else:
                    why = _changed(full, p.size, p.mtime)
                    if why:
                        out.append(('%s/%s' % (root, rel), why))
    for (root, rel) in known:
        if (root, rel) not in seen:
            out.append(('%s/%s' % (root, rel), 'missing'))
    return out


def shadowed_paths(lib, roots=DEFAULT_ROOTS):
    """Relative paths (lower-cased) of packages that exist in more than one root. The overlay load order
    counts every copy as loaded, but the other tool never restores a parked file whose name is taken in
    Mods, so a kept copy there might never load. apply() refuses while any exist."""
    seen = defaultdict(set)
    for p in lib.packages():
        if p.root in roots:
            seen[p.rel.lower()].add(p.root)
    return sorted(rel for rel, rs in seen.items() if len(rs) > 1)


# ---------------------------------------------------------------------------------------------- plan
class PackagePlan:
    """What happens to one package.

    action: 'quarantine' (everything the game needs from it has a copy elsewhere: the whole file goes to
    quarantine), 'rewrite' (a new file without the dropped copies, other resources in their original
    order) or 'skip' (the drops were cancelled; reason says why). drop holds (t, g, i, off) of each copy
    to remove; only_metadata_left lists the types (manifest / NameMap) that are all that would remain."""

    def __init__(self, pkg):
        self.id, self.root, self.rel, self.path = pkg.id, pkg.root, pkg.rel, pkg.path
        self.size, self.mtime, self.n = pkg.size, pkg.mtime, pkg.n
        self.drop = set()
        self.drop_bytes = 0
        self.kept_n = 0
        self.action = None
        self.reason = ''
        self.new_size = 0
        self.has_manifest = False
        self.only_metadata_left = []

    @property
    def name(self):
        return '%s/%s' % (self.root, self.rel)

    @property
    def saved(self):
        """Bytes the package shrinks by once the quarantine is emptied."""
        if self.action == 'quarantine':
            return self.size
        if self.action == 'rewrite':
            return max(0, self.size - self.new_size)
        return 0

    def to_dict(self):
        return {'package': self.name, 'action': self.action, 'reason': self.reason, 'size': self.size,
                'resources': self.n, 'drop': len(self.drop), 'drop_bytes': self.drop_bytes, 'kept': self.kept_n,
                'new_size': self.new_size, 'saved': self.saved, 'has_s4s_manifest': self.has_manifest}


class Plan:
    """The result of plan(): which copies go, per package, plus everything report() needs."""

    def __init__(self, policy, roots, active, protected, ignore_namemap):
        self.policy, self.roots, self.active = policy, tuple(roots), active
        self.protected = set(protected)
        self.protected_source = 'given by the caller'
        self.ignore_namemap = ignore_namemap
        self.created = time.time()
        self.packages = {}         # pkg id -> PackagePlan (packages that lose something)
        self.keepers = {}          # pkg id -> (path, size, mtime): packages holding a kept copy of a touched key
        self.touched = set()       # keys with a copy dropped
        self.check_keys = set()    # duplicated keys whose effective content apply() compares before/after
        self.names = {}            # pkg id -> 'root/rel'
        self.counts = Counter()
        self.by_type = defaultdict(Counter)
        self.conflicts = {}        # key -> [(pkg id, variant number)] in load order
        self.undecidable = {}      # key -> [(pkg id, err)]
        self.overlap = defaultdict(Counter)   # (standalone protected pkg, S4S-merged pkg) -> counts
        self.merged = set()        # pkg ids of S4S-merged packages
        self.index_problems = []
        self.hash_stats = {}

    def actions(self, action=None):
        """PackagePlans with the given action (all with drops if None), largest saving first."""
        out = [pp for pp in self.packages.values() if action is None or pp.action == action]
        return sorted(out, key=lambda pp: -pp.saved)

    def ignorable(self):
        """Types that are tool metadata here: never deduplicated, not counted as content."""
        return {MANIFEST_TYPE} | ({NAMEMAP} if self.ignore_namemap else set())

    def summary(self):
        """Headline numbers as a dict."""
        q, r, s = self.actions('quarantine'), self.actions('rewrite'), self.actions('skip')
        live = q + r
        act = [pp for pp in live if pp.root == self.active]
        return {
            'policy': self.policy, 'roots': list(self.roots), 'active_root': self.active,
            'ignore_namemap': self.ignore_namemap, 'protected_packages': len(self.protected),
            'protected_source': self.protected_source,
            'copies_kept_only_because_protected': self.counts['protection_kept_copies'],
            'bytes_kept_only_because_protected': self.counts['protection_kept_bytes'],
            'duplicated_keys': self.counts['keys'], 'copies': self.counts['copies'],
            'identical_keys': self.counts['identical'], 'identical_raw_keys': self.counts['identical_raw'],
            'identical_after_decompress_keys': self.counts['identical'] - self.counts['identical_raw'],
            'conflicting_keys': self.counts['conflict'], 'undecidable_keys': self.counts['undecidable'],
            'copies_dropped': sum(len(pp.drop) for pp in live),
            'stored_bytes_dropped': sum(pp.drop_bytes for pp in live),
            'active_root_copies_dropped': sum(len(pp.drop) for pp in act),
            'active_root_bytes_dropped': sum(pp.drop_bytes for pp in act),
            'packages_quarantined': len(q), 'packages_quarantined_bytes': sum(pp.size for pp in q),
            'packages_rewritten': len(r), 'packages_rewritten_bytes': sum(pp.size for pp in r),
            'rewritten_new_bytes': sum(pp.new_size for pp in r),
            'packages_skipped': len(s),
            'bytes_saved_after_emptying_quarantine': sum(pp.saved for pp in live),
            'index_problems': len(self.index_problems),
        }


def _keep(cs, droppable, is_active, winner):
    """Split the copies of one key (in load order) into (keep, drop).

    Copies outside `droppable` packages always stay. Identical policy: if none of those is in the active
    root but the key is there, the first active copy stays; if still nothing stays, the first copy
    stays. Winner policy: the copy the game uses (first overall) and the first in the active root stay."""
    keep = [c for c in cs if c.pkg not in droppable]
    act = [c for c in cs if is_active(c.pkg)]
    if winner:
        for c in (cs[0], act[0] if act else None):
            if c is not None and c not in keep:
                keep.append(c)
    else:
        if act and not any(is_active(c.pkg) for c in keep):
            keep.append(act[0])
        if not keep:
            keep.append(cs[0])
    return keep, [c for c in cs if c not in keep]


def plan(lib, roots=DEFAULT_ROOTS, policy='identical', protected=None, active='Mods', ignore_namemap=False,
         cache_path=None, progress=None, threads=THREADS, include_merged=True, companions_cache=None):
    """Work out which duplicate copies can be removed. Read-only (hashes go to the hash cache).

    lib: speedkit.library.Library whose index is current (scan it first). roots: the roots laid over each
    other (load order as if all were in Mods). policy: 'identical' or 'winner' (see the module docstring).
    protected: package ids that never lose a resource (default: default_protected(lib, roots,
    include_merged=include_merged, companions_cache=companions_cache)). active: the root the game loads
    now; every key it holds keeps a copy there. Returns a Plan."""
    if policy not in POLICIES:
        raise ValueError('policy must be one of %s' % (POLICIES,))
    roots = tuple(roots)
    if active not in roots or len(roots) < 2:
        active = None
    pkgs = {p.id: p for p in lib.packages()}
    source = None
    if protected is None:
        protected, source = _protection(lib, roots, include_merged=include_merged, companions_cache=companions_cache)
    P = Plan(policy, roots, active, protected, ignore_namemap)
    P.protected_source = source or P.protected_source
    P.index_problems = index_problems(lib, roots)
    P.names = {pid: '%s/%s' % (p.root, p.rel) for pid, p in pkgs.items()}
    P.merged = {pid for (pid,) in lib.db.execute('select distinct pkg from res where t=?', (MANIFEST_TYPE,))}
    groups = hash_copies(lib, roots, progress, cache_path, threads, P.hash_stats)

    in_scope = {c.pkg for cs in groups.values() for c in cs}
    changeable = {pid for pid in in_scope if not pkgs[pid].err
                  and _changed(pkgs[pid].path, pkgs[pid].size, pkgs[pid].mtime) is None}
    droppable = changeable - P.protected

    def is_active(pid):
        return active is not None and pkgs[pid].root == active

    ignorable = P.ignorable()
    drops = defaultdict(list)
    keepers = set()
    for key, cs in groups.items():
        t = key[0]
        st = key_status(cs)
        raw_same = len({(c.raw, c.comp) for c in cs}) == 1 and cs[0].raw is not None
        P.counts['keys'] += 1
        P.counts['copies'] += len(cs)
        P.counts[st] += 1
        P.counts['identical_raw'] += st == 'identical' and raw_same
        bt = P.by_type[t]
        bt['keys'] += 1
        bt[st] += 1
        variant = {}
        if st == 'conflict':
            P.conflicts[key] = [(c.pkg, variant.setdefault(c.data, len(variant))) for c in cs]
        elif st == 'undecidable':
            P.undecidable[key] = [(c.pkg, c.err) for c in cs]
        if t not in METADATA:
            _note_overlap(P, cs)
        if t in ignorable:
            continue
        P.check_keys.add(key)
        if st == 'identical':
            keep, gone = _keep(cs, droppable, is_active, winner=False)
            if any(c.pkg in P.protected for c in cs):          # what protection costs
                alt = _keep(cs, changeable, is_active, winner=False)[1]
                P.counts['protection_kept_copies'] += len(alt) - len(gone)
                P.counts['protection_kept_bytes'] += sum(c.fsize for c in alt) - sum(c.fsize for c in gone)
        elif st == 'conflict' and policy == 'winner' and len({c.pkg for c in cs}) == len(cs):
            keep, gone = _keep(cs, droppable, is_active, winner=True)
        else:
            continue
        if not gone:
            if st == 'identical' and len(cs) > 1:
                bt['identical_nothing_droppable'] += 1
            continue
        P.touched.add(key)
        for c in gone:
            drops[c.pkg].append(c)
        keepers.update(c.pkg for c in keep)

    for pid, cs in drops.items():
        pp = PackagePlan(pkgs[pid])
        pp.drop = {(c.key[0], c.key[1], c.key[2], c.off) for c in cs}
        pp.drop_bytes = sum(c.fsize for c in cs)
        rows = lib.entries(pid)            # (t, g, i signed, off, fsize, msize, comp) in index order
        where = Counter((r[0], r[1], unsigned64(r[2]), r[3]) for r in rows)
        kept = [r for r in rows if (r[0], r[1], unsigned64(r[2]), r[3]) not in pp.drop]
        pp.kept_n = len(kept)
        pp.has_manifest = any(r[0] == MANIFEST_TYPE for r in rows)
        real = [r for r in kept if r[0] not in ignorable]
        left_types = {r[0] for r in kept}
        if any(where[d] > 1 for d in pp.drop):
            pp.action = 'skip'
            pp.reason = 'two index entries of one dropped key point at the same bytes; they cannot be told apart'
        elif not real:
            pp.action = 'quarantine'
            pp.only_metadata_left = sorted(tname(t) for t in left_types)
        elif len({(r[0], r[1], r[2]) for r in kept}) < len(kept):
            pp.action = 'skip'
            pp.reason = 'the file holds one key twice and both copies would stay (the package writer cannot)'
        else:
            pp.action = 'rewrite'
            pp.new_size = 96 + sum(r[4] for r in kept) + 4 + 32 * len(kept)
            if left_types <= set(METADATA):
                pp.only_metadata_left = sorted(tname(t) for t in left_types)
        P.packages[pid] = pp
    for pp in P.packages.values():
        if pp.action != 'skip':
            for c in drops[pp.id]:
                P.by_type[c.key[0]]['copies_dropped'] += 1
                P.by_type[c.key[0]]['bytes_dropped'] += c.fsize
    P.keepers = {pid: (pkgs[pid].path, pkgs[pid].size, pkgs[pid].mtime) for pid in keepers}
    return P


def _same_content(a, b):
    if a.raw is not None and (a.raw, a.comp) == (b.raw, b.comp):
        return True
    if a.data is not None and b.data is not None:
        return a.data == b.data
    return None


def _note_overlap(P, cs):
    """Count keys a standalone protected package (a script companion, not itself an S4S merge) shares with
    an S4S-merged package: script tuning that was merged into a CC pack, possibly an older version."""
    prot = [c for c in cs if c.pkg in P.protected and c.pkg not in P.merged]
    if not prot:
        return
    for pc in prot:
        for oc in cs:
            if oc.pkg == pc.pkg or oc.pkg not in P.merged:
                continue
            e = P.overlap[(pc.pkg, oc.pkg)]
            e['shared'] += 1
            same = _same_content(pc, oc)
            if same is None:
                e['undecidable'] += 1
            elif same:
                e['identical'] += 1
            else:
                e['differing'] += 1
                if oc.pos < pc.pos:
                    e['differing_merged_copy_loads_first'] += 1


# ---------------------------------------------------------------------------------------------- report
def _apply_order(plan):
    """Packages in the order apply() handles them: quarantines (no new file) first, then the rewrites that
    save the most per byte written, so a run cut short by free space gets the most done."""
    return plan.actions('quarantine') + sorted(plan.actions('rewrite'), key=lambda pp: -pp.saved / max(pp.new_size, 1))


def _read_only(path):
    """True if the file has the read-only attribute (False if it cannot be read)."""
    try:
        st = os.stat(path)
    except OSError:
        return False
    attrs = getattr(st, 'st_file_attributes', None)
    return bool(attrs & stat.FILE_ATTRIBUTE_READONLY) if attrs is not None else not os.access(path, os.W_OK)


def _move_problem(pp, journal_home):
    """Why pp's original cannot be moved into the quarantine, or None. Across drives shutil.move copies the
    file and then deletes it, and Windows refuses to delete a read-only file (the move would fail half-way,
    leaving both copies; 210 of the 627 library packages are read-only). On the same drive it is a rename,
    which works for read-only files."""
    if _drive(journal_home) != _drive(pp.path) and _read_only(pp.path):
        return ('read-only file: a quarantine on another drive (%s) cannot move it; clear its read-only attribute '
                'or keep the quarantine on %s' % (_drive(journal_home), _drive(pp.path)))
    return None


def _space_problem(pp, journal_home, min_free, free):
    """Why pp cannot be done with the free space in `free` ({drive: bytes}), or None. The new file needs
    room on the package's drive; a quarantine on another drive needs room for the original there."""
    d, q = _drive(pp.path), _drive(journal_home)
    need = pp.new_size if pp.action == 'rewrite' else 0
    if need and free[d] - need < min_free:
        return 'not enough free space on %s (%.1f GB free, needs %.1f GB + %.1f GB margin)' % (
            d, free[d] / 1e9, need / 1e9, min_free / 1e9)
    if q != d and free[q] - pp.size < min_free:
        return 'not enough free space for the quarantine on %s (%.1f GB free, needs %.1f GB + %.1f GB margin)' % (
            q, free[q] / 1e9, pp.size / 1e9, min_free / 1e9)
    return None


def free_space(plan, lib, min_free=MIN_FREE, journal_home=None):
    """Disk space an apply() of this plan needs, and how far one run gets with the space free now.

    journal_home: where the quarantine goes (default <Sims 4 folder>/SpeedKit, the same drive as Mods).
    Returns {'drives': {drive: free bytes}, 'quarantine_home', 'quarantine_on_same_drive',
    'new_files_bytes', 'largest_new_file', 'quarantined_originals_bytes', 'peak_growth_of_mods_drive',
    'saved_after_quarantine_emptied', 'one_run_with_current_free_space': {...}}. With the quarantine on
    the Mods drive every rewritten file adds its full new size until the quarantine is emptied; on another
    drive the Mods drive only needs room for the largest new file."""
    home = journal_home or os.path.join(sims_folder(lib, plan.roots) or SIMS, 'SpeedKit')
    todo = _apply_order(plan)
    rw = [pp for pp in todo if pp.action == 'rewrite']
    free = {}
    for path in [home] + [lib.roots[r] for r in plan.roots if r in lib.roots] + [pp.path for pp in todo]:
        d = _drive(path)
        if d not in free:
            free[d] = _free(path)
    now = dict(free)
    same = all(_drive(lib.roots[r]) == _drive(home) for r in plan.roots if r in lib.roots)
    done = rewrites = saved = 0
    skipped = []
    read_only = []
    for pp in todo:                                     # the same checks apply() makes, in its order
        if _move_problem(pp, home):
            read_only.append(pp.name)
            continue
        if _space_problem(pp, home, min_free, free):
            skipped.append(pp.name)
            continue
        d, q = _drive(pp.path), _drive(home)
        if pp.action == 'rewrite':
            free[d] -= pp.new_size
            rewrites += 1
        if q != d:
            free[d] += pp.size
            free[q] -= pp.size
        done += 1
        saved += pp.saved
    new = sum(pp.new_size for pp in rw)
    largest = max((pp.new_size for pp in rw), default=0)
    return {'drives': now, 'quarantine_home': home, 'quarantine_on_same_drive': same,
            'new_files_bytes': new, 'largest_new_file': largest,
            'quarantined_originals_bytes': sum(pp.size for pp in todo),
            'peak_growth_of_mods_drive': new if same else largest,
            'saved_after_quarantine_emptied': sum(pp.saved for pp in todo),
            'one_run_with_current_free_space': {'min_free': min_free, 'packages_done': done, 'of': len(todo),
                                                'rewrites_done': rewrites, 'rewrites': len(rw), 'saved_bytes': saved,
                                                'skipped_for_space': len(skipped),
                                                'skipped_read_only_across_drives': len(read_only)}}


def report(plan, lib, top=25, journal_home=None):
    """What the plan found and would do, as a dict: removable identical copies/bytes, packages that become
    empty, conflicting keys (by type, by package pair), stale script-mod tuning copies inside CC merges,
    the metadata keys ignored (S4S manifest / NameMap), undecidable keys and free-space needs."""
    name = lambda pid: plan.names.get(pid, str(pid))
    out = {'summary': plan.summary()}
    bt = [{'type': tname(t), 'keys': c['keys'], 'identical': c['identical'], 'conflict': c['conflict'],
           'undecidable': c['undecidable'], 'copies_dropped': c['copies_dropped'], 'bytes_dropped': c['bytes_dropped']}
          for t, c in sorted(plan.by_type.items(), key=lambda kv: -kv[1]['bytes_dropped'])]
    out['removable_by_type'] = bt[:top]
    q = plan.actions('quarantine')
    out['packages_becoming_empty'] = [{'package': pp.name, 'size': pp.size, 'resources': pp.n,
                                       'left_only': pp.only_metadata_left} for pp in q]
    rw = plan.actions('rewrite')
    out['packages_rewritten_top'] = [pp.to_dict() for pp in rw[:top]]
    out['packages_skipped'] = [pp.to_dict() for pp in plan.actions('skip')]
    # conflicts
    ctype = Counter()
    pairs = Counter()
    for key, cv in plan.conflicts.items():
        if key[0] == MANIFEST_TYPE:
            continue
        ctype[tname(key[0])] += 1
        byp = defaultdict(set)
        for pid, v in cv:
            byp[pid].add(v)
        ps = sorted(byp, key=name)
        for a in range(len(ps)):
            for b in range(a + 1, len(ps)):
                if byp[ps[a]] != byp[ps[b]]:
                    pairs[(ps[a], ps[b])] += 1
    out['conflicts'] = {
        'keys': sum(ctype.values()), 'by_type': dict(ctype.most_common()), 'package_pairs': len(pairs),
        'by_package_pair': [{'a': name(a), 'b': name(b), 'keys': n} for (a, b), n in pairs.most_common(top)],
        'note': 'under the identical policy nothing is removed for these keys; the first-loaded copy is what the game uses'}
    out['stale_script_copies_in_merges'] = stale_script_copies(plan, lib, top)
    # metadata
    man = plan.by_type.get(MANIFEST_TYPE, Counter())
    nm = plan.by_type.get(NAMEMAP, Counter())
    out['ignored_metadata_keys'] = {
        'S4S merge manifest (7FB6AD8A)': {
            'merged_packages': len(plan.merged), 'duplicated_keys': man['keys'],
            'rewritten_packages_with_manifest': sum(pp.has_manifest for pp in rw),
            'handling': 'never deduplicated; rewritten without the removed keys; ignored when deciding that a '
                        'package is empty and in the before/after check (the game never reads it)'},
        'NameMap (0166038C)': {
            'duplicated_keys': nm['keys'], 'ignored': plan.ignore_namemap,
            'packages_left_with_only_metadata': [pp.name for pp in rw if pp.only_metadata_left],
            'handling': ('treated like the manifest' if plan.ignore_namemap else
                         'kept as ordinary content (whether the game reads CC NameMaps is unknown); packages '
                         'listed above would become empty with ignore_namemap=True')},
    }
    out['undecidable_keys'] = [{'key': '%08X:%08X:%016X' % k, 'copies': [{'package': name(p), 'error': e} for p, e in v]}
                               for k, v in list(plan.undecidable.items())[:top]]
    out['index_problems'] = plan.index_problems[:top]
    out['in_more_than_one_root'] = shadowed_paths(lib, plan.roots)[:top]
    out['free_space'] = free_space(plan, lib, journal_home=journal_home)
    return out


def _merge_sources(path):
    """{source name: set of (t, g, i)} from a package's S4S manifest ({} if it has none or it is unreadable)."""
    try:
        with Package(path) as p:
            e = next((e for e in p.entries if e.t == MANIFEST_TYPE), None)
            return {} if e is None else sources_of(manifest_payload(p.raw(e), e.comp, e.msize))
    except Exception:
        return {}


def _same_name(a, b):
    """True if two package / merge-source names are the same file name (case, punctuation, '.package' ignored)."""
    def norm(s):
        s = s.rsplit('/', 1)[-1]
        s = s[:-len('.package')] if s.lower().endswith('.package') else s
        return ''.join(ch for ch in s.lower() if ch.isalnum())
    return norm(a) == norm(b)


def stale_script_copies(plan, lib, top=25):
    """Keys a standalone protected package (script companion) shares with S4S merges.

    Per (companion, merge) pair: keys shared, identical (the identical policy drops the merge's copy unless
    the merge is protected), differing (kept; the game uses whichever loads first) and the merge sources
    that carry them. 'same_file' pairs are merges holding a copy of the companion file itself (e.g. an old
    WickedWhims tuning inside sim/m27): their differing keys are stale versions. The other pairs are other
    mods' files that override the companion's keys. NameMap and manifest keys are not counted."""
    comp_keys = {}
    srcs = {}
    rows = []
    for (pc, mp), c in plan.overlap.items():
        if pc not in comp_keys:
            comp_keys[pc] = {(t, g, unsigned64(i)) for t, g, i, *_ in lib.entries(pc)}
        if mp not in srcs:
            srcs[mp] = _merge_sources(lib.path(*plan.names[mp].split('/', 1)))
        sources = Counter({n: len(keys & comp_keys[pc]) for n, keys in srcs[mp].items()})
        sources = {k: v for k, v in sources.most_common(3) if v}
        rows.append({'companion': plan.names.get(pc), 'merge': plan.names.get(mp),
                     'same_file': any(_same_name(n, plan.names.get(pc, '')) for n in sources),
                     'shared_keys': c['shared'], 'identical': c['identical'], 'differing': c['differing'],
                     'differing_where_merge_loads_first': c['differing_merged_copy_loads_first'],
                     'undecidable': c['undecidable'], 'merge_protected': mp in plan.protected,
                     'merge_sources': sources})
    same = sorted((r for r in rows if r['same_file']), key=lambda r: (-r['differing'], -r['shared_keys']))
    other = sorted((r for r in rows if not r['same_file']), key=lambda r: (-r['differing'], -r['shared_keys']))
    return {'pairs': len(rows), 'same_file_pairs': len(same),
            'same_file_differing_keys': sum(r['differing'] for r in same),
            'same_file_identical_keys': sum(r['identical'] for r in same),
            'other_mod_overrides_keys': sum(r['differing'] for r in other),
            'same_file': same[:top], 'other_mod_overrides': other[:top]}


# ---------------------------------------------------------------------------------------------- apply
def rewrite_package(pp, check_keys=(), cache=None):
    """Write pp's package without the dropped copies to <path>.speedkit-dedup (via '.writing') and verify
    it: same keys in the same order, every kept resource byte-identical to the original, the S4S manifest
    equal to the expected rewrite. Returns (tmp_path, stats). Raises DedupError (temp file removed) on
    any mismatch. With a HashCache, raw hashes of the new file's copies of `check_keys` are cached."""
    tmp = pp.path + TMP_SUFFIX
    for leftover in (tmp, tmp + '.writing'):
        if os.path.exists(leftover):
            raise DedupError('a temporary file from an earlier run is in the way: %s' % leftover)
    with Package(pp.path) as src:
        entries = src.entries
        kept = [e for e in entries if (e.t, e.g, e.i, e.off) not in pp.drop]
        if len(entries) - len(kept) != len(pp.drop):
            raise DedupError('%s: the index does not match the plan' % pp.name)
        removed = {(t, g, i) for t, g, i, _ in pp.drop} - {key_of(e) for e in kept}
        new_manifest = {}
        try:
            with PackageWriter(tmp) as w:
                for e in kept:
                    if e.t == MANIFEST_TYPE and removed:
                        try:
                            old = manifest_payload(src.raw(e), e.comp, e.msize)
                            data = manifest_without(old, removed)
                        except Exception:
                            old = data = None       # unreadable manifest: keep it as it is
                        if data != old:
                            w.add(key_of(e), data)
                            new_manifest[key_of(e)] = data
                            continue
                    w.add_raw(e, src.raw(e))
        except BaseException:
            if os.path.exists(tmp + '.writing'):    # PackageWriter.close() failed half-way (e.g. disk full)
                os.remove(tmp + '.writing')
            raise
        try:
            stats = _verify_rewrite(pp, src, kept, tmp, new_manifest, set(check_keys), cache)
        except BaseException:
            os.remove(tmp)
            raise
    return tmp, stats


def _verify_rewrite(pp, src, kept, tmp, new_manifest, check_keys, cache):
    rows = []
    st = os.stat(tmp)
    nbytes = 0
    with Package(tmp) as new:
        if len(new.entries) != len(kept):
            raise DedupError('%s: new file has %d resources, expected %d' % (pp.name, len(new.entries), len(kept)))
        for a, b in zip(kept, new.entries):
            k = key_of(a)
            if k != key_of(b):
                raise DedupError('%s: resource order differs at %08X:%08X:%016X' % ((pp.name,) + k))
            if k in new_manifest:
                if manifest_payload(new.raw(b), b.comp, b.msize) != new_manifest[k]:
                    raise DedupError('%s: rewritten S4S manifest does not read back' % pp.name)
                continue
            if (a.fsize, a.msize, a.comp, a.committed) != (b.fsize, b.msize, b.comp, b.committed):
                raise DedupError('%s: index entry of %08X:%08X:%016X changed' % ((pp.name,) + k))
            ra, rb = src.raw(a), new.raw(b)
            if ra != rb:
                raise DedupError('%s: bytes of %08X:%08X:%016X differ after rewriting' % ((pp.name,) + k))
            nbytes += len(rb)
            if cache is not None and k in check_keys:
                raw = digest(rb)
                rows.append((pp.root, pp.rel, st.st_size, st.st_mtime, b.t, b.g, signed64(b.i), b.off, b.comp,
                             raw, cache.data_of(raw, b.comp), None))
    if cache is not None and rows:
        cache.store(rows)
    return {'resources': len(kept), 'bytes_verified': nbytes, 'size': st.st_size,
            'manifest_rewritten': bool(new_manifest)}


def _scopes(plan):
    return [plan.roots] + ([(plan.active,)] if plan.active else [])


def _snapshot_keys(lib, plan, todo):
    """Remember every key of the packages about to change, per scope, to check none disappears. Packages are
    looked up by path in the current index (a rescan since the plan gives them new ids)."""
    db = lib.db
    db.execute('drop table if exists temp.dd_before')
    db.execute('create temp table dd_before(scope integer, t integer, g integer, i integer, primary key(scope, t, g, i))')
    ign = tuple(plan.ignorable())
    ids = {(r, rel): pid for pid, r, rel in db.execute('select id, root, rel from pkg')}
    for n, scope in enumerate(_scopes(plan)):
        for pp in todo:
            pid = ids.get((pp.root, pp.rel))
            if pp.root in scope and pid is not None:
                db.execute('insert or ignore into temp.dd_before select ?, t, g, i from res where pkg=? and comp!=? '
                           'and t not in (%s)' % ','.join('?' * len(ign)), (n, pid, DELETED) + ign)


def _missing_keys(lib, plan, limit=50):
    """Keys remembered by _snapshot_keys that no loaded package of their scope holds any more."""
    out = []
    for n, scope in enumerate(_scopes(plan)):
        lib.db.execute('drop table if exists temp.dd_loaded')
        lib.db.execute('create temp table dd_loaded(pkg integer primary key)')
        lib.db.executemany('insert into temp.dd_loaded values(?)', ((p,) for p in lib.order_positions(scope)))
        q = """select b.t, b.g, b.i from temp.dd_before b where b.scope = ? and not exists (
                   select 1 from res r join temp.dd_loaded l on l.pkg = r.pkg
                   where r.t = b.t and r.g = b.g and r.i = b.i and r.comp != ?) limit ?"""
        for t, g, i in lib.db.execute(q, (n, DELETED, limit)):
            out.append(('+'.join(scope), (t, g, unsigned64(i))))
    return out


def _effective(lib, plan, cache_path, progress, threads):
    keys = sorted(plan.check_keys)
    return {scope: effective_map(lib, scope, keys, cache_path, progress, threads) for scope in _scopes(plan)}


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


def _free_journal_id(journal_home, kind='dedup', wait=2.0):
    """Wait until the journal id a new Journal would get is unused. Journal ids have one-second resolution
    and speedkit.journal.Journal() silently overwrites an existing journal file with the same id, which
    would lose the earlier run's undo record. The id is built exactly as Journal builds it."""
    deadline = time.time() + wait
    while True:
        jid = _journal_mod.time.strftime('%Y%m%d-%H%M%S') + '-' + kind
        if not (os.path.exists(os.path.join(journal_home, 'journal', jid + '.json'))
                or os.path.exists(os.path.join(journal_home, 'quarantine', jid))):
            return jid
        if time.time() > deadline:
            raise DedupError('journal %s already exists in %s; not overwriting it (try again)' % (jid, journal_home))
        time.sleep(0.2)


def _roll_back(j, journal_home, check_game, lib):
    """Undo journal j after a failure. Returns a sentence for the error message (never raises)."""
    try:
        undo(j.id, home=journal_home, check_game=check_game)
        note = 'journal %s was undone' % j.id
    except Exception as e:
        note = ('journal %s could NOT be undone (%s); every finished step is complete and keeps a copy of every '
                'key - undo it later with: python -m speedkit.dedup undo %s' % (j.id, e, j.id))
    try:
        lib.scan()
    except Exception:
        pass
    return note


def apply(plan, lib, journal_home=None, sims=None, dry_run=True, check_game=True, min_free=MIN_FREE,
          cache_path=None, progress=None, threads=THREADS):
    """Carry out a plan, one package at a time. Dry run by default: returns what would happen.

    Real run (dry_run=False): refuses while TS4_x64.exe runs, if the library index (packages and scripts) is
    not current, or if a package exists in more than one root (see shadowed_paths);
    quarantines packages that become empty and rewrites the others (new file next to the original,
    verified byte for byte, then Journal.replace). Skips a package when a drive would drop below min_free,
    and a read-only package when the quarantine is on another drive (see _move_problem).
    Afterwards it rescans `lib` and checks that, for every duplicated key, the content the game would
    use - with all roots laid over each other and with the active root alone - is unchanged and that no
    key of a changed package has disappeared. If not, it undoes the journal and raises InvariantError.
    Any other failure (a verification mismatch, the game being started, Ctrl+C - also during that check)
    undoes the journal as well.
    sims defaults to the folder holding the library roots (the real Sims 4 folder for the real library; a
    real run refuses if the roots have no common parent and sims is not given); journal_home (journal +
    quarantine) defaults to <sims>/SpeedKit and must not lie inside a library root (the game would load
    the quarantined packages)."""
    t0 = time.time()
    sims = sims or sims_folder(lib, plan.roots)
    journal_home = journal_home or (os.path.join(sims, 'SpeedKit') if sims else None)
    if journal_home and any(_inside(journal_home, base) or _inside(base, journal_home) for base in lib.roots.values()):
        raise DedupError('the journal/quarantine folder %s must not be inside (or hold) a mod folder' % journal_home)
    todo = _apply_order(plan)
    stale_targets = {pp.id: why for pp in todo if (why := _changed(pp.path, pp.size, pp.mtime))}
    stale_keepers = [(path, why) for pid, (path, size, mtime) in plan.keepers.items()
                     if (why := _changed(path, size, mtime))]
    res = {'dry_run': dry_run, 'journal': None, 'journal_home': journal_home, 'quarantined': [], 'rewritten': [],
           'skipped': [], 'bytes_saved_after_emptying_quarantine': 0, 'new_bytes_written': 0,
           'moved_to_quarantine_bytes': 0, 'free_space': free_space(plan, lib, min_free, journal_home),
           'stale_targets': len(stale_targets), 'stale_keepers': stale_keepers[:20]}
    if dry_run:
        res['would_quarantine'] = [pp.to_dict() for pp in todo if pp.action == 'quarantine']
        res['would_rewrite'] = [pp.to_dict() for pp in todo if pp.action == 'rewrite']
        res['index_problems'] = index_problems(lib, plan.roots)[:20]
        return res
    if not sims:
        raise DedupError('the library roots %s have no common parent folder: pass sims= (the Sims 4 folder '
                         'that holds them)' % sorted(lib.roots.values()))
    outside = [pp.path for pp in todo if not _inside(pp.path, sims)]
    if outside:
        raise DedupError('%d packages are outside %s, e.g. %s' % (len(outside), sims, outside[0]))
    if check_game and game_running():
        raise DedupError('The Sims 4 is running - close it first.')
    problems = index_problems(lib, plan.roots)
    if problems or stale_keepers:
        raise DedupError('the library changed since the plan was made (%s) - rescan and plan again'
                         % (problems or stale_keepers)[:3])
    shadowed = shadowed_paths(lib, plan.roots)
    if shadowed:
        raise DedupError('%d packages exist in more than one of %s (e.g. %s); move one copy away first'
                         % (len(shadowed), plan.roots, shadowed[0]))
    before = _effective(lib, plan, cache_path, progress, threads)
    unread = [(s, k, v) for s, m in before.items() for k, v in m.items() if v and v.startswith('error:')]
    if unread:
        raise DedupError('cannot read %d copies the check depends on, e.g. %r - nothing was changed' % (len(unread), unread[:3]))
    _snapshot_keys(lib, plan, todo)
    _free_journal_id(journal_home)
    j = Journal('dedup', '%s policy: %d packages' % (plan.policy, len(todo)), home=journal_home, sims=sims,
                check_game=check_game)
    res['journal'] = j.id
    cache = HashCache(cache_path)
    tmp = None
    try:
        for n, pp in enumerate(todo):
            if progress:
                progress('apply', n, len(todo), pp.name)
            why = stale_targets.get(pp.id) or _changed(pp.path, pp.size, pp.mtime)
            if why:
                res['skipped'].append((pp.name, why))
                continue
            if check_game and game_running():
                raise DedupError('The Sims 4 was started - stopped after %d of %d packages' % (n, len(todo)))
            free = {d: _free(p) for d, p in ((_drive(pp.path), pp.path), (_drive(journal_home), journal_home))}
            why = _move_problem(pp, journal_home) or _space_problem(pp, journal_home, min_free, free)
            if why:
                res['skipped'].append((pp.name, why))
                continue
            if pp.action == 'quarantine':
                j.quarantine(pp.path)
                res['quarantined'].append(pp.name)
                new_size = 0
            else:
                tmp, st = rewrite_package(pp, plan.check_keys, cache)
                j.replace(tmp, pp.path)
                tmp = None
                res['rewritten'].append(pp.name)
                res['new_bytes_written'] += st['size']
                new_size = st['size']
            res['moved_to_quarantine_bytes'] += pp.size
            res['bytes_saved_after_emptying_quarantine'] += pp.size - new_size
        j.close('committed')
    except BaseException as e:
        cache.close()
        if tmp and os.path.exists(tmp):
            os.remove(tmp)               # our own unfinished new file, never put in place
        j.close('failed: %s' % e)
        note = _roll_back(j, journal_home, check_game, lib)
        if not isinstance(e, Exception):
            raise                        # Ctrl+C / exit: rolled back, pass it on
        raise DedupError('%s; %s' % (e, note)) from e
    cache.close()
    try:
        lib.scan()
        after = _effective(lib, plan, cache_path, progress, threads)
        changed = _diff(before, after)
        missing = _missing_keys(lib, plan)
    except BaseException as e:
        note = _roll_back(j, journal_home, check_game, lib)       # the check could not be made: undo
        if not isinstance(e, Exception):
            raise
        raise DedupError('the check after the run failed (%s); %s' % (e, note)) from e
    res['invariant'] = {'keys_compared': len(plan.check_keys), 'scopes': ['+'.join(s) for s in before],
                        'changed': changed, 'missing': missing}
    if changed or missing:
        note = _roll_back(j, journal_home, check_game, lib)
        restored = _diff(before, _effective(lib, plan, cache_path, progress, threads))
        raise InvariantError('the game would load different content after dedup (%d changed, %d missing, e.g. %r); '
                             '%s%s' % (len(changed), len(missing), (changed or missing)[:3], note,
                                       '' if not restored else ' BUT %d keys still differ' % len(restored)))
    res['seconds'] = round(time.time() - t0, 1)
    return res


# ---------------------------------------------------------------------------------------------- CLI
def main():
    import argparse
    from .library import Library, DEFAULT_DB
    from .journal import HOME
    try:
        sys.stdout.reconfigure(errors='replace')      # package names hold characters the console cannot show
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description='Find and remove duplicate resources in the Sims 4 mod library.')
    ap.add_argument('command', choices=('report', 'apply', 'undo', 'journals'))
    ap.add_argument('journal', nargs='?', help='journal id for undo')
    ap.add_argument('--db', default=DEFAULT_DB, help='library index')
    ap.add_argument('--scan', action='store_true', help='bring the library index up to date first')
    ap.add_argument('--policy', default='identical', choices=POLICIES)
    ap.add_argument('--roots', default=','.join(DEFAULT_ROOTS))
    ap.add_argument('--ignore-namemap', action='store_true')
    ap.add_argument('--unprotect-merges', action='store_true',
                    help='let S4S merges that only hold stale copies of standalone script-mod files lose their identical copies')
    ap.add_argument('--cache', default=None, help='hash cache (default data/hash.sqlite)')
    ap.add_argument('--companions-cache', default=None, help='speedkit.companions cache (default data/companions.sqlite)')
    ap.add_argument('--journal-home', default=None,
                    help='journal and quarantine folder (default <Sims 4 folder>\\SpeedKit; another drive keeps C: free)')
    ap.add_argument('--min-free-gb', type=float, default=MIN_FREE / (1 << 30))
    ap.add_argument('--json', help='write the full report here')
    ap.add_argument('--really', action='store_true', help='apply: change files (otherwise a dry run)')
    a = ap.parse_args()
    if a.command == 'journals':
        for row in list_journals(a.journal_home or HOME):
            print('  %s  %-8s %-12s %3d steps  %s' % row)
        return
    if a.command == 'undo':
        for act in undo(a.journal, home=a.journal_home or HOME):
            print('  %s: %s' % act)
        return
    lib = Library(a.db)
    if a.scan:
        lib.scan(verbose=True)
    last = [0.0]

    def progress(label, done, total, *rest):
        if time.time() - last[0] > 5 or done == total:
            last[0] = time.time()
            print('  %-9s %d/%d' % (label, done, total), flush=True)
    p = plan(lib, tuple(a.roots.split(',')), a.policy, ignore_namemap=a.ignore_namemap, cache_path=a.cache,
             progress=progress, include_merged=not a.unprotect_merges, companions_cache=a.companions_cache)
    rep = report(p, lib, journal_home=a.journal_home)
    if a.json:
        with open(a.json, 'w', encoding='utf-8') as f:
            json.dump(rep, f, indent=1, default=str)
    for k, v in rep['summary'].items():
        print('%-40s %s' % (k, v))
    fs = rep['free_space']
    run = fs['one_run_with_current_free_space']
    print('quarantine in %s (%s drive); the Mods drive grows by up to %.1f GB until the quarantine is emptied; '
          'free: %s' % (fs['quarantine_home'], 'same' if fs['quarantine_on_same_drive'] else 'another',
                        fs['peak_growth_of_mods_drive'] / 1e9, {d: '%.1f GB' % (b / 1e9) for d, b in fs['drives'].items()}))
    print('one run with the space free now: %d of %d packages (%d of %d rewrites), saving %.1f GB; %d skipped for '
          'space, %d read-only files skipped (quarantine on another drive)'
          % (run['packages_done'], run['of'], run['rewrites_done'], run['rewrites'], run['saved_bytes'] / 1e9,
             run['skipped_for_space'], run['skipped_read_only_across_drives']))
    if a.command == 'apply':
        r = apply(p, lib, journal_home=a.journal_home, dry_run=not a.really, cache_path=a.cache, progress=progress,
                  min_free=int(a.min_free_gb * (1 << 30)))
        print(json.dumps({k: v for k, v in r.items() if k not in ('would_quarantine', 'would_rewrite')}, indent=1, default=str))


if __name__ == '__main__':
    main()
