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
"""
import datetime
import json
import os

from . import api as A
from . import patchday as PD
from . import errorlogs as EL
from . import savebackup as SB
from . import loadstats as LS
from . import profiles as PR
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
               ('%d script mod%s older than the update. An older file does not prove a mod is broken, but these are the '
                'first ones to check. They can be set aside until they are updated.' % (n, ' is' if n == 1 else 's are'))
               if n else 'All script mods are newer than the update.'))
    else:
        msg = ('%d script mod%s older than the latest game update.' % (n, ' is' if n == 1 else 's are')) if n else \
            'All script mods are newer than the latest game update.'
    game = dict(info, update_time=when)
    game.pop('fingerprint', None)
    return {'ok': True, 'game': game, 'older': lists['older'], 'newer': lists['newer'], 'set_aside': held,
            'message': msg}


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


# ------------------------------------------------------------------------------------------ for api.py's undo
KINDS = ('aside', 'saves')


def title(j):
    note = (j.get('note') or '').lower()
    if j['kind'] == 'aside':
        return 'Put mods back' if note.startswith('put back') else 'Set mods aside until they are updated'
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
