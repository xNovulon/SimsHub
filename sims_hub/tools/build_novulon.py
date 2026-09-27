r"""Build dist/Novulon.ts4script from ingame/novulon/**, subpackage-aware.

    python tools/build_novulon.py

Same pipeline as `build_ingame.py` (SpeedKit Monitor), same facts it relies on:
  * the game imports only .pyc/.pyo from a .ts4script, so the archive must hold bytecode for the game's
    exact Python: 3.7.0, pyc magic 3394 (b'B\r\r\n');
  * the .pyc files are compiled by py_compile running INSIDE the game's own python37_x64.dll
    (`tools/game_python.py`), not by this Python 3.12.

One real difference from `build_ingame.py`, not a copy-paste: SpeedKit Monitor's package is flat
(`ingame/speedkit_monitor/*.py`, no sub-packages), so `build_ingame.sources()` just lists a directory.
Novulon's tree has real sub-packages (`menukit/`, `sims/`, `gameplay/`, `adult/`, `compat/`, ...), so
`sources()` here walks the whole tree with `os.walk` and every function below carries the file's relative
path through, preserving it inside the archive (`novulon/menukit/page.pyc`, `novulon/sims/query.pyc`, ...)
and in `co_filename` (`Novulon.ts4script/novulon/sims/query.py`) for readable tracebacks - `build_ingame.py`
cannot be reused unchanged for this (engineering.md §11).
"""
import json
import os
import sys
import tempfile
import time
import zipfile

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT not in sys.path:
    sys.path.insert(0, PROJECT)
from tools import game_python  # noqa: E402

SRC = os.path.join(PROJECT, 'ingame', 'novulon')
DIST = os.path.join(PROJECT, 'dist', 'Novulon.ts4script')
ARCHIVE = 'Novulon.ts4script'
PACKAGE = 'novulon'
MAGIC_37 = 3394

COMPILE37 = r'''
import json, os, sys, importlib.util, py_compile
job = json.loads(HOST_ARGS)
out = {'version': sys.version, 'magic': importlib.util.MAGIC_NUMBER.hex(), 'compiled': [], 'errors': []}
for src, cfile, dfile in job['files']:
    try:
        os.makedirs(os.path.dirname(cfile), exist_ok=True)
        py_compile.compile(src, cfile=cfile, dfile=dfile, doraise=True)
        out['compiled'].append(cfile)
    except Exception as e:
        out['errors'].append('%s: %s' % (src, e))
with open(job['result'], 'w', encoding='utf-8') as f:
    json.dump(out, f)
'''


def sources(src_dir=SRC):
    """Every .py file under the package, subpackage-aware: a sorted list of (abs_path, rel_path), rel_path
    using forward slashes (e.g. 'sims/query.py'). __pycache__ directories are never walked into."""
    out = []
    for dirpath, dirnames, filenames in os.walk(src_dir):
        dirnames[:] = [n for n in dirnames if n != '__pycache__']
        for n in filenames:
            if n.endswith('.py'):
                abspath = os.path.join(dirpath, n)
                rel = os.path.relpath(abspath, src_dir).replace(os.sep, '/')
                out.append((abspath, rel))
    out.sort(key=lambda t: t[1])
    return out


def magic_ok(data):
    """True if data starts with a Python 3.7.0 .pyc header (magic 3394 + b'\\r\\n', 16-byte header)."""
    return len(data) >= 16 and int.from_bytes(data[:2], 'little') == MAGIC_37 and data[2:4] == b'\r\n'


def compile_in_game_python(files, out_dir, timeout=300):
    """files: [(src_abspath, rel_path), ...]. Compile with py_compile inside the game's python37_x64.dll.
    Returns the child's report: {'version', 'magic', 'compiled': [pyc paths, same order], 'errors', ...}."""
    job = {'files': [], 'result': os.path.join(out_dir, '_compile_result.json')}
    for src, rel in files:
        cfile = os.path.join(out_dir, *rel.split('/'))[:-3] + '.pyc'      # keeps sub-directories under out_dir
        dfile = '%s/%s/%s' % (ARCHIVE, PACKAGE, rel)
        job['files'].append([src, cfile, dfile])
    script = os.path.join(out_dir, '_compile37.py')
    with open(script, 'w', encoding='utf-8') as f:
        f.write(COMPILE37)
    cp = game_python.run(script, args=json.dumps(job), timeout=timeout)
    try:
        with open(job['result'], encoding='utf-8') as f:
            rep = json.load(f)
    except (OSError, ValueError):
        rep = {'version': None, 'magic': None, 'compiled': [], 'errors': ['no result from game Python']}
    rep['stdout'] = (cp.stdout or '') + (cp.stderr or '')
    rep['returncode'] = cp.returncode
    return rep


def build(src_dir=SRC, dist=DIST):
    """Compile and pack the mod. Returns {'dist', 'entries', 'bytes', 'python', 'seconds'}; raises
    RuntimeError if anything fails to compile or a .pyc has the wrong magic number."""
    if not game_python.available():
        raise RuntimeError('game Python not found at %s' % game_python.DLL)
    t0 = time.perf_counter()
    files = sources(src_dir)
    if not files:
        raise RuntimeError('no .py files in %s' % src_dir)
    with tempfile.TemporaryDirectory(prefix='novulon_build_') as tmp:
        rep = compile_in_game_python(files, tmp)
        if rep['errors'] or len(rep['compiled']) != len(files):
            raise RuntimeError('compile failed: %s\n%s' % (rep['errors'], rep['stdout']))
        entries = []
        os.makedirs(os.path.dirname(dist), exist_ok=True)
        part = dist + '.writing'
        try:
            with zipfile.ZipFile(part, 'w', zipfile.ZIP_DEFLATED) as z:
                for (src, rel), cfile in zip(files, rep['compiled']):
                    with open(cfile, 'rb') as f:
                        data = f.read()
                    if not magic_ok(data):
                        raise RuntimeError('%s: not a Python 3.7 .pyc (magic %r)' % (cfile, data[:4]))
                    arc = '%s/%s' % (PACKAGE, rel[:-3] + '.pyc')
                    info = zipfile.ZipInfo(arc, time.localtime(os.path.getmtime(src))[:6])
                    info.compress_type = zipfile.ZIP_DEFLATED
                    z.writestr(info, data)
                    entries.append(arc)
            os.replace(part, dist)
        finally:
            if os.path.exists(part):          # a failed build leaves the previous dist untouched
                os.remove(part)
    return {'dist': dist, 'entries': entries, 'bytes': os.path.getsize(dist), 'python': rep['version'],
            'magic': rep['magic'], 'seconds': time.perf_counter() - t0}


def verify(dist=DIST):
    """Check a built archive: every entry is novulon/<relpath>.pyc with magic 3394, no .py.
    Returns a list of problems (empty = fine)."""
    problems = []
    with zipfile.ZipFile(dist) as z:
        names = z.namelist()
        if not names:
            problems.append('empty archive')
        for n in names:
            if not (n.startswith(PACKAGE + '/') and n.endswith('.pyc')):
                problems.append('unexpected entry %s' % n)
            elif not magic_ok(z.read(n)):
                problems.append('bad magic in %s' % n)
        if PACKAGE + '/__init__.pyc' not in names:
            problems.append('missing %s/__init__.pyc' % PACKAGE)
    return problems


def main():
    r = build()
    problems = verify(r['dist'])
    print('built %s: %d modules, %d bytes, %.1f s, compiled by game Python %s (magic %s)' % (
        r['dist'], len(r['entries']), r['bytes'], r['seconds'], (r['python'] or '').split()[0], r['magic']))
    for e in r['entries']:
        print('  ' + e)
    if problems:
        print('PROBLEMS:', *problems, sep='\n  ')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
