r"""The Hub's buttons for patch day, game errors, save backups and load-time savings (docs\care.md).

speedkit/api.py re-exports every public function here, so the app calls them as api.<name> like the others; they
follow the same rules (docs\hub_contract.md): safe from a background thread, {'ok': False, 'message': <plain>}
instead of raising, progress(step, fraction, message), plain words only. They use api's configuration
(api.configure(sims=..., check_game=...)), so tests point them at a fake Sims 4 folder the same way.

    patch_day()                    what changed since the game was last updated, and the mods set aside
    patch_seen()                   the player has seen the patch-day notice
    set_aside(rels, why='patch')   set mod files aside until they are updated (backs up the saves first on patch day)
    put_back(rels)                 bring set-aside mods back
    game_errors()                  the game's error reports, grouped, with the mod behind each one
    errors_seen()                  hide the errors seen so far (they stay listed as older ones)
    save_health()                  each save's size and growth, plus the save backups
    backup_saves()                 back up the saves now
    restore_saves(backup)          put the saves of one backup back (undoable)
    load_savings()                 load time per mode and the time Quick Start saves
    batch_fixes()                  CC that may need a Sims 4 Studio batch fix (from the last check; docs\batchfix.md)
    batch_fix_scan()               check the CC files for them (a task: new or changed files only)
    batch_fix_open(rel)            open the folder of one file the check listed
"""
import datetime
import json
import os
import time

from . import api as A
from . import patchday as PD
from . import errorlogs as EL
from . import savebackup as SB
from . import loadstats as LS
from . import profiles as PR
from . import batchfix as BF
from .journal import JournalError

KEEP_BACKUPS = 5
CARE = 'care.json'                  # SpeedKit\care.json: small choices of these pages (errors seen until...)


def _home():
    return A._home()


def _backup_root():
    return SB.default_root(A._sims(), _home())


def _read_care():
    try:
        with open(os.path.join(_home(), CARE), encoding='utf-8') as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_care(doc):
    p = os.path.join(_home(), CARE)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(doc, f, indent=1)
    os.replace(p + '.tmp', p)


def _game_dir():
    try:
        g = A._game()
        return g['game_dir'] if g else None
    except Exception:
        return None


def _date(ts):
    if not ts:
        return None
    return datetime.datetime.fromtimestamp(ts).isoformat(timespec='seconds')


# ------------------------------------------------------------------------------------------ patch day
@A._safe
def patch_day():
    """{'ok', 'game': {'version', 'previous', 'updated', 'first_look', 'update_time' (iso), 'noticed'},
    'older': [{'mod', 'rel', 'date', 'days_before', 'size_mb', 'goes_with': [rels]}], 'newer': int,
    'set_aside': [{'rel', 'mod', 'since', 'why', 'date', 'state', 'script'}], 'message'}. Read-only apart from
    remembering the game's version (SpeedKit\\game_version.json)."""
    info = PD.check(A._sims(), _home(), _game_dir())
    ut = info.get('update_time')
    lists = PD.older_scripts(A._sims(), ut) if ut else {'older': [], 'newer': 0}
    held = [h for h in PD.held_status(A._sims(), _home()) if h['state'] in ('aside', 'updated')]
    n = len(lists['older'])
    when = _date(ut)
    if not ut:
        msg = 'The date of the last game update is not known yet. Game updates are tracked from now on.'
    elif info['updated']:
        msg = ('The Sims 4 was updated%s. %s' % (' to %s' % info['version'] if info.get('version') else '',
               ('%d script mod%s older than the update. Check these first.' % (n, ' is' if n == 1 else 's are'))
               if n else 'All script mods are newer than the update.'))
    else:
        msg = ('%d script mod%s older than the latest game update.' % (n, ' is' if n == 1 else 's are')) if n else \
            'All script mods are newer than the latest game update.'
    game = dict(info, update_time=when)
    game.pop('fingerprint', None)
    return {'ok': True, 'game': game, 'older': lists['older'], 'newer': lists['newer'], 'set_aside': held,
            'message': msg, 'batch_fixes': _batch_summary()}


@A._safe
def patch_seen():
    PD.acknowledge(A._sims(), _home())
    return {'ok': True, 'message': 'Notice dismissed.'}


def _backup_first(tell, reason):
    """Back up the saves before a patch-day change. Returns a plain line for the steps (never raises)."""
    try:
        tell('backup', None, 'Backing up your saves first')
        r = SB.backup(A._saves(), _backup_root(), reason=reason, keep=KEEP_BACKUPS, game_running=A._game_running,
                      protect=SB.protected(_home()))
        return True, 'Saves backed up first (%d save%s).' % (r['files'], '' if r['files'] == 1 else 's')
    except SB.BackupError as e:
        return False, 'The saves could not be backed up first: %s' % e
    except Exception as e:
        A._log_error('backup before set aside', e)
        return False, 'The saves could not be backed up first (%s).' % A._plain(e)


def _names(rels):
    names = sorted({PD.mod_name(r) for r in rels}, key=str.lower)
    return ', '.join(names[:4]) + (' and %d more' % (len(names) - 4) if len(names) > 4 else '')


@A._safe
def set_aside(rels, why='patch', progress=None):
    """Set these mod files (paths relative to Mods, as patch_day/game_errors give them) aside until they are
    updated. A script's companion files go with it. On patch day the saves are backed up first. Refuses while
    the game runs. Returns {'ok', 'message', 'moved': [rels], 'skipped': [{'rel', 'why'}], 'journal', 'steps'}."""
    tell = A._Progress(progress)
    if isinstance(rels, str):
        rels = [rels]
    if A._game_running():
        return {'ok': False, 'message': 'The Sims 4 is running. Close it first, then try again.', 'moved': [],
                'skipped': [], 'journal': None}
    steps = []
    if why == 'patch':
        ok, line = _backup_first(tell, 'before setting mods aside')
        steps.append({'step': 'backup', 'ok': True, 'message': line, 'warn': not ok})
    tell('aside', None, 'Setting the mods aside')
    try:
        with A._run_lock:
            info = PD.check(A._sims(), _home(), _game_dir(), remember=False)
            r = PD.set_aside(rels, sims=A._sims(), home=_home(), check_game=A._cfg['check_game'], why=why,
                             game_version=info.get('version'))
    except (PD.PatchError, PR.ProfileError, JournalError) as e:
        return {'ok': False, 'message': A._plain(e), 'moved': [], 'skipped': [], 'journal': None, 'steps': steps}
    A._cache.clear()
    n = len(r['moved'])
    msg = 'Set aside: %s (%d file%s). They can be put back on the Tools page.' % (
        _names(r['moved']), n, '' if n == 1 else 's')
    if r['skipped']:
        msg += ' %d stayed where they are.' % len(r['skipped'])
    steps.append({'step': 'aside', 'ok': True, 'message': msg, 'warn': False})
    for s in r['skipped']:
        steps.append({'step': 'aside', 'ok': True, 'message': '%s: %s' % (s['rel'], s['why']), 'warn': True})
    return {'ok': True, 'message': msg, 'moved': r['moved'], 'skipped': r['skipped'], 'journal': r['journal'],
            'steps': steps}


@A._safe
def put_back(rels, progress=None):
    """Bring set-aside mods back into Mods. Returns {'ok', 'message', 'moved', 'skipped', 'journal'}."""
    tell = A._Progress(progress)
    if isinstance(rels, str):
        rels = [rels]
    if A._game_running():
        return {'ok': False, 'message': 'The Sims 4 is running. Close it first, then try again.', 'moved': [],
                'skipped': [], 'journal': None}
    tell('back', None, 'Putting the mods back')
    try:
        with A._run_lock:
            r = PD.put_back(rels, sims=A._sims(), home=_home(), check_game=A._cfg['check_game'])
    except (PD.PatchError, PR.ProfileError, JournalError) as e:
        return {'ok': False, 'message': A._plain(e), 'moved': [], 'skipped': [], 'journal': None}
    A._cache.clear()
    msg = 'Put back: %s.' % _names(r['moved'])
    if r['skipped']:
        msg += ' ' + ' '.join(s['why'] for s in r['skipped'][:2])
    return {'ok': True, 'message': msg, 'moved': r['moved'], 'skipped': r['skipped'], 'journal': r['journal']}


# ------------------------------------------------------------------------------------------ game errors
@A._safe
def game_errors():
    """{'ok', 'errors': [{'id', 'kind': 'script'|'ui'|'other', 'error', 'mod': {'name', 'file', 'rel', 'root',
    'script', 'can_set_aside'}|None, 'how': 'named'|'mentioned'|None, 'also', 'count', 'first', 'last', 'files',
    'details', 'new', 'set_aside'}], 'files', 'unreadable', 'message'}. Read-only."""
    seen = _read_care().get('errors_seen_until')
    rep = EL.scan(A._sims(), seen_until=seen)
    held = {h['rel'].lower() for h in PD.held_status(A._sims(), _home()) if h['state'] in ('aside', 'updated')}
    for g in rep['errors']:
        m = g.get('mod')
        g['set_aside'] = bool(m and m['rel'].lower() in held)
        if m and m['root'] != 'Mods':
            m['can_set_aside'] = False
    new = [g for g in rep['errors'] if g['new']]
    named = [g for g in new if g.get('mod')]
    if not rep['files']:
        msg = 'No error reports found.'
    elif not rep['errors']:
        msg = 'The game wrote error reports, but they hold no errors.'
    elif not new:
        msg = 'No new errors since the last review.'
    else:
        msg = '%d kind%s of error%s' % (len(new), '' if len(new) == 1 else 's', '' if len(new) == 1 else 's') + \
              (', %d pointing at a mod.' % len(named) if named else '. None of them names a mod.')
    return dict(rep, ok=True, message=msg, seen_until=seen)


@A._safe
def errors_seen():
    doc = _read_care()
    doc['errors_seen_until'] = datetime.datetime.now().isoformat(timespec='seconds')
    _write_care(doc)
    return {'ok': True, 'message': 'The errors so far are marked as seen.'}


# ------------------------------------------------------------------------------------------ saves
@A._safe
def save_health():
    """{'ok', 'saves': [{'file', 'slot', 'name', 'size_mb', 'last_played', 'history', 'growth_mb', 'growth_days',
    'level', 'note'}], 'backups': [{'id', 'when', 'reason', 'files', 'bytes', 'saves', 'complete'}],
    'backup_folder', 'keep', 'free_gb', 'message'}. Records each save's size (once a day) - never opens a save
    for writing."""
    saves = SB.health(A._saves(), os.path.join(_home(), 'save_sizes.json'))
    backups = SB.list_backups(_backup_root())
    free = SB._free(_backup_root())
    warn = [s for s in saves if s['level'] != 'ok']
    msg = ('%d save%s large or growing quickly.' % (len(warn), ' is' if len(warn) == 1 else 's are')) if warn else \
        ('No size warnings.' if saves else 'No saves yet.')
    return {'ok': True, 'saves': saves, 'backups': backups, 'backup_folder': _backup_root(), 'keep': KEEP_BACKUPS,
            'free_gb': round(free / 1e9, 1) if free is not None else None, 'message': msg}


@A._safe
def backup_saves(progress=None):
    """Back up every save now. Returns {'ok', 'message', 'backup', 'files', 'bytes'}."""
    tell = A._Progress(progress)
    tell('backup', 0.0, 'Backing up your saves')
    try:
        info = PD.check(A._sims(), _home(), _game_dir(), remember=False)
        r = SB.backup(A._saves(), _backup_root(), reason='by hand', keep=KEEP_BACKUPS, game_running=A._game_running,
                      game_version=info.get('version'), protect=SB.protected(_home()), progress=tell)
    except SB.BackupError as e:
        return {'ok': False, 'message': str(e), 'backup': None}
    tell('backup', 1.0, 'Done')
    return {'ok': True, 'message': 'Backed up %d save%s (%s). The newest %d backups are kept.' % (
        r['files'], '' if r['files'] == 1 else 's', A._size_text(r['bytes']), KEEP_BACKUPS),
        'backup': r['id'], 'files': r['files'], 'bytes': r['bytes']}


@A._safe
def restore_saves(backup, progress=None):
    """Put the saves of one backup back (the game must be closed). The saves as they are now are backed up first,
    and 'Undo last change' puts them back. Returns {'ok', 'message', 'journal', 'restored', 'left'}."""
    tell = A._Progress(progress)
    try:
        info = PD.check(A._sims(), _home(), _game_dir(), remember=False)
        with A._run_lock:
            r = SB.restore(backup, A._saves(), _backup_root(), _home(), A._sims(), game_running=A._game_running,
                           keep=KEEP_BACKUPS, protect=SB.protected(_home()), game_version=info.get('version'),
                           progress=tell)
    except (SB.BackupError, JournalError) as e:
        return {'ok': False, 'message': A._plain(e), 'journal': None}
    A._cache.clear()
    n = len(r['restored'])
    msg = 'Restored %d save%s from the backup. The previous saves were backed up first' % (n, '' if n == 1 else 's')
    msg += '; "Undo last change" on the Tools page restores them.'
    if r['left']:
        msg += ' %d newer save%s not changed.' % (len(r['left']), ' was' if len(r['left']) == 1 else 's were')
    return {'ok': True, 'message': msg, 'journal': r['journal'], 'restored': r['restored'], 'left': r['left']}


# ------------------------------------------------------------------------------------------ load times
@A._safe
def load_savings():
    """{'ok', 'modes': {'fast'|'save'|'full'|'studio'|'other': {'starts', 'menu_s', 'lot_s', 'total_s', 'last'}},
    'compare', 'saved_s', 'saved_total_s', 'confidence': 'none'|'one_mode'|'low'|'ok', 'starts', 'message'}."""
    return LS.summary(os.path.join(A._reports(), 'loadtimes.csv'))


# ------------------------------------------------------------------------------------------ Sims 4 Studio batch fixes
FIX_FILES_SHOWN = 200               # files listed per fix (the count is always the full one)


def _bf_path():
    return os.path.join(os.path.dirname(os.path.abspath(A._cfg['db_path'])), 'batchfix.sqlite')


def _bf_state():
    """(state, findings) of the last check, or (None, {}) when there was none. Reads only the results file."""
    if not os.path.isfile(_bf_path()):
        return None, {}
    st = BF.Store(_bf_path())
    try:
        return st.state(), st.findings()
    finally:
        st.close()


def _bf_files(findings):
    """findings with each file where it is now (Mods, or parked / set aside), files that are gone left out."""
    held = {h['rel'].lower() for h in PD.held_status(A._sims(), _home()) if h['state'] == 'aside'}
    roots = A._roots()
    where = {}
    out = {}
    for fid, files in findings.items():
        keep = []
        for f in files:
            k = f['rel'].lower()
            if k not in where:
                where[k] = next((r for r in ('Mods', 'Mods_parked')
                                 if os.path.isfile(os.path.join(roots[r], f['rel'].replace('/', os.sep)))), None)
            if where[k] is None:
                continue
            keep.append(dict(f, root=where[k], set_aside=k in held))
        if keep:
            out[fid] = keep
    return out


def _batch_summary():
    """For the patch-day notice: {'files', 'fixes': [{'id', 'name', 'files'}], 'scanned'} or None (never checked)."""
    try:
        state, found = _bf_state()
    except Exception as e:
        A._log_error('batch summary', e)
        return None
    if not state or not state.get('scanned'):
        return None
    found = _bf_files(found)
    files = {f['rel'].lower() for fs in found.values() for f in fs if not f['set_aside']}
    fixes = [{'id': fx['id'], 'name': fx['name'], 'files': sum(1 for f in found.get(fx['id'], []) if not f['set_aside'])}
             for fx in BF.FIXES]
    return {'files': len(files), 'fixes': [f for f in fixes if f['files']], 'scanned': state['scanned']}


@A._safe
def batch_fixes():
    """{'ok', 'scanned': iso|None, 'files_checked', 'files' (CC files that may need a fix), 'fixes': [{'id', 'name',
    'menu': [str], 'section', 'update', 'problem', 'what', 'count', 'in_mods', 'set_aside', 'files': [{'rel', 'name',
    'folder', 'root', 'in_mods', 'set_aside', 'why', 'parts'}], 'more', 'sources'}], 'parked', 'message'}.
    From the last check only (batch_fix_scan); never opens a CC file and never changes one."""
    state, found = _bf_state()
    if not state or not state.get('scanned'):
        return {'ok': True, 'scanned': None, 'files_checked': 0, 'files': 0, 'fixes': [], 'parked': 0,
                'message': 'Your CC has not been checked yet. The first check reads every CC file and can take a few '
                           'minutes for a big collection.'}
    found = _bf_files(found)
    fixes, all_files, parked = [], set(), 0
    for fx in BF.FIXES:
        files = found.get(fx['id'])
        if not files:
            continue
        view = []
        for f in files:
            parts = f['rel'].split('/')
            view.append({'rel': f['rel'], 'name': parts[-1], 'folder': '/'.join(parts[:-1]), 'root': f['root'],
                         'in_mods': f['root'] == 'Mods', 'set_aside': f['set_aside'], 'parts': f.get('parts', 1),
                         'why': BF.why(fx['id'], f)})
            all_files.add(f['rel'].lower())
        n_parked = sum(1 for f in view if not f['in_mods'] and not f['set_aside'])
        parked += n_parked
        fixes.append({'id': fx['id'], 'name': fx['name'], 'menu': list(fx['menu']), 'section': fx['section'],
                      'update': fx['update'], 'problem': fx['problem'], 'what': fx['what'], 'count': len(view),
                      'in_mods': sum(1 for f in view if f['in_mods']), 'set_aside': sum(1 for f in view if f['set_aside']),
                      'parked': n_parked, 'files': view[:FIX_FILES_SHOWN], 'more': max(0, len(view) - FIX_FILES_SHOWN),
                      'sources': list(fx['sources'])})
    n = len(all_files)
    if not fixes:
        msg = 'No CC matches a problem that a Sims 4 Studio batch fix is known for.'
    else:
        msg = '%d CC file%s may need a Sims 4 Studio batch fix (%d fix%s).' % (
            n, '' if n == 1 else 's', len(fixes), '' if len(fixes) == 1 else 'es')
    return {'ok': True, 'scanned': state['scanned'], 'files_checked': state['files'], 'files': n, 'fixes': fixes,
            'parked': parked, 'message': msg}


@A._safe
def batch_fix_scan(progress=None):
    """Check every CC file for problems that a Sims 4 Studio batch fix is known for (read-only; new or changed files
    only after the first time). Returns {'ok', 'message', 'files', 'found', 'read', 'seconds'}."""
    from . import fastmode as F
    tell = A._Progress(progress)
    t0 = time.time()
    with A._run_lock:
        tell('library', 0.0, 'Looking for new or changed CC files')
        lib = A._library()
        st = BF.Store(_bf_path())
        try:
            lib.scan()

            def sub(step, fraction=None, message=''):
                tell(step, None if fraction is None else round(0.1 + 0.9 * fraction, 3), message)
            res = st.scan(lib, progress=sub, skip=F.is_speedkit_file)
        finally:
            st.close()
            lib.close()
    r = batch_fixes()
    n = r.get('files', 0)
    tell('done', 1.0, 'Checked %s CC files' % format(res['files'], ','))
    msg = 'Checked %s CC files. ' % format(res['files'], ',') + (
        '%d may need a Sims 4 Studio batch fix.' % n if n else 'None of them matches a known Sims 4 Studio fix.')
    return {'ok': True, 'message': msg, 'files': res['files'], 'found': n, 'read': res['read'],
            'seconds': round(time.time() - t0, 1)}


@A._safe
def batch_fix_open(rel):
    """Open the folder of one file that the last check listed (in Mods or, when parked, its set-aside place)."""
    if not isinstance(rel, str) or not rel.strip():
        return {'ok': False, 'message': 'Pick a file first.'}
    key = rel.replace('\\', '/').strip('/').lower()
    _, found = _bf_state()
    hit = next((f for fs in _bf_files(found).values() for f in fs if f['rel'].lower() == key), None)
    if hit is None:
        return {'ok': False, 'message': 'That file is not in the list any more. Check again.'}
    path = os.path.join(A._roots()[hit['root']], hit['rel'].replace('/', os.sep))
    if A._cfg['opener'] is None and os.name == 'nt':
        import subprocess
        subprocess.Popen(['explorer', '/select,', path], creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    else:
        A._open(os.path.dirname(path))
    return {'ok': True, 'message': 'Opened the folder of %s.' % os.path.basename(path), 'path': os.path.dirname(path)}


# ------------------------------------------------------------------------------------------ for api.py's undo
KINDS = ('aside', 'saves')


def title(j):
    note = (j.get('note') or '').lower()
    if j['kind'] == 'aside':
        if note.startswith('put back'):
            return 'Put mods back'
        return 'Set CC aside until it gets a Sims 4 Studio fix' if '(fix)' in note else 'Set mods aside until they are updated'
    return 'Put back saves from a backup'


def undo(j, dry_run, check_game):
    """Undo one 'aside' or 'saves' change (dry_run: only check it could be undone now)."""
    if j['kind'] == 'aside':
        return PD.undo(j['id'], sims=A._sims(), home=j.get('_home') or _home(), check_game=check_game,
                       dry_run=dry_run)
    try:
        return SB.undo_restore(j['id'], j.get('_home') or _home(), game_running=A._game_running if check_game else None,
                               dry_run=dry_run)
    except SB.BackupError as e:
        raise JournalError(str(e))
