"""Every change SpeedKit makes to the Sims 4 folder goes through a Journal, so it can be undone.

Rules the journal enforces:
  * nothing happens while TS4_x64.exe is running (checked when the journal opens and before every step);
  * files are never deleted: a replaced or removed file is moved into <home>\\quarantine\\<id>\\...
    The quarantine may be on another drive (e.g. E: when C: is short of space): then the file is
    copied, the copy's size checked, and only then the original removed;
  * every step is written to <home>\\journal\\<id>.json before it starts and again when it is done,
    so an interrupted run can still be undone - undo() looks at the disk to see how far an
    unfinished step got;
  * undo() first works out every action against a model of the disk and refuses before touching
    anything if one of them would overwrite something; it marks each reversed step, so an undo
    that stops half-way (a file in use, say) can simply be run again.

    with Journal('dedup', 'remove 42 duplicate copies') as j:
        j.quarantine(path)                 # move a file out of the way
        j.put_new(tmp_path, final_path)    # move a newly written file into place (final must not exist)
        j.replace(tmp_path, final_path)    # quarantine final_path, then move tmp_path into its place
        j.move(src, dst)                   # plain move inside the Sims 4 folder (profiles)
"""
import hashlib, json, os, shutil, stat, sys, time, uuid

from .library import SIMS, game_running

HOME = os.path.join(SIMS, 'SpeedKit')
JOURNALS = os.path.join(HOME, 'journal')
QUARANTINE = os.path.join(HOME, 'quarantine')
SCRIPT_KINDS = ('profile', 'inbox', 'install')


class JournalError(Exception):
    pass


def _fingerprint(path):
    st = os.stat(path)
    return [st.st_size, round(st.st_mtime, 3)]


def _norm(p):
    return os.path.normcase(os.path.abspath(p))


def _inside(path, base):
    path, base = _norm(path), _norm(base)
    return path == base or path.startswith(base.rstrip('\\/') + os.sep)


def _same_drive(a, b):
    return os.path.splitdrive(os.path.abspath(a))[0].lower() == os.path.splitdrive(os.path.abspath(b))[0].lower()


def _move(src, dst):
    """Move a file or folder. Same drive: a rename. Other drive: copy, check sizes, then remove the source."""
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if _same_drive(src, dst):
        os.replace(src, dst) if os.path.isfile(src) else os.rename(src, dst)
        return
    if os.path.isdir(src):
        shutil.copytree(src, dst)
        for dp, dn, fn in os.walk(src):
            for n in fn:
                a = os.path.join(dp, n)
                b = os.path.join(dst, os.path.relpath(a, src))
                if os.path.getsize(a) != os.path.getsize(b):
                    raise JournalError('copy of %s is incomplete' % a)
        _remove_tree(src)
        return
    tmp = dst + '.copying'
    shutil.copy2(src, tmp)
    if os.path.getsize(tmp) != os.path.getsize(src):
        os.remove(tmp)
        raise JournalError('copy of %s is incomplete' % src)
    os.replace(tmp, dst)
    _unlink(src)


def _unlink(path):
    try:
        os.remove(path)
    except PermissionError:
        os.chmod(path, stat.S_IWRITE)        # read-only file
        os.remove(path)


def _remove_tree(path):
    def retry(func, p, exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=retry)
    else:
        shutil.rmtree(path, onerror=retry)


def _mirror(path, sims):
    """The same place in the other mod root (Mods <-> Mods_parked), or None when path is in neither.
    Mod switchers (SpeedKit's and the other chat's mods_switch.py) move files between the two roots."""
    for a, b in (('Mods', 'Mods_parked'), ('Mods_parked', 'Mods')):
        base = os.path.join(sims, a)
        if _inside(path, base) and _norm(path) != _norm(base):
            return os.path.join(sims, b, os.path.relpath(os.path.abspath(path), base))
    return None


class Journal:
    def __init__(self, kind, note='', home=HOME, sims=SIMS, check_game=True, quarantine_home=None):
        """home: where the journal lives (default <Sims 4>\\SpeedKit). quarantine_home: where replaced files
        go (default <home>\\quarantine); may be on another drive."""
        self.check_game = check_game
        self._game_check()
        for mods in ('Mods', 'Mods_parked'):
            for d in (home, quarantine_home):
                if d and _inside(d, os.path.join(sims, mods)):
                    raise JournalError('the SpeedKit folder must not be inside %s (the game would load quarantined files)' % mods)
        self.kind, self.note = kind, note
        self.sims = sims
        self.home = home
        base = time.strftime('%Y%m%d-%H%M%S') + '-' + kind
        os.makedirs(os.path.join(home, 'journal'), exist_ok=True)
        self.id = base
        n = 1
        while os.path.exists(os.path.join(home, 'journal', self.id + '.json')):
            n += 1
            self.id = '%s-%d' % (base, n)
        self.dir_q = os.path.join(quarantine_home or os.path.join(home, 'quarantine'), self.id)
        self.path = os.path.join(home, 'journal', self.id + '.json')
        self.steps = []
        self.state = 'open'
        # claim the id atomically so two processes cannot share it
        try:
            with open(self.path, 'x', encoding='utf-8') as f:
                f.write('{}')
        except FileExistsError:
            self.id = '%s-%s' % (base, uuid.uuid4().hex[:6])
            self.path = os.path.join(home, 'journal', self.id + '.json')
            self.dir_q = os.path.join(os.path.dirname(self.dir_q), self.id)
        self._save()

    # --------------------------------------------------------------- bookkeeping
    def _game_check(self):
        if self.check_game and game_running():
            raise JournalError('The Sims 4 is running (or its state could not be checked) - close it first.')

    def _save(self):
        tmp = self.path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump({'id': self.id, 'kind': self.kind, 'note': self.note, 'state': self.state, 'sims': self.sims,
                       'quarantine': self.dir_q, 'steps': self.steps}, f, indent=1)
        os.replace(tmp, self.path)

    def _check_path(self, p):
        if not _inside(p, self.sims):
            raise JournalError('refusing to touch a path outside the Sims 4 folder: %s' % p)
        if os.path.normcase(p).endswith('.ts4script') and self.kind not in SCRIPT_KINDS:
            raise JournalError('refusing to change a script mod: %s' % p)
        for protected in ('saves', 'Tray'):
            if _inside(p, os.path.join(self.sims, protected)):
                raise JournalError('refusing to change %s: %s' % (protected, p))

    def _step(self, op, **kw):
        self._game_check()
        kw['op'] = op
        kw['done'] = False
        self.steps.append(kw)
        self._save()
        return kw

    def _done(self, step):
        step['done'] = True
        self._save()

    def _qpath(self, path):
        return os.path.join(self.dir_q, os.path.relpath(os.path.abspath(path), self.sims))

    # --------------------------------------------------------------- operations
    def quarantine(self, path):
        """Move an existing file into this run's quarantine folder. Returns the quarantine path."""
        self._check_path(path)
        if not os.path.exists(path):
            raise JournalError('nothing to quarantine at %s' % path)
        q = self._qpath(path)
        if os.path.exists(q):
            raise JournalError('already quarantined: %s' % path)
        s = self._step('quarantine', path=path, q=q, fp=_fingerprint(path))
        _move(path, q)
        self._done(s)
        return q

    def put_new(self, tmp, final):
        """Move a finished new file into place. final must not exist; tmp should be on final's drive."""
        self._check_path(final)
        if os.path.exists(final):
            raise JournalError('will not overwrite %s' % final)
        s = self._step('put_new', path=final, tmp=tmp)
        _move(tmp, final)
        s['fp'] = _fingerprint(final)
        self._done(s)

    def replace(self, tmp, final):
        """Quarantine final, then move tmp into its place."""
        self.quarantine(final)
        self.put_new(tmp, final)

    def move(self, src, dst):
        """Move a file or folder within the Sims 4 folder (dst must not exist)."""
        self._check_path(src)
        self._check_path(dst)
        if os.path.exists(dst):
            raise JournalError('will not overwrite %s' % dst)
        s = self._step('move', src=src, dst=dst)
        _move(src, dst)
        self._done(s)

    def close(self, state='committed'):
        self.state = state
        self._save()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close('committed' if exc_type is None else 'failed: %s' % (exc,))
        return False


def list_journals(home=HOME):
    d = os.path.join(home, 'journal')
    out = []
    if os.path.isdir(d):
        for n in sorted(os.listdir(d)):
            if n.endswith('.json'):
                try:
                    with open(os.path.join(d, n), encoding='utf-8') as f:
                        j = json.load(f)
                    out.append((j['id'], j['kind'], j['state'], len(j['steps']), j.get('note', '')))
                except (ValueError, KeyError, OSError):
                    continue
    return out


def _effect_happened(s):
    """For a step that was started but not marked done: did its move actually happen?"""
    if s['op'] == 'quarantine':
        return os.path.exists(s['q']) and not os.path.exists(s['path'])
    if s['op'] == 'put_new':
        return os.path.exists(s['path']) and not os.path.exists(s.get('tmp', ''))
    if s['op'] == 'move':
        return os.path.exists(s['dst']) and not os.path.exists(s['src'])
    return False


def undo(journal_id, home=HOME, check_game=True, dry_run=False):
    """Reverse a journal's steps, newest first. Returns the list of (action, path).

    Plans everything against a model of the disk first and raises JournalError before changing
    anything if an action would overwrite a file or a needed file is missing. Each reversed step is
    marked in the journal, so an interrupted undo can be run again and continues where it stopped.
    """
    if check_game and game_running():
        raise JournalError('The Sims 4 is running (or its state could not be checked) - close it first.')
    path = os.path.join(home, 'journal', journal_id + '.json')
    with open(path, encoding='utf-8') as f:
        j = json.load(f)
    if j.get('state') == 'undone':
        raise JournalError('journal %s was already undone' % journal_id)

    todo = []
    for n, s in reversed(list(enumerate(j['steps']))):
        if s.get('undone'):
            continue
        if s['done'] or _effect_happened(s):
            todo.append((n, s))

    # plan against a model of the disk: path -> exists?
    exists = {}

    def ex(p):
        k = _norm(p)
        return exists[k] if k in exists else os.path.exists(p)

    def setx(p, v):
        exists[_norm(p)] = v

    plan = []
    for n, s in todo:
        if s['op'] == 'put_new':
            if ex(s['path']):
                if 'fp' in s and os.path.exists(s['path']) and _norm(s['path']) not in exists \
                        and _fingerprint(s['path']) != s['fp']:
                    raise JournalError('%s changed after SpeedKit wrote it; not undoing' % s['path'])
                away = os.path.join(os.path.dirname(j.get('quarantine') or os.path.join(home, 'quarantine', journal_id)),
                                    journal_id, '_undone_new', os.path.relpath(s['path'], j['sims']))
                if ex(away):
                    away += '.%s' % uuid.uuid4().hex[:6]
                plan.append((n, 'remove new file (kept in quarantine)', s['path'], away))
                setx(s['path'], False)
                setx(away, True)
            else:
                moved = _mirror(s['path'], j['sims'])
                if moved and os.path.exists(moved):
                    raise JournalError('%s was moved to %s after SpeedKit wrote it (a mod switch); switch back '
                                       'first, or restoring the old copy would leave two copies' % (s['path'], moved))
                plan.append((n, 'already gone', s['path'], None))
        elif s['op'] == 'quarantine':
            if not ex(s['q']):
                raise JournalError('quarantined copy is missing: %s' % s['q'])
            if ex(s['path']):
                raise JournalError('cannot restore %s: something is in its place' % s['path'])
            plan.append((n, 'restore', s['q'], s['path']))
            setx(s['q'], False)
            setx(s['path'], True)
        elif s['op'] == 'move':
            if not ex(s['dst']):
                raise JournalError('moved item is missing: %s' % s['dst'])
            if ex(s['src']):
                raise JournalError('cannot move back to %s: something is in its place' % s['src'])
            plan.append((n, 'move back', s['dst'], s['src']))
            setx(s['dst'], False)
            setx(s['src'], True)

    actions = [(what, dst or src) for _, what, src, dst in plan]
    if dry_run:
        return actions
    for n, what, src, dst in plan:
        if check_game and game_running():
            raise JournalError('The Sims 4 was started during the undo - it stopped part-way; run it again '
                               'after closing the game (it continues where it stopped).')
        if dst is not None:
            _move(src, dst)
        j['steps'][n]['undone'] = True
        with open(path + '.tmp', 'w', encoding='utf-8') as f:
            json.dump(j, f, indent=1)
        os.replace(path + '.tmp', path)
    j['state'] = 'undone'
    with open(path + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(j, f, indent=1)
    os.replace(path + '.tmp', path)
    return actions


def file_digest(path, chunk=1 << 22):
    h = hashlib.blake2b(digest_size=16)
    with open(path, 'rb') as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()
