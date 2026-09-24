"""savepacks - 'Play this save': a pack of only the custom content one save uses.

The user picks one save; the game then loads only the CC that save's sims wear and its lots use (every
sim, every lot in every world of that save), plus everything the fast profile keeps loading anyway:
script mods, their tuning, animations and default replacements. Mechanics:

    saves = list_saves()                              # current slots: name, household, world, sims, lots
    refs1 = scan_one(saves_dir, 'Slot_00000014')      # usedpack refs of that one save file (cached)
    plan = plan_save_pack(lib, refs1, 'Slot_00000014', parked, bc_cache=...)   # read-only
    update_save_pack(lib, refs1, 'Slot_00000014', home, dry_run=False)          # build / delta / nothing
    status('Slot_00000014', home)                     # fresh / stale / missing, and why

The save pack is a fast pack (speedkit.fastmode) whose part (a) - the CC the saves use - covers this one
save instead of every save and Tray item; parts (b) and (c) (script/tuning content, EA overrides, what
kept CC and tuning need) do not depend on saves and come from fastmode's b/c cache, so preparing a second
save costs only its own part. Its files are '!!!!!SpeedKit_Save_<the slot's 8 hex digits>_###.package'
(fastmode.save_kind): they sort right after the fast pack's name, before every mod, so their copies win
like the fast pack's, and the slot in the name tells the profile switcher which folder a file belongs to.
A pack lives in <Sims 4>\\SpeedKit\\savepacks\\<slot>\\ (savepack.json, savepack_keys.tsv and, while that
save is not being played, the .package files). speedkit.profiles.switch('save', save_slot=...) puts it at
the Mods root (SavePackProvider is the pack tool it talks to).

The save's own name, played household, world, sims and lots come from its SaveGameData protobuf, with
the field numbers of the game's schemas (Game\\Bin\\Python\\generated.zip, FileSerialization.proto):
  SaveGameData: guid 1, save_slot 2 (SaveSlotData), neighborhoods 4, households 5, sims 6, zones 7
  SaveSlotData: slot_id 1, last_neighborhood 3, last_zone 5, slot_name 9, active_household_id 11
  HouseholdData: household_id 2, name 3, home_zone 4;  ZoneData: zone_id 1, name 2, neighborhood_id 10
  NeighborhoodData: neighborhood_id 1, name 3 (the world's name, e.g. 'Willow Creek')
slot_id is what the game wrote into the file; a save copied by the game's recovery keeps its original's
(Slot_00000018 holds 23 = 0x17), so the in-game check compares name + slot id + guid, not the id alone.
Reading is read-only and uses usedpack's share-delete opener (the game can rotate a save meanwhile).
"""
import collections
import datetime
import io
import os
import re
import time

from .dbpf import read_entries, decompress, DELETED
from .library import SIMS
from . import usedpack as U
from . import fastmode as F

SAVES = os.path.join(SIMS, 'saves')
HOME = os.path.join(SIMS, 'SpeedKit')
SAVEPACKS = 'savepacks'
SLOT_RX = re.compile(r'^Slot_([0-9A-Fa-f]{8})$', re.I)
T_SAVEGAME = 0x0D


class SaveError(Exception):
    """A save cannot be used as asked (the message says why in plain words)."""


# ------------------------------------------------------------------------------------------ slots
def slot_name(x):
    """'Slot_<hex>' (lower-case hex, the game's own spelling) for 'Slot_00000014', 'Slot_00000014.save', a
    path to it or 'save:Slot_00000014'. SaveError otherwise."""
    s = (x or '').strip()
    if s.lower().startswith('save:'):
        s = s[5:]
    s = os.path.basename(s.replace('/', os.sep))
    if s.lower().endswith('.save'):
        s = s[:-5]
    m = SLOT_RX.match(s)
    if not m:
        raise SaveError('%r is not a save slot (expected Slot_ and 8 hex digits, like Slot_00000014)' % (x,))
    return 'Slot_' + m.group(1).lower()


def pack_dir(home, slot):
    """<home>\\savepacks\\<slot>: where a save's pack lives while that save is not being played."""
    return os.path.join(home, SAVEPACKS, slot_name(slot))


def kind(slot):
    """fastmode.PackKind of a save's pack."""
    return F.save_kind(slot_name(slot))


def pack_names(home, slot, mods_dir=None):
    """Names of the save pack's files, wherever they are now (its folder or the Mods root)."""
    k = kind(slot)
    out = set()
    for d in (pack_dir(home, slot), mods_dir):
        if d and os.path.isdir(d):
            out.update(n for n in os.listdir(d) if k.matches(n))
    return sorted(out)


# ------------------------------------------------------------------------------------------ headers
_HEADERS = {}


def _text(b, span):
    return U._text(b, span) if isinstance(span, tuple) else ''


def read_header(path):
    """The save's own facts: {'slot', 'file', 'name', 'household', 'household_id', 'world', 'sims', 'lots',
    'households', 'worlds', 'slot_id', 'guid', 'last_played' (ISO, file mtime), 'mtime', 'size', 'size_mb'}.
    Read-only; cached by path, size and mtime. Raises SaveError when the file is not a readable save."""
    try:
        st = os.stat(path)
    except OSError as e:
        raise SaveError('the save %s cannot be read (%s)' % (os.path.basename(path), e))
    ck = (os.path.normcase(os.path.abspath(path)), st.st_size, st.st_mtime_ns)
    if ck in _HEADERS:
        return dict(_HEADERS[ck])
    try:
        blob = U._read_file(path)
        data = None
        for e in read_entries(io.BytesIO(blob)):
            if e.t == T_SAVEGAME and e.comp != DELETED:
                data = decompress(blob[e.off:e.off + e.fsize], e.comp, e.msize)
                break
    except Exception as e:
        raise SaveError('the save %s cannot be read (%s: %s)' % (os.path.basename(path), type(e).__name__, e))
    if data is None:
        raise SaveError('the save %s holds no game data' % os.path.basename(path))
    top = U.parse_message(data)
    if top is None:
        raise SaveError('the save %s is damaged (its game data does not parse)' % os.path.basename(path))
    slot_fields = []
    households, zones, hoods = {}, {}, {}
    sims = 0
    for f, wt, v in top:
        if wt != 2:
            continue
        if f == 2:
            slot_fields = U.parse_message(data, *v) or []
        elif f == 6:
            sims += 1
        elif f == 5:
            m = U.parse_message(data, *v) or []
            households[U._first(m, 2, 0)] = (_text(data, U._first(m, 3)), U._first(m, 4, 0))
        elif f == 7:
            m = U.parse_message(data, *v) or []
            zones[U._first(m, 1, 0)] = (_text(data, U._first(m, 2)), U._first(m, 10, 0))
        elif f == 4:
            m = U.parse_message(data, *v) or []
            hoods[U._first(m, 1, 0)] = _text(data, U._first(m, 3))
    name = _text(data, U._first(slot_fields, 9)) or None
    ahh = U._first(slot_fields, 11)
    household = households.get(ahh, ('', 0))[0] or None if ahh else None

    def world_of_zone(z):
        zz = zones.get(z)
        return (hoods.get(zz[1]) or None) if zz else None
    world = None
    if ahh and ahh in households:
        world = world_of_zone(households[ahh][1])
    if not world:
        world = world_of_zone(U._first(slot_fields, 5, 0)) or (hoods.get(U._first(slot_fields, 3, 0)) or None)
    slot = os.path.splitext(os.path.basename(path))[0]
    out = {'slot': slot, 'file': path, 'name': name, 'household': household, 'household_id': ahh,
           'world': world, 'sims': sims, 'lots': len(zones), 'households': len(households),
           'worlds': sorted({n for n in hoods.values() if n}), 'slot_id': U._first(slot_fields, 1),
           'guid': U._first(top, 1), 'mtime': st.st_mtime, 'size': st.st_size,
           'size_mb': round(st.st_size / 1e6, 1),
           'last_played': datetime.datetime.fromtimestamp(st.st_mtime).isoformat(timespec='seconds')}
    _HEADERS[ck] = dict(out)
    return out


def list_slot_files(saves_dir=SAVES):
    """[(slot, path)] of the current save slots (Slot_XXXXXXXX.save; .ver backups are not saves you play)."""
    out = []
    if os.path.isdir(saves_dir):
        for n in sorted(os.listdir(saves_dir)):
            stem, ext = os.path.splitext(n)
            p = os.path.join(saves_dir, n)
            if ext.lower() == '.save' and SLOT_RX.match(stem) and os.path.isfile(p):
                out.append((stem, p))
    return out


def list_saves(saves_dir=SAVES):
    """read_header of every current slot, newest first. A save that cannot be read is listed with
    'error' (and name None) instead of stopping the list."""
    out = []
    for slot, path in list_slot_files(saves_dir):
        try:
            out.append(read_header(path))
        except SaveError as e:
            try:
                st = os.stat(path)
                mtime, size = st.st_mtime, st.st_size
            except OSError:
                mtime, size = 0, 0
            out.append({'slot': slot, 'file': path, 'name': None, 'household': None, 'world': None, 'sims': 0,
                        'lots': 0, 'slot_id': None, 'guid': None, 'mtime': mtime, 'size': size,
                        'size_mb': round(size / 1e6, 1), 'error': str(e),
                        'last_played': datetime.datetime.fromtimestamp(mtime).isoformat(timespec='seconds')})
    out.sort(key=lambda h: -h['mtime'])
    return out


# ------------------------------------------------------------------------------------------ references
def save_refs(refs, slot):
    """usedpack Refs restricted to the one current save file of `slot` (no other save, no Tray, no backup).
    SaveError when refs does not hold that save or has no scan result for it."""
    slot = slot_name(slot)
    want = slot.lower() + '.save'
    sources = [s for s in refs.sources if s.kind == 'save' and s.name.lower() == want]
    if not sources:
        raise SaveError('the save %s was not found' % slot)
    by_fp = {s.fp: refs.by_fp[s.fp] for s in sources if s.fp in refs.by_fp}
    sims = {s.fp: refs.sims.get(s.fp, []) for s in sources}
    out = U.Refs(sources, by_fp, sims, dict(refs.stats or {}), False)
    if out.unparsed():
        raise SaveError('the save %s could not be read (%s) - the game may be saving it; try again in a minute'
                        % (slot, (refs.stats.get('errors') or {}).get(sources[0].name, 'no scan result')))
    return out


def scan_one(saves_dir, slot, cache_db=U.DEFAULT_REFS_DB):
    """usedpack Refs of one save file only, parsing it when its content is not in the refs cache yet (the
    same cache and fingerprints as usedpack.scan_references, whose other rows are left alone). Read-only
    on the save. SaveError when the save is missing or cannot be parsed now (the game saving it)."""
    slot = slot_name(slot)
    path = os.path.join(saves_dir, slot + '.save')
    try:
        st = os.stat(path)
    except OSError:
        raise SaveError('the save %s was not found' % slot)
    db = U._open_refs_db(cache_db)
    try:
        row = db.execute('select size, mtime_ns, fp from seen where path=?', (path,)).fetchone()
        if row and row[0] == st.st_size and row[1] == st.st_mtime_ns:
            fp = row[2]
        else:
            fp = U.fingerprint(path, st.st_size)
            db.execute('insert or replace into seen values(?,?,?,?)', (path, st.st_size, st.st_mtime_ns, fp))
            db.commit()
        errors = {}
        if not db.execute('select 1 from src where fp=?', (fp,)).fetchone():
            _p, res, err = U._scan_job((path, 'save', fp))
            if err:
                errors[os.path.basename(path)] = err
            else:
                U._store(db, fp, 'save', st.st_size, res)
        src = U.Source(path, os.path.basename(path), 'save', True, st.st_size, st.st_mtime_ns, fp)
        refs = U._load_refs(db, [src], False)
        refs.stats.update({'sources': 1, 'errors': errors})
    finally:
        db.close()
    if errors:
        raise SaveError('the save %s could not be read (%s) - the game may be saving it; try again in a minute'
                        % (slot, errors[os.path.basename(path)]))
    return refs


def save_usage(lib, refs, game, parked=None, roots=F.ROOTS2):
    """Per current save slot in refs: {slot: {'cc_parts', 'cc_missing', 'pack_casp'}} - the CC CAS parts
    it uses that the library loads (EA's own parts and library overrides of them left out), the CC CAS
    parts it uses that are installed nowhere, and the CAS part keys its save pack's part (a) would hold
    (the full library's winner copy, when that copy is in a parked package). Read-only."""
    view = F._view(lib)
    pl = U._Planner(view, tuple(roots), game)
    per = {}
    allv = set()
    for s in refs.sources:
        if s.kind != 'save' or s.fp not in refs.by_fp or not SLOT_RX.match(os.path.splitext(s.name)[0]):
            continue
        ids = set(refs.by_fp[s.fp].get(U.PART, ())) | set(refs.by_fp[s.fp].get(U.PART_OTHER, ()))
        per[slot_name(s.name)] = ids
        allv |= ids
    rows, present = pl.by_instance([U.T_CASP], allv)
    loaded = {}
    for k, row in rows.items():
        loaded.setdefault(k[2], []).append((k, row))
    parked_rels = {rel.upper() for _, rel in (parked or [])}
    pkgs = pl.pkgs
    out = {}
    for slot, ids in per.items():
        cc = [v for v in ids if v in loaded and not game.has(U.T_CASP, v)]
        missing = [v for v in ids if v >= U.BIG and v not in present and not game.has(U.T_CASP, v)]
        casp = set()
        if parked is not None:
            for v in ids:
                for k, row in loaded.get(v, ()):
                    if pkgs[row[1]].rel.upper() in parked_rels:
                        casp.add(k)
        out[slot] = {'cc_parts': len(cc), 'cc_missing': len(missing), 'pack_casp': casp}
    return out


# ------------------------------------------------------------------------------------------ the pack
def plan_save_pack(lib, refs, slot, parked=None, **plan_kw):
    """fastmode.plan_pack for one save: part (a) from that save only (refs may hold more; they are narrowed
    with save_refs), parts (b)/(c) as the fast pack's (pass bc_cache= to reuse them). Read-only."""
    k = kind(slot)
    plan_kw.setdefault('pack_name', k.name(1))
    return F.plan_pack(lib, save_refs(refs, slot), parked, **plan_kw)


def status(slot, home=HOME, root_dirs=None, saves_dir=None, check_saves=True):
    """Is the save pack of `slot` up to date? fastmode.status for that pack family (its own save file is the
    only save that counts) plus 'gb' (size on disk) and 'dir'. A save that is gone makes it 'stale'."""
    slot = slot_name(slot)
    out_dir = pack_dir(home, slot)
    st = F.status(out_dir, root_dirs, saves_dir, None, check_saves=check_saves, kind=kind(slot))
    st['dir'] = out_dir
    st['gb'] = round(st['bytes'] / 1e9, 2) if st.get('bytes') else None
    if st['state'] != 'missing' and saves_dir and not os.path.exists(os.path.join(saves_dir, slot + '.save')):
        st['state'] = 'stale'
        st['why'] = list(st['why']) + ['the save %s is gone' % slot]
    return st


def update_save_pack(lib, refs, slot, home=HOME, sims=None, dry_run=True, check_game=False, prune=True, **plan_kw):
    """fastmode.update_pack for one save's pack in <home>\\savepacks\\<slot>: nothing / refresh / a delta /
    a rebuild. refs may hold every save (it is narrowed to this one). prune keeps only the newest previous
    copy of each pack in SpeedKit's quarantine. plan_kw go to plan_pack (bc_cache, game, cache_path ...)."""
    slot = slot_name(slot)
    return F.update_pack(lib, save_refs(refs, slot), out_dir=pack_dir(home, slot), sims=sims, home=home,
                         dry_run=dry_run, check_game=check_game, kind=kind(slot), prune=prune, **plan_kw)


class PackProvider:
    """The pack tool speedkit.profiles.switch talks to (park_set / status / update_pack), for the fast pack
    (slot None) or one save's pack, with SpeedKit's caches and the Sims folder baked in.

    refs: a callable returning usedpack Refs (only called when the pack must be updated). plan_kw: passed to
    fastmode.plan_pack (bc_cache, game, cache_path, game_db, game_dir, progress). last: the last update's
    result (without the plan object)."""

    def __init__(self, slot=None, refs=None, plan_kw=None, prune=True, companions_cache=None, game_dir=None):
        self.slot = slot_name(slot) if slot else None
        self.kind = kind(self.slot) if self.slot else F.FAST
        self.refs_fn = refs
        self.plan_kw = dict(plan_kw or {})
        self.prune = prune
        self.companions_cache = companions_cache
        self.game_dir = game_dir
        self.last = None

    def park_set(self, lib, roots=F.ROOTS2, verdicts=None, cache_path=None):
        kw = {'cache_path': cache_path or self.companions_cache or F.companions.DEFAULT_CACHE}
        if self.game_dir:
            kw['game_dir'] = self.game_dir
        return F.park_set(lib, roots, verdicts=verdicts, **kw)

    def status(self, out_dir):
        if self.slot is None:
            return F.status(out_dir)
        return F.status(out_dir, kind=self.kind)

    def _refs(self):
        if self.refs_fn is None:
            raise SaveError('no save references to plan the pack from')
        return self.refs_fn() if callable(self.refs_fn) else self.refs_fn

    def update_pack(self, lib=None, out_dir=None, dry_run=True, check_game=False, sims=None, home=None, progress=None):
        refs = self._refs()
        kw = dict(self.plan_kw)
        if progress is not None:
            kw['progress'] = progress
        if self.game_dir and 'game_dir' not in kw:
            kw['game_dir'] = self.game_dir
        if self.companions_cache and 'cache_path' not in kw:
            kw['cache_path'] = self.companions_cache
        parked = self.park_set(lib, verdicts=kw.pop('verdicts', None))
        if self.slot is None:
            res = F.update_pack(lib, refs, out_dir=out_dir, parked=parked, dry_run=dry_run, check_game=check_game,
                                sims=sims, home=home, prune=self.prune, **kw)
        else:
            res = F.update_pack(lib, save_refs(refs, self.slot), out_dir=out_dir, parked=parked, dry_run=dry_run,
                                check_game=check_game, sims=sims, home=home, kind=self.kind, prune=self.prune, **kw)
        plan = res.pop('plan', None)
        if plan is not None:
            res['plan_stats'] = {k: plan.stats.get(k) for k in ('keys', 'bytes', 'parts', 'cas_parts', 'bc_cache',
                                                                'seconds', 'timings')}
        self.last = res
        return res


def SavePackProvider(slot, **kw):
    """PackProvider for one save's pack (see PackProvider)."""
    return PackProvider(slot, **kw)


# ------------------------------------------------------------------------------------------ CLI
def main(argv=None):
    """python -m speedkit.savepacks list | status <slot>   (read-only)"""
    import argparse
    import sys
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(errors='backslashreplace')
    ap = argparse.ArgumentParser(description='Per-save packs ("Play this save").')
    ap.add_argument('cmd', choices=['list', 'status'])
    ap.add_argument('slot', nargs='?')
    ap.add_argument('--saves', default=SAVES)
    ap.add_argument('--home', default=HOME)
    a = ap.parse_args(argv)
    if a.cmd == 'list':
        for h in list_saves(a.saves):
            print('%-14s %-40s %-24s %-18s %4d sims %4d lots %6.1f MB  %s' % (
                h['slot'], (h['name'] or '?')[:40], (h['household'] or '-')[:24], (h['world'] or '-')[:18],
                h['sims'], h['lots'], h['size_mb'], h['last_played']))
        return 0
    st = status(a.slot, a.home, saves_dir=a.saves)
    print('%s: %s' % (slot_name(a.slot), st['state']))
    for w in st['why']:
        print('  -', w)
    return 0


if __name__ == '__main__':
    main()
