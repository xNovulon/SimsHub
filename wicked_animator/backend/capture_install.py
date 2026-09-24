"""Motion capture's one-time download: MediaPipe Tasks Vision 1.0.1 (Apache-2.0) and its four models (about 64 MB).

Everything lands in web/vendor/mediapipe/ and is checked against pinned hashes before it is used:
    vision_bundle.mjs, wasm/vision_wasm_internal.js, wasm/vision_wasm_internal.wasm   (from the npm tarball)
    models/pose_landmarker_heavy.task, pose_landmarker_full.task, hand_landmarker.task, face_landmarker.task
Only Python's standard library is used (no npm, no pip).

- Every download goes to '<file>.part' first and is moved into place (os.replace) only after its size and hash
  match, so a broken or half-finished file is never used. A '.part' left by an interrupted run is continued where
  it stopped (HTTP Range) the next time.
- From the npm tarball only the three named files are taken, by exact name (never extractall).
- A file already there with the right size and hash is skipped, so running it again is always safe.
- manifest.json records the version and what was installed.

Tests replace the file table with WICKED_CAPTURE_FILES=<a JSON file>: either a list of entries shaped like FILES
below, or {"root": "<folder to install into>", "files": [...]} (a mock server on 127.0.0.1 serves them).
"""
import base64, hashlib, io, json, os, tarfile, threading, time, traceback
import urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
VENDOR = os.path.normpath(os.path.join(HERE, '..', 'web', 'vendor', 'mediapipe'))
VERSION = '1.0.1'
CHUNK = 1 << 20

# capture.md 2.1-2.2: the npm tarball (sha512 integrity) and the four float16 models (the bucket's own md5), pinned.
FILES = [
    {'name': 'MediaPipe runtime', 'kind': 'tar', 'part': 'tasks-vision-1.0.1.tgz',
     'url': 'https://registry.npmjs.org/@mediapipe/tasks-vision/-/tasks-vision-1.0.1.tgz',
     'size': None, 'approx': 11500000, 'hash': 'sha512',
     'value': 'rvRE2FmAZ6ZxKSw7wq+e+jQDpN3t1B/tD2mJz9SmAzb1msoDkd4dMoE4wAh8Z30Um0PQwLiHr9QtomhmXk3aUQ==',
     'members': [
         {'member': 'package/vision_bundle.mjs', 'dest': 'vision_bundle.mjs', 'size': 155439},
         {'member': 'package/wasm/vision_wasm_internal.js', 'dest': 'wasm/vision_wasm_internal.js', 'size': 323377},
         {'member': 'package/wasm/vision_wasm_internal.wasm', 'dest': 'wasm/vision_wasm_internal.wasm', 'size': 11756954},
     ]},
    {'name': 'Body model (best)', 'dest': 'models/pose_landmarker_heavy.task', 'size': 30664242, 'hash': 'md5',
     'value': 'RT3sTQLMxNPOgStt6E+lFg==',
     'url': 'https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/1/pose_landmarker_heavy.task'},
    {'name': 'Body model (fast)', 'dest': 'models/pose_landmarker_full.task', 'size': 9398198, 'hash': 'md5',
     'value': 'g4eWidNz0UO+CUyXI1Xkjg==',
     'url': 'https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task'},
    {'name': 'Hand model', 'dest': 'models/hand_landmarker.task', 'size': 7819105, 'hash': 'md5',
     'value': 'FTGEMOo4UWcP6ZFBFqnPrQ==',
     'url': 'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task'},
    {'name': 'Face model', 'dest': 'models/face_landmarker.task', 'size': 3758596, 'hash': 'md5',
     'value': 'sOcnSQehZEQE/vZrKN1thQ==',
     'url': 'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task'},
]

_lock = threading.Lock()
_state = {'busy': False, 'done_bytes': 0, 'total_bytes': 0, 'error': None, 'stage': '', 'finished': None}


# ---------------------------------------------------------------------------------------------------- the table
def _table():
    """(root folder, file entries): the pinned table, or the test table from WICKED_CAPTURE_FILES."""
    path = os.environ.get('WICKED_CAPTURE_FILES')
    if not path:
        return VENDOR, FILES
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if isinstance(data, dict):
        return os.path.normpath(data.get('root') or VENDOR), data['files']
    return VENDOR, data


def _outputs(entry):
    """The files an entry puts on disk: [(dest relative to root, expected size or None)]."""
    if entry.get('kind') == 'tar':
        return [(m['dest'], m.get('size')) for m in entry['members']]
    return [(entry['dest'], entry.get('size'))]


def _dest(root, rel):
    full = os.path.normpath(os.path.join(root, rel))
    if os.path.commonpath([os.path.normcase(full), os.path.normcase(root)]) != os.path.normcase(root):
        raise ValueError('bad destination ' + rel)
    return full


def _part_path(root, entry):
    return _dest(root, entry.get('part') or entry['dest']) + '.part'


class Damaged(Exception):
    """A download whose size or hash is wrong (it is deleted, never used)."""


def _digest(kind, path=None, data=None):
    h = hashlib.new(kind)
    if data is not None:
        h.update(data)
    else:
        with open(path, 'rb') as f:
            for block in iter(lambda: f.read(CHUNK), b''):
                h.update(block)
    return base64.b64encode(h.digest()).decode('ascii')


def _manifest(root):
    try:
        with open(os.path.join(root, 'manifest.json'), 'r', encoding='utf-8') as f:
            m = json.load(f)
        return m if isinstance(m, dict) else {}
    except (OSError, ValueError):
        return {}


def _file_ok(root, rel, size, manifest, deep=False, entry=None):
    """Is this output there and right? Sizes always; with deep=True also the hash (the model's own hash, or the
    sha256 the manifest recorded for a file taken from the tarball)."""
    path = _dest(root, rel)
    if not os.path.isfile(path):
        return False
    if size is not None and os.path.getsize(path) != size:
        return False
    if not deep:
        return True
    if entry is not None and entry.get('kind') != 'tar':
        return _digest(entry['hash'], path) == entry['value']
    want = (manifest.get('sha256') or {}).get(rel.replace('\\', '/'))
    return want is None or _digest('sha256', path) == want


def _entry_ok(root, entry, manifest, deep=False):
    return all(_file_ok(root, rel, size, manifest, deep, entry) for rel, size in _outputs(entry))


def _entry_bytes(entry):
    """How many bytes an entry downloads (the tarball's real size once known, else its estimate)."""
    return entry.get('size') or entry.get('_length') or entry.get('approx') or sum(s or 0 for _, s in _outputs(entry))


# ---------------------------------------------------------------------------------------------------- status
def status():
    """{installed, missing: [names], bytes_needed, busy, done_bytes, total_bytes, error, stage, version, files}"""
    try:
        root, table = _table()
    except Exception as ex:                       # a broken test table
        return {'installed': False, 'missing': [], 'bytes_needed': 0, 'busy': False, 'done_bytes': 0,
                'total_bytes': 0, 'error': str(ex), 'stage': '', 'version': VERSION, 'files': []}
    man = _manifest(root)
    files, missing, needed = [], [], 0
    for e in table:
        ok = True
        for rel, size in _outputs(e):
            path = _dest(root, rel)
            if not os.path.isfile(path):
                st = 'missing'
            elif size is not None and os.path.getsize(path) != size:
                st = 'wrong'
            else:
                st = 'ok'
            ok = ok and st == 'ok'
            files.append({'file': rel.replace('\\', '/'), 'state': st, 'bytes': size})
        if not ok:
            missing.append(e['name'])
            needed += _entry_bytes(e)
    with _lock:
        s = dict(_state)
    return {'installed': not missing, 'missing': missing, 'bytes_needed': needed, 'busy': s['busy'],
            'done_bytes': s['done_bytes'], 'total_bytes': s['total_bytes'], 'error': s['error'], 'stage': s['stage'],
            'version': man.get('version') or VERSION, 'files': files}


# ---------------------------------------------------------------------------------------------------- download
def _set(**kw):
    with _lock:
        _state.update(kw)


def _add_done(n):
    with _lock:
        _state['done_bytes'] += n


def _download(entry, part, cancel=None):
    """Stream entry['url'] into `part`, continuing a '.part' an earlier run left (HTTP Range). Returns the size."""
    os.makedirs(os.path.dirname(part), exist_ok=True)
    have = os.path.getsize(part) if os.path.isfile(part) else 0
    size = entry.get('size')
    if size is not None and have > size:
        os.remove(part)
        have = 0
    if size is not None and have == size:
        _add_done(have)
        return have
    req = urllib.request.Request(entry['url'], headers={'User-Agent': 'WickedAnimator-capture/1', 'Accept-Encoding': 'identity'})
    if have:
        req.add_header('Range', 'bytes=%d-' % have)
    try:
        r = urllib.request.urlopen(req, timeout=30)
    except urllib.error.HTTPError as ex:
        if ex.code == 416 and have:                # the '.part' is already whole: its hash decides
            _add_done(have)
            return have
        raise
    with r:
        code = getattr(r, 'status', 200)
        crange = r.headers.get('Content-Range') or ''
        if have and not (code == 206 and crange.startswith('bytes %d-' % have)):
            have = 0                               # the server sent the whole file again: start over
        length = r.headers.get('Content-Length')
        expect = None
        if length and length.isdigit():
            total = expect = have + int(length)
            if entry.get('kind') == 'tar' and not size:
                old = _entry_bytes(entry)
                entry['_length'] = total
                with _lock:
                    _state['total_bytes'] += total - old
        _add_done(have)
        with open(part, 'ab' if have else 'wb') as f:
            while True:
                if cancel is not None and cancel.is_set():
                    raise InterruptedError('stopped')
                block = r.read(CHUNK)
                if not block:
                    break
                f.write(block)
                have += len(block)
                _add_done(len(block))
    if expect is not None and have < expect:
        # the connection dropped: keep the '.part', the next run continues from here
        raise ConnectionError('The download was interrupted.')
    return have


def _replace_into(data, dest):
    """Write bytes as dest.part, then move it into place."""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + '.part'
    with open(tmp, 'wb') as f:
        f.write(data)
    os.replace(tmp, dest)


def _install_entry(root, entry, man, cancel=None):
    part = _part_path(root, entry)
    got = _download(entry, part, cancel)
    size = entry.get('size')
    if (size is not None and got != size) or _digest(entry['hash'], part) != entry['value']:
        try:
            os.remove(part)                        # a damaged download never stays around
        except OSError:
            pass
        raise Damaged('The download of "%s" was damaged - please try again.' % entry['name'])
    if entry.get('kind') != 'tar':
        os.replace(part, _dest(root, entry['dest']))
        return
    with open(part, 'rb') as f:
        data = f.read()
    sha = man.setdefault('sha256', {})
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as tar:
        for m in entry['members']:
            info = tar.getmember(m['member'])      # exactly this name, nothing else from the archive
            if not info.isfile():
                raise Damaged('Unexpected file in the download: ' + m['member'])
            if m.get('size') is not None and info.size != m['size']:
                raise Damaged('Unexpected size of %s in the download.' % m['member'])
            blob = tar.extractfile(info).read()
            _replace_into(blob, _dest(root, m['dest']))
            sha[m['dest'].replace('\\', '/')] = _digest('sha256', data=blob)
    os.remove(part)


def _write_manifest(root, table, man):
    files = {}
    for e in table:
        for rel, size in _outputs(e):
            p = _dest(root, rel)
            if os.path.isfile(p):
                files[rel.replace('\\', '/')] = os.path.getsize(p)
    man.update({'version': VERSION, 'files': files, 'installed': int(time.time())})
    _replace_into(json.dumps(man, indent=1).encode('utf-8'), os.path.join(root, 'manifest.json'))


def _claim():
    """Mark the installer busy; False when another run is going on."""
    with _lock:
        if _state['busy']:
            return False
        _state.update(busy=True, done_bytes=0, total_bytes=0, error=None, stage='Starting...', finished=None)
        return True


def install(progress=None, cancel=None, _claimed=False):
    """Download and check everything that is missing. Returns status(). Safe to run again at any time."""
    if not _claimed and not _claim():
        return None
    try:
        root, table = _table()
        man = _manifest(root)
        todo = [e for e in table if not _entry_ok(root, e, man, deep=True)]
        _set(total_bytes=sum(_entry_bytes(e) for e in todo))
        for e in todo:
            _set(stage='Downloading ' + e['name'] + '...')
            if progress:
                progress(status())
            _install_entry(root, e, man, cancel)
        _write_manifest(root, table, man)
        _set(stage='Ready!', finished=time.time())
    except InterruptedError:
        _set(error='The download was stopped. Click Download to continue where it stopped.', stage='')
    except Damaged as ex:
        _set(error=str(ex), stage='')
    except ConnectionError:
        _set(error='The download was interrupted - check the internet and click Download again to continue where '
                   'it stopped.', stage='')
    except urllib.error.HTTPError as ex:
        _set(error='The download server answered %d - please try again later.' % ex.code, stage='')
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as ex:
        net = isinstance(ex, (urllib.error.URLError, TimeoutError, ConnectionError)) or 'timed out' in str(ex)
        _set(error='No internet right now - connect once to download it.' if net else str(ex), stage='')
        if not net:
            traceback.print_exc()
    except Exception as ex:
        traceback.print_exc()
        _set(error=str(ex) or repr(ex), stage='')
    finally:
        _set(busy=False)
    return status()


def start(cancel=None):
    """install() on a background thread (one at a time). Returns the status right away (busy while it runs)."""
    if _claim():
        threading.Thread(target=install, kwargs={'cancel': cancel, '_claimed': True}, daemon=True,
                         name='capture-install').start()
    return status()


if __name__ == '__main__':
    import sys
    if '--install' in sys.argv:
        print(json.dumps(install(), indent=1))
    else:
        print(json.dumps(status(), indent=1))
