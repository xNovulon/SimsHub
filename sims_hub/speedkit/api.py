r"""The engine behind Novulon's Sims Hub: every button of the app is one function here (docs\hub_contract.md).

Rules for every public function:
  * safe to call from a background thread (each call opens its own library connection);
  * never raises for expected failures: it returns {'ok': False, 'message': '<plain explanation>'};
  * reports progress through an optional callback progress(step: str, fraction: float | None, message: str);
  * every user-facing string is short, plain English - the user is not technical.

Tests (and anyone who wants another Sims 4 folder) point it elsewhere with configure(sims=..., db_path=...,
...); reset() restores the defaults. Nothing here writes outside the Sims 4 folder's SpeedKit folder, Mods
and Mods_parked (through the components' journals), the project's data\ caches and, for the free-disk-space
clean-up only, a quarantine folder on another drive.

The one-click flow (play / prepare): refuse while the game runs -> tidy SpeedKit's own leftovers -> scan the
mod library -> install/refresh SpeedKit Monitor -> graphics 'SpeedKit Max Quality' when SGR Full is active
-> build/update the pack the mode needs (fast pack, or the chosen save's pack) and switch the Mods folder
-> memory check (warnings become steps) -> start the game (play only; writes launch_time.json).
"""
import collections
import csv
import datetime
import functools
import json
import os
import re
import shutil
import string
import subprocess
import sys
import threading
import time
import traceback

from . import library as L
from . import journal as J
from . import usedpack as U
from . import fastmode as F
from . import savepacks as S
from . import profiles as PR
from . import settings as ST
from . import gamepath as G
from . import companions, game_index, hashing, ingame_install
from . import launch as LA

PROJECT = L.PROJECT
ANIMATOR_DIR = os.path.join(os.path.expanduser('~'), 'Tools', 'sims4_animator')
ANIMATOR_EXE = os.path.join(ANIMATOR_DIR, 'Wicked Animator.exe')          # the desktop app (single instance)
ANIMATOR_BAT = os.path.join(ANIMATOR_DIR, 'Start Wicked Animator.bat')    # fallback when the exe is missing

DEFAULTS = {
    'sims': L.SIMS,                      # the Sims 4 user folder (Mods, Mods_parked, saves, Tray, SpeedKit)
    'home': None,                        # SpeedKit's folder: <sims>\SpeedKit
    'db_path': L.DEFAULT_DB,             # the mod library index
    'refs_db': U.DEFAULT_REFS_DB,        # what saves/Tray reference (cache)
    'game_ids_db': U.DEFAULT_GAME_DB,    # EA's own ids (cache)
    'game_db': game_index.DEFAULT_DB,    # the game index (EA overrides)
    'companions_cache': companions.DEFAULT_CACHE,
    'hash_cache': hashing.DEFAULT_CACHE,
    'bc_cache': os.path.join(PROJECT, 'data', 'plan_bc.json.gz'),   # parts b/c of the packs (save-independent)
    'game': None,                        # {'exe', 'game_dir', 'store', 'source'} to use instead of finding it
    'game_clues': None,                  # gamepath.Clues (tests)
    'remember_game': True,               # remember a game found through the running process
    'check_game': True,                  # refuse while TS4_x64.exe runs (tests turn it off)
    'scan_workers': 1,                   # save scanning processes (1: safe inside any host process)
    'verdicts': None,                    # callable(lib) -> companion verdicts (tests); None = companions.classify
    'dist': ingame_install.DIST,         # the built SpeedKit Monitor
    'build_monitor': True,               # rebuild the monitor when its sources are newer than the build
    'animator': None,                    # Novulon's Wicked Animator to start; None: the exe, else the .bat
    'opener': None,                      # callable(path or url) that opens a folder/file (tests); None = os.startfile
    'cleanup_home': None,                # journal home of the duplicate clean-up (None: automatic)
    'max_package_bytes': 1_900_000_000,
    'prune': True,                       # keep only the newest previous pack copy in the quarantine
    'processes': True,                   # preflight looks at other programs' memory
}
_cfg = dict(DEFAULTS)
_lock = threading.RLock()
_cache = {}


def configure(**kw):
    """Point the engine at another Sims 4 folder / caches (tests), e.g. configure(sims=r'E:\\fake\\The Sims 4',
    db_path=..., check_game=False). Unknown keys raise KeyError. Returns the configuration now in effect."""
    with _lock:
        for k, v in kw.items():
            if k not in DEFAULTS:
                raise KeyError('unknown setting %r' % k)
            _cfg[k] = v
        _cache.clear()
        G._CACHE.clear()
        return dict(_cfg)


def reset():
    """Back to the defaults (the real Sims 4 folder)."""
    with _lock:
        _cfg.clear()
        _cfg.update(DEFAULTS)
        _cache.clear()
        G._CACHE.clear()


def cfg(key):
    return _cfg[key]


# ------------------------------------------------------------------------------------------ small helpers
def _sims():
    return _cfg['sims']


def _home():
    return _cfg['home'] or os.path.join(_sims(), 'SpeedKit')


def _mods():
    return os.path.join(_sims(), 'Mods')


def _parked():
    return os.path.join(_sims(), 'Mods_parked')


def _saves():
    return os.path.join(_sims(), 'saves')


def _tray():
    return os.path.join(_sims(), 'Tray')


def _reports():
    return os.path.join(_home(), 'reports')


def _fastpack():
    return os.path.join(_home(), 'fastpack')


def _roots():
    return {'Mods': _mods(), 'Mods_parked': _parked()}


def _gb(n):
    return round((n or 0) / 1e9, 2)


def _now_iso():
    return datetime.datetime.now().isoformat(timespec='seconds')


class _Progress:
    """Calls progress(step, fraction, message) and never lets its errors through."""

    def __init__(self, fn):
        self.fn = fn

    def __call__(self, step, fraction=None, message=''):
        if self.fn:
            try:
                self.fn(step, fraction, message)
            except Exception:
                pass


# words the user should never have to read, and what to say instead (file names such as 'x.package' are kept)
_WORDS = [(re.compile(r'(?<![\w.])Mods_parked(?!\w)'), 'the set-aside folder'),
          (re.compile(r'(?<![\w.])packages(?!\w)', re.I), 'mod files'),
          (re.compile(r'(?<![\w.])package\(s\)(?!\w)', re.I), 'mod file(s)'),
          (re.compile(r'(?<![\w.])package(?!\w)', re.I), 'mod file'),
          (re.compile(r'(?<![\w.])quarantined(?!\w)', re.I), 'set aside'),
          (re.compile(r'(?<![\w.])quarantine(?!\w)', re.I), 'safe-keeping folder'),
          (re.compile(r'(?<![\w.])journals?(?!\w)', re.I), 'change record'),
          (re.compile(r'(?<![\w.])profiles(?!\w)', re.I), 'modes'),
          (re.compile(r'(?<![\w.])profile(?!\w)', re.I), 'mode'),
          (re.compile(r'(?<![\w.])CASPs?(?!\w)'), 'CAS part')]


def _plainify(text):
    """The same message without SpeedKit's inside words (package, quarantine, journal, profile, CASP)."""
    if not isinstance(text, str):
        return text
    for rx, word in _WORDS:
        text = rx.sub(word, text)
    return text


def _plain(e):
    """A plain sentence for an exception (the components' own messages are already written for the user)."""
    msg = str(e).strip() or type(e).__name__
    if isinstance(e, (PermissionError,)) or 'WinError 32' in msg:
        return 'A file is in use by another program (%s). Close it and try again.' % _plainify(msg)
    if isinstance(e, MemoryError):
        return 'The PC ran out of memory. Close some programs and try again.'
    if isinstance(e, OSError) and getattr(e, 'errno', None) == 28:
        return 'The disk is full. Free some space and try again.'
    msg = _plainify(msg)
    return msg[0].upper() + msg[1:] if msg else msg


def _safe(fn):
    """Decorator: unexpected exceptions become {'ok': False, 'message': ...} (logged to reports\\hub_errors.log).
    functools.wraps keeps the function's own signature visible (the app looks for a progress parameter)."""
    @functools.wraps(fn)
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except Exception as e:
            _log_error(fn.__name__, e)
            out = {'ok': False, 'message': 'Something went wrong: %s' % _plain(e)}
            return out
    return wrapper


def _log_error(where, e):
    try:
        os.makedirs(_reports(), exist_ok=True)
        with open(os.path.join(_reports(), 'hub_errors.log'), 'a', encoding='utf-8', errors='replace') as f:
            f.write('%s  %s: %s\n%s\n' % (_now_iso(), where, e, traceback.format_exc()))
    except Exception:
        pass


def _game_running():
    return L.game_running() if _cfg['check_game'] else False


def _library(scan=False):
    """A Library on this Sims folder (the caller closes it)."""
    lib = L.Library(db_path=_cfg['db_path'], roots=_roots())
    if scan:
        lib.scan()
    return lib


def _verdicts_fn():
    return _cfg['verdicts']


def _open(path):
    op = _cfg['opener']
    if op is not None:
        op(path)
    elif hasattr(os, 'startfile'):
        os.startfile(path)
    else:
        subprocess.Popen(['xdg-open', path])


def _cached(key, seconds, fn):
    now = time.time()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < seconds:
            return hit[1]
    value = fn()
    with _lock:
        _cache[key] = (now, value)
    return value


# ------------------------------------------------------------------------------------------ the game
def _locate():
    if _cfg['game']:
        g = dict(_cfg['game'])
        return dict(g, found=True, saved=False, message='The Sims 4 is at %s.' % g.get('game_dir'))
    return G.locate_game(_sims(), _home(), _cfg['game_clues'], _cfg['remember_game'])


def _game():
    g = _locate()
    return {k: g[k] for k in ('exe', 'game_dir', 'store', 'source')} if g.get('found') else None


def _game_bin(game):
    return os.path.join(game['game_dir'], 'Game', 'Bin') if game else ST.GAME_BIN


def _game_ids(game):
    return U.load_game_ids(game['game_dir'], _cfg['game_ids_db'])


# ------------------------------------------------------------------------------------------ status
PROFILE_LABELS = {'full': 'Full Start - all CC is loaded', 'fast': 'Quick Start - only the CC your sims use',
                  'studio': 'Studio - the animation work set', 'custom': 'Custom - changed by hand or another tool'}


def _profile_status():
    cur = PR.current(sims=_sims(), home=_home())
    state = PR.read_state(_sims(), _home()) or {}
    name = cur['profile']
    slot = cur.get('save_slot')
    label = PROFILE_LABELS.get(name, name)
    if name == 'save':
        save_name = None
        try:
            save_name = S.read_header(os.path.join(_saves(), slot + '.save')).get('name')
        except Exception:
            save_name = state.get('save_name')
        label = "Play this save - only the CC of '%s'" % (save_name or slot)
    return {'name': name, 'save_slot': slot, 'label': label}


def _graphics_signature(game):
    sig = []
    co = os.path.join(_sims(), 'ConfigOverride')
    for p in [os.path.join(co, n) for n in (sorted(os.listdir(co)) if os.path.isdir(co) else [])] + [
            os.path.join(_sims(), 'Options.ini'), os.path.join(_sims(), 'Config.log'),
            os.path.join(_game_bin(game), 'GraphicsRules.sgr'), os.path.join(_home(), 'journal')]:
        try:
            st = os.stat(p)
            sig.append((p, st.st_size, st.st_mtime))
        except OSError:
            sig.append((p, None))
    return tuple(sig)


# settings.graphics_status notes -> what the Performance page says (None: not shown - it only matters to a
# developer). Checked in order; the first pattern that matches wins.
_DETAILS = [
    (r'graphics_use_tuned would install', 'SpeedKit Max Quality can be switched on: the same sharp look, without the lag.'),
    (r'^SGR Full turns off Sim LOD', 'SGR Full draws sims and small objects in full detail however far away they are - '
                                     'that is what makes the game lag.'),
    (r'is active: SGR Full', "SGR Full's look, with only the settings that caused the lag tuned."),
    (r'file was edited: .* above SpeedKit', "Your graphics file was changed since, and some settings that cause lag are "
                                            "high again. 'Fix the lag' puts them right."),
    (r'lines of the .* file could not be tuned', 'A few settings could not be tuned and keep their old values.'),
    (r'Config\.log confirms the game loaded', 'The game used these settings the last time it started.'),
    (r'^The rules changed after the last game start', 'The new settings take effect the next time the game starts.'),
    (r'was installed \(journal .*has been replaced since', 'Your graphics file was replaced after SpeedKit Max Quality '
                                                           'was switched on.'),
    (r'^SpeedKit Max Quality: .*(not SGR Full|leaves your own)', 'SpeedKit leaves your own graphics file as it is.'),
    (r'^SpeedKit Max Quality: ', None),
    (r'^The rules include .*which is missing', 'A file your graphics settings need is missing, so some of them do '
                                               'not work.'),
    (r'rules lines could not be read', 'Some lines of your graphics file could not be read.'),
    (r'These Setters still keep Sims at full detail out to ([\d.,]+) m', r'These settings keep sims in full detail up '
                                                                         r'to \1 m away.'),
    (r'is in ConfigOverride but is not loaded', None),
    (r'options of the stock rules are not defined', None),
    (r'^Config\.log starts with', None),
]


def _plain_detail(note):
    """One settings.graphics_status note in the user's words, or None when it only matters to a developer."""
    for rx, plain in _DETAILS:
        m = re.search(rx, note)
        if m:
            return m.expand(plain) if plain else None
    if re.search(r'(?i)\b(graphics_\w+|use_stock|use_preset|ConfigOverride|LOD|stock|override|\w+\.sgr|Config\.log|'
                 r'journal|FSAA|culling|clip)\b', note):
        return None
    return _plainify(note)


def _plain_value(v):
    """A graphics value as the table shows it: '120.0f' -> '120', '1.3f' -> '1.3'."""
    if v is None:
        return None
    s = ST.settings_sgr.fmt(v)
    s = re.sub(r'(?<=\d)[fF]\b', '', s)
    return re.sub(r'\b(\d+)\.0\b', r'\1', s)


def _graphics_status(game):
    if game is None:
        return {'state': 'other', 'label': "Unknown - the game was not found", 'can_tune': False,
                'details': ["Click 'Locate The Sims 4' first."]}
    key = ('graphics', _graphics_signature(game))
    if not os.path.isfile(os.path.join(_game_bin(game), 'GraphicsRules.sgr')):
        return {'state': 'other', 'label': "Unknown - the game's own graphics file was not found", 'can_tune': False,
                'details': ['%s is missing.' % os.path.join(_game_bin(game), 'GraphicsRules.sgr')]}

    def compute():
        g = ST.graphics_status(_sims(), _game_bin(game), _home())
        state = {'speedkit_tuned': 'tuned', 'simp_sgr_full': 'sgr_full', 'stock': 'stock'}.get(g['active'], 'other')
        label = {'tuned': 'SpeedKit Max Quality - sharp graphics without the lag',
                 'sgr_full': "Simp4Sims 'SGR Full' - looks great but causes lag",
                 'stock': "The game's own graphics settings"}.get(state, g['label'])
        return {'state': state, 'label': label, 'can_tune': (g.get('tune') or {}).get('action') in ('add', 'replace'),
                'details': [d for d in (_plain_detail(n) for n in g.get('notes') or []) if d]}
    return _cached(key, 300, compute)


def _memory_status():
    def compute():
        rep = ST.preflight(_sims(), processes=_cfg['processes'], game_bin=_game_bin(_game()))
        m = rep['memory']
        top = [{'name': a['name'], 'gb': round(a['private_mb'] / 1024, 1)} for a in rep.get('apps', [])
               if not a.get('system')][:8]
        return {'free_gb': round(m['ram_available_mb'] / 1024, 1), 'total_gb': round(m['ram_total_mb'] / 1024, 1),
                'warnings': [w for w in rep['warnings'] if 'already running' not in w], 'top': top,
                '_report': rep}
    return _cached('memory', 30, compute)


def _library_status():
    try:
        mtime = os.path.getmtime(_cfg['db_path'])
    except OSError:
        return {'packages': 0, 'gb': 0.0, 'cas_full': 0, 'cas_fast': None}

    def compute():
        lib = _library()
        try:
            n = b = 0
            own = set()
            for p in lib.packages():
                if F.is_speedkit_pack(p.rel):
                    own.add(p.id)
                else:
                    n += 1
                    b += p.size
            cas = sum(c for pid, c in lib.db.execute('select pkg, count(*) from res where t=? and comp != ? group by pkg',
                                                     (U.T_CASP, 0xFFE0)) if pid not in own)
        finally:
            lib.close()
        fast = None
        try:
            man = F.read_manifest(_fastpack())
            fast = (man or {}).get('cas_parts', {}).get('fast')
        except ValueError:
            pass
        return {'packages': n, 'gb': _gb(b), 'cas_full': cas, 'cas_fast': fast}
    return _cached(('library', mtime), 600, compute)


def _pack_why(st):
    """fastmode.status's reasons in the user's words."""
    if st['state'] == 'missing':
        return 'Not made yet - it is made the first time you play in this mode.'
    if st['state'] == 'fresh':
        return 'Up to date.'
    bits = []
    raw = ' '.join(st.get('why') or [])
    if st.get('saves_changed'):
        bits.append('your saves changed since it was made')
    if 'mod library changed' in raw:
        bits.append('your mods changed since it was made')
    if 'rules' in raw:
        bits.append('SpeedKit was updated')
    if any(w in raw for w in ('missing', 'changed:', 'both', 'split', 'does not list', 'damaged', 'version')):
        bits.append('some of its files are missing or out of place')
    return ('Needs a quick update: %s.' % '; '.join(bits)) if bits else 'Needs a quick update.'


def _fastpack_status():
    st = F.status(_fastpack(), _roots(), _saves(), _tray())
    why = _pack_why(st)
    return {'state': st['state'], 'why': why, 'gb': _gb(st.get('bytes')) if st.get('bytes') else None}


def _inbox_path():
    from . import merge
    return merge.inbox_path(sims=_sims())


def _inbox_status():
    """{'path', 'waiting'}: the downloads waiting in the Inbox (items at its top level; nothing is opened)."""
    from . import merge
    path = _inbox_path()
    n = 0
    if os.path.isdir(path):
        for name in os.listdir(path):
            low = name.lower()
            if low in merge.INBOX_RESERVED or low in merge.INBOX_IGNORED or low.endswith(merge.PARTIAL_SUFFIXES):
                continue
            n += 1
    return {'path': path, 'waiting': n}


def _report_status():
    p = os.path.join(_reports(), 'library_report.html')
    try:
        return {'path': p, 'when': datetime.datetime.fromtimestamp(os.path.getmtime(p)).isoformat(timespec='seconds')}
    except OSError:
        return {'path': None, 'when': None}


_PKG_CASP = {}


def _pack_file_casp(path):
    """CAS parts in one package file read from its own index (for files the library index does not know yet,
    e.g. a pack just put into Mods). Cached by path, size and mtime."""
    from .dbpf import read_entries, open_shared, DELETED
    st = os.stat(path)
    key = (os.path.normcase(path), st.st_size, st.st_mtime_ns)
    if key not in _PKG_CASP:
        with open_shared(path) as f:
            _PKG_CASP[key] = sum(1 for e in read_entries(f) if e.t == U.T_CASP and e.comp != DELETED)
    return _PKG_CASP[key]


def _cas_now():
    """CAS parts the game loads in the mode the Mods folder is in now (any mode, also 'custom'): every .package
    in Mods up to 5 folders deep, counted from the library index (by relative path, size and mtime) or, for a
    file the index does not know (a SpeedKit pack just put there), from the file's own index."""
    mods = _mods()
    if not os.path.isdir(mods):
        return 0
    files = []
    for dp, dn, fn in os.walk(mods):
        rel_dir = os.path.relpath(dp, mods)
        depth = 0 if rel_dir == '.' else rel_dir.count(os.sep) + 1
        if depth >= L.MAX_DEPTH:
            dn[:] = []
        for n in fn:
            if n.lower().endswith('.package'):
                full = os.path.join(dp, n)
                try:
                    st = os.stat(full)
                except OSError:
                    continue
                files.append((os.path.relpath(full, mods).replace(os.sep, '/').upper(), st.st_size, full))
    known = {}
    if os.path.exists(_cfg['db_path']):
        lib = _library()
        try:
            for rel, size, n in lib.db.execute('select p.rel, p.size, count(r.pkg) from pkg p left join res r on '
                                               'r.pkg = p.id and r.t = ? and r.comp != ? group by p.id',
                                               (U.T_CASP, 0xFFE0)):
                known[(rel.upper(), size)] = n
        finally:
            lib.close()
    total = 0
    for rel, size, full in files:
        n = known.get((rel, size))
        if n is None:
            try:
                n = _pack_file_casp(full)
            except Exception:
                n = 0
        total += n
    return total


def _load_times(limit=20):
    path = os.path.join(_reports(), 'loadtimes.csv')
    out = []
    try:
        with open(path, encoding='utf-8', errors='replace', newline='') as f:
            rows = list(csv.DictReader(f))
    except OSError:
        return out

    def num(v):
        try:
            return float(v) if v not in (None, '') else None
        except ValueError:
            return None
    for r in reversed(rows):
        t = r.get('time') or ''
        try:
            t = datetime.datetime.strptime(t, '%Y-%m-%d %H:%M:%S').isoformat()
        except ValueError:
            pass
        out.append({'time': t, 'event': r.get('event'), 'profile': r.get('profile') or '',
                    'launch_to_menu_s': num(r.get('launch_to_menu_s')), 'lot_load_s': num(r.get('lot_load_s'))})
        if len(out) >= limit:
            break
    return out


def _journal_homes():
    return [_home()] + _cleanup_homes_known()


def _when(jid):
    try:
        return datetime.datetime.strptime(jid[:15], '%Y%m%d-%H%M%S').isoformat()
    except ValueError:
        return None


def _journals(limit=15):
    out = []
    for h in _journal_homes():
        for jid, kind, state, n, note in J.list_journals(h):
            try:
                mtime = os.path.getmtime(os.path.join(h, 'journal', jid + '.json'))
            except OSError:
                mtime = 0.0
            j = {'id': jid, 'kind': kind, 'state': state, 'when': _when(jid), 'note': note, '_home': h,
                 '_order': (jid[:15], mtime)}
            j['title'] = _title(j)
            j['undoable'] = _undoable(j)
            out.append(j)
    # ids have one-second resolution: journals of the same second are ordered by when they were last written
    out.sort(key=lambda j: j['_order'], reverse=True)
    # the next one to undo: the newest whose undo would go through now (a dry run against the disk); a change
    # whose files were changed since (the other chat's mods_switch.py, the user, a later switch) is skipped
    # instead of blocking every older change for good. Behind such a change only graphics / cache changes may
    # come next: they never touch Mods, so undoing them cannot clash with files the skipped change moved
    first, blocked = None, None
    for j in out:
        if not j['undoable']:
            continue
        if blocked is not None and j['kind'] not in INDEPENDENT_KINDS:
            j['undoable'] = False
            j['_why'] = 'the newer change "%s" cannot be undone any more' % blocked['title']
            continue
        why = _undo_refusal(j)
        if why is None:
            first = j
            break
        j['undoable'] = False
        j['_why'] = why
        blocked = blocked or j
    for j in out:
        j['cannot_undo'] = bool(j.get('_why'))
    for j in out:
        j['next_undo'] = j is first
    return out[:limit] if limit else out


_MODE_WORDS = {'full': 'Full Start', 'fast': 'Quick Start', 'studio': 'Studio', 'save': 'Play this save'}


def _title(j):
    """A plain sentence for one recorded change (status()['journals'][n]['title'])."""
    kind, note = j['kind'], (j['note'] or '')
    low = note.lower()
    if kind in ('aside', 'saves'):                  # patch day / save backups (api_care.py)
        from . import api_care
        return api_care.title(j)
    if kind == 'profile':
        if low.startswith('thumbnail cache'):
            return 'Set the thumbnail cache aside (the game rebuilds it)'
        if low.startswith('bring the fast pack home'):
            return 'Moved the packs back to their folder for an update'
        m = re.match(r'switch to (\w+)', low)
        return 'Switched to %s' % _MODE_WORDS.get(m.group(1), m.group(1)) if m else 'Changed the Mods folder'
    if kind == 'fastpack':
        return 'Updated the fast pack' if (' delta' in low or ' refresh' in low) else 'Made the fast pack'
    if kind == 'savepack':
        m = re.search(r'(slot_[0-9a-f]{8})', low)
        what = 'the pack for save %s' % ('Slot_' + m.group(1)[5:] if m else '')
        return ('Updated %s' if (' delta' in low or ' refresh' in low) else 'Made %s') % what.strip()
    if kind == 'install':
        return 'Removed SpeedKit Monitor' if low.startswith('uninstall') else 'Installed SpeedKit Monitor'
    if kind == 'settings':
        if 'max quality' in low:
            return 'Graphics set to Max Quality'
        if 'options' in low:
            return 'Changed the game options'
        return 'Changed the graphics settings'
    return {'caches': 'Cleared the game caches', 'merge': 'Combined mod files', 'inbox': 'Installed new downloads',
            'dedup': 'Removed duplicate copies', 'usedpack': 'Made the used-CC pack',
            'setaside': 'Set CC files aside'}.get(kind, 'Changed %s' % kind)


def _disk():
    out = {}
    try:
        out['c_free_gb'] = round(shutil.disk_usage('C:\\' if os.name == 'nt' else '/').free / 2 ** 30, 1)
    except OSError:
        out['c_free_gb'] = None
    try:
        out['sims_drive_free_gb'] = round(shutil.disk_usage(_sims()).free / 2 ** 30, 1)
    except OSError:
        out['sims_drive_free_gb'] = None
    return out


@_safe
def status():
    """Everything the home screen shows (see docs\\hub_contract.md). Each part is worked out on its own, so one
    failing part only empties that part (and adds a line to 'problems')."""
    problems = []
    loc = _locate()
    game = {k: loc[k] for k in ('exe', 'game_dir', 'store', 'source')} if loc.get('found') else None

    def part(name, fn, fallback):
        try:
            return fn()
        except Exception as e:
            _log_error('status.' + name, e)
            problems.append('%s: %s' % (name, _plain(e)))
            return fallback
    out = {'ok': True}
    out['game_running'] = part('game_running', _game_running, False)
    out['profile'] = part('profile', _profile_status, {'name': 'custom', 'save_slot': None, 'label': 'Unknown'})
    out['graphics'] = part('graphics', lambda: _graphics_status(game),
                           {'state': 'other', 'label': 'Unknown', 'can_tune': False, 'details': []})
    mem = part('memory', _memory_status, {'free_gb': None, 'total_gb': None, 'warnings': [], 'top': []})
    out['memory'] = {k: v for k, v in mem.items() if not k.startswith('_')}
    out['library'] = part('library', _library_status, {'packages': 0, 'gb': 0.0, 'cas_full': 0, 'cas_fast': None})
    out['fastpack'] = part('fastpack', _fastpack_status, {'state': 'missing', 'why': '', 'gb': None})
    found = part('monitor', lambda: ingame_install.find_installed(_sims()), [])
    out['monitor'] = {'installed': bool(found), 'where': found[0] if found else None}
    out['library']['cas_now'] = part('cas_now', _cas_now, None)
    out['inbox'] = part('inbox', _inbox_status, {'path': _inbox_path(), 'waiting': 0})
    out['report'] = part('report', _report_status, {'path': None, 'when': None})
    out['load_times'] = part('load_times', _load_times, [])
    out['journals'] = [{k: v for k, v in j.items() if not k.startswith('_')}
                       for j in part('journals', _journals, [])]
    anim = _animator_path()
    out['animator'] = {'installed': anim is not None, 'path': anim}
    out['disk'] = part('disk', _disk, {'c_free_gb': None})
    out['game'] = {'found': bool(loc.get('found')), 'exe': loc.get('exe') if loc.get('found') else None,
                   'source': loc.get('source') or '', 'saved': bool(loc.get('saved')), 'message': loc.get('message'),
                   'store': loc.get('store'), 'game_dir': loc.get('game_dir') if loc.get('found') else None,
                   'lost_path': loc.get('lost_path')}
    if problems:
        out['problems'] = problems
    return out


# ------------------------------------------------------------------------------------------ saves
def _scan_all_refs(tell):
    if _run_lock.locked():
        # a Play/Prepare is running and may be reading the saves itself: use what is known, parse nothing
        return U.load_refs(_saves(), _tray(), _cfg['refs_db'])
    tell('saves', None, 'Reading your saves (the first time takes a few minutes)')
    refs = U.scan_references(_saves(), _tray(), _cfg['refs_db'], workers=_cfg['scan_workers'])
    return refs


@_safe
def list_saves(progress=None):
    """Every current save slot with its own name, played household, world, sims, lots, the CC CAS parts it
    uses, how many CAS parts the game would load when playing only that save, and its pack's state."""
    tell = _Progress(progress)
    tell('saves', 0.0, 'Looking at your saves')
    headers = S.list_saves(_saves())
    out = []
    usage, extra = {}, {}
    game = _game()
    lib = None
    try:
        if headers:
            refs = _scan_all_refs(tell)
            errors = refs.stats.get('errors') or {}
            if game is not None:
                tell('saves', 0.6, 'Matching the CC your saves use with your mods')
                lib = _library()
                if not lib.packages():
                    lib.scan()
                ids = _game_ids(game)
                v = _verdicts_fn()
                parked = F.park_set(lib, verdicts=v(lib) if v else None, cache_path=_cfg['companions_cache'],
                                    game_dir=game['game_dir'])
                usage = S.save_usage(lib, refs, ids, parked)
                bc = F.cached_bc(lib, parked, ids, _cfg['bc_cache'])
                extra['kept_casp'] = parked.stats.get('kept_casp')
                extra['bc_casp'] = ({k for k in bc['items'] if k[0] == U.T_CASP} if bc else None)
            extra['errors'] = errors
        tell('saves', 0.9, 'Checking which saves are prepared')
        for h in headers:
            slot = h['slot']
            u = usage.get(S.slot_name(slot))
            pst = S.status(slot, _home(), _roots(), _saves())
            man_cas = None
            if pst['state'] == 'fresh':
                try:
                    man_cas = (F.read_manifest(S.pack_dir(_home(), slot), S.kind(slot)) or {}).get(
                        'cas_parts', {}).get('fast')
                except ValueError:
                    man_cas = None
            cas_loaded = man_cas
            if cas_loaded is None and u is not None and extra.get('bc_casp') is not None \
                    and extra.get('kept_casp') is not None:
                cas_loaded = extra['kept_casp'] + len(u['pack_casp'] | extra['bc_casp'])
            item = {'slot': slot, 'name': h.get('name') or slot, 'household': h.get('household'),
                    'world': h.get('world'), 'last_played': h.get('last_played'), 'size_mb': h.get('size_mb'),
                    'sims': h.get('sims', 0), 'lots': h.get('lots', 0),
                    'cc_parts': u['cc_parts'] if u else None, 'cc_missing': u['cc_missing'] if u else None,
                    'cas_loaded': cas_loaded,
                    'pack': {'state': pst['state'], 'gb': pst.get('gb')}}
            if h.get('error'):
                item['problem'] = 'This save cannot be read: %s' % h['error']
            elif slot + '.save' in (extra.get('errors') or {}):
                item['problem'] = 'This save could not be read just now (the game may be saving it).'
            out.append(item)
    finally:
        if lib is not None:
            lib.close()
    tell('saves', 1.0, '%d saves' % len(out))
    return {'ok': True, 'saves': out}


# ------------------------------------------------------------------------------------------ play / prepare
TARGETS = ('fast', 'full', 'studio')


def _parse_target(target):
    t = (target or '').strip()
    if t.lower() in TARGETS:
        return t.lower(), None
    if t.lower().startswith('save:'):
        return 'save', S.slot_name(t)
    raise S.SaveError("Choose what to play: fast, full, studio, or a save ('save:Slot_00000014').")


class _Run:
    """One play/prepare run: its steps and progress."""

    def __init__(self, progress):
        self.tell = _Progress(progress)
        self.steps = []

    def step(self, name, ok, message, warn=False):
        """warn: the step is fine but needs the user's attention (memory warnings, a file left as it is...)."""
        message = _plainify(message)
        self.steps.append({'step': name, 'ok': bool(ok), 'message': message, 'warn': bool(warn or not ok)})
        self.tell(name, None, message)
        return ok

    def result(self, ok, message, launched=False):
        return {'ok': bool(ok), 'message': _plainify(message), 'launched': bool(launched), 'steps': self.steps}


def _housekeeping(run):
    """Leftovers of a crashed pack build and old pack copies in the quarantine (SpeedKit's own files)."""
    home = _home()
    left = F.cleanup_staging(home)
    pr = F.prune_quarantine(home) if _cfg['prune'] else {'pruned': [], 'bytes': 0}
    freed = sum(x['bytes'] for x in left) + pr['bytes']
    if left or pr['pruned']:
        run.step('housekeeping', True, 'Tidied up old SpeedKit pack copies (%.1f GB freed).' % (freed / 1e9))


def _monitor_sources_newer(dist):
    src = os.path.join(PROJECT, 'ingame', 'speedkit_monitor')
    try:
        newest = max(os.path.getmtime(os.path.join(src, n)) for n in os.listdir(src) if n.endswith('.py'))
        return newest > os.path.getmtime(dist)
    except (OSError, ValueError):
        return False


def _monitor_parked():
    """SpeedKit Monitor sits in the set-aside folder (the other chat's mods_switch.py 'lean' parks it) and not in
    Mods: the Mods folder switch brings that copy back, so nothing is installed before it (a second copy made
    now would sit beside the parked one, and undoing the switch would leave the monitor in both places)."""
    return (os.path.isfile(os.path.join(_parked(), ingame_install.NAME))
            and not ingame_install.find_installed(_sims()))


def _ensure_monitor(run, after_switch=False):
    """Install / update SpeedKit Monitor. Returns 'parked' (nothing done) when the Mods switch that follows
    brings the parked copy back; the flow then calls this again with after_switch=True."""
    if not after_switch and _monitor_parked():
        run.tell('monitor', None, 'SpeedKit Monitor was set aside by another tool; it comes back with your mods')
        return 'parked'
    dist = _cfg['dist']
    if _cfg['build_monitor'] and (not os.path.isfile(dist) or _monitor_sources_newer(dist)):
        try:
            if PROJECT not in sys.path:
                sys.path.insert(0, PROJECT)
            from tools import build_ingame
            build_ingame.build(dist=dist)
        except Exception as e:
            _log_error('build monitor', e)
    if not os.path.isfile(dist):
        return run.step('monitor', True, 'SpeedKit Monitor is not built, so load times are not measured.', warn=True)
    plan = ingame_install.install(dry_run=True, dist=dist, sims=_sims())
    if plan['action'] == 'up_to_date' and not plan['quarantine']:
        return run.step('monitor', True, 'SpeedKit Monitor is installed.')
    ingame_install.install(dry_run=False, dist=dist, sims=_sims(), home=_home(), check_game=_cfg['check_game'])
    return run.step('monitor', True, 'SpeedKit Monitor %s.' % ('updated' if plan['action'] == 'replace' else 'installed'))


GRAPHICS_KEEP = 'keep_previous'     # settings.json 'graphics': the user put the old graphics file back


def _graphics_choice():
    """What the user chose for the graphics file: GRAPHICS_KEEP after 'Put my old graphics back' (or undoing Max
    Quality), until they press 'Fix the lag' again; else None (Play switches SGR Full to Max Quality)."""
    return G.read_settings(_sims(), _home()).get('graphics')


def _remember(key, value):
    """Keep (value None: forget) one of SpeedKit's own choices in <Sims 4>\\SpeedKit\\settings.json (the file
    gamepath keeps the game's place in). Best effort."""
    try:
        doc = G.read_settings(_sims(), _home())
        if doc.get(key) == value:
            return
        if value is None:
            doc.pop(key, None)
        else:
            doc[key] = value
        G._write_settings(doc, _sims(), _home())
    except OSError as e:
        _log_error('remember ' + key, e)


def _set_graphics_choice(value):
    """Remember (or forget, value None) the user's graphics choice."""
    _remember('graphics', value)


def _ensure_graphics(run, game):
    """Graphics: 'SpeedKit Max Quality' when SGR Full is active (settings.graphics_use_tuned; docs\\settings.md) -
    unless the user put the previous file back on purpose (then it is left alone until they tune again)."""
    try:
        p = ST.graphics_use_tuned(dry_run=True, sims=_sims(), home=_home(), check_game=False, game_bin=_game_bin(game))
        if p['action'] == 'none':
            return run.step('graphics', True, 'Graphics: SpeedKit Max Quality is on.')
        if p['action'] in ('add', 'replace') and _graphics_choice() == GRAPHICS_KEEP:
            return run.step('graphics', True, "Graphics: your previous graphics file, as you chose ('Fix the lag' on "
                                              "the Performance page switches Max Quality back on).")
        if p['action'] == 'refused':
            if p['active'] == 'stock':
                return run.step('graphics', True, "Graphics: the game's own settings.")
            return run.step('graphics', True, 'Graphics: your own graphics file was left as it is (%s).'
                            % (p['active_label'] or 'a custom file'), warn=True)
        ST.graphics_use_tuned(dry_run=False, sims=_sims(), home=_home(), check_game=_cfg['check_game'],
                              game_bin=_game_bin(game))
        _cache.clear()
        return run.step('graphics', True, 'Graphics: switched to SpeedKit Max Quality - sharp, without the lag.')
    except Exception as e:
        _log_error('graphics', e)
        return run.step('graphics', True, 'Graphics could not be tuned (%s); the game starts with the old settings.'
                        % _plain(e), warn=True)


def _ensure_game_index(game, run):
    """The game index (EA overrides) must be current before parts b/c are planned; only needed on a cache miss."""
    gi = game_index.GameIndex(_cfg['game_db'], game['game_dir'])
    try:
        run.tell('pack', None, "Reading the game's own files (first time only)")
        gi.scan()
    finally:
        gi.close()


def _provider(slot, game, lib, run):
    """The pack tool profiles.switch uses (fast pack or the save's pack), with SpeedKit's caches."""
    ids = _game_ids(game)
    v = _verdicts_fn()

    def refs():
        if slot:
            return S.scan_one(_saves(), slot, _cfg['refs_db'])
        r = U.scan_references(_saves(), _tray(), _cfg['refs_db'], workers=_cfg['scan_workers'])
        if r.stats.get('errors'):
            raise PR.ProfileError('Some saves could not be read (%s) - the game may be saving; try again in a '
                                  'minute.' % ', '.join(sorted(r.stats['errors'])[:3]))
        return r
    plan_kw = {'bc_cache': _cfg['bc_cache'], 'game': ids, 'game_db': _cfg['game_db'], 'game_dir': game['game_dir'],
               'cache_path': _cfg['companions_cache'], 'max_package_bytes': _cfg['max_package_bytes']}
    prov = _Provider(slot, refs=refs, plan_kw=plan_kw, prune=_cfg['prune'], companions_cache=_cfg['companions_cache'],
                     game_dir=game['game_dir'], verdicts=v)
    prov.before_plan = lambda lib_, parked: (F.cached_bc(lib_, parked, ids, _cfg['bc_cache']) is None
                                             and _ensure_game_index(game, run))
    return prov


class _Provider(S.PackProvider):
    """PackProvider that knows the test verdicts and max package size."""

    def __init__(self, slot, verdicts=None, **kw):
        plan_kw = dict(kw.pop('plan_kw', {}))
        self.max_package_bytes = plan_kw.pop('max_package_bytes', 1_900_000_000)
        super().__init__(slot, plan_kw=plan_kw, **kw)
        self.verdicts_fn = verdicts
        self.before_plan = None

    def park_set(self, lib, roots=F.ROOTS2, verdicts=None, cache_path=None):
        if verdicts is None and self.verdicts_fn is not None:
            verdicts = self.verdicts_fn(lib)
        return super().park_set(lib, roots, verdicts, cache_path)

    def update_pack(self, lib=None, out_dir=None, dry_run=True, check_game=False, sims=None, home=None, progress=None):
        refs = self._refs()
        kw = dict(self.plan_kw)
        if progress is not None:
            kw['progress'] = progress
        parked = self.park_set(lib)
        if self.before_plan is not None:
            self.before_plan(lib, parked)             # the game index must be current when b/c are planned
        common = dict(out_dir=out_dir, parked=parked, dry_run=dry_run, check_game=check_game, sims=sims, home=home,
                      prune=self.prune, max_package_bytes=self.max_package_bytes)
        if self.slot is None:
            res = F.update_pack(lib, refs, **common, **kw)
        else:
            res = F.update_pack(lib, S.save_refs(refs, self.slot), kind=self.kind, **common, **kw)
        plan = res.pop('plan', None)
        if plan is not None:
            res['plan_stats'] = {k: plan.stats.get(k) for k in ('keys', 'bytes', 'parts', 'cas_parts', 'bc_cache',
                                                                'seconds', 'timings')}
        self.last = res
        return res


def _pack_message(profile, slot, info, prov):
    what = 'Fast pack' if profile == 'fast' else 'Save pack'
    if not info:
        return '%s: ready.' % what
    last = prov.last if prov else None
    if last:
        act = last.get('action')
        st = last.get('plan_stats') or {}
        gb = _gb(st.get('bytes'))
        if act == 'rebuild':
            return '%s: built (%.1f GB, %d items).' % (what, gb, st.get('keys') or 0)
        if act == 'delta':
            return '%s: added %d new items (%.0f MB).' % (what, last.get('missing_keys') or 0,
                                                        (last.get('missing_bytes') or 0) / 1e6)
        if act == 'refresh':
            return '%s: up to date (checked against your latest saves).' % what
    return '%s: up to date.' % what


def _switch(run, profile, slot, game, lib):
    prov = None
    if profile in ('fast', 'save'):
        if slot and not os.path.isfile(os.path.join(_saves(), slot + '.save')):
            raise S.SaveError('The save %s is gone.' % slot)
        prov = _provider(slot, game, lib, run)
        run.tell('pack', None, 'Checking the %s' % ('fast pack' if profile == 'fast' else 'pack of this save'))
    v = _verdicts_fn()
    plan = PR.switch(profile, dry_run=False, lib=lib, sims=_sims(), home=_home(), check_game=_cfg['check_game'],
                     fastmode=prov, verdicts=v if v else None, companions_cache=_cfg['companions_cache'],
                     save_slot=slot, progress=run.tell, scan=False)
    if prov is not None:
        run.step('pack', True, _pack_message(profile, slot, plan.get('pack'), prov))
    return plan


def _plain_warning(w):
    """The profile switch's warnings in the user's words."""
    if 'more than one folder deep' in w:
        return 'Some script mods sit too deep in the Mods folder and never load (see the library report).'
    if 'still need a parked script' in w:
        return 'Some mods need a script mod that is set aside in this mode.'
    if 'exist in both Mods and Mods_parked' in w:
        return 'Some mods exist twice (in Mods and in the set-aside folder); the copy in Mods is used.'
    if w.startswith('after the switch'):
        return 'The Mods folder did not end up exactly as planned - press the button again.'
    return _plainify(w)


def _switch_message(profile, slot, plan):
    names = {'full': 'Full Start', 'fast': 'Quick Start', 'studio': 'Studio'}
    what = names.get(profile) or 'Play this save (%s)' % slot
    if plan.get('nothing_to_do'):
        return 'Mods folder: already set to %s.' % what
    c = plan.get('counts') or {}
    return 'Mods folder: switched to %s (%d mod files set aside, %d brought back).' % (
        what, c.get('park_files', 0), c.get('restore_files', 0))


def _run_flow(target, launch, progress):
    run = _Run(progress)
    try:
        profile, slot = _parse_target(target)
    except S.SaveError as e:
        return run.result(False, str(e))
    if _game_running():
        return run.result(False, 'The Sims 4 is already running. Close it first, then press the button again.')
    loc = _locate()
    game = _game()
    if game is None and (launch or profile in ('fast', 'save')):
        run.step('game', False, loc.get('message') or "I can't find The Sims 4.")
        return run.result(False, loc.get('message') or "The Sims 4 wasn't found. Click 'Locate The Sims 4'.")
    lib = None
    try:
        _housekeeping(run)
        run.tell('library', None, 'Checking your mods')
        lib = _library()
        st = lib.scan()
        run.step('library', True, 'Checked your mods (%s mod files%s).' % (
            '{:,}'.format(st['packages']), ', %d changed' % st['reread'] if st['reread'] else ''))
        monitor = None
        try:
            monitor = _ensure_monitor(run)
        except Exception as e:
            _log_error('monitor', e)
            run.step('monitor', True, 'SpeedKit Monitor could not be installed (%s).' % _plain(e), warn=True)
        if game is not None:
            _ensure_graphics(run, game)
        try:
            plan = _switch(run, profile, slot, game, lib)
        except (PR.ProfileError, S.SaveError, F.FastPackError, J.JournalError, U.PlanStale, ValueError) as e:
            run.step('mods', False, _plain(e))
            return run.result(False, _plain(e))
        _cache.clear()
        run.step('mods', True, _switch_message(profile, slot, plan))
        for w in plan.get('warnings') or []:
            run.step('mods', True, 'Note: ' + _plain_warning(w), warn=True)
        if monitor == 'parked':                     # the switch brought the parked copy back: now check it
            try:
                _ensure_monitor(run, after_switch=True)
            except Exception as e:
                _log_error('monitor', e)
                run.step('monitor', True, 'SpeedKit Monitor could not be installed (%s).' % _plain(e), warn=True)
        rep = None
        try:
            rep = ST.preflight(_sims(), processes=_cfg['processes'], game_bin=_game_bin(game))
            warns = [w for w in rep['warnings'] if 'already running' not in w]
            if not warns:
                run.step('memory', True, 'Memory: %.1f GB free - fine.' % (rep['memory']['ram_available_mb'] / 1024))
            for w in warns:
                run.step('memory', True, w, warn=True)
        except Exception as e:
            _log_error('preflight', e)
            run.step('memory', True, 'The memory check was skipped (%s).' % _plain(e), warn=True)
        if not launch:
            return run.result(True, 'Ready. Everything is prepared - start the game whenever you like.')
        try:
            url = G.STEAM_URL if game.get('store') == 'steam' else None
            r = LA.launch(
                exe=game['exe'], dry_run=False, sims=_sims(), home=_home(), check_game=_cfg['check_game'],
                processes=_cfg['processes'], url=url, preflight_report=rep,
                extra={'save_slot': slot} if slot else None)
        except Exception as e:
            _log_error('launch', e)
            run.step('launch', False, 'The game could not be started (%s).' % _plain(e))
            return run.result(False, 'Everything is prepared, but the game could not be started: %s' % _plain(e))
        if r.get('refused'):
            why = r['refused']
            if why.startswith('Game exe not found'):
                why = ("The game's program file is missing (%s). Everything else is prepared - click 'Locate The Sims 4' "
                       "and select its folder." % game['exe'])
            run.step('launch', False, why)
            return run.result(False, why)
        run.step('launch', True, 'Starting The Sims 4%s.' % (' through Steam' if url else ''))
        return run.result(True, 'The Sims 4 is starting.', launched=True)
    except Exception as e:
        _log_error('play', e)
        run.step('error', False, _plain(e))
        return run.result(False, 'Something went wrong: %s' % _plain(e))
    finally:
        if lib is not None:
            lib.close()


@_safe
def play(target, progress=None):
    """One click: prepare everything for target ('fast' | 'full' | 'studio' | 'save:<slot>') and start the game.
    Returns {'ok', 'message', 'launched', 'steps': [{'step', 'ok', 'message'}]}."""
    with _run_lock:
        return _run_flow(target, True, progress)


@_safe
def prepare(target, progress=None):
    """Everything play() does except starting the game."""
    with _run_lock:
        return _run_flow(target, False, progress)


_run_lock = threading.Lock()


# ------------------------------------------------------------------------------------------ undo
HELPER_NOTES = ('thumbnail cache moved aside', 'bring the fast pack home')


PACK_KINDS = ('fastpack', 'savepack')             # SpeedKit's own packs: rebuilt by Play, nothing to undo


def _undoable(j):
    """The state rule: a finished (or failed) change that is not a small helper step of a switch, and not a
    pack build (undoing one would only delete the pack, which the next Play builds again)."""
    state = j['state'] or ''
    if state != 'committed' and not state.startswith('failed'):
        return False
    if j.get('kind') in PACK_KINDS:
        return False
    return not any((j['note'] or '').startswith(n) for n in HELPER_NOTES)


INDEPENDENT_KINDS = ('settings', 'caches', 'saves')   # changes outside Mods / Mods_parked ('saves': a restore)


def _moved_between_roots(jid, home):
    """For a change undone with plain journal.undo (duplicate clean-up, SpeedKit Monitor, packs): the first file
    it put into (or took out of) Mods or Mods_parked that sits at the same place in the OTHER root now - a
    Mods switch (SpeedKit's or the other chat's mods_switch.py) moved it since. journal.undo would count the
    moved file as 'already gone' and put the old copy back beside it: two copies. Returns that path or None."""
    try:
        with open(os.path.join(home, 'journal', jid + '.json'), encoding='utf-8') as f:
            steps = json.load(f).get('steps') or []
    except (OSError, ValueError):
        return None
    roots = ((_mods(), _parked()), (_parked(), _mods()))
    for s in steps:
        p = s.get('path') if s.get('op') in ('put_new', 'quarantine') and not s.get('undone') else None
        if not p or os.path.exists(p):
            continue
        for root, other in roots:
            if os.path.normcase(os.path.abspath(p)).startswith(os.path.normcase(root) + os.sep):
                twin = os.path.join(other, os.path.relpath(p, root))
                if os.path.exists(twin):
                    return twin
    return None


def _undo_journal(j, dry_run):
    """Undo one change with the tool that made it (dry_run: only check it could be undone now)."""
    jid, kind, home = j['id'], j['kind'], j['_home']
    check = _cfg['check_game'] and not dry_run
    if kind in ('aside', 'saves'):                  # patch day / save backups (api_care.py)
        from . import api_care
        return api_care.undo(j, dry_run, check)
    if kind not in ('profile', 'merge', 'inbox') + INDEPENDENT_KINDS:
        moved = _moved_between_roots(jid, home)
        if moved:
            raise J.JournalError('%s was moved by a Mods folder switch since this change; switch back first' % moved)
    if kind == 'profile':
        return PR.undo_switch(jid, dry_run=dry_run, sims=_sims(), home=home, check_game=check)
    if kind in ('merge', 'inbox'):
        from . import merge
        return merge.undo(jid, home=home, check_game=check, dry_run=dry_run)
    if kind in ('settings', 'caches'):
        return ST.restore(jid, dry_run=dry_run, sims=_sims(), home=home, check_game=check)
    return J.undo(jid, home=home, check_game=check, dry_run=dry_run)


def _undo_refusal(j):
    """None when the change could be undone now (checked against the disk, nothing moves), else the reason."""
    try:
        _undo_journal(j, dry_run=True)
    except Exception as e:
        return _plain(e) or type(e).__name__
    return None


NOT_UNDOABLE = ('cannot be undone now: its files were changed or moved since (by you or another tool). To change '
                'how the game starts, pick a way to play on the Home page.')


@_safe
def undo_last(progress=None):
    """Undo the newest SpeedKit change that can still be undone (a change that can no longer be undone - its files
    were changed since, e.g. by the other chat's mods_switch.py - is skipped; status() marks the same one
    next_undo). Returns {'ok', 'message', 'journal'}."""
    tell = _Progress(progress)
    if _game_running():
        return {'ok': False, 'message': 'The Sims 4 is running. Close it first, then undo.', 'journal': None}
    with _run_lock:
        js = _journals(limit=0)
        cands = [j for j in js if j['next_undo']]
        if not cands:
            blocked = [j for j in js if j.get('_why')]
            if blocked:
                return {'ok': False, 'journal': None, 'message': 'There is nothing left that can be undone. "%s" %s'
                        % (blocked[0]['title'], NOT_UNDOABLE)}
            return {'ok': False, 'message': 'There is nothing to undo.', 'journal': None}
        j = cands[0]
        tell('undo', None, 'Undoing: %s' % j['title'])
        try:
            _undo_journal(j, dry_run=False)
        except Exception as e:
            _log_error('undo', e)
            return {'ok': False, 'message': 'Could not undo "%s": %s' % (j['title'], _plain(e)), 'journal': j['id']}
        if j['kind'] == 'settings' and 'max quality' in (j['note'] or '').lower():
            _set_graphics_choice(GRAPHICS_KEEP)     # undoing Max Quality is a choice too: Play leaves it alone
    _cache.clear()
    return {'ok': True, 'message': 'Undone: %s (%s).' % (j['title'], (j['when'] or '').replace('T', ' ')),
            'journal': j['id']}


# ------------------------------------------------------------------------------------------ inbox
def _inbox_reason(it):
    """One plain sentence about one download (merge.process_inbox gives a reason per file, and joined they read
    oddly: 'everything in it is already installed; new CC (8 resources already installed were left out)')."""
    files = it.get('files') or []
    if it.get('status') in ('refused', 'skipped') or not files:
        return it.get('why') or None
    if any(str(f.get('file') or '').lower().endswith('.ts4script') for f in files):
        if any(f.get('action') == 'update' for f in files):
            return 'An update of a script mod you have: the new files replace the old ones.'
        if all(f.get('action') == 'duplicate' for f in files):
            return 'This script mod is already in your game.'
        return 'A script mod (%d file%s): it goes into its own folder in Mods, untouched.' % (
            len(files), '' if len(files) == 1 else 's')
    n = collections.Counter(f.get('action') for f in files)
    bits = []
    for action, one, many in (('merge', '%d new CC file', '%d new CC files'),
                              ('update', '%d update of a mod you have', '%d updates of mods you have'),
                              ('install', '%d mod added as it is', '%d mods added as they are'),
                              ('loose', '%d CC file kept apart (it differs from CC you have)',
                               '%d CC files kept apart (they differ from CC you have)'),
                              ('duplicate', '%d already in your game', '%d already in your game')):
        if n.get(action):
            bits.append((one if n[action] == 1 else many) % n[action])
    text = ', '.join(bits) if bits else it.get('why') or ''
    return (text[:1].upper() + text[1:] + '.') if text else None


@_safe
def inbox(apply=False, progress=None):
    """What the Inbox holds and where each download goes; apply=True installs them. Returns {'ok', 'message',
    'items': [{'name', 'status', 'where', 'reason'}], 'inbox_path'}."""
    from . import merge
    tell = _Progress(progress)
    if apply and _game_running():
        return {'ok': False, 'message': 'The Sims 4 is running. Close it first.', 'items': [],
                'inbox_path': merge.inbox_path(sims=_sims())}
    lib = _library()
    try:
        tell('inbox', None, 'Checking your mods')
        lib.scan()
        path = merge.inbox_path(lib, _sims())
        if apply:
            merge.ensure_inbox(lib, _sims())
        tell('inbox', None, 'Looking at your downloads')
        with _run_lock:
            rep = merge.process_inbox(lib, dry_run=not apply, journal_home=_home(), sims=_sims(),
                                      check_game=_cfg['check_game'], cache_path=_cfg['hash_cache'])
    finally:
        lib.close()
    items = []
    for it in rep.get('items', []):
        files = it.get('files') or []
        where = sorted({f.get('to') for f in files if f.get('to')})
        items.append({'name': it.get('item'), 'status': it.get('status'),
                      'where': ', '.join(where) if where else None, 'reason': _inbox_reason(it) or None,
                      'files': [{'file': f.get('file'), 'action': f.get('action'), 'to': f.get('to')} for f in files]})
    for it in items:
        it['reason'] = _plainify(it['reason'])
    ready = [i for i in items if i['status'] not in ('skipped', 'refused')]
    held = len(items) - len(ready)
    held_msg = (' %d cannot be added yet (see why).' % held) if held else ''
    if not items:
        msg = 'Your Inbox is empty. Drop downloads into it, then press this again.'
    elif apply:
        done = sum(1 for i in items if i['status'] == 'done')
        msg = 'Added %d of %d downloads.%s' % (done, len(items), held_msg)
    elif ready:
        msg = "%d download%s waiting. Press 'Add them to my game' to add %s.%s" % (
            len(ready), ' is' if len(ready) == 1 else 's are', 'it' if len(ready) == 1 else 'them', held_msg)
    else:
        msg = 'Nothing can be added yet.%s' % held_msg
    if rep.get('journal'):
        _cache.clear()
    return {'ok': True, 'message': msg, 'items': items, 'inbox_path': path, 'journal': rep.get('journal'),
            'warnings': rep.get('warnings') or []}


# ------------------------------------------------------------------------------------------ duplicate clean-up
def _norm_path(p):
    return os.path.normcase(os.path.abspath(p))


def _cleanup_homes_known():
    """The folders on other drives where duplicate clean-ups keep their record and safe copies: configured, and
    every one remembered in settings.json ('cleanup_homes') - so those changes stay on the Tools page and can
    still be undone after the Hub was closed and opened again. Existing folders only, SpeedKit's own left out."""
    out, seen = [], {_norm_path(_home())}
    for h in [_cfg['cleanup_home']] + list(G.read_settings(_sims(), _home()).get('cleanup_homes') or []):
        if isinstance(h, str) and h and _norm_path(h) not in seen and os.path.isdir(h):
            seen.add(_norm_path(h))
            out.append(h)
    return out


def _cleanup_home(need_bytes):
    """Where the duplicate clean-up keeps its journal and quarantine: configured, else SpeedKit's folder when
    the Sims drive keeps 20 GB free, else a remembered '<other drive>\\SpeedKit Quarantine' that still has room,
    else a new one on the fixed drive with most room."""
    if _cfg['cleanup_home']:
        return _cfg['cleanup_home']
    try:
        free = shutil.disk_usage(_sims()).free
    except OSError:
        free = 0
    if free - need_bytes > 20 * 2 ** 30:
        return _home()
    for h in _cleanup_homes_known():
        try:
            if shutil.disk_usage(h).free > need_bytes + 20 * 2 ** 30:
                return h
        except OSError:
            continue
    best = None
    sims_drive = os.path.splitdrive(os.path.abspath(_sims()))[0].upper()
    for d in G.fixed_drives():
        if d[:2].upper() == sims_drive:
            continue
        try:
            f = shutil.disk_usage(d).free
        except OSError:
            continue
        if f > need_bytes + 20 * 2 ** 30 and (best is None or f > best[0]):
            best = (f, os.path.join(d, 'SpeedKit Quarantine'))
    return best[1] if best else _home()


def _packs_in_mods():
    """SpeedKit pack files at the Mods (or Mods_parked) root. The duplicate clean-up must not run then: a pack
    holds copies of library resources, and the clean-up would take them for the copies to keep."""
    out = []
    for root in (_mods(), _parked()):
        try:
            out += [n for n in os.listdir(root) if F.is_speedkit_pack(n)]
        except OSError:
            pass
    return out


PACKS_IN_MODS = "Freeing disk space works in the 'Full Start' mode only. Prepare 'Full Start' first, then try again."


def _dedup_plan(tell):
    from . import dedup
    lib = _library()
    lib.scan()
    tell('cleanup', None, 'Looking for exact duplicate copies (this can take a minute)')
    key = ('dedup', F.listing_fingerprint(F.library_listing_index(F._view(lib))))
    with _lock:
        hit = _cache.get(key)
    if hit:
        return lib, hit[1]
    plan = dedup.plan(lib, cache_path=_cfg['hash_cache'], companions_cache=_cfg['companions_cache'])
    with _lock:
        _cache[key] = (time.time(), plan)
    return lib, plan


@_safe
def cleanup_plan(progress=None):
    """How much disk space removing exact duplicate copies would free (nothing changes). Returns {'ok',
    'message', 'copies', 'gb', 'rewritten', 'removed'}."""
    tell = _Progress(progress)
    if _packs_in_mods():
        return {'ok': False, 'message': PACKS_IN_MODS, 'copies': 0, 'gb': 0.0, 'rewritten': 0, 'removed': 0}
    lib, plan = _dedup_plan(tell)
    try:
        s = plan.summary()
    finally:
        lib.close()
    gb = _gb(s['stored_bytes_dropped'])
    msg = ('No duplicate copies found.' if not s['copies_dropped'] else
           '%d duplicate copies (%s) can be removed. Nothing changes what the game shows.'
           % (s['copies_dropped'], _size_text(s['stored_bytes_dropped'])))
    return {'ok': True, 'message': msg, 'copies': s['copies_dropped'], 'gb': gb,
            'mb': round((s['stored_bytes_dropped'] or 0) / 1e6, 1),
            'rewritten': s['packages_rewritten'], 'removed': s['packages_quarantined']}


def _size_text(n):
    """'2.4 GB', '35 MB' or 'less than 1 MB' (never '0.0 GB')."""
    n = n or 0
    if n >= 1e8:
        return '%.1f GB' % (n / 1e9)
    if n >= 1e6:
        return '%d MB' % round(n / 1e6)
    return 'less than 1 MB'


@_safe
def cleanup_apply(progress=None):
    """Remove the exact duplicate copies (kept in a quarantine; undo_last puts them back). Returns {'ok',
    'message', 'journal'}."""
    from . import dedup
    tell = _Progress(progress)
    if _game_running():
        return {'ok': False, 'message': 'The Sims 4 is running. Close it first.', 'journal': None}
    if _packs_in_mods():
        return {'ok': False, 'message': PACKS_IN_MODS, 'journal': None}
    lib, plan = _dedup_plan(tell)
    try:
        s = plan.summary()
        if not s['copies_dropped']:
            return {'ok': True, 'message': 'There are no duplicate copies to remove.', 'journal': None}
        home = _cleanup_home(s['packages_rewritten_bytes'] + s['packages_quarantined_bytes'])
        tell('cleanup', None, 'Removing duplicate copies')
        with _run_lock:
            res = dedup.apply(plan, lib, journal_home=home, sims=_sims(), dry_run=False,
                              check_game=_cfg['check_game'], cache_path=_cfg['hash_cache'])
    finally:
        lib.close()
    _cache.clear()
    jid = res.get('journal') if isinstance(res, dict) else None
    if _norm_path(home) != _norm_path(_home()) and jid:
        known = [h for h in G.read_settings(_sims(), _home()).get('cleanup_homes') or [] if isinstance(h, str)]
        if _norm_path(home) not in {_norm_path(h) for h in known}:
            _remember('cleanup_homes', known + [home])      # found again after the Hub restarts (undo, Tools page)
    return {'ok': True, 'message': 'Removed %d duplicate copies. The originals are kept in a safe place, so this '
            'can be undone.' % s['copies_dropped'], 'journal': jid}


# ------------------------------------------------------------------------------------------ graphics
PLAIN_SETTINGS = {'RenderSimLODDistances': 'Sim detail distance', 'RenderSimTextureSizes': 'Sim texture sharpness',
                  'ObjectSizeCullFactor': 'Small-object culling', 'ObjectLODBias': 'Object detail switching',
                  'ClipPlaneDistances': 'How far you can see', 'FSAALevel': 'Edge smoothing',
                  'ShadowMapSize': 'Shadow sharpness', 'MirrorFadeRadiusThreshold': 'Mirror fade distance',
                  'InteriorMirrorFarPlane': 'Mirror reflections indoors',
                  'ExteriorMirrorFarPlane': 'Mirror reflections outdoors', 'TerrainLODBoost': 'Terrain detail'}


@_safe
def graphics_tune(apply=False, progress=None):
    """SpeedKit Max Quality: the before/after table, and with apply=True install it. Returns {'ok', 'message',
    'table': [{'setting', 'stock', 'before', 'after'}]}."""
    game = _game()
    if game is None:
        return {'ok': False, 'message': "The Sims 4 wasn't found. Click 'Locate The Sims 4' first.", 'table': []}
    if apply and _game_running():
        return {'ok': False, 'message': 'The Sims 4 is running. Close it first.', 'table': []}
    p = ST.graphics_use_tuned(dry_run=not apply, sims=_sims(), home=_home(), check_game=_cfg['check_game'] and apply,
                              game_bin=_game_bin(game))
    table = [{'setting': PLAIN_SETTINGS.get(r.get('prop')) or r.get('what') or r.get('prop'), 'prop': r.get('prop'),
              'detail': r.get('what'), 'stock': _plain_value(r.get('stock')), 'before': _plain_value(r.get('before')),
              'after': _plain_value(r.get('after'))}
             for r in p.get('table') or []]
    _cache.clear()
    if p['action'] == 'refused':
        return {'ok': False, 'message': _plainify(p['refused']), 'table': table}
    if p['action'] == 'none':
        return {'ok': True, 'message': 'SpeedKit Max Quality is already on.', 'table': table}
    if not apply:
        return {'ok': True, 'message': 'SpeedKit Max Quality keeps your sharp graphics and removes the lag. '
                'Press Apply to switch.', 'table': table}
    _set_graphics_choice(None)                  # the user wants Max Quality again: Play keeps it on from now on
    return {'ok': True, 'message': 'Switched to SpeedKit Max Quality.', 'table': table, 'journal': p.get('journal')}


@_safe
def graphics_restore(apply=False, progress=None):
    """Put the graphics file back as it was before SpeedKit Max Quality. Returns {'ok', 'message'}."""
    if apply and _game_running():
        return {'ok': False, 'message': 'The Sims 4 is running. Close it first.'}
    try:
        acts = ST.graphics_restore(None, dry_run=not apply, sims=_sims(), home=_home(), check_game=_cfg['check_game'])
    except J.JournalError as e:
        msg = str(e)
        if 'no SpeedKit Max Quality install' in msg:
            msg = 'SpeedKit Max Quality is not installed, so there is nothing to put back.'
        return {'ok': False, 'message': _plainify(msg)}
    _cache.clear()
    if not apply:
        return {'ok': True, 'message': 'This puts your previous graphics file back (%d step%s).'
                % (len(acts), '' if len(acts) == 1 else 's')}
    _set_graphics_choice(GRAPHICS_KEEP)         # the next Play must not switch Max Quality back on by itself
    return {'ok': True, 'message': 'Your previous graphics file is back.'}


# ------------------------------------------------------------------------------------------ report
@_safe
def report(progress=None):
    """Write reports\\library_report.html (a readable overview). Returns {'ok', 'message', 'path'}."""
    from . import report as R
    tell = _Progress(progress)
    tell('report', None, 'Collecting the numbers')
    st = status()
    saves = list_saves(progress)
    game = _game()
    table = []
    if game:
        try:
            table = [{'setting': PLAIN_SETTINGS.get(r.get('prop')) or r.get('what') or r.get('prop'),
                      'stock': _plain_value(r.get('stock')), 'before': _plain_value(r.get('before')),
                      'after': _plain_value(r.get('after'))}
                     for r in ST.graphics_tuned_table(_sims(), _home(), _game_bin(game))]
        except Exception:
            table = []
    path = os.path.join(_reports(), 'library_report.html')
    R.write(path, st, saves.get('saves', []) if saves.get('ok') else [], table)
    return {'ok': True, 'message': 'The report is ready.', 'path': path}


# ------------------------------------------------------------------------------------------ opening things
def _animator_path():
    """Novulon's Wicked Animator: the configured path, else 'Wicked Animator.exe', else 'Start Wicked
    Animator.bat' (in Tools\\sims4_animator); None when none of them is there."""
    if _cfg['animator']:
        return _cfg['animator'] if os.path.isfile(_cfg['animator']) else None
    for p in (ANIMATOR_EXE, ANIMATOR_BAT):
        if os.path.isfile(p):
            return p
    return None


def _start_quietly(path):
    """Start a program (or a .bat) detached, with no console window, in its own folder."""
    flags = (getattr(subprocess, 'DETACHED_PROCESS', 0) | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0))
    kw = dict(cwd=os.path.dirname(path), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
              stderr=subprocess.DEVNULL, close_fds=True)
    if path.lower().endswith(('.bat', '.cmd')):
        proc = subprocess.Popen(['cmd.exe', '/c', path], creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), **kw)
    else:
        proc = subprocess.Popen([path], creationflags=flags, **kw)
    _STARTED.append(proc)       # kept (like launch._LAUNCHED): the program outlives this call on purpose


_STARTED = []


@_safe
def open_animator():
    """Start Novulon's Wicked Animator (the desktop app: it is single-instance, so a second start only brings its
    window to the front; the .bat is the fallback when the exe is missing). Returns {'ok', 'message'}."""
    p = _animator_path()
    if p is None:
        return {'ok': False, 'message': "Novulon's Wicked Animator is not installed on this PC."}
    if _cfg['opener'] is not None:
        _cfg['opener'](p)
    else:
        _start_quietly(p)
    return {'ok': True, 'message': "Starting Novulon's Wicked Animator.", 'path': p}


FOLDERS = ('mods', 'reports', 'inbox', 'saves', 'quarantine')


@_safe
def open_folder(which):
    """Open a folder in Explorer: mods | reports | inbox | saves | quarantine (also 'report_html': the last
    library_report.html). Returns {'ok', 'message'}."""
    if which == 'report_html':
        p = os.path.join(_reports(), 'library_report.html')
        if not os.path.isfile(p):
            return {'ok': False, 'message': 'There is no report yet - make one first.'}
        _open(p)
        return {'ok': True, 'message': 'Opened the report.', 'path': p}
    paths = {'mods': _mods(), 'reports': _reports(), 'inbox': os.path.join(_home(), 'Inbox'), 'saves': _saves(),
             'quarantine': os.path.join(_home(), 'quarantine')}
    if which not in paths:
        return {'ok': False, 'message': 'Unknown folder %r.' % which}
    p = paths[which]
    if which in ('reports', 'inbox', 'quarantine'):
        os.makedirs(p, exist_ok=True)                  # SpeedKit's own folders
    if not os.path.isdir(p):
        return {'ok': False, 'message': 'The %s folder does not exist yet.' % which}
    _open(p)
    return {'ok': True, 'message': 'Opened %s.' % p, 'path': p}


# ------------------------------------------------------------------------------------------ CC browser
# The Library page's pictures and categories and the Saves page's "CC this save uses" (speedkit/ccbrowser.py,
# docs/ccbrowser.md). Its index and pictures live beside the library index (data\ccbrowser.sqlite,
# data\ccthumbs\), never in the game's folders.
CC_MISSING_KINDS = {'cas': 'Clothing, hair, makeup or another Create a Sim item',
                    'object': 'A Build/Buy object on a lot', 'look': 'A skin tone, slider or preset'}
_CC_PICS = []                       # one ExtraPictures for the whole process (it keeps file indexes in memory)


def _cc_paths():
    d = os.path.dirname(os.path.abspath(_cfg['db_path']))
    return os.path.join(d, 'ccbrowser.sqlite'), os.path.join(d, 'ccthumbs')


def _cc_index():
    from . import ccbrowser as CB
    return CB.CCIndex(_cc_paths()[0])


def _cc_thumbs():
    from . import ccbrowser as CB
    return CB.ThumbCache(_cc_paths()[1])


def _cc_side_places():
    """Where CC that is not in Mods may still be: the Hub's safe copies (every journal home) and the Inbox."""
    places = [('safe copies', os.path.join(h, 'quarantine')) for h in _journal_homes()]
    places.append(('Inbox', _inbox_path()))
    return places


def _cc_extra(more=()):
    """ExtraPictures over the game's thumbnail cache, the newest thumbnail caches in the safe copies and `more`."""
    from . import ccbrowser as CB
    if not _CC_PICS:
        _CC_PICS.append(CB.ExtraPictures())
    ex = _CC_PICS[0]

    def old_caches():
        out = []
        for _, q in _cc_side_places()[:-1]:
            for dp, dn, fn in os.walk(q):
                out += [os.path.join(dp, n) for n in fn if n.lower() == 'localthumbcache.package']

        def age(p):
            try:
                return -os.path.getmtime(p)
            except OSError:
                return 0
        return sorted(out, key=age)[:5]
    return ex.with_files([os.path.join(_sims(), 'localthumbcache.package')] + list(more) +
                         _cached(('cc_old_caches',), 300, old_caches))


def _cc_token(text):
    import hashlib
    return hashlib.blake2b(text.encode('utf-8', 'replace'), digest_size=6).hexdigest()


def _cc_view(row):
    """One index row as the app shows it (plain words, no inside names)."""
    from . import ccbrowser as CB
    if not row:
        return None
    used_by = json.loads(row['used_by']) if row.get('used_by') else []
    pic = _cc_token('%s|%s|%s|%s' % (row['rel'], row['size'], row['mtime'], row['thumb'])) if row.get('thumb') else None
    dup = row.get('dup_of')
    return {'id': row['id'], 'name': row['name'], 'rel': row['rel'], 'folder': row['folder'] or '',
            'creator': row['creator'], 'kind': row['kind'], 'category': row['category'],
            'category_label': CB.CATEGORY_LABELS.get(row['category'], 'Other'),
            'cats': [c for c in (row['cats'] or '').split(',') if c], 'body': row['body'],
            'part_name': row['part_name'], 'size_mb': round((row['size'] or 0) / 1e6, 2),
            'modified': datetime.datetime.fromtimestamp(row['mtime'] or 0).isoformat(timespec='seconds'),
            'cas_parts': row['n_cas'] or 0, 'objects': row['n_obj'] or 0, 'pic': pic,
            'in_mods': row['root'] == 'Mods', 'used': None if row['used'] is None else bool(row['used']),
            'used_by': used_by, 'broken': row['broken'],
            'duplicate_of': (os.path.basename(dup) if dup != '?' else 'another file') if dup else None}


@_safe
def cc_list(category=None, folder=None, creator=None, q=None, used=None, flag=None, sort='name', offset=0, limit=60,
            facets=False):
    """One page of the CC browser: {'ok', 'index': {'state': 'ready'|'missing', 'items', 'when', 'used_known'},
    'total', 'offset', 'limit', 'items': [_cc_view], 'categories': [{'key', 'label', 'n'}], 'flags': {'used',
    'unused', 'duplicate', 'broken'}} (+ 'folders', 'creators' with facets=True). Reads only the CC index."""
    from . import ccbrowser as CB
    idx = _cc_index()
    try:
        state = idx.state()
        r = idx.query(category=category or None, folder=folder, creator=creator or None, q=(q or '').strip() or None,
                      used=used if used in ('used', 'unused') else None,
                      flag=flag if flag in CB.FLAGS else None, sort=sort or 'name', offset=offset, limit=limit)
        out = {'ok': True, 'index': state, 'total': r['total'], 'offset': r['offset'], 'limit': r['limit'],
               'items': [_cc_view(x) for x in r['items']],
               'categories': [{'key': k, 'label': lbl, 'n': r['categories'].get(k, 0)} for k, lbl in CB.CATEGORIES],
               'flags': r['flags']}
        if facets:
            out.update(idx.facets())
    finally:
        idx.close()
    if state['state'] == 'missing':
        out['message'] = "CC files have not been sorted yet. Use 'Sort CC files'; the first run takes a few minutes."
    return out


@_safe
def cc_item(item_id):
    """Everything the details window shows about one CC file (its full path too)."""
    from . import ccbrowser as CB
    idx = _cc_index()
    try:
        row = idx.get(item_id)
    finally:
        idx.close()
    if not row:
        return {'ok': False, 'message': 'That file is no longer in the CC list. Use "Look again".'}
    view = _cc_view(row)
    roots = _roots()
    view['path'] = CB.locate(roots, row['root'], row['rel']) or os.path.join(roots.get(row['root'], _mods()),
                                                                              row['rel'].replace('/', os.sep))
    return dict(view, ok=True)


def cc_picture(item_id=None, kind=None, instance=None):
    """The picture of one CC file (item_id) or of one CAS part / object by its id (kind 'cas'|'object', instance as
    16 hex digits): {'ok': True, 'data': bytes, 'type': 'image/webp'|'image/png'} or {'ok': False}. Pictures are
    made once and then read from data\\ccthumbs\\. Not JSON: the server sends the bytes as they are."""
    from . import ccbrowser as CB
    try:
        thumbs = _cc_thumbs()
        if item_id is not None:
            idx = _cc_index()
            lib = None
            try:
                row = idx.get(int(item_id))
                if row and (row.get('thumb') or '').startswith('cache:') and os.path.exists(_cfg['db_path']):
                    lib = _library()
                got = CB.item_picture(idx, thumbs, int(item_id), _roots(), _cc_extra(), lib=lib)
            finally:
                idx.close()
                if lib is not None:
                    lib.close()
        else:
            inst = int(str(instance), 16)
            idx = _cc_index()
            try:
                more = [p for p, place, name, t in idx.side_find([inst]).get(inst, ())]
            finally:
                idx.close()
            lib = _library() if os.path.exists(_cfg['db_path']) else None
            try:
                got = CB.part_picture(lib, thumbs, 'cas' if kind == 'cas' else 'object', inst, _cc_extra(more))
            finally:
                if lib is not None:
                    lib.close()
        if not got:
            return {'ok': False, 'message': 'No picture.'}
        return {'ok': True, 'data': got[0], 'type': got[1]}
    except Exception as e:
        _log_error('cc_picture', e)
        return {'ok': False, 'message': 'No picture.'}


@_safe
def cc_scan(progress=None):
    """Sort every CC file into a category and find its picture (incremental: only new or changed files are read;
    the first time takes a few minutes for a big library). Also marks duplicates, damaged files and which CC the
    saves use. Read-only on the game's folders. Returns {'ok', 'message', 'items', 'read', 'seconds'}."""
    tell = _Progress(progress)
    t0 = time.time()
    with _run_lock:
        tell('library', 0.0, 'Looking for new or changed CC files')
        lib = _library()
        idx = _cc_index()
        try:
            lib.scan()
            tell('saves', 0.12, 'Reading which CC the saves use (the first run takes a while)')
            refs = None
            try:
                refs = U.scan_references(_saves(), _tray(), _cfg['refs_db'], workers=_cfg['scan_workers'])
            except Exception as e:
                _log_error('cc_scan.refs', e)
            names = {}
            try:
                for h in S.list_saves(_saves()):
                    if h.get('name'):
                        names[h['slot'] + '.save'] = h['name']
            except Exception as e:
                _log_error('cc_scan.names', e)

            def sub(step, fraction=None, message=''):
                tell(step, None if fraction is None else round(0.3 + 0.7 * fraction, 3), message)
            res = idx.scan(lib, refs=refs, save_names=names, progress=sub, skip=F.is_speedkit_file)
        finally:
            idx.close()
            lib.close()
    tell('done', 1.0, 'Sorted %s CC files' % format(res['items'], ','))
    msg = 'Sorted %s CC files into categories.' % format(res['items'], ',')
    if res['read']:
        msg += ' %s new or changed files were looked at.' % format(res['read'], ',')
    return {'ok': True, 'message': msg, 'items': res['items'], 'read': res['read'],
            'seconds': round(time.time() - t0, 1)}


@_safe
def cc_set_aside(ids, progress=None):
    """Set CC files aside: out of Mods into the safe copies, as one change that 'Undo last change' puts back.
    ids: CC browser item ids. Refuses while the game runs; script mods and files not in Mods are left alone.
    Returns {'ok', 'message', 'journal', 'done': [names], 'refused': [{'name', 'why'}]}."""
    from . import ccbrowser as CB
    tell = _Progress(progress)
    nothing = {'ok': False, 'message': 'Pick the files to set aside first.', 'journal': None, 'done': [], 'refused': []}
    try:
        ids = [int(i) for i in (ids or [])]
    except (TypeError, ValueError):
        return nothing
    if not ids:
        return nothing
    if _game_running():
        return dict(nothing, message='The Sims 4 is running. Close the game first, then try again.')
    tell('check', 0.0, 'Making sure the game is closed')
    with _run_lock:
        idx = _cc_index()
        try:
            r = CB.set_aside(idx, ids, sims=_sims(), home=_home(), check_game=_cfg['check_game'], progress=tell)
        finally:
            idx.close()
    _cache.clear()
    refused = [{'name': n, 'why': w} for n, w in r['refused']]
    n = len(r['done'])
    if not n:
        why = refused[0]['why'] if refused else ''
        return dict(nothing, message=('Nothing was set aside. %s' % why).strip(), refused=refused)
    msg = ('Set aside %d file%s. They are kept safe - "Undo last change" on the Tools page puts them back.'
           % (n, '' if n == 1 else 's'))
    if refused:
        msg += ' %d file%s stayed where %s.' % (len(refused), '' if len(refused) == 1 else 's',
                                                'it was' if len(refused) == 1 else 'they were')
    tell('done', 1.0, msg)
    return {'ok': True, 'message': msg, 'journal': r['journal'], 'done': r['done'], 'refused': refused}


@_safe
def cc_open(item_id):
    """Open the folder of one CC file in Explorer, with the file selected."""
    info = cc_item(item_id)
    if not info.get('ok'):
        return info
    path = info['path']
    if not os.path.exists(path):
        return {'ok': False, 'message': 'That file is no longer there. Use "Look again".'}
    folder = os.path.dirname(path)
    if _cfg['opener'] is None and os.name == 'nt':
        subprocess.Popen(['explorer', '/select,', path], creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    else:
        _open(folder)
    return {'ok': True, 'message': 'Opened the folder of %s.' % info['name'], 'path': folder}


class _SideLookup:
    """ccbrowser.usage_report's side folders: indexed only when a save really misses CC."""

    def __init__(self, idx):
        self.idx, self.ready = idx, False

    def side_find(self, instances):
        if not self.ready:
            self.idx.side_update(_cc_side_places())
            self.ready = True
        return self.idx.side_find(instances)


@_safe
def save_cc(slot, progress=None):
    """The CC one save uses ('tray': the households and lots in the game's library): the installed CC files with
    their pictures, the CC per household and sim, and the CC it uses that is installed nowhere (by id - and by
    name when a copy is in the safe copies or the Inbox). Read-only. Returns {'ok', 'slot', 'name', 'household',
    'counts', 'files', 'households', 'missing', 'index'}."""
    from . import ccbrowser as CB
    tell = _Progress(progress)
    tell('read', None, 'Reading what this save uses')
    played, name, household = None, None, None
    if slot == 'tray':
        refs = U.load_refs(_saves(), _tray(), _cfg['refs_db'])
        tray_srcs = [s for s in refs.sources if s.kind not in ('save', 'backup')]
        if not tray_srcs:
            return {'ok': False, 'message': 'The in-game library has no households or lots yet.'}
        sub = U.Refs(tray_srcs, {s.fp: refs.by_fp[s.fp] for s in tray_srcs if s.fp in refs.by_fp},
                     {s.fp: refs.sims.get(s.fp, []) for s in tray_srcs}, {}, False)
        name = 'In-game library'
    else:
        try:
            slot = S.slot_name(slot)
        except S.SaveError:
            return {'ok': False, 'message': "That save wasn't found. It may have been deleted or renamed."}
        path = os.path.join(_saves(), slot + '.save')
        if not os.path.isfile(path):
            return {'ok': False, 'message': "That save wasn't found. It may have been deleted or renamed."}
        try:
            if _run_lock.locked():          # a Play is running: use what is known, parse nothing
                sub = S.save_refs(U.load_refs(_saves(), _tray(), _cfg['refs_db']), slot)
            else:
                sub = S.scan_one(_saves(), slot, _cfg['refs_db'])
        except S.SaveError:
            return {'ok': False, 'message': 'This save could not be read just now (the game may be saving it). '
                                            'Try again in a minute.'}
        try:
            h = S.read_header(path)
            played, name, household = h.get('household_id'), h.get('name'), h.get('household')
        except S.SaveError:
            pass
    tell('match', None, 'Matching its CC with your CC files')
    game = _game()
    ids = None
    if game is not None:
        try:
            ids = _game_ids(game)
        except Exception as e:
            _log_error('save_cc.game_ids', e)
    lib = _library()
    idx = _cc_index()
    try:
        if not lib.packages():
            lib.scan()
        rep = CB.usage_report(lib, sub, ids, idx, played_household=played, skip=F.is_speedkit_file,
                              side=_SideLookup(idx))
        state = idx.state()
    finally:
        idx.close()
        lib.close()
    files = []
    for f in rep['files']:
        view = _cc_view(f['item'])
        files.append({'name': f['name'], 'folder': f['folder'], 'in_mods': f['root'] == 'Mods', 'item': view,
                      'category_label': view['category_label'] if view else None,
                      'parts': f['parts'], 'objects': f['objects'], 'looks': f['looks'],
                      'pic': ({'kind': 'cas', 'id': f['first_part']} if f['first_part'] else
                              {'kind': 'object', 'id': f['first_object']} if f['first_object'] else None),
                      'sims': f['sims'], 'sims_count': f['sims_count']})
    missing = [dict(m, what=CC_MISSING_KINDS.get(m['kind'], 'CC'),
                    found=[{'place': x['place'], 'name': x['name'], 'creator': x['creator']} for x in m['found']])
               for m in rep['missing']]
    return {'ok': True, 'slot': slot, 'name': name or slot, 'household': household, 'counts': rep['counts'],
            'files': files, 'households': rep['households'], 'missing': missing, 'index': state,
            'message': '' if files or missing else 'This save uses no CC.'}


# ------------------------------------------------------------------------------------------ finding the game
def _volume_label(root):
    if os.name != 'nt':
        return ''
    import ctypes
    buf = ctypes.create_unicode_buffer(261)
    try:
        if ctypes.windll.kernel32.GetVolumeInformationW(root, buf, 261, None, None, None, None, 0):
            return buf.value
    except Exception:
        pass
    return ''


def _hint(path, name):
    low = name.lower()
    if G.is_game_folder(path):
        return 'Looks like The Sims 4'
    if low == 'steamapps' or (low == 'common' and os.path.basename(os.path.dirname(path)).lower() == 'steamapps'):
        return 'Steam library'
    if low in ('steamlibrary', 'steam'):
        return 'Steam'
    if low in ('ea games', 'origin games', 'ea app'):
        return 'EA games folder'
    if 'sims 4' in low or 'sims4' in low:
        return 'Might be The Sims 4'
    return None


def _hidden(entry):
    if entry.name.startswith(('$', '.')) or entry.name.lower() in ('system volume information', 'recovery',
                                                                   'windows', 'config.msi', 'msocache'):
        return True
    try:
        attrs = entry.stat(follow_symlinks=False).st_file_attributes
        return bool(attrs & 0x2 or attrs & 0x4)       # FILE_ATTRIBUTE_HIDDEN / SYSTEM
    except (OSError, AttributeError):
        return False


def _drives(drive_list=None):
    out = []
    for d in (drive_list if drive_list is not None else G.fixed_drives()):
        try:
            free = round(shutil.disk_usage(d).free / 2 ** 30, 1)
        except OSError:
            continue
        out.append({'name': d.rstrip('\\/'), 'label': _volume_label(d), 'free_gb': free})
    return out


@_safe
def browse(path=None):
    """One level of the in-app folder browser. path None = 'This PC' (the fixed drives). Returns {'ok',
    'message', 'path', 'parent', 'drives', 'entries': [{'name', 'path', 'is_game', 'hint'}], 'is_game' (this
    folder), 'suggestions' (installs found automatically)}. Folders only, hidden/system ones left out,
    folders that cannot be read skipped."""
    clues = _cfg['game_clues']
    drive_list = clues.drives() if clues is not None else None
    drives = _drives(drive_list)

    def suggestions():
        return [{'name': g['game_dir'], 'path': g['game_dir'], 'exe': g['exe'], 'source': g['source'],
                 'is_game': True, 'hint': 'Found automatically (%s)' % g['source']}
                for g in G.search(clues, skip_remembered=True, sims=_sims(), home=_home(), first_only=False)]
    sug = _cached(('browse_suggestions', id(clues)), 60, suggestions)
    if not path:
        entries = [{'name': ('%s %s' % (d['name'], ('(%s)' % d['label']) if d['label'] else '')).strip(),
                    'path': d['name'] + '\\', 'is_game': False, 'hint': '%.0f GB free' % d['free_gb']} for d in drives]
        return {'ok': True, 'message': 'This PC', 'path': None, 'parent': None, 'drives': drives, 'entries': entries,
                'is_game': False, 'suggestions': sug}
    p = os.path.abspath(path)
    if not os.path.isdir(p):
        return {'ok': False, 'message': 'That folder does not exist.', 'path': p, 'parent': None, 'drives': drives,
                'entries': [], 'is_game': False, 'suggestions': sug}
    entries = []
    try:
        with os.scandir(p) as it:
            items = list(it)
    except OSError:
        return {'ok': False, 'message': 'That folder cannot be opened (no access).', 'path': p,
                'parent': _parent(p), 'drives': drives, 'entries': [], 'is_game': False, 'suggestions': sug}
    for e in items:
        try:
            if not e.is_dir(follow_symlinks=False) or _hidden(e):
                continue
            with os.scandir(e.path):                   # can we open it at all?
                pass
        except OSError:
            continue
        entries.append({'name': e.name, 'path': e.path, 'is_game': G.is_game_folder(e.path), 'hint': _hint(e.path, e.name)})
    entries.sort(key=lambda x: x['name'].lower())
    here = G.is_game_folder(p)
    return {'ok': True, 'message': 'This is The Sims 4.' if here else '%d folders' % len(entries), 'path': p,
            'parent': _parent(p), 'drives': drives, 'entries': entries, 'is_game': here, 'suggestions': sug}


def _parent(p):
    par = os.path.dirname(p.rstrip('\\/'))
    if not par or par == p or os.path.splitdrive(p)[1] in ('\\', '/', ''):
        return None
    return par if os.path.splitdrive(par)[1] else par + '\\'


@_safe
def set_game_path(path):
    """Remember the user's choice of the game folder for good (any of: the game folder, its Game or Bin
    folder, a folder with TS4_x64.exe, the exe). Returns {'ok', 'message', 'exe', 'game_dir'}."""
    r = G.set_game_path(path, _sims(), _home())
    _cache.clear()
    return r


def choose_game_folder():
    """Kept for older app builds: the Hub now draws its own folder browser (browse / set_game_path)."""
    return {'ok': False, 'message': "Use the folder browser: browse() and set_game_path().", 'exe': None,
            'game_dir': None}


# ------------------------------------------------------------------------------------------ patch day, game errors,
# save backups, load-time savings: speedkit/api_care.py (docs\care.md) - imported last, it uses the helpers above
from .api_care import (patch_day, patch_seen, set_aside, put_back, game_errors, errors_seen,  # noqa: E402,F401
                       save_health, backup_saves, restore_saves, load_savings,
                       batch_fixes, batch_fix_scan, batch_fix_open)
