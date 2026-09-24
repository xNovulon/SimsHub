"""Saved animations (projects) and progressions (chains of animations that play one after another).

A project is identified by its `uid` (kept when it is renamed). A progression is {id, name, author, steps: [uid],
repeat}: WickedWhims stage links are made from it at export - step N plays next after step N-1.

Every read and write of these files goes through one lock, so a list or a load never meets a save half way. Windows
also refuses to replace (or open) a file while something else has it open - the other copy of the app, a backup tool
or a virus scanner - so each file step is tried again for about two seconds before it gives up."""
import hashlib, json, os, re, shutil, sys, threading, time, uuid

import gamedata as G

# ANIMATOR_SAVES / WICKED_PROJECTS_DIR (tests only): keep this server's saves (and reference files) in another folder,
# so a test never touches the user's
ROOT = os.environ.get('ANIMATOR_SAVES') or os.environ.get('WICKED_PROJECTS_DIR') or os.path.join(G.SIMS_DIR, 'saves', 'FitStudio')
PROJECTS = os.path.join(ROOT, 'animator_projects')
PROGRESSIONS = os.path.join(ROOT, 'animator_progressions.json')
OLD = os.path.join(ROOT, 'animator_replaced')
RECOVERY = os.path.join(ROOT, 'animator_recovery.json')
EXPORTS_MAP = os.path.join(ROOT, 'animator_exports.json')     # uid -> the package name it was last sent to the game as
MY_POSES = os.path.join(ROOT, 'animator_my_poses.json')
REFS = os.path.join(ROOT, 'animator_refs')                     # reference pictures / videos, one folder per animation uid

_lock = threading.RLock()      # re-entrant: save() lists the folder, load() may look a name up in the list
_RESERVED = re.compile(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$', re.I)
# waits (seconds) between tries when Windows says a file is in use (WinError 5 / 32): about 2 s in all
_WAITS = (0.02, 0.05, 0.05, 0.1, 0.1, 0.1, 0.2, 0.2, 0.2, 0.3, 0.3, 0.3)


class NameTaken(Exception):
    """Another animation (a different uid) is already saved under this file name. `existing` describes it."""

    def __init__(self, existing):
        super().__init__('"%s" is a different animation saved under the same name.' % (existing.get('name') or existing.get('file')))
        self.existing = existing


def safe(name):
    """The file name for a project name. Letters of every alphabet are kept (an Arabic name stays Arabic); only
    characters Windows can't use in a file name, and leading/trailing dots and spaces, are dropped."""
    s = re.sub(r"[^\w \-().,'!&+]+", '', name or '')
    s = ' '.join(s.split()).strip(' .')[:80].strip(' .')
    if _RESERVED.match(s):
        s += '_'
    return s or 'untitled'


def _legacy_safe(name):
    """How older versions turned names into file names (only A-Z, 0-9, space, _ and -)."""
    return re.sub(r'[^A-Za-z0-9 _-]+', '', name or '').strip()[:80] or 'untitled'


def _retry(fn, *args):
    """fn(*args), tried again while Windows says the file is in use (PermissionError). The last error is raised."""
    for wait in _WAITS:
        try:
            return fn(*args)
        except PermissionError:
            time.sleep(wait)
    return fn(*args)


def _read_once(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def _read(path):
    """The JSON in a saved file. FileNotFoundError when it isn't there, ValueError when it isn't JSON; a file that
    is only in use for a moment is waited for."""
    return _retry(_read_once, path)


def _write(path, data):
    """Writes the whole file at once: a reader sees the old or the new content, never half of it. The temporary
    file is private to this process and thread, so two saves (or two copies of the app) never share it."""
    text = json.dumps(data)
    tmp = '%s.%d-%d.tmp' % (path, os.getpid(), threading.get_ident())
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            f.write(text)
        _retry(os.replace, tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _set_aside(path, tag=''):
    """Moves a saved file into animator_replaced (kept there, never deleted) under a name no kept copy has yet."""
    os.makedirs(OLD, exist_ok=True)
    stem = os.path.basename(path)[:-5] + ('.' + tag if tag else '') + '.%d' % int(time.time())
    dst, k = os.path.join(OLD, stem + '.json'), 2
    while os.path.exists(dst):
        dst = os.path.join(OLD, '%s-%d.json' % (stem, k))
        k += 1
    _retry(os.replace, path, dst)
    return dst


def _load(path, default):
    """A shared settings file (progressions, exports map, my poses): `default` only when there is no such file.

    A file that is there but can't be read is NEVER taken as empty - the next save would then write the empty list
    over everything in it. If it stays in use, the error is raised (the app says it could not load). If it is
    damaged (not JSON any more), it is kept in animator_replaced and the app starts that list afresh."""
    try:
        return _read(path)
    except FileNotFoundError:
        return default
    except ValueError:
        try:
            kept = _set_aside(path, 'damaged')
            print('Kept a damaged file as', kept, file=sys.stderr)
        except FileNotFoundError:
            pass
        return default


def _files():
    os.makedirs(PROJECTS, exist_ok=True)
    return [os.path.join(PROJECTS, fn) for fn in sorted(os.listdir(PROJECTS)) if fn.endswith('.json')]


def meta_of(d, path, mtime=None):
    sims = d.get('sims', [])
    return {
        'file': os.path.basename(path)[:-5], 'uid': d.get('uid'), 'name': d.get('name', ''), 'author': d.get('author', ''),
        'category': d.get('category', ''), 'tags': d.get('tags', []), 'locations': d.get('locations', []),
        'sims': len(sims), 'genders': [s.get('gender', 'BOTH') for s in sims], 'bodies': [s.get('frame', 'yf') for s in sims],
        'keys': sum(len(s.get('keys', [])) for s in sims), 'layers': sum(len(s.get('layers', [])) for s in sims),
        'length': d.get('length', 90), 'fps': d.get('fps', 30), 'has_thumb': bool(d.get('thumb')),
        'modified': os.path.getmtime(path) if mtime is None else mtime,
    }


# project file -> ((modified ns, size), its list entry): the list only reads the files that changed since last time
_metas = {}


def list_projects():
    """Every saved animation (newest first). Old files without a uid get one (written back once)."""
    with _lock:
        out, seen = [], {}
        for p in _files():
            try:
                st = os.stat(p)
            except FileNotFoundError:
                continue              # moved away just now (by the other copy of the app)
            sig = (st.st_mtime_ns, st.st_size)
            hit = _metas.get(p)
            if hit and hit[0] == sig:
                out.append(hit[1])
                seen[p] = hit
                continue
            try:
                d = _read(p)
            except FileNotFoundError:
                continue
            except (ValueError, OSError) as ex:
                # damaged, or kept open by another program for seconds: left alone (a save never overwrites it,
                # see _uid_at), and listed again as soon as it can be read
                print('Could not read the saved animation', p, '-', ex, file=sys.stderr)
                continue
            if not isinstance(d, dict):
                continue
            if not d.get('uid'):
                d['uid'] = 'a' + uuid.uuid4().hex[:12]
                try:
                    _write(p, d)
                    st = os.stat(p)
                    sig = (st.st_mtime_ns, st.st_size)
                except OSError:
                    sig = None        # read (and give it a uid) again next time
            m = meta_of(d, p, st.st_mtime)
            if sig:
                seen[p] = (sig, m)
            out.append(m)
        _metas.clear()
        _metas.update(seen)
    out.sort(key=lambda x: -x['modified'])
    return out


def by_uid():
    return {m['uid']: m for m in list_projects()}


def _plain(file):
    """A saved file name as the list gives it (no folders, no '..')."""
    return (bool(file) and file == os.path.basename(file) and not file.startswith('.') and not file.endswith((' ', '.'))
            and not re.search(r'[\\/:*?"<>|\x00-\x1f]', file) and not _RESERVED.match(file.split('.')[0]))


def _path_of(file, by_name=False):
    """The saved file for `file` (a name from the list, or older clients' cleaned-up names). With by_name, a
    project whose animation name is `file` is also found (the Open dialog passes names)."""
    cands = ([file] if _plain(file) else []) + [safe(file), _legacy_safe(file)]
    for stem in dict.fromkeys(cands):
        p = os.path.join(PROJECTS, stem + '.json')
        if os.path.isfile(p):
            return p
    if by_name:
        m = next((m for m in list_projects() if m['name'] == file), None)
        if m:
            return os.path.join(PROJECTS, m['file'] + '.json')
    raise FileNotFoundError('The animation "%s" is not saved any more.' % file)


def load(file):
    with _lock:
        return _read(_path_of(file, by_name=True))


def load_uid(uid):
    with _lock:
        m = by_uid().get(uid)
        return load(m['file']) if m else None


def thumb(file):
    d = load(file)
    return d.get('thumb') or ''


def _uid_at(path):
    try:
        st = os.stat(path)
        hit = _metas.get(path)
        if hit and hit[0] == (st.st_mtime_ns, st.st_size):
            return hit[1]['uid']      # unchanged since the list read it
        return _read(path).get('uid')
    except Exception:
        return None       # unreadable: treated as someone else's file, never overwritten


def name_check(name, uid=None):
    """{'file': the file name `name` saves under, 'clash': the OTHER animation already saved there, or None}."""
    with _lock:
        file = safe(name)
        path = os.path.join(PROJECTS, file + '.json')
        clash = None
        if os.path.exists(path) and (_uid_at(path) != uid or not uid):
            clash = _about(path)
        return {'file': file, 'clash': clash}


def _about(path):
    """{name, author, uid, file} of a saved file (what the app shows when asking about a name clash)."""
    try:
        d = _read(path)
    except Exception:
        d = {}
    d = d if isinstance(d, dict) else {}
    return {'name': d.get('name', ''), 'author': d.get('author', ''), 'uid': d.get('uid'), 'file': os.path.basename(path)[:-5]}


def save(body, overwrite=False, ask=False):
    """Save a project -> {'saved', 'file', 'name', 'uid', 'renamed', 'replaced'}: the file name actually used.

    A file of the same name that holds a DIFFERENT animation (another uid) is never overwritten silently:
    - overwrite (the user chose "Replace it"): that animation is moved to animator_replaced first (kept, like Remove
      does) and this one takes its file name. 'replaced' describes it.
    - ask: NameTaken is raised (the server answers 409), so the app can ask the user.
    - otherwise this one is saved as 'Name (2)', 'Name (3)'... and 'renamed' is True.
    If the same animation (uid) was saved under another name before, that older file is moved aside too."""
    with _lock:
        os.makedirs(PROJECTS, exist_ok=True)
        if not body.get('uid'):
            body['uid'] = 'a' + uuid.uuid4().hex[:12]
        uid = body['uid']
        want = safe(body.get('name', 'untitled'))
        stem, replaced = want, None
        path = os.path.join(PROJECTS, stem + '.json')
        if os.path.exists(path) and _uid_at(path) != uid:
            if overwrite:
                replaced = _about(path)
                _set_aside(path, 'replaced')
            elif ask:
                raise NameTaken(_about(path))
            else:
                k = 2
                while os.path.exists(path) and _uid_at(path) != uid:
                    stem = '%s (%d)' % (want, k)
                    path = os.path.join(PROJECTS, stem + '.json')
                    k += 1
        for p in _files():
            if os.path.normcase(p) == os.path.normcase(path):
                continue
            if _uid_at(p) == uid:
                try:
                    _set_aside(p)
                except OSError:
                    pass
        _write(path, body)
    return {'saved': stem, 'file': stem, 'name': body.get('name', ''), 'uid': uid, 'renamed': stem != want,
            'replaced': replaced}


def remove(file):
    """Moves the project out of the list (kept in animator_replaced, never deleted). Its reference pictures and videos
    go along into animator_replaced (refs_<uid>...)."""
    with _lock:
        try:
            p = _path_of(file)
        except FileNotFoundError:
            return {'removed': file}
        uid = _uid_at(p)
        _set_aside(p, 'removed')
        if uid and _UID.match(uid) and os.path.isdir(os.path.join(REFS, uid)):
            try:
                os.makedirs(OLD, exist_ok=True)
                dst, k = os.path.join(OLD, 'refs_%s.%d' % (uid, int(time.time()))), 2
                while os.path.exists(dst):
                    dst = os.path.join(OLD, 'refs_%s.%d-%d' % (uid, int(time.time()), k))
                    k += 1
                _retry(shutil.move, os.path.join(REFS, uid), dst)
            except OSError as ex:
                print('Could not move the reference files of', uid, '-', ex, file=sys.stderr)
    return {'removed': file}


# ------------------------------------------------------------------ reference pictures and videos (spec_editing 12.3)
_UID = re.compile(r'^[A-Za-z0-9]{4,40}$')
_REF_FILE = re.compile(r'^[0-9a-f]{16}\.(png|jpg|webp|gif|mp4|webm)$')
_REF_EXT = {'image/png': 'png', 'image/jpeg': 'jpg', 'image/webp': 'webp', 'image/gif': 'gif', 'video/mp4': 'mp4', 'video/webm': 'webm'}
REF_TYPES = {v: k for k, v in _REF_EXT.items()}
REF_MAX = 400_000_000


def save_ref(uid, data, ctype):
    """Keep a reference picture / video for the animation `uid` -> {'file', 'bytes'}. The name is the content's hash, so
    the same file dropped twice is kept once. ValueError for a bad uid, an unknown type, an empty or too big file."""
    if not _UID.match(uid or ''):
        raise ValueError('That animation id is not valid.')
    ext = _REF_EXT.get((ctype or '').split(';')[0].strip().lower())
    if not ext:
        raise ValueError('Use a picture (PNG, JPG, WEBP, GIF) or a video (MP4, WEBM).')
    if not data:
        raise ValueError('The file is empty.')
    if len(data) > REF_MAX:
        raise ValueError('That file is too big for a reference (over 400 MB).')
    name = hashlib.sha1(data).hexdigest()[:16] + '.' + ext
    folder = os.path.join(REFS, uid)
    path = os.path.join(folder, name)
    with _lock:
        os.makedirs(folder, exist_ok=True)
        if not os.path.isfile(path) or os.path.getsize(path) != len(data):
            tmp = '%s.%d-%d.tmp' % (path, os.getpid(), threading.get_ident())
            try:
                with open(tmp, 'wb') as f:
                    f.write(data)
                _retry(os.replace, tmp, path)
            except BaseException:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
                raise
    return {'file': name, 'bytes': len(data)}


def ref_path(uid, file):
    """The path of a kept reference file (FileNotFoundError when it is not there; ValueError for a bad name)."""
    if not _UID.match(uid or '') or not _REF_FILE.match(file or ''):
        raise ValueError('Not a reference file name.')
    path = os.path.join(REFS, uid, file)
    if not os.path.isfile(path):
        raise FileNotFoundError('That reference file is not there any more.')
    return path


# ------------------------------------------------------------------ progressions
def progressions():
    """Every progression. [] only when none were ever saved; a file that can't be read raises (see _load)."""
    with _lock:
        d = _load(PROGRESSIONS, {})
        items = d.get('progressions', []) if isinstance(d, dict) else []
        return [g for g in items if isinstance(g, dict)]


def save_progressions(items):
    clean = []
    for it in items:
        clean.append({'id': it.get('id') or 'g' + uuid.uuid4().hex[:10], 'name': (it.get('name') or 'Progression').strip()[:60],
                      'author': (it.get('author') or '').strip()[:40], 'steps': [s for s in it.get('steps', []) if s],
                      'repeat': bool(it.get('repeat'))})
    with _lock:
        os.makedirs(ROOT, exist_ok=True)
        _write(PROGRESSIONS, {'progressions': clean})
    return clean


def stage_links(uid, has_step=None, links_to=None):
    """(next step uids, only_through_chain, waiting) for an animation, from every progression it is in.

    has_step(u): is the earlier step u there to lead into this one (in the same mod, or in your game)? None = yes.
    links_to(u): may a next-stage link to u be written? None = yes.
    only_through_chain is True only when the animation is never the first step of a progression AND the step before
    it is there somewhere - otherwise nothing would ever start it. waiting = [(progression name, earlier uid)] that
    were missing (empty when the animation starts a progression anyway)."""
    nxt, later, first, waiting = [], False, False, []
    for g in progressions():
        steps = g.get('steps') or []
        for i, s in enumerate(steps):
            if s != uid:
                continue
            if i == 0:
                first = True
            elif has_step is None or has_step(steps[i - 1]):
                later = True
            else:
                waiting.append((g.get('name') or 'Progression', steps[i - 1]))
            n = steps[i + 1] if i + 1 < len(steps) else (steps[0] if g.get('repeat') and len(steps) > 1 else None)
            if n and n != uid and (links_to is None or links_to(n)):
                nxt.append(n)
    return list(dict.fromkeys(nxt)), later and not first, ([] if first or later else waiting)


# ------------------------------------------------------------------ what was sent to the game
def exports():
    """{uid: package name (no .package)} of each animation's last Send to game."""
    with _lock:
        d = _load(EXPORTS_MAP, {})
        return d if isinstance(d, dict) else {}


def remember_export(uid, base):
    if not uid:
        return
    with _lock:
        os.makedirs(ROOT, exist_ok=True)
        m = exports()
        m[uid] = base
        _write(EXPORTS_MAP, m)


# ------------------------------------------------------------------ My poses (kept here, not in the browser)
def my_poses():
    with _lock:
        d = _load(MY_POSES, {})
        return d.get('poses', []) if isinstance(d, dict) else []


def save_my_poses(items):
    items = [x for x in (items or []) if isinstance(x, dict)]
    with _lock:
        os.makedirs(ROOT, exist_ok=True)
        _write(MY_POSES, {'poses': items})
    return {'saved': len(items)}


# ------------------------------------------------------------------ crash recovery
# While there are unsaved changes the app writes everything here every few seconds (and when its window closes).
# Saving (or choosing Ignore) clears it, so a clean close never asks about recovery.
def _recovery_path(slot=None):
    """Where unfinished work is kept. The user's own app (usual port) uses animator_recovery.json; automated test
    browsers (slot 'test') and test copies of the server on other ports get their own file, so they can never
    replace or clear the user's unfinished work."""
    tag = re.sub(r'[^A-Za-z0-9]+', '', slot or '')[:16]
    port = os.environ.get('ANIMATOR_PORT', '8765')
    if port != '8765':
        tag = (tag + '_' if tag else '') + 'port' + re.sub(r'\D+', '', port)
    if not tag:
        return RECOVERY
    # test copies never write into the user's saves folder: without ANIMATOR_SAVES they use the app's cache
    folder = ROOT if os.environ.get('ANIMATOR_SAVES') else os.path.join(G.CACHE, 'recovery_tests')
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, 'animator_recovery_%s.json' % tag)


def read_recovery(slot=None):
    """The unfinished work, or {} when there is none. A file that stays in use raises (the app then uses the
    browser's own copy); a damaged one counts as none."""
    with _lock:
        try:
            d = _read(_recovery_path(slot))
        except (FileNotFoundError, ValueError):
            return {}
        return d if isinstance(d, dict) else {}


def write_recovery(body, slot=None):
    body = dict(body or {})
    body['written'] = time.time()
    with _lock:
        os.makedirs(ROOT, exist_ok=True)
        _write(_recovery_path(slot), body)
    return {'ok': True}


def clear_recovery(slot=None):
    with _lock:
        try:
            _retry(os.remove, _recovery_path(slot))
        except FileNotFoundError:
            pass
    return {'ok': True}
