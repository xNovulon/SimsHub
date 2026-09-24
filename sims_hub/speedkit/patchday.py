r"""Patch day: notice that The Sims 4 was updated, list the script mods that are older than the update, and set
mods aside until they are updated - through the same parking store the Mods modes use.

    info = game_version(sims, game_dir)          # what the game's files say now (read-only)
    st = check(sims, home, game_dir)             # compares with the last version the Hub saw (remembers it)
    older = older_scripts(sims, st['update_time'])
    set_aside(['MCCC/mc_cmd_center.ts4script'], sims=..., home=..., check_game=True)   # journal id
    put_back(['MCCC/mc_cmd_center.ts4script'], ...)
    undo(journal_id, ...)                        # what the Hub's "Undo last change" runs for these changes

How an update is noticed (nothing is guessed from the internet; only files on this PC are read):
  * <Game>\Game\Bin\TS4_x64.exe: its size and modified time are the build's fingerprint. A patch rewrites the
    exe, so a new fingerprint means the game was updated - even before the game was started again, which is
    exactly when a warning helps. Its modified time is when the update landed (the "update time").
  * Steam installs: steamapps\appmanifest_1222670.acf gives "buildid" and "LastUpdated" (the update time).
  * <Sims 4>\GameVersion.txt: the version the game wrote when it last started ("1.119.109.1020", after a few
    bytes of header). Shown to the player; it only changes after the first start on the new version.
SpeedKit\game_version.json remembers the last fingerprint and version the Hub saw. The first look only
remembers them (no warning); a later look with another fingerprint records the change until the player
dismisses the notice (acknowledge()).

"Older than the update" means the script file's modified time is before the update time. A script mod that
was built before a patch is not necessarily broken, and one built after it is not necessarily fixed - the
Hub says so in those words. Only .ts4script files the game loads (the Mods root and one folder down) are
listed; SpeedKit's own monitor is left out. A script's companions - packages in the same folder (or, at the
Mods root, with the same name) whose XML tuning names one of the script's Python modules (m="...") - go
with it: tuning left behind without its script only makes more errors.

Setting aside (kind 'aside' journal; nothing is deleted): each file moves from Mods to the same place in
Mods_parked, Mods_parked\_manifest.json is rebuilt with profiles.rebuild_manifest (so mods_switch.py's
'full' can restore it), and SpeedKit\set_aside.json lists it. profiles.compute_target keeps every held file
parked in every mode until it is put back (or restored by another tool). Both JSON files go through the
journal (staged, old copy kept), so undo() puts the files, the list and the manifest back exactly.
Refuses while the game runs (the Journal checks before every step).
"""
import datetime
import json
import os
import re
import zipfile

from .library import SIMS, MAX_DEPTH
from .journal import Journal, JournalError, undo as journal_undo
from . import profiles as PR

STATE = 'game_version.json'
HELD = PR.HELD
STEAM_APP = 1222670
VERSION_RX = re.compile(rb'(\d{1,2}\.\d{1,4}\.\d{1,5}\.\d{3,5})')
MONITOR = PR.MONITOR.lower()
MAX_COMPANION_BYTES = 64 << 20        # tuning companions are small; bigger packages are CC, not read


class PatchError(Exception):
    """Refused, with a plain message."""


def _iso(t):
    return datetime.datetime.fromtimestamp(t).isoformat(timespec='seconds') if t else None


def _now_iso():
    return datetime.datetime.now().isoformat(timespec='seconds')


def _home(sims, home):
    return home or os.path.join(sims, 'SpeedKit')


# ------------------------------------------------------------------------------------------ the game's version
def read_version_file(path):
    """The version string in GameVersion.txt ('1.119.109.1020'), or None. The file starts with a few binary
    bytes (a length prefix), so the text is found by its shape."""
    try:
        with open(path, 'rb') as f:
            data = f.read(4096)
    except OSError:
        return None
    m = VERSION_RX.search(data)
    return m.group(1).decode('ascii') if m else None


def _steam_manifest(game_dir):
    """steamapps\\appmanifest_1222670.acf next to steamapps\\common\\<game>: {'buildid', 'updated'} or {}."""
    if not game_dir:
        return {}
    common = os.path.dirname(os.path.abspath(game_dir))
    if os.path.basename(common).lower() != 'common':
        return {}
    acf = os.path.join(os.path.dirname(common), 'appmanifest_%d.acf' % STEAM_APP)
    try:
        with open(acf, encoding='utf-8', errors='replace') as f:
            text = f.read(65536)
    except OSError:
        return {}
    out = {}
    m = re.search(r'"buildid"\s+"(\d+)"', text)
    if m:
        out['buildid'] = m.group(1)
    m = re.search(r'"LastUpdated"\s+"(\d+)"', text)
    if m:
        out['updated'] = int(m.group(1))
    return out


def game_version(sims=SIMS, game_dir=None):
    """What this PC's files say about the installed game (read-only):
    {'version': str|None (GameVersion.txt), 'version_time': unix|None, 'fingerprint': str|None (the exe),
     'build': str|None (Steam build id), 'update_time': unix|None (best guess of when the update landed)}."""
    out = {'version': None, 'version_time': None, 'fingerprint': None, 'build': None, 'update_time': None}
    vf = os.path.join(sims, 'GameVersion.txt')
    out['version'] = read_version_file(vf)
    if out['version']:
        try:
            out['version_time'] = os.path.getmtime(vf)
        except OSError:
            pass
    times = []
    if game_dir:
        exe = os.path.join(game_dir, 'Game', 'Bin', 'TS4_x64.exe')
        try:
            st = os.stat(exe)
            out['fingerprint'] = '%d-%d' % (st.st_size, int(st.st_mtime))
            times.append(st.st_mtime)
        except OSError:
            pass
        steam = _steam_manifest(game_dir)
        if steam.get('buildid'):
            out['build'] = steam['buildid']
            out['fingerprint'] = 'steam-%s' % steam['buildid'] + ('/' + out['fingerprint'] if out['fingerprint'] else '')
        if steam.get('updated'):
            times.append(steam['updated'])
    if times:
        out['update_time'] = max(times)
    return out


def _read_json(path):
    try:
        with open(path, encoding='utf-8') as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_json(path, doc):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(doc, f, indent=1)
    os.replace(path + '.tmp', path)


def check(sims=SIMS, home=None, game_dir=None, remember=True):
    """Compare the game's files with what the Hub saw last time (SpeedKit\\game_version.json).

    Returns {'version', 'previous' (the version before the update, if known), 'updated' (a change was seen and
    not acknowledged yet), 'first_look', 'update_time' (unix, when the game was last updated), 'noticed'
    (iso, when the Hub saw the change), 'fingerprint'}. remember=False only reads."""
    home = _home(sims, home)
    path = os.path.join(home, STATE)
    doc = _read_json(path)
    now = game_version(sims, game_dir)
    known = doc.get('known') if isinstance(doc.get('known'), dict) else None
    first = known is None
    changed = False
    if first:
        doc = {'known': dict(now, seen=_now_iso()), 'history': []}
        changed = bool(now['fingerprint'] or now['version'])
    elif now['fingerprint'] and known.get('fingerprint') and now['fingerprint'] != known['fingerprint']:
        doc['previous'] = known
        doc['known'] = dict(now, seen=_now_iso())
        doc['noticed'] = _now_iso()
        doc['acknowledged'] = False
        doc.setdefault('history', []).append({'from': known.get('version'), 'to': now.get('version'),
                                              'noticed': doc['noticed'], 'update_time': now.get('update_time')})
        del doc['history'][:-20]
        changed = True
    elif (not now['fingerprint'] and not known.get('fingerprint') and now['version'] and known.get('version')
          and now['version'] != known['version']):
        # no exe to look at (the game was not found): the version file is the only clue
        doc['previous'] = known
        doc['known'] = dict(now, seen=_now_iso())
        doc['noticed'] = _now_iso()
        doc['acknowledged'] = False
        doc.setdefault('history', []).append({'from': known.get('version'), 'to': now.get('version'),
                                              'noticed': doc['noticed'], 'update_time': now.get('update_time')})
        changed = True
    else:
        # the same build: keep what is new (the version file is rewritten at the first start after a patch)
        for k in ('version', 'version_time', 'update_time', 'build'):
            if now.get(k) and now[k] != known.get(k):
                known[k] = now[k]
                changed = True
        if now['fingerprint'] and not known.get('fingerprint'):
            known['fingerprint'] = now['fingerprint']
            changed = True
    if changed and remember:
        try:
            _write_json(path, doc)
        except OSError:
            pass
    known = doc['known']
    prev = doc.get('previous') or {}
    update_time = known.get('update_time') or now.get('update_time')
    if not update_time and doc.get('noticed'):
        try:
            update_time = datetime.datetime.fromisoformat(doc['noticed']).timestamp()
        except ValueError:
            update_time = None
    return {'version': known.get('version') or now.get('version'), 'previous': prev.get('version'),
            'updated': bool(doc.get('noticed')) and not doc.get('acknowledged', True), 'first_look': first,
            'update_time': update_time, 'noticed': doc.get('noticed'), 'fingerprint': known.get('fingerprint')}


def acknowledge(sims=SIMS, home=None):
    """The player has seen the patch-day notice (the Dismiss button). Returns True when something was recorded."""
    path = os.path.join(_home(sims, home), STATE)
    doc = _read_json(path)
    if not doc or doc.get('acknowledged', True):
        return False
    doc['acknowledged'] = True
    doc['acknowledged_at'] = _now_iso()
    _write_json(path, doc)
    return True


# ------------------------------------------------------------------------------------------ script mods
def _module_names(zpath):
    """Dotted module names inside a .ts4script (compiled and source files), or set() when unreadable."""
    out = set()
    try:
        with zipfile.ZipFile(zpath) as z:
            names = z.namelist()
    except (OSError, zipfile.BadZipFile, ValueError, RuntimeError):
        return out
    for n in names:
        p = n.replace('\\', '/')
        if p.startswith('lib/'):
            p = p[4:]
        stem, ext = os.path.splitext(p)
        if ext.lower() not in ('.pyc', '.pyo', '.py'):
            continue
        parts = [x for x in stem.split('/') if x]
        if parts and parts[-1] == '__init__':
            parts = parts[:-1]
        if parts:
            out.add('.'.join(parts))
    return out


_FACTS = {}


def _tuning_modules(path):
    """Top-level Python module names this package's XML tuning names (m="..."), cached; set() on any trouble."""
    try:
        st = os.stat(path)
    except OSError:
        return set()
    key = (os.path.normcase(path), st.st_size, st.st_mtime_ns)
    if key in _FACTS:
        return _FACTS[key]
    tops = set()
    if st.st_size <= MAX_COMPANION_BYTES:
        try:
            from .companions import package_facts
            facts = package_facts(path)
            for row in facts.get('xml') or []:
                m = row[4] if len(row) > 4 else None
                if m:
                    tops.add(m.split('.')[0].lower())
        except Exception:
            tops = set()
    _FACTS[key] = tops
    return tops


def _norm_stem(name):
    s = os.path.splitext(os.path.basename(name))[0].lower()
    return re.sub(r'[\s_\-]*(scripts?|tuning|package|ts4script)$', '', s)


def mod_name(rel):
    """How a player would call the mod a file belongs to: its top folder in Mods, else the file's name."""
    rel = rel.replace('\\', '/')
    if '/' in rel:
        return rel.split('/')[0]
    return os.path.splitext(rel)[0]


def scripts(mods):
    """[(rel, path, stat)] of the .ts4script files the game loads: the Mods root and one folder down."""
    out = []
    if not os.path.isdir(mods):
        return out
    for dp, dn, fn in os.walk(mods):
        rel_dir = os.path.relpath(dp, mods)
        depth = 0 if rel_dir == '.' else rel_dir.count(os.sep) + 1
        if depth >= 1:
            dn[:] = []
        for n in fn:
            if not n.lower().endswith('.ts4script'):
                continue
            full = os.path.join(dp, n)
            rel = os.path.relpath(full, mods).replace(os.sep, '/')
            if rel.lower() == MONITOR or n.lower().startswith('speedkit_monitor'):
                continue                              # SpeedKit's own monitor: rebuilt by Play
            try:
                out.append((rel, full, os.stat(full)))
            except OSError:
                continue
    return sorted(out, key=lambda x: x[0].lower())


def companions_of(mods, rel):
    """rels of the packages that go with the script `rel`: in the same folder (not the Mods root) and whose
    tuning names one of the script's modules, or - at the Mods root - with the same name."""
    rel = rel.replace('\\', '/')
    spath = os.path.join(mods, rel.replace('/', os.sep))
    tops = {m.split('.')[0].lower() for m in _module_names(spath)}
    folder = os.path.dirname(spath)
    out = []
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return out
    at_root = '/' not in rel
    for n in names:
        if not n.lower().endswith('.package'):
            continue
        full = os.path.join(folder, n)
        if not os.path.isfile(full):
            continue
        prel = (os.path.dirname(rel) + '/' + n) if not at_root else n
        if at_root:
            if _norm_stem(n) and _norm_stem(n) == _norm_stem(rel):
                out.append(prel)
            continue
        if tops and _tuning_modules(full) & tops:
            out.append(prel)
    # a package one level below the script's folder is not loaded as its companion here: keep it simple
    return out


def older_scripts(sims=SIMS, update_time=None, with_companions=True):
    """Script mods in Mods whose file is older than update_time (unix): [{'mod', 'rel', 'date', 'days_before',
    'size_mb', 'goes_with': [rels]}], oldest first; plus the number of newer ones. ({'older': [], 'newer': n})"""
    mods = os.path.join(sims, 'Mods')
    older, newer = [], 0
    for rel, full, st in scripts(mods):
        if update_time and st.st_mtime < update_time:
            item = {'mod': mod_name(rel), 'rel': rel, 'date': _iso(st.st_mtime),
                    'days_before': int((update_time - st.st_mtime) // 86400), 'size_mb': round(st.st_size / 1e6, 2),
                    'goes_with': companions_of(mods, rel) if with_companions else []}
            older.append(item)
        else:
            newer += 1
    older.sort(key=lambda x: (x['date'] or '', x['rel'].lower()))
    return {'older': older, 'newer': newer}


# ------------------------------------------------------------------------------------------ the held list
def read_held(sims=SIMS, home=None):
    """SpeedKit\\set_aside.json as {'held': [{'rel', 'since', 'why', 'game_version', 'size', 'mtime'}]}."""
    doc = _read_json(os.path.join(_home(sims, home), HELD))
    held = [h for h in doc.get('held') or [] if isinstance(h, dict) and isinstance(h.get('rel'), str)]
    doc['held'] = held
    return doc


def held_status(sims=SIMS, home=None):
    """The held mods as the Hub shows them: [{'rel', 'mod', 'since', 'why', 'date', 'state'}], state:
    'aside' (parked), 'back' (in Mods again: put back by another tool), 'updated' (a different copy is in Mods
    at that place - the old one stays parked), 'gone' (neither)."""
    mods, parked = os.path.join(sims, 'Mods'), os.path.join(sims, 'Mods_parked')
    out = []
    for h in read_held(sims, home)['held']:
        rel = h['rel']
        m = os.path.join(mods, rel.replace('/', os.sep))
        p = os.path.join(parked, rel.replace('/', os.sep))
        in_m, in_p = os.path.isfile(m), os.path.isfile(p)
        state = 'aside' if in_p and not in_m else 'updated' if in_p and in_m else 'back' if in_m else 'gone'
        try:
            mt = os.path.getmtime(p if in_p else m)
        except OSError:
            mt = h.get('mtime')
        out.append({'rel': rel, 'mod': mod_name(rel), 'since': h.get('since'), 'why': h.get('why') or 'patch',
                    'game_version': h.get('game_version'), 'date': _iso(mt) if mt else None, 'state': state,
                    'script': rel.lower().endswith('.ts4script')})
    return out


# ------------------------------------------------------------------------------------------ changes
def _clean_rel(rel):
    if not isinstance(rel, str):
        raise PatchError('That is not a mod file.')
    r = rel.replace('\\', '/').strip().strip('/')
    if not r or PR._check_entry(r) is not None or ':' in r or r.startswith('.'):
        raise PatchError("That mod file isn't in your Mods folder: %s" % rel)
    return r


def _own_file(rel):
    name = rel.split('/')[-1]
    return '/' not in rel and (PR._is_monitor_name(name) or PR._pack_family(name) is not None)


def _rebuild_manifest(j, P, doc, staging):
    inv = PR.inventory(P)
    p_files = {k: it.p_rel for k, it in inv.items.items() if it.p_rel is not None}
    p_files.update({PR._key(n): n for n in inv.all_packs('P')})
    if inv.monitor_parked:
        p_files[PR._key(inv.monitor_parked)] = inv.monitor_parked
    entries, _info = PR.rebuild_manifest(doc['moved'], p_files, inv.p_dirs, inv.m_keys(), PR._special_keys(inv))
    if entries != doc['moved']:
        new_doc = dict(doc)
        new_doc['moved'] = entries
        PR._journal_json(j, staging, P.manifest, new_doc)
    return entries


def _tidy_up(paths, roots):
    """Remove the folders above these paths that are empty now (os.rmdir cannot remove anything with content),
    up to but never including the roots. An emptied Mods_parked folder would make mods_switch.py's 'lean' skip
    that folder, and an emptied Mods folder would block a folder entry of the parking list."""
    roots_n = {os.path.normcase(os.path.abspath(r)) for r in roots}
    for p in sorted(set(paths), key=lambda x: -x.count(os.sep)):
        d = os.path.dirname(os.path.abspath(p))
        while os.path.normcase(d) not in roots_n and any(os.path.normcase(d).startswith(r + os.sep) for r in roots_n):
            try:
                os.rmdir(d)
            except OSError:
                break
            d = os.path.dirname(d)


def _staging(P, jid):
    return os.path.join(P.home, 'staging', jid)


def _drop_empty(d):
    for p in (d, os.path.dirname(d)):
        try:
            os.rmdir(p)
        except OSError:
            break


def _run(kind_note, P, check_game, body):
    """Open the journal, run body(j, staging), roll everything back on any failure (Ctrl+C included)."""
    try:
        j = Journal('aside', kind_note, home=P.home, sims=P.sims, check_game=check_game)
    except JournalError as e:
        raise PatchError(str(e) + ' Nothing was changed.')
    staging = _staging(P, j.id)
    try:
        with j:
            out = body(j, staging)
    except BaseException as e:
        moved = [s.get('dst') for s in j.steps if s.get('op') == 'move'] + \
                [s.get('src') for s in j.steps if s.get('op') == 'move']
        try:
            journal_undo(j.id, home=P.home, check_game=check_game)
            _tidy_up([m for m in moved if m], (P.mods, P.parked))
            back = 'Everything was put back as it was.'
        except Exception as e2:
            back = 'Putting things back failed too (%s); close the game if it runs, then undo the last change.' % e2
        _drop_empty(staging)
        if not isinstance(e, Exception):
            raise
        raise PatchError('%s %s' % (e if isinstance(e, (PatchError, JournalError)) else '%s: %s' % (type(e).__name__, e),
                                    back))
    _drop_empty(staging)
    return j.id, out


def set_aside(rels, sims=SIMS, home=None, check_game=True, why='patch', game_version=None, with_companions=True):
    """Move these mod files (rels relative to Mods) to the same place in Mods_parked, list them in
    SpeedKit\\set_aside.json and rebuild the parking list - one 'aside' journal. A script's companions (see
    companions_of) go with it. Returns {'journal', 'moved': [rels], 'skipped': [{'rel', 'why'}]}.
    Raises PatchError (plain message) when refused; nothing is changed then."""
    P = PR.Paths(sims, home)
    if check_game:
        from .library import game_running
        if game_running():
            raise PatchError('The Sims 4 is running. Close it first, then try again. Nothing was changed.')
    want, skipped = [], []
    seen = set()
    for rel in rels or []:
        r = _clean_rel(rel)
        group = [r] + (companions_of(P.mods, r) if with_companions and r.lower().endswith('.ts4script') else [])
        for x in group:
            k = x.lower()
            if k in seen:
                continue
            seen.add(k)
            src = os.path.join(P.mods, x.replace('/', os.sep))
            dst = os.path.join(P.parked, x.replace('/', os.sep))
            if _own_file(x):
                skipped.append({'rel': x, 'why': "This is the Hub's own file."})
            elif not os.path.isfile(src):
                skipped.append({'rel': x, 'why': "It isn't in your Mods folder any more."})
            elif not x.lower().endswith(('.ts4script', '.package')):
                skipped.append({'rel': x, 'why': 'Only mod files can be set aside.'})
            elif os.path.exists(dst):
                skipped.append({'rel': x, 'why': 'An older copy is already set aside at the same place, so this one stays.'})
            else:
                want.append(x)
    if not want:
        raise PatchError(skipped[0]['why'] if len(skipped) == 1 else 'There is nothing to set aside.')
    doc, _ = PR.load_manifest(P)                     # a damaged parking list refuses (ProfileError)
    held = read_held(sims, home)
    now = _now_iso()

    def body(j, staging):
        for x in want:
            src = os.path.join(P.mods, x.replace('/', os.sep))
            st = os.stat(src)
            j.move(src, os.path.join(P.parked, x.replace('/', os.sep)))
            keep = [h for h in held['held'] if h['rel'].lower() != x.lower()]
            keep.append({'rel': x, 'since': now, 'why': why, 'game_version': game_version, 'size': st.st_size,
                         'mtime': st.st_mtime})
            held['held'] = keep
        _rebuild_manifest(j, P, doc, staging)
        new = dict(held, version=1)
        PR._journal_json(j, staging, os.path.join(P.home, HELD), new)
        return None
    note = 'set aside %d file(s) until updated (%s): %s' % (len(want), why, ', '.join(want[:5]))
    jid, _ = _run(note, P, check_game, body)
    return {'journal': jid, 'moved': want, 'skipped': skipped}


def put_back(rels, sims=SIMS, home=None, check_game=True):
    """Bring held mods back from Mods_parked to Mods (one 'aside' journal) and drop them from the held list.
    A file that has a copy in Mods again (an update was installed there) stays parked. Returns {'journal',
    'moved', 'skipped'}; raises PatchError when refused."""
    P = PR.Paths(sims, home)
    if check_game:
        from .library import game_running
        if game_running():
            raise PatchError('The Sims 4 is running. Close it first, then try again. Nothing was changed.')
    held = read_held(sims, home)
    by_key = {h['rel'].lower(): h for h in held['held']}
    want, skipped = [], []
    for rel in rels or []:
        r = _clean_rel(rel)
        if r.lower() in {w.lower() for w in want}:
            continue
        src = os.path.join(P.parked, r.replace('/', os.sep))
        dst = os.path.join(P.mods, r.replace('/', os.sep))
        if r.lower() not in by_key:
            skipped.append({'rel': r, 'why': 'This file was not set aside by the Hub.'})
        elif not os.path.isfile(src):
            skipped.append({'rel': r, 'why': "It isn't in the set-aside folder any more."})
        elif os.path.exists(dst):
            skipped.append({'rel': r, 'why': 'A newer copy is already in your Mods folder, so the old one stays set aside.'})
        else:
            want.append(r)
    if not want:
        raise PatchError(skipped[0]['why'] if len(skipped) == 1 else 'There is nothing to put back.')
    doc, _ = PR.load_manifest(P)
    gone = {w.lower() for w in want}

    def body(j, staging):
        for x in want:
            j.move(os.path.join(P.parked, x.replace('/', os.sep)), os.path.join(P.mods, x.replace('/', os.sep)))
        # the Mods_parked folders this emptied go (mods_switch.py's 'lean' would skip a folder name that is there)
        _tidy_up([os.path.join(P.parked, x.replace('/', os.sep)) for x in want], (P.parked,))
        _rebuild_manifest(j, P, doc, staging)
        new = dict(held, version=1)
        new['held'] = [h for h in held['held'] if h['rel'].lower() not in gone]
        PR._journal_json(j, staging, os.path.join(P.home, HELD), new)
    note = 'put back %d file(s): %s' % (len(want), ', '.join(want[:5]))
    jid, _ = _run(note, P, check_game, body)
    return {'journal': jid, 'moved': want, 'skipped': skipped}


def undo(journal_id, sims=SIMS, home=None, check_game=True, dry_run=False):
    """Undo one 'aside' journal (set aside or put back): the files, the held list and the parking list go back
    exactly (journal.undo), then the folders it had filled and that are empty again are removed. dry_run: only
    check it could be undone now (raises JournalError otherwise)."""
    home = _home(sims, home)
    path = os.path.join(home, 'journal', journal_id + '.json')
    with open(path, encoding='utf-8') as f:
        j = json.load(f)
    if j.get('kind') != 'aside':
        raise JournalError('this change was not made by setting mods aside')
    actions = journal_undo(journal_id, home=home, check_game=check_game, dry_run=dry_run)
    if not dry_run:
        moved = [s.get('dst') for s in j.get('steps') or [] if s.get('op') == 'move'] + \
                [s.get('src') for s in j.get('steps') or [] if s.get('op') == 'move']
        _tidy_up([m for m in moved if m], (os.path.join(sims, 'Mods'), os.path.join(sims, 'Mods_parked')))
    return actions
