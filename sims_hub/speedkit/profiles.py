"""One-click Mods profiles - 'full', 'fast', 'studio', 'save' - that live side by side with the other chat's
mods_switch.py (C:\\Users\\basim\\Tools\\sims4_fitstudio\\mods_switch.py).

    from speedkit import profiles
    profiles.switch('fast')                    # dry run: what would move (nothing changes)
    profiles.switch('fast', dry_run=False)     # do it (refuses while The Sims 4 runs)
    profiles.current()                         # which profile the folders match, or 'custom' + differences
    print(profiles.format_status(profiles.status()))

Profiles
  full    every mod is in Mods.
  fast    everything except speedkit.fastmode.park_set(lib) (the CAS-heavy CC catalogs), plus the fast
          pack ('!!!!!SpeedKit_Fast_NNN.package' from SIMS\\SpeedKit\\fastpack) placed at the Mods root.
          The switch first makes sure the pack is fresh (fastmode.status / update_pack) and refuses
          if it cannot be: without the pack, sims would lose CC they wear.
  studio  exactly what mods_switch.py keeps in 'lean': its KEEP list, imported from that file at run
          time (a built-in copy when the file is missing or unreadable).
  save    'Play this save' (switch('save', save_slot='Slot_00000014')): the same packages as 'fast' are
          parked, and instead of the fast pack the save pack of that one save
          ('!!!!!SpeedKit_Save_00000014_NNN.package' from SIMS\\SpeedKit\\savepacks\\Slot_00000014, see
          speedkit.savepacks) sits at the Mods root: only the CC that save's sims and lots use, plus the
          script/tuning/animation/default-replacement content the fast pack also carries.
Mods\\SpeedKit_Monitor.ts4script is kept at the Mods root in every profile (and brought back when the
other tool parked it). Every pack that is not the profile's own goes back to its folder: the fast pack to
SIMS\\SpeedKit\\fastpack, a save pack to SIMS\\SpeedKit\\savepacks\\<slot>.

Shared parking store (so both tools stay consistent)
  * A parked file lives in Mods_parked at the same relative path it has in Mods.
  * Mods_parked\\_manifest.json = {"moved": [rel paths relative to Mods, folders end with '/']} lists
    every parked path, in the form mods_switch.py's 'full' can restore: 'dir/' only when the folder
    does not exist in Mods (else 'full' would skip it), individual files otherwise. Entries SpeedKit did
    not create stay as they are while they are still valid; entries for paths that are back in Mods
    are dropped (exactly what 'full' does); an entry that points nowhere is kept; a 'dir/' entry that
    no longer fits is split into the entries for what is still parked below it; parked files that no
    entry covers are added. Other keys of the document are kept.
  * A damaged manifest (not JSON, not {"moved": [...]}, entries with '..' or drive letters) makes
    every change refuse with a plain message instead of guessing.
  * The folders a switch emptied are removed when empty (os.rmdir cannot remove anything with
    content); an emptied folder left in Mods_parked would make its 'lean' skip that folder, one left
    in Mods would block a 'dir/' entry. Empty folders that were there before are left alone, and a
    parked folder with nothing in it comes back in 'full' (so 'full' leaves the list empty, as the
    other tool's 'full' does).

Every change goes through one Journal of kind 'profile' (same-drive renames; nothing is deleted):
the moves, the fast pack, the manifest (quarantine old + put the new one, written complete
beforehand, in place with os.replace) and SIMS\\SpeedKit\\profile_state.json {"profile", "switched"}.
So undo_switch(<id>) puts the folders, the manifest and the state file back exactly and removes the
folders the switch had created that are empty again. localthumbcache.package (quarantined when the
loaded CC set changed - the game rebuilds it) goes through its own small 'profile' journal opened
just before, so a cache the game rebuilt after the switch never blocks undoing the switch. If a step
fails half-way (Ctrl+C included), both are undone automatically. A .ts4script and the companion packages that ship
with it (companions.classify: 'core' in the same folder) always end up on the same side, and a
package that needs a script ('core'/'addon') is never kept while its script is parked - the fix is
always to keep more, never to park more. Relative paths never change, so a script never gets deeper.

Scratch/bookkeeping written directly (not game data): SIMS\\SpeedKit\\profiles\\last_<profile>.json
(the parked set of the last switch, used by current() when fastmode is not importable) and the
staging copies of the manifest/state files.
"""
import datetime
import importlib.util
import inspect
import json
import os
import re
import sys
from collections import namedtuple

from .library import SIMS, game_running
from .journal import Journal, JournalError, list_journals, undo as journal_undo

PROFILES = ('full', 'fast', 'studio', 'save')
MODS_SWITCH = r'C:\Users\basim\Tools\sims4_fitstudio\mods_switch.py'
# mods_switch.py's KEEP list as of 2026-09-24 (used only when that file cannot be imported)
BUILTIN_KEEP = [
    'Resource.cfg',
    'desktop.ini',
    'scripts/TURBODRIVER_WickedWhims_Scripts.ts4script',
    'scripts/TURBODRIVER_WickedWhims_Tuning.package',
    'scripts/desktop.ini',
    'animation/WW_LAMABOY_Animation.package',
    'animation/WW_LAMABOY_Animations.package',
    'animation/desktop.ini',
    'FitStudio/',
]
MONITOR = 'SpeedKit_Monitor.ts4script'
PACK_PREFIX = '!!!!!speedkit_fast_'         # '!!!!!SpeedKit_Fast_001.package' ... (lower-cased match)
# exactly the names speedkit.fastmode writes (its _PACK_RX): a user's '!!!!!SpeedKit_Fast_001 - Copy.package'
# is ordinary CC, not the pack
PACK_RX = re.compile(r'^!!!!!speedkit_fast_\d{3}\.package$', re.I)
# the save packs of speedkit.savepacks: '!!!!!SpeedKit_Save_<the slot's 8 hex digits>_###.package' (fastmode's
# _SAVE_PACK_RX); the slot in the name says which SpeedKit\savepacks\<slot> folder a file belongs to
SAVE_PACK_RX = re.compile(r'^!!!!!speedkit_save_([0-9a-f]{8})_\d{3}\.package$', re.I)
SLOT_RX = re.compile(r'^slot_([0-9a-f]{8})$', re.I)
SAVEPACKS = 'savepacks'
MANIFEST = '_manifest.json'
OLD_CACHES = '_old_caches'                  # the other tool's parked thumbnail caches: never mods
PARKED_SKIP_FILES = {'_manifest.json', '_manifest.json.tmp'}
MOD_EXTS = ('.package', '.ts4script')
THUMBCACHE = 'localthumbcache.package'
# safety net on top of fastmode.park_set: the other chat's own mod and the WickedWhims animation packs
FAST_NEVER_PARK = ('fitstudio', 'animation')
SHOW = 40                                   # how many paths a difference list shows


class ProfileError(Exception):
    """A switch was refused or failed; the message is meant for the user."""


# ------------------------------------------------------------------ small helpers
def _norm_rel(rel):
    return rel.replace('\\', '/').strip('/')


def _key(rel):
    """Case-insensitive identity of a relative path (NTFS names are case-insensitive)."""
    return _norm_rel(rel).lower()


def _parent(key):
    return key.rsplit('/', 1)[0] if '/' in key else ''


def _ancestors(key):
    parts = key.split('/')
    return ['/'.join(parts[:i]) for i in range(1, len(parts))]


def _under(key, d):
    return key == d or key.startswith(d + '/')


def _is_mod(rel):
    return rel.lower().endswith(MOD_EXTS)


def _is_pack_name(name):
    return bool(PACK_RX.match(name))


def _save_family(name):
    """'save:<hex>' for a save pack file name, else None."""
    m = SAVE_PACK_RX.match(name)
    return 'save:' + m.group(1).lower() if m else None


def _pack_family(name):
    """'fast' / 'save:<hex>' for a SpeedKit pack file name at a root, else None."""
    return 'fast' if _is_pack_name(name) else _save_family(name)


def slot_key(slot):
    """'Slot_<hex>' (lower-case hex, as the game names its files) for 'Slot_00000014', 'slot_00000014.save',
    a path, or 'save:Slot_...'; ProfileError when it is not a save slot."""
    s = (slot or '').strip()
    if s.lower().startswith('save:'):
        s = s[5:]
    s = os.path.basename(s.replace('/', os.sep))
    if s.lower().endswith('.save'):
        s = s[:-5]
    m = SLOT_RX.match(s)
    if not m:
        raise ProfileError('%r is not a save slot (expected Slot_ and 8 hex digits, like Slot_00000014)' % (slot,))
    return 'Slot_' + m.group(1).lower()


def _family_of_slot(slot):
    return 'save:' + slot_key(slot)[5:]


def _is_monitor_name(name):
    return name.lower() == MONITOR.lower()


def _gb(b):
    return b / 1e9


def _now_iso():
    return datetime.datetime.now().isoformat(timespec='seconds')


class Paths:
    """Every location a profile switch touches, derived from the Sims 4 folder."""

    def __init__(self, sims=SIMS, home=None, fastpack=None):
        self.sims = sims
        self.mods = os.path.join(sims, 'Mods')
        self.parked = os.path.join(sims, 'Mods_parked')
        self.manifest = os.path.join(self.parked, MANIFEST)
        self.home = home or os.path.join(sims, 'SpeedKit')
        self.fastpack = fastpack or os.path.join(self.home, 'fastpack')
        self.state = os.path.join(self.home, 'profile_state.json')
        self.records = os.path.join(self.home, 'profiles')
        self.thumbcache = os.path.join(sims, THUMBCACHE)
        self.savepacks = os.path.join(self.home, SAVEPACKS)

    def save_dir(self, slot):
        """SpeedKit\\savepacks\\<slot>: where a save pack lives while it is not in Mods."""
        return os.path.join(self.savepacks, slot_key(slot))

    def family_home(self, fam):
        """The folder a pack family goes back to: the fastpack folder, or savepacks\\Slot_<hex>."""
        return self.fastpack if fam == 'fast' else os.path.join(self.savepacks, 'Slot_' + fam.split(':', 1)[1])

    def root(self, side):
        return self.mods if side == 'M' else self.parked

    def path(self, side, rel):
        return os.path.join(self.root(side), _norm_rel(rel).replace('/', os.sep))


# ------------------------------------------------------------------ mods_switch.py's KEEP list
_KEEP_CACHE = {}


def load_keep(path=MODS_SWITCH):
    """(KEEP list, source): mods_switch.py's KEEP, imported from the file (its code only defines
    constants and functions; its main block does not run on import), else the built-in copy."""
    try:
        st = os.stat(path)
    except OSError:
        return list(BUILTIN_KEEP), 'built-in copy (%s not found)' % path
    ck = (os.path.normcase(os.path.abspath(path)), st.st_size, st.st_mtime)
    if ck in _KEEP_CACHE:
        return list(_KEEP_CACHE[ck]), path
    try:
        spec = importlib.util.spec_from_file_location('_speedkit_mods_switch_keep', path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        keep = getattr(mod, 'KEEP')
        if not isinstance(keep, (list, tuple)) or not keep or not all(isinstance(k, str) and k.strip() for k in keep):
            raise ValueError('KEEP is not a list of paths')
    except (Exception, SystemExit) as e:        # a broken or changed file must not break SpeedKit
        return list(BUILTIN_KEEP), 'built-in copy (could not read KEEP from %s: %s)' % (path, e)
    _KEEP_CACHE[ck] = [k.replace('\\', '/') for k in keep]
    return list(_KEEP_CACHE[ck]), path


def keep_matcher(keep):
    """kept(rel) -> True if mods_switch.py's 'lean' keeps rel ('dir/' keeps everything inside).
    Case-insensitive (mods_switch.py compares exact strings; on NTFS both name the same file)."""
    dirs = [k.lower() for k in keep if k.endswith('/')]
    files = {_key(k) for k in keep if not k.endswith('/')}

    def kept(rel):
        k = _key(rel)
        return k in files or any((k + '/').startswith(d) for d in dirs)
    return kept


# ------------------------------------------------------------------ the parking manifest
def _check_entry(e):
    if not isinstance(e, str) or not e.strip('/\\ '):
        return 'an entry is not a path: %r' % (e,)
    n = e.replace('\\', '/')
    if n.startswith('/') or (len(n) > 1 and n[1] == ':'):
        return 'an entry is an absolute path: %r' % e
    if '..' in n.split('/'):
        return "an entry leaves the Mods folder ('..'): %r" % e
    return None


def load_manifest(paths):
    """(document, exists). Refuses with ProfileError when the file is damaged - never guesses."""
    p = paths.manifest if isinstance(paths, Paths) else paths
    if not os.path.exists(p):
        return {'moved': []}, False
    try:
        with open(p, encoding='utf-8') as f:
            doc = json.load(f)
    except (OSError, ValueError) as e:
        raise ProfileError('The parking list %s cannot be read (%s). Nothing was changed. The Mods switch tool '
                           'wrote it; fix or rename that file first.' % (p, e))
    if not isinstance(doc, dict) or not isinstance(doc.get('moved'), list):
        raise ProfileError('The parking list %s is not in the expected {"moved": [...]} form. Nothing was '
                           'changed; fix or rename that file first.' % p)
    for e in doc['moved']:
        why = _check_entry(e)
        if why:
            raise ProfileError('The parking list %s looks damaged: %s. Nothing was changed.' % (p, why))
    return doc, True


def _entry_is_dir(e):
    return e.replace('\\', '/').endswith('/')


def _entry_key(e):
    return _key(e)


def rebuild_manifest(entries, p_files, p_dirs, m_keys, special=()):
    """The manifest entries that make mods_switch.py's 'full' restore exactly what is parked.

    entries: the current list. p_files / p_dirs: {key: rel} of what is in Mods_parked (files, folders).
    m_keys: keys of every file and folder in Mods. special: keys of SpeedKit's own files (the fast
    pack, the monitor) - stale entries for them are dropped. Returns (new list, info dict)."""
    valid_dirs = set()
    for e in entries:
        k = _entry_key(e)
        if _entry_is_dir(e) and k in p_dirs and k not in m_keys:
            valid_dirs.add(k)
    # a valid folder entry inside another valid folder entry is redundant
    top_dirs = {d for d in valid_dirs if not any(a in valid_dirs for a in _ancestors(d))}
    out, seen = [], set()
    info = {'kept': 0, 'dropped_restored': [], 'dropped_nested': [], 'split': [], 'kept_stale': [], 'added': [],
            'duplicates': []}
    for e in entries:
        k = _entry_key(e)
        isdir = _entry_is_dir(e)
        ident = (k, isdir)
        if ident in seen:
            info['duplicates'].append(e)
            continue
        if any(a in top_dirs for a in _ancestors(k)) or (not isdir and k in top_dirs):
            info['dropped_nested'].append(e)
            continue
        if isdir:
            if k in top_dirs:
                out.append(e); seen.add(ident); info['kept'] += 1
            elif k in p_dirs:                         # still parked but Mods has that folder now: split it
                info['split'].append(e)
            elif k in m_keys or k in special:
                info['dropped_restored'].append(e)
            else:
                out.append(e); seen.add(ident); info['kept_stale'].append(e)
        else:
            if k in p_files:
                out.append(e); seen.add(ident); info['kept'] += 1
            elif k in m_keys or k in special:
                info['dropped_restored'].append(e)
            elif k in p_dirs:                          # a folder now stands where the file was: cover it below
                info['split'].append(e)
            else:
                out.append(e); seen.add(ident); info['kept_stale'].append(e)
    covered_files = {_entry_key(e) for e in out if not _entry_is_dir(e)}
    covered_dirs = {_entry_key(e) for e in out if _entry_is_dir(e) and _entry_key(e) in p_dirs}

    def is_covered(k):
        return k in covered_files or any(a in covered_dirs for a in _ancestors(k))
    uncovered = {k for k in p_files if not is_covered(k)}
    if uncovered:
        # coarsest valid cover: a whole folder when everything below it is uncovered and Mods has no such folder
        files_under = {}
        for k in p_files:
            for a in _ancestors(k):
                files_under.setdefault(a, []).append(k)
        added = []
        done_dirs = set()
        for k in sorted(uncovered):
            if any(a in done_dirs for a in _ancestors(k)):
                continue
            chosen = None
            for a in _ancestors(k):                   # outermost first
                if a in m_keys or a in covered_dirs:
                    continue
                if all(x in uncovered for x in files_under.get(a, ())):
                    chosen = a
                    break
            if chosen is not None:
                done_dirs.add(chosen)
                added.append(p_dirs.get(chosen, chosen).replace('\\', '/') + '/')
            else:
                added.append(p_files[k].replace('\\', '/'))
        added = [a for a in added if not (not a.endswith('/') and any(x in done_dirs for x in _ancestors(_key(a))))]
        out.extend(added)
        info['added'] = added
    return out, info


def check_manifest(sims=SIMS):
    """Is Mods_parked\\_manifest.json consistent with the folders, from mods_switch.py's point of view?

    Returns {'entries', 'unlisted' (parked files 'full' would leave behind), 'blocked' (folder entries
    'full' would skip because Mods has that folder), 'in_both' (file entries whose name is also in Mods:
    two copies, 'full' leaves the parked one - a switch cannot fix that), 'nested', 'duplicates',
    'stale' (pointing nowhere - harmless), 'error', 'ok' (no unlisted, blocked or nested)}."""
    P = Paths(sims)
    out = {'entries': 0, 'unlisted': [], 'blocked': [], 'in_both': [], 'nested': [], 'duplicates': [], 'stale': [],
           'error': None, 'ok': False}
    try:
        doc, _ = load_manifest(P)
    except ProfileError as e:
        out['error'] = str(e)
        return out
    inv = inventory(P)
    entries = doc['moved']
    out['entries'] = len(entries)
    p_files = {k: it.p_rel for k, it in inv.items.items() if it.p_rel is not None}
    p_files.update({_key(n): n for n in inv.all_packs('P')})
    if inv.monitor_parked:
        p_files[_key(inv.monitor_parked)] = inv.monitor_parked
    m_keys = inv.m_keys()
    dir_entries = {_entry_key(e) for e in entries if _entry_is_dir(e)}
    seen = set()
    for e in entries:
        k = _entry_key(e)
        if (k, _entry_is_dir(e)) in seen:
            out['duplicates'].append(e)
        seen.add((k, _entry_is_dir(e)))
        if any(a in dir_entries for a in _ancestors(k)):
            out['nested'].append(e)
        exists = k in inv.p_dirs if _entry_is_dir(e) else k in p_files
        if not exists:
            out['stale'].append(e)
        elif k in m_keys:
            out['blocked' if _entry_is_dir(e) else 'in_both'].append(e)
    file_entries = {_entry_key(e) for e in entries if not _entry_is_dir(e)}
    for k, rel in sorted(p_files.items()):
        if k not in file_entries and not any(a in dir_entries for a in _ancestors(k)):
            out['unlisted'].append(rel)
    out['ok'] = not (out['unlisted'] or out['blocked'] or out['nested'])
    return out


# ------------------------------------------------------------------ what is where
Item = namedtuple('Item', 'key m_rel p_rel size')


class Inventory:
    """Files and folders in Mods ('M') and Mods_parked ('P'), keyed case-insensitively by rel path.

    items: {key: Item(key, m_rel or None, p_rel or None, size)} - ordinary files (both roots);
    m_dirs / p_dirs: {key: rel} of sub-folders; SpeedKit's own files at the roots are kept apart:
    pack_mods / pack_parked (fast pack files at the Mods / Mods_parked root), pack_home (in the
    fastpack folder), monitor_mods / monitor_parked (SpeedKit_Monitor.ts4script at a root).
    packs: {family: {'M': names at the Mods root, 'P': at the Mods_parked root, 'H': in its own folder}} for
    every pack family ('fast' - the same lists as pack_mods/pack_parked/pack_home - and 'save:<hex>' for
    the save pack of each slot)."""

    def __init__(self):
        self.items = {}
        self.m_dirs, self.p_dirs = {}, {}
        self.pack_mods, self.pack_parked, self.pack_home = [], [], []
        self.packs = {'fast': {'M': self.pack_mods, 'P': self.pack_parked, 'H': self.pack_home}}
        self.monitor_mods = self.monitor_parked = None
        self.sizes = {}                              # (side, key) -> bytes

    def family(self, fam):
        return self.packs.setdefault(fam, {'M': [], 'P': [], 'H': []})

    def all_packs(self, side):
        """Pack file names of every family on one side ('M', 'P' or 'H')."""
        return [n for f in self.packs.values() for n in f[side]]

    def deployed(self):
        """{family: names} of the packs at the Mods root."""
        return {fam: list(f['M']) for fam, f in self.packs.items() if f['M']}

    def m_keys(self):
        ks = {k for k, it in self.items.items() if it.m_rel is not None} | set(self.m_dirs)
        ks.update(_key(n) for n in self.all_packs('M'))
        if self.monitor_mods:
            ks.add(_key(self.monitor_mods))
        return ks

    def conflicts(self):
        return sorted(it.m_rel for it in self.items.values() if it.m_rel is not None and it.p_rel is not None)

    def parked_keys(self):
        """Keys parked and not shadowed by a Mods copy of the same path."""
        return {k for k, it in self.items.items() if it.p_rel is not None and it.m_rel is None}

    def totals(self, side):
        n = b = 0
        for it in self.items.values():
            if (it.m_rel if side == 'M' else it.p_rel) is not None:
                n += 1
                b += self.sizes.get((side, it.key), 0)
        return n, b


def _walk(root, parked):
    """[(rel, size)] files and [rel] folders under root (scandir: sizes come with the listing)."""
    files, dirs = [], []
    stack = ['']
    while stack:
        rel_dir = stack.pop()
        full = os.path.join(root, rel_dir.replace('/', os.sep)) if rel_dir else root
        try:
            with os.scandir(full) as it:
                entries = list(it)
        except OSError:
            continue
        for e in entries:
            rel = rel_dir + '/' + e.name if rel_dir else e.name
            try:
                is_dir = e.is_dir()
            except OSError:
                continue
            if is_dir:
                if parked and not rel_dir and e.name.lower() == OLD_CACHES:
                    continue
                dirs.append(rel)
                stack.append(rel)
            else:
                if parked and not rel_dir and (e.name.lower() in PARKED_SKIP_FILES or e.name.lower().endswith('.speedkit-tmp')):
                    continue
                try:
                    size = e.stat().st_size
                except OSError:
                    size = 0
                files.append((rel, size))
    return files, dirs


def inventory(paths):
    """Look at the disk now (read-only)."""
    inv = Inventory()
    items = {}
    for side, root in (('M', paths.mods), ('P', paths.parked)):
        if not os.path.isdir(root):
            continue
        files, dirs = _walk(root, side == 'P')
        for rel in dirs:
            (inv.m_dirs if side == 'M' else inv.p_dirs)[_key(rel)] = rel
        for rel, size in files:
            fam = _pack_family(rel) if '/' not in rel else None
            if fam:
                inv.family(fam)[side].append(rel)
                continue
            if '/' not in rel and _is_monitor_name(rel):
                if side == 'M':
                    inv.monitor_mods = rel
                else:
                    inv.monitor_parked = rel
                continue
            k = _key(rel)
            m_rel, p_rel = items.get(k, (None, None))
            items[k] = (rel, p_rel) if side == 'M' else (m_rel, rel)
            inv.sizes[(side, k)] = size
    for k, (m_rel, p_rel) in items.items():
        size = inv.sizes.get(('M', k), inv.sizes.get(('P', k), 0))
        inv.items[k] = Item(k, m_rel, p_rel, size)
    if os.path.isdir(paths.fastpack):
        inv.pack_home.extend(sorted(n for n in os.listdir(paths.fastpack)
                                    if _is_pack_name(n) and os.path.isfile(os.path.join(paths.fastpack, n))))
    if os.path.isdir(paths.savepacks):
        for d in sorted(os.listdir(paths.savepacks)):
            m = SLOT_RX.match(d)
            full = os.path.join(paths.savepacks, d)
            if not m or not os.path.isdir(full):
                continue
            fam = 'save:' + m.group(1).lower()
            inv.family(fam)['H'].extend(sorted(n for n in os.listdir(full) if _save_family(n) == fam
                                                and os.path.isfile(os.path.join(full, n))))
    for f in inv.packs.values():
        for side in 'MPH':
            f[side].sort()
    return inv


# ------------------------------------------------------------------ fast mode (speedkit.fastmode)
def _load_fastmode(fastmode=None):
    """(module, error). fastmode may be passed in (tests use a stub); else speedkit.fastmode, imported lazily."""
    if fastmode is not None:
        return fastmode, None
    try:
        from . import fastmode as fm
        return fm, None
    except Exception as e:
        return None, 'speedkit.fastmode is not available (%s: %s)' % (type(e).__name__, e)


def _params(fn):
    try:
        return inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return {}


def _call(fn, first=None, **avail):
    """Call fn with the keyword arguments it names out of `avail` (never through a **kwargs catch-all:
    fastmode.update_pack forwards those to plan_pack); `first` fills a required first parameter that
    none of them names (e.g. status(out) instead of status(out_dir))."""
    params = _params(fn)
    kw = {k: v for k, v in avail.items() if k in params
          and params[k].kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)}
    args = []
    plist = list(params.values())
    if plist and first is not None:
        p0 = plist[0]
        if p0.name not in kw and p0.default is p0.empty and p0.kind in (p0.POSITIONAL_ONLY, p0.POSITIONAL_OR_KEYWORD):
            args.append(first)
    return fn(*args, **kw)


def _fresh(st):
    """(fresh?, why) from whatever fastmode.status returned (bool, 'fresh'/'stale ...', dict, tuple, object)."""
    why = ''
    if isinstance(st, (tuple, list)) and st:
        why = '; '.join(str(x) for x in st[1:] if x)
        f, w = _fresh(st[0])
        return f, why or w
    if isinstance(st, bool):
        return st, why
    if isinstance(st, str):
        low = st.strip().lower()
        return low.startswith('fresh') or low in ('ok', 'up to date', 'up-to-date', 'current'), st
    if isinstance(st, dict):
        for k in ('why', 'reason', 'reasons', 'because', 'message', 'details'):
            if st.get(k):
                v = st[k]
                why = '; '.join(map(str, v)) if isinstance(v, (list, tuple)) else str(v)
                break
        if 'fresh' in st:
            return bool(st['fresh']), why
        if 'stale' in st:
            return not bool(st['stale']), why
        for k in ('state', 'status'):
            if isinstance(st.get(k), str):
                return st[k].strip().lower().startswith('fresh') or st[k].strip().lower() == 'ok', why or st[k]
        return False, why or 'fastmode.status gave no fresh/stale answer'
    for attr in ('fresh', 'is_fresh'):
        if hasattr(st, attr):
            v = getattr(st, attr)
            return bool(v() if callable(v) else v), str(getattr(st, 'why', '') or '')
    return False, 'fastmode.status gave no fresh/stale answer (%r)' % (st,)


def _park_rels(result):
    """rel paths out of whatever park_set returned: [(root, rel)], [(root, rel, reason)], {(root, rel): reason},
    [rel], objects with .rel, or (list, reasons)."""
    if isinstance(result, tuple) and len(result) == 2 and isinstance(result[0], (list, set, tuple, dict)) \
            and isinstance(result[1], dict):
        result = result[0]
    items = result.keys() if isinstance(result, dict) else result
    rels = []
    for it in items or ():
        rel = None
        if isinstance(it, str):
            rel = it
        elif isinstance(it, dict):
            rel = it.get('rel')
        elif hasattr(it, 'rel') and not isinstance(it, (tuple, list)):
            rel = it.rel
        elif isinstance(it, (tuple, list)) and it:
            if len(it) >= 2 and it[0] in ('Mods', 'Mods_parked') and isinstance(it[1], str):
                rel = it[1]
            elif isinstance(it[0], str):
                rel = it[0]
        if rel:
            rels.append(_norm_rel(rel))
    return rels


def _jsonable(x, depth=0):
    if depth > 4:
        return repr(x)[:200]
    if x is None or isinstance(x, (bool, int, float, str)):
        return x
    if isinstance(x, dict):
        return {str(k): _jsonable(v, depth + 1) for k, v in list(x.items())[:50]}
    if isinstance(x, (list, tuple, set)):
        return [_jsonable(v, depth + 1) for v in list(x)[:50]]
    return repr(x)[:200]


# ------------------------------------------------------------------ targets
def _record_path(P, profile):
    return os.path.join(P.records, 'last_%s.json' % profile)


def _read_record(P, profile):
    try:
        with open(_record_path(P, profile), encoding='utf-8') as f:
            d = json.load(f)
        return {_key(r) for r in d.get('parked', [])}
    except (OSError, ValueError, AttributeError, TypeError):
        return None


def _write_record(P, profile, parked_rels):
    os.makedirs(P.records, exist_ok=True)
    p = _record_path(P, profile)
    with open(p + '.tmp', 'w', encoding='utf-8') as f:
        json.dump({'profile': profile, 'switched': _now_iso(), 'parked': sorted(parked_rels)}, f, indent=1)
    os.replace(p + '.tmp', p)


def _any_rel(it):
    return it.m_rel if it.m_rel is not None else it.p_rel


def _follow_dirs(inv, target):
    """Non-mod files (desktop.ini, .cfg, logs, readmes) go where the mods of their folder go: parked
    only when every mod below their folder is parked; a folder with no mods follows its parent."""
    count = {}
    for k, side in target.items():
        for a in _ancestors(k):
            c = count.setdefault(a, [0, 0])
            c[0] += 1
            c[1] += side == 'P'

    def decide(d):
        while d:
            c = count.get(d)
            if c and c[0]:
                return 'P' if c[1] == c[0] else 'M'
            d = _parent(d)
        return 'M'
    out = dict(target)
    for k, it in inv.items.items():
        if k not in out:
            out[k] = decide(_parent(k))
    return out


def _companion_map(lib, verdicts):
    """{package key: (kind, script key)} for packages that need a script ('core'/'addon')."""
    pk = {p.id: p for p in lib.packages()}
    out = {}
    for pid, v in verdicts.items():
        p = pk.get(pid)
        kind = getattr(v, 'kind', None)
        script = getattr(v, 'script', None)
        if p is None or kind not in ('core', 'addon') or not script:
            continue
        out.setdefault(_key(p.rel), (kind, _key(script)))
    return out


def _closure(target, comp):
    """Keep scripts together with their companions (only ever flips parked -> kept). Returns notes."""
    notes = []
    same_folder = {}
    for k, (kind, s) in comp.items():
        if kind == 'core' and _parent(k) == _parent(s):
            same_folder.setdefault(s, set()).add(k)
    changed = True
    while changed:
        changed = False
        for k, (kind, s) in sorted(comp.items()):
            if target.get(k) == 'M' and target.get(s) == 'P':
                target[s] = 'M'
                notes.append('kept script %s because %s (kept) needs it' % (s, k))
                changed = True
        for s, ks in sorted(same_folder.items()):
            if target.get(s) == 'M':
                for k in sorted(ks):
                    if target.get(k) == 'P':
                        target[k] = 'M'
                        notes.append('kept %s together with its script %s' % (k, s))
                        changed = True
    return notes


def compute_target(profile, inv, keep=None, park_rels=None, comp=None):
    """{key: 'M' | 'P'} for every ordinary file, plus notes. SpeedKit's own files are handled apart.
    'save' parks exactly what 'fast' parks (only the pack at the Mods root differs)."""
    notes = []
    if profile == 'save':
        profile = 'fast'
    if profile == 'full':
        return {k: 'M' for k in inv.items}, notes
    if profile == 'studio':
        kept = keep_matcher(keep if keep is not None else BUILTIN_KEEP)
        target = {k: ('M' if kept(_any_rel(it)) else 'P') for k, it in inv.items.items()}
        if comp:
            notes += _closure(target, comp)
        return target, notes
    if profile == 'fast':
        park = {_key(r) for r in (park_rels or ())}
        target = {}
        for k, it in inv.items.items():
            rel = _any_rel(it)
            if rel.lower().endswith('.ts4script'):
                target[k] = 'M'
                if k in park:
                    notes.append('never parks a script: %s stays' % rel)
            elif rel.lower().endswith('.package'):
                if k in park and any(_under(k, d) for d in FAST_NEVER_PARK):
                    notes.append('never parks %s in fast mode: %s stays' % (k.split('/')[0] + '/', rel))
                    target[k] = 'M'
                else:
                    target[k] = 'P' if k in park else 'M'
        if comp:
            notes += _closure(target, comp)
        return _follow_dirs(inv, target), notes
    raise ProfileError('unknown profile %r (choose one of %s)' % (profile, ', '.join(PROFILES)))


def empty_dir_side(profile, target, keep=None):
    """side(dir key) -> 'M' | 'P' for a parked folder with no file anywhere below it (e.g. an empty
    settings folder mods_switch.py's 'lean' parked as 'dir/'): 'full' brings every one back, 'fast'
    lets it follow the files of its nearest folder that has any (like _follow_dirs), 'studio' brings
    back only what KEEP keeps. Only the parked -> Mods direction is ever planned: an empty folder in
    Mods loads nothing and stays where it is."""
    if profile == 'full':
        return lambda d: 'M'
    if profile == 'studio':
        kept = keep_matcher(keep if keep is not None else BUILTIN_KEEP)
        return lambda d: 'M' if kept(d) else 'P'
    count = {}                                   # 'fast' and 'save
    for k, side in target.items():
        for a in _ancestors(k):
            c = count.setdefault(a, [0, 0])
            c[0] += 1
            c[1] += side == 'P'

    def side(d):
        while d:
            c = count.get(d)
            if c and c[0]:
                return 'P' if c[1] == c[0] else 'M'
            d = _parent(d)
        return 'M'
    return side


# ------------------------------------------------------------------ the move plan
def plan_moves(inv, target, P, dir_side=None):
    """Fewest moves from the current state to target: a whole folder moves as one rename when all of it
    is on one side, goes to the other side, and the destination has no such folder; else file by file.
    A parked folder with no file below it comes back as one rename when dir_side(key) says 'M' (and
    Mods has no such folder). A path present in both roots is never overwritten (reported in
    conflicts). Returns (moves, conflicts)."""
    children_dirs, children_files = {}, {}
    for d in set(inv.m_dirs) | set(inv.p_dirs):
        children_dirs.setdefault(_parent(d), set()).add(d)
    for k in inv.items:
        children_files.setdefault(_parent(k), set()).add(k)
    files_under = {}
    for k in inv.items:
        for a in _ancestors(k):
            files_under.setdefault(a, []).append(k)
    moves, conflicts = [], []

    def file_move(k):
        it = inv.items[k]
        want = target.get(k)
        if it.m_rel is not None and it.p_rel is not None:
            conflicts.append(it.m_rel)
            return
        if want == 'P' and it.m_rel is not None:
            moves.append({'op': 'park', 'what': 'file', 'rel': it.m_rel, 'files': 1,
                          'bytes': inv.sizes.get(('M', k), 0), 'src': P.path('M', it.m_rel), 'dst': P.path('P', it.m_rel),
                          'mods': int(_is_mod(it.m_rel)), 'keys': [k]})
        elif want == 'M' and it.p_rel is not None:
            moves.append({'op': 'restore', 'what': 'file', 'rel': it.p_rel, 'files': 1,
                          'bytes': inv.sizes.get(('P', k), 0), 'src': P.path('P', it.p_rel), 'dst': P.path('M', it.p_rel),
                          'mods': int(_is_mod(it.p_rel)), 'keys': [k]})

    def visit(d):
        fs = files_under.get(d, [])
        if fs:
            m_only = all(inv.items[k].m_rel is not None and inv.items[k].p_rel is None for k in fs) and d not in inv.p_dirs
            p_only = all(inv.items[k].p_rel is not None and inv.items[k].m_rel is None for k in fs) and d not in inv.m_dirs
            all_p = all(target.get(k) == 'P' for k in fs)
            all_m = all(target.get(k) == 'M' for k in fs)
            if (m_only and all_p) or (p_only and all_m):
                side = 'M' if m_only else 'P'
                rel = (inv.m_dirs if side == 'M' else inv.p_dirs)[d]
                other = 'P' if side == 'M' else 'M'
                moves.append({'op': 'park' if side == 'M' else 'restore', 'what': 'folder', 'rel': rel + '/',
                              'files': len(fs), 'bytes': sum(inv.sizes.get((side, k), 0) for k in fs),
                              'src': P.path(side, rel), 'dst': P.path(other, rel),
                              'mods': sum(_is_mod(k) for k in fs), 'keys': list(fs), 'dir': d})
                return
        elif d in inv.p_dirs and d not in inv.m_dirs and dir_side is not None and dir_side(d) == 'M':
            rel = inv.p_dirs[d]
            moves.append({'op': 'restore', 'what': 'folder', 'rel': rel + '/', 'files': 0, 'bytes': 0,
                          'src': P.path('P', rel), 'dst': P.path('M', rel), 'mods': 0, 'keys': [], 'dir': d})
            return
        for sub in sorted(children_dirs.get(d, ())):
            visit(sub)
        for k in sorted(children_files.get(d, ())):
            file_move(k)

    for sub in sorted(children_dirs.get('', ())):
        visit(sub)
    for k in sorted(children_files.get('', ())):
        file_move(k)
    return moves, conflicts


def _special_moves(inv, P, profile, slot=None):
    """Moves of SpeedKit's own files: the monitor (always to the Mods root) and the packs: the profile's own
    pack (the fast pack in 'fast', the save pack of `slot` in 'save') to the Mods root, every other pack
    family back to its own folder (fastpack, savepacks\\<slot>). A stale copy whose name is taken is
    quarantined."""
    out = []
    want = 'fast' if profile == 'fast' else (_family_of_slot(slot) if profile == 'save' and slot else None)
    if inv.monitor_parked:
        if inv.monitor_mods:
            out.append({'op': 'quarantine', 'what': 'monitor', 'rel': inv.monitor_parked,
                        'src': P.path('P', inv.monitor_parked), 'dst': None,
                        'why': 'an older parked copy; Mods already has the monitor'})
        else:
            out.append({'op': 'restore', 'what': 'monitor', 'rel': inv.monitor_parked,
                        'src': P.path('P', inv.monitor_parked), 'dst': os.path.join(P.mods, MONITOR)})
    if want is not None:
        inv.family(want)
    for fam in sorted(inv.packs, key=lambda f: (f != 'fast', f)):
        f = inv.packs[fam]
        home_dir = P.family_home(fam)
        folder = 'fastpack' if fam == 'fast' else 'save pack'
        mods = {n.lower(): n for n in f['M']}
        home = {n.lower(): n for n in f['H']}
        parked = {n.lower(): n for n in f['P']}
        if fam == want:
            for low, n in sorted(home.items()):
                if low in mods:
                    out.append({'op': 'quarantine', 'what': 'pack', 'rel': mods[low], 'src': os.path.join(P.mods, mods[low]),
                                'dst': None, 'why': 'replaced by the newer copy in the %s folder' % folder, 'family': fam})
                out.append({'op': 'deploy', 'what': 'pack', 'rel': n, 'src': os.path.join(home_dir, n),
                            'dst': os.path.join(P.mods, n), 'family': fam})
            for low, n in sorted(parked.items()):
                if low in home or low in mods:
                    out.append({'op': 'quarantine', 'what': 'pack', 'rel': n, 'src': os.path.join(P.parked, n), 'dst': None,
                                'why': 'an older parked copy', 'family': fam})
                else:
                    out.append({'op': 'deploy', 'what': 'pack', 'rel': n, 'src': os.path.join(P.parked, n),
                                'dst': os.path.join(P.mods, n), 'family': fam})
        else:
            taken = set(home)
            for where, names, root in (('M', mods, P.mods), ('P', parked, P.parked)):
                for low, n in sorted(names.items()):
                    if low in taken:
                        out.append({'op': 'quarantine', 'what': 'pack', 'rel': n, 'src': os.path.join(root, n), 'dst': None,
                                    'why': 'the %s folder already has this file' % folder, 'family': fam})
                    else:
                        taken.add(low)
                        out.append({'op': 'store', 'what': 'pack', 'rel': n, 'src': os.path.join(root, n),
                                    'dst': os.path.join(home_dir, n), 'family': fam})
    return out


def _tidy_candidates(moves):
    """{'M': dir keys, 'P': dir keys} a switch may leave empty: the folders the moved things came out of."""
    out = {'M': set(), 'P': set()}
    for mv in moves:
        side = 'M' if mv['op'] == 'park' else 'P'
        k = mv['dir'] if mv['what'] == 'folder' else mv['keys'][0]
        out[side].update(_ancestors(k))
    return out


def _final_model(inv, moves, protect=()):
    """(p_files, p_dirs, m_keys) after the moves and the tidy-up (for the dry-run manifest)."""
    m_files = {k: it.m_rel for k, it in inv.items.items() if it.m_rel is not None}
    p_files = {k: it.p_rel for k, it in inv.items.items() if it.p_rel is not None}
    m_dirs, p_dirs = dict(inv.m_dirs), dict(inv.p_dirs)
    for mv in moves:
        src_f, dst_f, src_d, dst_d = (m_files, p_files, m_dirs, p_dirs) if mv['op'] == 'park' else (p_files, m_files, p_dirs, m_dirs)
        if mv['what'] == 'folder':
            d = mv['dir']
            for k in list(src_f):
                if _under(k, d):
                    dst_f[k] = src_f.pop(k)
            for k in list(src_d):
                if _under(k, d):
                    dst_d[k] = src_d.pop(k)
            for a in _ancestors(d):
                dst_d.setdefault(a, a)
        else:
            k = mv['keys'][0]
            dst_f[k] = src_f.pop(k)
            for a in _ancestors(k):
                dst_d.setdefault(a, a)
    cand = _tidy_candidates(moves)
    _model_tidy(m_files, m_dirs, cand['M'], ())
    _model_tidy(p_files, p_dirs, set(cand['P']) | (set(p_dirs) & set(m_dirs)), {d for d in protect if d not in m_dirs})
    return p_files, p_dirs, set(m_files) | set(m_dirs)


def _model_tidy(files, dirs, cands, protect):
    """What _tidy does, on the model: a candidate folder with nothing left in it goes (deepest first)."""
    for d in sorted(cands, key=lambda x: -x.count('/')):
        if d in dirs and d not in protect and not any(_under(k, d) for k in files) \
                and not any(x != d and _under(x, d) for x in dirs):
            del dirs[d]


def _protected_dirs(entries):
    """Folder entries of the parking list: an empty folder the other tool parked on purpose stays."""
    return {_entry_key(e) for e in entries if _entry_is_dir(e)}


def _protect(P, entries):
    """The parking list's 'dir/' entries that are still valid (Mods has no such folder): their folders
    in Mods_parked stay even when empty. A 'dir/' entry whose folder Mods has again is split by the
    manifest rebuild anyway, so an emptied leftover of it goes - else mods_switch.py's 'lean' would
    later skip that folder ('already parked with this name')."""
    return {k for k in _protected_dirs(entries) if not os.path.isdir(os.path.join(P.mods, k.replace('/', os.sep)))}


def _special_keys(inv):
    return {_key(n) for side in 'MPH' for n in inv.all_packs(side)} | {MONITOR.lower()}


def _tidy(P, cand_m, cand_p=(), protect=()):
    """Remove the candidate folders that are empty now, deepest first (os.rmdir cannot remove a folder
    that holds anything): the folders a switch emptied (the ones moved things came out of) or, after a
    rollback/undo, the ones it had created - plus, in Mods_parked, an empty folder whose twin exists in
    Mods. Nothing else is touched - an empty folder that was there before (a mod's empty settings
    folder, the empty sub-folders of a download parked with it) stays, so a rollback or undo gives
    back exactly the folders there were. In Mods_parked, the root, _old_caches and the
    folders of still-valid 'dir/' entries (`protect`) are never removed. Why tidy at all: an emptied
    Mods_parked\\sim would make mods_switch.py's 'lean' skip 'sim' ('already parked with this name');
    an emptied Mods\\sim would make its 'full' skip a 'sim/' entry."""
    removed = []
    protect = set(protect)
    cand_p = set(cand_p)
    # Mods_parked, deepest first: the candidates, and any empty folder whose twin exists in Mods (such a
    # leftover - e.g. from a run that was killed before its tidy-up - is never a folder parked on
    # purpose, and it is exactly what makes 'lean' skip a folder)
    if os.path.isdir(P.parked):
        for dp, dn, fn in os.walk(P.parked, topdown=False):
            if fn or os.path.normcase(dp) == os.path.normcase(P.parked):
                continue
            d = _key(os.path.relpath(dp, P.parked))
            if d.split('/')[0] == OLD_CACHES or d in protect:
                continue
            if d not in cand_p and not os.path.isdir(P.path('M', d)):
                continue
            try:
                if not os.listdir(dp):
                    os.rmdir(dp)
                    removed.append('Mods_parked/' + d)
            except OSError:
                pass
    for d in sorted(set(cand_m), key=lambda x: -x.count('/')):
        full = P.path('M', d)
        try:
            if not d or not os.path.isdir(full) or os.listdir(full):
                continue
            os.rmdir(full)
            removed.append('Mods/' + d)
        except OSError:
            pass
    return removed


def _state_doc(profile, inv_after=None, extra=None):
    """SpeedKit\\profile_state.json: {"profile", "switched", "tool", "parked_files", "fast_pack"}; for 'save' also
    "save_slot", "pack_dir", "save_pack" (the files at the Mods root) and what identifies the save in the
    game ("save_name", "save_slot_id", "save_guid" - the in-game monitor compares them with the loaded save);
    for 'fast' also "pack_dir"."""
    doc = {'profile': profile, 'switched': _now_iso(), 'tool': 'speedkit.profiles'}
    if inv_after is not None:
        n, b = inv_after.totals('P')
        doc['parked_files'] = n
        doc['fast_pack'] = sorted(inv_after.pack_mods)
    for k, v in (extra or {}).items():
        doc[k] = v
    if profile == 'save' and inv_after is not None and doc.get('save_slot'):
        doc['save_pack'] = sorted(inv_after.family(_family_of_slot(doc['save_slot']))['M'])
    return doc


def read_state(sims=SIMS, home=None):
    """SpeedKit\\profile_state.json as a dict, or None."""
    P = Paths(sims, home)
    try:
        with open(P.state, encoding='utf-8') as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


# ------------------------------------------------------------------ library + companions
def _open_library(lib, P, scan):
    if lib is None:
        from .library import Library, ROOTS
        if os.path.normcase(os.path.abspath(P.sims)) != os.path.normcase(os.path.abspath(SIMS)):
            raise ProfileError('pass lib=Library(db_path=..., roots=...) for a Sims 4 folder other than the real one')
        lib = Library()
    roots = getattr(lib, 'roots', {})
    for name, want in (('Mods', P.mods), ('Mods_parked', P.parked)):
        have = roots.get(name)
        if have is None or os.path.normcase(os.path.abspath(have)) != os.path.normcase(os.path.abspath(want)):
            raise ProfileError('the library index looks at %s for %s, but this switch works on %s' % (have, name, want))
    if scan:
        lib.scan()
    return lib


def _verdicts(lib, verdicts, companions_cache):
    """{pkg_id: Verdict} or (None, warning)."""
    if verdicts is False:
        return None, None
    if isinstance(verdicts, dict):
        return verdicts, None
    try:
        if callable(verdicts):
            return verdicts(lib), None
        from . import companions
        kw = {'cache_path': companions_cache} if companions_cache else {}
        return companions.classify(lib, **kw), None
    except Exception as e:
        return None, 'the script/companion check was skipped (%s: %s)' % (type(e).__name__, e)


# ------------------------------------------------------------------ plan / switch
def _fast_park_rels(fm, lib, verdicts=None, companions_cache=None):
    """rels fastmode.park_set(lib) leaves out; our verdicts and companions cache are handed over when it takes them."""
    avail = {'roots': ('Mods', 'Mods_parked')}
    if isinstance(verdicts, dict):
        avail['verdicts'] = verdicts
    if companions_cache:
        avail['cache_path'] = companions_cache
    try:
        return _park_rels(_call(fm.park_set, lib, lib=lib, **avail))
    except Exception as e:
        raise ProfileError('the fast profile cannot be worked out: fastmode.park_set failed (%s: %s)' % (type(e).__name__, e))


def _default_refs(P):
    """What the saves and Tray use (usedpack.scan_references, incremental, one process: no pool needed)."""
    from . import usedpack
    refs = usedpack.scan_references(os.path.join(P.sims, 'saves'), os.path.join(P.sims, 'Tray'), workers=1)
    if refs.stats.get('errors'):
        raise ProfileError('some saves could not be read (%s) - the game may be saving; try again in a minute'
                           % ', '.join(sorted(refs.stats['errors'])[:3]))
    return refs


def _pack_status(fm, P, lib, out_dir=None):
    out_dir = out_dir or P.fastpack
    try:
        st = _call(fm.status, out_dir, out_dir=out_dir, lib=lib, sims=P.sims, home=P.home)
    except Exception as e:
        return False, 'fastmode.status failed (%s: %s)' % (type(e).__name__, e), None
    fresh, why = _fresh(st)
    return fresh, why, _jsonable(st)


def _build_plan(profile, P, inv, doc, lib, fm, keep, keep_source, verdicts, companions_cache, pack_info, pack_before=None,
                slot=None):
    park_rels, comp, warnings, notes, v = None, None, [], [], None
    if profile != 'full' and lib is not None:
        v, w = _verdicts(lib, verdicts, companions_cache)
        if w:
            warnings.append(w)
        if v:
            comp = _companion_map(lib, v)
    if profile in ('fast', 'save'):
        park_rels = _fast_park_rels(fm, lib, v, companions_cache)
        own = _special_keys(inv)
        park_rels = [r for r in park_rels if _key(r) not in own and not ('/' not in r and _pack_family(r))]
    target, tnotes = compute_target(profile, inv, keep, park_rels, comp)
    notes += tnotes
    moves, conflicts = plan_moves(inv, target, P, empty_dir_side(profile, target, keep))
    special = _special_moves(inv, P, profile, slot)
    # script checks on the result
    kept_scripts = [k for k, side in target.items() if side == 'M' and k.endswith('.ts4script')]
    deep = sorted(_any_rel(inv.items[k]) for k in kept_scripts if k.count('/') > 1)
    if deep:
        warnings.append('%d script mod(s) sit more than one folder deep and never load: %s' % (len(deep), ', '.join(deep[:5])))
    if comp:
        lonely = sorted(k for k, (kind, s) in comp.items() if target.get(k) == 'M' and target.get(s) == 'P')
        if lonely:
            warnings.append('%d kept package(s) still need a parked script: %s' % (len(lonely), ', '.join(lonely[:5])))
    if conflicts:
        warnings.append('%d path(s) exist in both Mods and Mods_parked; the Mods copy is used and neither is moved: %s'
                        % (len(conflicts), ', '.join(conflicts[:5])))
    p_files, p_dirs, m_keys = _final_model(inv, moves, _protected_dirs(doc['moved']))
    new_entries, minfo = rebuild_manifest(doc['moved'], p_files, p_dirs, m_keys, _special_keys(inv))
    # did the CC the game loads change? (then the thumbnail cache is quarantined; the game rebuilds it)
    pack_after = {n.lower() for n in inv.all_packs('M')}
    for s in special:
        if s['what'] == 'pack' and s['op'] == 'deploy':
            pack_after.add(s['rel'].lower())
        elif s['what'] == 'pack' and s['op'] == 'store':
            pack_after.discard(s['rel'].lower())
    before = {n.lower() for n in (pack_before if pack_before is not None else inv.all_packs('M'))}
    pack_changed = pack_after != before or any(s['what'] == 'pack' and s['op'] == 'quarantine' for s in special) \
        or bool((pack_info or {}).get('update_called')) or ((pack_info or {}).get('action') == 'update' and bool(before))
    cc_changed = any(mv['mods'] for mv in moves) or pack_changed
    park_files = sum(mv['files'] for mv in moves if mv['op'] == 'park')
    park_bytes = sum(mv['bytes'] for mv in moves if mv['op'] == 'park')
    rest_files = sum(mv['files'] for mv in moves if mv['op'] == 'restore')
    rest_bytes = sum(mv['bytes'] for mv in moves if mv['op'] == 'restore')
    m_n, m_b = inv.totals('M')
    p_n, p_b = inv.totals('P')
    both = {k for k, it in inv.items.items() if it.m_rel is not None and it.p_rel is not None}
    after_parked = {k for k, side in target.items() if side == 'P' and k not in both}
    after_p = sum(inv.sizes.get(('P', k), inv.sizes.get(('M', k), 0)) for k in after_parked) \
        + sum(inv.sizes.get(('P', k), 0) for k in both)
    after_m = sum(inv.sizes.get(('M', k), inv.sizes.get(('P', k), 0)) for k in inv.items if k not in after_parked and k not in both) \
        + sum(inv.sizes.get(('M', k), 0) for k in both)
    return {
        'profile': profile,
        'moves': moves,
        'special': special,
        'conflicts': conflicts,
        'target_parked': sorted(_any_rel(inv.items[k]) for k in after_parked),
        'counts': {'moves': len(moves) + len(special),
                   'park_files': park_files, 'park_bytes': park_bytes,
                   'restore_files': rest_files, 'restore_bytes': rest_bytes,
                   'folder_moves': sum(mv['what'] == 'folder' for mv in moves),
                   'file_moves': sum(mv['what'] == 'file' for mv in moves),
                   'mods_before': {'files': m_n, 'bytes': m_b}, 'parked_before': {'files': p_n, 'bytes': p_b},
                   'parked_after': {'files': len(after_parked) + len(both), 'bytes': after_p},
                   'mods_after': {'files': len(inv.items) - len(after_parked), 'bytes': after_m}},
        'manifest': {'before': len(doc['moved']), 'after': len(new_entries), 'changed': new_entries != doc['moved'],
                     'entries': new_entries, 'info': minfo},
        'cc_changed': bool(cc_changed),
        'thumbcache': P.thumbcache if cc_changed and os.path.exists(P.thumbcache) else None,
        'keep_source': keep_source if profile == 'studio' else None,
        'notes': notes,
        'warnings': warnings,
    }


def _public(plan):
    """The plan without internal fields, safe to print or dump as JSON."""
    out = dict(plan)
    out['moves'] = [{k: v for k, v in m.items() if k not in ('keys', 'dir')} for m in plan.get('moves', [])]
    if 'manifest' in out:
        out['manifest'] = {k: v for k, v in out['manifest'].items() if k != 'entries'}
    return out


def _bring_pack_home(P, inv, check_game):
    """Move every fast pack file found in Mods / Mods_parked into the fastpack folder (own journal).
    Returns the journal id or None."""
    moves = [s for s in _special_moves(inv, P, 'full') if s['what'] == 'pack']
    if not moves:
        return None
    try:
        j = Journal('profile', 'bring the fast pack home for an update', home=P.home, sims=P.sims, check_game=check_game)
    except JournalError as e:
        raise ProfileError('%s Nothing was changed.' % e)
    try:
        with j:
            for s in moves:
                if s['op'] == 'quarantine':
                    j.quarantine(s['src'])
                else:
                    j.move(s['src'], s['dst'])
    except BaseException as e:                      # Ctrl+C too: put the pack back first
        try:
            journal_undo(j.id, home=P.home, check_game=check_game)
            back = 'Nothing was changed.'
        except Exception as e2:
            back = 'Putting it back failed too (%s); undo journal %s.' % (e2, j.id)
        if not isinstance(e, Exception):
            raise
        raise ProfileError('The fast pack could not be moved home for its update (%s: %s). %s' % (type(e).__name__, e, back))
    return j.id


def _ensure_pack(fm, P, lib, dry_run, update, check_game, progress, refs=None, fam='fast'):
    """Make sure the profile's pack (the fast pack, or a save pack: fam 'save:<hex>') is fresh before a 'fast'
    or 'save' switch. Returns a dict for the plan.

    Fresh (fm.status) and present: nothing to do. Otherwise, in a real run: bring every pack file home to
    its own folder (own 'profile' journal, so the pack tool sees the whole pack and can add a small delta
    instead of rebuilding), ask again, call fm.update_pack if still stale, and refuse (putting the packs
    back where they were) if it is still not fresh. A dry run only reports."""
    inv = inventory(P)
    out_dir = P.family_home(fam)
    f = inv.family(fam)
    info = {'dir': out_dir, 'home': list(f['H']), 'deployed': list(f['M']), 'parked': list(f['P'])}
    fresh, why, raw = _pack_status(fm, P, lib, out_dir)
    info.update(fresh=fresh, why=why, status=raw)
    have = bool(f['H'] or f['M'] or f['P'])
    if not have and fresh:
        fresh = False
        why = why or 'no pack files found'
        info.update(fresh=False, why=why)
    if fresh:
        info['action'] = 'none'
        return info
    if dry_run:
        info['action'] = 'update' if update else 'refuse'
        return info
    if not update:
        raise ProfileError('The fast pack is not ready (%s). Update it first (fastpack update). Nothing was changed.'
                           % (why or 'no pack files'))
    jid = _bring_pack_home(P, inv, check_game)
    info['brought_home'] = jid
    try:
        fresh, why, raw = _pack_status(fm, P, lib, out_dir)
        info['update_called'] = False
        if not (fresh and inventory(P).family(fam)['H']):
            if refs is None and 'refs' in _params(fm.update_pack):
                refs = _default_refs(P)
            res = _call(fm.update_pack, None, lib=lib, refs=refs, out_dir=out_dir, dry_run=False, check_game=False,
                        sims=P.sims, home=P.home, progress=progress)
            info['update_called'] = True
            info['update_result'] = _jsonable(res)
            fresh, why, raw = _pack_status(fm, P, lib, out_dir)
        info.update(fresh=fresh, why=why, status=raw, action='updated' if info['update_called'] else 'checked at home')
        if not fresh or not inventory(P).family(fam)['H']:
            raise ProfileError('The fast pack could not be brought up to date (%s). The profile was not changed.'
                               % (why or 'no pack files were written'))
    except BaseException as e:                      # Ctrl+C too: the pack goes back where it was
        if jid:
            try:
                journal_undo(jid, home=P.home, check_game=check_game)
            except Exception as e2:                 # report both; the journal can be undone later
                raise ProfileError('%s - and putting the fast pack back into Mods failed too (%s: %s); close the game '
                                   'if it runs, then undo journal %s' % (e, type(e2).__name__, e2, jid))
        if isinstance(e, ProfileError) or not isinstance(e, Exception):
            raise
        raise ProfileError('The fast pack could not be updated (%s: %s). The profile was not changed.' % (type(e).__name__, e))
    return info


def _stage_json(staging, name, doc):
    os.makedirs(staging, exist_ok=True)
    tmp = os.path.join(staging, name + '.new')
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(doc, f, indent=1)                  # same layout mods_switch.py writes
        f.flush()
        os.fsync(f.fileno())
    return tmp


def _journal_json(j, staging, path, doc):
    """Write a JSON file through the journal: complete copy staged first, then quarantine the old file
    and move the new one in (os.replace on the same drive); undo puts the old one back."""
    tmp = _stage_json(staging, os.path.basename(path), doc)
    if os.path.exists(path):
        j.replace(tmp, path)
    else:
        j.put_new(tmp, path)


def switch(profile, dry_run=True, lib=None, sims=SIMS, home=None, fastpack_dir=None, check_game=True,
           fastmode=None, update_pack=True, verdicts=None, companions_cache=None, keep=None,
           mods_switch_path=MODS_SWITCH, scan=True, progress=None, refs=None, save_slot=None, save_info=None):
    """Switch the Mods folder to `profile` ('full' | 'fast' | 'studio' | 'save'). dry_run (default) changes nothing.

    lib: a Library for this Sims folder (default: the shared index, scanned first); needed for 'fast'/'save'
    (fastmode.park_set) and for the script/companion check. fastmode: a module-like object with
    park_set/status/update_pack (default speedkit.fastmode, imported lazily); for 'save' it must be a pack
    provider for that save's pack (speedkit.savepacks.SavePackProvider): its status/update_pack look after
    SpeedKit\\savepacks\\<save_slot>. verdicts: {pkg_id: Verdict}, a callable(lib), None (companions.classify)
    or False (no companion check). keep: override KEEP. update_pack: a stale pack is updated (real run)
    instead of refusing; refs: usedpack Refs for fastmode.update_pack (default: usedpack.scan_references of
    this Sims folder, only when an update is needed and the provider takes refs). scan: rescan lib before
    planning and after moving. save_slot: the save of the 'save' profile ('Slot_00000014'); save_info: what
    identifies it in the game ({'name', 'slot_id', 'guid'}, from speedkit.savepacks.read_header - read from
    the save when not given), written to profile_state.json for the in-game monitor.

    Returns the plan: profile, save_slot, current (before), moves [{op park|restore, what file|folder, rel,
    files, bytes, src, dst, mods}], special (packs / monitor), conflicts, target_parked, counts, manifest
    {before, after, changed, info}, cc_changed, thumbcache, pack (fast/save), notes, warnings, dry_run,
    game_running, nothing_to_do; after a real run also journal, done, verified. Raises ProfileError when
    refused (game running, damaged manifest, pack not ready, ...); a failure half-way is undone."""
    if profile not in PROFILES:
        raise ProfileError('unknown profile %r (choose one of %s)' % (profile, ', '.join(PROFILES)))
    P = Paths(sims, home, fastpack_dir)
    running = game_running() if check_game else False
    if running and not dry_run:
        raise ProfileError('The Sims 4 is running (or its state could not be checked) - close it first. Nothing was changed.')
    slot = None
    if profile == 'save':
        if not save_slot:
            raise ProfileError('Choose which save to play (save_slot=...).')
        slot = slot_key(save_slot)
        if save_info is None:
            save_info = _read_save_info(P, slot)
    doc, _exists = load_manifest(P)
    keep_source = None
    if keep is None and profile == 'studio':
        keep, keep_source = load_keep(mods_switch_path)
    elif keep is not None:
        keep_source = 'given'
    if profile in ('fast', 'save') or (profile == 'studio' and verdicts is not False):
        lib = _open_library(lib, P, scan)
    elif lib is not None:
        lib = _open_library(lib, P, False)
    fm = pack_info = pack_before = None
    if profile in ('fast', 'save'):
        if profile == 'save' and fastmode is None:
            raise ProfileError('The save profile needs the save pack tool (fastmode=savepacks.SavePackProvider(...)).')
        fm, err = _load_fastmode(fastmode)
        if fm is None:
            raise ProfileError('The fast profile needs the fast pack tool: %s' % err)
        pack_before = inventory(P).all_packs('M')
        fam = 'fast' if profile == 'fast' else _family_of_slot(slot)
        pack_info = _ensure_pack(fm, P, lib, dry_run, update_pack, check_game, progress, refs, fam)
    try:
        plan = _plan_and_run(profile, P, doc, lib, fm, keep, keep_source, verdicts, companions_cache, pack_info,
                             pack_before, dry_run, running, check_game, scan, mods_switch_path, slot, save_info)
        if not dry_run and plan.get('journal') and (pack_info or {}).get('brought_home'):
            # undo_switch of this switch also puts back the packs that were brought home for the update
            _annotate_journal(P.home, plan['journal'], 'packs_brought_home', pack_info['brought_home'])
        return plan
    except BaseException as e:
        jid = (pack_info or {}).get('brought_home')
        if not jid or dry_run:
            raise
        # the pack was taken out of Mods for its update: put it back so the old profile keeps its CC
        try:
            journal_undo(jid, home=P.home, check_game=check_game)
            extra = ' The fast pack was put back where it was.' if profile == 'fast' else \
                ' The packs were put back where they were.'
        except Exception as e2:
            extra = ' Putting the fast pack back failed too (%s: %s); undo journal %s.' % (type(e2).__name__, e2, jid)
        if not isinstance(e, Exception):
            raise
        raise ProfileError((str(e) if isinstance(e, ProfileError) else '%s: %s' % (type(e).__name__, e)) + extra)


def _annotate_journal(home, jid, key, value):
    """Add one key to a finished journal's file (journal.undo keeps unknown keys). Best effort."""
    path = os.path.join(home, 'journal', jid + '.json')
    try:
        with open(path, encoding='utf-8') as f:
            d = json.load(f)
        d[key] = value
        with open(path + '.tmp', 'w', encoding='utf-8') as f:
            json.dump(d, f, indent=1)
        os.replace(path + '.tmp', path)
    except (OSError, ValueError):
        pass


def _read_save_info(P, slot):
    """{'name', 'slot_id', 'guid'} of a save (speedkit.savepacks.read_header), or {} when it cannot be read."""
    try:
        from . import savepacks
        h = savepacks.read_header(os.path.join(P.sims, 'saves', slot + '.save'))
        return {'name': h.get('name'), 'slot_id': h.get('slot_id'), 'guid': h.get('guid')}
    except Exception:
        return {}


def _plan_and_run(profile, P, doc, lib, fm, keep, keep_source, verdicts, companions_cache, pack_info, pack_before,
                  dry_run, running, check_game, scan, mods_switch_path, slot=None, save_info=None):
    sims, home, fastpack_dir = P.sims, P.home, P.fastpack
    inv = inventory(P)
    before = current(sims=sims, home=home, fastpack_dir=fastpack_dir, keep=keep, mods_switch_path=mods_switch_path, _inv=inv)
    plan = _build_plan(profile, P, inv, doc, lib if profile != 'full' else None, fm, keep, keep_source, verdicts,
                       companions_cache, pack_info, pack_before, slot)
    plan.update(current=before['profile'], dry_run=dry_run, game_running=running, pack=pack_info, save_slot=slot)
    if running:
        plan['warnings'].insert(0, 'The Sims 4 is running: a real switch waits until it is closed.')
    if profile in ('fast', 'save'):
        fam = 'fast' if profile == 'fast' else _family_of_slot(slot)
        in_mods = {n.lower() for n in inv.family(fam)['M']}
        in_mods -= {s['rel'].lower() for s in plan['special'] if s['op'] == 'quarantine' and s['what'] == 'pack'}
        in_mods |= {s['rel'].lower() for s in plan['special'] if s['op'] == 'deploy'}
        if not in_mods:
            msg = ('The fast pack has not been built yet, so the fast profile would leave sims without their CC. '
                   'Build it first (fastpack build).' if profile == 'fast' else
                   'The pack of %s has not been built yet, so its sims would lose their CC. Prepare that save first.'
                   % slot)
            if not dry_run:
                raise ProfileError(msg + ' Nothing was changed.')
            if pack_info.get('action') != 'update':
                plan['warnings'].append(msg)
    state = read_state(sims, home)
    nothing = not plan['moves'] and not plan['special'] and not plan['manifest']['changed'] \
        and (state or {}).get('profile') == profile \
        and (profile != 'save' or ((state or {}).get('save_slot') or '').lower() == slot.lower())
    plan['nothing_to_do'] = nothing
    if dry_run or nothing:
        plan['done'] = []
        if not dry_run:
            plan['verified'] = True
        return _public(plan)
    extra = {}
    if profile == 'fast':
        extra = {'pack_dir': P.fastpack, 'installed_nowhere': _installed_nowhere(P.fastpack, 'fastpack.json')}
    elif profile == 'save':
        info = save_info or {}
        extra = {'save_slot': slot, 'pack_dir': P.save_dir(slot), 'save_name': info.get('name'),
                 'save_slot_id': info.get('slot_id'), 'save_guid': info.get('guid'),
                 'installed_nowhere': _installed_nowhere(P.save_dir(slot), 'savepack.json')}
    return _public(_execute(plan, P, inv, doc, lib, check_game, scan, extra))


def _installed_nowhere(pack_dir, manifest):
    """The CAS part ids (hex) the pack's saves use that no mod provides - installed nowhere, or only in packages
    the game never loads (the pack's manifest: 'absent' / 'unloadable'). They are missing in every mode, so
    SpeedKit Monitor does not count them as 'this mode was not prepared'."""
    try:
        with open(os.path.join(pack_dir, manifest), encoding='utf-8') as f:
            man = json.load(f)
        ids = set()
        for part in ('absent', 'unloadable'):
            ids.update((man.get(part) or {}).get('cas') or [])
        return sorted(i for i in ids if isinstance(i, str))
    except (OSError, ValueError, AttributeError):
        return []


def _quarantine_thumbcache(P, profile, check_game):
    """Move localthumbcache.package into quarantine through its own small 'profile' journal, opened
    BEFORE the switch's journal. It is kept out of the switch's journal on purpose: the game rebuilds
    the file on its next start, and a rebuilt cache sitting where the old one was would make
    journal.undo refuse to undo the whole switch ('something is in its place'). Returns the journal id."""
    try:
        tj = Journal('profile', 'thumbnail cache moved aside before the switch to %s (the game rebuilds it)' % profile,
                     home=P.home, sims=P.sims, check_game=check_game)
    except JournalError as e:
        raise ProfileError('%s Nothing was changed.' % e)
    try:
        with tj:
            tj.quarantine(P.thumbcache)
    except BaseException as e:
        try:
            journal_undo(tj.id, home=P.home, check_game=check_game)
        except Exception:
            pass
        if not isinstance(e, Exception):
            raise
        raise ProfileError('The thumbnail cache could not be moved aside (%s: %s). Nothing was changed.'
                           % (type(e).__name__, e))
    return tj.id


def _execute(plan, P, inv, doc, lib, check_game, scan, extra=None):
    """Carry out a plan inside one 'profile' journal; undo it automatically if a step fails (Ctrl+C
    included). The thumbnail cache, when the loaded CC changes, goes first through its own journal."""
    profile = plan['profile']
    cand = _tidy_candidates(plan['moves'])
    note = 'switch to %s: park %d files (%.1f GB), restore %d files (%.1f GB)' % (
        profile, plan['counts']['park_files'], _gb(plan['counts']['park_bytes']),
        plan['counts']['restore_files'], _gb(plan['counts']['restore_bytes']))
    done = []
    tj = None
    if plan['cc_changed'] and os.path.exists(P.thumbcache):
        tj = _quarantine_thumbcache(P, profile, check_game)
        done.append(('quarantine', THUMBCACHE))
    try:
        j = Journal('profile', note, home=P.home, sims=P.sims, check_game=check_game)
    except BaseException as e:
        _undo_quietly(tj, P, check_game)
        if not isinstance(e, Exception):
            raise
        raise ProfileError('%s Nothing was changed.' % e)
    staging = os.path.join(P.home, 'staging', j.id)
    try:
        with j:
            for mv in plan['moves']:
                j.move(mv['src'], mv['dst'])
                done.append((mv['op'], mv['rel']))
            for s in plan['special']:
                if s['op'] == 'quarantine':
                    j.quarantine(s['src'])
                else:
                    j.move(s['src'], s['dst'])
                done.append((s['op'], s['rel']))
            _tidy(P, cand['M'], cand['P'], _protect(P, doc['moved']))
            inv2 = inventory(P)
            p_files = {k: it.p_rel for k, it in inv2.items.items() if it.p_rel is not None}
            p_files.update({_key(n): n for n in inv2.all_packs('P')})
            if inv2.monitor_parked:
                p_files[_key(inv2.monitor_parked)] = inv2.monitor_parked
            entries, minfo = rebuild_manifest(doc['moved'], p_files, inv2.p_dirs, inv2.m_keys(), _special_keys(inv))
            if entries != doc['moved']:
                new_doc = dict(doc)
                new_doc['moved'] = entries
                _journal_json(j, staging, P.manifest, new_doc)
                done.append(('manifest', '%d entries' % len(entries)))
            plan['manifest'].update(after=len(entries), changed=entries != doc['moved'], info=minfo)
            _journal_json(j, staging, P.state, _state_doc(profile, inv2, extra))
            done.append(('state', profile))
    except BaseException as e:                      # a failed step, the game starting, or Ctrl+C
        msg = '%s: %s' % (type(e).__name__, e)
        try:
            journal_undo(j.id, home=P.home, check_game=check_game)
            created = _created_dirs(inv, P)
            _tidy(P, created['M'], created['P'], _protect(P, doc['moved']))
            _undo_quietly(tj, P, check_game)       # the thumbnail cache too (disposable: best effort)
            back = 'Everything was put back as it was.'
        except Exception as e2:
            back = 'Putting things back failed too (%s: %s); close the game if it runs, then undo journal %s.' % (
                type(e2).__name__, e2, j.id)
        _drop_empty(staging)
        if not isinstance(e, Exception):
            raise
        raise ProfileError('Switching to %s stopped: %s. %s' % (profile, msg, back))
    _drop_empty(staging)
    plan['journal'] = j.id
    plan['thumbcache_journal'] = tj
    plan['done'] = done
    # bookkeeping + checks (SpeedKit's own record file; read-only otherwise)
    try:
        _write_record(P, profile, [_any_rel(it) for it in inv2.items.values() if it.p_rel is not None and it.m_rel is None])
    except OSError as e:
        plan['warnings'].append('could not write the profile record (%s)' % e)
    if lib is not None and scan:
        try:
            lib.scan()
        except Exception as e:
            plan['warnings'].append('library rescan failed (%s)' % e)
    chk = check_manifest(P.sims)
    plan['manifest']['check'] = {k: chk[k] for k in ('ok', 'unlisted', 'blocked', 'in_both', 'nested')}
    parked_now = inv2.parked_keys()
    want = {_key(r) for r in plan['target_parked']} - {_key(c) for c in plan['conflicts']}
    missing = sorted(want - parked_now)
    extra = sorted(parked_now - want)
    plan['verified'] = chk['ok'] and not missing and not extra
    if not plan['verified']:
        plan['warnings'].append('after the switch: %d file(s) not parked as planned, %d parked but not planned, '
                                'parking list ok=%s' % (len(missing), len(extra), chk['ok']))
    return plan


def _undo_quietly(jid, P, check_game):
    """Undo a small helper journal (the thumbnail cache) if there is one; a failure is not an error -
    the game rebuilds that file anyway."""
    if not jid:
        return
    try:
        journal_undo(jid, home=P.home, check_game=check_game)
    except Exception:
        pass


def _created_dirs(inv, P):
    """{'M': keys, 'P': keys} of folders that did not exist before the switch (removed again if empty)."""
    out = {'M': set(), 'P': set()}
    for side, before in (('M', inv.m_dirs), ('P', inv.p_dirs)):
        root = P.root(side)
        if not os.path.isdir(root):
            continue
        for dp, dn, fn in os.walk(root):
            if side == 'P' and os.path.normcase(dp) == os.path.normcase(root):
                dn[:] = [d for d in dn if d.lower() != OLD_CACHES]
            for d in dn:
                k = _key(os.path.relpath(os.path.join(dp, d), root))
                if k not in before:
                    out[side].add(k)
    return out


def _drop_empty(d):
    for p in (d, os.path.dirname(d)):
        try:
            os.rmdir(p)
        except OSError:
            break


# ------------------------------------------------------------------ what is active now
def current(lib=None, sims=SIMS, home=None, fastpack_dir=None, fastmode=None, keep=None, mods_switch_path=MODS_SWITCH,
            _inv=None):
    """Which profile the folders match now: {'profile': 'full'|'fast'|'studio'|'save'|'custom', 'save_slot'
    (the save whose pack is in Mods, for 'save'), 'closest', 'differences' (for the closest: to_park /
    to_restore rels, pack), 'per_profile', 'mods', 'parked', 'conflicts', 'notes'}. Read-only. 'fast' and
    'save' are recognised from the parked set of the last SpeedKit fast/save switch
    (SpeedKit\\profiles\\last_fast.json / last_save.json), else from fastmode.park_set(lib) when lib is
    given; they differ by the pack at the Mods root (the fast pack, or one save's pack)."""
    P = Paths(sims, home, fastpack_dir)
    inv = _inv or inventory(P)
    if keep is None:
        keep, _ = load_keep(mods_switch_path)
    parked_now = inv.parked_keys()
    targets = {}
    targets['full'] = [set()]
    studio_t, _ = compute_target('studio', inv, keep)
    targets['studio'] = [{k for k, s in studio_t.items() if s == 'P'}]
    rec = _read_record(P, 'studio')
    if rec is not None:
        targets['studio'].append(rec & set(inv.items))
    fast_sets = []
    for rec in (_read_record(P, 'fast'), _read_record(P, 'save')):
        if rec is not None:
            fast_sets.append(rec & set(inv.items))
    if lib is not None:
        fm, err = _load_fastmode(fastmode)
        if fm is not None:
            try:
                ft, _ = compute_target('fast', inv, park_rels=_fast_park_rels(fm, lib))
                fast_sets.append({k for k, s in ft.items() if s == 'P'})
            except Exception:
                pass
    targets['fast'] = fast_sets
    targets['save'] = fast_sets
    conflicts = {k for k, it in inv.items.items() if it.m_rel is not None and it.p_rel is not None}
    deployed = inv.deployed()
    saves_in = sorted(f for f in deployed if f.startswith('save:'))
    per, best = {}, None
    for name in PROFILES:
        if name == 'fast':
            pack_ok = 'fast' in deployed and not saves_in
        elif name == 'save':
            pack_ok = len(saves_in) == 1 and 'fast' not in deployed
        else:
            pack_ok = not deployed
        if not targets[name]:
            per[name] = {'known': False, 'match': False, 'to_park': None, 'to_restore': None, 'pack_ok': pack_ok}
            continue
        opts = []
        for t in targets[name]:
            to_park = sorted(t - parked_now - conflicts)
            to_restore = sorted(parked_now - t)
            opts.append((len(to_park) + len(to_restore), to_park, to_restore))
        n, to_park, to_restore = min(opts)
        match = n == 0 and pack_ok
        per[name] = {'known': True, 'match': match, 'to_park': len(to_park), 'to_restore': len(to_restore),
                     'pack_ok': pack_ok, '_lists': (to_park, to_restore)}
        score = n + (0 if pack_ok else 1)
        if best is None or score < best[0]:
            best = (score, name)
    matched = [n for n in ('full', 'studio', 'fast', 'save') if per[n].get('match')]
    profile = matched[0] if matched else 'custom'
    closest = profile if matched else (best[1] if best else None)
    diff = {}
    if closest and per[closest].get('known'):
        tp, tr = per[closest]['_lists']
        diff = {'to_park': [_any_rel(inv.items[k]) for k in tp[:SHOW]], 'to_park_count': len(tp),
                'to_restore': [_any_rel(inv.items[k]) for k in tr[:SHOW]], 'to_restore_count': len(tr),
                'pack': None if per[closest]['pack_ok'] else (
                    'fast pack is not in Mods' if closest == 'fast' else
                    'not exactly one save pack is in Mods' if closest == 'save' else
                    '%s in Mods' % ('fast pack is' if list(deployed) == ['fast'] else 'SpeedKit packs are'))}
    for v in per.values():
        v.pop('_lists', None)
    notes = []
    if inv.monitor_parked and not inv.monitor_mods:
        notes.append('SpeedKit Monitor was parked (by the Mods switch tool); any SpeedKit switch puts it back.')
    if inv.pack_parked:
        notes.append('%d fast pack file(s) sit in Mods_parked; any SpeedKit switch moves them to the right place.' % len(inv.pack_parked))
    parked_saves = [n for fam, f in inv.packs.items() if fam != 'fast' for n in f['P']]
    if parked_saves:
        notes.append('%d save pack file(s) sit in Mods_parked; any SpeedKit switch moves them to the right place.'
                     % len(parked_saves))
    if len(saves_in) > 1:
        notes.append('The packs of %d saves are in Mods at once; switch profile to tidy that up.' % len(saves_in))
    if conflicts:
        notes.append('%d path(s) exist in both Mods and Mods_parked (the Mods copy is used).' % len(conflicts))
    if not per['fast']['known']:
        notes.append("'fast' is recognised after the first SpeedKit fast switch (or when a library index is given).")
    m_n, m_b = inv.totals('M')
    p_n, p_b = inv.totals('P')
    save_slot = 'Slot_' + saves_in[0].split(':', 1)[1] if len(saves_in) == 1 else None
    return {'profile': profile, 'save_slot': save_slot if profile == 'save' else None,
            'deployed_save': save_slot, 'closest': closest, 'differences': diff, 'per_profile': per,
            'mods': {'files': m_n, 'bytes': m_b}, 'parked': {'files': p_n, 'bytes': p_b},
            'conflicts': sorted(inv.items[k].m_rel for k in conflicts), 'notes': notes,
            'fast_pack': {'in_mods': inv.pack_mods, 'in_fastpack': inv.pack_home, 'in_parked': inv.pack_parked},
            'save_packs': {'Slot_' + fam.split(':', 1)[1]: {'in_mods': f['M'], 'in_folder': f['H'], 'in_parked': f['P']}
                           for fam, f in sorted(inv.packs.items()) if fam != 'fast'},
            'monitor': 'in Mods' if inv.monitor_mods else ('parked' if inv.monitor_parked else 'not installed')}


def status(lib=None, sims=SIMS, home=None, fastpack_dir=None, fastmode=None, pack_status=True):
    """Everything a human wants to know about profiles (read-only): current(), the state file, the
    manifest check, the fast pack, the KEEP source, unfinished profile journals, whether the game runs."""
    P = Paths(sims, home, fastpack_dir)
    keep, keep_source = load_keep()
    cur = current(lib=lib, sims=sims, home=home, fastpack_dir=fastpack_dir, fastmode=fastmode, keep=keep)
    st = read_state(sims, home)
    out = {'current': cur, 'state_file': st,
           'state_matches': bool(st) and st.get('profile') == cur['profile'],
           'manifest': check_manifest(sims), 'keep_source': keep_source, 'game_running': game_running()}
    pack = dict(cur['fast_pack'])
    if pack_status:
        fm, err = _load_fastmode(fastmode)
        if fm is None:
            pack['status'] = err
        else:
            fresh, why, _raw = _pack_status(fm, P, lib)
            pack['fresh'] = fresh
            pack['why'] = why
    out['fast_pack'] = pack
    out['unfinished_journals'] = [j for j in list_journals(P.home) if j[1] == 'profile' and j[2] not in ('committed', 'undone')]
    return out


def format_status(st):
    """Plain-language lines for status()."""
    c = st['current']
    lines = []
    name = c['profile']
    if name == 'custom':
        lines.append('Mods profile: custom (closest: %s)' % (c['closest'] or '-'))
        d = c.get('differences') or {}
        if d.get('to_park_count'):
            lines.append('  %d file(s) would still be parked, e.g. %s' % (d['to_park_count'], ', '.join(d['to_park'][:3])))
        if d.get('to_restore_count'):
            lines.append('  %d parked file(s) would come back, e.g. %s' % (d['to_restore_count'], ', '.join(d['to_restore'][:3])))
        if d.get('pack'):
            lines.append('  ' + d['pack'])
    elif name == 'save':
        lines.append('Mods profile: save (only the CC of %s)' % c.get('save_slot'))
    else:
        lines.append('Mods profile: %s' % name)
    lines.append('  in Mods: %d files, %.1f GB; parked: %d files, %.1f GB' % (
        c['mods']['files'], _gb(c['mods']['bytes']), c['parked']['files'], _gb(c['parked']['bytes'])))
    s = st.get('state_file')
    if s and not st.get('state_matches'):
        lines.append('  note: SpeedKit last switched to %s (%s); the folders changed since.' % (s.get('profile'), s.get('switched')))
    p = st.get('fast_pack') or {}
    where = 'in Mods' if p.get('in_mods') else ('built, not in Mods' if p.get('in_fastpack') else 'not built')
    fresh = p.get('fresh')
    lines.append('  fast pack: %s%s' % (where, '' if fresh is None else (', up to date' if fresh else ', out of date (%s)' % (p.get('why') or '?'))))
    for slot, sp in sorted((c.get('save_packs') or {}).items()):
        lines.append('  save pack of %s: %s' % (slot, 'in Mods' if sp['in_mods'] else
                                                ('built, not in Mods' if sp['in_folder'] else 'parked')))
    lines.append('  SpeedKit Monitor: %s' % c['monitor'])
    m = st.get('manifest') or {}
    if m.get('error'):
        lines.append('  PROBLEM: ' + m['error'])
    elif not m.get('ok'):
        lines.append('  parking list: %d unlisted, %d blocked, %d nested entries - the next SpeedKit switch repairs it'
                     % (len(m['unlisted']), len(m['blocked']), len(m['nested'])))
    for n in c.get('notes', []):
        lines.append('  note: ' + n)
    if st.get('unfinished_journals'):
        lines.append('  %d unfinished profile switch(es): %s' % (len(st['unfinished_journals']),
                                                                ', '.join(j[0] for j in st['unfinished_journals'])))
    if st.get('game_running'):
        lines.append('  The Sims 4 is running: switching waits until it is closed.')
    return '\n'.join(lines)


def format_plan(plan):
    """Plain-language summary of a switch() result."""
    c = plan['counts']
    lines = ['%s %s (now: %s)' % ('Would switch to' if plan['dry_run'] else 'Switched to', plan['profile'], plan['current'])]
    if plan.get('nothing_to_do'):
        lines.append('  already there - nothing to do')
        return '\n'.join(lines)
    lines.append('  park %d files (%.1f GB), bring back %d files (%.1f GB) in %d moves (%d folders, %d files)' % (
        c['park_files'], _gb(c['park_bytes']), c['restore_files'], _gb(c['restore_bytes']), c['moves'],
        c['folder_moves'], c['file_moves']))
    lines.append('  after: %d files (%.1f GB) in Mods, %d files (%.1f GB) parked' % (
        c['mods_after']['files'], _gb(c['mods_after']['bytes']), c['parked_after']['files'], _gb(c['parked_after']['bytes'])))
    for s in plan.get('special', []):
        lines.append('  %s %s' % (s['op'], s['rel']))
    pk = plan.get('pack')
    if pk:
        lines.append('  fast pack: %s%s' % ('up to date' if pk.get('fresh') else 'out of date (%s)' % (pk.get('why') or '?'),
                                            '' if pk.get('action') in (None, 'none') else ' -> ' + pk['action']))
    m = plan['manifest']
    lines.append('  parking list: %d -> %d entries%s' % (m['before'], m['after'], '' if m['changed'] else ' (unchanged)'))
    if plan.get('thumbcache'):
        lines.append('  thumbnail cache: moved aside (the game rebuilds it)')
    for n in plan.get('notes', [])[:10]:
        lines.append('  note: ' + n)
    for w in plan.get('warnings', []):
        lines.append('  WARNING: ' + w)
    if plan.get('journal'):
        lines.append('  undo: journal %s' % plan['journal'])
    return '\n'.join(lines)


def undo_switch(journal_id, dry_run=True, sims=SIMS, home=None, check_game=True):
    """Undo a profile switch: journal.undo(), then remove the folders the switch had created (in Mods
    and Mods_parked) that are empty again (see _tidy) - a leftover empty Mods\\sim would make
    mods_switch.py's 'full' skip a 'sim/' entry. Returns the undo actions. Use this rather than
    journal.undo for 'profile' journals; other kinds are refused, and every refusal is a ProfileError
    with a plain message. The thumbnail cache is not part of a switch's journal (plan
    ['thumbcache_journal'] holds it), so a cache the game rebuilt since never blocks the undo."""
    P = Paths(sims, home)
    cand = {'M': set(), 'P': set()}
    try:
        with open(os.path.join(P.home, 'journal', journal_id + '.json'), encoding='utf-8') as f:
            jdoc = json.load(f)
    except (OSError, ValueError) as e:
        raise ProfileError('There is no readable SpeedKit journal %s (%s).' % (journal_id, e))
    if jdoc.get('kind') != 'profile':
        raise ProfileError('Journal %s is a %r change, not a profile switch; undo it with the tool that made it.'
                           % (journal_id, jdoc.get('kind')))
    for s in jdoc.get('steps', []):
        dst = s.get('dst') if s.get('op') == 'move' else None
        for side, root in (('M', P.mods), ('P', P.parked)):
            if dst and _inside_dir(dst, root):
                cand[side].update(_ancestors(_key(os.path.relpath(dst, root))))
    try:
        acts = journal_undo(journal_id, home=P.home, check_game=check_game, dry_run=dry_run)
    except JournalError as e:
        raise ProfileError('The switch %s cannot be undone: %s. Nothing was changed.' % (journal_id, e))
    except OSError as e:                            # a file in use half-way: the undo resumes where it stopped
        raise ProfileError('Undoing %s stopped half-way (%s: %s). Close whatever uses that file, then run the '
                           'same undo again - it continues where it stopped.' % (journal_id, type(e).__name__, e))
    helper = jdoc.get('packs_brought_home')
    if helper:
        # the packs this switch's update had brought home go back where they were (Mods root / parked)
        try:
            with open(os.path.join(P.home, 'journal', helper + '.json'), encoding='utf-8') as f:
                hstate = json.load(f).get('state')
        except (OSError, ValueError):
            hstate = None
        if hstate == 'committed':
            try:
                acts = list(acts) + list(journal_undo(helper, home=P.home, check_game=check_game, dry_run=dry_run))
            except (JournalError, OSError) as e:
                acts = list(acts) + [('packs could not be put back (%s); undo journal %s' % (e, helper), None)]
    if not dry_run:
        try:
            doc, _ = load_manifest(P)
            protect = _protect(P, doc['moved'])
        except ProfileError:
            protect = set(_key(os.path.relpath(os.path.join(dp, d), P.parked))
                          for dp, dn, fn in os.walk(P.parked) for d in dn) if os.path.isdir(P.parked) else set()
        _tidy(P, cand['M'], cand['P'], protect)
    return acts


def _inside_dir(path, base):
    path, base = os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.abspath(base))
    return path.startswith(base.rstrip('\\/') + os.sep)


# ------------------------------------------------------------------ command line
def main(argv=None):
    import argparse
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(errors='backslashreplace')
    ap = argparse.ArgumentParser(description='SpeedKit Mods profiles: full / fast / studio (dry run unless --apply).')
    sub = ap.add_subparsers(dest='cmd')
    sub.add_parser('status')
    sub.add_parser('check', help='check Mods_parked\\_manifest.json against the folders')
    sw = sub.add_parser('switch')
    sw.add_argument('profile', choices=PROFILES)
    sw.add_argument('--slot', default=None, help="save: the save slot, e.g. Slot_00000014 (use 'python -m speedkit play save:<slot>' to build its pack)")
    sw.add_argument('--apply', action='store_true', help='really move files (default: dry run)')
    sw.add_argument('--no-update', action='store_true', help='do not update a stale fast pack (refuse instead)')
    sw.add_argument('--json', action='store_true')
    un = sub.add_parser('undo')
    un.add_argument('journal')
    un.add_argument('--apply', action='store_true')
    a = ap.parse_args(argv)
    try:
        if a.cmd == 'switch':
            fm = None
            if a.profile == 'save':
                from . import savepacks
                fm = savepacks.SavePackProvider(a.slot)
            plan = switch(a.profile, dry_run=not a.apply, update_pack=not a.no_update, save_slot=a.slot, fastmode=fm)
            print(json.dumps(plan, indent=1, default=str) if a.json else format_plan(plan))
        elif a.cmd == 'check':
            print(json.dumps(check_manifest(), indent=1))
        elif a.cmd == 'undo':
            for what, p in undo_switch(a.journal, dry_run=not a.apply):
                print('  %s %s' % (what, p))
        else:
            print(format_status(status()))
    except ProfileError as e:
        print(str(e))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
