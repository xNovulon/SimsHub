r"""Save backups and save health. The contents of a save are never changed - only whole files are copied.

    b = backup(saves_dir, root, reason='by hand')       # {'id', 'files', 'bytes', 'pruned'}
    list_backups(root)                                   # newest first
    r = restore(b['id'], saves_dir, root, home, sims)    # one-click restore (a 'saves' journal records it)
    undo_restore(r['journal'], saves_dir, root, home)    # what "Undo last change" runs for it
    health(saves_dir, history_path)                      # size, growth over time, gentle warnings

Backups: <root>\<id>\ holds a copy of every Slot_XXXXXXXX.save directly in saves\ (the game's own .ver files are
older copies of the same saves and are left out; sub-folders such as saves\FitStudio are not saves) plus
backup.json {'id', 'when', 'reason', 'game_version', 'files': [{'name', 'size', 'mtime', 'save_name'}]}. A backup
is written into <id>.partial and renamed when every copy has the right size, so a half-made backup never looks
finished. A file unchanged since the newest backup (same size and time) is hard-linked to it when the drive
allows (no extra space). root defaults to <Sims 4>\SpeedKit\save_backups: the game never reads that folder.
Only the newest `keep` backups stay; older ones (the Hub's own extra copies) are removed, except a backup an
undoable restore still needs. Refuses while the game runs (a save could be half-written).

Restore (the game must be closed): first a full backup of the saves as they are now ('before restore'); then each
file of the chosen backup is copied next to its place (<name>.hubrestore), checked, and swapped in with
os.replace. Saves that are not in the backup are left alone. A kind 'saves' journal in SpeedKit\journal records
which backup, the 'before' backup and the files written, so the Hub's undo can put the saves back as they were
- unless one of the restored saves changed since (you played), then it refuses and says so.
"""
import datetime
import json
import os
import re
import shutil
import time

from .library import SIMS

BACKUP_JSON = 'backup.json'
ID_RX = re.compile(r'^\d{8}-\d{6}(-\d{1,3})?$')
SLOT_RX = re.compile(r'^Slot_[0-9A-Fa-f]{8}\.save$')
KEEP = 5
BIG_MB, VERY_BIG_MB = 150, 250
GROW_PCT, GROW_MB, GROW_DAYS = 25, 15, 30
HISTORY_POINTS = 180


class BackupError(Exception):
    """Refused or failed, with a plain message."""


def _iso(t):
    return datetime.datetime.fromtimestamp(t).isoformat(timespec='seconds') if t else None


def default_root(sims=SIMS, home=None):
    return os.path.join(home or os.path.join(sims, 'SpeedKit'), 'save_backups')


def save_files(saves_dir):
    """[(name, path, stat)] of the current save slots (Slot_XXXXXXXX.save directly in saves\\)."""
    out = []
    try:
        names = sorted(os.listdir(saves_dir))
    except OSError:
        return out
    for n in names:
        p = os.path.join(saves_dir, n)
        if SLOT_RX.match(n) and os.path.isfile(p):
            try:
                out.append((n, p, os.stat(p)))
            except OSError:
                continue
    return out


def _save_name(path):
    try:
        from .savepacks import read_header
        return read_header(path).get('name')
    except Exception:
        return None


def _read_meta(folder):
    try:
        with open(os.path.join(folder, BACKUP_JSON), encoding='utf-8') as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def _id_order(name):
    """Sort key of a backup id: its second, then its number within that second ('-2', '-10')."""
    m = ID_RX.match(name)
    if not m:
        return (name, 0)
    return (name[:15], int(m.group(1)[1:]) if m.group(1) else 1)


def list_backups(root):
    """Finished backups, newest first: [{'id', 'when', 'reason', 'files', 'bytes', 'saves': [{'name', 'save_name',
    'size'}], 'complete'}]. complete: every file is there with its size."""
    out = []
    try:
        names = sorted(os.listdir(root), key=_id_order, reverse=True)
    except OSError:
        return out
    for n in names:
        folder = os.path.join(root, n)
        if not ID_RX.match(n) or not os.path.isdir(folder):
            continue
        meta = _read_meta(folder)
        if not meta:
            continue
        files = meta.get('files') or []
        complete = True
        for f in files:
            try:
                if os.path.getsize(os.path.join(folder, f['name'])) != f['size']:
                    complete = False
            except (OSError, KeyError, TypeError):
                complete = False
        out.append({'id': n, 'when': meta.get('when'), 'reason': meta.get('reason') or '', 'files': len(files),
                    'bytes': sum(int(f.get('size') or 0) for f in files), 'game_version': meta.get('game_version'),
                    'saves': [{'name': f.get('name'), 'save_name': f.get('save_name'), 'size': f.get('size')}
                              for f in files], 'complete': complete})
    return out


def _free(path):
    p = path
    while p and not os.path.exists(p):
        parent = os.path.dirname(p)
        if parent == p:
            break
        p = parent
    try:
        return shutil.disk_usage(p).free
    except OSError:
        return None


def _new_id(root):
    """A new id that sorts after every backup made in the same second (also ones pruned already)."""
    base = time.strftime('%Y%m%d-%H%M%S')
    top = 0
    try:
        for n in os.listdir(root):
            n = n[:-8] if n.endswith('.partial') else n
            if n[:15] == base and ID_RX.match(n):
                top = max(top, _id_order(n)[1])
    except OSError:
        pass
    last = _LAST_ID.get(root)
    if last and last[:15] == base:
        top = max(top, _id_order(last)[1])
    bid = base if top == 0 else '%s-%d' % (base, top + 1)
    _LAST_ID[root] = bid
    return bid


_LAST_ID = {}


def _copy_checked(src, dst):
    shutil.copy2(src, dst)
    if os.path.getsize(dst) != os.path.getsize(src):
        raise BackupError('The copy of %s came out incomplete.' % os.path.basename(src))


def backup(saves_dir, root, reason='by hand', keep=KEEP, game_running=None, game_version=None, protect=(),
           progress=None):
    """Copy every current save into a new backup folder. Returns {'id', 'files', 'bytes', 'pruned': [ids]}.
    game_running: callable -> bool (refuses when True). protect: backup ids pruning must keep."""
    if game_running is not None and game_running():
        raise BackupError('The Sims 4 is running. Close it first, so no save is copied while the game writes it.')
    files = save_files(saves_dir)
    if not files:
        raise BackupError('There are no saves to back up yet.')
    total = sum(st.st_size for _, _, st in files)
    free = _free(root)
    if free is not None and free < total * 1.05 + (200 << 20):
        raise BackupError('There is not enough free space for a backup (%.1f GB needed, %.1f GB free).'
                          % (total * 1.05 / 1e9 + 0.2, free / 1e9))
    os.makedirs(root, exist_ok=True)
    prev = list_backups(root)
    last = None
    for b in prev:
        if b['complete']:
            last = b
            break
    last_meta = {f['name']: f for f in (_read_meta(os.path.join(root, last['id'])) or {}).get('files', [])} if last else {}
    bid = _new_id(root)
    tmp = os.path.join(root, bid + '.partial')
    os.makedirs(tmp)
    meta_files = []
    try:
        for i, (name, path, st) in enumerate(files):
            if progress:
                progress('backup', i / len(files), 'Copying %s' % name)
            dst = os.path.join(tmp, name)
            old = last_meta.get(name)
            linked = False
            if old and old.get('size') == st.st_size and abs(float(old.get('mtime') or 0) - st.st_mtime) < 0.01:
                try:
                    os.link(os.path.join(root, last['id'], name), dst)
                    linked = os.path.getsize(dst) == st.st_size
                except (OSError, AttributeError):
                    linked = False
                if not linked and os.path.exists(dst):
                    os.remove(dst)
            if not linked:
                _copy_checked(path, dst)
            meta_files.append({'name': name, 'size': st.st_size, 'mtime': st.st_mtime,
                               'save_name': (old or {}).get('save_name') if linked else _save_name(path)})
        meta = {'id': bid, 'when': datetime.datetime.now().isoformat(timespec='seconds'), 'reason': reason,
                'game_version': game_version, 'files': meta_files}
        with open(os.path.join(tmp, BACKUP_JSON), 'w', encoding='utf-8') as f:
            json.dump(meta, f, indent=1)
        os.rename(tmp, os.path.join(root, bid))
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)            # our own half-made copy: nothing of the player's
        raise
    pruned = prune(root, keep, protect=set(protect) | {bid})
    return {'id': bid, 'files': len(meta_files), 'bytes': sum(f['size'] for f in meta_files), 'pruned': pruned}


def prune(root, keep=KEEP, protect=()):
    """Remove the Hub's own backups beyond the newest `keep` (never one in `protect`), and leftovers of backups
    that were never finished. Returns the ids removed."""
    removed = []
    try:
        names = os.listdir(root)
    except OSError:
        return removed
    for n in names:
        if n.endswith('.partial') and ID_RX.match(n[:-8]):
            p = os.path.join(root, n)
            try:
                if time.time() - os.path.getmtime(p) > 3600:       # not one being written right now
                    shutil.rmtree(p, ignore_errors=True)
            except OSError:
                pass
    kept = 0
    for b in list_backups(root):
        kept += 1
        if kept > keep and b['id'] not in protect:
            shutil.rmtree(os.path.join(root, b['id']), ignore_errors=True)
            removed.append(b['id'])
    return removed


# ------------------------------------------------------------------------------------------ restore
def _journal_path(home, jid):
    return os.path.join(home, 'journal', jid + '.json')


def _write_journal(home, jid, doc):
    path = _journal_path(home, jid)
    with open(path + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(doc, f, indent=1)
    os.replace(path + '.tmp', path)


def _put(src, saves_dir, name):
    """Copy src next to saves\\<name>, check it, then swap it in. Returns the new file's (size, mtime)."""
    dst = os.path.join(saves_dir, name)
    tmp = dst + '.hubrestore'
    shutil.copy2(src, tmp)
    if os.path.getsize(tmp) != os.path.getsize(src):
        os.remove(tmp)
        raise BackupError('The copy of %s came out incomplete; nothing more was changed.' % name)
    os.replace(tmp, dst)
    st = os.stat(dst)
    return st.st_size, st.st_mtime


def restore(backup_id, saves_dir, root, home, sims=SIMS, game_running=None, keep=KEEP, protect=(), game_version=None,
            progress=None):
    """Put the saves of one backup back. Returns {'journal', 'before', 'restored': [names], 'left': [names]}.
    Raises BackupError (plain message) when refused - nothing is changed then."""
    if not isinstance(backup_id, str) or not ID_RX.match(backup_id):
        raise BackupError('That backup is not known.')
    if game_running is not None and game_running():
        raise BackupError('The Sims 4 is running. Close it first, then try again.')
    folder = os.path.join(root, backup_id)
    meta = _read_meta(folder)
    if not meta:
        raise BackupError('That backup is not there any more.')
    files = [f for f in meta.get('files') or [] if isinstance(f, dict) and SLOT_RX.match(str(f.get('name') or ''))]
    for f in files:
        try:
            ok = os.path.getsize(os.path.join(folder, f['name'])) == f['size']
        except OSError:
            ok = False
        if not ok:
            raise BackupError('That backup is incomplete (%s is missing or damaged), so nothing was changed.' % f['name'])
    if not files:
        raise BackupError('That backup holds no saves.')
    os.makedirs(saves_dir, exist_ok=True)
    if progress:
        progress('backup', None, 'Backing up your saves as they are now')
    before = None
    if save_files(saves_dir):
        before = backup(saves_dir, root, reason='before restore', keep=keep, game_running=game_running,
                        game_version=game_version, protect=set(protect) | {backup_id})['id']
    from .journal import Journal
    # the record only (no journal steps: the journal never touches saves\); the game was checked above
    j = Journal('saves', 'restore saves from backup %s' % backup_id, home=home, sims=sims, check_game=False)
    j.close('open')
    written, done = [], []
    present = {n for n, _, _ in save_files(saves_dir)}
    try:
        for i, f in enumerate(files):
            if game_running is not None and game_running():
                raise BackupError('The Sims 4 was started during the restore.')
            if progress:
                progress('restore', i / len(files), 'Putting back %s' % (f.get('save_name') or f['name']))
            size, mtime = _put(os.path.join(folder, f['name']), saves_dir, f['name'])
            written.append({'name': f['name'], 'size': size, 'mtime': mtime, 'existed': f['name'] in present})
            done.append(f['name'])
    except BaseException as e:
        # put back what was already swapped, from the 'before' backup (or set aside a save that was not there)
        _roll_back(written, saves_dir, root, before, j.id)
        doc = _load_journal(home, j.id)
        doc.update({'state': 'rolled_back', 'error': str(e), 'backup': backup_id, 'before': before})
        _write_journal(home, j.id, doc)
        if not isinstance(e, Exception):
            raise
        raise BackupError('Restoring stopped (%s). Your saves were put back as they were.' % e)
    doc = _load_journal(home, j.id)
    doc.update({'state': 'committed', 'backup': backup_id, 'before': before, 'written': written,
                'backup_root': root, 'saves_dir': saves_dir})
    _write_journal(home, j.id, doc)
    left = sorted(present - set(done))
    return {'journal': j.id, 'before': before, 'restored': done, 'left': left}


def _load_journal(home, jid):
    with open(_journal_path(home, jid), encoding='utf-8') as f:
        return json.load(f)


def _roll_back(written, saves_dir, root, before, jid):
    before_dir = os.path.join(root, before) if before else None
    for w in reversed(written):
        name = w['name']
        src = os.path.join(before_dir, name) if before_dir else None
        if w.get('existed') and src and os.path.isfile(src):
            _put(src, saves_dir, name)
        elif not w.get('existed'):
            away = os.path.join(root, '%s-set-aside' % jid)
            os.makedirs(away, exist_ok=True)
            shutil.move(os.path.join(saves_dir, name), os.path.join(away, name))


def restore_refusal(jid, home):
    """None when the restore recorded in journal `jid` can be undone now, else the plain reason."""
    try:
        doc = _load_journal(home, jid)
    except (OSError, ValueError):
        return 'Its record cannot be read.'
    if doc.get('state') == 'undone':
        return 'It was already undone.'
    if doc.get('state') != 'committed':
        return 'It did not finish.'
    saves_dir, root, before = doc.get('saves_dir'), doc.get('backup_root'), doc.get('before')
    for w in doc.get('written') or []:
        p = os.path.join(saves_dir or '', w['name'])
        try:
            st = os.stat(p)
        except OSError:
            return 'The save %s is not there any more.' % w['name']
        if st.st_size != w['size'] or abs(st.st_mtime - w['mtime']) > 0.01:
            return ('You played since the saves were put back (%s changed). To go back anyway, put back the '
                    '"before restore" backup from the Saves page.' % w['name'])
        if w.get('existed'):
            meta = _read_meta(os.path.join(root or '', before or '')) if before else None
            if not meta or w['name'] not in {f.get('name') for f in meta.get('files') or []}:
                return 'The backup made just before the restore is missing.'
    return None


def undo_restore(jid, home, game_running=None, dry_run=False):
    """Undo a restore: the saves it wrote go back to how they were before it (from its 'before' backup); a save
    that was not there before is moved into the backups folder (never deleted). Raises BackupError."""
    if game_running is not None and not dry_run and game_running():
        raise BackupError('The Sims 4 is running. Close it first, then undo.')
    why = restore_refusal(jid, home)
    if why:
        raise BackupError(why)
    if dry_run:
        return []
    doc = _load_journal(home, jid)
    _roll_back(doc.get('written') or [], doc['saves_dir'], doc['backup_root'], doc.get('before'), jid)
    doc['state'] = 'undone'
    _write_journal(home, jid, doc)
    return [('restore', w['name']) for w in doc.get('written') or []]


def protected(home):
    """Backup ids an undoable restore still needs (its 'before' backup and the backup it put back)."""
    out = set()
    d = os.path.join(home, 'journal')
    try:
        names = os.listdir(d)
    except OSError:
        return out
    for n in names:
        if not n.endswith('-saves.json') and '-saves-' not in n:
            continue
        try:
            with open(os.path.join(d, n), encoding='utf-8') as f:
                doc = json.load(f)
        except (OSError, ValueError):
            continue
        if doc.get('kind') == 'saves' and doc.get('state') == 'committed':
            out.update(x for x in (doc.get('before'), doc.get('backup')) if x)
    return out


# ------------------------------------------------------------------------------------------ health
def _load_history(path):
    try:
        with open(path, encoding='utf-8') as f:
            d = json.load(f)
        return d if isinstance(d, dict) and isinstance(d.get('saves'), dict) else {'saves': {}}
    except (OSError, ValueError):
        return {'saves': {}}


def record_sizes(saves_dir, history_path, today=None):
    """Remember each save's size once per day (SpeedKit\\save_sizes.json {'saves': {name: [[date, bytes], ...]}}).
    Returns the history. Best effort: a history that cannot be written is still returned."""
    hist = _load_history(history_path)
    today = today or datetime.date.today().isoformat()
    changed = False
    for name, path, st in save_files(saves_dir):
        pts = hist['saves'].setdefault(name, [])
        if pts and pts[-1][0] == today:
            if pts[-1][1] != st.st_size:
                pts[-1][1] = st.st_size
                changed = True
        else:
            pts.append([today, st.st_size])
            changed = True
        del pts[:-HISTORY_POINTS]
    if changed:
        try:
            os.makedirs(os.path.dirname(history_path), exist_ok=True)
            with open(history_path + '.tmp', 'w', encoding='utf-8') as f:
                json.dump(hist, f, indent=1)
            os.replace(history_path + '.tmp', history_path)
        except OSError:
            pass
    return hist


def _growth(points, today):
    """(grown bytes, over days) against the oldest point in the last GROW_DAYS days (else the oldest one)."""
    if len(points) < 2:
        return None, None
    t = datetime.date.fromisoformat(today)
    base = None
    for d, b in points:
        try:
            age = (t - datetime.date.fromisoformat(d)).days
        except ValueError:
            continue
        if age <= GROW_DAYS:
            base = (d, b, age)
            break
    if base is None:
        d, b = points[0]
        try:
            base = (d, b, (t - datetime.date.fromisoformat(d)).days)
        except ValueError:
            return None, None
    if base[2] <= 0:
        return None, None
    return points[-1][1] - base[1], base[2]


def health(saves_dir, history_path, today=None, names=None):
    """Each save's size, its growth and a gentle note: [{'file', 'slot', 'name', 'size_mb', 'last_played',
    'history': [[date, mb]], 'growth_mb', 'growth_days', 'level': 'ok'|'big'|'very_big'|'growing', 'note'}].
    names: {file name: save name} when known (else read from the save's header)."""
    today = today or datetime.date.today().isoformat()
    hist = record_sizes(saves_dir, history_path, today)
    out = []
    for name, path, st in save_files(saves_dir):
        mb = st.st_size / 1e6
        pts = hist['saves'].get(name) or []
        grown, days = _growth(pts, today)
        gmb = round(grown / 1e6, 1) if grown is not None else None
        level, note = 'ok', None
        if mb >= VERY_BIG_MB:
            level = 'very_big'
            note = ('This save is very large (%d MB). Large saves take longer to load and can slow the game down. '
                    'Save contents are never changed.' % round(mb))
        elif mb >= BIG_MB:
            level = 'big'
            note = 'This save is getting large (%d MB), which is common for long-played saves.' % round(mb)
        if grown is not None and days and grown >= GROW_MB * 1e6 and grown >= (st.st_size - grown) * GROW_PCT / 100:
            if level == 'ok':
                level = 'growing'
            note = ((note + ' ') if note else '') + 'It grew %d MB in the last %d day%s.' % (
                round(grown / 1e6), days, '' if days == 1 else 's')
        slot = name[:-5]
        out.append({'file': name, 'slot': slot, 'name': (names or {}).get(name) or _save_name(path) or slot,
                    'size_mb': round(mb, 1), 'last_played': _iso(st.st_mtime),
                    'history': [[d, round(b / 1e6, 1)] for d, b in pts[-60:]], 'growth_mb': gmb, 'growth_days': days,
                    'level': level, 'note': note})
    out.sort(key=lambda s: s['last_played'] or '', reverse=True)
    return out
