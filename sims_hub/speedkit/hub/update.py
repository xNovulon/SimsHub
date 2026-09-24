r"""Keeps the Hub up to date from GitHub: the sims_hub folder of github.com/xNovulon/SimsHub (main branch).

    python -m speedkit.hub.update       update now (what the launcher does before the Hub's server starts)

Every start asks GitHub for the newest commit - one small request, given up after a few seconds (offline, GitHub
down: the Hub simply opens as it is). When there is a newer one, only the files that differ are downloaded, each is
checked against GitHub's own hash, and only once every one of them is here are they put in place - an update is never
half-applied by a lost connection. Files that are not on GitHub (your own, caches, logs) are never touched; a file you
changed yourself is copied to the update backup before it is replaced. Windows line ends (CRLF) count as the same
text, and .bat files are written with them. Files only developers need (SKIP) are left out.

A folder that is a git checkout of the repository is left to git (it is where the Hub is worked on).
SIMS_HUB_NO_UPDATE=1 turns updating off. The same steps keep Novulon's Wicked Animator up to date
(wicked_animator\desktop\Updater.cs).
"""
import concurrent.futures
import hashlib
import json
import os
import re
import shutil
import sys
import time
import urllib.parse
import urllib.request
import uuid

OWNER, REPO, BRANCH, FOLDER = 'xNovulon', 'SimsHub', 'main', 'sims_hub/'
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DIR = os.path.join(os.environ.get('LOCALAPPDATA') or os.path.expanduser('~'), 'NovulonSimsHub', 'update')
API = 'https://api.github.com/repos/%s/%s' % (OWNER, REPO)
RAW = 'https://raw.githubusercontent.com/%s/%s' % (OWNER, REPO)
KEEP_BACKUPS = 3
# only developers need these (the program's source, tests, research notes, artwork) - the same list as Sims Hub.exe's
# (sims_hub/desktop/Program.cs); the Hub reads one research file
SKIP = ('desktop/', 'tests/', 'research/', 'branding/', 'docs/')
KEEP = ('research/merging/companions.json',)


def wanted(rel):
    return rel in KEEP or not rel.startswith(SKIP)


def fetch(url, accept=None, timeout=60):
    """The body of a GitHub URL (tests replace this)."""
    headers = {'User-Agent': 'NovulonSimsHub'}
    if accept:
        headers['Accept'] = accept
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as r:
        return r.read()


# ---------------------------------------------------------------------------------------------------- GitHub
def latest_commit():
    """The newest commit on the branch (its full hash), or None (offline, GitHub not answering, too many checks)."""
    try:
        sha = fetch('%s/commits/%s' % (API, BRANCH), 'application/vnd.github.sha', timeout=6)
    except (OSError, ValueError) as ex:
        log('no update check (offline?): %s' % ex)
        return None
    sha = sha.decode('ascii', 'replace').strip().lower()
    return sha if re.fullmatch('[0-9a-f]{40}', sha) else None


def tree(commit):
    """Every file in the Hub's folder at that commit: path inside the folder -> git hash (None if unknown)."""
    j = json.loads(fetch('%s/git/trees/%s?recursive=1' % (API, commit), 'application/vnd.github+json'))
    if j.get('truncated'):
        log("GitHub's file list came back incomplete - not updating")
        return None
    files = {}
    for e in j.get('tree', ()):
        path = e.get('path') or ''
        if e.get('type') != 'blob' or e.get('mode') == '120000' or not path.startswith(FOLDER):   # folders, links
            continue
        files[path[len(FOLDER):]] = e['sha']
    return files or None


def download(commit, path, sha):
    """One file at that commit, exactly as it is in git (checked); three tries."""
    url = '%s/%s/%s' % (RAW, commit, urllib.parse.quote(path))
    for attempt in (1, 2, 3):
        try:
            data = fetch(url)
            if blob_sha(data) == sha:
                return data
            raise ValueError("the download did not match GitHub's hash")
        except (OSError, ValueError) as ex:
            if attempt == 3:
                raise
            log('retrying %s: %s' % (path, ex))
            time.sleep(attempt)


# ---------------------------------------------------------------------------------------------------- files
def blob_sha(data):
    """git's hash of a file's contents."""
    return hashlib.sha1(b'blob %d\0' % len(data) + data).hexdigest()


def same_as(path, sha):
    """Is the file on disk that git version? Windows line ends (CRLF) count as the same text."""
    if not sha or not os.path.isfile(path):
        return False
    try:
        with open(path, 'rb') as f:
            data = f.read()
    except OSError:
        return False
    if blob_sha(data) == sha:
        return True
    if b'\0' in data or b'\r\n' not in data:                # binary, or no CRLF
        return False
    return blob_sha(data.replace(b'\r\n', b'\n')) == sha


def to_crlf(data):
    return re.sub(rb'(?<!\r)\n', b'\r\n', data)


def target_path(root, rel):
    """Where a file of the folder goes on this PC (None for a path that would leave the folder)."""
    full = os.path.abspath(os.path.join(root, *rel.split('/')))
    top = os.path.abspath(root).rstrip('\\/') + os.sep
    return full if os.path.normcase(full).startswith(os.path.normcase(top)) else None


def is_repo_checkout(root):
    """A git checkout of this repository (a .git folder here or above, pointing at it)."""
    d = os.path.abspath(root)
    while True:
        config = os.path.join(d, '.git', 'config')
        if os.path.isfile(config):
            try:
                with open(config, encoding='utf-8', errors='replace') as f:
                    return ('%s/%s' % (OWNER, REPO)).lower() in f.read().lower()
            except OSError:
                return True
        up = os.path.dirname(d)
        if up == d:
            return False
        d = up


def load_state():
    try:
        with open(os.path.join(DIR, 'state.json'), encoding='utf-8') as f:
            s = json.load(f)
        return {'commit': s.get('commit'), 'files': dict(s.get('files') or {})}
    except (OSError, ValueError, AttributeError):
        return {'commit': None, 'files': {}}


def save_state(state):
    path = os.path.join(DIR, 'state.json')
    with open(path + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=1)
    os.replace(path + '.tmp', path)


def log(line):
    try:
        os.makedirs(DIR, exist_ok=True)
        path = os.path.join(DIR, 'update.log')
        if os.path.isfile(path) and os.path.getsize(path) > 500000:
            os.replace(path, path + '.old')
        with open(path, 'a', encoding='utf-8') as f:
            f.write('%s %s\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), line))
    except OSError:
        pass


# ---------------------------------------------------------------------------------------------------- update
def disabled(root=None):
    return os.environ.get('SIMS_HUB_NO_UPDATE') == '1' or is_repo_checkout(root or ROOT)


def waiting(root=None):
    """The newer commit on GitHub when there is one (a quick check), else None."""
    if disabled(root):
        return None
    commit = latest_commit()
    return commit if commit and commit != load_state()['commit'] else None


def run(root=None, commit=None):
    """Bring the folder up to date. Returns {'changed': files replaced or removed, 'commit': ..., 'complete': ...}."""
    root = root or ROOT
    nothing = {'changed': 0, 'commit': None, 'complete': True}
    try:
        if disabled(root):
            return nothing
        os.makedirs(DIR, exist_ok=True)
        state = load_state()
        commit = commit or latest_commit()
        if not commit or commit == state['commit']:
            return nothing
        every = tree(commit)
        if not every:
            return nothing
        files = {rel: sha for rel, sha in every.items() if wanted(rel)}
        for rel in [r for r in state['files'] if r in every and r not in files]:
            del state['files'][rel]                       # developers only: a copy already here stays as it is
        todo = []
        for rel, sha in files.items():
            target = target_path(root, rel)
            if target and not same_as(target, sha):
                todo.append((rel, sha, target))
        gone = [rel for rel in state['files'] if rel not in every]
        if not todo and not gone:
            state['files'].update(files)
            state['commit'] = commit
            save_state(state)
            return dict(nothing, commit=commit)

        # 1. download everything that changed into a staging folder, each file checked against its git hash
        log('updating %s to %s: %d file(s) to download, %d removed' % (root, commit[:7], len(todo), len(gone)))
        stage = os.path.join(DIR, 'staging')
        shutil.rmtree(stage, ignore_errors=True)
        os.makedirs(stage)
        staged = {}

        def get(item):
            rel, sha, _ = item
            data = download(commit, FOLDER + rel, sha)
            if rel.lower().endswith(('.bat', '.cmd')):
                data = to_crlf(data)                       # cmd.exe misreads labels in files with bare LF line ends
            tmp = os.path.join(stage, uuid.uuid4().hex)
            with open(tmp, 'wb') as f:
                f.write(data)
            staged[rel] = tmp

        with concurrent.futures.ThreadPoolExecutor(6) as pool:
            list(pool.map(get, todo))                     # any failed download ends the update: nothing changed yet

        # 2. put them in place
        backup = os.path.join(DIR, 'backup', time.strftime('%Y-%m-%d_%H%M%S'))
        changed, complete = 0, True
        for rel, sha, target in todo:
            try:
                if os.path.isfile(target) and not same_as(target, state['files'].get(rel)):
                    to = os.path.join(backup, *rel.split('/'))          # changed here (or never updated here)
                    os.makedirs(os.path.dirname(to), exist_ok=True)
                    shutil.copy2(target, to)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                os.replace(staged[rel], target)
                state['files'][rel] = sha
                changed += 1
            except OSError as ex:
                complete = False
                log('could not replace %s: %s' % (rel, ex))
        replaced = {rel for rel, _, _ in todo}
        for rel, sha in files.items():
            if rel not in replaced:                       # already the same as on GitHub
                state['files'][rel] = sha
        # files removed from GitHub go too - only while they are still exactly as the update left them
        for rel in gone:
            target = target_path(root, rel)
            try:
                if target and same_as(target, state['files'][rel]):
                    os.remove(target)
                    changed += 1
                del state['files'][rel]
            except OSError as ex:
                complete = False
                log('could not remove %s: %s' % (rel, ex))
        if complete:
            state['commit'] = commit                     # otherwise the next start tries again
        save_state(state)
        shutil.rmtree(stage, ignore_errors=True)
        _prune(os.path.join(DIR, 'backup'))
        log('updated %d file(s)%s' % (changed, '' if complete else ' (some could not be replaced - trying again next start)'))
        return {'changed': changed, 'commit': commit, 'complete': complete}
    except Exception as ex:                                # an update must never keep the Hub from opening
        log('update skipped: %s' % ex)
        return nothing


def _prune(folder):
    try:
        for name in sorted(os.listdir(folder), reverse=True)[KEEP_BACKUPS:]:
            shutil.rmtree(os.path.join(folder, name), ignore_errors=True)
    except OSError:
        pass


def main():
    r = run()
    print('Updated %d file(s) to %s.' % (r['changed'], r['commit'][:7]) if r['commit'] else 'Nothing to update.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
